import frappe
from frappe.utils import add_days, today, getdate

CASH_THRESHOLD = 10000


# ─────────────────────────────────────────────────────────────────────
# CORE LOGIC
# ─────────────────────────────────────────────────────────────────────

def check_cash_threshold(doc, method):
    if doc.payment_type != "Receive":
        return

    if doc.party_type != "Customer":
        return

    cash_modes = get_cash_modes()
    if doc.mode_of_payment not in cash_modes:
        return

    if doc.paid_amount <= CASH_THRESHOLD:
        return

    existing = frappe.db.exists(
        "IRS Form 8300 Log", {"payment_entry": doc.name}
    )
    if existing:
        return

    create_8300_log(doc, doc.party, doc.paid_amount)


def create_8300_log(payment_entry, customer, amount):
    existing = frappe.db.exists(
        "IRS Form 8300 Log", {"payment_entry": payment_entry.name}
    )
    if existing:
        return

    customer_doc = frappe.get_doc("Customer", customer)

    log = frappe.new_doc("IRS Form 8300 Log")
    log.payment_entry         = payment_entry.name
    log.customer              = customer
    log.payer_name            = customer_doc.customer_name
    log.transaction_date      = payment_entry.posting_date
    log.cash_amount           = payment_entry.paid_amount
    log.nature_of_transaction = "Cannabis retail sale"
    log.filing_status         = "Pending"

    log.insert(ignore_permissions=True)
    frappe.db.commit()

    frappe.msgprint(
        f"⚠️ IRS Form 8300 required! Log {log.name} created. "
        f"Deadline: {log.filing_deadline}",
        alert=True, indicator="orange"
    )


def get_cash_modes():
    modes = frappe.get_all(
        "Mode of Payment", filters={"type": "Cash"}, pluck="name"
    )
    return modes or ["Cash"]


# ─────────────────────────────────────────────────────────────────────
# SCHEDULED JOBS
# ─────────────────────────────────────────────────────────────────────

def check_overdue_filings():
    overdue = frappe.get_all(
        "IRS Form 8300 Log",
        filters={
            "filing_status": "Pending",
            "filing_deadline": ["<", today()]
        },
        pluck="name"
    )
    for name in overdue:
        frappe.db.set_value(
            "IRS Form 8300 Log", name, "filing_status", "Overdue"
        )
    if overdue:
        frappe.db.commit()


def send_january_notices():
    from frappe.utils import now_datetime
    now = now_datetime()
    if not (now.month == 1 and now.day == 31):
        return

    # Never send notice for suspicious activity filings — IRS rule
    logs = frappe.get_all(
        "IRS Form 8300 Log",
        filters={
            "payer_notified":        0,
            "is_suspicious_activity": 0,
            "filing_status": ["in", ["Reported", "Filed - E-File", "Filed - Paper"]]
        },
        fields=["name", "payer_name", "customer", "cash_amount", "transaction_date"]
    )

    for log in logs:
        email = frappe.db.get_value("Customer", log.customer, "email_id")
        if email:
            frappe.sendmail(
                recipients=[email],
                subject="Notice: IRS Form 8300 Filed on Your Behalf",
                message=f"""
                    Dear {log.payer_name},<br><br>
                    Please be advised that pursuant to 31 U.S.C. § 5331, we have filed
                    IRS Form 8300 reporting a cash transaction of
                    ${log.cash_amount:,.2f} on {log.transaction_date}.<br><br>
                    Please contact us with any questions.
                """
            )
            frappe.db.set_value("IRS Form 8300 Log", log.name, {
                "payer_notified":           1,
                "payer_notification_date":  today()
            })
    frappe.db.commit()


# ─────────────────────────────────────────────────────────────────────
# WHITELISTED FUNCTIONS
# ─────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_8300_status_for_payment(payment_entry_name):
    """Called by Payment Entry client script to get linked 8300 log."""
    log = frappe.db.sql("""
        SELECT
            name, payer_name, cash_amount, filing_status,
            filing_deadline, fincen_confirmation_number,
            is_suspicious_activity, is_related_transaction,
            DATEDIFF(filing_deadline, CURDATE()) AS days_left
        FROM `tabIRS Form 8300 Log`
        WHERE payment_entry = %(pe)s
        LIMIT 1
    """, {"pe": payment_entry_name}, as_dict=True)

    return log[0] if log else None


@frappe.whitelist()
def get_8300_attachment_for_payment(payment_entry_name):
    """Check if a Form 8300 file is already attached to this Payment Entry."""
    file = frappe.db.get_value(
        "File",
        {
            "attached_to_doctype": "Payment Entry",
            "attached_to_name":    payment_entry_name,
            "file_name":           ["like", "%8300%"]
        },
        ["name", "file_name", "file_url"],
        as_dict=True
    )
    return file or None


@frappe.whitelist()
def mark_8300_as_filed(log_name, status, filing_date=None,
                        conf_number=None, file_url=None):
    log = frappe.get_doc("IRS Form 8300 Log", log_name)
    log.filing_status = status
    log.filing_date   = filing_date or today()

    if conf_number:
        log.fincen_confirmation_number = conf_number

    if file_url:
        existing_notes = log.notes or ""
        log.notes = (
            existing_notes +
            f"\n\n[{today()}] Form 8300 document attached from Payment Entry. "
            f"File: {file_url}"
        ).strip()

    log.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
def scan_payment_for_8300(payment_entry_name):
    """Manually run the 8300 check against a specific Payment Entry."""
    pe = frappe.get_doc("Payment Entry", payment_entry_name)

    if pe.payment_type != "Receive":
        return {
            "payment":  payment_entry_name,
            "customer": pe.party,
            "amount":   pe.paid_amount,
            "mode":     pe.mode_of_payment,
            "log":      "Skipped — payment_type is not 'Receive'"
        }

    check_cash_threshold(pe, None)
    frappe.db.commit()

    log = frappe.db.get_value(
        "IRS Form 8300 Log",
        {"payment_entry": payment_entry_name},
        ["name", "cash_amount", "filing_status", "filing_deadline"],
        as_dict=True
    )
    return {
        "payment":  payment_entry_name,
        "customer": pe.party,
        "amount":   pe.paid_amount,
        "mode":     pe.mode_of_payment,
        "log":      log or "No log created — payment may be below threshold or not cash"
    }


@frappe.whitelist()
def bulk_scan_cash_payments(limit=50):
    """Scan N cash payment entries and create 8300 logs where needed."""
    cash_modes = get_cash_modes()
    if not cash_modes:
        return {"error": "No Cash modes of payment found in system"}

    entries = frappe.db.sql("""
        SELECT pe.name, pe.party, pe.paid_amount, pe.posting_date, pe.mode_of_payment
        FROM `tabPayment Entry` pe
        WHERE pe.party_type      = 'Customer'
          AND pe.payment_type    = 'Receive'
          AND pe.docstatus       = 1
          AND pe.paid_amount     > %(threshold)s
          AND pe.mode_of_payment IN %(modes)s
        ORDER BY pe.posting_date ASC
        LIMIT %(limit)s
    """, {
        "modes":     tuple(cash_modes),
        "limit":     int(limit),
        "threshold": CASH_THRESHOLD
    }, as_dict=True)

    results = {"scanned": 0, "triggered": 0, "skipped": 0, "errors": []}

    for row in entries:
        results["scanned"] += 1
        try:
            pe = frappe.get_doc("Payment Entry", row.name)
            existing = frappe.db.exists(
                "IRS Form 8300 Log", {"payment_entry": row.name}
            )
            if existing:
                results["skipped"] += 1
                continue
            check_cash_threshold(pe, None)
            results["triggered"] += 1
        except Exception as e:
            results["errors"].append({"payment": row.name, "error": str(e)})

    frappe.db.commit()

    results["logs"] = frappe.get_all(
        "IRS Form 8300 Log",
        fields=["name", "payer_name", "cash_amount", "filing_status",
                "filing_deadline", "payment_entry"],
        order_by="creation desc",
        limit=50
    )

    return results


@frappe.whitelist()
def run_8300_scan_and_report(limit=200):
    """Scan existing cash Payment Entries, create logs, return report data."""
    cash_modes = get_cash_modes()
    if not cash_modes:
        frappe.throw("No Cash type Modes of Payment found.")

    entries = frappe.db.sql("""
        SELECT pe.name
        FROM `tabPayment Entry` pe
        WHERE pe.party_type      = 'Customer'
          AND pe.payment_type    = 'Receive'
          AND pe.docstatus       = 1
          AND pe.paid_amount     > %(threshold)s
          AND pe.mode_of_payment IN %(modes)s
        ORDER BY pe.posting_date ASC
        LIMIT %(limit)s
    """, {
        "modes":     tuple(cash_modes),
        "limit":     int(limit),
        "threshold": CASH_THRESHOLD
    }, as_dict=True)

    scanned = 0
    errors  = []

    for row in entries:
        scanned += 1
        try:
            pe = frappe.get_doc("Payment Entry", row.name)
            check_cash_threshold(pe, None)
        except Exception as e:
            errors.append({"payment": row.name, "error": str(e)})

    frappe.db.commit()

    report_data = frappe.db.sql("""
        SELECT
            name, payment_entry, payer_name, cash_amount,
            transaction_date, filing_deadline, filing_status,
            payer_notified, is_suspicious_activity, is_related_transaction,
            DATEDIFF(filing_deadline, CURDATE()) AS days_left
        FROM `tabIRS Form 8300 Log`
        ORDER BY filing_deadline ASC
    """, as_dict=True)

    return {
        "scanned_payments": scanned,
        "logs_found":       len(report_data),
        "errors":           errors,
        "report_data":      report_data
    }


@frappe.whitelist()
def get_customer_cash_total(customer, months_back=12):
    """Check total cash received from a customer over N months."""
    cash_modes = get_cash_modes()
    start_date = add_days(today(), -int(months_back) * 30)

    rows = frappe.db.sql("""
        SELECT pe.name, pe.posting_date, pe.paid_amount, pe.mode_of_payment
        FROM `tabPayment Entry` pe
        WHERE pe.party_type      = 'Customer'
          AND pe.payment_type    = 'Receive'
          AND pe.party           = %(customer)s
          AND pe.mode_of_payment IN %(modes)s
          AND pe.posting_date    >= %(start)s
          AND pe.docstatus       = 1
        ORDER BY pe.posting_date ASC
    """, {
        "customer": customer,
        "modes":    tuple(cash_modes),
        "start":    start_date
    }, as_dict=True)

    total = sum(r.paid_amount for r in rows)

    existing_logs = frappe.get_all(
        "IRS Form 8300 Log",
        filters={"customer": customer},
        fields=["name", "payment_entry", "cash_amount",
                "filing_status", "filing_deadline",
                "is_suspicious_activity", "is_related_transaction"]
    )

    return {
        "customer":      customer,
        "period_start":  start_date,
        "total_cash":    total,
        "threshold":     CASH_THRESHOLD,
        "payment_count": len(rows),
        "payments":      rows,
        "existing_logs": existing_logs
    }


@frappe.whitelist()
def reset_and_initialize_8300_logs():
    """
    ⚠️  DESTRUCTIVE — deletes ALL existing IRS Form 8300 Log records
    then re-scans every qualifying submitted Payment Entry (Receive type,
    Customer party, Cash mode, > $10,000) and creates fresh logs.

    Run via:
        bench execute cannabis_management.cannabis_management.utils.irs_8300.reset_and_initialize_8300_logs
    """
    if not frappe.has_permission("IRS Form 8300 Log", "delete"):
        frappe.throw(
            "You do not have permission to reset 8300 logs.",
            frappe.PermissionError
        )

    # ── 1. Delete all existing logs ───────────────────────────────────
    existing_logs = frappe.get_all("IRS Form 8300 Log", pluck="name")
    deleted_count = 0

    for log_name in existing_logs:
        try:
            frappe.delete_doc(
                "IRS Form 8300 Log",
                log_name,
                ignore_permissions=True,
                force=True
            )
            deleted_count += 1
        except Exception as e:
            frappe.log_error(
                f"Failed to delete IRS Form 8300 Log {log_name}: {e}",
                "8300 Reset Error"
            )

    frappe.db.commit()

    # ── 2. Fetch all qualifying Payment Entries ───────────────────────
    cash_modes = get_cash_modes()
    if not cash_modes:
        return {
            "error":   "No Cash type Modes of Payment found in system.",
            "deleted": deleted_count,
            "created": 0,
            "skipped": 0,
            "errors":  []
        }

    qualifying_payments = frappe.db.sql("""
        SELECT
            pe.name,
            pe.party,
            pe.paid_amount,
            pe.posting_date,
            pe.mode_of_payment
        FROM `tabPayment Entry` pe
        WHERE pe.party_type      = 'Customer'
          AND pe.payment_type    = 'Receive'
          AND pe.docstatus       = 1
          AND pe.paid_amount     > %(threshold)s
          AND pe.mode_of_payment IN %(modes)s
        ORDER BY pe.posting_date ASC
    """, {
        "threshold": CASH_THRESHOLD,
        "modes":     tuple(cash_modes)
    }, as_dict=True)

    # ── 3. Create logs ────────────────────────────────────────────────
    created_count = 0
    skipped_count = 0
    errors        = []

    for row in qualifying_payments:
        try:
            pe = frappe.get_doc("Payment Entry", row.name)
            create_8300_log(pe, pe.party, pe.paid_amount)
            created_count += 1
        except Exception as e:
            skipped_count += 1
            errors.append({
                "payment": row.name,
                "amount":  row.paid_amount,
                "error":   str(e)
            })
            frappe.log_error(
                f"Failed to create 8300 log for {row.name}: {e}",
                "8300 Init Error"
            )

    frappe.db.commit()

    # ── 4. Return summary ─────────────────────────────────────────────
    logs_created = frappe.get_all(
        "IRS Form 8300 Log",
        fields=[
            "name", "payment_entry", "payer_name",
            "cash_amount", "filing_status", "filing_deadline",
            "transaction_date"
        ],
        order_by="transaction_date asc"
    )

    return {
        "deleted":    deleted_count,
        "scanned":    len(qualifying_payments),
        "created":    created_count,
        "skipped":    skipped_count,
        "errors":     errors,
        "cash_modes": cash_modes,
        "threshold":  CASH_THRESHOLD,
        "logs":       logs_created
    }