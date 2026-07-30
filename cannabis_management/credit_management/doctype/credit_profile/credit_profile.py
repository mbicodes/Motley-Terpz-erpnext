import frappe
from frappe.model.document import Document
from frappe.utils import flt

# Credit score bands — American standard (FICO-style ranges).
SCORE_BANDS = [
    (800, 850, "Exceptional"),
    (740, 799, "Very Good"),
    (670, 739, "Good"),
    (580, 669, "Fair"),
    (300, 579, "Poor"),
]


def band_for_score(score):
    score = int(flt(score))
    if not score:
        return ""
    for low, high, label in SCORE_BANDS:
        if low <= score <= high:
            return label
    # Out of range — clamp to nearest meaningful band.
    if score > 850:
        return "Exceptional"
    if score < 300:
        return "Poor"
    return ""


class CreditProfile(Document):
    def validate(self):
        self.credit_band = band_for_score(self.credit_score)

        # A COD account cannot carry credit terms.
        if self.status == "COD" and self.term and self.term != "COD":
            self.term = "COD"

        # Credit Approved must have the mandatory pre-conditions on file.
        if self.status == "Credit Approved":
            missing = []
            if not self.agreement_on_file:
                missing.append("signed Credit Agreement")
            if not self.md_approval_reference:
                missing.append("MD approval reference")
            if not (self.ap_contact_name and self.ap_contact_email):
                missing.append("named AP contact (name + email)")
            if not self.reconciliation_clause_ack:
                missing.append("reconciliation clause acknowledgement")
            if not self.approved_line:
                missing.append("approved line")
            if missing:
                frappe.throw(
                    "Cannot set status to <b>Credit Approved</b> — missing: "
                    + ", ".join(missing)
                    + ".<br>Every customer is COD until credit is formally approved and documented."
                )
            if self.term == "COD":
                frappe.throw("A Credit Approved account needs a credit term (Net 15 or Net 30).")


def get_or_create(customer):
    """Return the Credit Profile for a customer, creating a default COD one if
    none exists. Safe to call from hooks."""
    name = frappe.db.get_value("Credit Profile", {"customer": customer})
    if name:
        return frappe.get_doc("Credit Profile", name)
    doc = frappe.get_doc({
        "doctype": "Credit Profile",
        "customer": customer,
        "legal_buyer_name": frappe.db.get_value("Customer", customer, "customer_name"),
        "status": "COD",
        "term": "COD",
    })
    doc.insert(ignore_permissions=True)
    return doc
