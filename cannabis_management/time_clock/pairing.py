from frappe.utils import get_datetime, now_datetime, time_diff_in_seconds


def build_sessions(punches, now=None):
	now = now or now_datetime()
	sessions = []
	open_session = None

	for punch in punches:
		punch_time = get_datetime(punch.get("time"))

		if punch.get("log_type") == "IN":
			if open_session:
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
		open_session["seconds"] = max(
			0, time_diff_in_seconds(now, open_session["in_time"])
		)
		sessions.append(open_session)

	return sessions


def sessions_for_date(punches, date, now=None):
	return [s for s in build_sessions(punches, now=now) if s["in_time"].date() == date]


def total_seconds(sessions):
	return sum(s["seconds"] for s in sessions)
