// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Detailed Balance Sheet"] = $.extend({}, erpnext.financial_statements);

erpnext.utils.add_dimensions("Detailed Balance Sheet", 10);

frappe.query_reports["Detailed Balance Sheet"]["filters"].push(
	{
		fieldname: "selected_view",
		label: __("Select View"),
		fieldtype: "Select",
		options: [
			{ value: "Report", label: __("Report View") },
			{ value: "Growth", label: __("Growth View") },
			{ value: "Margin", label: __("Percentage View (% of Total Assets)") },
		],
		default: "Report",
		reqd: 1,
	},
	{
		fieldname: "accumulated_values",
		label: __("Accumulated Values"),
		fieldtype: "Check",
		default: 1,
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

// Same as erpnext.financial_statements' shared formatter, except the account
// column never navigates away to General Ledger: every account expands, in
// place, into its own transactions and (for Sales/Purchase Invoices etc.)
// their line items - see attach_transaction_rows() in financial_statements.py
// (shared with Profit and Loss Statement (Child Accounts), which uses this
// same formatter pattern) - so there's no need to leave the report, and doing
// so would break anyway for the synthetic "account" ids on those
// transaction/item rows.
frappe.query_reports["Detailed Balance Sheet"].formatter = function (
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
	} else if (frappe.query_report.get_filter_value("selected_view") == "Margin" && data && column.colIndex >= 2) {
		// Common-size balance sheet: every value is a % of Total Assets -
		// already computed server-side (see compute_margin_view_data() in
		// financial_statements.py, called with base_account_name="Assets").
		const marginPercent = data[column.fieldname];

		if (marginPercent == undefined) return "NA";

		value = $(`<span>${marginPercent + "%"}</span>`);
		if (marginPercent < 0) value = $(value).addClass("text-danger");
		else value = $(value).addClass("text-success");
		value = $(value).wrap("<p></p>").parent().html();

		return value;
	}

	if (data && column.fieldname == this.name_field) {
		// first column
		value = data.section_name || data.account_name || value;

		if (filter && filter?.text && filter?.type == "contains") {
			if (!value.toLowerCase().includes(filter.text)) {
				return value;
			}
		}

		column.is_tree = true;

		// Transaction rows carry a real voucher_type/voucher_no (see
		// make_transaction_row() in financial_statements.py) - route
		// straight to that document.
		if (data.voucher_type && data.voucher_no) {
			return frappe.utils.get_form_link(data.voucher_type, data.voucher_no, true, value);
		}

		// Item drill-down rows (see make_item_row()) - route to the Item
		// master they belong to.
		if (data.item_code) {
			return frappe.utils.get_form_link("Item", data.item_code, true, value);
		}

		// Real account rows (leaf or group - both carry is_group, unlike the
		// synthetic total/transaction/item rows above) should not navigate
		// anywhere: they already expand in place into their own
		// transactions, so return the plain label instead of falling
		// through to default_formatter, which would otherwise build a
		// Link-to-Account href out of the real, unquoted account name.
		if (Object.prototype.hasOwnProperty.call(data, "is_group")) {
			return value;
		}
	}

	value = default_formatter(value, row, column, data);

	if (data && !data.parent_account && !data.parent_section) {
		value = $(`<span>${value}</span>`);

		var $value = $(value).css("font-weight", "bold");
		if (data.warn_if_negative && data[column.fieldname] < 0) {
			$value.addClass("text-danger");
		}

		value = $value.wrap("<p></p>").parent().html();
	}

	return value;
};
