// Wash Plan Board: the single screen for planning washes. Layout follows motley-wash-production-plan-demo.html.
// All rules (stock allocation, blocking, yields, MR creation) run on the server; this file only renders and calls.
const WPB_M = 'cannabis_management.cannabis_management.page.wash_plan_board.wash_plan_board.';
const LB_KG = 0.453592;
const WPB_LIVE_DOCTYPES = ['Wash Production Plan', 'Material Request', 'Work Order', 'Stock Entry'];

const WPB_PILLS = {
	'Planned': ['#f1ecf7', '#4a3f5c'],
	'MR Created': ['#E3EDFA', '#1E4E8C'],
	'Washed': ['#FBEBD9', '#8A4508'],
	'Completed': ['#f3e6fb', '#4d129e'],
	'Skipped': ['#f1ecf7', '#6b6080'],
	'Draft': ['#f1ecf7', '#4a3f5c'],
	'In Progress': ['#FBEBD9', '#8A4508'],
	'Cancelled': ['#FDE8E1', '#9A3412'],
	'Not saved': ['#f7f3fc', '#6b6080'],
	'All plans': ['#E3EDFA', '#1E4E8C'],
};

const WPB_SVG = {
	check: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
	x: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
	minus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14"/></svg>',
	plus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
	trash: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>',
	cal: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></svg>',
	info: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
	warn: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
	chev: rot => '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="transform:' + rot + '"><path d="m9 6 6 6-6 6"/></svg>',
};

const wpb_esc = v => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const wpb_fmt = n => Math.round(n || 0).toLocaleString('en-US');
const wpb_lbs = n => (Math.round((n || 0) * 10) / 10).toLocaleString('en-US');
const wpb_pct = n => (Math.round((n || 0) * 100) / 100).toLocaleString('en-US') + '%';
const wpb_words = n => n + (n === 1 ? ' wash' : ' washes');
const WPB_WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const WPB_MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function wpb_day(key) {
	const d = new Date(key + 'T00:00:00');
	if (!key || isNaN(d.getTime())) return { key, short: '—', md: '—', label: '—', year: '' };
	const md = WPB_MO[d.getMonth()] + ' ' + d.getDate();
	return { key, short: WPB_WD[d.getDay()], md, label: WPB_WD[d.getDay()] + ', ' + md, year: d.getFullYear() };
}

function wpb_key(d) {
	return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function wpb_range(from, to) {
	const out = [];
	if (!from || !to) return out;
	const d = new Date(from + 'T00:00:00'), end = new Date(to + 'T00:00:00');
	while (d <= end && out.length < 62) { out.push(wpb_day(wpb_key(d))); d.setDate(d.getDate() + 1); }
	return out;
}

function wpb_period(from, to) {
	if (!from || !to) return '—';
	const a = wpb_day(from), b = wpb_day(to);
	if (from === to) return a.label + ', ' + a.year;
	return a.md + (a.year !== b.year ? ', ' + a.year : '') + ' – ' + b.md + ', ' + b.year;
}

function wpb_opts(list, sel) {
	return list.map(o => '<option value="' + wpb_esc(o.key) + '"' + (String(o.key) === String(sel == null ? '' : sel) ? ' selected' : '') + '>' + wpb_esc(o.label) + '</option>').join('');
}

frappe.pages['wash-plan-board'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Wash Plan Board'), single_column: true });
	$(wrapper).addClass('wash-plan-board-page');
	const root = $('<div class="wash-plan-board"><div class="wpb-loading">' + __('Loading…') + '</div></div>').appendTo(page.main);
	wrapper.wpb = new WashPlanBoard(root[0]);
};

frappe.pages['wash-plan-board'].on_page_show = function (wrapper) {
	wrapper.wpb && wrapper.wpb.route();
};

class WashPlanBoard {
	constructor(el) {
		this.el = el;
		this.ctx = null;
		this.board = null;
		this.scope = null;
		this.view = null;
		this.draft = null;
		this.day = 'all';
		this.filters = { freezer: 'all', project: 'all', item: 'all' };
		this.expanded = {};
		this.fzOpen = {};
		this.rowErr = {};
		this.toast = null;
		this.form = { date: '', item: '', freezer: '', project: '', lbs: '50' };
		this.formError = '';
		this.preview = null;
		this.saving = 0;
		this.saveState = '';
		this.queue = Promise.resolve();
		this.timers = {};
		this.lastWrite = 0;
		this.pending = 0;
		this.dirty = false;
		this.updatedAt = null;
		this.bind();
		// live: refresh when a plan, MR, Work Order or Stock Entry changes anywhere, plus a slow poll for other stock moves
		frappe.realtime.on('list_update', d => this.on_change(d));
		frappe.realtime.on('doc_update', d => this.on_change(d));
		this.subscribe();
		setInterval(() => this.tick(), 60000);
		document.addEventListener('visibilitychange', () => {
			if (document.visibilityState === 'visible' && this.updatedAt && Date.now() - this.updatedAt > 30000) this.tick();
		});
	}

	subscribe() {
		WPB_LIVE_DOCTYPES.forEach(dt => frappe.realtime.doctype_subscribe && frappe.realtime.doctype_subscribe(dt));
	}

	on_board() {
		return frappe.get_route()[0] === 'wash-plan-board';
	}

	idle() {
		const a = document.activeElement;
		const typing = a && this.el.contains(a) && (a.tagName === 'INPUT' || a.tagName === 'SELECT' || a.tagName === 'TEXTAREA');
		return !this.saving && !this.pending && !typing && !(window.cur_dialog && cur_dialog.display);
	}

	on_change(d) {
		if (!d || !WPB_LIVE_DOCTYPES.includes(d.doctype) || !this.board || !this.on_board()) return;
		this.dirty = true;
		this.debounce('live', () => this.tick(), 1500);
	}

	tick() {
		if (!this.ctx || !this.scope || !this.on_board() || document.visibilityState !== 'visible') return;
		if (!this.idle()) { this.dirty = true; return this.debounce('live', () => this.tick(), 3000); }
		this.dirty = false;
		this.subscribe();
		return this.load_context().then(() => this.load());
	}

	// ---------- routing / loading ----------
	route() {
		const arg = frappe.get_route()[1];
		const want = arg === 'new' ? { mode: 'draft' } : arg ? { mode: 'plan', plan: arg } : { mode: 'view' };
		const same = this.scope && this.scope.mode === want.mode && (want.mode !== 'plan' || this.scope.plan === want.plan);
		if (same && this.board && (want.mode !== 'view' || this.view)) return;
		this.day = 'all';
		this.toast = null;
		this.rowErr = {};
		const ready = this.ctx ? Promise.resolve() : this.load_context();
		ready.then(() => {
			if (want.mode === 'draft') {
				this.draft = { plan_type: 'Weekly', from_date: this.ctx.week.from, to_date: this.ctx.week.to };
				this.scope = { mode: 'draft' };
			} else if (want.mode === 'plan') {
				this.draft = null;
				this.scope = want;
			} else {
				this.draft = null;
				this.view = this.view || { from: this.ctx.week.from, to: this.ctx.week.to };
				this.scope = { mode: 'view' };
			}
			this.load();
		});
	}

	go(plan) {
		frappe.set_route('wash-plan-board', ...(plan ? [plan] : []));
	}

	load_context() {
		return frappe.xcall(WPB_M + 'get_context').then(ctx => { this.ctx = ctx; });
	}

	server_scope() {
		if (this.scope.mode === 'plan') return { mode: 'plan', plan: this.scope.plan };
		if (this.scope.mode === 'draft') return { mode: 'view', from: this.draft_period().from, to: this.draft_period().to };
		return { mode: 'view', from: this.view.from, to: this.view.to };
	}

	load() {
		return frappe.xcall(WPB_M + 'get_board', { scope: this.server_scope() })
			.then(b => this.apply(b))
			.catch(() => { this.board = null; this.render(); });
	}

	apply(b) {
		this.board = b;
		this.updatedAt = Date.now();
		if (b.mode === 'plan' && this.scope.mode !== 'plan') {
			this.scope = { mode: 'plan', plan: b.plan.name };
			this.draft = null;
			this.go(b.plan.name);
		}
		this.render();
		this.refresh_preview();
	}

	// ---------- writes ----------
	mutate(method, args, opt = {}) {
		this.saving++;
		this.saveState = 'saving';
		this.paint_status();
		const run = () => frappe.call({ method: WPB_M + method, args: Object.assign({}, args, { scope: this.server_scope() }) })
			.then(r => {
				const m = r.message || {};
				this.lastWrite = Date.now();
				if (m.plans) this.ctx.plans = m.plans;
				if (m.ok) {
					this.saveState = 'saved';
					if (opt.row) delete this.rowErr[opt.row];
					if (opt.form) this.formError = '';
					if (m.message) this.toast = { kind: 'ok', text: m.message };
				} else {
					this.saveState = 'error';
					if (opt.row) this.rowErr[opt.row] = m.error;
					else if (opt.form) this.formError = m.error;
					else this.toast = { kind: 'err', text: m.error };
				}
				if (m.board) this.apply(m.board); else this.render();
				return m;
			})
			.catch(() => { this.saveState = 'error'; this.render(); })
			.finally(() => { this.saving--; this.paint_status(); });
		this.queue = this.queue.then(run, run);
		return this.queue;
	}

	debounce(key, fn, ms) {
		clearTimeout(this.timers[key]);
		this.timers[key] = setTimeout(fn, ms);
	}

	update_row(row, field, value, ms) {
		const go = () => this.mutate('update_wash', { row, field, value }, { row });
		const key = 'row:' + row + ':' + field;
		const wasPending = !!this.timers[key];
		clearTimeout(this.timers[key]);
		if (wasPending) this.pending--;
		delete this.timers[key];
		if (ms) {
			this.pending++;
			this.saveState = 'pending';
			this.paint_status();
			this.timers[key] = setTimeout(() => { delete this.timers[key]; this.pending--; go(); }, ms);
		} else go();
	}

	// ---------- view model ----------
	period() {
		if (this.scope.mode === 'plan' && this.board && this.board.plan) return { from: this.board.plan.from_date, to: this.board.plan.to_date };
		if (this.scope.mode === 'draft') return this.draft_period();
		return { from: this.view.from, to: this.view.to };
	}

	draft_period() {
		const d = this.draft;
		if (d.plan_type === 'Daily') return { from: d.from_date, to: d.from_date };
		if (d.plan_type === 'Weekly') {
			const e = new Date(d.from_date + 'T00:00:00');
			e.setDate(e.getDate() + 6);
			return { from: d.from_date, to: wpb_key(e) };
		}
		return { from: d.from_date, to: d.to_date };
	}

	compute() {
		const b = this.board, f = this.filters;
		const rows = this.scope.mode === 'draft' ? [] : b.rows;
		const p = this.period();
		const days = wpb_range(p.from, p.to);
		const filtered = rows.filter(r =>
			(f.freezer === 'all' || r.freezer === f.freezer) &&
			(f.project === 'all' || r.project === f.project) &&
			(f.item === 'all' || r.item === f.item));
		const scoped = this.day === 'all' ? filtered : filtered.filter(r => r.planned_date === this.day);
		const sum = (list, k) => list.reduce((s, r) => s + (r[k] || 0), 0);
		const done = scoped.filter(r => r.status === 'Washed' || r.status === 'Completed');
		const eligible = scoped.filter(r => r.editable && !r.blocked).map(r => r.name);

		const groups = {}, order = [];
		scoped.forEach(r => {
			const k = r.project || '';
			if (!groups[k]) { groups[k] = { name: r.project_name, w: 0, l: 0, h: 0, r: 0 }; order.push(k); }
			const g = groups[k];
			g.w++; g.l += r.planned_lbs; g.h += r.expected_hash_g; g.r += r.expected_rosin_g;
		});
		order.sort((a, c) => a === '' ? 1 : c === '' ? -1 : a < c ? -1 : 1);

		const projects = {}, items = {};
		rows.forEach(r => { if (r.project) projects[r.project] = r.project_name; items[r.item] = r.item_name; });

		return {
			rows: scoped, filtered, days, eligible, groups, order, projects, items,
			tLbs: sum(scoped, 'planned_lbs'), tHash: sum(scoped, 'expected_hash_g'), tRosin: sum(scoped, 'expected_rosin_g'),
			aHash: sum(done, 'actual_hash_g'), aRosin: sum(scoped, 'actual_rosin_g'), washed: done.length,
		};
	}

	// ---------- render ----------
	render() {
		if (!this.ctx || !this.scope) return;
		const focus = this.capture_focus();
		this.el.innerHTML = this.board ? this.html() : '<div class="wpb-loading">' + __('Could not load the board.') + '</div>';
		this.restore_focus(focus);
	}

	paint_status() {
		const el = this.el.querySelector('[data-role="save-status"]');
		if (el) el.outerHTML = this.status_html();
	}

	status_html() {
		const s = this.saving ? 'saving' : this.saveState;
		const map = {
			pending: ['#f7f3fc', 'var(--muted)', __('Unsaved change…')],
			saving: ['#f7f3fc', 'var(--muted)', __('Saving…')],
			saved: ['#f3e6fb', 'var(--brand2)', __('Saved')],
			error: ['#FFF6F1', 'var(--warn)', __('Not saved')],
		};
		const m = map[s];
		if (!m) return '<span data-role="save-status"></span>';
		return '<span data-role="save-status" class="pill" role="status" style="background:' + m[0] + ';color:' + m[1] + ';font-weight:700">' + (s === 'saved' ? WPB_SVG.check + ' ' : '') + m[2] + '</span>';
	}

	capture_focus() {
		const a = document.activeElement;
		if (!a || !this.el.contains(a) || !a.dataset.focus) return null;
		let start = null, end = null;
		try { start = a.selectionStart; end = a.selectionEnd; } catch (e) { /* number inputs */ }
		return { key: a.dataset.focus, value: (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA') ? a.value : null, start, end };
	}

	restore_focus(f) {
		if (!f) return;
		const el = this.el.querySelector('[data-focus="' + CSS.escape(f.key) + '"]');
		if (!el) return;
		// keep what the user is typing; a pending debounce saves it
		if (f.value != null) el.value = f.value;
		el.focus();
		try { if (f.start != null) el.setSelectionRange(f.start, f.end); } catch (e) { /* number inputs */ }
	}

	html() {
		const v = this.compute();
		return this.html_band() + '<main class="wpb-main">' +
			this.html_header(v) + this.html_toast() + this.html_tabs(v) + this.html_kpis(v) + this.html_table(v) +
			'<div class="wpb-bottom">' + this.html_add(v) + this.html_freezers() + this.html_next() + '</div></main>';
	}

	html_band() {
		const crumb = this.scope.mode === 'plan' ? this.board.plan.name : this.scope.mode === 'draft' ? __('New plan') : __('All plans');
		const user = this.ctx.user.full_name || this.ctx.user.name;
		const app = this.ctx.app_name || '';
		const at = this.updatedAt ? new Date(this.updatedAt) : null;
		const live = at ? '<span class="wpb-live" title="' + __('Refreshes automatically when plans, Material Requests, Work Orders or Stock Entries change') + '"><span class="wpb-live-dot"></span>' + __('Live') + ' · ' + __('updated {0}', [String(at.getHours()).padStart(2, '0') + ':' + String(at.getMinutes()).padStart(2, '0')]) + '</span>' : '';
		return '<header class="wpb-band"><div class="wpb-brand"><div class="wpb-logo">' + wpb_esc(app.charAt(0).toUpperCase()) + '</div>' +
			'<div style="display:flex;flex-direction:column"><span style="font-weight:800;font-size:16px">' + wpb_esc(app) + '</span><span style="font-size:12px;color:#e4d6f7">' + wpb_esc(this.ctx.company) + '</span></div></div>' +
			'<nav aria-label="Breadcrumb" class="wpb-crumbs"><a href="/app/manufacturing">' + __('Manufacturing') + '</a><span aria-hidden="true">/</span>' +
			'<a data-action="home" href="#">' + __('Wash Production Plan') + '</a><span aria-hidden="true">/</span><span style="color:#fff;font-weight:700">' + wpb_esc(crumb) + '</span></nav>' +
			'<div style="display:flex;align-items:center;gap:14px">' + live + '<div style="display:flex;align-items:center;gap:10px"><div class="wpb-avatar">' + wpb_esc(user.charAt(0).toUpperCase()) + '</div><span style="font-size:13px">' + wpb_esc(user) + '</span></div></div></header>';
	}

	html_header(v) {
		const mode = this.scope.mode, p = this.board.plan, ctx = this.ctx;
		const status = mode === 'plan' ? p.status : mode === 'draft' ? 'Not saved' : 'All plans';
		const pill = WPB_PILLS[status] || WPB_PILLS.Draft;
		const can = mode === 'draft' || (mode === 'plan' && p.can_write);
		const strong = t => '<strong style="color:var(--ink)">' + t + '</strong>';
		let meta;
		if (mode === 'plan') {
			meta = '<span>' + __('Plan') + ' ' + strong(wpb_esc(p.name)) + '</span><span>' + __('Company') + ' ' + strong(wpb_esc(p.company)) + '</span>' +
				'<span>' + __('Routing') + ' ' + strong(wpb_esc(p.routing)) + '</span><span>' + __('Planned By') + ' ' + strong(wpb_esc(p.planned_by)) + '</span>';
		} else if (mode === 'draft') {
			meta = '<span>' + __('Plan') + ' ' + strong(__('New, saved with the first wash or Create Plan')) + '</span><span>' + __('Company') + ' ' + strong(wpb_esc(ctx.company)) + '</span>' +
				'<span>' + __('Routing') + ' ' + strong(wpb_esc(ctx.routing)) + '</span><span>' + __('Planned By') + ' ' + strong(wpb_esc(ctx.user.full_name)) + '</span>';
		} else {
			const links = this.board.plans_in_view.map(x => '<a href="#" class="mono" data-action="openPlan" data-id="' + wpb_esc(x.name) + '">' + wpb_esc(x.name) + '</a>').join(', ');
			meta = '<span>' + __('Showing') + ' ' + strong(__('all plans in this period')) + '</span>' +
				'<span>' + __('Plans') + ' ' + (links ? strong(links) : strong(__('none yet'))) + '</span>' +
				'<span>' + __('Company') + ' ' + strong(wpb_esc(ctx.company)) + '</span><span>' + __('Routing') + ' ' + strong(wpb_esc(ctx.routing)) + '</span>';
		}

		const plans = ctx.plans.slice();
		if (p && !plans.some(x => x.name === p.name)) plans.unshift({ name: p.name, from_date: p.from_date, to_date: p.to_date, total_washes: this.board.rows.length, status: p.status });
		const selOpts = [{ key: '', label: __('All plans · by date range') }].concat(plans.map(x => ({
			key: x.name, label: x.name + ' · ' + wpb_period(x.from_date, x.to_date) + ' · ' + wpb_words(x.total_washes || 0) + (x.status === 'In Progress' ? '' : ' · ' + __(x.status)),
		})));
		const selected = mode === 'plan' ? p.name : mode === 'draft' ? '__new' : '';
		if (mode === 'draft') selOpts.push({ key: '__new', label: __('New plan (not saved)') });

		let h = '<section class="card" style="padding:22px 24px;display:flex;flex-direction:column;gap:18px"><div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:20px;align-items:flex-start">' +
			'<div style="display:flex;flex-direction:column;gap:8px;min-width:0"><div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">' +
			'<h1 class="wpb-h1">' + (mode === 'draft' ? __('New Wash Production Plan') : __('Wash Production Plan')) + '</h1>' +
			'<span class="pill" style="background:' + pill[0] + ';color:' + pill[1] + '">' + wpb_esc(__(status)) + '</span>' + this.status_html() + '</div>' +
			'<div class="muted wpb-meta">' + meta + '</div></div>';

		h += '<div style="display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end">' +
			'<label class="lbl">' + __('Plan') + '<select class="field" data-change="pickPlan" style="min-width:260px;height:42px">' + wpb_opts(selOpts, selected) + '</select></label>' +
			'<button type="button" class="wpb-btn-out" data-action="newPlan">' + WPB_SVG.plus + __('New Plan') + '</button>' +
			(mode === 'plan' && ctx.is_admin ? '<a class="wpb-formlink" href="/app/wash-production-plan/' + encodeURIComponent(p.name) + '">' + __('Open in form') + '</a>' : '') +
			'</div></div>';

		// period controls
		h += '<div style="display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end">';
		if (mode === 'view') {
			const bad = this.view.to < this.view.from;
			h += '<label class="lbl">' + __('From Date') + '<input class="field" type="date" data-change="viewFrom" value="' + wpb_esc(this.view.from) + '" style="height:42px' + (bad ? ';border-color:var(--warnline)' : '') + '"></label>' +
				'<label class="lbl">' + __('To Date') + '<input class="field" type="date" data-change="viewTo" value="' + wpb_esc(this.view.to) + '" style="height:42px' + (bad ? ';border-color:var(--warnline)' : '') + '"></label>' +
				'<div class="lbl">' + __('Quick range') + '<div class="seg">' +
				'<button type="button" data-action="week" data-id="0" style="' + this.seg(this.view.from === ctx.week.from && this.view.to === ctx.week.to) + '">' + __('This week') + '</button>' +
				'<button type="button" data-action="week" data-id="1" style="' + this.seg(false) + '">' + __('Next week') + '</button></div></div>';
		} else {
			const t = mode === 'plan' ? p.plan_type : this.draft.plan_type;
			const from = mode === 'plan' ? p.from_date : this.draft.from_date;
			const to = mode === 'plan' ? p.to_date : this.draft.to_date;
			const dis = can ? '' : ' disabled';
			h += '<div class="lbl">' + __('Plan Type') + '<div class="seg">' +
				['Daily', 'Weekly', 'Custom'].map(x => '<button type="button" data-action="planType" data-id="' + x + '"' + dis + ' style="' + this.seg(t === x) + '">' + (x === 'Custom' ? WPB_SVG.cal : '') + __(x) + '</button>').join('') + '</div></div>' +
				'<label class="lbl">' + (t === 'Daily' ? __('Date') : t === 'Weekly' ? __('Week Starting') : __('From Date')) +
				'<input class="field" type="date" data-change="planFrom" value="' + wpb_esc(from) + '"' + dis + ' style="height:42px"></label>' +
				(t === 'Custom' ? '<label class="lbl">' + __('To Date') + '<input class="field" type="date" data-change="planTo" value="' + wpb_esc(to) + '"' + dis + ' style="height:42px"></label>' : '');
		}
		const per = this.period();
		h += '<div class="lbl">' + __('Plan Period') + '<div class="wpb-period">' + wpb_esc(wpb_period(per.from, per.to)) + '</div></div>';
		if (mode === 'draft') {
			h += '<button type="button" class="wpb-btn-brand" data-action="createPlan">' + __('Create Plan') + '</button>' +
				'<button type="button" class="wpb-btn-ghost" data-action="cancelDraft">' + __('Cancel') + '</button>';
		}
		h += '</div>';

		// project summary
		const scopeName = this.day === 'all' ? wpb_period(per.from, per.to) : wpb_day(this.day).label + ', ' + wpb_day(this.day).year;
		h += '<div style="border-top:1px solid var(--line2);padding-top:16px;display:flex;flex-direction:column;gap:10px"><span class="wpb-eyebrow">' + __('Project Summary') + ' · ' + wpb_esc(scopeName) + '</span><div style="display:flex;flex-wrap:wrap;gap:10px">';
		if (!v.order.length) h += '<span class="muted" style="font-size:13px">' + __('No washes in this period.') + '</span>';
		v.order.forEach(k => {
			const g = v.groups[k];
			h += '<div class="wpb-proj' + (k ? '' : ' none') + '"><span style="font-weight:800;font-size:13px">' + wpb_esc(k ? (g.name || k) : __('No Project')) + '</span>' +
				'<span class="mono muted" style="font-size:12px">' + wpb_esc(k || __('MR project left empty')) + '</span>' +
				'<span style="font-size:13px;margin-top:4px"><strong>' + wpb_words(g.w) + '</strong> · <strong>' + wpb_lbs(g.l) + ' lbs</strong> FF</span>' +
				'<span class="muted" style="font-size:12px">' + __('Exp. hash') + ' ' + wpb_fmt(g.h) + ' g · ' + __('rosin') + ' ' + wpb_fmt(g.r) + ' g</span></div>';
		});
		return h + '</div></div></section>';
	}

	seg(on) {
		return 'background:' + (on ? 'var(--brand)' : 'transparent') + ';color:' + (on ? '#fff' : 'var(--ink)');
	}

	html_toast() {
		const t = this.toast;
		if (!t) return '';
		const ok = t.kind === 'ok';
		return '<div role="' + (ok ? 'status' : 'alert') + '" class="wpb-toast ' + (ok ? 'ok' : 'err') + '"><div style="display:flex;align-items:center;gap:10px">' + (ok ? WPB_SVG.check : WPB_SVG.warn) +
			'<span style="font-weight:600">' + wpb_esc(t.text) + '</span></div><button type="button" aria-label="' + __('Dismiss message') + '" data-action="dismiss" class="wpb-toast-x">' + WPB_SVG.x + '</button></div>';
	}

	html_tabs(v) {
		const t = this.scope.mode === 'plan' ? this.board.plan.plan_type : this.scope.mode === 'draft' ? this.draft.plan_type : 'View';
		if (t === 'Daily') return '';
		const tabs = [{ key: 'all', short: t === 'Weekly' ? __('All week') : __('All days') }].concat(v.days.length <= 14 ? v.days : []);
		let h = '<nav aria-label="' + __('Plan days') + '" style="display:flex;gap:8px;flex-wrap:wrap">';
		tabs.forEach(d => {
			const count = d.key === 'all' ? v.filtered.length : v.filtered.filter(r => r.planned_date === d.key).length;
			const sel = this.day === d.key;
			h += '<button type="button" data-action="pickDay" data-id="' + d.key + '" class="wpb-tab' + (sel ? ' on' : '') + '">' +
				'<span style="font-weight:800;font-size:13px">' + wpb_esc(d.short) + '</span><span class="wpb-tab-sub">' + (d.key === 'all' ? '' : wpb_esc(d.md) + ' · ') + wpb_words(count) + '</span></button>';
		});
		return h + '</nav>';
	}

	html_kpis(v) {
		const c = this.ctx, unit = u => ' <span class="muted" style="font-size:15px">' + u + '</span>';
		return '<section aria-label="' + __('Plan totals') + '" class="wpb-kpis">' +
			'<div class="card kpi"><span class="k">' + __('Total Washes') + '</span><span class="v mono">' + v.rows.length + '</span><span class="muted" style="font-size:12px">' + v.washed + ' ' + __('washed') + ' · ' + (v.rows.length - v.washed) + ' ' + __('still to run') + '</span></div>' +
			'<div class="card kpi"><span class="k">' + __('Planned Fresh Frozen') + '</span><span class="v mono">' + wpb_lbs(v.tLbs) + unit('lbs') + '</span><span class="muted" style="font-size:12px">' + wpb_fmt(v.tLbs * LB_KG) + ' ' + __('kg into the washing machine') + '</span></div>' +
			'<div class="card kpi"><span class="k">' + __('Expected Bubble Hash') + '</span><span class="v mono">' + wpb_fmt(v.tHash) + unit('g') + '</span><span class="muted" style="font-size:12px">' +
			(v.aHash ? __('Actual') + ' <strong class="mono" style="color:var(--ink)">' + wpb_fmt(v.aHash) + ' g</strong> ' + __('from {0}', [wpb_words(v.washed)]) : __('Default yield {0} of input', [wpb_pct(c.hash_yield)])) + '</span></div>' +
			'<div class="card kpi"><span class="k">' + __('Expected Rosin') + '</span><span class="v mono">' + wpb_fmt(v.tRosin) + unit('g') + '</span><span class="muted" style="font-size:12px">' +
			(v.aRosin ? __('Actual') + ' <strong class="mono" style="color:var(--ink)">' + wpb_fmt(v.aRosin) + ' g</strong> ' + __('pressed so far') : __('Default yield {0} of hash', [wpb_pct(c.rosin_yield)])) + '</span></div></section>';
	}

	html_table(v) {
		const mode = this.scope.mode, n = v.eligible.length, f = this.filters;
		const per = this.period();
		const label = this.day === 'all'
			? (mode === 'plan' && this.board.plan.plan_type === 'Weekly' ? __('Week of') + ' ' : '') + wpb_period(per.from, per.to)
			: wpb_day(this.day).label + ', ' + wpb_day(this.day).year;
		const fz = this.ctx.freezers.map(x => ({ key: x, label: x }));
		const pj = Object.keys(v.projects).sort().map(k => ({ key: k, label: k + (v.projects[k] ? ' · ' + v.projects[k] : '') }));
		const it = Object.keys(v.items).map(k => ({ key: k, label: v.items[k] })).sort((a, b) => a.label.localeCompare(b.label));

		let h = '<section class="card" style="overflow:hidden"><div class="wpb-table-head">' +
			'<div style="display:flex;flex-direction:column;gap:2px"><h2 class="h2">' + __('Planned Washes') + '</h2><span class="muted" style="font-size:13px">' + wpb_esc(label) + ' · ' + wpb_words(v.rows.length) + '</span></div>' +
			'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:10px">' +
			'<label class="wpb-filter">' + __('Freezer') + '<select class="field" data-change="filterFreezer">' + wpb_opts([{ key: 'all', label: __('All freezers') }].concat(fz), f.freezer) + '</select></label>' +
			'<label class="wpb-filter">' + __('Project') + '<select class="field" data-change="filterProject">' + wpb_opts([{ key: 'all', label: __('All projects') }, { key: '', label: __('No Project') }].concat(pj), f.project) + '</select></label>' +
			'<label class="wpb-filter">' + __('Strain') + '<select class="field" data-change="filterItem" style="max-width:220px">' + wpb_opts([{ key: 'all', label: __('All strains') }].concat(it), f.item) + '</select></label>' +
			'<button type="button" data-action="bulk" class="wpb-btn-accent"' + (n ? '' : ' disabled') + '>' + __('Create MRs for {0} planned {1}', [n, n === 1 ? __('wash') : __('washes')]) + '</button></div></div>';

		h += '<div style="overflow-x:auto"><div class="wpb-grid"><div class="grid-row grid-head"><span>' + __('Planned Date') + '</span><span>' + __('Strain / Freezer') + '</span><span>' + __('Project') + '</span><span>' + __('Available') + '</span><span>' + __('Planned (lbs)') + '</span><span>' + __('Exp. Hash') + '</span><span>' + __('Exp. Rosin') + '</span><span>' + __('Status') + '</span><span>' + __('Action') + '</span></div>';
		if (!v.rows.length) {
			h += '<div class="muted" style="padding:36px 20px;text-align:center">' +
				(mode === 'draft' ? __('This plan has no washes yet. Use “Add a Wash” below; the plan is saved with the first wash.') : __('No washes match this period and these filters. Use “Add a Wash” below.')) + '</div>';
		}
		v.rows.forEach(r => { h += this.html_row(r, mode); });
		return h + '</div></div></section>';
	}

	html_row(r, mode) {
		const d = wpb_day(r.planned_date), pill = WPB_PILLS[r.status] || WPB_PILLS.Planned, ex = !!this.expanded[r.name];
		const over = r.editable && r.over_by > 0, err = this.rowErr[r.name];
		const missing = r.editable && (!r.bubble_hash_item || !r.rosin_item);
		let h = '<div style="border-top:1px solid var(--line2);background:' + (over ? '#FFF6F1' : '#fff') + '"><div class="grid-row">';

		h += '<div style="display:flex;align-items:center;gap:10px"><button type="button" class="icon-btn" style="width:32px;height:32px;flex:none" data-action="toggle" data-id="' + r.name + '" aria-expanded="' + ex + '" aria-label="' + (ex ? __('Hide finished goods') : __('Show finished goods')) + '">' + WPB_SVG.chev(ex ? 'rotate(90deg)' : 'none') + '</button>' +
			'<div style="display:flex;flex-direction:column;gap:2px;min-width:0"><span style="font-weight:800">' + d.short + '</span><span class="muted" style="font-size:12px">' + d.md + ', ' + d.year + '</span>' +
			(mode === 'view' ? '<a href="#" class="mono wpb-planlink" data-action="openPlan" data-id="' + wpb_esc(r.plan) + '" title="' + __('Open this plan on the board') + '">' + wpb_esc(r.plan) + '</a>' : '') + '</div></div>';

		// strain / freezer
		h += '<div style="display:flex;flex-direction:column;gap:4px;min-width:0"><span style="font-weight:700">' + wpb_esc(r.item_name) + '</span>';
		if (r.editable) {
			const fo = (r.freezer_options || []).map(o => ({ key: o.warehouse, label: o.warehouse + ' · ' + wpb_lbs(o.qty) + ' lbs' }));
			if (!fo.some(o => o.key === r.freezer)) fo.unshift({ key: r.freezer, label: r.freezer + ' · 0 lbs' });
			h += '<label style="display:flex"><span class="sr">' + __('Source freezer') + '</span><select class="field" data-change="rowFreezer" data-id="' + r.name + '" data-focus="fz:' + r.name + '" style="height:34px;max-width:260px;font-size:12px;border-radius:8px">' + wpb_opts(fo, r.freezer) + '</select></label>';
		} else {
			h += '<span class="muted" style="font-size:12px">' + wpb_esc(r.freezer) + '</span>';
		}
		if (over) h += '<span class="wpb-warn">' + wpb_esc(__('Exceeds stock in {0} by {1} lbs', [r.freezer, wpb_lbs(r.over_by)])) + '</span>';
		if (over && r.held_by && r.held_by.length) h += '<span class="wpb-held">' + wpb_esc(__('Held by: {0}', [r.held_by.join('; ')])) + '</span>';
		if (missing) h += '<span class="wpb-warn">' + __('Finished items not created yet. Expand the row to create them.') + '</span>';
		else if (r.blocked && !over) h += '<span class="wpb-warn">' + wpb_esc(r.blocked.charAt(0).toUpperCase() + r.blocked.slice(1)) + '</span>';
		if (err) h += '<span class="wpb-warn" role="alert">' + WPB_SVG.warn + ' ' + wpb_esc(err) + '</span>';
		h += '</div>';

		// project
		h += '<div style="min-width:0">';
		if (r.editable) {
			const po = [{ key: '', label: __('No Project') }];
			(r.project_options || []).forEach(o => {
				if (!o.project) po[0].label = __('No Project') + ' · ' + wpb_lbs(o.qty) + ' lbs';
				else po.push({ key: o.project, label: o.project + (o.project_name ? ' · ' + o.project_name : '') + ' · ' + wpb_lbs(o.qty) + ' lbs' });
			});
			if (r.project && !po.some(o => o.key === r.project)) po.push({ key: r.project, label: r.project + (r.project_name ? ' · ' + r.project_name : '') + ' · 0 lbs' });
			h += '<label style="display:flex"><span class="sr">' + __('Project') + '</span><select class="field" data-change="rowProject" data-id="' + r.name + '" data-focus="pj:' + r.name + '" style="height:36px;width:100%;font-size:12px;border-radius:8px">' + wpb_opts(po, r.project) + '</select></label>';
		} else {
			h += '<div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:13px;font-weight:700;color:' + (r.project ? 'var(--ink)' : 'var(--muted)') + '">' + wpb_esc(r.project ? (r.project_name || r.project) : __('No Project')) + '</span><span class="mono muted" style="font-size:11px">' + wpb_esc(r.project || __('MR project left empty')) + '</span></div>';
		}
		h += '</div>';

		h += '<span class="mono"' + (over ? ' style="color:var(--warn);font-weight:600"' : '') + '>' + (r.available_lbs == null ? '—' : wpb_lbs(r.available_lbs)) + '</span>';

		// qty
		h += '<div>' + (r.editable
			? '<div style="display:flex;align-items:center;gap:4px"><button type="button" class="icon-btn" data-action="dec" data-id="' + r.name + '" aria-label="' + __('Decrease by 5 lbs') + '">' + WPB_SVG.minus + '</button>' +
			'<label style="display:flex"><span class="sr">' + __('Planned pounds') + '</span><input type="number" min="0" step="5" data-input="rowQty" data-change="rowQty" data-id="' + r.name + '" data-focus="qty:' + r.name + '" value="' + wpb_esc(r.planned_lbs) + '" class="mono wpb-qty" style="border-color:' + (over ? 'var(--warnline)' : '#d8cceb') + '"></label>' +
			'<button type="button" class="icon-btn" data-action="inc" data-id="' + r.name + '" aria-label="' + __('Increase by 5 lbs') + '">' + WPB_SVG.plus + '</button></div>'
			: '<span class="mono" style="font-weight:600">' + wpb_lbs(r.planned_lbs) + ' lbs</span>') + '</div>';

		h += '<div style="display:flex;flex-direction:column;gap:2px"><span class="mono" style="font-weight:600">' + wpb_fmt(r.expected_hash_g) + ' g</span>' + (r.actual_hash_g ? '<span class="muted" style="font-size:12px">' + __('Actual') + ' ' + wpb_fmt(r.actual_hash_g) + ' g</span>' : '') + '</div>';
		h += '<div style="display:flex;flex-direction:column;gap:2px"><span class="mono" style="font-weight:600">' + wpb_fmt(r.expected_rosin_g) + ' g</span>' + (r.actual_rosin_g ? '<span class="muted" style="font-size:12px">' + __('Actual') + ' ' + wpb_fmt(r.actual_rosin_g) + ' g</span>' : '') + '</div>';

		h += '<div style="display:flex;flex-direction:column;gap:4px;align-items:flex-start"><span class="pill" style="background:' + pill[0] + ';color:' + pill[1] + '">' + wpb_esc(__(r.status)) + '</span>' +
			(r.material_request ? '<a class="mono muted" style="font-size:11px" href="/app/material-request/' + encodeURIComponent(r.material_request) + '" title="' + wpb_esc(r.mr_state) + '">' + wpb_esc(r.material_request) + '</a>' : '<span class="mono muted" style="font-size:11px">—</span>') + '</div>';

		h += '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">';
		if (r.editable) {
			h += '<button type="button" data-action="createMr" data-id="' + r.name + '"' + (r.blocked ? ' disabled title="' + wpb_esc(r.blocked) + '"' : '') + ' class="wpb-btn-mr">' + __('Create MR') + '</button>' +
				'<button type="button" data-action="remove" data-id="' + r.name + '" aria-label="' + __('Remove wash from plan') + '" class="wpb-trash">' + WPB_SVG.trash + '</button>';
		} else if (r.status === 'MR Created') {
			const mr = '<a class="mono" href="/app/material-request/' + encodeURIComponent(r.material_request) + '">' + wpb_esc(r.material_request) + '</a>';
			h += '<span class="muted" style="font-size:12px;font-weight:600">' + (r.hash_work_order
				? __('Hash Work Order') + ' <a class="mono" href="/app/work-order/' + encodeURIComponent(r.hash_work_order) + '">' + wpb_esc(r.hash_work_order) + '</a>'
				: r.mr_state === 'Draft' ? __('Draft MR {0}', [mr]) : __('Waiting for Work Orders')) + '</span>';
			if (r.mr_state === 'Draft' && r.can_write) h += '<button type="button" data-action="submitMr" data-id="' + r.name + '" class="wpb-btn-mr" style="background:var(--brand);color:#fff;border-color:var(--brand)">' + __('Submit MR') + '</button>';
		} else if (r.status === 'Washed') {
			h += '<span style="font-size:12px;font-weight:700;color:var(--brand2)">' + __('Washed · rosin pressing next') + '</span>';
		} else if (r.status === 'Completed') {
			h += '<span style="display:flex;align-items:center;gap:6px;color:var(--brand2);font-weight:700;font-size:13px">' + WPB_SVG.check + __('Work Orders done') + '</span>';
		} else if (r.status === 'Planned') {
			h += '<span class="muted" style="font-size:12px">' + __('Read only') + '</span>';
		}
		h += '</div></div>';

		if (ex) h += this.html_fg(r);
		return h + '</div>';
	}

	html_fg(r) {
		const planned = r.status === 'Planned';
		const done = r.actual_hash_g > 0;
		const proj = r.project ? __('MR project: {0}', [r.project]) : __('MR project: none');
		const fg = [
			{ op: __('Hash Processing'), wo: r.hash_work_order, code: r.bubble_hash_item, name: r.bubble_hash_name || (r.base + ' - Bubble Hash'), want: r.base + ' - Bubble Hash', group: this.ctx.bubble_hash_group, y: r.expected_hash_yield, yf: 'expected_hash_yield', q: r.expected_hash_g, ay: done ? wpb_pct(r.actual_hash_yield) : '—', act: done ? wpb_fmt(r.actual_hash_g) : '—', kind: 'bubble_hash' },
			{ op: __('Rosin Pressing'), wo: r.rosin_work_order, code: r.rosin_item, name: r.rosin_name || (r.base + ' - Rosin'), want: r.base + ' - Rosin', group: this.ctx.rosin_group, y: r.expected_rosin_yield, yf: 'expected_rosin_yield', q: r.expected_rosin_g, ay: r.actual_rosin_g ? wpb_pct(r.actual_rosin_yield) : '—', act: r.actual_rosin_g ? wpb_fmt(r.actual_rosin_g) : '—', kind: 'rosin' },
		];
		let h = '<div class="wpb-fg"><div class="wpb-fg-head"><span style="font-weight:800;font-size:13px">' + __('Finished Goods') + '</span><span class="muted" style="font-size:12px">' +
			wpb_esc((planned ? __('Copied to the MR Finished Goods table on Create MR') : __('Sent to the Finished Goods table of {0}', [r.material_request])) + ' · ' + proj) + '</span></div>' +
			'<div class="fg-row wpb-fg-cols"><span>' + __('Operation') + '</span><span>' + __('Finished Item') + '</span><span>' + __('Item Group') + '</span><span>' + __('Exp. Yield') + '</span><span>' + __('Exp. Qty (g)') + '</span><span>' + __('Actual Yield') + '</span><span>' + __('Actual (g)') + '</span></div>';
		fg.forEach(g => {
			h += '<div class="fg-row" style="border-top:1px solid var(--line2)"><span style="display:flex;flex-direction:column;gap:2px"><span style="font-weight:700">' + g.op + '</span>' +
				(g.wo ? '<a class="mono" style="font-size:11px" href="/app/work-order/' + encodeURIComponent(g.wo) + '">' + wpb_esc(g.wo) + '</a>' : '') + '</span><div style="display:flex;flex-direction:column;gap:3px;min-width:0">' +
				(g.code ? '<span class="mono" style="font-weight:600">' + wpb_esc(g.code) + '</span><span class="muted" style="font-size:12px">' + wpb_esc(g.name) + '</span>'
					: '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><div style="display:flex;flex-direction:column;gap:2px"><span style="font-size:12px;font-weight:700;color:var(--warn)">' + __('Not created yet') + '</span><span class="muted" style="font-size:12px">' + wpb_esc(g.want) + '</span></div>' +
					(r.editable ? '<button type="button" data-action="createItem" data-id="' + r.name + '" data-arg="' + g.kind + '" class="wpb-btn-mr" style="min-height:34px;padding:6px 10px">' + __('Create Item') + '</button>' : '') + '</div>') +
				'</div><span>' + wpb_esc(g.group) + '</span>' +
				(r.editable
					? '<label style="display:flex;align-items:center;gap:2px"><span class="sr">' + g.op + ' ' + __('expected yield') + '</span><input type="number" min="0" step="0.1" class="mono wpb-qty" style="width:64px" data-input="rowYield" data-change="rowYield" data-id="' + r.name + '" data-arg="' + g.yf + '" data-focus="y:' + g.yf + ':' + r.name + '" value="' + wpb_esc(g.y) + '"><span class="mono">%</span></label>'
					: '<span class="mono">' + wpb_pct(g.y) + '</span>') +
				'<span class="mono" style="font-weight:600">' + wpb_fmt(g.q) + '</span><span class="mono" style="font-weight:600">' + g.ay + '</span><span class="mono" style="font-weight:600">' + g.act + '</span></div>';
		});
		h += '<div class="wpb-fg-notes"><label class="lbl" style="flex:1">' + __('Notes') +
			(r.can_write ? '<textarea class="field wpb-notes" rows="2" data-input="rowNotes" data-change="rowNotes" data-id="' + r.name + '" data-focus="notes:' + r.name + '" placeholder="' + __('Notes for this wash') + '">' + wpb_esc(r.notes) + '</textarea>'
				: '<span style="font-weight:500;color:var(--ink)">' + (wpb_esc(r.notes) || '—') + '</span>') + '</label></div>';
		return h + '<div class="muted wpb-fg-foot">' + WPB_SVG.info + '<span>' +
			(planned ? __('No BOM is needed at planning time. BOMs for these items are created automatically when the Material Request is submitted.') : __('BOMs for these items are created automatically when {0} is submitted.', [r.material_request])) + '</span></div></div>';
	}

	html_add(v) {
		const ctx = this.ctx, f = this.form, p = this.preview || {};
		if (!ctx.strains.length) {
			return '<section class="card wpb-add"><div style="display:flex;flex-direction:column;gap:2px"><h2 class="h2">' + __('Add a Wash') + '</h2>' +
				'<span class="muted" style="font-size:13px">' + (ctx.freezers.length ? __('No Fresh Frozen stock in the configured freezers.') : __('No freezers are configured in Wash Plan Settings.')) + '</span></div></section>';
		}
		const st = ctx.strains.find(x => x.item === f.item) || ctx.strains[0];
		const fz = Object.keys(st.stock).map(k => ({ key: k, label: k + ' · ' + wpb_lbs(st.stock[k]) + ' lbs' }));
		const po = [{ key: '', label: __('No Project') }].concat((p.projects || []).filter(x => x.project).map(x => ({ key: x.project, label: x.project + (x.project_name ? ' · ' + x.project_name : '') + ' · ' + wpb_lbs(x.qty) + ' lbs' })));
		const per = this.period();
		const dates = wpb_range(per.from, per.to).map(d => ({ key: d.key, label: d.label + ', ' + d.year }));
		let target = '';
		if (p.target) {
			target = p.target.new
				? __('New {0} plan, {1}', [__(p.target.plan_type).toLowerCase(), wpb_period(p.target.from_date, p.target.to_date)])
				: p.target.plan;
		}
		const strong = t => '<strong style="color:var(--ink)">' + t + '</strong>';
		return '<section class="card wpb-add"><div style="display:flex;flex-direction:column;gap:2px"><h2 class="h2">' + __('Add a Wash') + '</h2><span class="muted" style="font-size:13px">' +
			__('Default yields: {0} hash, {1} rosin. Project is optional.', [wpb_pct(ctx.hash_yield), wpb_pct(ctx.rosin_yield)]) + '</span></div>' +
			'<div class="wpb-form">' +
			'<label class="lbl">' + __('Planned Date') + '<select class="field" data-change="formDate" data-focus="f:date">' + wpb_opts(dates, f.date) + '</select></label>' +
			'<label class="lbl">' + __('Planned Qty (lbs)') + '<input class="field mono" type="number" min="0" step="5" data-input="formLbs" data-change="formLbs" data-focus="f:lbs" value="' + wpb_esc(f.lbs) + '" style="height:42px"></label>' +
			'<label class="lbl" style="grid-column:span 2">' + __('Fresh Frozen Strain') + '<select class="field" data-change="formItem" data-focus="f:item">' + wpb_opts(ctx.strains.map(x => ({ key: x.item, label: x.item_name + ' (' + x.item + ')' })), st.item) + '</select></label>' +
			'<label class="lbl">' + __('Source Freezer') + '<select class="field" data-change="formFreezer" data-focus="f:fz">' + wpb_opts(fz, f.freezer) + '</select></label>' +
			'<label class="lbl">' + __('Project (optional)') + '<select class="field" data-change="formProject" data-focus="f:pj">' + wpb_opts(po, f.project) + '</select></label></div>' +
			'<div class="muted wpb-preview">' +
			'<span>' + __('Exp. hash') + ' ' + strong(p.expected_hash_g == null ? '…' : wpb_fmt(p.expected_hash_g) + ' g') + '</span>' +
			'<span>' + __('Exp. rosin') + ' ' + strong(p.expected_rosin_g == null ? '…' : wpb_fmt(p.expected_rosin_g) + ' g') + '</span>' +
			'<span>' + __('Free in this freezer') + ' ' + strong(p.available == null ? '…' : wpb_lbs(p.available) + ' lbs') + '</span>' +
			'<span>' + __('Bubble Hash item') + ' ' + strong(wpb_esc(p.bubble_hash_item || __('Not created yet'))) + '</span>' +
			'<span>' + __('Rosin item') + ' ' + strong(wpb_esc(p.rosin_item || __('Not created yet'))) + '</span>' +
			(target ? '<span>' + __('Goes into') + ' ' + strong(wpb_esc(target)) + '</span>' : '') + '</div>' +
			(this.formError ? '<span role="alert" class="wpb-warn" style="font-size:13px">' + wpb_esc(this.formError) + '</span>' : '') +
			'<button type="button" data-action="addWash" class="wpb-btn-brand" style="align-self:flex-start"' + (this.scope.mode === 'plan' && !this.board.plan.can_write ? ' disabled' : '') + '>' + WPB_SVG.plus + __('Add to Plan') + '</button></section>';
	}

	html_freezers() {
		const bar = x => {
			const over = x.booked > x.stock + 0.0001;
			const pct = x.stock > 0 ? Math.min(100, x.booked / x.stock * 100) : (x.booked ? 100 : 0);
			return '<div style="display:flex;flex-direction:column;gap:5px"><div style="display:flex;justify-content:space-between;gap:10px;font-size:13px"><span style="font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + wpb_esc(x.item) + '">' + wpb_esc(x.item_name) + '</span><span class="mono muted" style="white-space:nowrap">' + wpb_lbs(x.booked) + ' / ' + wpb_lbs(x.stock) + ' lbs</span></div>' +
				'<div class="wpb-bar"><div style="width:' + pct + '%;background:' + (over ? 'var(--warnline)' : 'var(--brand2)') + '"></div></div>' +
				'<span style="font-size:12px;font-weight:600;color:' + (over ? 'var(--warn)' : 'var(--muted)') + '">' + (over ? __('Over-booked by {0} lbs', [wpb_lbs(x.booked - x.stock)]) : __('{0} lbs free to plan', [wpb_lbs(x.stock - x.booked)])) + '</span></div>';
		};
		let h = '<section class="card wpb-fz"><div style="display:flex;flex-direction:column;gap:2px"><h2 class="h2">' + __('Freezer Stock vs Plan') + '</h2><span class="muted" style="font-size:13px">' +
			__('Booked by the washes shown here that have not consumed stock yet, per item, freezer and project. One freezer can hold stock for several projects.') + '</span></div>';
		this.board.freezers.forEach(fz => {
			const all = !!this.fzOpen[fz.name];
			const n = fz.projects.reduce((c, g) => c + g.items.length, 0);
			let left = all ? Infinity : Math.max(fz.projects.reduce((c, g) => c + g.items.filter(x => x.booked > 0).length, 0), 4);
			h += '<div class="wpb-fz-box"><div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline"><span style="font-weight:800">' + wpb_esc(fz.name) + '</span><span class="mono muted" style="font-size:12px">' + wpb_lbs(fz.booked) + ' / ' + wpb_lbs(fz.stock) + ' lbs ' + __('booked') + '</span></div>';
			if (!n) h += '<span class="muted" style="font-size:12px">' + __('No Fresh Frozen stock.') + '</span>';
			if (Math.abs((fz.ledger_total || 0) - fz.stock) > 0.5) {
				h += '<span class="wpb-held">' + wpb_esc(__('Ledger total in this freezer is {0} lbs, but project balances add up to {1} lbs. Some stock left the freezer without a project, so project availability may be overstated.', [wpb_lbs(fz.ledger_total), wpb_lbs(fz.stock)])) + '</span>';
			}
			fz.projects.forEach(g => {
				if (left <= 0) return;
				const items = g.items.slice(0, left);
				left -= items.length;
				h += '<div class="wpb-fz-proj"><div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline"><span style="font-size:12px;font-weight:800;color:var(--muted)">' +
					wpb_esc(g.project ? (g.project_name ? g.project_name + ' · ' : '') + g.project : __('No Project')) + '</span><span class="mono muted" style="font-size:11px">' + wpb_lbs(g.booked) + ' / ' + wpb_lbs(g.stock) + ' lbs</span></div>' +
					items.map(bar).join('') + '</div>';
			});
			if (n > 4 && (all || left <= 0)) {
				h += '<button type="button" class="wpb-more" data-action="toggleFz" data-id="' + wpb_esc(fz.name) + '">' + (all ? __('Show fewer') : __('Show all {0} items with stock', [n])) + '</button>';
			}
			h += '</div>';
		});
		return h + '</section>';
	}

	html_next() {
		const step = (n, t) => '<div style="display:flex;gap:10px"><span class="wpb-step">' + n + '</span><span>' + t + '</span></div>';
		return '<section class="wpb-next"><h2 class="h2">' + __('What happens next') + '</h2><div style="display:flex;flex-direction:column;gap:12px;font-size:13px;color:#ece3f9">' +
			step(1, __('Plan washes by day, week or a custom date range, with a freezer and an optional project per wash.')) +
			step(2, __('Create MR raises a Manufacture Material Request from that freezer; the wash’s project maps to the MR, or stays empty if none is set.')) +
			step(3, __('On approval, Work Orders for Hash Processing and Rosin Pressing are created and their BOMs are generated.')) +
			step(4, __('Completed Work Orders write actual hash and rosin back to the plan.')) + '</div></section>';
	}

	// ---------- Add a Wash form ----------
	sync_form() {
		const ctx = this.ctx, f = this.form;
		if (!ctx.strains.length) return;
		const per = this.period();
		if (!f.date || f.date < per.from || f.date > per.to) {
			const today = frappe.datetime.get_today();
			f.date = this.day !== 'all' ? this.day : (today >= per.from && today <= per.to ? today : per.from);
		}
		const st = ctx.strains.find(x => x.item === f.item) || ctx.strains[0];
		f.item = st.item;
		if (!st.stock[f.freezer]) f.freezer = Object.keys(st.stock)[0] || '';
	}

	refresh_preview() {
		this.sync_form();
		const f = this.form;
		if (!f.item) return;
		this.debounce('preview', () => {
			const args = { item: f.item, freezer: f.freezer, project: f.project, qty: f.lbs, planned_date: f.date };
			if (this.scope.mode === 'plan') args.plan = this.scope.plan;
			if (this.scope.mode === 'draft') args.new_plan = this.draft;
			const key = JSON.stringify(args);
			this.previewKey = key;
			frappe.xcall(WPB_M + 'preview_wash', args).then(p => {
				if (this.previewKey !== key) return;
				const held = (p.projects || []).filter(x => x.project);
				// project defaults like the form: stock under a single project -> preselect it
				if (!this.formProjectTouched && held.length === 1 && !(p.projects || []).some(x => !x.project) && f.project !== held[0].project) {
					f.project = held[0].project;
					return this.refresh_preview();
				}
				if (f.project && !held.some(x => x.project === f.project)) {
					f.project = '';
					return this.refresh_preview();
				}
				this.preview = p;
				this.render();
			});
		}, 250);
	}

	// ---------- events ----------
	bind() {
		const actions = {
			home: () => { this.view = null; this.go(); },
			openPlan: id => this.go(id),
			newPlan: () => this.go('new'),
			cancelDraft: () => this.go(),
			dismiss: () => { this.toast = null; this.render(); },
			pickDay: id => { this.day = id; if (id !== 'all') this.form.date = id; this.render(); this.refresh_preview(); },
			toggle: id => { this.expanded[id] = !this.expanded[id]; this.render(); },
			toggleFz: id => { this.fzOpen[id] = !this.fzOpen[id]; this.render(); },
			week: id => {
				const s = new Date(this.ctx.week.from + 'T00:00:00');
				s.setDate(s.getDate() + 7 * Number(id));
				const e = new Date(s);
				e.setDate(e.getDate() + 6);
				this.view = { from: wpb_key(s), to: wpb_key(e) };
				this.day = 'all';
				this.load();
			},
			planType: id => this.set_period({ plan_type: id }),
			createPlan: () => {
				const d = this.draft, p = this.draft_period();
				this.mutate('create_plan', { plan_type: d.plan_type, from_date: p.from, to_date: p.to });
			},
			inc: id => this.bump(id, 5),
			dec: id => this.bump(id, -5),
			createMr: id => this.mutate('create_mrs', { rows: [id] }, { row: id }),
			bulk: () => {
				const ids = this.compute().eligible;
				if (!ids.length) return;
				frappe.confirm(__('Create a Material Request for each of the {0} planned washes shown?', [ids.length]), () => this.mutate('create_mrs', { rows: ids }));
			},
			remove: id => {
				const r = this.board.rows.find(x => x.name === id);
				frappe.confirm(__('Remove {0} ({1}) from the plan?', [r.item_name, r.freezer]), () => this.mutate('remove_wash', { row: id }));
			},
			createItem: (id, arg) => this.create_item_dialog(id, arg),
			submitMr: id => {
				const r = this.board.rows.find(x => x.name === id);
				frappe.confirm(__('Submit {0}? The BOMs and the Hash Processing and Rosin Pressing Work Orders are created on submit.', [r.material_request]),
					() => this.mutate('submit_mr', { row: id }, { row: id }));
			},
			addWash: () => {
				const f = this.form, args = { planned_date: f.date, item: f.item, freezer: f.freezer, project: f.project, qty: f.lbs };
				if (this.scope.mode === 'plan') args.plan = this.scope.plan;
				if (this.scope.mode === 'draft') args.new_plan = Object.assign({}, this.draft, { to_date: this.draft_period().to });
				this.mutate('add_wash', args, { form: true });
			},
		};
		const changes = {
			pickPlan: v => { if (v !== '__new') this.go(v || null); },
			viewFrom: v => { this.view = Object.assign({}, this.view, { from: v }); this.day = 'all'; this.reload_view(); },
			viewTo: v => { this.view = Object.assign({}, this.view, { to: v }); this.day = 'all'; this.reload_view(); },
			planFrom: v => this.set_period({ from_date: v }),
			planTo: v => this.set_period({ to_date: v }),
			filterFreezer: v => { this.filters.freezer = v; this.render(); },
			filterProject: v => { this.filters.project = v; this.render(); },
			filterItem: v => { this.filters.item = v; this.render(); },
			rowFreezer: (v, id) => this.update_row(id, 'source_freezer', v),
			rowProject: (v, id) => this.update_row(id, 'project', v),
			rowQty: (v, id) => this.update_row(id, 'planned_qty_lbs', v === '' ? 0 : v),
			rowYield: (v, id, arg) => this.update_row(id, arg, v === '' ? 0 : v),
			rowNotes: (v, id) => this.update_row(id, 'notes', v),
			formDate: v => { this.form.date = v; this.refresh_preview(); },
			formLbs: v => { this.form.lbs = v; this.formError = ''; this.refresh_preview(); },
			formItem: v => { this.form.item = v; this.form.freezer = ''; this.form.project = ''; this.formProjectTouched = false; this.refresh_preview(); },
			formFreezer: v => { this.form.freezer = v; this.form.project = ''; this.formProjectTouched = false; this.refresh_preview(); },
			formProject: v => { this.form.project = v; this.formProjectTouched = true; this.refresh_preview(); },
		};
		const inputs = {
			rowQty: (v, id) => this.update_row(id, 'planned_qty_lbs', v === '' ? 0 : v, 700),
			rowYield: (v, id, arg) => this.update_row(id, arg, v === '' ? 0 : v, 700),
			rowNotes: (v, id) => this.update_row(id, 'notes', v, 1200),
			formLbs: v => { this.form.lbs = v; this.refresh_preview(); },
		};

		this.el.addEventListener('click', e => {
			const b = e.target.closest('[data-action]');
			if (!b || b.disabled || !this.el.contains(b)) return;
			e.preventDefault();
			const fn = actions[b.dataset.action];
			if (fn) fn(b.dataset.id, b.dataset.arg);
		});
		this.el.addEventListener('change', e => {
			const el = e.target.closest('[data-change]');
			if (!el) return;
			const fn = changes[el.dataset.change];
			if (fn) fn(el.value, el.dataset.id, el.dataset.arg);
		});
		this.el.addEventListener('input', e => {
			const el = e.target.closest('[data-input]');
			if (!el) return;
			const fn = inputs[el.dataset.input];
			if (fn) fn(el.value, el.dataset.id, el.dataset.arg);
		});
	}

	create_item_dialog(id, kind) {
		const r = this.board.rows.find(x => x.name === id);
		const bh = kind === 'bubble_hash';
		const suffix = bh ? 'Bubble Hash' : 'Rosin';
		const d = new frappe.ui.Dialog({
			title: bh ? __('Create Bubble Hash Item') : __('Create Rosin Item'),
			fields: [
				{ fieldname: 'base', fieldtype: 'Data', label: __('Strain Name'), reqd: 1, default: r.base,
					description: __('Fresh Frozen item: {0}', [r.item_name]),
					onchange: () => d.set_value('item_name', (d.get_value('base') || '').trim() + ' - ' + suffix) },
				{ fieldname: 'item_name', fieldtype: 'Data', label: __('Item Name'), read_only: 1, default: r.base + ' - ' + suffix },
				{ fieldname: 'item_group', fieldtype: 'Data', label: __('Item Group'), read_only: 1, default: bh ? this.ctx.bubble_hash_group : this.ctx.rosin_group },
				{ fieldname: 'code', fieldtype: 'Data', label: __('Item Code'), read_only: 1, default: bh ? __('Next code in the BH-##### series') : __('Next code in the RS##### series') },
			],
			primary_action_label: __('Create Item'),
			primary_action: v => {
				d.hide();
				this.mutate('create_item', { row: id, kind, base: v.base }, { row: id });
			},
		});
		d.show();
	}

	reload_view() {
		if (!this.view.from || !this.view.to || this.view.to < this.view.from) {
			this.toast = { kind: 'err', text: __('To Date cannot be before From Date.') };
			return this.render();
		}
		this.toast = null;
		this.load();
	}

	bump(id, delta) {
		const r = this.board.rows.find(x => x.name === id);
		const next = Math.max(0, (Number(r.planned_lbs) || 0) + delta);
		r.planned_lbs = next;
		const input = this.el.querySelector('[data-focus="qty:' + CSS.escape(id) + '"]');
		if (input) input.value = next;
		this.update_row(id, 'planned_qty_lbs', next, 500);
	}

	set_period(patch) {
		if (this.scope.mode === 'draft') {
			Object.assign(this.draft, patch);
			if (this.draft.plan_type === 'Custom' && (!this.draft.to_date || this.draft.to_date < this.draft.from_date)) this.draft.to_date = this.draft.from_date;
			this.day = 'all';
			return this.load();
		}
		const p = this.board.plan;
		const next = Object.assign({ plan_type: p.plan_type, from_date: p.from_date, to_date: p.to_date }, patch);
		this.day = 'all';
		this.mutate('update_plan', { plan: p.name, plan_type: next.plan_type, from_date: next.from_date, to_date: next.to_date });
	}
}
