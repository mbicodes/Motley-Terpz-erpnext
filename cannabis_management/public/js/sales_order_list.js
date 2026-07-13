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
	});
})();
