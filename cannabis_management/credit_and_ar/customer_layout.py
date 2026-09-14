"""Customer form layout and field rules that must outlast a migrate.

Everything here is re-asserted on `after_migrate`, which Frappe runs *after*
`sync_fixtures()` and `sync_customizations()`. That ordering is the whole point:
the app ships an unfiltered "Custom Field" fixture, so any change made to a field
it already contains is silently undone on every migrate. Rather than edit that
fixture, this module states the intended end-state in code and stamps it back
after the fixture has had its say.

Three rules, all idempotent:

1. The Credit Control tab starts AFTER the Details tab's last field. A Tab Break
   owns every field after it until the next one, so anchoring it mid-Details
   (custom_notebox) dragged the stock Defaults / Internal Customer / More
   Information sections into Credit Control. Anchored to custom_link_supplier —
   the last field before dashboard_tab — those three stay in Details.

2. custom_credit_status is permlevel 1 and editable. The engines still set it,
   but it is not read-only — permlevel 1, already granted on Customer to Credit
   Finance, Managing Director, Accounts Manager and Sales Master Manager, is what
   decides who may change it.

3. REMOVED_FIELDS are gone (custom_reconciliation_clause_ack, the retired
   Policy Exempt checkbox and its column break, custom_license_verified). Each
   underlying column is left alone, so no data is destroyed — only the field is
   removed from the form.
"""

import frappe

from cannabis_management.credit_and_ar import utils
from cannabis_management.credit_and_ar.custom_fields import CREDIT_STATUS_OPTIONS

CUSTOMER = "Customer"

CREDIT_TAB = "custom_credit_control_tab"
DETAILS_LAST_FIELD = "custom_link_supplier"

STATUS_FIELD = "custom_credit_status"
STATUS_PERMLEVEL = 1
# Editable by hand — permlevel 1 is what limits who, not a read-only flag.
STATUS_READ_ONLY = 0

REMOVED_FIELDS = (
	"custom_reconciliation_clause_ack",
	# Replaced by Credit Status = "Policy Exempt" — see _migrate_exemption below,
	# which moves the value across before the field goes.
	"custom_credit_policy_exempt",
	# Column break that only existed to sit beside that checkbox.
	"custom_credit_exemption_cb",
	# Requested removed outright. The underlying column is left alone per the
	# module docstring, so no data is destroyed.
	"custom_license_verified",
	# Replaced by Credit Status = "Hard Hold" — see utils.is_on_hold. Two fields
	# describing the same state could disagree; the status is the one people read.
	"custom_on_hold",
)

EXEMPT_CHECKBOX = "custom_credit_policy_exempt"

# Why an account is on Hard Hold. Shown only while it is held, since the reason
# for a released account is history, not current state — that lives on the AR
# Case. Auto reasons are stamped by the engines (see ar_case.sync_customer_from_
# cases); the Manual ones are there for Finance to pick.
HOLD_REASON_FIELD = "custom_hold_reason"
HOLD_REASON_DEPENDS_ON = f'eval:doc.{STATUS_FIELD}=="{utils.STATUS_HARD_HOLD}"'



def _name(fieldname):
	return f"{CUSTOMER}-{fieldname}"


def enforce(*args, **kwargs):
	"""Apply all three rules. Safe to run repeatedly; returns what it changed."""
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
	"""Keep Defaults / Internal Customer / More Information in the Details tab."""
	name = _name(CREDIT_TAB)
	if not frappe.db.exists("Custom Field", name):
		return []

	# Only meaningful while the anchor itself exists; if that field is ever
	# removed, leave the tab where it is rather than dropping it to the end.
	if not frappe.db.exists("Custom Field", _name(DETAILS_LAST_FIELD)):
		return []

	if frappe.db.get_value("Custom Field", name, "insert_after") == DETAILS_LAST_FIELD:
		return []

	frappe.db.set_value("Custom Field", name, "insert_after", DETAILS_LAST_FIELD)
	return [f"{CREDIT_TAB} moved after {DETAILS_LAST_FIELD}"]


def _set_status_permlevel():
	"""Everything about custom_credit_status that the fixture would undo.

	The fixture still carries this field's original shape — COD in the options, a
	default of COD, the "every customer is COD by default" description, permlevel
	0 and read_only 1 — so all five are re-stamped here rather than trusting the
	fixture import to leave them alone.

	Order matters: the default is cleared BEFORE the options are narrowed. Frappe
	refuses to save a Select whose default is not one of its options, and leaving
	a stored default of "COD" behind a COD-less option list makes the field
	unsaveable from the UI afterwards.
	"""
	name = _name(STATUS_FIELD)
	if not frappe.db.exists("Custom Field", name):
		return []

	current = frappe.db.get_value(
		"Custom Field", name,
		["permlevel", "read_only", "options", "default", "description"],
		as_dict=True,
	)
	changed = []

	if (current.default or "") != "":
		frappe.db.set_value("Custom Field", name, "default", "")
		changed.append(f"{STATUS_FIELD} default cleared")

	if (current.options or "") != CREDIT_STATUS_OPTIONS:
		frappe.db.set_value("Custom Field", name, "options", CREDIT_STATUS_OPTIONS)
		changed.append(f"{STATUS_FIELD} options reset (COD removed)")

	if (current.description or "") != "":
		frappe.db.set_value("Custom Field", name, "description", "")
		changed.append(f"{STATUS_FIELD} description cleared")

	if int(current.permlevel or 0) != STATUS_PERMLEVEL:
		frappe.db.set_value("Custom Field", name, "permlevel", STATUS_PERMLEVEL)
		changed.append(f"{STATUS_FIELD} set to permlevel {STATUS_PERMLEVEL}")

	if int(current.read_only or 0) != STATUS_READ_ONLY:
		frappe.db.set_value("Custom Field", name, "read_only", STATUS_READ_ONLY)
		changed.append(f"{STATUS_FIELD} read_only -> {STATUS_READ_ONLY}")

	return changed


def _drop_removed_fields():
	"""Delete retired fields, without orphaning whatever sat below them.

	Custom fields are positioned by a chain of insert_after values. Deleting one
	link leaves everything anchored to it with a dead anchor, and Frappe drops an
	unanchored field at the very end of the form — which is how removing the
	exempt checkbox emptied the Credit Control tab and scattered its contents
	past the last tab. So each dependent is repointed at the deleted field's own
	anchor first, closing the chain rather than breaking it.

	The table column is deliberately left in place: dropping it would throw away
	values that existing customers still carry.
	"""
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
	"""Repair any field whose anchor no longer exists.

	custom_fields.CUSTOMER_FIELDS is the intended layout, so an orphan is put
	back where that says it belongs. Without this a single missing anchor sends
	a field — and everything chained below it — to the bottom of the form, past
	the last tab, which reads to everyone as "the tab has disappeared".
	"""
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
	"""Create the Hold Reason field, and keep its options and visibility right.

	Created here rather than in custom_fields.py so it stays out of the app's
	Custom Field fixture entirely: a field the fixture has never seen is one it
	can never revert.
	"""
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
	"""Carry any surviving checkbox exemption onto the Credit Status.

	Runs before the field is retired, and keeps working afterwards: dropping a
	Custom Field leaves its column in the table, so an account exempted on an
	older release is still found and moved across on the next migrate.
	"""
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
	"""Remove ERPNext's native credit limit from accounts already exempt.

	The Customer hook keeps this true going forward, but accounts exempted before
	that existed still carry the mirrored row — and that row is what blocks their
	Sales Invoices with ERPNext's own "Credit Limit Crossed" popup. Runs on every
	migrate and no-ops once there is nothing left to clear.
	"""
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
