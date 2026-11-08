"""Single error format (§10.8): {"error": {"code": ..., "message_fr": ...}}."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message_fr: str, extra: dict | None = None):
        super().__init__(message_fr)
        self.status_code = status_code
        self.code = code
        self.message_fr = message_fr
        self.extra = extra or {}


def error_body(code: str, message_fr: str, **extra) -> dict:
    return {"error": {"code": code, "message_fr": message_fr, **extra}}


_DEFAULT_CODES = {
    400: ("bad_request", "Requête invalide."),
    401: ("unauthorized", "Authentification requise."),
    403: ("forbidden", "Action non autorisée."),
    404: ("not_found", "Ressource introuvable."),
    405: ("method_not_allowed", "Méthode non autorisée."),
    409: ("conflict", "Conflit avec l'état du serveur."),
    422: ("validation_error", "Données invalides."),
    429: ("rate_limited", "Trop de requêtes, réessayez dans une minute."),
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content=error_body(exc.code, exc.message_fr, **exc.extra)
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, msg = _DEFAULT_CODES.get(exc.status_code, ("http_error", "Erreur."))
        return JSONResponse(
            status_code=exc.status_code, content=error_body(code, msg), headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg", "")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", "Données invalides.", details=details),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        # Concurrent writes (same client UUID inserted twice at the same time) end up here.
        log.warning("integrity error: %s", exc.orig)
        return JSONResponse(
            status_code=409,
            content=error_body("conflict", "Conflit avec l'état du serveur, réessayez."),
        )

    @app.exception_handler(Exception)
    async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        # Same JSON format as every other error (§10.8); details only in the server log.
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=500, content=error_body("internal_error", "Erreur interne du serveur.")
        )
