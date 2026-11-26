// Toll Stock On Hand as a page report (Sales Operation Board look). Same numbers as the Script Report.
frappe.pages['toll-stock-on-hand'].on_page_load = function (wrapper) {
	frappe.require('/assets/cannabis_management/js/mg_report_page.js?v=1', () => {
		wrapper.report = new MGReportPage({
			wrapper,
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
		});
	});
};
