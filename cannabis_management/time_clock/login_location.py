import json
import os

import frappe
from frappe import _
from frappe.utils import flt, get_bench_path, now_datetime

PENDING_COOKIE = "login_geo_pending"

PENDING_TTL_SECONDS = 6 * 60 * 60

APPROXIMATE_ABOVE_M = 100

LOGOUT_EXEMPT_USERS = ("Administrator", "nikki@motleyterpz.com")

STATUSES = ("Captured", "Approximate", "Denied", "Unavailable", "Not Supported")

DEFAULT_GEOIP_DB = os.path.join(get_bench_path(), "geoip", "dbip-city-lite.mmdb")

_geoip_reader = None


def _pending_key(sid):
	return f"login_location_pending:{sid}"


def _geojson_point(lat, lng):
	return json.dumps(
		{
			"type": "FeatureCollection",
			"features": [
				{"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [lng, lat]}}
			],
		}
	)


def lookup_ip(ip):
	global _geoip_reader
	if not ip:
		return None
	try:
		if _geoip_reader is None:
			import maxminddb

			_geoip_reader = maxminddb.open_database(frappe.conf.get("geoip_city_db") or DEFAULT_GEOIP_DB)
		data = _geoip_reader.get(ip) or {}
	except Exception:
		frappe.log_error(title="Login location: IP lookup failed")
		return None

	loc = data.get("location") or {}
	if loc.get("latitude") is None or loc.get("longitude") is None:
		return None

	def name(d):
		return ((d or {}).get("names") or {}).get("en")

	parts = [name(data.get("city")), *(name(s) for s in data.get("subdivisions") or []), name(data.get("country"))]
	return {
		"latitude": flt(loc["latitude"]),
		"longitude": flt(loc["longitude"]),
		"label": ", ".join(dict.fromkeys(p for p in parts if p)),
	}


def _apply_ip_location(doc):
	geo = lookup_ip(doc.ip_address)
	if not geo:
		return
	doc.ip_location = geo["label"]
	doc.latitude = geo["latitude"]
	doc.longitude = geo["longitude"]
	doc.accuracy = None
	doc.location_source = "IP Address"
	doc.location = _geojson_point(geo["latitude"], geo["longitude"])


def on_session_creation(login_manager):
	if frappe.session.user == "Guest" or not frappe.session.sid:
		return

	pending = str(now_datetime())
	try:
		doc = frappe.new_doc("User Login Location")
		doc.update(
			{
				"user": frappe.session.user,
				"login_time": pending,
				"status": "IP Only",
				"ip_address": frappe.local.request_ip,
				"user_agent": frappe.get_request_header("User-Agent"),
			}
		)
		_apply_ip_location(doc)
		doc.insert(ignore_permissions=True)
		pending = doc.name
	except Exception:
		frappe.log_error(title="Login location: could not write the login row")

	frappe.cache().set_value(_pending_key(frappe.session.sid), pending, expires_in_sec=PENDING_TTL_SECONDS)
	frappe.local.cookie_manager.set_cookie(PENDING_COOKIE, "1", max_age=PENDING_TTL_SECONDS)


@frappe.whitelist(methods=["POST"])
def record(status, latitude=None, longitude=None, accuracy=None, error_message=None):
	if frappe.session.user == "Guest":
		frappe.throw(_("Not logged in."), frappe.PermissionError)

	frappe.local.cookie_manager.delete_cookie(PENDING_COOKIE)

	key = _pending_key(frappe.session.sid)
	pending = frappe.cache().get_value(key)
	if not pending:
		return {"recorded": False}
	frappe.cache().delete_value(key)

	if status not in STATUSES:
		frappe.throw(_("Invalid status."))

	if frappe.db.exists("User Login Location", {"name": pending, "user": frappe.session.user}):
		doc = frappe.get_doc("User Login Location", pending)
	else:
		doc = frappe.new_doc("User Login Location")
		doc.update(
			{
				"user": frappe.session.user,
				"login_time": pending,
				"ip_address": frappe.local.request_ip,
				"user_agent": frappe.get_request_header("User-Agent"),
			}
		)
		_apply_ip_location(doc)

	doc.status = status
	doc.error_message = (error_message or "")[:500] or None

	if status in ("Captured", "Approximate"):
		lat, lng = flt(latitude), flt(longitude)
		if latitude in (None, "") or longitude in (None, "") or not (-90 <= lat <= 90 and -180 <= lng <= 180):
			frappe.throw(_("Invalid coordinates."))
		doc.latitude = lat
		doc.longitude = lng
		doc.accuracy = flt(accuracy) or None
		doc.status = "Approximate" if not doc.accuracy or doc.accuracy > APPROXIMATE_ABOVE_M else "Captured"
		doc.location_source = "Device"
		doc.location = _geojson_point(lat, lng)

	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.insert()
	else:
		doc.save()

	if status == "Denied" and frappe.session.user not in LOGOUT_EXEMPT_USERS:
		frappe.local.login_manager.logout()
		return {"recorded": True, "status": doc.status, "logged_out": True}

	return {"recorded": True, "status": doc.status, "accuracy": doc.accuracy}
