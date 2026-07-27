// Copyright (c) 2026, Cannabis Management
// License: GNU General Public License v3. See license.txt
//
// Custom, from-scratch Frappe Page (NOT a Workspace, NOT a modification of
// the existing "Detailed Balance Sheet" Script Report) built to support one
// thing frappe-datatable cannot do: a column that appears only while a row
// carrying data for it is currently expanded/visible, and disappears again
// the instant that row is collapsed. Re-initializing frappe-datatable on
// every expand/collapse to fake this would reset every other expanded
// branch in the tree and be slow at the 10-13k row sizes this report can
// return once transaction/item drill-down is included - so this page
// renders its own plain HTML <table> instead and recomputes visible
// rows/columns with a single O(n) pass (see computeVisibleRowsAndColumns()
// below) on every toggle, search keystroke, and view switch.
//
// Deliberately reuses the exact same backend the existing report already
// uses - frappe.desk.query_report.run() against report_name "Detailed
// Balance Sheet" - so there is no new Python in this app: same filters,
// same is_tree/parent_field contract, same columns/result/chart/
// report_summary shape. See cannabis_management/cannabis_management/report/
// detailed_balance_sheet/detailed_balance_sheet.py for how that payload is
// built, and financial_statements.py (same package) for
// attach_transaction_rows()/get_transaction_detail_columns(), which is
// where the 4 row "kinds" (account group, account leaf, transaction, item)
// and the 12 possible "transaction detail" columns come from. Unlike the
// P&L version of this report, root section headings here are real
// Asset/Liability/Equity accounts (see simplify_root_heading() in the .py)
// rather than synthetic heading rows, and there is no Income/Expense
// concept at all - see the icon/KPI logic below, which is written for this
// report's own vocabulary rather than reused verbatim from the P&L page.
//
// Visual structure/CSS organization mirrors this app's existing
// profit_and_loss_repo.js page closely (same dark-header/light-body
// dashboard aesthetic, same frappe.call pattern, same KPI-cards/chart/
// filters-panel/CSV-export approach). All class/id names here use a
// "dbsd-" prefix (distinct from that page's "pnl-" prefix and the P&L
// Drilldown page's "pld-" prefix) so all three pages' injected <style>
// blocks can coexist in the same desk session without clashing.

frappe.pages["detailed-balance-sheet-drilldown"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Detailed Balance Sheet (Drilldown)",
		single_column: true,
	});

	$(wrapper).find(".page-head").hide();

	var $body = $(page.body);
	$body.html('<div id="dbsd-root"></div>');
	var $root = $("#dbsd-root");

	// ── Every transaction-detail column the shared backend can possibly
	// return (see TRANSACTION_DETAIL_FIELDS in financial_statements.py) - the
	// ONLY columns eligible for live expand/collapse-driven show/hide. Every
	// other column (account, each period, total) is a base column and always
	// renders. Kept in sync with that Python tuple's fieldnames (note the
	// valuation-rate column's fieldname is "rate", not "valuation_rate").
	var TRANSACTION_DETAIL_FIELDNAMES = [
		"posting_date", "voucher_type", "voucher_no", "party", "against",
		"debit", "credit", "item_code", "item_name", "qty", "rate", "amount",
	];

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
		// Matches this report's own filter default (see
		// detailed_balance_sheet.js push() block) - 1, not 0 (unlike the
		// Profit and Loss Drilldown page).
		accumulated_values: 1,
		show_zero_values: 0,
		include_default_book_entries: 1,
		loading: false,
		allRows: [],
		baseColumns: [],
		dynamicColumnDefs: [],
		summary: null,
		chartData: null,
		reportMessage: null,
		expandedState: {},
		lastVisible: [],
		lastDynamicColumns: [],
		fiscal_years: [],
		chart_type: "bar",
		chart_instance: null,
	};

	// ── Inject CSS ──────────────────────────────────────────────────────────
	if (!document.getElementById("dbsd-styles")) {
		var style = document.createElement("style");
		style.id = "dbsd-styles";
		style.textContent = `
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

            @keyframes dbsd-spin    { to { transform: rotate(360deg); } }
            @keyframes dbsd-fade-up { from { opacity:0; transform:translateY(14px); } to { opacity:1; transform:translateY(0); } }
            @keyframes dbsd-pulse-ring {
                0%   { box-shadow: 0 0 0 0 rgba(99,102,241,0.35); }
                70%  { box-shadow: 0 0 0 8px rgba(99,102,241,0); }
                100% { box-shadow: 0 0 0 0 rgba(99,102,241,0); }
            }

            #dbsd-root {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #eef0f6;
                min-height: 100vh;
                padding: 0;
                -webkit-font-smoothing: antialiased;
            }
            #dbsd-root ::-webkit-scrollbar { width: 6px; height: 6px; }
            #dbsd-root ::-webkit-scrollbar-track { background: #f1f5f9; }
            #dbsd-root ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 99px; }
            #dbsd-root ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

            .dbsd-header {
                background:
                    radial-gradient(ellipse 80% 60% at 10% -10%, rgba(14,165,233,0.28) 0%, transparent 55%),
                    radial-gradient(ellipse 60% 50% at 90% 110%, rgba(139,92,246,0.18) 0%, transparent 55%),
                    linear-gradient(160deg, #0f1225 0%, #1e2347 45%, #151929 100%);
                padding: 26px 40px 22px;
                color: #fff;
                position: relative;
                overflow: hidden;
                border-bottom: 1px solid rgba(255,255,255,0.06);
            }
            .dbsd-header::before {
                content: '';
                position: absolute; inset: 0;
                background-image: radial-gradient(rgba(255,255,255,0.04) 1px, transparent 1px);
                background-size: 24px 24px;
                pointer-events: none;
            }
            .dbsd-header-inner { position: relative; z-index: 1; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; }
            .dbsd-title-block { display: flex; align-items: center; gap: 16px; }
            .dbsd-logo-icon {
                width: 50px; height: 50px;
                background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
                border-radius: 15px;
                display: flex; align-items: center; justify-content: center;
                font-size: 24px;
                box-shadow: 0 0 0 1px rgba(255,255,255,0.12), 0 8px 24px rgba(14,165,233,0.5);
            }
            .dbsd-main-title { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; margin: 0; color: #fff; }
            .dbsd-subtitle { font-size: 12.5px; color: rgba(255,255,255,0.5); margin: 3px 0 0; letter-spacing: 0.1px; }
            .dbsd-run-btn {
                background: linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%);
                border: none; color: #fff;
                padding: 11px 26px; border-radius: 12px;
                font-size: 13.5px; font-weight: 700; cursor: pointer;
                box-shadow: 0 1px 0 rgba(255,255,255,0.15) inset, 0 6px 20px rgba(14,165,233,0.55);
                transition: all 0.2s; display: flex; align-items: center; gap: 8px;
                white-space: nowrap; letter-spacing: 0.1px;
            }
            .dbsd-run-btn:hover { transform: translateY(-2px); box-shadow: 0 1px 0 rgba(255,255,255,0.15) inset, 0 10px 28px rgba(14,165,233,0.65); }
            .dbsd-run-btn:active { transform: translateY(0); }
            .dbsd-run-btn.loading { animation: dbsd-pulse-ring 1.2s ease-out infinite; }
            .dbsd-run-btn .btn-spinner { display: none; font-size: 16px; }
            .dbsd-run-btn.loading .btn-text { display: none; }
            .dbsd-run-btn.loading .btn-spinner { display: inline-block; }

            .dbsd-filters-panel { background: #fff; border-bottom: 1px solid #e8eaf0; padding: 16px 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
            .dbsd-filters-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px 14px; align-items: end; }
            .dbsd-field { display: flex; flex-direction: column; gap: 5px; }
            .dbsd-field label { font-size: 10.5px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.7px; }
            .dbsd-field select, .dbsd-field input[type="text"], .dbsd-field input[type="date"] {
                border: 1.5px solid #e2e8f0; border-radius: 9px; padding: 7px 10px;
                font-size: 13px; font-weight: 500; color: #1e293b; background: #f8fafc;
                outline: none; transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
                width: 100%; box-sizing: border-box; font-family: inherit;
            }
            .dbsd-field select:hover, .dbsd-field input:hover { border-color: #bae6fd; }
            .dbsd-field select:focus, .dbsd-field input:focus { border-color: #0ea5e9; box-shadow: 0 0 0 3px rgba(14,165,233,0.14); background: #fff; }
            .dbsd-filters-row2 { margin-top: 14px; display: flex; gap: 24px; flex-wrap: wrap; align-items: center; padding-top: 14px; border-top: 1px dashed #e8eaf0; }
            .dbsd-check-field { display: flex; align-items: center; gap: 9px; cursor: pointer; }
            .dbsd-check-field input[type="checkbox"] { display: none; }
            .dbsd-toggle-track { width: 34px; height: 19px; background: #d1d5db; border-radius: 99px; position: relative; transition: background 0.2s; flex-shrink: 0; cursor: pointer; }
            .dbsd-toggle-track::after { content: ''; position: absolute; top: 2px; left: 2px; width: 15px; height: 15px; background: #fff; border-radius: 50%; transition: transform 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
            .dbsd-check-field input:checked + .dbsd-toggle-track { background: #0ea5e9; }
            .dbsd-check-field input:checked + .dbsd-toggle-track::after { transform: translateX(15px); }
            .dbsd-check-field span { font-size: 12.5px; color: #475569; font-weight: 500; cursor: pointer; user-select: none; }

            .dbsd-body { padding: 24px 40px 32px; }
            .dbsd-warning-banner {
                background: #fffbeb; border: 1px solid #fde68a; color: #92400e;
                border-radius: 12px; padding: 10px 16px; font-size: 12.5px; font-weight: 600;
                margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
            }
            .dbsd-placeholder, .dbsd-loader {
                background: #fff; border-radius: 20px; padding: 72px 24px; text-align: center;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.04);
                border: 1px solid #f1f5f9; color: #94a3b8;
            }
            .dbsd-placeholder .ph-icon { font-size: 56px; margin-bottom: 16px; display: block; filter: grayscale(0.2); }
            .dbsd-placeholder p { font-size: 15px; color: #64748b; line-height: 1.6; }
            .dbsd-placeholder strong { color: #0ea5e9; }
            .dbsd-spinner { width: 44px; height: 44px; border: 3px solid #e2e8f0; border-top-color: #0ea5e9; border-radius: 50%; animation: dbsd-spin 0.65s linear infinite; margin: 0 auto 16px; }
            .dbsd-loader p { color: #64748b; font-size: 14px; font-weight: 500; }

            .dbsd-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 22px; }
            .dbsd-kpi-card {
                background: #fff; border-radius: 18px; padding: 22px 24px 18px;
                box-shadow: 0 1px 0 rgba(255,255,255,0.8) inset, 0 2px 6px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.05);
                border: 1px solid rgba(226,232,240,0.8);
                position: relative; overflow: hidden;
                transition: transform 0.2s cubic-bezier(.34,1.56,.64,1), box-shadow 0.2s;
                animation: dbsd-fade-up 0.4s ease both;
            }
            .dbsd-kpi-card:nth-child(1) { animation-delay: 0.05s; }
            .dbsd-kpi-card:nth-child(2) { animation-delay: 0.10s; }
            .dbsd-kpi-card:nth-child(3) { animation-delay: 0.15s; }
            .dbsd-kpi-card:nth-child(4) { animation-delay: 0.20s; }
            .dbsd-kpi-card:hover { transform: translateY(-4px) scale(1.01); box-shadow: 0 1px 0 rgba(255,255,255,0.8) inset, 0 12px 32px rgba(0,0,0,0.1); }
            .dbsd-kpi-card::before { content: ''; position: absolute; top: 0; left: 0; bottom: 0; width: 4px; border-radius: 18px 0 0 18px; }
            .dbsd-kpi-asset::before     { background: linear-gradient(180deg, #0ea5e9, #0284c7); }
            .dbsd-kpi-liability::before { background: linear-gradient(180deg, #f59e0b, #d97706); }
            .dbsd-kpi-equity::before    { background: linear-gradient(180deg, #8b5cf6, #7c3aed); }
            .dbsd-kpi-pl::before        { background: linear-gradient(180deg, #6366f1, #4338ca); }
            .kpi-icon { width: 42px; height: 42px; border-radius: 13px; display: flex; align-items: center; justify-content: center; font-size: 20px; margin-bottom: 14px; }
            .dbsd-kpi-asset .kpi-icon     { background: linear-gradient(135deg, #e0f2fe, #bae6fd); }
            .dbsd-kpi-liability .kpi-icon { background: linear-gradient(135deg, #fef3c7, #fde68a); }
            .dbsd-kpi-equity .kpi-icon    { background: linear-gradient(135deg, #ede9fe, #ddd6fe); }
            .dbsd-kpi-pl .kpi-icon        { background: linear-gradient(135deg, #e0e7ff, #c7d2fe); }
            .kpi-label { font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.7px; }
            .kpi-value { font-size: 26px; font-weight: 800; color: #0f172a; margin: 5px 0 8px; letter-spacing: -1px; line-height: 1; }
            .kpi-value.positive { color: #059669; }
            .kpi-value.negative { color: #dc2626; }
            .kpi-badge { display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; font-weight: 700; padding: 3px 9px; border-radius: 20px; }
            .kpi-badge.up { background: #dcfce7; color: #15803d; }
            .kpi-badge.down { background: #fee2e2; color: #b91c1c; }
            .kpi-badge.neutral { background: #f1f5f9; color: #64748b; }

            .dbsd-content-grid { display: grid; grid-template-columns: 1fr; gap: 20px; }

            .dbsd-chart-card { background: #fff; border-radius: 18px; padding: 24px 26px; box-shadow: 0 2px 6px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.05); border: 1px solid rgba(226,232,240,0.8); animation: dbsd-fade-up 0.4s 0.1s ease both; }
            .dbsd-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 10px; }
            .dbsd-card-title { font-size: 15px; font-weight: 700; color: #0f172a; letter-spacing: -0.2px; }
            .dbsd-card-subtitle { font-size: 12px; color: #94a3b8; margin-top: 2px; }
            .dbsd-chart-tabs { display: flex; gap: 4px; background: #f1f5f9; border-radius: 9px; padding: 3px; }
            .dbsd-chart-tab { padding: 5px 13px; border-radius: 7px; font-size: 12px; font-weight: 600; border: none; background: transparent; color: #64748b; cursor: pointer; transition: all 0.15s; }
            .dbsd-chart-tab:hover { color: #475569; }
            .dbsd-chart-tab.active { background: #fff; color: #0369a1; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
            .dbsd-chart-wrap { position: relative; height: 290px; }
            .dbsd-chart-wrap canvas { max-height: 290px; }

            .dbsd-table-card { background: #fff; border-radius: 18px; box-shadow: 0 2px 6px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.05); border: 1px solid rgba(226,232,240,0.8); overflow: hidden; animation: dbsd-fade-up 0.4s 0.15s ease both; }
            .dbsd-table-card-header { display: flex; align-items: center; justify-content: space-between; padding: 18px 24px 16px; flex-wrap: wrap; gap: 12px; border-bottom: 1px solid #f1f5f9; background: linear-gradient(180deg, #fafbff, #fff); }
            .dbsd-search-box { display: flex; align-items: center; gap: 8px; background: #f8fafc; border-radius: 9px; padding: 7px 13px; border: 1.5px solid #e2e8f0; transition: all 0.15s; }
            .dbsd-search-box:focus-within { background: #fff; border-color: #0ea5e9; box-shadow: 0 0 0 3px rgba(14,165,233,0.12); }
            .dbsd-search-box svg { color: #94a3b8; flex-shrink: 0; }
            .dbsd-search-input { border: none; background: transparent; outline: none; font-size: 13px; color: #1e293b; width: 190px; font-family: inherit; }
            .dbsd-search-input::placeholder { color: #94a3b8; }
            .dbsd-table-actions { display: flex; gap: 8px; flex-wrap: wrap; }
            .dbsd-action-btn { padding: 7px 14px; border-radius: 9px; font-size: 12px; font-weight: 600; border: 1.5px solid #e2e8f0; background: #f8fafc; color: #475569; cursor: pointer; transition: all 0.15s; display: flex; align-items: center; gap: 5px; font-family: inherit; }
            .dbsd-action-btn:hover { background: #f1f5f9; border-color: #bae6fd; color: #0369a1; }
            .dbsd-action-btn.primary { background: linear-gradient(135deg, #0ea5e9, #6366f1); border-color: transparent; color: #fff; box-shadow: 0 2px 8px rgba(14,165,233,0.35); }
            .dbsd-action-btn.primary:hover { background: linear-gradient(135deg, #0284c7, #4f46e5); box-shadow: 0 4px 12px rgba(14,165,233,0.45); transform: translateY(-1px); }

            /* Bounded, self-contained scroll box - see the identical comment
               in profit_and_loss_drilldown.js: a sticky thead needs its own
               actually-scrolling container to stick within, otherwise the
               ancestor card's overflow:hidden (there only for rounded
               corners) silently becomes the sticky containing block instead
               and the header scrolls away with the rest of the page. */
            .dbsd-table-scroll { overflow: auto; max-height: 65vh; }
            .dbsd-table { width: 100%; border-collapse: collapse; font-size: 13px; }
            .dbsd-table thead { position: sticky; top: 0; z-index: 2; }
            .dbsd-table thead tr { background: #f8fafc; border-bottom: 2px solid #e2e8f0; }
            .dbsd-table thead th { position: sticky; top: 0; padding: 12px 14px; text-align: left; font-size: 10.5px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.8px; white-space: nowrap; background: #f8fafc; z-index: 2; }
            .dbsd-table thead th.num { text-align: right; }
            .dbsd-table tbody tr.row-leaf:nth-child(even) td { background: #fafbff; }
            .dbsd-table tbody tr { border-bottom: 1px solid #f1f5f9; transition: background 0.12s; }
            .dbsd-table tbody tr:not(.row-section-header):not(.row-total):not(.row-net-profit):hover td { background: #f0f9ff !important; }
            .dbsd-table td { padding: 9px 14px; color: #334155; vertical-align: middle; }
            .dbsd-table td.num { text-align: right; font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }

            .row-section-header td { background: linear-gradient(90deg, #e0f2fe 0%, #ede9fe 100%) !important; font-weight: 800; font-size: 13px; color: #0c4a6e; border-top: 2px solid #bae6fd; border-bottom: 2px solid #bae6fd; padding-top: 12px; padding-bottom: 12px; letter-spacing: 0.1px; }
            .row-group-header td { background: #f8fafc !important; font-weight: 600; color: #1e293b; font-size: 13px; border-bottom: 1px solid #e8edf4; }
            .row-total td { background: linear-gradient(90deg, #1e293b, #0f172a) !important; color: #e2e8f0 !important; font-weight: 700; font-size: 13px; border-top: 2px solid #334155 !important; border-bottom: 2px solid #334155 !important; padding-top: 11px; padding-bottom: 11px; }
            .row-total td .num-positive { color: #86efac !important; }
            .row-total td .num-negative { color: #fca5a5 !important; }
            .row-net-profit td { background: linear-gradient(90deg, #0c1e3d 0%, #1e3a6e 50%, #0c1e3d 100%) !important; color: #dbeafe !important; font-weight: 800; font-size: 14px; border-top: 3px solid #0ea5e9 !important; border-bottom: 3px solid #0ea5e9 !important; padding-top: 14px; padding-bottom: 14px; letter-spacing: -0.2px; }
            .row-net-profit td .num-positive, .row-net-profit td .net-positive { color: #6ee7b7 !important; font-size: 15px; }
            .row-net-profit td .num-negative, .row-net-profit td .net-negative { color: #fca5a5 !important; font-size: 15px; }
            .row-transaction td { background: #f8fbff; color: #475569; font-size: 12.5px; }
            .row-item td { background: #fdfdff; color: #64748b; font-size: 12px; }

            .dbsd-account-cell { display: flex; align-items: center; }
            .dbsd-indent { display: inline-block; flex-shrink: 0; }
            .dbsd-toggle { width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; color: #cbd5e1; flex-shrink: 0; font-size: 9px; transition: transform 0.18s, color 0.15s; margin-right: 3px; user-select: none; border-radius: 4px; }
            .dbsd-toggle:hover { background: #e0f2fe; color: #0ea5e9; }
            .dbsd-toggle.open { transform: rotate(90deg); color: #0ea5e9; }
            .dbsd-toggle-spacer { width: 23px; display: inline-block; flex-shrink: 0; }
            .dbsd-acct-icon { width: 24px; height: 24px; border-radius: 7px; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; margin-right: 8px; flex-shrink: 0; }
            .icon-asset     { background: linear-gradient(135deg, #e0f2fe, #bae6fd); color: #075985; }
            .icon-liability { background: linear-gradient(135deg, #fef3c7, #fde68a); color: #78350f; }
            .icon-equity    { background: linear-gradient(135deg, #ede9fe, #ddd6fe); color: #4c1d95; }
            .icon-neutral   { background: linear-gradient(135deg, #f1f5f9, #e2e8f0); color: #475569; }

            .num-positive { color: #16a34a; font-weight: 600; }
            .num-negative { color: #dc2626; font-weight: 600; }
            .num-zero { color: #cbd5e1; }

            .dbsd-view-pills { display: flex; gap: 3px; background: #f1f5f9; border-radius: 10px; padding: 3px; }
            .dbsd-view-pill { padding: 5px 14px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; color: #64748b; border: none; background: transparent; font-family: inherit; }
            .dbsd-view-pill:hover { color: #475569; }
            .dbsd-view-pill.active { background: #fff; color: #0369a1; box-shadow: 0 1px 4px rgba(0,0,0,0.1), 0 0 0 1px rgba(14,165,233,0.1); }

            .dbsd-footer { text-align: center; padding: 18px 40px 24px; font-size: 12px; color: #94a3b8; letter-spacing: 0.1px; }
            .dbsd-footer strong { color: #0ea5e9; }

            @media (max-width: 900px) {
                .dbsd-header { padding: 20px 20px; }
                .dbsd-filters-panel { padding: 14px 20px; }
                .dbsd-body { padding: 16px 20px 24px; }
                .dbsd-filters-grid { grid-template-columns: 1fr 1fr; }
            }
            @media (max-width: 600px) {
                .dbsd-filters-grid { grid-template-columns: 1fr; }
                .dbsd-kpis { grid-template-columns: 1fr 1fr; }
                .dbsd-kpi-card { padding: 16px; }
                .kpi-value { font-size: 20px; }
                .dbsd-table-card-header { flex-direction: column; align-items: flex-start; }
                .dbsd-search-input { width: 140px; }
            }

            /* ── Print: header title/company/fiscal-year + table exactly as
               currently expanded on screen; everything else (filters, KPI
               cards, chart, search/expand/collapse/CSV/print chrome) hidden. */
            @media print {
                .dbsd-run-btn, .dbsd-filters-panel, .dbsd-kpis,
                .dbsd-content-grid > .dbsd-chart-card,
                .dbsd-table-card-header, .dbsd-footer { display: none !important; }
                #dbsd-root { background: #fff; }
                .dbsd-header { background: #fff !important; color: #000 !important; box-shadow: none; padding: 0 0 12px; }
                .dbsd-header::before { display: none; }
                .dbsd-main-title, .dbsd-subtitle { color: #000 !important; }
                .dbsd-logo-icon { display: none; }
                .dbsd-body { padding: 10px 0; }
                .dbsd-table-card { box-shadow: none; border: none; }
                .dbsd-table-scroll { overflow: visible; max-height: none; }
                .dbsd-table thead, .dbsd-table thead th { position: static; }
            }
        `;
		document.head.appendChild(style);
	}

	// ── Chart.js from CDN, loaded once and reused ─────────────────────────────
	function ensureChartJs(cb) {
		if (window.Chart) { cb(); return; }
		var s = document.createElement("script");
		s.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js";
		s.onload = cb;
		document.head.appendChild(s);
	}

	// ── Formatting helpers ────────────────────────────────────────────────────
	function fmt_currency(val, currency) {
		if (val === "" || val === null || val === undefined) return "";
		var n = parseFloat(val) || 0;
		try {
			return new Intl.NumberFormat("en-US", { style: "currency", currency: currency || "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
		} catch (e) {
			return (n < 0 ? "-" : "") + (currency || "") + " " + Math.abs(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
		}
	}

	function fmt_number(val) {
		if (val === "" || val === null || val === undefined) return "";
		var n = parseFloat(val) || 0;
		return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 4 });
	}

	function escHtml(s) {
		return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
	}

	function isBlank(v) {
		return v === null || v === undefined || v === "";
	}

	function getCurrency() {
		return state.presentation_currency
			|| (state.chartData && state.chartData.currency)
			|| frappe.defaults.get_default("currency")
			|| "USD";
	}

	// ── Row classification (computed once per row, right after data loads) ──
	// Every row in the flat result is exactly one of:
	//   'blank'       - falsy/spacer entry between statement sections
	//   'group'       - real group account, including the Assets/Liabilities/
	//                   Equity root of each tree (simplify_root_heading() in
	//                   the .py only relabels/blanks that row - it keeps the
	//                   real root account's own "account"/is_group values)
	//   'leaf'        - real leaf account (has a real, unquoted "account")
	//   'transaction' - a voucher drilled into under a leaf account
	//   'item'        - a line item drilled into under a transaction row
	//   'total'       - a synthetic total/diff row (Total Asset/Liability/
	//                   Equity, Provisional Profit / Loss (Credit), Total
	//                   (Credit), Unclosed Fiscal Years Profit / Loss -
	//                   quoted "account", never collapsible, never a link)
	// Every synthetic row financial_statements.py/detailed_balance_sheet.py
	// builds quotes its "account" value in literal single-quotes
	// specifically so Link-fieldtype rendering treats it as plain text
	// instead of a (broken) link to a real Account - see the comment on
	// make_transaction_row() in financial_statements.py. We reuse that same
	// quoting convention here to tell a real account apart from a synthetic
	// row without needing any extra field.
	function classifyRow(row) {
		if (!row || (row.account === undefined && row.account_name === undefined && row.is_group === undefined)) {
			return "blank";
		}
		if (row.item_code) return "item";
		if (row.voucher_type && row.voucher_no) return "transaction";
		if (row.is_group) return "group";
		var acct = row.account;
		var isSynthetic = typeof acct === "string" && acct.charAt(0) === "'";
		if (acct && !isSynthetic) return "leaf";
		return "total";
	}

	// The stable, unique key used for both the expandedState map and the
	// collapse-tracking pass below. Real accounts and every synthetic row
	// carry a real (or quoted) "account" value; account_name is only a
	// fallback for the rare row missing "account" entirely.
	function rowKey(row) {
		return row.account || row.account_name;
	}

	function annotateRows(allRows) {
		for (var i = 0; i < allRows.length; i++) {
			var row = allRows[i];
			if (!row) continue;
			row.__kind = classifyRow(row);
			row.__key = row.__kind === "blank" ? null : rowKey(row);
			if (row.__kind === "transaction") {
				var indent = row.indent || 0;
				var next = allRows[i + 1];
				row.__hasItems = !!(next && (next.indent || 0) === indent + 1 && next.item_code);
			}
		}
	}

	// Seed a sensible default expand state so the initial view reads like a
	// normal balance sheet, not an exploded wall of transactions: account
	// rows at indent <= 2 start expanded (absence from the map = expanded);
	// deeper account rows and every transaction row start collapsed.
	function seedDefaultExpandState(allRows) {
		var expanded = {};
		for (var i = 0; i < allRows.length; i++) {
			var row = allRows[i];
			if (!row || row.__kind === "blank" || row.__kind === "item" || row.__kind === "total") continue;
			var indent = row.indent || 0;
			if (row.__kind === "transaction") {
				expanded[row.__key] = false;
			} else if (indent > 2) {
				expanded[row.__key] = false;
			}
		}
		return expanded;
	}

	// ── THE core new logic: single O(n) pass computing which rows are
	// currently visible (given collapse state) and which of the 12 possible
	// transaction-detail columns still have data among those visible rows -
	// i.e. columns that show only while a row with data for them is
	// expanded, and vanish again the instant that row collapses. Deliberately
	// NOT the reference page's ancestor-walk (O(n^2) - fine for ~100 account
	// rows, far too slow once transaction/item drill-down pushes this past
	// 10k+ rows): every row already carries a correct pre-order `indent`, so
	// a single pass with a small "currently collapsed" stack is enough.
	//
	// One deliberate refinement over the plain "is_group || voucher_type"
	// collapsibility rule: a real LEAF account row is also collapsible (its
	// children are the transactions attach_transaction_rows() attached to
	// it) even though is_group is falsy for a leaf - so collapsibility here
	// is kind-based (group / leaf / transaction) rather than only
	// is_group/voucher_type, otherwise collapsing a leaf account would never
	// actually hide its own transactions.
	function computeVisibleRowsAndColumns(allRows, expandedState, transactionDetailColumnDefs, searchText) {
		var visible = [];
		var collapseStack = [];

		for (var i = 0; i < allRows.length; i++) {
			var row = allRows[i];
			if (!row) { visible.push(row); continue; }

			var indent = row.indent || 0;
			while (collapseStack.length && indent <= collapseStack[collapseStack.length - 1]) {
				collapseStack.pop();
			}
			var isHidden = collapseStack.length > 0;
			if (!isHidden) visible.push(row);

			var isCollapsible = row.__kind === "group" || row.__kind === "leaf" || row.__kind === "transaction";
			var isCollapsed = isCollapsible && expandedState[row.__key] === false;
			if (isCollapsible && isCollapsed) {
				collapseStack.push(indent);
			}
		}

		if (searchText) {
			var needle = searchText.toLowerCase();
			visible = visible.filter(function (r) {
				if (!r) return true; // keep spacer rows
				var label = r.account_name || "";
				return label.toLowerCase().indexOf(needle) !== -1;
			});
		}

		var dynamicColumns = transactionDetailColumnDefs.filter(function (col) {
			for (var j = 0; j < visible.length; j++) {
				var r = visible[j];
				if (r && r[col.fieldname] !== null && r[col.fieldname] !== undefined && r[col.fieldname] !== "") {
					return true;
				}
			}
			return false;
		});

		return { visible: visible, dynamicColumns: dynamicColumns };
	}

	// ── Build Shell HTML ─────────────────────────────────────────────────────
	function buildShell() {
		return `
        <div class="dbsd-header">
            <div class="dbsd-header-inner">
                <div class="dbsd-title-block">
                    <div class="dbsd-logo-icon">🏦</div>
                    <div>
                        <div class="dbsd-main-title">Detailed Balance Sheet (Drilldown)</div>
                        <div class="dbsd-subtitle" id="dbsd-header-sub">Select filters and run the report</div>
                    </div>
                </div>
                <button class="dbsd-run-btn" id="dbsd-run-btn">
                    <svg class="btn-text" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M5 3l14 9-14 9V3z"/></svg>
                    <span class="btn-text">Run Report</span>
                    <span class="btn-spinner">⟳</span>
                </button>
            </div>
        </div>

        <div class="dbsd-filters-panel">
            <div class="dbsd-filters-grid">
                <div class="dbsd-field">
                    <label>Company</label>
                    <select id="dbsd-company"></select>
                </div>
                <div class="dbsd-field">
                    <label>Filter Based On</label>
                    <select id="dbsd-filter-based-on">
                        <option value="Fiscal Year">Fiscal Year</option>
                        <option value="Date Range">Date Range</option>
                    </select>
                </div>
                <div class="dbsd-field" id="dbsd-fy-from-wrap">
                    <label>From Fiscal Year</label>
                    <select id="dbsd-from-fy"></select>
                </div>
                <div class="dbsd-field" id="dbsd-fy-to-wrap">
                    <label>To Fiscal Year</label>
                    <select id="dbsd-to-fy"></select>
                </div>
                <div class="dbsd-field" id="dbsd-date-from-wrap" style="display:none">
                    <label>Start Date</label>
                    <input type="date" id="dbsd-start-date"/>
                </div>
                <div class="dbsd-field" id="dbsd-date-to-wrap" style="display:none">
                    <label>End Date</label>
                    <input type="date" id="dbsd-end-date"/>
                </div>
                <div class="dbsd-field">
                    <label>Periodicity</label>
                    <select id="dbsd-periodicity">
                        <option value="Monthly">Monthly</option>
                        <option value="Quarterly">Quarterly</option>
                        <option value="Half-Yearly">Half-Yearly</option>
                        <option value="Yearly" selected>Yearly</option>
                    </select>
                </div>
                <div class="dbsd-field">
                    <label>Currency</label>
                    <select id="dbsd-currency">
                        <option value="">Company Default</option>
                    </select>
                </div>
                <div class="dbsd-field">
                    <label>View</label>
                    <select id="dbsd-view">
                        <option value="Report">Report View</option>
                        <option value="Growth">Growth View</option>
                        <option value="Margin">Percentage View (% of Total Assets)</option>
                    </select>
                </div>
            </div>
            <div class="dbsd-filters-row2">
                <label class="dbsd-check-field">
                    <input type="checkbox" id="dbsd-accum" checked/>
                    <span class="dbsd-toggle-track"></span>
                    <span>Accumulated Values</span>
                </label>
                <label class="dbsd-check-field">
                    <input type="checkbox" id="dbsd-show-zero"/>
                    <span class="dbsd-toggle-track"></span>
                    <span>Show Zero Values</span>
                </label>
                <label class="dbsd-check-field">
                    <input type="checkbox" id="dbsd-default-book" checked/>
                    <span class="dbsd-toggle-track"></span>
                    <span>Include Default Book Entries</span>
                </label>
            </div>
        </div>

        <div class="dbsd-body" id="dbsd-body">
            <div class="dbsd-placeholder">
                <div class="ph-icon">🏦</div>
                <p>Configure your filters and click <strong>Run Report</strong> to generate the Detailed Balance Sheet drilldown.</p>
            </div>
        </div>

        <div class="dbsd-footer" id="dbsd-footer" style="display:none">
            Generated on <span id="dbsd-gen-time"></span> &nbsp;·&nbsp; <strong id="dbsd-company-name"></strong>
        </div>
        `;
	}

	// ── Render body content ──────────────────────────────────────────────────
	function renderResults() {
		var $b = $("#dbsd-body");
		if (state.loading) {
			$b.html('<div class="dbsd-loader"><div class="dbsd-spinner"></div><p>Fetching financial data…</p></div>');
			return;
		}
		if (!state.allRows || !state.allRows.length) return;

		var currency = getCurrency();
		var warnHtml = state.reportMessage
			? '<div class="dbsd-warning-banner">⚠️ ' + escHtml(state.reportMessage) + '</div>'
			: "";
		var kpiHtml = buildKpiCards(currency);
		var chartHtml = buildChartCard();
		var tableHtml = buildTableCard();

		$b.html(warnHtml +
			'<div class="dbsd-kpis" id="dbsd-kpis">' + kpiHtml + '</div>' +
			'<div class="dbsd-content-grid">' + chartHtml + tableHtml + '</div>');

		renderChart();
		rerenderTable();

		$("#dbsd-gen-time").text(frappe.datetime.now_datetime());
		$("#dbsd-company-name").text(state.company);
		$("#dbsd-footer").show();
	}

	// ── KPI Cards ────────────────────────────────────────────────────────────
	// report_summary already comes back in the exact order get_report_summary()
	// in detailed_balance_sheet.py builds it - 4 real entries (Total Asset /
	// Total Liability / Total Equity / Provisional Profit / Loss (Credit)),
	// no separators - rendered positionally rather than string-matching on
	// label text.
	function buildKpiCards(currency) {
		var summary = (state.summary || []).filter(function (s) { return s && s.type !== "separator"; });
		var configs = [
			{ cls: "dbsd-kpi-asset", icon: "🏦", badge: "neutral", badgeText: "Assets" },
			{ cls: "dbsd-kpi-liability", icon: "💳", badge: "neutral", badgeText: "Liabilities" },
			{ cls: "dbsd-kpi-equity", icon: "📑", badge: "neutral", badgeText: "Equity" },
			{ cls: "dbsd-kpi-pl", icon: "⚖️", badge: null },
		];
		var html = "";
		for (var i = 0; i < summary.length && i < configs.length; i++) {
			var s = summary[i];
			var cfg = configs[i];
			var val = flt_(s.value);
			var valueClass = val >= 0 ? "positive" : "negative";
			var badge = cfg.badge;
			var badgeText = cfg.badgeText;
			if (!badge) {
				badge = val >= 0 ? "up" : "down";
				badgeText = val >= 0 ? "▲ Balanced" : "▼ Shortfall";
			}
			html += '<div class="dbsd-kpi-card ' + cfg.cls + '">' +
				'<div class="kpi-icon">' + cfg.icon + '</div>' +
				'<div class="kpi-label">' + escHtml(s.label || "") + '</div>' +
				'<div class="kpi-value ' + valueClass + '">' + fmt_currency(val, currency) + '</div>' +
				'<span class="kpi-badge ' + badge + '">' + escHtml(badgeText) + '</span>' +
				'</div>';
		}
		return html;
	}

	function flt_(v) { return parseFloat(v) || 0; }

	// ── Chart Card ────────────────────────────────────────────────────────────
	function buildChartCard() {
		var period = state.from_fiscal_year || state.period_start_date || "";
		if (state.to_fiscal_year && state.to_fiscal_year !== state.from_fiscal_year) period += " – " + state.to_fiscal_year;
		return `
            <div class="dbsd-chart-card">
                <div class="dbsd-card-header">
                    <div>
                        <div class="dbsd-card-title">Financial Position Overview</div>
                        <div class="dbsd-card-subtitle">${escHtml(state.company)}${period ? " &nbsp;·&nbsp; " + escHtml(period) : ""}</div>
                    </div>
                    <div class="dbsd-chart-tabs">
                        <button class="dbsd-chart-tab ${state.chart_type === "bar" ? "active" : ""}" data-type="bar">Bar</button>
                        <button class="dbsd-chart-tab ${state.chart_type === "line" ? "active" : ""}" data-type="line">Line</button>
                    </div>
                </div>
                <div class="dbsd-chart-wrap">
                    <canvas id="dbsd-chart"></canvas>
                </div>
            </div>
        `;
	}

	function renderChart() {
		ensureChartJs(function () {
			var cd = state.chartData;
			if (!cd || !cd.data) return;
			if (state.chart_instance) { state.chart_instance.destroy(); state.chart_instance = null; }

			var ctx = document.getElementById("dbsd-chart");
			if (!ctx) return;

			var labels = cd.data.labels || [];
			var palette = [
				{ bg: "rgba(14,165,233,0.15)", border: "#0ea5e9" },
				{ bg: "rgba(245,158,11,0.15)", border: "#f59e0b" },
				{ bg: "rgba(139,92,246,0.15)", border: "#8b5cf6" },
			];
			var datasets = (cd.data.datasets || []).map(function (ds, i) {
				var c = palette[i % palette.length];
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
						legend: { position: "top", labels: { font: { size: 12, weight: "600" }, usePointStyle: true, pointStyleWidth: 12, padding: 20 } },
						tooltip: {
							backgroundColor: "#1a1f36", titleColor: "#fff", bodyColor: "rgba(255,255,255,0.8)",
							padding: 12, cornerRadius: 10,
							callbacks: { label: function (c) { return " " + c.dataset.label + ": " + fmt_currency(c.parsed.y || 0, getCurrency()); } },
						},
					},
					scales: {
						x: { grid: { display: false }, ticks: { font: { size: 12 } } },
						y: {
							grid: { color: "rgba(0,0,0,0.05)" },
							ticks: {
								font: { size: 11 },
								callback: function (v) {
									var abs = Math.abs(v);
									if (abs >= 1e6) return (v / 1e6).toFixed(1) + "M";
									if (abs >= 1e3) return (v / 1e3).toFixed(0) + "K";
									return v;
								},
							},
						},
					},
				},
			});

			$(".dbsd-chart-tab").off("click").on("click", function () {
				$(".dbsd-chart-tab").removeClass("active");
				$(this).addClass("active");
				state.chart_type = $(this).data("type");
				renderChart();
			});
		});
	}

	// ── Table Card ────────────────────────────────────────────────────────────
	function buildTableCard() {
		return `
            <div class="dbsd-table-card">
                <div class="dbsd-table-card-header">
                    <div class="dbsd-card-title">Account Breakdown</div>
                    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                        <div class="dbsd-view-pills" id="dbsd-view-pills">
                            <button class="dbsd-view-pill ${state.selected_view === "Report" ? "active" : ""}" data-view="Report">Report</button>
                            <button class="dbsd-view-pill ${state.selected_view === "Growth" ? "active" : ""}" data-view="Growth">Growth</button>
                            <button class="dbsd-view-pill ${state.selected_view === "Margin" ? "active" : ""}" data-view="Margin">%</button>
                        </div>
                        <div class="dbsd-search-box">
                            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                            <input class="dbsd-search-input" id="dbsd-search" type="text" placeholder="Search accounts…"/>
                        </div>
                        <div class="dbsd-table-actions">
                            <button class="dbsd-action-btn" id="dbsd-expand-all">⊞ Expand All</button>
                            <button class="dbsd-action-btn" id="dbsd-collapse-all">⊟ Collapse All</button>
                            <button class="dbsd-action-btn" id="dbsd-print-btn">🖨 Print</button>
                            <button class="dbsd-action-btn primary" id="dbsd-export-btn">↓ Export CSV</button>
                        </div>
                    </div>
                </div>
                <div class="dbsd-table-scroll">
                    <table class="dbsd-table" id="dbsd-table">
                        <thead id="dbsd-thead"></thead>
                        <tbody id="dbsd-tbody"></tbody>
                    </table>
                </div>
            </div>
        `;
	}

	function buildColumnHeaders(baseColumns, dynamicColumns) {
		var html = "";
		for (var i = 0; i < baseColumns.length; i++) {
			var cls = i === 0 ? "" : ' class="num"';
			html += "<th" + cls + ">" + escHtml(baseColumns[i].label || "") + "</th>";
		}
		for (var j = 0; j < dynamicColumns.length; j++) {
			html += '<th class="num">' + escHtml(dynamicColumns[j].label || "") + "</th>";
		}
		return html;
	}

	function baseValueCell(row, col, currency) {
		var val = row[col.fieldname];
		if (isBlank(val)) return '<td class="num"></td>';

		var n = parseFloat(val) || 0;
		var formatted, numClass;

		if (state.selected_view === "Growth") {
			if (col.fieldname === "total") {
				formatted = fmt_currency(n, currency);
				numClass = n > 0 ? "num-positive" : n < 0 ? "num-negative" : "num-zero";
			} else {
				formatted = (n >= 0 ? "+" : "") + n + "%";
				numClass = n > 0 ? "num-positive" : n < 0 ? "num-negative" : "num-zero";
			}
		} else if (state.selected_view === "Margin") {
			// Common-size balance sheet: every value is a % of Total Assets
			// (already computed server-side - see compute_margin_view_data()
			// call in detailed_balance_sheet.py, base_account_name="Total
			// Asset (Debit)").
			formatted = n + "%";
			numClass = n > 0 ? "num-positive" : n < 0 ? "num-negative" : "num-zero";
		} else {
			formatted = fmt_currency(n, currency);
			numClass = n > 0 ? "num-positive" : n < 0 ? "num-negative" : "num-zero";
		}
		return '<td class="num ' + numClass + '">' + formatted + "</td>";
	}

	function dynamicValueCell(row, col) {
		var val = row[col.fieldname];
		if (isBlank(val)) return '<td class="num"></td>';

		var formatted;
		if (col.fieldtype === "Currency") {
			formatted = fmt_currency(val, row.currency || getCurrency());
		} else if (col.fieldtype === "Float") {
			formatted = fmt_number(val);
		} else if (col.fieldtype === "Date") {
			formatted = escHtml(frappe.datetime.str_to_user ? frappe.datetime.str_to_user(val) : String(val));
		} else {
			formatted = escHtml(String(val));
		}
		return '<td class="num">' + formatted + "</td>";
	}

	function nameCell(row, indentPx) {
		var toggleHtml = "";
		var iconHtml = "";
		var labelHtml;
		var label = escHtml(row.account_name || "");

		if (row.__kind === "group" || row.__kind === "leaf" || row.__kind === "transaction") {
			var isOpen = state.expandedState[row.__key] !== false;
			toggleHtml = '<span class="dbsd-toggle ' + (isOpen ? "open" : "") + '" data-key="' + escHtml(row.__key) + '">▶</span>';
		} else if (row.__kind === "item") {
			toggleHtml = '<span class="dbsd-toggle-spacer"></span>';
		}

		if (row.__kind === "group" && (row.indent || 0) === 0) {
			var lower = (row.account_name || "").toLowerCase();
			var iconCls = "icon-neutral", iconChar = "▤";
			if (lower.indexOf("asset") !== -1) { iconCls = "icon-asset"; iconChar = "🏦"; }
			else if (lower.indexOf("liabilit") !== -1) { iconCls = "icon-liability"; iconChar = "💳"; }
			else if (lower.indexOf("equity") !== -1) { iconCls = "icon-equity"; iconChar = "📑"; }
			iconHtml = '<span class="dbsd-acct-icon ' + iconCls + '">' + iconChar + "</span>";
		}

		if (row.__kind === "transaction") {
			labelHtml = frappe.utils.get_form_link(row.voucher_type, row.voucher_no, true, label);
		} else if (row.__kind === "item") {
			labelHtml = frappe.utils.get_form_link("Item", row.item_code, true, label);
		} else {
			// Real account rows (leaf or group) and every synthetic
			// total/heading row never navigate anywhere - they already
			// expand in place, so plain text only (see the existing
			// report .js files' identical rule/comment).
			labelHtml = label;
		}

		return '<td><div class="dbsd-account-cell">' +
			'<span class="dbsd-indent" style="min-width:' + indentPx + 'px"></span>' +
			toggleHtml + iconHtml + "<span>" + labelHtml + "</span>" +
			"</div></td>";
	}

	function rowClassFor(row, isLastRealRow) {
		if (row.__kind === "group") return (row.indent || 0) === 0 ? "row-section-header" : "row-group-header";
		if (row.__kind === "total") return isLastRealRow ? "row-net-profit" : "row-total";
		if (row.__kind === "transaction") return "row-transaction";
		if (row.__kind === "item") return "row-item";
		return "row-leaf";
	}

	function buildTableRows(visibleRows, baseColumns, dynamicColumns) {
		var currency = getCurrency();
		var html = "";
		var totalCols = baseColumns.length + dynamicColumns.length;

		// The final row of the whole (unfiltered) dataset is always the
		// bottom-line summary row (Total (Credit), or Provisional Profit /
		// Loss (Credit) if there's no unclosed-year adjustment - see the
		// tail of execute() in detailed_balance_sheet.py) - detected
		// positionally rather than by matching label text.
		var lastRealRow = null;
		for (var li = state.allRows.length - 1; li >= 0; li--) {
			if (state.allRows[li]) { lastRealRow = state.allRows[li]; break; }
		}

		for (var i = 0; i < visibleRows.length; i++) {
			var row = visibleRows[i];
			if (!row || row.__kind === "blank") {
				html += '<tr><td colspan="' + totalCols + '" style="padding:4px"></td></tr>';
				continue;
			}

			var indentPx = (row.indent || 0) * 18;
			var rowClass = rowClassFor(row, row === lastRealRow);

			html += '<tr class="' + rowClass + '">';
			html += nameCell(row, indentPx);

			for (var c = 1; c < baseColumns.length; c++) {
				html += baseValueCell(row, baseColumns[c], currency);
			}
			for (var d = 0; d < dynamicColumns.length; d++) {
				html += dynamicValueCell(row, dynamicColumns[d]);
			}
			html += "</tr>";
		}
		return html;
	}

	// Recomputes visible rows + dynamic columns (the O(n) pass) and rebuilds
	// only <thead>/<tbody> - called on initial load and on every toggle,
	// search keystroke, and Expand All / Collapse All click.
	function rerenderTable() {
		var searchText = ($("#dbsd-search").val() || "").trim();
		var res = computeVisibleRowsAndColumns(state.allRows, state.expandedState, state.dynamicColumnDefs, searchText);
		state.lastVisible = res.visible;
		state.lastDynamicColumns = res.dynamicColumns;
		$("#dbsd-thead").html("<tr>" + buildColumnHeaders(state.baseColumns, res.dynamicColumns) + "</tr>");
		$("#dbsd-tbody").html(buildTableRows(res.visible, state.baseColumns, res.dynamicColumns));
	}

	// ── Table event binding (delegated on the persistent #dbsd-root so it
	// survives every innerHTML rebuild of the body underneath it) ───────────
	function bindTableEventsOnce() {
		$root.on("click", "#dbsd-tbody .dbsd-toggle", function (e) {
			e.stopPropagation();
			var key = $(this).data("key");
			state.expandedState[key] = state.expandedState[key] === false ? true : false;
			rerenderTable();
		});

		$root.on("input", "#dbsd-search", function () {
			rerenderTable();
		});

		$root.on("click", "#dbsd-expand-all", function () {
			state.expandedState = {};
			rerenderTable();
		});

		$root.on("click", "#dbsd-collapse-all", function () {
			var collapsed = {};
			for (var i = 0; i < state.allRows.length; i++) {
				var row = state.allRows[i];
				if (row && (row.__kind === "group" || row.__kind === "leaf" || row.__kind === "transaction")) {
					collapsed[row.__key] = false;
				}
			}
			state.expandedState = collapsed;
			rerenderTable();
		});

		$root.on("click", "#dbsd-view-pills .dbsd-view-pill", function () {
			state.selected_view = $(this).data("view");
			$("#dbsd-view").val(state.selected_view);
			runReport();
		});

		$root.on("click", "#dbsd-export-btn", function () { exportCsv(); });

		$root.on("click", "#dbsd-print-btn", function () { window.print(); });
	}

	// ── CSV Export - current dynamic column set + current visible rows only,
	// i.e. exactly what's on screen right now (collapsed branches excluded,
	// hidden columns excluded). ───────────────────────────────────────────
	function exportCsv() {
		var baseColumns = state.baseColumns;
		var dynamicColumns = state.lastDynamicColumns;
		var rows = state.lastVisible;
		var lines = [];

		var headerCells = baseColumns.map(function (c) { return c.label || ""; })
			.concat(dynamicColumns.map(function (c) { return c.label || ""; }));
		lines.push(headerCells.map(function (h) { return '"' + h.replace(/"/g, '""') + '"'; }).join(","));

		rows.forEach(function (row) {
			if (!row || row.__kind === "blank") return;
			var cells = [];
			cells.push(row.account_name || "");
			for (var c = 1; c < baseColumns.length; c++) {
				var v = row[baseColumns[c].fieldname];
				cells.push(isBlank(v) ? "" : v);
			}
			for (var d = 0; d < dynamicColumns.length; d++) {
				var v2 = row[dynamicColumns[d].fieldname];
				cells.push(isBlank(v2) ? "" : v2);
			}
			lines.push(cells.map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(","));
		});

		var blob = new Blob([lines.join("\n")], { type: "text/csv" });
		var a = document.createElement("a");
		a.href = URL.createObjectURL(blob);
		a.download = "detailed_balance_sheet_drilldown_" + (state.company || "company") + "_" + frappe.datetime.nowdate() + ".csv";
		a.click();
	}

	// ── Load metadata ─────────────────────────────────────────────────────────
	function loadMetadata() {
		frappe.db.get_list("Company", { fields: ["name"], limit: 100 }).then(function (res) {
			var $s = $("#dbsd-company");
			$s.empty();
			(res || []).forEach(function (c) {
				var sel = c.name === state.company ? " selected" : "";
				$s.append('<option value="' + escHtml(c.name) + '"' + sel + ">" + escHtml(c.name) + "</option>");
			});
			if (!state.company && res && res[0]) {
				state.company = res[0].name;
				$s.val(state.company);
			}
		});

		frappe.db.get_list("Fiscal Year", { fields: ["name", "year_start_date", "year_end_date"], order_by: "year_start_date desc", limit: 50 }).then(function (res) {
			state.fiscal_years = res || [];
			var $from = $("#dbsd-from-fy");
			var $to = $("#dbsd-to-fy");
			$from.empty(); $to.empty();

			(res || []).forEach(function (fy) {
				$from.append('<option value="' + escHtml(fy.name) + '">' + escHtml(fy.name) + "</option>");
				$to.append('<option value="' + escHtml(fy.name) + '">' + escHtml(fy.name) + "</option>");
			});

			var today = frappe.datetime.get_today();
			var currentFy = null;
			for (var i = 0; i < (res || []).length; i++) {
				if (today >= res[i].year_start_date && today <= res[i].year_end_date) { currentFy = res[i].name; break; }
			}
			if (!currentFy && res && res[0]) currentFy = res[0].name;
			if (currentFy) {
				state.from_fiscal_year = currentFy;
				state.to_fiscal_year = currentFy;
				$from.val(currentFy);
				$to.val(currentFy);
			}
			scheduleRun();
		});

		frappe.db.get_list("Currency", { fields: ["name"], filters: [["enabled", "=", 1]], limit: 200 }).then(function (res) {
			var $c = $("#dbsd-currency");
			$c.empty();
			$c.append('<option value="">Company Default</option>');
			(res || []).forEach(function (cur) { $c.append('<option value="' + escHtml(cur.name) + '">' + escHtml(cur.name) + "</option>"); });
		});
	}

	// ── Debounced auto-run ────────────────────────────────────────────────────
	var autoRunTimer = null;
	function scheduleRun() {
		clearTimeout(autoRunTimer);
		autoRunTimer = setTimeout(function () { runReport(); }, 300);
	}

	function bindControls() {
		$("#dbsd-company").on("change", function () { state.company = $(this).val(); updateHeaderSub(); scheduleRun(); });
		$("#dbsd-filter-based-on").on("change", function () { state.filter_based_on = $(this).val(); toggleDateFyFields(); scheduleRun(); });
		$("#dbsd-from-fy").on("change", function () { state.from_fiscal_year = $(this).val(); scheduleRun(); });
		$("#dbsd-to-fy").on("change", function () { state.to_fiscal_year = $(this).val(); scheduleRun(); });
		$("#dbsd-start-date").on("change", function () { state.period_start_date = $(this).val(); scheduleRun(); });
		$("#dbsd-end-date").on("change", function () { state.period_end_date = $(this).val(); scheduleRun(); });
		$("#dbsd-periodicity").on("change", function () { state.periodicity = $(this).val(); scheduleRun(); });
		$("#dbsd-currency").on("change", function () { state.presentation_currency = $(this).val(); scheduleRun(); });
		$("#dbsd-view").on("change", function () { state.selected_view = $(this).val(); scheduleRun(); });
		$("#dbsd-accum").on("change", function () { state.accumulated_values = $(this).is(":checked") ? 1 : 0; scheduleRun(); });
		$("#dbsd-show-zero").on("change", function () { state.show_zero_values = $(this).is(":checked") ? 1 : 0; scheduleRun(); });
		$("#dbsd-default-book").on("change", function () { state.include_default_book_entries = $(this).is(":checked") ? 1 : 0; scheduleRun(); });

		$("#dbsd-run-btn").on("click", function () { clearTimeout(autoRunTimer); runReport(); });

		$(".dbsd-filters-panel").on("keydown", function (e) {
			if (e.key === "Enter") { clearTimeout(autoRunTimer); runReport(); }
		});
	}

	function toggleDateFyFields() {
		if (state.filter_based_on === "Fiscal Year") {
			$("#dbsd-fy-from-wrap, #dbsd-fy-to-wrap").show();
			$("#dbsd-date-from-wrap, #dbsd-date-to-wrap").hide();
		} else {
			$("#dbsd-fy-from-wrap, #dbsd-fy-to-wrap").hide();
			$("#dbsd-date-from-wrap, #dbsd-date-to-wrap").show();
		}
	}

	function updateHeaderSub() {
		var sub = state.company ? state.company + " · " : "";
		sub += state.from_fiscal_year || "";
		if (state.to_fiscal_year && state.to_fiscal_year !== state.from_fiscal_year) sub += " – " + state.to_fiscal_year;
		if (!sub) sub = "Select filters and run the report";
		$("#dbsd-header-sub").text(sub);
	}

	// ── Run Report - same generic endpoint the existing query reports use,
	// same report_name, same filters shape, same is_tree/parent_field. ──────
	function runReport() {
		if (!state.company) { frappe.msgprint("Please select a Company."); return; }
		if (state.filter_based_on === "Fiscal Year" && !state.from_fiscal_year) { frappe.msgprint("Please select a Fiscal Year."); return; }
		if (state.filter_based_on === "Date Range" && (!state.period_start_date || !state.period_end_date)) { frappe.msgprint("Please select Start Date and End Date."); return; }

		state.loading = true;
		renderResults();
		$("#dbsd-run-btn").addClass("loading");

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

		frappe.call({
			method: "frappe.desk.query_report.run",
			args: {
				report_name: "Detailed Balance Sheet",
				filters: filters,
				is_tree: true,
				parent_field: "parent_account",
			},
			callback: function (r) {
				state.loading = false;
				$("#dbsd-run-btn").removeClass("loading");

				if (r && r.message) {
					var msg = r.message;
					var allColumns = msg.columns || [];
					state.baseColumns = allColumns.filter(function (c) {
						return !c.hidden && TRANSACTION_DETAIL_FIELDNAMES.indexOf(c.fieldname) === -1;
					});
					state.dynamicColumnDefs = allColumns.filter(function (c) {
						return !c.hidden && TRANSACTION_DETAIL_FIELDNAMES.indexOf(c.fieldname) !== -1;
					});
					state.allRows = msg.result || [];
					state.summary = msg.report_summary || [];
					state.chartData = msg.chart || null;
					state.reportMessage = msg.message || null;

					annotateRows(state.allRows);
					state.expandedState = seedDefaultExpandState(state.allRows);

					updateHeaderSub();
					renderResults();
				} else {
					frappe.msgprint("No data returned. Please check your filters.");
					$("#dbsd-body").html('<div class="dbsd-placeholder"><div class="ph-icon">⚠️</div><p>No data found for the selected filters.</p></div>');
				}
			},
			error: function (r) {
				state.loading = false;
				$("#dbsd-run-btn").removeClass("loading");
				var msg = (r && r.message) || "An error occurred while fetching the report.";
				frappe.msgprint(msg);
				$("#dbsd-body").html('<div class="dbsd-placeholder"><div class="ph-icon">❌</div><p>' + escHtml(String(msg)) + "</p></div>");
			},
		});
	}

	// ── Bootstrap ─────────────────────────────────────────────────────────────
	$root.html(buildShell());
	loadMetadata();
	bindControls();
	bindTableEventsOnce();
};
