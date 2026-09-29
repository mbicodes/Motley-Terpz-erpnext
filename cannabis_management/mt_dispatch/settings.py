"""Per-company configuration lookup and team authority.

Every handler in this module starts with `cfg = get_company_settings(company)`.
No record, or `enabled = 0`, means the company is not on the dispatch flow and
every hook and gate ignores its orders. That is what lets companies be switched
on one at a time.
"""

import frappe

from cannabis_management.mt_dispatch import stages


def get_company_settings(company):
	"""The enabled settings record for a company, or None.

	Cached per request: the reminder job and the notify layer both call this
	many times over the same handful of companies.
	"""
	if not company:
		return None

	cache = frappe.local.mt_dispatch_cfg = getattr(frappe.local, "mt_dispatch_cfg", {})
	if company in cache:
		return cache[company]

	cfg = None
	if frappe.db.exists("Dispatch Company Settings", company):
		doc = frappe.get_cached_doc("Dispatch Company Settings", company)
		if doc.enabled:
			cfg = doc

	cache[company] = cfg
	return cfg


def clear_settings_cache(doc=None, method=None):
	frappe.local.mt_dispatch_cfg = {}


def team_row(cfg, user):
	"""This user's row on this company's team, or None."""
	if not cfg or not user:
		return None
	for row in cfg.team or []:
		if row.user == user:
			return row
	return None


def team_flags(user, cfg):
	"""The set of flow flags this user holds at this company.

	Authority is per company on purpose: a user can be fulfillment for Master
	Touch and have no rights at TSBC. The ERP role still governs document
	access -- both must pass.
	"""
	row = team_row(cfg, user)
	if not row:
		return set()
	flags = {f for f in stages.ALL_FLAGS if row.get(f)}
	if row.can_override:
		flags.add("can_override")
	if row.backup_approver:
		flags.add("backup_approver")
	return flags


def users_with_flag(cfg, flag):
	"""Every ERP user carrying a flag at this company, in table order."""
	if not cfg:
		return []
	return [row.user for row in (cfg.team or []) if row.get(flag)]


def is_administrator(user=None):
	return (user or frappe.session.user) == "Administrator"


def require_team_flag(cfg, user, flags):
	"""Raise unless the user holds at least one of `flags` at this company.

	`flags` empty means the action has no team requirement. Administrator is
	exempt so the flow stays recoverable when a settings record is wrong.
	"""
	from cannabis_management.mt_dispatch.gates import GateError

	if not flags:
		return
	if is_administrator(user):
		return
	held = team_flags(user, cfg)
	if held & set(flags):
		return

	company = cfg.company if cfg else "this company"
	if not team_row(cfg, user):
		raise GateError(f"You're not on the {company} dispatch team.")
	raise GateError(f"Your role on the {company} dispatch team doesn't cover this step.")
