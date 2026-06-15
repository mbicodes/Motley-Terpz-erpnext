import frappe

BLOCK_NAME = "Sales Dashboard"

HTML = """\
<div class="sd-dash">

  <!-- HEADER -->
  <div class="sd-header">
    <div class="sd-header-left">
      <div class="sd-label">Motley Terpz</div>
      <h1>Sales Dashboard</h1>
      <p class="sd-subtitle">Targets vs actuals — <span class="sd-greeting"></span></p>
    </div>
    <div class="sd-header-right">
      <div class="sd-territory-wrap">
        <label class="sd-territory-label">Territory</label>
        <select id="sd-territory" class="sd-territory-select">
          <option value="">Select territory…</option>
        </select>
      </div>
      <button class="sd-refresh-btn" onclick="window.salesDash && window.salesDash.reload()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
        Refresh
      </button>
    </div>
  </div>

  <!-- PERIOD TOGGLE -->
  <div class="sd-period-bar">
    <div class="sd-period-toggle">
      <button class="sd-period-btn" data-period="daily">Today</button>
      <button class="sd-period-btn active" data-period="weekly">This Week</button>
      <button class="sd-period-btn" data-period="monthly">This Month</button>
    </div>
    <div class="sd-period-label" id="sd-period-label">This Week</div>
  </div>

  <!-- KPI SUMMARY -->
  <div class="sd-section-title">
    <span class="sd-section-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg></span>
    At a Glance
  </div>
  <div class="sd-kpi-grid">
    <div class="sd-kpi-card" style="--kc:var(--sd-violet)">
      <div class="sd-kpi-accent"></div>
      <div class="sd-kpi-label" id="sd-target-label">Pro-rated Target</div>
      <div class="sd-kpi-value" id="sd-kpi-target"><span class="sd-loader"></span></div>
      <div class="sd-kpi-sub" id="sd-kpi-target-sub">loading…</div>
    </div>
    <div class="sd-kpi-card" style="--kc:var(--sd-emerald)">
      <div class="sd-kpi-accent"></div>
      <div class="sd-kpi-label">Actual Revenue</div>
      <div class="sd-kpi-value" id="sd-kpi-actual"><span class="sd-loader"></span></div>
      <div class="sd-kpi-sub" id="sd-kpi-actual-sub">loading…</div>
    </div>
    <div class="sd-kpi-card" id="sd-variance-card" style="--kc:var(--sd-emerald)">
      <div class="sd-kpi-accent"></div>
      <div class="sd-kpi-label">Variance</div>
      <div class="sd-kpi-value" id="sd-kpi-variance"><span class="sd-loader"></span></div>
      <div class="sd-kpi-sub" id="sd-kpi-variance-sub">vs pro-rated target</div>
    </div>
    <div class="sd-kpi-card" style="--kc:var(--sd-amber)">
      <div class="sd-kpi-accent"></div>
      <div class="sd-kpi-label">Draft Invoices</div>
      <div class="sd-kpi-value" id="sd-kpi-pending"><span class="sd-loader"></span></div>
      <div class="sd-kpi-sub">open drafts · target: 0</div>
    </div>
  </div>

  <!-- PRODUCT LINE PERFORMANCE -->
  <div class="sd-section-title">
    <span class="sd-section-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg></span>
    Product Line Performance
  </div>
  <div id="sd-product-grid" class="sd-product-grid">
    <div class="sd-loading"><div class="sd-spinner"></div></div>
  </div>

  <!-- INVENTORY -->
  <div class="sd-section-title" style="margin-top:32px">
    <span class="sd-section-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg></span>
    Inventory — Stock on Hand (Cost Valuation)
  </div>
  <div id="sd-inventory-grid" class="sd-inv-grid">
    <div class="sd-loading"><div class="sd-spinner"></div></div>
  </div>

  <div class="sd-section-divider"></div>

  <!-- RECENT INVOICES TABLE -->
  <div class="sd-section-title">
    <span class="sd-section-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></span>
    <span id="sd-inv-table-label">Sales Invoices — This Week</span>
  </div>
  <div class="sd-table-card">
    <div class="sd-table-toolbar">
      <div class="sd-table-title">Invoice Summary</div>
      <span class="sd-badge" id="sd-inv-count">loading…</span>
    </div>
    <div id="sd-inv-table"><div class="sd-loading"><div class="sd-spinner"></div></div></div>
  </div>

</div>
"""

SCRIPT = """\
(function () {
    var rootEl = root_element;
    var API = 'cannabis_management.api.jamie.';
    var currentPeriod = 'weekly';
    var tablePages = {};

    // Greeting
    var hour = new Date().getHours();
    var ge = rootEl.querySelector('.sd-greeting');
    if (ge) ge.textContent = hour < 12 ? 'good morning' : hour < 17 ? 'good afternoon' : 'good evening';

    window.salesDash = { reload: function () { loadAll(currentPeriod); } };

    // ── Helpers ──────────────────────────────────────────────

    function fmtCurrency(val) {
        return '$ ' + parseFloat(val || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    function fmtQty(val) {
        return parseFloat(val || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    function fmtPct(val) {
        var v = parseFloat(val || 0);
        return (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
    }
    function shimmerKpi(id) {
        var el = rootEl.querySelector('#' + id);
        if (el) { el.classList.remove('loaded', 'error'); el.innerHTML = '<span class="sd-loader"></span>'; }
    }
    function shimmerEl(id) {
        var el = rootEl.querySelector('#' + id);
        if (el) el.innerHTML = '<div class="sd-loading"><div class="sd-spinner"></div></div>';
    }
    function setPeriodUI(period) {
        var labels = { daily: 'Today', weekly: 'This Week', monthly: 'This Month' };
        rootEl.querySelectorAll('.sd-period-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.period === period);
        });
        var lbl = rootEl.querySelector('#sd-period-label');
        if (lbl) lbl.textContent = labels[period] || period;
        var tl = rootEl.querySelector('#sd-inv-table-label');
        if (tl) tl.textContent = 'Sales Invoices — ' + (labels[period] || period);
        var kl = rootEl.querySelector('#sd-target-label');
        if (kl) kl.textContent = 'Pro-rated Target · ' + (labels[period] || period);
    }

    // ── Table renderer ────────────────────────────────────────

    function renderTable(containerId, columns, rows, emptyMsg) {
        var el = rootEl.querySelector('#' + containerId);
        if (!el) return;
        if (!rows || !rows.length) {
            el.innerHTML = '<p class="sd-empty">' + (emptyMsg || 'No data.') + '</p>';
            return;
        }
        var PAGE_SIZE = 12;
        tablePages[containerId] = 0;
        function render(page) {
            var total = Math.ceil(rows.length / PAGE_SIZE);
            page = Math.max(0, Math.min(page, total - 1));
            tablePages[containerId] = page;
            var start = page * PAGE_SIZE;
            var pageRows = rows.slice(start, start + PAGE_SIZE);
            var html = '<table class="sd-data-table"><thead><tr>';
            columns.forEach(function (c) { html += '<th>' + c.label + '</th>'; });
            html += '</tr></thead><tbody>';
            pageRows.forEach(function (row) {
                html += '<tr>';
                columns.forEach(function (c) {
                    var val = c.format ? c.format(row[c.key], row) : (row[c.key] != null ? row[c.key] : '—');
                    html += '<td>' + val + '</td>';
                });
                html += '</tr>';
            });
            html += '</tbody></table>';
            if (total > 1) {
                var from = start + 1, to = Math.min(start + PAGE_SIZE, rows.length);
                html += '<div class="sd-pagination">'
                    + '<button class="sd-page-btn sd-page-prev"' + (page === 0 ? ' disabled' : '') + '><svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg></button>'
                    + '<span class="sd-page-info">' + from + '–' + to + ' of ' + rows.length + '</span>'
                    + '<button class="sd-page-btn sd-page-next"' + (page >= total - 1 ? ' disabled' : '') + '><svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg></button>'
                    + '</div>';
            }
            el.innerHTML = html;
            var prev = el.querySelector('.sd-page-prev'), next = el.querySelector('.sd-page-next');
            if (prev) prev.addEventListener('click', function () { render(tablePages[containerId] - 1); });
            if (next) next.addEventListener('click', function () { render(tablePages[containerId] + 1); });
        }
        render(0);
    }

    // ── Product performance cards ─────────────────────────────

    var ACCENTS = ['#059669','#0891b2','#7c3aed','#d97706','#e11d48','#2563eb','#ea580c'];

    function renderProductGrid(products) {
        var grid = rootEl.querySelector('#sd-product-grid');
        if (!grid) return;
        if (!products || !products.length) {
            grid.innerHTML = '<p class="sd-empty">No targets configured. Select a territory above to load targets.</p>';
            return;
        }
        var html = '';
        products.forEach(function (p, i) {
            var accent     = ACCENTS[i % ACCENTS.length];
            var on         = p.on_target;
            var sc         = on ? '#059669' : '#e11d48';
            var sb         = on ? 'rgba(5,150,105,0.10)' : 'rgba(225,29,72,0.10)';
            var progress   = Math.min(Math.max(p.progress_pct || 0, 0), 100);
            html += '<div class="sd-product-card" style="--pa:' + accent + '">'
                +   '<div class="sd-product-top">'
                +     '<div class="sd-product-name">' + frappe.utils.escape_html(p.item_group || '—') + '</div>'
                +     '<span class="sd-status-badge" style="color:' + sc + ';background:' + sb + '">'
                +       (on ? '▲ On Track' : '▼ Behind')
                +     '</span>'
                +   '</div>'
                +   '<div class="sd-product-numbers">'
                +     '<div class="sd-product-stat">'
                +       '<div class="sd-product-stat-label">Actual</div>'
                +       '<div class="sd-product-stat-val" style="color:' + sc + '">' + fmtCurrency(p.actual_rev) + '</div>'
                +     '</div>'
                +     '<div class="sd-product-stat">'
                +       '<div class="sd-product-stat-label">Target</div>'
                +       '<div class="sd-product-stat-val">' + fmtCurrency(p.period_target_rev) + '</div>'
                +     '</div>'
                +   '</div>'
                +   '<div class="sd-progress-wrap">'
                +     '<div class="sd-progress-bar"><div class="sd-progress-fill" style="width:' + progress + '%;background:' + sc + '"></div></div>'
                +     '<div class="sd-progress-labels">'
                +       '<span style="color:#94a3b8;font-size:11px">' + progress.toFixed(0) + '% of target</span>'
                +       '<span style="color:' + sc + ';font-size:11px;font-weight:700">' + fmtPct(p.variance_pct) + '</span>'
                +     '</div>'
                +   '</div>'
                +   '<div class="sd-product-footer">'
                +     '<span class="sd-product-meta">Monthly: ' + fmtCurrency(p.monthly_target_rev) + '</span>'
                +     '<span class="sd-product-meta">Avg rate: ' + fmtCurrency(p.avg_rate) + '</span>'
                +   '</div>'
                + '</div>';
        });
        grid.innerHTML = html;
    }

    // ── Inventory cards ───────────────────────────────────────

    var INV_ACC = [
        {a:'#0891b2',d:'rgba(8,145,178,0.08)'},{a:'#059669',d:'rgba(5,150,105,0.08)'},
        {a:'#7c3aed',d:'rgba(124,58,237,0.08)'},{a:'#d97706',d:'rgba(217,119,6,0.08)'},
        {a:'#2563eb',d:'rgba(37,99,235,0.08)'},{a:'#e11d48',d:'rgba(225,29,72,0.08)'},
        {a:'#ea580c',d:'rgba(234,88,12,0.08)'},{a:'#0f766e',d:'rgba(15,118,110,0.08)'},
    ];

    function renderInventoryGrid(rows) {
        var grid = rootEl.querySelector('#sd-inventory-grid');
        if (!grid) return;
        if (!rows || !rows.length) {
            grid.innerHTML = '<p class="sd-empty">No inventory data.</p>';
            return;
        }
        var html = '';
        rows.forEach(function (r, i) {
            var acc = INV_ACC[i % INV_ACC.length];
            html += '<div class="sd-inv-card" style="--sa:' + acc.a + ';--sad:' + acc.d + '">'
                +   '<div class="sd-inv-ring"><div class="sd-inv-ring-inner"></div></div>'
                +   '<div class="sd-inv-qty">' + fmtQty(r.qty_on_hand) + '</div>'
                +   '<div class="sd-inv-label">' + frappe.utils.escape_html(r.item_group || '—') + '</div>'
                +   '<div class="sd-inv-value">' + fmtCurrency(r.stock_value) + ' cost</div>'
                + '</div>';
        });
        grid.innerHTML = html;
    }

    // ── Data loaders ──────────────────────────────────────────

    function loadSalesData(period, territory) {
        ['sd-kpi-target','sd-kpi-actual','sd-kpi-variance','sd-kpi-pending'].forEach(shimmerKpi);
        shimmerEl('sd-product-grid');

        frappe.call({
            method: API + 'get_sales_dashboard_data',
            args: { period: period, company: 'Motley Terpz', territory: territory || null },
            callback: function (r) {
                if (!r.message) return;
                var d = r.message;

                var kpiTarget = rootEl.querySelector('#sd-kpi-target');
                if (kpiTarget) { kpiTarget.textContent = fmtCurrency(d.total_target_rev); kpiTarget.classList.add('loaded'); }
                var kpiTargetSub = rootEl.querySelector('#sd-kpi-target-sub');
                if (kpiTargetSub) kpiTargetSub.textContent = d.products.length + ' product line' + (d.products.length !== 1 ? 's' : '') + ' · ' + (d.period_fraction * 100).toFixed(0) + '% of period elapsed';

                var kpiActual = rootEl.querySelector('#sd-kpi-actual');
                if (kpiActual) { kpiActual.textContent = fmtCurrency(d.total_actual_rev); kpiActual.classList.add('loaded'); }
                var kpiActualSub = rootEl.querySelector('#sd-kpi-actual-sub');
                if (kpiActualSub) kpiActualSub.textContent = d.from_date + ' → ' + d.to_date;

                var kpiVar = rootEl.querySelector('#sd-kpi-variance');
                if (kpiVar) {
                    kpiVar.textContent = (d.total_variance >= 0 ? '+' : '') + fmtCurrency(d.total_variance);
                    kpiVar.classList.add('loaded');
                }
                var varCard = rootEl.querySelector('#sd-variance-card');
                if (varCard) varCard.style.setProperty('--kc', d.on_target ? 'var(--sd-emerald)' : 'var(--sd-rose)');
                var kpiVarSub = rootEl.querySelector('#sd-kpi-variance-sub');
                if (kpiVarSub) kpiVarSub.textContent = (d.total_variance_pct >= 0 ? '+' : '') + (d.total_variance_pct || 0).toFixed(1) + '% vs pro-rated target';

                var kpiPend = rootEl.querySelector('#sd-kpi-pending');
                if (kpiPend) { kpiPend.textContent = d.pending_invoices || 0; kpiPend.classList.add('loaded'); }

                renderProductGrid(d.products);
            },
            error: function () {
                ['sd-kpi-target','sd-kpi-actual','sd-kpi-variance','sd-kpi-pending'].forEach(function (id) {
                    var el = rootEl.querySelector('#' + id);
                    if (el) { el.textContent = '–'; el.classList.add('error'); }
                });
            }
        });
    }

    function loadInventory() {
        var grid = rootEl.querySelector('#sd-inventory-grid');
        if (grid) grid.innerHTML = '<div class="sd-loading"><div class="sd-spinner"></div></div>';
        frappe.call({
            method: API + 'get_dashboard_inventory',
            args: { company: 'Motley Terpz' },
            callback: function (r) { renderInventoryGrid(r.message || []); },
            error: function () {
                var grid = rootEl.querySelector('#sd-inventory-grid');
                if (grid) grid.innerHTML = '<p class="sd-empty">Error loading inventory.</p>';
            }
        });
    }

    function loadInvoices(period) {
        shimmerEl('sd-inv-table');
        var apiPeriod = period === 'daily' ? 'weekly' : period;
        frappe.call({
            method: API + 'get_sales_by_period',
            args: { period: apiPeriod },
            callback: function (r) {
                if (!r.message) return;
                var rows = r.message.invoices || [];
                var badge = rootEl.querySelector('#sd-inv-count');
                if (badge) badge.textContent = rows.length + ' invoice' + (rows.length !== 1 ? 's' : '');
                renderTable('sd-inv-table', [
                    { label: 'Invoice',     key: 'name',               format: function (v) { return '<a href="/app/sales-invoice/' + v + '">' + v + '</a>'; } },
                    { label: 'Customer',    key: 'customer_name' },
                    { label: 'Date',        key: 'posting_date',       format: function (v) { return frappe.datetime.str_to_user(v); } },
                    { label: 'Total',       key: 'grand_total',        format: function (v) { return fmtCurrency(v); } },
                    { label: 'Outstanding', key: 'outstanding_amount', format: function (v) { return fmtCurrency(v); } },
                    { label: 'Status',      key: 'status' },
                ], rows, 'No invoices for this period.');
            }
        });
    }

    function loadTerritories() {
        frappe.call({
            method: API + 'get_sales_territories',
            callback: function (r) {
                var sel = rootEl.querySelector('#sd-territory');
                if (!sel || !r.message || !r.message.length) return;
                r.message.forEach(function (t) {
                    var opt = document.createElement('option');
                    opt.value = opt.textContent = t.name;
                    sel.appendChild(opt);
                });
                sel.value = r.message[0].name;
                loadAll(currentPeriod);
            }
        });
    }

    function loadAll(period) {
        setPeriodUI(period);
        var territory = (rootEl.querySelector('#sd-territory') || {}).value || '';
        loadSalesData(period, territory);
        loadInventory();
        loadInvoices(period);
    }

    // ── Events ────────────────────────────────────────────────

    rootEl.querySelectorAll('.sd-period-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            currentPeriod = btn.dataset.period;
            loadAll(currentPeriod);
        });
    });

    var terrSel = rootEl.querySelector('#sd-territory');
    if (terrSel) {
        terrSel.addEventListener('change', function () {
            loadSalesData(currentPeriod, terrSel.value);
        });
    }

    // ── Init ─────────────────────────────────────────────────
    setPeriodUI(currentPeriod);
    loadTerritories();
    loadInventory();

}());
"""

STYLE = """\
.sd-dash {
  --sd-border: #e2e8f0; --sd-border-hover: #cbd5e1;
  --sd-text-primary: #1e293b; --sd-text-secondary: #64748b; --sd-text-muted: #94a3b8;
  --sd-gold: #b45309;
  --sd-emerald: #059669; --sd-emerald-dim: rgba(5,150,105,0.08);
  --sd-blue: #2563eb;    --sd-blue-dim: rgba(37,99,235,0.08);
  --sd-rose: #e11d48;    --sd-rose-dim: rgba(225,29,72,0.08);
  --sd-amber: #d97706;   --sd-amber-dim: rgba(217,119,6,0.08);
  --sd-violet: #7c3aed;  --sd-violet-dim: rgba(124,58,237,0.08);
  --sd-cyan: #0891b2;    --sd-cyan-dim: rgba(8,145,178,0.08);
  --sd-orange: #ea580c;  --sd-orange-dim: rgba(234,88,12,0.08);
  --sd-radius: 12px; --sd-radius-sm: 8px;

  font-family: 'DM Sans', sans-serif;
  max-width: 1280px; margin: 0 auto; padding: 32px 24px 48px; position: relative;
}

/* Header */
.sd-dash .sd-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 20px; flex-wrap: wrap; gap: 16px;
}
.sd-dash .sd-label {
  font-size: 11px; font-weight: 600; letter-spacing: 2px;
  text-transform: uppercase; color: var(--sd-gold); margin-bottom: 8px;
  display: flex; align-items: center; gap: 8px;
}
.sd-dash .sd-label::before { content:''; display:inline-block; width:16px; height:2px; background:var(--sd-gold); border-radius:1px; }
.sd-dash h1 { font-size:28px; font-weight:700; color:var(--sd-text-primary); line-height:1.2; margin-bottom:4px; letter-spacing:-0.5px; }
.sd-dash .sd-subtitle { font-size:13px; color:var(--sd-text-secondary); margin:0; }
.sd-dash .sd-subtitle span { color:var(--sd-gold); font-weight:500; }
.sd-dash .sd-header-right { display:flex; align-items:flex-end; gap:12px; flex-wrap:wrap; }

/* Territory select */
.sd-dash .sd-territory-wrap { display:flex; flex-direction:column; gap:5px; }
.sd-dash .sd-territory-label { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.08em; color:var(--sd-text-muted); }
.sd-dash .sd-territory-select {
  padding:8px 12px; border:1.5px solid var(--sd-border); border-radius:var(--sd-radius-sm);
  font-size:12px; font-family:'DM Sans',sans-serif; color:var(--sd-text-primary);
  background:#fff; cursor:pointer; transition:border-color 0.15s; min-width:180px;
}
.sd-dash .sd-territory-select:focus { outline:none; border-color:var(--sd-gold); }

/* Refresh button */
.sd-dash .sd-refresh-btn {
  display:inline-flex; align-items:center; gap:6px;
  padding:8px 16px; border:1.5px solid var(--sd-border); border-radius:var(--sd-radius-sm);
  background:#fff; color:var(--sd-text-secondary); font-size:12px; font-weight:600;
  font-family:'DM Sans',sans-serif; cursor:pointer; transition:all 0.15s;
}
.sd-dash .sd-refresh-btn:hover { border-color:var(--sd-gold); color:var(--sd-gold); }
.sd-dash .sd-refresh-btn svg { width:14px; height:14px; stroke:currentColor; fill:none; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }

/* Period toggle */
.sd-dash .sd-period-bar {
  display:flex; align-items:center; justify-content:space-between;
  flex-wrap:wrap; gap:10px; margin-bottom:28px; padding:10px 16px;
  background:#f8fafc; border:1px solid var(--sd-border); border-radius:var(--sd-radius);
}
.sd-dash .sd-period-toggle {
  display:flex; gap:4px; background:#fff;
  border:1px solid var(--sd-border); border-radius:8px; padding:3px;
}
.sd-dash .sd-period-btn {
  padding:6px 20px; border:none; border-radius:6px; background:transparent;
  font-size:12px; font-weight:600; font-family:'DM Sans',sans-serif;
  color:var(--sd-text-secondary); cursor:pointer; transition:all 0.18s; white-space:nowrap;
}
.sd-dash .sd-period-btn:hover:not(.active) { background:#f1f5f9; color:var(--sd-text-primary); }
.sd-dash .sd-period-btn.active { background:#1e293b; color:#fff; box-shadow:0 1px 4px rgba(0,0,0,0.15); }
.sd-dash .sd-period-label { font-size:12px; font-weight:600; color:var(--sd-text-secondary); font-family:'DM Mono',monospace; letter-spacing:0.03em; }

/* Section labels */
.sd-dash .sd-section-title { font-size:11px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:var(--sd-text-muted); margin-bottom:16px; display:flex; align-items:center; gap:6px; }
.sd-dash .sd-section-icon { display:inline-flex; align-items:center; color:var(--sd-text-muted); opacity:0.7; }
.sd-dash .sd-section-divider { height:1px; background:var(--sd-border); margin:8px 0 28px; }

/* KPI cards */
.sd-dash .sd-kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:32px; }
.sd-dash .sd-kpi-card {
  position:relative; background:#fff; border:1px solid var(--sd-border);
  border-radius:var(--sd-radius); padding:22px 20px 18px; overflow:hidden; transition:all 0.2s;
}
.sd-dash .sd-kpi-card:hover { border-color:var(--sd-border-hover); transform:translateY(-2px); box-shadow:0 4px 16px rgba(0,0,0,0.05); }
.sd-dash .sd-kpi-accent { position:absolute; top:0; left:0; right:0; height:3px; background:var(--kc); opacity:0.85; }
.sd-dash .sd-kpi-label { font-size:11px; font-weight:600; color:var(--sd-text-muted); text-transform:uppercase; letter-spacing:0.08em; margin-bottom:10px; }
.sd-dash .sd-kpi-value { font-size:26px; font-weight:700; color:var(--kc); line-height:1; margin-bottom:6px; min-height:32px; display:flex; align-items:flex-end; }
.sd-dash .sd-kpi-value.loaded { animation:sdNumberPop 0.35s cubic-bezier(0.34,1.56,0.64,1) both; }
.sd-dash .sd-kpi-value.error { font-size:14px; font-weight:500; color:var(--sd-text-muted); }
.sd-dash .sd-kpi-sub { font-size:11px; color:var(--sd-text-muted); font-family:'DM Mono',monospace; }

/* Product performance grid */
.sd-dash .sd-product-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:16px; margin-bottom:32px; }
.sd-dash .sd-product-card {
  background:#fff; border:1px solid var(--sd-border); border-radius:var(--sd-radius);
  padding:20px; transition:all 0.2s; overflow:hidden; position:relative;
}
.sd-dash .sd-product-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:var(--pa); opacity:0.8; }
.sd-dash .sd-product-card:hover { border-color:var(--sd-border-hover); transform:translateY(-2px); box-shadow:0 4px 16px rgba(0,0,0,0.06); }
.sd-dash .sd-product-top { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; margin-bottom:16px; }
.sd-dash .sd-product-name { font-size:15px; font-weight:700; color:var(--sd-text-primary); line-height:1.3; }
.sd-dash .sd-status-badge { flex-shrink:0; font-size:10px; font-weight:700; padding:3px 8px; border-radius:20px; letter-spacing:0.05em; white-space:nowrap; }
.sd-dash .sd-product-numbers { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px; }
.sd-dash .sd-product-stat-label { font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:0.07em; color:var(--sd-text-muted); margin-bottom:3px; }
.sd-dash .sd-product-stat-val { font-size:16px; font-weight:700; color:var(--sd-text-primary); font-family:'DM Mono',monospace; }
.sd-dash .sd-progress-wrap { margin-bottom:12px; }
.sd-dash .sd-progress-bar { height:6px; background:#f1f5f9; border-radius:3px; overflow:hidden; margin-bottom:5px; }
.sd-dash .sd-progress-fill { height:100%; border-radius:3px; transition:width 0.5s cubic-bezier(0.4,0,0.2,1); }
.sd-dash .sd-progress-labels { display:flex; justify-content:space-between; align-items:center; }
.sd-dash .sd-product-footer { display:flex; justify-content:space-between; padding-top:12px; border-top:1px solid #f1f5f9; }
.sd-dash .sd-product-meta { font-size:10.5px; color:var(--sd-text-muted); font-family:'DM Mono',monospace; }

/* Inventory grid */
.sd-dash .sd-inv-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; margin-bottom:32px; }
.sd-dash .sd-inv-card {
  position:relative; background:#fff; border:1px solid var(--sd-border);
  border-radius:var(--sd-radius); padding:22px 20px 18px; overflow:hidden; transition:all 0.25s;
}
.sd-dash .sd-inv-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:var(--sa); opacity:0.8; }
.sd-dash .sd-inv-card:hover { border-color:var(--sd-border-hover); transform:translateY(-2px); box-shadow:0 4px 16px rgba(0,0,0,0.06); }
.sd-dash .sd-inv-ring { position:absolute; top:-20px; right:-20px; width:72px; height:72px; border-radius:50%; border:1.5px solid var(--sa); opacity:0.08; pointer-events:none; }
.sd-dash .sd-inv-ring-inner { position:absolute; top:10px; left:10px; width:52px; height:52px; border-radius:50%; border:1px solid var(--sa); opacity:0.3; }
.sd-dash .sd-inv-qty { font-size:36px; font-weight:700; color:var(--sa); line-height:1; margin-bottom:6px; }
.sd-dash .sd-inv-label { font-size:13px; font-weight:600; color:var(--sd-text-primary); margin-bottom:3px; line-height:1.3; }
.sd-dash .sd-inv-value { font-size:11px; color:var(--sd-text-muted); font-family:'DM Mono',monospace; }

/* Table card */
.sd-dash .sd-table-card { background:#fff; border:1px solid var(--sd-border); border-radius:var(--sd-radius); overflow:hidden; margin-bottom:8px; }
.sd-dash .sd-table-toolbar { display:flex; align-items:center; gap:12px; padding:14px 20px; border-bottom:1px solid #f1f5f9; flex-wrap:wrap; }
.sd-dash .sd-table-title { font-size:13px; font-weight:700; color:var(--sd-text-primary); flex:1; }
.sd-dash .sd-badge { font-size:11px; background:#f1f5f9; color:#64748b; border-radius:20px; padding:3px 10px; font-weight:600; white-space:nowrap; }

/* Data table */
.sd-dash .sd-data-table { width:100%; border-collapse:collapse; }
.sd-dash .sd-data-table thead th { font-size:10.5px; font-weight:700; color:var(--sd-text-muted); text-transform:uppercase; letter-spacing:0.07em; padding:10px 16px; text-align:left; background:#fafbfc; border-bottom:1px solid #f1f5f9; white-space:nowrap; }
.sd-dash .sd-data-table tbody tr { border-bottom:1px solid #f8fafc; transition:background 0.12s; }
.sd-dash .sd-data-table tbody tr:last-child { border-bottom:none; }
.sd-dash .sd-data-table tbody tr:hover { background:#fafbfc; }
.sd-dash .sd-data-table tbody td { padding:11px 16px; font-size:13px; color:var(--sd-text-secondary); white-space:nowrap; }
.sd-dash .sd-data-table a { color:var(--sd-blue); text-decoration:none; font-family:'DM Mono',monospace; font-size:12px; font-weight:500; }
.sd-dash .sd-data-table a:hover { text-decoration:underline; }

/* Pagination */
.sd-dash .sd-pagination { display:flex; align-items:center; justify-content:flex-end; gap:8px; padding:10px 16px; border-top:1px solid #f1f5f9; }
.sd-dash .sd-page-btn { display:flex; align-items:center; justify-content:center; width:30px; height:30px; border:1.5px solid var(--sd-border); border-radius:6px; background:#fff; cursor:pointer; transition:all 0.15s; padding:0; }
.sd-dash .sd-page-btn:hover:not([disabled]) { border-color:var(--sd-gold); color:var(--sd-gold); }
.sd-dash .sd-page-btn[disabled] { opacity:0.35; cursor:not-allowed; }
.sd-dash .sd-page-btn svg { width:14px; height:14px; stroke:currentColor; fill:none; stroke-width:2.5; stroke-linecap:round; stroke-linejoin:round; }
.sd-dash .sd-page-info { font-size:11px; font-weight:600; color:var(--sd-text-muted); font-family:'DM Mono',monospace; min-width:80px; text-align:center; }

/* Loading */
.sd-dash .sd-loading { text-align:center; padding:50px; }
.sd-dash .sd-spinner { display:inline-block; width:24px; height:24px; border:2px solid #e2e8f0; border-top-color:var(--sd-gold); border-radius:50%; animation:sdSpin 0.7s linear infinite; }
.sd-dash .sd-loader { display:inline-block; width:44px; height:32px; border-radius:6px; background:linear-gradient(110deg,#f1f5f9 25%,#e2e8f0 50%,#f1f5f9 75%); background-size:200% 100%; animation:sdShimmer 1.5s ease-in-out infinite; }
.sd-dash .sd-empty { color:var(--sd-text-muted); font-size:13px; padding:32px; text-align:center; margin:0; }

/* Animations */
@keyframes sdShimmer { 0% { background-position:200% 0; } 100% { background-position:-200% 0; } }
@keyframes sdSpin { to { transform:rotate(360deg); } }
@keyframes sdNumberPop { 0% { opacity:0; transform:scale(0.7) translateY(8px); } 100% { opacity:1; transform:scale(1) translateY(0); } }

/* Responsive */
@media (max-width:1100px) { .sd-dash .sd-kpi-grid { grid-template-columns:repeat(2,1fr); } }
@media (max-width:768px) {
  .sd-dash { padding:20px 14px 36px; }
  .sd-dash h1 { font-size:22px; }
  .sd-dash .sd-header, .sd-dash .sd-period-bar { flex-direction:column; }
  .sd-dash .sd-product-grid { grid-template-columns:1fr; }
  .sd-dash .sd-period-toggle { width:100%; }
  .sd-dash .sd-period-btn { flex:1; text-align:center; }
}
@media (max-width:640px) { .sd-dash .sd-kpi-grid { grid-template-columns:1fr; } }
"""


def execute():
    if not frappe.db.exists("Custom HTML Block", BLOCK_NAME):
        doc = frappe.new_doc("Custom HTML Block")
        doc.name = BLOCK_NAME
    else:
        doc = frappe.get_doc("Custom HTML Block", BLOCK_NAME)

    doc.html   = HTML
    doc.script = SCRIPT
    doc.style  = STYLE
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.msgprint(f"Custom HTML Block '{BLOCK_NAME}' created/updated.")
