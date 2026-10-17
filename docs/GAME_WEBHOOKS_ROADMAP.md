# Game webhooks implementation roadmap

Status: implemented in the backend; frontend controls are deferred.

## Summary

Add one optional webhook per game, configured through direct game creation or
host-only lobby settings. Support two formats:

- **Discord:** short messages posted directly to a channel.
- **JSON:** structured notifications for bots and other integrations.

Support two notification modes: **decision changes** (default) and **every game
update**. This roadmap covers the backend API and documentation only.

## 1. Configuration and public API

Add an optional `webhook` object to game creation, lobby creation, and lobby
settings:

```json
{
  "webhook": {
    "url": "https://discord.com/api/webhooks/...",
    "format": "discord",
    "mode": "decision_changes"
  }
}
```

- `format`: `discord` or `json`.
- `mode`: `decision_changes` or `state_changes`; default to `decision_changes`.
- Omission disables webhooks at creation. In lobby settings, omission preserves
  the configuration; explicit `null` removes it.
- Lobby changes remain host-only and restricted to the existing lobby settings
  phase. Configuration carries into the created game. Do not send draft
  notifications or add an in-match configuration endpoint in v1.
- Store configuration privately on managed games/lobbies, outside engine state.
  Persist game configuration with existing saves; older saves default to
  disabled. Never expose URLs through views, broadcasts, replays, logs, or
  validation-error details.

## 2. Message formats

Use hero names with optional player names: `Hanu (Sebastian)`, falling back to
`Hanu`.

Example messages:

- `Hanu (Sebastian)'s turn.`
- `New turn. Hanu (Sebastian), Arien (Alex): choose your cards.`
- `Waiting for Hanu (Sebastian), Arien (Alex).`
- `Board updated. Waiting for Hanu (Sebastian).`
- `Game over. RED wins.`

Discord delivery uses `content`, with `allowed_mentions.parse` empty and an
explicit `users` allowlist for the heroes currently being waited on. Accept
optional numeric Discord user IDs separately from display names: direct game
creation uses `discord_user_ids` keyed by hero name; lobby creation/joining uses
`discord_user_id` per player, transferred to their claimed hero. Names remain
readable and are escaped; only the separate IDs generate user mentions. An incoming
webhook needs no bot installation. Document how to create a channel webhook and
paste its URL. See the [Discord webhook API](https://github.com/discord/discord-api-docs/blob/main/developers/resources/webhook.mdx).

JSON callbacks contain `version`, `event_id`, `game_id`, `event`, `occurred_at`,
`round`, `turn`, `phase`, `awaiting_heroes` (IDs, hero names, optional player
names and optional Discord user IDs), `winner`, and the same human-readable `message`. Include no board
snapshot, private choices, input options, or game-access tokens.

## 3. Trigger detection

- Add a shared observer to the registry's save path, before its
  persistence-disabled early return. This covers REST, WebSocket, automatic
  timeouts, rollback, and overrides without adding engine hooks.
- Observe the completed state under the game lock; enqueue an immutable
  notification without performing network I/O.
- Determine waiting heroes from existing input visibility helpers, including
  team decisions, simultaneous choices, and Hanu control. During planning,
  include heroes whose planning is incomplete, respecting second-card rules.
  During timed ready checks, include players still required to ready.
- **Decision changes:** notify when the waiting set, phase, round, or turn
  changes. Repeated choices by the same hero within that boundary stay quiet.
  Announce game completion once.
- **State changes:** send one notification per changed state observed at an
  action boundary, regardless of whether decision makers changed. Combine
  overlapping triggers into one message.
- Compare a canonical internal state fingerprint, excluding clock bookkeeping
  but including meaningful clock status/readiness. Repeated saves, rejected
  actions without a game change, reads, reconnects, pointers, and pings produce
  no notifications. Internal engine steps are not separate updates.
- Send an initial notification when the game is registered. On restore,
  initialize comparison baselines without sending startup notifications.

## 4. Background delivery

- Use an application-managed dispatcher and shared asynchronous HTTP client;
  promote `httpx` to a runtime dependency. Preserve order per game while
  allowing different games to deliver concurrently.
- Use a five-second request timeout and at most three attempts. Retry network
  failures and server errors with backoff; honor rate-limit retry delays. Other
  client errors stop that delivery. See [Discord rate limits](https://github.com/discord/discord-api-docs/blob/main/developers/topics/rate-limits.mdx).
- Failures never fail or delay gameplay. Log game ID, event ID, and outcome
  without destination credentials.
- Accept public HTTPS destinations only. Reject credentials in URL authority,
  private/local addresses, and redirects. Validate resolved addresses and
  connect to a validated address to prevent DNS rebinding. Discord format
  additionally requires a recognized Discord webhook URL.
- Delivery is best effort. Pending messages may be lost during restart; retries
  may duplicate delivery. JSON consumers can deduplicate using `event_id`.

## 5. Verification and documentation

- Test request validation, host-only lobby settings, removal, transfer to games,
  persistence, legacy saves, and credential redaction.
- Test single/team/simultaneous decisions, planning completion, second cards,
  Hanu control, same-player new turns, and game completion.
- Verify REST, WebSocket, timeout, rollback, and override paths. Confirm duplicate
  saves and clock-only bookkeeping remain quiet.
- Mock outbound HTTP to verify exact Discord/JSON payloads, ordering, retries,
  rate limits, timeout isolation, destination restrictions, and restart
  behavior.
- Run server tests before and after implementation:
  `uv run pytest tests/server/ -q` (the project config supplies `src` on the
  Python path).
- Update `docs/CLIENT_INTEGRATION_GUIDE.md` with configuration, Discord setup,
  payload examples, trigger semantics, and delivery limitations.

## Defaults and exclusions

Defaults are one destination, decision-change notifications, Discord pings only
for explicitly supplied user IDs, and best-effort delivery. Do not add a durable queue, callback signing, frontend
controls, or full-state payloads in v1.
