frappe.pages['bank0-receipts'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Bank Receipts',
		single_column: true
	});
}