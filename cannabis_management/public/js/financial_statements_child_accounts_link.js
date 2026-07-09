// Adds a link to "Profit and Loss Statement Child Accounts" inside the
// "Financial Statements" dropdown of erpnext's standard Balance Sheet,
// Profit and Loss Statement, and Cash Flow reports (that dropdown is shared
// via erpnext.financial_statements.onload, so this patches all three).

frappe.ready(function () {
	add_child_accounts_link_to_financial_statements();
});

function add_child_accounts_link_to_financial_statements() {
	["Profit and Loss Statement", "Balance Sheet", "Cash Flow"].forEach(function (report_name) {
		var settings = frappe.query_reports[report_name];
		if (!settings || settings._cm_child_accounts_link_patched) return;
		settings._cm_child_accounts_link_patched = true;

		var original_onload = settings.onload;
		settings.onload = function (report) {
			if (original_onload) original_onload(report);
			if (!report.page) return;

			var menu = find_financial_statements_menu(report.page);
			if (!menu) menu = report.page.add_custom_button_group(__("Financial Statements"));

			report.page.add_custom_menu_item(menu, __("Profit and Loss (Child Accounts)"), function () {
				var filters = report.get_values();
				frappe.set_route("query-report", "Profit and Loss Statement Child Accounts", {
					company: filters.company,
				});
			});
		};
	});
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
