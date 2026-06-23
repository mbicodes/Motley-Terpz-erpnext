"""
Set up Jamie Expense Entry system — mirrors the Nikki expense setup but expense-only.

What this script does:
  1. Creates "Jamie Expense Entry" doctype (same fields as Nikki Expense Entry)
  2. Creates Web Form: jamie-expense-tracker
  3. Adds get_jamie_expense_summary() API to jamie.py
  4. Creates Server Scripts (auto-submit, ETE creation on submit, cascade delete)
  5. Updates DocPerms for Jamie Expense Entry
  6. Updates Jamie Custom HTML Block (HTML, script, style)

Run:
  bench --site stage.alltechvirtual.com execute cannabis_management.setup_jamie_expense.run
"""
import frappe


# ─────────────────────────────────────────────────────────
# 1. Jamie Expense Entry doctype
# ─────────────────────────────────────────────────────────

JAMIE_EXPENSE_FIELDS = [
    {"fieldname": "naming_series",          "label": "Series",             "fieldtype": "Select",       "options": "JAMIEEXP-.YYYY.-.#####\n",     "reqd": 0, "idx": 0},
    {"fieldname": "expense_type",           "label": "Expense Type",       "fieldtype": "Select",       "options": "\nPersonal\nMotley",           "reqd": 1, "idx": 1},
    {"fieldname": "business",               "label": "Business",           "fieldtype": "Link",         "options": "Company",                        "reqd": 0, "idx": 2},
    {"fieldname": "party_type",             "label": "Party Type",         "fieldtype": "Select",       "options": "\nCustomer\nSupplier",           "reqd": 0, "idx": 3},
    {"fieldname": "customer",               "label": "Customer",           "fieldtype": "Link",         "options": "Customer",                       "reqd": 0, "idx": 4},
    {"fieldname": "supplier",               "label": "Supplier",           "fieldtype": "Link",         "options": "Supplier",                       "reqd": 0, "idx": 5},
    {"fieldname": "column_break_fjko",      "label": None,                 "fieldtype": "Column Break", "options": None,                             "reqd": 0, "idx": 6},
    {"fieldname": "transaction_date",       "label": "Transaction Date",   "fieldtype": "Date",         "options": None,                             "reqd": 1, "idx": 7},
    {"fieldname": "status",                 "label": "Status",             "fieldtype": "Select",       "options": "\nOpen\nCompleted",              "reqd": 0, "idx": 8},
    {"fieldname": "mode_of_payment",        "label": "Mode of Payment",    "fieldtype": "Link",         "options": "Mode of Payment",                "reqd": 0, "idx": 9},
    {"fieldname": "section_break_sbmc",     "label": None,                 "fieldtype": "Section Break","options": None,                             "reqd": 0, "idx": 10},
    {"fieldname": "money_in",               "label": "Money In",           "fieldtype": "Currency",     "options": None,                             "reqd": 0, "idx": 11},
    {"fieldname": "column_break_lymm",      "label": None,                 "fieldtype": "Column Break", "options": None,                             "reqd": 0, "idx": 12},
    {"fieldname": "money_out",              "label": "Money Out",          "fieldtype": "Currency",     "options": None,                             "reqd": 0, "idx": 13},
    {"fieldname": "section_break_vjsc",     "label": None,                 "fieldtype": "Section Break","options": None,                             "reqd": 0, "idx": 14},
    {"fieldname": "invoice_no",             "label": "Invoice #",          "fieldtype": "Data",         "options": None,                             "reqd": 0, "idx": 15},
    {"fieldname": "column_break_eknz",      "label": None,                 "fieldtype": "Column Break", "options": None,                             "reqd": 0, "idx": 16},
    {"fieldname": "receipt",                "label": "Receipt",            "fieldtype": "Attach",       "options": None,                             "reqd": 0, "idx": 17},
    {"fieldname": "section_break_rczl",     "label": None,                 "fieldtype": "Section Break","options": None,                             "reqd": 0, "idx": 18},
    {"fieldname": "transaction_notes",      "label": "Transaction Notes",  "fieldtype": "Small Text",   "options": None,                             "reqd": 0, "idx": 19},
    {"fieldname": "section_break_0xpn",     "label": None,                 "fieldtype": "Section Break","options": None,                             "reqd": 0, "idx": 20},
    {"fieldname": "amended_from",           "label": "Amended From",       "fieldtype": "Link",         "options": "Jamie Expense Entry",            "reqd": 0, "idx": 21},
    {"fieldname": "expense_tracker_entry",  "label": "Expense Tracker Entry","fieldtype": "Link",       "options": "Expense Tracker Entry",          "reqd": 0, "idx": 22},
    {"fieldname": "payment_entry",          "label": "Payment Entry",      "fieldtype": "Link",         "options": "Payment Entry",                  "reqd": 0, "idx": 23},
]


def _create_jamie_expense_doctype():
    if frappe.db.exists("DocType", "Jamie Expense Entry"):
        print("  Jamie Expense Entry already exists — skipping doctype creation")
        return

    dt = frappe.new_doc("DocType")
    dt.name = "Jamie Expense Entry"
    dt.module = "Cannabis Management"
    dt.custom = 0
    dt.is_submittable = 1
    dt.track_changes = 1
    dt.autoname = "naming_series:"
    dt.naming_series = "JAMIEEXP-.YYYY.-.#####"

    for f in JAMIE_EXPENSE_FIELDS:
        dt.append("fields", {
            "fieldname": f["fieldname"],
            "label":     f.get("label") or "",
            "fieldtype": f["fieldtype"],
            "options":   f.get("options") or "",
            "reqd":      f.get("reqd", 0),
            "idx":       f["idx"],
        })

    # Permissions
    perm_rows = [
        {"role": "Website Manager",  "read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 0, "delete": 0, "permlevel": 0},
        {"role": "Finance Manager",  "read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1, "delete": 0, "permlevel": 0},
        {"role": "Accounts Manager", "read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1, "delete": 0, "permlevel": 0},
        {"role": "System Manager",   "read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1, "delete": 1, "permlevel": 0},
    ]
    for p in perm_rows:
        dt.append("permissions", p)

    dt.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.reload_doctype("Jamie Expense Entry")
    print("  Created: Jamie Expense Entry doctype")


# ─────────────────────────────────────────────────────────
# 2. Web Form: jamie-expense-tracker
# ─────────────────────────────────────────────────────────

WEB_FORM_FIELDS = [
    {"fieldname": "expense_type",       "label": "Expense Type",     "fieldtype": "Select",    "reqd": 1},
    {"fieldname": "transaction_date",   "label": "Transaction Date", "fieldtype": "Date",      "reqd": 1},
    {"fieldname": "party_type",         "label": "Party Type",       "fieldtype": "Select",    "reqd": 0},
    {"fieldname": "customer",           "label": "Customer",         "fieldtype": "Link",      "reqd": 0},
    {"fieldname": "supplier",           "label": "Supplier",         "fieldtype": "Link",      "reqd": 0},
    {"fieldname": "mode_of_payment",    "label": "Mode of Payment",  "fieldtype": "Link",      "reqd": 0},
    {"fieldname": "money_in",           "label": "Money In",         "fieldtype": "Currency",  "reqd": 0},
    {"fieldname": "money_out",          "label": "Money Out",        "fieldtype": "Currency",  "reqd": 0},
    {"fieldname": "invoice_no",         "label": "Invoice #",        "fieldtype": "Data",      "reqd": 0},
    {"fieldname": "business",           "label": "Company",          "fieldtype": "Link",      "reqd": 0},
    {"fieldname": "receipt",            "label": "Receipt",          "fieldtype": "Attach",    "reqd": 0},
    {"fieldname": "transaction_notes",  "label": "Transaction Notes","fieldtype": "Small Text","reqd": 0},
]


def _create_web_form():
    if frappe.db.exists("Web Form", "jamie-expense-tracker"):
        print("  Web Form jamie-expense-tracker already exists — skipping")
        return

    wf = frappe.new_doc("Web Form")
    wf.name = "jamie-expense-tracker"
    wf.title = "Jamie Expense Tracker"
    wf.doc_type = "Jamie Expense Entry"
    wf.route = "jamie-expense-tracker"
    wf.is_standard = 1
    wf.login_required = 1
    wf.allow_edit = 0
    wf.allow_multiple = 1
    wf.show_sidebar = 0

    for f in WEB_FORM_FIELDS:
        wf.append("web_form_fields", {
            "fieldname":  f["fieldname"],
            "label":      f["label"],
            "fieldtype":  f["fieldtype"],
            "reqd":       f.get("reqd", 0),
        })

    wf.insert(ignore_permissions=True)
    frappe.db.commit()
    print("  Created: Web Form jamie-expense-tracker")


# ─────────────────────────────────────────────────────────
# 3. Server Scripts
# ─────────────────────────────────────────────────────────

AUTO_SUBMIT_SCRIPT = """\
try:
    if frappe.db.get_value(doc.doctype, doc.name, "docstatus") == 0:
        frappe.get_doc(doc.doctype, doc.name).submit()
except Exception as exc:
    frappe.log_error(str(exc), doc.doctype + " auto-submit error")
"""

JAMIE_ETE_SCRIPT = """\
# Jamie Expense Entry → Expense Tracker Entry (auto-create on submit)
# Sandbox rules (RestrictedPython): no import/from, no underscore names, no function defs.

try:
    existing_ete = frappe.db.get_value("Jamie Expense Entry", doc.name, "expense_tracker_entry")

    if existing_ete:
        current_status = frappe.db.get_value("Expense Tracker Entry", existing_ete, "docstatus")
        if current_status == 0:
            frappe.db.set_value("Expense Tracker Entry", existing_ete, "docstatus", 1)
        bal_person = frappe.db.get_value("Expense Tracker Entry", existing_ete, "cash_tracker_person")
    else:
        direction = None
        amount = None
        if doc.money_out and float(doc.money_out) > 0:
            direction = "Expense"
            amount = float(doc.money_out)
        elif doc.money_in and float(doc.money_in) > 0:
            direction = "Reimbursement"
            amount = float(doc.money_in)

        if direction and amount:
            bal_person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")

            date_s = str(doc.transaction_date)[:10]
            mon_num = int(date_s[5:7]) - 1
            mon_list = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
            month_val = mon_list[mon_num] + " " + date_s[:4]

            ete = frappe.new_doc("Expense Tracker Entry")
            ete.date = doc.transaction_date
            ete.month = month_val
            ete.direction = direction
            ete.amount = amount
            ete.receipt = doc.receipt or None
            ete.notes = ("[Web Form] Source: Jamie Expense Entry " + str(doc.name) + ". " + str(doc.transaction_notes or "")).strip()
            ete.company = doc.business or None
            ete.cash_tracker_person = bal_person or None
            ete.transaction_type = "Reimbursement" if direction == "Reimbursement" else "Other"
            ete.entity = doc.business or "Motley Terpz"

            ete.db_insert()
            frappe.db.set_value("Expense Tracker Entry", ete.name, "docstatus", 1)
            frappe.db.set_value("Jamie Expense Entry", doc.name, "expense_tracker_entry", ete.name)
        else:
            frappe.log_error(
                "No money_in or money_out on Jamie Expense Entry " + str(doc.name),
                "Jamie Expense to ETE: no amount"
            )
            bal_person = None

    if bal_person:
        ci = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabCash Ledger Entry` WHERE cash_tracker_person=%s AND direction='Cash In' AND docstatus=1", bal_person)[0][0]
        co = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabCash Ledger Entry` WHERE cash_tracker_person=%s AND direction='Cash Out' AND docstatus=1", bal_person)[0][0]
        ep = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabExpense Tracker Entry` WHERE cash_tracker_person=%s AND direction='Expense' AND docstatus=1", bal_person)[0][0]
        rb = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabExpense Tracker Entry` WHERE cash_tracker_person=%s AND direction='Reimbursement' AND docstatus=1", bal_person)[0][0]
        net_cash = float(ci) - float(co)
        net_owed = float(ep) - float(rb)
        frappe.db.set_value("Cash Tracker Person", bal_person, {"cash_balance": net_cash, "total_expenses": float(ep), "total_reimbursed": float(rb), "net_owed": net_owed})
        ledger = frappe.db.get_value("Cash Balance Ledger", {"cash_tracker_person": bal_person})
        if ledger:
            frappe.db.set_value("Cash Balance Ledger", ledger, {"total_cash_in": float(ci), "total_cash_out": float(co), "net_cash": net_cash, "total_expenses": float(ep), "total_reimbursed": float(rb), "net_owed": net_owed})
except Exception as exc:
    frappe.log_error(str(exc), "Jamie Expense → ETE error")
"""

JAMIE_DELETE_CASCADE_SCRIPT = """\
linked = doc.expense_tracker_entry
if linked and frappe.db.exists("Expense Tracker Entry", linked):
    current_status = frappe.db.get_value("Expense Tracker Entry", linked, "docstatus")
    if current_status == 1:
        ete_doc = frappe.get_doc("Expense Tracker Entry", linked)
        ete_doc.cancel()
    frappe.delete_doc("Expense Tracker Entry", linked, ignore_permissions=True, force=1)
    frappe.db.set_value("Jamie Expense Entry", doc.name, "expense_tracker_entry", None)
"""

SCRIPTS = [
    {
        "name":              "Jamie Expense → Auto Submit",
        "script_type":       "DocType Event",
        "reference_doctype": "Jamie Expense Entry",
        "doctype_event":     "After Insert",
        "script":            AUTO_SUBMIT_SCRIPT,
    },
    {
        "name":              "Jamie Expense → Expense Tracker Entry",
        "script_type":       "DocType Event",
        "reference_doctype": "Jamie Expense Entry",
        "doctype_event":     "After Submit",
        "script":            JAMIE_ETE_SCRIPT,
    },
    {
        "name":              "Jamie Expense → Delete Expense Tracker Entry",
        "script_type":       "DocType Event",
        "reference_doctype": "Jamie Expense Entry",
        "doctype_event":     "Before Delete",
        "script":            JAMIE_DELETE_CASCADE_SCRIPT,
    },
]


def _create_server_scripts():
    for s in SCRIPTS:
        if frappe.db.exists("Server Script", s["name"]):
            doc = frappe.get_doc("Server Script", s["name"])
            doc.script        = s["script"]
            doc.doctype_event = s["doctype_event"]
            doc.disabled      = 0
            doc.save(ignore_permissions=True)
            print(f"  Updated: {s['name']}")
        else:
            doc = frappe.get_doc({"doctype": "Server Script", **s, "disabled": 0})
            doc.insert(ignore_permissions=True)
            print(f"  Created: {s['name']}")
    frappe.db.commit()


# ─────────────────────────────────────────────────────────
# 4. DocPerms update (if doctype was pre-existing)
# ─────────────────────────────────────────────────────────

def _set_perm(doctype, role, **kwargs):
    row = frappe.db.get_value(
        "DocPerm",
        {"parent": doctype, "role": role, "permlevel": 0},
        "name"
    )
    if row:
        frappe.db.set_value("DocPerm", row, kwargs)
        print(f"  Updated perm [{doctype}] {role}: {kwargs}")
    else:
        perm = frappe.get_doc({
            "doctype":    "DocPerm",
            "parent":     doctype,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "permlevel":  0,
            "role":       role,
            **kwargs,
        })
        perm.insert(ignore_permissions=True)
        print(f"  Created perm [{doctype}] {role}: {kwargs}")


# ─────────────────────────────────────────────────────────
# 5. Jamie workspace HTML update
# ─────────────────────────────────────────────────────────

NCK_CSS = """
/* ── Expense Widget (nck) styles ──────────────────────────────────────── */
.nck-wrap { margin-top: 36px; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: #fff; }
.nck-widget { border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: #fff; }
.nck-bar { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); flex-wrap: wrap; gap: 10px; }
.nck-bar-left { display: flex; align-items: center; gap: 10px; }
.nck-icon { width: 18px; height: 18px; stroke: #10b981; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.nck-heading { font-size: 14px; font-weight: 700; color: #f8fafc; letter-spacing: -0.2px; }
.nck-live-dot { width: 7px; height: 7px; border-radius: 50%; background: #10b981; box-shadow: 0 0 0 0 rgba(16,185,129,0.4); animation: nckPulse 1.8s ease-in-out infinite; }
@keyframes nckPulse { 0%,100% { box-shadow: 0 0 0 0 rgba(16,185,129,0.4); } 50% { box-shadow: 0 0 0 5px rgba(16,185,129,0); } }
.nck-bar-right { display: flex; gap: 8px; }
.nck-btn-new { padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; background: #10b981; color: #fff; text-decoration: none; transition: background 0.15s; }
.nck-btn-new:hover { background: #059669; color: #fff; }
.nck-btn-all { padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 600; background: rgba(255,255,255,0.1); color: #94a3b8; border: 1px solid rgba(255,255,255,0.15); text-decoration: none; transition: all 0.15s; }
.nck-btn-all:hover { background: rgba(255,255,255,0.18); color: #f1f5f9; }
.nck-kpi-row { display: grid; grid-template-columns: repeat(4,1fr); border-bottom: 1px solid #f1f5f9; }
.nck-kpi { padding: 18px 20px; border-right: 1px solid #f1f5f9; position: relative; }
.nck-kpi:last-child { border-right: none; }
.nck-kpi-dot { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--nkc); }
.nck-kpi-label { font-size: 10px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }
.nck-kpi-value { font-size: 22px; font-weight: 700; color: var(--nkc); font-family: 'DM Mono', monospace; }
.nck-table-card { padding: 0; }
.nck-table-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; border-bottom: 1px solid #f1f5f9; }
.nck-table-title { font-size: 12px; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: 0.06em; }
.nck-badge { font-size: 11px; font-weight: 600; color: #64748b; background: #f1f5f9; border-radius: 20px; padding: 2px 10px; }
.nck-loading { display: flex; justify-content: center; align-items: center; padding: 40px; }
.nck-spinner { width: 24px; height: 24px; border-radius: 50%; border: 2px solid #e2e8f0; border-top-color: #10b981; animation: nckSpin 0.7s linear infinite; }
@keyframes nckSpin { to { transform: rotate(360deg); } }
.nck-empty { padding: 24px 20px; text-align: center; color: #94a3b8; font-size: 13px; }
.nck-empty a { color: #10b981; }
.nck-tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.nck-tbl thead tr { border-bottom: 1px solid #f1f5f9; }
.nck-tbl thead th { padding: 10px 16px; text-align: left; font-size: 11px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }
.nck-tbl thead th.nck-right { text-align: right; }
.nck-tbl tbody tr { border-bottom: 1px solid #f8fafc; transition: background 0.1s; }
.nck-tbl tbody tr:last-child { border-bottom: none; }
.nck-tbl tbody tr:hover { background: #f8fafc; }
.nck-tbl td { padding: 10px 16px; color: #334155; vertical-align: middle; }
.nck-mono { font-family: 'DM Mono', monospace; font-size: 12px; }
.nck-right { text-align: right; }
.nck-dir { font-weight: 600; }
.nck-pill { display: inline-block; padding: 2px 9px; border-radius: 12px; font-size: 11px; font-weight: 600; background: #f1f5f9; color: #64748b; }
.nck-notes { max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#718096; font-size:12px; }
@media (max-width: 640px) { .nck-kpi-row { grid-template-columns: repeat(2,1fr); } .nck-kpi:nth-child(2) { border-right: none; } }
"""

EXPENSE_WIDGET_HTML = """
<!-- ── JAMIE EXPENSE TRACKER ───────────────────────────────────────────────── -->
<div class="nck-widget" id="jkeWidget" style="margin-top:32px">
  <div class="nck-bar">
    <div class="nck-bar-left">
      <svg class="nck-icon" viewBox="0 0 24 24"><path d="M9 14l2 2 4-4m-7 7h10a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2zm3-14V3m0 18v-2M3 12h2m14 0h2"/></svg>
      <span class="nck-heading">My Expense Tracker</span>
      <span class="nck-live-dot" title="Updates live"></span>
    </div>
    <div class="nck-bar-right">
      <a href="/jamie-expense-tracker" class="nck-btn-new">+ New Entry</a>
    </div>
  </div>
  <div class="nck-kpi-row">
    <div class="nck-kpi" style="--nkc:#c05621"><div class="nck-kpi-dot"></div><div class="nck-kpi-label">Expenses</div><div class="nck-kpi-value" id="jke-expenses">&mdash;</div></div>
    <div class="nck-kpi" style="--nkc:#059669"><div class="nck-kpi-dot"></div><div class="nck-kpi-label">Reimbursed</div><div class="nck-kpi-value" id="jke-reimbursed">&mdash;</div></div>
    <div class="nck-kpi" style="--nkc:#7c3aed"><div class="nck-kpi-dot"></div><div class="nck-kpi-label">Net Owed</div><div class="nck-kpi-value" id="jke-net">&mdash;</div></div>
    <div class="nck-kpi" style="--nkc:#2563eb"><div class="nck-kpi-dot"></div><div class="nck-kpi-label">Entries</div><div class="nck-kpi-value" id="jke-cnt">&mdash;</div></div>
  </div>
  <div class="nck-table-card">
    <div class="nck-table-header">
      <span class="nck-table-title">Recent Expenses</span>
      <span class="nck-badge" id="jke-badge">loading&hellip;</span>
    </div>
    <div id="jke-table"><div class="nck-loading"><div class="nck-spinner"></div></div></div>
  </div>
</div>
"""

EXPENSE_WIDGET_JS = """
// ── Jamie Expense Widget (real-time) ─────────────────────────────────────
(function() {
  var JKE_API = "cannabis_management.api.jamie.get_jamie_expense_summary";

  function fmtMoney(n) {
    n = parseFloat(n || 0);
    var neg = n < 0;
    var s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    return neg ? "-" + s : s;
  }

  function fmtDate(d) {
    if (!d) return "–";
    try { var p = d.toString().split(" ")[0].split("-"); return p[1] + "/" + p[2] + "/" + p[0]; }
    catch(e) { return d; }
  }

  function setEl(id, html) {
    var el = (typeof root_element !== "undefined" && root_element)
      ? root_element.querySelector("#" + id)
      : document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  function loadExpenseWidget() {
    frappe.call({
      method: JKE_API,
      callback: function(r) {
        if (!r || !r.message) return;
        var d = r.message;
        setEl("jke-expenses",   fmtMoney(d.total_expenses));
        setEl("jke-reimbursed", fmtMoney(d.total_reimbursed));
        var netV = parseFloat(d.net_owed || 0);
        setEl("jke-net", '<span style="color:' + (netV > 0 ? "#7c3aed" : "#059669") + '">' + fmtMoney(netV) + "</span>");
        setEl("jke-cnt", (d.count || 0).toLocaleString());
        var badge = (typeof root_element !== "undefined" && root_element)
          ? root_element.querySelector("#jke-badge")
          : document.getElementById("jke-badge");
        if (badge) badge.textContent = (d.count || 0) + " entries";
        renderExpenseTable(d.recent || []);
      }
    });
  }

  function renderExpenseTable(rows) {
    var wrap = (typeof root_element !== "undefined" && root_element)
      ? root_element.querySelector("#jke-table")
      : document.getElementById("jke-table");
    if (!wrap) return;
    if (!rows.length) {
      wrap.innerHTML = '<div class="nck-empty">No expense entries yet — <a href="/jamie-expense-tracker">submit your first entry</a></div>';
      return;
    }
    var html = '<div style="overflow-x:auto"><table class="nck-tbl">' +
      '<thead><tr><th>Date</th><th>Direction</th><th class="nck-right">Amount</th><th>Type</th><th>Notes</th></tr></thead><tbody>';
    rows.forEach(function(r) {
      var isExp = r.direction === "Expense";
      var color = isExp ? "#c05621" : "#059669";
      var notes = r.notes ? r.notes.replace(/^\\[.*?\\]\\s*/, "").substring(0, 55) + (r.notes.length > 55 ? "…" : "") : "–";
      html += "<tr>" +
        '<td class="nck-mono">' + fmtDate(r.date) + "</td>" +
        '<td><span class="nck-dir" style="color:' + color + '">' + (r.direction || "–") + "</span></td>" +
        '<td class="nck-mono nck-right" style="color:' + color + ';font-weight:600">' + fmtMoney(r.amount) + "</td>" +
        "<td>" + (r.transaction_type || "–") + "</td>" +
        '<td class="nck-notes">' + notes + "</td></tr>";
    });
    wrap.innerHTML = html + "</tbody></table></div>";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadExpenseWidget);
  } else {
    setTimeout(loadExpenseWidget, 300);
  }

  try {
    frappe.realtime.on("list_update", function(data) {
      if (data && data.doctype === "Jamie Expense Entry") {
        setTimeout(loadExpenseWidget, 500);
      }
    });
  } catch(e) { console.warn("JKE realtime:", e); }
})();
"""

HEMET_STORAGE_WIDGET_HTML = """
<!-- ── Hemet Storage Gauge ───────────────────────────────────────────────── -->
<div class="nck-widget" id="hemetStorageWidget" style="margin-top:32px">
  <div class="nck-bar">
    <div class="nck-bar-left">
      <svg class="nck-icon" viewBox="0 0 24 24"><path d="M4 7h16v10H4zM20 10h2v4h-2zM6 10v4"/></svg>
      <span class="nck-heading">Hemet Distro Storage</span>
      <span class="nck-live-dot" title="Live storage gauge"></span>
    </div>
    <div class="nck-bar-right">
      <a href="/app/query-report/Stock Balance" class="nck-btn-all">Stock Balance</a>
    </div>
  </div>
  <div class="hemet-gauge-wrap">
    <div id="hemet-gauge" style="font-family:Arial,sans-serif;max-width:420px;margin:0 auto;">
      <div style="font-weight:700;color:#401090;font-size:15px;margin-bottom:8px;">Hemet Distro — Storage Capacity</div>
      <svg viewBox="0 0 420 150" width="100%">
        <rect x="10" y="30" width="370" height="90" rx="10" fill="#fff" stroke="#401090" stroke-width="4"/>
        <rect x="382" y="60" width="16" height="30" rx="4" fill="#401090"/>
        <rect id="hemet-fill" x="14" y="34" width="0" height="82" rx="7" fill="#C060E0"/>
        <text id="hemet-pct" x="195" y="82" text-anchor="middle" font-size="34" font-weight="800" fill="#1c1c22">0%</text>
      </svg>
      <div id="hemet-lbl" style="text-align:center;color:#6b6b76;font-size:13px;margin-top:4px;">— lbs of — lbs</div>
    </div>
  </div>
</div>
"""

HEMET_STORAGE_WIDGET_JS = """
// ── Hemet Storage Gauge ─────────────────────────────────────────────────
(function() {
  var HEMET_API = "cannabis_management.api.jamie.get_hemet_storage_lbs";
  var CAPACITY_LBS = 40000; // Update with Hemet's confirmed max capacity in lbs.

  function renderHemetGauge(currentLbs) {
    currentLbs = parseFloat(currentLbs || 0);
    var pct = Math.min(100, Math.round(currentLbs / CAPACITY_LBS * 100));
    var w = Math.max(0, Math.min(362, 362 * currentLbs / CAPACITY_LBS));
    var fill = document.getElementById("hemet-fill");
    if (!fill) return;
    fill.setAttribute("width", w);
    fill.setAttribute("fill", pct >= 90 ? "#b91c1c" : (pct >= 70 ? "#b45309" : "#15803d"));
    document.getElementById("hemet-pct").textContent = pct + "%";
    document.getElementById("hemet-lbl").textContent =
      Math.round(currentLbs).toLocaleString() + " lbs of " +
      CAPACITY_LBS.toLocaleString() + " lbs";
  }

  function loadHemetGauge() {
    if (window.frappe && frappe.call) {
      frappe.call({ method: HEMET_API, callback: function(r) {
        renderHemetGauge((r && r.message) || 0);
      }});
    } else {
      renderHemetGauge(0);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadHemetGauge);
  } else {
    loadHemetGauge();
  }
})();
"""

HEMET_STORAGE_WIDGET_CSS = """
.hemet-gauge-wrap { padding: 18px 20px; }
.hemet-gauge-wrap svg { background: #f8fafc; border-radius: 14px; }
"""


def _update_jamie_workspace():
    block = frappe.get_doc("Custom HTML Block", "Jamie")
    html = block.html or ""
    injection_marker = "<div id=\"jd-pipeline-container\"></div>"
    fallback_marker = "<!-- TOLLING PARTNER STOCK -->"
    widget_html = ""

    if "hemetStorageWidget" in html:
        print("  Hemet storage widget HTML already present in Jamie block — skipping")
    else:
        if "jke-expenses" in html:
            widget_html += HEMET_STORAGE_WIDGET_HTML
            print("  Will insert Hemet storage widget HTML into Jamie block")
        else:
            widget_html += HEMET_STORAGE_WIDGET_HTML + EXPENSE_WIDGET_HTML
            print("  Will insert Jamie expense and Hemet storage widget HTML")

    if "HEMET_API" in (block.script or "") or "get_hemet_storage_lbs" in (block.script or ""):
        print("  Hemet storage gauge JS already present in Jamie block — skipping")
    else:
        block.script = (block.script or "") + HEMET_STORAGE_WIDGET_JS
        print("  Added Hemet storage gauge JS to Jamie block")

    if "JKE_API" in (block.script or ""):
        print("  Expense widget JS already present in Jamie block — skipping")
    else:
        block.script = (block.script or "") + EXPENSE_WIDGET_JS
        print("  Added expense widget JS to Jamie block")

    if "nck-widget" in (block.style or ""):
        print("  NCK CSS already present in Jamie style — skipping")
    else:
        block.style = (block.style or "") + NCK_CSS
        print("  Added NCK CSS to Jamie style")

    if ".hemet-gauge-wrap" in (block.style or ""):
        print("  Hemet storage gauge CSS already present in Jamie style — skipping")
    else:
        block.style = (block.style or "") + HEMET_STORAGE_WIDGET_CSS
        print("  Added Hemet storage gauge CSS to Jamie style")

    if widget_html:
        if injection_marker in html:
            block.html = html.replace(injection_marker, widget_html + injection_marker, 1)
            print("  Inserted widget HTML under Quick Links in Jamie block")
        elif fallback_marker in html:
            block.html = html.replace(fallback_marker, widget_html + fallback_marker, 1)
            print("  Inserted widget HTML before Tolling Partner Stock section")
        else:
            block.html = html + widget_html
            print("  Appended widget HTML to Jamie block (marker not found)")
    else:
        print("  No widget HTML insertion needed")

    block.save(ignore_permissions=True)
    frappe.db.commit()
    print("  Saved Jamie Custom HTML Block")


# ─────────────────────────────────────────────────────────
# 6. Add API function to jamie.py
# ─────────────────────────────────────────────────────────

JAMIE_API_FUNCTION = '''

@frappe.whitelist()
def get_jamie_expense_summary():
    """Returns expense summary for the currently logged-in user (Jamie).
    Filters strictly by owner = session user — no Finance bypass."""
    user = frappe.session.user
    user_filter = "AND owner = {escaped_user}".format(escaped_user=frappe.db.escape(user))

    summary = frappe.db.sql("""
        SELECT
            COALESCE(SUM(CASE WHEN money_out > 0 THEN money_out ELSE 0 END), 0) AS total_expenses,
            COALESCE(SUM(CASE WHEN money_in > 0 THEN money_in ELSE 0 END), 0)  AS total_reimbursed,
            COUNT(*) AS count
        FROM `tabJamie Expense Entry`
        WHERE docstatus = 1 {user_filter}
    """.format(user_filter=user_filter), as_dict=True)

    row = summary[0] if summary else {}
    total_expenses   = float(row.get("total_expenses")   or 0)
    total_reimbursed = float(row.get("total_reimbursed") or 0)
    net_owed = total_expenses - total_reimbursed

    recent = frappe.db.sql("""
        SELECT
            transaction_date AS date,
            CASE WHEN money_out > 0 THEN 'Expense' ELSE 'Reimbursement' END AS direction,
            CASE WHEN money_out > 0 THEN money_out ELSE money_in END AS amount,
            expense_type AS transaction_type,
            transaction_notes AS notes
        FROM `tabJamie Expense Entry`
        WHERE docstatus = 1 {user_filter}
        ORDER BY transaction_date DESC
        LIMIT 20
    """.format(user_filter=user_filter), as_dict=True)

    return {
        "total_expenses":   total_expenses,
        "total_reimbursed": total_reimbursed,
        "net_owed":         net_owed,
        "count":            int(row.get("count") or 0),
        "recent":           recent,
    }
'''


def _add_api_function():
    import os
    app_path = frappe.get_app_path("cannabis_management")
    api_path = os.path.join(app_path, "cannabis_management", "api", "jamie.py")
    with open(api_path, "r") as f:
        content = f.read()

    if "get_jamie_expense_summary" in content:
        print("  get_jamie_expense_summary already in jamie.py — skipping")
        return

    with open(api_path, "a") as f:
        f.write(JAMIE_API_FUNCTION)
    print("  Added get_jamie_expense_summary to jamie.py")


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────

def run():
    frappe.set_user("Administrator")

    print("\n── 1. Create Jamie Expense Entry doctype ────────────────────")
    _create_jamie_expense_doctype()

    print("\n── 2. Create Web Form: jamie-expense-tracker ────────────────")
    _create_web_form()

    print("\n── 3. Create Server Scripts ─────────────────────────────────")
    _create_server_scripts()

    print("\n── 4. Update DocPerms (ensure correct) ──────────────────────")
    dt = "Jamie Expense Entry"
    _set_perm(dt, "Website Manager",  read=1, write=1, create=1, submit=1, cancel=0, delete=0)
    _set_perm(dt, "Finance Manager",  read=1, write=1, create=1, submit=1, cancel=1, delete=0)
    _set_perm(dt, "Accounts Manager", read=1, write=1, create=1, submit=1, cancel=1, delete=0)
    _set_perm(dt, "System Manager",   read=1, write=1, create=1, submit=1, cancel=1, delete=1)
    frappe.db.commit()

    print("\n── 5. Update Jamie workspace ─────────────────────────────────")
    _update_jamie_workspace()

    print("\n── 6. Add API function to jamie.py ──────────────────────────")
    _add_api_function()

    frappe.db.commit()
    print("\nDone. Run: bench clear-cache && bench build --app cannabis_management")
