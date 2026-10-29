(function () {
const ARH_METHOD = 'cannabis_management.credit_and_ar.page.ar_hub.ar_hub.';
const ARD_METHOD = 'cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.';
const ARL_METHOD = 'cannabis_management.cannabis_management.page.ar_legacy.ar_legacy.';
const ARW_METHOD = 'cannabis_management.credit_and_ar.page.ar_weekly_review.ar_weekly_review.';
const ALL_COMPANIES = '__ALL__';
const BOOK_NEW = 'New AR';

const TIERS = {
	level3: { label: __('Level 3'), full: __('Level 3 — 60+ days overdue'), desc: __('Legal pursuit status.'),
		color: 'var(--arh-red)', q: __('What is going on?') },
	level2: { label: __('Level 2'), full: __('Level 2 — 30-60 days overdue'), desc: __('DEFCON Level 2 — Emergency.'),
		color: 'var(--arh-orange)', q: __('What is going on?') },
	level1: { label: __('Level 1'), full: __('Level 1 — 0-30 days overdue'), desc: __('Should never get here. Extremely urgent. In default.'),
		color: 'var(--arh-amber)', q: __('How did this account get here?') },
	upcoming: { label: __('On terms'), full: __('On terms — not yet due'), desc: __('On agreed terms, not yet due.'),
		color: 'var(--arh-green)', q: __('What is going on?') },
};
const TIER_ORDER = ['level3', 'level2', 'level1', 'upcoming'];
const TIER_RANK = { upcoming: 0, level1: 1, level2: 2, level3: 3 };

const STATUS_COLOR = {
	'Will Pay On Time': 'var(--arh-green)',
	'Will Pay Immediately': 'var(--arh-green)',
	'Client Is Dodging Us': 'var(--arh-red)',
	'Need Reconciliation': 'var(--arh-amber)',
	'WIP At Lab': 'var(--arh-blue)',
	'Pending Pickup': 'var(--arh-violet)',
	'Payment Plan': 'var(--arh-orange)',
	'No Longer In Business': 'var(--arh-red)',
};
const RECON_COLOR = {
	'Reconciled collecting money': 'var(--arh-green)',
	'Reconciled trouble collecting money': 'var(--arh-amber)',
	'Unreconciled': 'var(--arh-red)',
	'Dispute': 'var(--arh-violet)',
	'Adjustment': 'var(--arh-blue)',
};
const FLAG_COLOR = { Yes: 'var(--arh-green)', No: 'var(--arh-red)' };

const MODE_LABEL = { legacy: __('Legacy AR'), new: __('New AR'), all: __('Legacy + New AR') };
const GROUPS = [
	['tier', __('Group by debt level')],
	['status', __('Group by weekly status')],
	['segment', __('Group by segment')],
	['recon', __('Group by recon status')],
	['none', __('No grouping')],
];
const SORTS = [
	['outstanding', __('Sort by largest balance')],
	['age', __('Sort by oldest invoice')],
	['invoices', __('Sort by most invoices')],
	['name', __('Sort by name (A-Z)')],
];
const AGES = [['', __('Any invoice age')], ['90', __('Oldest 90+ days')], ['180', __('Oldest 180+ days')],
	['270', __('Oldest 270+ days')], ['365', __('Oldest 1 year+')]];

const COL_SETS = [
	{ key: 'book', label: __('Legacy / New AR split'), on: true },
	{ key: 'billing', label: __('Invoiced and paid'), on: false },
	{ key: 'account', label: __('Segment and recon status'), on: true },
	{ key: 'flags', label: __('Onboarding and company made contact'), on: false },
	{ key: 'weekly', label: __('Weekly status and latest note'), on: true },
	{ key: 'terms', label: __('On-terms breakdown (days left)'), on: false },
	{ key: 'aging', label: __('Overdue breakdown (days past due)'), on: false },
];
const COLS_KEY = 'ar_hub_columns';

const ICONS = {
	chevron: '<path d="m9 18 6-6-6-6"/>',
	down: '<path d="m6 9 6 6 6-6"/>',
	search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
	download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
	printer: '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect width="12" height="8" x="6" y="14"/>',
	refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
	columns: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="M15 3v18"/>',
	x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
	external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
	sheet: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M8 13h2"/><path d="M14 13h2"/><path d="M8 17h2"/><path d="M14 17h2"/>',
	file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
	filter: '<path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z"/>',
	inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
};
const icon = (name, size) => `<svg class="arh-ico" width="${size || 16}" height="${size || 16}" viewBox="0 0 24 24" fill="none"
	stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;

const esc = (s) => frappe.utils.escape_html(s == null ? '' : String(s));
const money = (n) => (n < 0 ? '-$' : '$') + Math.abs(n || 0).toLocaleString('en-US',
	{ minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money_short = (n) => {
	const a = Math.abs(n || 0);
	if (a >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
	if (a >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'k';
	return money(n);
};
const dash = '<span class="arh-nil">—</span>';
const cash = (n) => (Math.abs(n || 0) >= 0.005 ? money(n) : dash);
const nice_date = (d) => {
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || '');
	return m ? new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('en-US',
		{ month: 'short', day: 'numeric', year: 'numeric' }) : '';
};
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const options_html = (list, sel) => list.map((o) =>
	`<option value="${esc(o[0])}"${o[0] === sel ? ' selected' : ''}>${esc(o[1])}</option>`).join('');
const blank_filters = () => ({ search: '', segment: '', recon: '', level: '', status: '', age: '', min: '', hide_motley: false, bucket: '' });
const TERMS_BUCKET = '__terms__';

function load_cols() {
	const cols = {};
	COL_SETS.forEach((s) => { cols[s.key] = s.on; });
	try {
		Object.assign(cols, JSON.parse(localStorage.getItem(COLS_KEY) || '{}'));
	} catch (e) {  }
	return cols;
}

function save_cols(cols) {
	try { localStorage.setItem(COLS_KEY, JSON.stringify(cols)); } catch (e) {  }
}

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
		cols: load_cols(),
		open: {},
		detail: {},
		edits: {},
	};
	page.arh = hub;

	page.main.html(`
		<div class="arh">
			<div class="arh-top">
				<div class="arh-tabs" role="tablist" aria-label="${__('AR Mode')}">
					${['legacy', 'new', 'all'].map((m) => `<button type="button" role="tab" data-mode="${m}"
						class="arh-tab${m === hub.mode ? ' is-active' : ''}" aria-selected="${m === hub.mode}">${MODE_LABEL[m]}</button>`).join('')}
				</div>
				<select class="arh-input arh-company" data-k="company" aria-label="${__('Company')}">
					<option value="${ALL_COMPANIES}">${__('All Entities')}</option>
				</select>
				<div class="arh-spacer"></div>
				<select class="arh-input" data-k="group" aria-label="${__('Group by')}">${options_html(GROUPS, hub.group)}</select>
				<select class="arh-input" data-k="sort" aria-label="${__('Sort')}">${options_html(SORTS, hub.sort)}</select>
				<div class="arh-menu-wrap">
					<button type="button" class="arh-btn arh-btn-outline" data-menu="cols">${icon('columns')}${__('Columns')}</button>
					<div class="arh-menu" data-menu-for="cols" role="menu"></div>
				</div>
				<div class="arh-menu-wrap">
					<button type="button" class="arh-btn arh-btn-outline" data-menu="export">${icon('download')}${__('Export')}${icon('down', 14)}</button>
					<div class="arh-menu arh-menu-right" data-menu-for="export" role="menu">
						<button type="button" class="arh-menu-item" data-act="xlsx">${icon('sheet')}${__('Excel workbook')}<span>.xlsx</span></button>
						<button type="button" class="arh-menu-item" data-act="csv">${icon('file')}${__('CSV, grid only')}<span>.csv</span></button>
						<div class="arh-menu-sep"></div>
						<button type="button" class="arh-menu-item" data-act="print">${icon('printer')}${__('Print this view')}</button>
					</div>
				</div>
				<button type="button" class="arh-btn arh-btn-outline arh-btn-icon" data-act="refresh"
					title="${__('Refresh')}" aria-label="${__('Refresh')}">${icon('refresh')}</button>
			</div>

			<div class="arh-cards"></div>
			<div class="arh-aging"></div>

			<div class="arh-panel">
				<div class="arh-toolbar">
					<div class="arh-search">${icon('search')}
						<input type="text" data-f="search" placeholder="${__('Search customers…')}" aria-label="${__('Search customers')}"></div>
					<select class="arh-input arh-filter" data-f="segment" aria-label="${__('Segment')}"></select>
					<select class="arh-input arh-filter" data-f="recon" aria-label="${__('Recon Status')}"></select>
					<select class="arh-input arh-filter" data-f="level" aria-label="${__('Level')}"></select>
					<select class="arh-input arh-filter arh-wk-only" data-f="status" aria-label="${__('Weekly Status')}"></select>
					<select class="arh-input arh-filter" data-f="age" aria-label="${__('Oldest invoice')}">${options_html(AGES, '')}</select>
					<input type="number" class="arh-input arh-filter arh-min" data-f="min" min="0" step="1000"
						placeholder="${__('Min balance')}" aria-label="${__('Minimum balance')}">
					<label class="arh-toggle"><input type="checkbox" data-f="hide_motley">${__('Hide Motley')}</label>
					<button type="button" class="arh-btn arh-btn-ghost arh-reset" data-act="clear">${__('Reset')}${icon('x', 14)}</button>
				</div>
				<div class="arh-status"></div>
				<div class="arh-grid"><div class="arh-empty">${__('Loading receivables…')}</div></div>
			</div>
		</div>
	`);

	bind(hub);
	load(hub);
};

function load(hub) {
	const seq = ++hub.seq;
	if (hub.data) hub.page.main.find('.arh-status-text').text(__('Refreshing…'));
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
			hub.page.main.find('.arh-grid').html(`<div class="arh-empty">${__('Receivables could not be loaded.')}</div>`);
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

function books(r) { return r.ledgers || []; }
function wk(r, book) { return (r.weekly || {})[book] || { tier: 'upcoming', statuses: [], status: '', note: '' }; }

function primary_book(r) {
	let best = null;
	books(r).forEach((b) => {
		if (!best || TIER_RANK[wk(r, b).tier] > TIER_RANK[wk(r, best).tier]) best = b;
	});
	return best;
}

function segment_color(hub, seg) { return seg ? (hub.data.segment_colors[seg] || 'var(--arh-violet)') : ''; }
function recon_color(hub, status) {
	if (!status) return '';
	const own = (hub.data.recon_statuses || []).find((s) => s.value === status);
	return (own && own.color) || RECON_COLOR[status] || 'var(--arh-slate)';
}

function fill_options(hub) {
	const d = hub.data, m = hub.page.main, f = hub.f;

	if (d.companies.indexOf(hub.company) === -1) hub.company = ALL_COMPANIES;
	m.find('[data-k="company"]').html(options_html([[ALL_COMPANIES, __('All Entities')]].concat(d.companies.map((c) => [c, c])), hub.company));
	m.find('[data-f="segment"]').html(options_html([['', __('All segments')], ['__none__', d.unassigned_label]]
		.concat(d.segments.map((s) => [s, s])), f.segment));
	m.find('[data-f="recon"]').html(options_html([['', __('All recon statuses')], ['__none__', __('Recon not set')]]
		.concat(d.recon_statuses.map((s) => [s.value, s.label || s.value])), f.recon));
	m.find('[data-f="level"]').html(options_html([['', __('All levels')]].concat(TIER_ORDER.map((t) => [t, TIERS[t].label])), f.level));

	m.find('.arh-wk-only').toggle(!!d.can_weekly);
	m.find('[data-f="status"]').html(options_html([['', __('All weekly statuses')], ['__none__', __('No status yet')]]
		.concat(d.statuses.map((s) => [s, s])), f.status));
	if (!d.can_weekly) {
		f.status = '';
		if (hub.group === 'status') hub.group = 'tier';
	}
	m.find('[data-k="group"]').html(options_html(GROUPS.filter((g) => d.can_weekly || g[0] !== 'status'), hub.group));
}

function filters_active(hub) {
	return Object.keys(hub.f).some((k) => !!hub.f[k]);
}

function visible_rows(hub, keep_bucket = true) {
	const f = hub.f;
	const q = (f.search || '').trim().toLowerCase();
	const min = parseFloat(f.min) || 0;
	const age = parseInt(f.age, 10) || 0;
	return hub.data.rows.filter(function (r) {
		if (q && r.customer.toLowerCase().indexOf(q) === -1
			&& (r.customer_name || '').toLowerCase().indexOf(q) === -1) return false;
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
		if (keep_bucket && f.bucket
			&& !((f.bucket === TERMS_BUCKET ? r.on_terms : (r.buckets || {})[f.bucket]) > 0.005)) return false;
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

function keys_with_extras(keys, rows, value_of) {
	const out = keys.slice();
	rows.forEach((r) => { const v = value_of(r); if (v && out.indexOf(v) === -1) out.push(v); });
	return out;
}

function grouped(hub, rows) {
	const d = hub.data;
	let groups;
	if (hub.group === 'tier') {
		groups = TIER_ORDER.map((t) => ({ title: TIERS[t].full, desc: TIERS[t].desc, color: TIERS[t].color,
			rows: rows.filter((r) => r.tier === t) }));
	} else if (hub.group === 'segment') {
		groups = keys_with_extras([''].concat(d.segments), rows, (r) => r.segment).map((k) => ({
			title: k || d.unassigned_label, desc: k ? '' : __('No segment chosen yet.'),
			color: k ? segment_color(hub, k) : 'var(--arh-slate)',
			rows: rows.filter((r) => (r.segment || '') === k),
		}));
	} else if (hub.group === 'recon') {
		groups = keys_with_extras([''].concat(d.recon_statuses.map((s) => s.value)), rows, (r) => r.recon_status).map((k) => ({
			title: k || __('Recon status not set'), desc: '',
			color: k ? recon_color(hub, k) : 'var(--arh-slate)',
			rows: rows.filter((r) => (r.recon_status || '') === k),
		}));
	} else if (hub.group === 'status') {
		const status_of = (r) => wk(r, primary_book(r)).status || '';
		groups = keys_with_extras([''].concat(d.statuses), rows, status_of).map((k) => ({
			title: k || __('No status yet'), desc: k ? '' : __('Needs a status this week.'),
			color: k ? (STATUS_COLOR[k] || 'var(--arh-slate)') : 'var(--arh-slate)',
			rows: rows.filter((r) => status_of(r) === k),
		}));
	} else {
		groups = [{ title: null, rows: rows }];
	}
	groups = groups.filter((g) => g.rows.length);
	groups.forEach((g) => sort_rows(g.rows, hub.sort));
	return groups;
}

function col_set_applies(hub, key) {
	if (key === 'book') return hub.data.ar_mode === 'all';
	if (key === 'weekly') return !!hub.data.can_weekly;
	return true;
}

function columns(hub) {
	const d = hub.data;
	const on = (k) => hub.cols[k] && col_set_applies(hub, k);
	const cols = [
		{ k: 'customer', label: __('Customer') },
		{ k: 'level', label: __('Level'), tip: __('Debt level of the most overdue invoice') },
		{ k: 'outstanding', label: __('Outstanding'), num: true, sum: (r) => r.outstanding, tip: __('Unpaid balance on open invoices') },
		{ k: 'overdue', label: __('Overdue'), num: true, sum: (r) => r.overdue, tip: __('Past the due date') },
		{ k: 'on_terms', label: __('On terms'), num: true, sum: (r) => r.on_terms, tip: __('Not yet due') },
	];
	if (on('book')) {
		cols.push({ k: 'legacy', label: __('Legacy AR'), num: true, sum: (r) => r.legacy_ar, tip: __('Invoices up to {0}', [nice_date(d.legacy_cutoff)]) },
			{ k: 'new', label: __('New AR'), num: true, sum: (r) => r.new_ar, tip: __('Invoices from {0}', [nice_date(d.new_ar_start)]) });
	}
	if (on('billing')) {
		cols.push({ k: 'invoiced', label: __('Invoiced'), num: true, sum: (r) => r.invoiced, tip: __('Total of the open invoices') },
			{ k: 'paid', label: __('Paid'), num: true, sum: (r) => r.paid, tip: __('Already paid on the open invoices') });
	}
	cols.push({ k: 'oldest', label: __('Oldest invoice'), tip: __('Posting date of the oldest unpaid invoice') });
	if (on('weekly')) {
		cols.push({ k: 'wstatus', label: __('Weekly status'), tip: __('Latest AR Accountability status, per book') });
	}
	if (on('account')) {
		cols.push({ k: 'segment', label: __('Segment'), tip: __('Whose relationship the account is (Categorized AR)') },
			{ k: 'recon', label: __('Recon status') });
	}
	if (on('flags')) {
		cols.push({ k: 'onboarding', label: __('Onboarding') },
			{ k: 'company_made_contact', label: __('Company made contact') });
	}
	if (on('weekly')) cols.push({ k: 'wnote', label: __('Latest note') });
	if (on('terms')) {
		d.terms.forEach((t) => cols.push({ k: 'term-' + t.key, kicker: __('On terms'), label: __('{0} days left', [t.label]),
			num: true, sum: (r) => r.terms[t.key] }));
	}
	if (on('aging')) {
		d.overdue.forEach((b) => cols.push({ k: 'od-' + b.tier, kicker: __('Overdue'), label: b.label,
			num: true, sum: (r) => r.buckets[b.label] }));
	}
	return cols;
}

function pick_html(kind, field, r, value, options, color, editable, printing) {
	const label = (options.find((o) => o[0] === (value || '')) || [value, value])[1] || '—';
	const style = value && color ? ` style="--c:${esc(color)}"` : '';
	const empty = value ? '' : ' is-empty';
	if (!editable || printing) {
		return `<span class="arh-badge${empty}"${style}>${esc(label)}</span>`;
	}
	return `<select class="arh-pick arh-inline${empty}" data-kind="${kind}" data-field="${field}"
		data-customer="${esc(r.customer)}"${style} title="${esc(label)}">${options_html(options, value || '')}</select>`;
}

function field_options(hub, kind, r) {
	const d = hub.data;
	if (kind === 'segment') {
		return [['', d.unassigned_label]].concat(keys_with_extras(d.segments, [r], (x) => x.segment).map((s) => [s, s]));
	}
	if (kind === 'recon') {
		return [['', __('Not set')]].concat(keys_with_extras(d.recon_statuses.map((s) => s.value), [r], (x) => x.recon_status).map((s) => [s, s]));
	}
	return [['', '—'], ['Yes', __('Yes')], ['No', __('No')]];
}

function field_pick(hub, kind, field, r, printing) {
	const d = hub.data;
	const value = r[field] || '';
	const color = kind === 'segment' ? segment_color(hub, value) : kind === 'recon' ? recon_color(hub, value) : FLAG_COLOR[value];
	const editable = kind === 'segment' ? d.can_edit_segment : d.can_edit_recon;
	return pick_html(kind, field, r, value, field_options(hub, kind, r), color, editable, printing);
}

function level_badge(tier) {
	return `<span class="arh-badge arh-badge-solid t-${tier}">${TIERS[tier].label}</span>`;
}

function cell(hub, c, r, printing) {
	switch (c.k) {
	case 'customer': {
		const open = !printing && hub.open[r.customer];
		return `<td class="c-customer"><div class="arh-cust">
			${printing ? '' : `<span class="arh-chev${open ? ' is-open' : ''}">${icon('chevron', 14)}</span>`}
			<div class="arh-cust-text">
				<div class="arh-cname">${esc(r.customer_name)}${printing ? '' : `<a class="arh-ext" href="/app/customer/${encodeURIComponent(r.customer)}"
					target="_blank" rel="noopener" title="${__('Open customer')}">${icon('external', 13)}</a>`}</div>
				<div class="arh-sub">${plural(r.invoice_count, __('invoice'), __('invoices'))} · ${esc(r.companies.join(', '))}</div>
			</div></div></td>`;
	}
	case 'level':
		return `<td class="c-level">${level_badge(r.tier)}${r.worst ? `<div class="arh-sub">${esc(r.worst)}</div>` : ''}</td>`;
	case 'oldest': {
		const cls = r.age_days >= 365 ? ' is-old' : r.age_days >= 180 ? ' is-aging' : '';
		return `<td class="c-oldest">${esc(nice_date(r.oldest))}<div class="arh-sub${cls}">${plural(r.age_days, __('day'), __('days'))}</div></td>`;
	}
	case 'segment':
		return `<td class="c-pick">${field_pick(hub, 'segment', 'segment', r, printing)}</td>`;
	case 'recon':
		return `<td class="c-pick">${field_pick(hub, 'recon', 'recon_status', r, printing)}</td>`;
	case 'onboarding':
	case 'company_made_contact':
		return `<td class="c-pick">${field_pick(hub, 'flag', c.k, r, printing)}</td>`;
	case 'wstatus':
	case 'wnote': {
		const bs = books(r);
		return `<td class="c-${c.k}">${bs.map((b) => {
			const w = wk(r, b);
			const tag = bs.length > 1 ? `<span class="arh-book">${b === BOOK_NEW ? __('New') : __('Legacy')}</span>` : '';
			if (c.k === 'wnote') {
				return `<div class="arh-line" title="${esc(w.note)}">${tag}<span class="arh-note">${w.note ? esc(w.note) : dash}</span></div>`;
			}
			const badge = w.status
				? `<span class="arh-badge" style="--c:${esc(STATUS_COLOR[w.status] || 'var(--arh-slate)')}">${esc(w.status)}</span>`
				: `<span class="arh-badge is-empty is-dashed">${__('No status yet')}</span>`;
			return `<div class="arh-line">${tag}${badge}</div>`;
		}).join('')}</td>`;
	}
	default:
		return `<td class="c-num c-${c.k}">${cash(c.sum(r))}</td>`;
	}
}

function sync_filter_ui(hub) {
	const m = hub.page.main;
	m.find('[data-f]').each(function () {
		const set = this.type === 'checkbox' ? this.checked : !!$(this).val();
		$(this).toggleClass('is-set', set);
		if (this.type === 'checkbox') $(this).closest('.arh-toggle').toggleClass('is-set', set);
	});
	m.find('.arh-reset').toggle(filters_active(hub));
	m.find('.arh-tab').each(function () {
		const on = $(this).attr('data-mode') === hub.mode;
		$(this).toggleClass('is-active', on).attr('aria-selected', on ? 'true' : 'false');
	});
}

function render(hub) {
	const d = hub.data;
	if (!d) return;
	sync_filter_ui(hub);
	const rows = visible_rows(hub);
	const groups = grouped(hub, rows);
	hub.shown = [].concat.apply([], groups.map((g) => g.rows));

	const m = hub.page.main;
	const company_label = hub.company === ALL_COMPANIES ? __('All Entities') : hub.company;
	m.find('.arh-status').html(`
		<span class="arh-status-text">${__('Showing {0} of {1}', [`<b>${rows.length}</b>`, plural(d.rows.length, __('customer'), __('customers'))])}
			· ${esc(MODE_LABEL[d.ar_mode])} · ${esc(company_label)} · ${__('as of {0}', [esc(nice_date(d.as_of))])}</span>
		<span class="arh-hint">${d.can_weekly ? __('Click a customer for invoices, account fields and this week\'s entry.')
		: __('Click a customer for invoices and account fields.')}</span>`);
	m.find('.arh-cards').html(cards_html(hub, rows));
	m.find('.arh-aging').html(aging_html(hub, visible_rows(hub, false)));

	const $grid = m.find('.arh-grid');
	const $old = $grid.find('.arh-wrap');
	const scroll = $old.length ? [$old.scrollTop(), $old.scrollLeft()] : [0, 0];

	if (!rows.length) {
		$grid.html(`<div class="arh-empty">${icon('inbox', 28)}
			<b>${d.rows.length ? __('No customers match these filters') : __('No outstanding receivables')}</b>
			${d.rows.length ? `<button type="button" class="arh-btn arh-btn-outline" data-act="clear">${__('Reset filters')}</button>` : ''}
		</div>`);
		return;
	}
	$grid.html(`<div class="arh-wrap">${table_html(hub, groups, false)}</div>`);

	const $wrap = $grid.find('.arh-wrap');
	$wrap.scrollTop(scroll[0]).scrollLeft(scroll[1]);
	freeze($wrap);
	Object.keys(hub.open).forEach((c) => { if (hub.open[c]) fetch_detail(hub, c); });
}

function freeze($wrap) {
	let top = 0;
	$wrap.children('table').children('thead').children('tr').each(function () {
		$(this).children().css('top', top + 'px');
		top += this.getBoundingClientRect().height;
	});
	const w = $wrap[0].clientWidth;
	if (w) $wrap.find('.arh-detail-in').css('width', (w - 1) + 'px');
}

function table_html(hub, groups, printing) {
	const d = hub.data;
	const cols = columns(hub);
	const all_rows = [].concat.apply([], groups.map((g) => g.rows));
	const n_inv = all_rows.reduce((s, r) => s + r.invoice_count, 0);

	const head = cols.map((c) => `<th class="c-${c.k}${c.num ? ' is-num' : ''}"${c.tip ? ` title="${esc(c.tip)}"` : ''}>
		${c.kicker ? `<span class="arh-kicker">${esc(c.kicker)}</span>` : ''}${esc(c.label)}</th>`).join('');
	const totals = cols.map((c, i) => {
		if (i === 0) {
			return `<td class="c-customer"><div class="arh-total-label">${__('Total')}</div>
				<div class="arh-sub">${plural(all_rows.length, __('customer'), __('customers'))} · ${plural(n_inv, __('invoice'), __('invoices'))}</div></td>`;
		}
		if (!c.sum) return '<td></td>';
		return `<td class="c-num c-${c.k}">${cash(all_rows.reduce((s, r) => s + (c.sum(r) || 0), 0))}</td>`;
	}).join('');

	let body = '';
	groups.forEach((g) => {
		if (g.title !== null) {
			const amt = g.rows.reduce((s, r) => s + r.outstanding, 0);
			body += `<tr class="arh-grp" style="--c:${esc(g.color)}"><td colspan="${cols.length}"><div class="arh-grp-in">
				<span class="arh-dot"></span><span class="arh-grp-title">${esc(g.title)}</span>
				${g.desc ? `<span class="arh-grp-desc">${esc(g.desc)}</span>` : ''}
				<span class="arh-count">${g.rows.length}</span>
				<span class="arh-grp-amt">${money(amt)}</span>
			</div></td></tr>`;
		}
		g.rows.forEach((r) => {
			const open = !printing && hub.open[r.customer];
			body += `<tr class="arh-row${open ? ' is-open' : ''}" data-customer="${esc(r.customer)}">
				${cols.map((c) => cell(hub, c, r, printing)).join('')}</tr>`;
			if (open) {
				body += `<tr class="arh-detail"><td colspan="${cols.length}"><div class="arh-detail-in">${detail_html(hub, r)}</div></td></tr>`;
			}
		});
	});

	return `<table class="arh-table${d.ar_mode === 'new' ? ' is-new-mode' : ''}">
		<thead><tr class="arh-head">${head}</tr><tr class="arh-totals">${totals}</tr></thead>
		<tbody>${body}</tbody>
	</table>`;
}

function cards_html(hub, rows) {
	const d = hub.data;
	const sum = (list, k) => list.reduce((s, r) => s + (r[k] || 0), 0);
	const outstanding = sum(rows, 'outstanding');
	const overdue = sum(rows, 'overdue');
	const lvl3 = rows.filter((r) => r.tier === 'level3');
	const unfiled = rows.filter((r) => !r.segment);
	const cards = [
		{ label: __('Total outstanding'), value: money(outstanding),
			sub: `${plural(rows.length, __('customer'), __('customers'))} · ${money_short(sum(rows, 'invoiced'))} ${__('invoiced')}, ${money_short(sum(rows, 'paid'))} ${__('paid')}` },
		{ label: __('Overdue'), tone: 'red', value: money(overdue),
			sub: __('{0}% of outstanding', [outstanding ? (overdue / outstanding * 100).toFixed(1) : '0.0']) },
		{ label: __('On terms'), tone: 'green', value: money(sum(rows, 'on_terms')), sub: __('Not yet due') },
		{ label: __('Level 3 · 60+ days'), tone: 'red', value: money(sum(lvl3, 'outstanding')),
			sub: plural(lvl3.length, __('customer'), __('customers')), quick: ['level', 'level3'] },
		{ label: __('No segment'), tone: 'violet', value: money(sum(unfiled, 'outstanding')),
			sub: plural(unfiled.length, __('customer needs an owner'), __('customers need an owner')), quick: ['segment', '__none__'] },
	];
	if (d.can_weekly) {
		const unfiled_wk = rows.filter((r) => books(r).some((b) => !wk(r, b).status));
		cards.push({ label: __('No weekly status'), tone: 'amber', value: money(sum(unfiled_wk, 'outstanding')),
			sub: `${plural(unfiled_wk.length, __('customer'), __('customers'))} · ${__('this week')}`,
			quick: ['status', '__none__'] });
	}
	return cards.map((c) => {
		const active = c.quick && hub.f[c.quick[0]] === c.quick[1];
		const tag = c.quick ? 'button' : 'div';
		const attrs = c.quick ? ` type="button" data-quick-f="${c.quick[0]}" data-quick-v="${c.quick[1]}" aria-pressed="${active}"` : '';
		return `<${tag} class="arh-card${c.tone ? ' tone-' + c.tone : ''}${c.quick ? ' is-quick' : ''}${active ? ' is-active' : ''}"${attrs}>
			<span class="arh-card-label">${esc(c.label)}${c.quick ? `<span class="arh-card-act">${active ? __('Showing') + icon('x', 12) : icon('filter', 12) + __('Show')}</span>` : ''}</span>
			<span class="arh-card-value">${c.value}</span>
			<span class="arh-card-sub">${esc(c.sub)}</span>
		</${tag}>`;
	}).join('');
}

function aging_html(hub, rows) {
	const d = hub.data;
	const amount = (r, key) => (key === TERMS_BUCKET ? r.on_terms : (r.buckets || {})[key]) || 0;
	const per_tier = {};
	d.overdue.forEach((b) => { per_tier[b.tier] = (per_tier[b.tier] || 0) + 1; });
	const seen = {};
	const tiles = [{ key: TERMS_BUCKET, label: __('On terms'), unit: __('not yet due'), tier: 'upcoming', shade: 100 }]
		.concat(d.overdue.map((b) => {
			seen[b.tier] = (seen[b.tier] || 0) + 1;
			const n = per_tier[b.tier];
			return { key: b.label, label: b.label, unit: __('overdue'), tier: b.tier,
				shade: n > 1 ? Math.round(55 + 45 * (seen[b.tier] - 1) / (n - 1)) : 100 };
		}));
	tiles.forEach((t) => {
		const holders = rows.filter((r) => amount(r, t.key) > 0.005);
		t.amt = holders.reduce((s, r) => s + amount(r, t.key), 0);
		t.n = holders.length;
		t.color = `color-mix(in srgb, ${TIERS[t.tier].color} ${t.shade}%, var(--arh-bg))`;
	});
	const total = tiles.reduce((s, t) => s + t.amt, 0);
	const pct = (v) => (total ? (v / total) * 100 : 0);
	const active = hub.f.bucket;

	const bar = total ? tiles.filter((t) => pct(t.amt) >= 0.3).map((t) => `<span class="arh-agebar-seg"
		style="width:${pct(t.amt).toFixed(2)}%;background:${t.color}"
		title="${esc(t.label)}: ${money(t.amt)} (${pct(t.amt).toFixed(1)}%)">${pct(t.amt) >= 7 ? `${pct(t.amt).toFixed(0)}%` : ''}</span>`).join('')
		: `<span class="arh-agebar-seg is-empty" style="width:100%"></span>`;

	const tile_html = tiles.map((t) => {
		const on = active === t.key;
		return `<button type="button" class="arh-agetile${on ? ' is-active' : ''}${t.amt ? '' : ' is-zero'}" data-bucket="${esc(t.key)}"
			aria-pressed="${on}" style="--arh-age:${t.color};--arh-age-fg:${TIERS[t.tier].color}"
			title="${on ? __('Showing these customers — click to clear') : __('Show customers with a balance here')}">
			<span class="arh-agetile-label">${esc(t.label)}<small>${esc(t.unit)}</small></span>
			<span class="arh-agetile-value">${t.amt ? money(t.amt) : dash}</span>
			<span class="arh-agetile-sub">${t.amt ? `${pct(t.amt).toFixed(1)}% · ${plural(t.n, __('customer'), __('customers'))}` : '&nbsp;'}</span>
		</button>`;
	}).join('');

	const active_tile = tiles.find((t) => t.key === active);
	return `<div class="arh-aging-card">
		<div class="arh-aging-head">
			<span class="arh-aging-title">${__('Aging breakdown')}</span>
			<span class="arh-aging-meta">${active_tile
				? `${__('Grid shows customers with a balance in {0}', [`<b>${esc(active_tile.label)}${active_tile.key === TERMS_BUCKET ? '' : ' ' + __('overdue')}</b>`])}
					<button type="button" class="arh-btn arh-btn-ghost arh-aging-clear" data-bucket="${esc(active)}">${__('Clear')}${icon('x', 12)}</button>`
				: `${money(total)} · ${plural(rows.length, __('customer'), __('customers'))}`}</span>
		</div>
		<div class="arh-agebar" role="img" aria-label="${__('Aging distribution')}">${bar}</div>
		<div class="arh-agetiles">${tile_html}</div>
	</div>`;
}

function detail_html(hub, r) {
	const d = hub.data;
	const det = hub.detail[r.customer];
	const loaded = det && typeof det === 'object';
	const paid = loaded ? det.paid_invoices : [];
	const show_book = d.ar_mode === 'all';

	const inv_row = (i, is_paid) => `<tr${is_paid ? ' class="is-paid"' : ''}>
		<td><a class="arh-link" href="/app/sales-invoice/${encodeURIComponent(i.name)}" target="_blank" rel="noopener">${esc(i.name)}</a></td>
		<td class="arh-muted">${esc(i.company)}</td>
		${show_book ? `<td class="arh-muted">${esc(i.ledger)}</td>` : ''}
		<td>${esc(nice_date(i.posting_date))}</td>
		<td>${esc(nice_date(i.due_date))}</td>
		<td>${is_paid ? `<span class="arh-badge" style="--c:var(--arh-green)">${__('Paid')}</span>`
		: `<span class="arh-badge t-${i.tier}">${esc(i.aging)}</span>`}</td>
		<td class="is-num">${money(i.invoiced)}</td>
		<td class="is-num">${money(is_paid ? i.invoiced : i.paid)}</td>
		<td class="is-num arh-strong">${is_paid ? dash : money(i.outstanding)}</td>
	</tr>`;
	const total = (k) => r.invoices.reduce((s, i) => s + i[k], 0);
	const paid_note = det === 'loading' ? __('loading paid invoices…') : det === 'error'
		? __('paid invoices could not be loaded') : plural(paid.length, __('paid'), __('paid'));
	const inv_html = `<section class="arh-dcard is-wide">
		<header><h4>${__('Invoices')}</h4><p>${plural(r.invoices.length, __('open'), __('open'))} · ${esc(paid_note)}</p></header>
		<div class="arh-dscroll"><table class="arh-dtable"><thead><tr>
			<th>${__('Invoice')}</th><th>${__('Company')}</th>${show_book ? `<th>${__('Book')}</th>` : ''}
			<th>${__('Posted')}</th><th>${__('Due')}</th><th>${__('Aging')}</th>
			<th class="is-num">${__('Invoiced')}</th><th class="is-num">${__('Paid')}</th><th class="is-num">${__('Outstanding')}</th>
		</tr></thead>
		<tbody>${r.invoices.map((i) => inv_row(i, false)).join('')}${paid.map((i) => inv_row(i, true)).join('')}</tbody>
		<tfoot><tr><td colspan="${show_book ? 6 : 5}">${__('Open total')}</td>
			<td class="is-num">${money(total('invoiced'))}</td><td class="is-num">${money(total('paid'))}</td>
			<td class="is-num">${money(total('outstanding'))}</td></tr></tfoot>
		</table></div>
	</section>`;

	const fld = (label, html) => `<div class="arh-field"><label>${esc(label)}</label>${html}</div>`;
	const acct_html = `<section class="arh-dcard">
		<header><h4>${__('Account')}</h4><p>${d.can_edit_recon || d.can_edit_segment
		? __('Changes save as soon as you pick them.') : __('Read only for your role.')}</p></header>
		<div class="arh-dbody arh-form">
			${fld(__('Segment'), field_pick(hub, 'segment', 'segment', r))}
			${fld(__('Recon status'), field_pick(hub, 'recon', 'recon_status', r))}
			${fld(__('Onboarding'), field_pick(hub, 'flag', 'onboarding', r))}
			${fld(__('Company made contact'), field_pick(hub, 'flag', 'company_made_contact', r))}
			<label class="arh-check arh-span"><input type="checkbox" class="arh-newar" data-customer="${esc(r.customer)}"
				${r.new_ar_available ? 'checked' : ''}${d.can_edit_recon ? '' : ' disabled'}>${__('New AR available')}</label>
			<div class="arh-field arh-span"><label>${__('Notebox')}</label>${d.can_edit_recon
		? `<textarea class="arh-input arh-notebox" data-customer="${esc(r.customer)}" placeholder="${__('Saved when you click away')}">${esc(r.notebox)}</textarea>`
		: `<div class="arh-ro-text">${r.notebox ? esc(r.notebox) : dash}</div>`}</div>
		</div>
	</section>`;

	if (!d.can_weekly) return `<div class="arh-detail-grid">${inv_html}${acct_html}</div>`;

	const e = hub.edits[r.customer] || {};
	const bs = books(r);
	const book = bs.indexOf(e.book) !== -1 ? e.book : primary_book(r);
	const w = wk(r, book);
	const tier = TIERS[w.tier] || TIERS.upcoming;
	const text = (role, label, input) => fld(label, input
		? `<input type="text" class="arh-input" data-role="${role}" data-customer="${esc(r.customer)}" value="${esc(e[role] || '')}">`
		: `<textarea class="arh-input" data-role="${role}" data-customer="${esc(r.customer)}">${esc(e[role] || '')}</textarea>`);
	const entry_html = `<section class="arh-dcard">
		<header><h4>${__('This week\'s entry')}</h4><p>${__('Week of {0}', [esc(nice_date(d.week_of))])} · ${__('adds a new entry, never overwrites')}</p></header>
		<div class="arh-dbody">
			<div class="arh-form">
				${bs.length > 1 ? fld(__('Book'), `<select class="arh-input" data-role="book" data-customer="${esc(r.customer)}">
					${options_html(bs.map((b) => [b, b]), book)}</select>`) : ''}
				<div class="arh-field"><label>${__('Status')} ${level_badge(w.tier)}</label>
					<select class="arh-input" data-role="status" data-customer="${esc(r.customer)}">
						${options_html([['', __('Pick a status…')]].concat(w.statuses.map((s) => [s, s])), e.status || '')}
					</select></div>
				${w.tier !== 'upcoming' ? `<label class="arh-check arh-span"><input type="checkbox" data-role="call" data-customer="${esc(r.customer)}"${e.call ? ' checked' : ''}>
					${__('Need three-way call with finance')}</label>` : ''}
				<div class="arh-span">${text('qa', tier.q)}</div>
				${text('plan', __('What is the plan?'))}
				${text('notes', __('Notes'))}
				${text('contact', __('Contact info'), true)}
				${text('email', __('Email'), true)}
			</div>
			<div class="arh-dfoot">
				<button type="button" class="arh-btn arh-btn-primary arh-save-week" data-customer="${esc(r.customer)}">${__('Save entry for {0}', [esc(book)])}</button>
			</div>
		</div>
	</section>`;

	const log = loaded ? det.log || [] : null;
	const span = show_book ? 8 : 7;
	const log_rows = log === null
		? `<tr><td colspan="${span}" class="arh-muted">${det === 'error' ? __('Could not load.') : __('Loading…')}</td></tr>`
		: !log.length ? `<tr><td colspan="${span}" class="arh-muted">${__('No weekly entries yet — this will be the first.')}</td></tr>`
			: log.map((x) => `<tr>
				<td class="arh-strong">${esc(nice_date(x.week_of))}</td>
				${show_book ? `<td class="arh-muted">${esc(x.ledger)}</td>` : ''}
				<td><span class="arh-badge" style="--c:${esc(STATUS_COLOR[x.status] || 'var(--arh-slate)')}">${esc(x.status || '')}</span></td>
				<td class="is-wrap">${esc(x.qa || '')}</td>
				<td class="is-wrap">${esc(x.plan || '')}</td>
				<td class="is-wrap">${esc(x.notes || '')}</td>
				<td class="is-wrap">${esc(x.contact || '')}${x.email ? ' · ' + esc(x.email) : ''}${x.need_three_way_call ? ' · ' + __('3-way call') : ''}</td>
				<td class="arh-muted">${esc(x.owner || '')}</td>
			</tr>`).join('');
	const log_html = `<section class="arh-dcard is-wide">
		<header><h4>${__('Entry history')}</h4><p>${log && log.length ? plural(log.length, __('entry'), __('entries')) + ' · ' : ''}${__('most recent first')}</p></header>
		<div class="arh-dscroll"><table class="arh-dtable"><thead><tr>
			<th>${__('Week of')}</th>${show_book ? `<th>${__('Book')}</th>` : ''}<th>${__('Status')}</th>
			<th>${__('What is going on?')}</th><th>${__('Plan')}</th><th>${__('Notes')}</th><th>${__('Contact')}</th><th>${__('Filed by')}</th>
		</tr></thead><tbody>${log_rows}</tbody></table></div>
	</section>`;

	return `<div class="arh-detail-grid">${inv_html}${entry_html}${acct_html}${log_html}</div>`;
}

function cols_menu_html(hub) {
	return `<div class="arh-menu-label">${__('Show columns')}</div>
		${COL_SETS.filter((s) => !hub.data || col_set_applies(hub, s.key)).map((s) => `<label class="arh-menu-item arh-menu-check">
			<input type="checkbox" data-col="${s.key}"${hub.cols[s.key] ? ' checked' : ''}>${esc(s.label)}</label>`).join('')}
		<div class="arh-menu-sep"></div>
		<button type="button" class="arh-menu-item" data-cols-reset>${__('Reset to default')}</button>`;
}

function close_menus(hub) {
	hub.page.main.find('.arh-menu').removeClass('is-open');
	hub.page.main.find('[data-menu]').attr('aria-expanded', 'false');
}

function bind(hub) {
	const m = hub.page.main;

	m.on('click', '.arh-tab', function () {
		const mode = $(this).attr('data-mode');
		if (mode === hub.mode) return;
		hub.mode = mode;
		hub.detail = {};
		sync_filter_ui(hub);
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
		else sync_filter_ui(hub);
	});

	m.on('click', '.arh-agetile[data-bucket], .arh-aging-clear[data-bucket]', function () {
		const b = $(this).attr('data-bucket');
		hub.f.bucket = hub.f.bucket === b ? '' : b;
		render(hub);
	});

	m.on('click', '.arh-card[data-quick-f]', function () {
		const f = $(this).attr('data-quick-f');
		const v = $(this).attr('data-quick-v');
		hub.f[f] = hub.f[f] === v ? '' : v;
		m.find(`[data-f="${f}"]`).val(hub.f[f]);
		render(hub);
	});

	m.on('click', '[data-menu]', function (e) {
		e.stopPropagation();
		const k = $(this).attr('data-menu');
		const $menu = m.find(`.arh-menu[data-menu-for="${k}"]`);
		const was_open = $menu.hasClass('is-open');
		close_menus(hub);
		if (was_open) return;
		if (k === 'cols') $menu.html(cols_menu_html(hub));
		$menu.addClass('is-open');
		$(this).attr('aria-expanded', 'true');
	});
	m.on('click', '.arh-menu', (e) => e.stopPropagation());
	$(document).on('click.arh-menu', () => close_menus(hub));
	$(document).on('keydown.arh-menu', (e) => { if (e.key === 'Escape') close_menus(hub); });

	m.on('change', '[data-col]', function () {
		hub.cols[$(this).attr('data-col')] = this.checked;
		save_cols(hub.cols);
		render(hub);
	});
	m.on('click', '[data-cols-reset]', function () {
		COL_SETS.forEach((s) => { hub.cols[s.key] = s.on; });
		save_cols(hub.cols);
		m.find('.arh-menu[data-menu-for="cols"]').html(cols_menu_html(hub));
		render(hub);
	});

	m.on('click', '[data-act]', function () {
		const act = $(this).attr('data-act');
		close_menus(hub);
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

	m.on('input change', '.arh-detail [data-role]', function () {
		const customer = $(this).attr('data-customer');
		const role = $(this).attr('data-role');
		const e = (hub.edits[customer] = hub.edits[customer] || {});
		e[role] = this.type === 'checkbox' ? this.checked : $(this).val();
		if (role === 'book') {
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
	const rows = visible_rows(hub);
	const groups = grouped(hub, rows);
	if (!groups.length) {
		frappe.msgprint(__('Nothing to print — no customers in view.'));
		return;
	}
	let styles = '';
	document.querySelectorAll('style').forEach((st) => { if (/\.arh/.test(st.textContent)) styles += st.outerHTML; });
	const html = `<!doctype html><html><head><meta charset="utf-8"><title>${__('AR Hub')}</title>${styles}
		<style>
			@page { size: landscape; margin: 8mm; }
			body { margin: 0; font-family: Inter, Arial, sans-serif; }
			.arh-wrap { max-height: none; overflow: visible; }
			.arh-table th, .arh-table td { position: static !important; padding: 4px 6px; font-size: 9px; }
			.arh-cards { grid-template-columns: repeat(6, 1fr); }
			.arh-card { padding: 8px 10px; box-shadow: none; }
			.arh-card-value { font-size: 14px; }
			.arh-card-act { display: none; }
			h2 { margin: 0 0 4px; font-size: 16px; }
			* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		</style></head><body><div class="arh">
		<h2>${__('AR Hub')}</h2>
		<div class="arh-status">${esc(hub.page.main.find('.arh-status-text').text())}</div>
		<div class="arh-cards">${cards_html(hub, rows)}</div>
		<div class="arh-panel"><div class="arh-wrap">${table_html(hub, groups, true)}</div></div>
		</div></body></html>`;
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
