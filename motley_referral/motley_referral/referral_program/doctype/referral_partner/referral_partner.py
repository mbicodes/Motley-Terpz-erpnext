import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class ReferralPartner(Document):
    def validate(self):
        s = frappe.get_cached_doc("Referral Settings")
        for f in ("year1_rate", "year2_rate", "year1_months", "year2_months"):
            if self.get(f) in (None, ""):
                self.set(f, s.get(f))
        if self.status == "Terminated" and not self.termination_date:
            frappe.throw(_("Termination Date is mandatory when the partner is Terminated."))
        if self.email:
            frappe.utils.validate_email_address(self.email, throw=True)

    @frappe.whitelist()
    def activate(self):
        frappe.only_for(("Referral Manager", "System Manager"))
        if self.status == "Active":
            frappe.throw(_("This partner is already Active."))
        missing = [
            lbl
            for f, lbl in (
                ("agreement_date", "Agreement Date"),
                ("signed_agreement", "Signed Agreement"),
                ("compliance_confirmed", "Compliance Confirmed"),
                ("tax_id", "Tax ID"),
                ("email", "Email"),
            )
            if not self.get(f)
        ]
        if missing:
            frappe.throw(_("Cannot activate. Please complete: {0}.").format(", ".join(missing)))
        self.supplier = self.supplier or self.make_supplier()
        self.portal_user = self.make_portal_user()
        self.status = "Active"
        self.flags.ignore_permissions = True
        self.save()
        return self.status

    def make_supplier(self):
        group = frappe.get_cached_doc("Referral Settings").supplier_group or "Referral Partners"
        if not frappe.db.exists("Supplier Group", group):
            frappe.get_doc(
                {"doctype": "Supplier Group", "supplier_group_name": group, "parent_supplier_group": "All Supplier Groups"}
            ).insert(ignore_permissions=True)
        sup = frappe.new_doc("Supplier")
        sup.supplier_name = self.partner_name
        sup.supplier_group = group
        sup.supplier_type = self.partner_type or "Individual"
        sup.tax_id = self.tax_id
        sup.default_currency = "USD"
        if sup.meta.has_field("irs_1099"):
            sup.irs_1099 = 1
        sup.insert(ignore_permissions=True)
        return sup.name

    def make_portal_user(self):
        if self.portal_user and frappe.db.exists("User", self.portal_user):
            return self.portal_user
        if frappe.db.exists("User", self.email):
            user = frappe.get_doc("User", self.email)
            if not any(r.role == "Referral Partner" for r in user.roles):
                user.append("roles", {"role": "Referral Partner"})
                user.save(ignore_permissions=True)
            return user.name
        user = frappe.new_doc("User")
        user.update(
            {
                "email": self.email,
                "first_name": self.partner_name,
                "user_type": "Website User",
                "send_welcome_email": 0,
                "enabled": 1,
            }
        )
        user.append("roles", {"role": "Referral Partner"})
        user.insert(ignore_permissions=True)
        try:
            user.send_welcome_mail_to_user()
        except Exception:
            frappe.log_error(title="Referral Partner welcome email", message=frappe.get_traceback())
        return user.name

    @frappe.whitelist()
    def terminate(self, termination_date=None):
        frappe.only_for(("Referral Manager", "System Manager"))
        if self.status != "Active":
            frappe.throw(_("Only an Active partner can be terminated."))
        self.termination_date = getdate(termination_date or nowdate())
        self.status = "Terminated"
        self.flags.ignore_permissions = True
        self.save()
        return self.status
