
// Render the attached receipt image in the preview panel on the right.
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

// Money In and Money Out are mutually exclusive — mirror of the server
// validation in tsbc_cash_tracking.py, enforced live in the form.

function toggle_money_fields(frm) {
	var money_in = flt(frm.doc.money_in);
	var money_out = flt(frm.doc.money_out);
	frm.set_df_property('money_out', 'read_only', money_in ? 1 : 0);
	frm.set_df_property('money_in', 'read_only', money_out ? 1 : 0);
}

frappe.ui.form.on('TSBC Cash Tracking', {
	setup: function (frm) {
		// Only people ticked "Allow For TSBC" can be picked here — the server
		// enforces the same rule in TSBCCashTracking.validate_tsbc_allowed.
		frm.set_query('cash_tracker_person', function () {
			return { filters: { is_active: 1, allow_for_tsbc: 1 } };
		});
		cannabis.cash_tracking.setup(frm);
	},

	onload: function (frm) {
		if (frm.is_new() && !frm.doc.cash_tracker_person) {
			frappe.db.get_value('Cash Tracker Person',
				{ user: frappe.session.user, is_active: 1, allow_for_tsbc: 1 }, 'name')
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
		toggle_money_fields(frm);
		render_receipt_preview(frm);
		cannabis.cash_tracking.refresh(frm);
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
