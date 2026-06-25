from __future__ import annotations


class DraftError(Exception):
    status_code: int = 400


class DraftNotFoundError(DraftError):
    status_code = 404


class PlayerNotFoundError(DraftError):
    status_code = 404


class DraftFullError(DraftError):
    status_code = 409


class NotHostError(DraftError):
    status_code = 403


class NotActingCaptainError(DraftError):
    status_code = 403


class InvalidDraftPhaseError(DraftError):
    status_code = 409


class HeroUnavailableError(DraftError):
    status_code = 409


class HeroNotClaimableError(DraftError):
    status_code = 409


class InvalidTeamError(DraftError):
    status_code = 400
