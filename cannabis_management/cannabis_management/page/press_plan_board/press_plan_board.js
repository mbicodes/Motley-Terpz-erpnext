// Press Plan Board: the single screen for planning rosin pressing. Layout follows motley-press-production-plan-demo.html.
// All rules (queue, stock check, Work Order and job card updates, actuals) run on the server; this file only renders and calls.
const PPB_M = 'cannabis_management.cannabis_management.page.press_plan_board.press_plan_board.';
const PPB_LIVE_DOCTYPES = ['Press Production Plan', 'Work Order', 'Job Card', 'Stock Entry'];

const PPB_PILLS = {
	'Scheduled': ['#EDE9FE', '#4C1D95'],
	'Pressed': ['#FEF3C7', '#854D0E'],
	'Whipped': ['#DCFCE7', '#166534'],
	'Cancelled': ['#FDE8E1', '#9A3412'],
	'Draft': ['#f1ecf7', '#4a3f5c'],
	'In Progress': ['#FBEBD9', '#8A4508'],
	'Completed': ['#f3e6fb', '#4d129e'],
	'Not saved': ['#f7f3fc', '#6b6080'],
	'All plans': ['#E3EDFA', '#1E4E8C'],
};

const PPB_SVG = {
	check: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
	x: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
	plus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
	cal: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></svg>',
	info: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
	warn: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
	chev: rot => '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="transform:' + rot + '"><path d="m9 6 6 6-6 6"/></svg>',
};

const ppb_esc = v => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const ppb_fmt = n => Math.round(n || 0).toLocaleString('en-US');
const ppb_pct = n => (Math.round((n || 0) * 10) / 10).toFixed(1) + '%';
const ppb_num = n => String(Math.round((n || 0) * 100) / 100);
const ppb_words = n => n + (n === 1 ? ' ' + __('wash') : ' ' + __('washes'));
const PPB_WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const PPB_MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function ppb_day(key) {
	const d = new Date(key + 'T00:00:00');
	if (!key || isNaN(d.getTime())) return { key, short: '—', md: '—', label: '—', year: '' };
	const md = PPB_MO[d.getMonth()] + ' ' + d.getDate();
	return { key, short: PPB_WD[d.getDay()], md, label: PPB_WD[d.getDay()] + ', ' + md, year: d.getFullYear() };
}

function ppb_key(d) {
	return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function ppb_range(from, to) {
	const out = [];
	if (!from || !to) return out;
	const d = new Date(from + 'T00:00:00'), end = new Date(to + 'T00:00:00');
	while (d <= end && out.length < 62) { out.push(ppb_day(ppb_key(d))); d.setDate(d.getDate() + 1); }
	return out;
}

function ppb_period(from, to) {
	if (!from || !to) return '—';
	const a = ppb_day(from), b = ppb_day(to);
	if (from === to) return a.label + ', ' + a.year;
	return a.md + (a.year !== b.year ? ', ' + a.year : '') + ' – ' + b.md + ', ' + b.year;
}

function ppb_opts(list, sel) {
	return list.map(o => '<option value="' + ppb_esc(o.key) + '"' + (String(o.key) === String(sel == null ? '' : sel) ? ' selected' : '') + '>' + ppb_esc(o.label) + '</option>').join('');
}

const ppb_link = (doctype, name, cls) => name
	? '<a class="mono' + (cls ? ' ' + cls : '') + '" href="/app/' + frappe.router.slug(doctype) + '/' + encodeURIComponent(name) + '" target="_blank" rel="noopener">' + ppb_esc(name) + '</a>'
	: '';

// "Only 444 g of 850 g is in Finished Goods - MTM for PROJ-0061; 2 washes share BH-00218 (1,294 g in stock)."
function ppb_stock_warn(st, item, project) {
	if (!st || st.covered + 0.5 >= st.need) return '';
	let t = st.covered > 0.5
		? __('Only {0} g of {1} g is in {2}', [ppb_fmt(st.covered), ppb_fmt(st.need), st.warehouse])
		: __('No Bubble Hash for this wash in {0}', [st.warehouse]);
	if (project) t += ' ' + __('for {0}', [project]);
	t += '.';
	if (st.sharing > 1) t += ' ' + __('{0} washes share {1} ({2} g in stock).', [st.sharing, item, ppb_fmt(st.stock)]);
	return '<span class="ppb-warn">' + PPB_SVG.warn + '<span>' + ppb_esc(t) + '</span></span>';
}

frappe.pages['press-plan-board'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Press Plan Board'), single_column: true });
	$(wrapper).addClass('press-plan-board-page');
	const root = $('<div class="press-plan-board"><div class="ppb-loading">' + __('Loading…') + '</div></div>').appendTo(page.main);
	wrapper.ppb = new PressPlanBoard(root[0]);
};

frappe.pages['press-plan-board'].on_page_show = function (wrapper) {
	wrapper.ppb && wrapper.ppb.route();
};

class PressPlanBoard {
	constructor(el) {
		this.el = el;
		this.ctx = null;
		this.board = null;
		this.scope = null;
		this.view = null;
		this.draft = null;
		this.day = 'all';
		this.target = '';
		this.expanded = {};
		this.rowErr = {};
		this.toast = null;
		this.noStockOpen = false;
		this.saving = 0;
		this.saveState = '';
		this.chain = Promise.resolve();
		this.timers = {};
		this.pending = 0;
		this.updatedAt = null;
		this.bind();
		// live: refresh when a plan, Work Order, job card or stock entry changes anywhere, plus a slow poll
		frappe.realtime.on('list_update', d => this.on_change(d));
		frappe.realtime.on('doc_update', d => this.on_change(d));
		this.subscribe();
		setInterval(() => this.tick(), 60000);
		document.addEventListener('visibilitychange', () => {
			if (document.visibilityState === 'visible' && this.updatedAt && Date.now() - this.updatedAt > 30000) this.tick();
		});
	}

	subscribe() {
		PPB_LIVE_DOCTYPES.forEach(dt => frappe.realtime.doctype_subscribe && frappe.realtime.doctype_subscribe(dt));
	}

	on_board() {
		return frappe.get_route()[0] === 'press-plan-board';
	}

	idle() {
		const a = document.activeElement;
		const typing = a && this.el.contains(a) && (a.tagName === 'INPUT' || a.tagName === 'SELECT' || a.tagName === 'TEXTAREA');
		return !this.saving && !this.pending && !typing && !(window.cur_dialog && cur_dialog.display);
	}

	on_change(d) {
		if (!d || !PPB_LIVE_DOCTYPES.includes(d.doctype) || !this.board || !this.on_board()) return;
		this.debounce('live', () => this.tick(), 1500);
	}

	tick() {
		if (!this.ctx || !this.scope || !this.on_board() || document.visibilityState !== 'visible') return;
		if (!this.idle()) return this.debounce('live', () => this.tick(), 3000);
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
		frappe.set_route('press-plan-board', ...(plan ? [plan] : []));
	}

	load_context() {
		return frappe.xcall(PPB_M + 'get_context').then(ctx => { this.ctx = ctx; });
	}

	server_scope() {
		if (this.scope.mode === 'plan') return { mode: 'plan', plan: this.scope.plan };
		if (this.scope.mode === 'draft') return { mode: 'view', from: this.draft_period().from, to: this.draft_period().to };
		return { mode: 'view', from: this.view.from, to: this.view.to };
	}

	load() {
		return frappe.xcall(PPB_M + 'get_board', { scope: this.server_scope() })
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
	}

	// ---------- writes ----------
	mutate(method, args, opt = {}) {
		this.saving++;
		this.saveState = 'saving';
		this.paint_status();
		const run = () => frappe.call({ method: PPB_M + method, args: Object.assign({}, args, { scope: this.server_scope() }) })
			.then(r => {
				const m = r.message || {};
				if (m.plans) this.ctx.plans = m.plans;
				if (m.ok) {
					this.saveState = 'saved';
					if (opt.row) delete this.rowErr[opt.row];
					if (m.message) this.toast = { kind: 'ok', text: m.message };
				} else {
					this.saveState = 'error';
					if (opt.row) this.rowErr[opt.row] = m.error;
					else this.toast = { kind: 'err', text: m.error };
				}
				if (m.board) this.apply(m.board); else this.render();
				return m;
			})
			.catch(() => { this.saveState = 'error'; this.render(); })
			.finally(() => { this.saving--; this.paint_status(); });
		this.chain = this.chain.then(run, run);
		return this.chain;
	}

	debounce(key, fn, ms) {
		clearTimeout(this.timers[key]);
		this.timers[key] = setTimeout(fn, ms);
	}

	update_row(row, field, value, ms) {
		const go = () => this.mutate('update_row', { row, field, value }, { row });
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
			return { from: d.from_date, to: ppb_key(e) };
		}
		return { from: d.from_date, to: d.to_date };
	}

	plan_type() {
		return this.scope.mode === 'plan' ? this.board.plan.plan_type : this.scope.mode === 'draft' ? this.draft.plan_type : 'View';
	}

	plan_period_of(row) {
		if (this.scope.mode === 'plan') return { from: this.board.plan.from_date, to: this.board.plan.to_date };
		const p = (this.board.plans_in_view || []).find(x => x.name === row.plan);
		return p ? { from: p.from_date, to: p.to_date } : { from: row.planned_date, to: row.planned_date };
	}

	compute() {
		const b = this.board, p = this.period();
		const days = ppb_range(p.from, p.to);
		const rows = this.scope.mode === 'draft' ? [] : b.rows;
		const scoped = this.day === 'all' ? rows : rows.filter(r => r.planned_date === this.day);
		const live = scoped.filter(r => r.status !== 'Cancelled');
		const sum = (list, f) => list.reduce((s, x) => s + (f(x) || 0), 0);
		const ready = b.queue.filter(q => q.stock && q.stock.covered > 0.5);
		const noStock = b.queue.filter(q => !(q.stock && q.stock.covered > 0.5));
		const pressed = live.filter(r => r.actual_rosin_g > 0);
		// the day picked for "Schedule on" always lies in the period shown
		const keys = days.map(d => d.key);
		if (!keys.includes(this.target)) {
			const today = this.ctx.today;
			this.target = this.day !== 'all' ? this.day : keys.includes(today) ? today : (keys[0] || '');
		}
		return {
			days, rows: scoped, live, ready, noStock, all: rows,
			waitG: sum(ready, q => Math.min(q.bh_planned_g, q.stock.covered)),
			planG: sum(live, r => r.bh_planned_g), expG: sum(live, r => r.expected_rosin_g),
			actG: sum(pressed, r => r.actual_rosin_g), actIn: sum(pressed, r => r.bh_planned_g), pressedN: pressed.length,
		};
	}

	// ---------- render ----------
	render() {
		if (!this.ctx || !this.scope) return;
		const focus = this.capture_focus();
		this.el.innerHTML = this.board ? this.html() : '<div class="ppb-loading">' + __('Could not load the board.') + '</div>';
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
		return '<span data-role="save-status" class="pill" role="status" style="background:' + m[0] + ';color:' + m[1] + ';font-weight:700">' + (s === 'saved' ? PPB_SVG.check + ' ' : '') + m[2] + '</span>';
	}

	capture_focus() {
		const a = document.activeElement;
		if (!a || !this.el.contains(a) || !a.dataset.focus) return null;
		let start = null, end = null;
		try { start = a.selectionStart; end = a.selectionEnd; } catch (e) { /* number inputs */ }
		return { key: a.dataset.focus, value: a.tagName === 'INPUT' ? a.value : null, start, end };
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
		return this.html_band() + '<main class="ppb-main">' + this.html_header(v) + this.html_toast() + this.html_kpis(v) +
			'<div class="ppb-layout">' + this.html_queue(v) + '<section class="ppb-col">' + this.html_tabs(v) + this.html_schedule(v) + this.html_how() + '</section></div></main>';
	}

	html_band() {
		const crumb = this.scope.mode === 'plan' ? this.board.plan.name : this.scope.mode === 'draft' ? __('New plan') : __('All plans');
		const user = this.ctx.user.full_name || this.ctx.user.name;
		const app = this.ctx.app_name || '';
		const at = this.updatedAt ? new Date(this.updatedAt) : null;
		const live = at ? '<span class="ppb-live" title="' + __('Refreshes automatically when plans, Work Orders, job cards or stock entries change') + '"><span class="ppb-live-dot"></span>' + __('Live') + ' · ' + __('updated {0}', [String(at.getHours()).padStart(2, '0') + ':' + String(at.getMinutes()).padStart(2, '0')]) + '</span>' : '';
		return '<header class="ppb-band"><div class="ppb-brand"><div class="ppb-logo">' + ppb_esc(app.charAt(0).toUpperCase()) + '</div>' +
			'<div style="display:flex;flex-direction:column"><span style="font-weight:800;font-size:16px">' + ppb_esc(app) + '</span><span style="font-size:12px;color:#e4d6f7">' + ppb_esc(this.ctx.company) + '</span></div></div>' +
			'<nav aria-label="Breadcrumb" class="ppb-crumbs"><a href="/app/manufacturing">' + __('Manufacturing') + '</a><span aria-hidden="true">/</span>' +
			'<a data-action="home" href="#">' + __('Press Production Plan') + '</a><span aria-hidden="true">/</span><span style="color:#fff;font-weight:700">' + ppb_esc(crumb) + '</span></nav>' +
			'<div style="display:flex;align-items:center;gap:14px">' + live + '<div style="display:flex;align-items:center;gap:10px"><div class="ppb-avatar">' + ppb_esc(user.charAt(0).toUpperCase()) + '</div><span style="font-size:13px">' + ppb_esc(user) + '</span></div></div></header>';
	}

	html_header(v) {
		const mode = this.scope.mode, p = this.board.plan, ctx = this.ctx;
		const status = mode === 'plan' ? p.status : mode === 'draft' ? 'Not saved' : 'All plans';
		const pill = PPB_PILLS[status] || PPB_PILLS.Draft;
		const can = mode === 'draft' || (mode === 'plan' && p.can_write);
		const strong = t => '<strong style="color:var(--ink)">' + t + '</strong>';
		let meta = '';
		if (mode === 'plan') meta += '<span>' + __('Plan') + ' ' + strong(ppb_esc(p.name)) + '</span>';
		else if (mode === 'draft') meta += '<span>' + __('Plan') + ' ' + strong(__('New, saved with the first scheduled wash or Create Plan')) + '</span>';
		else {
			const links = this.board.plans_in_view.map(x => '<a href="#" class="mono" data-action="openPlan" data-id="' + ppb_esc(x.name) + '">' + ppb_esc(x.name) + '</a>').join(', ');
			meta += '<span>' + __('Showing') + ' ' + strong(__('all plans in this period')) + '</span><span>' + __('Plans') + ' ' + strong(links || __('none yet')) + '</span>';
		}
		meta += '<span>' + __('Press') + ' ' + strong(ppb_esc(ctx.press_workstation)) + '</span><span>' + __('Source') + ' ' + strong(ppb_esc(ctx.source_warehouse)) + '</span>';
		if (mode !== 'view') meta += '<span>' + __('Planned By') + ' ' + strong(ppb_esc(mode === 'plan' ? p.planned_by : ctx.user.full_name)) + '</span>';
		meta += '<span>' + __('Run time') + ' ' + strong(__('not fixed, planned by grams')) + '</span>';

		const plans = ctx.plans.slice();
		if (p && !plans.some(x => x.name === p.name)) plans.unshift({ name: p.name, from_date: p.from_date, to_date: p.to_date, washes: this.board.rows.length, status: p.status });
		const selOpts = [{ key: '', label: __('All plans · by date range') }].concat(plans.map(x => ({
			key: x.name, label: x.name + ' · ' + ppb_period(x.from_date, x.to_date) + ' · ' + ppb_words(x.washes || 0) + (x.status === 'Draft' ? '' : ' · ' + __(x.status)),
		})));
		const selected = mode === 'plan' ? p.name : mode === 'draft' ? '__new' : '';
		if (mode === 'draft') selOpts.push({ key: '__new', label: __('New plan (not saved)') });

		let h = '<section class="card" style="padding:22px 24px;display:flex;flex-direction:column;gap:18px"><div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:20px;align-items:flex-start">' +
			'<div style="display:flex;flex-direction:column;gap:8px;min-width:0"><div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">' +
			'<h1 class="ppb-h1">' + (mode === 'draft' ? __('New Press Production Plan') : __('Press Production Plan')) + '</h1>' +
			'<span class="pill" style="background:' + pill[0] + ';color:' + pill[1] + '">' + ppb_esc(__(status)) + '</span>' + this.status_html() + '</div>' +
			'<div class="muted ppb-meta">' + meta + '</div></div>';
		h += '<div style="display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end">' +
			'<label class="lbl ppb-plan-pick">' + __('Plan') + '<select class="field" data-change="pickPlan" style="height:42px">' + ppb_opts(selOpts, selected) + '</select></label>' +
			'<button type="button" class="ppb-btn-out" data-action="newPlan">' + PPB_SVG.plus + __('New Plan') + '</button>' +
			'<a class="ppb-formlink" href="/app/wash-plan-board">' + __('Wash Plan Board') + '</a>' +
			(mode === 'plan' && ctx.is_admin ? '<a class="ppb-formlink" href="/app/press-production-plan/' + encodeURIComponent(p.name) + '">' + __('Open in form') + '</a>' : '') +
			'</div></div>';

		// period controls
		h += '<div style="display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end">';
		if (mode === 'view') {
			const bad = this.view.to < this.view.from;
			h += '<label class="lbl">' + __('From Date') + '<input class="field" type="date" data-change="viewFrom" value="' + ppb_esc(this.view.from) + '" style="height:42px' + (bad ? ';border-color:var(--warnline)' : '') + '"></label>' +
				'<label class="lbl">' + __('To Date') + '<input class="field" type="date" data-change="viewTo" value="' + ppb_esc(this.view.to) + '" style="height:42px' + (bad ? ';border-color:var(--warnline)' : '') + '"></label>' +
				'<div class="lbl">' + __('Quick range') + '<div class="seg">' +
				'<button type="button" data-action="week" data-id="0" style="' + this.seg(this.view.from === ctx.week.from && this.view.to === ctx.week.to) + '">' + __('This week') + '</button>' +
				'<button type="button" data-action="week" data-id="1" style="' + this.seg(false) + '">' + __('Next week') + '</button></div></div>';
		} else {
			const t = this.plan_type();
			const from = mode === 'plan' ? p.from_date : this.draft.from_date;
			const to = mode === 'plan' ? p.to_date : this.draft.to_date;
			const dis = can ? '' : ' disabled';
			h += '<div class="lbl">' + __('Plan Type') + '<div class="seg">' +
				['Daily', 'Weekly', 'Custom'].map(x => '<button type="button" data-action="planType" data-id="' + x + '"' + dis + ' style="' + this.seg(t === x) + '">' + (x === 'Custom' ? PPB_SVG.cal : '') + __(x) + '</button>').join('') + '</div></div>' +
				'<label class="lbl">' + (t === 'Daily' ? __('Date') : t === 'Weekly' ? __('Week Starting') : __('From Date')) +
				'<input class="field" type="date" data-change="planFrom" value="' + ppb_esc(from) + '"' + dis + ' style="height:42px"></label>' +
				(t === 'Custom' ? '<label class="lbl">' + __('To Date') + '<input class="field" type="date" data-change="planTo" value="' + ppb_esc(to) + '"' + dis + ' style="height:42px"></label>' : '');
		}
		const per = this.period();
		h += '<div class="lbl">' + __('Plan Period') + '<div class="ppb-period">' + ppb_esc(ppb_period(per.from, per.to)) + '</div></div>';
		if (mode === 'draft') {
			h += '<button type="button" class="ppb-btn-brand" data-action="createPlan">' + __('Create Plan') + '</button>' +
				'<button type="button" class="ppb-btn-ghost" data-action="cancelDraft">' + __('Cancel') + '</button>';
		}
		return h + '</div></section>';
	}

	seg(on) {
		return 'background:' + (on ? 'var(--brand)' : 'transparent') + ';color:' + (on ? '#fff' : 'var(--ink)');
	}

	html_toast() {
		const t = this.toast;
		if (!t) return '';
		const ok = t.kind === 'ok';
		return '<div role="' + (ok ? 'status' : 'alert') + '" class="ppb-toast ' + (ok ? 'ok' : 'err') + '"><div style="display:flex;align-items:center;gap:10px">' + (ok ? PPB_SVG.check : PPB_SVG.warn) +
			'<span style="font-weight:600">' + ppb_esc(t.text) + '</span></div><button type="button" aria-label="' + __('Dismiss message') + '" data-action="dismiss" class="ppb-toast-x">' + PPB_SVG.x + '</button></div>';
	}

	html_kpis(v) {
		const kpi = (k, val, sub) => '<div class="card kpi"><span class="k">' + k + '</span><span class="v mono">' + val + ' <span class="muted" style="font-size:15px">g</span></span><span class="muted" style="font-size:12px">' + sub + '</span></div>';
		const waitSub = __('{0} not scheduled yet', [ppb_words(v.ready.length)]) + (v.noStock.length ? ' · ' + __('{0} more without stock', [v.noStock.length]) : '');
		return '<section aria-label="' + __('Plan totals') + '" class="ppb-kpis">' +
			kpi(__('Bubble Hash Waiting'), ppb_fmt(v.waitG), waitSub) +
			kpi(__('Planned to Press'), ppb_fmt(v.planG), __('{0} in this view', [ppb_words(v.live.length)])) +
			kpi(__('Expected Rosin'), ppb_fmt(v.expG), __('Micron-wise yields · {0} blended', [ppb_pct(v.planG ? v.expG / v.planG * 100 : 0)])) +
			kpi(__('Actual Rosin Pressed'), ppb_fmt(v.actG), v.pressedN ? __('{0} pressed · {1} of BH', [v.pressedN, ppb_pct(v.actIn ? v.actG / v.actIn * 100 : 0)]) : __('Nothing pressed yet')) +
			'</section>';
	}

	// ---------- Ready to Press ----------
	html_queue(v) {
		const opts = v.days.map(d => ({ key: d.key, label: d.label + ', ' + d.year }));
		const locked = this.scope.mode === 'plan' && !this.board.plan.can_write;
		let h = '<section class="card ppb-queue"><div class="ppb-queue-head"><h2 class="h2">' + __('Ready to Press') + '</h2>' +
			'<span class="muted" style="font-size:13px">' + __('Washed Bubble Hash in {0}, oldest wash first. Pick a day and schedule it.', [ppb_esc(this.ctx.source_warehouse)]) + '</span>' +
			'<label class="lbl" style="flex-direction:row;align-items:center;margin-top:6px">' + __('Schedule on') +
			'<select class="field" data-change="target" data-focus="target" style="flex:1;height:40px;font-size:13px"' + (opts.length ? '' : ' disabled') + '>' + ppb_opts(opts, this.target) + '</select></label></div>';
		if (!v.ready.length && !v.noStock.length) h += '<div class="muted" style="padding:28px 18px;text-align:center">' + __('All washed Bubble Hash is scheduled.') + '</div>';
		else if (!v.ready.length) h += '<div class="muted" style="padding:20px 18px;text-align:center">' + __('No washed Bubble Hash in stock is waiting.') + '</div>';
		v.ready.forEach(q => { h += this.html_lot(q, locked); });
		if (v.noStock.length) {
			h += '<div class="ppb-nostock"><button type="button" class="ppb-more" data-action="toggleNoStock" aria-expanded="' + this.noStockOpen + '">' + PPB_SVG.chev(this.noStockOpen ? 'rotate(90deg)' : 'none') +
				__('{0} Work Orders with no Bubble Hash in stock', [v.noStock.length]) + '</button>' +
				(this.noStockOpen ? '<span class="muted" style="font-size:12px">' + __('Their wash is completed and the Rosin Work Order is still open, but the Bubble Hash is no longer in stock. Close or fix these Work Orders.') + '</span>' : '') + '</div>';
			if (this.noStockOpen) v.noStock.forEach(q => { h += this.html_lot(q, locked); });
		}
		return h + '</section>';
	}

	html_lot(q, locked) {
		const age = q.days == null ? '' : q.days === 0 ? __('Washed today') : q.days === 1 ? __('Washed 1 day ago') : __('Washed {0} days ago', [q.days]);
		const sub = [ppb_esc(q.bubble_hash_item), ppb_esc(q.project || __('No Project')), ppb_link('Work Order', q.rosin_work_order)];
		let h = '<div class="ppb-lot"><div style="display:flex;justify-content:space-between;gap:10px"><span style="font-weight:800">' + ppb_esc(q.strain) + '</span><span class="mono" style="font-weight:600;white-space:nowrap">' + ppb_fmt(q.bh_planned_g) + ' g</span></div>' +
			'<div class="muted ppb-lot-meta">' + sub.map(x => '<span>' + x + '</span>').join('') +
			(age ? '<span style="font-weight:700;color:' + (q.aging ? 'var(--warn)' : 'var(--muted)') + '"' + (q.aging ? ' title="' + __('Waiting {0} days or more', [this.ctx.aging_days]) + '"' : '') + '>' + age + '</span>' : '') + '</div>' +
			'<div class="ppb-chips">' + q.microns.map(m => '<span class="mono ppb-chip">' + ppb_esc(m.label) + ' ' + ppb_fmt(m.g) + ' g</span>').join('') + '</div>';
		if (q.transferred) h += '<span class="ppb-info">' + PPB_SVG.info + '<span>' + ppb_esc(__('Bubble Hash already transferred to {0}.', [q.stock ? q.stock.warehouse : ''])) + '</span></span>';
		h += ppb_stock_warn(q.stock, q.bubble_hash_item, q.project);
		if (q.micron_note) h += '<span class="ppb-warn">' + PPB_SVG.warn + '<span>' + ppb_esc(q.micron_note) + '</span></span>';
		const when = this.target ? ppb_day(this.target).label : '';
		h += '<div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><span class="muted" style="font-size:12px">' + __('Exp. rosin') + ' <strong style="color:var(--ink)">' + ppb_fmt(q.expected_rosin_g) + ' g</strong></span>' +
			'<button type="button" class="ppb-btn" data-action="schedule" data-id="' + ppb_esc(q.rosin_work_order) + '"' + (locked || !this.target ? ' disabled' : ' title="' + ppb_esc(__('Schedule on {0}', [when])) + '"') + '>' + __('Schedule') + '</button></div></div>';
		return h;
	}

	// ---------- schedule ----------
	html_tabs(v) {
		const t = this.plan_type();
		if (t === 'Daily') return '';
		const tabs = [{ key: 'all', short: t === 'Weekly' ? __('All week') : __('All days') }].concat(v.days.length <= 14 ? v.days : []);
		let h = '<nav aria-label="' + __('Plan days') + '" class="ppb-tabs">';
		tabs.forEach(d => {
			const list = (d.key === 'all' ? v.all : v.all.filter(r => r.planned_date === d.key)).filter(r => r.status !== 'Cancelled');
			const g = list.reduce((s, r) => s + r.bh_planned_g, 0), sel = this.day === d.key;
			h += '<button type="button" data-action="pickDay" data-id="' + d.key + '" class="ppb-tab' + (sel ? ' on' : '') + '">' +
				'<span style="font-weight:800;font-size:13px">' + ppb_esc(d.short) + '</span><span class="ppb-tab-sub">' + (d.key === 'all' ? '' : ppb_esc(d.md) + ' · ') + ppb_words(list.length) + ' · ' + ppb_fmt(g) + ' g</span></button>';
		});
		return h + '</nav>';
	}

	html_schedule(v) {
		const per = this.period();
		const label = this.day === 'all' ? ppb_period(per.from, per.to) : ppb_day(this.day).label + ', ' + ppb_day(this.day).year;
		let h = '<div class="card" style="overflow:hidden"><div style="padding:16px 20px;border-bottom:1px solid var(--line);display:flex;flex-direction:column;gap:2px"><h2 class="h2">' + __('Press Schedule') + '</h2>' +
			'<span class="muted" style="font-size:13px">' + ppb_esc(label + ' · ' + ppb_words(v.live.length) + ' · ' + ppb_fmt(v.planG) + ' g ' + __('Bubble Hash')) + '</span></div>';
		if (!v.rows.length) {
			h += '<div class="muted" style="padding:36px 20px;text-align:center">' + (this.scope.mode === 'draft'
				? __('This plan has no washes yet. Schedule Bubble Hash from “Ready to Press”; the plan is saved with the first wash.')
				: __('Nothing scheduled for this period. Schedule Bubble Hash from “Ready to Press”.')) + '</div>';
		}
		v.rows.forEach(r => { h += this.html_row(r); });
		return h + '</div>';
	}

	html_row(r) {
		const d = ppb_day(r.planned_date), p = PPB_PILLS[r.status] || PPB_PILLS.Scheduled, ex = !!this.expanded[r.name], err = this.rowErr[r.name];
		const col = (k, val) => '<div class="ppb-col-v"><span class="k" style="font-size:11px">' + k + '</span><span class="mono" style="font-weight:600">' + val + '</span></div>';
		const meta = [ppb_esc(r.bubble_hash_item), ppb_esc(r.project || __('No Project')), ppb_link('Work Order', r.rosin_work_order)];
		if (this.scope.mode === 'view') meta.push('<a href="#" class="mono" data-action="openPlan" data-id="' + ppb_esc(r.plan) + '" title="' + __('Open this plan on the board') + '">' + ppb_esc(r.plan) + '</a>');
		let h = '<div class="ppb-row-wrap"><div class="ppb-row">' +
			'<button type="button" class="icon-btn" data-action="toggle" data-id="' + r.name + '" aria-expanded="' + ex + '" aria-label="' + (ex ? __('Hide micron breakdown') : __('Show micron breakdown')) + '">' + PPB_SVG.chev(ex ? 'rotate(90deg)' : 'none') + '</button>' +
			'<div style="display:flex;flex-direction:column;gap:2px;min-width:70px"><span style="font-weight:800">' + d.short + '</span><span class="muted" style="font-size:12px">' + d.md + ', ' + d.year + '</span></div>' +
			'<div style="display:flex;flex-direction:column;gap:3px;flex:1 1 220px;min-width:0"><span style="font-weight:800">' + ppb_esc(r.strain) + '</span><span class="muted ppb-lot-meta">' + meta.map(x => '<span>' + x + '</span>').join('') + '</span>' +
			ppb_stock_warn(r.stock, r.bubble_hash_item, r.project) +
			(r.micron_note ? '<span class="ppb-warn">' + PPB_SVG.warn + '<span>' + ppb_esc(r.micron_note) + '</span></span>' : '') +
			(err ? '<span class="ppb-warn" role="alert">' + PPB_SVG.warn + '<span>' + ppb_esc(err) + '</span></span>' : '') + '</div>' +
			col(__('BH In'), ppb_fmt(r.bh_planned_g) + ' g') + col(__('Exp. Rosin'), ppb_fmt(r.expected_rosin_g) + ' g') +
			col(__('Actual Rosin'), r.actual_rosin_g ? ppb_fmt(r.actual_rosin_g) + ' g · ' + ppb_pct(r.actual_yield) : '—') +
			'<span class="pill" style="background:' + p[0] + ';color:' + p[1] + '">' + ppb_esc(__(r.status)) + '</span>' +
			'<div class="ppb-actions">' + this.html_actions(r) + '</div></div>';
		if (ex) h += this.html_detail(r);
		return h + '</div>';
	}

	html_actions(r) {
		const jc = r.job_card ? '<a class="ppb-btn' + (r.status === 'Scheduled' ? ' solid' : '') + '" href="/app/job-card/' + encodeURIComponent(r.job_card) + '" target="_blank" rel="noopener">' + __('Open Job Card') + '</a>' : '';
		if (r.status === 'Scheduled') {
			const block = r.unschedule_block;
			return jc + (r.editable ? '<button type="button" class="ppb-btn ghost" data-action="unschedule" data-id="' + r.name + '"' + (block ? ' disabled title="' + ppb_esc(__('Cannot unschedule: {0}', [block])) + '"' : '') + '>' + __('Unschedule') + '</button>' : '');
		}
		if (r.status === 'Pressed') {
			if (r.can_whip) return '<button type="button" class="ppb-btn" data-action="whip" data-id="' + r.name + '">' + __('{0} Done', [this.ctx.whip_step]) + '</button>' + jc;
			return '<span class="muted" style="font-size:12px;font-weight:600">' + ppb_esc(__('Record {0} on the job card', [this.ctx.whip_step])) + '</span>' + jc;
		}
		if (r.status === 'Whipped') return '<span style="color:var(--brand);font-weight:700;font-size:13px;display:flex;align-items:center;gap:6px">' + PPB_SVG.check + __('Job card complete') + '</span>' + (r.job_card ? ppb_link('Job Card', r.job_card) : '');
		return '<span class="muted" style="font-size:12px;font-weight:600">' + __('Work Order cancelled') + '</span>';
	}

	html_detail(r) {
		const edit = r.editable;
		let h = '<div class="ppb-detail"><div class="ppb-detail-head"><span style="font-weight:800;font-size:13px">' + __('Micron Breakdown') + '</span><span class="muted" style="font-size:12px">' +
			(r.wash_job_card ? __('BH grams from the wash job card {0}', [ppb_link('Job Card', r.wash_job_card)]) : __('No micron split on the wash job card')) + ' · ' + __('each micron pressed separately') + '</span></div>' +
			'<div style="overflow-x:auto"><div style="min-width:680px"><div class="ppb-mrow k" style="font-size:11px;padding:8px 14px"><span>' + __('Micron') + '</span><span>' + __('BH (g)') + '</span><span>' + __('Exp. Yield') + '</span><span>' + __('Exp. Rosin (g)') + '</span><span>' + __('Actual (g)') + '</span><span>' + __('Actual Yield') + '</span></div>';
		const done = r.status === 'Pressed' || r.status === 'Whipped' || r.actual_rosin_g > 0;
		r.microns.forEach(m => {
			h += '<div class="ppb-mrow" style="border-top:1px solid var(--line2)"><span style="font-weight:700">' + ppb_esc(m.label) + '</span><span class="mono">' + ppb_fmt(m.bh) + '</span><span>' +
				(edit ? '<label style="display:flex;align-items:center;gap:4px"><span class="sr">' + __('Expected yield for {0}', [m.label]) + '</span><input type="number" min="0" max="100" step="0.5" class="mono ppb-yield" data-input="rowYield" data-change="rowYield" data-id="' + r.name + '" data-arg="exp_yield_' + m.slot + '" data-focus="y:' + m.slot + ':' + r.name + '" value="' + ppb_esc(ppb_num(m.exp_yield)) + '"> %</label>'
					: '<span class="mono">' + ppb_pct(m.exp_yield) + '</span>') +
				'</span><span class="mono" style="font-weight:600">' + ppb_fmt(m.exp_rosin) + '</span><span class="mono" style="font-weight:600">' + (done ? ppb_fmt(m.act) : '—') + '</span><span class="mono" style="font-weight:600">' + (done && m.act ? ppb_pct(m.act_yield) : '—') + '</span></div>';
		});
		h += '<div class="ppb-mrow ppb-mtotal"><span>' + __('Total') + '</span><span class="mono">' + ppb_fmt(r.bh_planned_g) + '</span><span class="mono">' + ppb_pct(r.bh_planned_g ? r.expected_rosin_g / r.bh_planned_g * 100 : 0) + '</span><span class="mono">' + ppb_fmt(r.expected_rosin_g) + '</span><span class="mono">' + (done ? ppb_fmt(r.actual_rosin_g) : '—') + '</span><span class="mono">' + (done && r.actual_rosin_g ? ppb_pct(r.actual_yield) : '—') + '</span></div></div></div>';

		// Work Order note, steps, links, edits
		const wo = ppb_link('Work Order', r.rosin_work_order);
		const woNote = done
			? __('Work Order {0}: pressed from {1} g Bubble Hash; expected {2} g rosin, actual {3} g.', [wo, ppb_fmt(r.bh_planned_g), ppb_fmt(r.expected_rosin_g), ppb_fmt(r.actual_rosin_g)])
			: r.transferred
			? __('Work Order {0}: {1} g Bubble Hash already transferred to Work In Progress; rosin target {2} g.', [wo, ppb_fmt(r.bh_planned_g), ppb_fmt(r.expected_rosin_g)])
			: __('Work Order {0}: BH to consume set to {1} g (wash produced {2} g) instead of the expected-yield quantity; rosin target {3} g.', [wo, ppb_fmt(r.bh_planned_g), ppb_fmt(r.bh_actual_g), ppb_fmt(r.expected_rosin_g)]);
		const step = (name, st) => ppb_esc(name) + ' ' + (st === 'Complete' ? __('complete') : st === 'Work In Progress' ? __('in progress') : __('pending'));
		const links = [];
		if (r.metrc_tag) links.push(__('METRC tag') + ' <strong class="mono" style="color:var(--ink)">' + ppb_esc(r.metrc_tag) + '</strong>');
		if (r.material_request) links.push(__('Wash MR') + ' ' + ppb_link('Material Request', r.material_request));
		if (r.hash_work_order) links.push(__('Hash Work Order') + ' ' + ppb_link('Work Order', r.hash_work_order));
		if (r.wash_plan) links.push(__('Wash plan') + ' <a class="mono" href="/app/wash-plan-board/' + encodeURIComponent(r.wash_plan) + '">' + ppb_esc(r.wash_plan) + '</a>');
		if (r.washed_on) links.push(__('Washed {0}', [ppb_day(r.washed_on).label + ', ' + ppb_day(r.washed_on).year]));
		h += '<div class="muted ppb-detail-foot"><span>' + woNote + '</span><span>' + step(this.ctx.press_step, r.steps.press) + ' · ' + step(this.ctx.whip_step, r.steps.whip) + '.</span>' +
			(links.length ? '<span class="ppb-links">' + links.map(x => '<span>' + x + '</span>').join('') + '</span>' : '');
		if (edit) {
			const per = this.plan_period_of(r);
			const days = ppb_range(per.from, per.to).map(x => ({ key: x.key, label: x.label + ', ' + x.year }));
			h += '<div class="ppb-edits"><label class="lbl">' + __('Press date') + '<select class="field" data-change="rowDate" data-id="' + r.name + '" data-focus="d:' + r.name + '" style="height:38px;font-size:13px">' + ppb_opts(days, r.planned_date) + '</select></label>' +
				(r.can_change_bh
					? '<label class="lbl">' + __('BH to press (g)') + '<input type="number" min="0" step="1" class="field mono" style="height:38px;width:140px" data-input="rowBh" data-change="rowBh" data-id="' + r.name + '" data-focus="bh:' + r.name + '" value="' + ppb_esc(ppb_num(r.bh_planned_g)) + '"></label>'
					: '') + '</div>';
		}
		return h + '</div></div>';
	}

	html_how() {
		const step = (n, t) => '<div style="display:flex;gap:10px"><span class="ppb-step">' + n + '</span><span>' + t + '</span></div>';
		return '<section class="ppb-how"><h2 class="h2">' + __('How the press plan works') + '</h2><div style="display:flex;flex-direction:column;gap:10px;font-size:13px;color:#ece3f9">' +
			step(1, __('When a wash is completed, its Bubble Hash and micron split come into Ready to Press automatically.')) +
			step(2, __('Scheduling a wash dates its existing Rosin Pressing Work Order and job card and sets the Work Order to the actual Bubble Hash grams. No new Material Request is needed.')) +
			step(3, __('Completing the job card writes rosin grams per micron back to the plan; {0} closes the wash.', [ppb_esc(this.ctx.whip_step)])) + '</div></section>';
	}

	// ---------- events ----------
	bind() {
		const find = id => this.board.rows.find(x => x.name === id);
		const actions = {
			home: () => { this.view = null; this.go(); },
			openPlan: id => this.go(id),
			newPlan: () => this.go('new'),
			cancelDraft: () => this.go(),
			dismiss: () => { this.toast = null; this.render(); },
			pickDay: id => { this.day = id; if (id !== 'all') this.target = id; this.render(); },
			toggle: id => { this.expanded[id] = !this.expanded[id]; this.render(); },
			toggleNoStock: () => { this.noStockOpen = !this.noStockOpen; this.render(); },
			week: id => {
				const s = new Date(this.ctx.week.from + 'T00:00:00');
				s.setDate(s.getDate() + 7 * Number(id));
				const e = new Date(s);
				e.setDate(e.getDate() + 6);
				this.view = { from: ppb_key(s), to: ppb_key(e) };
				this.day = 'all';
				this.load();
			},
			planType: id => this.set_period({ plan_type: id }),
			createPlan: () => {
				const d = this.draft, p = this.draft_period();
				this.mutate('create_plan', { plan_type: d.plan_type, from_date: p.from, to_date: p.to });
			},
			schedule: id => {
				const q = this.board.queue.find(x => x.rosin_work_order === id);
				const args = { rosin_work_order: id, planned_date: this.target };
				if (this.scope.mode === 'plan') args.plan = this.scope.plan;
				if (this.scope.mode === 'draft') args.new_plan = Object.assign({}, this.draft, { to_date: this.draft_period().to });
				const go = () => this.mutate('schedule', args);
				const st = q && q.stock;
				if (st && st.covered + 0.5 < st.need) {
					frappe.confirm(__('Only {0} g of the {1} g Bubble Hash for {2} is in stock. Schedule it anyway?', [ppb_fmt(st.covered), ppb_fmt(st.need), q.strain]), go);
				} else go();
			},
			unschedule: id => {
				const r = find(id);
				frappe.confirm(__('Move {0} back to Ready to Press? Work Order {1} gets its original start date back.', [r.strain, r.rosin_work_order]),
					() => this.mutate('unschedule', { row: id }, { row: id }));
			},
			whip: id => {
				const r = find(id);
				frappe.confirm(__('Mark {0} complete on job card {1}?', [this.ctx.whip_step, r.job_card]),
					() => this.mutate('complete_whipping', { row: id }, { row: id }));
			},
		};
		const changes = {
			pickPlan: v => { if (v !== '__new') this.go(v || null); },
			viewFrom: v => { this.view = Object.assign({}, this.view, { from: v }); this.day = 'all'; this.reload_view(); },
			viewTo: v => { this.view = Object.assign({}, this.view, { to: v }); this.day = 'all'; this.reload_view(); },
			planFrom: v => this.set_period({ from_date: v }),
			planTo: v => this.set_period({ to_date: v }),
			target: v => { this.target = v; this.render(); },
			rowYield: (v, id, arg) => this.update_row(id, arg, v === '' ? 0 : v),
			rowBh: (v, id) => this.update_row(id, 'bh_planned_g', v === '' ? 0 : v),
			rowDate: (v, id) => this.update_row(id, 'planned_date', v),
		};
		const inputs = {
			rowYield: (v, id, arg) => this.update_row(id, arg, v === '' ? 0 : v, 700),
			rowBh: (v, id) => this.update_row(id, 'bh_planned_g', v === '' ? 0 : v, 900),
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

	reload_view() {
		if (!this.view.from || !this.view.to || this.view.to < this.view.from) {
			this.toast = { kind: 'err', text: __('To Date cannot be before From Date.') };
			return this.render();
		}
		this.toast = null;
		this.load();
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
