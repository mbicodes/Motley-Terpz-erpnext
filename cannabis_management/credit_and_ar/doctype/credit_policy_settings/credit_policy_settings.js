frappe.ui.form.on("Credit Policy Settings", {
	refresh(frm) {
		frm.dashboard.clear_headline();

		if (!frm.doc.policy_effective_date) {
			frm.dashboard.set_headline(
				__(
					"Policy Effective Date is not set. Every Credit &amp; AR scheduled job is inert until you set it."
				),
				"orange"
			);
			return;
		}

		if (frm.doc.company_freeze_active) {
			frm.dashboard.set_headline(
				__("Company freeze is ACTIVE — {0}", [
					frappe.utils.escape_html(frm.doc.freeze_reason || __("reason not recorded")),
				]),
				"red"
			);
		}
	},
});
