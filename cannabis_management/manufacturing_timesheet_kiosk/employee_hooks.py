import frappe
from frappe import _

FIELDNAME = "custom_kiosk_access_code"


def validate(doc, method=None):
	code = (doc.get(FIELDNAME) or "").strip()

	if code != (doc.get(FIELDNAME) or ""):
		doc.set(FIELDNAME, code)

	if not code:
		return

	_validate_unique(doc, code)


def _validate_unique(doc, code):
	clash = frappe.db.get_value(
		"Employee",
		{FIELDNAME: code, "name": ["!=", doc.name]},
		["name", "employee_name"],
		as_dict=True,
	)
	if clash:
		frappe.throw(
			_("This Kiosk Access Code is already assigned to another employee ({0}). "
			  "Please choose a different code.").format(
				frappe.bold(f"{clash.name} - {clash.employee_name}")
			),
			title=_("Duplicate Code"),
		)
