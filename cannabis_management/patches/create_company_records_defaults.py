import frappe

ROLES = ["Accounting Team", "Operations", "ERP Dev Team", "Director"]

WORKFLOW_STATES = {
	"Draft": "Danger",
	"Under Review": "Warning",
	"Approved": "Success",
	"Locked": "Primary",
	"Active": "Success",
	"Expired": "Danger",
	"Terminated": "Danger",
}

WORKFLOW_ACTIONS = [
	"Submit for Review", "Approve", "Reject", "Lock",
	"Activate", "Mark Expired", "Terminate",
]

BUSINESS_ENTITIES = [
	"TSBC Ranch", "Motley Terpz", "Master Touch Manufacturing",
	"LA Canna",
]


def execute():
	"""Seed roles, workflow masters and Business Entity records for Company Records."""
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)

	for state, style in WORKFLOW_STATES.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)

	for action in WORKFLOW_ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	for entity in BUSINESS_ENTITIES:
		if not frappe.db.exists("Business Entity", entity):
			frappe.get_doc({"doctype": "Business Entity", "entity_name": entity}).insert(
				ignore_permissions=True
			)
