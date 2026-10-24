from __future__ import annotations

import re
import secrets
from contextvars import ContextVar, Token
from dataclasses import dataclass

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    client_ip: str


_context: ContextVar[RequestContext | None] = ContextVar(
    "request_context",
    default=None,
)


def new_request_context(request) -> tuple[RequestContext, Token]:
    supplied = request.headers.get("x-request-id", "")
    request_id = (
        supplied
        if _REQUEST_ID_PATTERN.fullmatch(supplied)
        else secrets.token_hex(12)
    )
    client_ip = request.headers.get("x-real-ip") or (
        request.client.host if request.client else ""
    )
    context = RequestContext(request_id=request_id, client_ip=client_ip[:64])
    return context, _context.set(context)


def reset_request_context(token: Token) -> None:
    _context.reset(token)


def current_request_id() -> str:
    context = _context.get()
    return context.request_id if context else ""


def current_client_ip() -> str:
    context = _context.get()
    return context.client_ip if context else ""
