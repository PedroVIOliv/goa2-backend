"""Rebuild already-baked shares as keyframe groups.

    PYTHONPATH=src python -m goa2.scripts.migrate_shares [--dry-run]

Reads each share's baked positions and rewrites them as groups, keeping the
token so links already handed out keep working. Nothing is re-simulated, so a
share cannot change meaning because the engine moved on since it was minted.

Shares already in the new format are skipped, which makes the command safe to
re-run — including after an interrupted one.
"""

from __future__ import annotations

import argparse
import sys

from goa2.server import shares


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="List what would be converted and stop"
    )
    args = parser.parse_args(argv)

    pending = [m for m in shares.list_shares() if not shares.is_grouped(m)]
    if not pending:
        print("Nothing to do: every share is already stored as groups.")
        return 0

    before = sum(int(m.get("size_bytes") or 0) for m in pending)
    print(f"{len(pending)} share(s) to convert, {before / 1e6:.1f} MB")
    if args.dry_run:
        for meta in pending:
            print(f"  {meta['token']}  {meta.get('total_decisions', 0)} decisions")
        return 0

    after = 0
    for meta in pending:
        token = meta["token"]
        was = int(meta.get("size_bytes") or 0)
        try:
            updated = shares.migrate_share_to_groups(token)
        except Exception as e:  # one damaged share must not abort the rest
            print(f"  {token}  FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if updated is None:
            print(f"  {token}  skipped")
            continue
        now = int(updated["size_bytes"])
        after += now
        ratio = f"{was / now:.0f}x" if now else "-"
        print(
            f"  {token}  {was / 1e6:5.2f} MB -> {now / 1024:6.0f} KB  ({ratio}, "
            f"{len(updated['groups'])} groups)"
        )

    if after:
        print(f"total {before / 1e6:.1f} MB -> {after / 1024:.0f} KB ({before / after:.0f}x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
