"""
Sales Invoice doc hooks — AR Policy enforcement.

Fires on validate (every save, draft or otherwise) so Finance is blocked
before the invoice ever reaches submission.

Checks:
  1. Total company AR (from GL Entry ledger) + this invoice would not breach $400k.
  2. Warn if this customer already has invoices 30+ days past due.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

AR_CAP_HARD    = 400_000.0
AR_CAP_WARN    = 300_000.0

RECEIVABLE_ACCOUNTS = ("Debtors - MT", "Debtors - TSBC")

AR_ALERT_RECIPIENTS = [
    "matt@motleyterpz.com",
    "jamie@motleyterpz.com",
    "imran@motleyterpz.com",
    "mbi@alltechvirtual.com",
]


# ── Hook entry point ──────────────────────────────────────────────────────────

def validate(doc, method=None):
    _check_total_ar_cap(doc)
    _warn_customer_overdue(doc)


# ── Hard block: total AR cap ──────────────────────────────────────────────────

def _check_total_ar_cap(doc):
    """
    Total AR = SUM(debit - credit) on receivable accounts in GL Entry.
    We add doc.grand_total as the projected new exposure.
    Throws at $400k, shows a non-blocking warning at $300k.
    """
    total_ar = _get_total_ar_from_ledger()
    projected = total_ar + flt(doc.grand_total)

    if projected >= AR_CAP_HARD:
        frappe.throw(
            _(
                "AR Hard Cap Exceeded — this invoice cannot be saved.<br><br>"
                "Current outstanding AR (from ledger): <b>${0}</b><br>"
                "This invoice: <b>${1}</b><br>"
                "Projected total: <b>${2}</b><br><br>"
                "The policy cap is <b>$400,000</b>. "
                "Contact Finance to collect outstanding balances before proceeding."
            ).format(
                "{:,.2f}".format(total_ar),
                "{:,.2f}".format(flt(doc.grand_total)),
                "{:,.2f}".format(projected),
            ),
            title=_("AR Policy: Hard Block")
        )

    elif projected >= AR_CAP_WARN:
        # Show in-app warning to the user saving the invoice
        frappe.msgprint(
            _(
                "AR Warning — total outstanding AR will reach <b>${0}</b> "
                "once this invoice is posted ($300k warning threshold). "
                "Finance has been notified by email."
            ).format("{:,.2f}".format(projected)),
            title=_("AR Policy: Warning"),
            indicator="orange",
            alert=True,
        )
        # Email Finance team — but only once per day to avoid flooding on every save
        _send_ar_warning_email(total_ar, projected, doc)


def _get_total_ar_from_ledger():
    """
    Reads the live Accounts Receivable balance directly from GL Entry.
    SUM(debit - credit) on receivable accounts across ALL customers.
    This is identical to what the ERPNext Accounts Receivable report shows.
    """
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0) AS total_ar
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND account IN %(accounts)s
          AND is_cancelled = 0
        """,
        {"accounts": RECEIVABLE_ACCOUNTS},
        as_dict=True,
    )
    return flt(result[0].total_ar) if result else 0.0


def _send_ar_warning_email(current_ar, projected_ar, doc):
    """
    Send a one-time-per-day email to Finance when AR crosses the $300k warning.
    Uses frappe.cache to suppress duplicate emails within the same calendar day.
    """
    today     = nowdate()
    cache_key = f"ar_warning_email_sent_{today}"

    if frappe.cache().get_value(cache_key):
        return  # already sent today

    try:
        cap_pct  = (projected_ar / AR_CAP_HARD) * 100
        bar_width = min(cap_pct, 100)
        color    = "#d97706"

        html = f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
            max-width:600px;margin:0 auto;padding:24px;">
  <div style="background:{color};color:#fff;padding:16px 22px;border-radius:10px 10px 0 0;">
    <h2 style="margin:0;font-size:18px">AR Warning — $300k Threshold Crossed</h2>
  </div>
  <div style="background:#fff;border:1px solid #e2e8f0;padding:22px;border-radius:0 0 10px 10px;">
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:18px">
      <tr>
        <td style="padding:7px 0;color:#64748b">Current AR (GL Ledger)</td>
        <td style="text-align:right;font-weight:700">${current_ar:,.2f}</td>
      </tr>
      <tr>
        <td style="padding:7px 0;color:#64748b">Invoice being created</td>
        <td style="text-align:right;font-weight:700">{doc.customer} — ${flt(doc.grand_total):,.2f}</td>
      </tr>
      <tr style="border-top:2px solid #e2e8f0">
        <td style="padding:10px 0;font-weight:700">Projected AR</td>
        <td style="text-align:right;font-size:20px;font-weight:800;color:{color}">${projected_ar:,.2f}</td>
      </tr>
    </table>
    <div style="background:#f1f5f9;border-radius:6px;height:12px;overflow:hidden;margin-bottom:6px">
      <div style="background:{color};height:100%;width:{bar_width:.1f}%"></div>
    </div>
    <p style="color:#94a3b8;font-size:12px;margin:0 0 18px">{cap_pct:.1f}% of $400,000 hard cap</p>
    <p style="color:#334155;font-size:13px;margin:0">
      <b>Action required:</b> Review outstanding AR and accelerate collections
      before the $400,000 hard cap is reached. New invoices will be blocked at $400k.
    </p>
    <p style="color:#94a3b8;font-size:11px;margin:14px 0 0">
      Invoice: {doc.name or "New"} &nbsp;·&nbsp; {today}
    </p>
  </div>
</div>"""

        frappe.sendmail(
            recipients=AR_ALERT_RECIPIENTS,
            subject=f"AR Warning: Outstanding AR at ${projected_ar:,.2f} — Action Required",
            message=html,
            delayed=False,
        )

        # Suppress further emails for the rest of today (86400 seconds)
        frappe.cache().set_value(cache_key, True, expires_in_sec=86400)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "[ar_policy] warning email failed")


# ── Advisory warning: customer overdue ───────────────────────────────────────

def _warn_customer_overdue(doc):
    """
    Warn (non-blocking) if this customer has any invoice 30+ days past due_date
    with a positive outstanding_amount. Uses Sales Invoice due_date for the
    aging check; uses GL Entry balance to show the actual ledger balance.
    """
    if not doc.customer:
        return

    overdue = frappe.db.sql(
        """
        SELECT COUNT(*) AS cnt,
               COALESCE(SUM(outstanding_amount), 0) AS overdue_amount
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND customer = %(customer)s
          AND outstanding_amount > 0
          AND due_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        """,
        {"customer": doc.customer},
        as_dict=True,
    )

    if not overdue or not overdue[0].cnt:
        return

    cnt    = int(overdue[0].cnt)
    amount = flt(overdue[0].overdue_amount)

    # Pull the live ledger balance for this customer for context
    ledger = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0) AS balance
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND party = %(customer)s
          AND account IN %(accounts)s
          AND is_cancelled = 0
        """,
        {"customer": doc.customer, "accounts": RECEIVABLE_ACCOUNTS},
        as_dict=True,
    )
    ledger_balance = flt(ledger[0].balance) if ledger else 0.0

    frappe.msgprint(
        _(
            "<b>AR Red List Warning</b> — {0} has {1} invoice{2} more than "
            "30 days past due.<br>"
            "Overdue amount: <b>${3}</b> &nbsp;|&nbsp; "
            "Ledger balance: <b>${4}</b><br><br>"
            "Finance may place this account On Hold and withhold commission "
            "for the assigned sales rep."
        ).format(
            doc.customer,
            cnt,
            "s" if cnt != 1 else "",
            "{:,.2f}".format(amount),
            "{:,.2f}".format(ledger_balance),
        ),
        title=_("AR Policy: Customer Overdue"),
        indicator="orange",
    )
