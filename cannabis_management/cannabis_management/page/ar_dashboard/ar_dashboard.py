import frappe
from frappe.utils import nowdate


@frappe.whitelist()
def init_page():
    return {
        "companies": frappe.get_all("Company", pluck="name", order_by="name"),
    }


@frappe.whitelist()
def get_ar_data(company, report_date=None, customer=None, ageing_based_on="Due Date", range_str="30, 60, 90, 120"):
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

    # Build range labels from the range string
    range_numbers = [int(r.strip()) for r in range_str.split(",") if r.strip().isdigit()]
    ranges = []
    prev = 0
    for num in range_numbers:
        ranges.append({"key": f"range{len(ranges) + 1}", "label": f"{prev}-{num}"})
        prev = num
    ranges.append({"key": f"range{len(ranges) + 1}", "label": f"{prev}+"})

    # Initialise totals
    totals = {"invoiced": 0.0, "paid": 0.0, "outstanding": 0.0}
    for r in ranges:
        totals[r["key"]] = 0.0

    rows = []
    for row in (data or []):
        # Skip group/total rows that have no voucher
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
    }


@frappe.whitelist()
def update_recon_status(party, status):
    """Update custom_reconciliation_status on the Customer master."""
    if status not in ("", "Reconciled", "Unreconciled"):
        frappe.throw("Invalid reconciliation status")

    if not frappe.db.exists("Customer", party):
        frappe.throw(f"Customer {party} not found")

    frappe.db.set_value("Customer", party, "custom_reconciliation_status", status)

    return {"party": party, "status": status}