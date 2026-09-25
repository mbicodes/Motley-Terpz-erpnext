// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt


// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Stock Ledger Custom"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "warehouse",
			label: __("Warehouses"),
			fieldtype: "MultiSelectList",
			options: "Warehouse",
			get_data: function (txt) {
				const company = frappe.query_report.get_filter_value("company");

				return frappe.db.get_link_options("Warehouse", txt, {
					company: company,
				});
			},
		},
		{
			fieldname: "item_code",
			label: __("Items"),
			fieldtype: "MultiSelectList",
			options: "Item",
			get_data: async function (txt) {
				let { message: data } = await frappe.call({
					method: "erpnext.controllers.queries.item_query",
					args: {
						doctype: "Item",
						txt: txt,
						searchfield: "name",
						start: 0,
						// No practical limit: page_len goes straight into the SQL
						// LIMIT, and core's 10 meant the picker only ever offered ten
						// items, so more than ten could not be selected. This sits
						// well above the whole catalogue (~3.7k items), which measured
						// at 566 KB / 40 ms for a blank search - and typing anything
						// narrows it immediately. 0 is NOT the way to say "no limit":
						// LIMIT 0 returns nothing.
						page_len: 10000,
						filters: {},
						as_dict: 1,
					},
				});
				data = data.map(({ name, ...rest }) => {
					return {
						value: name,
						description: Object.values(rest),
					};
				});

				return data || [];
			},
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "batch_no",
			label: __("Batch No"),
			fieldtype: "Link",
			options: "Batch",
			on_change() {
				const batch_no = frappe.query_report.get_filter_value("batch_no");
				if (batch_no) {
					frappe.query_report.set_filter_value("segregate_serial_batch_bundle", 1);
				} else {
					frappe.query_report.set_filter_value("segregate_serial_batch_bundle", 0);
				}
			},
		},
		{
			fieldname: "brand",
			label: __("Brand"),
			fieldtype: "Link",
			options: "Brand",
		},
		{
			fieldname: "voucher_no",
			label: __("Voucher #"),
			fieldtype: "MultiSelectList",
			// voucher_no is not a Link - it is the target half of a Dynamic Link -
			// so there is no doctype to read options from. They come from the ledger
			// itself, narrowed by whatever company / date range is already selected
			// so the list stays relevant instead of offering every voucher on site.
			get_data: function (txt) {
				let picked = {};
				try {
					picked = frappe.query_report.get_filter_values() || {};
				} catch (e) {
					picked = {};
				}

				let filters = { voucher_no: ["like", "%" + (txt || "") + "%"] };
				if (picked.company) filters.company = picked.company;
				if (picked.from_date && picked.to_date) {
					filters.posting_date = ["between", [picked.from_date, picked.to_date]];
				}

				return frappe.db
					.get_list("Stock Ledger Entry", {
						filters: filters,
						fields: ["voucher_no", "voucher_type"],
						group_by: "voucher_no",
						order_by: "posting_date desc",
						limit: 20,
					})
					.then(function (rows) {
						return (rows || []).map(function (r) {
							return { value: r.voucher_no, description: r.voucher_type };
						});
					});
			},
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "include_uom",
			label: __("Include UOM"),
			fieldtype: "Link",
			options: "UOM",
		},
		{
			fieldname: "valuation_field_type",
			label: __("Valuation Field Type"),
			fieldtype: "Select",
			width: "80",
			options: "Currency\nFloat",
			default: "Currency",
		},
		{
			fieldname: "segregate_serial_batch_bundle",
			label: __("Segregate Serial / Batch Bundle"),
			fieldtype: "Check",
			default: 0,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname == "out_qty" && data && data.out_qty < 0) {
			value = "<span style='color:red'>" + value + "</span>";
		} else if (column.fieldname == "in_qty" && data && data.in_qty > 0) {
			value = "<span style='color:green'>" + value + "</span>";
		}

		return value;
	},

	onload: function (report) {
		report.page.add_inner_button(__("View Stock Balance"), function () {
			var filters = report.get_values();
			frappe.set_route("query-report", "Stock Balance", filters);
		});
	},
};

erpnext.utils.add_inventory_dimensions("Stock Ledger", 10);
