// Adds a link to "Profit and Loss Statement Child Accounts" inside the
// "Financial Statements" dropdown of erpnext's standard Balance Sheet,
// Profit and Loss Statement, and Cash Flow reports.
//
// Two things this file must NOT do, both of which silently killed the link:
//
//   * frappe.ready() only exists on the website/portal (it is defined inline in
//     frappe/templates/base.html). On the desk (/app) it is undefined, so
//     calling it here threw a TypeError and nothing below it ever ran.
//
//   * frappe.query_reports["Profit and Loss Statement"] is undefined at desk
//     boot. Report scripts are fetched lazily (frappe.desk.query_report.get_script)
//     the first time a report is opened, so there is nothing to patch yet.
//
// Instead patch the shared erpnext.financial_statements.onload, which all three
// standard reports inherit via $.extend(). erpnext.bundle.js is loaded before
// this file (apps.txt order), and because the reports copy the object later,
// every copy picks up the patched onload.

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

			// The child-accounts reports build their own dropdown; don't add a
			// link back to the report the user is already looking at.
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

	// erpnext.bundle.js normally wins the race, but don't depend on script order:
	// retry once the DOM is ready and once the desk signals app_ready.
	if (!add_child_accounts_link_to_financial_statements()) {
		$(document).ready(add_child_accounts_link_to_financial_statements);
		$(document).on("app_ready", add_child_accounts_link_to_financial_statements);
	}
})();
