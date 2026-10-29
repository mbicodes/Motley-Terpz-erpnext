import frappe

from cannabis_management.credit_and_ar import utils
from cannabis_management.credit_and_ar.custom_fields import (
	CREDIT_STATUS_DEFAULT,
	CREDIT_STATUS_DESCRIPTION,
	CREDIT_STATUS_OPTIONS,
)

CUSTOMER = "Customer"

CREDIT_TAB = "custom_credit_control_tab"
DETAILS_LAST_FIELD = "custom_link_supplier"

STATUS_FIELD = "custom_credit_status"
STATUS_PERMLEVEL = 1
STATUS_READ_ONLY = 0

REMOVED_FIELDS = (
	"custom_reconciliation_clause_ack",
	"custom_credit_policy_exempt",
	"custom_credit_exemption_cb",
	"custom_license_verified",
	"custom_on_hold",
)

EXEMPT_CHECKBOX = "custom_credit_policy_exempt"

HOLD_REASON_FIELD = "custom_hold_reason"
HOLD_REASON_DEPENDS_ON = f'eval:doc.{STATUS_FIELD}=="{utils.STATUS_HARD_HOLD}"'


def _name(fieldname):
	return f"{CUSTOMER}-{fieldname}"


def enforce(*args, **kwargs):
	changed = []
	changed += _migrate_exemption()
	changed += _install_hold_reason()
	changed += _place_credit_tab()
	changed += _set_status_permlevel()
	changed += _drop_removed_fields()
	changed += _clear_exempt_credit_limits()
	changed += _heal_orphans()

	if changed:
		frappe.db.commit()
		frappe.clear_cache(doctype=CUSTOMER)
	return {"changed": changed}


def _place_credit_tab():
	name = _name(CREDIT_TAB)
	if not frappe.db.exists("Custom Field", name):
		return []

	if not frappe.db.exists("Custom Field", _name(DETAILS_LAST_FIELD)):
		return []

	if frappe.db.get_value("Custom Field", name, "insert_after") == DETAILS_LAST_FIELD:
		return []

	frappe.db.set_value("Custom Field", name, "insert_after", DETAILS_LAST_FIELD)
	return [f"{CREDIT_TAB} moved after {DETAILS_LAST_FIELD}"]


def _set_status_permlevel():
	name = _name(STATUS_FIELD)
	if not frappe.db.exists("Custom Field", name):
		return []

	current = frappe.db.get_value(
		"Custom Field", name,
		["permlevel", "read_only", "options", "default", "description"],
		as_dict=True,
	)
	changed = []

	if (current.options or "") != CREDIT_STATUS_OPTIONS:
		frappe.db.set_value("Custom Field", name, "options", CREDIT_STATUS_OPTIONS)
		changed.append(f"{STATUS_FIELD} options reset")

	if (current.default or "") != CREDIT_STATUS_DEFAULT:
		frappe.db.set_value("Custom Field", name, "default", CREDIT_STATUS_DEFAULT)
		changed.append(f"{STATUS_FIELD} default set to {CREDIT_STATUS_DEFAULT}")

	if (current.description or "") != CREDIT_STATUS_DESCRIPTION:
		frappe.db.set_value("Custom Field", name, "description", CREDIT_STATUS_DESCRIPTION)
		changed.append(f"{STATUS_FIELD} description set")

	if int(current.permlevel or 0) != STATUS_PERMLEVEL:
		frappe.db.set_value("Custom Field", name, "permlevel", STATUS_PERMLEVEL)
		changed.append(f"{STATUS_FIELD} set to permlevel {STATUS_PERMLEVEL}")

	if int(current.read_only or 0) != STATUS_READ_ONLY:
		frappe.db.set_value("Custom Field", name, "read_only", STATUS_READ_ONLY)
		changed.append(f"{STATUS_FIELD} read_only -> {STATUS_READ_ONLY}")

	return changed


def _drop_removed_fields():
	changed = []
	for fieldname in REMOVED_FIELDS:
		name = _name(fieldname)
		if not frappe.db.exists("Custom Field", name):
			continue

		anchor = frappe.db.get_value("Custom Field", name, "insert_after")
		dependents = frappe.get_all(
			"Custom Field", filters={"dt": CUSTOMER, "insert_after": fieldname}, pluck="name"
		)
		for dependent in dependents:
			frappe.db.set_value("Custom Field", dependent, "insert_after", anchor)

		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
		changed.append(f"{fieldname} removed")
		if dependents:
			changed.append(f"  re-anchored {len(dependents)} field(s) to {anchor}")
	return changed


def _heal_orphans():
	from cannabis_management.credit_and_ar.custom_fields import CUSTOMER_FIELDS

	declared = {
		f["fieldname"]: f.get("insert_after")
		for f in CUSTOMER_FIELDS
		if f.get("insert_after")
	}
	rows = frappe.get_all(
		"Custom Field", filters={"dt": CUSTOMER}, fields=["name", "fieldname", "insert_after"]
	)
	present = {f.fieldname for f in frappe.get_meta(CUSTOMER).fields} | {r.fieldname for r in rows}

	changed = []
	for row in rows:
		if not row.insert_after or row.insert_after in present:
			continue
		wanted = declared.get(row.fieldname)
		if wanted and wanted in present:
			frappe.db.set_value("Custom Field", row.name, "insert_after", wanted)
			changed.append(f"{row.fieldname} re-anchored to {wanted}")
	return changed


def _install_hold_reason():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	name = _name(HOLD_REASON_FIELD)
	if not frappe.db.exists("Custom Field", name):
		create_custom_fields(
			{
				CUSTOMER: [
					{
						"fieldname": HOLD_REASON_FIELD,
						"fieldtype": "Select",
						"label": "Hold Reason",
						"options": utils.HOLD_REASON_OPTIONS,
						"depends_on": HOLD_REASON_DEPENDS_ON,
						"permlevel": STATUS_PERMLEVEL,
						"insert_after": STATUS_FIELD,
						"in_standard_filter": 1,
					}
				]
			},
			update=True,
		)
		return [f"{HOLD_REASON_FIELD} created"]

	current = frappe.db.get_value(
		"Custom Field", name, ["options", "depends_on", "permlevel"], as_dict=True
	)
	changed = []
	if (current.options or "") != utils.HOLD_REASON_OPTIONS:
		frappe.db.set_value("Custom Field", name, "options", utils.HOLD_REASON_OPTIONS)
		changed.append(f"{HOLD_REASON_FIELD} options reset")
	if (current.depends_on or "") != HOLD_REASON_DEPENDS_ON:
		frappe.db.set_value("Custom Field", name, "depends_on", HOLD_REASON_DEPENDS_ON)
		changed.append(f"{HOLD_REASON_FIELD} depends_on reset")
	if int(current.permlevel or 0) != STATUS_PERMLEVEL:
		frappe.db.set_value("Custom Field", name, "permlevel", STATUS_PERMLEVEL)
		changed.append(f"{HOLD_REASON_FIELD} permlevel reset")
	return changed


def _migrate_exemption():
	if not frappe.db.has_column(CUSTOMER, EXEMPT_CHECKBOX):
		return []

	stragglers = frappe.db.sql(
		f"""
		SELECT name FROM `tabCustomer`
		WHERE `{EXEMPT_CHECKBOX}` = 1 AND IFNULL(custom_credit_status, '') != %s
		""",
		utils.STATUS_EXEMPT,
		pluck=True,
	)
	if not stragglers:
		return []

	for customer in stragglers:
		frappe.db.set_value(
			CUSTOMER, customer, "custom_credit_status", utils.STATUS_EXEMPT,
			update_modified=False,
		)
	return [f"{len(stragglers)} account(s) moved to Credit Status = {utils.STATUS_EXEMPT}"]


def _clear_exempt_credit_limits():
	exempt = frappe.get_all(
		CUSTOMER, filters={"custom_credit_status": utils.STATUS_EXEMPT}, pluck="name"
	)
	if not exempt:
		return []

	rows = frappe.get_all(
		"Customer Credit Limit",
		filters={"parenttype": CUSTOMER, "parent": ["in", exempt]},
		fields=["name", "parent"],
	)
	if not rows:
		return []

	frappe.db.delete("Customer Credit Limit", {"parenttype": CUSTOMER, "parent": ["in", exempt]})
	for customer in {r.parent for r in rows}:
		frappe.clear_document_cache(CUSTOMER, customer)
	return [f"native credit limit cleared on {len(rows)} row(s) for exempt account(s)"]
