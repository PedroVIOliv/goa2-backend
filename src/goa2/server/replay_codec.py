"""Engine-independent keyframe/JSON Patch groups shared by all replay readers."""

from __future__ import annotations

import gzip
import json
import zlib
from copy import deepcopy
from typing import Any

import brotli
import jsonpatch


def dumps(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def encode(group: dict[str, Any], *, quality: int = 9) -> bytes:
    return brotli.compress(dumps(group), quality=quality)


def decode(data: bytes) -> dict[str, Any]:
    group = json.loads(brotli.decompress(data))
    if not isinstance(group, dict) or not {"start", "keyframe", "patches"} <= group.keys():
        raise ValueError("Invalid replay group")
    return group


def for_delivery(stored: bytes, *, accepts_brotli: bool) -> tuple[bytes, str]:
    if accepts_brotli:
        return stored, "br"
    return gzip.compress(brotli.decompress(stored), 6), "gzip"


def reconstruct(group: dict[str, Any], index: int) -> Any:
    offset = index - group["start"]
    if not 0 <= offset <= len(group["patches"]):
        raise ValueError("Position outside replay group")
    value = deepcopy(group["keyframe"])
    for patch in group["patches"][:offset]:
        value = apply_patch(value, patch)
    return value


def apply_patch(value: Any, patch: list[dict[str, Any]]) -> Any:
    # jsonpatch assigns operation values by reference. Later nested patches
    # must not mutate the captured operation values or other readers' groups.
    return jsonpatch.apply_patch(value, deepcopy(patch), in_place=True)


def project_member(group: dict[str, Any], member: str) -> dict[str, Any]:
    """Project a member of a group whose patches stay within member boundaries.

    The live writer partitions diffs by viewer. Strip that prefix before
    applying patches, so reading one seat never expands every other seat.
    Reject cross-member moves rather than silently building an incorrect view.
    """
    prefix = "/" + member.replace("~", "~0").replace("/", "~1")

    def inside(path: str) -> bool:
        return path == prefix or path.startswith(prefix + "/")

    patches = []
    for patch in group["patches"]:
        scoped = []
        for operation in patch:
            path = operation["path"]
            if path == "" and operation["op"] in ("add", "replace"):
                scoped.append({"op": "replace", "path": "", "value": operation["value"][member]})
            elif inside(path):
                copied = {**operation, "path": path[len(prefix) :]}
                if "from" in copied:
                    if not inside(copied["from"]):
                        raise ValueError("Cross-member replay patch")
                    copied["from"] = copied["from"][len(prefix) :]
                scoped.append(copied)
            elif "from" in operation and inside(operation["from"]):
                raise ValueError("Cross-member replay patch")
        patches.append(scoped)
    return {"start": group["start"], "keyframe": group["keyframe"][member], "patches": patches}


def reconstruct_many(group: dict[str, Any], indices: list[int]) -> dict[int, Any]:
    """Walk a group once instead of replaying its prefix for every position."""
    result = {}
    value = deepcopy(group["keyframe"])
    cursor = group["start"]
    for target in sorted(set(indices)):
        if not cursor <= target <= group["start"] + len(group["patches"]):
            raise ValueError("Position outside replay group")
        while cursor < target:
            value = apply_patch(value, group["patches"][cursor - group["start"]])
            cursor += 1
        result[target] = deepcopy(value)
    return result


def _equal(before: Any, after: Any, memo: dict[tuple[int, int], bool]) -> bool:
    if before is after:
        return True
    if type(before) is not type(after) or before != after:
        return False
    pair = (id(before), id(after))
    if pair in memo:
        return memo[pair]
    same = True
    if isinstance(before, dict):
        same = all(_equal(before[key], after[key], memo) for key in before)
    elif isinstance(before, list):
        same = all(_equal(a, b, memo) for a, b in zip(before, after, strict=True))
    memo[pair] = same
    return same


def make_patch(
    before: Any, after: Any, path: str = "", _memo: dict | None = None
) -> list[dict[str, Any]]:
    """Prune equal view subtrees before asking jsonpatch to diff changed leaves.

    jsonpatch otherwise walks (and JSON-encodes) every unchanged board tile and
    card for every viewer. Equal-length containers can be partitioned safely;
    structural edits and all operation semantics remain the library's job.
    """
    memo = {} if _memo is None else _memo
    if _equal(before, after, memo):
        return []
    children: list[tuple[str, Any, Any]] = []
    if isinstance(before, dict) and isinstance(after, dict) and before.keys() == after.keys():
        children = [
            (str(key).replace("~", "~0").replace("/", "~1"), before[key], after[key])
            for key in before
            if not _equal(before[key], after[key], memo)
        ]
    elif isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        children = [
            (str(i), old, new)
            for i, (old, new) in enumerate(zip(before, after, strict=True))
            if not _equal(old, new, memo)
        ]
    if children:
        return [
            op for key, old, new in children for op in make_patch(old, new, path + "/" + key, memo)
        ]
    operations = jsonpatch.make_patch(before, after).patch
    for operation in operations:
        operation["path"] = path + operation["path"]
        if "from" in operation:
            operation["from"] = path + operation["from"]
    return operations


class GroupBuilder:
    """Append positions; return a closed group when the next keyframe is due.

    The budget matches the original share format. A rejected final patch becomes
    the next keyframe, keeping the old representation and boundary semantics.
    """

    def __init__(
        self,
        start: int,
        value: Any,
        *,
        max_patches: int = 512,
        check_every: int = 8,
        budget_multiple: int = 2,
        copy_values: bool = True,
    ) -> None:
        self.copy_values = copy_values
        self.max_patches = max_patches
        self.check_every = check_every
        self.budget_multiple = budget_multiple
        self._start_group(start, value)

    def _start_group(self, start: int, value: Any) -> None:
        self.group = {
            "start": start,
            "keyframe": deepcopy(value) if self.copy_values else value,
            "patches": [],
        }
        self.previous = deepcopy(value) if self.copy_values else value
        self._keyframe_raw = dumps(value)
        self._init_proxy()
        self._patch_bytes: list[bytes] = []

    def _init_proxy(self) -> None:
        # The immutable keyframe dominates the group. Copying the compression
        # state lets every eighth budget check compress only the small patches.
        self._compressor = zlib.compressobj(1, wbits=31)
        self._proxy_prefix_size = len(self._compressor.compress(self._keyframe_raw))
        self._keyframe_size = self._proxy_prefix_size + len(self._compressor.copy().flush())

    def __getstate__(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "_compressor"}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._init_proxy()

    def append(self, index: int, value: Any) -> dict[str, Any] | None:
        if index != self.group["start"] + len(self.group["patches"]) + 1:
            raise ValueError("Replay positions must be consecutive")
        patch = make_patch(self.previous, value)
        self.group["patches"].append(patch)
        self._patch_bytes.append(dumps(patch))
        count = len(self._patch_bytes)
        over = count >= self.max_patches
        if not over and count % self.check_every == 0:
            proxy = self._compressor.copy()
            size = (
                self._proxy_prefix_size
                + len(proxy.compress(b"".join(self._patch_bytes)))
                + len(proxy.flush())
            )
            over = size - self._keyframe_size > self.budget_multiple * self._keyframe_size
        if over:
            self.group["patches"].pop()
            closed = self.group
            self._start_group(index, value)
            return closed
        self.previous = deepcopy(value) if self.copy_values else value
        return None

    @classmethod
    def restore(cls, group: dict[str, Any], *, copy_values: bool = True) -> GroupBuilder:
        builder = cls(group["start"], group["keyframe"], copy_values=copy_values)
        # Rebuild bookkeeping without re-diffing or changing existing boundaries.
        builder.group = deepcopy(group)
        builder._patch_bytes = [dumps(patch) for patch in group["patches"]]
        builder.previous = reconstruct(group, group["start"] + len(group["patches"]))
        return builder
