"""Bug-report endpoints.

Two routers live here:

- ``public_router`` — the in-game submit endpoint. Always registered; requires
  the game's own bearer token (player or spectator) like every other game
  route. Nothing from the client is trusted except title and description: the
  replay position is computed server-side at submit time.
- ``admin_router`` — triage endpoints (list / resolve / delete). Registered
  and gated exactly like the replay debugger: see ``server/admin.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from goa2.server import bug_reports
from goa2.server.admin import require_admin
from goa2.server.auth import PlayerDep, RegistryDep
from goa2.server.models import BugReportResponse, SubmitBugReportRequest

public_router = APIRouter(prefix="/games", tags=["bug-reports"])
admin_router = APIRouter(
    prefix="/bug-reports", tags=["bug-reports"], dependencies=[Depends(require_admin)]
)


@public_router.post("/{game_id}/bug-reports", status_code=201, response_model=BugReportResponse)
def submit_bug_report(
    game_id: str,
    body: SubmitBugReportRequest,
    player: PlayerDep,
    registry: RegistryDep,
) -> BugReportResponse:
    game = registry.get(game_id)  # 404 via GameNotFoundError if unknown
    if bug_reports.count_reports_for_game(game_id) >= bug_reports.MAX_REPORTS_PER_GAME:
        raise HTTPException(
            status_code=429,
            detail=f"Report limit reached for this game " f"({bug_reports.MAX_REPORTS_PER_GAME})",
        )
    state = game.session.state
    report = bug_reports.create_report(
        game_id=game_id,
        title=body.title,
        description=body.description,
        reporter_hero=None if player.is_spectator else player.hero_id,
        decision_index=bug_reports.count_replay_decisions(game_id),
        round_num=state.round,
        turn=state.turn,
    )
    return BugReportResponse(**report)


@admin_router.get("", response_model=list[BugReportResponse])
def list_bug_reports() -> list[BugReportResponse]:
    return [BugReportResponse(**r) for r in bug_reports.list_reports()]


@admin_router.patch("/{report_id}", response_model=BugReportResponse)
def update_bug_report(report_id: str, body: dict) -> BugReportResponse:
    status = body.get("status")
    if status not in ("open", "resolved"):
        raise HTTPException(status_code=422, detail="status must be 'open' or 'resolved'")
    try:
        report = bug_reports.set_status(report_id, status)
    except FileNotFoundError:
        report = None
    if report is None:
        raise HTTPException(status_code=404, detail=f"Bug report '{report_id}' not found")
    return BugReportResponse(**report)


@admin_router.delete("/{report_id}", status_code=204)
def delete_bug_report(report_id: str) -> None:
    try:
        deleted = bug_reports.delete_report(report_id)
    except FileNotFoundError:
        deleted = False
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Bug report '{report_id}' not found")
