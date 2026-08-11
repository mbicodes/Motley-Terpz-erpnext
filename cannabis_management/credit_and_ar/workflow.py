"""The Credit Application Approval workflow.

Application → Finance recommendation → MD approval → terms go live.

Built in code rather than hand-authored fixture JSON so it is idempotent and
readable; it still exports through the app's existing unfiltered ``Workflow``,
``Workflow State`` and ``Workflow Action`` fixtures.
"""

import frappe

WORKFLOW_NAME = "Credit Application Approval"
DOCTYPE = "Credit Application"

# (state, doc_status, style, allow_edit)
STATES = [
	("Draft", 0, "Warning", "Credit Finance"),
	("Finance Review", 0, "Warning", "Credit Finance"),
	("Pending MD Approval", 0, "Primary", "Managing Director"),
	("Approved", 1, "Success", "Credit Finance"),
	("Rejected", 1, "Danger", "Credit Finance"),
	("Expired", 1, "Danger", "Credit Finance"),
	("Revoked", 1, "Danger", "Credit Finance"),
]

# Draft is editable by Sales too; the extra grants are added as additional rows
# because a Workflow Document State carries exactly one role.
EXTRA_STATE_ROLES = [
	("Draft", "Sales User"),
	("Draft", "System Manager"),
	("Finance Review", "System Manager"),
	("Pending MD Approval", "System Manager"),
]

# (action, from_state, next_state, allowed_role)
TRANSITIONS = [
	("Submit for Review", "Draft", "Finance Review", "Sales User"),
	("Submit for Review", "Draft", "Finance Review", "Credit Finance"),
	("Recommend", "Finance Review", "Pending MD Approval", "Credit Finance"),
	("Reject", "Finance Review", "Rejected", "Credit Finance"),
	("Approve", "Pending MD Approval", "Approved", "Managing Director"),
	("Reject", "Pending MD Approval", "Rejected", "Managing Director"),
	("Revoke", "Approved", "Revoked", "Credit Finance"),
	("Revoke", "Approved", "Revoked", "Managing Director"),
]

ACTIONS = sorted({transition[0] for transition in TRANSITIONS} | {"Mark Expired"})


def install_workflow():
	_ensure_states()
	_ensure_actions()
	_ensure_workflow()


def _ensure_states():
	for state, _doc_status, style, _role in STATES:
		if frappe.db.exists("Workflow State", state):
			continue
		frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
		).insert(ignore_permissions=True)


def _ensure_actions():
	for action in ACTIONS:
		if frappe.db.exists("Workflow Action Master", action):
			continue
		frappe.get_doc(
			{"doctype": "Workflow Action Master", "workflow_action_name": action}
		).insert(ignore_permissions=True)


def _ensure_workflow():
	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		doc = frappe.get_doc("Workflow", WORKFLOW_NAME)
		doc.states = []
		doc.transitions = []
	else:
		doc = frappe.new_doc("Workflow")
		doc.workflow_name = WORKFLOW_NAME

	doc.document_type = DOCTYPE
	doc.workflow_state_field = "workflow_state"
	doc.is_active = 1
	doc.send_email_alert = 0
	doc.override_status = 0

	for state, doc_status, style, role in STATES:
		doc.append(
			"states",
			{
				"state": state,
				"doc_status": str(doc_status),
				"allow_edit": role,
				"style": style,
			},
		)

	for state, role in EXTRA_STATE_ROLES:
		doc.append("states", {"state": state, "doc_status": "0", "allow_edit": role})

	for action, from_state, next_state, role in TRANSITIONS:
		doc.append(
			"transitions",
			{
				"state": from_state,
				"action": action,
				"next_state": next_state,
				"allowed": role,
				"allow_self_approval": 1,
			},
		)

	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	return doc.name
