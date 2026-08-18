"""Server-side verification for the Manufacturing Portal access layer.

    bench --site <site> execute cannabis_management.manufacturing_portal.verify.run

Covers code validation, matching, rate limiting and the route allowlist. The full
unlock flow (login_as + session guard) needs a real HTTP request and is covered by
the companion curl script — login_manager does not exist in a console context.

Creates throwaway users and deletes them again. Safe to re-run.
"""

import frappe

from cannabis_management.manufacturing_portal import access, session_guard

USER_A = "mfgportal.a@example.com"
USER_B = "mfgportal.b@example.com"

GOOD_CODE = "SHOP7412"
OTHER_CODE = "LINE9930"

_results = []


def _check(label, condition, detail=""):
	_results.append((label, bool(condition), detail))
	print(f"{'PASS' if condition else 'FAIL'}  {label}{'  — ' + str(detail) if detail else ''}")


def _expect_throw(label, fn):
	try:
		fn()
		_check(label, False, "no exception raised")
	except frappe.ValidationError as exc:
		_check(label, True, str(exc)[:60])


def _make_user(email, first_name, code=None, enabled_flag=True):
	doc = frappe.new_doc("User")
	doc.email = email
	doc.first_name = first_name
	doc.send_welcome_email = 0
	doc.user_type = "System User"
	if code:
		doc.custom_process_code = code
		doc.custom_process_code_enabled = 1 if enabled_flag else 0
	doc.insert(ignore_permissions=True)
	return doc


def _cleanup():
	frappe.set_user("Administrator")
	for email in (USER_A, USER_B):
		for name in frappe.get_all("Process Access Log", filters={"user": email}, pluck="name"):
			frappe.delete_doc("Process Access Log", name, force=1, ignore_permissions=True)
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=1, ignore_permissions=True)
	frappe.cache().delete_value(access._failure_key("1.2.3.4"))
	frappe.db.commit()


def run():
	frappe.set_user("Administrator")
	_cleanup()

	try:
		# ── code strength ────────────────────────────────────────────
		_expect_throw("rejects code shorter than 6", lambda: _make_user(USER_A, "A", "12345"))
		_expect_throw("rejects repeated character", lambda: _make_user(USER_A, "A", "777777"))
		_expect_throw("rejects ascending run", lambda: _make_user(USER_A, "A", "123456"))
		_expect_throw("rejects descending run", lambda: _make_user(USER_A, "A", "987654"))
		_expect_throw("rejects code with space", lambda: _make_user(USER_A, "A", "SHOP 74"))

		# ── enabled flag without a code ──────────────────────────────
		def _enabled_no_code():
			doc = frappe.new_doc("User")
			doc.email = USER_A
			doc.first_name = "A"
			doc.send_welcome_email = 0
			doc.custom_process_code_enabled = 1
			doc.insert(ignore_permissions=True)

		_expect_throw("rejects enabled flag with no code", _enabled_no_code)

		# ── happy path ───────────────────────────────────────────────
		_make_user(USER_A, "PortalA", GOOD_CODE)
		frappe.db.commit()
		_check("accepts a strong unique code", frappe.db.exists("User", USER_A))

		# ── uniqueness ───────────────────────────────────────────────
		_expect_throw("rejects duplicate code", lambda: _make_user(USER_B, "PortalB", GOOD_CODE))
		_expect_throw(
			"duplicate check is case-insensitive",
			lambda: _make_user(USER_B, "PortalB", GOOD_CODE.lower()),
		)

		_make_user(USER_B, "PortalB", OTHER_CODE)
		frappe.db.commit()
		_check("second user with a different code is fine", frappe.db.exists("User", USER_B))

		# ── whitespace normalisation ─────────────────────────────────
		doc_b = frappe.get_doc("User", USER_B)
		doc_b.custom_process_code = f"  {OTHER_CODE}  "
		doc_b.save(ignore_permissions=True)
		frappe.db.commit()
		_check(
			"code is trimmed on save",
			frappe.db.get_value("User", USER_B, "custom_process_code") == OTHER_CODE,
		)

		# ── matching ─────────────────────────────────────────────────
		_check("matches the right user", access.match_code(GOOD_CODE) == USER_A)
		_check("no match for unknown code", access.match_code("NOSUCHCODE") is None)
		_check("no match for empty code", access.match_code("") is None)

		frappe.db.set_value("User", USER_A, "custom_process_code_enabled", 0)
		frappe.db.commit()
		_check("disabled flag blocks matching", access.match_code(GOOD_CODE) is None)
		frappe.db.set_value("User", USER_A, "custom_process_code_enabled", 1)

		frappe.db.set_value("User", USER_A, "enabled", 0)
		frappe.db.commit()
		_check("disabled user blocks matching", access.match_code(GOOD_CODE) is None)
		frappe.db.set_value("User", USER_A, "enabled", 1)
		frappe.db.commit()

		# ── rate limiting ────────────────────────────────────────────
		ip = "1.2.3.4"
		frappe.cache().delete_value(access._failure_key(ip))
		_check("starts unlocked", not access.is_locked_out(ip))
		for _ in range(access.MAX_FAILURES):
			access._record_failure(ip)
		_check(
			f"locks out after {access.MAX_FAILURES} failures",
			access.is_locked_out(ip),
			f"count={access._failure_count(ip)}",
		)
		access._clear_failures(ip)
		_check("clears on success", not access.is_locked_out(ip))

		# ── audit log ────────────────────────────────────────────────
		before = frappe.db.count("Process Access Log")
		access.log_attempt("Failed", reason="verify probe")
		frappe.db.commit()
		_check("log row written", frappe.db.count("Process Access Log") == before + 1)
		newest = frappe.get_all(
			"Process Access Log",
			filters={"reason": "verify probe"},
			fields=["result", "user"],
			limit=1,
		)
		_check("failed row records no user", newest and newest[0].user in (None, ""))
		for name in frappe.get_all(
			"Process Access Log", filters={"reason": "verify probe"}, pluck="name"
		):
			frappe.delete_doc("Process Access Log", name, force=1, ignore_permissions=True)

		# ── route allowlist ──────────────────────────────────────────
		allowed = [
			"/manufacturing-process",
			"/manufacturing-process/",
			"/manufacturing-process.js",
			"/manufacturing-process.css",
			"/website_script.js",
			"/assets/cannabis_management/js/manufacturing_process_timer_portal.js",
			"/api/method/cannabis_management.api.manufacturing_process.get_timer_defaults",
			"/api/method/cannabis_management.api.manufacturing_process.save_timer_entry",
			"/api/method/cannabis_management.manufacturing_portal.access.lock",
			"/api/method/frappe.desk.search.search_link",
			"/api/method/frappe.client.insert",
			"/logout",
		]
		blocked = [
			"/app",
			"/app/user",
			"/app/user/Administrator",
			"/api/method/frappe.client.delete",
			"/api/method/frappe.core.doctype.user.user.reset_password",
			"/api/resource/User",
			"/crm",
			"/timeclock",
		]

		bad_allow = [p for p in allowed if not session_guard._is_allowed(session_guard._normalise(p))]
		bad_block = [p for p in blocked if session_guard._is_allowed(session_guard._normalise(p))]
		_check("allowlist permits every path the page needs", not bad_allow, bad_allow)
		_check("allowlist blocks everything else", not bad_block, bad_block)

		# ── legacy cmd= dispatch (website.js's frappe.call POSTs to "/") ──
		# This is what the page's own JS (Sign out, Start Timer) actually sends —
		# not /api/method/<method> — so it needs its own allow/block check.
		frappe.form_dict.cmd = "cannabis_management.manufacturing_portal.access.lock"
		_check("cmd= dispatch allows the page's own methods", session_guard._is_allowed("/"))
		frappe.form_dict.cmd = "frappe.client.delete"
		_check("cmd= dispatch blocks everything else", not session_guard._is_allowed("/"))
		frappe.form_dict.pop("cmd", None)
		_check("bare POST / with no cmd is still blocked", not session_guard._is_allowed("/"))

	finally:
		_cleanup()

	passed = sum(1 for _, ok, _ in _results if ok)
	total = len(_results)
	print(f"\n{'=' * 52}\n{passed}/{total} checks passed")
	failures = [label for label, ok, _ in _results if not ok]
	if failures:
		print("FAILED: " + "; ".join(failures))
	return {"passed": passed, "total": total, "failures": failures}
