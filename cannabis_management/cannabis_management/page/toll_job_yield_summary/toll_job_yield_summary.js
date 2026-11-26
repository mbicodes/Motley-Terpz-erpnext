// Toll Job Yield Summary as a page report (Sales Operation Board look). Same numbers as the Script Report.
window.mg_report_boot = window.mg_report_boot || function (wrapper, title, make) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title, single_column: true });
	$(wrapper).addClass('mg-glass-page mg-report-page');
	$('<div class="mg mgr mgr-boot"><div class="mg-bg" aria-hidden="true"><i></i></div><div class="mg-loading">' + __('Loading…') + '</div></div>').appendTo(page.main);
	const start = () => { wrapper.report = make(page); };
	if (window.MGReportPage) return start();
	const src = '/assets/cannabis_management/js/mg_report_page.js?v=2';
	let tag = document.querySelector('script[data-mg-report]');
	if (!tag) {
		tag = document.createElement('script');
		tag.src = src;
		tag.dataset.mgReport = '1';
		document.head.appendChild(tag);
	}
	tag.addEventListener('load', start);
	tag.addEventListener('error', () => $(page.main).find('.mg-loading').text(__('The report could not be loaded. Refresh the page.')));
};

frappe.pages['toll-job-yield-summary'].on_page_load = function (wrapper) {
	window.mg_report_boot(wrapper, __('Toll Job Yield Summary'), page => new MGReportPage({
			wrapper,
			page,
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
		}));
};
