(function () {
	function add_child_accounts_link_to_financial_statements() {
		if (
			typeof erpnext === "undefined" ||
			!erpnext.financial_statements ||
			erpnext.financial_statements._cm_child_accounts_link_patched
		) {
			return false;
		}
		erpnext.financial_statements._cm_child_accounts_link_patched = true;

		var original_onload = erpnext.financial_statements.onload;

		erpnext.financial_statements.onload = function (report) {
			if (original_onload) original_onload.call(this, report);

			if (!report || !report.page) return;

			if ((report.report_name || "").indexOf("Child Accounts") !== -1) return;

			var menu = find_financial_statements_menu(report.page);
			if (!menu) menu = report.page.add_custom_button_group(__("Financial Statements"));

			report.page.add_custom_menu_item(menu, __("Profit and Loss (Child Accounts)"), function () {
				var filters = report.get_values();
				frappe.set_route("query-report", "Profit and Loss Statement Child Accounts", {
					company: filters.company,
				});
			});
		};

		return true;
	}

	function find_financial_statements_menu(page) {
		var group = page.custom_actions
			.find(".custom-btn-group-label")
			.filter(function () {
				return $(this).text().trim() === __("Financial Statements");
			})
			.closest(".custom-btn-group")
			.find(".dropdown-menu");
		return group.length ? group : null;
	}

	if (!add_child_accounts_link_to_financial_statements()) {
		$(document).ready(add_child_accounts_link_to_financial_statements);
		$(document).on("app_ready", add_child_accounts_link_to_financial_statements);
	}
})();
