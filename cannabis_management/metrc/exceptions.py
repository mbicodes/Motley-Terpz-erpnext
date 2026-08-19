# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Exception hierarchy for the Metrc integration.

The split matters operationally: `TERMINAL_ERRORS` never get retried by the
outbox worker because no amount of retrying fixes bad data or bad keys, while
everything else is transient and worth backing off on.
"""


class MetrcError(Exception):
    """Base for every Metrc failure."""

    def __init__(self, message, status_code=None, body=None, endpoint=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.endpoint = endpoint


class MetrcNotConfigured(MetrcError):
    """Settings missing, integration disabled, or licence not configured."""


class MetrcAuthError(MetrcError):
    """401 / 403 — wrong keys or wrong environment. Never retry."""


class MetrcValidationError(MetrcError):
    """400 — Metrc rejected the data. A human must fix it. Never retry."""


class MetrcPayloadTooLargeError(MetrcError):
    """413 — more than 10 objects in the array. A bug in our chunker."""


class MetrcRateLimitError(MetrcError):
    """429 — back off, honouring Retry-After when present."""

    def __init__(self, message, retry_after=None, **kw):
        super().__init__(message, **kw)
        self.retry_after = retry_after


class MetrcServerError(MetrcError):
    """5xx or a network failure. Retry with backoff."""


# Errors that will never succeed on retry — the outbox parks these immediately.
TERMINAL_ERRORS = (
    MetrcAuthError,
    MetrcValidationError,
    MetrcPayloadTooLargeError,
    MetrcNotConfigured,
)
