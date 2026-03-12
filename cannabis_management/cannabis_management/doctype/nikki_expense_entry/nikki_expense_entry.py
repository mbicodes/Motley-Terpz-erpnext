import frappe
from frappe.model.document import Document


class NikkiExpenseEntry(Document):
    
    def validate(self):
        frappe.msgprint("Hello world", alert=True)

    def after_insert(self):
        self.create_payment_entry()

    def create_payment_entry(self):
        try:
            if not self.money_in and not self.money_out:
                frappe.log_error(
                    title=f"Nikki Expense Entry — Missing amount [{self.name}]",
                    message=f"Both Money In and Money Out are empty on {self.name}."
                )
                frappe.throw("Either Money In or Money Out must be set to create a Payment Entry.")

            is_receive = bool(self.money_in and self.money_in > 0)
            amount = self.money_in if is_receive else self.money_out
            payment_type = "Receive" if is_receive else "Pay"

            try:
                company_doc = frappe.get_cached_doc("Company", self.business)
            except Exception:
                frappe.log_error(
                    title=f"Nikki Expense Entry — Company fetch failed [{self.name}]",
                    message=frappe.get_traceback()
                )
                frappe.throw(f"Could not load Company <b>{self.business}</b>.")

            cash_account = company_doc.default_cash_account
            if not cash_account:
                frappe.log_error(
                    title=f"Nikki Expense Entry — No Default Cash Account [{self.name}]",
                    message=f"Company: {self.business} has no Default Cash Account configured."
                )
                frappe.throw(
                    f"Default Cash Account not set for Company <b>{self.business}</b>. "
                    f"Please configure it under Company > Accounts tab."
                )

            if is_receive:
                offset_account = company_doc.default_receivable_account
                label = "Default Receivable Account"
            else:
                offset_account = company_doc.default_payable_account
                label = "Default Payable Account"

            if not offset_account:
                frappe.log_error(
                    title=f"Nikki Expense Entry — No {label} [{self.name}]",
                    message=(
                        f"Company: {self.business}\n"
                        f"Payment Type: {payment_type}\n"
                        f"Expected field: {label}\n"
                        f"Value was empty."
                    )
                )
                frappe.throw(
                    f"{label} not set for Company <b>{self.business}</b>. "
                    f"Please configure it under Company > Accounts tab."
                )

            pe = frappe.new_doc("Payment Entry")
            pe.payment_type   = payment_type
            pe.posting_date   = self.transaction_date
            pe.company        = self.business
            pe.reference_no   = self.invoice_no or None
            pe.reference_date = self.transaction_date if self.invoice_no else None
            pe.remarks        = self.transaction_notes or f"Auto-created from {self.name}"

            if is_receive:
                pe.paid_from = offset_account
                pe.paid_to   = cash_account
            else:
                pe.paid_from = cash_account
                pe.paid_to   = offset_account

            pe.paid_amount     = amount
            pe.received_amount = amount

            try:
                pe.insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(
                    title=f"Nikki Expense Entry — Payment Entry insert failed [{self.name}]",
                    message=(
                        f"Nikki Entry: {self.name}\n"
                        f"Payment Type: {payment_type}\n"
                        f"Amount: {amount}\n"
                        f"Paid From: {pe.paid_from}\n"
                        f"Paid To: {pe.paid_to}\n\n"
                        f"{frappe.get_traceback()}"
                    )
                )
                frappe.throw(
                    "Failed to insert Payment Entry. Check the Error Log for details."
                )

            try:
                frappe.db.set_value("Nikki Expense Entry", self.name, "payment_entry", pe.name)
            except Exception:
                frappe.log_error(
                    title=f"Nikki Expense Entry — Failed to save PE reference [{self.name}]",
                    message=(
                        f"Payment Entry {pe.name} was created successfully but could not be "
                        f"linked back to Nikki Expense Entry {self.name}.\n\n"
                        f"{frappe.get_traceback()}"
                    )
                )

            frappe.msgprint(
                f"Payment Entry <b>{pe.name}</b> created.",
                indicator="green",
                alert=True
            )

        except frappe.ValidationError:
            raise

        except Exception:
            frappe.log_error(
                title=f"Nikki Expense Entry — Unexpected error [{self.name}]",
                message=frappe.get_traceback()
            )
            frappe.throw(
                "An unexpected error occurred while creating the Payment Entry. "
                "Check the Error Log for details."
            )