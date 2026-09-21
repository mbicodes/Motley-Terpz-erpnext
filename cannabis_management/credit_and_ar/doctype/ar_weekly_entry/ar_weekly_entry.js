// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

// Mirrors STATUSES_BY_TIER in ar_weekly_entry.py. The server enforces the same
// rule on validate; this only keeps the dropdown honest while typing.
const AR_WE_STATUSES_BY_TIER = {
	upcoming: ['Will Pay On Time'],
	level1: ['Will Pay Immediately', 'Client Is Dodging Us', 'Need Reconciliation'],
	level2: ['Will Pay Immediately', 'Client Is Dodging Us', 'Need Reconciliation'],
	level3: ['Will Pay Immediately', 'Client Is Dodging Us', 'Need Reconciliation'],
};

frappe.ui.form.on('AR Weekly Entry', {
	refresh: function (frm) {
		frm.trigger('tier_snapshot');
	},

	tier_snapshot: function (frm) {
		let allowed = AR_WE_STATUSES_BY_TIER[frm.doc.tier_snapshot];
		// No tier recorded (a hand-made entry) — leave every option available
		// rather than emptying the dropdown.
		frm.set_df_property('status', 'options', ['']
			.concat(allowed || [].concat.apply([], Object.values(AR_WE_STATUSES_BY_TIER)))
			.filter((v, i, a) => a.indexOf(v) === i)
			.join('\n'));
		if (allowed && frm.doc.status && allowed.indexOf(frm.doc.status) === -1) {
			frm.set_value('status', '');
		}
	},
});
