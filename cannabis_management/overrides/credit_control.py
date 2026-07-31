"""Credit control — COD default gate, overdue notifications/freeze, and the
company-wide Disable Credit Sale switch.

Design (per spec):
  * Every customer is COD by default. A Sales Order with custom_mode_of_payment
    = "Payment Terms" cannot be submitted unless the customer has a Credit Limit
    (Customer.custom_credit_limit) set — i.e. credit was formally approved.
  * Cash On Delivery orders are always exempt.
  * When Selling Settings "Disable Credit Sale" is on (auto-enabled once total AR
    exceeds $400,000), no Payment Terms order can be submitted.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, date_diff

PAYMENT_TERMS = "Payment Terms"
NOTIFY_ROLES = ("Accounts Manager", "Operations")
NOTIFY_USERS = ("imran@motleyterpz.com",)
AR_CAP = 400000
OVERDUE_DAYS = 5
OVERDUE_OUTSTANDING = 1000


# ---------------------------------------------------------------------------
# Sales Order gate (before_submit)
# ---------------------------------------------------------------------------

def check_credit_on_sales_order(doc, method=None):
    if getattr(doc, "custom_mode_of_payment", None) != PAYMENT_TERMS:
        return  # COD / anything else is exempt

    if frappe.db.get_single_value("Selling Settings", "custom_disable_credit_sale"):
        frappe.throw(
            _("Credit sales are currently disabled (total AR cap reached). "
              "Only Cash On Delivery orders can be submitted."),
            title=_("Credit Sale Disabled"),
        )

    limit = flt(frappe.db.get_value("Customer", doc.customer, "custom_credit_limit"))
    if not limit:
        frappe.throw(
            _("{0} has no approved Credit Limit — credit is not formally approved. "
              "Create and submit a Credit Approval for this customer, or set the order "
              "to Cash On Delivery.").format(doc.customer),
            title=_("Credit Not Approved"),
        )


# ---------------------------------------------------------------------------
# Notification recipients
# ---------------------------------------------------------------------------

def _recipients():
    emails = set()
    for role in NOTIFY_ROLES:
        for u in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"):
            if "@" in (u or "") and frappe.db.get_value("User", u, "enabled"):
                emails.add(u)
    for u in NOTIFY_USERS:
        if frappe.db.exists("User", u):
            emails.add(u)
    return list(emails)


# ---------------------------------------------------------------------------
# Daily: due-date notifications, overdue freeze
# ---------------------------------------------------------------------------

def run_credit_notifications():
    recipients = _recipients()
    if not recipients:
        return
    tdy = getdate(today())

    open_invoices = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["name", "customer", "due_date", "outstanding_amount"],
    )

    # 1) Invoices whose due date is today.
    due_today = [i for i in open_invoices if i.due_date and getdate(i.due_date) == tdy]
    for inv in due_today:
        _notify(recipients, subject=f"Invoice {inv.name} is due today",
                body=f"Sales Invoice <b>{inv.name}</b> for <b>{inv.customer}</b> "
                     f"(outstanding {frappe.utils.fmt_money(inv.outstanding_amount)}) is due today.")

    # 2) Overdue > 5 days AND customer outstanding > $1,000 -> notify + freeze.
    outstanding_by_customer = {}
    for i in open_invoices:
        outstanding_by_customer[i.customer] = outstanding_by_customer.get(i.customer, 0) + flt(i.outstanding_amount)

    frozen = set()
    for inv in open_invoices:
        if not inv.due_date:
            continue
        days = date_diff(tdy, getdate(inv.due_date))
        cust_outstanding = outstanding_by_customer.get(inv.customer, 0)
        if days > OVERDUE_DAYS and cust_outstanding > OVERDUE_OUTSTANDING and inv.customer not in frozen:
            frozen.add(inv.customer)
            _freeze_customer(inv.customer)
            _notify(
                recipients,
                subject=f"Customer frozen — {inv.customer} overdue",
                body=f"<b>{inv.customer}</b> has an invoice ({inv.name}) more than {OVERDUE_DAYS} days "
                     f"overdue and total outstanding of {frappe.utils.fmt_money(cust_outstanding)} "
                     f"(over ${OVERDUE_OUTSTANDING:,}). The customer has been frozen and flagged "
                     f"'Credit Limit Cross'.",
            )
    frappe.db.commit()


def _freeze_customer(customer):
    frappe.db.set_value("Customer", customer, {
        "is_frozen": 1,
        "custom_credit_limit_cross": 1,
    })


def _notify(recipients, subject, body):
    try:
        frappe.sendmail(recipients=recipients, subject=subject, message=body)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Credit notification failed")


# ---------------------------------------------------------------------------
# Daily: auto-enable Disable Credit Sale when total AR exceeds the cap
# ---------------------------------------------------------------------------

def sync_disable_credit_sale():
    total_ar = flt(frappe.db.sql(
        "SELECT COALESCE(SUM(outstanding_amount),0) FROM `tabSales Invoice` "
        "WHERE docstatus=1 AND outstanding_amount>0"
    )[0][0])
    if total_ar >= AR_CAP and not frappe.db.get_single_value("Selling Settings", "custom_disable_credit_sale"):
        frappe.db.set_value("Selling Settings", "Selling Settings", "custom_disable_credit_sale", 1)
        frappe.db.commit()
        recipients = _recipients()
        if recipients:
            _notify(recipients, subject="Credit sales auto-disabled",
                    body=f"Total AR reached {frappe.utils.fmt_money(total_ar)} (cap ${AR_CAP:,}). "
                         f"'Disable Credit Sale' has been turned on — Payment Terms orders are blocked.")


def run_daily():
    run_credit_notifications()
    sync_disable_credit_sale()
