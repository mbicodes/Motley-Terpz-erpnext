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
		const marginPercent = data[column.fieldname];

		if (marginPercent == undefined) return "NA";

		value = $(`<span>${marginPercent + "%"}</span>`);
		if (marginPercent < 0) value = $(value).addClass("text-danger");
		else value = $(value).addClass("text-success");
		value = $(value).wrap("<p></p>").parent().html();

		return value;
	}

	if (data && column.fieldname == this.name_field) {
		value = data.section_name || data.account_name || value;

		if (filter && filter?.text && filter?.type == "contains") {
			if (!value.toLowerCase().includes(filter.text)) {
				return value;
			}
		}

		column.is_tree = true;

		if (data.voucher_type && data.voucher_no) {
			return frappe.utils.get_form_link(data.voucher_type, data.voucher_no, true, value);
		}

		if (data.item_code) {
			return frappe.utils.get_form_link("Item", data.item_code, true, value);
		}

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
