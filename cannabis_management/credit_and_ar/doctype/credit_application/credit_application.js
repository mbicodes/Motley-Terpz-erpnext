frappe.ui.form.on("Credit Application", {
	setup(frm) {
		frm.set_query("credit_group_parent", () => ({
			filters: { name: ["!=", frm.doc.customer || ""] },
		}));
	},

	refresh(frm) {
		frm.dashboard.clear_headline();
		render_license_banner(frm);
		render_exposure_banner(frm);

		if (frm.doc.customer && !frm.is_new()) {
			frm.add_custom_button(
				__("Customer"),
				() => frappe.set_route("Form", "Customer", frm.doc.customer),
				__("View")
			);
		}
	},

	customer(frm) {
		if (!frm.doc.customer) return;

		frappe.db
			.get_value("Customer", frm.doc.customer, [
				"customer_name",
				"custom_license_number",
				"custom_license_expiry",
				"custom_credit_group_parent",
				"custom_ap_contact_name",
				"custom_ap_contact_phone",
				"custom_ap_contact_email",
			])
			.then(({ message }) => {
				if (!message) return;
				const map = {
					exact_legal_buyer: message.customer_name,
					license_number: message.custom_license_number,
					license_expiry_date: message.custom_license_expiry,
					credit_group_parent: message.custom_credit_group_parent,
					ap_contact_name: message.custom_ap_contact_name,
					ap_contact: message.custom_ap_contact_phone,
					ap_contact_email: message.custom_ap_contact_email,
				};
				// Only fill blanks — never overwrite what the credit file already says.
				Object.entries(map).forEach(([field, value]) => {
					if (value && !frm.doc[field]) frm.set_value(field, value);
				});
			});
	},

	recommended_limit(frm) {
		frm.set_value("requested_limit", frm.doc.requested_limit || frm.doc.recommended_limit);
	},

	license_expiry_date(frm) {
		render_license_banner(frm);
	},
});

function render_license_banner(frm) {
	if (!frm.doc.license_expiry_date) return;

	const days = frappe.datetime.get_day_diff(frm.doc.license_expiry_date, frappe.datetime.get_today());

	if (days < 0) {
		frm.dashboard.set_headline(
			__("The license expired {0} days ago. An expired license cannot support a credit line.", [
				Math.abs(days),
			]),
			"red"
		);
	} else if (days <= 30) {
		frm.dashboard.set_headline(
			__("The license expires in {0} days.", [days]),
			days <= 7 ? "red" : "orange"
		);
	}
}

function render_exposure_banner(frm) {
	if (!frm.doc.group_existing_exposure) return;

	frm.dashboard.add_comment(
		__("Group already owes {0} across all operating companies.", [
			format_currency(frm.doc.group_existing_exposure),
		]),
		"blue",
		true
	);
}
