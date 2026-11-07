frappe.ui.form.on("AR Collection", {
	refresh(frm) {
		frm.add_custom_button(__("Open AR Collections board"), () => frappe.set_route("ar-collections"));
		if (!frm.is_new()) {
			frm.add_custom_button(__("Print Statement"), () => {
				frappe
					.xcall("frappe.client.get_single_value", {
						doctype: "AR Collections Settings",
						field: "statement_print_format",
					})
					.then((fmt) => {
						const url =
							"/printview?doctype=" +
							encodeURIComponent(frm.doctype) +
							"&name=" +
							encodeURIComponent(frm.doc.name) +
							"&format=" +
							encodeURIComponent(fmt || "AR Collection Statement") +
							"&no_letterhead=0";
						window.open(url, "_blank");
					});
			});
		}
	},
});
