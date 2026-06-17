"""
Rebuild the "Sales Target and Inventory Dashboard" Custom HTML Block, adding two
data sections ABOVE the Sales dashboard:

  1. COD Orders Shipped Yesterday  (Delivery Notes posted yesterday whose Sales
     Order has a payment_schedule)  -> Order | Customer | Amount
  2. Predicted vs Actual Money In   (Sales Invoices with outstanding > 0)
     -> KPI: Expected total vs Received total, table: Reference | Expected | Received

Data comes from cannabis_management.api.sales_daily_sync.
Runs inside the block's Shadow DOM, so all DOM access uses `root_element`.

Run: bench --site stage.alltechvirtual.com execute cannabis_management.add_sales_daily_sync_sections.run
"""
import frappe
from cannabis_management.build_sales_target_inventory_block import build as build_base

BLOCK_NAME = "Sales Target and Inventory Dashboard"

TOP_HTML = """
<!-- ===== SALES DAILY SYNC — TOP SECTIONS ===== -->
<div class="sds-top">

  <!-- COD orders shipped yesterday -->
  <div class="sds-card">
    <div class="sds-card-head">
      <div>
        <div class="sds-eyebrow">Logistics</div>
        <h3 class="sds-title">COD Orders Shipped — Last 7 Days</h3>
        <p class="sds-sub">Delivery Notes posted in the last 7 days whose Sales Order carries a payment schedule &middot; <span id="sds-cod-date">—</span></p>
      </div>
      <div class="sds-badge" id="sds-cod-total">—</div>
    </div>
    <div class="sds-table-wrap" id="sds-cod-table"><div class="sds-loading"><div class="sds-spin"></div></div></div>
  </div>

  <!-- Predicted vs actual money in -->
  <div class="sds-card">
    <div class="sds-card-head">
      <div>
        <div class="sds-eyebrow">Cash Flow</div>
        <h3 class="sds-title">Predicted vs Actual Money In</h3>
        <p class="sds-sub">Sales Invoices (last 7 days) with an outstanding balance — total invoiced vs actually received &middot; <span id="sds-pva-date">—</span></p>
      </div>
    </div>
    <div class="sds-kpi-row">
      <div class="sds-kpi sds-kpi-exp">
        <div class="sds-kpi-label">Expected — Total Invoiced</div>
        <div class="sds-kpi-val" id="sds-exp-total">—</div>
      </div>
      <div class="sds-kpi sds-kpi-rcv">
        <div class="sds-kpi-label">Actually Received</div>
        <div class="sds-kpi-val" id="sds-rcv-total">—</div>
      </div>
    </div>
    <div class="sds-table-wrap sds-scroll" id="sds-pva-table"><div class="sds-loading"><div class="sds-spin"></div></div></div>
  </div>

</div>
"""

SDS_CSS = """
/* ===== SALES DAILY SYNC — TOP SECTIONS CSS ===== */
.sds-top {
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  display:grid; grid-template-columns:1fr 1fr; gap:16px;
  max-width:1280px; margin:0 auto; padding:24px 24px 0;
}
@media(max-width:980px){ .sds-top{ grid-template-columns:1fr; } }
.sds-card {
  background:#fff; border:1px solid #e2e8f0; border-radius:12px;
  padding:18px 20px; box-shadow:0 1px 3px rgba(0,0,0,.05);
}
.sds-card-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:14px; }
.sds-eyebrow { font-size:10px; font-weight:700; letter-spacing:.8px; text-transform:uppercase; color:#94a3b8; }
.sds-title { font-size:17px; font-weight:700; color:#0f172a; margin:3px 0 4px; line-height:1.2; }
.sds-sub { font-size:12px; color:#64748b; margin:0; line-height:1.4; }
.sds-badge {
  background:#eff6ff; color:#1d4ed8; border-radius:8px; padding:6px 12px;
  font-size:12px; font-weight:700; white-space:nowrap; flex-shrink:0;
}
.sds-kpi-row { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:14px; }
.sds-kpi { border-radius:10px; padding:14px 16px; border:1px solid #e2e8f0; }
.sds-kpi-exp { background:#f5f3ff; border-color:#ddd6fe; }
.sds-kpi-rcv { background:#f0fdf4; border-color:#bbf7d0; }
.sds-kpi-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#94a3b8; margin-bottom:6px; }
.sds-kpi-val { font-size:24px; font-weight:800; line-height:1; }
.sds-kpi-exp .sds-kpi-val { color:#7c3aed; }
.sds-kpi-rcv .sds-kpi-val { color:#059669; }
.sds-table-wrap { overflow-x:auto; }
.sds-scroll { max-height:360px; overflow-y:auto; }
.sds-tbl { width:100%; border-collapse:collapse; font-size:13px; }
.sds-tbl th {
  position:sticky; top:0; background:#f8fafc; text-align:left; padding:9px 12px;
  font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.5px;
  color:#94a3b8; border-bottom:2px solid #e2e8f0; white-space:nowrap; z-index:1;
}
.sds-tbl td { padding:10px 12px; border-bottom:1px solid #f1f5f9; vertical-align:top; color:#334155; }
.sds-tbl tbody tr:hover td { background:#f8faff; }
.sds-r { text-align:right; }
.sds-mono { font-variant-numeric:tabular-nums; font-weight:600; color:#0f172a; }
.sds-link { color:#1d4ed8; font-weight:700; text-decoration:none; font-family:'SF Mono',Consolas,monospace; font-size:12px; }
.sds-link:hover { text-decoration:underline; }
.sds-muted { font-size:11px; color:#94a3b8; margin-top:2px; }
.sds-pos { color:#059669; }
.sds-neg { color:#dc2626; }
.sds-empty { padding:28px 16px; text-align:center; color:#94a3b8; font-size:13px; }
.sds-loading { padding:28px; text-align:center; }
.sds-spin { display:inline-block; width:22px; height:22px; border:3px solid #e2e8f0; border-top-color:#2563eb; border-radius:50%; animation:sdsSpin .7s linear infinite; }
@keyframes sdsSpin { to { transform:rotate(360deg); } }
"""

SDS_JS = r"""
/* ===== SALES DAILY SYNC — TOP SECTIONS JS ===== */
(function() {
  var API = "cannabis_management.api.sales_daily_sync.";

  function q(id) { return root_element.querySelector('#' + id); }
  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function money(n) {
    n = parseFloat(n || 0);
    var neg = n < 0;
    var s = '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return neg ? '-' + s : s;
  }
  function fmtDate(d) {
    if (!d) return '—';
    var p = String(d).split(' ')[0].split('-');
    return p.length === 3 ? p[1] + '/' + p[2] + '/' + p[0] : d;
  }

  function loadCod() {
    frappe.call({
      method: API + 'get_cod_deliveries_last_7_days',
      callback: function(r) {
        if (!r || !r.message) return;
        var d = r.message;
        var dl = q('sds-cod-date'); if (dl) dl.textContent = fmtDate(d.from_date) + ' – ' + fmtDate(d.to_date);
        var tb = q('sds-cod-total');
        if (tb) tb.textContent = money(d.total) + ' · ' + d.count + ' order' + (d.count !== 1 ? 's' : '');
        var wrap = q('sds-cod-table'); if (!wrap) return;
        if (!d.rows.length) { wrap.innerHTML = '<div class="sds-empty">No COD orders shipped in the last 7 days.</div>'; return; }
        var h = '<table class="sds-tbl"><thead><tr><th>Order</th><th>Customer</th><th class="sds-r">Amount</th></tr></thead><tbody>';
        d.rows.forEach(function(row) {
          h += '<tr><td>'
             + '<a class="sds-link" href="/app/delivery-note/' + esc(row.delivery_note) + '" target="_blank">' + esc(row.delivery_note) + '</a>'
             + '<div class="sds-muted">' + fmtDate(row.date) + (row.sales_order ? ' · SO: ' + esc(row.sales_order) : '') + '</div>'
             + '</td><td>' + esc(row.customer) + '</td>'
             + '<td class="sds-r sds-mono">' + money(row.amount) + '</td></tr>';
        });
        h += '</tbody></table>';
        wrap.innerHTML = h;
      },
      error: function() { var w = q('sds-cod-table'); if (w) w.innerHTML = '<div class="sds-empty">Could not load.</div>'; }
    });
  }

  function loadPva() {
    frappe.call({
      method: API + 'get_predicted_vs_actual',
      callback: function(r) {
        if (!r || !r.message) return;
        var d = r.message;
        var e = q('sds-exp-total'); if (e) e.textContent = money(d.expected_total);
        var rc = q('sds-rcv-total'); if (rc) rc.textContent = money(d.received_total);
        var pd = q('sds-pva-date'); if (pd) pd.textContent = fmtDate(d.from_date) + ' – ' + fmtDate(d.to_date);
        var wrap = q('sds-pva-table'); if (!wrap) return;
        if (!d.rows.length) { wrap.innerHTML = '<div class="sds-empty">No outstanding invoices in the last 7 days.</div>'; return; }
        var h = '<table class="sds-tbl"><thead><tr><th>Reference</th><th class="sds-r">Expected</th><th class="sds-r">Received</th></tr></thead><tbody>';
        d.rows.forEach(function(row) {
          var full = row.expected > 0 && row.received >= row.expected;
          h += '<tr><td>'
             + '<a class="sds-link" href="/app/sales-invoice/' + esc(row.reference) + '" target="_blank">' + esc(row.reference) + '</a>'
             + '<div class="sds-muted">' + esc(row.customer) + ' · ' + fmtDate(row.date) + '</div>'
             + '</td>'
             + '<td class="sds-r sds-mono">' + money(row.expected) + '</td>'
             + '<td class="sds-r sds-mono ' + (full ? 'sds-pos' : 'sds-neg') + '">' + money(row.received) + '</td></tr>';
        });
        h += '</tbody></table>';
        wrap.innerHTML = h;
      },
      error: function() { var w = q('sds-pva-table'); if (w) w.innerHTML = '<div class="sds-empty">Could not load.</div>'; }
    });
  }

  loadCod();
  loadPva();
})();
"""


AR_HTML = """
<!-- ===== AR DASHBOARD (beneath Inventory) ===== -->
<div class="ars-wrap">
  <div class="ars-head">
    <div>
      <div class="ars-eyebrow">Accounts Receivable</div>
      <h3 class="ars-title">AR Dashboard</h3>
      <p class="ars-sub">Legacy (pre Jun 1) vs post-legacy receivables &middot; week of <span id="ars-week">—</span></p>
    </div>
    <div class="ars-filter">
      <label class="ars-filter-label">Company</label>
      <select id="ars-company" class="ars-select"></select>
    </div>
  </div>
  <div class="ars-grid">
    <div class="ars-card ars-c1">
      <div class="ars-q">What is our legacy AR at?</div>
      <div class="ars-val" id="ars-legacy-bal">—</div>
      <div class="ars-label">Legacy AR Outstanding</div>
    </div>
    <div class="ars-card ars-c2">
      <div class="ars-q">How much legacy AR have we collected this week?</div>
      <div class="ars-val" id="ars-legacy-coll">—</div>
      <div class="ars-label">Legacy Collected · This Week</div>
    </div>
    <div class="ars-card ars-c3">
      <div class="ars-q">How much post-legacy AR have we accumulated so far this week?</div>
      <div class="ars-val" id="ars-new-acc">—</div>
      <div class="ars-label">Post-Legacy AR Accumulated · This Week</div>
    </div>
    <div class="ars-card ars-c4">
      <div class="ars-q">How much AR have we paid down this week?</div>
      <div class="ars-val" id="ars-paid">—</div>
      <div class="ars-label">AR Paid Down · This Week</div>
    </div>
  </div>
</div>
"""

AR_CSS = """
/* ===== AR DASHBOARD SECTION CSS ===== */
.ars-wrap {
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  max-width:1280px; margin:0 auto; padding:8px 24px 40px;
}
.ars-head { margin-bottom:14px; display:flex; align-items:flex-end; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.ars-eyebrow { font-size:10px; font-weight:700; letter-spacing:.8px; text-transform:uppercase; color:#94a3b8; }
.ars-title { font-size:18px; font-weight:700; color:#0f172a; margin:3px 0 4px; }
.ars-sub { font-size:12px; color:#64748b; margin:0; }
.ars-filter { display:flex; flex-direction:column; gap:5px; }
.ars-filter-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#94a3b8; }
.ars-select {
  border:1.5px solid #e2e8f0; border-radius:8px; padding:7px 11px; font-size:13px;
  background:#fff; color:#0f172a; cursor:pointer; min-width:200px; outline:none;
  transition:border-color .15s, box-shadow .15s;
}
.ars-select:focus { border-color:#2563eb; box-shadow:0 0 0 3px rgba(37,99,235,.1); }
.ars-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }
@media(max-width:980px){ .ars-grid{ grid-template-columns:repeat(2,1fr); } }
@media(max-width:560px){ .ars-grid{ grid-template-columns:1fr; } }
.ars-card {
  position:relative; background:#fff; border:1px solid #e2e8f0; border-radius:12px;
  padding:18px 18px 16px; box-shadow:0 1px 3px rgba(0,0,0,.05);
  border-top:3px solid #e2e8f0; display:flex; flex-direction:column; gap:8px;
}
.ars-c1 { border-top-color:#dc2626; }
.ars-c2 { border-top-color:#059669; }
.ars-c3 { border-top-color:#7c3aed; }
.ars-c4 { border-top-color:#2563eb; }
.ars-q { font-size:11.5px; font-weight:600; color:#475569; line-height:1.35; min-height:32px; }
.ars-val { font-size:26px; font-weight:800; line-height:1; }
.ars-c1 .ars-val { color:#dc2626; }
.ars-c2 .ars-val { color:#059669; }
.ars-c3 .ars-val { color:#7c3aed; }
.ars-c4 .ars-val { color:#2563eb; }
.ars-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#94a3b8; }
"""

AR_JS = r"""
/* ===== AR DASHBOARD SECTION JS ===== */
(function() {
  var SUMMARY_API   = "cannabis_management.api.sales_daily_sync.get_ar_week_summary";
  var COMPANIES_API = "cannabis_management.api.sales_daily_sync.get_ar_companies";
  var DEFAULT_COMPANY = "Motley Terpz";   // matches the AR Dashboard page default

  function q(id) { return root_element.querySelector('#' + id); }
  function money(n) {
    n = parseFloat(n || 0);
    var neg = n < 0;
    var s = '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return neg ? '-' + s : s;
  }
  function fmtDate(d) {
    if (!d) return '—';
    var p = String(d).split(' ')[0].split('-');
    return p.length === 3 ? p[1] + '/' + p[2] + '/' + p[0] : d;
  }
  function shimmer() {
    ['ars-legacy-bal','ars-legacy-coll','ars-new-acc','ars-paid'].forEach(function(id){
      var el = q(id); if (el) el.textContent = '…';
    });
  }

  function load(company) {
    shimmer();
    frappe.call({
      method: SUMMARY_API,
      args: { company: company },
      callback: function(r) {
        if (!r || !r.message) return;
        var d = r.message;
        var w = q('ars-week'); if (w) w.textContent = fmtDate(d.week_start) + ' – ' + fmtDate(d.week_end);
        var a = q('ars-legacy-bal'); if (a) a.textContent = money(d.legacy_ar_balance);
        var b = q('ars-legacy-coll'); if (b) b.textContent = money(d.legacy_collected_week);
        var c = q('ars-new-acc'); if (c) c.textContent = money(d.post_legacy_accumulated_week);
        var e = q('ars-paid'); if (e) e.textContent = money(d.ar_paid_down_week);
      }
    });
  }

  // Populate the company dropdown, then load the default company.
  frappe.call({
    method: COMPANIES_API,
    callback: function(r) {
      var sel = q('ars-company');
      var companies = (r && r.message) || [];
      if (sel) {
        companies.forEach(function(co) {
          var opt = document.createElement('option');
          opt.value = opt.textContent = co;
          sel.appendChild(opt);
        });
        var initial = companies.indexOf(DEFAULT_COMPANY) !== -1 ? DEFAULT_COMPANY : (companies[0] || '');
        sel.value = initial;
        sel.addEventListener('change', function() { load(this.value); });
        load(initial);
      } else {
        load(DEFAULT_COMPANY);
      }
    },
    error: function() { load(DEFAULT_COMPANY); }
  });
})();
"""


URC_HTML = """
<!-- ===== UNRECONCILED CUSTOMERS (below AR Dashboard) ===== -->
<div class="urc-wrap">
  <div class="urc-head">
    <div>
      <div class="urc-eyebrow">Accounts Receivable</div>
      <h3 class="urc-title">Unreconciled Customers</h3>
      <p class="urc-sub">Customers with legacy AR still flagged unreconciled &middot; as of <span id="urc-asof">—</span></p>
    </div>
    <div class="urc-filter">
      <label class="urc-filter-label">Company</label>
      <select id="urc-company" class="urc-select"></select>
    </div>
  </div>
  <div class="urc-kpi-row">
    <div class="urc-kpi">
      <div class="urc-kpi-label">Accounts Currently Unreconciled</div>
      <div class="urc-kpi-val" id="urc-count">—</div>
      <div class="urc-kpi-trend" id="urc-trend">—</div>
    </div>
    <div class="urc-note">
      Track day over day to confirm this number is shrinking. If it's flat or growing, that's the conversation.
    </div>
  </div>
  <div class="urc-table-wrap urc-scroll" id="urc-table"><div class="urc-loading"><div class="urc-spin"></div></div></div>
</div>
"""

URC_CSS = """
/* ===== UNRECONCILED CUSTOMERS SECTION CSS ===== */
.urc-wrap { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; max-width:1280px; margin:0 auto; padding:8px 24px 48px; }
.urc-head { margin-bottom:14px; display:flex; align-items:flex-end; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.urc-eyebrow { font-size:10px; font-weight:700; letter-spacing:.8px; text-transform:uppercase; color:#94a3b8; }
.urc-title { font-size:18px; font-weight:700; color:#0f172a; margin:3px 0 4px; }
.urc-sub { font-size:12px; color:#64748b; margin:0; }
.urc-filter { display:flex; flex-direction:column; gap:5px; }
.urc-filter-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#94a3b8; }
.urc-select { border:1.5px solid #e2e8f0; border-radius:8px; padding:7px 11px; font-size:13px; background:#fff; color:#0f172a; cursor:pointer; min-width:200px; outline:none; transition:border-color .15s, box-shadow .15s; }
.urc-select:focus { border-color:#2563eb; box-shadow:0 0 0 3px rgba(37,99,235,.1); }
.urc-kpi-row { display:flex; gap:14px; align-items:stretch; margin-bottom:14px; flex-wrap:wrap; }
.urc-kpi { background:#fff; border:1px solid #e2e8f0; border-top:3px solid #dc2626; border-radius:12px; padding:16px 18px; min-width:220px; box-shadow:0 1px 3px rgba(0,0,0,.05); }
.urc-kpi-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#94a3b8; margin-bottom:6px; }
.urc-kpi-val { font-size:30px; font-weight:800; color:#dc2626; line-height:1; }
.urc-kpi-trend { font-size:11px; font-weight:600; margin-top:8px; color:#94a3b8; }
.urc-trend-down { color:#059669; }
.urc-trend-up { color:#dc2626; }
.urc-trend-flat { color:#b45309; }
.urc-note { flex:1; min-width:240px; background:#fffbeb; border:1px solid #fde68a; border-radius:12px; padding:14px 16px; font-size:12px; color:#92400e; line-height:1.5; display:flex; align-items:center; }
.urc-table-wrap { overflow-x:auto; background:#fff; border:1px solid #e2e8f0; border-radius:12px; }
.urc-scroll { max-height:460px; overflow-y:auto; }
.urc-tbl { width:100%; border-collapse:collapse; font-size:13px; }
.urc-tbl th { position:sticky; top:0; background:#f8fafc; text-align:left; padding:10px 14px; font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:#94a3b8; border-bottom:2px solid #e2e8f0; white-space:nowrap; z-index:1; }
.urc-tbl td { padding:11px 14px; border-bottom:1px solid #f1f5f9; vertical-align:top; color:#334155; }
.urc-tbl tbody tr:hover td { background:#f8faff; }
.urc-cust { font-weight:600; color:#0f172a; }
.urc-muted { font-size:11px; color:#94a3b8; margin-top:2px; }
.urc-r { text-align:right; }
.urc-mono { font-variant-numeric:tabular-nums; }
.urc-out { font-weight:700; color:#dc2626; }
.urc-tfoot td { position:sticky; bottom:0; background:#f8fafc; border-top:2px solid #e2e8f0; font-weight:800; color:#0f172a; padding:11px 14px; }
.urc-empty { padding:28px 16px; text-align:center; color:#94a3b8; font-size:13px; }
.urc-loading { padding:28px; text-align:center; }
.urc-spin { display:inline-block; width:22px; height:22px; border:3px solid #e2e8f0; border-top-color:#dc2626; border-radius:50%; animation:urcSpin .7s linear infinite; }
@keyframes urcSpin { to { transform:rotate(360deg); } }
"""

URC_JS = r"""
/* ===== UNRECONCILED CUSTOMERS SECTION JS ===== */
(function() {
  var SUMMARY_API   = "cannabis_management.api.sales_daily_sync.get_unreconciled_customers";
  var COMPANIES_API = "cannabis_management.api.sales_daily_sync.get_ar_companies";
  var DEFAULT_COMPANY = "Motley Terpz";

  function q(id) { return root_element.querySelector('#' + id); }
  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function money(n) {
    n = parseFloat(n || 0);
    var neg = n < 0;
    var s = '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return neg ? '-' + s : s;
  }
  function fmtDate(d) {
    if (!d) return '—';
    var p = String(d).split(' ')[0].split('-');
    return p.length === 3 ? p[1] + '/' + p[2] + '/' + p[0] : d;
  }

  function renderTrend(d) {
    var el = q('urc-trend'); if (!el) return;
    if (d.prev_count === null || d.prev_count === undefined) {
      el.className = 'urc-kpi-trend'; el.textContent = 'baseline set today · trend builds from tomorrow';
      return;
    }
    var diff = d.count - d.prev_count;
    var since = ' since ' + fmtDate(d.prev_date);
    if (diff < 0)      { el.className = 'urc-kpi-trend urc-trend-down'; el.textContent = '▼ ' + Math.abs(diff) + ' fewer' + since + ' (shrinking)'; }
    else if (diff > 0) { el.className = 'urc-kpi-trend urc-trend-up';   el.textContent = '▲ ' + diff + ' more' + since + ' — worth a conversation'; }
    else               { el.className = 'urc-kpi-trend urc-trend-flat'; el.textContent = 'No change' + since; }
    if (d.week_start_count !== null && d.week_start_count !== undefined) {
      var wd = d.count - d.week_start_count;
      el.textContent += ' · ' + (wd <= 0 ? '▼ ' + Math.abs(wd) : '▲ ' + wd) + ' vs start of week';
    }
  }

  function load(company) {
    var wrap = q('urc-table');
    if (wrap) wrap.innerHTML = '<div class="urc-loading"><div class="urc-spin"></div></div>';
    frappe.call({
      method: SUMMARY_API,
      args: { company: company },
      callback: function(r) {
        if (!r || !r.message) return;
        var d = r.message;
        var ao = q('urc-asof'); if (ao) ao.textContent = fmtDate(d.as_of);
        var cnt = q('urc-count'); if (cnt) cnt.textContent = (d.count || 0).toLocaleString();
        renderTrend(d);
        if (!wrap) return;
        if (!d.rows.length) { wrap.innerHTML = '<div class="urc-empty">No unreconciled customers for this company.</div>'; return; }
        var h = '<table class="urc-tbl"><thead><tr><th>Customer</th><th class="urc-r">Invoiced</th><th class="urc-r">Paid</th><th class="urc-r">Outstanding</th></tr></thead><tbody>';
        var ti = 0, tp = 0, to = 0;
        d.rows.forEach(function(row) {
          ti += row.invoiced; tp += row.paid; to += row.outstanding;
          h += '<tr><td><span class="urc-cust">' + esc(row.customer_name) + '</span>'
             + '<div class="urc-muted">' + (row.invoice_count || 0) + ' invoice' + (row.invoice_count !== 1 ? 's' : '') + '</div></td>'
             + '<td class="urc-r urc-mono">' + money(row.invoiced) + '</td>'
             + '<td class="urc-r urc-mono">' + money(row.paid) + '</td>'
             + '<td class="urc-r urc-mono urc-out">' + money(row.outstanding) + '</td></tr>';
        });
        h += '</tbody><tfoot><tr><td class="urc-tfoot">Total · ' + d.rows.length + ' customers</td>'
           + '<td class="urc-tfoot urc-r urc-mono">' + money(ti) + '</td>'
           + '<td class="urc-tfoot urc-r urc-mono">' + money(tp) + '</td>'
           + '<td class="urc-tfoot urc-r urc-mono urc-out">' + money(to) + '</td></tr></tfoot></table>';
        wrap.innerHTML = h;
      },
      error: function() { if (wrap) wrap.innerHTML = '<div class="urc-empty">Could not load.</div>'; }
    });
  }

  frappe.call({
    method: COMPANIES_API,
    callback: function(r) {
      var sel = q('urc-company');
      var companies = (r && r.message) || [];
      if (sel) {
        companies.forEach(function(co) {
          var opt = document.createElement('option');
          opt.value = opt.textContent = co;
          sel.appendChild(opt);
        });
        var initial = companies.indexOf(DEFAULT_COMPANY) !== -1 ? DEFAULT_COMPANY : (companies[0] || '');
        sel.value = initial;
        sel.addEventListener('change', function() { load(this.value); });
        load(initial);
      } else { load(DEFAULT_COMPANY); }
    },
    error: function() { load(DEFAULT_COMPANY); }
  });
})();
"""


def run():
    frappe.set_user("Administrator")
    base_html, base_script, base_style = build_base()

    # AR + Unreconciled sections go at the end of the HTML => beneath the Inventory dashboard.
    full_html = TOP_HTML.strip() + "\n\n" + base_html + "\n\n" + AR_HTML.strip() + "\n\n" + URC_HTML.strip()
    full_style = base_style + "\n\n" + SDS_CSS.strip() + "\n\n" + AR_CSS.strip() + "\n\n" + URC_CSS.strip()
    full_script = base_script + "\n\n" + SDS_JS.strip() + "\n\n" + AR_JS.strip() + "\n\n" + URC_JS.strip()

    doc = frappe.get_doc("Custom HTML Block", BLOCK_NAME)
    doc.html = full_html
    doc.script = full_script
    doc.style = full_style
    doc.private = 0
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    print(f"Updated block '{BLOCK_NAME}'")
    print(f"  html   : {len(full_html):,} chars")
    print(f"  script : {len(full_script):,} chars")
    print(f"  style  : {len(full_style):,} chars")
