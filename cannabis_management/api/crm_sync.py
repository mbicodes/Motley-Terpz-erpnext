"""
CRM Sync — nightly job (Mon–Fri).
For every CRM Lead with custom_erp_customer set, pulls live AR/financial data
from ERPNext and writes it back to the CRM Lead (read-only section).

Fields synced per spec:
  AR Balance · AR Aging (days) · AR Status · COD Flag
  Last Invoice Date / Amount · Last Payment Date
  MTD Revenue · 8-Week Trailing Revenue · Payment Terms · Last Synced

AR Status computation (per FRAPPE CRM field spec):
  Clean   — AR Balance = $0
  Watch   — AR > $0, aging 1–30 days
  Overdue — aging 31–90 days
  Blocked — aging > 90 days
"""

import frappe
from frappe.utils import flt, nowdate, getdate, now_datetime
from datetime import timedelta


BLOCKED_AR_THRESHOLD  = None  # disabled — no dollar blocking limit
BLOCKED_AGING_DAYS    = 90
OVERDUE_AGING_DAYS    = 30


def sync_crm_ar_data():
    """Scheduled nightly entry point."""
    if not frappe.db.exists("DocType", "CRM Lead"):
        return
    leads = frappe.get_all(
        "CRM Lead",
        filters=[["custom_erp_customer", "not in", ["", None]]],
        fields=["name", "custom_erp_customer"],
    )
    ok = 0
    for lead in leads:
        try:
            _sync_lead(lead.name, lead.custom_erp_customer)
            ok += 1
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"[crm_sync] failed for lead {lead.name} / customer {lead.custom_erp_customer}",
            )
    frappe.db.commit()
    frappe.logger().info(f"[crm_sync] synced {ok}/{len(leads)} leads")


@frappe.whitelist()
def sync_now(lead_name=None):
    """Manual trigger from desk — sync a single lead or all leads."""
    if lead_name:
        lead = frappe.get_value("CRM Lead", lead_name, ["custom_erp_customer"], as_dict=True)
        if not lead or not lead.custom_erp_customer:
            frappe.throw("Lead has no linked ERPNext Customer (custom_erp_customer).")
        _sync_lead(lead_name, lead.custom_erp_customer)
        frappe.db.commit()
        return f"synced {lead_name}"
    sync_crm_ar_data()
    return "full sync done"


# ── Core sync ─────────────────────────────────────────────────────────────────

def _sync_lead(lead_name, customer):
    data = _compute_ar_data(customer)
    frappe.db.set_value("CRM Lead", lead_name, {
        "custom_ar_balance":          data["ar_balance"],
        "custom_ar_aging_days":       data["aging_days"],
        "custom_ar_status":           data["ar_status"],
        "custom_last_invoice_date":   data["last_invoice_date"],
        "custom_last_invoice_amount": data["last_invoice_amount"],
        "custom_last_payment_date":   data["last_payment_date"],
        "custom_mtd_revenue":         data["mtd_revenue"],
        "custom_trailing_8w_revenue": data["trailing_8w"],
        "custom_payment_terms":       data["payment_terms"],
        "custom_cod_flag":            1 if _is_cod_customer(data["payment_terms"]) else 0,
        "custom_last_sync":           now_datetime(),
    }, update_modified=False)



def _is_cod_customer(payment_terms):
    if not payment_terms:
        return False
    return "cod" in payment_terms.lower() or "cash on delivery" in payment_terms.lower()


def _compute_ar_data(customer):
    today = getdate(nowdate())

    # ── AR balance + max aging ────────────────────────────────────────────────
    ar = frappe.db.sql("""
        SELECT
            COALESCE(SUM(outstanding_amount), 0)          AS balance,
            COALESCE(MAX(DATEDIFF(CURDATE(), due_date)), 0) AS max_aging
        FROM `tabSales Invoice`
        WHERE customer = %s
          AND docstatus = 1
          AND outstanding_amount > 0.01
    """, customer, as_dict=True)

    ar_balance  = flt(ar[0].balance)  if ar else 0.0
    aging_days  = int(ar[0].max_aging) if ar else 0

    # ── AR Status ─────────────────────────────────────────────────────────────
    if aging_days > BLOCKED_AGING_DAYS:  # AR balance threshold removed
        ar_status = "Blocked"
    elif aging_days > OVERDUE_AGING_DAYS:
        ar_status = "Overdue"
    elif ar_balance > 0.01:
        ar_status = "Watch"
    else:
        ar_status = "Clean"

    # ── Last invoice ──────────────────────────────────────────────────────────
    last_inv = frappe.db.sql("""
        SELECT posting_date, grand_total
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1
        ORDER BY posting_date DESC, creation DESC
        LIMIT 1
    """, customer, as_dict=True)

    # ── Last payment ──────────────────────────────────────────────────────────
    last_pay = frappe.db.sql("""
        SELECT posting_date
        FROM `tabPayment Entry`
        WHERE party = %s
          AND party_type = 'Customer'
          AND docstatus = 1
          AND payment_type = 'Receive'
        ORDER BY posting_date DESC, creation DESC
        LIMIT 1
    """, customer, as_dict=True)

    # ── MTD revenue ───────────────────────────────────────────────────────────
    mtd_start = today.replace(day=1)
    mtd = frappe.db.sql("""
        SELECT COALESCE(SUM(grand_total), 0) AS rev
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1
          AND posting_date BETWEEN %s AND %s
    """, (customer, str(mtd_start), str(today)), as_dict=True)

    # ── 8-week trailing ───────────────────────────────────────────────────────
    eight_weeks_ago = today - timedelta(weeks=8)
    t8w = frappe.db.sql("""
        SELECT COALESCE(SUM(grand_total), 0) AS rev
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1
          AND posting_date BETWEEN %s AND %s
    """, (customer, str(eight_weeks_ago), str(today)), as_dict=True)

    # ── Payment terms ─────────────────────────────────────────────────────────
    pt = frappe.db.get_value("Customer", customer, "payment_terms") or ""

    return {
        "ar_balance":         ar_balance,
        "aging_days":         aging_days,
        "ar_status":          ar_status,
        "last_invoice_date":  last_inv[0].posting_date   if last_inv else None,
        "last_invoice_amount": flt(last_inv[0].grand_total) if last_inv else 0.0,
        "last_payment_date":  last_pay[0].posting_date   if last_pay else None,
        "mtd_revenue":        flt(mtd[0].rev)            if mtd else 0.0,
        "trailing_8w":        flt(t8w[0].rev)            if t8w else 0.0,
        "payment_terms":      pt,
    }
