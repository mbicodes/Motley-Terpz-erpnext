"""Server side of the Referral Program Board.

All numbers come from SQL aggregates on the ledger (no loops over documents). Every method checks the
role on the server: Referral Manager, Accounts Manager or System Manager.
"""
import json

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, nowdate

ROLES = ("Referral Manager", "Accounts Manager", "System Manager")
APPROVERS = ("Accounts Manager", "System Manager")
PAGE = 50


def _check(roles=ROLES):
    if not set(frappe.get_roles()) & set(roles) and frappe.session.user != "Administrator":
        frappe.throw(_("You are not permitted to use the Referral Program Board."), frappe.PermissionError)


def _filters(filters):
    if isinstance(filters, str):
        filters = json.loads(filters or "{}")
    return frappe._dict(filters or {})


def _range(f):
    if f.get("from_date") or f.get("to_date"):
        a = getdate(f.get("from_date") or f.get("to_date"))
        b = getdate(f.get("to_date") or f.get("from_date"))
    else:
        base = getdate(f.period + "-01") if f.get("period") else get_first_day(getdate(nowdate()))
        a, b = get_first_day(base), get_last_day(base)
    if b < a:
        a, b = b, a
    return a, b


def _prev(a, b):
    days = (b - a).days + 1
    return add_days(a, -days), add_days(a, -1)


def _companies(f):
    c = f.get("companies")
    if isinstance(c, str):
        c = [x for x in c.split(",") if x]
    return tuple(c) if c else ()


def _ledger_where(f, a, b, alias="l"):
    where, p = [f"{alias}.posting_date between %(a)s and %(b)s"], {"a": a, "b": b}
    cs = _companies(f)
    if cs:
        where.append(f"{alias}.company in %(cs)s")
        p["cs"] = cs
    if f.get("partner"):
        where.append(f"{alias}.referral_partner = %(partner)s")
        p["partner"] = f.partner
    return " and ".join(where), p


def _sum_ledger(f, a, b):
    w, p = _ledger_where(f, a, b)
    r = frappe.db.sql(
        f"select coalesce(sum(l.amount_received),0) rev, coalesce(sum(l.commission_amount),0) com from `tabReferral Commission Ledger` l where {w}",
        p,
        as_dict=True,
    )[0]
    return flt(r.rev), flt(r.com)


def _delta(cur, prev):
    if not prev:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)


# ----------------------------------------------------------------------------- board data
@frappe.whitelist()
def get_board_data(filters=None):
    _check()
    f = _filters(filters)
    a, b = _range(f)
    pa, pb = _prev(a, b)
    rev, com = _sum_ledger(f, a, b)
    prev_rev, prev_com = _sum_ledger(f, pa, pb)
    pw, pp = (" and referral_partner = %(partner)s", {"partner": f.partner}) if f.get("partner") else ("", {})

    active = frappe.db.sql(f"select count(*) from `tabReferral Partner` where status='Active' {pw.replace('referral_partner', 'name')}", pp)[0][0]
    earning = frappe.db.sql(
        f"select count(*) from `tabPartner Referral` where status='Acknowledged' and window_status in ('Year 1','Year 2') {pw}", pp
    )[0][0]
    cs = _companies(f)
    sw, sp = "", dict(pp)
    if cs:
        sw += " and company in %(cs)s"
        sp["cs"] = cs
    sw += pw
    outstanding = flt(
        frappe.db.sql(f"select coalesce(sum(net_payable),0) from `tabReferral Commission Statement` where docstatus=1 and status='Approved' {sw}", sp)[0][0]
    )
    cost = round(com / rev * 100, 2) if rev else 0
    prev_cost = round(prev_com / prev_rev * 100, 2) if prev_rev else 0

    today = nowdate()
    soon = add_days(today, 60)
    alerts = {
        "awaiting": frappe.db.sql(f"select count(*) from `tabPartner Referral` where status in ('Submitted','Under Review') {pw}", pp)[0][0],
        "overdue": frappe.db.sql(
            f"select count(*) from `tabReferral Commission Statement` where docstatus=1 and status='Approved' and due_date < %(today)s {sw}",
            {**sp, "today": today},
        )[0][0],
        "expiring": frappe.db.sql(
            f"""select count(*) from `tabPartner Referral` where status='Acknowledged' and
            ((window_status='Year 1' and year1_end between %(today)s and %(soon)s) or (window_status='Year 2' and year2_end between %(today)s and %(soon)s)) {pw}""",
            {**pp, "today": today, "soon": soon},
        )[0][0],
    }

    start12 = add_months(get_first_day(getdate(today)), -11).strftime("%Y-%m")
    lw, lp = ["l.period >= %(s12)s"], {"s12": start12}
    if cs:
        lw.append("l.company in %(cs)s")
        lp["cs"] = cs
    if f.get("partner"):
        lw.append("l.referral_partner = %(partner)s")
        lp["partner"] = f.partner
    monthly = frappe.db.sql(
        f"""select l.period, sum(l.amount_received) revenue, sum(l.commission_amount) commission
        from `tabReferral Commission Ledger` l where {' and '.join(lw)} group by l.period order by l.period""",
        lp,
        as_dict=True,
    )
    by_period = {m.period: m for m in monthly}
    labels, rev_s, com_s = [], [], []
    d = getdate(start12 + "-01")
    for _i in range(12):
        k = d.strftime("%Y-%m")
        labels.append(k)
        rev_s.append(flt(by_period[k].revenue) if k in by_period else 0)
        com_s.append(flt(by_period[k].commission) if k in by_period else 0)
        d = add_months(d, 1)
    w, p = _ledger_where(f, a, b)
    top = frappe.db.sql(
        f"""select l.referral_partner id, p.partner_name name, sum(l.commission_amount) commission
        from `tabReferral Commission Ledger` l join `tabReferral Partner` p on p.name = l.referral_partner
        where {w} group by l.referral_partner order by commission desc limit 10""",
        p,
        as_dict=True,
    )
    ref_status = frappe.db.sql(f"select status, count(*) n from `tabPartner Referral` where 1=1 {pw} group by status", pp, as_dict=True)
    win_status = frappe.db.sql(
        f"select coalesce(nullif(window_status,''),'Awaiting first payment') status, count(*) n from `tabPartner Referral` where status='Acknowledged' {pw} group by 1",
        pp,
        as_dict=True,
    )
    return {
        "range": {"from": str(a), "to": str(b)},
        "kpis": {
            "active_partners": {"value": active},
            "earning_accounts": {"value": earning},
            "revenue": {"value": rev, "delta": _delta(rev, prev_rev)},
            "commission": {"value": com, "delta": _delta(com, prev_com)},
            "outstanding": {"value": outstanding},
            "cost_pct": {"value": cost, "delta": round(cost - prev_cost, 2) if prev_rev else None, "delta_abs": True},
        },
        "alerts": alerts,
        "charts": {
            "monthly": {"labels": labels, "revenue": rev_s, "commission": com_s},
            "top_partners": top,
            "referral_status": ref_status,
            "window_status": win_status,
        },
        "companies": frappe.get_all("Referral Eligible Company", filters={"parent": "Referral Settings"}, pluck="company"),
        "partners": frappe.get_all("Referral Partner", fields=["name", "partner_name"], order_by="partner_name"),
        "can_approve": bool(set(frappe.get_roles()) & set(APPROVERS)),
    }


# ----------------------------------------------------------------------------- tabs
def _col(key, label, type="text", align=None):
    return {"key": key, "label": label, "type": type, "align": align or ("right" if type in ("currency", "int", "percent") else "left")}


def _spec(tab, f):
    a, b = _range(f)
    cs = _companies(f)
    p = {"a": a, "b": b, "today": nowdate(), "soon": add_days(nowdate(), 60)}
    partner = f.get("partner")
    search = (f.get("search") or "").strip()
    like = None
    if search:
        like = "%" + search.replace("%", "") + "%"
        p["like"] = like

    def add_partner(col):
        if partner:
            p["partner"] = partner
            return [f"{col} = %(partner)s"]
        return []

    def add_company(col):
        if cs:
            p["cs"] = cs
            return [f"{col} in %(cs)s"]
        return []

    period_sum = "coalesce((select sum({m}) from `tabReferral Commission Ledger` l where l.partner_referral = r.name and l.posting_date between %(a)s and %(b)s), 0)"

    if tab == "queue":
        return dict(
            frm="`tabPartner Referral` r left join `tabReferral Partner` p on p.name = r.referral_partner",
            where=["r.status in ('Submitted','Under Review')"] + add_partner("r.referral_partner"),
            search=["r.business_name", "r.contact_name", "p.partner_name", "r.email"],
            cols=[
                (_col("name", "Referral", "link"), "r.name"),
                (_col("partner", "Partner"), "p.partner_name"),
                (_col("business_name", "Business"), "r.business_name"),
                (_col("contact_name", "Contact"), "r.contact_name"),
                (_col("submitted_on", "Submitted On", "date"), "r.submitted_on"),
                (_col("age", "Age (days)", "int"), "datediff(curdate(), r.submitted_on)"),
                (_col("duplicate", "Duplicate Check", "dup"), "r.duplicate_check_result"),
                (_col("status", "Status", "badge"), "r.status"),
            ],
            extra={"email": "r.email"},
            order="r.submitted_on asc", totals=[], p=p,
        )
    if tab == "accounts":
        return dict(
            frm="`tabPartner Referral` r join `tabReferral Partner` p on p.name = r.referral_partner",
            where=["r.status = 'Acknowledged'"] + add_partner("r.referral_partner"),
            search=["r.business_name", "r.customer", "p.partner_name"],
            cols=[
                (_col("name", "Referral", "link"), "r.name"),
                (_col("partner", "Partner"), "p.partner_name"),
                (_col("customer", "Customer", "customer"), "r.customer"),
                (_col("start", "Start Date", "date"), "r.commission_start_date"),
                (_col("strip", "24-Month Window", "strip"), "r.current_month_no"),
                (_col("rate", "Current Rate", "percent"), "case r.window_status when 'Year 1' then p.year1_rate when 'Year 2' then p.year2_rate else null end"),
                (_col("collected_period", "Collected (Period)", "currency"), period_sum.format(m="l.amount_received")),
                (_col("commission_period", "Commission (Period)", "currency"), period_sum.format(m="l.commission_amount")),
                (_col("collected_total", "Collected To Date", "currency"), "r.total_received"),
                (_col("commission_total", "Commission To Date", "currency"), "r.total_commission"),
                (_col("open_ar", "Open AR", "currency"),
                 "coalesce((select sum(si.outstanding_amount) from `tabSales Invoice` si where si.customer = r.customer and si.docstatus = 1 and si.outstanding_amount > 0), 0)"),
            ],
            extra={"window_status": "r.window_status", "current_month_no": "r.current_month_no", "y1": "coalesce(p.year1_months,12)", "y2": "coalesce(p.year2_months,12)"},
            order="r.commission_start_date desc",
            totals=["collected_period", "commission_period", "collected_total", "commission_total", "open_ar"], p=p,
        )
    if tab == "partners":
        yr = "year(%(b)s)"
        return dict(
            frm="`tabReferral Partner` p",
            where=["1=1"] + add_partner("p.name"),
            search=["p.partner_name", "p.email"],
            cols=[
                (_col("name", "Partner ID", "link"), "p.name"),
                (_col("partner_name", "Partner"), "p.partner_name"),
                (_col("status", "Status", "badge"), "p.status"),
                (_col("n_ref", "Referrals", "int"), "(select count(*) from `tabPartner Referral` r where r.referral_partner = p.name)"),
                (_col("n_ack", "Acknowledged", "int"), "(select count(*) from `tabPartner Referral` r where r.referral_partner = p.name and r.status = 'Acknowledged')"),
                (_col("n_earn", "Earning", "int"), "(select count(*) from `tabPartner Referral` r where r.referral_partner = p.name and r.status = 'Acknowledged' and r.window_status in ('Year 1','Year 2'))"),
                (_col("commission_period", "Commission (Period)", "currency"),
                 "coalesce((select sum(l.commission_amount) from `tabReferral Commission Ledger` l where l.referral_partner = p.name and l.posting_date between %(a)s and %(b)s), 0)"),
                (_col("commission_ytd", "Year To Date", "currency"),
                 f"coalesce((select sum(l.commission_amount) from `tabReferral Commission Ledger` l where l.referral_partner = p.name and year(l.posting_date) = {yr}), 0)"),
                (_col("paid", "Paid To Date", "currency"),
                 "coalesce((select sum(s.net_payable) from `tabReferral Commission Statement` s where s.referral_partner = p.name and s.docstatus = 1 and s.status = 'Paid'), 0)"),
                (_col("outstanding", "Outstanding", "currency"),
                 "coalesce((select sum(s.net_payable) from `tabReferral Commission Statement` s where s.referral_partner = p.name and s.docstatus = 1 and s.status = 'Approved'), 0)"),
            ],
            extra={}, order="p.partner_name asc",
            totals=["n_ref", "n_ack", "n_earn", "commission_period", "commission_ytd", "paid", "outstanding"], p=p,
        )
    if tab == "ledger":
        w, lp = _ledger_where(f, a, b, "l")
        p.update(lp)
        return dict(
            frm="`tabReferral Commission Ledger` l join `tabReferral Partner` p on p.name = l.referral_partner",
            where=[w],
            search=["l.customer", "l.voucher_no", "l.sales_invoice", "p.partner_name"],
            cols=[
                (_col("partner", "Partner"), "p.partner_name"),
                (_col("customer", "Customer", "customer"), "l.customer"),
                (_col("posting_date", "Date", "date"), "l.posting_date"),
                (_col("voucher_no", "Payment", "voucher"), "l.voucher_no"),
                (_col("sales_invoice", "Invoice", "invoice"), "l.sales_invoice"),
                (_col("statement", "Statement", "statement"), "l.statement"),
                (_col("month_no", "Month", "int"), "l.month_no"),
                (_col("rate", "Rate", "percent"), "l.rate"),
                (_col("amount_received", "Amount Received", "currency"), "l.amount_received"),
                (_col("commission_amount", "Commission", "currency"), "l.commission_amount"),
            ],
            extra={"voucher_type": "l.voucher_type", "is_reversal": "l.is_reversal", "name": "l.name"},
            order="p.partner_name asc, l.customer asc, l.posting_date asc, l.creation asc",
            totals=["amount_received", "commission_amount"], p=p,
        )
    if tab == "statements":
        where = ["s.docstatus < 2"] + add_partner("s.referral_partner") + add_company("s.company")
        if f.get("period"):
            where.append("s.period = %(period)s")
            p["period"] = f.period
        return dict(
            frm="`tabReferral Commission Statement` s join `tabReferral Partner` p on p.name = s.referral_partner",
            where=where,
            search=["s.name", "p.partner_name"],
            cols=[
                (_col("name", "Statement", "link"), "s.name"),
                (_col("period", "Period"), "s.period"),
                (_col("partner", "Partner"), "p.partner_name"),
                (_col("company", "Company"), "s.company"),
                (_col("net_payable", "Net Payable", "currency"), "s.net_payable"),
                (_col("due_date", "Due Date", "date"), "s.due_date"),
                (_col("status", "Status", "badge"), "s.status"),
                (_col("days_to_due", "Days To Due", "due"),
                 "case when s.status in ('Approved') then datediff(s.due_date, curdate()) else null end"),
            ],
            extra={"docstatus": "s.docstatus", "purchase_invoice": "s.purchase_invoice"},
            order="s.period desc, p.partner_name asc", totals=["net_payable"], p=p,
        )
    if tab == "expiry":
        return dict(
            frm="`tabPartner Referral` r join `tabReferral Partner` p on p.name = r.referral_partner",
            where=["r.status = 'Acknowledged'",
                   "((r.window_status = 'Year 1' and r.year1_end <= %(soon)s) or (r.window_status = 'Year 2' and r.year2_end <= %(soon)s))"] + add_partner("r.referral_partner"),
            search=["r.business_name", "r.customer", "p.partner_name"],
            cols=[
                (_col("name", "Referral", "link"), "r.name"),
                (_col("partner", "Partner"), "p.partner_name"),
                (_col("customer", "Customer", "customer"), "r.customer"),
                (_col("event", "Event"), "case when r.window_status = 'Year 1' then 'Moves to Year 2' else 'Window ends' end"),
                (_col("event_date", "Date", "date"), "case when r.window_status = 'Year 1' then date_add(r.year1_end, interval 1 day) else r.year2_end end"),
                (_col("days_left", "Days Left", "int"), "datediff(case when r.window_status = 'Year 1' then date_add(r.year1_end, interval 1 day) else r.year2_end end, curdate())"),
                (_col("current_month_no", "Month", "int"), "r.current_month_no"),
                (_col("commission_total", "Commission To Date", "currency"), "r.total_commission"),
            ],
            extra={}, order="case when r.window_status = 'Year 1' then r.year1_end else r.year2_end end asc",
            totals=["commission_total"], p=p,
        )
    if tab == "ar":
        return dict(
            frm="`tabSales Invoice` si join `tabCustomer` c on c.name = si.customer join `tabReferral Partner` p on p.name = c.referral_partner",
            where=["si.docstatus = 1", "si.outstanding_amount > 0.005", "ifnull(c.referral_partner,'') != ''"]
            + add_partner("c.referral_partner") + add_company("si.company"),
            search=["si.customer", "si.name", "p.partner_name"],
            cols=[
                (_col("customer", "Customer", "customer"), "si.customer"),
                (_col("partner", "Partner"), "p.partner_name"),
                (_col("invoice", "Invoice", "invoice"), "si.name"),
                (_col("company", "Company"), "si.company"),
                (_col("due_date", "Due Date", "date"), "si.due_date"),
                (_col("outstanding", "Outstanding", "currency"), "si.outstanding_amount"),
                (_col("days_overdue", "Days Overdue", "overdue"), "greatest(datediff(curdate(), si.due_date), 0)"),
            ],
            extra={}, order="si.due_date asc", totals=["outstanding"], p=p,
        )
    frappe.throw(_("Unknown tab {0}").format(tab))


def _run(tab, f, start=0, page_length=PAGE, sort=None, sort_dir="asc"):
    s = _spec(tab, f)
    cols = {c["key"]: expr for c, expr in s["cols"]}
    where = list(s["where"])
    if f.get("search") and s["search"]:
        where.append("(" + " or ".join(f"{c} like %(like)s" for c in s["search"]) + ")")
    sel = ", ".join(f"{expr} as `{k}`" for k, expr in cols.items())
    sel += "".join(f", {expr} as `{k}`" for k, expr in s["extra"].items() if k not in cols)
    order = s["order"]
    if sort in cols:
        order = f"{cols[sort]} {'desc' if sort_dir == 'desc' else 'asc'}"
    base = f"from {s['frm']} where {' and '.join(where)}"
    total = frappe.db.sql(f"select count(*) {base}", s["p"])[0][0]
    limit = f" limit {int(start)}, {int(page_length)}" if page_length else ""
    rows = frappe.db.sql(f"select {sel} {base} order by {order}{limit}", s["p"], as_dict=True)
    totals = {}
    if s["totals"]:
        tsel = ", ".join(f"coalesce(sum({cols[k]}), 0) as `{k}`" for k in s["totals"])
        totals = frappe.db.sql(f"select {tsel} {base}", s["p"], as_dict=True)[0]
    return [c for c, _e in s["cols"]], rows, total, totals


@frappe.whitelist()
def get_tab_data(tab, filters=None, start=0, page_length=PAGE, sort=None, sort_dir="asc"):
    _check()
    f = _filters(filters)
    columns, rows, total, totals = _run(tab, f, int(start), int(page_length), sort, sort_dir)
    for r in rows:
        for k, v in list(r.items()):
            if hasattr(v, "isoformat"):
                r[k] = str(v)
    return {"columns": columns, "rows": rows, "total": total, "totals": {k: flt(v) for k, v in totals.items()}}


@frappe.whitelist()
def export_tab(tab, filters=None):
    _check()
    from frappe.utils.xlsxutils import make_xlsx

    f = _filters(filters)
    columns, rows, _t, totals = _run(tab, f, 0, 0)
    data = [[c["label"] for c in columns]]
    for r in rows:
        data.append([r.get(c["key"]) for c in columns])
    if totals:
        data.append([_("Total") if i == 0 else totals.get(c["key"], "") for i, c in enumerate(columns)])
    xlsx = make_xlsx(data, tab.title())
    frappe.response["filename"] = f"referral_{tab}_{nowdate()}.xlsx"
    frappe.response["filecontent"] = xlsx.getvalue()
    frappe.response["type"] = "binary"


# ----------------------------------------------------------------------------- actions
@frappe.whitelist()
def acknowledge_referral(name, customer=None, create_customer=0):
    _check()
    doc = frappe.get_doc("Partner Referral", name)
    doc.acknowledge(customer=customer, create_customer=create_customer)
    return doc.as_dict()


@frappe.whitelist()
def reject_referral(name, reason, note=None):
    _check()
    doc = frappe.get_doc("Partner Referral", name)
    doc.reject(reason, note)
    return doc.as_dict()


@frappe.whitelist()
def run_statements(period=None):
    _check(ROLES)  # same roles as Run Now in Referral Settings; the guide gives Referral Manager the full Board
    from motley_referral.referral_program.doctype.referral_commission_statement.referral_commission_statement import (
        create_monthly_statements,
    )

    return len(create_monthly_statements(period or None))


@frappe.whitelist()
def approve_statement(name):
    _check(APPROVERS)
    doc = frappe.get_doc("Referral Commission Statement", name)
    if doc.docstatus != 0:
        frappe.throw(_("Statement {0} is not a Draft.").format(name))
    doc.submit()
    return doc.purchase_invoice


@frappe.whitelist()
def email_statement(name):
    _check(APPROVERS)
    from motley_referral import notifications

    doc = frappe.get_doc("Referral Commission Statement", name)
    if doc.docstatus != 1 or doc.status not in ("Approved", "Paid"):
        frappe.throw(_("Only Approved or Paid statements can be emailed."))
    notifications.notify("statement_approved" if doc.status == "Approved" else "statement_paid", statement=doc, attach_pdf=True)
    return True


@frappe.whitelist()
def activate_partner(name):
    _check()
    return frappe.get_doc("Referral Partner", name).activate()


@frappe.whitelist()
def terminate_partner(name, termination_date=None):
    _check()
    return frappe.get_doc("Referral Partner", name).terminate(termination_date)
