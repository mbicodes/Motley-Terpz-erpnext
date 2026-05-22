frappe.pages['inventory-sales-dashboard'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Inventory Sales Dashboard',
        single_column: true,
    });

    page.main.html(`
<style>
/* ── layout ── */
.isd-wrap { padding: 16px; font-family: inherit; }
.isd-header { display:flex; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; gap:12px; margin-bottom:18px; }
.isd-title { font-size:22px; font-weight:700; margin:0 0 4px; }
.isd-subtitle { color:#6c757d; font-size:13px; margin:0; }
.isd-body { display:grid; grid-template-columns:240px 1fr; gap:16px; }
@media(max-width:900px){ .isd-body{ grid-template-columns:1fr; } }

/* ── sidebar ── */
.isd-sidebar { background:#fff; border:1px solid #e0e0e0; border-radius:8px; overflow:hidden; }
.isd-sidebar-header { background:#f8f9fa; padding:10px 14px; font-weight:600; font-size:13px; border-bottom:1px solid #e0e0e0; display:flex; justify-content:space-between; align-items:center; cursor:pointer; }
.isd-group-list { padding:6px 0; }
.isd-group-btn { padding:8px 14px; cursor:pointer; font-size:13px; transition:background .15s; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.isd-group-btn:hover { background:#f0f4f8; }
.isd-group-btn.active { background:#e8f0fe; color:#1a73e8; font-weight:600; }

/* ── main panel ── */
.isd-main { display:flex; flex-direction:column; gap:14px; }
.isd-group-title { font-size:18px; font-weight:700; margin:0; }
.isd-card { background:#fff; border:1px solid #e0e0e0; border-radius:8px; overflow:hidden; }
.isd-card-body { padding:14px; }

/* ── summary cards ── */
.isd-summary-row { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
@media(max-width:700px){ .isd-summary-row{ grid-template-columns:repeat(2,1fr); } }
.isd-summary-card { background:#fff; border:1px solid #e0e0e0; border-radius:8px; padding:14px; }
.isd-summary-label { font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:#6c757d; margin-bottom:4px; }
.isd-summary-value { font-size:24px; font-weight:700; }
.isd-sum-1 .isd-summary-value { color:#1a73e8; }
.isd-sum-2 .isd-summary-value { color:#34a853; }
.isd-sum-3 .isd-summary-value { color:#188038; }
.isd-sum-4 .isd-summary-value { color:#e37400; }

/* ── filter bar ── */
.isd-filter-bar { display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; }
.isd-filter-group { display:flex; flex-direction:column; gap:4px; }
.isd-filter-label { font-size:11px; font-weight:600; color:#5f6368; }
.isd-filter-input { border:1px solid #dadce0; border-radius:6px; padding:6px 10px; font-size:13px; outline:none; min-width:160px; }
.isd-filter-input:focus { border-color:#1a73e8; }
.isd-filter-select { border:1px solid #dadce0; border-radius:6px; padding:6px 10px; font-size:13px; outline:none; background:#fff; }
.isd-switch-wrap { display:flex; align-items:center; gap:6px; font-size:13px; padding-top:6px; }
.isd-btn-reset { background:#f8f9fa; border:1px solid #dadce0; border-radius:6px; padding:6px 14px; font-size:13px; cursor:pointer; }
.isd-btn-reset:hover { background:#e8eaed; }
.isd-btn-export { background:#1a73e8; color:#fff; border:none; border-radius:6px; padding:6px 14px; font-size:13px; cursor:pointer; }
.isd-btn-export:hover { background:#1557b0; }

/* ── table ── */
.isd-table-wrap { overflow-x:auto; }
.isd-table { width:100%; border-collapse:collapse; font-size:13px; }
.isd-table th { background:#f8f9fa; padding:9px 10px; text-align:left; font-weight:600; font-size:12px; border-bottom:2px solid #e0e0e0; white-space:nowrap; }
.isd-table td { padding:8px 10px; border-bottom:1px solid #f0f0f0; vertical-align:middle; }
.isd-table tr.row-danger td { background:#fff5f5; }
.isd-table tr.row-warning td { background:#fffbf0; }
.isd-table tr.expand-row td { background:#f8fbff; padding:0; }

/* ── status badges ── */
.badge-available { background:#e6f4ea; color:#137333; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }
.badge-low { background:#fef7e0; color:#b06000; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }
.badge-out { background:#fce8e6; color:#c5221f; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }
.badge-type-bho { background:#e8f0fe; color:#1a73e8; padding:2px 7px; border-radius:10px; font-size:11px; }
.badge-type-sho { background:#fce8e6; color:#c5221f; padding:2px 7px; border-radius:10px; font-size:11px; }

/* ── sales column ── */
.isd-sales-btn { background:none; border:1px solid #dadce0; border-radius:6px; padding:3px 10px; font-size:12px; cursor:pointer; white-space:nowrap; }
.isd-sales-btn:hover { background:#f0f4f8; }
.isd-sales-btn.has-activity { border-color:#1a73e8; color:#1a73e8; }
.isd-sales-btn.needs-invoice { border-color:#e37400; color:#e37400; }

/* ── expand panel ── */
.isd-expand-panel { padding:14px 16px; }
.isd-customer-block { border:1px solid #e0e0e0; border-radius:8px; margin-bottom:10px; overflow:hidden; }
.isd-customer-header { background:#f8f9fa; padding:8px 14px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:6px; }
.isd-customer-name { font-weight:600; font-size:13px; }
.isd-sale-status-badge { padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; }
.status-fully-invoiced    { background:#e6f4ea; color:#137333; }
.status-partially-invoiced{ background:#fef7e0; color:#b06000; }
.status-delivered-not-inv { background:#fce8e6; color:#c5221f; }
.status-invoiced-direct   { background:#e8f0fe; color:#1a73e8; }
.status-no-activity       { background:#f1f3f4; color:#5f6368; }

.isd-customer-body { padding:10px 14px; }
.isd-section-title { font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:#6c757d; font-weight:600; margin:8px 0 6px; }
.isd-doc-row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:5px 0; border-bottom:1px dashed #f0f0f0; font-size:12px; }
.isd-doc-row:last-child { border-bottom:none; }
.isd-doc-link { color:#1a73e8; font-weight:600; text-decoration:none; }
.isd-doc-link:hover { text-decoration:underline; }
.isd-doc-detail { color:#5f6368; }
.isd-sub-invoices { margin-left:20px; border-left:2px solid #e8f0fe; padding-left:10px; margin-top:4px; }
.isd-alert-msg { padding:6px 10px; border-radius:6px; font-size:12px; font-weight:500; margin-top:6px; }
.isd-alert-warn  { background:#fef7e0; color:#b06000; }
.isd-alert-ok    { background:#e6f4ea; color:#137333; }
.isd-alert-info  { background:#e8f0fe; color:#1a73e8; }
.isd-no-activity { color:#9aa0a6; font-size:12px; font-style:italic; }

/* ── misc ── */
.isd-loading { padding:30px; text-align:center; color:#5f6368; }
.isd-empty { padding:30px; text-align:center; color:#9aa0a6; }
.isd-copy-btn { background:none; border:1px solid #dadce0; border-radius:4px; padding:1px 7px; font-size:11px; cursor:pointer; margin-left:4px; }
.isd-copy-btn:hover { background:#e8eaed; }
.isd-actions { display:flex; gap:8px; }
</style>

<div class="isd-wrap">
    <div class="isd-header">
        <div>
            <h2 class="isd-title">Inventory Sales Dashboard</h2>
            <p class="isd-subtitle">Stock visibility with Delivery Notes and Sales Invoice status</p>
        </div>
        <div class="isd-actions">
            <button class="isd-btn-export" id="isd-export-btn" type="button">Export CSV</button>
        </div>
    </div>

    <div class="isd-body">
        <!-- Sidebar -->
        <div class="isd-sidebar">
            <div class="isd-sidebar-header" id="isd-sidebar-toggle">
                <span>Item Groups</span>
                <span id="isd-sidebar-icon">▼</span>
            </div>
            <div class="isd-group-list" id="isd-group-list">
                <div class="isd-loading">Loading...</div>
            </div>
        </div>

        <!-- Main -->
        <div class="isd-main">
            <h4 class="isd-group-title" id="isd-selected-group">Select an Item Group</h4>

            <!-- Summary -->
            <div class="isd-summary-row">
                <div class="isd-summary-card isd-sum-1">
                    <div class="isd-summary-label">Total Items</div>
                    <div class="isd-summary-value" id="isd-total-items">-</div>
                </div>
                <div class="isd-summary-card isd-sum-2">
                    <div class="isd-summary-label">Total Qty</div>
                    <div class="isd-summary-value" id="isd-total-qty">-</div>
                </div>
                <div class="isd-summary-card isd-sum-3">
                    <div class="isd-summary-label">Available Qty</div>
                    <div class="isd-summary-value" id="isd-avail-qty">-</div>
                </div>
                <div class="isd-summary-card isd-sum-4">
                    <div class="isd-summary-label">Low Stock</div>
                    <div class="isd-summary-value" id="isd-low-stock">-</div>
                </div>
            </div>

            <!-- Filters -->
            <div class="isd-card">
                <div class="isd-card-body">
                    <div class="isd-filter-bar">
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Search</label>
                            <input type="text" id="isd-search" class="isd-filter-input" placeholder="Item code or name">
                        </div>
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Warehouse</label>
                            <select id="isd-warehouse" class="isd-filter-select">
                                <option value="__ALL__">All Warehouses</option>
                            </select>
                        </div>
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Only Available</label>
                            <label class="isd-switch-wrap">
                                <input type="checkbox" id="isd-only-available">
                                <span>Yes</span>
                            </label>
                        </div>
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Low Stock Only</label>
                            <label class="isd-switch-wrap">
                                <input type="checkbox" id="isd-low-stock-only">
                                <span>Yes</span>
                            </label>
                        </div>
                        <div class="isd-filter-group">
                            <label class="isd-filter-label">Has Sales Activity</label>
                            <label class="isd-switch-wrap">
                                <input type="checkbox" id="isd-has-sales">
                                <span>Yes</span>
                            </label>
                        </div>
                        <div class="isd-filter-group" style="justify-content:flex-end;">
                            <button class="isd-btn-reset" id="isd-reset-btn" type="button">Reset</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Table -->
            <div class="isd-card">
                <div class="isd-card-body isd-table-wrap" id="isd-table-wrap">
                    <div class="isd-empty">Select an item group to view stock</div>
                </div>
            </div>
        </div>
    </div>
</div>
    `);

    // ── state ──
    const S = {
        group: null,
        items: [],
        salesData: {},
        filtered: [],
        expandedRows: new Set(),
        filters: { search: '', warehouse: '__ALL__', onlyAvailable: false, lowStockOnly: false, hasSales: false },
    };

    const LOW = 5;
    const DEFAULT_WH = "Nature's Lab - MT";
    const GROUP_WH = { 'Fresh Frozen': 'Hemet TSBC - TSBC' };

    // ── helpers ──
    function esc(s) {
        if (s === null || s === undefined) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
    }
    function num(v) { let n = parseFloat(v || 0); return isNaN(n) ? 0 : n; }
    function avail(item) { return num(item.actual_qty) - num(item.reserved_qty); }
    function debounce(fn, ms) {
        let t; return function() { clearTimeout(t); t = setTimeout(() => fn.apply(this, arguments), ms); };
    }
    function defaultWh(g) { return GROUP_WH[g] || DEFAULT_WH; }
    function isFreshFrozen() { return S.group === 'Fresh Frozen'; }

    function statusBadge(a) {
        if (a <= 0) return '<span class="badge-out">Out of Stock</span>';
        if (a <= LOW) return '<span class="badge-low">Low Stock</span>';
        return '<span class="badge-available">Available</span>';
    }

    function rowClass(a) {
        if (a <= 0) return 'row-danger';
        if (a <= LOW) return 'row-warning';
        return '';
    }

    function cleanName(name, group) {
        if (!name) return '-';
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

    // ── group loading ──
    function loadGroups() {
        frappe.call({
            method: 'cannabis_management.cannabis_management.page.inventory_sales_dashboard.inventory_sales_dashboard.get_item_groups',
            callback: function(r) {
                if (r && r.message && r.message.length) {
                    renderGroups(sortGroups(filterSubgroups(r.message)));
                } else {
                    document.getElementById('isd-group-list').innerHTML = '<div class="isd-empty">No groups found</div>';
                }
            },
            error: function() {
                document.getElementById('isd-group-list').innerHTML = '<div class="isd-empty">Could not load groups</div>';
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
            html += `<div class="isd-group-btn" data-group="${esc(g.name)}">${esc(g.name)}</div>`;
        });
        const el = document.getElementById('isd-group-list');
        el.innerHTML = html;
        el.querySelectorAll('.isd-group-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                loadStock(this.dataset.group);
            });
        });
    }

    // ── stock + sales loading ──
    function loadStock(group) {
        S.group = group;
        S.items = [];
        S.salesData = {};
        S.filtered = [];
        S.expandedRows = new Set();

        document.getElementById('isd-selected-group').textContent = group;
        document.getElementById('isd-table-wrap').innerHTML = '<div class="isd-loading">Loading stock and sales data...</div>';
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
                document.getElementById('isd-table-wrap').innerHTML = '<div class="isd-empty">Could not load data</div>';
            }
        });
    }

    // ── filters ──
    function resetFilters() {
        S.filters = {
            search: '',
            warehouse: defaultWh(S.group),
            onlyAvailable: false,
            lowStockOnly: false,
            hasSales: false,
        };
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
            document.getElementById('isd-table-wrap').innerHTML = '<div class="isd-empty">No items found for this group</div>';
            return;
        }

        const warehouses = [...new Set(S.items.map(i => i.warehouse).filter(Boolean))].sort();
        populateWh(warehouses);

        S.filtered = S.items.filter(item => {
            const a = avail(item);
            const name = cleanName(item.item_name, item.item_group || S.group).toLowerCase();
            const code = (item.item_code || '').toLowerCase();
            const search = S.filters.search;

            if (S.filters.warehouse !== '__ALL__' && item.warehouse !== S.filters.warehouse) return false;
            if (search && !code.includes(search) && !name.includes(search)) return false;
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
        if (warehouses.includes(S.filters.warehouse)) {
            el.value = S.filters.warehouse;
        } else {
            el.value = '__ALL__';
        }
    }

    // ── summary ──
    function setSummary(items, salesData) {
        let totalQty = 0, totalAvail = 0, low = 0;
        items.forEach(i => {
            const a = avail(i);
            totalQty += num(i.actual_qty);
            totalAvail += a;
            if (a > 0 && a <= LOW) low++;
        });
        document.getElementById('isd-total-items').textContent = items.length;
        document.getElementById('isd-total-qty').textContent = totalQty.toFixed(2);
        document.getElementById('isd-avail-qty').textContent = totalAvail.toFixed(2);
        document.getElementById('isd-low-stock').textContent = low;
    }

    // ── table ──
    function renderTable(items) {
        if (!items.length) {
            document.getElementById('isd-table-wrap').innerHTML = '<div class="isd-empty">No items match the filters</div>';
            return;
        }

        const ff = isFreshFrozen();
        let html = `<table class="isd-table"><thead><tr>
            <th>Item Code</th><th>Item Name</th>
            ${ff ? '<th>Type</th>' : ''}
            <th>Warehouse</th>
            <th class="text-right">Qty</th>
            <th class="text-right">Reserved</th>
            <th class="text-right">Available</th>
            <th>Status</th>
            <th>Sales</th>
        </tr></thead><tbody>`;

        items.forEach((item, idx) => {
            const a = avail(item);
            const rc = rowClass(a);
            const tl = typeLabel(item);
            const codeJson = JSON.stringify(String(item.item_code || ''));
            const salesEntries = S.salesData[item.item_code];
            const salesBtn = buildSalesBtn(item.item_code, salesEntries);

            html += `<tr class="${rc}" data-idx="${idx}">
                <td><span>${esc(item.item_code || '')}</span><button class="isd-copy-btn" onclick='isdCopy(${codeJson})'>Copy</button></td>
                <td>${esc(cleanName(item.item_name, item.item_group || S.group))}</td>
                ${ff ? `<td>${tl ? `<span class="badge-type-${tl.toLowerCase()}">${esc(tl)}</span>` : ''}</td>` : ''}
                <td>${esc(item.warehouse || '')}</td>
                <td style="text-align:right">${num(item.actual_qty).toFixed(2)}</td>
                <td style="text-align:right">${num(item.reserved_qty).toFixed(2)}</td>
                <td style="text-align:right"><strong>${a.toFixed(2)}</strong></td>
                <td>${statusBadge(a)}</td>
                <td>${salesBtn}</td>
            </tr>
            <tr class="expand-row" id="expand-${idx}" style="display:none">
                <td colspan="${ff ? 9 : 8}">
                    <div class="isd-expand-panel" id="expand-body-${idx}"></div>
                </td>
            </tr>`;
        });

        html += '</tbody></table>';
        document.getElementById('isd-table-wrap').innerHTML = html;
    }

    function buildSalesBtn(itemCode, entries) {
        if (!entries || !entries.length) {
            return `<button class="isd-sales-btn">No Sales</button>`;
        }
        const needsInvoice = entries.some(e => e.sale_status === 'delivered_not_invoiced' || e.sale_status === 'partially_invoiced');
        const cls = needsInvoice ? 'needs-invoice' : 'has-activity';
        const label = needsInvoice ? '⚠ Invoice Pending' : '✓ View Sales';
        return `<button class="isd-sales-btn ${cls}">${label}</button>`;
    }

    // The buttons already have onclick via event delegation — let me correct the approach:
    // Sales buttons get their idx from the row's data-idx attribute.

    function toggleExpand(idx) {
        const expandRow = document.getElementById(`expand-${idx}`);
        const body = document.getElementById(`expand-body-${idx}`);
        if (!expandRow) return;

        if (S.expandedRows.has(idx)) {
            S.expandedRows.delete(idx);
            expandRow.style.display = 'none';
        } else {
            S.expandedRows.add(idx);
            expandRow.style.display = '';
            const item = S.filtered[idx];
            body.innerHTML = buildExpandPanel(item);
        }
    }

    function buildExpandPanel(item) {
        const entries = S.salesData[item.item_code];

        if (!entries || !entries.length) {
            return `<div class="isd-no-activity">No delivery notes or sales invoices found for <strong>${esc(item.item_code)}</strong>.</div>`;
        }

        let html = '';

        entries.forEach(entry => {
            const statusLabel = saleStatusLabel(entry.sale_status);
            const statusClass = saleStatusClass(entry.sale_status);
            const alertHtml = buildAlertMsg(entry);

            html += `<div class="isd-customer-block">
                <div class="isd-customer-header">
                    <span class="isd-customer-name">${esc(entry.customer)}</span>
                    <span class="isd-sale-status-badge ${statusClass}">${esc(statusLabel)}</span>
                </div>
                <div class="isd-customer-body">
                    ${alertHtml}
                    ${buildDNSection(entry.delivery_notes)}
                    ${buildDirectInvoiceSection(entry.direct_invoices)}
                </div>
            </div>`;
        });

        return html;
    }

    function buildDNSection(dns) {
        if (!dns || !dns.length) return '';
        let html = '<div class="isd-section-title">Delivery Notes</div>';
        dns.forEach(dn => {
            const invoiceHtml = buildLinkedInvoices(dn.invoices);
            html += `<div class="isd-doc-row">
                <a class="isd-doc-link" href="/app/delivery-note/${esc(dn.name)}" target="_blank">${esc(dn.name)}</a>
                <span class="isd-doc-detail">Date: ${esc(dn.date)}</span>
                <span class="isd-doc-detail">Qty: ${num(dn.qty).toFixed(2)} ${esc(dn.uom)}</span>
                <span class="isd-doc-detail">Status: ${esc(dn.status)}</span>
            </div>
            ${invoiceHtml}`;
        });
        return html;
    }

    function buildLinkedInvoices(invoices) {
        if (!invoices || !invoices.length) {
            return `<div class="isd-sub-invoices"><span class="isd-alert-msg isd-alert-warn">No sales invoice generated for this delivery note</span></div>`;
        }
        let html = '<div class="isd-sub-invoices"><div class="isd-section-title" style="margin-top:0">Linked Sales Invoices</div>';
        invoices.forEach(inv => {
            const paidClass = inv.outstanding <= 0 ? 'isd-alert-ok' : '';
            html += `<div class="isd-doc-row">
                <a class="isd-doc-link" href="/app/sales-invoice/${esc(inv.name)}" target="_blank">${esc(inv.name)}</a>
                <span class="isd-doc-detail">Date: ${esc(inv.date)}</span>
                <span class="isd-doc-detail">Total: ${formatCurrency(inv.total)}</span>
                <span class="isd-doc-detail ${paidClass}">Outstanding: ${formatCurrency(inv.outstanding)}</span>
                <span class="isd-doc-detail">Status: ${esc(inv.status)}</span>
            </div>`;
        });
        html += '</div>';
        return html;
    }

    function buildDirectInvoiceSection(invoices) {
        if (!invoices || !invoices.length) return '';
        let html = '<div class="isd-section-title">Direct Sales Invoices (No Delivery Note)</div>';
        invoices.forEach(inv => {
            html += `<div class="isd-doc-row">
                <a class="isd-doc-link" href="/app/sales-invoice/${esc(inv.name)}" target="_blank">${esc(inv.name)}</a>
                <span class="isd-doc-detail">Date: ${esc(inv.date)}</span>
                <span class="isd-doc-detail">Total: ${formatCurrency(inv.total)}</span>
                <span class="isd-doc-detail">Outstanding: ${formatCurrency(inv.outstanding)}</span>
                <span class="isd-doc-detail">Status: ${esc(inv.status)}</span>
            </div>`;
        });
        return html;
    }

    function buildAlertMsg(entry) {
        const msgs = {
            'fully_invoiced':      ['isd-alert-ok',   '✓ Delivered and fully invoiced for this customer.'],
            'partially_invoiced':  ['isd-alert-warn',  '⚠ Some delivery notes have no invoice yet.'],
            'delivered_not_invoiced': ['isd-alert-warn','⚠ Item has been delivered but no sales invoice has been generated for this customer.'],
            'invoiced_direct':     ['isd-alert-info',  'ℹ Invoiced directly (no delivery note recorded).'],
            'no_activity':         ['',                ''],
        };
        const [cls, msg] = msgs[entry.sale_status] || ['', ''];
        if (!msg) return '';
        return `<div class="isd-alert-msg ${cls}">${msg}</div>`;
    }

    function saleStatusLabel(s) {
        return {
            'fully_invoiced':         'Delivered & Invoiced',
            'partially_invoiced':     'Partially Invoiced',
            'delivered_not_invoiced': 'Delivered — Invoice Pending',
            'invoiced_direct':        'Invoiced (No DN)',
            'no_activity':            'No Activity',
        }[s] || s;
    }

    function saleStatusClass(s) {
        return {
            'fully_invoiced':         'status-fully-invoiced',
            'partially_invoiced':     'status-partially-invoiced',
            'delivered_not_invoiced': 'status-delivered-not-inv',
            'invoiced_direct':        'status-invoiced-direct',
            'no_activity':            'status-no-activity',
        }[s] || '';
    }

    function formatCurrency(v) {
        const n = parseFloat(v || 0);
        return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    // ── event bindings ──

    // Sales button clicks (delegated)
    document.getElementById('isd-table-wrap').addEventListener('click', function(e) {
        const btn = e.target.closest('.isd-sales-btn');
        if (!btn) return;
        const row = btn.closest('tr[data-idx]');
        if (!row) return;
        toggleExpand(parseInt(row.dataset.idx));
    });

    const searchEl  = document.getElementById('isd-search');
    const whEl      = document.getElementById('isd-warehouse');
    const availEl   = document.getElementById('isd-only-available');
    const lowEl     = document.getElementById('isd-low-stock-only');
    const salesEl   = document.getElementById('isd-has-sales');
    const resetBtn  = document.getElementById('isd-reset-btn');
    const exportBtn = document.getElementById('isd-export-btn');

    searchEl.addEventListener('input', debounce(function() { S.filters.search = this.value.trim().toLowerCase(); applyFilters(); }, 200));
    whEl.addEventListener('change', function() { S.filters.warehouse = this.value; applyFilters(); });
    availEl.addEventListener('change', function() { S.filters.onlyAvailable = this.checked; applyFilters(); });
    lowEl.addEventListener('change', function() { S.filters.lowStockOnly = this.checked; applyFilters(); });
    salesEl.addEventListener('change', function() { S.filters.hasSales = this.checked; applyFilters(); });
    resetBtn.addEventListener('click', function() { resetFilters(); applyFilters(); });
    exportBtn.addEventListener('click', exportCSV);

    document.getElementById('isd-sidebar-toggle').addEventListener('click', function() {
        const gl = document.getElementById('isd-group-list');
        gl.style.display = gl.style.display === 'none' ? '' : 'none';
    });

    // ── CSV export ──
    function exportCSV() {
        if (!S.filtered.length) {
            frappe.show_alert({ message: 'No rows to export', indicator: 'orange' });
            return;
        }
        const ff = isFreshFrozen();
        const rows = [['Item Code','Item Name', ...(ff ? ['Type'] : []), 'Warehouse','Qty','Reserved','Available','Status','Sale Status','Customers']];
        S.filtered.forEach(item => {
            const a = avail(item);
            const entries = S.salesData[item.item_code] || [];
            const customers = entries.map(e => e.customer).join('; ');
            const saleStatuses = entries.map(e => saleStatusLabel(e.sale_status)).join('; ');
            const tl = typeLabel(item);
            rows.push([
                item.item_code || '',
                cleanName(item.item_name, item.item_group || S.group),
                ...(ff ? [tl] : []),
                item.warehouse || '',
                num(item.actual_qty).toFixed(2),
                num(item.reserved_qty).toFixed(2),
                a.toFixed(2),
                a <= 0 ? 'Out of Stock' : a <= LOW ? 'Low Stock' : 'Available',
                saleStatuses || 'No Activity',
                customers,
            ]);
        });

        const csv = rows.map(r => r.map(v => '"' + String(v).replace(/"/g,'""') + '"').join(',')).join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = (S.group || 'inventory').replace(/\s+/g,'_') + '_sales.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        frappe.show_alert({ message: 'CSV exported', indicator: 'green' });
    }

    // ── init ──
    loadGroups();

    // Expose copy helper globally for inline onclick
    window.isdCopy = function(text) {
        if (!text) return;
        (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
            .then(() => frappe.show_alert({ message: 'Copied: ' + text, indicator: 'green' }))
            .catch(() => {
                const t = document.createElement('input');
                t.value = text;
                document.body.appendChild(t);
                t.select();
                try { document.execCommand('copy'); frappe.show_alert({ message: 'Copied: ' + text, indicator: 'green' }); } catch(e) {}
                document.body.removeChild(t);
            });
    };
};
