"""Records where each user physically is when they log in (User Login Location).

A row is written at login itself, located from the IP address, so every login
has a location even if the user never answers the browser's permission prompt:

1. ``on_session_creation`` (server) looks the request IP up in the local DB-IP
   City Lite database, inserts the row (status IP Only), remembers the row for
   this session in cache and sets a readable ``login_geo_pending`` cookie.
2. ``public/js/login_location.js`` (desk and website) sees the cookie, asks the
   browser for its position and posts it to ``record``, which upgrades the same
   row to the device's position.

The IP position needs no permission but is city-level at best, and wrong behind
a VPN. ``record`` only accepts one post per session, and only for a session that
was marked at login, so a caller cannot backfill or spam locations. If the user
blocks location access the row is kept (status Denied, IP location) so the
refusal itself is visible, and then the session ends: sharing location is a
condition of being logged in.
"""

import json
import os

import frappe
from frappe import _
from frappe.utils import flt, get_bench_path, now_datetime

PENDING_COOKIE = "login_geo_pending"

# Long enough for someone to answer the browser's permission prompt late.
PENDING_TTL_SECONDS = 6 * 60 * 60

# A fix worse than this (metres) is a network/IP guess, not a real position, and is
# stored as Approximate so it can be filtered out.
APPROXIMATE_ABOVE_M = 100

# Not logged out on a refusal (the Denied row is still written). Administrator so
# there is always a way back in to fix things; the rest are business exceptions.
LOGOUT_EXEMPT_USERS = ("Administrator", "nikki@motleyterpz.com")

STATUSES = ("Captured", "Approximate", "Denied", "Unavailable", "Not Supported")

# DB-IP City Lite (CC BY 4.0, https://db-ip.com), refreshed monthly from
# https://download.db-ip.com/free/dbip-city-lite-YYYY-MM.mmdb.gz. Override the
# path with site_config "geoip_city_db".
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
	"""City, state, country and coordinates for an IP, or None. Never raises."""
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
		# Never block a login over this; record() falls back to a fresh row.
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

	# The row written at login; a session from before rows were written at login
	# (or whose insert failed) holds the login time instead.
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
