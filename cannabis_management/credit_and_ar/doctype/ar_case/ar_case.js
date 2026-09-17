frappe.ui.form.on("AR Case", {
	refresh(frm) {
		render_banner(frm);
		add_actions(frm);
	},
	// Resolution/frequency drive whether Generate Plan shows — re-evaluate the
	// moment either changes, without waiting for a save + reload.
	resolution(frm) {
		add_actions(frm);
	},
	installment_frequency(frm) {
		add_actions(frm);
	},
});

function is_finance() {
	return ["Credit Finance", "System Manager"].some((r) => frappe.user_roles.includes(r));
}

function is_md() {
	return ["Managing Director", "System Manager"].some((r) => frappe.user_roles.includes(r));
}

function render_banner(frm) {
	frm.dashboard.clear_headline();
	if (frm.is_new()) return;

	if (frm.doc.status === "Closed") {
		frm.dashboard.set_headline(
			__("This case is Closed — it no longer restrains the customer."),
			"green"
		);
	}
}

function add_actions(frm) {
	// Idempotent: called again on resolution/installment_frequency change, not
	// just on refresh, so clear whatever we added last time first.
	frm.clear_custom_buttons();

	if (frm.is_new()) return;

	if (frm.doc.status === "Active") {
		if (is_finance()) {
			frm.add_custom_button(__("Release Hold"), () => release_hold(frm), __("Create"));
			frm.add_custom_button(
				__("Payment Plan"),
				() => set_resolution(frm, "Payment Plan", "sec_plan"),
				__("Create")
			);
		}
		if (is_md()) {
			frm.add_custom_button(
				__("Workout"),
				() => set_resolution(frm, "Workout", "sec_workout"),
				__("Create")
			);
		}
		if (is_finance() || is_md()) {
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		}
	}

	if (
		frm.doc.resolution === "Payment Plan" &&
		frm.doc.installment_frequency &&
		frm.doc.installment_frequency !== "Custom"
	) {
		frm.add_custom_button(__("Generate Plan"), () => generate_plan(frm));
	}

	frm.add_custom_button(
		__("Customer"),
		() => frappe.set_route("Form", "Customer", frm.doc.customer),
		__("View")
	);

	frm.add_custom_button(
		__("Refresh Figures"),
		() => {
			frappe.call({
				method: "cannabis_management.credit_and_ar.api.refresh_ar_case",
				args: { case_name: frm.doc.name },
				callback: () => frm.reload_doc(),
			});
		},
		__("View")
	);
}

function release_hold(frm) {
	frappe.prompt(
		[
			{
				fieldname: "release_basis",
				fieldtype: "Select",
				label: __("Release Basis"),
				options: ["Paid in Full", "MD Exception"],
				reqd: 1,
			},
			{
				fieldname: "notes",
				fieldtype: "Small Text",
				label: __("Notes"),
				description: __("Required for an MD exception — record who approved it."),
			},
		],
		({ release_basis, notes }) => {
			frappe.call({
				method: "cannabis_management.credit_and_ar.api.release_ar_case",
				args: { case_name: frm.doc.name, release_basis, notes },
				freeze: true,
				freeze_message: __("Verifying the release basis…"),
				callback: () => {
					frappe.show_alert({
						message: __("Hold released."),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
		__("Release Hold"),
		__("Release")
	);
}

function generate_plan(frm) {
	if (!frm.doc.plan_start_date || !frm.doc.plan_end_date) {
		frappe.msgprint(__("Set Plan Start Date and Plan End Date first."));
		return;
	}

	const run = () => {
		frappe.call({
			method: "cannabis_management.credit_and_ar.plan_workout.generate_schedule",
			args: {
				case_name: frm.doc.name,
				resolution: frm.doc.resolution,
				plan_start_date: frm.doc.plan_start_date,
				plan_end_date: frm.doc.plan_end_date,
				installment_frequency: frm.doc.installment_frequency,
			},
			freeze: true,
			freeze_message: __("Building the installment schedule…"),
			callback: (r) => {
				const result = r.message;
				if (!result) return;

				frm.clear_table("schedule");

				(result.installments || []).forEach((inst) => {
					const row = frm.add_child("schedule", {
						due_date: inst.due_date,
						amount: inst.amount,
					});
					(inst.invoices || []).forEach((inv) => {
						const inv_row = frappe.model.add_child(
							row,
							"AR Case Installment Invoice",
							"invoices"
						);
						inv_row.sales_invoice = inv.sales_invoice;
						inv_row.allocated_amount = inv.allocated_amount;
					});
				});

				frm.refresh_field("schedule");
				frm.dirty();
				frappe.show_alert({
					message: __(
						"{0} installment(s) generated from {1} open invoice(s), totalling {2}. Review and Save.",
						[
							(result.installments || []).length,
							result.invoice_count,
							format_currency(result.total),
						]
					),
					indicator: "green",
				});
				frm.scroll_to_field("sec_schedule");
			},
		});
	};

	if ((frm.doc.schedule || []).length) {
		frappe.confirm(
			__("This replaces the existing installment schedule. Continue?"),
			run
		);
	} else {
		run();
	}
}

function set_resolution(frm, resolution, section_fieldname) {
	if (frm.doc.resolution === resolution) {
		frm.scroll_to_field(section_fieldname);
		return;
	}
	frm.set_value("resolution", resolution).then(() => {
		frm.scroll_to_field(section_fieldname);
		frappe.show_alert({
			message: __("Fill in the {0} details below, then save.", [resolution]),
			indicator: "blue",
		});
	});
}
