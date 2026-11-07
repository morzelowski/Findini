"""Jednolity format błędów API: {"error": {"code": ..., "message": ...}} z komunikatem po polsku."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra or {}


def not_found(what: str = "Nie znaleziono zasobu.") -> ApiError:
    return ApiError(404, "not_found", what)


def forbidden(msg: str = "Brak uprawnień do tego zasobu.") -> ApiError:
    return ApiError(403, "forbidden", msg)


def conflict(code: str, msg: str) -> ApiError:
    return ApiError(409, code, msg)


def invalid(code: str, msg: str) -> ApiError:
    return ApiError(422, code, msg)
