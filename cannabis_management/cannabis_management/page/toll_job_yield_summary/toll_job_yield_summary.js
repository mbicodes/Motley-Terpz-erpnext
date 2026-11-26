// Toll Job Yield Summary as a page report (Sales Operation Board look). Same numbers as the Script Report.
frappe.pages['toll-job-yield-summary'].on_page_load = function (wrapper) {
	frappe.require('/assets/cannabis_management/js/mg_report_page.js?v=1', () => {
		wrapper.report = new MGReportPage({
			wrapper,
			title: __('Toll Job Yield Summary'),
			report: 'Toll Job Yield Summary',
			hint: __('Per job or per client: Fresh Frozen washed, bubble hash and rosin made, yields, material returned and revenue. Dates are received dates.'),
			back: { label: __('Toll Processing Board'), route: 'toll-processing-board' },
			total_row: true,
			filters: [
				{ fieldname: 'group_by', label: __('Group By'), type: 'seg', options: ['Toll Job', 'Customer'], default: 'Toll Job' },
				{ fieldname: 'from_date', label: __('From'), type: 'date', default: () => frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
				{ fieldname: 'to_date', label: __('To'), type: 'date', default: () => frappe.datetime.get_today() },
				{ fieldname: 'customer', label: __('Customer'), all: __('All customers'), type: 'select', options_from: 'customers' },
				{ fieldname: 'include_cancelled', label: __('Include cancelled'), type: 'check', default: 0 },
			],
		});
	});
};
