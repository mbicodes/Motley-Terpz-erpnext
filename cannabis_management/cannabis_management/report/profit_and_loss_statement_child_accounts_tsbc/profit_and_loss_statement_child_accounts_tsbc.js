// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Profit and Loss Statement Child Accounts TSBC"] = $.extend({}, erpnext.financial_statements);

erpnext.utils.add_dimensions("Profit and Loss Statement Child Accounts TSBC", 10);

frappe.query_reports["Profit and Loss Statement Child Accounts TSBC"]["filters"].push(
	{
		fieldname: "selected_view",
		label: __("Select View"),
		fieldtype: "Select",
		options: [
			{ value: "Report", label: __("Report View") },
			{ value: "Growth", label: __("Growth View") },
			{ value: "Margin", label: __("Percentage View (% of Income)") },
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
frappe.query_reports["Profit and Loss Statement Child Accounts TSBC"].onload = function (report) {
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
			frappe.set_route("query-report", "Profit and Loss Statement Child Accounts TSBC", {
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
// synthetic heading/total rows (see profit_and_loss_statement_child_accounts_tsbc.py)
// that erpnext.financial_statements' own rule wasn't written to account for.
// Rest of the formatter is unchanged.
frappe.query_reports["Profit and Loss Statement Child Accounts TSBC"].formatter = function (
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

		// Deliberately no erpnext.financial_statements.open_general_ledger()
		// link_onclick here: every account expands, in place, into its own
		// transactions and (for Sales/Purchase Invoices) their line items -
		// see attach_transaction_rows() in the .py - so there's no need to
		// navigate away to General Ledger, and doing so would break anyway
		// for the synthetic "account" ids on those transaction/item rows.
		column.is_tree = true;

		// Transaction rows carry a real voucher_type/voucher_no (see
		// make_transaction_row() in the .py) - route straight to that
		// document. Falling through to the default formatter would try to
		// build a Link-to-Account href out of the row's synthetic, quoted
		// "account" id, which isn't a real Account and would go nowhere.
		if (data.voucher_type && data.voucher_no) {
			return frappe.utils.get_form_link(data.voucher_type, data.voucher_no, true, value);
		}

		// Item drill-down rows (see make_item_row() in the .py) - route to
		// the Item master they belong to.
		if (data.item_code) {
			return frappe.utils.get_form_link("Item", data.item_code, true, value);
		}

		// Real account rows (leaf or group - both carry is_group, unlike the
		// synthetic heading/total/transaction/item rows above) should not
		// navigate anywhere at all: they already expand in place into their
		// own transactions, so return the plain label instead of falling
		// through to default_formatter, which would otherwise build a
		// Link-to-Account href out of the real, unquoted account name.
		if (Object.prototype.hasOwnProperty.call(data, "is_group")) {
			return value;
		}
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
