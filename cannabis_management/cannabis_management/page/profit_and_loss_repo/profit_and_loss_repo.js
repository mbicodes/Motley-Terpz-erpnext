frappe.pages["profit-and-loss-repo"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Profit & Loss Report",
        single_column: true,
    });

    $(wrapper).find(".page-head").hide();

    var $body = $(page.body);
    $body.html('<div id="pnl-root"></div>');
    var $root = $("#pnl-root");

    // ── State ───────────────────────────────────────────────────────────────
    var state = {
        company: frappe.defaults.get_user_default("Company") || "",
        filter_based_on: "Fiscal Year",
        from_fiscal_year: "",
        to_fiscal_year: "",
        period_start_date: "",
        period_end_date: "",
        periodicity: "Yearly",
        presentation_currency: "",
        selected_view: "Report",
        accumulated_values: 1,
        show_zero_values: 0,
        include_default_book_entries: 1,
        finance_book: "",
        cost_center: [],
        project: [],
        loading: false,
        data: null,
        columns: [],
        summary: null,
        chart_data: null,
        expanded: {},
        fiscal_years: [],
        companies: [],
        currencies: [],
        chart_type: "bar",
        chart_instance: null,
    };

    // ── Inject CSS ──────────────────────────────────────────────────────────
    if (!document.getElementById("pnl-styles")) {
        var style = document.createElement("style");
        style.id = "pnl-styles";
        style.textContent = `
            #pnl-root {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #f0f2f5;
                min-height: 100vh;
                padding: 0;
            }

            /* ── Header ── */
            .pnl-header {
                background: linear-gradient(135deg, #1a1f36 0%, #2d3561 50%, #1a1f36 100%);
                padding: 28px 36px 24px;
                color: #fff;
                position: relative;
                overflow: hidden;
            }
            .pnl-header::before {
                content: '';
                position: absolute;
                top: -60px; right: -60px;
                width: 260px; height: 260px;
                background: radial-gradient(circle, rgba(99,102,241,0.25) 0%, transparent 70%);
                border-radius: 50%;
            }
            .pnl-header::after {
                content: '';
                position: absolute;
                bottom: -80px; left: 40%;
                width: 340px; height: 340px;
                background: radial-gradient(circle, rgba(16,185,129,0.12) 0%, transparent 70%);
                border-radius: 50%;
            }
            .pnl-header-inner {
                position: relative; z-index: 1;
                display: flex; align-items: center; justify-content: space-between;
                flex-wrap: wrap; gap: 12px;
            }
            .pnl-title-block { display: flex; align-items: center; gap: 14px; }
            .pnl-logo-icon {
                width: 48px; height: 48px;
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                border-radius: 14px;
                display: flex; align-items: center; justify-content: center;
                font-size: 22px; box-shadow: 0 4px 16px rgba(99,102,241,0.4);
            }
            .pnl-main-title {
                font-size: 24px; font-weight: 700; letter-spacing: -0.3px; margin: 0;
                color: #fff;
            }
            .pnl-subtitle {
                font-size: 13px; color: rgba(255,255,255,0.6); margin: 2px 0 0;
            }
            .pnl-run-btn {
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                border: none; color: #fff;
                padding: 10px 24px; border-radius: 10px;
                font-size: 14px; font-weight: 600; cursor: pointer;
                box-shadow: 0 4px 14px rgba(99,102,241,0.5);
                transition: all 0.2s; display: flex; align-items: center; gap: 8px;
                white-space: nowrap;
            }
            .pnl-run-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(99,102,241,0.6); }
            .pnl-run-btn:active { transform: translateY(0); }
            .pnl-run-btn .btn-spinner { display: none; }
            .pnl-run-btn.loading .btn-text { display: none; }
            .pnl-run-btn.loading .btn-spinner { display: inline-block; }

            /* ── Filter Panel ── */
            .pnl-filters-panel {
                background: #fff;
                border-bottom: 1px solid #e5e7eb;
                padding: 18px 36px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            }
            .pnl-filters-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
                gap: 12px 16px;
                align-items: end;
            }
            .pnl-field { display: flex; flex-direction: column; gap: 4px; }
            .pnl-field label {
                font-size: 11px; font-weight: 600; color: #6b7280;
                text-transform: uppercase; letter-spacing: 0.6px;
            }
            .pnl-field select,
            .pnl-field input[type="text"],
            .pnl-field input[type="date"] {
                border: 1.5px solid #e5e7eb;
                border-radius: 8px;
                padding: 7px 10px;
                font-size: 13px;
                color: #111827;
                background: #f9fafb;
                outline: none;
                transition: border-color 0.15s, box-shadow 0.15s;
                width: 100%;
                box-sizing: border-box;
            }
            .pnl-field select:focus,
            .pnl-field input:focus {
                border-color: #6366f1;
                box-shadow: 0 0 0 3px rgba(99,102,241,0.12);
                background: #fff;
            }
            .pnl-check-field {
                display: flex; align-items: center; gap: 8px;
                padding: 8px 0 2px;
            }
            .pnl-check-field input[type="checkbox"] {
                width: 16px; height: 16px; accent-color: #6366f1; cursor: pointer;
            }
            .pnl-check-field label {
                font-size: 13px; color: #374151; cursor: pointer; font-weight: 500;
            }
            .pnl-filters-row2 {
                margin-top: 12px;
                display: flex; gap: 20px; flex-wrap: wrap; align-items: center;
            }

            /* ── Body ── */
            .pnl-body { padding: 24px 36px; }

            /* ── Empty/Loading states ── */
            .pnl-placeholder {
                background: #fff; border-radius: 16px;
                padding: 60px 24px; text-align: center;
                box-shadow: 0 1px 4px rgba(0,0,0,0.06);
                color: #9ca3af;
            }
            .pnl-placeholder .ph-icon { font-size: 52px; margin-bottom: 12px; }
            .pnl-placeholder p { font-size: 15px; }
            .pnl-loader {
                background: #fff; border-radius: 16px;
                padding: 60px 24px; text-align: center;
                box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            }
            .pnl-spinner {
                width: 42px; height: 42px;
                border: 4px solid #e5e7eb;
                border-top-color: #6366f1;
                border-radius: 50%;
                animation: pnl-spin 0.7s linear infinite;
                margin: 0 auto 14px;
            }
            @keyframes pnl-spin { to { transform: rotate(360deg); } }

            /* ── KPI Cards ── */
            .pnl-kpis {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }
            .pnl-kpi-card {
                background: #fff;
                border-radius: 16px;
                padding: 20px 22px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.07);
                border: 1px solid #f3f4f6;
                position: relative; overflow: hidden;
                transition: transform 0.15s, box-shadow 0.15s;
            }
            .pnl-kpi-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0,0,0,0.1); }
            .pnl-kpi-card::after {
                content: '';
                position: absolute; top: 0; left: 0; right: 0; height: 4px;
                border-radius: 16px 16px 0 0;
            }
            .pnl-kpi-income::after { background: linear-gradient(90deg, #10b981, #059669); }
            .pnl-kpi-expense::after { background: linear-gradient(90deg, #f59e0b, #d97706); }
            .pnl-kpi-profit::after { background: linear-gradient(90deg, #6366f1, #8b5cf6); }
            .pnl-kpi-ratio::after  { background: linear-gradient(90deg, #0ea5e9, #0284c7); }
            .kpi-icon {
                width: 40px; height: 40px; border-radius: 12px;
                display: flex; align-items: center; justify-content: center;
                font-size: 18px; margin-bottom: 12px;
            }
            .pnl-kpi-income .kpi-icon { background: #ecfdf5; }
            .pnl-kpi-expense .kpi-icon { background: #fffbeb; }
            .pnl-kpi-profit .kpi-icon { background: #eef2ff; }
            .pnl-kpi-ratio .kpi-icon  { background: #f0f9ff; }
            .kpi-label { font-size: 12px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; }
            .kpi-value { font-size: 26px; font-weight: 700; color: #111827; margin: 4px 0; letter-spacing: -0.5px; }
            .kpi-value.positive { color: #059669; }
            .kpi-value.negative { color: #dc2626; }
            .kpi-badge {
                display: inline-flex; align-items: center; gap: 4px;
                font-size: 12px; font-weight: 600;
                padding: 2px 8px; border-radius: 20px;
            }
            .kpi-badge.up { background: #dcfce7; color: #166534; }
            .kpi-badge.down { background: #fee2e2; color: #991b1b; }
            .kpi-badge.neutral { background: #f3f4f6; color: #6b7280; }

            /* ── Chart + Table Layout ── */
            .pnl-content-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 20px;
            }

            /* ── Chart ── */
            .pnl-chart-card {
                background: #fff; border-radius: 16px;
                padding: 22px 24px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.07);
                border: 1px solid #f3f4f6;
            }
            .pnl-card-header {
                display: flex; align-items: center; justify-content: space-between;
                margin-bottom: 18px; flex-wrap: wrap; gap: 10px;
            }
            .pnl-card-title {
                font-size: 15px; font-weight: 700; color: #111827;
            }
            .pnl-chart-tabs { display: flex; gap: 6px; }
            .pnl-chart-tab {
                padding: 5px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
                border: 1.5px solid #e5e7eb; background: #f9fafb; color: #6b7280;
                cursor: pointer; transition: all 0.15s;
            }
            .pnl-chart-tab.active { background: #6366f1; border-color: #6366f1; color: #fff; }
            .pnl-chart-wrap { position: relative; height: 280px; }
            .pnl-chart-wrap canvas { max-height: 280px; }

            /* ── Table Card ── */
            .pnl-table-card {
                background: #fff; border-radius: 16px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.07);
                border: 1px solid #f3f4f6; overflow: hidden;
            }
            .pnl-table-card-header {
                display: flex; align-items: center; justify-content: space-between;
                padding: 18px 24px 16px; flex-wrap: wrap; gap: 10px;
                border-bottom: 1px solid #f3f4f6;
            }
            .pnl-search-box {
                display: flex; align-items: center; gap: 8px;
                background: #f3f4f6; border-radius: 8px; padding: 6px 12px;
                border: 1.5px solid transparent; transition: all 0.15s;
            }
            .pnl-search-box:focus-within {
                background: #fff; border-color: #6366f1;
                box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
            }
            .pnl-search-box svg { color: #9ca3af; flex-shrink: 0; }
            .pnl-search-input {
                border: none; background: transparent; outline: none;
                font-size: 13px; color: #111827; width: 180px;
            }
            .pnl-table-actions { display: flex; gap: 8px; }
            .pnl-action-btn {
                padding: 6px 14px; border-radius: 8px; font-size: 12px; font-weight: 600;
                border: 1.5px solid #e5e7eb; background: #f9fafb; color: #374151;
                cursor: pointer; transition: all 0.15s; display: flex; align-items: center; gap: 6px;
            }
            .pnl-action-btn:hover { background: #f3f4f6; border-color: #d1d5db; }
            .pnl-action-btn.primary { background: #6366f1; border-color: #6366f1; color: #fff; }
            .pnl-action-btn.primary:hover { background: #4f46e5; }

            /* ── Table ── */
            .pnl-table-scroll { overflow-x: auto; }
            .pnl-table {
                width: 100%; border-collapse: collapse; font-size: 13.5px;
            }
            .pnl-table thead tr {
                background: #f8f9fc;
                border-bottom: 2px solid #e5e7eb;
            }
            .pnl-table thead th {
                padding: 11px 16px; text-align: left;
                font-size: 11px; font-weight: 700; color: #6b7280;
                text-transform: uppercase; letter-spacing: 0.6px;
                white-space: nowrap;
            }
            .pnl-table thead th.num { text-align: right; }
            .pnl-table tbody tr { border-bottom: 1px solid #f3f4f6; transition: background 0.1s; }
            .pnl-table tbody tr:hover { background: #fafbff; }
            .pnl-table td {
                padding: 10px 16px; color: #374151; vertical-align: middle;
            }
            .pnl-table td.num { text-align: right; font-variant-numeric: tabular-nums; }

            /* Row types */
            .row-section-header td {
                background: linear-gradient(90deg, #f0f4ff, #f8f9fc);
                font-weight: 700; font-size: 13px; color: #1e1b4b;
                border-top: 2px solid #e0e7ff;
                border-bottom: 1px solid #e0e7ff;
            }
            .row-group-header td {
                background: #fafbff;
                font-weight: 600; color: #374151;
                font-size: 13px;
            }
            .row-total td {
                background: #1a1f36 !important;
                color: #fff !important;
                font-weight: 700;
                font-size: 13.5px;
                border-top: 2px solid #374151 !important;
            }
            .row-net-profit td {
                background: linear-gradient(90deg, #1e1b4b, #2d3561) !important;
                color: #fff !important;
                font-weight: 800;
                font-size: 14px;
                border-top: 3px solid #6366f1 !important;
            }
            .row-net-profit td .net-positive { color: #34d399; }
            .row-net-profit td .net-negative { color: #f87171; }
            .row-subtotal td {
                background: #f5f7ff;
                font-weight: 600; color: #4338ca;
                border-top: 1px solid #e0e7ff;
            }

            .pnl-account-cell {
                display: flex; align-items: center; gap: 0;
            }
            .pnl-indent { display: inline-block; }
            .pnl-toggle {
                width: 18px; height: 18px;
                display: inline-flex; align-items: center; justify-content: center;
                cursor: pointer; color: #9ca3af; flex-shrink: 0;
                font-size: 10px; transition: transform 0.15s;
                margin-right: 4px; user-select: none;
            }
            .pnl-toggle.open { transform: rotate(90deg); color: #6366f1; }
            .pnl-toggle-spacer { width: 22px; display: inline-block; flex-shrink: 0; }

            .pnl-acct-icon {
                width: 22px; height: 22px; border-radius: 6px;
                display: inline-flex; align-items: center; justify-content: center;
                font-size: 11px; margin-right: 6px; flex-shrink: 0;
            }
            .icon-income { background: #dcfce7; color: #166534; }
            .icon-expense { background: #fef3c7; color: #92400e; }
            .icon-profit { background: #ede9fe; color: #5b21b6; }
            .icon-leaf { background: #dbeafe; color: #1e40af; }

            .num-positive { color: #059669; }
            .num-negative { color: #dc2626; }
            .num-zero { color: #9ca3af; }

            /* ── View toggle ── */
            .pnl-view-pills {
                display: flex; gap: 4px;
                background: #f3f4f6; border-radius: 10px; padding: 3px;
            }
            .pnl-view-pill {
                padding: 5px 14px; border-radius: 7px; font-size: 12px; font-weight: 600;
                cursor: pointer; transition: all 0.15s; color: #6b7280;
                border: none; background: transparent;
            }
            .pnl-view-pill.active { background: #fff; color: #4338ca; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }

            /* ── Footer ── */
            .pnl-footer {
                text-align: center; padding: 20px;
                font-size: 12px; color: #9ca3af;
            }

            /* ── Responsive ── */
            @media (max-width: 768px) {
                .pnl-header { padding: 20px 16px; }
                .pnl-filters-panel { padding: 14px 16px; }
                .pnl-body { padding: 16px; }
                .pnl-filters-grid { grid-template-columns: 1fr 1fr; }
            }
        `;
        document.head.appendChild(style);
    }

    // ── Load Chart.js ────────────────────────────────────────────────────────
    function ensureChartJs(cb) {
        if (window.Chart) { cb(); return; }
        var s = document.createElement("script");
        s.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js";
        s.onload = cb;
        document.head.appendChild(s);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────
    function fmt_currency(val, currency) {
        if (val === "" || val === null || val === undefined) return "";
        var n = parseFloat(val) || 0;
        try {
            return new Intl.NumberFormat("en-US", { style: "currency", currency: currency || "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
        } catch(e) {
            return (n < 0 ? "-" : "") + (currency || "") + " " + Math.abs(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        }
    }

    function fmt_number(val) {
        if (val === "" || val === null || val === undefined) return "";
        var n = parseFloat(val) || 0;
        return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function escHtml(s) {
        return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    }

    function getCurrency() {
        return state.presentation_currency || frappe.defaults.get_default("currency") || "USD";
    }

    // ── Build Shell HTML ─────────────────────────────────────────────────────
    function buildShell() {
        return `
        <div class="pnl-header">
            <div class="pnl-header-inner">
                <div class="pnl-title-block">
                    <div class="pnl-logo-icon">📊</div>
                    <div>
                        <div class="pnl-main-title">Profit &amp; Loss Statement</div>
                        <div class="pnl-subtitle" id="pnl-header-sub">Select filters and run the report</div>
                    </div>
                </div>
                <button class="pnl-run-btn" id="pnl-run-btn">
                    <svg class="btn-text" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M5 3l14 9-14 9V3z"/></svg>
                    <span class="btn-text">Run Report</span>
                    <span class="btn-spinner">⟳</span>
                </button>
            </div>
        </div>

        <div class="pnl-filters-panel">
            <div class="pnl-filters-grid" id="pnl-filters-grid">
                <div class="pnl-field">
                    <label>Company</label>
                    <select id="pnl-company"></select>
                </div>
                <div class="pnl-field">
                    <label>Filter Based On</label>
                    <select id="pnl-filter-based-on">
                        <option value="Fiscal Year">Fiscal Year</option>
                        <option value="Date Range">Date Range</option>
                    </select>
                </div>
                <div class="pnl-field" id="pnl-fy-from-wrap">
                    <label>From Fiscal Year</label>
                    <select id="pnl-from-fy"></select>
                </div>
                <div class="pnl-field" id="pnl-fy-to-wrap">
                    <label>To Fiscal Year</label>
                    <select id="pnl-to-fy"></select>
                </div>
                <div class="pnl-field" id="pnl-date-from-wrap" style="display:none">
                    <label>Start Date</label>
                    <input type="date" id="pnl-start-date"/>
                </div>
                <div class="pnl-field" id="pnl-date-to-wrap" style="display:none">
                    <label>End Date</label>
                    <input type="date" id="pnl-end-date"/>
                </div>
                <div class="pnl-field">
                    <label>Periodicity</label>
                    <select id="pnl-periodicity">
                        <option value="Monthly">Monthly</option>
                        <option value="Quarterly">Quarterly</option>
                        <option value="Half-Yearly">Half-Yearly</option>
                        <option value="Yearly" selected>Yearly</option>
                    </select>
                </div>
                <div class="pnl-field">
                    <label>Currency</label>
                    <select id="pnl-currency">
                        <option value="">Company Default</option>
                    </select>
                </div>
                <div class="pnl-field">
                    <label>View</label>
                    <select id="pnl-view">
                        <option value="Report">Report View</option>
                        <option value="Growth">Growth View</option>
                        <option value="Margin">Margin View</option>
                    </select>
                </div>
            </div>
            <div class="pnl-filters-row2">
                <label class="pnl-check-field">
                    <input type="checkbox" id="pnl-accum" checked/>
                    <span>Accumulated Values</span>
                </label>
                <label class="pnl-check-field">
                    <input type="checkbox" id="pnl-show-zero"/>
                    <span>Show Zero Values</span>
                </label>
                <label class="pnl-check-field">
                    <input type="checkbox" id="pnl-default-book" checked/>
                    <span>Include Default Book Entries</span>
                </label>
            </div>
        </div>

        <div class="pnl-body" id="pnl-body">
            <div class="pnl-placeholder">
                <div class="ph-icon">📈</div>
                <p>Configure your filters and click <strong>Run Report</strong> to generate the Profit &amp; Loss statement.</p>
            </div>
        </div>

        <div class="pnl-footer" id="pnl-footer" style="display:none">
            Generated on <span id="pnl-gen-time"></span> &nbsp;·&nbsp; Data from <strong id="pnl-company-name"></strong>
        </div>
        `;
    }

    // ── Render body content ──────────────────────────────────────────────────
    function renderResults() {
        var $b = $("#pnl-body");
        if (state.loading) {
            $b.html('<div class="pnl-loader"><div class="pnl-spinner"></div><p style="color:#6b7280;font-size:14px">Fetching financial data…</p></div>');
            return;
        }
        if (!state.data) return;

        var currency = getCurrency();
        var kpiHtml = buildKpiCards(currency);
        var chartHtml = buildChartCard();
        var tableHtml = buildTableCard(currency);

        $b.html('<div class="pnl-kpis" id="pnl-kpis">' + kpiHtml + '</div>' +
                '<div class="pnl-content-grid">' + chartHtml + tableHtml + '</div>');

        renderChart();
        bindTableEvents();

        // Footer
        $("#pnl-gen-time").text(frappe.datetime.now_datetime());
        $("#pnl-company-name").text(state.company);
        $("#pnl-footer").show();
    }

    // ── KPI Cards ────────────────────────────────────────────────────────────
    function buildKpiCards(currency) {
        var summary = state.summary || [];
        var net_income = 0, net_expense = 0, net_profit = 0;

        for (var i = 0; i < summary.length; i++) {
            var s = summary[i];
            if (s.label && s.label.toLowerCase().includes("income")) net_income = s.value || 0;
            if (s.label && s.label.toLowerCase().includes("expense")) net_expense = s.value || 0;
            if (s.label && s.label.toLowerCase().includes("profit") || s.label === "Net Profit") net_profit = s.value || 0;
        }

        var margin = net_income !== 0 ? ((net_profit / net_income) * 100).toFixed(1) : "0.0";
        var marginClass = parseFloat(margin) >= 0 ? "positive" : "negative";
        var profitClass = net_profit >= 0 ? "positive" : "negative";

        return `
            <div class="pnl-kpi-card pnl-kpi-income">
                <div class="kpi-icon">💰</div>
                <div class="kpi-label">Total Income</div>
                <div class="kpi-value positive">${fmt_currency(net_income, currency)}</div>
                <span class="kpi-badge up">↑ Revenue</span>
            </div>
            <div class="pnl-kpi-card pnl-kpi-expense">
                <div class="kpi-icon">💸</div>
                <div class="kpi-label">Total Expenses</div>
                <div class="kpi-value" style="color:#d97706">${fmt_currency(net_expense, currency)}</div>
                <span class="kpi-badge neutral">Cost Base</span>
            </div>
            <div class="pnl-kpi-card pnl-kpi-profit">
                <div class="kpi-icon">📈</div>
                <div class="kpi-label">Net Profit / Loss</div>
                <div class="kpi-value ${profitClass}">${fmt_currency(net_profit, currency)}</div>
                <span class="kpi-badge ${net_profit >= 0 ? 'up' : 'down'}">${net_profit >= 0 ? '▲ Profit' : '▼ Loss'}</span>
            </div>
            <div class="pnl-kpi-card pnl-kpi-ratio">
                <div class="kpi-icon">📐</div>
                <div class="kpi-label">Profit Margin</div>
                <div class="kpi-value ${marginClass}">${margin}%</div>
                <span class="kpi-badge ${parseFloat(margin) >= 0 ? 'up' : 'down'}">${parseFloat(margin) >= 0 ? 'Healthy' : 'Negative'}</span>
            </div>
        `;
    }

    // ── Chart Card ────────────────────────────────────────────────────────────
    function buildChartCard() {
        return `
            <div class="pnl-chart-card">
                <div class="pnl-card-header">
                    <div class="pnl-card-title">Financial Overview</div>
                    <div class="pnl-chart-tabs">
                        <button class="pnl-chart-tab active" data-type="bar">Bar</button>
                        <button class="pnl-chart-tab" data-type="line">Line</button>
                    </div>
                </div>
                <div class="pnl-chart-wrap">
                    <canvas id="pnl-chart"></canvas>
                </div>
            </div>
        `;
    }

    function renderChart() {
        ensureChartJs(function() {
            var cd = state.chart_data;
            if (!cd || !cd.data) return;

            if (state.chart_instance) {
                state.chart_instance.destroy();
                state.chart_instance = null;
            }

            var ctx = document.getElementById("pnl-chart");
            if (!ctx) return;

            var labels = cd.data.labels || [];
            var datasets = (cd.data.datasets || []).map(function(ds, i) {
                var colors = [
                    { bg: "rgba(16,185,129,0.15)", border: "#10b981" },
                    { bg: "rgba(245,158,11,0.15)", border: "#f59e0b" },
                    { bg: "rgba(99,102,241,0.15)", border: "#6366f1" },
                ];
                var c = colors[i % colors.length];
                return {
                    label: ds.name,
                    data: ds.values,
                    backgroundColor: c.bg,
                    borderColor: c.border,
                    borderWidth: 2.5,
                    tension: 0.4,
                    fill: state.chart_type === "line",
                    pointBackgroundColor: c.border,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    borderRadius: state.chart_type === "bar" ? 6 : 0,
                };
            });

            state.chart_instance = new Chart(ctx, {
                type: state.chart_type,
                data: { labels: labels, datasets: datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: "index", intersect: false },
                    plugins: {
                        legend: {
                            position: "top",
                            labels: { font: { size: 12, weight: "600" }, usePointStyle: true, pointStyleWidth: 12, padding: 20 }
                        },
                        tooltip: {
                            backgroundColor: "#1a1f36",
                            titleColor: "#fff",
                            bodyColor: "rgba(255,255,255,0.8)",
                            padding: 12,
                            cornerRadius: 10,
                            callbacks: {
                                label: function(ctx) {
                                    var v = ctx.parsed.y || 0;
                                    return " " + ctx.dataset.label + ": " + fmt_currency(v, getCurrency());
                                }
                            }
                        }
                    },
                    scales: {
                        x: { grid: { display: false }, ticks: { font: { size: 12 } } },
                        y: {
                            grid: { color: "rgba(0,0,0,0.05)" },
                            ticks: {
                                font: { size: 11 },
                                callback: function(v) {
                                    var abs = Math.abs(v);
                                    if (abs >= 1e6) return (v/1e6).toFixed(1)+"M";
                                    if (abs >= 1e3) return (v/1e3).toFixed(0)+"K";
                                    return v;
                                }
                            }
                        }
                    }
                }
            });

            // chart type toggle
            $(".pnl-chart-tab").off("click").on("click", function() {
                $(".pnl-chart-tab").removeClass("active");
                $(this).addClass("active");
                state.chart_type = $(this).data("type");
                renderChart();
            });
        });
    }

    // ── Visible columns (skip hidden like 'currency') ─────────────────────────
    function getVisibleColumns() {
        return (state.columns || []).filter(function(c) { return !c.hidden; });
    }

    // ── Table Card ────────────────────────────────────────────────────────────
    function buildTableCard(currency) {
        var colHeaders = buildColumnHeaders();
        var rows = buildTableRows(currency);

        return `
            <div class="pnl-table-card">
                <div class="pnl-table-card-header">
                    <div class="pnl-card-title">Account Breakdown</div>
                    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                        <div class="pnl-view-pills" id="pnl-view-pills">
                            <button class="pnl-view-pill ${state.selected_view==='Report'?'active':''}" data-view="Report">Report</button>
                            <button class="pnl-view-pill ${state.selected_view==='Growth'?'active':''}" data-view="Growth">Growth</button>
                            <button class="pnl-view-pill ${state.selected_view==='Margin'?'active':''}" data-view="Margin">Margin</button>
                        </div>
                        <div class="pnl-search-box">
                            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                            <input class="pnl-search-input" id="pnl-search" type="text" placeholder="Search accounts…"/>
                        </div>
                        <div class="pnl-table-actions">
                            <button class="pnl-action-btn" id="pnl-expand-all">⊞ Expand All</button>
                            <button class="pnl-action-btn" id="pnl-collapse-all">⊟ Collapse All</button>
                            <button class="pnl-action-btn primary" id="pnl-export-btn">↓ Export CSV</button>
                        </div>
                    </div>
                </div>
                <div class="pnl-table-scroll">
                    <table class="pnl-table" id="pnl-table">
                        <thead><tr>${colHeaders}</tr></thead>
                        <tbody id="pnl-tbody">${rows}</tbody>
                    </table>
                </div>
            </div>
        `;
    }

    function buildColumnHeaders() {
        var cols = getVisibleColumns();
        var html = '<th>Account</th>';
        for (var i = 1; i < cols.length; i++) {
            html += '<th class="num">' + escHtml(cols[i].label || "") + '</th>';
        }
        return html;
    }

    function buildTableRows(currency, searchText) {
        var rows = state.data || [];
        var cols = getVisibleColumns();
        var html = "";
        var search = (searchText || "").toLowerCase();

        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            if (!row) continue;

            var accountName = row.account_name || row.section_name || "";
            var isTotal = accountName.includes("Total") || accountName.includes("total");
            var isNetProfit = accountName.includes("Profit for the year") || accountName.includes("Profit / Loss");
            var isGroup = row.is_group === 1;
            var isSection = !row.parent_account && !row.parent_section && !isTotal && !isNetProfit && isGroup;
            var isBlank = !accountName;
            var indent = parseInt(row.indent) || 0;

            // Search filter
            if (search && accountName.toLowerCase().indexOf(search) === -1) continue;

            // Visibility based on expand state
            if (!isNetProfit && !isTotal && !isSection) {
                var parentKey = row.parent_account || row.parent_section || "";
                if (parentKey && state.expanded[parentKey] === false) continue;
            }

            var rowClass = "";
            if (isNetProfit) rowClass = "row-net-profit";
            else if (isTotal) rowClass = "row-total";
            else if (isSection) rowClass = "row-section-header";
            else if (isGroup) rowClass = "row-group-header";

            if (isBlank) { html += '<tr><td colspan="' + (cols.length) + '" style="padding:4px"></td></tr>'; continue; }

            html += '<tr class="' + rowClass + '" data-account="' + escHtml(accountName) + '">';

            // Account name cell
            var indentPx = indent * 18;
            var toggleHtml = "";
            var iconHtml = "";

            if (isGroup && !isTotal && !isNetProfit) {
                var isOpen = state.expanded[accountName] !== false;
                toggleHtml = '<span class="pnl-toggle ' + (isOpen ? "open" : "") + '" data-acct="' + escHtml(accountName) + '">▶</span>';
            } else if (!isTotal && !isNetProfit && !isSection) {
                toggleHtml = '<span class="pnl-toggle-spacer"></span>';
            }

            if (isSection) {
                iconHtml = '<span class="pnl-acct-icon ' + (accountName.toLowerCase().includes("income") ? "icon-income" : "icon-expense") + '">' +
                    (accountName.toLowerCase().includes("income") ? "↑" : "↓") + '</span>';
            } else if (isNetProfit) {
                iconHtml = '<span class="pnl-acct-icon icon-profit">≡</span>';
            }

            html += '<td><div class="pnl-account-cell">' +
                '<span class="pnl-indent" style="min-width:' + indentPx + 'px"></span>' +
                toggleHtml + iconHtml +
                '<span>' + escHtml(accountName) + '</span>' +
                '</div></td>';

            // Value cells
            for (var j = 1; j < cols.length; j++) {
                var col = cols[j];
                var fn = col.fieldname;
                var val = row[fn];

                if (val === "" || val === null || val === undefined) {
                    html += '<td class="num"></td>';
                    continue;
                }

                var formatted = "";
                var numClass = "";

                if (col.fieldtype === "Currency") {
                    var n = parseFloat(val) || 0;
                    if (state.selected_view === "Report") {
                        formatted = fmt_currency(n, currency);
                        numClass = n > 0 ? "num-positive" : n < 0 ? "num-negative" : "num-zero";
                    } else if (state.selected_view === "Growth") {
                        if (fn === "total") {
                            formatted = fmt_currency(n, currency);
                        } else {
                            formatted = (n >= 0 ? "+" : "") + n + "%";
                            numClass = n > 0 ? "num-positive" : n < 0 ? "num-negative" : "num-zero";
                        }
                    } else { // Margin
                        formatted = n + "%";
                        numClass = n > 0 ? "num-positive" : n < 0 ? "num-negative" : "num-zero";
                    }
                } else {
                    formatted = escHtml(String(val));
                }

                if (isNetProfit) {
                    var nv = parseFloat(val) || 0;
                    html += '<td class="num"><span class="' + (nv >= 0 ? "net-positive" : "net-negative") + '">' + formatted + '</span></td>';
                } else {
                    html += '<td class="num ' + numClass + '">' + formatted + '</td>';
                }
            }

            html += '</tr>';
        }
        return html;
    }

    // ── Table event binding ───────────────────────────────────────────────────
    function bindTableEvents() {
        // Toggle expand/collapse
        $("#pnl-tbody").off("click", ".pnl-toggle").on("click", ".pnl-toggle", function(e) {
            e.stopPropagation();
            var acct = $(this).data("acct");
            if (state.expanded[acct] === false) {
                state.expanded[acct] = true;
            } else {
                state.expanded[acct] = false;
            }
            rebuildTableBody(getCurrency());
        });

        // Search
        $("#pnl-search").off("input").on("input", function() {
            rebuildTableBody(getCurrency(), $(this).val());
        });

        // Expand / Collapse all
        $("#pnl-expand-all").off("click").on("click", function() {
            (state.data || []).forEach(function(r) {
                if (r && r.is_group === 1) state.expanded[r.account_name] = true;
            });
            rebuildTableBody(getCurrency());
        });
        $("#pnl-collapse-all").off("click").on("click", function() {
            (state.data || []).forEach(function(r) {
                if (r && r.is_group === 1) state.expanded[r.account_name] = false;
            });
            rebuildTableBody(getCurrency());
        });

        // View pills (Growth/Margin/Report quick switch without re-running)
        $("#pnl-view-pills").off("click", ".pnl-view-pill").on("click", ".pnl-view-pill", function() {
            $(".pnl-view-pill").removeClass("active");
            $(this).addClass("active");
            var v = $(this).data("view");
            state.selected_view = v;
            $("#pnl-view").val(v);
            // Re-run the report with the new view so backend computes Growth/Margin correctly
            runReport();
        });

        // Export CSV
        $("#pnl-export-btn").off("click").on("click", function() {
            exportCsv();
        });
    }

    function rebuildTableBody(currency, searchText) {
        $("#pnl-tbody").html(buildTableRows(currency, searchText));
        // re-bind toggle events
        $("#pnl-tbody").off("click", ".pnl-toggle").on("click", ".pnl-toggle", function(e) {
            e.stopPropagation();
            var acct = $(this).data("acct");
            state.expanded[acct] = state.expanded[acct] === false ? true : false;
            rebuildTableBody(getCurrency(), $("#pnl-search").val());
        });
    }

    // ── CSV Export ────────────────────────────────────────────────────────────
    function exportCsv() {
        var rows = state.data || [];
        var cols = getVisibleColumns();
        var lines = [];

        // Header
        lines.push(cols.map(function(c) { return '"' + (c.label || "") + '"'; }).join(","));

        rows.forEach(function(row) {
            if (!row) return;
            var cells = cols.map(function(col) {
                var val = col.fieldname === "account" ? (row.account_name || "") : (row[col.fieldname] || "");
                return '"' + String(val).replace(/"/g, '""') + '"';
            });
            lines.push(cells.join(","));
        });

        var blob = new Blob([lines.join("\n")], { type: "text/csv" });
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "profit_and_loss_" + (state.company || "company") + "_" + frappe.datetime.nowdate() + ".csv";
        a.click();
    }

    // ── Load metadata ─────────────────────────────────────────────────────────
    function loadMetadata() {
        // Load companies
        frappe.db.get_list("Company", { fields: ["name"], limit: 100 }).then(function(res) {
            var $s = $("#pnl-company");
            $s.empty();
            (res || []).forEach(function(c) {
                var sel = c.name === state.company ? " selected" : "";
                $s.append('<option value="' + escHtml(c.name) + '"' + sel + '>' + escHtml(c.name) + '</option>');
            });
            if (!state.company && res && res[0]) {
                state.company = res[0].name;
                $s.val(state.company);
            }
        });

        // Load fiscal years
        frappe.db.get_list("Fiscal Year", { fields: ["name", "year_start_date", "year_end_date"], order_by: "year_start_date desc", limit: 50 }).then(function(res) {
            state.fiscal_years = res || [];
            var $from = $("#pnl-from-fy");
            var $to = $("#pnl-to-fy");
            $from.empty(); $to.empty();

            (res || []).forEach(function(fy) {
                $from.append('<option value="' + escHtml(fy.name) + '">' + escHtml(fy.name) + '</option>');
                $to.append('<option value="' + escHtml(fy.name) + '">' + escHtml(fy.name) + '</option>');
            });

            // Default to current fiscal year
            var today = frappe.datetime.get_today();
            var currentFy = null;
            for (var i = 0; i < (res || []).length; i++) {
                if (today >= res[i].year_start_date && today <= res[i].year_end_date) {
                    currentFy = res[i].name;
                    break;
                }
            }
            if (!currentFy && res && res[0]) currentFy = res[0].name;
            if (currentFy) {
                state.from_fiscal_year = currentFy;
                state.to_fiscal_year = currentFy;
                $from.val(currentFy);
                $to.val(currentFy);
            }
            // Auto-run once defaults are ready
            scheduleRun();
        });

        // Load currencies
        frappe.db.get_list("Currency", { fields: ["name"], filters: [["enabled", "=", 1]], limit: 200 }).then(function(res) {
            var $c = $("#pnl-currency");
            $c.empty();
            $c.append('<option value="">Company Default</option>');
            (res || []).forEach(function(cur) {
                $c.append('<option value="' + escHtml(cur.name) + '">' + escHtml(cur.name) + '</option>');
            });
        });
    }

    // ── Debounced auto-run (300 ms after last change) ─────────────────────────
    var autoRunTimer = null;
    function scheduleRun() {
        clearTimeout(autoRunTimer);
        autoRunTimer = setTimeout(function() { runReport(); }, 300);
    }

    // ── Bind filter controls ──────────────────────────────────────────────────
    function bindControls() {
        $("#pnl-company").on("change", function() { state.company = $(this).val(); updateHeaderSub(); scheduleRun(); });
        $("#pnl-filter-based-on").on("change", function() {
            state.filter_based_on = $(this).val();
            toggleDateFyFields();
            scheduleRun();
        });
        $("#pnl-from-fy").on("change", function() { state.from_fiscal_year = $(this).val(); scheduleRun(); });
        $("#pnl-to-fy").on("change", function() { state.to_fiscal_year = $(this).val(); scheduleRun(); });
        $("#pnl-start-date").on("change", function() { state.period_start_date = $(this).val(); scheduleRun(); });
        $("#pnl-end-date").on("change", function() { state.period_end_date = $(this).val(); scheduleRun(); });
        $("#pnl-periodicity").on("change", function() { state.periodicity = $(this).val(); scheduleRun(); });
        $("#pnl-currency").on("change", function() { state.presentation_currency = $(this).val(); scheduleRun(); });
        $("#pnl-view").on("change", function() { state.selected_view = $(this).val(); scheduleRun(); });
        $("#pnl-accum").on("change", function() { state.accumulated_values = $(this).is(":checked") ? 1 : 0; scheduleRun(); });
        $("#pnl-show-zero").on("change", function() { state.show_zero_values = $(this).is(":checked") ? 1 : 0; scheduleRun(); });
        $("#pnl-default-book").on("change", function() { state.include_default_book_entries = $(this).is(":checked") ? 1 : 0; scheduleRun(); });

        $("#pnl-run-btn").on("click", function() { clearTimeout(autoRunTimer); runReport(); });

        // Enter key on any filter
        $(".pnl-filters-panel").on("keydown", function(e) {
            if (e.key === "Enter") { clearTimeout(autoRunTimer); runReport(); }
        });
    }

    function toggleDateFyFields() {
        if (state.filter_based_on === "Fiscal Year") {
            $("#pnl-fy-from-wrap, #pnl-fy-to-wrap").show();
            $("#pnl-date-from-wrap, #pnl-date-to-wrap").hide();
        } else {
            $("#pnl-fy-from-wrap, #pnl-fy-to-wrap").hide();
            $("#pnl-date-from-wrap, #pnl-date-to-wrap").show();
        }
    }

    function updateHeaderSub() {
        var sub = state.company ? state.company + " · " : "";
        sub += state.from_fiscal_year || "";
        if (state.to_fiscal_year && state.to_fiscal_year !== state.from_fiscal_year) sub += " – " + state.to_fiscal_year;
        if (!sub) sub = "Select filters and run the report";
        $("#pnl-header-sub").text(sub);
    }

    // ── Run Report ────────────────────────────────────────────────────────────
    function runReport() {
        if (!state.company) { frappe.msgprint("Please select a Company."); return; }
        if (state.filter_based_on === "Fiscal Year" && !state.from_fiscal_year) {
            frappe.msgprint("Please select a Fiscal Year."); return;
        }
        if (state.filter_based_on === "Date Range" && (!state.period_start_date || !state.period_end_date)) {
            frappe.msgprint("Please select Start Date and End Date."); return;
        }

        state.loading = true;
        state.expanded = {};
        renderResults();
        $("#pnl-run-btn").addClass("loading");

        var filters = {
            company: state.company,
            filter_based_on: state.filter_based_on,
            periodicity: state.periodicity,
            accumulated_values: state.accumulated_values,
            show_zero_values: state.show_zero_values,
            include_default_book_entries: state.include_default_book_entries,
            selected_view: state.selected_view,
        };
        if (state.filter_based_on === "Fiscal Year") {
            filters.from_fiscal_year = state.from_fiscal_year;
            filters.to_fiscal_year = state.to_fiscal_year || state.from_fiscal_year;
        } else {
            filters.period_start_date = state.period_start_date;
            filters.period_end_date = state.period_end_date;
        }
        if (state.presentation_currency) filters.presentation_currency = state.presentation_currency;
        if (state.finance_book) filters.finance_book = state.finance_book;

        frappe.call({
            method: "frappe.desk.query_report.run",
            args: {
                report_name: "Custom Profit and Loss Statement",
                filters: filters,
                is_tree: true,
                parent_field: "parent_account",
            },
            callback: function(r) {
                state.loading = false;
                $("#pnl-run-btn").removeClass("loading");

                if (r && r.message) {
                    var msg = r.message;
                    state.columns = msg.columns || [];
                    state.data = msg.result || [];
                    state.summary = msg.report_summary || [];
                    state.chart_data = msg.chart || null;

                    updateHeaderSub();
                    renderResults();
                } else {
                    frappe.msgprint("No data returned. Please check your filters.");
                    $("#pnl-body").html('<div class="pnl-placeholder"><div class="ph-icon">⚠️</div><p>No data found for the selected filters.</p></div>');
                }
            },
            error: function(r) {
                state.loading = false;
                $("#pnl-run-btn").removeClass("loading");
                var msg = (r && r.message) || "An error occurred while fetching the report.";
                frappe.msgprint(msg);
                $("#pnl-body").html('<div class="pnl-placeholder"><div class="ph-icon">❌</div><p>' + escHtml(String(msg)) + '</p></div>');
            }
        });
    }

    // ── Bootstrap ─────────────────────────────────────────────────────────────
    $root.html(buildShell());
    loadMetadata();
    bindControls();
};
