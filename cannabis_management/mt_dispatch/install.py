"""Fields and property setters this module owns.

Created in code, re-asserted on every migrate. Deliberately not fixtures: a
fixture export would drag in every unrelated Custom Field on Sales Order and
rewrite them from whatever the exporting site happened to hold.

Every Sales Order field here is allow_on_submit, because the order is already
submitted for the whole of the flow. They are written with db_set inside
transitions, never by saving the order.
"""

import frappe

from cannabis_management.mt_dispatch import stages

STAGE_FIELD = "custom_logistic_status"


def install():
	install_custom_fields()
	install_property_setters()
	install_roles()


# Section 10. The role gives document access; the company's team table gives
# the flow action. Both must pass. Fulfilment - Consolidated and the Accounts
# roles already exist and already carry what fulfillment and finance need.
ROLE_PERMS = {
	"Compliance - Consolidated": {
		"Sales Order": ["read"],
		"Delivery Note": ["read", "create", "write"],
	},
	"Dispatch Approver": {
		"Sales Order": ["read"],
		"Delivery Note": ["read", "write", "submit"],
	},
	"Dispatch Driver": {
		"Sales Order": ["read"],
		"Delivery Note": ["read"],
	},
}


def install_roles():
	"""Create the three new roles and grant their rights. Idempotent: an
	existing grant is left as it is, so hand-made changes survive a migrate."""
	from frappe.permissions import add_permission, update_permission_property

	for role, doctypes in ROLE_PERMS.items():
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

		for doctype, rights in doctypes.items():
			if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
				continue
			add_permission(doctype, role, 0)
			for right in rights:
				if right != "read":
					update_permission_property(doctype, role, 0, right, 1)


def install_custom_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "custom_conversion_required",
					"label": "Conversion Required",
					"fieldtype": "Check",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": STAGE_FIELD,
				},
				{
					"fieldname": "custom_payment_verified",
					"label": "Payment Verified",
					"fieldtype": "Check",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_conversion_required",
					"description": "Cached result of the payment gate. The gate itself always recomputes.",
				},
				{
					"fieldname": "custom_amount_paid",
					"label": "Amount Paid",
					"fieldtype": "Currency",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_payment_verified",
					"options": "currency",
				},
				{
					"fieldname": "custom_hold_from_stage",
					"label": "Hold From Stage",
					"fieldtype": "Data",
					"hidden": 1,
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_amount_paid",
				},
				{
					"fieldname": "custom_hold_reason",
					"label": "Hold Reason",
					"fieldtype": "Small Text",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_hold_from_stage",
					"depends_on": f'eval:doc.{STAGE_FIELD}=="{stages.ON_HOLD}"',
				},
				{
					"fieldname": "custom_released_by",
					"label": "Released By",
					"fieldtype": "Link",
					"options": "User",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_hold_reason",
				},
				{
					"fieldname": "custom_released_on",
					"label": "Released On",
					"fieldtype": "Datetime",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_released_by",
				},
				{
					"fieldname": "custom_release_override_reason",
					"label": "Release Override Reason",
					"fieldtype": "Small Text",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_released_on",
				},
				{
					"fieldname": "custom_dispatch_audit_section",
					"label": "Dispatch Audit",
					"fieldtype": "Section Break",
					"collapsible": 1,
					"insert_after": "custom_release_override_reason",
				},
				{
					"fieldname": "custom_stage_log",
					"label": "Stage Log",
					"fieldtype": "Table",
					"options": "Dispatch Stage Log",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_dispatch_audit_section",
				},
				{
					"fieldname": "custom_slack_messages",
					"label": "Slack Messages",
					"fieldtype": "Table",
					"options": "Dispatch Slack Message",
					"hidden": 1,
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_stage_log",
				},
			],
			"User": [
				{
					"fieldname": "custom_slack_user_id",
					"label": "Slack User ID",
					"fieldtype": "Data",
					"insert_after": "username",
					"description": "Filled automatically on first use. Set by hand when the "
					"Slack account uses a different email than the ERP login.",
				}
			],
		},
		ignore_validate=True,
	)
	# Nothing the flow writes belongs on an amended copy.
	for fieldname in (
		"custom_conversion_required", "custom_payment_verified", "custom_amount_paid",
		"custom_hold_from_stage", "custom_hold_reason", "custom_released_by", "custom_released_on",
		"custom_release_override_reason", "custom_stage_log", "custom_slack_messages",
	):
		name = frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": fieldname})
		if name:
			frappe.db.set_value("Custom Field", name, "no_copy", 1)


def install_property_setters():
	"""The stage Select's options, and the read-only that keeps people out of it.

	Read-only is belt to flow.guard_stage_field's braces: the guard is what
	actually stops an API write, this is what stops the field looking editable.
	"""
	# The Custom Field was created as virtual. A virtual field's options are
	# evaluated as Python whenever the order is serialised -- which ERPNext
	# does on every Delivery Note submit -- so the stage list raised a
	# SyntaxError and release could not submit the note. The column is real;
	# the flag was wrong.
	cf = frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": STAGE_FIELD}, ["name", "is_virtual"], as_dict=True)
	if cf and cf.is_virtual and frappe.db.has_column("Sales Order", STAGE_FIELD):
		frappe.db.set_value("Custom Field", cf.name, "is_virtual", 0)
		frappe.clear_cache(doctype="Sales Order")

	frappe.make_property_setter(
		{
			"doctype": "Sales Order",
			"fieldname": STAGE_FIELD,
			"doctype_or_field": "DocField",
			"property": "options",
			"value": "\n" + "\n".join(stages.ALL_STAGES),
			"property_type": "Text",
		},
		is_system_generated=False,
	)
	# Editable on a submitted order, so people can change the stage from the
	# field itself. The form script turns a pick into the matching transition
	# (same gates, same dialogs); guard_stage_field still rejects any save or
	# API write that tries to set it directly.
	for prop, value, ptype in (
		("read_only", "0", "Check"),
		("read_only_depends_on", "eval:doc.docstatus!==1", "Code"),
		# An amended order starts its own flow. Copying the cancelled order's
		# stage would make on_submit think it is already on the board.
		("no_copy", "1", "Check"),
	):
		frappe.make_property_setter(
			{
				"doctype": "Sales Order",
				"fieldname": STAGE_FIELD,
				"doctype_or_field": "DocField",
				"property": prop,
				"value": value,
				"property_type": ptype,
			},
			is_system_generated=False,
		)
	frappe.make_property_setter(
		{
			"doctype": "Sales Order",
			"fieldname": STAGE_FIELD,
			"doctype_or_field": "DocField",
			"property": "allow_on_submit",
			"value": "1",
			"property_type": "Check",
		},
		is_system_generated=False,
	)
