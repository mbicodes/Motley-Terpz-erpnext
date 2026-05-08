frappe.pages['sales-target-dashboa'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Sales Target Dashboard',
        single_column: true
    });

    $(wrapper).find('.layout-main-section').html(getDashboardHTML());
    var rootEl = wrapper.querySelector('.sd-dash');

    var API = 'cannabis_management.api.jamie.';
    var currentPeriod = 'weekly';
    var currentMatrix = 'weekly';
    var currentView   = 'value';
    var matrixCache   = {};

    var hour = new Date().getHours();
    var ge = rootEl.querySelector('.sd-greeting');
    if (ge) ge.textContent = hour < 12 ? 'good morning' : hour < 17 ? 'good afternoon' : 'good evening';

    window.salesDash = { reload: function () { loadAll(currentPeriod); } };

    // ── Formatters ────────────────────────────────────────────────
    function fmtCurrency(val) {
        return '$ ' + parseFloat(val || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    function fmtQty(val) {
        return parseFloat(val || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    // ── Shimmer helpers ───────────────────────────────────────────
    function shimmerKpi(id) {
        var el = rootEl.querySelector('#' + id);
        if (el) { el.classList.remove('loaded', 'error'); el.innerHTML = '<span class="sd-loader"></span>'; }
    }
    function shimmerEl(id) {
        var el = rootEl.querySelector('#' + id);
        if (el) el.innerHTML = '<div class="sd-loading"><div class="sd-spinner"></div></div>';
    }

    // ── Period bar ────────────────────────────────────────────────
    function setPeriodUI(period) {
        var labels = { daily: 'Today', weekly: 'This Week', monthly: 'This Month', last_month: 'Last Month' };
        rootEl.querySelectorAll('.sd-period-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.period === period);
        });
        var lbl = rootEl.querySelector('#sd-period-label');
        if (lbl) lbl.textContent = labels[period] || period;
        var kl = rootEl.querySelector('#sd-target-label');
        if (kl) kl.textContent = 'Pro-rated Target · ' + (labels[period] || period);
    }

    // ── Matrix toggle ─────────────────────────────────────────────
    function setMatrixUI(mtx) {
        currentMatrix = mtx;
        rootEl.querySelectorAll('.sd-mtx-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.mtx === mtx);
        });
        var title = rootEl.querySelector('#sd-matrix-title');
        if (title) {
            var labels = { monthly: 'Monthly', weekly: 'Weekly', daily: 'Daily' };
            title.textContent = (labels[mtx] || 'Weekly') + ' Revenue Matrix';
        }
        if (matrixCache[mtx]) renderMatrix('sd-matrix', matrixCache[mtx]);
    }

    // ── Value / Qty toggle ────────────────────────────────────────
    function setViewUI(view) {
        currentView = view;
        rootEl.querySelectorAll('.sd-view-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.view === view);
        });
        if (matrixCache[currentMatrix]) renderMatrix('sd-matrix', matrixCache[currentMatrix]);
    }

    // ── Matrix renderer ───────────────────────────────────────────
    function renderMatrix(containerId, matrix) {
        var el = rootEl.querySelector('#' + containerId);
        if (!el) return;
        if (!matrix || !matrix.columns || !matrix.columns.length) {
            el.innerHTML = '<p class="sd-empty">No data for this period.</p>';
            return;
        }
        if (!matrix.products || !matrix.products.length) {
            el.innerHTML = '<p class="sd-empty">No targets configured. Set Territory › Target Detail to see this matrix.</p>';
            return;
        }

        var isQty   = currentView === 'qty';
        var cols    = matrix.columns;
        var showAvg = currentMatrix === 'weekly';
        var AVG     = 'Avg (8 Wks)';

        // Divisor for the static "Target" column header
        var targetDiv, targetLabel;
        if (currentMatrix === 'monthly') { targetDiv = 1;  targetLabel = 'Monthly Target'; }
        else if (currentMatrix === 'daily') { targetDiv = 20; targetLabel = 'Daily Target'; }
        else                              { targetDiv = 4;  targetLabel = 'Weekly Target'; }

        // Pre-compute averages over all weeks (weekly view only)
        var avgActuals = {}, avgUnits = {};
        if (showAvg) {
            matrix.products.forEach(function (p) {
                var rSum = 0, qSum = 0;
                cols.forEach(function (c) { rSum += p.actuals[c] || 0; qSum += (p.units && p.units[c]) || 0; });
                avgActuals[p.item_group] = rSum / cols.length;
                avgUnits[p.item_group]   = qSum / cols.length;
            });
        }

        function cellClass(actual, target) {
            if (!target || target <= 0) return '';
            var r = actual / target;
            if (r >= 1)   return 'sd-cell-green';
            if (r >= 0.7) return 'sd-cell-amber';
            if (actual > 0) return 'sd-cell-red';
            return '';
        }

        // ── Header ────────────────────────────────────────────────
        var html = '<table class="sd-matrix"><thead><tr>';
        html += '<th class="sd-matrix-th-product">Item Group</th>';
        html += '<th class="sd-matrix-th-static">Target Units</th>';
        html += '<th class="sd-matrix-th-static">Avg Price</th>';
        html += '<th class="sd-matrix-th-static">' + (isQty ? targetLabel.replace('Target','Target Units') : targetLabel) + '</th>';
        cols.forEach(function (c) {
            html += '<th class="sd-matrix-th-period">' + frappe.utils.escape_html(c) + '</th>';
        });
        if (showAvg) html += '<th class="sd-matrix-th-avg">' + AVG + '</th>';
        html += '</tr></thead>';

        // ── Body ──────────────────────────────────────────────────
        html += '<tbody>';
        matrix.products.forEach(function (p) {
            var rowClass = p.has_target ? '' : 'sd-matrix-row-untargeted';
            html += '<tr' + (rowClass ? ' class="' + rowClass + '"' : '') + '>';

            var sourceTag = (p.has_target && p.from_sales_invoice === false)
                ? ' <span class="sd-source-tag" title="Actuals sourced from another doctype">other source</span>'
                : '';
            html += '<td class="sd-matrix-product">'
                + frappe.utils.escape_html(p.item_group)
                + (p.has_target ? '' : ' <span class="sd-no-target-tag">no target</span>')
                + sourceTag + '</td>';
            var dispUnits = p.target_units ? p.target_units / targetDiv : 0;
            html += '<td class="sd-matrix-num">' + (dispUnits ? fmtQty(dispUnits) : '—') + '</td>';
            html += '<td class="sd-matrix-num">' + (p.avg_price ? fmtCurrency(p.avg_price) : '—') + '</td>';

            if (isQty) {
                var tgtUnits = p.target_units ? p.target_units / targetDiv : 0;
                html += '<td class="sd-matrix-num sd-matrix-target-rev">' + (tgtUnits ? fmtQty(tgtUnits) : '—') + '</td>';
            } else {
                var tgtRev = p.monthly_target ? p.monthly_target / targetDiv : 0;
                html += '<td class="sd-matrix-num sd-matrix-target-rev">' + (tgtRev ? fmtCurrency(tgtRev) : '—') + '</td>';
            }

            cols.forEach(function (col) {
                if (isQty) {
                    var aq  = (p.units && p.units[col]) || 0;
                    var tqu = p.target_units ? p.target_units / targetDiv : 0;
                    html += '<td class="sd-matrix-num ' + cellClass(aq, tqu) + '">' + (aq > 0 ? fmtQty(aq) : '—') + '</td>';
                } else {
                    var av = p.actuals[col] || 0;
                    var ct = (p.cell_targets && p.cell_targets[col]) || 0;
                    html += '<td class="sd-matrix-num ' + cellClass(av, ct) + '">' + (av > 0 ? fmtCurrency(av) : '—') + '</td>';
                }
            });

            if (showAvg) {
                var avgVal = isQty ? (avgUnits[p.item_group] || 0) : (avgActuals[p.item_group] || 0);
                html += '<td class="sd-matrix-num sd-matrix-avg">' + (avgVal > 0 ? (isQty ? fmtQty(avgVal) : fmtCurrency(avgVal)) : '—') + '</td>';
            }
            html += '</tr>';
        });
        html += '</tbody>';

        // ── Footer ────────────────────────────────────────────────
        html += '<tfoot>';

        html += '<tr><td colspan="3"></td><td class="sd-matrix-foot-label">Motley</td>';
        cols.forEach(function (c) {
            var v = (matrix.motley_totals && matrix.motley_totals[c]) || 0;
            html += '<td class="sd-matrix-num">' + (v > 0 ? fmtCurrency(v) : '—') + '</td>';
        });
        if (showAvg) html += '<td class="sd-matrix-num sd-matrix-avg">' + (matrix.avg_motley > 0 ? fmtCurrency(matrix.avg_motley) : '—') + '</td>';
        html += '</tr>';

        html += '<tr><td colspan="3"></td><td class="sd-matrix-foot-label">TSBC</td>';
        cols.forEach(function (c) {
            var v = (matrix.tsbc_totals && matrix.tsbc_totals[c]) || 0;
            html += '<td class="sd-matrix-num">' + (v > 0 ? fmtCurrency(v) : '—') + '</td>';
        });
        if (showAvg) html += '<td class="sd-matrix-num sd-matrix-avg">' + (matrix.avg_tsbc > 0 ? fmtCurrency(matrix.avg_tsbc) : '—') + '</td>';
        html += '</tr>';

        html += '<tr class="sd-matrix-foot-net"><td colspan="3"></td><td class="sd-matrix-foot-label">Net</td>';
        cols.forEach(function (c) {
            var v = matrix.target_net[c] || 0;
            html += '<td class="sd-matrix-num ' + (v >= 0 ? 'sd-pos' : 'sd-neg') + '">' + fmtCurrency(v) + '</td>';
        });
        if (showAvg) html += '<td class="sd-matrix-num sd-matrix-avg ' + (matrix.avg_net >= 0 ? 'sd-pos' : 'sd-neg') + '">' + fmtCurrency(matrix.avg_net || 0) + '</td>';
        html += '</tr>';

        html += '</tfoot></table>';
        el.innerHTML = html;
    }

    // ── Data loading ──────────────────────────────────────────────
    function loadAll(period) {
        setPeriodUI(period);
        var territory = (rootEl.querySelector('#sd-territory') || {}).value || '';

        ['sd-kpi-target','sd-kpi-actual','sd-kpi-variance','sd-kpi-pending'].forEach(shimmerKpi);
        shimmerEl('sd-matrix');

        frappe.call({
            method: API + 'get_sales_dashboard_data',
            args: { period: period, territory: territory || null },
            callback: function (r) {
                if (!r.message) return;
                var d = r.message, k;
                k = rootEl.querySelector('#sd-kpi-target');
                if (k) { k.textContent = fmtCurrency(d.total_target_rev); k.classList.add('loaded'); }
                k = rootEl.querySelector('#sd-kpi-target-sub');
                if (k) k.textContent = (d.products.length || 0) + ' product line' + (d.products.length !== 1 ? 's' : '') + ' · FY ' + (d.fiscal_year || '—');
                k = rootEl.querySelector('#sd-kpi-actual');
                if (k) { k.textContent = fmtCurrency(d.total_actual_rev); k.classList.add('loaded'); }
                k = rootEl.querySelector('#sd-kpi-actual-sub');
                if (k) k.textContent = d.from_date + ' → ' + d.to_date;
                k = rootEl.querySelector('#sd-kpi-variance');
                if (k) { k.textContent = (d.total_variance >= 0 ? '+' : '') + fmtCurrency(d.total_variance); k.classList.add('loaded'); }
                var vc = rootEl.querySelector('#sd-variance-card');
                if (vc) vc.style.setProperty('--kc', d.on_target ? 'var(--sd-emerald)' : 'var(--sd-rose)');
                k = rootEl.querySelector('#sd-kpi-variance-sub');
                if (k) k.textContent = (d.total_variance_pct >= 0 ? '+' : '') + (d.total_variance_pct || 0).toFixed(1) + '% vs pro-rated target';
                k = rootEl.querySelector('#sd-kpi-pending');
                if (k) { k.textContent = d.pending_invoices || 0; k.classList.add('loaded'); }
            }
        });

        frappe.call({
            method: API + 'get_sales_matrix',
            args: { territory: territory || null },
            callback: function (r) {
                if (!r.message) return;
                matrixCache = {
                    monthly: r.message.monthly,
                    weekly:  r.message.weekly,
                    daily:   r.message.daily,
                };
                renderMatrix('sd-matrix', matrixCache[currentMatrix]);
            },
            error: function () {
                var el = rootEl.querySelector('#sd-matrix');
                if (el) el.innerHTML = '<p class="sd-empty">Error loading data.</p>';
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

    // ── Event listeners ───────────────────────────────────────────
    rootEl.querySelectorAll('.sd-mtx-btn').forEach(function (btn) {
        btn.addEventListener('click', function () { setMatrixUI(btn.dataset.mtx); });
    });
    rootEl.querySelectorAll('.sd-view-btn').forEach(function (btn) {
        btn.addEventListener('click', function () { setViewUI(btn.dataset.view); });
    });
    rootEl.querySelectorAll('.sd-period-btn').forEach(function (btn) {
        btn.addEventListener('click', function () { currentPeriod = btn.dataset.period; loadAll(currentPeriod); });
    });
    var terrSel = rootEl.querySelector('#sd-territory');
    if (terrSel) terrSel.addEventListener('change', function () { loadAll(currentPeriod); });

    setMatrixUI(currentMatrix);
    setPeriodUI(currentPeriod);
    loadTerritories();

    page.set_primary_action('Refresh', function () { loadAll(currentPeriod); }, 'refresh');
};

function getDashboardHTML() {
    return `
    <div class="sd-dash">
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

      <div class="sd-period-bar">
        <div class="sd-period-toggle">
          <button class="sd-period-btn" data-period="daily">Today</button>
          <button class="sd-period-btn active" data-period="weekly">This Week</button>
          <button class="sd-period-btn" data-period="monthly">This Month</button>
          <button class="sd-period-btn" data-period="last_month">Last Month</button>
        </div>
        <div class="sd-period-label" id="sd-period-label">This Week</div>
      </div>

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

      <div class="sd-matrix-bar">
        <div class="sd-section-title" style="margin:0">
          <span class="sd-section-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg></span>
          <span id="sd-matrix-title">Weekly Revenue Matrix</span>
        </div>
        <div class="sd-matrix-controls">
          <div class="sd-view-toggle">
            <button class="sd-view-btn active" data-view="value">$ Value</button>
            <button class="sd-view-btn" data-view="qty">Qty</button>
          </div>
          <div class="sd-mtx-toggle">
            <button class="sd-mtx-btn" data-mtx="monthly">Monthly</button>
            <button class="sd-mtx-btn active" data-mtx="weekly">Weekly</button>
            <button class="sd-mtx-btn" data-mtx="daily">Daily</button>
          </div>
        </div>
      </div>
      <div class="sd-matrix-card">
        <div id="sd-matrix" class="sd-matrix-wrap"><div class="sd-loading"><div class="sd-spinner"></div></div></div>
      </div>

    </div>
    `;
}
