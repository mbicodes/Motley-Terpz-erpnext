// Copyright (c) 2026, Cannabis Management
// License: GNU General Public License v3. See license.txt
//
// Custom, from-scratch Frappe Page (NOT a Workspace, NOT a modification of the
// existing "Profit and Loss Statement Child Accounts" Script Report) built to
// support one thing frappe-datatable cannot do: a column that appears only
// while a row carrying data for it is currently expanded/visible, and
// disappears again the instant that row is collapsed. Re-initializing
// frappe-datatable on every expand/collapse to fake this would reset every
// other expanded branch in the tree and be slow at the 10-13k row sizes this
// report can return once transaction/item drill-down is included - so this
// page renders its own plain HTML <table> instead and recomputes visible
// rows/columns with a single O(n) pass (see computeVisibleRowsAndColumns()
// below) on every toggle, search keystroke, and view switch.
//
// Deliberately reuses the exact same backend the existing report already
// uses - frappe.desk.query_report.run() against report_name "Profit and Loss
// Statement Child Accounts" - so there is no new Python in this app: same
// filters, same is_tree/parent_field contract, same columns/result/chart/
// report_summary shape. See cannabis_management/cannabis_management/report/
// profit_and_loss_statement_child_accounts/profit_and_loss_statement_child_accounts.py
// for how that payload is built, and financial_statements.py (same package)
// for attach_transaction_rows()/get_transaction_detail_columns(), which is
// where the 4 row "kinds" (account group, account leaf, transaction, item)
// and the 12 possible "transaction detail" columns come from.
//
// Visual structure/CSS organization mirrors this app's existing
// profit_and_loss_repo.js page closely (same dark-header/light-body
// dashboard aesthetic, same frappe.call pattern, same KPI-cards/chart/
// filters-panel/CSV-export approach) - see that file for the shared style.
// All class/id names here use a "pld-" prefix (distinct from that page's
// "pnl-" prefix) so both pages' injected <style> blocks can coexist in the
// same desk session without clashing.

frappe.pages["profit-and-loss-drilldown"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Profit and Loss (Drilldown)",
		single_column: true,
	});

	$(wrapper).find(".page-head").hide();

	var $body = $(page.body);
	$body.html('<div id="pld-root"></div>');
	var $root = $("#pld-root");

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

	// ── Stock Valuation Lineage drill-down (COGS only) ───────────────────────
	// A COGS item row sold via Sales Invoice/Delivery Note (see show_lineage
	// on the row - set server-side in make_item_row()) can expand one level
	// further into its backward valuation trace: Sold -> Produced/Repack ->
	// Consumed Input -> ... -> Purchased/Opening/Transferred - the exact same
	// engine as the standalone "Stock Valuation Lineage" report, fetched on
	// demand for just this one line via get_item_lineage(). These 4 columns
	// only ever appear on lineage rows, so the backend never returns them -
	// they're appended to state.dynamicColumnDefs by hand once the report
	// loads (see runReport()'s callback) so the same expand/collapse-driven
	// dynamic-column logic picks them up automatically.
	var LINEAGE_ONLY_COLUMNS = [
		{ label: "Phase", fieldname: "phase", fieldtype: "Data", width: 220 },
		{ label: "UOM", fieldname: "uom", fieldtype: "Data", width: 70 },
		{ label: "Warehouse", fieldname: "warehouse", fieldtype: "Link", options: "Warehouse", width: 160 },
		{ label: "Stock Ledger Entry", fieldname: "stock_ledger_entry", fieldtype: "Link", options: "Stock Ledger Entry", width: 170 },
	];
	var LINEAGE_METHOD = "cannabis_management.cannabis_management.report.stock_valuation_lineage.stock_valuation_lineage.get_item_lineage";

	// ── Account-level transaction/item drill-down - lazy, on demand ─────────
	// The backend (profit_and_loss_statement_child_accounts.py) skips its own
	// eager attach_transaction_rows() step for this page (see
	// filters.skip_transaction_drilldown in runReport() below) - building
	// every leaf account's transactions/items up front was what made every
	// report run slow, even though almost all of them start collapsed (see
	// seedDefaultExpandState()) and most never get expanded at all. Instead,
	// a leaf account's own transactions (and, for vouchers with an item
	// table, their line items) are fetched only once that specific row is
	// actually expanded - same on-demand shape as the lineage drill-down
	// above, just one level shallower in the tree.
	var DRILLDOWN_METHOD = "cannabis_management.cannabis_management.report.profit_and_loss_statement_child_accounts.profit_and_loss_statement_child_accounts.get_account_drilldown";
	var BULK_DRILLDOWN_METHOD = "cannabis_management.cannabis_management.report.profit_and_loss_statement_child_accounts.profit_and_loss_statement_child_accounts.get_accounts_drilldown";

	// Since the backend no longer eagerly builds any transaction/item rows
	// at initial load, `data` never carries a value for these fields at that
	// point either - so get_transaction_detail_columns() (data-driven, only
	// includes a column if some row actually has it) would always come back
	// empty. Hardcoded here instead, mirroring that same Python function's
	// column defs exactly, same reasoning as LINEAGE_ONLY_COLUMNS above: the
	// existing show/hide-while-expanded logic in
	// computeVisibleRowsAndColumns() only needs the DEFINITIONS up front: it
	// already decides per-render whether a column has any visible data.
	var TRANSACTION_DETAIL_COLUMN_DEFS = [
		{ label: "Posting Date", fieldname: "posting_date", fieldtype: "Date", width: 100 },
		{ label: "Voucher Type", fieldname: "voucher_type", fieldtype: "Data", width: 130 },
		{ label: "Voucher No", fieldname: "voucher_no", fieldtype: "Dynamic Link", options: "voucher_type", width: 160 },
		{ label: "Party", fieldname: "party", fieldtype: "Data", width: 140 },
		{ label: "Against", fieldname: "against", fieldtype: "Data", width: 140 },
		{ label: "Debit", fieldname: "debit", fieldtype: "Currency", options: "currency", width: 120 },
		{ label: "Credit", fieldname: "credit", fieldtype: "Currency", options: "currency", width: 120 },
		{ label: "Item Code", fieldname: "item_code", fieldtype: "Link", options: "Item", width: 120 },
		{ label: "Item Name", fieldname: "item_name", fieldtype: "Data", width: 160 },
		{ label: "Qty", fieldname: "qty", fieldtype: "Float", width: 80 },
		{ label: "Rate", fieldname: "rate", fieldtype: "Currency", options: "currency", width: 120 },
		{ label: "Amount", fieldname: "amount", fieldtype: "Currency", options: "currency", width: 100 },
	];

	var VOUCHER_TYPE_LABELS_INCOME = ["income"];

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
		// profit_and_loss_statement_child_accounts.js push() block) - 0, not 1.
		accumulated_values: 0,
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
		rowsByKey: {},
		lastVisible: [],
		lastDynamicColumns: [],
		fiscal_years: [],
		chart_type: "bar",
		chart_instance: null,
	};

	// ── Inject CSS ──────────────────────────────────────────────────────────
	if (!document.getElementById("pld-styles")) {
		var style = document.createElement("style");
		style.id = "pld-styles";
		style.textContent = `
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

            @keyframes pld-spin    { to { transform: rotate(360deg); } }
            @keyframes pld-fade-up { from { opacity:0; transform:translateY(14px); } to { opacity:1; transform:translateY(0); } }
            @keyframes pld-shimmer { from { background-position: -600px 0; } to { background-position: 600px 0; } }
            @keyframes pld-pulse-ring {
                0%   { box-shadow: 0 0 0 0 rgba(99,102,241,0.35); }
                70%  { box-shadow: 0 0 0 8px rgba(99,102,241,0); }
                100% { box-shadow: 0 0 0 0 rgba(99,102,241,0); }
            }

            #pld-root {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #eef0f6;
                min-height: 100vh;
                padding: 0;
                -webkit-font-smoothing: antialiased;
            }
            #pld-root ::-webkit-scrollbar { width: 6px; height: 6px; }
            #pld-root ::-webkit-scrollbar-track { background: #f1f5f9; }
            #pld-root ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 99px; }
            #pld-root ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

            .pld-header {
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
            .pld-header::before {
                content: '';
                position: absolute; inset: 0;
                background-image: radial-gradient(rgba(255,255,255,0.04) 1px, transparent 1px);
                background-size: 24px 24px;
                pointer-events: none;
            }
            .pld-header-inner {
                position: relative; z-index: 1;
                display: flex; align-items: center; justify-content: space-between;
                flex-wrap: wrap; gap: 14px;
            }
            .pld-title-block { display: flex; align-items: center; gap: 16px; }
            .pld-logo-icon {
                width: 50px; height: 50px;
                background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                border-radius: 15px;
                display: flex; align-items: center; justify-content: center;
                font-size: 24px;
                box-shadow: 0 0 0 1px rgba(255,255,255,0.12), 0 8px 24px rgba(99,102,241,0.5);
            }
            .pld-main-title { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; margin: 0; color: #fff; }
            .pld-subtitle { font-size: 12.5px; color: rgba(255,255,255,0.5); margin: 3px 0 0; letter-spacing: 0.1px; }
            .pld-run-btn {
                background: linear-gradient(135deg, #6366f1 0%, #7c3aed 100%);
                border: none; color: #fff;
                padding: 11px 26px; border-radius: 12px;
                font-size: 13.5px; font-weight: 700; cursor: pointer;
                box-shadow: 0 1px 0 rgba(255,255,255,0.15) inset, 0 6px 20px rgba(99,102,241,0.55);
                transition: all 0.2s; display: flex; align-items: center; gap: 8px;
                white-space: nowrap; letter-spacing: 0.1px;
            }
            .pld-run-btn:hover { transform: translateY(-2px); box-shadow: 0 1px 0 rgba(255,255,255,0.15) inset, 0 10px 28px rgba(99,102,241,0.65); }
            .pld-run-btn:active { transform: translateY(0); }
            .pld-run-btn.loading { animation: pld-pulse-ring 1.2s ease-out infinite; }
            .pld-run-btn .btn-spinner { display: none; font-size: 16px; }
            .pld-run-btn.loading .btn-text { display: none; }
            .pld-run-btn.loading .btn-spinner { display: inline-block; }

            .pld-filters-panel { background: #fff; border-bottom: 1px solid #e8eaf0; padding: 16px 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
            .pld-filters-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 10px 14px; align-items: end; }
            .pld-field { display: flex; flex-direction: column; gap: 5px; }
            .pld-field label { font-size: 10.5px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.7px; }
            .pld-field select, .pld-field input[type="text"], .pld-field input[type="date"] {
                border: 1.5px solid #e2e8f0; border-radius: 9px; padding: 7px 10px;
                font-size: 13px; font-weight: 500; color: #1e293b; background: #f8fafc;
                outline: none; transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
                width: 100%; box-sizing: border-box; font-family: inherit;
            }
            .pld-field select:hover, .pld-field input:hover { border-color: #c7d2fe; }
            .pld-field select:focus, .pld-field input:focus { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.14); background: #fff; }
            .pld-filters-row2 { margin-top: 14px; display: flex; gap: 24px; flex-wrap: wrap; align-items: center; padding-top: 14px; border-top: 1px dashed #e8eaf0; }
            .pld-check-field { display: flex; align-items: center; gap: 9px; cursor: pointer; }
            .pld-check-field input[type="checkbox"] { display: none; }
            .pld-toggle-track { width: 34px; height: 19px; background: #d1d5db; border-radius: 99px; position: relative; transition: background 0.2s; flex-shrink: 0; cursor: pointer; }
            .pld-toggle-track::after { content: ''; position: absolute; top: 2px; left: 2px; width: 15px; height: 15px; background: #fff; border-radius: 50%; transition: transform 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
            .pld-check-field input:checked + .pld-toggle-track { background: #6366f1; }
            .pld-check-field input:checked + .pld-toggle-track::after { transform: translateX(15px); }
            .pld-check-field span { font-size: 12.5px; color: #475569; font-weight: 500; cursor: pointer; user-select: none; }

            .pld-body { padding: 24px 40px 32px; }
            .pld-warning-banner {
                background: #fffbeb; border: 1px solid #fde68a; color: #92400e;
                border-radius: 12px; padding: 10px 16px; font-size: 12.5px; font-weight: 600;
                margin-bottom: 16px; display: flex; align-items: center; gap: 8px;
            }
            .pld-placeholder, .pld-loader {
                background: #fff; border-radius: 20px; padding: 72px 24px; text-align: center;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05), 0 4px 16px rgba(0,0,0,0.04);
                border: 1px solid #f1f5f9; color: #94a3b8;
            }
            .pld-placeholder .ph-icon { font-size: 56px; margin-bottom: 16px; display: block; filter: grayscale(0.2); }
            .pld-placeholder p { font-size: 15px; color: #64748b; line-height: 1.6; }
            .pld-placeholder strong { color: #6366f1; }
            .pld-spinner { width: 44px; height: 44px; border: 3px solid #e2e8f0; border-top-color: #6366f1; border-radius: 50%; animation: pld-spin 0.65s linear infinite; margin: 0 auto 16px; }
            .pld-loader p { color: #64748b; font-size: 14px; font-weight: 500; }

            .pld-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 22px; }
            .pld-kpi-card {
                background: #fff; border-radius: 18px; padding: 22px 24px 18px;
                box-shadow: 0 1px 0 rgba(255,255,255,0.8) inset, 0 2px 6px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.05);
                border: 1px solid rgba(226,232,240,0.8);
                position: relative; overflow: hidden;
                transition: transform 0.2s cubic-bezier(.34,1.56,.64,1), box-shadow 0.2s;
                animation: pld-fade-up 0.4s ease both;
            }
            .pld-kpi-card:nth-child(1) { animation-delay: 0.05s; }
            .pld-kpi-card:nth-child(2) { animation-delay: 0.10s; }
            .pld-kpi-card:nth-child(3) { animation-delay: 0.15s; }
            .pld-kpi-card:nth-child(4) { animation-delay: 0.20s; }
            .pld-kpi-card:nth-child(5) { animation-delay: 0.25s; }
            .pld-kpi-card:hover { transform: translateY(-4px) scale(1.01); box-shadow: 0 1px 0 rgba(255,255,255,0.8) inset, 0 12px 32px rgba(0,0,0,0.1); }
            .pld-kpi-card::before { content: ''; position: absolute; top: 0; left: 0; bottom: 0; width: 4px; border-radius: 18px 0 0 18px; }
            .pld-kpi-income::before   { background: linear-gradient(180deg, #10b981, #059669); }
            .pld-kpi-cogs::before     { background: linear-gradient(180deg, #f59e0b, #d97706); }
            .pld-kpi-gross::before    { background: linear-gradient(180deg, #0ea5e9, #0284c7); }
            .pld-kpi-expense::before  { background: linear-gradient(180deg, #ef4444, #dc2626); }
            .pld-kpi-profit::before   { background: linear-gradient(180deg, #6366f1, #8b5cf6); }
            .kpi-icon { width: 42px; height: 42px; border-radius: 13px; display: flex; align-items: center; justify-content: center; font-size: 20px; margin-bottom: 14px; }
            .pld-kpi-income .kpi-icon  { background: linear-gradient(135deg, #d1fae5, #a7f3d0); }
            .pld-kpi-cogs .kpi-icon    { background: linear-gradient(135deg, #fef3c7, #fde68a); }
            .pld-kpi-gross .kpi-icon   { background: linear-gradient(135deg, #e0f2fe, #bae6fd); }
            .pld-kpi-expense .kpi-icon { background: linear-gradient(135deg, #fee2e2, #fecaca); }
            .pld-kpi-profit .kpi-icon  { background: linear-gradient(135deg, #ede9fe, #ddd6fe); }
            .kpi-label { font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.7px; }
            .kpi-value { font-size: 26px; font-weight: 800; color: #0f172a; margin: 5px 0 8px; letter-spacing: -1px; line-height: 1; }
            .kpi-value.positive { color: #059669; }
            .kpi-value.negative { color: #dc2626; }
            .kpi-badge { display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; font-weight: 700; padding: 3px 9px; border-radius: 20px; }
            .kpi-badge.up { background: #dcfce7; color: #15803d; }
            .kpi-badge.down { background: #fee2e2; color: #b91c1c; }
            .kpi-badge.neutral { background: #f1f5f9; color: #64748b; }

            .pld-content-grid { display: grid; grid-template-columns: 1fr; gap: 20px; }

            .pld-chart-card { background: #fff; border-radius: 18px; padding: 24px 26px; box-shadow: 0 2px 6px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.05); border: 1px solid rgba(226,232,240,0.8); animation: pld-fade-up 0.4s 0.1s ease both; }
            .pld-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 10px; }
            .pld-card-title { font-size: 15px; font-weight: 700; color: #0f172a; letter-spacing: -0.2px; }
            .pld-card-subtitle { font-size: 12px; color: #94a3b8; margin-top: 2px; }
            .pld-chart-tabs { display: flex; gap: 4px; background: #f1f5f9; border-radius: 9px; padding: 3px; }
            .pld-chart-tab { padding: 5px 13px; border-radius: 7px; font-size: 12px; font-weight: 600; border: none; background: transparent; color: #64748b; cursor: pointer; transition: all 0.15s; }
            .pld-chart-tab:hover { color: #475569; }
            .pld-chart-tab.active { background: #fff; color: #4338ca; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
            .pld-chart-wrap { position: relative; height: 290px; }
            .pld-chart-wrap canvas { max-height: 290px; }

            .pld-table-card { background: #fff; border-radius: 18px; box-shadow: 0 2px 6px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.05); border: 1px solid rgba(226,232,240,0.8); overflow: hidden; animation: pld-fade-up 0.4s 0.15s ease both; }
            .pld-table-card-header { display: flex; align-items: center; justify-content: space-between; padding: 18px 24px 16px; flex-wrap: wrap; gap: 12px; border-bottom: 1px solid #f1f5f9; background: linear-gradient(180deg, #fafbff, #fff); }
            .pld-search-box { display: flex; align-items: center; gap: 8px; background: #f8fafc; border-radius: 9px; padding: 7px 13px; border: 1.5px solid #e2e8f0; transition: all 0.15s; }
            .pld-search-box:focus-within { background: #fff; border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.12); }
            .pld-search-box svg { color: #94a3b8; flex-shrink: 0; }
            .pld-search-input { border: none; background: transparent; outline: none; font-size: 13px; color: #1e293b; width: 190px; font-family: inherit; }
            .pld-search-input::placeholder { color: #94a3b8; }
            .pld-table-actions { display: flex; gap: 8px; flex-wrap: wrap; }
            .pld-action-btn { padding: 7px 14px; border-radius: 9px; font-size: 12px; font-weight: 600; border: 1.5px solid #e2e8f0; background: #f8fafc; color: #475569; cursor: pointer; transition: all 0.15s; display: flex; align-items: center; gap: 5px; font-family: inherit; }
            .pld-action-btn:hover { background: #f1f5f9; border-color: #c7d2fe; color: #4338ca; }
            .pld-action-btn.primary { background: linear-gradient(135deg, #6366f1, #7c3aed); border-color: transparent; color: #fff; box-shadow: 0 2px 8px rgba(99,102,241,0.35); }
            .pld-action-btn.primary:hover { background: linear-gradient(135deg, #4f46e5, #6d28d9); box-shadow: 0 4px 12px rgba(99,102,241,0.45); transform: translateY(-1px); }

            /* Bounded, self-contained scroll box: a sticky thead only has
               something real to stick to once ITS OWN container actually
               scrolls. Before this, .pld-table-scroll had no height limit
               (it just grew with content) so the whole page scrolled past
               it instead - "sticky" had no scroll boundary to pin against,
               and the ancestor .pld-table-card's overflow:hidden (there for
               the rounded corners) silently became the sticky containing
               block instead, which never itself moves. Giving this element
               its own max-height + overflow makes it the nearest scrolling
               ancestor, so the header now reliably stays put while rows
               scroll underneath it, no matter how far you scroll. */
            .pld-table-scroll { overflow: auto; max-height: 65vh; }
            .pld-table { width: 100%; border-collapse: collapse; font-size: 13px; }
            .pld-table thead { position: sticky; top: 0; z-index: 2; }
            .pld-table thead tr { background: #f8fafc; border-bottom: 2px solid #e2e8f0; }
            .pld-table thead th { position: sticky; top: 0; padding: 12px 14px; text-align: left; font-size: 10.5px; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.8px; white-space: nowrap; background: #f8fafc; z-index: 2; }
            .pld-table thead th.num { text-align: right; }
            .pld-table tbody tr.row-leaf:nth-child(even) td { background: #fafbff; }
            .pld-table tbody tr { border-bottom: 1px solid #f1f5f9; transition: background 0.12s; }
            .pld-table tbody tr:not(.row-section-header):not(.row-total):not(.row-net-profit):hover td { background: #f0f4ff !important; }
            .pld-table td { padding: 9px 14px; color: #334155; vertical-align: middle; }
            .pld-table td.num { text-align: right; font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }

            .row-section-header td { background: linear-gradient(90deg, #eef2ff 0%, #f5f3ff 100%) !important; font-weight: 800; font-size: 13px; color: #312e81; border-top: 2px solid #c7d2fe; border-bottom: 2px solid #c7d2fe; padding-top: 12px; padding-bottom: 12px; letter-spacing: 0.1px; }
            .row-group-header td { background: #f8fafc !important; font-weight: 600; color: #1e293b; font-size: 13px; border-bottom: 1px solid #e8edf4; }
            .row-total td { background: linear-gradient(90deg, #1e293b, #0f172a) !important; color: #e2e8f0 !important; font-weight: 700; font-size: 13px; border-top: 2px solid #334155 !important; border-bottom: 2px solid #334155 !important; padding-top: 11px; padding-bottom: 11px; }
            .row-total td .num-positive { color: #86efac !important; }
            .row-total td .num-negative { color: #fca5a5 !important; }
            .row-net-profit td { background: linear-gradient(90deg, #1e1b4b 0%, #312e81 50%, #1e1b4b 100%) !important; color: #e0e7ff !important; font-weight: 800; font-size: 14px; border-top: 3px solid #6366f1 !important; border-bottom: 3px solid #6366f1 !important; padding-top: 14px; padding-bottom: 14px; letter-spacing: -0.2px; }
            .row-net-profit td .num-positive, .row-net-profit td .net-positive { color: #6ee7b7 !important; font-size: 15px; }
            .row-net-profit td .num-negative, .row-net-profit td .net-negative { color: #fca5a5 !important; font-size: 15px; }
            .row-transaction td { background: #f8fbff; color: #475569; font-size: 12.5px; }
            .row-item td { background: #fdfdff; color: #64748b; font-size: 12px; }
            .row-lineage td { background: #fbfaff; color: #7c7a99; font-size: 11.5px; font-style: italic; }
            .row-lineage .pld-account-cell span:not(.pld-indent):not(.pld-toggle-spacer) { font-style: normal; }

            .pld-account-cell { display: flex; align-items: center; }
            .pld-indent { display: inline-block; flex-shrink: 0; }
            .pld-toggle { width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; color: #cbd5e1; flex-shrink: 0; font-size: 9px; transition: transform 0.18s, color 0.15s; margin-right: 3px; user-select: none; border-radius: 4px; }
            .pld-toggle:hover { background: #e0e7ff; color: #6366f1; }
            .pld-toggle.open { transform: rotate(90deg); color: #6366f1; }
            .pld-toggle.loading { animation: pld-spin 0.8s linear infinite; transform-origin: center; cursor: wait; }
            .pld-toggle-lineage { color: #a78bfa; }
            .pld-toggle-lineage:hover { background: #ede9fe; color: #7c3aed; }
            .pld-toggle-lineage.open { color: #7c3aed; }
            .pld-toggle-lineage.loading { animation: pld-spin 0.8s linear infinite; transform-origin: center; cursor: wait; }
            .pld-toggle-spacer { width: 23px; display: inline-block; flex-shrink: 0; }
            .pld-acct-icon { width: 24px; height: 24px; border-radius: 7px; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; margin-right: 8px; flex-shrink: 0; }
            .icon-income  { background: linear-gradient(135deg, #d1fae5, #a7f3d0); color: #065f46; }
            .icon-expense { background: linear-gradient(135deg, #fef3c7, #fde68a); color: #78350f; }
            .icon-profit  { background: linear-gradient(135deg, #ede9fe, #ddd6fe); color: #4c1d95; }

            .num-positive { color: #16a34a; font-weight: 600; }
            .num-negative { color: #dc2626; font-weight: 600; }
            .num-zero { color: #cbd5e1; }

            .pld-view-pills { display: flex; gap: 3px; background: #f1f5f9; border-radius: 10px; padding: 3px; }
            .pld-view-pill { padding: 5px 14px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; color: #64748b; border: none; background: transparent; font-family: inherit; }
            .pld-view-pill:hover { color: #475569; }
            .pld-view-pill.active { background: #fff; color: #4338ca; box-shadow: 0 1px 4px rgba(0,0,0,0.1), 0 0 0 1px rgba(99,102,241,0.1); }

            .pld-footer { text-align: center; padding: 18px 40px 24px; font-size: 12px; color: #94a3b8; letter-spacing: 0.1px; }
            .pld-footer strong { color: #6366f1; }

            @media (max-width: 900px) {
                .pld-header { padding: 20px 20px; }
                .pld-filters-panel { padding: 14px 20px; }
                .pld-body { padding: 16px 20px 24px; }
                .pld-filters-grid { grid-template-columns: 1fr 1fr; }
            }
            @media (max-width: 600px) {
                .pld-filters-grid { grid-template-columns: 1fr; }
                .pld-kpis { grid-template-columns: 1fr 1fr; }
                .pld-kpi-card { padding: 16px; }
                .kpi-value { font-size: 20px; }
                .pld-table-card-header { flex-direction: column; align-items: flex-start; }
                .pld-search-input { width: 140px; }
            }

            /* ── Print: header title/company/fiscal-year + table exactly as
               currently expanded on screen; everything else (filters, KPI
               cards, chart, search/expand/collapse/CSV/print chrome) hidden. */
            @media print {
                .pld-run-btn, .pld-filters-panel, .pld-kpis,
                .pld-content-grid > .pld-chart-card,
                .pld-table-card-header, .pld-footer { display: none !important; }
                #pld-root { background: #fff; }
                .pld-header { background: #fff !important; color: #000 !important; box-shadow: none; padding: 0 0 12px; }
                .pld-header::before { display: none; }
                .pld-main-title, .pld-subtitle { color: #000 !important; }
                .pld-logo-icon { display: none; }
                .pld-body { padding: 10px 0; }
                .pld-table-card { box-shadow: none; border: none; }
                .pld-table-scroll { overflow: visible; max-height: none; }
                .pld-table thead, .pld-table thead th { position: static; }
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
	//   'group'       - real group account, OR a synthetic section-heading row
	//                   (Income / Cost of Goods Sold / Expense - see
	//                   get_section_heading_row() in the .py, which sets
	//                   is_group=1 but has no "account" field at all)
	//   'leaf'        - real leaf account (has a real, unquoted "account")
	//   'transaction' - a voucher drilled into under a leaf account
	//   'item'        - a line item drilled into under a transaction row
	//   'total'       - a synthetic total/diff/net-profit row (quoted
	//                   "account", never collapsible, never a link)
	// Every synthetic row financial_statements.py builds (total rows,
	// transaction rows, item rows) quotes its "account" value in literal
	// single-quotes specifically so Link-fieldtype rendering treats it as
	// plain text instead of a (broken) link to a real Account - see the
	// comment on make_transaction_row() in that file. We reuse that same
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
	// financial_statements.py builds carry a real (or quoted) "account" value
	// - the one exception is this report's own get_section_heading_row(),
	// which omits "account" entirely, so we fall back to account_name for
	// those 3 rows (Income / Cost of Goods Sold / Expense - unique among
	// themselves, which is all that matters here).
	function rowKey(row) {
		return row.account || row.account_name;
	}

	// reset=false merges into the existing state.rowsByKey instead of
	// wiping it - used when annotating a batch of rows freshly fetched by
	// the on-demand drill-down below, which must not lose track of every
	// row already on screen.
	function annotateRows(allRows, reset) {
		if (reset !== false) state.rowsByKey = {};
		for (var i = 0; i < allRows.length; i++) {
			var row = allRows[i];
			if (!row) continue;
			row.__kind = classifyRow(row);
			row.__key = row.__kind === "blank" ? null : rowKey(row);
			if (row.__key) state.rowsByKey[row.__key] = row;
			if (row.__kind === "transaction") {
				var indent = row.indent || 0;
				var next = allRows[i + 1];
				row.__hasItems = !!(next && (next.indent || 0) === indent + 1 && next.item_code);
			}
		}
	}

	// Seed a sensible default expand state so the initial view reads like a
	// normal income statement, not an exploded wall of transactions: account
	// rows at indent <= 2 start expanded (absence from the map = expanded);
	// deeper account rows, every transaction row, and every lineage-eligible
	// COGS item row start collapsed (nobody wants a 50-row valuation trace
	// unfolding under every single sold item by default).
	function seedDefaultExpandState(allRows) {
		var expanded = {};
		for (var i = 0; i < allRows.length; i++) {
			var row = allRows[i];
			if (!row || row.__kind === "blank" || row.__kind === "total") continue;
			if (row.__kind === "item") {
				if (row.show_lineage) expanded[row.__key] = false;
				continue;
			}
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
	// i.e. columns that show only while a row with data for them is expanded,
	// and vanish again the instant that row collapses. Deliberately NOT the
	// reference page's ancestor-walk (O(n^2) - fine for ~100 account rows,
	// far too slow once transaction/item drill-down pushes this past 10k+
	// rows): every row already carries a correct pre-order `indent`, so a
	// single pass with a small "currently collapsed" stack is enough.
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

			// A lineage-eligible item row is also collapsible: its lineage
			// phase rows (fetched on demand) are its children, one level
			// deeper, exactly like a leaf account's transactions.
			var isCollapsible = row.__kind === "group" || row.__kind === "leaf" || row.__kind === "transaction"
				|| (row.__kind === "item" && row.show_lineage);
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
        <div class="pld-header">
            <div class="pld-header-inner">
                <div class="pld-title-block">
                    <div class="pld-logo-icon">📊</div>
                    <div>
                        <div class="pld-main-title">Profit &amp; Loss (Drilldown)</div>
                        <div class="pld-subtitle" id="pld-header-sub">Select filters and run the report</div>
                    </div>
                </div>
                <button class="pld-run-btn" id="pld-run-btn">
                    <svg class="btn-text" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M5 3l14 9-14 9V3z"/></svg>
                    <span class="btn-text">Run Report</span>
                    <span class="btn-spinner">⟳</span>
                </button>
            </div>
        </div>

        <div class="pld-filters-panel">
            <div class="pld-filters-grid">
                <div class="pld-field">
                    <label>Company</label>
                    <select id="pld-company"></select>
                </div>
                <div class="pld-field">
                    <label>Filter Based On</label>
                    <select id="pld-filter-based-on">
                        <option value="Fiscal Year">Fiscal Year</option>
                        <option value="Date Range">Date Range</option>
                    </select>
                </div>
                <div class="pld-field" id="pld-fy-from-wrap">
                    <label>From Fiscal Year</label>
                    <select id="pld-from-fy"></select>
                </div>
                <div class="pld-field" id="pld-fy-to-wrap">
                    <label>To Fiscal Year</label>
                    <select id="pld-to-fy"></select>
                </div>
                <div class="pld-field" id="pld-date-from-wrap" style="display:none">
                    <label>Start Date</label>
                    <input type="date" id="pld-start-date"/>
                </div>
                <div class="pld-field" id="pld-date-to-wrap" style="display:none">
                    <label>End Date</label>
                    <input type="date" id="pld-end-date"/>
                </div>
                <div class="pld-field">
                    <label>Periodicity</label>
                    <select id="pld-periodicity">
                        <option value="Monthly">Monthly</option>
                        <option value="Quarterly">Quarterly</option>
                        <option value="Half-Yearly">Half-Yearly</option>
                        <option value="Yearly" selected>Yearly</option>
                    </select>
                </div>
                <div class="pld-field">
                    <label>Currency</label>
                    <select id="pld-currency">
                        <option value="">Company Default</option>
                    </select>
                </div>
                <div class="pld-field">
                    <label>View</label>
                    <select id="pld-view">
                        <option value="Report">Report View</option>
                        <option value="Growth">Growth View</option>
                        <option value="Margin">Percentage View (% of Income)</option>
                    </select>
                </div>
            </div>
            <div class="pld-filters-row2">
                <label class="pld-check-field">
                    <input type="checkbox" id="pld-accum"/>
                    <span class="pld-toggle-track"></span>
                    <span>Accumulated Values</span>
                </label>
                <label class="pld-check-field">
                    <input type="checkbox" id="pld-show-zero"/>
                    <span class="pld-toggle-track"></span>
                    <span>Show Zero Values</span>
                </label>
                <label class="pld-check-field">
                    <input type="checkbox" id="pld-default-book" checked/>
                    <span class="pld-toggle-track"></span>
                    <span>Include Default Book Entries</span>
                </label>
            </div>
        </div>

        <div class="pld-body" id="pld-body">
            <div class="pld-placeholder">
                <div class="ph-icon">📈</div>
                <p>Configure your filters and click <strong>Run Report</strong> to generate the Profit &amp; Loss drilldown.</p>
            </div>
        </div>

        <div class="pld-footer" id="pld-footer" style="display:none">
            Generated on <span id="pld-gen-time"></span> &nbsp;·&nbsp; <strong id="pld-company-name"></strong>
        </div>
        `;
	}

	// ── Render body content ──────────────────────────────────────────────────
	function renderResults() {
		var $b = $("#pld-body");
		if (state.loading) {
			$b.html('<div class="pld-loader"><div class="pld-spinner"></div><p>Fetching financial data…</p></div>');
			return;
		}
		if (!state.allRows || !state.allRows.length) return;

		var currency = getCurrency();
		var warnHtml = state.reportMessage
			? '<div class="pld-warning-banner">⚠️ ' + escHtml(state.reportMessage) + '</div>'
			: "";
		var kpiHtml = buildKpiCards(currency);
		var chartHtml = buildChartCard();
		var tableHtml = buildTableCard();

		$b.html(warnHtml +
			'<div class="pld-kpis" id="pld-kpis">' + kpiHtml + '</div>' +
			'<div class="pld-content-grid">' + chartHtml + tableHtml + '</div>');

		renderChart();
		rerenderTable();

		$("#pld-gen-time").text(frappe.datetime.now_datetime());
		$("#pld-company-name").text(state.company);
		$("#pld-footer").show();
	}

	// ── KPI Cards ────────────────────────────────────────────────────────────
	// report_summary already comes back in the exact order get_report_summary()
	// in profit_and_loss_statement_child_accounts.py builds it - 5 real entries
	// (Total Income / Total COGS / Gross Profit / Total Expense / Net Profit)
	// interleaved with separator entries - so we render positionally rather
	// than string-matching on label text (which would break under
	// translation or if the "Net Profit" vs "Net Profit This Year" label
	// varies).
	function buildKpiCards(currency) {
		var summary = (state.summary || []).filter(function (s) { return s && s.type !== "separator"; });
		var configs = [
			{ cls: "pld-kpi-income", icon: "💰", badge: "up", badgeText: "Revenue" },
			{ cls: "pld-kpi-cogs", icon: "📦", badge: "neutral", badgeText: "Cost Base" },
			{ cls: "pld-kpi-gross", icon: "📐", badge: null },
			{ cls: "pld-kpi-expense", icon: "💸", badge: "neutral", badgeText: "Expenses" },
			{ cls: "pld-kpi-profit", icon: "📈", badge: null },
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
				badgeText = val >= 0 ? "▲ Positive" : "▼ Negative";
			}
			html += '<div class="pld-kpi-card ' + cfg.cls + '">' +
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
            <div class="pld-chart-card">
                <div class="pld-card-header">
                    <div>
                        <div class="pld-card-title">Financial Overview</div>
                        <div class="pld-card-subtitle">${escHtml(state.company)}${period ? " &nbsp;·&nbsp; " + escHtml(period) : ""}</div>
                    </div>
                    <div class="pld-chart-tabs">
                        <button class="pld-chart-tab ${state.chart_type === "bar" ? "active" : ""}" data-type="bar">Bar</button>
                        <button class="pld-chart-tab ${state.chart_type === "line" ? "active" : ""}" data-type="line">Line</button>
                    </div>
                </div>
                <div class="pld-chart-wrap">
                    <canvas id="pld-chart"></canvas>
                </div>
            </div>
        `;
	}

	function renderChart() {
		ensureChartJs(function () {
			var cd = state.chartData;
			if (!cd || !cd.data) return;
			if (state.chart_instance) { state.chart_instance.destroy(); state.chart_instance = null; }

			var ctx = document.getElementById("pld-chart");
			if (!ctx) return;

			var labels = cd.data.labels || [];
			var palette = [
				{ bg: "rgba(16,185,129,0.15)", border: "#10b981" },
				{ bg: "rgba(245,158,11,0.15)", border: "#f59e0b" },
				{ bg: "rgba(14,165,233,0.15)", border: "#0ea5e9" },
				{ bg: "rgba(239,68,68,0.15)", border: "#ef4444" },
				{ bg: "rgba(99,102,241,0.15)", border: "#6366f1" },
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

			$(".pld-chart-tab").off("click").on("click", function () {
				$(".pld-chart-tab").removeClass("active");
				$(this).addClass("active");
				state.chart_type = $(this).data("type");
				renderChart();
			});
		});
	}

	// ── Table Card ────────────────────────────────────────────────────────────
	function buildTableCard() {
		return `
            <div class="pld-table-card">
                <div class="pld-table-card-header">
                    <div class="pld-card-title">Account Breakdown</div>
                    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                        <div class="pld-view-pills" id="pld-view-pills">
                            <button class="pld-view-pill ${state.selected_view === "Report" ? "active" : ""}" data-view="Report">Report</button>
                            <button class="pld-view-pill ${state.selected_view === "Growth" ? "active" : ""}" data-view="Growth">Growth</button>
                            <button class="pld-view-pill ${state.selected_view === "Margin" ? "active" : ""}" data-view="Margin">%</button>
                        </div>
                        <div class="pld-search-box">
                            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                            <input class="pld-search-input" id="pld-search" type="text" placeholder="Search accounts…"/>
                        </div>
                        <div class="pld-table-actions">
                            <button class="pld-action-btn" id="pld-expand-all">⊞ Expand All</button>
                            <button class="pld-action-btn" id="pld-collapse-all">⊟ Collapse All</button>
                            <button class="pld-action-btn" id="pld-print-btn">🖨 Print</button>
                            <button class="pld-action-btn primary" id="pld-export-btn">↓ Export CSV</button>
                        </div>
                    </div>
                </div>
                <div class="pld-table-scroll">
                    <table class="pld-table" id="pld-table">
                        <thead id="pld-thead"></thead>
                        <tbody id="pld-tbody"></tbody>
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
		} else if (col.fieldtype === "Link" && col.options) {
			formatted = frappe.utils.get_form_link(col.options, val, true, escHtml(String(val)));
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

		var isLineageToggle = row.__kind === "item" && row.show_lineage;
		if (row.__kind === "group" || row.__kind === "leaf" || row.__kind === "transaction" || isLineageToggle) {
			// Same !== false ("absent from the map = open") convention for
			// every collapsible kind, lineage-eligible items included -
			// seedDefaultExpandState() explicitly seeds these to false so
			// they still start closed despite the shared convention.
			var isOpen = state.expandedState[row.__key] !== false;
			// A leaf account's OWN transactions/items are fetched on demand
			// the first time it's expanded (see bindTableEventsOnce()'s
			// .pld-toggle handler) - row.__txnLoading mirrors
			// row.__lineageLoading's spinner treatment below for that wait.
			var isLoading = row.__lineageLoading || row.__txnLoading;
			var lineageClass = isLineageToggle ? " pld-toggle-lineage" : "";
			var title = isLineageToggle ? ' title="Trace valuation lineage"' : "";
			toggleHtml = '<span class="pld-toggle' + lineageClass + (isLoading ? " loading" : "") + (isOpen ? " open" : "") + '" data-key="' + escHtml(row.__key) + '"' + title + '>' + (isLoading ? "⟳" : "▶") + '</span>';
		} else if (row.__kind === "item" || row.__kind === "lineage") {
			toggleHtml = '<span class="pld-toggle-spacer"></span>';
		}

		if (row.__kind === "group" && (row.indent || 0) === 0) {
			var lower = (row.account_name || "").toLowerCase();
			var isIncome = lower.indexOf("income") !== -1;
			iconHtml = '<span class="pld-acct-icon ' + (isIncome ? "icon-income" : "icon-expense") + '">' + (isIncome ? "↑" : "↓") + "</span>";
		}

		if (row.__kind === "transaction") {
			labelHtml = frappe.utils.get_form_link(row.voucher_type, row.voucher_no, true, label);
		} else if (row.__kind === "item" || row.__kind === "lineage") {
			labelHtml = row.item_code ? frappe.utils.get_form_link("Item", row.item_code, true, label) : label;
		} else {
			// Real account rows (leaf or group) and every synthetic
			// total/heading row never navigate anywhere - they already
			// expand in place, so plain text only (see the existing
			// report .js files' identical rule/comment).
			labelHtml = label;
		}

		return '<td><div class="pld-account-cell">' +
			'<span class="pld-indent" style="min-width:' + indentPx + 'px"></span>' +
			toggleHtml + iconHtml + "<span>" + labelHtml + "</span>" +
			"</div></td>";
	}

	function rowClassFor(row, isLastRealRow) {
		if (row.__kind === "group") return (row.indent || 0) === 0 ? "row-section-header" : "row-group-header";
		if (row.__kind === "total") return isLastRealRow ? "row-net-profit" : "row-total";
		if (row.__kind === "transaction") return "row-transaction";
		if (row.__kind === "item") return "row-item";
		if (row.__kind === "lineage") return "row-lineage";
		return "row-leaf";
	}

	function buildTableRows(visibleRows, baseColumns, dynamicColumns) {
		var currency = getCurrency();
		var html = "";
		var totalCols = baseColumns.length + dynamicColumns.length;

		// The final row of the whole (unfiltered) dataset is always the
		// bottom-line Net Profit row (data.append(net_profit_row) is
		// literally the last statement in execute()) - detected positionally
		// rather than by matching label text, since that label can read
		// "Net Profit" or "Net Profit This Year" depending on the period.
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
		var searchText = ($("#pld-search").val() || "").trim();
		var res = computeVisibleRowsAndColumns(state.allRows, state.expandedState, state.dynamicColumnDefs, searchText);
		state.lastVisible = res.visible;
		state.lastDynamicColumns = res.dynamicColumns;
		$("#pld-thead").html("<tr>" + buildColumnHeaders(state.baseColumns, res.dynamicColumns) + "</tr>");
		$("#pld-tbody").html(buildTableRows(res.visible, state.baseColumns, res.dynamicColumns));
	}

	// ── Table event binding (delegated on the persistent #pld-root so it
	// survives every innerHTML rebuild of the body underneath it) ───────────
	// Turns one Stock Valuation Lineage phase row (get_item_lineage()'s own
	// shape: phase/item_code/qty/uom/valuation_rate/amount/warehouse/
	// voucher_type/voucher_no/posting_date/stock_ledger_entry/indent) into
	// this table's row shape. Reuses "rate"/"amount"/"item_code"/"qty"/
	// "voucher_type"/"voucher_no"/"posting_date" so the EXISTING
	// transaction-detail columns already know how to render them; only
	// "phase"/"uom"/"warehouse"/"stock_ledger_entry" are genuinely new (see
	// LINEAGE_ONLY_COLUMNS).
	function lineageRowToDisplayRow(lineageRow, itemRow, idx) {
		var key = itemRow.__key + "::lineage::" + idx;
		return {
			__kind: "lineage",
			__key: key,
			account: "'" + key + "'",
			parent_account: itemRow.__key,
			indent: (itemRow.indent || 0) + 1 + (lineageRow.indent || 0),
			currency: itemRow.currency,
			account_name: lineageRow.phase + (lineageRow.item_name || lineageRow.item_code
				? " — " + (lineageRow.item_name || lineageRow.item_code) : ""),
			phase: lineageRow.phase,
			item_code: lineageRow.item_code,
			item_name: lineageRow.item_name,
			qty: lineageRow.qty,
			uom: lineageRow.uom,
			rate: lineageRow.valuation_rate,
			amount: lineageRow.amount,
			warehouse: lineageRow.warehouse,
			voucher_type: lineageRow.voucher_type,
			voucher_no: lineageRow.voucher_no,
			posting_date: lineageRow.posting_date,
			stock_ledger_entry: lineageRow.stock_ledger_entry,
		};
	}

	function insertRowsAfter(afterRow, newRows) {
		var idx = state.allRows.indexOf(afterRow);
		if (idx === -1) return;
		state.allRows.splice.apply(state.allRows, [idx + 1, 0].concat(newRows));
	}

	// Fetches and splices in one leaf account's transactions/items (see
	// DRILLDOWN_METHOD above). Resolves once state.allRows/expandedState are
	// updated - caller still has to rerenderTable() itself, same as every
	// other mutate-then-render call in this file, so it can control exactly
	// when (e.g. Expand All batches many of these before a single rerender).
	function fetchAccountDrilldown(row) {
		return new Promise(function (resolve) {
			row.__txnLoading = true;
			state.expandedState[row.__key] = true;
			rerenderTable();

			frappe.call({
				method: DRILLDOWN_METHOD,
				args: {
					account: row.account,
					indent: row.indent || 0,
					use_valuation_rate: row.use_valuation_rate ? 1 : 0,
					filters: JSON.stringify(buildReportFilters()),
				},
				callback: function (r) {
					row.__txnLoading = false;
					row.__txnLoaded = true;
					var newRows = r.message || [];
					if (newRows.length) {
						annotateRows(newRows, false);
						$.extend(state.expandedState, seedDefaultExpandState(newRows));
						insertRowsAfter(row, newRows);
					}
					resolve();
				},
				error: function () {
					row.__txnLoading = false;
					frappe.show_alert({ message: __("Failed to load transactions for this account."), indicator: "red" });
					resolve();
				},
			});
		});
	}

	function bindTableEventsOnce() {
		// Bound BEFORE the generic .pld-toggle handler below and stops
		// immediate propagation - a lineage toggle's element carries BOTH
		// classes (it's a .pld-toggle for styling), so without this the
		// generic handler would also fire and flip expandedState a second,
		// conflicting time.
		$root.on("click", "#pld-tbody .pld-toggle-lineage", function (e) {
			e.stopPropagation();
			e.stopImmediatePropagation();
			var key = $(this).data("key");
			var row = state.rowsByKey[key];
			if (!row) return;

			if (row.__lineageLoaded || row.__lineageLoading) {
				if (!row.__lineageLoading) {
					state.expandedState[key] = state.expandedState[key] === false ? true : false;
					rerenderTable();
				}
				return;
			}

			row.__lineageLoading = true;
			state.expandedState[key] = true;
			rerenderTable();

			frappe.call({
				method: LINEAGE_METHOD,
				args: {
					item_code: row.item_code,
					warehouse: row.warehouse,
					voucher_type: row.voucher_type,
					voucher_no: row.voucher_no,
				},
				callback: function (r) {
					row.__lineageLoading = false;
					row.__lineageLoaded = true;
					var lineageRows = (r.message || []).map(function (lr, idx) {
						return lineageRowToDisplayRow(lr, row, idx);
					});
					lineageRows.forEach(function (lr) { state.rowsByKey[lr.__key] = lr; });
					if (lineageRows.length) {
						insertRowsAfter(row, lineageRows);
					} else {
						frappe.show_alert({ message: __("No lineage could be traced for this item."), indicator: "orange" });
					}
					rerenderTable();
				},
				error: function () {
					row.__lineageLoading = false;
					frappe.show_alert({ message: __("Failed to load valuation lineage."), indicator: "red" });
					rerenderTable();
				},
			});
		});

		$root.on("click", "#pld-tbody .pld-toggle", function (e) {
			e.stopPropagation();
			var key = $(this).data("key");
			var row = state.rowsByKey[key];
			if (!row) return;

			// A leaf account's own transactions/items aren't in state.allRows
			// yet until it's actually expanded (see the module-level comment
			// on DRILLDOWN_METHOD above) - fetch them the first time, then
			// behave exactly like every other toggle from then on.
			if (row.__kind === "leaf" && !row.__txnLoaded) {
				if (row.__txnLoading) return;
				fetchAccountDrilldown(row).then(function () { rerenderTable(); });
				return;
			}

			state.expandedState[key] = state.expandedState[key] === false ? true : false;
			rerenderTable();
		});

		$root.on("input", "#pld-search", function () {
			rerenderTable();
		});

		$root.on("click", "#pld-expand-all", function () {
			var pending = [];
			for (var i = 0; i < state.allRows.length; i++) {
				var row = state.allRows[i];
				if (row && row.__kind === "leaf" && !row.__txnLoaded && !row.__txnLoading) {
					pending.push(row);
				}
			}

			if (!pending.length) {
				state.expandedState = {};
				rerenderTable();
				return;
			}

			pending.forEach(function (row) { row.__txnLoading = true; });
			rerenderTable();
			$("#pld-expand-all").prop("disabled", true);

			var accountsArg = pending.map(function (row) {
				return { account: row.account, indent: row.indent || 0, use_valuation_rate: row.use_valuation_rate ? 1 : 0 };
			});

			frappe.call({
				method: BULK_DRILLDOWN_METHOD,
				args: { accounts: JSON.stringify(accountsArg), filters: JSON.stringify(buildReportFilters()) },
				callback: function (r) {
					var byAccount = r.message || {};
					// Walk allRows back-to-front so inserting one account's
					// rows never shifts the index the next insertion (further
					// up the list) relies on.
					for (var i = state.allRows.length - 1; i >= 0; i--) {
						var acctRow = state.allRows[i];
						if (!acctRow || acctRow.__kind !== "leaf" || !acctRow.__txnLoading) continue;
						acctRow.__txnLoading = false;
						acctRow.__txnLoaded = true;
						var newRows = byAccount[acctRow.account] || [];
						if (!newRows.length) continue;
						annotateRows(newRows, false);
						$.extend(state.expandedState, seedDefaultExpandState(newRows));
						insertRowsAfter(acctRow, newRows);
					}
					state.expandedState = {};
					$("#pld-expand-all").prop("disabled", false);
					rerenderTable();
				},
				error: function () {
					pending.forEach(function (row) { row.__txnLoading = false; });
					$("#pld-expand-all").prop("disabled", false);
					frappe.show_alert({ message: __("Failed to load some accounts' transactions."), indicator: "red" });
					rerenderTable();
				},
			});
		});

		$root.on("click", "#pld-collapse-all", function () {
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

		$root.on("click", "#pld-view-pills .pld-view-pill", function () {
			state.selected_view = $(this).data("view");
			$("#pld-view").val(state.selected_view);
			runReport();
		});

		$root.on("click", "#pld-export-btn", function () { exportCsv(); });

		$root.on("click", "#pld-print-btn", function () { window.print(); });
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
		a.download = "profit_and_loss_drilldown_" + (state.company || "company") + "_" + frappe.datetime.nowdate() + ".csv";
		a.click();
	}

	// ── Load metadata ─────────────────────────────────────────────────────────
	function loadMetadata() {
		frappe.db.get_list("Company", { fields: ["name"], limit: 100 }).then(function (res) {
			var $s = $("#pld-company");
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
			var $from = $("#pld-from-fy");
			var $to = $("#pld-to-fy");
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
			var $c = $("#pld-currency");
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
		$("#pld-company").on("change", function () { state.company = $(this).val(); updateHeaderSub(); scheduleRun(); });
		$("#pld-filter-based-on").on("change", function () { state.filter_based_on = $(this).val(); toggleDateFyFields(); scheduleRun(); });
		$("#pld-from-fy").on("change", function () { state.from_fiscal_year = $(this).val(); scheduleRun(); });
		$("#pld-to-fy").on("change", function () { state.to_fiscal_year = $(this).val(); scheduleRun(); });
		$("#pld-start-date").on("change", function () { state.period_start_date = $(this).val(); scheduleRun(); });
		$("#pld-end-date").on("change", function () { state.period_end_date = $(this).val(); scheduleRun(); });
		$("#pld-periodicity").on("change", function () { state.periodicity = $(this).val(); scheduleRun(); });
		$("#pld-currency").on("change", function () { state.presentation_currency = $(this).val(); scheduleRun(); });
		$("#pld-view").on("change", function () { state.selected_view = $(this).val(); scheduleRun(); });
		$("#pld-accum").on("change", function () { state.accumulated_values = $(this).is(":checked") ? 1 : 0; scheduleRun(); });
		$("#pld-show-zero").on("change", function () { state.show_zero_values = $(this).is(":checked") ? 1 : 0; scheduleRun(); });
		$("#pld-default-book").on("change", function () { state.include_default_book_entries = $(this).is(":checked") ? 1 : 0; scheduleRun(); });

		$("#pld-run-btn").on("click", function () { clearTimeout(autoRunTimer); runReport(); });

		$(".pld-filters-panel").on("keydown", function (e) {
			if (e.key === "Enter") { clearTimeout(autoRunTimer); runReport(); }
		});
	}

	function toggleDateFyFields() {
		if (state.filter_based_on === "Fiscal Year") {
			$("#pld-fy-from-wrap, #pld-fy-to-wrap").show();
			$("#pld-date-from-wrap, #pld-date-to-wrap").hide();
		} else {
			$("#pld-fy-from-wrap, #pld-fy-to-wrap").hide();
			$("#pld-date-from-wrap, #pld-date-to-wrap").show();
		}
	}

	function updateHeaderSub() {
		var sub = state.company ? state.company + " · " : "";
		sub += state.from_fiscal_year || "";
		if (state.to_fiscal_year && state.to_fiscal_year !== state.from_fiscal_year) sub += " – " + state.to_fiscal_year;
		if (!sub) sub = "Select filters and run the report";
		$("#pld-header-sub").text(sub);
	}

	// Same filters shape both runReport() and the on-demand drill-down calls
	// need (company/period/currency) - factored out so a leaf account's
	// lazy-loaded transactions always match the period/currency the report
	// itself was just run with.
	function buildReportFilters() {
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
		return filters;
	}

	// ── Run Report - same generic endpoint the existing query reports use,
	// same report_name, same filters shape, same is_tree/parent_field. ──────
	function runReport() {
		if (!state.company) { frappe.msgprint("Please select a Company."); return; }
		if (state.filter_based_on === "Fiscal Year" && !state.from_fiscal_year) { frappe.msgprint("Please select a Fiscal Year."); return; }
		if (state.filter_based_on === "Date Range" && (!state.period_start_date || !state.period_end_date)) { frappe.msgprint("Please select Start Date and End Date."); return; }

		state.loading = true;
		renderResults();
		$("#pld-run-btn").addClass("loading");

		var filters = buildReportFilters();
		// Tells the backend to skip its own eager transaction/item
		// drill-down (attach_transaction_rows()) - this Page fetches that
		// on demand per account instead (see DRILLDOWN_METHOD above), so
		// building it for every leaf account up front here would just be
		// wasted work for whatever the user never expands.
		filters.skip_transaction_drilldown = 1;

		frappe.call({
			method: "frappe.desk.query_report.run",
			args: {
				report_name: "Profit and Loss Statement Child Accounts",
				filters: filters,
				is_tree: true,
				parent_field: "parent_account",
			},
			callback: function (r) {
				state.loading = false;
				$("#pld-run-btn").removeClass("loading");

				if (r && r.message) {
					var msg = r.message;
					var allColumns = msg.columns || [];
					state.baseColumns = allColumns.filter(function (c) {
						return !c.hidden && TRANSACTION_DETAIL_FIELDNAMES.indexOf(c.fieldname) === -1;
					});
					// Never sourced from the backend's own columns here -
					// filters.skip_transaction_drilldown means `msg.result`
					// never carries a transaction/item row at initial load
					// (they're fetched lazily per account instead - see
					// DRILLDOWN_METHOD above), so the backend's own
					// data-driven get_transaction_detail_columns() would
					// always come back empty. Same reasoning as
					// LINEAGE_ONLY_COLUMNS: the existing show/hide-while-
					// visible logic in computeVisibleRowsAndColumns() only
					// needs the column DEFINITIONS up front.
					state.dynamicColumnDefs = TRANSACTION_DETAIL_COLUMN_DEFS.concat(LINEAGE_ONLY_COLUMNS);
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
					$("#pld-body").html('<div class="pld-placeholder"><div class="ph-icon">⚠️</div><p>No data found for the selected filters.</p></div>');
				}
			},
			error: function (r) {
				state.loading = false;
				$("#pld-run-btn").removeClass("loading");
				var msg = (r && r.message) || "An error occurred while fetching the report.";
				frappe.msgprint(msg);
				$("#pld-body").html('<div class="pld-placeholder"><div class="ph-icon">❌</div><p>' + escHtml(String(msg)) + "</p></div>");
			},
		});
	}

	// ── Bootstrap ─────────────────────────────────────────────────────────────
	$root.html(buildShell());
	loadMetadata();
	bindControls();
	bindTableEventsOnce();
};
