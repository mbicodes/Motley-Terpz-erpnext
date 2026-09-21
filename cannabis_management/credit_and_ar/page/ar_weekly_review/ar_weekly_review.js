// Copyright (c) 2026, alltechvirtual.com and contributors
// AR Weekly Review — port of the ar_weekly_review.html mockup onto a Desk page.
//
// Tier and amount are never stored; every load recomputes them from Sales
// Invoice server-side (see ar_weekly_review.py). Saving a week's entry inserts
// an AR Weekly Entry and never overwrites an earlier one, which is what gives
// the per-customer history at the bottom of an expanded row.

const ARW_METHOD = 'cannabis_management.credit_and_ar.page.ar_weekly_review.ar_weekly_review.';

const ARW_TIER_DEF = {
	upcoming: { label: 'Upcoming', full: 'Upcoming Terms Due',
		desc: 'On agreed terms, not yet due.' },
	level1: { label: 'Level 1', full: 'Bad Debt Level 1 (0–30)',
		desc: 'Should never get here. Extremely urgent. In default.',
		q1: 'How did this account get here?', call: true },
	level2: { label: 'Level 2', full: 'Bad Debt Level 2 (30–60)',
		desc: 'DEFCON Level 2 — Emergency.',
		q1: 'What is going on?', call: true },
	level3: { label: 'Level 3', full: 'Bad Debt Level 3 (60+)',
		desc: 'Legal pursuit status.',
		q1: 'What is going on?', call: true },
};
const ARW_TIER_ORDER = ['upcoming', 'level1', 'level2', 'level3'];
const ARW_STATUS_ORDER = ['Will Pay On Time', 'Will Pay Immediately',
	'Client Is Dodging Us', 'Need Reconciliation'];
const ARW_STATUS_CLASS = {
	'Will Pay On Time': 's-pay',
	'Will Pay Immediately': 's-pay',
	'Client Is Dodging Us': 's-dodge',
	'Need Reconciliation': 's-recon',
};
const ARW_STATUS_DEF = {
	none: { full: 'No Status Set', desc: 'Needs a status this week.' },
	'Will Pay On Time': { full: 'Will Pay On Time', desc: '' },
	'Will Pay Immediately': { full: 'Will Pay Immediately', desc: '' },
	'Client Is Dodging Us': { full: 'Client Is Dodging Us', desc: '' },
	'Need Reconciliation': { full: 'Need Reconciliation', desc: '' },
};

frappe.pages['ar-weekly-review'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('AR Weekly Review'),
		single_column: true,
	});
	wrapper.page = page;

	page.arw = {
		rows: [],
		meta: {},
		open: {},          // row id -> expanded?
		logs: {},          // "customer|ledger" -> log rows (lazy loaded)
		edits: {},         // row id -> unsaved form values
		ui: { mode: 'tier', ledger: 'New AR', search: '' },
	};

	page.main.html(`
		<div class="arw-root">
			<div class="arw-head">
				<div>
					<div class="arw-title">${__('Accounts Receivable — Weekly Review')}</div>
					<div class="arw-sub" id="arw-sub">${__('Loading…')}</div>
				</div>
				<div style="display:flex;align-items:center;">
					<span class="arw-savemsg" id="arw-savemsg"></span>
					<button class="btn btn-default btn-sm" id="arw-refresh">${__('Refresh')}</button>
				</div>
			</div>

			<div class="arw-kpis" id="arw-kpis"></div>

			<div class="arw-seclabel">${__('Group by')}</div>
			<div class="arw-seg" id="arw-modeseg">
				<button data-mode="tier" class="on">${__('By debt level')}</button>
				<button data-mode="status">${__('By status')}</button>
			</div>

			<div class="arw-toolbar">
				<input class="arw-search" id="arw-search" type="text" placeholder="${__('Search customer…')}">
				<div class="arw-seg" id="arw-ledgerseg">
					<button data-ledger="New AR" class="on">${__('New AR')}</button>
					<button data-ledger="Legacy AR">${__('Legacy AR')}</button>
				</div>
				<div class="arw-spacer"></div>
				<span class="arw-count" id="arw-count"></span>
			</div>

			<div id="arw-groups">
				<div class="arw-loading">${__('Loading receivables…')}</div>
			</div>

			<div class="arw-foot">
				${__('Each customer has one row per ledger. On-terms and overdue balances are shown separately because only one of them is moving. "Save this week\'s entry" adds a new dated entry without erasing earlier ones.')}
			</div>
		</div>
	`);

	bind_events(page);
	load(page);
};

function bind_events(page) {
	page.main.find('#arw-refresh').on('click', () => load(page));

	page.main.find('#arw-modeseg button').on('click', function () {
		page.main.find('#arw-modeseg button').removeClass('on');
		$(this).addClass('on');
		page.arw.ui.mode = $(this).data('mode');
		render(page);
	});

	page.main.find('#arw-ledgerseg button').on('click', function () {
		page.main.find('#arw-ledgerseg button').removeClass('on');
		$(this).addClass('on');
		page.arw.ui.ledger = String($(this).data('ledger'));
		render(page);
	});

	page.main.find('#arw-search').on('input', function () {
		page.arw.ui.search = this.value;
		render(page);
	});

	// Row expand / collapse
	page.main.on('click', '.arw-rowline', function () {
		const id = $(this).data('rowid');
		page.arw.open[id] = !page.arw.open[id];
		if (page.arw.open[id]) load_log(page, id);
		render(page);
	});

	// Never let a click inside the editor collapse the row
	page.main.on('click', '.arw-detailwrap', (e) => e.stopPropagation());

	// Track edits so a re-render does not lose typing
	page.main.on('input change', '.arw-detailwrap [data-role]', function () {
		const id = $(this).data('rowid');
		const role = $(this).data('role');
		const edits = (page.arw.edits[id] = page.arw.edits[id] || {});
		edits[role] = this.type === 'checkbox' ? this.checked : this.value;
	});

	page.main.on('click', '.arw-addweek', function (e) {
		e.stopPropagation();
		save_entry(page, $(this).data('rowid'), $(this));
	});
}

function load(page) {
	frappe.call({
		method: ARW_METHOD + 'get_ar_weekly_review',
		args: { ledger: null },
		callback: function (r) {
			if (!r || !r.message) return;
			page.arw.rows = r.message.rows || [];
			page.arw.meta = r.message;
			page.arw.logs = {};
			page.main.find('#arw-sub').text(
				__('One row per customer per ledger · all entities · as of {0}', [r.message.as_of])
			);
			render(page);
		},
	});
}

function log_key(row) { return row.customer + '|' + row.ledger; }

function load_log(page, rowid) {
	const row = page.arw.rows.find((r) => r.id === rowid);
	if (!row) return;
	const key = log_key(row);
	if (page.arw.logs[key]) return;            // already fetched
	page.arw.logs[key] = 'loading';
	frappe.call({
		method: ARW_METHOD + 'get_ar_weekly_log',
		args: { customer: row.customer, ledger: row.ledger },
		callback: function (r) {
			page.arw.logs[key] = (r && r.message) || [];
			render(page);
		},
		error: function () {
			// Drop the sentinel so the row shows an empty log (and can retry on
			// the next render) rather than hanging on "Loading…".
			page.arw.logs[key] = [];
			render(page);
		},
	});
}

function fmt_money(n) {
	return '$' + Math.round(n || 0).toLocaleString('en-US');
}

function visible_rows(page) {
	const ui = page.arw.ui;
	const needle = (ui.search || '').toLowerCase();
	return page.arw.rows.filter(function (r) {
		if (r.ledger !== ui.ledger) return false;
		if (needle && r.customer.toLowerCase().indexOf(needle) === -1) return false;
		return true;
	});
}

function render(page) {
	render_kpis(page);
	render_groups(page);
	ensure_open_logs(page);
}

// Clicking is not the only way a row ends up expanded: it also stays open across
// a reload (after saving an entry, or hitting Refresh), and load() clears the log
// cache. Anything open without a cached log is fetched here, otherwise the log
// table sits on "Loading…" forever.
function ensure_open_logs(page) {
	Object.keys(page.arw.open).forEach(function (id) {
		if (page.arw.open[id]) load_log(page, id);
	});
}

function render_kpis(page) {
	const rows = visible_rows(page);
	const total = rows.reduce((s, r) => s + r.amount, 0);
	const unfiled = rows.filter((r) => !r.current_status);
	const filed = rows.filter((r) => r.current_status);
	const lvl3 = rows.filter((r) => r.tier === 'level3');

	const worst = lvl3.length ? '120+ days'
		: rows.some((r) => r.tier === 'level2') ? '30-60 days'
		: rows.some((r) => r.tier === 'level1') ? '0-30 days'
		: rows.length ? 'On terms' : 'n/a';

	const kpis = [
		{ cls: '', label: __('OUTSTANDING'), value: fmt_money(total),
			sub: rows.length + ' ' + __('rows') },
		{ cls: 'acc-orange', label: __('NO STATUS SET'),
			value: fmt_money(unfiled.reduce((s, r) => s + r.amount, 0)),
			sub: unfiled.length + ' ' + __('rows') },
		{ cls: 'acc-green', label: __('STATUS FILED'),
			value: fmt_money(filed.reduce((s, r) => s + r.amount, 0)),
			sub: filed.length + ' ' + __('rows') },
		{ cls: 'acc-blue', label: __('WORST AGING IN VIEW'), value: worst,
			sub: lvl3.length + ' ' + __('rows at Level 3') },
	];

	page.main.find('#arw-kpis').html(kpis.map((k) => `
		<div class="arw-kpi ${k.cls}">
			<div class="arw-kpi-label">${k.label}</div>
			<div class="arw-kpi-value">${k.value}</div>
			<div class="arw-kpi-sub">${k.sub}</div>
		</div>`).join(''));
}

function render_groups(page) {
	const pool = visible_rows(page);
	const by_tier = page.arw.ui.mode === 'tier';
	const keys = by_tier ? ARW_TIER_ORDER : ['none'].concat(ARW_STATUS_ORDER);
	const $wrap = page.main.find('#arw-groups').empty();

	let shown = 0, amt_shown = 0;

	keys.forEach(function (key) {
		const def = by_tier ? ARW_TIER_DEF[key] : ARW_STATUS_DEF[key];
		const rows = pool.filter((r) => by_tier
			? r.tier === key
			: (key === 'none' ? !r.current_status : r.current_status === key));
		rows.sort((a, b) => b.amount - a.amount);

		shown += rows.length;
		const amt = rows.reduce((s, r) => s + r.amount, 0);
		amt_shown += amt;

		const $box = $(`<div class="arw-box ${by_tier ? 'tier-' + key : ''}"></div>`);
		$box.append(`
			<div class="arw-boxhead">
				<div class="arw-titlerow">
					<div>
						<div class="arw-name">${frappe.utils.escape_html(def.full)}</div>
						${def.desc ? `<div class="arw-desc">${frappe.utils.escape_html(def.desc)}</div>` : ''}
					</div>
					<div class="arw-meta">
						<span class="arw-cnt">${rows.length} ${rows.length === 1 ? __('row') : __('rows')}</span>${fmt_money(amt)}
					</div>
				</div>
			</div>`);

		if (!rows.length) {
			$box.append(`<div class="arw-empty">${__('No accounts in this group right now.')}</div>`);
		} else {
			$box.append(build_table(page, rows, by_tier));
		}
		$wrap.append($box);
	});

	page.main.find('#arw-count').text(
		shown + ' ' + (shown === 1 ? __('row') : __('rows')) + ' · ' + fmt_money(amt_shown) + ' ' + __('total')
	);
}

function build_table(page, rows, by_tier) {
	const cols = 6 + (by_tier ? 1 : 1); // arrow + customer + (level|status) + amount + aging + notes
	let html = `<table class="arw-rows"><thead><tr>
			<th style="width:22px"></th>
			<th>${__('Customer')}</th>
			${by_tier ? '' : `<th>${__('Level')}</th>`}
			<th>${__('Amount')}</th>
			<th>${__('Worst aging')}</th>
			${by_tier ? `<th>${__('Status')}</th>` : ''}
			<th>${__('Latest note')}</th>
		</tr></thead><tbody>`;

	rows.forEach(function (r) {
		const open = !!page.arw.open[r.id];
		const status_html = r.current_status
			? `<span class="arw-statuschip ${ARW_STATUS_CLASS[r.current_status] || ''}">${frappe.utils.escape_html(r.current_status)}</span>`
			: `<span class="arw-statuschip">${__('No status yet')}</span>`;

		html += `<tr class="arw-rowline${open ? ' open' : ''}" data-rowid="${frappe.utils.escape_html(r.id)}">
			<td><span class="arw-arrow">▸</span></td>
			<td>
				<div class="arw-cust">${frappe.utils.escape_html(r.customer)}</div>
				<div class="arw-ledgertag">${r.ledger} · ${r.portion === 'upcoming' ? __('on terms') : __('overdue')} · ${r.invoice_count} ${__('inv')}</div>
			</td>
			${by_tier ? '' : `<td><span class="arw-tierchip ${r.tier}">${ARW_TIER_DEF[r.tier].label}</span></td>`}
			<td class="arw-amt">${fmt_money(r.amount)}</td>
			<td><span class="arw-days">${frappe.utils.escape_html(r.days)}</span></td>
			${by_tier ? `<td>${status_html}</td>` : ''}
			<td class="arw-notes">${r.latest_note ? frappe.utils.escape_html(r.latest_note) : '—'}</td>
		</tr>`;

		if (open) {
			html += `<tr class="arw-detail"><td colspan="${cols}">${detail_html(page, r)}</td></tr>`;
		}
	});

	return html + '</tbody></table>';
}

function detail_html(page, r) {
	const def = ARW_TIER_DEF[r.tier];
	const edits = page.arw.edits[r.id] || {};
	const esc = frappe.utils.escape_html;

	const bd = r.breakdown.map((b) =>
		`<div class="arw-bdchip">${esc(b.label)} &middot; <b>${fmt_money(b.amount)}</b></div>`).join('');

	const statuses = r.statuses || [];
	const opts = ['<option value="">— ' + __('pick status') + ' —</option>'].concat(
		statuses.map((s) => `<option value="${esc(s)}"${edits.status === s ? ' selected' : ''}>${esc(s)}</option>`)
	).join('');

	const log = page.arw.logs[log_key(r)];
	let log_rows;
	if (log === 'loading' || log === undefined) {
		log_rows = `<tr><td class="arw-emptylog" colspan="6">${__('Loading…')}</td></tr>`;
	} else if (!log.length) {
		log_rows = `<tr><td class="arw-emptylog" colspan="6">${__('No weekly entries yet — this will be the first.')}</td></tr>`;
	} else {
		log_rows = log.map((e) => `<tr>
			<td>${esc(e.week_of || '')}</td>
			<td>${esc(e.status || '')}</td>
			<td>${esc(e.qa || '')}</td>
			<td>${esc(e.plan || '')}</td>
			<td>${esc(e.notes || '')}</td>
			<td>${esc(e.contact || '')}${e.email ? ' · ' + esc(e.email) : ''}</td>
		</tr>`).join('');
	}

	const q1 = def.q1 || __('What is going on?');

	return `<div class="arw-detailwrap">
		<div class="arw-breakdown">${bd}</div>
		<div class="arw-qarow">
			<div class="arw-field">
				<label>${__('This week\'s status')}</label>
				<select data-role="status" data-rowid="${esc(r.id)}">${opts}</select>
			</div>
			${def.call ? `<div class="arw-field"><label>&nbsp;</label>
				<div class="arw-flagrow">
					<input type="checkbox" data-role="need_three_way_call" data-rowid="${esc(r.id)}" ${edits.need_three_way_call ? 'checked' : ''}>
					${__('Need three-way call with finance')}
				</div></div>` : '<div></div>'}
			<div class="arw-field full"><label>${esc(q1)}</label>
				<textarea data-role="qa" data-rowid="${esc(r.id)}">${esc(edits.qa || '')}</textarea></div>
			<div class="arw-field"><label>${__('What is the plan?')}</label>
				<textarea data-role="plan" data-rowid="${esc(r.id)}">${esc(edits.plan || '')}</textarea></div>
			<div class="arw-field"><label>${__('Notes')}</label>
				<textarea data-role="notes" data-rowid="${esc(r.id)}">${esc(edits.notes || '')}</textarea></div>
			<div class="arw-field"><label>${__('Contact info')}</label>
				<input type="text" data-role="contact" data-rowid="${esc(r.id)}" value="${esc(edits.contact || '')}"></div>
			<div class="arw-field"><label>${__('Email')}</label>
				<input type="text" data-role="email" data-rowid="${esc(r.id)}" value="${esc(edits.email || '')}"></div>
		</div>
		<button class="arw-addweek" data-rowid="${esc(r.id)}">+ ${__('Save this week\'s entry')} (${page.arw.meta.week_of || ''})</button>
		<div class="arw-weeklog">
			<h4>${__('All filled entries for this customer, most recent first')}</h4>
			<table class="arw-logtable"><thead><tr>
				<th>${__('Week of')}</th><th>${__('Status')}</th><th>${esc(q1)}</th>
				<th>${__('Plan')}</th><th>${__('Notes')}</th><th>${__('Contact')}</th>
			</tr></thead><tbody>${log_rows}</tbody></table>
		</div>
	</div>`;
}

function save_entry(page, rowid, $btn) {
	const row = page.arw.rows.find((r) => r.id === rowid);
	if (!row) return;
	const edits = page.arw.edits[rowid] || {};

	if (!edits.status) {
		frappe.msgprint({
			title: __('Status required'),
			message: __('Pick a status before saving this week\'s entry.'),
			indicator: 'orange',
		});
		return;
	}

	$btn.prop('disabled', true);
	page.main.find('#arw-savemsg').text(__('Saving…'));

	frappe.call({
		method: ARW_METHOD + 'add_ar_weekly_entry',
		args: {
			customer: row.customer,
			ledger: row.ledger,
			status: edits.status,
			qa: edits.qa || '',
			plan: edits.plan || '',
			notes: edits.notes || '',
			contact: edits.contact || '',
			email: edits.email || '',
			need_three_way_call: edits.need_three_way_call ? 1 : 0,
		},
		callback: function (r) {
			if (!r || !r.message) { $btn.prop('disabled', false); return; }
			delete page.arw.edits[rowid];
			delete page.arw.logs[log_key(row)];   // force a refetch of the history
			page.main.find('#arw-savemsg').text(__('Saved {0}', [r.message.week_of]));
			frappe.show_alert({ message: __('Weekly entry saved'), indicator: 'green' }, 4);
			load(page);
		},
		error: function () {
			$btn.prop('disabled', false);
			page.main.find('#arw-savemsg').text(__('Save failed'));
		},
	});
}
