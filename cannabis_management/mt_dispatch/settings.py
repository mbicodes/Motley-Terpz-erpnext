import frappe

from cannabis_management.mt_dispatch import stages


def get_company_settings(company):
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
	if not cfg or not user:
		return None
	for row in cfg.team or []:
		if row.user == user:
			return row
	return None


def team_flags(user, cfg):
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
	if not cfg:
		return []
	return [row.user for row in (cfg.team or []) if row.get(flag)]


def is_administrator(user=None):
	return (user or frappe.session.user) == "Administrator"


def require_team_flag(cfg, user, flags):
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
