// Copyright (c) 2026, alltechvirtual.com and contributors
// AP Accountability — the payables twin of the AR Accountability page.
//
// Deliberately the same shape as ar_weekly_review.js: the people who run the AR
// review run this one too, and a second layout to learn would be the main cost
// of having a second page. What changes is the subject and the direction —
// rows are suppliers we owe, the second axis is Company rather than ledger, and
// the questions ask what WE are going to do rather than when THEY will pay.
//
// Tier and amount are never stored; every load recomputes them from Purchase
// Invoice server-side (see ap_weekly_review.py). Saving a week's entry inserts
// an AP Weekly Entry and never overwrites an earlier one, which is what gives
// the per-supplier history at the bottom of an expanded row.

const APW_METHOD = 'cannabis_management.credit_and_ar.page.ap_weekly_review.ap_weekly_review.';
const APW_ALL = '__all__';

const APW_TIER_DEF = {
	upcoming: { label: 'Upcoming', full: 'Upcoming — Not Yet Due',
		desc: 'On agreed terms. Nothing to chase; confirm it is scheduled.' },
	level1: { label: 'Level 1', full: 'Past Due Level 1 (0–30)',
		desc: 'We are late. Supplier goodwill is the thing at risk here.',
		q1: 'Why did this go past due?', signoff: true },
	level2: { label: 'Level 2', full: 'Past Due Level 2 (30–60)',
		desc: 'Supply risk — expect credit holds or a demand for COD.',
		q1: 'What is going on?', signoff: true },
	level3: { label: 'Level 3', full: 'Past Due Level 3 (60+)',
		desc: 'Account likely on hold. Collections exposure.',
		q1: 'What is going on?', signoff: true },
};
const APW_TIER_ORDER = ['upcoming', 'level1', 'level2', 'level3'];
const APW_STATUS_ORDER = ['Scheduled On Time', 'Paying Immediately', 'Payment Scheduled',
	'Awaiting Approval', 'Disputed - Need Reconciliation', 'Short On Funds'];
const APW_STATUS_CLASS = {
	'Scheduled On Time': 's-pay',
	'Paying Immediately': 's-pay',
	'Payment Scheduled': 's-pay',
	'Awaiting Approval': 's-recon',
	'Disputed - Need Reconciliation': 's-recon',
	'Short On Funds': 's-dodge',
};
const APW_STATUS_DEF = {
	none: { full: 'No Status Set', desc: 'Needs a status this week.' },
	'Scheduled On Time': { full: 'Scheduled On Time', desc: '' },
	'Paying Immediately': { full: 'Paying Immediately', desc: '' },
	'Payment Scheduled': { full: 'Payment Scheduled', desc: '' },
	'Awaiting Approval': { full: 'Awaiting Approval', desc: '' },
	'Disputed - Need Reconciliation': { full: 'Disputed — Need Reconciliation', desc: '' },
	'Short On Funds': { full: 'Short On Funds', desc: 'Cannot be funded yet. Finance needs to see these.' },
};

frappe.pages['ap-weekly-review'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('AP Accountability'),
		single_column: true,
	});
	wrapper.page = page;

	page.apw = {
		rows: [],
		meta: {},
		open: {},          // row id -> expanded?
		logs: {},          // "supplier|company" -> log rows (lazy loaded)
		edits: {},         // row id -> unsaved form values
		ui: { mode: 'tier', company: APW_ALL, search: '' },
	};

	page.main.html(`
		<div class="apw-root">
			<div class="apw-head">
				<div>
					<div class="apw-title">${__('Accounts Payable — Weekly Review')}</div>
					<div class="apw-sub" id="apw-sub">${__('Loading…')}</div>
				</div>
				<div style="display:flex;align-items:center;">
					<span class="apw-savemsg" id="apw-savemsg"></span>
					<button class="btn btn-default btn-sm" id="apw-excel" style="margin-right:6px;">${__('Export to Excel')}</button>
					<button class="btn btn-default btn-sm" id="apw-csv" style="margin-right:6px;">${__('Export to CSV')}</button>
					<button class="btn btn-default btn-sm" id="apw-print" style="margin-right:6px;">${__('Print')}</button>
					<button class="btn btn-default btn-sm" id="apw-refresh">${__('Refresh')}</button>
				</div>
			</div>

			<div class="apw-kpis" id="apw-kpis"></div>

			<div class="apw-seclabel">${__('Group by')}</div>
			<div class="apw-seg" id="apw-modeseg">
				<button data-mode="tier" class="on">${__('By how late')}</button>
				<button data-mode="status">${__('By status')}</button>
			</div>

			<div class="apw-toolbar">
				<input class="apw-search" id="apw-search" type="text" placeholder="${__('Search supplier…')}">
				<div class="apw-seg" id="apw-companyseg"></div>
				<div class="apw-spacer"></div>
				<span class="apw-count" id="apw-count"></span>
			</div>

			<div id="apw-groups">
				<div class="apw-loading">${__('Loading payables…')}</div>
			</div>

			<div class="apw-foot">
				${__('One row per supplier per company, because each entity pays its own bills. Scheduled and past-due balances are shown separately since only one of them needs chasing. Inter-company bills are excluded — that is money the group owes itself. "Save this week\'s entry" adds a new dated entry without erasing earlier ones.')}
			</div>
		</div>
	`);

	bind_events(page);
	load(page);
};

function bind_events(page) {
	page.main.find('#apw-refresh').on('click', () => load(page));
	page.main.find('#apw-print').on('click', () => print_review(page));
	page.main.find('#apw-excel').on('click', () => export_excel(page, 'xlsx'));
	page.main.find('#apw-csv').on('click', () => export_excel(page, 'csv'));

	page.main.find('#apw-modeseg button').on('click', function () {
		page.main.find('#apw-modeseg button').removeClass('on');
		$(this).addClass('on');
		page.apw.ui.mode = $(this).data('mode');
		render(page);
	});

	// The company buttons are built after load, so they are delegated.
	page.main.on('click', '#apw-companyseg button', function () {
		page.main.find('#apw-companyseg button').removeClass('on');
		$(this).addClass('on');
		page.apw.ui.company = String($(this).attr('data-company'));
		render(page);
	});

	page.main.find('#apw-search').on('input', function () {
		page.apw.ui.search = this.value;
		render(page);
	});

	// Row expand / collapse
	page.main.on('click', '.apw-rowline', function () {
		const id = $(this).data('rowid');
		page.apw.open[id] = !page.apw.open[id];
		if (page.apw.open[id]) load_log(page, id);
		render(page);
	});

	// Never let a click inside the editor collapse the row
	page.main.on('click', '.apw-detailwrap', (e) => e.stopPropagation());

	// Track edits so a re-render does not lose typing
	page.main.on('input change', '.apw-detailwrap [data-role]', function () {
		const id = $(this).data('rowid');
		const role = $(this).data('role');
		const edits = (page.apw.edits[id] = page.apw.edits[id] || {});
		edits[role] = this.type === 'checkbox' ? this.checked : this.value;
	});

	page.main.on('click', '.apw-addweek', function (e) {
		e.stopPropagation();
		save_entry(page, $(this).data('rowid'), $(this));
	});
}

function load(page) {
	frappe.call({
		method: APW_METHOD + 'get_ap_weekly_review',
		args: { company: null },
		callback: function (r) {
			if (!r || !r.message) return;
			page.apw.rows = r.message.rows || [];
			page.apw.meta = r.message;
			page.apw.logs = {};
			page.main.find('#apw-sub').text(
				__('One row per supplier per company · inter-company excluded · as of {0}', [r.message.as_of])
			);
			render_company_filter(page);
			render(page);
		},
	});
}

// Companies come from the data, not from a hardcoded list, so an entity with
// nothing outstanding never appears as an empty tab.
function render_company_filter(page) {
	const companies = page.apw.meta.companies || [];
	const esc = frappe.utils.escape_html;
	const chosen = page.apw.ui.company;
	const valid = chosen === APW_ALL || companies.indexOf(chosen) !== -1;
	if (!valid) page.apw.ui.company = APW_ALL;

	const buttons = [`<button data-company="${APW_ALL}" class="${page.apw.ui.company === APW_ALL ? 'on' : ''}">${__('All companies')}</button>`]
		.concat(companies.map((c) =>
			`<button data-company="${esc(c)}" class="${page.apw.ui.company === c ? 'on' : ''}">${esc(c)}</button>`));
	page.main.find('#apw-companyseg').html(buttons.join(''));
}

function log_key(row) { return row.supplier + '|' + row.company; }

function load_log(page, rowid) {
	const row = page.apw.rows.find((r) => r.id === rowid);
	if (!row) return;
	const key = log_key(row);
	if (page.apw.logs[key]) return;            // already fetched
	page.apw.logs[key] = 'loading';
	frappe.call({
		method: APW_METHOD + 'get_ap_weekly_log',
		args: { supplier: row.supplier, company: row.company },
		callback: function (r) {
			page.apw.logs[key] = (r && r.message) || [];
			render(page);
		},
		error: function () {
			// Drop the sentinel so the row shows an empty log (and can retry on
			// the next render) rather than hanging on "Loading…".
			page.apw.logs[key] = [];
			render(page);
		},
	});
}

function fmt_money(n) {
	return '$' + Math.round(n || 0).toLocaleString('en-US');
}

function visible_rows(page) {
	const ui = page.apw.ui;
	const needle = (ui.search || '').toLowerCase();
	return page.apw.rows.filter(function (r) {
		if (ui.company !== APW_ALL && r.company !== ui.company) return false;
		if (needle && (r.supplier_name || r.supplier).toLowerCase().indexOf(needle) === -1) return false;
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
	Object.keys(page.apw.open).forEach(function (id) {
		if (page.apw.open[id]) load_log(page, id);
	});
}

function render_kpis(page) {
	const rows = visible_rows(page);
	const total = rows.reduce((s, r) => s + r.amount, 0);
	const unfiled = rows.filter((r) => !r.current_status);
	const overdue = rows.filter((r) => r.portion === 'overdue');
	const held = rows.reduce((s, r) => s + (r.held_amount || 0), 0);
	const held_rows = rows.filter((r) => (r.held_count || 0) > 0);

	const kpis = [
		{ cls: '', label: __('TOTAL PAYABLE'), value: fmt_money(total),
			sub: rows.length + ' ' + __('rows') },
		{ cls: 'acc-orange', label: __('PAST DUE'),
			value: fmt_money(overdue.reduce((s, r) => s + r.amount, 0)),
			sub: overdue.length + ' ' + __('rows') },
		{ cls: 'acc-blue', label: __('NO STATUS SET'),
			value: fmt_money(unfiled.reduce((s, r) => s + r.amount, 0)),
			sub: unfiled.length + ' ' + __('rows') },
		{ cls: 'acc-green', label: __('ON HOLD'), value: fmt_money(held),
			sub: held_rows.length + ' ' + __('suppliers held deliberately') },
	];

	page.main.find('#apw-kpis').html(kpis.map((k) => `
		<div class="apw-kpi ${k.cls}">
			<div class="apw-kpi-label">${k.label}</div>
			<div class="apw-kpi-value">${k.value}</div>
			<div class="apw-kpi-sub">${k.sub}</div>
		</div>`).join(''));
}

function render_groups(page) {
	const pool = visible_rows(page);
	const by_tier = page.apw.ui.mode === 'tier';
	const keys = by_tier ? APW_TIER_ORDER : ['none'].concat(APW_STATUS_ORDER);
	const $wrap = page.main.find('#apw-groups').empty();

	let shown = 0, amt_shown = 0;

	keys.forEach(function (key) {
		const def = by_tier ? APW_TIER_DEF[key] : APW_STATUS_DEF[key];
		const rows = pool.filter((r) => by_tier
			? r.tier === key
			: (key === 'none' ? !r.current_status : r.current_status === key));
		rows.sort((a, b) => b.amount - a.amount);

		shown += rows.length;
		const amt = rows.reduce((s, r) => s + r.amount, 0);
		amt_shown += amt;

		const $box = $(`<div class="apw-box ${by_tier ? 'tier-' + key : ''}"></div>`);
		$box.append(`
			<div class="apw-boxhead">
				<div class="apw-titlerow">
					<div>
						<div class="apw-name">${frappe.utils.escape_html(def.full)}</div>
						${def.desc ? `<div class="apw-desc">${frappe.utils.escape_html(def.desc)}</div>` : ''}
					</div>
					<div class="apw-meta">
						<span class="apw-cnt">${rows.length} ${rows.length === 1 ? __('row') : __('rows')}</span>${fmt_money(amt)}
					</div>
				</div>
			</div>`);

		if (!rows.length) {
			$box.append(`<div class="apw-empty">${__('No suppliers in this group right now.')}</div>`);
		} else {
			$box.append(build_table(page, rows, by_tier));
		}
		$wrap.append($box);
	});

	page.main.find('#apw-count').text(
		shown + ' ' + (shown === 1 ? __('row') : __('rows')) + ' · ' + fmt_money(amt_shown) + ' ' + __('total')
	);
}

function build_table(page, rows, by_tier) {
	const cols = 7;   // arrow + supplier + (level|status) + amount + aging + notes
	let html = `<table class="apw-rows"><thead><tr>
			<th style="width:22px"></th>
			<th>${__('Supplier')}</th>
			${by_tier ? '' : `<th>${__('Level')}</th>`}
			<th>${__('Amount')}</th>
			<th>${__('Worst aging')}</th>
			${by_tier ? `<th>${__('Status')}</th>` : ''}
			<th>${__('Latest note')}</th>
		</tr></thead><tbody>`;

	rows.forEach(function (r) {
		const open = !!page.apw.open[r.id];
		const status_html = r.current_status
			? `<span class="apw-statuschip ${APW_STATUS_CLASS[r.current_status] || ''}">${frappe.utils.escape_html(r.current_status)}</span>`
			: `<span class="apw-statuschip">${__('No status yet')}</span>`;
		const held = (r.held_count || 0)
			? ` · <b>${r.held_count} ${__('on hold')}</b>` : '';

		html += `<tr class="apw-rowline${open ? ' open' : ''}" data-rowid="${frappe.utils.escape_html(r.id)}">
			<td><span class="apw-arrow">▸</span></td>
			<td>
				<div class="apw-cust">${frappe.utils.escape_html(r.supplier_name || r.supplier)}</div>
				<div class="apw-ledgertag">${frappe.utils.escape_html(r.company)} · ${r.portion === 'upcoming' ? __('scheduled') : __('past due')} · ${r.invoice_count} ${__('bills')}${held}</div>
			</td>
			${by_tier ? '' : `<td><span class="apw-tierchip ${r.tier}">${APW_TIER_DEF[r.tier].label}</span></td>`}
			<td class="apw-amt">${fmt_money(r.amount)}</td>
			<td><span class="apw-days">${frappe.utils.escape_html(r.days)}</span></td>
			${by_tier ? `<td>${status_html}</td>` : ''}
			<td class="apw-notes">${r.latest_note ? frappe.utils.escape_html(r.latest_note) : '—'}</td>
		</tr>`;

		if (open) {
			html += `<tr class="apw-detail"><td colspan="${cols}">${detail_html(page, r)}</td></tr>`;
		}
	});

	return html + '</tbody></table>';
}

function detail_html(page, r) {
	const def = APW_TIER_DEF[r.tier];
	const edits = page.apw.edits[r.id] || {};
	const esc = frappe.utils.escape_html;

	const bd = r.breakdown.map((b) =>
		`<div class="apw-bdchip">${esc(b.label)} &middot; <b>${fmt_money(b.amount)}</b></div>`).join('');
	const extra = [];
	if (r.oldest_due) extra.push(`<div class="apw-bdchip">${__('Oldest due')} &middot; <b>${esc(r.oldest_due)}</b></div>`);
	if (r.held_count) extra.push(`<div class="apw-bdchip">${__('On hold')} &middot; <b>${fmt_money(r.held_amount)}</b> (${r.held_count})</div>`);

	const statuses = r.statuses || [];
	const opts = ['<option value="">— ' + __('pick status') + ' —</option>'].concat(
		statuses.map((s) => `<option value="${esc(s)}"${edits.status === s ? ' selected' : ''}>${esc(s)}</option>`)
	).join('');

	const log = page.apw.logs[log_key(r)];
	let log_rows;
	if (log === 'loading' || log === undefined) {
		log_rows = `<tr><td class="apw-emptylog" colspan="6">${__('Loading…')}</td></tr>`;
	} else if (!log.length) {
		log_rows = `<tr><td class="apw-emptylog" colspan="6">${__('No weekly entries yet — this will be the first.')}</td></tr>`;
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

	return `<div class="apw-detailwrap">
		<div class="apw-breakdown">${bd}${extra.join('')}</div>
		<div class="apw-qarow">
			<div class="apw-field">
				<label>${__('This week\'s status')}</label>
				<select data-role="status" data-rowid="${esc(r.id)}">${opts}</select>
			</div>
			${def.signoff ? `<div class="apw-field"><label>&nbsp;</label>
				<div class="apw-flagrow">
					<input type="checkbox" data-role="need_finance_signoff" data-rowid="${esc(r.id)}" ${edits.need_finance_signoff ? 'checked' : ''}>
					${__('Need sign-off from finance')}
				</div></div>` : '<div></div>'}
			<div class="apw-field full"><label>${esc(q1)}</label>
				<textarea data-role="qa" data-rowid="${esc(r.id)}">${esc(edits.qa || '')}</textarea></div>
			<div class="apw-field"><label>${__('When will this be paid?')}</label>
				<textarea data-role="plan" data-rowid="${esc(r.id)}">${esc(edits.plan || '')}</textarea></div>
			<div class="apw-field"><label>${__('Notes')}</label>
				<textarea data-role="notes" data-rowid="${esc(r.id)}">${esc(edits.notes || '')}</textarea></div>
			<div class="apw-field"><label>${__('Contact info')}</label>
				<input type="text" data-role="contact" data-rowid="${esc(r.id)}" value="${esc(edits.contact || '')}"></div>
			<div class="apw-field"><label>${__('Email')}</label>
				<input type="text" data-role="email" data-rowid="${esc(r.id)}" value="${esc(edits.email || '')}"></div>
		</div>
		<button class="apw-addweek" data-rowid="${esc(r.id)}">+ ${__('Save this week\'s entry')} (${page.apw.meta.week_of || ''})</button>
		<div class="apw-weeklog">
			<h4>${__('All filled entries for this supplier, most recent first')}</h4>
			<table class="apw-logtable"><thead><tr>
				<th>${__('Week of')}</th><th>${__('Status')}</th><th>${esc(q1)}</th>
				<th>${__('When paid')}</th><th>${__('Notes')}</th><th>${__('Contact')}</th>
			</tr></thead><tbody>${log_rows}</tbody></table>
		</div>
	</div>`;
}

function save_entry(page, rowid, $btn) {
	const row = page.apw.rows.find((r) => r.id === rowid);
	if (!row) return;
	const edits = page.apw.edits[rowid] || {};

	if (!edits.status) {
		frappe.msgprint({
			title: __('Status required'),
			message: __('Pick a status before saving this week\'s entry.'),
			indicator: 'orange',
		});
		return;
	}

	$btn.prop('disabled', true);
	page.main.find('#apw-savemsg').text(__('Saving…'));

	frappe.call({
		method: APW_METHOD + 'add_ap_weekly_entry',
		args: {
			supplier: row.supplier,
			company: row.company,
			status: edits.status,
			qa: edits.qa || '',
			plan: edits.plan || '',
			notes: edits.notes || '',
			contact: edits.contact || '',
			email: edits.email || '',
			need_finance_signoff: edits.need_finance_signoff ? 1 : 0,
		},
		callback: function (r) {
			if (!r || !r.message) { $btn.prop('disabled', false); return; }
			delete page.apw.edits[rowid];
			delete page.apw.logs[log_key(row)];   // force a refetch of the history
			page.main.find('#apw-savemsg').text(__('Saved {0}', [r.message.week_of]));
			frappe.show_alert({ message: __('Weekly entry saved'), indicator: 'green' }, 4);
			load(page);
		},
		error: function () {
			$btn.prop('disabled', false);
			page.main.find('#apw-savemsg').text(__('Save failed'));
		},
	});
}

// Export every company, not just the one on screen: taking this to Excel is
// normally about pivoting across entities, and a filtered export that quietly
// drops rows is worse than one more column to filter on. The workbook is built
// server-side so the figures are the same ones the page was given.
function export_excel(page, format) {
	if (!page.apw.rows.length) {
		frappe.msgprint(__('Nothing to export yet — wait for the review to load.'));
		return;
	}
	// CSV carries the payables grid alone; the aging breakdown and the weekly
	// log are extra sheets, which a CSV cannot hold.
	frappe.dom.freeze(format === 'csv' ? __('Building CSV…') : __('Building workbook…'));
	open_url_post(frappe.request.url, {
		cmd: APW_METHOD + (format === 'csv' ? 'export_csv' : 'export_xlsx'),
	});
	setTimeout(() => frappe.dom.unfreeze(), 3000);
}


// Print the whole review: every company, every group, every row, full notes.
// Ignores the search box and company toggle; keeps the current "Group by" mode.
// Rendered into a fresh window so Desk chrome and the interactive editor stay out.
function print_review(page) {
	if (!page.apw.rows.length) {
		frappe.msgprint(__('Nothing to print yet — wait for the review to load.'));
		return;
	}
	const esc = frappe.utils.escape_html;
	const by_tier = page.apw.ui.mode === 'tier';
	const keys = by_tier ? APW_TIER_ORDER : ['none'].concat(APW_STATUS_ORDER);
	const companies = page.apw.meta.companies || [];

	const company_html = companies.map(function (company) {
		const pool = page.apw.rows.filter((r) => r.company === company);
		if (!pool.length) return '';
		const total = pool.reduce((s, r) => s + r.amount, 0);
		const unfiled = pool.filter((r) => !r.current_status);

		const groups = keys.map(function (key) {
			const def = by_tier ? APW_TIER_DEF[key] : APW_STATUS_DEF[key];
			const rows = pool.filter((r) => by_tier
				? r.tier === key
				: (key === 'none' ? !r.current_status : r.current_status === key));
			rows.sort((a, b) => b.amount - a.amount);
			const amt = rows.reduce((s, r) => s + r.amount, 0);

			const body = rows.length ? `<table><thead><tr>
					<th>${__('Supplier')}</th>
					${by_tier ? '' : `<th>${__('Level')}</th>`}
					<th class="num">${__('Amount')}</th>
					<th>${__('Worst aging')}</th>
					${by_tier ? `<th>${__('Status')}</th>` : ''}
					<th>${__('Latest note')}</th>
				</tr></thead><tbody>${rows.map((r) => `<tr>
					<td><b>${esc(r.supplier_name || r.supplier)}</b><div class="dim">${r.portion === 'upcoming' ? __('scheduled') : __('past due')} · ${r.invoice_count} ${__('bills')}${r.held_count ? ' · ' + r.held_count + ' ' + __('on hold') : ''}</div></td>
					${by_tier ? '' : `<td>${APW_TIER_DEF[r.tier].label}</td>`}
					<td class="num">${fmt_money(r.amount)}</td>
					<td>${esc(r.days)}</td>
					${by_tier ? `<td>${r.current_status ? esc(r.current_status) : '<span class="dim">' + __('No status yet') + '</span>'}</td>` : ''}
					<td>${r.latest_note ? esc(r.latest_note) : '—'}</td>
				</tr>`).join('')}</tbody></table>`
				: `<div class="dim empty">${__('No suppliers in this group.')}</div>`;

			return `<div class="group ${by_tier ? 'tier-' + key : ''}">
				<div class="ghead"><span><b>${esc(def.full)}</b>${def.desc ? ` <span class="dim">— ${esc(def.desc)}</span>` : ''}</span>
				<span><span class="dim">${rows.length} ${rows.length === 1 ? __('row') : __('rows')}</span> <b>${fmt_money(amt)}</b></span></div>
				${body}</div>`;
		}).join('');

		return `<section>
			<h2>${esc(company)} <span class="dim">· ${fmt_money(total)} ${__('payable')} · ${pool.length} ${__('rows')} · ${unfiled.length} ${__('with no status')}</span></h2>
			${groups}</section>`;
	}).join('');

	const html = `<!doctype html><html><head><meta charset="utf-8">
		<title>${__('AP Accountability')} — ${esc(page.apw.meta.as_of || '')}</title>
		<style>
			body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1f2430;font-size:11.5px;margin:24px;}
			h1{font-size:17px;margin:0;} h2{font-size:14px;margin:22px 0 8px;border-bottom:2px solid #1f2430;padding-bottom:4px;}
			.dim{color:#767b8a;font-weight:normal;}
			.group{border:1px solid #ddd;border-left:5px solid #0f6d66;margin-bottom:12px;break-inside:auto;}
			.tier-upcoming{border-left-color:#2e7d5b;} .tier-level1{border-left-color:#b23b3b;}
			.tier-level2{border-left-color:#c47b1f;} .tier-level3{border-left-color:#7a2233;}
			.ghead{display:flex;justify-content:space-between;gap:10px;padding:7px 10px;background:#eaf4f3;}
			table{width:100%;border-collapse:collapse;}
			th{text-align:left;font-size:10px;color:#767b8a;padding:5px 10px;border-bottom:1px solid #ddd;}
			td{padding:5px 10px;border-bottom:1px solid #eee;vertical-align:top;}
			tr{break-inside:avoid;} thead{display:table-header-group;}
			.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;}
			.empty{padding:8px 10px;}
			@page{size:landscape;margin:12mm;}
			@media print{body{margin:0;-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
		</style></head><body>
		<h1>${__('Accounts Payable — Weekly Review')}</h1>
		<div class="dim">${__('As of {0}', [esc(page.apw.meta.as_of || '')])} · ${__('Grouped')} ${by_tier ? __('by how late') : __('by status')} · ${__('Inter-company excluded')} · ${__('Printed by {0}', [esc(frappe.session.user_fullname || frappe.session.user)])}</div>
		${company_html}
		</body></html>`;

	const w = window.open('', '_blank');
	if (!w) {
		frappe.msgprint(__('Allow pop-ups for this site to print.'));
		return;
	}
	w.document.open();
	w.document.write(html);
	w.document.close();
	w.focus();
	setTimeout(() => w.print(), 300);
}
