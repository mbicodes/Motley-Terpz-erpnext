// Money In and Money Out are mutually exclusive — mirror of the server
// validation in personal_cash_tracking.py, enforced live in the form.

function toggle_money_fields(frm) {
	var money_in = flt(frm.doc.money_in);
	var money_out = flt(frm.doc.money_out);
	frm.set_df_property('money_out', 'read_only', money_in ? 1 : 0);
	frm.set_df_property('money_in', 'read_only', money_out ? 1 : 0);
}

frappe.ui.form.on('Personal Cash Tracking', {
	onload: function (frm) {
		if (frm.is_new() && !frm.doc.transaction_date) {
			frm.set_value('transaction_date', frappe.datetime.get_today());
		}
	},

	refresh: function (frm) {
		if (frm.is_new()) {
			frm.set_intro(
				__('Fill <b>Money In</b> only if you collected money, or <b>Money Out</b> only if you spent money — never both.'),
				'blue'
			);
		}
		toggle_money_fields(frm);
	},

	money_in: function (frm) {
		if (flt(frm.doc.money_in) && flt(frm.doc.money_out)) {
			frm.set_value('money_out', 0);
		}
		toggle_money_fields(frm);
	},

	money_out: function (frm) {
		if (flt(frm.doc.money_out) && flt(frm.doc.money_in)) {
			frm.set_value('money_in', 0);
		}
		toggle_money_fields(frm);
	}
});
