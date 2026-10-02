// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Undelivered COGS Recognition"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: "Motley Terpz", reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: "2026-01-01", reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: "2026-06-30", reqd: 1 },
		{ fieldname: "only_gaps", label: __("Only Lines With A Gap"), fieldtype: "Check", default: 1 },
	],

	onload(report) {
		if (!frappe.user.has_role(["Accounts Manager", "System Manager"])) return;
		report.page.add_inner_button(__("Post COGS Journal Entries"), () => {
			const f = report.get_values();
			const rows = (frappe.query_report.data || []).filter((r) => r.status === "To Post");
			const total = rows.reduce((s, r) => s + (r.amount || 0), 0);
			frappe.confirm(
				__("Post COGS for {0} undelivered lines, total {1}? (Dr COGS / Cr Stock Adjustment, no stock movement)", [
					rows.length,
					format_currency(total),
				]),
				() =>
					frappe
						.call("cannabis_management.api.undelivered_cogs.enqueue_post", {
							company: f.company,
							from_date: f.from_date,
							to_date: f.to_date,
						})
						.then((r) => frappe.show_alert({ message: r.message, indicator: "blue" }))
			);
		});
	},
};
