"""User validation for the Manufacturing Portal access code.

Uniqueness is enforced here rather than with a DB unique index on purpose: most users
have no code, and Frappe stores an unset Data field as ``''`` rather than NULL, so a
unique index would reject the *second* user without a code. Validating in Python lets
empty values be ignored.
"""

import frappe
from frappe import _

from cannabis_management.manufacturing_portal.custom_fields import MIN_CODE_LENGTH


def validate(doc, method=None):
	code = (doc.get("custom_process_code") or "").strip()

	# Normalise before anything else so " 1234 " and "1234" cannot both exist.
	if code != (doc.get("custom_process_code") or ""):
		doc.custom_process_code = code

	if not code:
		if doc.get("custom_process_code_enabled"):
			frappe.throw(
				_("Set a Manufacturing Portal Code, or untick Manufacturing Portal Access Enabled."),
				title=_("Code Required"),
			)
		return

	_validate_strength(code)
	_validate_unique(doc, code)


def _validate_strength(code):
	if len(code) < MIN_CODE_LENGTH:
		frappe.throw(
			_("The Manufacturing Portal Code must be at least {0} characters.").format(MIN_CODE_LENGTH),
			title=_("Code Too Short"),
		)

	if any(ch.isspace() for ch in code):
		frappe.throw(_("The Manufacturing Portal Code cannot contain spaces."), title=_("Invalid Code"))

	if len(set(code)) == 1:
		frappe.throw(
			_("The Manufacturing Portal Code cannot be a single repeated character."),
			title=_("Code Too Weak"),
		)

	if _is_sequential(code):
		frappe.throw(
			_("The Manufacturing Portal Code cannot be a simple run like 123456 or 987654."),
			title=_("Code Too Weak"),
		)


def _is_sequential(code):
	"""True for strictly ascending or descending single-step runs (123456, 654321, abcdef)."""
	deltas = {ord(b) - ord(a) for a, b in zip(code, code[1:])}
	return deltas in ({1}, {-1})


def _validate_unique(doc, code):
	"""A code must identify exactly one person, or 'whoever it matches' is undefined."""
	clash = frappe.db.get_value(
		"User",
		{"custom_process_code": code, "name": ["!=", doc.name]},
		["name", "full_name"],
		as_dict=True,
	)
	if clash:
		# Naming the clashing user is safe here: only administrators can edit Users,
		# and they can already read every code on the system.
		frappe.throw(
			_("That Manufacturing Portal Code is already used by {0}. Codes must be unique.").format(
				clash.full_name or clash.name
			),
			title=_("Duplicate Code"),
		)
