import frappe
from frappe.model.document import Document
from frappe.utils import add_days, today, getdate


class IRSForm8300Log(Document):

    def before_save(self):
        # Auto-set deadline from payment entry posting date
        if self.payment_entry and not self.transaction_date:
            self.transaction_date = frappe.db.get_value(
                "Payment Entry", self.payment_entry, "posting_date"
            )

        if self.transaction_date and not self.filing_deadline:
            self.filing_deadline = add_days(self.transaction_date, 15)

        # Auto-populate customer info from Payment Entry
        if self.payment_entry and not self.payer_name:
            pe = frappe.get_doc("Payment Entry", self.payment_entry)
            self.customer = pe.party
            self.payer_name = frappe.db.get_value(
                "Customer", pe.party, "customer_name"
            )
            self.cash_amount = pe.paid_amount
            self.nature_of_transaction = "Cannabis retail sale"

        # Check if attachment exists — auto set to Reported
        if self.name and not self.is_new():
            has_attachment = frappe.db.exists("File", {
                "attached_to_doctype": "Payment Entry",
                "attached_to_name": self.payment_entry
            })
            if has_attachment and self.filing_status in ("Pending", "Overdue"):
                self.filing_status = "Reported"
                if not self.filing_date:
                    self.filing_date = today()

        # Flip to Overdue if deadline passed and still pending
        if self.filing_status == "Pending":
            if self.filing_deadline and getdate(self.filing_deadline) < getdate(today()):
                self.filing_status = "Overdue"

    def after_insert(self):
        self.send_internal_alert()

    def send_internal_alert(self):
        recipients = frappe.get_all(
            "Has Role",
            filters={"role": "System Manager"},
            pluck="parent"
        )
        if not recipients:
            return

        frappe.sendmail(
            recipients=list(set(recipients)),
            subject=f"[ACTION REQUIRED] IRS Form 8300 Due by {self.filing_deadline}",
            message=f"""
                A cash transaction over $10,000 has been logged and requires filing.<br><br>
                <b>Customer:</b> {self.payer_name}<br>
                <b>Payment Entry:</b> {self.payment_entry}<br>
                <b>Amount:</b> ${self.cash_amount:,.2f}<br>
                <b>Transaction Date:</b> {self.transaction_date}<br>
                <b>Filing Deadline:</b> {self.filing_deadline}<br><br>
                <a href="{frappe.utils.get_url()}/app/irs-form-8300-log/{self.name}">
                    Open Record →
                </a>
            """
        )