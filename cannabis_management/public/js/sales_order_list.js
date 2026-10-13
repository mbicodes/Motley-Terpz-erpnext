// Render the custom_delivery_note_created column as a small truck icon
// instead of a checkbox tick: green truck when a Delivery Note exists, grey
// otherwise. Merge into (don't replace) ERPNext's existing list settings.
frappe.listview_settings['Sales Order'] = frappe.listview_settings['Sales Order'] || {};

(function () {
	const so_settings = frappe.listview_settings['Sales Order'];

	const truck_icon = `
		<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
			fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
			stroke-linejoin="round" style="vertical-align: middle;">
			<rect x="1" y="3" width="15" height="13"></rect>
			<polygon points="16 8 20 8 23 11 23 16 16 16 16 8"></polygon>
			<circle cx="5.5" cy="18.5" r="2.5"></circle>
			<circle cx="18.5" cy="18.5" r="2.5"></circle>
		</svg>`;

	// Give each Logistic Status option its own indicator-pill color.
	const logistic_status_colors = {
		'Need to Schedule': 'red',
		'Scheduled': 'orange',
		'Order Preparing': 'yellow',
		'Order Prepared': 'blue',
		'Order Staged': 'purple',
		'Order Closed Out': 'green',
	};

	// Give each Sales Order Type (fieldname: custom_sales_order_type) option its own indicator-pill color.
	const sales_order_type_colors = {
		'Sales': 'blue',
		'Samples': 'cyan',
		'Events': 'purple',
		'Testing': 'yellow',
		'Influencers': 'pink',
		'Consignment': 'orange',
		'Tolling': 'darkgrey',
	};

	// "Hide Cancelled" checkbox in the filter bar. It is not a Sales Order
	// field, and FilterArea.get_standard_filters() turns every filter-bar
	// control into a column filter, so swap it for docstatus != 2 there.
	const is_hide_cancelled_filter = (f) =>
		f && f[1] === 'docstatus' && f[2] === '!=' && String(f[3]) === '2';

	function add_hide_cancelled_filter(listview) {
		const filter_area = listview.filter_area;
		if (!filter_area || !filter_area.standard_filters_wrapper) return;
		if (listview.page.fields_dict.hide_cancelled) return;

		const check = listview.page.add_field(
			{
				fieldtype: 'Check',
				fieldname: 'hide_cancelled',
				label: __('Hide Cancelled'),
				onchange: () => filter_area.debounced_refresh_list_view(),
			},
			filter_area.standard_filters_wrapper
		);

		const get_standard_filters = filter_area.get_standard_filters.bind(filter_area);
		filter_area.get_standard_filters = function () {
			const filters = get_standard_filters().filter((f) => f[1] !== 'hide_cancelled');
			if (check.get_value()) filters.push([listview.doctype, 'docstatus', '!=', 2]);
			return filters;
		};

		// The list saves its filters per user, so a reload brings docstatus != 2
		// back as an ordinary filter. Move it back onto the checkbox.
		const saved = filter_area.filter_list.filters.filter(
			(f) => f.field && is_hide_cancelled_filter(f.get_value())
		);
		if (saved.length) {
			saved.forEach((f) => f.remove());
			filter_area.filter_list.update_filters();
			check.set_value(1);
		}
	}

	// Chain onto ERPNext's onload (Close / Re-open menu, bulk actions).
	const erpnext_onload = so_settings.onload;
	so_settings.onload = function (listview) {
		erpnext_onload && erpnext_onload.call(this, listview);
		add_hide_cancelled_filter(listview);
	};

	so_settings.formatters = Object.assign({}, so_settings.formatters, {
		custom_delivery_note_created(value) {
			const created = !!value;
			const color = created ? 'var(--green-600, #1f9d57)' : 'var(--gray-400, #9ca3af)';
			const title = created ? __('Delivery Note Created') : __('No Delivery Note');
			return `<span title="${title}" style="color: ${color};">${truck_icon}</span>`;
		},
		custom_logistic_status(value) {
			if (!value) return '';
			const color = logistic_status_colors[value] || 'gray';
			return `<span class="indicator-pill ${color} filterable" data-value="${frappe.utils.escape_html(value)}">
				<span>${__(value)}</span>
			</span>`;
		},
		custom_sales_order_type(value) {
			if (!value) return '';
			const color = sales_order_type_colors[value] || 'gray';
			return `<span class="indicator-pill ${color} filterable" data-value="${frappe.utils.escape_html(value)}">
				<span>${__(value)}</span>
			</span>`;
		},
	});
})();
