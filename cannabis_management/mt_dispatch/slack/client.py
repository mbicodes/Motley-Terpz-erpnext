"""A thin wrapper over the Slack Web API.

Everything that talks to Slack goes through `api()`. It adds the bot token,
backs off on HTTP 429 using Retry-After, and raises SlackError on any reply
with ok = false so callers never have to inspect the envelope themselves.
"""

import json
import time

import frappe
import requests

API = "https://slack.com/api/"
TIMEOUT = 10
MAX_RETRIES = 3

ALLOWED_MIMETYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
ALLOWED_FILETYPES = {"pdf", "png", "jpg", "jpeg"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class SlackError(Exception):
	def __init__(self, method, error, response=None):
		super().__init__(f"{method}: {error}")
		self.method = method
		self.error = error
		self.response = response or {}


def bot_token():
	try:
		return frappe.get_cached_doc("Dispatch Global Settings").get_password(
			"bot_token", raise_exception=False
		)
	except Exception:
		return None


def _call(method, http_method, params):
	token = bot_token()
	if not token:
		raise SlackError(method, "no_bot_token")

	params = {k: v for k, v in params.items() if v is not None}
	headers = {"Authorization": f"Bearer {token}"}

	for attempt in range(MAX_RETRIES + 1):
		if http_method == "POST":
			headers["Content-Type"] = "application/json; charset=utf-8"
			r = requests.post(API + method, data=json.dumps(params), headers=headers, timeout=TIMEOUT)
		else:
			r = requests.get(API + method, params=params, headers=headers, timeout=TIMEOUT)

		if r.status_code == 429 and attempt < MAX_RETRIES:
			time.sleep(min(int(r.headers.get("Retry-After") or 1), 30))
			continue
		r.raise_for_status()
		data = r.json()
		if not data.get("ok"):
			raise SlackError(method, data.get("error") or "unknown_error", data)
		return data

	raise SlackError(method, "rate_limited")


def api(method, **params):
	"""Call one Web API method with a JSON body."""
	return _call(method, "POST", params)


def api_get(method, **params):
	"""GET form, for the read methods that take query parameters."""
	return _call(method, "GET", params)


# ── messages ─────────────────────────────────────────────────────────────────


def post(channel, text, blocks=None, thread_ts=None):
	"""chat.postMessage. Returns (channel, ts). The channel is the resolved
	id, which for a DM is the D… conversation, not the user id passed in."""
	data = api("chat.postMessage", channel=channel, text=text, blocks=blocks, thread_ts=thread_ts)
	return data["channel"], data["ts"]


def update(channel, ts, text, blocks=None):
	return api("chat.update", channel=channel, ts=ts, text=text, blocks=blocks)


def post_ephemeral(channel, user, text, thread_ts=None):
	return api("chat.postEphemeral", channel=channel, user=user, text=text, thread_ts=thread_ts)


def permalink(channel, ts):
	try:
		return api_get("chat.getPermalink", channel=channel, message_ts=ts).get("permalink")
	except (SlackError, requests.RequestException):
		return None


def open_dm(slack_user):
	return api("conversations.open", users=slack_user)["channel"]["id"]


def respond(response_url, text):
	"""Ephemeral reply to whoever clicked, through the interaction's response_url."""
	requests.post(
		response_url,
		json={"response_type": "ephemeral", "replace_original": False, "text": text},
		timeout=TIMEOUT,
	)


# ── views ────────────────────────────────────────────────────────────────────


def views_open(trigger_id, view):
	return api("views.open", trigger_id=trigger_id, view=view)


def views_update(view_id, view, hash=None):
	return api("views.update", view_id=view_id, view=view, hash=hash)


def views_publish(slack_user, view):
	return api("views.publish", user_id=slack_user, view=view)


# ── users ────────────────────────────────────────────────────────────────────


def lookup_by_email(email):
	try:
		return api_get("users.lookupByEmail", email=email)["user"]["id"]
	except (SlackError, requests.RequestException):
		return None


def user_info(slack_user):
	try:
		return api_get("users.info", user=slack_user)["user"]
	except (SlackError, requests.RequestException):
		return None


# ── files ────────────────────────────────────────────────────────────────────


def check_upload(file_obj):
	"""None when a Slack file object is acceptable, else a message for the user."""
	mimetype = (file_obj.get("mimetype") or "").lower()
	filetype = (file_obj.get("filetype") or "").lower()
	if mimetype not in ALLOWED_MIMETYPES and filetype not in ALLOWED_FILETYPES:
		return "Only PDF, PNG or JPG files."
	if int(file_obj.get("size") or 0) > MAX_UPLOAD_BYTES:
		return "Files are limited to 20 MB."
	return None


def download_to_file(file_obj, attached_to_doctype=None, attached_to_name=None):
	"""Fetch a Slack upload with the bot token and save it as a private File.
	Returns the File's file_url."""
	if not file_obj.get("url_private_download") and not file_obj.get("url_private"):
		file_obj = {**api_get("files.info", file=file_obj["id"])["file"], **file_obj}

	problem = check_upload(file_obj)
	if problem:
		raise SlackError("files.download", problem)

	url = file_obj.get("url_private_download") or file_obj.get("url_private")
	r = requests.get(url, headers={"Authorization": f"Bearer {bot_token()}"}, timeout=60)
	r.raise_for_status()
	content = r.content
	if len(content) > MAX_UPLOAD_BYTES:
		raise SlackError("files.download", "Files are limited to 20 MB.")
	# Slack serves its sign-in page instead of the file when the token lacks files:read.
	if content[:15].lower().startswith(b"<!doctype html"):
		raise SlackError("files.download", "Slack refused the download. Check the files:read scope.")

	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_obj.get("name") or f"slack-{file_obj.get('id')}",
			"content": content,
			"is_private": 1,
			"attached_to_doctype": attached_to_doctype,
			"attached_to_name": attached_to_name,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.file_url
