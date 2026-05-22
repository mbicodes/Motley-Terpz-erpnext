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
            /* ── Google Font ── */
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

            /* ── Animations ── */
            @keyframes pnl-spin    { to { transform: rotate(360deg); } }
            @keyframes pnl-fade-up { from { opacity:0; transform:translateY(14px); } to { opacity:1; transform:translateY(0); } }
            @keyframes pnl-shimmer { from { background-position: -600px 0; } to { background-position: 600px 0; } }
            @keyframes pnl-pulse-ring {
                0%   { box-shadow: 0 0 0 0 rgba(99,102,241,0.35); }
                70%  { box-shadow: 0 0 0 8px rgba(99,102,241,0); }
                100% { box-shadow: 0 0 0 0 rgba(99,102,241,0); }
            }

            /* ── Root ── */
            #pnl-root {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #eef0f6;
                min-height: 100vh;
                padding: 0;
                -webkit-font-smoothing: antialiased;
            }

            /* ── Scrollbar ── */
            #pnl-root ::-webkit-scrollbar { width: 6px; height: 6px; }
            #pnl-root ::-webkit-scrollbar-track { background: #f1f5f9; }
            #pnl-root ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 99px; }
            #pnl-root ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

            /* ═══════════════════════════════════════
               HEADER
            ═══════════════════════════════════════ */
            .pnl-header {
                background:
                    radial-gradient(ellipse 80% 60% at 10% -10%, rgba(99,102,241,0.28) 0%, transparent 55%),
                    radial-gradient(ellipse 60% 50% at 90% 110%, rgba(16,185,129,0.18) 0%, transparent 55%),
                    linear-gradient(160deg, #0f1225 0%, #1e2347 45%, #151929 100%);
                padding: 26px 40px 22px;
                color: #fff;
                position: relative;
                overflow: hidden;
                border-bottom: 1px solid rgba(255,255,255,0.06);
            }
            /* Dot-grid texture */
            .pnl-header::before {
                content: '';
                position: absolute; inset: 0;
                background-image: radial-gradient(rgba(255,255,255,0.04) 1px, transparent 1px);
                background-size: 24px 24px;
                pointer-events: none;
            }
            .pnl-header-inner {
                position: relative; z-index: 1;
                display: flex; align-items: center; justify-content: space-between;
                flex-wrap: wrap; gap: 14px;
            }
            .pnl-title-block { display: flex; align-items: center; gap: 16px; }
            .pnl-logo-icon {
                width: 50px; height: 50px;
                background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                border-radius: 15px;
                display: flex; align-items: center; justify-content: center;
                font-size: 24px;
                box-shadow: 0 0 0 1px rgba(255,255,255,0.12), 0 8px 24px rgba(99,102,241,0.5);
            }
            .pnl-main-title {
                font-size: 22px; font-weight: 800; letter-spacing: -0.5px; margin: 0;
                color: #fff;
            }
            .pnl-subtitle {
                font-size: 12.5px; color: rgba(255,255,255,0.5);
                margin: 3px 0 0; letter-spacing: 0.1px;
            }
            /* Header stat chips */
            .pnl-header-chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 2px; }
            .pnl-chip {
                display: inline-flex; align-items: center; gap: 5px;
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 20px; padding: 3px 10px;
                font-size: 11.5px; font-weight: 500; color: rgba(255,255,255,0.75);
                backdrop-filter: blur(4px);
            }
            .pnl-chip-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
            .pnl-run-btn {
                background: linear-gradient(135deg, #6366f1 0%, #7c3aed 100%);
                border: none; color: #fff;
                padding: 11px 26px; border-radius: 12px;
                font-size: 13.5px; font-weight: 700; cursor: pointer;
                box-shadow: 0 1px 0 rgba(255,255,255,0.15) inset,
                            0 6px 20px rgba(99,102,241,0.55);
                transition: all 0.2s; display: flex; align-items: center; gap: 8px;
                white-space: nowrap; letter-spacing: 0.1px;
            }
            .pnl-run-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 1px 0 rgba(255,255,255,0.15) inset, 0 10px 28px rgba(99,102,241,0.65);
            }
            .pnl-run-btn:active { transform: translateY(0); }
            .pnl-run-btn.loading { animation: pnl-pulse-ring 1.2s ease-out infinite; }
            .pnl-run-btn .btn-spinner { display: none; font-size: 16px; }
            .pnl-run-btn.loading .btn-text { display: none; }
            .pnl-run-btn.loading .btn-spinner { display: inline-block; }

            /* ═══════════════════════════════════════
               FILTER PANEL
            ═══════════════════════════════════════ */
            .pnl-filters-panel {
                background: #fff;
                border-bottom: 1px solid #e8eaf0;
                padding: 16px 40px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            }
            .pnl-filters-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
                gap: 10px 14px;
                align-items: end;
            }
            .pnl-field { display: flex; flex-direction: column; gap: 5px; }
            .pnl-field label {
                font-size: 10.5px; font-weight: 700; color: #94a3b8;
                text-transform: uppercase; letter-spacing: 0.7px;
            }
            .pnl-field select,
            .pnl-field input[type="text"],
            .pnl-field input[type="date"] {
                border: 1.5px solid #e2e8f0;
                border-radius: 9px;
                padding: 7px 10px;
                font-size: 13px; font-weight: 500;
                color: #1e293b;
                background: #f8fafc;
                outline: none;
                transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
                width: 100%;
                box-sizing: border-box;
                font-family: inherit;
            }
            .pnl-field select:hover,
            .pnl-field input:hover { border-color: #c7d2fe; }
            .pnl-field select:focus,
            .pnl-field input:focus {
                border-color: #6366f1;
                box-shadow: 0 0 0 3px rgba(99,102,241,0.14);
                background: #fff;
            }
            /* Custom toggle switch */
            .pnl-filters-row2 {
                margin-top: 14px;
                display: flex; gap: 24px; flex-wrap: wrap; align-items: center;
                padding-top: 14px;
                border-top: 1px dashed #e8eaf0;
            }
            .pnl-check-field {
                display: flex; align-items: center; gap: 9px; cursor: pointer;
            }
            .pnl-check-field input[type="checkbox"] { display: none; }
            .pnl-toggle-track {
                width: 34px; height: 19px;
                background: #d1d5db; border-radius: 99px;
                position: relative; transition: background 0.2s; flex-shrink: 0;
                cursor: pointer;
            }
            .pnl-toggle-track::after {
                content: '';
                position: absolute; top: 2px; left: 2px;
                width: 15px; height: 15px;
                background: #fff; border-radius: 50%;
                transition: transform 0.2s;
                box-shadow: 0 1px 3px rgba(0,0,0,0.2);
            }
            .pnl-check-field input:checked + .pnl-toggle-track { background: #6366f1; }
            .pnl-check-field input:checked + .pnl-toggle-track::after { transform: translateX(15px); }
            .pnl-check-field span {
                font-size: 12.5px; color: #475569; font-weight: 500; cursor: pointer;
                user-select: none;
            }

            /* ═══════════════════════════════════════
               BODY
            ═══════════════════════════════════════ */
            .pnl-body { padding: 24px 40px 32px; }

            /* ── Empty state ── */
            .pnl-placeholder {
                background: #fff; border-radius: 20px;
                padding: 72px 24px; text-align: center;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.04);
                border: 1px solid #f1f5f9;
                color: #94a3b8;
            }
            .pnl-placeholder .ph-icon {
                font-size: 56px; margin-bottom: 16px;
                display: block; filter: grayscale(0.2);
            }
            .pnl-placeholder p { font-size: 15px; color: #64748b; line-height: 1.6; }
            .pnl-placeholder strong { color: #6366f1; }

            /* ── Loading state ── */
            .pnl-loader {
                background: #fff; border-radius: 20px;
                padding: 72px 24px; text-align: center;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.04);
                border: 1px solid #f1f5f9;
            }
            .pnl-spinner {
                width: 44px; height: 44px;
                border: 3px solid #e2e8f0;
                border-top-color: #6366f1;
                border-radius: 50%;
                animation: pnl-spin 0.65s linear infinite;
                margin: 0 auto 16px;
            }
            .pnl-loader p { color: #64748b; font-size: 14px; font-weight: 500; }

            /* ── Skeleton rows ── */
            .pnl-skeleton-row {
                height: 20px; border-radius: 6px;
                background: linear-gradient(90deg, #f1f5f9 25%, #e8edf4 50%, #f1f5f9 75%);
                background-size: 600px 100%;
                animation: pnl-shimmer 1.4s infinite linear;
                margin: 10px 0;
            }

            /* ═══════════════════════════════════════
               KPI CARDS
            ═══════════════════════════════════════ */
            .pnl-kpis {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 16px;
                margin-bottom: 22px;
            }
            .pnl-kpi-card {
                background: #fff;
                border-radius: 18px;
                padding: 22px 24px 18px;
                box-shadow:
                    0 1px 0 rgba(255,255,255,0.8) inset,
                    0 2px 6px rgba(0,0,0,0.05),
                    0 8px 24px rgba(0,0,0,0.05);
                border: 1px solid rgba(226,232,240,0.8);
                position: relative; overflow: hidden;
                transition: transform 0.2s cubic-bezier(.34,1.56,.64,1), box-shadow 0.2s;
                animation: pnl-fade-up 0.4s ease both;
            }
            .pnl-kpi-card:nth-child(1) { animation-delay: 0.05s; }
            .pnl-kpi-card:nth-child(2) { animation-delay: 0.10s; }
            .pnl-kpi-card:nth-child(3) { animation-delay: 0.15s; }
            .pnl-kpi-card:nth-child(4) { animation-delay: 0.20s; }
            .pnl-kpi-card:hover {
                transform: translateY(-4px) scale(1.01);
                box-shadow: 0 1px 0 rgba(255,255,255,0.8) inset, 0 12px 32px rgba(0,0,0,0.1);
            }
            /* Colored left accent bar */
            .pnl-kpi-card::before {
                content: '';
                position: absolute; top: 0; left: 0; bottom: 0; width: 4px;
                border-radius: 18px 0 0 18px;
            }
            /* Subtle corner glow */
            .pnl-kpi-card::after {
                content: '';
                position: absolute; top: -30px; right: -30px;
                width: 100px; height: 100px; border-radius: 50%;
                opacity: 0.07;
            }
            .pnl-kpi-income::before { background: linear-gradient(180deg, #10b981, #059669); }
            .pnl-kpi-income::after  { background: #10b981; }
            .pnl-kpi-expense::before { background: linear-gradient(180deg, #f59e0b, #d97706); }
            .pnl-kpi-expense::after  { background: #f59e0b; }
            .pnl-kpi-profit::before  { background: linear-gradient(180deg, #6366f1, #8b5cf6); }
            .pnl-kpi-profit::after   { background: #6366f1; }
            .pnl-kpi-ratio::before   { background: linear-gradient(180deg, #0ea5e9, #0284c7); }
            .pnl-kpi-ratio::after    { background: #0ea5e9; }
            .kpi-icon {
                width: 42px; height: 42px; border-radius: 13px;
                display: flex; align-items: center; justify-content: center;
                font-size: 20px; margin-bottom: 14px; position: relative; z-index: 1;
            }
            .pnl-kpi-income .kpi-icon { background: linear-gradient(135deg, #d1fae5, #a7f3d0); }
            .pnl-kpi-expense .kpi-icon { background: linear-gradient(135deg, #fef3c7, #fde68a); }
            .pnl-kpi-profit .kpi-icon  { background: linear-gradient(135deg, #ede9fe, #ddd6fe); }
            .pnl-kpi-ratio .kpi-icon   { background: linear-gradient(135deg, #e0f2fe, #bae6fd); }
            .kpi-label {
                font-size: 11px; font-weight: 700; color: #94a3b8;
                text-transform: uppercase; letter-spacing: 0.7px;
                position: relative; z-index: 1;
            }
            .kpi-value {
                font-size: 28px; font-weight: 800; color: #0f172a;
                margin: 5px 0 8px; letter-spacing: -1px; line-height: 1;
                position: relative; z-index: 1;
            }
            .kpi-value.positive { color: #059669; }
            .kpi-value.negative { color: #dc2626; }
            .kpi-badge {
                display: inline-flex; align-items: center; gap: 4px;
                font-size: 11.5px; font-weight: 700;
                padding: 3px 9px; border-radius: 20px;
                position: relative; z-index: 1;
            }
            .kpi-badge.up     { background: #dcfce7; color: #15803d; }
            .kpi-badge.down   { background: #fee2e2; color: #b91c1c; }
            .kpi-badge.neutral { background: #f1f5f9; color: #64748b; }

            /* ═══════════════════════════════════════
               CONTENT GRID
            ═══════════════════════════════════════ */
            .pnl-content-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 20px;
            }

            /* ═══════════════════════════════════════
               CHART CARD
            ═══════════════════════════════════════ */
            .pnl-chart-card {
                background: #fff; border-radius: 18px;
                padding: 24px 26px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.05);
                border: 1px solid rgba(226,232,240,0.8);
                animation: pnl-fade-up 0.4s 0.1s ease both;
            }
            .pnl-card-header {
                display: flex; align-items: center; justify-content: space-between;
                margin-bottom: 20px; flex-wrap: wrap; gap: 10px;
            }
            .pnl-card-title {
                font-size: 15px; font-weight: 700; color: #0f172a; letter-spacing: -0.2px;
            }
            .pnl-card-subtitle { font-size: 12px; color: #94a3b8; margin-top: 2px; }
            .pnl-chart-tabs { display: flex; gap: 4px; background: #f1f5f9; border-radius: 9px; padding: 3px; }
            .pnl-chart-tab {
                padding: 5px 13px; border-radius: 7px; font-size: 12px; font-weight: 600;
                border: none; background: transparent; color: #64748b;
                cursor: pointer; transition: all 0.15s;
            }
            .pnl-chart-tab:hover { color: #475569; }
            .pnl-chart-tab.active {
                background: #fff; color: #4338ca;
                box-shadow: 0 1px 4px rgba(0,0,0,0.1);
            }
            .pnl-chart-wrap { position: relative; height: 290px; }
            .pnl-chart-wrap canvas { max-height: 290px; }

            /* ═══════════════════════════════════════
               TABLE CARD
            ═══════════════════════════════════════ */
            .pnl-table-card {
                background: #fff; border-radius: 18px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.05);
                border: 1px solid rgba(226,232,240,0.8);
                overflow: hidden;
                animation: pnl-fade-up 0.4s 0.15s ease both;
            }
            .pnl-table-card-header {
                display: flex; align-items: center; justify-content: space-between;
                padding: 18px 24px 16px; flex-wrap: wrap; gap: 12px;
                border-bottom: 1px solid #f1f5f9;
                background: linear-gradient(180deg, #fafbff, #fff);
            }
            .pnl-search-box {
                display: flex; align-items: center; gap: 8px;
                background: #f8fafc; border-radius: 9px; padding: 7px 13px;
                border: 1.5px solid #e2e8f0; transition: all 0.15s;
            }
            .pnl-search-box:focus-within {
                background: #fff; border-color: #6366f1;
                box-shadow: 0 0 0 3px rgba(99,102,241,0.12);
            }
            .pnl-search-box svg { color: #94a3b8; flex-shrink: 0; }
            .pnl-search-input {
                border: none; background: transparent; outline: none;
                font-size: 13px; color: #1e293b; width: 190px; font-family: inherit;
            }
            .pnl-search-input::placeholder { color: #94a3b8; }
            .pnl-table-actions { display: flex; gap: 8px; flex-wrap: wrap; }
            .pnl-action-btn {
                padding: 7px 14px; border-radius: 9px; font-size: 12px; font-weight: 600;
                border: 1.5px solid #e2e8f0; background: #f8fafc; color: #475569;
                cursor: pointer; transition: all 0.15s;
                display: flex; align-items: center; gap: 5px;
                font-family: inherit;
            }
            .pnl-action-btn:hover { background: #f1f5f9; border-color: #c7d2fe; color: #4338ca; }
            .pnl-action-btn.primary {
                background: linear-gradient(135deg, #6366f1, #7c3aed);
                border-color: transparent; color: #fff;
                box-shadow: 0 2px 8px rgba(99,102,241,0.35);
            }
            .pnl-action-btn.primary:hover {
                background: linear-gradient(135deg, #4f46e5, #6d28d9);
                box-shadow: 0 4px 12px rgba(99,102,241,0.45);
                transform: translateY(-1px);
            }

            /* ═══════════════════════════════════════
               TABLE
            ═══════════════════════════════════════ */
            .pnl-table-scroll { overflow-x: auto; }
            .pnl-table {
                width: 100%; border-collapse: collapse; font-size: 13px;
            }
            /* Sticky header */
            .pnl-table thead {
                position: sticky; top: 0; z-index: 2;
            }
            .pnl-table thead tr {
                background: #f8fafc;
                border-bottom: 2px solid #e2e8f0;
            }
            .pnl-table thead th {
                padding: 12px 16px; text-align: left;
                font-size: 10.5px; font-weight: 700; color: #94a3b8;
                text-transform: uppercase; letter-spacing: 0.8px;
                white-space: nowrap;
                background: #f8fafc;
            }
            .pnl-table thead th.num { text-align: right; }
            /* Zebra stripe on leaf rows */
            .pnl-table tbody tr.row-leaf:nth-child(even) td { background: #fafbff; }
            .pnl-table tbody tr { border-bottom: 1px solid #f1f5f9; transition: background 0.12s; }
            .pnl-table tbody tr:not(.row-section-header):not(.row-total):not(.row-net-profit):hover td {
                background: #f0f4ff !important;
            }
            .pnl-table td {
                padding: 9px 16px; color: #334155; vertical-align: middle;
            }
            .pnl-table td.num {
                text-align: right; font-variant-numeric: tabular-nums; font-feature-settings: "tnum";
            }

            /* ── Row: Section Header (Income / Expense) ── */
            .row-section-header td {
                background: linear-gradient(90deg, #eef2ff 0%, #f5f3ff 100%) !important;
                font-weight: 800; font-size: 13px; color: #312e81;
                border-top: 2px solid #c7d2fe;
                border-bottom: 2px solid #c7d2fe;
                padding-top: 12px; padding-bottom: 12px;
                letter-spacing: 0.1px;
            }

            /* ── Row: Group Header (sub-section) ── */
            .row-group-header td {
                background: #f8fafc !important;
                font-weight: 600; color: #1e293b;
                font-size: 13px; border-bottom: 1px solid #e8edf4;
            }

            /* ── Row: Total (Total Income / Total Expense) ── */
            .row-total td {
                background: linear-gradient(90deg, #1e293b, #0f172a) !important;
                color: #e2e8f0 !important;
                font-weight: 700; font-size: 13px;
                border-top: 2px solid #334155 !important;
                border-bottom: 2px solid #334155 !important;
                padding-top: 11px; padding-bottom: 11px;
            }
            .row-total td .num-positive { color: #86efac !important; }
            .row-total td .num-negative { color: #fca5a5 !important; }

            /* ── Row: Net Profit / Loss ── */
            .row-net-profit td {
                background: linear-gradient(90deg, #1e1b4b 0%, #312e81 50%, #1e1b4b 100%) !important;
                color: #e0e7ff !important;
                font-weight: 800; font-size: 14px;
                border-top: 3px solid #6366f1 !important;
                border-bottom: 3px solid #6366f1 !important;
                padding-top: 14px; padding-bottom: 14px;
                letter-spacing: -0.2px;
            }
            .row-net-profit td .net-positive { color: #6ee7b7; font-size: 15px; }
            .row-net-profit td .net-negative { color: #fca5a5; font-size: 15px; }

            /* ── Account cell ── */
            .pnl-account-cell { display: flex; align-items: center; }
            .pnl-indent { display: inline-block; flex-shrink: 0; }
            .pnl-toggle {
                width: 20px; height: 20px;
                display: inline-flex; align-items: center; justify-content: center;
                cursor: pointer; color: #cbd5e1; flex-shrink: 0;
                font-size: 9px; transition: transform 0.18s, color 0.15s;
                margin-right: 3px; user-select: none; border-radius: 4px;
            }
            .pnl-toggle:hover { background: #e0e7ff; color: #6366f1; }
            .pnl-toggle.open { transform: rotate(90deg); color: #6366f1; }
            .pnl-toggle-spacer { width: 23px; display: inline-block; flex-shrink: 0; }
            .pnl-acct-icon {
                width: 24px; height: 24px; border-radius: 7px;
                display: inline-flex; align-items: center; justify-content: center;
                font-size: 12px; margin-right: 8px; flex-shrink: 0;
            }
            .icon-income  { background: linear-gradient(135deg, #d1fae5, #a7f3d0); color: #065f46; }
            .icon-expense { background: linear-gradient(135deg, #fef3c7, #fde68a); color: #78350f; }
            .icon-profit  { background: linear-gradient(135deg, #ede9fe, #ddd6fe); color: #4c1d95; }

            /* ── Number colours ── */
            .num-positive { color: #16a34a; font-weight: 600; }
            .num-negative { color: #dc2626; font-weight: 600; }
            .num-zero     { color: #cbd5e1; }

            /* ── View pills ── */
            .pnl-view-pills {
                display: flex; gap: 3px;
                background: #f1f5f9; border-radius: 10px; padding: 3px;
            }
            .pnl-view-pill {
                padding: 5px 14px; border-radius: 8px; font-size: 12px; font-weight: 600;
                cursor: pointer; transition: all 0.15s; color: #64748b;
                border: none; background: transparent; font-family: inherit;
            }
            .pnl-view-pill:hover { color: #475569; }
            .pnl-view-pill.active {
                background: #fff; color: #4338ca;
                box-shadow: 0 1px 4px rgba(0,0,0,0.1), 0 0 0 1px rgba(99,102,241,0.1);
            }

            /* ═══════════════════════════════════════
               FOOTER
            ═══════════════════════════════════════ */
            .pnl-footer {
                text-align: center; padding: 18px 40px 24px;
                font-size: 12px; color: #94a3b8; letter-spacing: 0.1px;
            }
            .pnl-footer strong { color: #6366f1; }

            /* ═══════════════════════════════════════
               RESPONSIVE
            ═══════════════════════════════════════ */
            @media (max-width: 900px) {
                .pnl-header { padding: 20px 20px; }
                .pnl-filters-panel { padding: 14px 20px; }
                .pnl-body { padding: 16px 20px 24px; }
                .pnl-filters-grid { grid-template-columns: 1fr 1fr; }
            }
            @media (max-width: 600px) {
                .pnl-filters-grid { grid-template-columns: 1fr; }
                .pnl-kpis { grid-template-columns: 1fr 1fr; }
                .pnl-kpi-card { padding: 16px; }
                .kpi-value { font-size: 22px; }
                .pnl-table-card-header { flex-direction: column; align-items: flex-start; }
                .pnl-search-input { width: 140px; }
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
                    <span class="pnl-toggle-track"></span>
                    <span>Accumulated Values</span>
                </label>
                <label class="pnl-check-field">
                    <input type="checkbox" id="pnl-show-zero"/>
                    <span class="pnl-toggle-track"></span>
                    <span>Show Zero Values</span>
                </label>
                <label class="pnl-check-field">
                    <input type="checkbox" id="pnl-default-book" checked/>
                    <span class="pnl-toggle-track"></span>
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
            Generated on <span id="pnl-gen-time"></span> &nbsp;·&nbsp; <strong id="pnl-company-name"></strong>
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
        var period = state.from_fiscal_year || state.period_start_date || "";
        if (state.to_fiscal_year && state.to_fiscal_year !== state.from_fiscal_year) period += " – " + state.to_fiscal_year;
        return `
            <div class="pnl-chart-card">
                <div class="pnl-card-header">
                    <div>
                        <div class="pnl-card-title">Financial Overview</div>
                        <div class="pnl-card-subtitle">${escHtml(state.company)}${period ? " &nbsp;·&nbsp; " + escHtml(period) : ""}</div>
                    </div>
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

            // Visibility based on expand state — walk up the full ancestor chain
            if (!isNetProfit && !isTotal && !isSection) {
                var parentKey = row.parent_account || row.parent_section || "";
                if (!parentKey) continue; // safety: non-section with no parent, skip
                // Hide if ANY ancestor is collapsed
                var ancestor = parentKey;
                var hidden = false;
                while (ancestor) {
                    if (state.expanded[ancestor] === false) { hidden = true; break; }
                    // find the parent row to walk up further
                    var parentRow = null;
                    for (var pi = 0; pi < rows.length; pi++) {
                        if (rows[pi] && (rows[pi].account === ancestor || rows[pi].section === ancestor)) {
                            parentRow = rows[pi]; break;
                        }
                    }
                    ancestor = parentRow ? (parentRow.parent_account || parentRow.parent_section || "") : "";
                }
                if (hidden) continue;
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
                var accountKey = row.account || row.section || accountName;
                var isOpen = state.expanded[accountKey] !== false;
                toggleHtml = '<span class="pnl-toggle ' + (isOpen ? "open" : "") + '" data-acct="' + escHtml(accountKey) + '">▶</span>';
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
                if (r && r.is_group === 1) {
                    var key = r.account || r.section || r.account_name;
                    state.expanded[key] = true;
                }
            });
            rebuildTableBody(getCurrency());
        });
        $("#pnl-collapse-all").off("click").on("click", function() {
            (state.data || []).forEach(function(r) {
                if (r && r.is_group === 1) {
                    var key = r.account || r.section || r.account_name;
                    state.expanded[key] = false;
                }
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
