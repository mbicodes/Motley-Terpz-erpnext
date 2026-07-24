// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Profit and Loss Statement Gross Profit"] = $.extend({}, erpnext.financial_statements);

erpnext.utils.add_dimensions("Profit and Loss Statement Gross Profit", 10);

frappe.query_reports["Profit and Loss Statement Gross Profit"]["filters"].push(
	{
		fieldname: "selected_view",
		label: __("Select View"),
		fieldtype: "Select",
		options: [
			{ value: "Report", label: __("Report View") },
			{ value: "Growth", label: __("Growth View") },
			{ value: "Margin", label: __("Margin View") },
		],
		default: "Report",
		reqd: 1,
	},
	{
		fieldname: "accumulated_values",
		label: __("Accumulated Values"),
		fieldtype: "Check",
		default: 0,
	},
	{
		fieldname: "include_default_book_entries",
		label: __("Include Default FB Entries"),
		fieldtype: "Check",
		default: 1,
	},
	{
		fieldname: "show_zero_values",
		label: __("Show zero values"),
		fieldtype: "Check",
	}
);

// Point the "Financial Statements" dropdown at the child-accounts versions of
// Balance Sheet / Cash Flow (via Consolidated Financial Statement Child Accounts'
// "report" filter) instead of erpnext.financial_statements' default onload, which
// links to the standard group-inclusive reports.
frappe.query_reports["Profit and Loss Statement Gross Profit"].onload = function (report) {
	let fiscal_year = erpnext.utils.get_fiscal_year(frappe.datetime.get_today());
	var filters = report.get_values();

	if (!filters.period_start_date || !filters.period_end_date) {
		frappe.model.with_doc("Fiscal Year", fiscal_year, function () {
			var fy = frappe.model.get_doc("Fiscal Year", fiscal_year);
			frappe.query_report.set_filter_value({
				period_start_date: fy.year_start_date,
				period_end_date: fy.year_end_date,
			});
		});
	}

	if (report.page) {
		const views_menu = report.page.add_custom_button_group(__("Financial Statements"));

		report.page.add_custom_menu_item(views_menu, __("Balance Sheet"), function () {
			var filters = report.get_values();
			frappe.set_route("query-report", "Consolidated Financial Statement Child Accounts", {
				company: filters.company,
				report: "Balance Sheet",
			});
		});

		report.page.add_custom_menu_item(views_menu, __("Profit and Loss"), function () {
			var filters = report.get_values();
			frappe.set_route("query-report", "Profit and Loss Statement Gross Profit", {
				company: filters.company,
			});
		});

		report.page.add_custom_menu_item(views_menu, __("Cash Flow Statement"), function () {
			var filters = report.get_values();
			frappe.set_route("query-report", "Consolidated Financial Statement Child Accounts", {
				company: filters.company,
				report: "Cash Flow",
			});
		});
	}
};

// Same as erpnext.financial_statements' shared formatter, except bolding is
// keyed off is_total_row (section headings, Total Income/COGS/Expense, Gross
// Profit, Net Profit) instead of "no parent_account" - this report injects
// synthetic heading/total rows that erpnext.financial_statements' own rule
// wasn't written to account for. Rest of the formatter is unchanged.
frappe.query_reports["Profit and Loss Statement Gross Profit"].formatter = function (
	value,
	row,
	column,
	data,
	default_formatter,
	filter
) {
	if (frappe.query_report.get_filter_value("selected_view") == "Growth" && data && column.colIndex >= 3) {
		const growthPercent = data[column.fieldname];

		if (growthPercent == undefined) return "NA";

		if (column.fieldname === "total") {
			value = $(`<span>${growthPercent}</span>`);
		} else {
			value = $(`<span>${(growthPercent >= 0 ? "+" : "") + growthPercent + "%"}</span>`);

			if (growthPercent < 0) {
				value = $(value).addClass("text-danger");
			} else {
				value = $(value).addClass("text-success");
			}
		}
		value = $(value).wrap("<p></p>").parent().html();

		return value;
	} else if (frappe.query_report.get_filter_value("selected_view") == "Margin" && data) {
		if (column.fieldname == "account" && data.account_name == __("Income")) {
			this.baseData = row;
		}
		if (column.colIndex >= 2) {
			const marginPercent = data[column.fieldname];

			if (marginPercent == undefined) return "NA";

			value = $(`<span>${marginPercent + "%"}</span>`);
			if (marginPercent < 0) value = $(value).addClass("text-danger");
			else value = $(value).addClass("text-success");
			value = $(value).wrap("<p></p>").parent().html();
			return value;
		}
	}

	if (data && column.fieldname == this.name_field) {
		// first column
		value = data.section_name || data.account_name || value;

		if (filter && filter?.text && filter?.type == "contains") {
			if (!value.toLowerCase().includes(filter.text)) {
				return value;
			}
		}

		if (data.account || data.accounts) {
			column.link_onclick =
				"erpnext.financial_statements.open_general_ledger(" + JSON.stringify(data) + ")";
		}
		column.is_tree = true;
	}

	value = default_formatter(value, row, column, data);

	if (data && data.is_total_row) {
		value = $(`<span>${value}</span>`);

		var $value = $(value).css("font-weight", "bold");
		if (data.warn_if_negative && data[column.fieldname] < 0) {
			$value.addClass("text-danger");
		}

		value = $value.wrap("<p></p>").parent().html();
	}

	return value;
};
