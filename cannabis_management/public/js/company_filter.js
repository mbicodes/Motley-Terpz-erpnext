// Shared "Company" filter for custom reports, with an All Company option.
//
// Frappe's Link filter can only offer real Company records, so there is no way
// to express "every company" other than leaving it blank — which is invisible
// and easy to mistake for "not chosen yet". This swaps in a Select carrying an
// explicit `All Company` entry alongside the live company list.
//
// The server side (`cannabis_management.api.report_filters`) strips that value
// out of the filters before the report runs, so each report's existing
// `if filters.get("company")` branch keeps working untouched.

frappe.provide("cannabis.reports");

cannabis.reports.ALL_COMPANIES = "All Company";
cannabis.reports._companies = null;
cannabis.reports._loading = null;

cannabis.reports._options = function () {
	return [cannabis.reports.ALL_COMPANIES].concat(cannabis.reports._companies || []);
};

// Fetched once per desk session, then reused by every report.
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

/**
 * A Company filter that can also mean "all of them".
 *
 * Defaults to the user's own company so existing behaviour is unchanged —
 * nobody's report silently starts spanning every entity. Pass
 * `{ default: cannabis.reports.ALL_COMPANIES }` to flip that per report.
 */
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

	// The list arrives after the filter is built, so refresh it in place. Until
	// then the current value still shows, because Frappe keeps unknown values.
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
