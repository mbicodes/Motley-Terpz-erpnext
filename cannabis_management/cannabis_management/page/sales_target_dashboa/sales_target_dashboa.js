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
    var arMatrixData  = null;

    var hour = new Date().getHours();
    var ge = rootEl.querySelector('.sd-greeting');
    if (ge) ge.textContent = hour < 12 ? 'good morning' : hour < 17 ? 'good afternoon' : 'good evening';

    window.salesDash = {
        reload:      function () { loadAll(currentPeriod); },
        exportExcel: function () { downloadCSV(); },
    };

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
        if (arMatrixData) {
            renderArMatrix('sd-ar-matrix', arMatrixData, arMatrixData.columns);
        }
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

        var isQty      = currentView === 'qty';
        var cols       = matrix.columns;
        var showAvg    = currentMatrix === 'weekly';
        var AVG        = 'Avg (8 Wks)';
        var FF_KEY     = 'Fresh Frozen Main';
        var totalCols  = 4 + cols.length + (showAvg ? 1 : 0);

        // Divisor for the static "Target" column header
        var targetDiv, targetLabel;
        if (currentMatrix === 'monthly') { targetDiv = 1;  targetLabel = 'Monthly Target'; }
        else if (currentMatrix === 'daily') { targetDiv = 20; targetLabel = 'Daily Target'; }
        else                              { targetDiv = 4;  targetLabel = 'Weekly Target'; }

        // Split products: Motley body rows vs Fresh Frozen (TSBC)
        var motleyProducts = matrix.products.filter(function (p) { return p.item_group !== FF_KEY; });
        var ffProduct      = matrix.products.find(function (p)   { return p.item_group === FF_KEY; }) || null;

        // Pre-compute averages (all products so Fresh Frozen avg is available)
        var avgActuals = {}, avgUnits = {};
        if (showAvg) {
            matrix.products.forEach(function (p) {
                var rSum = 0, qSum = 0;
                cols.forEach(function (c) { rSum += p.actuals[c] || 0; qSum += (p.units && p.units[c]) || 0; });
                avgActuals[p.item_group] = cols.length ? rSum / cols.length : 0;
                avgUnits[p.item_group]   = cols.length ? qSum / cols.length : 0;
            });
        }

        // Motley target totals (sum across all Motley products)
        var motleyTargetRev = 0, motleyTargetUnits = 0;
        motleyProducts.forEach(function (p) {
            motleyTargetRev   += p.monthly_target ? p.monthly_target / targetDiv : 0;
            motleyTargetUnits += p.target_units   ? p.target_units   / targetDiv : 0;
        });

        // TSBC targets
        var tsbcMonthly     = matrix.tsbc_monthly_target || 400000;
        var tsbcTargetRev   = tsbcMonthly / targetDiv;
        var tsbcTargetUnits = 2000 / targetDiv;
        var ffTargetRev     = ffProduct ? (ffProduct.monthly_target  ? ffProduct.monthly_target  / targetDiv : 0) : 0;
        var ffTargetUnits   = ffProduct ? (ffProduct.target_units    ? ffProduct.target_units    / targetDiv : 0) : 0;

        function cellClass(actual, target) {
            if (!target || target <= 0) return '';
            var r = actual / target;
            if (r >= 1)   return 'sd-cell-green';
            if (r >= 0.7) return 'sd-cell-amber';
            if (actual > 0) return 'sd-cell-red';
            return '';
        }

        function blankCells(n) {
            var s = '';
            for (var i = 0; i < n; i++) s += '<td class="sd-matrix-num">—</td>';
            return s;
        }

        // ── Header ────────────────────────────────────────────────
        var html = '<table class="sd-matrix"><thead><tr>';
        html += '<th class="sd-matrix-th-product">Item Group</th>';
        html += '<th class="sd-matrix-th-static">Target Units</th>';
        html += '<th class="sd-matrix-th-static">Avg Price</th>';
        html += '<th class="sd-matrix-th-static">' + (isQty ? targetLabel.replace('Target', 'Target Units') : targetLabel) + '</th>';
        cols.forEach(function (c) {
            html += '<th class="sd-matrix-th-period">' + frappe.utils.escape_html(c) + '</th>';
        });
        if (showAvg) html += '<th class="sd-matrix-th-avg">' + AVG + '</th>';
        html += '</tr></thead>';

        // ── Body: Motley rows only (no Fresh Frozen) ──────────────
        html += '<tbody>';
        motleyProducts.forEach(function (p) {
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

        // 1. Motley — target + actuals in one row
        html += '<tr class="sd-matrix-foot-motley">';
        html += '<td class="sd-matrix-product sd-matrix-foot-label">Motley</td>';
        html += '<td class="sd-matrix-num">—</td>';
        html += '<td class="sd-matrix-num">—</td>';
        if (isQty) {
            html += '<td class="sd-matrix-num sd-matrix-target-rev">' + (motleyTargetUnits ? fmtQty(motleyTargetUnits) : '—') + '</td>';
        } else {
            html += '<td class="sd-matrix-num sd-matrix-target-rev">' + (motleyTargetRev ? fmtCurrency(motleyTargetRev) : '—') + '</td>';
        }
        cols.forEach(function (c) {
            var v = (matrix.motley_totals && matrix.motley_totals[c]) || 0;
            html += '<td class="sd-matrix-num">' + (v > 0 ? fmtCurrency(v) : '—') + '</td>';
        });
        if (showAvg) html += '<td class="sd-matrix-num sd-matrix-avg">' + (matrix.avg_motley > 0 ? fmtCurrency(matrix.avg_motley) : '—') + '</td>';
        html += '</tr>';

        // 2. Separator
        html += '<tr class="sd-matrix-separator"><td colspan="' + totalCols + '"></td></tr>';

        // 3. Fresh Frozen Main product row
        if (ffProduct) {
            html += '<tr>';
            html += '<td class="sd-matrix-product">' + frappe.utils.escape_html(FF_KEY) + '</td>';
            var ffUnits = ffProduct.target_units ? ffProduct.target_units / targetDiv : 0;
            html += '<td class="sd-matrix-num">' + (ffUnits ? fmtQty(ffUnits) : '—') + '</td>';
            html += '<td class="sd-matrix-num">—</td>';
            if (isQty) {
                html += '<td class="sd-matrix-num sd-matrix-target-rev">' + (ffTargetUnits ? fmtQty(ffTargetUnits) : '—') + '</td>';
            } else {
                html += '<td class="sd-matrix-num sd-matrix-target-rev">' + (ffTargetRev ? fmtCurrency(ffTargetRev) : '—') + '</td>';
            }
            cols.forEach(function (col) {
                if (isQty) {
                    var aq = (ffProduct.units && ffProduct.units[col]) || 0;
                    html += '<td class="sd-matrix-num">' + (aq > 0 ? fmtQty(aq) : '—') + '</td>';
                } else {
                    var av = ffProduct.actuals[col] || 0;
                    var ct = (ffProduct.cell_targets && ffProduct.cell_targets[col]) || 0;
                    html += '<td class="sd-matrix-num ' + cellClass(av, ct) + '">' + (av > 0 ? fmtCurrency(av) : '—') + '</td>';
                }
            });
            if (showAvg) {
                var ffAvg = isQty ? (avgUnits[FF_KEY] || 0) : (avgActuals[FF_KEY] || 0);
                html += '<td class="sd-matrix-num sd-matrix-avg">' + (ffAvg > 0 ? (isQty ? fmtQty(ffAvg) : fmtCurrency(ffAvg)) : '—') + '</td>';
            }
            html += '</tr>';
        }

        // 4. TSBC — target + actuals in one row
        html += '<tr class="sd-matrix-foot-tsbc">';
        html += '<td class="sd-matrix-product sd-matrix-foot-label">TSBC</td>';
        html += '<td class="sd-matrix-num">—</td>';
        html += '<td class="sd-matrix-num">—</td>';
        if (isQty) {
            html += '<td class="sd-matrix-num sd-matrix-target-rev">' + (ffTargetUnits ? fmtQty(ffTargetUnits) : '—') + '</td>';
        } else {
            html += '<td class="sd-matrix-num sd-matrix-target-rev">' + (ffTargetRev ? fmtCurrency(ffTargetRev) : '—') + '</td>';
        }
        cols.forEach(function (col) {
            var v  = ffProduct ? (isQty ? ((ffProduct.units && ffProduct.units[col]) || 0) : (ffProduct.actuals[col] || 0)) : ((matrix.tsbc_totals && matrix.tsbc_totals[col]) || 0);
            var ct = ffProduct ? ((ffProduct.cell_targets && ffProduct.cell_targets[col]) || 0) : 0;
            html += '<td class="sd-matrix-num ' + cellClass(v, ct) + '">' + (v > 0 ? (isQty ? fmtQty(v) : fmtCurrency(v)) : '—') + '</td>';
        });
        if (showAvg) {
            var ffAvgTsbc = isQty ? (avgUnits[FF_KEY] || 0) : (avgActuals[FF_KEY] || 0);
            html += '<td class="sd-matrix-num sd-matrix-avg">' + (ffAvgTsbc > 0 ? (isQty ? fmtQty(ffAvgTsbc) : fmtCurrency(ffAvgTsbc)) : '—') + '</td>';
        }
        html += '</tr>';

        // 5. Separator
        html += '<tr class="sd-matrix-separator"><td colspan="' + totalCols + '"></td></tr>';

        // 6. Master Touch Manufacturing row
        html += '<tr class="sd-matrix-foot-mtm">';
        html += '<td class="sd-matrix-product sd-matrix-foot-label">Master Touch Manufacturing</td>';
        html += '<td class="sd-matrix-num">—</td><td class="sd-matrix-num">—</td><td class="sd-matrix-num">—</td>';
        cols.forEach(function (c) {
            var v = (matrix.mtm_totals && matrix.mtm_totals[c]) || 0;
            html += '<td class="sd-matrix-num">' + (v > 0 ? fmtCurrency(v) : '—') + '</td>';
        });
        if (showAvg) html += '<td class="sd-matrix-num sd-matrix-avg">' + (matrix.avg_mtm > 0 ? fmtCurrency(matrix.avg_mtm) : '—') + '</td>';
        html += '</tr>';

        // 7. LA Canna row
        html += '<tr class="sd-matrix-foot-lacanna">';
        html += '<td class="sd-matrix-product sd-matrix-foot-label">LA Canna</td>';
        html += '<td class="sd-matrix-num">—</td><td class="sd-matrix-num">—</td><td class="sd-matrix-num">—</td>';
        cols.forEach(function (c) {
            var v = (matrix.la_canna_totals && matrix.la_canna_totals[c]) || 0;
            html += '<td class="sd-matrix-num">' + (v > 0 ? fmtCurrency(v) : '—') + '</td>';
        });
        if (showAvg) html += '<td class="sd-matrix-num sd-matrix-avg">' + (matrix.avg_la_canna > 0 ? fmtCurrency(matrix.avg_la_canna) : '—') + '</td>';
        html += '</tr>';

        // 8. Separator
        html += '<tr class="sd-matrix-separator"><td colspan="' + totalCols + '"></td></tr>';

        // 9. Total row
        html += '<tr class="sd-matrix-foot-grand-total">';
        html += '<td class="sd-matrix-product sd-matrix-foot-label">Total</td>';
        html += '<td class="sd-matrix-num">—</td><td class="sd-matrix-num">—</td><td class="sd-matrix-num">—</td>';
        cols.forEach(function (c) {
            var motley  = (matrix.motley_totals   && matrix.motley_totals[c])   || 0;
            var tsbc    = ffProduct ? (ffProduct.actuals[c] || 0) : ((matrix.tsbc_totals && matrix.tsbc_totals[c]) || 0);
            var mtm     = (matrix.mtm_totals      && matrix.mtm_totals[c])      || 0;
            var lacanna = (matrix.la_canna_totals && matrix.la_canna_totals[c]) || 0;
            var total   = motley + tsbc + mtm + lacanna;
            html += '<td class="sd-matrix-num sd-matrix-total-cell">' + (total > 0 ? fmtCurrency(total) : '—') + '</td>';
        });
        if (showAvg) {
            var avgTotal = (matrix.avg_motley || 0) + (matrix.avg_tsbc || 0) + (matrix.avg_mtm || 0) + (matrix.avg_la_canna || 0);
            html += '<td class="sd-matrix-num sd-matrix-avg sd-matrix-total-cell">' + (avgTotal > 0 ? fmtCurrency(avgTotal) : '—') + '</td>';
        }
        html += '</tr>';

        html += '</tfoot></table>';
        el.innerHTML = html;
    }

    // ── AR Matrix renderer ────────────────────────────────────────
    function renderArMatrix(containerId, ar, cols) {
        var el = rootEl.querySelector('#' + containerId);
        if (!el) return;
        if (!ar || !cols || !cols.length) {
            el.innerHTML = '<p class="sd-empty">AR data loading…</p>';
            return;
        }

        var bal  = ar.balances  || {};
        var coll = ar.collected || {};
        var pace = ar.pace_by_col || {};
        var avg  = ar.avg || {};
        var showAvg = true;   // AR matrix always shows avg (monthly view)

        function arCell(v, cls) {
            return '<td class="sd-matrix-num ' + (cls||'') + '">' + (v > 0 ? fmtCurrency(v) : '—') + '</td>';
        }

        var html = '<table class="sd-matrix"><thead><tr>';
        html += '<th class="sd-matrix-th-product">AR Category</th>';
        html += '<th class="sd-matrix-th-static">Outstanding</th>';
        html += '<th class="sd-matrix-th-static">Monthly Pace</th>';
        cols.forEach(function (c) { html += '<th class="sd-matrix-th-period">' + frappe.utils.escape_html(c) + '</th>'; });
        if (showAvg) html += '<th class="sd-matrix-th-avg">Avg Collected</th>';
        html += '</tr></thead><tbody>';

        // ── Total AR (grayed, strikethrough) ──────────────────
        html += '<tr style="opacity:.55">';
        html += '<td class="sd-matrix-product" style="color:#94a3b8;font-style:italic;text-decoration:line-through;">Total AR</td>';
        html += '<td class="sd-matrix-num" style="text-decoration:line-through;">' + fmtCurrency(bal.total||0) + '</td>';
        html += '<td class="sd-matrix-num">—</td>';
        cols.forEach(function(c) { html += arCell((coll.total||{})[c]||0); });
        if (showAvg) html += arCell(avg.total||0);
        html += '</tr>';

        // ── Legacy AR (red, pace target) ──────────────────────
        html += '<tr class="sd-ar-legacy">';
        html += '<td class="sd-matrix-product sd-ar-label-legacy">Legacy AR'
             + ' <span class="sd-ar-badge-legacy">pre-May 15</span></td>';
        html += '<td class="sd-matrix-num" style="color:#dc2626;font-weight:800;">' + fmtCurrency(bal.legacy||0) + '</td>';
        html += '<td class="sd-matrix-num sd-matrix-target-rev">' + fmtCurrency(ar.legacy_monthly_target||400000) + '/mo</td>';
        cols.forEach(function(c) {
            var v = (coll.legacy||{})[c] || 0;
            var t = pace[c] || 0;
            var cls = '';
            if (v > 0 && t > 0) { var r = v/t; cls = r>=1 ? 'sd-cell-green' : r>=0.5 ? 'sd-cell-amber' : 'sd-cell-red'; }
            html += '<td class="sd-matrix-num ' + cls + '">' + (v > 0 ? fmtCurrency(v) : '—') + '</td>';
        });
        if (showAvg) html += arCell(avg.legacy||0, 'sd-matrix-avg');
        html += '</tr>';

        // ── Bad Standing (>30 days overdue) ───────────────────
        html += '<tr class="sd-ar-bad">';
        html += '<td class="sd-matrix-product sd-ar-label-bad">Bad Standing'
             + ' <span class="sd-ar-badge-bad">&gt;30 days</span></td>';
        html += '<td class="sd-matrix-num" style="color:#d97706;font-weight:700;">' + fmtCurrency(bal.bad||0) + '</td>';
        html += '<td class="sd-matrix-num">—</td>';
        cols.forEach(function(c) {
            var v = (coll.bad||{})[c] || 0;
            html += '<td class="sd-matrix-num' + (v > 0 ? ' sd-cell-green' : '') + '">' + (v > 0 ? fmtCurrency(v) : '—') + '</td>';
        });
        if (showAvg) html += arCell(avg.bad||0, 'sd-matrix-avg');
        html += '</tr>';

        // ── Good Standing (≤30 days) ──────────────────────────
        html += '<tr class="sd-ar-good">';
        html += '<td class="sd-matrix-product sd-ar-label-good">Good Standing'
             + ' <span class="sd-ar-badge-good">≤30 days</span></td>';
        html += '<td class="sd-matrix-num" style="color:#059669;font-weight:700;">' + fmtCurrency(bal.good||0) + '</td>';
        html += '<td class="sd-matrix-num">—</td>';
        cols.forEach(function(c) {
            var v = (coll.good||{})[c] || 0;
            html += '<td class="sd-matrix-num' + (v > 0 ? ' sd-cell-green' : '') + '">' + (v > 0 ? fmtCurrency(v) : '—') + '</td>';
        });
        if (showAvg) html += arCell(avg.good||0, 'sd-matrix-avg');
        html += '</tr>';

        html += '</tbody></table>';
        el.innerHTML = html;
    }

    // ── Excel export ──────────────────────────────────────────────
    function downloadCSV() {
        var matrix = matrixCache[currentMatrix];
        if (!matrix || !matrix.columns || !matrix.products) {
            frappe.msgprint('No data to export yet.'); return;
        }

        var isQty   = currentView === 'qty';
        var cols    = matrix.columns;
        var showAvg = currentMatrix === 'weekly';
        var FF_KEY  = 'Fresh Frozen';

        var targetDiv, targetLabel;
        if (currentMatrix === 'monthly')    { targetDiv = 1;  targetLabel = 'Monthly Target'; }
        else if (currentMatrix === 'daily') { targetDiv = 20; targetLabel = 'Daily Target'; }
        else                                { targetDiv = 4;  targetLabel = 'Weekly Target'; }

        var motleyProducts = matrix.products.filter(function (p) { return p.item_group !== FF_KEY; });
        var ffProduct      = matrix.products.find(function (p)   { return p.item_group === FF_KEY; }) || null;

        var motleyTargetRev = 0, motleyTargetUnits = 0;
        motleyProducts.forEach(function (p) {
            motleyTargetRev   += p.monthly_target ? p.monthly_target / targetDiv : 0;
            motleyTargetUnits += p.target_units   ? p.target_units   / targetDiv : 0;
        });

        var tsbcMonthly     = matrix.tsbc_monthly_target || 400000;
        var tsbcTargetRev   = tsbcMonthly / targetDiv;
        var tsbcTargetUnits = 2000 / targetDiv;
        var ffTargetRev     = ffProduct ? (ffProduct.monthly_target ? ffProduct.monthly_target / targetDiv : 0) : 0;
        var ffTargetUnits   = ffProduct ? (ffProduct.target_units   ? ffProduct.target_units   / targetDiv : 0) : 0;

        var avgActuals = {}, avgUnits = {};
        if (showAvg) {
            matrix.products.forEach(function (p) {
                var rSum = 0, qSum = 0;
                cols.forEach(function (c) { rSum += p.actuals[c] || 0; qSum += (p.units && p.units[c]) || 0; });
                avgActuals[p.item_group] = cols.length ? rSum / cols.length : 0;
                avgUnits[p.item_group]   = cols.length ? qSum / cols.length : 0;
            });
        }

        // ── Helpers ───────────────────────────────────────────────
        function he(s) {
            return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }
        function fmtNum(v) {
            if (!v || v <= 0) return '';
            return isQty
                ? parseFloat(v).toLocaleString(undefined, { maximumFractionDigits: 2 })
                : '$ ' + parseFloat(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
        function fmtTgt(v) { return fmtNum(v); }

        // Cell builders
        function th(txt, extra) {
            return '<td class="hdr"' + (extra || '') + '>' + he(txt) + '</td>';
        }
        function td(txt, cls, extra) {
            return '<td' + (cls ? ' class="' + cls + '"' : '') + (extra || '') + '>' + he(txt) + '</td>';
        }
        function tdNum(v, cls) {
            var s = fmtNum(v);
            return '<td class="num' + (cls ? ' ' + cls : '') + '">' + he(s) + '</td>';
        }
        function tdTgt(v) {
            return '<td class="num tgt">' + he(fmtTgt(v)) + '</td>';
        }
        function blank(n) { var s = ''; for (var i=0;i<n;i++) s += '<td></td>'; return s; }

        // ── Build HTML ────────────────────────────────────────────
        var periodLabel = currentMatrix.charAt(0).toUpperCase() + currentMatrix.slice(1);
        var dateStr     = new Date().toLocaleDateString(undefined, { year:'numeric', month:'short', day:'numeric' });
        var tgtColLabel = isQty ? targetLabel.replace('Target','Target Units') : targetLabel;
        var numDataCols = cols.length + (showAvg ? 1 : 0);

        var html = [
            '<html xmlns:o="urn:schemas-microsoft-com:office:office"',
            '      xmlns:x="urn:schemas-microsoft-com:office:excel"',
            '      xmlns="http://www.w3.org/TR/REC-html40">',
            '<head><meta charset="UTF-8">',
            '<!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet>',
            '<x:Name>Sales Target</x:Name>',
            '<x:WorksheetOptions><x:FreezePanes/><x:FrozenNoSplit/>',
            '<x:SplitHorizontal>2</x:SplitHorizontal><x:TopRowBottomPane>2</x:TopRowBottomPane>',
            '</x:WorksheetOptions></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]-->',
            '<style>',
            'body{font-family:Calibri,Arial,sans-serif;font-size:11pt;}',
            'table{border-collapse:collapse;width:100%;}',
            'td,th{border:1px solid #d1d5db;padding:5px 10px;vertical-align:middle;}',
            /* Title row */
            '.title{background:#1e293b;color:#fff;font-size:14pt;font-weight:700;border:none;padding:10px 14px;}',
            '.sub{background:#334155;color:#94a3b8;font-size:9pt;border:none;padding:4px 14px;}',
            /* Header */
            '.hdr{background:#1e293b;color:#fff;font-weight:700;font-size:10pt;text-align:center;white-space:nowrap;}',
            '.hdr-left{text-align:left;}',
            /* Numbers */
            '.num{text-align:right;font-family:"Courier New",monospace;font-size:10pt;white-space:nowrap;}',
            '.tgt{background:#f5f0ff;font-weight:600;}',
            /* Data cell colors */
            '.green{color:#065f46;background:#d1fae5;}',
            '.red{color:#991b1b;background:#fee2e2;}',
            '.amber{color:#92400e;background:#fef3c7;}',
            /* Section rows */
            '.tgt-motley td{background:#ede9fe;font-weight:700;}',
            '.tgt-motley .lbl{color:#6d28d9;}',
            '.motley-total td{background:#f1f5f9;font-weight:700;border-top:2px solid #7c3aed;}',
            '.motley-total .lbl{color:#475569;}',
            '.sep td{background:#fff;border:none;height:8px;}',
            '.ff-row td{background:#f0fdf4;}',
            '.tgt-tsbc td{background:#dcfce7;font-weight:700;}',
            '.tgt-tsbc .lbl{color:#15803d;}',
            '.tsbc-row td{background:#f0fdf4;font-weight:700;border-top:2px solid #059669;}',
            '.tsbc-row .lbl{color:#065f46;}',
            /* Label cells */
            '.lbl{font-weight:600;white-space:nowrap;}',
            '.dim{color:#94a3b8;}',
            '</style></head><body>',
        ].join('\n');

        html += '<table>';

        // ── Title rows ────────────────────────────────────────────
        var totalCols = 4 + cols.length + (showAvg ? 1 : 0);
        html += '<tr><td class="title" colspan="' + totalCols + '">Sales Target Dashboard &mdash; ' + he(periodLabel) + ' View</td></tr>';
        html += '<tr><td class="sub" colspan="' + totalCols + '">Exported ' + he(dateStr) + ' &nbsp;&bull;&nbsp; ' + he(currentView === 'qty' ? 'Quantity View' : 'Revenue View') + '</td></tr>';
        html += '<tr><td colspan="' + totalCols + '" style="border:none;height:4px;background:#fff;"></td></tr>';

        // ── Header row ────────────────────────────────────────────
        html += '<tr>';
        html += th('Item Group', ' class="hdr hdr-left"');
        html += th('Target Units');
        html += th('Avg Price');
        html += th(tgtColLabel);
        cols.forEach(function (c) { html += th(c); });
        if (showAvg) html += th('Avg (8 Wks)');
        html += '</tr>';

        // ── Motley product rows ───────────────────────────────────
        motleyProducts.forEach(function (p, i) {
            var bg = i % 2 === 0 ? '' : ' style="background:#f9fafb;"';
            html += '<tr' + bg + '>';
            html += td(p.item_group, 'lbl');
            var dU = p.target_units ? p.target_units / targetDiv : 0;
            html += td(dU ? Math.round(dU).toLocaleString() : '—', 'num dim');
            html += td(p.avg_price ? ('$' + parseFloat(p.avg_price).toFixed(2)) : '—', 'num dim');
            if (isQty) {
                var tU = p.target_units ? p.target_units / targetDiv : 0;
                html += td(tU ? Math.round(tU).toLocaleString() : '—', 'num tgt');
            } else {
                var tR = p.monthly_target ? p.monthly_target / targetDiv : 0;
                html += td(tR ? ('$ ' + tR.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})) : '—', 'num tgt');
            }
            cols.forEach(function (col) {
                var val = isQty ? ((p.units && p.units[col]) || 0) : (p.actuals[col] || 0);
                var tgt = isQty ? (p.target_units ? p.target_units / targetDiv : 0) : ((p.cell_targets && p.cell_targets[col]) || 0);
                var cls = '';
                if (val > 0 && tgt > 0) { var r = val/tgt; cls = r>=1 ? 'green' : r>=0.7 ? 'amber' : 'red'; }
                html += td(val > 0 ? fmtNum(val) : '—', 'num' + (cls ? ' ' + cls : ''));
            });
            if (showAvg) {
                var aV = isQty ? (avgUnits[p.item_group]||0) : (avgActuals[p.item_group]||0);
                html += td(aV > 0 ? fmtNum(aV) : '—', 'num');
            }
            html += '</tr>';
        });


        // ── Motley (target + actuals merged) ──────────
        html += '<tr class="motley-total">';
        html += td('Motley', 'lbl');
        html += td('', 'num'); html += td('', 'num');
        var tmV = isQty ? (motleyTargetUnits ? Math.round(motleyTargetUnits).toLocaleString() : '—')
                        : (motleyTargetRev   ? ('$ ' + motleyTargetRev.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})) : '—');
        html += td(tmV, 'num tgt');
        cols.forEach(function (c) {
            var v = (matrix.motley_totals && matrix.motley_totals[c]) || 0;
            html += td(v > 0 ? fmtNum(v) : '—', 'num');
        });
        if (showAvg) html += td(matrix.avg_motley > 0 ? fmtNum(matrix.avg_motley) : '—', 'num');
        html += '</tr>';

        // ── Separator ──────────────────────────────
        html += '<tr class="sep"><td colspan="' + totalCols + '"></td></tr>';

        // ── Fresh Frozen row ──────────────────────────
        if (ffProduct) {
            html += '<tr class="ff-row">';
            html += td(FF_KEY, 'lbl');
            var ffU = ffProduct.target_units ? ffProduct.target_units / targetDiv : 0;
            html += td(ffU ? Math.round(ffU).toLocaleString() : '—', 'num dim');
            html += td('—', 'num dim');
            var ffTV = isQty ? (ffTargetUnits ? Math.round(ffTargetUnits).toLocaleString() : '—')
                             : (ffTargetRev   ? ('$ ' + ffTargetRev.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})) : '—');
            html += td(ffTV, 'num tgt');
            cols.forEach(function (col) {
                var val = isQty ? ((ffProduct.units && ffProduct.units[col])||0) : (ffProduct.actuals[col]||0);
                var tgt = (ffProduct.cell_targets && ffProduct.cell_targets[col]) || 0;
                var cls = '';
                if (val > 0 && tgt > 0) { var r = val/tgt; cls = r>=1 ? 'green' : r>=0.7 ? 'amber' : 'red'; }
                html += td(val > 0 ? fmtNum(val) : '—', 'num' + (cls ? ' ' + cls : ''));
            });
            if (showAvg) {
                var ffAvg = isQty ? (avgUnits[FF_KEY]||0) : (avgActuals[FF_KEY]||0);
                html += td(ffAvg > 0 ? fmtNum(ffAvg) : '—', 'num');
            }
            html += '</tr>';
        }

        // ── TSBC (target + actuals merged) ────────────────────
        html += '<tr class="tsbc-row">';
        html += td('TSBC', 'lbl');
        html += td('—', 'num dim'); html += td('—', 'num dim');
        var ttV = isQty ? (ffTargetUnits ? Math.round(ffTargetUnits).toLocaleString() : '—')
                        : (ffTargetRev   ? ('$ ' + ffTargetRev.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})) : '—');
        html += td(ttV, 'num tgt');
        cols.forEach(function (c) {
            var v   = ffProduct ? (isQty ? ((ffProduct.units && ffProduct.units[c]) || 0) : (ffProduct.actuals[c] || 0)) : ((matrix.tsbc_totals && matrix.tsbc_totals[c]) || 0);
            var tgt = ffProduct ? ((ffProduct.cell_targets && ffProduct.cell_targets[c]) || 0) : 0;
            var cls = '';
            if (v > 0 && tgt > 0) { var r = v/tgt; cls = r>=1 ? 'green' : r>=0.7 ? 'amber' : 'red'; }
            html += td(v > 0 ? fmtNum(v) : '—', 'num' + (cls ? ' ' + cls : ''));
        });
        if (showAvg) {
            var ffAvgEx = isQty ? (avgUnits[FF_KEY] || 0) : (avgActuals[FF_KEY] || 0);
            html += td(ffAvgEx > 0 ? fmtNum(ffAvgEx) : '—', 'num');
        }
        html += '</tr>';

        // ── Separator ──────────────────────────────
        html += '<tr class="sep"><td colspan="' + totalCols + '"></td></tr>';

        // ── Master Touch Manufacturing ──────────────
        html += '<tr style="background:#eef2ff;">';
        html += td('Master Touch Manufacturing', 'lbl');
        html += td('—', 'num dim'); html += td('—', 'num dim'); html += td('—', 'num dim');
        cols.forEach(function (c) {
            var v = (matrix.mtm_totals && matrix.mtm_totals[c]) || 0;
            html += td(v > 0 ? fmtNum(v) : '—', 'num');
        });
        if (showAvg) html += td(matrix.avg_mtm > 0 ? fmtNum(matrix.avg_mtm) : '—', 'num');
        html += '</tr>';

        // ── LA Canna ────────────────────────────────
        html += '<tr style="background:#eef2ff;">';
        html += td('LA Canna', 'lbl');
        html += td('—', 'num dim'); html += td('—', 'num dim'); html += td('—', 'num dim');
        cols.forEach(function (c) {
            var v = (matrix.la_canna_totals && matrix.la_canna_totals[c]) || 0;
            html += td(v > 0 ? fmtNum(v) : '—', 'num');
        });
        if (showAvg) html += td(matrix.avg_la_canna > 0 ? fmtNum(matrix.avg_la_canna) : '—', 'num');
        html += '</tr>';

        // ── Separator ──────────────────────────────
        html += '<tr class="sep"><td colspan="' + totalCols + '"></td></tr>';

        // ── Total ───────────────────────────────────
        html += '<tr style="background:#1e293b;color:#fff;font-weight:700;">';
        html += '<td class="lbl" style="color:#fff;padding:7px 12px;">Total</td>';
        html += '<td></td><td></td><td></td>';
        cols.forEach(function (c) {
            var motley  = (matrix.motley_totals   && matrix.motley_totals[c])   || 0;
            var tsbc    = ffProduct ? (ffProduct.actuals[c] || 0) : ((matrix.tsbc_totals && matrix.tsbc_totals[c]) || 0);
            var mtm     = (matrix.mtm_totals      && matrix.mtm_totals[c])      || 0;
            var lacanna = (matrix.la_canna_totals && matrix.la_canna_totals[c]) || 0;
            var total   = motley + tsbc + mtm + lacanna;
            html += '<td style="text-align:right;font-family:Courier New,monospace;padding:7px 12px;color:#fff;">' + (total > 0 ? fmtNum(total) : '—') + '</td>';
        });
        if (showAvg) {
            var avgT = (matrix.avg_motley||0)+(matrix.avg_tsbc||0)+(matrix.avg_mtm||0)+(matrix.avg_la_canna||0);
            html += '<td style="text-align:right;font-family:Courier New,monospace;padding:7px 12px;color:#fff;">' + (avgT > 0 ? fmtNum(avgT) : '—') + '</td>';
        }
        html += '</tr>';

        html += '</table></body></html>';

        // ── Download ──────────────────────────────────────────────
        var blob = new Blob([html], { type: 'application/vnd.ms-excel;charset=utf-8;' });
        var url  = URL.createObjectURL(blob);
        var a    = document.createElement('a');
        a.href   = url;
        a.download = 'Sales_Target_' + periodLabel + '_' + new Date().toISOString().slice(0,10) + '.xls';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
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
                if (arMatrixData) {
                    renderArMatrix('sd-ar-matrix', arMatrixData, arMatrixData.columns);
                }
            },
            error: function () {
                var el = rootEl.querySelector('#sd-matrix');
                if (el) el.innerHTML = '<p class="sd-empty">Error loading data.</p>';
            }
        });

        shimmerEl('sd-ar-matrix');
        frappe.call({
            method: API + 'get_ar_matrix',
            callback: function (r) {
                if (!r.message) return;
                arMatrixData = r.message;
                renderArMatrix('sd-ar-matrix', arMatrixData, arMatrixData.columns);
            },
            error: function () {
                var el = rootEl.querySelector('#sd-ar-matrix');
                if (el) el.innerHTML = '<p class="sd-empty">Error loading AR data.</p>';
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
          <button class="sd-export-btn" onclick="window.salesDash && window.salesDash.exportExcel()" title="Export to Excel">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Export
          </button>
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

      <div class="sd-matrix-bar" style="margin-top:28px;">
        <div class="sd-section-title" style="margin:0">
          <span class="sd-section-icon"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg></span>
          <span>AR Tracking Matrix</span>
        </div>
        <div class="sd-matrix-controls">
          <span style="font-size:11px;color:var(--sd-text-muted);padding:4px 8px;background:#f8fafc;border-radius:6px;">Legacy target: $400k/month · Bad standing: &gt;30 days overdue</span>
        </div>
      </div>
      <div class="sd-matrix-card">
        <div id="sd-ar-matrix" class="sd-matrix-wrap"><div class="sd-loading"><div class="sd-spinner"></div></div></div>
      </div>

    </div>
    `;
}
