// Live-recalculate the summary lenses as lines are edited, mirroring
// weekly_cash_ledger.py (server recomputes authoritatively on save).

function wcl_money(row) {
	return flt(row.amount) || flt(row.expected_amount);
}

function wcl_recalc(frm) {
	var lines = frm.doc.lines || [];

	function split(rows) {
		var t = 0, c = 0, b = 0;
		rows.forEach(function (r) {
			var v = wcl_money(r);
			t += v;
			if (r.method === 'Cash') c += v;
			if (r.method === 'Bank') b += v;
		});
		return [t, c, b];
	}

	var collected = lines.filter(function (r) { return r.status === 'Collected'; });
	var expected = lines.filter(function (r) { return r.status === 'Expected this week'; });
	var col = split(collected), exp = split(expected);

	frm.set_value({
		collected_total: col[0], collected_cash: col[1], collected_bank: col[2],
		expected_total: exp[0], expected_cash: exp[1], expected_bank: exp[2],
		coming_in_total: col[0] + exp[0],
		coming_in_cash: col[1] + exp[1],
		coming_in_bank: col[2] + exp[2],
	});

	var sales = lines.filter(function (r) { return r.entry_type === 'Sales'; });
	var ar = lines.filter(function (r) { return r.entry_type === 'AR'; });
	var sum = function (rows) { return rows.reduce(function (s, r) { return s + wcl_money(r); }, 0); };

	frm.set_value({
		sales_written_total: sum(sales),
		sales_cod: sum(sales.filter(function (r) { return r.terms === 'COD'; })),
		sales_terms: sum(sales.filter(function (r) { return r.terms === 'Terms'; })),
		ar_total: sum(ar),
		ar_collected: sum(ar.filter(function (r) { return r.status === 'Collected'; })),
		ar_expected: sum(ar.filter(function (r) { return r.status === 'Expected this week'; })),
	});

	var outbound = lines.filter(function (r) { return r.direction === 'Outbound'; });
	var inbound = lines.filter(function (r) { return r.direction === 'Inbound'; });
	frm.set_value({
		outbound_value: sum(outbound), outbound_orders: outbound.length,
		inbound_value: sum(inbound), inbound_orders: inbound.length,
	});

	// per-category actuals (new sales only)
	var by_cat = {};
	sales.forEach(function (r) {
		if (r.category) by_cat[r.category] = (by_cat[r.category] || 0) + wcl_money(r);
	});
	var target_total = 0;
	(frm.doc.targets || []).forEach(function (t) {
		frappe.model.set_value(t.doctype, t.name, 'actual_amount', by_cat[t.category] || 0);
		target_total += flt(t.target_amount);
	});
	frm.set_value('sales_target_total', target_total);
}

frappe.ui.form.on('Weekly Cash Ledger', {
	refresh: function (frm) {
		frm.set_intro(
			__('One row per line of money. Summaries update as you type and are re-checked on save.'),
			'blue'
		);
	},
});

frappe.ui.form.on('Weekly Cash Ledger Line', {
	entry_type: wcl_recalc_row, amount: wcl_recalc_row, expected_amount: wcl_recalc_row,
	method: wcl_recalc_row, terms: wcl_recalc_row, status: wcl_recalc_row,
	direction: wcl_recalc_row, category: wcl_recalc_row,
	lines_remove: function (frm) { wcl_recalc(frm); },
});

frappe.ui.form.on('Weekly Sales Target Line', {
	target_amount: wcl_recalc_row,
	targets_remove: function (frm) { wcl_recalc(frm); },
});

function wcl_recalc_row(frm) {
	wcl_recalc(frm);
}
