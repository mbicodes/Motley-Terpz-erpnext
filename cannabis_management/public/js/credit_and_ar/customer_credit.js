// Customer — make the Credit & AR policy exemption impossible to miss.
//
// An account that is carved out of the policy looks identical to one that is
// inside it until you open the Credit Control tab. This banner puts it at the
// top of the form instead.

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

	// "On Hold" is Credit Status = Hard Hold now; the checkbox it used to read is gone.
	if (frm.doc.custom_credit_status === "Hard Hold") {
		// Hold Type is no longer stored on the Customer; ask the server for the
		// value derived from the active AR Case.
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

// New customers need an email address and a phone number
// (credit_and_ar/customer_contact_rules.py). The New Customer dialog asks for
// both; the full form only shows them read-only, so ask here rather than let the
// save fail. Administrator and Muhammad are exempt, as on the server. An
// internal customer (Is Internal Customer) needs only the phone number.
(function () {
	const EXEMPT = ['Administrator', 'muhammad@motleyterpz.com'];

	frappe.ui.form.on('Customer', {
		validate: function (frm) {
			if (!frm.is_new() || EXEMPT.indexOf(frappe.session.user) !== -1) return;
			const email_required = !frm.doc.is_internal_customer;
			const has_email = !!(frm.doc.email_id || '').trim();
			if ((has_email || !email_required) && (frm.doc.mobile_no || '').trim()) return;
			frappe.validated = false;
			const d = new frappe.ui.Dialog({
				title: __('Contact details required'),
				fields: [
					{ fieldname: 'email_id', fieldtype: 'Data', options: 'Email', label: __('Email Address'), reqd: email_required ? 1 : 0, default: frm.doc.email_id || '' },
					{ fieldname: 'mobile_no', fieldtype: 'Data', options: 'Phone', label: __('Phone Number'), reqd: 1, default: frm.doc.mobile_no || '' },
				],
				primary_action_label: __('Save Customer'),
				primary_action: function (values) {
					frm.doc.email_id = (values.email_id || '').trim();
					frm.doc.mobile_no = (values.mobile_no || '').trim();
					d.hide();
					frm.save();
				},
			});
			d.show();
		},
	});
})();
