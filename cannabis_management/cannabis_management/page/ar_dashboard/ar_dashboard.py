import frappe
from frappe.utils import nowdate


RECON_EDIT_ROLES = ("Account Manager", "System Manager", "Administrator")
TMM_GROUP_COMPANIES = ["Motley Terpz", "TSBC Ranch"]


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

    totals = {"invoiced": 0.0, "paid": 0.0, "outstanding": 0.0}
    for r in ranges:
        totals[r["key"]] = 0.0

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
            val = float(row.get(r["key"]) or 0)
            processed[r["key"]] = val
            totals[r["key"]] += val

        totals["invoiced"] += processed["invoiced"]
        totals["paid"] += processed["paid"]
        totals["outstanding"] += processed["outstanding"]

        rows.append(processed)

    return rows, totals


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
def get_ar_data(company, report_date=None, customer=None, ageing_based_on="Due Date", range_str="30, 60, 90, 120"):
    ranges = _build_ranges(range_str)

    if company == "TMM Group":
        all_rows = []
        combined_totals = {"invoiced": 0.0, "paid": 0.0, "outstanding": 0.0}
        for r in ranges:
            combined_totals[r["key"]] = 0.0

        for c in TMM_GROUP_COMPANIES:
            try:
                c_rows, c_totals = _fetch_rows_for_company(
                    c, report_date, customer, ageing_based_on, range_str, ranges
                )
                all_rows.extend(c_rows)
                for k in combined_totals:
                    combined_totals[k] += c_totals.get(k, 0.0)
            except Exception:
                frappe.log_error(f"AR data fetch failed for {c}", "TMM Group AR Dashboard")

        rows = all_rows
        totals = combined_totals
    else:
        rows, totals = _fetch_rows_for_company(
            company, report_date, customer, ageing_based_on, range_str, ranges
        )

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
