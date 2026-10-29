import hashlib
import hmac
import time

import frappe

MAX_AGE_SECONDS = 300


class SlackAuthError(Exception):
	pass


def _globals():
	return frappe.get_cached_doc("Dispatch Global Settings")


def expected_signature(secret, timestamp, body):
	if isinstance(body, str):
		body = body.encode()
	base = b"v0:" + str(timestamp).encode() + b":" + body
	return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def check_signature(secret, timestamp, body, signature, now=None):
	if not secret:
		raise SlackAuthError("signing secret not configured")
	if not timestamp or not signature:
		raise SlackAuthError("missing signature headers")
	try:
		ts = int(timestamp)
	except (TypeError, ValueError):
		raise SlackAuthError("bad timestamp")
	if abs((now if now is not None else time.time()) - ts) > MAX_AGE_SECONDS:
		raise SlackAuthError("stale request")
	if not hmac.compare_digest(expected_signature(secret, timestamp, body), signature):
		raise SlackAuthError("bad signature")


def verify():
	request = frappe.request
	check_signature(
		_globals().get_password("signing_secret", raise_exception=False),
		request.headers.get("X-Slack-Request-Timestamp"),
		request.get_data(),
		request.headers.get("X-Slack-Signature"),
	)


def check_team(team_id):
	expected = _globals().slack_team_id
	if not expected or team_id != expected:
		raise SlackAuthError("wrong workspace")
