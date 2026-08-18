"""Shared IN/OUT pairing logic for the time clock.

Used by both the portal API and the User Time Clock Summary report so the two can
never disagree about how many hours somebody worked.

Pairing is driven purely by punch order, never by calendar date. An 11pm IN and a
3am OUT the next morning form one session belonging to the *IN* date, which is what
makes overnight shifts come out right.
"""

from frappe.utils import get_datetime, now_datetime, time_diff_in_seconds


def build_sessions(punches, now=None):
	"""Pair an ascending list of punches into work sessions.

	Args:
		punches: rows ordered oldest-first, each with ``time`` and ``log_type``.
		now: reference time used to measure a still-open session. Defaults to now.

	Returns:
		list of dicts with ``in_time``, ``out_time`` (None while open), ``seconds``
		and ``is_open``. Sessions are ordered oldest-first.

	Unpaired punches are tolerated rather than dropped, because real timesheets are
	full of forgotten punches and the report has to show them instead of silently
	swallowing them:
	  * a second IN with no intervening OUT closes the previous session as open
	  * an OUT with no open IN is skipped (nothing sensible to pair it with)
	"""
	now = now or now_datetime()
	sessions = []
	open_session = None

	for punch in punches:
		punch_time = get_datetime(punch.get("time"))

		if punch.get("log_type") == "IN":
			if open_session:
				# Previous IN was never closed — leave it open and start a new one.
				sessions.append(open_session)
			open_session = {
				"in_time": punch_time,
				"out_time": None,
				"seconds": 0,
				"is_open": True,
			}
		elif punch.get("log_type") == "OUT" and open_session:
			open_session["out_time"] = punch_time
			open_session["seconds"] = max(
				0, time_diff_in_seconds(punch_time, open_session["in_time"])
			)
			open_session["is_open"] = False
			sessions.append(open_session)
			open_session = None

	if open_session:
		# Still clocked in: measure elapsed time so far, but never report negative
		# time if the punch is somehow stamped in the future.
		open_session["seconds"] = max(
			0, time_diff_in_seconds(now, open_session["in_time"])
		)
		sessions.append(open_session)

	return sessions


def sessions_for_date(punches, date, now=None):
	"""Sessions whose IN punch falls on ``date`` (so overnight work counts to its start day)."""
	return [s for s in build_sessions(punches, now=now) if s["in_time"].date() == date]


def total_seconds(sessions):
	return sum(s["seconds"] for s in sessions)
