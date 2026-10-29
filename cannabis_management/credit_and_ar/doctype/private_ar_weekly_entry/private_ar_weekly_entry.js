(function () {
	const PAR_WE_STATUSES_BY_TIER = {
		upcoming: ['Will Pay On Time'],
		level1: ['Will Pay Immediately', 'Client Is Dodging Us', 'Need Reconciliation',
			'WIP At Lab', 'Pending Pickup', 'Payment Plan', 'No Longer In Business'],
		level2: ['Will Pay Immediately', 'Client Is Dodging Us', 'Need Reconciliation',
			'WIP At Lab', 'Pending Pickup', 'Payment Plan', 'No Longer In Business'],
		level3: ['Will Pay Immediately', 'Client Is Dodging Us', 'Need Reconciliation',
			'WIP At Lab', 'Pending Pickup', 'Payment Plan', 'No Longer In Business'],
	};

	frappe.ui.form.on('Private AR Weekly Entry', {
		refresh: function (frm) {
			frm.trigger('tier_snapshot');
		},

		tier_snapshot: function (frm) {
			let allowed = PAR_WE_STATUSES_BY_TIER[frm.doc.tier_snapshot];
			frm.set_df_property('status', 'options', ['']
				.concat(allowed || [].concat.apply([], Object.values(PAR_WE_STATUSES_BY_TIER)))
				.filter((v, i, a) => a.indexOf(v) === i)
				.join('\n'));
			if (allowed && frm.doc.status && allowed.indexOf(frm.doc.status) === -1) {
				frm.set_value('status', '');
			}
		},
	});
})();
