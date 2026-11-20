"""Partner portal data and actions. Every function starts with get_current_partner() and every query is
filtered to that partner in Python/SQL. A record owned by another partner is reported as not found (404)."""
import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate, nowdate

from motley_referral.permissions import partner_of


def get_current_partner():
    user = frappe.session.user
    name = partner_of(user) if user and user != "Guest" else None
    if not name:
        raise frappe.PermissionError(_("You do not have access to the partner portal."))
    return frappe.get_doc("Referral Partner", name)


def mask(text):
    text = (text or "").strip()
    return "•" * max(len(text) - 4, 4) + text[-4:] if text else ""


def _not_found():
    raise frappe.DoesNotExistError


def _month_label(period):
    return frappe.utils.formatdate(f"{period}-01", "MMM yyyy")


# ----------------------------------------------------------------------------- pages
def dashboard(period=None):
    p = get_current_partner()
    today = getdate(nowdate())
    # the partner can pick any of the last 24 months; default is last month
    periods = [add_months(get_first_day(today), -i).strftime("%Y-%m") for i in range(1, 25)]
    last = period if period in periods else periods[0]
    earned_last = flt(frappe.db.sql("select coalesce(sum(commission_amount),0) from `tabReferral Commission Ledger` where referral_partner=%s and period=%s", (p.name, last))[0][0])
    paid = flt(frappe.db.sql("select coalesce(sum(net_payable),0) from `tabReferral Commission Statement` where referral_partner=%s and docstatus=1 and status='Paid'", p.name)[0][0])
    nxt = frappe.db.sql("select min(due_date) from `tabReferral Commission Statement` where referral_partner=%s and docstatus=1 and status='Approved'", p.name)[0][0]
    if not nxt:
        run_day = min(max(int(frappe.db.get_single_value("Referral Settings", "run_day") or 1), 1), 28)
        first = get_first_day(today)
        nxt = first.replace(day=run_day)
        if nxt <= today:
            nxt = add_months(first, 1).replace(day=run_day)
    earning = frappe.db.count("Partner Referral", {"referral_partner": p.name, "status": "Acknowledged", "window_status": ["in", ["Year 1", "Year 2"]]})
    start = add_months(get_first_day(today), -5)
    rows = {r.period: flt(r.c) for r in frappe.db.sql(
        "select period, sum(commission_amount) c from `tabReferral Commission Ledger` where referral_partner=%s and period>=%s group by period", (p.name, start.strftime("%Y-%m")), as_dict=True)}
    chart, d = [], start
    for _i in range(6):
        k = d.strftime("%Y-%m")
        chart.append({"label": d.strftime("%b"), "value": rows.get(k, 0)})
        d = add_months(d, 1)
    mx = max([c["value"] for c in chart] + [1])
    for c in chart:
        c["pct"] = max(round(abs(c["value"]) / mx * 100), 2) if c["value"] else 2
    statements = frappe.get_all("Referral Commission Statement", filters={"referral_partner": p.name, "docstatus": 1, "status": ["in", ["Approved", "Paid", "Carried Forward"]]},
                                fields=["name", "period", "net_payable", "status"], order_by="period desc", limit=24)
    period_statement = next((s for s in statements if s.period == last), None)
    return {"partner": p, "earned_last": earned_last, "last_label": _month_label(last), "paid": paid,
            "period": last, "periods": [(k, _month_label(k)) for k in periods], "period_statement": period_statement, "next_payout": nxt, "earning": earning, "chart": chart, "statements": statements,
            "readonly": p.status == "Terminated"}


def accounts():
    p = get_current_partner()
    today = getdate(nowdate())
    month = today.strftime("%Y-%m")
    rows = frappe.db.sql(
        """select r.name, r.business_name, r.status, r.commission_start_date, r.current_month_no, r.window_status, r.submitted_on, r.total_commission,
        coalesce((select sum(l.amount_received) from `tabReferral Commission Ledger` l where l.partner_referral=r.name and l.period=%(m)s),0) collected,
        coalesce((select sum(l.commission_amount) from `tabReferral Commission Ledger` l where l.partner_referral=r.name and l.period=%(m)s),0) earned,
        case r.window_status when 'Year 1' then %(y1)s when 'Year 2' then %(y2)s else null end rate
        from `tabPartner Referral` r where r.referral_partner=%(p)s order by r.creation desc""",
        {"m": month, "p": p.name, "y1": flt(p.year1_rate), "y2": flt(p.year2_rate)}, as_dict=True)
    return {"partner": p, "rows": rows, "total_months": (p.year1_months or 12) + (p.year2_months or 12)}


def account(name):
    p = get_current_partner()
    r = frappe.db.get_value("Partner Referral", {"name": name, "referral_partner": p.name}, ["*"], as_dict=True)
    if not r:
        _not_found()
    y1, y2 = p.year1_months or 12, p.year2_months or 12
    cur = r.current_month_no or 0
    strip = [{"n": i, "cls": ("y1" if i <= y1 else "y2") + (" cur" if i == cur else (" past" if cur and i < cur else "")) + (" end" if r.window_status == "Ended" else "")} for i in range(1, y1 + y2 + 1)]
    lines = frappe.get_all("Referral Commission Ledger", filters={"partner_referral": r.name}, fields=["posting_date", "sales_invoice", "amount_received", "rate", "commission_amount", "is_reversal", "month_no"], order_by="posting_date desc, creation desc", limit=500)
    open_inv = frappe.db.count("Sales Invoice", {"customer": r.customer, "docstatus": 1, "outstanding_amount": [">", 0.005]}) if r.customer else 0
    return {"partner": p, "ref": r, "strip": strip, "lines": lines, "open_invoices": open_inv, "total_months": y1 + y2, "readonly": p.status == "Terminated"}


def statements():
    p = get_current_partner()
    rows = frappe.get_all("Referral Commission Statement", filters={"referral_partner": p.name, "docstatus": 1, "status": ["in", ["Approved", "Paid", "Carried Forward"]]},
                          fields=["name", "period", "net_payable", "status", "due_date", "paid_on", "total_commission"], order_by="period desc")
    for r in rows:
        r.display_status = "Pending" if r.status == "Approved" else r.status
    return {"partner": p, "rows": rows}


def refer():
    p = get_current_partner()
    rows = frappe.get_all("Partner Referral", filters={"referral_partner": p.name}, fields=["name", "business_name", "status", "submitted_on", "rejection_reason"], order_by="creation desc")
    return {"partner": p, "rows": rows, "blocked": p.status != "Active"}


def profile():
    p = get_current_partner()
    return {"partner": p, "masked_payout": mask(p.payout_details), "agreement": p.signed_agreement}


# ----------------------------------------------------------------------------- actions
@frappe.whitelist()
def submit_referral(business_name, email, contact_name=None, phone=None, license_no=None, notes=None):
    p = get_current_partner()
    if p.status != "Active":
        frappe.throw(_("Your partner account is not active, so new referrals cannot be submitted."), frappe.PermissionError)
    doc = frappe.get_doc({"doctype": "Partner Referral", "referral_partner": p.name, "business_name": (business_name or "").strip(), "email": (email or "").strip(),
                          "contact_name": contact_name, "phone": phone, "license_no": license_no, "notes": notes})
    if not doc.business_name or not doc.email:
        frappe.throw(_("Business name and email are required."))
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


@frappe.whitelist()
def update_profile(phone=None, address=None, partner_name=None):
    p = get_current_partner()
    if p.status == "Terminated":
        frappe.throw(_("Your account is read only."), frappe.PermissionError)
    p.flags.ignore_permissions = True
    if phone is not None:
        p.phone = phone
    if address is not None:
        p.address = address
    p.save()
    return True


@frappe.whitelist()
def request_payout_change(payout_method, payout_details):
    p = get_current_partner()
    if p.status == "Terminated":
        frappe.throw(_("Your account is read only."), frappe.PermissionError)
    issue = frappe.get_doc({"doctype": "Issue", "subject": f"Payout change request from {p.partner_name} ({p.name})", "raised_by": frappe.session.user,
                            "description": f"Partner: {p.name}\nRequested method: {payout_method}\nRequested details: {payout_details}\n\nFinance: verify with the partner before updating the Referral Partner record."})
    issue.flags.ignore_permissions = True
    issue.insert()
    return issue.name


@frappe.whitelist()
def ask_question(referral, message):
    p = get_current_partner()
    if not frappe.db.exists("Partner Referral", {"name": referral, "referral_partner": p.name}):
        _not_found()
    issue = frappe.get_doc({"doctype": "Issue", "subject": f"Referral account question: {referral}", "raised_by": frappe.session.user, "description": message})
    issue.flags.ignore_permissions = True
    issue.insert()
    return issue.name


@frappe.whitelist()
def download_statement(name):
    p = get_current_partner()
    st = frappe.db.get_value("Referral Commission Statement", {"name": name, "referral_partner": p.name, "docstatus": 1, "status": ["in", ["Approved", "Paid", "Carried Forward"]]}, "name")
    if not st:
        _not_found()
    frappe.local.response.filename = f"{name}.pdf"
    frappe.local.response.filecontent = frappe.get_print("Referral Commission Statement", name, print_format="Referral Commission Statement", as_pdf=True)
    frappe.local.response.type = "pdf"
