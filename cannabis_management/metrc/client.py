# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Metrc Web API v2 transport layer.

Handles the five things the Metrc API forces on every integrator:

  * HTTP Basic auth where username = integrator key, password = user key.
  * Query-string encoding. A "+" in a timestamp offset MUST arrive as %2B or
    Metrc silently misreads the date and returns the wrong window of data.
  * Two response shapes. Passing pageSize wraps rows in a {"Data": [...]}
    envelope; several endpoints always return a bare array. Normalised once,
    in _unwrap, so nothing downstream has to care.
  * Object limiting. Arrays in request bodies are capped at 10 objects; more
    returns HTTP 413. post_chunked/put_chunked split automatically.
  * Rate limiting. 429 carries a Retry-After header we honour.

Every request and response is written to Metrc API Log. Headers are never
logged - the API keys live in the Authorization header.
"""

import json
import time
from urllib.parse import urlencode

import frappe
import requests
from frappe.utils import now_datetime

from cannabis_management.metrc import config
from cannabis_management.metrc.exceptions import (
    MetrcAuthError,
    MetrcError,
    MetrcNotConfigured,
    MetrcPayloadTooLargeError,
    MetrcRateLimitError,
    MetrcServerError,
    MetrcValidationError,
)

# Hard cap Metrc imposes on arrays in request bodies. Exceeding it -> HTTP 413.
MAX_OBJECTS_PER_REQUEST = 10

# Metrc caps pageSize at 20 on many endpoints; clamp rather than be rejected.
MAX_PAGE_SIZE = 20

DEFAULT_TIMEOUT = 60
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_LOG_FIELD = 60000


class MetrcClient:
    """One client per facility licence."""

    def __init__(self, license_number=None, timeout=DEFAULT_TIMEOUT):
        if not config.is_enabled():
            raise MetrcNotConfigured("Metrc integration is disabled in Metrc Settings")

        self.license_number = license_number
        self.base_url = config.base_url()
        self.timeout = timeout
        self.settings = config.get_settings()
        self.max_retries = self.settings.max_retries or 4

        self.session = requests.Session()
        self.session.auth = (
            config.integrator_key(),
            config.user_key(license_number) if license_number else "",
        )
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    # ------------------------------------------------------------------ core

    def request(self, method, path, params=None, body=None, reference=None, direction=None):
        """Issue one request.

        Returns the parsed JSON body, or None for the many PUT endpoints that
        respond with no content at all.
        """
        params = dict(params or {})
        if self.license_number and "licenseNumber" not in params:
            params["licenseNumber"] = self.license_number

        # urlencode is what produces %2B for "+" in timestamps. Never build
        # this string by concatenation.
        query = urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")

        direction = direction or ("Pull" if method == "GET" else "Push")

        if isinstance(body, list) and len(body) > MAX_OBJECTS_PER_REQUEST:
            raise MetrcPayloadTooLargeError(
                f"{len(body)} objects exceeds the Metrc limit of {MAX_OBJECTS_PER_REQUEST}. "
                "Use post_chunked()/put_chunked()."
            )

        if method != "GET" and config.is_dry_run():
            self._log(direction, method, url, body, 0, None, 0, "DRY RUN - not transmitted", reference)
            return None

        last_exc = None
        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            try:
                response = self.session.request(
                    method,
                    url,
                    data=json.dumps(body, default=str) if body is not None else None,
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                duration = int((time.monotonic() - started) * 1000)
                self._log(direction, method, url, body, 0, None, duration, str(e), reference)
                last_exc = MetrcServerError(f"Network error: {e}", endpoint=url)
                if attempt >= self.max_retries:
                    break
                self._backoff(attempt)
                continue

            duration = int((time.monotonic() - started) * 1000)
            text = response.text or ""
            try:
                parsed = json.loads(text) if text.strip() else None
            except ValueError:
                parsed = text

            self._log(direction, method, url, body, response.status_code, parsed, duration, None, reference)

            if response.status_code < 300:
                return parsed

            exc = self._to_exception(response, parsed, url)
            if response.status_code not in RETRYABLE_STATUS:
                raise exc

            last_exc = exc
            if attempt >= self.max_retries:
                break

            if isinstance(exc, MetrcRateLimitError) and exc.retry_after:
                time.sleep(min(exc.retry_after, 300))
            else:
                self._backoff(attempt)

        raise last_exc or MetrcError("Request failed", endpoint=url)

    @staticmethod
    def _to_exception(response, parsed, url):
        message = ""
        if isinstance(parsed, dict):
            message = parsed.get("Message") or parsed.get("message") or ""
        message = message or (response.text or "")[:500]
        kw = {"status_code": response.status_code, "body": parsed, "endpoint": url}

        if response.status_code in (401, 403):
            return MetrcAuthError(f"Auth failed ({response.status_code}): {message}", **kw)
        if response.status_code == 413:
            return MetrcPayloadTooLargeError(f"Payload too large: {message}", **kw)
        if response.status_code == 400:
            return MetrcValidationError(f"Validation failed: {message}", **kw)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after = int(retry_after) if retry_after else None
            except (TypeError, ValueError):
                retry_after = None
            return MetrcRateLimitError(f"Rate limited: {message}", retry_after=retry_after, **kw)
        if response.status_code >= 500:
            return MetrcServerError(f"Metrc server error: {message}", **kw)
        return MetrcError(f"HTTP {response.status_code}: {message}", **kw)

    @staticmethod
    def _backoff(attempt):
        time.sleep(min(2**attempt, 60))

    # -------------------------------------------------------------- read API

    @staticmethod
    def _unwrap(payload):
        """Normalise the two response shapes to (rows, total_pages)."""
        if payload is None:
            return [], 1
        if isinstance(payload, list):
            return payload, 1
        if isinstance(payload, dict) and "Data" in payload:
            return payload.get("Data") or [], payload.get("TotalPages") or 1
        return [payload], 1

    def get(self, path, params=None):
        """Single GET, normalised to a list of rows."""
        rows, _ = self._unwrap(self.request("GET", path, params=params))
        return rows

    def get_all(self, path, params=None, page_size=None):
        """GET every page, yielding rows."""
        params = dict(params or {})
        size = min(page_size or self.settings.default_page_size or MAX_PAGE_SIZE, MAX_PAGE_SIZE)
        params["pageSize"] = size
        page = 1

        while True:
            params["pageNumber"] = page
            rows, total_pages = self._unwrap(self.request("GET", path, params=params))
            for row in rows:
                yield row
            if not rows or page >= (total_pages or 1):
                return
            page += 1

    # ------------------------------------------------------------- write API

    def post(self, path, body, params=None, reference=None):
        return self.request("POST", path, params=params, body=body, reference=reference)

    def put(self, path, body, params=None, reference=None):
        return self.request("PUT", path, params=params, body=body, reference=reference)

    def delete(self, path, params=None, reference=None):
        return self.request("DELETE", path, params=params, reference=reference)

    def post_chunked(self, path, objects, params=None, reference=None):
        """POST an arbitrarily long list in 10-object chunks.

        Returns the concatenated Ids, positionally aligned with `objects` -
        Metrc returns IDs in submission order.
        """
        ids = []
        for i in range(0, len(objects), MAX_OBJECTS_PER_REQUEST):
            chunk = objects[i : i + MAX_OBJECTS_PER_REQUEST]
            result = self.post(path, chunk, params=params, reference=reference)
            if isinstance(result, dict) and result.get("Ids"):
                ids.extend(result["Ids"])
            else:
                ids.extend([None] * len(chunk))
        return ids

    def put_chunked(self, path, objects, params=None, reference=None):
        for i in range(0, len(objects), MAX_OBJECTS_PER_REQUEST):
            self.put(path, objects[i : i + MAX_OBJECTS_PER_REQUEST], params=params, reference=reference)

    # ------------------------------------------------------------------- log

    def _log(self, direction, method, url, body, status, response, duration_ms, error, reference):
        """Write a Metrc API Log row.

        Deliberately never logs headers: the integrator and user API keys live
        in the Authorization header and must not reach the database.
        """
        try:
            doc = frappe.new_doc("Metrc API Log")
            doc.timestamp = now_datetime()
            doc.direction = direction
            doc.method = method
            doc.endpoint = url[:500]
            doc.license_number = self.license_number
            doc.request_body = _truncate(body)
            doc.response_status = status
            doc.response_body = _truncate(response)
            doc.duration_ms = duration_ms
            doc.error = (error or "")[:1000] or None
            if reference:
                doc.reference_doctype, doc.reference_name = reference
            doc.flags.ignore_permissions = True
            doc.insert(ignore_permissions=True)
        except Exception:
            # Logging must never break a sync.
            frappe.log_error(frappe.get_traceback(), "[metrc] failed writing API log")


def _truncate(payload):
    if payload is None:
        return None
    try:
        text = json.dumps(payload, indent=2, default=str)
    except (TypeError, ValueError):
        text = str(payload)
    if len(text) > MAX_LOG_FIELD:
        return text[:MAX_LOG_FIELD] + f"\n... [truncated, {len(text)} chars total]"
    return text


def get_client(license_number):
    return MetrcClient(license_number)
