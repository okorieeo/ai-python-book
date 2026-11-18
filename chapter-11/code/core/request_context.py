"""Holds the id of the request being handled, so logs anywhere in the code can include it."""
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
