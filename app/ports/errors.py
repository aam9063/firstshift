"""Shared error taxonomy for every port (design/integration-contracts.md).

Every adapter raises one of these typed errors, never a raw HTTP error. The
outbox relay maps them to retry or dead-letter decisions:

- PortTransientError: retry with the default backoff.
- PortRateLimitedError: wait per the signal, then retry.
- PortValidationError: never retried; a task goes to a human.
- PortProtocolError: no retry; alert IT.
- PortAuthError: no retry; page IT.
"""

from __future__ import annotations


class PortError(RuntimeError):
    """Base class for every typed port failure."""


class PortTransientError(PortError):
    """Timeout, 5xx or network problem: retryable with backoff."""


class PortRateLimitedError(PortTransientError):
    """Explicit throttle signal: wait per the signal, then retry."""


class PortValidationError(PortError):
    """The client system rejected the payload: never retried, task for a
    human with the field errors."""


class PortProtocolError(PortError):
    """A response that does not match the documentation: no retry, alert IT."""


class PortAuthError(PortError):
    """Credentials or gateway rejected the call: no retry, page IT."""
