"""
Overdue-invoice reminders to the owning rep.

Policy (per client, June 2026): a customer is informally "on hold" the moment
they have ANY submitted invoice past its due date — but nothing is blocked.
Instead, each day we find every overdue invoice, figure out which user the
customer belongs to, and email that user a summary of their overdue accounts.
The email keeps going out daily until the invoice is paid (paid invoices simply
drop out of the query).

Owner resolution, in order:
  1. CRM Lead.custom_account_owner for the customer (custom_erp_customer match)
  2. Customer.account_manager (set on the customer when a CRM Deal is Won)
Invoices with no resolvable owner go to FALLBACK_RECIPIENTS so nothing is lost.

No document is ever blocked by this module.
"""

import frappe
from frappe.utils import flt, getdate, nowdate, date_diff

# Where to send overdue invoices that have no resolvable owner.
FALLBACK_RECIPIENTS = ["mbi@alltechvirtual.com"]


# ── Entry points ─────────────────────────────────────────────────────────────

def send_overdue_owner_reminders():
    """Scheduled daily. One email per owning user listing their overdue invoices."""
    today = getdate(nowdate())
    invoices = _overdue_invoices()
    if not invoices:
        return "No overdue invoices today."

    owner_cache = {}
    buckets = {}
    for inv in invoices:
        owner = _owner_for_customer(inv.customer, owner_cache)
        buckets.setdefault(owner or "__unowned__", []).append(inv)

    sent = 0
    for owner, rows in buckets.items():
        recipients = _recipients_for(owner)
        if not recipients:
            continue
        _send_email(recipients, rows, today, unowned=(owner == "__unowned__"))
        sent += 1

    return f"Sent {sent} overdue reminder email(s) covering {len(invoices)} invoice(s)."


@frappe.whitelist()
def send_now():
    """Manual trigger from the console/desk."""
    return send_overdue_owner_reminders()


@frappe.whitelist()
def preview():
    """Return the owner→invoice breakdown without sending anything (for testing)."""
    today = getdate(nowdate())
    invoices = _overdue_invoices()
    owner_cache = {}
    buckets = {}
    for inv in invoices:
        owner = _owner_for_customer(inv.customer, owner_cache)
        buckets.setdefault(owner or "__unowned__", []).append(inv)
    return {
        owner: {
            "recipients": _recipients_for(owner),
            "invoice_count": len(rows),
            "total_outstanding": round(sum(flt(r.outstanding_amount) for r in rows), 2),
            "invoices": [
                {"invoice": r.name, "customer": r.customer_name or r.customer,
                 "outstanding": flt(r.outstanding_amount), "due_date": str(r.due_date),
                 "days_overdue": int(r.days_overdue)}
                for r in rows
            ],
        }
        for owner, rows in buckets.items()
    }


# ── Core ─────────────────────────────────────────────────────────────────────

def _overdue_invoices():
    """All submitted, still-outstanding invoices whose due date has passed.
    Excludes internal customers and inter-company customers."""
    return frappe.db.sql(
        """
        SELECT si.name, si.customer, si.customer_name,
               si.outstanding_amount, si.due_date,
               DATEDIFF(CURDATE(), si.due_date) AS days_overdue
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0.01
          AND si.due_date IS NOT NULL
          AND si.due_date < CURDATE()
          AND COALESCE(c.is_internal_customer, 0) = 0
          AND (c.represents_company IS NULL OR c.represents_company = '')
          AND si.customer NOT IN (SELECT name FROM `tabCompany`)
        ORDER BY si.customer, si.due_date ASC
        """,
        as_dict=True,
    )


def _owner_for_customer(customer, cache):
    if customer in cache:
        return cache[customer]
    owner = frappe.db.get_value(
        "CRM Lead",
        {"custom_erp_customer": customer, "custom_account_owner": ["is", "set"]},
        "custom_account_owner",
    )
    if not owner:
        owner = frappe.db.get_value("Customer", customer, "account_manager")
    cache[customer] = owner or None
    return cache[customer]


def _recipients_for(owner):
    if owner == "__unowned__" or not owner:
        return list(FALLBACK_RECIPIENTS)
    info = frappe.db.get_value("User", owner, ["enabled", "email"], as_dict=True)
    if info and info.enabled and info.email:
        return [info.email]
    # owner set but not a usable User → don't lose it
    return list(FALLBACK_RECIPIENTS)


# ── Email ──────────────────────────────────────────────────────────────────

def _fmt(v):
    return "$ {:,.2f}".format(flt(v))


def _send_email(recipients, rows, today, unowned=False):
    rows = sorted(rows, key=lambda r: (r.customer_name or r.customer, getdate(str(r.due_date))))
    total = sum(flt(r.outstanding_amount) for r in rows)

    body_rows = ""
    for r in rows:
        body_rows += f"""<tr>
          <td style="padding:8px 12px;font-weight:600;border-bottom:1px solid #f1f5f9;">{r.customer_name or r.customer}</td>
          <td style="padding:8px 12px;font-family:monospace;font-size:11px;color:#64748b;border-bottom:1px solid #f1f5f9;">{r.name}</td>
          <td style="padding:8px 12px;text-align:right;font-weight:700;color:#dc2626;border-bottom:1px solid #f1f5f9;">{_fmt(r.outstanding_amount)}</td>
          <td style="padding:8px 12px;text-align:center;border-bottom:1px solid #f1f5f9;">{r.due_date}</td>
          <td style="padding:8px 12px;text-align:center;border-bottom:1px solid #f1f5f9;">
            <span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{int(r.days_overdue)}d overdue</span>
          </td>
        </tr>"""

    intro = (
        "The following customers have unpaid invoices that are past their due date. "
        "Please follow up until payment is received — you'll keep getting this reminder daily "
        "until each invoice is cleared."
    )
    if unowned:
        intro = ("These overdue invoices have no assigned account owner. " + intro)

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f9;color:#0f172a;margin:0;padding:20px;">
<div style="max-width:760px;margin:0 auto;">
  <div style="background:linear-gradient(135deg,#7f1d1d,#991b1b);border-radius:14px;padding:24px 30px;margin-bottom:16px;text-align:center;">
    <div style="font-size:20px;font-weight:800;color:#fff;">Overdue Invoice Follow-up</div>
    <div style="color:rgba(255,255,255,.8);font-size:13px;margin-top:6px;">{today}</div>
  </div>
  <div style="background:#fff;border-radius:10px;padding:14px 18px;border:1px solid #e2e8f0;margin-bottom:14px;font-size:13px;color:#334155;">
    {intro}
  </div>
  <div style="background:#fff;border-radius:10px;padding:14px 16px;border:1px solid #e2e8f0;margin-bottom:16px;">
    <span style="font-size:10px;font-weight:700;text-transform:uppercase;color:#64748b;">Total Overdue</span>
    <div style="font-size:22px;font-weight:800;color:#dc2626;">{_fmt(total)} <span style="font-size:12px;color:#94a3b8;font-weight:600;">across {len(rows)} invoice(s)</span></div>
  </div>
  <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;border:1px solid #e2e8f0;">
    <thead><tr style="background:#f8fafc;">
      <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Customer</th>
      <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Invoice</th>
      <th style="padding:8px 12px;text-align:right;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Outstanding</th>
      <th style="padding:8px 12px;text-align:center;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Due Date</th>
      <th style="padding:8px 12px;text-align:center;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Status</th>
    </tr></thead>
    <tbody>{body_rows}</tbody>
  </table>
  <div style="text-align:center;color:#94a3b8;font-size:11px;margin-top:16px;">Auto-generated daily · {today} · Do not reply.</div>
</div></body></html>"""

    frappe.sendmail(
        recipients=recipients,
        subject=f"Overdue Invoices — action needed ({today})",
        message=html,
        delayed=False,
    )
