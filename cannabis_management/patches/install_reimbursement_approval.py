import json

import frappe

DOCTYPE = "Personal Cash Tracking"
WORKFLOW = "Personal Cash Tracking Approval"
APPROVER = "Reimbursement Approver"
CASH_USER = "Cash Tracking User"

STATES = [
    ("Draft", 0, CASH_USER, None),
    ("Submitted", 1, CASH_USER, "Success"),
    ("Pending Approval", 0, APPROVER, "Warning"),
    ("Approved", 1, APPROVER, "Success"),
    ("Rejected", 0, APPROVER, "Danger"),
    ("Cancelled", 2, "Accounts Manager", "Inverse"),
]

EXTRA_DRAFT_ROLES = ["Nikki M - Consolidated", "Accounts Manager", "System Manager"]

IS_REIMB = 'doc.transaction_type == "Reimbursement"'
NOT_REIMB = 'doc.transaction_type != "Reimbursement"'
OWN = "doc.user == frappe.session.user"
NOT_OWN = "doc.user != frappe.session.user"

PENDING_FILTERS = [
    [DOCTYPE, "transaction_type", "=", "Reimbursement", False],
    [DOCTYPE, "workflow_state", "=", "Pending Approval", False],
]


def execute():
    install()


def install():
    ensure_role()
    backfill_workflow_state()
    ensure_states_and_actions()
    ensure_workflow()
    ensure_notifications()
    ensure_list_filter()
    ensure_number_cards()
    frappe.clear_cache(doctype=DOCTYPE)


def ensure_role():
    if not frappe.db.exists("Role", APPROVER):
        frappe.get_doc({"doctype": "Role", "role_name": APPROVER, "desk_access": 1}).insert(
            ignore_permissions=True
        )


def backfill_workflow_state():
    frappe.db.sql(
        """
        UPDATE `tabPersonal Cash Tracking`
        SET workflow_state = CASE docstatus
            WHEN 0 THEN 'Draft' WHEN 1 THEN 'Submitted' ELSE 'Cancelled' END
        WHERE IFNULL(workflow_state, '') = ''
        """
    )


def ensure_states_and_actions():
    for state, _ds, _role, style in STATES:
        if not frappe.db.exists("Workflow State", state):
            frappe.get_doc(
                {"doctype": "Workflow State", "workflow_state_name": state, "style": style or ""}
            ).insert(ignore_permissions=True)
    for action in ("Submit", "Request Approval", "Approve", "Reject", "Withdraw", "Revise", "Cancel"):
        if not frappe.db.exists("Workflow Action Master", action):
            frappe.get_doc(
                {"doctype": "Workflow Action Master", "workflow_action_name": action}
            ).insert(ignore_permissions=True)


def _role_exists(role):
    return bool(frappe.db.exists("Role", role))


def _transitions():
    rows = []

    def add(state, action, next_state, role, condition=None, self_approval=1):
        if _role_exists(role):
            rows.append({
                "state": state, "action": action, "next_state": next_state, "allowed": role,
                "condition": condition, "allow_self_approval": self_approval,
            })

    for role in [CASH_USER] + EXTRA_DRAFT_ROLES:
        add("Draft", "Submit", "Submitted", role, NOT_REIMB)
        add("Draft", "Request Approval", "Pending Approval", role, IS_REIMB)
    add("Pending Approval", "Approve", "Approved", APPROVER, NOT_OWN, self_approval=0)
    add("Pending Approval", "Reject", "Rejected", APPROVER)
    add("Pending Approval", "Withdraw", "Draft", CASH_USER, OWN)
    add("Rejected", "Revise", "Draft", CASH_USER, OWN)
    for role in ("Accounts Manager", "System Manager"):
        add("Submitted", "Cancel", "Cancelled", role)
        add("Approved", "Cancel", "Cancelled", role)
    return rows


def _states():
    rows = [{"state": s, "doc_status": str(ds), "allow_edit": role} for s, ds, role, _ in STATES]
    for role in EXTRA_DRAFT_ROLES:
        if _role_exists(role):
            rows.append({"state": "Draft", "doc_status": "0", "allow_edit": role})
    return rows


def ensure_workflow():
    if frappe.db.exists("Workflow", WORKFLOW):
        wf = frappe.get_doc("Workflow", WORKFLOW)
        wf.set("states", [])
        wf.set("transitions", [])
    else:
        wf = frappe.new_doc("Workflow")
        wf.workflow_name = WORKFLOW
    wf.document_type = DOCTYPE
    wf.workflow_state_field = "workflow_state"
    wf.is_active = 1
    wf.send_email_alert = 0
    wf.override_status = 0
    for row in _states():
        wf.append("states", row)
    for row in _transitions():
        wf.append("transitions", row)
    wf.flags.ignore_permissions = True
    wf.save()


def _notification(name, state, subject, message, recipients):
    doc = frappe.get_doc("Notification", name) if frappe.db.exists("Notification", name) else frappe.new_doc("Notification")
    is_new = doc.is_new()
    if is_new:
        doc.name = name
    doc.update({
        "subject": subject,
        "document_type": DOCTYPE,
        "event": "Value Change",
        "value_changed": "workflow_state",
        "condition": f'doc.transaction_type == "Reimbursement" and doc.workflow_state == "{state}"',
        "channel": "Email",
        "send_system_notification": 1,
        "enabled": 1,
        "message": message,
    })
    doc.set("recipients", recipients)
    doc.flags.ignore_permissions = True
    if is_new:
        doc.insert()
    else:
        doc.save()


def ensure_notifications():
    amount = "{{ frappe.utils.fmt_money(doc.money_in) }}"
    _notification(
        "Reimbursement Awaiting Approval",
        "Pending Approval",
        "Reimbursement request {{ doc.name }} from {{ doc.cash_tracker_person }} for " + amount + " is awaiting approval",
        "<p>{{ doc.cash_tracker_person }} has requested a reimbursement of " + amount
        + " ({{ doc.business }}).</p><p><b>Reason:</b> {{ doc.reason }}</p>"
        "<p>Open {{ frappe.utils.get_link_to_form(doc.doctype, doc.name) }} to approve or reject it.</p>",
        [{"receiver_by_role": APPROVER}, {"receiver_by_document_field": "safe_user"}],
    )
    _notification(
        "Reimbursement Approved",
        "Approved",
        "Your reimbursement {{ doc.name }} for " + amount + " has been approved",
        "<p>Your reimbursement {{ doc.name }} for " + amount + " has been approved"
        "{% if doc.safe_entry %} and paid from the Safe (entry {{ doc.safe_entry }}){% endif %}.</p>",
        [{"receiver_by_document_field": "user"}],
    )
    _notification(
        "Reimbursement Rejected",
        "Rejected",
        "Your reimbursement {{ doc.name }} was rejected: {{ doc.rejection_reason }}",
        "<p>Your reimbursement {{ doc.name }} for " + amount + " was rejected.</p>"
        "<p><b>Reason:</b> {{ doc.rejection_reason }}</p>"
        "<p>You can revise the request and send it again.</p>",
        [{"receiver_by_document_field": "user"}],
    )


def ensure_list_filter():
    if frappe.db.exists("List Filter", {"reference_doctype": DOCTYPE, "filter_name": "Pending Reimbursements"}):
        return
    frappe.get_doc({
        "doctype": "List Filter",
        "reference_doctype": DOCTYPE,
        "filter_name": "Pending Reimbursements",
        "for_user": "",
        "filters": json.dumps(PENDING_FILTERS),
    }).insert(ignore_permissions=True)


def ensure_number_cards():
    cards = [
        ("Pending Reimbursements", "Count", None),
        ("Pending Reimbursement Amount", "Sum", "money_in"),
    ]
    for label, function, field in cards:
        if frappe.db.exists("Number Card", label):
            continue
        frappe.get_doc({
            "doctype": "Number Card",
            "label": label,
            "name": label,
            "type": "Document Type",
            "document_type": DOCTYPE,
            "function": function,
            "aggregate_function_based_on": field,
            "filters_json": json.dumps(PENDING_FILTERS),
            "is_public": 1,
            "show_percentage_stats": 0,
            "module": "Cash Management",
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Workspace", "Cash Management"):
        return
    ws = frappe.get_doc("Workspace", "Cash Management")
    have = {c.number_card_name for c in ws.get("number_cards", [])}
    content = json.loads(ws.content or "[]")
    changed = False
    for label, _f, _x in reversed(cards):
        if label in have:
            continue
        ws.append("number_cards", {"number_card_name": label, "label": label})
        content.insert(0, {
            "id": frappe.generate_hash(length=10),
            "type": "number_card",
            "data": {"number_card_name": label, "col": 4},
        })
        changed = True
    if changed:
        ws.content = json.dumps(content)
        ws.flags.ignore_permissions = True
        ws.save()
