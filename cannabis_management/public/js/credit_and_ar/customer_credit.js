frappe.ui.form.on("Customer", {
	refresh(frm) {
		render_exemption_banner(frm);
	},

	custom_credit_policy_exempt(frm) {
		render_exemption_banner(frm);

		if (frm.doc.custom_credit_policy_exempt) {
			frappe.show_alert({
				message: __(
					"Credit & AR policy switched off for this account. Record why in Exemption Reason."
				),
				indicator: "orange",
			});
		}
	},
});

function render_exemption_banner(frm) {
	if (frm.is_new()) return;

	if (frm.doc.custom_credit_policy_exempt) {
		frm.dashboard.set_headline(
			__(
				"<b>Exempt from the Credit &amp; AR policy.</b> No order gate, no holds, no AR cases, no finance charges, no score. Their balance still counts toward the company AR cap, DSO and CEI. {0}",
				[
					frm.doc.custom_credit_policy_exempt_reason
						? frappe.utils.escape_html(frm.doc.custom_credit_policy_exempt_reason)
						: "",
				]
			),
			"blue"
		);
		return;
	}

	if (frm.doc.custom_credit_status === "Hard Hold") {
		frappe.call({
			method: "cannabis_management.credit_and_ar.api.get_customer_hold_type",
			args: { customer: frm.doc.name },
			callback(r) {
				frm.dashboard.set_headline(
					__("STOP WORK — this account is on {0}.", [r.message || __("hold")]),
					"red"
				);
			},
		});
	}
}
