frappe.ui.form.on("AR Case", {
	refresh(frm) {
		render_banner(frm);
		add_actions(frm);
	},

	case_type(frm) {
		render_banner(frm);
	},
});

const INACTIVE = ["Cured", "Released", "Closed"];
const HOLDING = ["Hard Hold", "Immediate Hold"];

function is_finance() {
	return ["Credit Finance", "System Manager"].some((r) => frappe.user_roles.includes(r));
}

function render_banner(frm) {
	frm.dashboard.clear_headline();
	if (frm.is_new()) return;

	if (INACTIVE.includes(frm.doc.status)) {
		frm.dashboard.set_headline(
			__("This case is {0} — it no longer restrains the customer.", [frm.doc.status]),
			"green"
		);
		return;
	}

	if (HOLDING.includes(frm.doc.case_type)) {
		frm.dashboard.set_headline(
			__(
				"STOP WORK — {0} is on {1}. No Sales Order, Delivery Note, Work Order or production Stock Entry can be submitted. Quotations are still allowed.",
				[frm.doc.customer, frm.doc.case_type]
			),
			"red"
		);
	} else if (frm.doc.case_type === "Warning") {
		frm.dashboard.set_headline(
			__("{0} is past due. Work continues, but the clock is running.", [frm.doc.customer]),
			"orange"
		);
	}
}

function add_actions(frm) {
	if (frm.is_new()) return;

	if (!INACTIVE.includes(frm.doc.status) && is_finance()) {
		frm.add_custom_button(__("Release Hold"), () => {
			frappe.prompt(
				[
					{
						fieldname: "release_basis",
						fieldtype: "Select",
						label: __("Release Basis"),
						options: ["Paid in Full", "Current on Approved Plan", "MD Exception"],
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
		}).addClass("btn-primary");
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
