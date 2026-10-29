frappe.provide("cannabis.reports");

cannabis.reports.ALL_COMPANIES = "All Company";
cannabis.reports._companies = null;
cannabis.reports._loading = null;

cannabis.reports._options = function () {
	return [cannabis.reports.ALL_COMPANIES].concat(cannabis.reports._companies || []);
};

cannabis.reports._load_companies = function () {
	if (cannabis.reports._companies) {
		return Promise.resolve(cannabis.reports._companies);
	}
	if (!cannabis.reports._loading) {
		cannabis.reports._loading = frappe.db
			.get_list("Company", { fields: ["name"], limit: 0, order_by: "name asc" })
			.then((rows) => {
				cannabis.reports._companies = (rows || []).map((row) => row.name);
				return cannabis.reports._companies;
			})
			.catch(() => {
				cannabis.reports._companies = [];
				return [];
			});
	}
	return cannabis.reports._loading;
};

cannabis.reports.company_filter = function (overrides) {
	const filter = Object.assign(
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Select",
			options: cannabis.reports._options(),
			default:
				frappe.defaults.get_user_default("Company") ||
				frappe.defaults.get_default("company") ||
				cannabis.reports.ALL_COMPANIES,
		},
		overrides || {}
	);

	cannabis.reports._load_companies().then((companies) => {
		const control =
			frappe.query_report && frappe.query_report.get_filter
				? frappe.query_report.get_filter("company")
				: null;
		if (!control) return;

		const options = [cannabis.reports.ALL_COMPANIES].concat(companies);
		if (JSON.stringify(control.df.options) === JSON.stringify(options)) return;

		const current = control.get_value();
		control.df.options = options;
		control.refresh();
		if (current) control.set_value(current);
	});

	return filter;
};
