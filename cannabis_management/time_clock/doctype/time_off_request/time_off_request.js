frappe.ui.form.on("Time Off Request", {
	refresh(frm) {
		show_balance(frm);
		if (frm.is_new()) return;
		const me = frappe.session.user;
		const hr = frappe.user.has_role(["HR Manager", "HR User", "System Manager"]);
		const call = (method, args) =>
			frappe
				.call({ method: "cannabis_management.time_clock.time_off." + method, args: { name: frm.doc.name, ...args }, freeze: true })
				.then(() => frm.reload_doc());

		if (frm.doc.status === "Pending" && (me === frm.doc.approver || hr) && me !== frm.doc.employee_user) {
			frm.add_custom_button(__("Approve"), () => call("decide", { approve: 1 })).addClass("btn-primary");
			frm.add_custom_button(__("Deny"), () =>
				frappe.prompt(
					{ fieldname: "comment", fieldtype: "Small Text", label: __("Reason (sent to the employee)") },
					(v) => call("decide", { approve: 0, comment: v.comment }),
					__("Deny Request"),
					__("Deny")
				)
			);
		}
		if (["Pending", "Approved"].includes(frm.doc.status) && (me === frm.doc.employee_user || me === frm.doc.owner || hr)) {
			frm.add_custom_button(__("Cancel Request"), () =>
				frappe.confirm(__("Cancel this time off? The hours go back to the bank."), () => call("cancel"))
			);
		}
	},
	employee: show_balance,
	leave_type: show_balance,
});

function show_balance(frm) {
	frappe
		.call({ method: "cannabis_management.time_clock.time_off.get_balances", args: { employee: frm.doc.employee || null } })
		.then((r) => {
			const b = r.message;
			if (!b) return frm.set_intro(__("Your user is not linked to an Employee. Ask HR to link it."), "red");
			if (!b.category) return frm.set_intro(__("This employee has no Time Off Category (Full Time / Part Time) yet. Ask HR."), "orange");
			const t = b.types[frm.doc.leave_type || "PTO"];
			frm.set_intro(
				__("{0} ({1}): {2} hrs available. Earned {3}, used {4}, waiting approval {5}.", [
					frm.doc.leave_type || "PTO", b.category, t.available, t.earned, t.used, t.pending,
				]),
				"blue"
			);
		});
}
