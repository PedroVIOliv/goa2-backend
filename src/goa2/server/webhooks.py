"""Private webhook configuration, change detection, and best-effort delivery."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import math
import re
import socket
import uuid
from collections import deque
from contextlib import suppress
from contextvars import ContextVar
from datetime import UTC, datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import TYPE_CHECKING, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from goa2.domain.models import GamePhase
from goa2.domain.time_control import ClockStatus
from goa2.domain.types import HeroID
from goa2.engine.phases import planning_complete
from goa2.server.visibility import awaiting_input_hero_ids

if TYPE_CHECKING:
    from goa2.server.registry import ManagedGame

logger = logging.getLogger(__name__)
DISCORD_ID_PATTERN = r"[1-9][0-9]{16,19}"
_sending_webhook: ContextVar[bool] = ContextVar("sending_webhook", default=False)


class _WebhookLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # httpx logs complete request URLs at INFO, including webhook credentials.
        return not _sending_webhook.get()


logging.getLogger("httpx").addFilter(_WebhookLogFilter())


def validate_discord_user_id(value: str | None) -> str | None:
    if value is not None and not re.fullmatch(DISCORD_ID_PATTERN, value):
        raise ValueError("discord_user_id must be a numeric Discord user ID (17-20 digits)")
    return value


def _public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    # Do not allow IPv4-in-IPv6 transition mechanisms to bypass IPv4 checks.
    return (
        ip.is_global
        and not ip.is_multicast
        and not (
            isinstance(ip, ipaddress.IPv6Address)
            and (ip.ipv4_mapped is not None or ip.sixtofour is not None or ip.teredo is not None)
        )
    )


def validate_url(value: str) -> httpx.URL:
    try:
        url = httpx.URL(value)
        if (
            url.scheme != "https"
            or not url.host
            or url.userinfo
            or url.fragment
            or any(ord(c) < 33 for c in value)
            or len(value) > 2048
        ):
            raise ValueError
        host = url.host.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if not _public_ip(host):
                raise ValueError
    except (ValueError, httpx.InvalidURL):
        raise ValueError(
            "webhook URL must be a public HTTPS URL without credentials or fragment"
        ) from None
    return url


class WebhookConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    url: SecretStr
    format: Literal["discord", "json"]
    mode: Literal["decision_changes", "state_changes"] = "decision_changes"

    @field_validator("url")
    @classmethod
    def _url(cls, value: SecretStr) -> SecretStr:
        validate_url(value.get_secret_value())
        return value

    @field_validator("format")
    @classmethod
    def _format(cls, value: str, info: Any) -> str:
        secret = info.data.get("url")
        if value == "discord" and secret is not None:
            url = validate_url(secret.get_secret_value())
            if (
                url.host not in {"discord.com", "canary.discord.com", "ptb.discord.com"}
                or url.port not in (None, 443)
                or not re.fullmatch(r"/api(?:/v[0-9]+)?/webhooks/[0-9]+/[A-Za-z0-9_-]+", url.path)
                or any(key not in {"thread_id", "wait"} for key in url.params)
            ):
                raise ValueError("discord format requires a Discord incoming webhook URL")
        return value

    def private_dump(self) -> dict[str, str]:
        """Only for the private save file, never responses or replay records."""
        return {"url": self.url.get_secret_value(), "format": self.format, "mode": self.mode}


def waiting_heroes(game: ManagedGame) -> list[str]:
    state = game.session.state
    if state.phase == GamePhase.GAME_OVER:
        return []
    clock = state.clock
    if clock and clock.status in {
        ClockStatus.WAITING_FOR_PLAYERS,
        ClockStatus.PAUSED,
        ClockStatus.SUSPENDED_FOR_INACTIVITY,
    }:
        return sorted(set(game.hero_to_token) - set(clock.ready_hero_ids))
    if state.phase == GamePhase.PLANNING:
        return sorted(
            str(hero.id)
            for team in state.teams.values()
            for hero in team.heroes
            if not planning_complete(state, hero.id)
        )
    request = game.last_result.input_request if game.last_result else None
    if request is not None:
        return sorted(awaiting_input_hero_ids(request, state))
    return [str(state.current_actor_id)] if state.current_actor_id is not None else []


def _without_step_input(value: Any) -> Any:
    """Ignore correlation IDs and buffered submissions, including on nested steps.

    A rejected selection can remain in pending_input when the same prompt is
    reissued. Accepted choices change the step's progress or execution context.
    """
    if isinstance(value, list):
        return [_without_step_input(item) for item in value]
    if isinstance(value, dict):
        is_step = "step_id" in value and "type" in value
        return {
            key: _without_step_input(item)
            for key, item in value.items()
            if not (is_step and key in {"pending_request_id", "pending_input"})
        }
    return value


def _fingerprint(game: ManagedGame) -> str:
    state = game.session.state
    data = state.model_dump(mode="json", exclude={"clock"})
    data["execution_stack"] = _without_step_input(data["execution_stack"])
    data["input_stack"] = [
        request.model_dump(mode="json", exclude={"id"}) for request in state.input_stack
    ]
    request = game.last_result.input_request if game.last_result else None
    data["server_input_request"] = (
        request.model_dump(mode="json", exclude={"id"}) if request else None
    )
    if state.clock:
        data["clock"] = {
            "status": state.clock.status.value,
            "ready_hero_ids": sorted(state.clock.ready_hero_ids),
        }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _escape(value: str) -> str:
    return re.sub(r"([\\`*_~|<>\[\]])", r"\\\1", value).replace("\n", " ").replace("\r", " ")


def _message(game: ManagedGame, event: str, heroes: list[dict[str, Any]], *, discord: bool) -> str:
    state = game.session.state
    names = []
    for hero in heroes:
        name = _escape(hero["hero_name"]) if discord else hero["hero_name"]
        player = hero["player_name"]
        if player:
            name += f" ({_escape(player) if discord else player})"
        if discord and hero["discord_user_id"]:
            name += f" <@{hero['discord_user_id']}>"
        names.append(name)
    waiting = ", ".join(names)
    if state.phase == GamePhase.GAME_OVER:
        return f"Game over. {state.winner.value} wins." if state.winner else "Game over."
    if state.clock and state.clock.status != ClockStatus.RUNNING:
        return (
            f"Waiting for {waiting} to ready up." if waiting else "Waiting for the game to resume."
        )
    if event == "game_created":
        return f"Game created. Waiting for {waiting}." if waiting else "Game created."
    if event == "new_turn" and state.phase == GamePhase.PLANNING:
        return f"New turn. {waiting}: choose your cards."
    if event == "state_changed":
        return f"Board updated. Waiting for {waiting}." if waiting else "Board updated."
    if len(names) == 1:
        return f"{names[0]}'s turn."
    return f"Waiting for {waiting}." if waiting else "Game updated."


def observe_game(game: ManagedGame, *, baseline_only: bool = False) -> dict[str, Any] | None:
    """Capture one immutable notification at a completed mutation boundary."""
    if game.webhook is None:
        return None
    state = game.session.state
    waiting = waiting_heroes(game)
    key = (state.round, state.turn, state.phase.value, tuple(waiting), state.winner)
    fingerprint = _fingerprint(game)
    previous_key = game.webhook_decision_key
    previous_fingerprint = game.webhook_fingerprint
    game.webhook_decision_key = key
    game.webhook_fingerprint = fingerprint
    if baseline_only or fingerprint == previous_fingerprint:
        return None
    if previous_key is None:
        event = "game_created"
    elif state.phase == GamePhase.GAME_OVER and previous_key[2] != GamePhase.GAME_OVER.value:
        event = "game_over"
    elif previous_key[:2] != key[:2]:
        event = "new_turn"
    elif previous_key != key:
        event = "decision_changed"
    elif game.webhook.mode == "state_changes":
        event = "state_changed"
    else:
        return None
    heroes = []
    for hero_id in waiting:
        hero = state.get_hero(HeroID(hero_id))
        if hero is not None:
            heroes.append(
                {
                    "hero_id": hero_id,
                    "hero_name": hero.name,
                    "player_name": game.hero_names.get(hero_id),
                    "discord_user_id": game.discord_user_ids.get(hero_id),
                }
            )
    payload = {
        "version": 1,
        "event_id": uuid.uuid4().hex,
        "game_id": game.game_id,
        "event": event,
        "occurred_at": datetime.now(UTC).isoformat(),
        "round": state.round,
        "turn": state.turn,
        "phase": state.phase.value,
        "awaiting_heroes": heroes,
        "winner": state.winner.value if state.winner else None,
        "message": _message(game, event, heroes, discord=game.webhook.format == "discord"),
    }
    if game.webhook.format == "discord":
        return {
            "content": payload["message"],
            "allowed_mentions": {
                "parse": [],
                "users": sorted({h["discord_user_id"] for h in heroes if h["discord_user_id"]}),
            },
        }
    return payload


async def resolve_public_addresses(host: str, port: int) -> list[str]:
    answers = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses or not all(_public_ip(address) for address in addresses):
        raise ValueError("webhook destination did not resolve exclusively to public addresses")
    return addresses


class WebhookDispatcher:
    """Bounded queues, ordered per game. Pending deliveries are not durable."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        # This dispatcher owns the client. IP pinning collapses different DNS
        # origins onto one cookie scope, so neither store nor send cookies.
        self.client.cookies = CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))
        self.queues: dict[str, deque[tuple[WebhookConfig, dict[str, Any], str]]] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.slots = asyncio.Semaphore(8)
        self.closed = False

    def enqueue(self, game_id: str, config: WebhookConfig, payload: dict[str, Any]) -> None:
        if self.closed:
            return
        queue = self.queues.setdefault(game_id, deque())
        event_id = str(payload.get("event_id") or uuid.uuid4().hex)
        if len(queue) >= 100:
            logger.warning("Webhook queue full game=%s event=%s", game_id, event_id)
            return
        queue.append((config, payload, event_id))
        if game_id not in self.tasks:
            self.tasks[game_id] = asyncio.create_task(self._worker(game_id))

    def cancel_game(self, game_id: str) -> None:
        task = self.tasks.pop(game_id, None)
        self.queues.pop(game_id, None)
        if task:
            task.cancel()

    async def close(self) -> None:
        self.closed = True
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        self.queues.clear()

    async def _worker(self, game_id: str) -> None:
        try:
            queue = self.queues[game_id]
            while queue:
                config, payload, event_id = queue.popleft()
                await self._deliver(game_id, config, payload, event_id)
        finally:
            if self.tasks.get(game_id) is asyncio.current_task():
                self.queues.pop(game_id, None)
                self.tasks.pop(game_id, None)

    async def _deliver(
        self,
        game_id: str,
        config: WebhookConfig,
        payload: dict[str, Any],
        event_id: str,
    ) -> None:
        for attempt in range(3):
            delay = float(2**attempt)
            outcome = "network_error"
            try:
                async with self.slots:
                    async with asyncio.timeout(5):
                        deadline = asyncio.get_running_loop().time() + 5
                        url = validate_url(config.url.get_secret_value())
                        addresses = await resolve_public_addresses(url.host, url.port or 443)
                        if config.format == "discord":
                            url = url.copy_set_param("wait", "true")
                        for index, address in enumerate(addresses):
                            # Reserve connection time for remaining addresses, so an
                            # unreachable IPv6 route cannot consume the whole attempt.
                            remaining = max(0.001, deadline - asyncio.get_running_loop().time())
                            try:
                                status, retry_after = await self._send_to_address(
                                    url,
                                    address,
                                    payload,
                                    event_id,
                                    connect_timeout=remaining / (len(addresses) - index),
                                )
                                break
                            except (httpx.ConnectError, httpx.ConnectTimeout):
                                if index == len(addresses) - 1:
                                    raise
                outcome = str(status)
                if 200 <= status < 300:
                    logger.info("Webhook delivered game=%s event=%s", game_id, event_id)
                    return
                if status == 429:
                    with suppress(ValueError):
                        delay = float(retry_after or delay)
                    if not math.isfinite(delay) or delay < 0:
                        delay = float(2**attempt)
                elif status < 500:
                    logger.warning(
                        "Webhook failed game=%s event=%s status=%s", game_id, event_id, outcome
                    )
                    return
            except ValueError:
                logger.warning("Webhook destination rejected game=%s event=%s", game_id, event_id)
                return
            except (httpx.HTTPError, OSError, TimeoutError):
                pass
            except Exception:
                # Never log exception text: HTTP libraries can embed the secret URL.
                logger.warning("Webhook delivery error game=%s event=%s", game_id, event_id)
                return
            if attempt < 2:
                await asyncio.sleep(delay)
        logger.warning(
            "Webhook exhausted retries game=%s event=%s status=%s", game_id, event_id, outcome
        )

    async def _send_to_address(
        self,
        url: httpx.URL,
        address: str,
        payload: dict[str, Any],
        event_id: str,
        *,
        connect_timeout: float,
    ) -> tuple[int, str | None]:
        # Connect to the validated IP, retaining the original TLS identity and
        # HTTP host. No second DNS lookup, redirects, or environment proxy.
        request = self.client.build_request(
            "POST",
            url.copy_with(host=address),
            json=payload,
            headers={"Host": url.netloc.decode("ascii"), "X-GoA2-Event-ID": event_id},
            extensions={"sni_hostname": url.host},
            timeout=httpx.Timeout(5, connect=connect_timeout),
        )
        # Stream and discard response bodies to bound memory use.
        token = _sending_webhook.set(True)
        try:
            response = await self.client.send(request, stream=True, follow_redirects=False)
            try:
                return response.status_code, response.headers.get("Retry-After")
            finally:
                await response.aclose()
        finally:
            _sending_webhook.reset(token)
