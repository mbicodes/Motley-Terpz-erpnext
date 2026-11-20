function render_receipt_preview(frm) {
	var field = frm.get_field('receipt_preview');
	if (!field) return;
	var url = frm.doc.receipt;
	if (!url) {
		field.$wrapper.html(
			'<div style="border:1.5px dashed var(--border-color,#d1d5db);border-radius:10px;' +
			'padding:26px 12px;text-align:center;color:var(--text-muted,#94a3b8);font-size:12px;">' +
			__('Receipt preview appears here once attached') + '</div>');
		return;
	}
	var encoded = encodeURI(url);
	var is_image = /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(url.split('?')[0]);
	var inner;
	if (is_image) {
		inner = '<a href="' + encoded + '" target="_blank" rel="noopener" title="' + __('Open full size') + '">' +
			'<img src="' + encoded + '" alt="Receipt" loading="lazy" ' +
			'style="max-width:100%;max-height:320px;border-radius:10px;display:block;' +
			'border:1px solid var(--border-color,#e2e8f0);box-shadow:0 2px 12px rgba(15,23,42,.10);">' +
			'</a>' +
			'<div style="font-size:11px;color:var(--text-muted,#94a3b8);margin-top:5px;">' +
			__('Click to open full size') + '</div>';
	} else {
		inner = '<a href="' + encoded + '" target="_blank" rel="noopener">' + __('Open attached receipt') + '</a>';
	}
	field.$wrapper.html(
		'<div style="padding:2px 0;">' +
		'<div style="font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;' +
		'color:var(--text-muted,#94a3b8);margin-bottom:6px;">' + __('Receipt') + '</div>' + inner + '</div>');
}

function is_reimbursement(frm) {
	return frm.doc.transaction_type === 'Reimbursement';
}

function set_default_safe(frm) {
	// Paid From Safe / Safe are permlevel 1 (Finance only); for requesters the server fills the Safe.
	if (!frm.perm || !frm.perm[1] || !frm.perm[1].write) return;
	frappe.call({
		method: 'cannabis_management.cash_management.doctype.personal_cash_tracking.personal_cash_tracking.get_safe_defaults',
		callback: function (r) {
			if (r.message && r.message.safe_person && !frm.doc.safe_person) {
				frm.set_value('safe_person', r.message.safe_person);
			}
		}
	});
}

function reimbursement_ui(frm) {
	var reimb = is_reimbursement(frm);
	frm.set_df_property('money_in', 'description', reimb
		? __('Amount you are asking to be reimbursed.')
		: __('ONLY fill this out if you collected money.'));
	if (!reimb) return;
	if (frm.doc.docstatus === 0 && (!frm.doc.workflow_state || frm.doc.workflow_state === 'Draft')) {
		frm.set_intro(__('This request will be sent to the Safe for approval.'), 'blue');
	} else if (frm.doc.workflow_state === 'Pending Approval') {
		frm.set_intro(__('This request is awaiting approval. Nothing has been posted yet.'), 'orange');
	} else if (frm.doc.workflow_state === 'Rejected') {
		frm.set_intro(__('This request was rejected: {0}', [frappe.utils.escape_html(frm.doc.rejection_reason || '')]), 'red');
	}
}

function toggle_money_fields(frm) {
	var money_in = flt(frm.doc.money_in);
	var money_out = flt(frm.doc.money_out);
	frm.set_df_property('money_out', 'read_only', money_in ? 1 : 0);
	frm.set_df_property('money_in', 'read_only', money_out ? 1 : 0);
}

frappe.ui.form.on('Personal Cash Tracking', {
	setup: function (frm) {
		frm.set_query('cash_tracker_person', function () {
			return { filters: { is_active: 1 } };
		});
		frm.set_query('safe_person', function () {
			return { filters: { is_active: 1, allow_for_safe: 1 } };
		});
		cannabis.cash_tracking.setup(frm);
	},

	onload: function (frm) {
		if (frm.is_new() && !frm.doc.transaction_date) {
			frm.set_value('transaction_date', frappe.datetime.get_today());
		}
		if (frm.is_new() && !frm.doc.cash_tracker_person) {
			frappe.db.get_value('Cash Tracker Person',
				{ user: frappe.session.user, is_active: 1 }, 'name')
				.then(function (r) {
					if (r.message && r.message.name) {
						frm.set_value('cash_tracker_person', r.message.name);
					}
				});
		}
	},

	refresh: function (frm) {
		if (frm.is_new()) {
			frm.set_intro(
				__('Fill <b>Money In</b> only if you collected money, or <b>Money Out</b> only if you spent money — never both.'),
				'blue'
			);
		}
		reimbursement_ui(frm);
		toggle_money_fields(frm);
		render_receipt_preview(frm);
		cannabis.cash_tracking.refresh(frm);
	},

	transaction_type: function (frm) {
		if (is_reimbursement(frm) && frm.doc.paid_from_safe && !frm.doc.safe_person) {
			set_default_safe(frm);
		}
		reimbursement_ui(frm);
	},

	paid_from_safe: function (frm) {
		if (frm.doc.paid_from_safe && !frm.doc.safe_person) set_default_safe(frm);
	},

	before_workflow_action: function (frm) {
		if (frm.selected_workflow_action !== 'Reject') return;
		return new Promise(function (resolve, reject) {
			var d = new frappe.ui.Dialog({
				title: __('Reject Reimbursement Request'),
				fields: [{
					fieldname: 'reason', fieldtype: 'Small Text', reqd: 1,
					label: __('Rejection Reason'),
					description: __('The requester will see this reason.')
				}],
				primary_action_label: __('Reject'),
				primary_action: function (values) {
					frappe.call({
						method: 'cannabis_management.cash_management.doctype.personal_cash_tracking.personal_cash_tracking.set_rejection_reason',
						args: { name: frm.doc.name, reason: values.reason },
						freeze: true,
						callback: function () { d.hide(); resolve(); },
						error: function () { reject(); }
					});
				},
				secondary_action_label: __('Cancel')
			});
			d.onhide = function () { reject(); };
			d.show();
		});
	},

	receipt: function (frm) {
		render_receipt_preview(frm);
	},

	invoice_number: function (frm) {
		cannabis.cash_tracking.invoice_number(frm);
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
