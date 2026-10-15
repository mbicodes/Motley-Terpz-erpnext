// Copyright (c) 2026, alltechvirtual.com and contributors
// AR Hub — one receivables grid doing the work of AR Dashboard, Categorized AR
// and AR Accountability. One row per customer:
//   * AR Dashboard's balances, on-terms and overdue aging, Recon Status, the
//     two Yes/No flags, Notebox and New AR;
//   * Categorized AR's segment;
//   * AR Accountability's debt level, weekly status and latest note.
// Click a customer for its invoices (open and paid), the notebox, this week's
// entry and the entry history.
//
// Every save goes through the endpoint of the page that owns the field, with
// that page's permission check (see ar_hub.py). The weekly review columns and
// form only appear for AR Accountability's role.
//
// Wrapped in its own scope: desk page scripts share one window.

(function () {
const ARH_METHOD = 'cannabis_management.credit_and_ar.page.ar_hub.ar_hub.';
const ARD_METHOD = 'cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.';
const ARL_METHOD = 'cannabis_management.cannabis_management.page.ar_legacy.ar_legacy.';
const ARW_METHOD = 'cannabis_management.credit_and_ar.page.ar_weekly_review.ar_weekly_review.';
const ALL_COMPANIES = '__ALL__';
const BOOK_NEW = 'New AR';

// Debt levels, worst first: the order the grid groups them in.
const TIERS = {
	level3: { label: __('Level 3'), full: __('Bad Debt Level 3 — 60+ days overdue'), desc: __('Legal pursuit status.'),
		bar: '#990000', q: __('What is going on?') },
	level2: { label: __('Level 2'), full: __('Bad Debt Level 2 — 30-60 days overdue'), desc: __('DEFCON Level 2 — Emergency.'),
		bar: '#b45f06', q: __('What is going on?') },
	level1: { label: __('Level 1'), full: __('Bad Debt Level 1 — 0-30 days overdue'), desc: __('Should never get here. Extremely urgent. In default.'),
		bar: '#cc0000', q: __('How did this account get here?') },
	upcoming: { label: __('On terms'), full: __('Upcoming Terms Due'), desc: __('On agreed terms, not yet due.'),
		bar: '#38761d', q: __('What is going on?') },
};
const TIER_ORDER = ['level3', 'level2', 'level1', 'upcoming'];
const TIER_RANK = { upcoming: 0, level1: 1, level2: 2, level3: 3 };

const STATUS_INK = {
	'Will Pay On Time': '#38761d',
	'Will Pay Immediately': '#38761d',
	'Client Is Dodging Us': '#cc0000',
	'Need Reconciliation': '#b45f06',
	'WIP At Lab': '#1155cc',
	'Pending Pickup': '#674ea7',
	'Payment Plan': '#e69138',
	'No Longer In Business': '#990000',
};
// AR Dashboard's colours for its five built-in recon statuses: [fill, ink].
const RECON_FALLBACK = {
	'Reconciled collecting money': ['#dcfce7', '#15803d'],
	'Reconciled trouble collecting money': ['#fef3c7', '#92400e'],
	'Unreconciled': ['#fee2e2', '#b91c1c'],
	'Dispute': ['#ede9fe', '#5b21b6'],
	'Adjustment': ['#dbeafe', '#1e40af'],
};

const MODE_LABEL = { legacy: __('Legacy AR'), new: __('New AR'), all: __('Legacy + New AR') };
const GROUPS = [
	['tier', __('Debt level')],
	['status', __('Weekly status')],
	['segment', __('Segment (ownership)')],
	['recon', __('Recon status')],
	['none', __('No grouping')],
];
const SORTS = [
	['outstanding', __('Largest balance')],
	['age', __('Oldest invoice first')],
	['invoices', __('Most invoices')],
	['name', __('Customer A-Z')],
];
const AGES = [['', __('Any age')], ['90', __('90+ days')], ['180', __('180+ days')],
	['270', __('270+ days')], ['365', __('1 year+')]];

const esc = (s) => frappe.utils.escape_html(s == null ? '' : String(s));
const money = (n) => (n < 0 ? '-$' : '$') + Math.abs(n || 0).toLocaleString('en-US',
	{ minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nil = '<span class="arh-nil">—</span>';
const cash = (n) => (Math.abs(n || 0) >= 0.005 ? money(n) : nil);
// "2026-10-09" -> "Oct 9, 2026", built from the parts so no timezone shifts the day.
const nice_date = (d) => {
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || '');
	return m ? new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('en-US',
		{ month: 'short', day: 'numeric', year: 'numeric' }) : '';
};
const blank_filters = () => ({ search: '', segment: '', recon: '', level: '', status: '', age: '', min: '', hide_motley: false });

frappe.pages['ar-hub'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('AR Hub'), single_column: true });
	wrapper.page = page;

	const hub = {
		page: page,
		data: null,
		seq: 0,
		mode: 'all',
		company: ALL_COMPANIES,
		f: blank_filters(),
		group: 'tier',
		sort: 'outstanding',
		open: {},     // customer -> expanded
		detail: {},   // customer -> 'loading' | 'error' | { paid_invoices, log }
		edits: {},    // customer -> unsaved weekly entry
	};
	page.arh = hub;

	const opts = (list, sel) => list.map((o) =>
		`<option value="${esc(o[0])}"${o[0] === sel ? ' selected' : ''}>${esc(o[1])}</option>`).join('');

	page.main.html(`
		<div class="arh">
			<div class="arh-bar">
				<div class="arh-ctl">
					<label>${__('AR Mode')}</label>
					<div class="arh-modes">
						${['legacy', 'new', 'all'].map((m) => `<button type="button" data-mode="${m}"${m === hub.mode ? ' class="on"' : ''}>${MODE_LABEL[m]}</button>`).join('')}
					</div>
				</div>
				<div class="arh-ctl"><label>${__('Company')}</label>
					<select data-k="company"><option value="${ALL_COMPANIES}">${__('All Entities')}</option></select></div>
				<div class="arh-ctl arh-ctl-search"><label>${__('Customer')}</label>
					<input type="text" data-f="search" placeholder="${__('Search customer…')}"></div>
				<div class="arh-ctl"><label>${__('Group by')}</label><select data-k="group">${opts(GROUPS, hub.group)}</select></div>
				<div class="arh-ctl"><label>${__('Sort')}</label><select data-k="sort">${opts(SORTS, hub.sort)}</select></div>
				<div class="arh-actions">
					<button type="button" class="arh-btn" data-act="xlsx">${__('Export Excel')}</button>
					<button type="button" class="arh-btn" data-act="csv">${__('Export CSV')}</button>
					<button type="button" class="arh-btn" data-act="print">${__('Print')}</button>
					<button type="button" class="arh-btn" data-act="refresh">${__('Refresh')}</button>
				</div>
			</div>
			<div class="arh-bar arh-bar2">
				<div class="arh-ctl"><label>${__('Segment')}</label><select data-f="segment"></select></div>
				<div class="arh-ctl"><label>${__('Recon Status')}</label><select data-f="recon"></select></div>
				<div class="arh-ctl"><label>${__('Level')}</label><select data-f="level"></select></div>
				<div class="arh-ctl arh-wk-only"><label>${__('Weekly Status')}</label><select data-f="status"></select></div>
				<div class="arh-ctl"><label>${__('Oldest invoice')}</label><select data-f="age">${opts(AGES, '')}</select></div>
				<div class="arh-ctl"><label>${__('Min balance')}</label>
					<input type="number" data-f="min" min="0" step="1000" placeholder="0"></div>
				<label class="arh-check"><input type="checkbox" data-f="hide_motley"> ${__('Hide Motley')}</label>
				<button type="button" class="arh-btn arh-btn-plain" data-act="clear">${__('Clear filters')}</button>
			</div>
			<div class="arh-sub"></div>
			<div class="arh-kpis"></div>
			<div class="arh-grid"><div class="arh-msg">${__('Loading receivables…')}</div></div>
		</div>
	`);

	bind(hub);
	load(hub);
};

// ---- data -------------------------------------------------------------------

function load(hub) {
	const seq = ++hub.seq;
	if (hub.data) hub.page.main.find('.arh-sub').text(__('Refreshing…'));
	frappe.call({
		method: ARH_METHOD + 'get_data',
		args: { ar_mode: hub.mode, company: hub.company },
		callback: function (r) {
			if (seq !== hub.seq || !r.message) return;
			hub.data = r.message;
			fill_options(hub);
			render(hub);
		},
		error: function () {
			if (seq !== hub.seq) return;
			hub.page.main.find('.arh-grid').html(`<div class="arh-msg">${__('Receivables could not be loaded.')}</div>`);
		},
	});
}

function fetch_detail(hub, customer) {
	if (hub.detail[customer]) return;
	hub.detail[customer] = 'loading';
	const seq = hub.seq;
	frappe.call({
		method: ARH_METHOD + 'get_customer_detail',
		args: { customer: customer, ar_mode: hub.mode, company: hub.company },
		callback: function (r) {
			if (seq !== hub.seq) return;
			hub.detail[customer] = r.message || { paid_invoices: [], log: [] };
			render(hub);
		},
		error: function () {
			if (seq !== hub.seq) return;
			hub.detail[customer] = 'error';
			render(hub);
		},
	});
}

function find_row(hub, customer) {
	return ((hub.data && hub.data.rows) || []).find((r) => r.customer === customer);
}

// The books (New AR / Legacy AR) a customer has money in, within the view.
function books(r) { return r.ledgers || []; }
function wk(r, book) { return (r.weekly || {})[book] || { tier: 'upcoming', statuses: [], status: '', note: '' }; }

// The book whose weekly status speaks for the customer when only one can: the
// one at the worse debt level, New AR on a tie.
function primary_book(r) {
	let best = null;
	books(r).forEach((b) => {
		if (!best || TIER_RANK[wk(r, b).tier] > TIER_RANK[wk(r, best).tier]) best = b;
	});
	return best;
}

function fill_options(hub) {
	const d = hub.data, m = hub.page.main;
	const opts = (list, sel) => list.map((o) =>
		`<option value="${esc(o[0])}"${o[0] === sel ? ' selected' : ''}>${esc(o[1])}</option>`).join('');

	if (d.companies.indexOf(hub.company) === -1) hub.company = ALL_COMPANIES;
	m.find('[data-k="company"]').html(opts([[ALL_COMPANIES, __('All Entities')]].concat(d.companies.map((c) => [c, c])), hub.company));

	const f = hub.f;
	m.find('[data-f="segment"]').html(opts([['', __('All')], ['__none__', d.unassigned_label]]
		.concat(d.segments.map((s) => [s, s])), f.segment));
	m.find('[data-f="recon"]').html(opts([['', __('All')], ['__none__', __('Not set')]]
		.concat(d.recon_statuses.map((s) => [s.value, s.label || s.value])), f.recon));
	m.find('[data-f="level"]').html(opts([['', __('All')]].concat(TIER_ORDER.map((t) => [t, TIERS[t].label])), f.level));

	m.find('.arh-wk-only').toggle(!!d.can_weekly);
	m.find('[data-f="status"]').html(opts([['', __('All')], ['__none__', __('No status yet')]]
		.concat(d.statuses.map((s) => [s, s])), f.status));
	if (!d.can_weekly) {
		f.status = '';
		if (hub.group === 'status') hub.group = 'tier';
	}
	m.find('[data-k="group"]').html(opts(GROUPS.filter((g) => d.can_weekly || g[0] !== 'status'), hub.group));
}

// ---- filtering, grouping ------------------------------------------------------

function visible_rows(hub) {
	const f = hub.f;
	const q = (f.search || '').trim().toLowerCase();
	const min = parseFloat(f.min) || 0;
	const age = parseInt(f.age, 10) || 0;
	return hub.data.rows.filter(function (r) {
		if (q && r.customer.toLowerCase().indexOf(q) === -1
			&& (r.customer_name || '').toLowerCase().indexOf(q) === -1) return false;
		// AR Dashboard's "Remove Motley": by name, on top of the intercompany exclusion.
		if (f.hide_motley && /motley/i.test(r.customer_name || r.customer)) return false;
		if (f.segment && (f.segment === '__none__' ? !!r.segment : r.segment !== f.segment)) return false;
		if (f.recon && (f.recon === '__none__' ? !!r.recon_status : r.recon_status !== f.recon)) return false;
		if (f.level && r.tier !== f.level) return false;
		if (f.status) {
			const st = books(r).map((b) => wk(r, b).status);
			if (f.status === '__none__' ? st.every(Boolean) : st.indexOf(f.status) === -1) return false;
		}
		if (min && r.outstanding < min) return false;
		if (age && r.age_days < age) return false;
		return true;
	});
}

function sort_rows(rows, by) {
	return rows.sort(function (a, b) {
		if (by === 'age') return b.age_days - a.age_days;
		if (by === 'invoices') return b.invoice_count - a.invoice_count;
		if (by === 'name') return (a.customer_name || a.customer).localeCompare(b.customer_name || b.customer);
		return b.outstanding - a.outstanding;
	});
}

// Keys from the live list first, then any value a customer still carries that
// has since been disabled, so nobody drops out of the grid.
function keys_with_extras(keys, rows, value_of) {
	const out = keys.slice();
	rows.forEach((r) => { const v = value_of(r); if (v && out.indexOf(v) === -1) out.push(v); });
	return out;
}

function grouped(hub, rows) {
	const d = hub.data;
	let groups;
	if (hub.group === 'tier') {
		groups = TIER_ORDER.map((t) => ({ title: TIERS[t].full, desc: TIERS[t].desc, color: TIERS[t].bar,
			rows: rows.filter((r) => r.tier === t) }));
	} else if (hub.group === 'segment') {
		groups = keys_with_extras([''].concat(d.segments), rows, (r) => r.segment).map((k) => ({
			title: k || d.unassigned_label, desc: k ? '' : __('No segment chosen yet.'),
			color: k ? (d.segment_colors[k] || '#6d28d9') : '#666666',
			rows: rows.filter((r) => (r.segment || '') === k),
		}));
	} else if (hub.group === 'recon') {
		groups = keys_with_extras([''].concat(d.recon_statuses.map((s) => s.value)), rows, (r) => r.recon_status).map((k) => ({
			title: k || __('Recon status not set'), desc: '',
			color: k ? recon_colors(hub, k)[1] : '#666666',
			rows: rows.filter((r) => (r.recon_status || '') === k),
		}));
	} else if (hub.group === 'status') {
		const status_of = (r) => wk(r, primary_book(r)).status || '';
		groups = keys_with_extras([''].concat(d.statuses), rows, status_of).map((k) => ({
			title: k || __('No status yet'), desc: k ? '' : __('Needs a status this week.'),
			color: k ? (STATUS_INK[k] || '#434343') : '#666666',
			rows: rows.filter((r) => status_of(r) === k),
		}));
	} else {
		groups = [{ title: null, rows: rows }];
	}
	groups = groups.filter((g) => g.rows.length);
	groups.forEach((g) => sort_rows(g.rows, hub.sort));
	return groups;
}

// ---- columns ------------------------------------------------------------------

const BANDS = {
	cust: '', own: __('Ownership'), acct: __('Account'), wk: __('Weekly Review'), age: __('Age'),
	bal: __('Balance'), book: __('Book'), terms: __('On Terms — days left'), overdue: __('Overdue — days past due'),
};

function columns(hub) {
	const d = hub.data;
	const cols = [
		{ k: 'customer', band: 'cust', label: __('Customer') },
		{ k: 'segment', band: 'own', label: __('Segment') },
		{ k: 'recon', band: 'acct', label: __('Recon Status') },
		{ k: 'onboarding', band: 'acct', label: __('Onboarding') },
		{ k: 'company_made_contact', band: 'acct', label: __('Company Made Contact') },
	];
	if (d.can_weekly) {
		cols.push({ k: 'wstatus', band: 'wk', label: __('Weekly Status') },
			{ k: 'wnote', band: 'wk', label: __('Latest Note') });
	}
	cols.push({ k: 'level', band: 'age', label: __('Level') },
		{ k: 'oldest', band: 'age', label: __('Oldest Invoice') },
		{ k: 'invoiced', band: 'bal', label: __('Invoiced'), sum: (r) => r.invoiced },
		{ k: 'paid', band: 'bal', label: __('Paid'), sum: (r) => r.paid },
		{ k: 'outstanding', band: 'bal', label: __('Outstanding'), sum: (r) => r.outstanding });
	if (d.ar_mode === 'all') {
		cols.push({ k: 'legacy', band: 'book', label: __('Legacy AR'), sum: (r) => r.legacy_ar },
			{ k: 'new', band: 'book', label: __('New AR'), sum: (r) => r.new_ar });
	}
	d.terms.forEach((t) => cols.push({ k: 'term-' + t.key, band: 'terms', label: t.label, sub: __('days left'),
		sum: (r) => r.terms[t.key] }));
	d.overdue.forEach((b) => cols.push({ k: 'od-' + b.tier, band: 'overdue', label: b.label.replace(' days', ''),
		sub: __('days'), sum: (r) => r.buckets[b.label] }));
	return cols;
}

function recon_colors(hub, status) {
	const own = (hub.data.recon_statuses || []).find((s) => s.value === status);
	if (own && own.color) return [own.color + '1f', own.color];
	return RECON_FALLBACK[status] || ['#f1f3f4', '#3c4043'];
}

function fill_style(bg, ink) {
	return ` style="background-color:${esc(bg)};color:${esc(ink)};border-color:${esc(ink)};"`;
}

// A dropdown, or the value alone for someone who may not change it.
function select_cell(kind, field, r, value, options, style, editable, printing) {
	if (!editable || printing) {
		const label = (options.find((o) => o[0] === value) || [value, value])[1];
		return `<td class="c-sel"><span class="arh-ro"${value ? style : ''}>${value ? esc(label) : nil}</span></td>`;
	}
	const opts = options.map((o) =>
		`<option value="${esc(o[0])}"${o[0] === (value || '') ? ' selected' : ''}>${esc(o[1])}</option>`).join('');
	return `<td class="c-sel"><select class="arh-inline" data-kind="${kind}" data-field="${field}"
		data-customer="${esc(r.customer)}"${value ? style : ''}>${opts}</select></td>`;
}

function cell(hub, c, r, printing) {
	const d = hub.data;
	switch (c.k) {
	case 'customer': {
		const open = !printing && hub.open[r.customer];
		return `<td class="c-customer">
			<div class="arh-cust">${printing ? '' : `<span class="arh-caret">${open ? '▾' : '▸'}</span>`}<span class="arh-cname">${esc(r.customer_name)}</span>${printing ? ''
				: ` <a class="arh-link" href="/app/customer/${encodeURIComponent(r.customer)}" target="_blank" rel="noopener" title="${__('Open customer')}">↗</a>`}</div>
			<div class="arh-cmeta">${r.invoice_count} ${__('inv')} · ${esc(r.companies.join(', '))}</div>
		</td>`;
	}
	case 'segment': {
		const seg_opts = [['', d.unassigned_label]].concat(keys_with_extras(d.segments, [r], (x) => x.segment).map((s) => [s, s]));
		const color = d.segment_colors[r.segment] || '#6d28d9';
		return select_cell('segment', 'segment', r, r.segment, seg_opts, fill_style(color + '1f', color), d.can_edit_segment, printing);
	}
	case 'recon': {
		const rec_opts = [['', '—']].concat(keys_with_extras(d.recon_statuses.map((s) => s.value), [r], (x) => x.recon_status).map((s) => [s, s]));
		const rc = recon_colors(hub, r.recon_status);
		return select_cell('recon', 'recon_status', r, r.recon_status, rec_opts, fill_style(rc[0], rc[1]), d.can_edit_recon, printing);
	}
	case 'onboarding':
	case 'company_made_contact': {
		const v = r[c.k];
		const style = v === 'Yes' ? fill_style('#d9ead3', '#274e13') : fill_style('#fce8e6', '#cc0000');
		return select_cell('flag', c.k, r, v, [['', '—'], ['Yes', 'Yes'], ['No', 'No']], style, d.can_edit_recon, printing);
	}
	case 'wstatus':
	case 'wnote': {
		const bs = books(r);
		return `<td class="c-${c.k}">${bs.map((b) => {
			const w = wk(r, b);
			const tag = bs.length > 1 ? `<span class="arh-book">${b === BOOK_NEW ? __('New') : __('Legacy')}</span>` : '';
			if (c.k === 'wnote') return `<div class="arh-note" title="${esc(w.note)}">${tag}${w.note ? esc(w.note) : nil}</div>`;
			return `<div class="arh-wk"${w.status ? ` style="color:${STATUS_INK[w.status] || '#3c4043'}"` : ''}>${tag}${w.status ? esc(w.status) : `<span class="arh-nil">${__('No status yet')}</span>`}</div>`;
		}).join('')}</td>`;
	}
	case 'level':
		return `<td class="c-level t-${r.tier}">${TIERS[r.tier].label}${r.worst ? `<small>${esc(r.worst)}</small>` : ''}</td>`;
	case 'oldest': {
		const cls = r.age_days >= 365 ? ' a-old' : r.age_days >= 180 ? ' a-mid' : '';
		return `<td class="c-oldest${cls}">${esc(nice_date(r.oldest))}<small>${r.age_days} ${__('days')}</small></td>`;
	}
	default:
		return `<td class="c-num c-${c.k}">${cash(c.sum(r))}</td>`;
	}
}

// A row of sums: the TOTALS row on top and each group's subtotal.
function sum_cells(cols, rows, label, cls) {
	return cols.map((c, i) => {
		if (i === 0) return `<td class="c-customer ${cls}">${label}</td>`;
		if (!c.sum) return `<td class="${cls}"></td>`;
		return `<td class="c-num c-${c.k} ${cls}">${cash(rows.reduce((s, r) => s + (c.sum(r) || 0), 0))}</td>`;
	}).join('');
}

// ---- rendering ------------------------------------------------------------------

function render(hub) {
	const d = hub.data;
	if (!d) return;
	const rows = visible_rows(hub);
	const groups = grouped(hub, rows);
	hub.shown = [].concat.apply([], groups.map((g) => g.rows));

	const company_label = hub.company === ALL_COMPANIES ? __('All Entities') : hub.company;
	hub.page.main.find('.arh-sub').text(__('As of {0} · {1} · {2} · {3} of {4} customers', [
		nice_date(d.as_of), MODE_LABEL[d.ar_mode], company_label, rows.length, d.rows.length]));
	hub.page.main.find('.arh-kpis').html(kpi_html(hub, rows));

	const $grid = hub.page.main.find('.arh-grid');
	const $old = $grid.find('.arh-wrap');
	const scroll = $old.length ? [$old.scrollTop(), $old.scrollLeft()] : [0, 0];

	if (!rows.length) {
		$grid.html(`<div class="arh-msg">${d.rows.length ? __('No customers match these filters.') : __('No outstanding receivables.')}</div>`);
		return;
	}
	$grid.html(`<div class="arh-wrap">${sheet_html(hub, groups, false)}</div>`);

	const $wrap = $grid.find('.arh-wrap');
	$wrap.scrollTop(scroll[0]).scrollLeft(scroll[1]);
	freeze(hub, $wrap);
	Object.keys(hub.open).forEach((c) => { if (hub.open[c]) fetch_detail(hub, c); });
}

// Header rows stay put while the sheet scrolls: each sticks below the ones above.
function freeze(hub, $wrap) {
	let top = 0;
	$wrap.find('thead tr').each(function () {
		$(this).children().css('top', top + 'px');
		top += this.getBoundingClientRect().height;
	});
	// Expanded rows span the whole sheet; keep their panel the width of the view.
	const w = $wrap[0].clientWidth;
	if (w) $wrap.find('.arh-detail-in').css('width', (w - 2) + 'px');
}

function sheet_html(hub, groups, printing) {
	const d = hub.data;
	const cols = columns(hub);
	const all_rows = [].concat.apply([], groups.map((g) => g.rows));

	// Band row: one cell per run of columns that share a band.
	const bands = [];
	cols.forEach((c) => {
		const last = bands[bands.length - 1];
		if (last && last.band === c.band) last.span++;
		else bands.push({ band: c.band, span: 1 });
	});
	const band_row = bands.map((b, i) =>
		`<th colspan="${b.span}" class="b-${b.band}${i === 0 ? ' c-customer' : ''}">${esc(BANDS[b.band])}</th>`).join('');
	const head_row = cols.map((c) =>
		`<th class="h-${c.band} c-${c.k}">${esc(c.label)}${c.sub ? `<small>${esc(c.sub)}</small>` : ''}</th>`).join('');
	const n_inv = all_rows.reduce((s, r) => s + r.invoice_count, 0);
	const totals = sum_cells(cols, all_rows,
		`${__('TOTALS')}<small>${all_rows.length} ${__('customers')} · ${n_inv} ${__('invoices')}</small>`, 'x-total');

	let body = '';
	groups.forEach((g) => {
		if (g.title !== null) {
			const amt = g.rows.reduce((s, r) => s + r.outstanding, 0);
			body += `<tr class="arh-grp"><td colspan="${cols.length}" style="background-color:${esc(g.color)};">
				<div class="arh-grp-in"><b>${esc(g.title)}</b>${g.desc ? `<span class="arh-grp-desc">${esc(g.desc)}</span>` : ''}
				<span class="arh-grp-meta">${g.rows.length} ${g.rows.length === 1 ? __('customer') : __('customers')} · ${money(amt)}</span></div>
			</td></tr>`;
		}
		g.rows.forEach((r) => {
			const open = !printing && hub.open[r.customer];
			body += `<tr class="arh-row${open ? ' is-open' : ''}" data-customer="${esc(r.customer)}">
				${cols.map((c) => cell(hub, c, r, printing)).join('')}</tr>`;
			if (open) {
				body += `<tr class="arh-detail"><td colspan="${cols.length}"><div class="arh-detail-in">${detail_html(hub, r)}</div></td></tr>`;
			}
		});
		if (g.title !== null) {
			body += `<tr class="arh-subtotal">${sum_cells(cols, g.rows, __('Subtotal'), 'x-sub')}</tr>`;
		}
	});

	return `<table class="arh-sheet${d.ar_mode === 'new' ? ' arh-mode-new' : ''}">
		<thead>
			<tr class="arh-band">${band_row}</tr>
			<tr class="arh-head">${head_row}</tr>
			<tr class="arh-totals">${totals}</tr>
		</thead>
		<tbody>${body}</tbody>
	</table>`;
}

function kpi_html(hub, rows) {
	const d = hub.data;
	const sum = (list, k) => list.reduce((s, r) => s + (r[k] || 0), 0);
	const outstanding = sum(rows, 'outstanding');
	const overdue = sum(rows, 'overdue');
	const lvl3 = rows.filter((r) => r.tier === 'level3');
	const unfiled = rows.filter((r) => !r.segment);
	const cells = [
		['k-out', __('Outstanding'), money(outstanding), rows.length + ' ' + __('customers')],
		['k-inv', __('Invoiced'), money(sum(rows, 'invoiced')), ''],
		['k-paid', __('Paid'), money(sum(rows, 'paid')), ''],
		['k-terms', __('On terms'), money(sum(rows, 'on_terms')), __('not yet due')],
		['k-over', __('Overdue'), money(overdue),
			(outstanding ? (overdue / outstanding * 100).toFixed(1) : '0.0') + '% ' + __('of AR')],
		['k-l3', __('Level 3 (60+ overdue)'), money(sum(lvl3, 'outstanding')), lvl3.length + ' ' + __('customers')],
		['k-seg', __('No segment'), money(sum(unfiled, 'outstanding')), unfiled.length + ' ' + __('customers')],
	];
	if (d.can_weekly) {
		const unfiled_wk = rows.filter((r) => books(r).some((b) => !wk(r, b).status));
		cells.push(['k-wk', __('No weekly status'), money(sum(unfiled_wk, 'outstanding')),
			unfiled_wk.length + ' ' + __('customers') + ' · ' + __('week of {0}', [nice_date(d.week_of)])]);
	}
	return `<table class="arh-kpi"><thead><tr>${cells.map((c) => `<th class="${c[0]}">${esc(c[1])}</th>`).join('')}</tr></thead>
		<tbody><tr>${cells.map((c) => `<td class="${c[0]}"><b>${c[2]}</b>${c[3] ? `<small>${esc(c[3])}</small>` : ''}</td>`).join('')}</tr></tbody></table>`;
}

function detail_html(hub, r) {
	const d = hub.data;
	const det = hub.detail[r.customer];
	const loaded = det && typeof det === 'object';
	const paid = loaded ? det.paid_invoices : [];
	const show_book = d.ar_mode === 'all';

	// Invoices: the open ones behind the row, then the fully paid ones.
	const inv_row = (i, is_paid) => `<tr${is_paid ? ' class="is-paid"' : ''}>
		<td class="m-inv"><a href="/app/sales-invoice/${encodeURIComponent(i.name)}" target="_blank" rel="noopener">${esc(i.name)}</a></td>
		<td class="m-co">${esc(i.company)}</td>
		${show_book ? `<td>${esc(i.ledger)}</td>` : ''}
		<td class="m-date">${esc(nice_date(i.posting_date))}</td>
		<td class="m-date">${esc(nice_date(i.due_date))}</td>
		<td class="m-age t-${is_paid ? 'paid' : i.tier}">${is_paid ? __('Paid') : esc(i.aging)}</td>
		<td class="m-num m-invd">${money(i.invoiced)}</td>
		<td class="m-num m-paid">${money(is_paid ? i.invoiced : i.paid)}</td>
		<td class="m-num m-out">${is_paid ? nil : money(i.outstanding)}</td>
	</tr>`;
	const total = (k) => r.invoices.reduce((s, i) => s + i[k], 0);
	const paid_note = det === 'loading' ? __('loading paid invoices…') : det === 'error'
		? __('paid invoices could not be loaded') : paid.length + ' ' + __('paid');
	const inv_html = `<section class="arh-sec arh-sec-inv">
		<header>${__('Invoices')} — ${r.invoices.length} ${__('open')} · ${esc(paid_note)}</header>
		<div class="arh-sec-scroll"><table class="arh-mini"><thead><tr>
			<th class="m-inv">${__('Invoice')}</th><th>${__('Company')}</th>${show_book ? `<th>${__('Book')}</th>` : ''}
			<th>${__('Posted')}</th><th>${__('Due')}</th><th>${__('Aging')}</th>
			<th class="m-num m-invd">${__('Invoiced')}</th><th class="m-num m-paid">${__('Paid')}</th><th class="m-num m-out">${__('Outstanding')}</th>
		</tr></thead>
		<tbody>${r.invoices.map((i) => inv_row(i, false)).join('')}${paid.map((i) => inv_row(i, true)).join('')}</tbody>
		<tfoot><tr><td colspan="${show_book ? 6 : 5}">${__('Open total')}</td>
			<td class="m-num m-invd">${money(total('invoiced'))}</td><td class="m-num m-paid">${money(total('paid'))}</td>
			<td class="m-num m-out">${money(total('outstanding'))}</td></tr></tfoot>
		</table></div>
	</section>`;

	// Account: AR Dashboard's Notebox and New AR flag.
	const acct_html = `<section class="arh-sec arh-sec-acct">
		<header>${__('Account notes')}</header>
		<div class="arh-sec-body arh-acct">
			<div class="arh-field arh-field-wide"><label>${__('Notebox')}</label>
				${d.can_edit_recon
		? `<textarea class="arh-notebox" data-customer="${esc(r.customer)}" placeholder="${__('Saved when you click away')}">${esc(r.notebox)}</textarea>`
		: `<div class="arh-ro-text">${r.notebox ? esc(r.notebox) : nil}</div>`}</div>
			<label class="arh-check"><input type="checkbox" class="arh-newar" data-customer="${esc(r.customer)}"
				${r.new_ar_available ? 'checked' : ''}${d.can_edit_recon ? '' : ' disabled'}> ${__('New AR available')}</label>
		</div>
	</section>`;

	if (!d.can_weekly) return `<div class="arh-detail-cols">${inv_html}${acct_html}</div>`;

	// This week's entry, for one book at a time.
	const e = hub.edits[r.customer] || {};
	const bs = books(r);
	const book = bs.indexOf(e.book) !== -1 ? e.book : primary_book(r);
	const w = wk(r, book);
	const tier = TIERS[w.tier] || TIERS.upcoming;
	const field = (role, label, tag) => `<div class="arh-field"><label>${esc(label)}</label>${tag === 'input'
		? `<input type="text" data-role="${role}" data-customer="${esc(r.customer)}" value="${esc(e[role] || '')}">`
		: `<textarea data-role="${role}" data-customer="${esc(r.customer)}">${esc(e[role] || '')}</textarea>`}</div>`;
	const entry_html = `<section class="arh-sec arh-sec-entry">
		<header>${__('This week\'s entry')} — ${__('week of {0}', [esc(nice_date(d.week_of))])}</header>
		<div class="arh-sec-body">
			<div class="arh-form">
				${bs.length > 1 ? `<div class="arh-field"><label>${__('Book')}</label>
					<select data-role="book" data-customer="${esc(r.customer)}">${bs.map((b) =>
		`<option value="${esc(b)}"${b === book ? ' selected' : ''}>${esc(b)}</option>`).join('')}</select></div>` : ''}
				<div class="arh-field"><label>${__('Status')} <span class="arh-lvl t-${w.tier}">${tier.label}</span></label>
					<select data-role="status" data-customer="${esc(r.customer)}">
						<option value="">— ${__('pick status')} —</option>
						${w.statuses.map((s) => `<option value="${esc(s)}"${e.status === s ? ' selected' : ''}>${esc(s)}</option>`).join('')}
					</select></div>
				${w.tier !== 'upcoming' ? `<label class="arh-check"><input type="checkbox" data-role="call" data-customer="${esc(r.customer)}"${e.call ? ' checked' : ''}>
					${__('Need three-way call with finance')}</label>` : ''}
				${field('qa', tier.q)}
				${field('plan', __('What is the plan?'))}
				${field('notes', __('Notes'))}
				${field('contact', __('Contact info'), 'input')}
				${field('email', __('Email'), 'input')}
			</div>
			<button type="button" class="arh-save-week" data-customer="${esc(r.customer)}">${__('Save this week\'s entry')} (${esc(book)})</button>
		</div>
	</section>`;

	const log = loaded ? det.log || [] : null;
	const log_rows = log === null
		? `<tr><td colspan="${show_book ? 8 : 7}" class="arh-nil">${det === 'error' ? __('Could not load.') : __('Loading…')}</td></tr>`
		: !log.length ? `<tr><td colspan="${show_book ? 8 : 7}" class="arh-nil">${__('No weekly entries yet — this will be the first.')}</td></tr>`
			: log.map((x) => `<tr>
				<td class="m-date"><b>${esc(nice_date(x.week_of))}</b></td>
				${show_book ? `<td>${esc(x.ledger)}</td>` : ''}
				<td><b style="color:${STATUS_INK[x.status] || '#3c4043'}">${esc(x.status || '')}</b></td>
				<td class="m-wrap">${esc(x.qa || '')}</td>
				<td class="m-wrap">${esc(x.plan || '')}</td>
				<td class="m-wrap">${esc(x.notes || '')}</td>
				<td class="m-wrap">${esc(x.contact || '')}${x.email ? ' · ' + esc(x.email) : ''}${x.need_three_way_call ? ' · ' + __('3-way call') : ''}</td>
				<td>${esc(x.owner || '')}</td>
			</tr>`).join('');
	const log_html = `<section class="arh-sec arh-sec-log">
		<header>${__('Entry history')}${log && log.length ? ` (${log.length})` : ''} — ${__('most recent first')}</header>
		<div class="arh-sec-scroll"><table class="arh-mini arh-log"><thead><tr>
			<th>${__('Week of')}</th>${show_book ? `<th>${__('Book')}</th>` : ''}<th>${__('Status')}</th>
			<th>${__('What is going on?')}</th><th>${__('Plan')}</th><th>${__('Notes')}</th><th>${__('Contact')}</th><th>${__('Filed by')}</th>
		</tr></thead><tbody>${log_rows}</tbody></table></div>
	</section>`;

	return `<div class="arh-detail-cols">${inv_html}${entry_html}</div>
		<div class="arh-detail-cols">${log_html}${acct_html}</div>`;
}

// ---- events -------------------------------------------------------------------

function bind(hub) {
	const m = hub.page.main;

	m.on('click', '.arh-modes button', function () {
		const mode = $(this).attr('data-mode');
		if (mode === hub.mode) return;
		hub.mode = mode;
		m.find('.arh-modes button').removeClass('on');
		$(this).addClass('on');
		hub.detail = {};
		load(hub);
	});

	m.on('change', '[data-k]', function () {
		const k = $(this).attr('data-k');
		if (k === 'company') {
			hub.company = $(this).val();
			hub.detail = {};
			load(hub);
			return;
		}
		hub[k] = $(this).val();
		render(hub);
	});

	m.on('input change', '[data-f]', function () {
		const k = $(this).attr('data-f');
		hub.f[k] = this.type === 'checkbox' ? this.checked : $(this).val();
		if (hub.data) render(hub);
	});

	m.on('click', '[data-act]', function () {
		const act = $(this).attr('data-act');
		if (act === 'refresh') { hub.detail = {}; load(hub); }
		else if (act === 'clear') {
			hub.f = blank_filters();
			m.find('[data-f]').each(function () {
				if (this.type === 'checkbox') this.checked = false;
				else $(this).val('');
			});
			if (hub.data) render(hub);
		}
		else if (act === 'print') print_view(hub);
		else export_view(hub, act);
	});

	// A click on a customer row opens it, unless it was on one of its controls.
	m.on('click', 'tr.arh-row', function (e) {
		if ($(e.target).closest('select, a, input, textarea, button, label').length) return;
		const customer = $(this).attr('data-customer');
		hub.open[customer] = !hub.open[customer];
		render(hub);
	});

	m.on('change', 'select.arh-inline', function () { save_field(hub, $(this)); });

	m.on('focusout', '.arh-notebox', function () {
		const customer = $(this).attr('data-customer');
		const row = find_row(hub, customer);
		const value = $(this).val();
		if (!row || value === (row.notebox || '')) return;
		save(hub, ARD_METHOD + 'update_notebox', { party: customer, value: value }, __('Notebox'), customer,
			() => { row.notebox = value; });
	});

	m.on('change', '.arh-newar', function () {
		const customer = $(this).attr('data-customer');
		const row = find_row(hub, customer);
		const value = this.checked ? 1 : 0;
		save(hub, ARD_METHOD + 'update_new_ar_available', { party: customer, value: value }, __('New AR'), customer,
			() => { row.new_ar_available = value; }, () => { this.checked = !value; });
	});

	// The weekly entry form keeps what is typed across re-renders.
	m.on('input change', '.arh-detail [data-role]', function () {
		const customer = $(this).attr('data-customer');
		const role = $(this).attr('data-role');
		const e = (hub.edits[customer] = hub.edits[customer] || {});
		e[role] = this.type === 'checkbox' ? this.checked : $(this).val();
		if (role === 'book') {
			// Statuses depend on the book's debt level; drop one the new book does not offer.
			const r = find_row(hub, customer);
			if (r && wk(r, e.book).statuses.indexOf(e.status) === -1) e.status = '';
			render(hub);
		}
	});

	m.on('click', '.arh-save-week', function () { save_week(hub, $(this).attr('data-customer'), $(this)); });
}

function save(hub, method, args, label, customer, on_ok, on_fail) {
	frappe.call({
		method: method,
		args: args,
		callback: function () {
			on_ok();
			frappe.show_alert({ message: __('{0} updated for {1}', [label, esc(customer)]), indicator: 'green' }, 3);
			render(hub);
		},
		error: function () {
			if (on_fail) on_fail();
			frappe.show_alert({ message: __('Could not update {0}', [label]), indicator: 'red' }, 5);
		},
	});
}

function save_field(hub, $sel) {
	const kind = $sel.attr('data-kind');
	const field = $sel.attr('data-field');
	const customer = $sel.attr('data-customer');
	const value = $sel.val();
	const row = find_row(hub, customer);
	if (!row) return;
	const old = row[field] || '';
	let method, args, label;
	if (kind === 'recon') {
		method = ARD_METHOD + 'update_recon_status';
		args = { party: customer, status: value };
		label = __('Recon Status');
	} else if (kind === 'flag') {
		method = ARD_METHOD + 'update_ar_flag';
		args = { party: customer, field: field, value: value };
		label = field === 'onboarding' ? __('Onboarding') : __('Company Made Contact');
	} else {
		method = ARL_METHOD + 'set_segment';
		args = { customer: customer, segment: value };
		label = __('Segment');
	}
	$sel.prop('disabled', true);
	save(hub, method, args, label, customer, () => { row[field] = value; },
		() => { $sel.prop('disabled', false).val(old); });
}

function save_week(hub, customer, $btn) {
	const r = find_row(hub, customer);
	if (!r) return;
	const e = hub.edits[customer] || {};
	const book = books(r).indexOf(e.book) !== -1 ? e.book : primary_book(r);
	if (!e.status) {
		frappe.msgprint(__('Pick a status before saving this week\'s entry.'));
		return;
	}
	$btn.prop('disabled', true);
	frappe.call({
		method: ARW_METHOD + 'add_ar_weekly_entry',
		args: {
			customer: customer,
			ledger: book,
			status: e.status,
			qa: e.qa || '',
			plan: e.plan || '',
			notes: e.notes || '',
			contact: e.contact || '',
			email: e.email || '',
			need_three_way_call: e.call ? 1 : 0,
		},
		callback: function () {
			frappe.show_alert({ message: __('Weekly entry saved for {0} ({1})', [esc(customer), esc(book)]), indicator: 'green' }, 4);
			delete hub.edits[customer];
			delete hub.detail[customer];
			load(hub);
		},
		error: function () { $btn.prop('disabled', false); },
	});
}

// ---- export / print -----------------------------------------------------------

// The server rebuilds every figure; the page only says which customers are in
// view and in what order.
function export_view(hub, file_format) {
	if (!hub.data || !(hub.shown || []).length) {
		frappe.msgprint(__('Nothing to export — no customers in view.'));
		return;
	}
	open_url_post(frappe.request.url, {
		cmd: ARH_METHOD + 'export_view',
		ar_mode: hub.mode,
		company: hub.company,
		customers: JSON.stringify(hub.shown.map((r) => r.customer)),
		file_format: file_format,
	});
}

function print_view(hub) {
	if (!hub.data) return;
	const groups = grouped(hub, visible_rows(hub));
	if (!groups.length) {
		frappe.msgprint(__('Nothing to print — no customers in view.'));
		return;
	}
	let styles = '';
	document.querySelectorAll('style').forEach((st) => { if (/\.arh/.test(st.textContent)) styles += st.outerHTML; });
	const html = `<!doctype html><html><head><meta charset="utf-8"><title>${__('AR Hub')}</title>${styles}
		<style>
			@page { size: landscape; margin: 8mm; }
			body { font-family: Arial, sans-serif; margin: 0; }
			.arh-wrap { max-height: none; overflow: visible; border: none; }
			.arh-sheet th, .arh-sheet td { position: static !important; padding: 3px 5px; font-size: 9px; }
			.arh-kpi th, .arh-kpi td { font-size: 9px; padding: 3px 6px; }
			h2 { font-size: 15px; margin: 0 0 4px; }
			* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		</style></head><body class="arh">
		<h2>${__('AR Hub')}</h2>
		<div class="arh-sub">${esc(hub.page.main.find('.arh-sub').text())}</div>
		${kpi_html(hub, visible_rows(hub))}
		<div class="arh-wrap">${sheet_html(hub, groups, true)}</div>
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
})();
