// Sales Operation Board: Board · By Owner · Calendar · List over Sales Pipeline Deal.
// Stages, owners, lists, alert rules and stock come from the server (Sales Pipeline Settings); this file renders and calls.
(function () {
	const ROUTE = 'sales-operation-board';
	const M = 'cannabis_management.cannabis_management.page.sales_operation_board.sales_operation_board.';
	const DT = 'Sales Pipeline Deal';
	const NONE = '__none';
	const LS_COLS = 'sob_list_cols_v1';
	const VIEWS = [['board', 'Board'], ['owner', 'By Owner'], ['calendar', 'Calendar'], ['list', 'List']];
	const ICON = {
		phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
		flask: '<path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-2.5L14 9V3"/>',
		flag: '<path d="M4 22V4M4 4h12l-2 4 2 4H4"/>',
		truck: '<path d="M3 6h11v10H3zM14 10h4l3 3v3h-7"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
	};
	const svg = (p, size) => `<svg width="${size || 13}" height="${size || 13}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
	const EVENTS = [
		{ key: 'followup', field: 'next_step_due', label: 'Follow-up', color: '#1D4ED8', bg: '#DBEAFE', icon: ICON.phone },
		{ key: 'sample', field: 'sample_date', label: 'Sample', color: '#92400E', bg: '#FEF3C7', icon: ICON.flask },
		{ key: 'close', field: 'expected_close', label: 'Close', color: '#166534', bg: '#DCFCE7', icon: ICON.flag },
		{ key: 'delivery', field: 'delivery_pickup', label: 'Delivery', color: '#6D28D9', bg: '#EDE9FE', icon: ICON.truck },
	];
	const LIST_COLS = [
		['stage', 'Stage', 'stage'], ['account', 'Account'], ['deal_owner', 'Owner', 'owner'], ['priority', 'Priority', 'priority'],
		['product_line', 'Product Line'], ['tier', 'Tier'], ['total_grams', 'Grams', 'num'], ['price_per_gram', 'Price/g', 'money2'],
		['deal_value', 'Deal Value', 'money'], ['weighted_value', 'Weighted', 'money'], ['next_step_due', 'Next Follow-up', 'date_edit'],
		['expected_close', 'Expected Close', 'date'], ['modified', 'Last Updated', 'datetime'],
		['contact_name', 'Contact'], ['phone', 'Phone'], ['email', 'Email'], ['customer', 'Customer'], ['lead', 'Lead'],
		['timeline', 'Timeline'], ['status_detail', 'Status Detail'], ['samples', 'Samples'], ['copack', 'Copack'],
		['hardware', 'Hardware'], ['sample_date', 'Sample Date', 'date'], ['delivery_pickup', 'Delivery / Pickup', 'date'],
		['days_in_stage', 'Days in Stage', 'num'], ['probability', 'Win %', 'pct'], ['value_override', 'Value Override', 'money'],
		['payment_terms', 'Payment Terms'], ['lead_source', 'Lead Source'], ['form', 'Form'], ['size_per_strain', 'Size per Strain'],
		['strain_profiles', 'Strain Profiles'], ['location_address', 'Location'], ['license_number', 'License #'],
	];
	const DEFAULT_COLS = LIST_COLS.slice(0, 13).map(c => c[0]);
	const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
	const MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

	const esc = v => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
	const n0 = n => Math.round(+n || 0).toLocaleString('en-US');
	const usd = n => '$' + n0(n);
	const money2 = n => '$' + (Math.round((+n || 0) * 100) / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	const fdate = s => (s ? frappe.datetime.str_to_user(String(s).slice(0, 10)) : '');
	const pd = s => { const d = new Date(String(s).slice(0, 10) + 'T00:00:00'); return isNaN(d.getTime()) ? null : d; };
	const key = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
	const addDays = (d, n) => { const x = new Date(d.getTime()); x.setDate(x.getDate() + n); return x; };
	const nice = s => { const d = pd(s); return d ? `${WD[d.getDay()]} ${d.getDate()} ${MO[d.getMonth()]}` : ''; };
	const tint = (hex, a) => {
		const h = String(hex || '').replace('#', '');
		if (!/^[0-9a-f]{6}$/i.test(h)) return `rgba(113,113,122,${a})`;
		return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`;
	};

	class SalesOperationBoard {
		constructor(page, wrapper) {
			this.page = page;
			this.wrapper = wrapper;
			this.data = null;
			this.busy = {};
			this.drag = null;
			this.state = {
				view: 'board', owners: null, prod: '', priority: '', q: '', attn: false, closed: false,
				cal_mode: 'month', cal_date: null, cal_type: 'all', sort: { key: '', dir: 1 }, sel: null, tab: 'overview',
			};
			this.cols = this.read_cols();

			page.set_primary_action(__('New Deal'), () => this.new_deal(), 'add');
			page.add_button(__('Export'), () => this.export_xlsx());
			page.add_menu_item(__('Deal List'), () => frappe.set_route('List', DT));
			page.add_menu_item(__('Sales Pipeline Settings'), () => frappe.set_route('Form', 'Sales Pipeline Settings'));

			this.$root = $(`
				<div class="sob">
					<div class="sob-kpis"></div>
					<nav class="sob-tabs" role="tablist" aria-label="${__('Views')}">
						${VIEWS.map(v => `<button type="button" class="sob-tab" role="tab" data-view="${v[0]}">${__(v[1])}</button>`).join('')}
					</nav>
					<div class="sob-filters">
						<div class="sob-fgroup sob-owner-group"><span class="sob-flabel">${__('Owner')}</span><div class="sob-pills sob-owner-pills"></div></div>
						<div class="sob-fgroup">
							<label class="sob-flabel" for="sob-prod">${__('Product Line')}</label><select id="sob-prod" class="sob-select sob-prod"></select>
							<label class="sob-flabel" for="sob-prio">${__('Priority')}</label><select id="sob-prio" class="sob-select sob-prio"></select>
						</div>
						<div class="sob-fgroup sob-search"><input type="search" class="sob-q" autocomplete="off" aria-label="${__('Search')}" placeholder="${__('Search account, contact or notes')}"></div>
						<div class="sob-fgroup">
							<button type="button" class="sob-pill sob-toggle" data-toggle="attn"></button>
							<button type="button" class="sob-pill sob-toggle" data-toggle="closed"></button>
						</div>
					</div>
					<div class="sob-view"><div class="sob-loading">${__('Loading…')}</div></div>
				</div>`).appendTo(page.main);

			this.$drawer = $(`<div class="sob-drawer-wrap" hidden><div class="sob-drawer-backdrop" data-act="close"></div>
				<aside class="sob-drawer" role="dialog" aria-modal="false" aria-label="${__('Deal')}"></aside></div>`).appendTo(page.main);

			this.bind();
			frappe.realtime.on('sales_pipeline_update', msg => this.queue_reload(msg));
		}

		// ---------- state and URL ----------

		read_cols() {
			try {
				const c = JSON.parse(localStorage.getItem(LS_COLS) || 'null');
				if (Array.isArray(c) && c.length) return c.filter(k => LIST_COLS.some(x => x[0] === k));
			} catch (e) { /* storage off */ }
			return DEFAULT_COLS.slice();
		}

		read_url() {
			const p = new URLSearchParams(window.location.search);
			const ro = frappe.route_options || {};
			frappe.route_options = null;
			const s = this.state;
			if (p.get('view') && VIEWS.some(v => v[0] === p.get('view'))) s.view = p.get('view');
			if (p.has('owner')) s.owners = p.get('owner') ? p.get('owner').split(',') : [];
			if (p.has('prod')) s.prod = p.get('prod');
			if (p.has('priority')) s.priority = p.get('priority');
			if (p.has('q')) s.q = p.get('q');
			if (p.has('attn')) s.attn = p.get('attn') === '1';
			if (p.has('closed')) s.closed = p.get('closed') === '1';
			if (p.get('cal') === 'week' || p.get('cal') === 'month') s.cal_mode = p.get('cal');
			if (p.get('date') && pd(p.get('date'))) s.cal_date = p.get('date');
			if (p.get('show')) s.cal_type = p.get('show');
			const deal = ro.deal || p.get('deal');
			if (deal) { s.sel = deal; s.tab = 'overview'; }
		}

		write_url() {
			const s = this.state;
			const p = new URLSearchParams();
			p.set('view', s.view);
			if (s.owners !== null) p.set('owner', s.owners.join(','));
			if (s.prod) p.set('prod', s.prod);
			if (s.priority) p.set('priority', s.priority);
			if (s.q) p.set('q', s.q);
			if (s.attn) p.set('attn', '1');
			if (s.closed) p.set('closed', '1');
			if (s.view === 'calendar') {
				p.set('cal', s.cal_mode);
				if (s.cal_date) p.set('date', s.cal_date);
				if (s.cal_type !== 'all') p.set('show', s.cal_type);
			}
			if (s.sel) p.set('deal', s.sel);
			const url = window.location.pathname + '?' + p.toString();
			if (url !== window.location.pathname + window.location.search) window.history.replaceState(window.history.state, '', url);
		}

		set(patch) {
			Object.assign(this.state, patch);
			this.render();
		}

		on_show() {
			this.read_url();
			this.load();
		}

		queue_reload() {
			clearTimeout(this._reload_t);
			this._reload_t = setTimeout(() => { if (frappe.get_route_str() === ROUTE) this.load(); }, 400);
		}

		load() {
			return frappe.xcall(M + 'get_board').then(r => {
				this.data = r;
				this.s = r.settings;
				if (this.state.owners === null) this.state.owners = r.is_owner && !r.is_manager ? [r.user] : [];
				if (!this.state.cal_date) this.state.cal_date = r.today;
				if (!r.can_create) this.page.clear_primary_action();
				this.render();
				if (this.state.sel) this.load_activity(this.state.sel);
			}).catch(() => {
				this.$root.find('.sob-view').html(`<div class="sob-loading">${__('The board could not be loaded. Please refresh the page.')}</div>`);
			});
		}

		// ---------- lookups ----------

		stage(name) { return (this.s.stages || []).find(x => x.name === name) || null; }
		won_stage() { return (this.s.stages || []).find(x => x.is_closed && x.is_won); }
		lost_stage() { return (this.s.stages || []).find(x => x.is_closed && !x.is_won); }
		owner(user) { return (this.s.all_owners || []).find(o => o.user === user) || null; }
		owner_name(user) { const o = this.owner(user); return o ? o.name : (user || __('Unassigned')); }
		find(name) { return (this.data && this.data.deals || []).find(d => d.name === name); }
		prio_rank(p) { const i = (this.s.lists.priority || []).indexOf(p); return i < 0 ? 99 : i; }
		is_top_priority(p) { return p && (this.s.lists.priority || [])[0] === p; }

		filtered(opts) {
			opts = opts || {};
			const s = this.state;
			const q = (s.q || '').trim().toLowerCase();
			const owners = s.owners || [];
			return (this.data ? this.data.deals : []).filter(d =>
				(opts.keep_hidden || s.closed || !d.hidden_closed) &&
				(opts.any_owner || !owners.length || owners.includes(d.deal_owner || NONE)) &&
				(!s.prod || d.product_line === s.prod) &&
				(!s.priority || d.priority === s.priority) &&
				(!q || [d.name, d.account, d.contact_name, d.customer, d.email, d.phone, d.timeline, d.status_detail,
					d.buyer_notes, d.deal_notes, d.next_steps, d.fulfillment_notes, d.ops_notes, d.strain_profiles]
					.join(' ').toLowerCase().indexOf(q) >= 0) &&
				(!s.attn || d.attention));
		}

		sorted_cards(list) {
			return list.slice().sort((a, b) =>
				(this.prio_rank(a.priority) - this.prio_rank(b.priority)) ||
				((a.next_step_due || '9999') < (b.next_step_due || '9999') ? -1 : (a.next_step_due || '9999') > (b.next_step_due || '9999') ? 1 : 0) ||
				(a.creation < b.creation ? -1 : 1));
		}

		// ---------- render ----------

		render() {
			if (!this.data) return;
			const s = this.state;
			this.$root.find('.sob-tab').each((_, el) => {
				const on = $(el).attr('data-view') === s.view;
				$(el).toggleClass('on', on).attr('aria-selected', on);
			});
			this.render_filters();
			this.render_kpis(this.filtered({ keep_hidden: true }));
			const list = this.filtered();
			const $v = this.$root.find('.sob-view');
			if (s.view === 'owner') this.render_owner($v, list);
			else if (s.view === 'calendar') this.render_calendar($v, list);
			else if (s.view === 'list') this.render_list($v, list);
			else this.render_board($v, list);
			this.render_drawer();
			this.write_url();
		}

		render_kpis(list) {
			const open = list.filter(d => !d.is_closed);
			const sum = (arr, f) => arr.reduce((a, d) => a + (+f(d) || 0), 0);
			const grams = sum(open, d => d.total_grams);
			const won = list.filter(d => d.won_this_month);
			const attn = open.filter(d => d.attention);
			const count = k => open.filter(d => (d.flags || []).some(f => f.key === k)).length;
			const today = pd(this.data.today);
			const kpis = [
				[__('Open deals'), String(open.length), __('Excluding closed deals')],
				[__('Open value'), usd(sum(open, d => d.deal_value)), __('Grams × price per gram, or override')],
				[__('Weighted value'), usd(sum(open, d => d.weighted_value)), __('Value × stage probability')],
				[__('Grams in pipeline'), n0(grams) + ' g', (grams / 1000).toFixed(1) + ' kg ' + __('in open deals')],
				[__('Won value'), usd(sum(won, d => d.deal_value)), won.length + ' ' + __('won in') + ' ' + MONTHS[today.getMonth()]],
				[__('Needs attention'), String(attn.length), `${count('overdue')} ${__('overdue')} · ${count('stalled')} ${__('stalled')} · ${count('no_owner')} ${__('no owner')} · ${count('short')} ${__('short')}`],
			];
			this.$root.find('.sob-kpis').html(kpis.map((k, i) => `
				<div class="sob-kpi${i === 5 && attn.length ? ' warn' : ''}">
					<div class="sob-kpi-label">${esc(k[0])}</div>
					<div class="sob-kpi-value">${esc(k[1])}</div>
					<div class="sob-kpi-sub">${esc(k[2])}</div>
				</div>`).join(''));
		}

		render_filters() {
			const s = this.state;
			const owners = s.owners || [];
			const pill = (val, label, on, colour) => `<button type="button" class="sob-pill${on ? ' on' : ''}" data-owner="${esc(val)}" aria-pressed="${on}">${colour ? `<span class="sob-dot" style="background:${esc(colour)}"></span>` : ''}${esc(label)}</button>`;
			this.$root.find('.sob-owner-pills').html(
				pill('', __('All'), !owners.length) +
				(this.s.owners || []).map(o => pill(o.user, o.name, owners.includes(o.user), o.colour)).join('') +
				pill(NONE, __('Unassigned'), owners.includes(NONE)));
			const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(label)}</option>`;
			this.$root.find('.sob-prod').html(opt('', __('All'), s.prod) + (this.s.product_lines || []).map(p => opt(p, p, s.prod)).join(''));
			this.$root.find('.sob-prio').html(opt('', __('All'), s.priority) + (this.s.lists.priority || []).map(p => opt(p, p, s.priority)).join(''));
			const $q = this.$root.find('.sob-q');
			if ($q.val() !== s.q && document.activeElement !== $q.get(0)) $q.val(s.q);
			this.$root.find('[data-toggle="attn"]').toggleClass('on', s.attn).attr('aria-pressed', s.attn).text(__('Needs attention only'));
			this.$root.find('[data-toggle="closed"]').toggleClass('on', s.closed).attr('aria-pressed', s.closed)
				.text(__('Show closed'))
				.attr('title', __('Closed deals hide {0} days after closing', [this.s.hide_closed_after_days || 0]));
		}

		badges(d) {
			const b = [];
			const neutral = (t, bg, fg) => `<span class="sob-badge" style="background:${bg};color:${fg}">${esc(t)}</span>`;
			if (d.status_detail) b.push(neutral(d.status_detail, '#F4F4F5', '#3F3F46'));
			if (d.samples) b.push(neutral(__('Samples') + ': ' + d.samples, '#FEF3C7', '#78350F'));
			if (d.copack === 'YES') b.push(neutral(__('Copack'), '#E0E7FF', '#312E81'));
			if (d.hardware) b.push(neutral(__('Hardware') + ': ' + d.hardware, '#E0E7FF', '#312E81'));
			(d.flags || []).forEach(f => b.push(`<span class="sob-badge ${f.kind === 'action' ? 'act' : 'info'}">${esc(f.label)}</span>`));
			return b.join('');
		}

		next_date_line(d) {
			const today = this.data.today;
			if (d.next_step_due) return `${__('Follow-up')} ${nice(d.next_step_due)}`;
			const up = EVENTS.filter(e => e.key !== 'followup' && d[e.field] && d[e.field] >= today)
				.sort((a, b) => (d[a.field] < d[b.field] ? -1 : 1))[0];
			return up ? `${__(up.label)} ${nice(d[up.field])}` : '';
		}

		avatar(d) {
			if (!d.deal_owner) return `<span class="sob-av none" title="${__('Unassigned')}">?</span>`;
			const o = this.owner(d.deal_owner);
			const name = o ? o.name : d.deal_owner;
			return `<span class="sob-av" style="background:${esc((o && o.colour) || '#18181B')}" title="${esc(name)}">${esc((name[0] || '?').toUpperCase())}</span>`;
		}

		stage_chip(stage) {
			const st = this.stage(stage) || {};
			const c = st.colour || '#71717A';
			return `<span class="sob-stage-chip" style="background:${tint(c, .14)};color:${esc(c)};border-color:${tint(c, .35)}">${esc(__(stage))}</span>`;
		}

		card(d, opts) {
			opts = opts || {};
			const grams = d.total_grams ? n0(d.total_grams) + ' g' + (d.price_per_gram ? ' @ ' + money2(d.price_per_gram) + '/g' : '') : '';
			const prod = [d.product_line, d.tier].filter(Boolean).join(' · ');
			const line = this.next_date_line(d);
			const st = this.stage(d.stage) || {};
			return `
				<div class="sob-card${this.state.sel === d.name ? ' sel' : ''}${this.busy[d.name] ? ' busy' : ''}" role="button" tabindex="0"
					draggable="${this.data.can_write ? 'true' : 'false'}" data-card="${esc(d.name)}" aria-label="${esc(d.account)}"
					style="--sob-stage:${esc(st.colour || '#A1A1AA')}">
					<div class="sob-card-top">
						<span class="sob-card-acc">${this.is_top_priority(d.priority) ? `<span class="sob-prio-dot" title="${esc(__('Priority') + ': ' + d.priority)}"></span>` : ''}${esc(d.account)}</span>
						${this.avatar(d)}
					</div>
					${opts.stage_chip ? this.stage_chip(d.stage) : ''}
					${prod ? `<span class="sob-badge sob-prod">${esc(prod)}</span>` : ''}
					<div class="sob-card-nums"><b>${d.deal_value ? usd(d.deal_value) : '—'}</b><span>${esc(grams)}</span></div>
					${d.timeline ? `<div class="sob-card-when">${esc(d.timeline)}</div>` : ''}
					${line ? `<div class="sob-card-next">${esc(line)}</div>` : ''}
					<div class="sob-badges">${this.badges(d)}</div>
				</div>`;
		}

		col_sub(items) {
			const v = items.reduce((a, d) => a + (+d.deal_value || 0), 0);
			const w = items.reduce((a, d) => a + (+d.weighted_value || 0), 0);
			return `${items.length} ${items.length === 1 ? __('deal') : __('deals')} · ${usd(v)} · ${usd(w)}`;
		}

		keep_scroll($v, html, sel) {
			const left = $v.find(sel).scrollLeft() || 0;
			$v.html(html);
			$v.find(sel).scrollLeft(left);
		}

		render_board($v, list) {
			const html = (this.s.stages || []).map(st => {
				const items = this.sorted_cards(list.filter(d => d.stage === st.name));
				return `
					<section class="sob-col" data-drop-stage="${esc(st.name)}" aria-label="${esc(st.name)}" style="--sob-stage:${esc(st.colour || '#A1A1AA')}">
						<header class="sob-col-head">
							<div class="sob-col-title"><span>${esc(__(st.name))}</span><span class="sob-col-prob">${+st.probability}%</span></div>
							<div class="sob-col-sub">${esc(this.col_sub(items))}</div>
						</header>
						${items.map(d => this.card(d)).join('')}
						${items.length ? '' : `<div class="sob-col-empty">${this.data.can_write ? __('Drop a deal here') : __('No deals')}</div>`}
					</section>`;
			}).join('');
			this.keep_scroll($v, `<div class="sob-hint">${__('Drag a card to another stage, or click it to open the deal.')}</div><div class="sob-scroll"><div class="sob-columns">${html}</div></div>`, '.sob-scroll');
		}

		render_owner($v, list) {
			const s = this.state;
			const picked = s.owners || [];
			const cols = (this.s.owners || []).filter(o => !picked.length || picked.includes(o.user)).map(o => ({ id: o.user, name: o.name, colour: o.colour }));
			if (!picked.length || picked.includes(NONE)) cols.push({ id: NONE, name: __('Unassigned'), colour: '' });
			const today = this.data.today;
			const order = st => { const i = (this.s.stages || []).findIndex(x => x.name === st); return i < 0 ? 99 : i; };
			const html = cols.map(c => {
				const items = list.filter(d => (d.deal_owner || NONE) === c.id)
					.sort((a, b) => order(a.stage) - order(b.stage) || this.prio_rank(a.priority) - this.prio_rank(b.priority));
				const overdue = items.filter(d => !d.is_closed && d.next_step_due && d.next_step_due < today).length;
				const unassigned = c.id === NONE;
				return `
					<section class="sob-col sob-owner-col${unassigned && items.length ? ' warn' : ''}" ${unassigned ? '' : `data-drop-owner="${esc(c.id)}"`} aria-label="${esc(c.name)}">
						<header class="sob-col-head">
							<div class="sob-col-title"><span>${c.colour ? `<span class="sob-dot" style="background:${esc(c.colour)}"></span>` : ''}${esc(c.name)}</span>
								${overdue ? `<span class="sob-badge act">${overdue} ${__('overdue')}</span>` : ''}</div>
							<div class="sob-col-sub">${esc(this.col_sub(items))}</div>
							${unassigned && items.length ? `<div class="sob-col-note">${__('Drag these deals to an owner.')}</div>` : ''}
						</header>
						${items.map(d => this.card(d, { stage_chip: true })).join('')}
						${items.length ? '' : `<div class="sob-col-empty">${unassigned ? __('Every deal has an owner') : __('Drop a deal here to reassign')}</div>`}
					</section>`;
			}).join('');
			this.keep_scroll($v, `<div class="sob-hint">${__('Drag a card to another owner to reassign it. The new owner is notified.')}</div><div class="sob-scroll"><div class="sob-columns">${html}</div></div>`, '.sob-scroll');
		}

		// ---------- calendar ----------

		cal_events(list) {
			const s = this.state;
			const today = this.data.today;
			const types = EVENTS.filter(e => s.cal_type === 'all' || s.cal_type === e.key);
			const out = [];
			list.forEach(d => types.forEach(e => {
				const v = d[e.field];
				if (!v) return;
				const overdue = e.key === 'followup' && !d.is_closed && v < today;
				out.push({ d, e, date: overdue ? today : v, real: v, overdue });
			}));
			return out;
		}

		event_chip(ev) {
			const o = ev.d.deal_owner ? this.owner_name(ev.d.deal_owner) : '?';
			return `<div class="sob-ev${ev.overdue ? ' overdue' : ''}" draggable="${this.data.can_write ? 'true' : 'false'}" role="button" tabindex="0"
				data-event="${esc(ev.d.name)}" data-field="${ev.e.field}" style="background:${ev.overdue ? '#FFEDD5' : ev.e.bg};color:${ev.overdue ? '#9A3412' : ev.e.color}"
				title="${esc(ev.d.account + ' · ' + __(ev.e.label) + ' · ' + fdate(ev.real))}">
				${svg(ev.e.icon, 12)}<span>${esc(ev.d.account)} · ${esc(__(ev.e.label))} · ${esc((o[0] || '?').toUpperCase())}</span></div>`;
		}

		render_calendar($v, list) {
			const s = this.state;
			const anchor = pd(s.cal_date || this.data.today);
			const today = this.data.today;
			let start, days, title;
			if (s.cal_mode === 'week') {
				start = addDays(anchor, -anchor.getDay());
				days = 7;
				const end = addDays(start, 6);
				title = `${MO[start.getMonth()]} ${start.getDate()} – ${MO[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`;
			} else {
				const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
				start = addDays(first, -first.getDay());
				const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
				days = Math.ceil((last.getDate() + first.getDay()) / 7) * 7;
				title = `${MONTHS[anchor.getMonth()]} ${anchor.getFullYear()}`;
			}
			const events = this.cal_events(list);
			const by = {};
			events.forEach(ev => { (by[ev.date] = by[ev.date] || []).push(ev); });
			const cells = [];
			for (let i = 0; i < days; i++) {
				const d = addDays(start, i);
				const k = key(d);
				const evs = (by[k] || []).sort((a, b) => EVENTS.indexOf(a.e) - EVENTS.indexOf(b.e));
				const over = evs.filter(x => x.overdue);
				const rest = evs.filter(x => !x.overdue);
				const out_month = s.cal_mode === 'month' && d.getMonth() !== anchor.getMonth();
				cells.push(`
					<div class="sob-cell${k === today ? ' today' : ''}${out_month ? ' out' : ''}" data-drop-date="${k}">
						<div class="sob-cell-day">${s.cal_mode === 'week' ? WD[d.getDay()] + ' ' : ''}${d.getDate()}</div>
						${over.length ? `<div class="sob-overdue-group"><div class="sob-overdue-cap">${__('Overdue')} (${over.length})</div>${over.map(ev => this.event_chip(ev)).join('')}</div>` : ''}
						${rest.map(ev => this.event_chip(ev)).join('')}
					</div>`);
			}
			const week_end = key(addDays(pd(today), 6));
			const agenda = events.filter(ev => ev.overdue || (ev.date >= today && ev.date <= week_end))
				.sort((a, b) => (a.overdue === b.overdue ? 0 : a.overdue ? -1 : 1) || (a.real < b.real ? -1 : a.real > b.real ? 1 : 0));
			const show_opts = [['all', __('All')]].concat(EVENTS.map(e => [e.key, __(e.label)]));
			$v.html(`
				<div class="sob-cal-bar">
					<div class="sob-cal-nav">
						<button type="button" class="sob-btn sm" data-cal="prev" aria-label="${__('Previous')}">‹</button>
						<button type="button" class="sob-btn sm" data-cal="today">${__('Today')}</button>
						<button type="button" class="sob-btn sm" data-cal="next" aria-label="${__('Next')}">›</button>
						<h3 class="sob-cal-title">${esc(title)}</h3>
					</div>
					<div class="sob-cal-nav">
						<div class="sob-seg" role="group" aria-label="${__('Calendar range')}">
							<button type="button" class="${s.cal_mode === 'month' ? 'on' : ''}" data-cal-mode="month">${__('Month')}</button>
							<button type="button" class="${s.cal_mode === 'week' ? 'on' : ''}" data-cal-mode="week">${__('Week')}</button>
						</div>
						<label class="sob-flabel" for="sob-cal-show">${__('Show')}</label>
						<select id="sob-cal-show" class="sob-select sob-cal-show">${show_opts.map(o => `<option value="${o[0]}"${s.cal_type === o[0] ? ' selected' : ''}>${esc(o[1])}</option>`).join('')}</select>
					</div>
				</div>
				<div class="sob-legend">${EVENTS.map(e => `<span style="color:${e.color}">${svg(e.icon, 12)} ${esc(__(e.label))}</span>`).join('')}<span class="sob-legend-over">${__('Overdue follow-ups are listed on today')}</span></div>
				<div class="sob-scroll"><div class="sob-cal ${s.cal_mode}">
					${WD.map(w => `<div class="sob-cal-head">${w}</div>`).join('')}
					${cells.join('')}
				</div></div>
				<section class="sob-agenda">
					<h3>${__('This week')}</h3>
					${agenda.length ? agenda.map(ev => `
						<div class="sob-agenda-row" role="button" tabindex="0" data-open="${esc(ev.d.name)}">
							<span class="sob-agenda-date${ev.overdue ? ' over' : ''}">${ev.overdue ? __('Overdue') + ' · ' : ''}${esc(nice(ev.real))}</span>
							<span class="sob-agenda-type" style="color:${ev.e.color}">${svg(ev.e.icon, 12)} ${esc(__(ev.e.label))}</span>
							<span class="sob-agenda-acc">${esc(ev.d.account)}</span>
							<span class="sob-agenda-meta">${esc(ev.d.deal_owner ? this.owner_name(ev.d.deal_owner) : __('Unassigned'))} · ${esc(__(ev.d.stage))}</span>
						</div>`).join('') : `<div class="sob-empty">${__('Nothing scheduled in the next 7 days.')}</div>`}
				</section>`);
		}

		// ---------- list ----------

		cell_value(d, c) {
			const v = d[c[0]];
			switch (c[2]) {
				case 'num': return v ? n0(v) : '';
				case 'money': return v ? usd(v) : '';
				case 'money2': return v ? money2(v) : '';
				case 'pct': return (+v || 0) + '%';
				case 'date': case 'date_edit': return v ? fdate(v) : '';
				case 'datetime': return v ? frappe.datetime.str_to_user(v) : '';
				default: return c[0] === 'deal_owner' ? (v ? this.owner_name(v) : __('Unassigned')) : (v == null ? '' : v);
			}
		}

		render_list($v, list) {
			const s = this.state;
			const cols = this.cols.map(k => LIST_COLS.find(c => c[0] === k)).filter(Boolean);
			const sk = s.sort.key;
			const rows = list.slice();
			if (sk) {
				const col = LIST_COLS.find(c => c[0] === sk) || [];
				const numeric = ['num', 'money', 'money2', 'pct'].includes(col[2]);
				const val = d => sk === 'deal_owner' ? (d[sk] ? this.owner_name(d[sk]) : '') : sk === 'stage' ? (this.s.stages || []).findIndex(x => x.name === d.stage) : sk === 'priority' ? this.prio_rank(d.priority) : d[sk];
				rows.sort((a, b) => {
					let x = val(a), y = val(b);
					if (numeric) return ((+x || 0) - (+y || 0)) * s.sort.dir;
					x = x == null || x === '' ? null : String(x).toLowerCase(); y = y == null || y === '' ? null : String(y).toLowerCase();
					if (sk === 'stage' || sk === 'priority') return ((+val(a)) - (+val(b))) * s.sort.dir;
					if (x === null) return 1; if (y === null) return -1;
					return (x < y ? -1 : x > y ? 1 : 0) * s.sort.dir;
				});
			}
			const can = this.data.can_write;
			const sel = (name, field, cur, opts) => `<select class="sob-inline" data-inline="${esc(name)}" data-field="${field}" aria-label="${esc(field)}">${opts.map(o => `<option value="${esc(o[0])}"${(cur || '') === o[0] ? ' selected' : ''}>${esc(o[1])}</option>`).join('')}</select>`;
			const owner_opts = d => [['', __('Unassigned')]].concat(this.owner_choices(d).map(o => [o.user, o.name]));
			const cell = (d, c) => {
				if (can && c[2] === 'stage') return sel(d.name, 'stage', d.stage, (this.s.stages || []).map(x => [x.name, __(x.name)]));
				if (can && c[2] === 'owner') return sel(d.name, 'deal_owner', d.deal_owner, owner_opts(d));
				if (can && c[2] === 'priority') return sel(d.name, 'priority', d.priority, (this.s.lists.priority || []).map(x => [x, x]));
				if (can && c[2] === 'date_edit') return `<input type="date" class="sob-inline" data-inline="${esc(d.name)}" data-field="${c[0]}" value="${esc(d[c[0]] || '')}" aria-label="${esc(c[1])}">`;
				if (c[0] === 'account') return `<b>${esc(d.account)}</b>${(d.flags || []).some(f => f.kind === 'action') ? ' <span class="sob-flag-dot" title="' + esc(d.flags.map(f => f.label).join(', ')) + '"></span>' : ''}`;
				return esc(this.cell_value(d, c));
			};
			const total = k => rows.reduce((a, d) => a + (+d[k] || 0), 0);
			const totals = cols.map((c, i) => {
				if (c[0] === 'total_grams') return n0(total('total_grams')) + ' g';
				if (c[0] === 'deal_value') return usd(total('deal_value'));
				if (c[0] === 'weighted_value') return usd(total('weighted_value'));
				return i === 0 ? __('Total') + ` (${rows.length})` : '';
			});
			const left = $v.find('.sob-table-wrap').scrollLeft() || 0;
			$v.html(`
				<div class="sob-list-bar">
					<span class="sob-muted">${rows.length} ${rows.length === 1 ? __('deal') : __('deals')}</span>
					<div class="sob-colpick">
						<button type="button" class="sob-btn sm" data-act="cols" aria-expanded="false">${__('Columns')}</button>
						<div class="sob-colpick-menu" hidden>
							${LIST_COLS.map(c => `<label><input type="checkbox" data-col="${c[0]}"${this.cols.includes(c[0]) ? ' checked' : ''}> ${esc(__(c[1]))}</label>`).join('')}
							<button type="button" class="sob-btn sm" data-act="cols-reset">${__('Reset to default')}</button>
						</div>
					</div>
				</div>
				<div class="sob-table-wrap"><table class="sob-table">
					<thead><tr>${cols.map(c => `<th><button type="button" data-sort="${c[0]}" class="${sk === c[0] ? 'on' : ''}">${esc(__(c[1]))}${sk === c[0] ? (s.sort.dir > 0 ? ' ▲' : ' ▼') : ''}</button></th>`).join('')}</tr></thead>
					<tbody>${rows.map(d => `<tr data-open="${esc(d.name)}" class="${s.sel === d.name ? 'sel' : ''}">${cols.map(c => `<td class="${['num', 'money', 'money2', 'pct'].includes(c[2]) ? 'r' : ''}">${cell(d, c)}</td>`).join('')}</tr>`).join('') ||
						`<tr><td colspan="${cols.length}" class="sob-empty">${__('No deals match the current filters.')}</td></tr>`}</tbody>
					<tfoot><tr>${totals.map((t, i) => `<td class="${['num', 'money', 'money2', 'pct'].includes(cols[i][2]) ? 'r' : ''}">${esc(t)}</td>`).join('')}</tr></tfoot>
				</table></div>`);
			$v.find('.sob-table-wrap').scrollLeft(left);
		}

		owner_choices(d) {
			const all = this.s.owners || [];
			if (this.data.is_manager) return all;
			return all.filter(o => o.user === this.data.user || (d && o.user === d.deal_owner));
		}

		// ---------- drawer ----------

		render_drawer() {
			const d = this.state.sel ? this.find(this.state.sel) : null;
			if (!d) { this.close_drawer(true); return; }
			const nav = document.querySelector('header.navbar, .navbar');
			const top = nav ? Math.max(0, nav.getBoundingClientRect().bottom) : 0;
			this.$drawer.prop('hidden', false).find('.sob-drawer').css('top', top + 'px');
			this.$drawer.find('.sob-drawer-backdrop').css('top', top + 'px');
			const tab = this.state.tab;
			const can = this.data.can_write;
			const st = this.stage(d.stage) || {};
			const tabs = [['overview', 'Overview'], ['buyer', 'Buyer'], ['requirements', 'Requirements'], ['notes', 'Notes'], ['activity', 'Activity']];
			const field = (label, value, html) => (value || html) ? `<div class="sob-f"><span>${esc(label)}</span><span>${html || esc(value)}</span></div>` : '';
			let body = '';
			if (tab === 'overview') {
				const stock = d.stock ? `${n0(d.stock.grams)} g ${__('available')} (${esc(d.stock.groups.join(', '))})${d.stock.on_orders ? ` · ${n0(d.stock.on_orders)} g ${__('on open Sales Orders')}` : ''}` : '';
				const dates = EVENTS.map(e => `
					<label class="sob-date"><span style="color:${e.color}">${svg(e.icon, 12)} ${esc(__(e.label))}</span>
						<input type="date" data-panel-field="${e.field}" value="${esc(d[e.field] || '')}"${can ? '' : ' disabled'}></label>`).join('');
				body = `
					${(d.flags || []).length ? `<div class="sob-badges">${(d.flags || []).map(f => `<span class="sob-badge ${f.kind === 'action' ? 'act' : 'info'}">${esc(f.label)}</span>`).join('')}</div>` : ''}
					${can ? `<div class="sob-block"><div class="sob-cap">${__('Stage')}</div><div class="sob-moves">${(this.s.stages || []).map(x => `<button type="button" class="sob-move${x.name === d.stage ? ' on' : ''}" data-move="${esc(x.name)}" aria-pressed="${x.name === d.stage}" style="--sob-stage:${esc(x.colour || '#2563EB')}">${esc(__(x.name))}</button>`).join('')}</div></div>` : ''}
					<div class="sob-tiles">
						<div><span>${__('Deal value')}</span><b>${d.deal_value ? usd(d.deal_value) : '—'}</b></div>
						<div><span>${__('Weighted')}</span><b>${d.weighted_value ? usd(d.weighted_value) : '—'}</b></div>
						<div><span>${__('Grams')}</span><b>${d.total_grams ? n0(d.total_grams) : '—'}</b></div>
						<div><span>${__('Price per gram')}</span><b>${d.price_per_gram ? money2(d.price_per_gram) : '—'}</b></div>
					</div>
					<div class="sob-two">
						<label class="sob-cap">${__('Owner')}
							<select data-panel-field="deal_owner"${can ? '' : ' disabled'}>${[['', __('Unassigned')]].concat(this.owner_choices(d).map(o => [o.user, o.name])).map(o => `<option value="${esc(o[0])}"${(d.deal_owner || '') === o[0] ? ' selected' : ''}>${esc(o[1])}</option>`).join('')}</select></label>
						<label class="sob-cap">${__('Priority')}
							<select data-panel-field="priority"${can ? '' : ' disabled'}>${(this.s.lists.priority || []).map(p => `<option${p === d.priority ? ' selected' : ''}>${esc(p)}</option>`).join('')}</select></label>
					</div>
					<div class="sob-dates">${dates}</div>
					<div class="sob-fields">
						${field(__('Stock available'), stock)}
						${field(__('In stage'), d.days_in_stage + ' ' + __('days') + (st.max_days ? ' ' + __('(limit {0})', [st.max_days]) : ''))}
						${field(__('Timeline'), d.timeline)}
						${field(__('Status detail'), d.status_detail)}
						${field(__('Lost reason'), d.lost_reason)}
					</div>`;
			} else if (tab === 'buyer') {
				body = `<div class="sob-fields">
					${field(__('Contact'), d.contact_name)}
					${field(__('Phone'), d.phone, d.phone ? `<a href="tel:${esc(String(d.phone).replace(/[^0-9+]/g, ''))}">${esc(d.phone)}</a>` : '')}
					${field(__('Email'), d.email, d.email ? `<a href="mailto:${esc(d.email)}">${esc(d.email)}</a>` : '')}
					${field(__('Location'), d.location_address)}
					${field(__('License #'), d.license_number)}
					${field(__('Customer'), d.customer, d.customer ? `<a href="/app/customer/${encodeURIComponent(d.customer)}">${esc(d.customer)}</a>` : '')}
					${field(__('Lead'), d.lead, d.lead ? `<a href="/app/lead/${encodeURIComponent(d.lead)}">${esc(d.lead)}</a>` : '')}
				</div>${!d.contact_name && !d.phone && !d.email ? `<div class="sob-empty">${__('No buyer contact yet. Use Open full form to add it.')}</div>` : ''}`;
			} else if (tab === 'requirements') {
				body = `<div class="sob-fields">
					${field(__('Product line'), d.product_line)}${field(__('Tier'), d.tier)}${field(__('Form'), d.form)}
					${field(__('Size per strain'), d.size_per_strain)}${field(__('Strain profiles'), d.strain_profiles)}
					${field(__('Samples'), d.samples)}${field(__('Copack'), d.copack)}${field(__('Hardware'), d.hardware)}
				</div>`;
			} else if (tab === 'notes') {
				body = `<div class="sob-fields">
					${field(__('Buyer notes'), d.buyer_notes)}${field(__('Deal notes'), d.deal_notes)}${field(__('Next steps to close'), d.next_steps)}
					${field(__('Fulfillment notes'), d.fulfillment_notes)}${field(__('Ops notes'), d.ops_notes)}
					${field(__('Payment terms'), d.payment_terms)}${field(__('Lead source'), d.lead_source)}
				</div>`;
			} else {
				const items = this.activity && this.activity.name === d.name ? this.activity.items : null;
				body = `
					<div class="sob-note-box">
						<textarea class="sob-note" rows="3" placeholder="${__('Add a note…')}" aria-label="${__('Add a note')}"></textarea>
						<button type="button" class="sob-btn primary sm" data-act="note">${__('Add note')}</button>
					</div>
					<div class="sob-activity">${items === null ? `<div class="sob-muted">${__('Loading…')}</div>` : items.length ? items.map(a => this.activity_row(a)).join('') : `<div class="sob-empty">${__('No activity yet.')}</div>`}</div>`;
			}
			const won = this.won_stage(), lost = this.lost_stage();
			const $prev = this.$drawer.find('.sob-note');
			const draft = $prev.length && this._drawer_deal === d.name ? $prev.val() : '';
			this._drawer_deal = d.name;
			this.$drawer.find('.sob-drawer').html(`
				<header class="sob-d-head">
					<div class="sob-d-row">${this.stage_chip(d.stage)}<span class="sob-muted">${+st.probability || 0}% · ${esc(d.name)}</span>
						<button type="button" class="sob-x" data-act="close" aria-label="${__('Close')}">×</button></div>
					<h2>${esc(d.account)}</h2>
					<div class="sob-muted">${esc([d.product_line, d.tier].filter(Boolean).join(' · ') || __('Product not set yet'))} · ${esc(d.deal_owner ? this.owner_name(d.deal_owner) : __('Unassigned'))}</div>
					<nav class="sob-d-tabs" role="tablist">${tabs.map(t => `<button type="button" role="tab" class="${t[0] === tab ? 'on' : ''}" aria-selected="${t[0] === tab}" data-tab="${t[0]}">${esc(__(t[1]))}</button>`).join('')}</nav>
				</header>
				<div class="sob-d-body">${body}</div>
				<footer class="sob-d-foot">
					<button type="button" class="sob-btn" data-act="form">${__('Open full form')}</button>
					${this.data.can_quote ? `<button type="button" class="sob-btn" data-act="quote">${__('Create Quotation')}</button>` : ''}
					${can && won && d.stage !== won.name ? `<button type="button" class="sob-btn won" data-act="won">${__('Mark Won')}</button>` : ''}
					${can && lost && d.stage !== lost.name ? `<button type="button" class="sob-btn lost" data-act="lost">${__('Mark Lost')}</button>` : ''}
				</footer>`);
			if (draft) this.$drawer.find('.sob-note').val(draft);
		}

		activity_row(a) {
			const when = a.on ? frappe.datetime.comment_when(a.on) : '';
			if (a.kind === 'stage') {
				return `<div class="sob-act stage"><div>${a.from_stage ? `${esc(__(a.from_stage))} → ` : `${__('Created in')} `}<b>${esc(__(a.to_stage))}</b>${a.from_stage ? ` <span class="sob-muted">(${a.days} ${__('days in previous stage')})</span>` : ''}</div><div class="sob-muted">${esc(a.by)} · ${when}</div></div>`;
			}
			return `<div class="sob-act ${a.kind}"><div class="sob-act-body">${frappe.utils.xss_sanitise ? frappe.utils.xss_sanitise(a.content || '') : esc(a.content)}</div><div class="sob-muted">${esc(a.by)} · ${when}</div></div>`;
		}

		load_activity(name) {
			return frappe.xcall(M + 'get_activity', { name }).then(items => {
				this.activity = { name, items };
				if (this.state.sel === name && this.state.tab === 'activity') this.render_drawer();
			}).catch(() => { this.activity = { name, items: [] }; });
		}

		open(name) {
			this.activity = null;
			this.set({ sel: name, tab: this.state.sel === name ? this.state.tab : 'overview' });
			this.load_activity(name);
		}

		close_drawer(silent) {
			this.$drawer.prop('hidden', true);
			if (!silent && this.state.sel) this.set({ sel: null });
		}

		// ---------- actions ----------

		missing(d, patch) {
			const next = Object.assign({}, d, patch);
			const st = this.stage(next.stage) || {};
			const need = [];
			if (!next.deal_owner) need.push('deal_owner');
			if (st.name && !st.is_closed && st.name !== this.s.first_stage && !next.next_step_due) need.push('next_step_due');
			if (st.is_closed && !st.is_won && !(next.lost_reason || '').trim()) need.push('lost_reason');
			if (st.is_closed && st.is_won && !next.customer) need.push('customer');
			return need;
		}

		apply(name, patch, done_msg) {
			const d = this.find(name);
			if (!d || this.busy[name]) return;
			const changed = Object.keys(patch).some(k => (patch[k] || '') !== (d[k] || ''));
			if (!changed) return;
			if ('deal_owner' in patch && !patch.deal_owner) {
				frappe.msgprint(__('Every deal needs an owner, so it cannot be moved back to Unassigned.'));
				this.render();
				return;
			}
			const need = this.missing(d, patch);
			if (!need.length) return this.send(name, patch, done_msg);
			const st = this.stage(patch.stage || d.stage) || {};
			const fields = [];
			if (need.includes('deal_owner')) {
				const choices = this.owner_choices(d);
				fields.push({ fieldname: 'deal_owner', fieldtype: 'Select', label: __('Owner'), reqd: 1,
					options: choices.map(o => ({ value: o.user, label: o.name })),
					default: choices.some(o => o.user === this.data.user) ? this.data.user : (choices[0] || {}).user });
			}
			if (need.includes('next_step_due')) fields.push({ fieldname: 'next_step_due', fieldtype: 'Date', label: __('Next Follow-up'), reqd: 1, default: frappe.datetime.add_days(this.data.today, 2) });
			if (need.includes('lost_reason')) fields.push({ fieldname: 'lost_reason', fieldtype: 'Small Text', label: __('Lost Reason'), reqd: 1 });
			if (need.includes('customer')) fields.push({ fieldname: 'customer', fieldtype: 'Link', options: 'Customer', label: __('Customer'), reqd: 1 });
			const dlg = new frappe.ui.Dialog({
				title: patch.stage ? __('Move {0} to {1}', [d.account, __(st.name)]) : __('Complete {0}', [d.account]),
				fields: [{ fieldtype: 'HTML', options: `<p class="text-muted">${__('This change needs a few more details.')}</p>` }].concat(fields),
				primary_action_label: __('Save'),
				primary_action: v => { dlg.hide(); this.send(name, Object.assign({}, patch, v), done_msg); },
			});
			dlg.show();
			this.render();
		}

		send(name, patch, done_msg) {
			const d = this.find(name);
			const prev = {};
			Object.keys(patch).forEach(k => { prev[k] = d[k]; d[k] = patch[k]; });
			this.busy[name] = true;
			this.render();
			return frappe.xcall(M + 'update_deal', { name, values: patch })
				.then(() => frappe.show_alert({ message: done_msg || __('{0} updated', [d.account]), indicator: 'green' }))
				.catch(() => Object.assign(d, prev))
				.finally(() => { delete this.busy[name]; this.load(); });
		}

		new_deal() {
			frappe.model.with_doctype(DT, () => {
				const doc = frappe.model.get_new_doc(DT);
				doc.stage = this.s.first_stage;
				doc.deal_owner = (this.s.owners || []).some(o => o.user === this.data.user) ? this.data.user : '';
				if (this.state.prod) doc.product_line = this.state.prod;
				frappe.ui.form.make_quick_entry(DT, saved => {
					this.load().then(() => { if (saved && saved.name) this.open(saved.name); });
				}, null, doc, true).then(qe => {
					const f = qe && qe.dialog && qe.dialog.fields_dict.deal_owner;
					if (f) f.get_query = () => ({ query: 'cannabis_management.sales_ops.active_owner_query' });
				});
			});
		}

		create_quotation(name) {
			const d = this.find(name);
			if (!d) return;
			const go = () => frappe.xcall(M + 'make_quotation', { name }).then(r => {
				if (r.message) frappe.show_alert({ message: r.message, indicator: 'orange' }, 8);
				frappe.model.sync(r.doc);
				frappe.set_route('Form', r.doc.doctype, r.doc.name);
			});
			if (d.customer) return go();
			const dlg = new frappe.ui.Dialog({
				title: __('Customer for {0}', [d.account]),
				fields: [
					{ fieldname: 'customer', fieldtype: 'Link', options: 'Customer', label: __('Customer'), reqd: 1 },
					{ fieldtype: 'HTML', options: `<p class="text-muted small">${__('The customer is saved on the deal, then the Quotation opens.')}</p>` },
				],
				primary_action_label: __('Create Quotation'),
				primary_action: v => frappe.xcall(M + 'update_deal', { name, values: { customer: v.customer } }).then(() => { dlg.hide(); d.customer = v.customer; go(); }),
			});
			dlg.show();
		}

		export_xlsx() {
			if (!this.data) return;
			const names = (this.state.view === 'list' ? this.list_order() : this.filtered()).map(d => d.name);
			if (!names.length) { frappe.msgprint(__('No deals match the current filters.')); return; }
			open_url_post('/api/method/' + M + 'export_xlsx', { names: JSON.stringify(names) });
		}

		list_order() {
			// export in the order shown in List view
			const order = [];
			this.$root.find('.sob-table tbody tr[data-open]').each((_, el) => order.push($(el).attr('data-open')));
			const all = this.filtered();
			return order.length ? order.map(n => all.find(d => d.name === n)).filter(Boolean) : all;
		}

		// ---------- events ----------

		bind() {
			const $r = this.$root, $d = this.$drawer;
			$r.on('click', '[data-view]', e => this.set({ view: $(e.currentTarget).attr('data-view') }));
			$r.on('click', '[data-owner]', e => {
				const v = $(e.currentTarget).attr('data-owner');
				let owners = (this.state.owners || []).slice();
				if (!v) owners = [];
				else owners = owners.includes(v) ? owners.filter(x => x !== v) : owners.concat([v]);
				this.set({ owners });
			});
			$r.on('change', '.sob-prod', e => this.set({ prod: e.target.value }));
			$r.on('change', '.sob-prio', e => this.set({ priority: e.target.value }));
			$r.on('input', '.sob-q', frappe.utils.debounce(e => this.set({ q: e.target.value }), 200));
			$r.on('click', '[data-toggle]', e => { const k = $(e.currentTarget).attr('data-toggle'); this.set({ [k]: !this.state[k] }); });

			// open a deal
			$r.on('click', '[data-card]', e => this.open($(e.currentTarget).attr('data-card')));
			$r.on('click', '[data-event]', e => this.open($(e.currentTarget).attr('data-event')));
			$r.on('click', 'tr[data-open], .sob-agenda-row', e => {
				if ($(e.target).closest('select, input, button, a').length) return;
				this.open($(e.currentTarget).attr('data-open'));
			});
			$r.on('keydown', '[data-card], [data-event], .sob-agenda-row', e => {
				if (e.key !== 'Enter' && e.key !== ' ') return;
				e.preventDefault();
				const el = e.currentTarget;
				this.open($(el).attr('data-card') || $(el).attr('data-event') || $(el).attr('data-open'));
			});

			// calendar
			$r.on('click', '[data-cal]', e => {
				const a = $(e.currentTarget).attr('data-cal');
				const cur = pd(this.state.cal_date || this.data.today);
				let next = pd(this.data.today);
				if (a !== 'today') {
					next = this.state.cal_mode === 'week' ? addDays(cur, a === 'next' ? 7 : -7) : new Date(cur.getFullYear(), cur.getMonth() + (a === 'next' ? 1 : -1), 1);
				}
				this.set({ cal_date: key(next) });
			});
			$r.on('click', '[data-cal-mode]', e => this.set({ cal_mode: $(e.currentTarget).attr('data-cal-mode') }));
			$r.on('change', '.sob-cal-show', e => this.set({ cal_type: e.target.value }));

			// list
			$r.on('click', '[data-sort]', e => {
				const k = $(e.currentTarget).attr('data-sort');
				const s = this.state.sort;
				this.set({ sort: { key: k, dir: s.key === k ? -s.dir : 1 } });
			});
			$r.on('change', '.sob-inline', e => {
				const el = e.currentTarget;
				this.apply($(el).attr('data-inline'), { [$(el).attr('data-field')]: el.value || null });
			});
			$r.on('click', '[data-act="cols"]', e => {
				const $m = $r.find('.sob-colpick-menu');
				const open = $m.prop('hidden');
				$m.prop('hidden', !open);
				$(e.currentTarget).attr('aria-expanded', open);
			});
			$r.on('change', '[data-col]', () => {
				const cols = [];
				$r.find('[data-col]:checked').each((_, el) => cols.push($(el).attr('data-col')));
				this.cols = LIST_COLS.map(c => c[0]).filter(k => cols.includes(k));
				if (!this.cols.length) this.cols = ['account'];
				try { localStorage.setItem(LS_COLS, JSON.stringify(this.cols)); } catch (x) { /* storage off */ }
				this.render();
				$r.find('.sob-colpick-menu').prop('hidden', false);
			});
			$r.on('click', '[data-act="cols-reset"]', () => {
				this.cols = DEFAULT_COLS.slice();
				try { localStorage.removeItem(LS_COLS); } catch (x) { /* storage off */ }
				this.render();
			});

			// drag and drop: cards (stage / owner) and calendar events (date)
			const dt = e => e.originalEvent && e.originalEvent.dataTransfer;
			$r.on('dragstart', '[data-card]', e => {
				this.drag = { name: $(e.currentTarget).attr('data-card'), kind: 'card' };
				$(e.currentTarget).addClass('dragging');
				try { dt(e).setData('text/plain', this.drag.name); dt(e).effectAllowed = 'move'; } catch (x) { /* old browsers */ }
			});
			$r.on('dragstart', '[data-event]', e => {
				this.drag = { name: $(e.currentTarget).attr('data-event'), kind: 'event', field: $(e.currentTarget).attr('data-field') };
				$(e.currentTarget).addClass('dragging');
				try { dt(e).setData('text/plain', this.drag.name); dt(e).effectAllowed = 'move'; } catch (x) { /* old browsers */ }
				e.stopPropagation();
			});
			$r.on('dragend', '[data-card], [data-event]', e => {
				$(e.currentTarget).removeClass('dragging');
				$r.find('.over').removeClass('over');
			});
			const target_ok = el => this.drag && ((this.drag.kind === 'card' && (el.hasAttribute('data-drop-stage') || el.hasAttribute('data-drop-owner'))) ||
				(this.drag.kind === 'event' && el.hasAttribute('data-drop-date')));
			$r.on('dragover', '[data-drop-stage], [data-drop-owner], [data-drop-date]', e => {
				if (!target_ok(e.currentTarget)) return;
				e.preventDefault();
				$r.find('.over').not(e.currentTarget).removeClass('over');
				$(e.currentTarget).addClass('over');
			});
			$r.on('dragleave', '[data-drop-stage], [data-drop-owner], [data-drop-date]', e => {
				if (!e.currentTarget.contains(e.relatedTarget)) $(e.currentTarget).removeClass('over');
			});
			$r.on('drop', '[data-drop-stage], [data-drop-owner], [data-drop-date]', e => {
				e.preventDefault();
				const el = e.currentTarget;
				$(el).removeClass('over');
				const ok = target_ok(el);
				const drag = this.drag;
				this.drag = null;
				if (!drag || !ok) return;
				if (drag.kind === 'card' && el.hasAttribute('data-drop-stage')) this.apply(drag.name, { stage: el.getAttribute('data-drop-stage') });
				else if (drag.kind === 'card' && el.hasAttribute('data-drop-owner')) {
					const owner = el.getAttribute('data-drop-owner');
					this.apply(drag.name, { deal_owner: owner }, __('Reassigned to {0}', [this.owner_name(owner)]));
				} else if (drag.kind === 'event' && el.hasAttribute('data-drop-date')) this.apply(drag.name, { [drag.field]: el.getAttribute('data-drop-date') });
			});

			// drawer
			$d.on('click', '[data-act="close"]', () => this.close_drawer());
			$d.on('click', '[data-tab]', e => {
				const tab = $(e.currentTarget).attr('data-tab');
				this.set({ tab });
				if (tab === 'activity' && this.state.sel) this.load_activity(this.state.sel);
			});
			$d.on('click', '[data-move]', e => this.apply(this.state.sel, { stage: $(e.currentTarget).attr('data-move') }));
			$d.on('change', '[data-panel-field]', e => this.apply(this.state.sel, { [$(e.currentTarget).attr('data-panel-field')]: e.currentTarget.value || null }));
			$d.on('click', '[data-act="form"]', () => frappe.set_route('Form', DT, this.state.sel));
			$d.on('click', '[data-act="quote"]', () => this.create_quotation(this.state.sel));
			$d.on('click', '[data-act="won"]', () => this.apply(this.state.sel, { stage: this.won_stage().name }, __('Marked as won')));
			$d.on('click', '[data-act="lost"]', () => this.apply(this.state.sel, { stage: this.lost_stage().name }, __('Marked as lost')));
			$d.on('click', '[data-act="note"]', () => {
				const name = this.state.sel;
				const note = ($d.find('.sob-note').val() || '').trim();
				if (!note) return;
				frappe.xcall(M + 'add_note', { name, note }).then(() => {
					frappe.show_alert({ message: __('Note added'), indicator: 'green' });
					$d.find('.sob-note').val('');
					this.load_activity(name);
				});
			});
			$(document).on('keydown.sob', e => {
				if (e.key === 'Escape' && this.state.sel && frappe.get_route_str() === ROUTE && !$('.modal.show').length) this.close_drawer();
			});
		}
	}

	frappe.pages[ROUTE].on_page_load = function (wrapper) {
		const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Sales Operation Board'), single_column: true });
		wrapper.sob_board = new SalesOperationBoard(page, wrapper);
	};

	frappe.pages[ROUTE].on_page_show = function (wrapper) {
		if (wrapper.sob_board) wrapper.sob_board.on_show();
	};

	frappe.pages[ROUTE].on_page_hide = function (wrapper) {
		if (wrapper.sob_board) wrapper.sob_board.$drawer.prop('hidden', true);
	};
})();
