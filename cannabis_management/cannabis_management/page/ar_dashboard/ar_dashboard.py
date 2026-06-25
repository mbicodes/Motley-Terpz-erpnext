import frappe
from frappe.utils import nowdate


RECON_EDIT_ROLES    = ("Account Manager", "System Manager", "Administrator")
TMM_GROUP_COMPANIES = ["Motley Terpz", "TSBC Ranch"]
LEGACY_CUTOFF       = "2026-05-31"
NEW_AR_START        = "2026-06-01"


def _internal_customer_names():
    """Return the set of customer names marked as internal (is_internal_customer=1)."""
    return set(frappe.db.sql_list(
        "SELECT name FROM `tabCustomer` WHERE is_internal_customer = 1"
    ))


def _can_edit_recon():
    user_roles = set(frappe.get_roles(frappe.session.user))
    return any(role in user_roles for role in RECON_EDIT_ROLES)


def _build_ranges(range_str):
    range_numbers = [int(r.strip()) for r in range_str.split(",") if r.strip().isdigit()]
    ranges = []
    prev = 0
    for num in range_numbers:
        ranges.append({"key": f"range{len(ranges) + 1}", "label": f"{prev}-{num}"})
        prev = num
    ranges.append({"key": f"range{len(ranges) + 1}", "label": f"{prev}+"})
    return ranges


def _compute_totals(rows, ranges):
    totals = {"invoiced": 0.0, "paid": 0.0, "outstanding": 0.0}
    for r in ranges:
        totals[r["key"]] = 0.0
    for row in rows:
        totals["invoiced"]    += row["invoiced"]
        totals["paid"]        += row["paid"]
        totals["outstanding"] += row["outstanding"]
        for r in ranges:
            totals[r["key"]] += row[r["key"]]
    return totals


def _strip_cross_company_rows(rows, company):
    """Remove Sales Invoice rows whose company field doesn't match the selected company."""
    si_nos = [r["voucher_no"] for r in rows if r.get("voucher_type") == "Sales Invoice"]
    if not si_nos:
        return rows

    valid = set(frappe.db.sql_list(
        "SELECT name FROM `tabSales Invoice` WHERE name IN %(names)s AND company = %(company)s",
        {"names": tuple(si_nos), "company": company},
    ))

    return [
        r for r in rows
        if r.get("voucher_type") != "Sales Invoice" or r["voucher_no"] in valid
    ]


def _apply_si_outstanding(rows, ranges, report_date):
    """
    Replace the GL-derived outstanding AND aging bucket values with figures
    derived from si.outstanding_amount / si.due_date for every Sales Invoice row,
    then drop rows that are fully paid.

    The ERPNext AR report reads from GL Entry, which diverges from
    si.outstanding_amount when payments are applied without full GL clearance.
    si.outstanding_amount is the authoritative paid/unpaid signal.
    """
    si_nos = [r["voucher_no"] for r in rows if r.get("voucher_type") == "Sales Invoice"]
    if not si_nos:
        return rows

    si_data = frappe.db.sql(
        "SELECT name, outstanding_amount, due_date FROM `tabSales Invoice` WHERE name IN %(names)s",
        {"names": tuple(si_nos)},
        as_dict=True,
    )
    si_map = {r.name: r for r in si_data}

    from frappe.utils import date_diff, getdate
    as_of = getdate(report_date or nowdate())

    # Build aging thresholds from ranges: range1 covers 0..limits[0], range2 limits[0]..limits[1], …
    # _build_ranges("30,60,90,120") → [0-30, 30-60, 60-90, 90-120, 120+]
    # We derive limits by parsing each label.
    range_keys = [r["key"] for r in ranges]

    def _bucket_key(days_overdue):
        """Return the range key for a given days-overdue value (0 = current/not yet due)."""
        prev = 0
        for i, rng in enumerate(ranges):
            label = rng["label"]
            if "+" in label:
                return rng["key"]   # last bucket catches everything remaining
            try:
                _, upper = label.split("-")
                upper = int(upper)
            except Exception:
                return rng["key"]
            if days_overdue <= upper:
                return rng["key"]
            prev = upper
        return range_keys[-1]

    result = []
    for r in rows:
        if r.get("voucher_type") == "Sales Invoice":
            si = si_map.get(r["voucher_no"])
            if not si:
                result.append(r)
                continue
            actual = float(si.outstanding_amount or 0)
            if actual <= 0.01:
                continue    # fully paid — exclude

            r = dict(r)
            r["outstanding"] = actual

            # Recalculate aging bucket: zero all ranges, then put actual in correct bucket
            due = getdate(str(si.due_date)) if si.due_date else as_of
            days_overdue = max(date_diff(as_of, due), 0)
            for key in range_keys:
                r[key] = 0.0
            r[_bucket_key(days_overdue)] = actual

        result.append(r)
    return result


def _fetch_rows_for_company(company, report_date, customer, ageing_based_on, range_str, ranges):
    from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute as ar_execute

    filters = frappe._dict({
        "company": company,
        "report_date": report_date or nowdate(),
        "party_type": "Customer",
        "ageing_based_on": ageing_based_on,
        "range": range_str,
    })
    if customer:
        filters["party"] = [customer]

    columns, data, _, _, _, _ = ar_execute(filters)

    rows = []
    for row in (data or []):
        if not row or not row.get("voucher_no"):
            continue

        processed = {
            "party": row.get("party") or "",
            "customer_name": row.get("customer_name") or row.get("party") or "",
            "voucher_type": row.get("voucher_type") or "",
            "voucher_no": row.get("voucher_no") or "",
            "posting_date": str(row.get("posting_date") or ""),
            "due_date": str(row.get("due_date") or ""),
            "invoiced": float(row.get("invoiced") or 0),
            "paid": float(row.get("paid") or 0),
            "outstanding": float(row.get("outstanding") or 0),
            "currency": row.get("currency") or "",
        }
        for r in ranges:
            processed[r["key"]] = float(row.get(r["key"]) or 0)

        rows.append(processed)

    return rows


@frappe.whitelist()
def init_page():
    companies = frappe.get_all("Company", pluck="name", order_by="name")
    if "TMM Group" not in companies:
        companies.append("TMM Group")
    companies.sort()
    return {
        "companies": companies,
        "can_edit_recon": _can_edit_recon(),
    }


@frappe.whitelist()
def get_ar_data(company, report_date=None, customer=None, ageing_based_on="Due Date",
                range_str="30, 60, 90, 120", ar_mode="legacy"):
    ranges = _build_ranges(range_str)

    # Clamp report_date to the correct window so aging is always computed inside the mode's boundary
    if ar_mode == "legacy":
        if not report_date or str(report_date) > LEGACY_CUTOFF:
            report_date = LEGACY_CUTOFF
    elif ar_mode == "all":
        if not report_date:
            report_date = nowdate()
    else:
        if not report_date or str(report_date) < NEW_AR_START:
            report_date = nowdate()

    if company == "TMM Group":
        all_rows = []
        for c in TMM_GROUP_COMPANIES:
            try:
                c_rows = _fetch_rows_for_company(
                    c, report_date, customer, ageing_based_on, range_str, ranges
                )
                c_rows = _strip_cross_company_rows(c_rows, c)
                c_rows = _apply_si_outstanding(c_rows, ranges, report_date)
                all_rows.extend(c_rows)
            except Exception:
                frappe.log_error(f"AR data fetch failed for {c}", "TMM Group AR Dashboard")
        rows = all_rows
    else:
        rows = _fetch_rows_for_company(
            company, report_date, customer, ageing_based_on, range_str, ranges
        )
        rows = _strip_cross_company_rows(rows, company)
        rows = _apply_si_outstanding(rows, ranges, report_date)

    # Apply mode date filter and strip intercompany rows in one pass
    internal = _internal_customer_names()
    if ar_mode == "legacy":
        rows = [r for r in rows
                if str(r.get("posting_date") or "") <= LEGACY_CUTOFF
                and r.get("party") not in internal]
    elif ar_mode == "all":
        rows = [r for r in rows
                if r.get("party") not in internal]
    else:
        # New AR: keep new invoices as-is, AND keep legacy invoices so legacy
        # customers appear in the New AR view too — but flag them and zero their
        # aging buckets so the legacy amount never enters the aging/term breakdown.
        kept = []
        for r in rows:
            if r.get("party") in internal:
                continue
            posting = str(r.get("posting_date") or "")
            if posting >= NEW_AR_START:
                kept.append(r)
            elif posting <= LEGACY_CUTOFF:
                lr = dict(r)
                lr["is_legacy"] = 1
                for rng in ranges:
                    lr[rng["key"]] = 0.0
                kept.append(lr)
        rows = kept

    # In modes that show the on-terms (0-10 / 10-20 / 20-30) breakdown, an invoice
    # that is NOT yet past its due date belongs only in those term columns — clear
    # its overdue aging buckets so the same amount never also appears in the red
    # 0-30/30-60/... columns. Once the due date passes, the amount drops out of the
    # term columns and shows in the overdue buckets. (Legacy mode keeps standard
    # ERPNext aging, where the first bucket includes current + 0-30 overdue.)
    if ar_mode in ("new", "all"):
        from frappe.utils import getdate
        as_of = getdate(report_date)
        for r in rows:
            due = r.get("due_date")
            not_overdue = (not due) or getdate(str(due)) >= as_of
            if not_overdue:
                for rng in ranges:
                    r[rng["key"]] = 0.0

    totals = _compute_totals(rows, ranges)

    # Attach reconciliation status from Customer master
    unique_parties = list({r["party"] for r in rows if r.get("party")})
    recon_map = {}
    if unique_parties:
        cust_rows = frappe.get_all(
            "Customer",
            filters={"name": ["in", unique_parties]},
            fields=["name", "custom_reconciliation_status"],
        )
        recon_map = {c["name"]: (c.get("custom_reconciliation_status") or "") for c in cust_rows}

    for r in rows:
        r["reconciliation_status"] = recon_map.get(r["party"], "")

    return {
        "rows": rows,
        "ranges": ranges,
        "totals": totals,
        "company": company,
        "report_date": str(report_date or nowdate()),
        "can_edit_recon": _can_edit_recon(),
        "ar_mode": ar_mode,
    }


@frappe.whitelist()
def update_recon_status(party, status):
    """Update custom_reconciliation_status on the Customer master.
    Restricted to users with the Account Manager role (plus System Manager / Administrator).
    """
    if not _can_edit_recon():
        frappe.throw(
            "You do not have permission to change the reconciliation status. "
            "This action is restricted to Account Managers.",
            frappe.PermissionError,
        )

    if status not in ("", "Reconciled", "Unreconciled"):
        frappe.throw("Invalid reconciliation status")

    if not frappe.db.exists("Customer", party):
        frappe.throw(f"Customer {party} not found")

    frappe.db.set_value("Customer", party, "custom_reconciliation_status", status)

    return {"party": party, "status": status}
