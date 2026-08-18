"""End-to-end verification for the Time Clock module.

    bench --site <site> execute cannabis_management.time_clock.verify.run

Creates a throwaway user, exercises punching, alternation, overnight pairing, notes
and the report, then deletes everything it made. Safe to re-run.
"""

import datetime

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

from cannabis_management.time_clock import api
from cannabis_management.time_clock.report.user_time_clock_summary import (
	user_time_clock_summary as report,
)

TEST_USER = "timeclock.verify@example.com"
NO_ROLE_USER = "timeclock.norole@example.com"

_results = []


def _check(label, condition, detail=""):
	_results.append((label, bool(condition), detail))
	print(f"{'PASS' if condition else 'FAIL'}  {label}{'  — ' + str(detail) if detail else ''}")


def _dt(date, hour, minute=0):
	return datetime.datetime.combine(getdate(date), datetime.time(hour, minute))


def _seed(user, when, log_type):
	"""Insert a historical punch. Source=Manual so the portal debounce does not apply."""
	doc = frappe.new_doc("User Checkin")
	doc.user = user
	doc.time = when
	doc.log_type = log_type
	doc.source = "Manual"
	doc.insert(ignore_permissions=True)
	return doc


def _make_user(email, first_name, with_role=True):
	doc = frappe.new_doc("User")
	doc.email = email
	doc.first_name = first_name
	doc.send_welcome_email = 0
	doc.user_type = "System User"
	if with_role:
		doc.append("roles", {"role": api.TIME_CLOCK_ROLE})
	doc.insert(ignore_permissions=True)
	return doc


def _cleanup():
	frappe.set_user("Administrator")
	for email in (TEST_USER, NO_ROLE_USER):
		for doctype in ("User Checkin", "User Day Note"):
			for name in frappe.get_all(doctype, filters={"user": email}, pluck="name"):
				frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=1, ignore_permissions=True)
	frappe.db.commit()


def run():
	frappe.set_user("Administrator")
	_cleanup()

	today = getdate(nowdate())
	yesterday = add_days(today, -1)

	_make_user(TEST_USER, "ClockTester")
	_make_user(NO_ROLE_USER, "NoRole", with_role=False)
	frappe.db.commit()

	try:
		# ── overnight shift: 11pm yesterday → 3am today is ONE session ──
		_seed(TEST_USER, _dt(yesterday, 23, 0), "IN")
		_seed(TEST_USER, _dt(today, 3, 0), "OUT")
		_seed(TEST_USER, _dt(today, 5, 0), "IN")  # still open
		frappe.db.commit()

		# ── alternation: neighbour-aware in both directions ──
		try:
			_seed(TEST_USER, _dt(today, 6, 0), "IN")
			_check("double IN rejected", False, "insert unexpectedly succeeded")
		except frappe.ValidationError:
			_check("double IN rejected", True)

		try:
			# Neighbour *before* 04:00 is the 03:00 OUT — must be caught even though
			# this is a backdated insert, not the latest punch.
			_seed(TEST_USER, _dt(today, 4, 0), "OUT")
			_check("backdated double OUT rejected", False, "insert unexpectedly succeeded")
		except frappe.ValidationError:
			_check("backdated double OUT rejected", True)

		# ── status as the user themselves ──
		frappe.set_user(TEST_USER)
		status = api.get_my_status()
		_check("is_clocked_in after open IN", status["is_clocked_in"] is True)
		_check("next_action is OUT", status["next_action"] == "OUT", status["next_action"])
		_check(
			"open_since is today 05:00",
			str(status["open_since"]).startswith(f"{today} 05:00"),
			status["open_since"],
		)
		_check(
			"today_sessions excludes yesterday's overnight IN",
			len(status["today_sessions"]) == 1,
			f"{len(status['today_sessions'])} session(s)",
		)

		# ── punch via the API ──
		punched = api.punch()
		_check("punch recorded OUT", punched["punched"] == "OUT", punched["punched"])
		_check("clocked out after punch", punched["is_clocked_in"] is False)
		_check("next_action back to IN", punched["next_action"] == "IN")
		frappe.db.commit()

		# ── debounce: an immediate second punch is refused ──
		try:
			api.punch()
			_check("debounce blocks instant re-punch", False, "second punch succeeded")
		except frappe.ValidationError:
			_check("debounce blocks instant re-punch", True)

		# ── a user without the role cannot punch or read status ──
		frappe.set_user(NO_ROLE_USER)
		try:
			api.get_my_status()
			_check("role gate blocks non-member", False, "status returned")
		except frappe.PermissionError:
			_check("role gate blocks non-member", True)

		# ── notes: created, edited in place, removed ──
		frappe.set_user(TEST_USER)
		try:
			api.set_day_note(user=TEST_USER, note="trying to note myself")
			_check("non-note-taker blocked from notes", False, "note saved")
		except frappe.PermissionError:
			_check("non-note-taker blocked from notes", True)

		frappe.set_user("Administrator")
		first = api.set_day_note(user=TEST_USER, note="On vacation")
		second = api.set_day_note(user=TEST_USER, note="Called in sick")
		frappe.db.commit()

		_check("note edit reuses same record", first["name"] == second["name"], second["name"])
		_check("note text updated", second["note"] == "Called in sick", second["note"])
		note_count = frappe.db.count("User Day Note", {"user": TEST_USER, "date": today})
		_check("exactly one note row (no duplicates)", note_count == 1, f"{note_count} row(s)")

		# ── roster reflects the note and the punch state ──
		roster = api.get_roster()
		row = next((r for r in roster["roster"] if r["user"] == TEST_USER), None)
		_check("roster includes test user", row is not None)
		if row:
			_check("roster shows note", (row["day_note"] or {}).get("note") == "Called in sick")
			_check("roster shows clocked out", row["is_clocked_in"] is False)

		api.remove_day_note(user=TEST_USER)
		frappe.db.commit()
		_check(
			"note removed",
			frappe.db.count("User Day Note", {"user": TEST_USER, "date": today}) == 0,
		)

		# ── report pairs sessions and attributes overnight work to its start day ──
		columns, rows = report.execute(
			{"from_date": str(yesterday), "to_date": str(today), "user": TEST_USER}
		)
		by_date = {}
		for r in rows:
			by_date.setdefault(r["date"], []).append(r)

		_check(
			"report has a row for the overnight shift",
			len(by_date.get(yesterday, [])) == 1,
			f"{len(by_date.get(yesterday, []))} row(s)",
		)
		if by_date.get(yesterday):
			overnight = by_date[yesterday][0]
			_check(
				"overnight shift is 4.0 hours",
				abs(overnight["hours"] - 4.0) < 0.01,
				overnight["hours"],
			)
			_check("overnight shift marked Complete", overnight["status"] == "Complete", overnight["status"])

		_check(
			"report has a row for today's shift",
			len(by_date.get(today, [])) == 1,
			f"{len(by_date.get(today, []))} row(s)",
		)
		if by_date.get(today):
			todays = by_date[today][0]
			_check("today's shift closed by the punch", todays["status"] == "Complete", todays["status"])
			_check("today's hours are positive", todays["hours"] > 0, todays["hours"])

	finally:
		_cleanup()

	passed = sum(1 for _, ok, _ in _results if ok)
	total = len(_results)
	print(f"\n{'=' * 52}\n{passed}/{total} checks passed")
	failures = [label for label, ok, _ in _results if not ok]
	if failures:
		print("FAILED: " + "; ".join(failures))
	return {"passed": passed, "total": total, "failures": failures}
