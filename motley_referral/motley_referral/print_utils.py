"""Jinja helpers for the Referral Program print formats (registered in hooks.py)."""
import frappe
from frappe.utils import flt, formatdate, getdate

BADGE = {
    "Draft": "grey", "Submitted": "grey", "Under Review": "amber", "Approved": "blue", "Paid": "green",
    "Acknowledged": "green", "Active": "green", "Rejected": "red", "Cancelled": "red", "Expired": "dark",
    "Carried Forward": "purple", "Terminated": "red",
}


def rp_usd(v, sign=False):
    v = flt(v)
    s = "${:,.2f}".format(abs(v))
    return ("-" + s) if v < 0 else s


def rp_badge(status):
    return BADGE.get(status, "grey")


def rp_mask(text):
    text = (text or "").strip()
    if not text:
        return "-"
    return "•" * max(len(text) - 4, 4) + text[-4:]


def rp_month_label(period):
    try:
        return formatdate(f"{period}-01", "MMMM yyyy")
    except Exception:
        return period or ""


def rp_company_footer(company):
    parts = [company or ""]
    try:
        from frappe.contacts.doctype.address.address import get_default_address

        addr = get_default_address("Company", company)
        if addr:
            a = frappe.db.get_value("Address", addr, ["address_line1", "city", "state", "pincode"], as_dict=True)
            parts.append(", ".join(x for x in (a.address_line1, a.city, " ".join(y for y in (a.state, a.pincode) if y)) if x))
    except Exception:
        pass
    return " · ".join(p for p in parts if p)


def rp_company_logo(company):
    return frappe.db.get_value("Company", company, "company_logo") if company else None


def rp_statement_detail(doc):
    rows = frappe.get_all(
        "Referral Commission Ledger",
        filters={"statement": doc.name},
        fields=["posting_date", "customer", "sales_invoice", "amount_received", "rate", "commission_amount", "is_reversal"],
        order_by="posting_date asc, creation asc",
    )
    return rows


def rp_month_strip(ref, partner=None):
    """24 cells: Year 1 / Year 2 / current / ended."""
    partner = partner or frappe.get_doc("Referral Partner", ref.referral_partner)
    y1 = partner.year1_months or 12
    total = y1 + (partner.year2_months or 12)
    cur = ref.current_month_no or 0
    cells = []
    for i in range(1, total + 1):
        cls = "y1" if i <= y1 else "y2"
        if ref.window_status == "Ended":
            cls = "ended"
        elif i == cur:
            cls += " cur"
        elif cur and i < cur:
            cls += " past"
        cells.append({"n": i, "cls": cls})
    return cells


def rp_partner_referrals(partner):
    rows = frappe.get_all(
        "Partner Referral", filters={"referral_partner": partner},
        fields=["name", "business_name", "status", "commission_start_date", "current_month_no", "window_status", "total_commission"],
        order_by="creation desc",
    )
    return rows


def rp_partner_statements(partner):
    return frappe.get_all(
        "Referral Commission Statement", filters={"referral_partner": partner, "docstatus": ["<", 2]},
        fields=["name", "period", "net_payable", "status"], order_by="period desc",
    )


def rp_signatory(user):
    if not user:
        return {"name": "", "title": ""}
    name = frappe.db.get_value("User", user, "full_name") or user
    title = frappe.db.get_value("Employee", {"user_id": user}, "designation") or "Authorized Representative"
    return {"name": name, "title": title}


def rp_default_company():
    return frappe.defaults.get_global_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")
