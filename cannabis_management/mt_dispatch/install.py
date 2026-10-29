import frappe

from cannabis_management.mt_dispatch import stages

STAGE_FIELD = "custom_logistic_status"


def install():
	install_custom_fields()
	install_property_setters()
	install_roles()

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
				{
					"fieldname": "custom_fulfillment_section",
					"label": "Fulfillment",
					"fieldtype": "Section Break",
					"collapsible": 1,
					"insert_after": "custom_slack_messages",
				},
				{
					"fieldname": "custom_pull_sheet",
					"label": "Pull Sheet",
					"fieldtype": "Attach",
					"allow_on_submit": 1,
					"insert_after": "custom_fulfillment_section",
					"description": "Photo or scan of the filled Lab Pull Sheet.",
				},
				{
					"fieldname": "custom_pull_sheet_by",
					"label": "Pull Sheet By",
					"fieldtype": "Link",
					"options": "User",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_pull_sheet",
				},
				{
					"fieldname": "custom_pull_sheet_on",
					"label": "Pull Sheet On",
					"fieldtype": "Datetime",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_pull_sheet_by",
				},
				{
					"fieldname": "custom_fulfillment_cb",
					"fieldtype": "Column Break",
					"insert_after": "custom_pull_sheet_on",
				},
				{
					"fieldname": "custom_update_ack_on",
					"label": "Update Acknowledged On",
					"fieldtype": "Datetime",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_fulfillment_cb",
					"description": "Last time someone cleared the board's Order Updated banner.",
				},
				{
					"fieldname": "custom_update_ack_by",
					"label": "Update Acknowledged By",
					"fieldtype": "Link",
					"options": "User",
					"read_only": 1,
					"allow_on_submit": 1,
					"insert_after": "custom_update_ack_on",
				},
				{
					"fieldname": "custom_cancel_reason",
					"label": "Cancel Reason",
					"fieldtype": "Small Text",
					"allow_on_submit": 1,
					"insert_after": "custom_update_ack_by",
					"description": "Shown on the Fulfillment Pipeline's Cancelled tab. Fill in before cancelling.",
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
	for fieldname in (
		"custom_conversion_required", "custom_payment_verified", "custom_amount_paid",
		"custom_hold_from_stage", "custom_hold_reason", "custom_released_by", "custom_released_on",
		"custom_release_override_reason", "custom_stage_log", "custom_slack_messages",
		"custom_pull_sheet", "custom_pull_sheet_by", "custom_pull_sheet_on",
		"custom_update_ack_on", "custom_update_ack_by", "custom_cancel_reason",
	):
		name = frappe.db.get_value("Custom Field", {"dt": "Sales Order", "fieldname": fieldname})
		if name:
			frappe.db.set_value("Custom Field", name, "no_copy", 1)


def install_property_setters():
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
	frappe.db.delete("Property Setter", {
		"doc_type": "Sales Order", "field_name": STAGE_FIELD, "property": "read_only_depends_on",
	})
	for prop, value, ptype in (
		("read_only", "0", "Check"),
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
