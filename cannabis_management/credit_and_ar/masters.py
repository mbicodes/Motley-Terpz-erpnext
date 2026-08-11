"""Native masters the Credit & AR module depends on.

All of these are ordinary ERPNext records — Roles, Payment Terms Templates, an
Item and the permlevel DocPerms. Creation is idempotent so the patches can run
on every migrate.
"""

import frappe
from frappe.utils import flt

# ── Roles ────────────────────────────────────────────────────────────────────

CREDIT_ROLES = [
	{
		"role_name": "Credit Finance",
		"desk_access": 1,
		"description": "Owns credit files, recommends limits, releases holds and runs the AR book.",
	},
	{
		"role_name": "Managing Director",
		"desk_access": 1,
		"description": "Approves credit lines and Terms Sales Orders; designates workout accounts.",
	},
	{
		"role_name": "Ops Manager",
		"desk_access": 1,
		"description": "Approves Terms Sales Orders alongside the Managing Director.",
	},
	{
		"role_name": "Collections Officer",
		"desk_access": 1,
		"description": "Works the Red List: promises to pay, contact history and next actions.",
	},
]


def install_roles():
	for role in CREDIT_ROLES:
		if frappe.db.exists("Role", role["role_name"]):
			continue
		frappe.get_doc({"doctype": "Role", **role}).insert(ignore_permissions=True)


# ── Payment Terms Templates ──────────────────────────────────────────────────
#
# NET7, NET15, NET30, "50% down NET15" and "50% down NET30" already exist on the
# site. They are left untouched; only the gaps are created, following the site's
# existing "50% down NETnn" naming rather than inventing a parallel convention.

PAYMENT_TERMS_TEMPLATES = [
	{"name": "COD", "rows": [(100.0, 0)]},
	{"name": "NET7", "rows": [(100.0, 7)]},
	{"name": "NET15", "rows": [(100.0, 15)]},
	{"name": "NET21", "rows": [(100.0, 21)]},
	{"name": "NET30", "rows": [(100.0, 30)]},
	{"name": "50% down NET7", "rows": [(50.0, 0), (50.0, 7)]},
	{"name": "50% down NET15", "rows": [(50.0, 0), (50.0, 15)]},
	{"name": "50% down NET21", "rows": [(50.0, 0), (50.0, 21)]},
	{"name": "50% down NET30", "rows": [(50.0, 0), (50.0, 30)]},
]

# Every non-COD template needs a written MD exception reason on the Credit
# Application before it can be approved.
TERMS_REQUIRING_MD_EXCEPTION = [
	template["name"] for template in PAYMENT_TERMS_TEMPLATES if template["name"] != "COD"
]


def install_payment_terms_templates():
	for template in PAYMENT_TERMS_TEMPLATES:
		if frappe.db.exists("Payment Terms Template", template["name"]):
			continue

		doc = frappe.new_doc("Payment Terms Template")
		doc.template_name = template["name"]
		for portion, credit_days in template["rows"]:
			doc.append(
				"terms",
				{
					"due_date_based_on": "Day(s) after invoice date",
					"invoice_portion": portion,
					"credit_days": credit_days,
					"description": _term_description(portion, credit_days),
				},
			)
		doc.insert(ignore_permissions=True)


def _term_description(portion: float, credit_days: int) -> str:
	if credit_days == 0:
		return f"{flt(portion):g}% due on delivery"
	return f"{flt(portion):g}% due {credit_days} days after invoice date"


# ── Finance charge item ──────────────────────────────────────────────────────

FINANCE_CHARGE_ITEM_CODE = "FINANCE-CHARGE"


def install_finance_charge_item():
	"""Create FINANCE-CHARGE, forcing the readable name.

	Stock Settings on this site names Items by series, so a plain insert yields
	something like STO-ITEM-2026-01826. Finance needs to recognise the line on a
	late-fee invoice, so the record is renamed after insert.
	"""
	if frappe.db.exists("Item", FINANCE_CHARGE_ITEM_CODE):
		return FINANCE_CHARGE_ITEM_CODE

	# A previous run may have created it under a series name.
	existing = frappe.db.get_value("Item", {"item_code": FINANCE_CHARGE_ITEM_CODE}, "name")
	if not existing:
		existing = frappe.db.get_value(
			"Item", {"item_name": "Finance Charge", "is_stock_item": 0}, "name"
		)
	if existing:
		return _rename_to_code(existing)

	item_group = _pick_item_group()
	if not item_group:
		frappe.logger("credit_and_ar").warning(
			"No Item Group available — FINANCE-CHARGE item not created."
		)
		return None

	doc = frappe.new_doc("Item")
	doc.item_code = FINANCE_CHARGE_ITEM_CODE
	doc.item_name = "Finance Charge"
	doc.description = "Late payment finance charge assessed under the signed Credit Agreement."
	doc.item_group = item_group
	doc.stock_uom = "Nos"
	doc.is_stock_item = 0
	doc.is_sales_item = 1
	doc.is_purchase_item = 0
	doc.include_item_in_manufacturing = 0
	doc.insert(ignore_permissions=True)

	return _rename_to_code(doc.name)


def _rename_to_code(name: str) -> str:
	if name == FINANCE_CHARGE_ITEM_CODE:
		return name
	try:
		frappe.rename_doc("Item", name, FINANCE_CHARGE_ITEM_CODE, force=True, show_alert=False)
		frappe.db.set_value("Item", FINANCE_CHARGE_ITEM_CODE, "item_code", FINANCE_CHARGE_ITEM_CODE)
		return FINANCE_CHARGE_ITEM_CODE
	except Exception:
		frappe.logger("credit_and_ar").warning(
			f"Could not rename finance charge item {name} to {FINANCE_CHARGE_ITEM_CODE}; "
			"leaving it under its series name."
		)
		return name


def _pick_item_group() -> str | None:
	for candidate in ("Services", "Service", "All Item Groups"):
		if frappe.db.exists("Item Group", candidate):
			return candidate
	return frappe.db.get_value("Item Group", {"is_group": 0}, "name")


# ── Permlevel 1 access ───────────────────────────────────────────────────────
#
# Customer.custom_credit_terms_template sits at permlevel 1 so Sales cannot set
# a customer's terms. Only Credit Finance and the Managing Director get read and
# write at that level.

PERMLEVEL_1_ROLES = ("Credit Finance", "Managing Director")


def install_permlevel_access(doctype: str = "Customer", permlevel: int = 1):
	for role in PERMLEVEL_1_ROLES:
		exists = frappe.db.exists(
			"Custom DocPerm",
			{"parent": doctype, "role": role, "permlevel": permlevel},
		)
		if exists:
			continue
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": permlevel,
				"read": 1,
				"write": 1,
			}
		).insert(ignore_permissions=True)

	frappe.clear_cache(doctype=doctype)


def install_all():
	install_roles()
	install_payment_terms_templates()
	install_finance_charge_item()
	install_permlevel_access()
