"""
Adds the Nikki Cash Ledger real-time widget to the Nikki workspace Custom HTML Block.
Also updates the Quick Link for 'Cash & Expense Tracker' to point to /nikki-cash-ledger.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.update_nikki_cash_widget.run
"""
import frappe

CASH_WIDGET_HTML = """
<!-- ── NIKKI CASH LEDGER TRACKER ──────────────────────────────────────── -->
<div class="nck-wrap" id="nckWrap">
  <div class="nck-bar">
    <div class="nck-bar-left">
      <svg class="nck-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
      <span class="nck-heading">My Cash Ledger</span>
      <span class="nck-live-dot" title="Updates live"></span>
    </div>
    <div class="nck-bar-right">
      <a href="/nikki-cash-ledger" class="nck-btn-new">+ New Entry</a>
      <a href="/cash-dashboard" class="nck-btn-all">View All &rarr;</a>
    </div>
  </div>
  <div class="nck-kpi-row">
    <div class="nck-kpi" style="--nkc:#059669"><div class="nck-kpi-dot"></div><div class="nck-kpi-label">Cash In</div><div class="nck-kpi-value" id="nck-in">&mdash;</div></div>
    <div class="nck-kpi" style="--nkc:#e11d48"><div class="nck-kpi-dot"></div><div class="nck-kpi-label">Cash Out</div><div class="nck-kpi-value" id="nck-out">&mdash;</div></div>
    <div class="nck-kpi" style="--nkc:#2563eb"><div class="nck-kpi-dot"></div><div class="nck-kpi-label">Net Cash</div><div class="nck-kpi-value" id="nck-net">&mdash;</div></div>
    <div class="nck-kpi" style="--nkc:#7c3aed"><div class="nck-kpi-dot"></div><div class="nck-kpi-label">Entries</div><div class="nck-kpi-value" id="nck-cnt">&mdash;</div></div>
  </div>
  <div class="nck-table-card">
    <div class="nck-table-header">
      <span class="nck-table-title">Recent Entries</span>
      <span class="nck-badge" id="nck-badge">loading&hellip;</span>
    </div>
    <div id="nck-table"><div class="nck-loading"><div class="nck-spinner"></div></div></div>
  </div>
</div>
"""

CASH_WIDGET_JS = """
// ── Nikki Cash Ledger Widget (real-time) ─────────────────────────────────
(function() {
  var NCK_API = "cannabis_management.api.nikki_cash_dashboard.get_nikki_ledger_summary";

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

  function loadCashWidget() {
    frappe.call({
      method: NCK_API,
      callback: function(r) {
        if (!r || !r.message) return;
        var d = r.message;
        setEl("nck-in",  fmtMoney(d.total_in));
        setEl("nck-out", fmtMoney(d.total_out));
        var netV = parseFloat(d.net || 0);
        setEl("nck-net", '<span style="color:' + (netV >= 0 ? "#059669" : "#e11d48") + '">' + fmtMoney(netV) + "</span>");
        setEl("nck-cnt", (d.count || 0).toLocaleString());
        var badge = (typeof root_element !== "undefined" && root_element)
          ? root_element.querySelector("#nck-badge")
          : document.getElementById("nck-badge");
        if (badge) badge.textContent = (d.count || 0) + " entries";
        renderCashTable(d.recent || []);
      }
    });
  }

  function renderCashTable(rows) {
    var wrap = (typeof root_element !== "undefined" && root_element)
      ? root_element.querySelector("#nck-table")
      : document.getElementById("nck-table");
    if (!wrap) return;
    if (!rows.length) {
      wrap.innerHTML = '<div class="nck-empty">No entries yet — <a href="/nikki-cash-ledger">submit your first entry</a></div>';
      return;
    }
    var html = '<div style="overflow-x:auto"><table class="nck-tbl">' +
      '<thead><tr><th>Date</th><th>Entity</th><th>Direction</th><th class="nck-right">Amount</th><th>Status</th></tr></thead><tbody>';
    rows.forEach(function(r) {
      var isIn   = r.direction === "Cash In";
      var color  = isIn ? "#059669" : "#e11d48";
      var prefix = isIn ? "+" : "-";
      var pills  = {
        "Open":      '<span class="nck-pill nck-open">Open</span>',
        "Reviewed":  '<span class="nck-pill nck-reviewed">Reviewed</span>',
        "Completed": '<span class="nck-pill nck-done">Done</span>'
      };
      var pill = pills[r.status] || ('<span class="nck-pill">' + (r.status || "–") + "</span>");
      html += "<tr>" +
        '<td class="nck-mono">' + fmtDate(r.date) + "</td>" +
        "<td>" + (r.entity || "–") + "</td>" +
        '<td><span class="nck-dir" style="color:' + color + '">' + (r.direction || "–") + "</span></td>" +
        '<td class="nck-mono nck-right" style="color:' + color + ';font-weight:600">' + prefix + fmtMoney(r.amount) + "</td>" +
        "<td>" + pill + "</td></tr>";
    });
    wrap.innerHTML = html + "</tbody></table></div>";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadCashWidget);
  } else {
    setTimeout(loadCashWidget, 250);
  }

  try {
    frappe.realtime.on("list_update", function(data) {
      if (data && data.doctype === "Nikki Cash Ledger Entry") {
        setTimeout(loadCashWidget, 500);
      }
    });
  } catch(e) { console.warn("NCK realtime:", e); }
})();
"""

CASH_WIDGET_CSS = """
/* ── Nikki Cash Ledger Widget ─────────────────────────────────────────── */
.nck-wrap { margin-top: 36px; border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; background: #fff; }
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
.nck-open     { background: #fef3c7; color: #b45309; }
.nck-reviewed { background: #dbeafe; color: #2563eb; }
.nck-done     { background: #dcfce7; color: #166534; }
@media (max-width: 640px) { .nck-kpi-row { grid-template-columns: repeat(2,1fr); } .nck-kpi:nth-child(2) { border-right: none; } }
"""


def run():
    frappe.set_user("Administrator")

    block = frappe.get_doc("Custom HTML Block", "Nikki")
    print(f"Current HTML len: {len(block.html or '')}")
    print(f"Current script len: {len(block.script or '')}")
    print(f"Current style len: {len(block.style or '')}")

    # ── 1. Update the Quick Link for "Cash & Expense Tracker" ──────────────
    old_html = block.html or ""
    if "/nikki-expense-tracker/new" in old_html:
        new_html = old_html.replace(
            'href="/nikki-expense-tracker/new"',
            'href="/nikki-cash-ledger"'
        ).replace(
            "Log and track operational expenses",
            "Log cash transactions by date, entity, and direction"
        )
        print("  Updated Quick Link: /nikki-expense-tracker/new → /nikki-cash-ledger")
    else:
        new_html = old_html
        print("  Quick Link already updated or not found — skipping")

    # ── 2. Append Cash Widget HTML (idempotent) ────────────────────────────
    if "nckWrap" not in new_html:
        new_html = new_html + "\n" + CASH_WIDGET_HTML.strip()
        print("  Appended cash widget HTML")
    else:
        print("  Cash widget HTML already present — skipping")

    # ── 3. Append Cash Widget JS (idempotent) ─────────────────────────────
    old_script = block.script or ""
    if "NCK_API" not in old_script:
        new_script = old_script + "\n" + CASH_WIDGET_JS.strip()
        print("  Appended cash widget JS")
    else:
        new_script = old_script
        print("  Cash widget JS already present — skipping")

    # ── 4. Append Cash Widget CSS (idempotent) ────────────────────────────
    old_style = block.style or ""
    if "nck-wrap" not in old_style:
        new_style = old_style + "\n" + CASH_WIDGET_CSS.strip()
        print("  Appended cash widget CSS")
    else:
        new_style = old_style
        print("  Cash widget CSS already present — skipping")

    block.html   = new_html
    block.script = new_script
    block.style  = new_style
    block.save(ignore_permissions=True)
    frappe.db.commit()

    print(f"\nUpdated HTML len: {len(block.html)}")
    print(f"Updated script len: {len(block.script)}")
    print(f"Updated style len: {len(block.style)}")
    print("\nDone. Clear cache and refresh the workspace to see changes.")
