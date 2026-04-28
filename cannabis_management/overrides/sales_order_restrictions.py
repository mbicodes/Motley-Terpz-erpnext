import frappe


def before_submit(doc, method=None):
    if doc.custom_mode_of_payment == "Payment Terms":
        frappe.throw(
            msg='Sales Orders with Mode of Payment set to <b>Payment Terms</b> cannot be submitted. '
                'Change the Mode of Payment to <b>Cash on Delivery</b> before submitting.',
            title="Submission Not Allowed"
        )
