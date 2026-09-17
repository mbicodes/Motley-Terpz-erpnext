import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password


class MetrcConfig(Document):
	pass


@frappe.whitelist()
def test_connection():
	"""Test the configured Base URL + API Key against Metrc.

	Metrc auth is HTTP Basic (vendor/integrator key : user key). This doctype
	holds the vendor key and, optionally, a user key of its own; if the user
	key field here is blank, falls back to the existing Metrc Settings (the
	first active facility), when that doctype is present.

	The test is a single GET /facilities/v2 — read-only, so it is safe to run
	even against the production endpoint (it never writes anything to Metrc).
	"""
	import requests

	cfg = frappe.get_single("Metrc Config")
	base = (cfg.base_url or "").rstrip("/")
	vendor = cfg.get_password("api_key", raise_exception=False)
	if not base or not vendor:
		frappe.throw("Set Base URL and API Key first, then save.")

	user = cfg.get_password("user_key", raise_exception=False) or _existing_user_key()

	try:
		resp = requests.get(f"{base}/facilities/v2", auth=(vendor, user or ""), timeout=30)
	except Exception as e:
		return {"ok": False, "status_code": None, "message": f"Could not reach {base} — {e}"}

	ok = resp.status_code == 200
	facilities = []
	if ok:
		try:
			data = resp.json()
			rows = data.get("Data", data) if isinstance(data, dict) else data
			for f in (rows or []):
				lic = (f.get("License") or {}).get("Number") if isinstance(f.get("License"), dict) else f.get("LicenseNumber")
				if lic:
					facilities.append(lic)
		except Exception:
			pass

	return {
		"ok": ok,
		"status_code": resp.status_code,
		"message": _explain(resp.status_code),
		"facilities": facilities[:25],
		"used_user_key": bool(user),
	}


def _existing_user_key():
	"""First active facility's User API key from Metrc Settings, if present."""
	if not frappe.db.exists("DocType", "Metrc Settings"):
		return None
	try:
		ms = frappe.get_single("Metrc Settings")
	except Exception:
		return None
	for row in (ms.get("facilities") or []):
		if row.get("is_active"):
			key = get_decrypted_password("Metrc Facility", row.name, "user_key", raise_exception=False)
			if key:
				return key
	return None


def _explain(code):
	return {
		200: "Connected — the key authenticated and Metrc returned facilities.",
		401: "401 Unauthorized — the vendor key and the user key don't belong together for this "
		"endpoint. A production vendor key needs a production User API key (the sandbox user "
		"key won't work against api-ca.metrc.com, and vice-versa).",
		403: "403 Forbidden — authenticated, but this key isn't permitted for that action.",
		404: "404 — endpoint not found at this Base URL. Check the URL.",
	}.get(code, f"HTTP {code} — see response.")
