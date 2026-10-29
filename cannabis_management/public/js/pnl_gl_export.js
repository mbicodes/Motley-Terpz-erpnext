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
			if (!row || !row.account || row.is_group !== 0) return;
			if (row.account.charAt(0) === "'") return;
			if (seen[row.account]) return;
			seen[row.account] = true;
			accounts.push(row.account);
		});

		return accounts;
	}

	if (!add_export_action_to_profit_and_loss()) {
		$(document).ready(add_export_action_to_profit_and_loss);
		$(document).on("app_ready", add_export_action_to_profit_and_loss);
	}
})();
