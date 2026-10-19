// "Break / Make Connections" in the menu of every submittable form: opens the
// Connection Tool for this document (the one still holding broken links, if any).
$(document).on("form-refresh", (e, frm) => {
	if (!frm || frm.is_new() || !frm.meta.is_submittable || frm.doctype === "Connection Tool") return;
	if (!frappe.model.can_create("Connection Tool")) return;

	frm.page.add_menu_item(__("Break / Make Connections"), () =>
		frappe
			.xcall(
				"cannabis_management.cannabis_management.doctype.connection_tool.connection_tool.open_tool",
				{ reference_doctype: frm.doctype, reference_name: frm.doc.name }
			)
			.then((name) => frappe.set_route("Form", "Connection Tool", name))
	);
});
