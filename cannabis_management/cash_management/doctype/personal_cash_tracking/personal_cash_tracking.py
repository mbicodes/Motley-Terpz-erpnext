import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, today

from cannabis_management.cash_management.doctype.motley_cash_tracking.motley_cash_tracking import (
    validate_money_in_out,
)

REIMBURSEMENT = "Reimbursement"
APPROVER_ROLE = "Reimbursement Approver"


class PersonalCashTracking(Document):
    def before_insert(self):
        self.set_person_links()

    def validate(self):
        self.set_person_links()
        validate_money_in_out(self)
        if self.is_reimbursement():
            self.set_default_safe()
            self.validate_reimbursement()
        else:
            self.warn_untyped_reimbursement()

    def before_submit(self):
        if self.is_reimbursement() and self.workflow_state != "Approved":
            frappe.throw(_("Reimbursement entries can only be submitted through approval."))

    def on_update(self):
        if not self.is_reimbursement() or not self.has_value_changed("workflow_state"):
            return
        if self.workflow_state == "Pending Approval":
            frappe.msgprint(_("Your request has been sent to the Safe for approval."), alert=True)
        elif self.workflow_state == "Rejected":
            frappe.msgprint(_("Request rejected. The requester has been notified."), alert=True)

    def on_submit(self):
        if not self.is_reimbursement():
            return
        self.db_set({"approved_by": frappe.session.user, "approved_on": now_datetime()})
        if not self.paid_from_safe:
            frappe.msgprint(_("Approved. No Safe entry was created because Paid From Safe is not ticked."))
            return
        safe = self.create_safe_entry()
        self.db_set("safe_entry", safe.name)
        refresh_person_balances(self.cash_tracker_person, self.safe_person)
        frappe.msgprint(_("Approved. Safe entry {0} has been created.").format(
            frappe.utils.get_link_to_form("Safe Cash Tracking", safe.name)))

    def on_cancel(self):
        if not self.is_reimbursement() or not self.safe_entry:
            return
        safe = frappe.get_doc("Safe Cash Tracking", self.safe_entry)
        if safe.docstatus == 1:
            frappe.flags.from_personal_reimbursement = True
            try:
                safe.flags.ignore_permissions = True
                safe.cancel()
            finally:
                frappe.flags.from_personal_reimbursement = False
        refresh_person_balances(self.cash_tracker_person, self.safe_person)

    def is_reimbursement(self):
        return self.transaction_type == REIMBURSEMENT

    def set_default_safe(self):
        # Requesters cannot see these fields (permlevel 1): every reimbursement goes to
        # the Safe unless Finance unticks Paid From Safe on the entry.
        if self.paid_from_safe is None or self.paid_from_safe == "":
            self.paid_from_safe = 1
        if not self.safe_person:
            self.safe_person = get_default_safe_person()
            if not self.safe_person:
                frappe.throw(_("No active Safe is set up. Please contact Finance."))
        if self.safe_person:
            self.safe_user = frappe.db.get_value("Cash Tracker Person", self.safe_person, "user")

    def validate_reimbursement(self):
        if flt(self.money_in) <= 0 or flt(self.money_out):
            frappe.throw(_("A reimbursement request must have an amount in Money In and nothing in Money Out."))

        if self.paid_from_safe:
            safe = self.safe_person and frappe.db.get_value(
                "Cash Tracker Person", self.safe_person, ["is_active", "allow_for_safe"], as_dict=True
            )
            if not safe or not safe.is_active or not safe.allow_for_safe:
                frappe.throw(_("Please select an active Safe for this reimbursement."))
            if self.safe_person == self.cash_tracker_person:
                frappe.throw(_("Reimbursements to the Safe owner must be posted by Finance."))

        if self.workflow_state == "Rejected" and not (self.rejection_reason or "").strip():
            frappe.throw(_("Please enter a reason for rejecting this request."))

        before = self.get_doc_before_save()
        if (
            before
            and before.workflow_state == "Pending Approval"
            and self.workflow_state == "Pending Approval"
            and APPROVER_ROLE not in frappe.get_roles()
            and frappe.session.user != "Administrator"
        ):
            frappe.throw(_("This request is awaiting approval and cannot be edited. Withdraw it first to make changes."))

    def warn_untyped_reimbursement(self):
        if self.docstatus == 0 and flt(self.money_in) and "reimburs" in (self.reason or "").lower():
            frappe.msgprint(
                _("If this is a reimbursement from the Safe, set Transaction Type to Reimbursement so it goes for approval."),
                indicator="orange",
                alert=True,
            )

    def create_safe_entry(self):
        approver = frappe.utils.get_fullname(frappe.session.user)
        reason = (self.reason or "").strip()
        notes = f"Reimbursement to {self.cash_tracker_person} — {self.name}."
        if reason:
            notes += f" {reason}"
        notes += f" Approved by {approver}."
        safe = frappe.get_doc({
            "doctype": "Safe Cash Tracking",
            "cash_tracker_person": self.safe_person,
            "transaction_date": today(),
            "money_in": 0,
            "money_out": flt(self.money_in),
            "transaction_type": REIMBURSEMENT,
            "business": self.business,
            "transaction_notes": notes,
            "receipt": self.receipt,
            "personal_entry": self.name,
        })
        safe.flags.ignore_permissions = True
        safe.insert()
        safe.submit()
        return safe

    def set_person_links(self):
        if not self.cash_tracker_person:
            from cannabis_management.cash_management.doctype.motley_cash_tracking.motley_cash_tracking import (
                get_person_for_user,
            )
            self.cash_tracker_person = get_person_for_user(frappe.session.user)
        if self.cash_tracker_person:
            person = frappe.db.get_value(
                "Cash Tracker Person", self.cash_tracker_person, ["user", "employee"], as_dict=True
            )
            self.user = person.user
            self.employee = person.employee
        elif not self.user:
            self.user = frappe.session.user


def get_default_safe_person():
    return frappe.db.get_value(
        "Cash Tracker Person", {"allow_for_safe": 1, "is_active": 1}, "name", order_by="creation asc"
    )


def refresh_person_balances(*persons):
    from cannabis_management.cash_management.utils.cash_utils import update_cash_balance_ledger

    for person in {p for p in persons if p}:
        update_cash_balance_ledger(frappe._dict(cash_tracker_person=person), None)


@frappe.whitelist()
def get_safe_defaults():
    return {"safe_person": get_default_safe_person()}


@frappe.whitelist()
def set_rejection_reason(name, reason):
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Please enter a reason for rejecting this request."))
    if APPROVER_ROLE not in frappe.get_roles() and frappe.session.user != "Administrator":
        frappe.throw(_("Only a Reimbursement Approver can reject this request."), frappe.PermissionError)
    doc = frappe.get_doc("Personal Cash Tracking", name)
    if doc.transaction_type != REIMBURSEMENT or doc.workflow_state != "Pending Approval":
        frappe.throw(_("Only reimbursement requests that are pending approval can be rejected."))
    doc.db_set("rejection_reason", reason)
    return reason


@frappe.whitelist()
def get_pending_reimbursements():
    from cannabis_management.cash_management.permissions import can_see_reimbursement_queue

    if not can_see_reimbursement_queue():
        return []
    rows = frappe.get_all(
        "Personal Cash Tracking",
        filters={"transaction_type": REIMBURSEMENT, "workflow_state": "Pending Approval", "docstatus": 0},
        fields=["name", "cash_tracker_person as person", "business", "transaction_date as date",
                "money_in as amount", "reason", "modified", "user", "owner"],
        order_by="transaction_date asc",
        ignore_permissions=True,
    )
    now = now_datetime().date()
    me = frappe.session.user
    approver = APPROVER_ROLE in frappe.get_roles()
    for r in rows:
        r["days_pending"] = (now - r.pop("modified").date()).days
        r["can_act"] = approver and not _is_requester(r, me)
        r.pop("owner")
        r.pop("user")
    return rows


def _is_requester(doc, user):
    return user in {doc.get("user"), doc.get("owner")}


@frappe.whitelist(methods=["POST"])
def reimbursement_action(name, action, reason=None):
    """Approve or Reject a pending reimbursement straight from the Safe panel."""
    if action not in ("Approve", "Reject"):
        frappe.throw(_("You are not allowed to perform this action on this reimbursement."), frappe.PermissionError)

    # Lock the row so a double click cannot approve (and post to the Safe) twice.
    state = frappe.db.get_value("Personal Cash Tracking", name, "workflow_state", for_update=True)
    doc = frappe.get_doc("Personal Cash Tracking", name)
    user = frappe.session.user
    if (
        doc.transaction_type != REIMBURSEMENT
        or state != "Pending Approval"
        or doc.docstatus != 0
        or APPROVER_ROLE not in frappe.get_roles(user)
        or _is_requester(doc, user)
    ):
        frappe.throw(_("You are not allowed to perform this action on this reimbursement."), frappe.PermissionError)

    if action == "Reject":
        reason = (reason or "").strip()
        if not reason:
            frappe.throw(_("Please enter a reason for rejecting this request."))
        doc.db_set("rejection_reason", reason, update_modified=False)

    from frappe.model.workflow import apply_workflow

    doc = apply_workflow(doc, action)
    # apply_workflow's own pop-ups are replaced by the one message the panel shows
    frappe.local.message_log = []

    safe_entry = frappe.db.get_value("Personal Cash Tracking", name, "safe_entry") if action == "Approve" else None
    if action == "Reject":
        message = _("Request rejected. The requester has been notified.")
    elif safe_entry:
        message = _("Approved. Safe entry {0} has been created.").format(safe_entry)
    else:
        message = _("Approved. No Safe entry was created because Paid From Safe is not ticked.")
    return {"workflow_state": doc.workflow_state, "safe_entry": safe_entry, "message": message}
