frappe.pages['inventory-sales-dashboard'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Inventory Sales Dashboard',
        single_column: true,
    });

    page.main.html(`
<style>
/* ═══════════════════════════════════════════════════
   INVENTORY SALES DASHBOARD — STYLES
═══════════════════════════════════════════════════ */

/* base */
.isd-wrap {
    padding:0;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
    background:#F1F5F9;
    min-height:calc(100vh - 60px);
}

/* ── header ── */
.isd-header {
    background:linear-gradient(135deg,#1E3A8A 0%,#2563EB 60%,#3B82F6 100%);
    padding:18px 24px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    flex-wrap:wrap;
    gap:12px;
}
.isd-header-left { display:flex; align-items:center; gap:14px; }
.isd-header-icon {
    width:44px; height:44px;
    background:rgba(255,255,255,.18);
    border-radius:12px;
    display:flex; align-items:center; justify-content:center;
    flex-shrink:0;
}
.isd-title  { font-size:19px; font-weight:700; color:#fff; margin:0 0 3px; line-height:1.2; }
.isd-subtitle { color:rgba(255,255,255,.75); font-size:12px; margin:0; }
.isd-btn-export {
    background:rgba(255,255,255,.15);
    color:#fff;
    border:1.5px solid rgba(255,255,255,.3);
    border-radius:8px;
    padding:8px 18px;
    font-size:13px;
    font-weight:500;
    cursor:pointer;
    display:flex; align-items:center; gap:6px;
    transition:background .15s;
    white-space:nowrap;
}
.isd-btn-export:hover { background:rgba(255,255,255,.28); }

/* ── body grid ── */
.isd-body {
    display:grid;
    grid-template-columns:220px 1fr;
    min-height:calc(100vh - 130px);
}
@media(max-width:900px){ .isd-body{ grid-template-columns:1fr; } }

/* ── sidebar ── */
.isd-sidebar {
    background:#fff;
    border-right:1px solid #E2E8F0;
}
.isd-sidebar-header {
    padding:12px 16px;
    font-size:10px;
    font-weight:700;
    letter-spacing:.8px;
    text-transform:uppercase;
    color:#94A3B8;
    border-bottom:1px solid #F1F5F9;
    background:#FAFBFC;
    display:flex; justify-content:space-between; align-items:center;
    cursor:pointer;
    user-select:none;
}
.isd-group-list { padding:6px 0; overflow-y:auto; max-height:calc(100vh - 180px); }
.isd-group-btn {
    padding:9px 16px 9px 14px;
    cursor:pointer;
    font-size:13px;
    font-weight:500;
    color:#475569;
    transition:all .13s;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
    border-left:3px solid transparent;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:6px;
}
.isd-group-btn:hover { background:#F0F7FF; color:#2563EB; border-left-color:#93C5FD; }
.isd-group-btn.active {
    background:#EFF6FF;
    color:#1D4ED8;
    font-weight:600;
    border-left-color:#2563EB;
}
.isd-group-count {
    font-size:10px;
    background:#E2E8F0;
    color:#64748B;
    border-radius:10px;
    padding:1px 6px;
    font-weight:600;
    flex-shrink:0;
}
.isd-group-btn.active .isd-group-count { background:#DBEAFE; color:#1D4ED8; }

/* ── main panel ── */
.isd-main { padding:20px; display:flex; flex-direction:column; gap:16px; }

/* ── group title bar ── */
.isd-group-title-bar {
    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;
}
.isd-group-title {
    font-size:18px;
    font-weight:700;
    color:#0F172A;
    margin:0;
    display:flex;
    align-items:center;
    gap:10px;
}
.isd-group-pill {
    background:#EFF6FF;
    color:#2563EB;
    border-radius:6px;
    padding:2px 10px;
    font-size:11px;
    font-weight:600;
    letter-spacing:.3px;
}

/* ── summary cards ── */
.isd-summary-row { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
@media(max-width:740px){ .isd-summary-row{ grid-template-columns:repeat(2,1fr); } }
.isd-summary-card {
    background:#fff;
    border-radius:12px;
    padding:16px;
    box-shadow:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
    border-top:3px solid #E2E8F0;
    display:flex;
    flex-direction:column;
    gap:6px;
}
.isd-sum-1 { border-top-color:#2563EB; }
.isd-sum-2 { border-top-color:#16A34A; }
.isd-sum-3 { border-top-color:#0891B2; }
.isd-sum-4 { border-top-color:#D97706; }
.isd-summary-label {
    font-size:10px;
    font-weight:700;
    text-transform:uppercase;
    letter-spacing:.6px;
    color:#94A3B8;
    margin:0;
}
.isd-summary-value { font-size:28px; font-weight:800; line-height:1; margin:0; }
.isd-sum-1 .isd-summary-value { color:#2563EB; }
.isd-sum-2 .isd-summary-value { color:#16A34A; }
.isd-sum-3 .isd-summary-value { color:#0891B2; }
.isd-sum-4 .isd-summary-value { color:#D97706; }

/* ── filter card ── */
.isd-card {
    background:#fff;
    border-radius:12px;
    box-shadow:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
    overflow:hidden;
}
.isd-filter-wrap { padding:14px 16px; }
.isd-filter-bar { display:flex; flex-wrap:wrap; gap:14px; align-items:flex-end; }
.isd-filter-group { display:flex; flex-direction:column; gap:5px; }
.isd-filter-label {
    font-size:10px;
    font-weight:700;
    text-transform:uppercase;
    letter-spacing:.5px;
    color:#94A3B8;
}
.isd-filter-input {
    border:1.5px solid #E2E8F0;
    border-radius:8px;
    padding:7px 11px;
    font-size:13px;
    outline:none;
    min-width:170px;
    color:#0F172A;
    background:#fff;
    transition:border-color .15s, box-shadow .15s;
}
.isd-filter-input:focus { border-color:#2563EB; box-shadow:0 0 0 3px rgba(37,99,235,.1); }
.isd-filter-select {
    border:1.5px solid #E2E8F0;
    border-radius:8px;
    padding:7px 11px;
    font-size:13px;
    outline:none;
    background:#fff;
    min-width:155px;
    color:#0F172A;
    cursor:pointer;
    transition:border-color .15s, box-shadow .15s;
}
.isd-filter-select:focus { border-color:#2563EB; box-shadow:0 0 0 3px rgba(37,99,235,.1); }
/* toggle switch */
.isd-toggle {
    position:relative;
    display:inline-block;
    width:40px; height:22px;
    margin-top:6px;
}
.isd-toggle input { opacity:0; width:0; height:0; position:absolute; }
.isd-toggle-slider {
    position:absolute; cursor:pointer;
    top:0; left:0; right:0; bottom:0;
    background:#CBD5E1; border-radius:22px;
    transition:.2s;
}
.isd-toggle-slider:before {
    position:absolute; content:"";
    height:16px; width:16px;
    left:3px; bottom:3px;
    background:#fff; border-radius:50%;
    transition:.2s;
    box-shadow:0 1px 3px rgba(0,0,0,.2);
}
.isd-toggle input:checked + .isd-toggle-slider { background:#2563EB; }
.isd-toggle input:checked + .isd-toggle-slider:before { transform:translateX(18px); }
.isd-btn-reset {
    background:#F8FAFC;
    border:1.5px solid #E2E8F0;
    border-radius:8px;
    padding:7px 16px;
    font-size:13px;
    font-weight:500;
    cursor:pointer;
    color:#475569;
    transition:all .15s;
    white-space:nowrap;
}
.isd-btn-reset:hover { background:#EFF6FF; border-color:#93C5FD; color:#1D4ED8; }

/* ── table ── */
.isd-table-wrap { overflow-x:auto; padding:0; }
.isd-table { width:100%; border-collapse:collapse; font-size:13px; }
.isd-table th {
    background:#F8FAFC;
    padding:10px 14px;
    text-align:left;
    font-size:10px;
    font-weight:700;
    text-transform:uppercase;
    letter-spacing:.5px;
    color:#94A3B8;
    border-bottom:2px solid #E2E8F0;
    white-space:nowrap;
}
.isd-table td { padding:11px 14px; border-bottom:1px solid #F1F5F9; vertical-align:middle; }
.isd-table tbody tr { transition:background .1s; }
.isd-table tbody tr:not(.expand-row):hover td { background:#F8FAFF; }
.isd-table tr.row-danger td { background:#FFF5F5; }
.isd-table tr.row-danger:hover td { background:#FEE2E2 !important; }
.isd-table tr.row-warning td { background:#FFFDF0; }
.isd-table tr.row-warning:hover td { background:#FEF9C3 !important; }
.isd-table tr.expand-row td {
    background:#F0F7FF;
    padding:0;
    border-bottom:2px solid #BFDBFE;
}
.isd-table tr.expand-row:hover td { background:#F0F7FF !important; }

/* item code cell */
.isd-code-cell { display:flex; align-items:center; gap:6px; }
.isd-code-text { font-family:'SF Mono',Consolas,monospace; font-size:12px; color:#1E3A8A; font-weight:600; }
.isd-copy-btn {
    background:#F1F5F9;
    border:none;
    border-radius:5px;
    padding:2px 7px;
    font-size:10px;
    cursor:pointer;
    color:#64748B;
    font-weight:600;
    transition:all .15s;
    white-space:nowrap;
    flex-shrink:0;
}
.isd-copy-btn:hover { background:#2563EB; color:#fff; }
.isd-item-name { color:#1E293B; font-weight:500; }
.isd-wh-text { color:#475569; font-size:12px; }
.isd-wh-none { color:#CBD5E1; font-size:12px; font-style:italic; }
.isd-num { font-variant-numeric:tabular-nums; color:#334155; }
.isd-num-avail { font-variant-numeric:tabular-nums; font-weight:700; color:#0F172A; }

/* ── status badges ── */
.badge-available { background:#DCFCE7; color:#15803D; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:700; white-space:nowrap; }
.badge-low       { background:#FEF9C3; color:#A16207; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:700; white-space:nowrap; }
.badge-out       { background:#FEE2E2; color:#DC2626; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:700; white-space:nowrap; }
.badge-type-bho  { background:#DBEAFE; color:#1D4ED8; padding:2px 9px; border-radius:20px; font-size:11px; font-weight:600; }
.badge-type-sho  { background:#FCE7F3; color:#9D174D; padding:2px 9px; border-radius:20px; font-size:11px; font-weight:600; }

/* ── expand arrow ── */
.isd-expand-td {
    width:42px;
    padding:8px 10px !important;
    text-align:center;
    cursor:pointer;
}
.isd-expand-arrow {
    display:inline-flex;
    align-items:center;
    justify-content:center;
    width:26px; height:26px;
    border-radius:7px;
    font-size:9px;
    font-weight:900;
    transition:transform .2s cubic-bezier(.34,1.56,.64,1), background .15s, color .15s;
    user-select:none;
    pointer-events:none;
}
.isd-expand-td:hover .isd-expand-arrow { background:#DBEAFE; color:#1D4ED8; }
.isd-expand-td.expanded .isd-expand-arrow { transform:rotate(90deg); background:#2563EB; color:#fff; }
.isd-expand-td.no-data   .isd-expand-arrow { background:#F1F5F9; color:#CBD5E1; cursor:not-allowed; }
.isd-expand-td.needs-invoice .isd-expand-arrow { background:#FEF3C7; color:#D97706; }
.isd-expand-td.has-activity  .isd-expand-arrow { background:#DCFCE7; color:#16A34A; }

/* ── expand panel ── */
.isd-expand-panel { padding:16px 20px 20px; }
.isd-expand-heading {
    font-size:10px;
    font-weight:700;
    text-transform:uppercase;
    letter-spacing:.8px;
    color:#94A3B8;
    margin-bottom:14px;
    display:flex;
    align-items:center;
    gap:10px;
}
.isd-expand-heading::after { content:''; flex:1; height:1px; background:#E2E8F0; }

.isd-customer-block {
    background:#fff;
    border:1px solid #E2E8F0;
    border-radius:12px;
    margin-bottom:12px;
    overflow:hidden;
    box-shadow:0 1px 4px rgba(0,0,0,.05);
}
.isd-customer-block:last-child { margin-bottom:0; }

.isd-customer-header {
    padding:11px 16px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    flex-wrap:wrap;
    gap:8px;
    border-bottom:1px solid #F1F5F9;
}
.isd-ch-fully     { background:#F0FDF4; }
.isd-ch-partial   { background:#FFFBEB; }
.isd-ch-notinv    { background:#FFF7ED; }
.isd-ch-unlinked  { background:#FAF5FF; }
.isd-ch-direct    { background:#EFF6FF; }
.isd-ch-none      { background:#F9FAFB; }

.isd-customer-name { font-weight:700; font-size:14px; color:#0F172A; display:flex; align-items:center; gap:7px; }
.isd-cust-icon { font-size:18px; line-height:1; }

.isd-sale-status-badge {
    padding:4px 12px;
    border-radius:20px;
    font-size:11px;
    font-weight:700;
    white-space:nowrap;
}
.isd-sb-fully    { background:#DCFCE7; color:#15803D; }
.isd-sb-partial  { background:#FEF9C3; color:#92400E; }
.isd-sb-notinv   { background:#FFEDD5; color:#C2410C; }
.isd-sb-unlinked { background:#EDE9FE; color:#6D28D9; }
.isd-sb-direct   { background:#DBEAFE; color:#1D4ED8; }
.isd-sb-none     { background:#F1F5F9; color:#64748B; }

.isd-customer-body { padding:14px 16px; }

.isd-alert-msg {
    padding:10px 14px;
    border-radius:8px;
    font-size:12px;
    font-weight:500;
    margin-bottom:14px;
    display:flex;
    align-items:flex-start;
    gap:8px;
    line-height:1.5;
    border:1px solid transparent;
}
.isd-alert-warn { background:#FFFBEB; color:#92400E; border-color:#FDE68A; }
.isd-alert-ok   { background:#F0FDF4; color:#14532D; border-color:#BBF7D0; }
.isd-alert-info { background:#EFF6FF; color:#1E3A8A; border-color:#BFDBFE; }
.isd-alert-icon { font-size:14px; flex-shrink:0; margin-top:1px; }

.isd-section-title {
    font-size:10px;
    font-weight:700;
    text-transform:uppercase;
    letter-spacing:.7px;
    color:#94A3B8;
    margin:0 0 8px;
    display:flex;
    align-items:center;
    gap:8px;
}
.isd-section-title::after { content:''; flex:1; height:1px; background:#F1F5F9; }

/* delivery note card */
.isd-dn-card {
    background:#F8FAFF;
    border:1px solid #DBEAFE;
    border-left:3px solid #2563EB;
    border-radius:8px;
    padding:11px 14px;
    margin-bottom:8px;
}
.isd-dn-card:last-child { margin-bottom:0; }
.isd-dn-top {
    display:flex;
    flex-wrap:wrap;
    gap:8px;
    align-items:center;
    margin-bottom:8px;
}
.isd-doc-link { color:#1D4ED8; font-weight:700; text-decoration:none; font-size:13px; font-family:'SF Mono',Consolas,monospace; }
.isd-doc-link:hover { text-decoration:underline; color:#1E40AF; }
.isd-pill {
    display:inline-flex; align-items:center; gap:3px;
    padding:2px 8px;
    border-radius:6px;
    font-size:11px;
    font-weight:600;
    white-space:nowrap;
}
.isd-pill-blue   { background:#EFF6FF; color:#1D4ED8; }
.isd-pill-green  { background:#F0FDF4; color:#15803D; }
.isd-pill-gray   { background:#F1F5F9; color:#475569; }
.isd-pill-orange { background:#FFF7ED; color:#C2410C; }

/* invoice list (nested under DN) */
.isd-no-invoice-msg {
    display:flex;
    align-items:center;
    gap:8px;
    background:#FFFBEB;
    border:1px solid #FDE68A;
    border-radius:7px;
    padding:8px 12px;
    font-size:12px;
    color:#92400E;
    font-weight:500;
    margin-top:6px;
}
.isd-si-list {
    margin-top:8px;
    border-left:2px solid #DBEAFE;
    padding-left:12px;
}
.isd-si-list-title {
    font-size:10px;
    font-weight:700;
    text-transform:uppercase;
    letter-spacing:.5px;
    color:#64748B;
    margin-bottom:6px;
}
.isd-si-row {
    display:flex;
    flex-wrap:wrap;
    gap:8px;
    align-items:center;
    padding:6px 0;
    border-bottom:1px dashed #E2E8F0;
    font-size:12px;
}
.isd-si-row:last-child { border-bottom:none; padding-bottom:0; }
.isd-si-link { color:#1D4ED8; font-weight:700; text-decoration:none; font-family:'SF Mono',Consolas,monospace; font-size:12px; }
.isd-si-link:hover { text-decoration:underline; }
.isd-si-amount { font-weight:700; color:#0F172A; font-variant-numeric:tabular-nums; }
.isd-outstanding-ok  { color:#15803D; font-weight:700; }
.isd-outstanding-due { color:#DC2626; font-weight:700; }

/* direct invoice section */
.isd-direct-section { margin-top:12px; }

/* misc */
.isd-loading {
    padding:56px 24px;
    text-align:center;
    color:#94A3B8;
    display:flex; flex-direction:column; align-items:center; gap:14px;
}
.isd-spinner {
    width:30px; height:30px;
    border:3px solid #E2E8F0;
    border-top-color:#2563EB;
    border-radius:50%;
    animation:isd-spin .7s linear infinite;
}
@keyframes isd-spin { to { transform:rotate(360deg); } }
.isd-loading-text { font-size:13px; color:#94A3B8; }
.isd-empty {
    padding:56px 24px;
    text-align:center;
    color:#94A3B8;
    font-size:14px;
    line-height:1.6;
}
.isd-empty-icon { font-size:40px; margin-bottom:10px; }
.isd-no-activity-msg {
    padding:16px;
    text-align:center;
    color:#94A3B8;
    font-size:12px;
    font-style:italic;
    background:#F8FAFC;
    border-radius:8px;
}
</style>

<div class="isd-wrap">

    <!-- Header -->
    <div class="isd-header">
        <div class="isd-header-left">
            <div class="isd-header-icon">
                <svg width="22" height="22" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                    <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                    <line x1="12" y1="22.08" x2="12" y2="12"/>
                </svg>
            </div>
            <div>
                <h2 class="isd-title">Inventory Sales Dashboard</h2>
                <p class="isd-subtitle">Stock visibility · Delivery Notes · Sales Invoice status</p>
            </div>
        </div>
        <button class="isd-btn-export" id="isd-export-btn" type="button">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Export CSV
        </button>
    </div>

    <div class="isd-body">

        <!-- Sidebar -->
        <div class="isd-sidebar">
            <div class="isd-sidebar-header" id="isd-sidebar-toggle">
                <span>Item Groups</span>
                <span id="isd-sidebar-icon">▾</span>
            </div>
            <div class="isd-group-list" id="isd-group-list">
                <div class="isd-loading"><div class="isd-spinner"></div></div>
            </div>
        </div>

        <!-- Main -->
        <div class="isd-main">

            <!-- Group title -->
            <div class="isd-group-title-bar">
                <h4 class="isd-group-title" id="isd-selected-group">
                    <svg width="18" height="18" fill="none" stroke="#94A3B8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24" style="flex-shrink:0"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                    Select an Item Group
                </h4>
            </div>

            <!-- Summary cards -->
            <div class="isd-summary-row">
                <div class="isd-summary-card isd-sum-1">
                    <div class="isd-summary-label">Total Items</div>
                    <div class="isd-summary-value" id="isd-total-items">—</div>
                </div>
                <div class="isd-summary-card isd-sum-2">
                    <div class="isd-summary-label">Total Qty</div>
                    <div class="isd-summary-value" id="isd-total-qty">—</div>
                </div>
                <div class="isd-summary-card isd-sum-3">
                    <div class="isd-summary-label">Available Qty</div>
                    <div class="isd-summary-value" id="isd-avail-qty">—</div>
                </div>
                <div class="isd-summary-card isd-sum-4">
                    <div class="isd-summary-label">Low Stock Items</div>
                    <div class="isd-summary-value" id="isd-low-stock">—</div>
                </div>
            </div>

            <!-- Filters -->
            <div class="isd-card">
                <div class="isd-filter-wrap">
                    <div class="isd-filter-bar">
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Search</label>
                            <input type="text" id="isd-search" class="isd-filter-input" placeholder="Item code or name…">
                        </div>
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Warehouse</label>
                            <select id="isd-warehouse" class="isd-filter-select">
                                <option value="__ALL__">All Warehouses</option>
                            </select>
                        </div>
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Only Available</label>
                            <label class="isd-toggle">
                                <input type="checkbox" id="isd-only-available">
                                <span class="isd-toggle-slider"></span>
                            </label>
                        </div>
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Low Stock Only</label>
                            <label class="isd-toggle">
                                <input type="checkbox" id="isd-low-stock-only">
                                <span class="isd-toggle-slider"></span>
                            </label>
                        </div>
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Has Sales Activity</label>
                            <label class="isd-toggle">
                                <input type="checkbox" id="isd-has-sales">
                                <span class="isd-toggle-slider"></span>
                            </label>
                        </div>
                        <div class="isd-filter-group" style="justify-content:flex-end;margin-left:auto">
                            <button class="isd-btn-reset" id="isd-reset-btn" type="button">Reset Filters</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Table -->
            <div class="isd-card">
                <div class="isd-table-wrap" id="isd-table-wrap">
                    <div class="isd-empty">
                        <div class="isd-empty-icon">📦</div>
                        Select an item group from the sidebar to view stock
                    </div>
                </div>
            </div>

        </div><!-- /isd-main -->
    </div><!-- /isd-body -->
</div><!-- /isd-wrap -->
    `);

    // ── state ──
    const S = {
        group: null,
        items: [],
        salesData: {},
        filtered: [],
        expandedRows: new Set(),
        filters: { search:'', warehouse:'__ALL__', onlyAvailable:false, lowStockOnly:false, hasSales:false },
    };

    const LOW = 5;
    const GROUP_WH = { 'Fresh Frozen': 'Hemet TSBC - TSBC' };

    // ── helpers ──
    function esc(s) {
        if (s === null || s === undefined) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
    }
    function num(v) { const n = parseFloat(v || 0); return isNaN(n) ? 0 : n; }
    function avail(item) { return num(item.actual_qty) - num(item.reserved_qty); }
    function debounce(fn, ms) {
        let t; return function() { clearTimeout(t); t = setTimeout(() => fn.apply(this, arguments), ms); };
    }
    function isFreshFrozen() { return S.group === 'Fresh Frozen'; }

    function statusBadge(a) {
        if (a <= 0) return '<span class="badge-out">Out of Stock</span>';
        if (a <= LOW) return '<span class="badge-low">Low Stock</span>';
        return '<span class="badge-available">In Stock</span>';
    }

    function rowClass(a) {
        if (a <= 0) return 'row-danger';
        if (a <= LOW) return 'row-warning';
        return '';
    }

    function cleanName(name, group) {
        if (!name) return '—';
        let n = String(name);
        if (group) n = n.replace(new RegExp('\\s*[-]\\s*' + group.replace(/[.*+?^${}()|[\]\\]/g,'\\$&') + '$','i'), '');
        n = n.replace(/_CDC$/i,'').replace(/_[A-Za-z0-9]$/i,'').replace(/_/g,' ').trim();
        return n || String(name);
    }

    function typeLabel(item) {
        const g = String(item.item_group || '');
        if (g === 'Fresh Frozen - BHO') return 'BHO';
        if (g === 'Fresh Frozen - SHO') return 'SHO';
        return '';
    }

    function fmtCurrency(v) {
        return '$' + parseFloat(v || 0).toLocaleString('en-US', { minimumFractionDigits:2, maximumFractionDigits:2 });
    }

    // ── group loading ──
    function loadGroups() {
        frappe.call({
            method: 'cannabis_management.cannabis_management.page.inventory_sales_dashboard.inventory_sales_dashboard.get_item_groups',
            callback: function(r) {
                if (r && r.message && r.message.length) {
                    renderGroups(sortGroups(filterSubgroups(r.message)));
                } else {
                    document.getElementById('isd-group-list').innerHTML = '<div class="isd-empty" style="padding:20px">No groups found</div>';
                }
            },
            error: function() {
                document.getElementById('isd-group-list').innerHTML = '<div class="isd-empty" style="padding:20px">Could not load groups</div>';
            }
        });
    }

    const GROUP_ORDER = ['Fresh Frozen','Primes','Subprimes','VRR','O2 Vape','1g O2 Vapes','LIQUID LIVE RESIN','Full Spec','Food Grade','Gummies','Farm Supplies','Drawings'];

    function filterSubgroups(groups) {
        return groups.filter(g => g.name !== 'Fresh Frozen - BHO' && g.name !== 'Fresh Frozen - SHO');
    }

    function sortGroups(groups) {
        return groups.sort((a, b) => {
            const ia = GROUP_ORDER.findIndex(x => x.toLowerCase() === a.name.toLowerCase());
            const ib = GROUP_ORDER.findIndex(x => x.toLowerCase() === b.name.toLowerCase());
            if (ia !== -1 && ib !== -1) return ia - ib;
            if (ia !== -1) return -1;
            if (ib !== -1) return 1;
            return a.name.localeCompare(b.name);
        });
    }

    function renderGroups(groups) {
        let html = '';
        groups.forEach(g => {
            html += `<div class="isd-group-btn" data-group="${esc(g.name)}">
                <span>${esc(g.name)}</span>
                <span class="isd-group-count">${g.item_count || ''}</span>
            </div>`;
        });
        const el = document.getElementById('isd-group-list');
        el.innerHTML = html;
        el.querySelectorAll('.isd-group-btn').forEach(btn => {
            btn.addEventListener('click', function() { loadStock(this.dataset.group); });
        });
    }

    // ── stock loading ──
    function loadStock(group) {
        S.group = group;
        S.items = [];
        S.salesData = {};
        S.filtered = [];
        S.expandedRows = new Set();

        document.getElementById('isd-selected-group').innerHTML = `
            <svg width="18" height="18" fill="none" stroke="#2563EB" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24" style="flex-shrink:0"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
            ${esc(group)}
        `;
        document.getElementById('isd-table-wrap').innerHTML = `
            <div class="isd-loading">
                <div class="isd-spinner"></div>
                <div class="isd-loading-text">Loading stock and sales data…</div>
            </div>`;
        setSummary([], {});

        document.querySelectorAll('.isd-group-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.group === group);
        });

        frappe.call({
            method: 'cannabis_management.cannabis_management.page.inventory_sales_dashboard.inventory_sales_dashboard.get_stock_with_sales',
            args: { item_group: group },
            callback: function(r) {
                if (r && r.message) {
                    S.items = r.message.items || [];
                    S.salesData = r.message.sales_data || {};
                } else {
                    S.items = [];
                    S.salesData = {};
                }
                resetFilters();
                applyFilters();
            },
            error: function() {
                document.getElementById('isd-table-wrap').innerHTML = `
                    <div class="isd-empty">
                        <div class="isd-empty-icon">⚠️</div>
                        Could not load data. Please try again.
                    </div>`;
            }
        });
    }

    // ── filters ──
    function resetFilters() {
        S.filters = { search:'', warehouse:'__ALL__', onlyAvailable:false, lowStockOnly:false, hasSales:false };
        document.getElementById('isd-search').value = '';
        document.getElementById('isd-only-available').checked = false;
        document.getElementById('isd-low-stock-only').checked = false;
        document.getElementById('isd-has-sales').checked = false;
    }

    function applyFilters() {
        if (!S.items.length) {
            S.filtered = [];
            setSummary([], {});
            populateWh([]);
            document.getElementById('isd-table-wrap').innerHTML = `
                <div class="isd-empty">
                    <div class="isd-empty-icon">🔍</div>
                    No items found for this group
                </div>`;
            return;
        }

        const warehouses = [...new Set(S.items.map(i => i.warehouse).filter(Boolean))].sort();
        populateWh(warehouses);

        S.filtered = S.items.filter(item => {
            const a = avail(item);
            const name = cleanName(item.item_name, item.item_group || S.group).toLowerCase();
            const code = (item.item_code || '').toLowerCase();
            const q = S.filters.search;
            if (S.filters.warehouse !== '__ALL__' && item.warehouse !== S.filters.warehouse) return false;
            if (q && !code.includes(q) && !name.includes(q)) return false;
            if (S.filters.onlyAvailable && a <= 0) return false;
            if (S.filters.lowStockOnly && !(a > 0 && a <= LOW)) return false;
            if (S.filters.hasSales && !S.salesData[item.item_code]) return false;
            return true;
        });

        setSummary(S.filtered, S.salesData);
        renderTable(S.filtered);
    }

    function populateWh(warehouses) {
        let html = '<option value="__ALL__">All Warehouses</option>';
        warehouses.forEach(w => html += `<option value="${esc(w)}">${esc(w)}</option>`);
        const el = document.getElementById('isd-warehouse');
        el.innerHTML = html;
        el.value = warehouses.includes(S.filters.warehouse) ? S.filters.warehouse : '__ALL__';
    }

    // ── summary ──
    function setSummary(items) {
        let totalQty = 0, totalAvail = 0, low = 0;
        items.forEach(i => {
            const a = avail(i);
            totalQty += num(i.actual_qty);
            totalAvail += a;
            if (a > 0 && a <= LOW) low++;
        });
        document.getElementById('isd-total-items').textContent = items.length;
        document.getElementById('isd-total-qty').textContent   = totalQty.toFixed(2);
        document.getElementById('isd-avail-qty').textContent   = totalAvail.toFixed(2);
        document.getElementById('isd-low-stock').textContent   = low;
    }

    // ── table ──
    function renderTable(items) {
        if (!items.length) {
            document.getElementById('isd-table-wrap').innerHTML = `
                <div class="isd-empty">
                    <div class="isd-empty-icon">🔍</div>
                    No items match the current filters
                </div>`;
            return;
        }

        const ff = isFreshFrozen();
        const colspan = ff ? 9 : 8;

        let html = `<table class="isd-table"><thead><tr>
            <th style="width:42px"></th>
            <th>Item Code</th>
            <th>Item Name</th>
            ${ff ? '<th>Type</th>' : ''}
            <th>Warehouse</th>
            <th style="text-align:right">Qty</th>
            <th style="text-align:right">Reserved</th>
            <th style="text-align:right">Available</th>
            <th>Status</th>
        </tr></thead><tbody>`;

        items.forEach((item, idx) => {
            const a = avail(item);
            const rc = rowClass(a);
            const tl = typeLabel(item);
            const codeJson = JSON.stringify(String(item.item_code || ''));
            const arrowCls = expandArrowClass(S.salesData[item.item_code]);

            html += `
            <tr class="${rc}" data-idx="${idx}">
                <td class="isd-expand-td ${arrowCls}" data-idx="${idx}" title="View Delivery Notes &amp; Invoices">
                    <span class="isd-expand-arrow">&#9654;</span>
                </td>
                <td>
                    <div class="isd-code-cell">
                        <span class="isd-code-text">${esc(item.item_code || '')}</span>
                        <button class="isd-copy-btn" onclick='isdCopy(${codeJson})'>Copy</button>
                    </div>
                </td>
                <td class="isd-item-name">${esc(cleanName(item.item_name, item.item_group || S.group))}</td>
                ${ff ? `<td>${tl ? `<span class="badge-type-${tl.toLowerCase()}">${esc(tl)}</span>` : ''}</td>` : ''}
                <td>${item.warehouse ? `<span class="isd-wh-text">${esc(item.warehouse)}</span>` : '<span class="isd-wh-none">— No Stock —</span>'}</td>
                <td style="text-align:right"><span class="isd-num">${num(item.actual_qty).toFixed(2)}</span></td>
                <td style="text-align:right"><span class="isd-num">${num(item.reserved_qty).toFixed(2)}</span></td>
                <td style="text-align:right"><span class="isd-num-avail">${a.toFixed(2)}</span></td>
                <td>${statusBadge(a)}</td>
            </tr>
            <tr class="expand-row" id="expand-${idx}" style="display:none">
                <td colspan="${colspan}">
                    <div class="isd-expand-panel" id="expand-body-${idx}"></div>
                </td>
            </tr>`;
        });

        html += '</tbody></table>';
        document.getElementById('isd-table-wrap').innerHTML = html;
    }

    function expandArrowClass(entries) {
        if (!entries || !entries.length) return 'no-data';
        const needsAttention = entries.some(e =>
            e.sale_status === 'delivered_not_invoiced' ||
            e.sale_status === 'partially_invoiced' ||
            e.sale_status === 'delivered_invoiced_unlinked'
        );
        return needsAttention ? 'needs-invoice' : 'has-activity';
    }

    function toggleExpand(idx, td) {
        const expandRow = document.getElementById(`expand-${idx}`);
        const body      = document.getElementById(`expand-body-${idx}`);
        if (!expandRow || (td && td.classList.contains('no-data'))) return;

        if (S.expandedRows.has(idx)) {
            S.expandedRows.delete(idx);
            expandRow.style.display = 'none';
            if (td) td.classList.remove('expanded');
        } else {
            S.expandedRows.add(idx);
            expandRow.style.display = '';
            if (td) td.classList.add('expanded');
            body.innerHTML = buildExpandPanel(S.filtered[idx]);
        }
    }

    // ── expand panel builders ──
    function buildExpandPanel(item) {
        const entries = S.salesData[item.item_code];
        if (!entries || !entries.length) {
            return `<div class="isd-no-activity-msg">No delivery notes or sales invoices found for <strong>${esc(item.item_code)}</strong>.</div>`;
        }

        let html = `<div class="isd-expand-heading">Sales &amp; Delivery history for ${esc(item.item_code)}</div>`;

        entries.forEach(entry => {
            const { hdrCls, badgeCls } = statusStyles(entry.sale_status);
            html += `
            <div class="isd-customer-block">
                <div class="isd-customer-header ${hdrCls}">
                    <span class="isd-customer-name">
                        <span class="isd-cust-icon">🏢</span>
                        ${esc(entry.customer)}
                    </span>
                    <span class="isd-sale-status-badge ${badgeCls}">${saleStatusLabel(entry.sale_status)}</span>
                </div>
                <div class="isd-customer-body">
                    ${buildAlertMsg(entry)}
                    ${buildDNSection(entry.delivery_notes)}
                    ${buildDirectSection(entry.direct_invoices)}
                </div>
            </div>`;
        });

        return html;
    }

    function buildDNSection(dns) {
        if (!dns || !dns.length) return '';
        let html = '<div class="isd-section-title">Delivery Notes</div>';
        dns.forEach(dn => {
            html += `
            <div class="isd-dn-card">
                <div class="isd-dn-top">
                    <a class="isd-doc-link" href="/app/delivery-note/${esc(dn.name)}" target="_blank">${esc(dn.name)}</a>
                    <span class="isd-pill isd-pill-blue">📅 ${esc(dn.date)}</span>
                    <span class="isd-pill isd-pill-gray">Qty: ${num(dn.qty).toFixed(2)} ${esc(dn.uom)}</span>
                    <span class="isd-pill ${dn.dn_status === 'Delivered' ? 'isd-pill-green' : 'isd-pill-orange'}">${esc(dn.dn_status)}</span>
                </div>
                ${buildLinkedInvoices(dn.invoices, dn.name)}
            </div>`;
        });
        return html;
    }

    function buildLinkedInvoices(invoices, dnName) {
        if (!invoices || !invoices.length) {
            return `<div class="isd-no-invoice-msg">
                <span>⚠️</span>
                <span>Product delivered (<strong>${esc(dnName)}</strong>) — no Sales Invoice has been generated yet for this customer.</span>
            </div>`;
        }
        let html = `<div class="isd-si-list">
            <div class="isd-si-list-title">Linked Sales Invoices</div>`;
        invoices.forEach(inv => {
            const paid = inv.outstanding <= 0;
            html += `
            <div class="isd-si-row">
                <a class="isd-si-link" href="/app/sales-invoice/${esc(inv.name)}" target="_blank">${esc(inv.name)}</a>
                <span class="isd-pill isd-pill-blue">📅 ${esc(inv.date)}</span>
                <span class="isd-si-amount">Total: ${fmtCurrency(inv.total)}</span>
                <span class="${paid ? 'isd-outstanding-ok' : 'isd-outstanding-due'}">
                    ${paid ? '✓ Paid' : `Outstanding: ${fmtCurrency(inv.outstanding)}`}
                </span>
                <span class="isd-pill ${paid ? 'isd-pill-green' : 'isd-pill-orange'}">${esc(inv.status)}</span>
            </div>`;
        });
        html += '</div>';
        return html;
    }

    function buildDirectSection(invoices) {
        if (!invoices || !invoices.length) return '';
        let html = `<div class="isd-direct-section">
            <div class="isd-section-title">Direct Sales Invoices <span style="font-size:10px;color:#94A3B8;font-weight:normal;text-transform:none;letter-spacing:0">(no delivery note)</span></div>`;
        invoices.forEach(inv => {
            const paid = inv.outstanding <= 0;
            html += `
            <div class="isd-si-row">
                <a class="isd-si-link" href="/app/sales-invoice/${esc(inv.name)}" target="_blank">${esc(inv.name)}</a>
                <span class="isd-pill isd-pill-blue">📅 ${esc(inv.date)}</span>
                <span class="isd-si-amount">Total: ${fmtCurrency(inv.total)}</span>
                <span class="${paid ? 'isd-outstanding-ok' : 'isd-outstanding-due'}">
                    ${paid ? '✓ Paid' : `Outstanding: ${fmtCurrency(inv.outstanding)}`}
                </span>
                <span class="isd-pill ${paid ? 'isd-pill-green' : 'isd-pill-orange'}">${esc(inv.status)}</span>
            </div>`;
        });
        html += '</div>';
        return html;
    }

    function buildAlertMsg(entry) {
        const dnCount  = (entry.delivery_notes || []).length;
        const invCount = (entry.delivery_notes || []).reduce((s, d) => s + (d.invoices || []).length, 0);
        const dCount   = (entry.direct_invoices || []).length;
        const map = {
            fully_invoiced: [
                'isd-alert-ok', '✅',
                `All ${dnCount} delivery note${dnCount!==1?'s':''} have been invoiced. Product delivered and fully billed.`
            ],
            partially_invoiced: [
                'isd-alert-warn', '⚠️',
                `${dnCount} delivery note${dnCount!==1?'s':''} on record — only ${invCount} ${invCount!==1?'are':'is'} linked to an invoice. Some deliveries are not yet billed.`
            ],
            delivered_not_invoiced: [
                'isd-alert-warn', '⚠️',
                `Product has been delivered (${dnCount} DN${dnCount!==1?'s':''}) but no Sales Invoice has been generated for this customer. Action required.`
            ],
            delivered_invoiced_unlinked: [
                'isd-alert-warn', '🔗',
                `A Delivery Note and ${dCount} Sales Invoice${dCount!==1?'s':''} both exist for this customer, but the invoice${dCount!==1?'s were':' was'} created separately and ${dCount!==1?'are':'is'} not linked to the Delivery Note. Please verify this is correct or link them in ERPNext.`
            ],
            invoiced_direct: [
                'isd-alert-info', 'ℹ️',
                'Customer was invoiced directly — no Delivery Note was recorded for this transaction.'
            ],
            no_activity: ['', '', ''],
        };
        const [cls, icon, msg] = map[entry.sale_status] || ['','',''];
        if (!msg) return '';
        return `<div class="isd-alert-msg ${cls}"><span class="isd-alert-icon">${icon}</span><span>${msg}</span></div>`;
    }

    function saleStatusLabel(s) {
        return {
            fully_invoiced:              'Delivered & Invoiced',
            partially_invoiced:          'Partially Invoiced',
            delivered_not_invoiced:      'Invoice Pending',
            delivered_invoiced_unlinked: 'Invoice Not Linked',
            invoiced_direct:             'Invoiced (No DN)',
            no_activity:                 'No Activity',
        }[s] || s;
    }

    function statusStyles(s) {
        const m = {
            fully_invoiced:              { hdrCls:'isd-ch-fully',    badgeCls:'isd-sb-fully'    },
            partially_invoiced:          { hdrCls:'isd-ch-partial',  badgeCls:'isd-sb-partial'  },
            delivered_not_invoiced:      { hdrCls:'isd-ch-notinv',   badgeCls:'isd-sb-notinv'   },
            delivered_invoiced_unlinked: { hdrCls:'isd-ch-unlinked', badgeCls:'isd-sb-unlinked' },
            invoiced_direct:             { hdrCls:'isd-ch-direct',   badgeCls:'isd-sb-direct'   },
            no_activity:                 { hdrCls:'isd-ch-none',     badgeCls:'isd-sb-none'     },
        };
        return m[s] || m.no_activity;
    }

    // ── events ──
    document.getElementById('isd-table-wrap').addEventListener('click', function(e) {
        const td = e.target.closest('.isd-expand-td');
        if (td) toggleExpand(parseInt(td.dataset.idx), td);
    });

    const searchEl = document.getElementById('isd-search');
    const whEl     = document.getElementById('isd-warehouse');
    const availEl  = document.getElementById('isd-only-available');
    const lowEl    = document.getElementById('isd-low-stock-only');
    const salesEl  = document.getElementById('isd-has-sales');
    const resetBtn = document.getElementById('isd-reset-btn');
    const exportBtn= document.getElementById('isd-export-btn');

    searchEl.addEventListener('input',  debounce(function() { S.filters.search = this.value.trim().toLowerCase(); applyFilters(); }, 200));
    whEl.addEventListener('change',     function() { S.filters.warehouse     = this.value;   applyFilters(); });
    availEl.addEventListener('change',  function() { S.filters.onlyAvailable = this.checked; applyFilters(); });
    lowEl.addEventListener('change',    function() { S.filters.lowStockOnly  = this.checked; applyFilters(); });
    salesEl.addEventListener('change',  function() { S.filters.hasSales      = this.checked; applyFilters(); });
    resetBtn.addEventListener('click',  function() { resetFilters(); applyFilters(); });
    exportBtn.addEventListener('click', exportCSV);

    document.getElementById('isd-sidebar-toggle').addEventListener('click', function() {
        const gl = document.getElementById('isd-group-list');
        gl.style.display = gl.style.display === 'none' ? '' : 'none';
    });

    // ── CSV export ──
    function exportCSV() {
        if (!S.filtered.length) { frappe.show_alert({ message:'No rows to export', indicator:'orange' }); return; }
        const ff = isFreshFrozen();
        const rows = [['Item Code','Item Name',...(ff?['Type']:[]),'Warehouse','Qty','Reserved','Available','Status','Sale Status','Customers']];
        S.filtered.forEach(item => {
            const a = avail(item);
            const entries = S.salesData[item.item_code] || [];
            rows.push([
                item.item_code || '',
                cleanName(item.item_name, item.item_group || S.group),
                ...(ff ? [typeLabel(item)] : []),
                item.warehouse || '',
                num(item.actual_qty).toFixed(2),
                num(item.reserved_qty).toFixed(2),
                a.toFixed(2),
                a<=0 ? 'Out of Stock' : a<=LOW ? 'Low Stock' : 'Available',
                entries.map(e => saleStatusLabel(e.sale_status)).join('; ') || 'No Activity',
                entries.map(e => e.customer).join('; '),
            ]);
        });
        const csv  = rows.map(r => r.map(v => '"'+String(v).replace(/"/g,'""')+'"').join(',')).join('\n');
        const blob = new Blob([csv], { type:'text/csv;charset=utf-8;' });
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href = url;
        a.download = (S.group||'inventory').replace(/\s+/g,'_') + '_sales.csv';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
        frappe.show_alert({ message:'CSV exported', indicator:'green' });
    }

    // ── init ──
    loadGroups();

    window.isdCopy = function(text) {
        if (!text) return;
        (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
            .then(() => frappe.show_alert({ message:'Copied: '+text, indicator:'green' }))
            .catch(() => {
                const t = document.createElement('input');
                t.value = text; document.body.appendChild(t); t.select();
                try { document.execCommand('copy'); frappe.show_alert({ message:'Copied: '+text, indicator:'green' }); } catch(e){}
                document.body.removeChild(t);
            });
    };
};
