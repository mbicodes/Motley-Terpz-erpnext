// Adds an "Export All Accounts (General Ledger)" action to the standard
// erpnext "Profit and Loss Statement" report.
//
// Clicking it re-runs the same filters currently applied on the P&L
// (company, fiscal year / date range, cost center, project, finance book,
// presentation currency, etc.) against the standard "General Ledger"
// report once per account shown on the P&L, and downloads a single Excel
// workbook with one sheet ("page") per account — the same data you'd get
// by clicking an account row to drill into its General Ledger, just done
// for every account in one export.
//
// Patched onto the shared erpnext.financial_statements.onload for the same
// reasons documented in financial_statements_child_accounts_link.js:
// frappe.ready() doesn't exist on the desk, and
// frappe.query_reports["Profit and Loss Statement"] isn't populated until
// the report script is lazily fetched, so there is nothing to patch until
// erpnext.bundle.js has already run.

(function () {
	function add_export_action_to_profit_and_loss() {
		if (
			typeof erpnext === "undefined" ||
			!erpnext.financial_statements ||
			erpnext.financial_statements._cm_gl_export_patched
		) {
			return false;
		}
		erpnext.financial_statements._cm_gl_export_patched = true;

		var original_onload = erpnext.financial_statements.onload;

		erpnext.financial_statements.onload = function (report) {
			if (original_onload) original_onload.call(this, report);

			if (!report || !report.page) return;
			if (report.report_name !== "Profit and Loss Statement") return;

			report.page.add_inner_button(
				__("Export All Accounts (General Ledger)"),
				function () {
					export_all_accounts_general_ledger(report);
				},
				__("Actions")
			);
		};

		return true;
	}

	function export_all_accounts_general_ledger(report) {
		var accounts = get_leaf_accounts_from_report();

		if (!accounts.length) {
			frappe.msgprint(__("No accounts found in the report to export."));
			return;
		}

		var filters = report.get_values();
		if (!filters || !filters.company) {
			frappe.msgprint(__("Please set the Company filter first."));
			return;
		}

		frappe.dom.freeze(__("Preparing General Ledger export for {0} accounts...", [accounts.length]));

		open_url_post(frappe.request.url, {
			cmd: "cannabis_management.api.pnl_gl_export.export_accounts_general_ledger",
			filters: JSON.stringify(filters),
			accounts: JSON.stringify(accounts),
		});

		setTimeout(function () {
			frappe.dom.unfreeze();
		}, 3000);
	}

	function get_leaf_accounts_from_report() {
		var rows = (frappe.query_report && frappe.query_report.data) || [];
		var seen = {};
		var accounts = [];

		rows.forEach(function (row) {
			// Real accounts always set is_group explicitly to 0 or 1. Synthetic
			// summary rows ("Total Income (Credit)", "Profit for the year", ...)
			// leave is_group undefined but still set `.account` to a quoted
			// label (e.g. "'Total Income (Credit)'"), which would otherwise
			// slip through and blow up the General Ledger call server-side.
			if (!row || !row.account || row.is_group !== 0) return;
			if (row.account.charAt(0) === "'") return;
			if (seen[row.account]) return;
			seen[row.account] = true;
			accounts.push(row.account);
		});

		return accounts;
	}

	// erpnext.bundle.js normally wins the race, but don't depend on script order:
	// retry once the DOM is ready and once the desk signals app_ready.
	if (!add_export_action_to_profit_and_loss()) {
		$(document).ready(add_export_action_to_profit_and_loss);
		$(document).on("app_ready", add_export_action_to_profit_and_loss);
	}
})();
