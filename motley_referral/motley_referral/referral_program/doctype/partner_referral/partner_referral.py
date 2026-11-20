import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

OPEN = ("Submitted", "Under Review", "Acknowledged")


class PartnerReferral(Document):
    def before_validate(self):
        if self.is_new():
            if not self.referral_partner:
                from motley_referral.permissions import partner_of

                self.referral_partner = partner_of(frappe.session.user)
            self.submitted_on = nowdate()
            self.status = "Submitted"

    def validate(self):
        if not self.referral_partner:
            frappe.throw(_("Referral Partner is required."))
        if self.is_new():
            partner_status = frappe.db.get_value("Referral Partner", self.referral_partner, "status")
            if partner_status != "Active":
                frappe.throw(_("New referrals can only be submitted by an Active partner."))
        if self.email:
            frappe.utils.validate_email_address(self.email, throw=True)
        before = self.get_doc_before_save()
        prev = before.status if before else None
        if prev == "Acknowledged" and self.status != "Acknowledged":
            frappe.throw(_("An acknowledged referral cannot change status."))
        if prev == "Acknowledged" and before.customer != self.customer:
            frappe.throw(_("The customer of an acknowledged referral cannot be changed."))
        if self.status == "Rejected":
            if not self.rejection_reason:
                frappe.throw(_("Please select a rejection reason."))
            if self.rejection_reason == "Other" and not self.rejection_note:
                frappe.throw(_("A rejection note is mandatory when the reason is Other."))
        if self.status == "Acknowledged" and prev != "Acknowledged":
            self.check_acknowledge()

    def check_acknowledge(self):
        roles = [r.role for r in frappe.get_cached_doc("Referral Settings").get("acknowledger_roles") or []]
        user_roles = set(frappe.get_roles())
        if frappe.session.user != "Administrator" and not (user_roles & set(roles)):
            frappe.throw(_("You are not allowed to acknowledge referrals. Required role: {0}.").format(", ".join(roles) or _("not configured in Referral Settings")))
        if not self.customer:
            frappe.throw(_("Link or create a Customer before acknowledging this referral."))
        if frappe.db.get_value("Referral Partner", self.referral_partner, "status") != "Active":
            frappe.throw(_("Only an Active partner can have referrals acknowledged."))
        other = frappe.db.exists(
            "Partner Referral", {"customer": self.customer, "name": ["!=", self.name], "status": ["in", OPEN]}
        )
        linked = frappe.db.get_value("Customer", self.customer, "partner_referral")
        if other or (linked and linked != self.name):
            frappe.throw(_("Customer {0} is already linked to referral {1}.").format(self.customer, other or linked))
        self.acknowledged_by = frappe.session.user
        self.acknowledged_on = getdate(nowdate())
        self.window_status = "Awaiting first payment"
        self.current_month_no = 0

    def after_insert(self):
        from motley_referral import notifications

        self.db_set("duplicate_check_result", duplicate_check(self), update_modified=False)
        try:
            notifications.notify("submitted_partner", ref=self)
            notifications.notify("submitted_team", ref=self)
        except Exception:
            frappe.log_error(title="Referral submit notification", message=frappe.get_traceback())

    def on_update(self):
        from motley_referral import notifications

        before = self.get_doc_before_save()
        prev = before.status if before else None
        if self.status == "Acknowledged" and prev != "Acknowledged":
            frappe.db.set_value(
                "Customer",
                self.customer,
                {"referral_partner": self.referral_partner, "partner_referral": self.name},
                update_modified=False,
            )
            attachments = []
            try:
                self.db_set("acknowledgement_letter", generate_letter(self), update_modified=False)
                attachments = [frappe.attach_print(self.doctype, self.name, print_format="Acknowledgement Letter")]
            except Exception:
                frappe.log_error(title="Referral acknowledgement letter", message=frappe.get_traceback())
            try:
                notifications.notify("acknowledged", ref=self, attachments=attachments)
            except Exception:
                frappe.log_error(title="Referral acknowledged email", message=frappe.get_traceback())
        elif self.status == "Rejected" and prev != "Rejected":
            try:
                notifications.notify("rejected", ref=self)
            except Exception:
                frappe.log_error(title="Referral rejected email", message=frappe.get_traceback())

    @frappe.whitelist()
    def acknowledge(self, customer=None, create_customer=0):
        """Acknowledge from the form or the Board: links or creates the Customer, then saves status = Acknowledged."""
        if int(create_customer or 0) and not customer:
            customer = self.create_customer()
        if customer:
            self.customer = customer
        self.status = "Acknowledged"
        self.save()
        return self

    def create_customer(self):
        existing = frappe.db.exists("Customer", {"customer_name": self.business_name})
        if existing:
            frappe.throw(_("A customer named {0} already exists. Link it instead of creating a new one.").format(self.business_name))
        c = frappe.new_doc("Customer")
        c.customer_name = self.business_name
        c.customer_type = "Company"
        c.customer_group = frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups"
        c.territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
        c.email_id = self.email
        c.insert(ignore_permissions=True)
        return c.name

    @frappe.whitelist()
    def reject(self, reason, note=None):
        frappe.only_for(("Referral Manager", "System Manager"))
        self.status = "Rejected"
        self.rejection_reason = reason
        self.rejection_note = note
        self.save()
        return self


def duplicate_check(ref):
    """Flag an existing customer, lead, opportunity or open referral for the same business or email."""
    hits = []
    biz = (ref.business_name or "").strip()
    email = (ref.email or "").strip()

    def add(kind, name):
        hits.append(f"{kind} {name}")

    if biz:
        for n in frappe.get_all("Customer", filters={"customer_name": biz}, pluck="name", limit=3):
            add("Customer", n)
        for n in frappe.get_all("Lead", filters={"company_name": biz}, pluck="name", limit=3):
            add("Lead", n)
        if frappe.get_meta("Opportunity").has_field("customer_name"):
            for n in frappe.get_all("Opportunity", filters={"customer_name": biz}, pluck="name", limit=3):
                add("Opportunity", n)
        for n in frappe.get_all(
            "Partner Referral", filters={"business_name": biz, "name": ["!=", ref.name], "status": ["in", OPEN]}, pluck="name", limit=3
        ):
            add("Referral", n)
    if email:
        for n in frappe.get_all("Lead", filters={"email_id": email}, pluck="name", limit=3):
            add("Lead", n)
        for n in frappe.get_all("Customer", filters={"email_id": email}, pluck="name", limit=3):
            add("Customer", n)
        for n in frappe.get_all("Contact Email", filters={"email_id": email, "parenttype": "Contact"}, pluck="parent", limit=3):
            add("Contact", n)
        for n in frappe.get_all(
            "Partner Referral", filters={"email": email, "name": ["!=", ref.name], "status": ["in", OPEN]}, pluck="name", limit=3
        ):
            add("Referral", n)
    hits = list(dict.fromkeys(hits))
    return "Clear" if not hits else "Match found: " + ", ".join(hits)


def generate_letter(ref):
    from frappe.utils.file_manager import save_file

    pdf = frappe.attach_print(ref.doctype, ref.name, print_format="Acknowledgement Letter")
    f = save_file(f"Acknowledgement Letter {ref.name}.pdf", pdf["fcontent"], ref.doctype, ref.name, is_private=1)
    return f.file_url
