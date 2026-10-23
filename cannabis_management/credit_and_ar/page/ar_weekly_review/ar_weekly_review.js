// Copyright (c) 2026, alltechvirtual.com and contributors
// AR Accountability (formerly AR Weekly Review) — port of the ar_weekly_review.html mockup onto a Desk page.
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
	'Client Is Dodging Us', 'Need Reconciliation', 'WIP At Lab', 'Pending Pickup',
	'Payment Plan', 'No Longer In Business'];
const ARW_STATUS_CLASS = {
	'Will Pay On Time': 's-pay',
	'Will Pay Immediately': 's-pay',
	'Client Is Dodging Us': 's-dodge',
	'Need Reconciliation': 's-recon',
	'WIP At Lab': 's-wip',
	'Pending Pickup': 's-pickup',
	'Payment Plan': 's-plan',
	'No Longer In Business': 's-closed',
};
const ARW_STATUS_DEF = {
	none: { full: 'No Status Set', desc: 'Needs a status this week.' },
	'Will Pay On Time': { full: 'Will Pay On Time', desc: '' },
	'Will Pay Immediately': { full: 'Will Pay Immediately', desc: '' },
	'Client Is Dodging Us': { full: 'Client Is Dodging Us', desc: '' },
	'Need Reconciliation': { full: 'Need Reconciliation', desc: '' },
	'WIP At Lab': { full: 'WIP At Lab', desc: '' },
	'Pending Pickup': { full: 'Pending Pickup', desc: '' },
	'Payment Plan': { full: 'Payment Plan', desc: '' },
	'No Longer In Business': { full: 'No Longer In Business', desc: '' },
};

// Customer dropdowns: Recon Status / Onboarding / Company Made Contact are the AR
// Dashboard's columns and Segment is Categorized AR's. They save through those
// pages' own endpoints, so the values and who may change them are the same
// everywhere. (arw_ prefix: desk page scripts share one window.)
const ARW_ARD_METHOD = 'cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.';
const ARW_ARL_METHOD = 'cannabis_management.cannabis_management.page.ar_legacy.ar_legacy.';
const ARW_FLAG_FIELDS = [['onboarding', 'Onboarding'], ['company_made_contact', 'Company Made Contact']];
// The AR Dashboard's colours for its five built-in recon statuses.
const ARW_RECON_COLORS = {
	'Reconciled collecting money': ['#dcfce7', '#15803d', '#16a34a'],
	'Reconciled trouble collecting money': ['#fef3c7', '#92400e', '#d97706'],
	'Unreconciled': ['#fee2e2', '#b91c1c', '#dc2626'],
	'Dispute': ['#ede9fe', '#5b21b6', '#7c3aed'],
	'Adjustment': ['#dbeafe', '#1e40af', '#3b82f6'],
};

function arw_cell_style(bg, fg, border) {
	return ` style="background-color:${bg};color:${fg};border-color:${border || fg};"`;
}

function arw_recon_style(page, status) {
	if (!status) return '';
	const own = (page.arw.meta.recon_statuses || []).find((s) => s.value === status);
	if (own && own.color) return arw_cell_style(own.color + '1f', own.color, own.color);
	const c = ARW_RECON_COLORS[status];
	return c ? arw_cell_style(c[0], c[1], c[2]) : '';
}

function arw_flag_style(value) {
	if (value === 'Yes') return arw_cell_style('#d9ead3', '#274e13', '#93c47d');
	if (value === 'No') return arw_cell_style('#fce8e6', '#cc0000', '#e6b8b7');
	return '';
}

function arw_segment_color(page, seg) {
	return seg ? ((page.arw.meta.segment_colors || {})[seg] || '#6d28d9') : '';
}

function arw_segment_style(page, seg) {
	const c = arw_segment_color(page, seg);
	return c ? arw_cell_style(c + '1f', c, c) : '';
}

// Reach Out Status: a Customer field, blank read as "Haven't Reached Out".
const ARW_NOT_REACHED = "Haven't Reached Out";
const ARW_REACH_OUT_DEF = {
	"Haven't Reached Out": { color: '#d97706', desc: 'Nobody has reached out to this account yet.' },
	'Ready to reach out': { color: '#2563eb', desc: '' },
	'Ready to reach out - Sales Rep': { color: '#7c3aed', desc: '' },
	'Find Info': { color: '#0891b2', desc: 'Contact or account info has to be found before anyone can reach out.' },
	'Reached Out': { color: '#16a34a', desc: '' },
};

function arw_reach_out_style(value) {
	const d = ARW_REACH_OUT_DEF[value || ARW_NOT_REACHED];
	return d ? arw_cell_style(d.color + '1f', d.color, d.color) : '';
}

// One dropdown cell, or a read-only value for someone without edit rights.
function arw_select(kind, field, customer, value, options, style, editable) {
	const esc = frappe.utils.escape_html;
	if (!editable) {
		const label = (options.find((o) => o[0] === value) || [value, value || '—'])[1];
		return `<span class="arw-inline-ro"${style}>${esc(label || '—')}</span>`;
	}
	const opts = options.map((o) =>
		`<option value="${esc(o[0])}"${o[0] === value ? ' selected' : ''}>${esc(o[1])}</option>`).join('');
	return `<select class="arw-inline" data-kind="${kind}" data-field="${esc(field)}"
		data-customer="${esc(customer)}" data-current="${esc(value || '')}"${style}>${opts}</select>`;
}

function arw_customer_cells(page, r) {
	const meta = page.arw.meta;
	const recon_opts = [['', '—']].concat((meta.recon_statuses || []).map((s) => [s.value, s.label || s.value]));
	const yes_no = [['', '—'], ['Yes', 'Yes'], ['No', 'No']];
	const seg_opts = [['', meta.unassigned_label || __('Unassigned')]].concat((meta.segments || []).map((s) => [s, s]));
	return `
		<td class="arw-cf">${arw_select('recon', 'recon_status', r.customer, r.recon_status, recon_opts,
			arw_recon_style(page, r.recon_status), meta.can_edit_recon)}</td>
		${ARW_FLAG_FIELDS.map((f) => `<td class="arw-cf">${arw_select('flag', f[0], r.customer, r[f[0]], yes_no,
			arw_flag_style(r[f[0]]), meta.can_edit_recon)}</td>`).join('')}
		<td class="arw-cf">${arw_select('segment', 'segment', r.customer, r.segment, seg_opts,
			arw_segment_style(page, r.segment), meta.can_edit_segment)}</td>
		<td class="arw-cf">${arw_select('reach_out', 'reach_out', r.customer, r.reach_out || ARW_NOT_REACHED,
			(meta.reach_out_statuses || [ARW_NOT_REACHED]).map((s) => [s, s]),
			arw_reach_out_style(r.reach_out), meta.can_edit_reach_out)}</td>`;
}

// Save one dropdown through its home page's endpoint, then update every row of
// that customer (it can have on-terms and overdue rows in both ledgers).
function arw_save_customer_field(page, $sel) {
	const kind = $sel.attr('data-kind');
	const field = $sel.attr('data-field');
	const customer = $sel.attr('data-customer');
	const value = $sel.val();
	const old = $sel.attr('data-current') || '';
	let method, args, label;
	if (kind === 'recon') {
		method = ARW_ARD_METHOD + 'update_recon_status';
		args = { party: customer, status: value };
		label = __('Recon Status');
	} else if (kind === 'flag') {
		method = ARW_ARD_METHOD + 'update_ar_flag';
		args = { party: customer, field: field, value: value };
		label = __((ARW_FLAG_FIELDS.find((f) => f[0] === field) || [field, field])[1]);
	} else if (kind === 'reach_out') {
		method = ARW_ARL_METHOD + 'set_reach_out_status';
		args = { customer: customer, status: value };
		label = __('Reach Out Status');
	} else {
		method = ARW_ARL_METHOD + 'set_segment';
		args = { customer: customer, segment: value };
		label = __('Segment');
	}
	$sel.prop('disabled', true);
	frappe.call({
		method: method,
		args: args,
		callback: function () {
			page.arw.rows.forEach(function (row) {
				if (row.customer === customer) row[field] = value;
			});
			frappe.show_alert({ message: __('{0} updated for {1}', [label, customer]), indicator: 'green' }, 3);
			render(page);
		},
		error: function () {
			$sel.prop('disabled', false).val(old);
			frappe.show_alert({ message: __('Could not update {0}', [label]), indicator: 'red' }, 5);
		},
	});
}

// The groups for the current "Group by" choice, shared by the page and Print.
function arw_groups(page, pool) {
	const mode = page.arw.ui.mode;
	let groups;
	if (mode === 'owner') {
		const meta = page.arw.meta;
		const keys = [''].concat(meta.segments || []);
		// A segment since disabled can still be on a customer: keep it visible.
		pool.forEach((r) => { if (r.segment && keys.indexOf(r.segment) === -1) keys.push(r.segment); });
		groups = keys.map((k) => ({
			key: k,
			def: { full: k || meta.unassigned_label || __('Unassigned'),
				desc: k ? '' : __('No segment chosen yet in Categorized AR.') },
			cls: 'owner',
			color: arw_segment_color(page, k) || '#9aa0a6',
			rows: pool.filter((r) => (r.segment || '') === k),
		}));
	} else if (mode === 'reach_out') {
		// "Haven't Reached Out" first: that is the pile still to be worked.
		groups = (page.arw.meta.reach_out_statuses || [ARW_NOT_REACHED]).map((k) => ({
			key: k,
			def: { full: k, desc: (ARW_REACH_OUT_DEF[k] || {}).desc || '' },
			cls: 'owner',
			color: (ARW_REACH_OUT_DEF[k] || {}).color || '#9aa0a6',
			rows: pool.filter((r) => (r.reach_out || ARW_NOT_REACHED) === k),
		}));
	} else if (mode === 'status') {
		groups = ['none'].concat(ARW_STATUS_ORDER).map((k) => ({
			key: k, def: ARW_STATUS_DEF[k], cls: '', color: '',
			rows: pool.filter((r) => (k === 'none' ? !r.current_status : r.current_status === k)),
		}));
	} else {
		groups = ARW_TIER_ORDER.map((k) => ({
			key: k, def: ARW_TIER_DEF[k], cls: 'tier-' + k, color: '',
			rows: pool.filter((r) => r.tier === k),
		}));
	}
	groups.forEach((g) => g.rows.sort((a, b) => b.amount - a.amount));
	return groups;
}

frappe.pages['ar-weekly-review'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('AR Accountability'),
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
					<button class="btn btn-default btn-sm" id="arw-excel" style="margin-right:6px;">${__('Export to Excel')}</button>
					<button class="btn btn-default btn-sm" id="arw-csv" style="margin-right:6px;">${__('Export to CSV')}</button>
					<button class="btn btn-default btn-sm" id="arw-print" style="margin-right:6px;">${__('Print')}</button>
					<button class="btn btn-default btn-sm" id="arw-refresh">${__('Refresh')}</button>
				</div>
			</div>

			<div class="arw-kpis" id="arw-kpis"></div>

			<div class="arw-seclabel">${__('Group by')}</div>
			<div class="arw-seg" id="arw-modeseg">
				<button data-mode="tier" class="on">${__('By debt level')}</button>
				<button data-mode="status">${__('By status')}</button>
				<button data-mode="owner">${__('By ownership')}</button>
				<button data-mode="reach_out">${__('By reach out status')}</button>
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
	page.main.find('#arw-print').on('click', () => print_review(page));
	page.main.find('#arw-excel').on('click', () => export_review(page, 'xlsx'));
	page.main.find('#arw-csv').on('click', () => export_review(page, 'csv'));

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

	// Customer dropdowns: a click must not expand the row, a change saves.
	page.main.on('click', '.arw-inline, .arw-inline-ro', (e) => e.stopPropagation());
	page.main.on('change', 'select.arw-inline', function () {
		arw_save_customer_field(page, $(this));
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
	const mode = page.arw.ui.mode;
	const $wrap = page.main.find('#arw-groups').empty();

	let shown = 0, amt_shown = 0;

	arw_groups(page, pool).forEach(function (g) {
		const def = g.def, rows = g.rows;
		shown += rows.length;
		const amt = rows.reduce((s, r) => s + r.amount, 0);
		amt_shown += amt;

		const $box = $(`<div class="arw-box ${g.cls}"${g.color ? ` style="border-left-color:${g.color}"` : ''}></div>`);
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
			$box.append(build_table(page, rows, mode));
		}
		$wrap.append($box);
	});

	page.main.find('#arw-count').text(
		shown + ' ' + (shown === 1 ? __('row') : __('rows')) + ' · ' + fmt_money(amt_shown) + ' ' + __('total')
	);
}

function build_table(page, rows, mode) {
	// Level shows unless the groups already are levels; Status unless they are statuses.
	const show_level = mode !== 'tier';
	const show_status = mode !== 'status';
	const cols = 10 + (show_level ? 1 : 0) + (show_status ? 1 : 0);
	let html = `<div class="arw-tablescroll"><table class="arw-rows"><thead><tr>
			<th style="width:22px"></th>
			<th>${__('Customer')}</th>
			${show_level ? `<th>${__('Level')}</th>` : ''}
			<th>${__('Amount')}</th>
			<th>${__('Worst aging')}</th>
			${show_status ? `<th>${__('Status')}</th>` : ''}
			<th>${__('Recon Status')}</th>
			<th>${__('Onboarding')}</th>
			<th>${__('Company Made Contact')}</th>
			<th>${__('Segment')}</th>
			<th>${__('Reach Out Status')}</th>
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
			${show_level ? `<td><span class="arw-tierchip ${r.tier}">${ARW_TIER_DEF[r.tier].label}</span></td>` : ''}
			<td class="arw-amt">${fmt_money(r.amount)}</td>
			<td><span class="arw-days">${frappe.utils.escape_html(r.days)}</span></td>
			${show_status ? `<td>${status_html}</td>` : ''}
			${arw_customer_cells(page, r)}
			<td class="arw-notes">${r.latest_note ? frappe.utils.escape_html(r.latest_note) : '—'}</td>
		</tr>`;

		if (open) {
			html += `<tr class="arw-detail"><td colspan="${cols}">${detail_html(page, r)}</td></tr>`;
		}
	});

	return html + '</tbody></table></div>';
}

function detail_html(page, r) {
	const def = ARW_TIER_DEF[r.tier];
	const edits = page.arw.edits[r.id] || {};
	const esc = frappe.utils.escape_html;
	// Cents here: a single invoice is where the odd cent actually shows.
	const money2 = (n) => '$' + (n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	// "2026-10-09" -> "Oct 9, 2026", built from the parts so no timezone can shift the day.
	const nice_date = (d) => {
		const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || '');
		return m ? new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('en-US',
			{ month: 'short', day: 'numeric', year: 'numeric' }) : '';
	};

	// Three sections, each under its own coloured title bar: the invoices behind
	// the row, this week's entry, and the entry history.

	// Aging breakdown, one cell per bucket in its tier's colour (in the Invoices bar).
	const bd = r.breakdown.map((b) =>
		`<span class="arw-bdcell tier-${esc(b.tier)}">${esc(b.label)} <b>${fmt_money(b.amount)}</b></span>`).join('');

	// The open invoices that make up this row, oldest due date first. Each aging
	// label belongs to one tier, and the row's breakdown already says which.
	const invs = r.invoices || [];
	const tier_of = {};
	r.breakdown.forEach((b) => { tier_of[b.label] = b.tier; });
	const inv_total = (k) => invs.reduce((s, i) => s + (i[k] || 0), 0);
	const inv_rows = invs.map((i) => `<tr>
			<td class="c-inv"><a href="/app/sales-invoice/${encodeURIComponent(i.name)}" target="_blank">${esc(i.name)}</a></td>
			<td class="c-co">${esc(i.company || '')}</td>
			<td class="c-date">${esc(nice_date(i.posting_date))}</td>
			<td class="c-date">${esc(nice_date(i.due_date))}</td>
			<td class="c-age tier-${esc(tier_of[i.aging] || 'upcoming')}">${esc(i.aging || '')}</td>
			<td class="c-amt c-invd">${money2(i.invoiced)}</td>
			<td class="c-amt c-paid">${money2(i.paid)}</td>
			<td class="c-amt c-out">${money2(i.outstanding)}</td>
		</tr>`).join('');
	const inv_html = `<section class="arw-sec arw-sec-inv">
			<header class="arw-sechead">
				<span class="arw-sectitle">${__('Invoices')} (${invs.length})</span>
				<span class="arw-bdcells">${bd}</span>
			</header>
			${invs.length ? `<div class="arw-secscroll"><table class="arw-sheet"><thead><tr>
				<th class="c-inv">${__('Invoice')}</th><th class="c-co">${__('Company')}</th>
				<th class="c-date">${__('Posted')}</th><th class="c-date">${__('Due')}</th>
				<th class="c-age">${__('Aging')}</th>
				<th class="c-amt c-invd">${__('Invoiced')}</th><th class="c-amt c-paid">${__('Paid')}</th>
				<th class="c-amt c-out">${__('Outstanding')}</th>
			</tr></thead><tbody>${inv_rows}</tbody>
			<tfoot><tr><td colspan="5">${__('Total')}</td>
				<td class="c-amt c-invd">${money2(inv_total('invoiced'))}</td>
				<td class="c-amt c-paid">${money2(inv_total('paid'))}</td>
				<td class="c-amt c-out">${money2(inv_total('outstanding'))}</td></tr></tfoot>
			</table></div>` : `<div class="arw-secempty">${__('No open invoices.')}</div>`}
		</section>`;

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
			<td class="c-week">${esc(nice_date(e.week_of))}</td>
			<td class="c-status ${ARW_STATUS_CLASS[e.status] || ''}">${esc(e.status || '')}</td>
			<td>${esc(e.qa || '')}</td>
			<td>${esc(e.plan || '')}</td>
			<td>${esc(e.notes || '')}</td>
			<td>${esc(e.contact || '')}${e.email ? ' · ' + esc(e.email) : ''}</td>
		</tr>`).join('');
	}
	const log_count = Array.isArray(log) ? log.length : 0;

	const q1 = def.q1 || __('What is going on?');

	return `<div class="arw-detailwrap">
		${inv_html}
		<section class="arw-sec arw-sec-entry">
			<header class="arw-sechead">
				<span class="arw-sectitle">${__('This week\'s entry')}</span>
				<span class="arw-secmeta">${__('Week of')} ${esc(nice_date(page.arw.meta.week_of))}</span>
			</header>
			<div class="arw-secbody">
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
			</div>
		</section>
		<section class="arw-sec arw-sec-log">
			<header class="arw-sechead">
				<span class="arw-sectitle">${__('Entry history')}${log_count ? ` (${log_count})` : ''}</span>
				<span class="arw-secmeta">${__('Most recent first')}</span>
			</header>
			<div class="arw-secscroll"><table class="arw-sheet arw-logsheet"><thead><tr>
				<th>${__('Week of')}</th><th>${__('Status')}</th><th>${esc(q1)}</th>
				<th>${__('Plan')}</th><th>${__('Notes')}</th><th>${__('Contact')}</th>
			</tr></thead><tbody>${log_rows}</tbody></table></div>
		</section>
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

// Both ledgers go into the file, not just the one on screen: the Ledger column
// is there to filter on, and an export that dropped half the book would be a
// worse failure than one more column. CSV carries the receivables grid alone --
// the aging breakdown and the weekly log are extra sheets a CSV cannot hold.
function export_review(page, format) {
	if (!page.arw.rows.length) {
		frappe.msgprint(__('Nothing to export yet — wait for the review to load.'));
		return;
	}
	frappe.dom.freeze(format === 'csv' ? __('Building CSV…') : __('Building workbook…'));
	open_url_post(frappe.request.url, {
		cmd: ARW_METHOD + (format === 'csv' ? 'export_csv' : 'export_xlsx'),
	});
	setTimeout(() => frappe.dom.unfreeze(), 3000);
}


// Print the whole review: both ledgers, every group, every row, full notes.
// Ignores the search box and ledger toggle; keeps the current "Group by" mode.
// Rendered into a fresh window so Desk chrome and the interactive editor stay out.
function print_review(page) {
	if (!page.arw.rows.length) {
		frappe.msgprint(__('Nothing to print yet — wait for the review to load.'));
		return;
	}
	const esc = frappe.utils.escape_html;
	const mode = page.arw.ui.mode;
	const by_tier = mode === 'tier';
	const show_status = mode !== 'status';

	const ledger_html = ['New AR', 'Legacy AR'].map(function (ledger) {
		const pool = page.arw.rows.filter((r) => r.ledger === ledger);
		const total = pool.reduce((s, r) => s + r.amount, 0);
		const unfiled = pool.filter((r) => !r.current_status);

		const groups = arw_groups(page, pool).map(function (g) {
			const def = g.def, rows = g.rows;
			const amt = rows.reduce((s, r) => s + r.amount, 0);

			const body = rows.length ? `<table><thead><tr>
					<th>${__('Customer')}</th>
					${by_tier ? '' : `<th>${__('Level')}</th>`}
					<th class="num">${__('Amount')}</th>
					<th>${__('Worst aging')}</th>
					${show_status ? `<th>${__('Status')}</th>` : ''}
					<th>${__('Segment')}</th>
					<th>${__('Reach Out Status')}</th>
					<th>${__('Latest note')}</th>
				</tr></thead><tbody>${rows.map((r) => `<tr>
					<td><b>${esc(r.customer)}</b><div class="dim">${r.portion === 'upcoming' ? __('on terms') : __('overdue')} · ${r.invoice_count} ${__('inv')}</div></td>
					${by_tier ? '' : `<td>${ARW_TIER_DEF[r.tier].label}</td>`}
					<td class="num">${fmt_money(r.amount)}</td>
					<td>${esc(r.days)}</td>
					${show_status ? `<td>${r.current_status ? esc(r.current_status) : '<span class="dim">' + __('No status yet') + '</span>'}</td>` : ''}
					<td>${esc(r.segment || page.arw.meta.unassigned_label || __('Unassigned'))}</td>
					<td>${esc(r.reach_out || ARW_NOT_REACHED)}</td>
					<td>${r.latest_note ? esc(r.latest_note) : '—'}</td>
				</tr>`).join('')}</tbody></table>`
				: `<div class="dim empty">${__('No accounts in this group.')}</div>`;

			return `<div class="group ${g.cls}"${g.color ? ` style="border-left-color:${g.color}"` : ''}>
				<div class="ghead"><span><b>${esc(def.full)}</b>${def.desc ? ` <span class="dim">— ${esc(def.desc)}</span>` : ''}</span>
				<span><span class="dim">${rows.length} ${rows.length === 1 ? __('row') : __('rows')}</span> <b>${fmt_money(amt)}</b></span></div>
				${body}</div>`;
		}).join('');

		return `<section>
			<h2>${esc(ledger)} <span class="dim">· ${fmt_money(total)} ${__('outstanding')} · ${pool.length} ${__('rows')} · ${unfiled.length} ${__('with no status')}</span></h2>
			${groups}</section>`;
	}).join('');

	const html = `<!doctype html><html><head><meta charset="utf-8">
		<title>${__('AR Accountability')} — ${esc(page.arw.meta.as_of || '')}</title>
		<style>
			body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#1f2430;font-size:11.5px;margin:24px;}
			h1{font-size:17px;margin:0;} h2{font-size:14px;margin:22px 0 8px;border-bottom:2px solid #1f2430;padding-bottom:4px;}
			.dim{color:#767b8a;font-weight:normal;}
			.group{border:1px solid #ddd;border-left:5px solid #6b46c1;margin-bottom:12px;break-inside:auto;}
			.tier-upcoming{border-left-color:#2e7d5b;} .tier-level1{border-left-color:#b23b3b;}
			.tier-level2{border-left-color:#c47b1f;} .tier-level3{border-left-color:#7a2233;}
			.ghead{display:flex;justify-content:space-between;gap:10px;padding:7px 10px;background:#f4f2f9;}
			table{width:100%;border-collapse:collapse;}
			th{text-align:left;font-size:10px;color:#767b8a;padding:5px 10px;border-bottom:1px solid #ddd;}
			td{padding:5px 10px;border-bottom:1px solid #eee;vertical-align:top;}
			tr{break-inside:avoid;} thead{display:table-header-group;}
			.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;}
			.empty{padding:8px 10px;}
			@page{size:landscape;margin:12mm;}
			@media print{body{margin:0;-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
		</style></head><body>
		<h1>${__('Accounts Receivable — Weekly Review')}</h1>
		<div class="dim">${__('As of {0}', [esc(page.arw.meta.as_of || '')])} · ${__('Grouped')} ${{ tier: __('by debt level'), status: __('by status'), owner: __('by ownership'), reach_out: __('by reach out status') }[mode]} · ${__('Printed by {0}', [esc(frappe.session.user_fullname || frappe.session.user)])}</div>
		${ledger_html}
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
