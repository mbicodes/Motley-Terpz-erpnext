// Toll Stock On Hand as a page report (Sales Operation Board look). Same numbers as the Script Report.
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

frappe.pages['toll-stock-on-hand'].on_page_load = function (wrapper) {
	window.mg_report_boot(wrapper, __('Toll Stock On Hand'), page => new MGReportPage({
			wrapper,
			page,
			title: __('Toll Stock On Hand'),
			report: 'Toll Stock On Hand',
			hint: __('Customer-owned material in the Toll warehouses, one line per Toll Job batch. Use it for physical counts and METRC reconciliation.'),
			back: { label: __('Toll Processing Board'), route: 'toll-processing-board' },
			filters: [
				{ fieldname: 'as_on_date', label: __('As on'), type: 'date', default: () => frappe.datetime.get_today() },
				{ fieldname: 'customer', label: __('Customer'), all: __('All customers'), type: 'select', options_from: 'customers' },
				{ fieldname: 'warehouse', label: __('Warehouse'), all: __('All toll warehouses'), type: 'select', options_from: 'warehouses' },
				{ fieldname: 'item_code', label: __('Item'), all: __('All toll items'), type: 'select', options_from: 'items' },
				{ fieldname: 'toll_job', label: __('Toll Job'), type: 'text' },
			],
		}));
};
