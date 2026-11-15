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
		down: '<path d="m6 9 6 6 6-6"/>',
		up: '<path d="m18 15-6-6-6 6"/>',
		left: '<path d="m15 18-6-6 6-6"/>',
		right: '<path d="m9 18 6-6-6-6"/>',
		x: '<path d="M18 6 6 18M6 6l12 12"/>',
		plus: '<path d="M12 5v14M5 12h14"/>',
	};
	// One line-icon style everywhere: stroke 2, colour from the text it sits in.
	const svg = (p, size) => `<svg width="${size || 14}" height="${size || 14}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
	// Event colours live in the stylesheet (.ev-<key>) so they follow light and dark themes.
	const EVENTS = [
		{ key: 'followup', field: 'next_step_due', label: 'Follow-up', icon: ICON.phone },
		{ key: 'sample', field: 'sample_date', label: 'Sample', icon: ICON.flask },
		{ key: 'close', field: 'expected_close', label: 'Close', icon: ICON.flag },
		{ key: 'delivery', field: 'delivery_pickup', label: 'Delivery', icon: ICON.truck },
	];
	const LIST_COLS = [
		['stage', 'Stage', 'stage'], ['account', 'Account'], ['deal_owner', 'Owner', 'owner'], ['priority', 'Priority', 'priority'],
		['product_line', 'Product Line'], ['tier', 'Tier'], ['total_grams', 'Grams', 'num'], ['price_per_gram', 'Price/g', 'money2'],
		['deal_value', 'Deal Value', 'money'], ['weighted_value', 'Weighted', 'money'], ['next_step_due', 'Next Follow-up', 'date_edit'],
		['expected_close', 'Expected Close', 'date'], ['modified', 'Last Updated', 'datetime'],
		['co_owners', 'Co-owners', 'co'], ['contact_name', 'Contact'], ['phone', 'Phone'], ['email', 'Email'], ['customer', 'Customer'], ['lead', 'Lead'],
		['timeline', 'Timeline'], ['status_detail', 'Status Detail'], ['samples', 'Samples'], ['copack', 'Copack'],
		['hardware', 'Hardware'], ['sample_date', 'Sample Date', 'date'], ['delivery_pickup', 'Delivery / Pickup', 'date'],
		['days_in_stage', 'Days in Stage', 'num'], ['probability', 'Win %', 'pct'], ['value_override', 'Value Override', 'money'],
		['payment_terms', 'Payment Terms'], ['lead_source', 'Lead Source'], ['form', 'Form'], ['size_per_strain', 'Size per Strain'],
		['strain_profiles', 'Strain Profiles'], ['location_address', 'Location'], ['license_number', 'License #'],
	];
	const DEFAULT_COLS = LIST_COLS.slice(0, 13).map(c => c[0]);
	const NOTE_SECTIONS = [
		['buyer_notes', 'Buyer Notes / Requests'], ['deal_notes', 'Deal Notes'], ['next_steps', 'Next Steps to Close'],
		['fulfillment_notes', 'Fulfillment Notes'], ['ops_notes', 'Ops Notes'],
	];
	const NUM_FIELDS = ['total_grams', 'price_per_gram', 'value_override'];
	const BOARDS = [['lead', 'Leads'], ['deal', 'Deals']];
	const NOTE_ICON = '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>';
	const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
	const MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

	const esc = v => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
	const n0 = n => Math.round(+n || 0).toLocaleString('en-US');
	const usd = n => '$' + n0(n);
	const money2 = n => '$' + (Math.round((+n || 0) * 100) / 100).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	const fdate = s => (s ? frappe.datetime.str_to_user(String(s).slice(0, 10)) : '');
	const fdt = s => {
		if (!s) return '';
		try {
			const local = frappe.datetime.convert_to_user_tz ? frappe.datetime.convert_to_user_tz(s) : s;
			return frappe.datetime.str_to_user(local).replace(/:\d\d(\.\d+)?$/, '');
		} catch (e) { return String(s).slice(0, 16); }
	};
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
				view: 'board', board: 'deal', owners: null, prods: [], priority: '', q: '', attn: false, closed: false,
				cal_mode: 'month', cal_date: null, cal_type: 'all', sort: { key: '', dir: 1 }, sel: null, tab: 'overview',
			};
			this.cols = this.read_cols();

			page.set_primary_action(__('New Deal'), () => this.new_deal(), 'add');
			page.add_button(__('Export'), () => this.export_xlsx());
			page.add_menu_item(__('Deal List'), () => frappe.set_route('List', DT));
			page.add_menu_item(__('Sales Pipeline Settings'), () => frappe.set_route('Form', 'Sales Pipeline Settings'));

				this.$root = $(`
				<div class="sob">
					<div class="sob-boards" role="group" aria-label="${__('Board')}">
						${BOARDS.map(b => `<button type="button" class="sob-board-btn" data-board="${b[0]}" aria-pressed="false">${__(b[1])} <span class="sob-board-n"></span></button>`).join('')}
					</div>
					<div class="sob-kpis"></div>
					<nav class="sob-tabs" role="tablist" aria-label="${__('Views')}">
						${VIEWS.map(v => `<button type="button" class="sob-tab" role="tab" data-view="${v[0]}">${__(v[1])}</button>`).join('')}
					</nav>
					<div class="sob-filters">
						<div class="sob-fgroup sob-owner-group"><span class="sob-flabel">${__('Owner')}</span><div class="sob-pills sob-owner-pills"></div></div>
						<div class="sob-fgroup">
							<span class="sob-flabel" id="sob-prod-label">${__('Product Line')}</span>
							<div class="sob-ms">
								<button type="button" class="sob-pill sob-ms-btn" data-act="prod-menu" aria-haspopup="true" aria-expanded="false" aria-labelledby="sob-prod-label sob-prod-value"><span id="sob-prod-value"></span><span class="sob-caret" aria-hidden="true">${svg(ICON.down, 14)}</span></button>
								<div class="sob-ms-menu" role="group" aria-labelledby="sob-prod-label" hidden></div>
							</div>
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
			if (BOARDS.some(b => b[0] === p.get('board'))) s.board = p.get('board');
			if (p.has('owner')) s.owners = p.get('owner') ? p.get('owner').split(',') : [];
			if (p.has('product_line')) s.prods = (p.get('product_line') || '').split(',').map(x => x.trim()).filter(Boolean);
			else if (p.has('prod')) s.prods = p.get('prod') ? [p.get('prod')] : [];  // links saved before the multi-select
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
			p.set('board', s.board);
			p.set('view', s.view);
			if (s.owners !== null && this.data && this.data.is_manager) p.set('owner', s.owners.join(','));
			if (s.prods.length) p.set('product_line', s.prods.join(','));
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
			// keep lists readable in the address bar: product_line=VRR,LLR
			const url = window.location.pathname + '?' + p.toString().replace(/%2C/gi, ',');
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
				// sales people only ever see the deals they are assigned to, so they get no owner filter
				if (!r.is_manager || this.state.owners === null) this.state.owners = [];
				if (!this.state.cal_date) this.state.cal_date = r.today;
				if (!r.can_create) this.page.clear_primary_action();
				this.render();
				if (this.state.sel) this.load_feed(this.state.sel);
			}).catch(() => {
				this.$root.find('.sob-view').html(`<div class="sob-loading">${__('The board could not be loaded. Please refresh the page.')}</div>`);
			});
		}

		// ---------- lookups ----------

			stage(name) { return (this.s.stages || []).find(x => x.name === name) || null; }
			board_of(stage) { const st = this.stage(stage); return st && st.board === 'Lead' ? 'lead' : 'deal'; }
			stages_of(board) { return (this.s.stages || []).filter(x => (x.board === 'Lead' ? 'lead' : 'deal') === board); }
			first_stage_of(board) { const open = this.stages_of(board).filter(x => !x.is_closed); return (open[0] || this.stages_of(board)[0] || {}).name || this.s.first_stage; }
			lines_of(d) {
				const w = this.work && this.work[d.name];
				return (w || d.lines || []).filter(l => !l.draft || w);
			}
			calc_value(d) { return this.lines_of(d).filter(l => l.product_line).reduce((a, l) => a + (+l.total_grams || 0) * (+l.price_per_gram || 0), 0); }
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
				(opts.any_board || this.board_of(d.stage) === s.board) &&
				(opts.any_owner || !owners.length || owners.includes(d.deal_owner || NONE) || (d.co_owners || []).some(u => owners.includes(u))) &&
				(!s.prods.length || (d.lines && d.lines.length ? d.lines.some(l => s.prods.includes(l.product_line)) : s.prods.includes(d.product_line))) &&
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
			const all = this.filtered({ any_board: true });
			this.$root.find('.sob-board-btn').each((_, el) => {
				const b = $(el).attr('data-board');
				const on = b === s.board;
				$(el).toggleClass('on', on).attr('aria-pressed', on).find('.sob-board-n').text(all.filter(d => this.board_of(d.stage) === b).length);
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
			const won_value = sum(won, d => d.deal_value);
			// [label, figure, caption, state]: state colours the one cell that carries meaning
			const kpis = [
				[this.state.board === 'lead' ? __('Open leads') : __('Open deals'), n0(open.length), __('Excluding closed deals')],
				[__('Open value'), usd(sum(open, d => d.deal_value)), __('Grams × price per gram, or override')],
				[__('Weighted value'), usd(sum(open, d => d.weighted_value)), __('Value × stage probability')],
				[__('Grams in pipeline'), n0(grams) + ' g', (grams / 1000).toFixed(1) + ' kg ' + __('in open deals')],
				[__('Won value'), usd(won_value), won.length + ' ' + __('won in') + ' ' + MONTHS[today.getMonth()], won_value ? 'good' : ''],
				[__('Needs attention'), n0(attn.length), `${count('overdue')} ${__('overdue')} · ${count('stalled')} ${__('stalled')} · ${count('no_owner')} ${__('no owner')} · ${count('short')} ${__('short')}`, attn.length ? 'attn' : ''],
			];
			this.$root.find('.sob-kpis').html(kpis.map(k => `
				<div class="sob-kpi${k[3] ? ' ' + k[3] : ''}">
					<div class="sob-kpi-label">${esc(k[0])}</div>
					<div class="sob-kpi-value">${esc(k[1])}</div>
					<div class="sob-kpi-sub">${esc(k[2])}</div>
				</div>`).join(''));
		}

		render_filters() {
			const s = this.state;
			const owners = s.owners || [];
			const pill = (val, label, on, colour) => `<button type="button" class="sob-pill${on ? ' on' : ''}" data-owner="${esc(val)}" aria-pressed="${on}">${colour ? `<span class="sob-dot" style="background:${esc(colour)}"></span>` : ''}${esc(label)}</button>`;
			this.$root.find('.sob-owner-group').toggle(!!this.data.is_manager);
			this.$root.find('.sob-owner-pills').html(
				pill('', __('All'), !owners.length) +
				(this.s.owners || []).map(o => pill(o.user, o.name, owners.includes(o.user), o.colour)).join('') +
				pill(NONE, __('Unassigned'), owners.includes(NONE)));
			const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(label)}</option>`;
			// Product Line: multi-select checkbox menu
			const lines = this.s.product_lines || [];
			s.prods = s.prods.filter(p => lines.includes(p));
			const picked = s.prods;
			const label = !picked.length ? __('All') : picked.length <= 2 ? picked.join(', ') : __('{0} selected', [picked.length]);
			const box = (v, text, on) => `<label class="sob-ms-opt"><input type="checkbox" data-prod="${esc(v)}"${on ? ' checked' : ''}> <span>${esc(text)}</span></label>`;
			this.$root.find('#sob-prod-value').text(label);
			this.$root.find('.sob-ms-btn').toggleClass('on', !!picked.length).attr('title', picked.join(', '));
			// rebuild the menu only when the lines change, so keyboard focus stays on the ticked box
			const $menu = this.$root.find('.sob-ms-menu');
			const sig = lines.join('|');
			if ($menu.attr('data-sig') !== sig) $menu.attr('data-sig', sig).html(box('', __('All'), !picked.length) + lines.map(p => box(p, p, picked.includes(p))).join(''));
			$menu.find('[data-prod]').each((_, el) => {
				const v = el.getAttribute('data-prod');
				el.checked = v ? picked.includes(v) : !picked.length;
			});
			this.$root.find('.sob-prio').html(opt('', __('All'), s.priority) + (this.s.lists.priority || []).map(p => opt(p, p, s.priority)).join(''));
			const $q = this.$root.find('.sob-q');
			if ($q.val() !== s.q && document.activeElement !== $q.get(0)) $q.val(s.q);
			this.$root.find('[data-toggle="attn"]').toggleClass('on', s.attn).attr('aria-pressed', s.attn).text(__('Needs attention only'));
			this.$root.find('[data-toggle="closed"]').toggleClass('on', s.closed).attr('aria-pressed', s.closed)
				.text(__('Show closed'))
				.attr('title', __('Closed deals hide {0} days after closing', [this.s.hide_closed_after_days || 0]));
		}

		// Deal attributes read as one quiet line; only alerts (flags) get coloured tags.
		card_meta(d) {
			const m = [];
			if (d.status_detail) m.push(d.status_detail);
			if (d.samples) m.push(__('Samples') + ': ' + d.samples);
			if (d.copack === 'YES') m.push(__('Copack'));
			if (d.hardware) m.push(__('Hardware') + ': ' + d.hardware);
			return m.join(' · ');
		}

		badges(d) {
			return (d.flags || []).map(f => `<span class="sob-badge ${f.kind === 'action' ? 'act' : 'info'}">${esc(f.label)}</span>`).join('');
		}

		// The next dated step on a card, drawn in its calendar colour and icon.
		next_date_line(d) {
			const today = this.data.today;
			const up = d.next_step_due ? EVENTS[0] : EVENTS.filter(e => e.key !== 'followup' && d[e.field] && d[e.field] >= today)
				.sort((a, b) => (d[a.field] < d[b.field] ? -1 : 1))[0];
			return up ? `<div class="sob-card-next ev-${up.key}">${svg(up.icon, 12)}<span>${esc(__(up.label))} ${esc(nice(d[up.field]))}</span></div>` : '';
		}

		co_list(d) { return (d.co_owners || []).filter(u => u && u !== d.deal_owner); }

		// Primary owner, then up to two co-owners overlapped, then "+N".
		avatar(d) {
			const one = (user, cls, role) => {
				const o = this.owner(user);
				const name = o ? o.name : user;
				return `<span class="sob-av${cls}" style="background:${esc((o && o.colour) || '#18181B')}" title="${esc(name + role)}">${esc((name[0] || '?').toUpperCase())}</span>`;
			};
			const co = this.co_list(d);
			const parts = [d.deal_owner ? one(d.deal_owner, '', ' (' + __('owner') + ')') : `<span class="sob-av none" title="${__('Unassigned')}">?</span>`];
			co.slice(0, 2).forEach(u => parts.push(one(u, ' co', ' (' + __('co-owner') + ')')));
			if (co.length > 2) parts.push(`<span class="sob-av more" title="${esc(co.slice(2).map(u => this.owner_name(u)).join(', '))}">+${co.length - 2}</span>`);
			if (!co.length) return parts[0];
			const label = (d.deal_owner ? this.owner_name(d.deal_owner) : __('Unassigned')) + ' · ' + __('Co-owners') + ': ' + co.map(u => this.owner_name(u)).join(', ');
			return `<span class="sob-avs" role="img" aria-label="${esc(label)}">${parts.join('')}</span>`;
		}

		stage_chip(stage) {
			const st = this.stage(stage) || {};
			const c = st.colour || '#71717A';
			return `<span class="sob-stage-chip" style="background:${tint(c, .14)};color:${esc(c)};border-color:${tint(c, .35)}">${esc(__(stage))}</span>`;
		}

		card(d, opts) {
			opts = opts || {};
			const lines = d.lines || [];
			const grams = d.total_grams ? n0(d.total_grams) + ' g' + (d.price_per_gram && lines.length < 2 ? ' @ ' + money2(d.price_per_gram) + '/g' : '') : '';
			const prods = lines.length ? lines.map(l => [l.product_line, l.tier].filter(Boolean).join(' · ') + (lines.length > 1 && +l.total_grams ? ' · ' + n0(l.total_grams) + ' g' : ''))
				: [[d.product_line, d.tier].filter(Boolean).join(' · ')].filter(Boolean);
			const line = this.next_date_line(d);
			const meta = this.card_meta(d);
			const flags = this.badges(d);
			const st = this.stage(d.stage) || {};
			return `
				<div class="sob-card${this.state.sel === d.name ? ' sel' : ''}${this.busy[d.name] ? ' busy' : ''}${opts.co ? ' co' : ''}" role="button" tabindex="0"
					draggable="${this.data.can_write ? 'true' : 'false'}" data-card="${esc(d.name)}"${opts.col ? ` data-from-owner="${esc(opts.col)}"` : ''}
					aria-label="${esc(d.account + (opts.co ? ' (' + __('Co-owner') + ')' : ''))}"
					style="--sob-stage:${esc(st.colour || '#A1A1AA')}">
					${opts.co ? `<span class="sob-card-tag">${__('Co-owner')}</span>` : ''}
					<div class="sob-card-top">
						<span class="sob-card-acc">${this.is_top_priority(d.priority) ? `<span class="sob-prio-dot" title="${esc(__('Priority') + ': ' + d.priority)}"></span>` : ''}${esc(d.account)}</span>
						<span class="sob-card-side">
							<button type="button" class="sob-qn" data-quick-note="${esc(d.name)}" draggable="false" title="${esc(__('Add a quick note'))}" aria-label="${esc(__('Add a quick note to {0}', [d.account]))}">${svg(NOTE_ICON, 14)}</button>
							${this.avatar(d)}
						</span>
					</div>
					${opts.stage_chip ? this.stage_chip(d.stage) : ''}
					${prods.length ? `<div class="sob-prods">${prods.map(p => `<span class="sob-prod">${esc(p)}</span>`).join('')}</div>` : ''}
					<div class="sob-card-nums"><b>${d.deal_value ? usd(d.deal_value) : '—'}</b><span>${esc(grams)}</span></div>
					${d.timeline ? `<div class="sob-card-when">${esc(d.timeline)}</div>` : ''}
					${meta ? `<div class="sob-card-meta">${esc(meta)}</div>` : ''}
					${line}
					${flags ? `<div class="sob-badges">${flags}</div>` : ''}
				</div>`;
		}

		col_sub(items) {
			const v = items.reduce((a, d) => a + (+d.deal_value || 0), 0);
			const w = items.reduce((a, d) => a + (+d.weighted_value || 0), 0);
			const lead = this.state.board === 'lead';
			return `${items.length} ${items.length === 1 ? (lead ? __('lead') : __('deal')) : (lead ? __('leads') : __('deals'))} · ${usd(v)} · ${usd(w)} ${__('weighted')}`;
		}

		keep_scroll($v, html, sel) {
			const left = $v.find(sel).scrollLeft() || 0;
			$v.html(html);
			$v.find(sel).scrollLeft(left);
		}

		render_board($v, list) {
			const html = this.stages_of(this.state.board).map(st => {
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
			this.keep_scroll($v, `<div class="sob-hint">${(this.state.board === 'lead' ? __('Drag a lead to another status, or open it. Moving it to a deal stage puts it on the Deals board.') : __('Drag a card to another stage, or click it to open the deal'))}</div><div class="sob-scroll"><div class="sob-columns">${html}</div></div>`, '.sob-scroll');
		}

		render_owner($v, list) {
			const s = this.state;
			const picked = s.owners || [];
			let cols = (this.s.owners || []).filter(o => !picked.length || picked.includes(o.user)).map(o => ({ id: o.user, name: o.name, colour: o.colour }));
			if (this.data.is_manager) {
				if (!picked.length || picked.includes(NONE)) cols.push({ id: NONE, name: __('Unassigned'), colour: '' });
			} else {
				cols = cols.filter(c => c.id === this.data.user);
				if (!cols.length) cols = [{ id: this.data.user, name: __('My deals'), colour: '' }];
			}
			const today = this.data.today;
			const order = st => { const i = (this.s.stages || []).findIndex(x => x.name === st); return i < 0 ? 99 : i; };
			const html = cols.map(c => {
				const shared = d => c.id !== NONE && d.deal_owner !== c.id && this.co_list(d).includes(c.id);
				const items = list.filter(d => (d.deal_owner || NONE) === c.id || shared(d))
					.sort((a, b) => order(a.stage) - order(b.stage) || this.prio_rank(a.priority) - this.prio_rank(b.priority));
				const overdue = items.filter(d => !d.is_closed && d.next_step_due && d.next_step_due < today).length;
				const unassigned = c.id === NONE;
				return `
					<section class="sob-col sob-owner-col${unassigned && items.length ? ' warn' : ''}" ${unassigned ? '' : `data-drop-owner="${esc(c.id)}"`} aria-label="${esc(c.name)}">
						<header class="sob-col-head">
							<div class="sob-col-title"><span>${c.colour ? `<span class="sob-dot" style="background:${esc(c.colour)}"></span>` : ''}${esc(c.name)}</span>
								${overdue ? `<span class="sob-badge act">${overdue} ${__('overdue')}</span>` : ''}</div>
							<div class="sob-col-sub">${esc(this.col_sub(items))}</div>
							${unassigned && items.length ? `<div class="sob-col-note">${__('Drag these deals to an owner')}</div>` : ''}
						</header>
						${items.map(d => this.card(d, { stage_chip: true, co: shared(d), col: c.id })).join('')}
						${items.length ? '' : `<div class="sob-col-empty">${unassigned ? __('Every deal has an owner') : __('Drop a deal here to reassign')}</div>`}
					</section>`;
			}).join('');
			this.keep_scroll($v, `<div class="sob-hint">${__('Drag a card to another owner to change its owner. The new owner is notified. Shared deals also appear in each co-owner\'s column.')}</div><div class="sob-scroll"><div class="sob-columns">${html}</div></div>`, '.sob-scroll');
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
			return `<div class="sob-ev ev-${ev.e.key}${ev.overdue ? ' overdue' : ''}" draggable="${this.data.can_write ? 'true' : 'false'}" role="button" tabindex="0"
				data-event="${esc(ev.d.name)}" data-field="${ev.e.field}"
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
						<button type="button" class="sob-btn sm icon" data-cal="prev" aria-label="${__('Previous')}">${svg(ICON.left, 16)}</button>
						<button type="button" class="sob-btn sm" data-cal="today">${__('Today')}</button>
						<button type="button" class="sob-btn sm icon" data-cal="next" aria-label="${__('Next')}">${svg(ICON.right, 16)}</button>
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
				<div class="sob-legend">${EVENTS.map(e => `<span class="ev-${e.key}"><i class="sob-sw"></i>${esc(__(e.label))}</span>`).join('')}<span class="sob-legend-over">${__('Overdue follow-ups are listed on today')}</span></div>
				<div class="sob-scroll"><div class="sob-cal ${s.cal_mode}">
					${WD.map(w => `<div class="sob-cal-head">${w}</div>`).join('')}
					${cells.join('')}
				</div></div>
				<section class="sob-agenda">
					<h3>${__('This week')}</h3>
					${agenda.length ? agenda.map(ev => `
						<div class="sob-agenda-row" role="button" tabindex="0" data-open="${esc(ev.d.name)}">
							<span class="sob-agenda-date${ev.overdue ? ' over' : ''}">${ev.overdue ? __('Overdue') + ' · ' : ''}${esc(nice(ev.real))}</span>
							<span class="sob-agenda-type ev-${ev.e.key}">${svg(ev.e.icon, 12)} ${esc(__(ev.e.label))}</span>
							<span class="sob-agenda-acc">${esc(ev.d.account)}</span>
							<span class="sob-agenda-meta">${esc(ev.d.deal_owner ? this.owner_name(ev.d.deal_owner) : __('Unassigned'))} · ${esc(__(ev.d.stage))}</span>
						</div>`).join('') : `<div class="sob-empty">${__('Nothing scheduled in the next 7 days')}</div>`}
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
				case 'co': return this.co_list(d).map(u => this.owner_name(u)).join(', ');
				case 'date': case 'date_edit': return v ? fdate(v) : '';
				case 'datetime': return v ? frappe.datetime.str_to_user(v) : '';
				default:
					if ((c[0] === 'product_line' || c[0] === 'tier') && (d.lines || []).length > 1) return [...new Set(d.lines.map(l => l[c[0]]).filter(Boolean))].join(', ');
					return c[0] === 'deal_owner' ? (v ? this.owner_name(v) : __('Unassigned')) : (v == null ? '' : v);
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
			// sheet colours: money columns carry a blue tint, an overdue follow-up date gets the red aging fill
			const today = this.data.today;
			const kls = (c, d) => [
				['num', 'money', 'money2', 'pct'].includes(c[2]) ? 'r' : '',
				['money', 'money2'].includes(c[2]) ? 'money' : '',
				d && c[0] === 'next_step_due' && !d.is_closed && d.next_step_due && d.next_step_due < today ? 'late' : '',
			].filter(Boolean).join(' ');
			const arrow = c => sk === c[0] ? svg(s.sort.dir > 0 ? ICON.up : ICON.down, 12) : '';
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
					<thead><tr>${cols.map(c => `<th class="${kls(c)}"><button type="button" data-sort="${c[0]}" class="${sk === c[0] ? 'on' : ''}">${esc(__(c[1]))}${arrow(c)}</button></th>`).join('')}</tr></thead>
					<tbody>${rows.map(d => `<tr data-open="${esc(d.name)}" class="${s.sel === d.name ? 'sel' : ''}">${cols.map(c => `<td class="${kls(c, d)}">${cell(d, c)}</td>`).join('')}</tr>`).join('') ||
						`<tr><td colspan="${cols.length}" class="sob-empty">${__('No deals match these filters')}</td></tr>`}</tbody>
					<tfoot><tr>${totals.map((t, i) => `<td class="${kls(cols[i])}">${esc(t)}</td>`).join('')}</tr></tfoot>
				</table></div>`);
			$v.find('.sob-table-wrap').scrollLeft(left);
		}

		owner_choices(d) {
			const all = this.s.owners || [];
			if (this.data.is_manager) return all;
			return all.filter(o => o.user === this.data.user || (d && o.user === d.deal_owner));
		}

		// ---------- drawer ----------

		// Buyer, product and notes: owners on their own deals, pipeline managers on any deal (server checks the same).
		can_edit(d) {
			return !!(d && this.data.can_write && (this.data.is_manager || d.deal_owner === this.data.user || this.co_list(d).includes(this.data.user)));
		}

		// Only the primary owner or a pipeline manager changes the co-owners.
		can_edit_owners(d) {
			return !!(d && this.data.can_write && (this.data.is_manager || d.deal_owner === this.data.user));
		}

		co_owner_block(d) {
			const editable = this.can_edit_owners(d);
			const co = this.co_list(d);
			const people = (this.s.owners || []).filter(o => o.user !== d.deal_owner).map(o => ({ user: o.user, name: o.name, colour: o.colour }));
			co.forEach(u => { if (!people.some(p => p.user === u)) people.push({ user: u, name: this.owner_name(u), colour: '' }); });
			const chip = p => {
				const on = co.includes(p.user);
				return `<button type="button" class="sob-pill sob-co-chip${on ? ' on' : ''}" data-co="${esc(p.user)}" aria-pressed="${on}"${editable ? '' : ' disabled'}>${p.colour ? `<span class="sob-dot" style="background:${esc(p.colour)}"></span>` : ''}${esc(p.name)}</button>`;
			};
			const shown = editable ? people : people.filter(p => co.includes(p.user));
			return `<div class="sob-block">
				<div class="sob-cap" id="sob-co-label">${__('Co-owners')}</div>
				<div class="sob-pills" role="group" aria-labelledby="sob-co-label">${shown.length ? shown.map(chip).join('') : `<span class="sob-muted">${__('No co-owners')}</span>`}</div>
				<div class="sob-muted">${editable ? __('Co-owners see and edit this deal like the owner. Tap a name to add or remove it.') : __('Only the deal owner or a pipeline manager can change the co-owners.')}</div>
			</div>`;
		}

		tiers_for(line) { return ((this.s.line_tiers || {})[line] || []).slice(); }

		editing(d, key) { return !!(this.editor && this.editor.deal === d.name && this.editor.key === key); }

		// Click-to-edit value. Enter or leaving the field saves; Escape cancels.
		ed(d, field, label, opts) {
			opts = opts || {};
			const editable = this.can_edit(d);
			const v = d[field];
			const shown = opts.html || (v == null || v === '' || (opts.type === 'number' && !+v) ? '' : esc(opts.fmt ? opts.fmt(v) : v));
			const tile = opts.tile;
			if (editable && this.editing(d, 'f:' + field)) {
				const type = opts.type || 'text';
				const raw = 'value' in opts ? opts.value : v;
				const val = raw == null || (type === 'number' && !+raw) ? '' : raw;
				const input = type === 'textarea'
					? `<textarea class="sob-ed-input" rows="3" data-ed-field="${field}" data-keep="f:${field}" aria-label="${esc(label)}">${esc(val)}</textarea>`
					: `<input class="sob-ed-input" type="${type}"${type === 'number' ? ' step="any" min="0" inputmode="decimal"' : ''} data-ed-field="${field}" data-keep="f:${field}" value="${esc(val)}" aria-label="${esc(label)}">`;
				return tile ? `<div class="sob-tile on"><span>${esc(label)}</span>${input}</div>`
					: `<div class="sob-f sob-ed on"><span>${esc(label)}</span><span>${input}<small class="sob-muted">${type === 'textarea' ? __('Enter to save, Shift+Enter for a new line, Esc to cancel') : __('Enter to save, Esc to cancel')}</small></span></div>`;
			}
			if (!editable) {
				if (tile) return `<div class="sob-tile"><span>${esc(label)}</span><b>${shown || '—'}</b></div>`;
				return shown ? `<div class="sob-f"><span>${esc(label)}</span><span>${shown}</span></div>` : '';
			}
			const empty = `<span class="sob-ed-empty">${esc(opts.placeholder || __('Add'))}</span>`;
			const pen = `<span class="sob-pen" aria-hidden="true">${svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>', 12)}</span>`;
			if (tile) return `<div class="sob-tile sob-ed" role="button" tabindex="0" data-ed="${field}" title="${esc(__('Click to edit'))}"><span>${esc(label)} ${pen}</span><b>${shown || empty}</b></div>`;
			return `<div class="sob-f sob-ed" role="button" tabindex="0" data-ed="${field}" title="${esc(__('Click to edit'))}"><span>${esc(label)}</span><span>${shown || empty}${pen}</span></div>`;
		}

		// Requirement lines: a deal can ask for several product lines. Changes save as soon as a field changes.
		req_editor(d) {
			const editable = this.can_edit(d);
			const w = this.work && this.work[d.name];
			const lines = w || (d.lines || []).map((l, i) => Object.assign({}, l, { key: l.name || 'v' + i }));
			const all_lines = this.s.product_lines || [];
			const o = (v, t, cur) => `<option value="${esc(v)}"${(cur || '') === v ? ' selected' : ''}>${esc(t)}</option>`;
			const busy = this.busy[d.name] ? ' busy' : '';
			const row = (l, i) => {
				const tiers = this.tiers_for(l.product_line);
				if (l.tier && !tiers.includes(l.tier)) tiers.unshift(l.tier);
				const line_opts = o('', __('Choose a product line'), l.product_line) + all_lines.map(x => o(x, x, l.product_line)).join('') +
					(l.product_line && !all_lines.includes(l.product_line) ? o(l.product_line, l.product_line, l.product_line) : '');
				const tier_opts = tiers.length ? o('', __('No tier'), l.tier) + tiers.map(x => o(x, x, l.tier)).join('')
					: o('', l.product_line ? __('No tiers for this line') : __('Tier'), '');
				const amount = (+l.total_grams || 0) * (+l.price_per_gram || 0);
				const stock = l.stock_grams == null || l.draft ? '' : (+l.short > 0
					? `<span class="sob-badge act" title="${esc(__('{0} g available', [n0(l.stock_grams)]))}">${__('Short')} ${n0(l.short)} g</span>`
					: `<span class="sob-badge ok" title="${esc(__('{0} g available', [n0(l.stock_grams)]))}">${__('In stock')}</span>`);
				const dis = editable ? '' : ' disabled';
				const k = esc(l.key);
				return `<div class="sob-req${l.draft ? ' draft' : ''}" data-req="${k}">
					<div class="sob-req-head"><span class="sob-req-n">${i + 1}</span>
						<select data-req-field="product_line" aria-label="${esc(__('Product line, requirement {0}', [i + 1]))}"${dis}>${line_opts}</select>
						<select data-req-field="tier" aria-label="${esc(__('Tier, requirement {0}', [i + 1]))}"${editable && tiers.length ? '' : ' disabled'}>${tier_opts}</select>
						${editable ? `<button type="button" class="sob-x sm" data-req-remove="${k}" aria-label="${esc(__('Remove requirement {0}', [i + 1]))}" title="${esc(__('Remove'))}">${svg(ICON.x, 14)}</button>` : ''}
					</div>
					<div class="sob-req-nums">
						<label>${__('Grams')}<input type="number" min="0" step="any" inputmode="decimal" data-req-field="total_grams" data-keep="req:${k}:g" value="${+l.total_grams ? esc(l.total_grams) : ''}"${dis}></label>
						<label>${__('Price / g')}<input type="number" min="0" step="any" inputmode="decimal" data-req-field="price_per_gram" data-keep="req:${k}:p" value="${+l.price_per_gram ? esc(l.price_per_gram) : ''}"${dis}></label>
						<div class="sob-req-amt"><span>${__('Amount')}</span><b>${amount ? usd(amount) : '—'}</b></div>
						<div class="sob-req-stock">${stock}</div>
					</div>
				</div>`;
			};
			return `<div class="sob-block sob-reqs${busy}">
				<div class="sob-cap">${__('Requirements')}</div>
				${lines.length ? lines.map(row).join('') : `<div class="sob-muted">${__('No product requirements yet.')}</div>`}
				${editable ? `<button type="button" class="sob-btn sm sob-req-add" data-act="req-add">${svg(ICON.plus, 14)}${__('Add requirement')}</button>` : ''}
			</div>`;
		}

		value_tiles(d) {
			const calc = this.calc_value(d);
			const manual = +d.value_override > 0;
			const value = manual ? +d.value_override : calc;
			const st = this.stage(d.stage) || {};
			const lines = this.lines_of(d).filter(l => l.product_line);
			const grams = lines.reduce((a, l) => a + (+l.total_grams || 0), 0);
			const avg = grams ? calc / grams : 0;
			const shown = (value ? usd(value) : '—') + (manual ? ` <span class="sob-badge manual">${__('Manual')}</span>` : '');
			const tile = this.can_edit(d)
				? this.ed(d, 'value_override', __('Deal value'), { tile: true, type: 'number', html: shown, value: value || '' })
				: `<div class="sob-tile"><span>${__('Deal value')}</span><b>${shown}</b></div>`;
			return `<div class="sob-tiles">
				${tile}
				<div class="sob-tile"><span>${__('Weighted')}</span><b>${value ? usd(value * (+st.probability || 0) / 100) : '—'}</b></div>
				<div class="sob-tile"><span>${__('Grams')}</span><b>${grams ? n0(grams) : '—'}</b></div>
				<div class="sob-tile"><span>${lines.length > 1 ? __('Avg price / g') : __('Price per gram')}</span><b>${avg ? money2(avg) : '—'}</b></div>
			</div>${manual ? `<div class="sob-manual-note"><span class="sob-muted">${__('Manual deal value. Calculated from the requirements: {0}.', [calc ? usd(calc) : '$0'])}</span>
				${this.can_edit(d) ? `<button type="button" class="sob-link" data-act="value-reset">${__('Use calculated value')}</button>` : ''}</div>`
				: (this.can_edit(d) ? `<div class="sob-muted">${__('Click Deal value to enter it by hand.')}</div>` : '')}`;
		}

		buyer_tab(d) {
			const editable = this.can_edit(d);
			const has = !!(d.customer || d.lead);
			const link = (dt, name, title) => `<a href="/app/${dt === 'Customer' ? 'customer' : 'lead'}/${encodeURIComponent(name)}">${esc(title || name)}</a>`;
			const searching = editable && (this.bsearch === d.name || !has);
			let head;
			if (has) {
				const main = d.customer ? ['Customer', d.customer, d.customer_title] : ['Lead', d.lead, d.lead_title];
				head = `<div class="sob-buyer-cur">
						<span class="sob-badge ${main[0] === 'Customer' ? 'cust' : 'lead'}">${esc(__(main[0]))}</span>
						<span class="sob-buyer-name">${link(main[0], main[1], main[2])}</span>
						${editable && !searching ? `<button type="button" class="sob-btn sm" data-act="buyer-change">${__('Change')}</button>` : ''}
					</div>
					${d.customer && d.lead ? `<div class="sob-muted">${__('Lead')}: ${link('Lead', d.lead, d.lead_title)}</div>` : ''}`;
			} else {
				head = `<div class="sob-buyer-empty">
						<div><b>${__('No buyer linked yet')}</b>
							<div class="sob-muted">${editable ? __('Create a new Customer or Lead, or search for an existing one below.') : __('The deal owner or a pipeline manager can add the buyer.')}</div></div>
						${editable ? `<button type="button" class="sob-btn primary sm" data-act="buyer-new">${__('Add buyer')}</button>` : ''}
					</div>`;
			}
			const search = searching ? `
				<div class="sob-bsearch">
					<div class="sob-bsearch-box">
						<input type="search" class="sob-bsearch-input" data-keep="bsearch" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="sob-bsearch-list"
							aria-label="${__('Search customers and leads')}" placeholder="${__('Search customers and leads')}">
						<div class="sob-bsearch-list" id="sob-bsearch-list" role="listbox" hidden></div>
					</div>
					${has ? `<button type="button" class="sob-btn sm" data-act="buyer-cancel">${__('Cancel')}</button>` : ''}
				</div>` : '';
			const contact = [d.contact_name, d.phone, d.email, d.location_address, d.license_number].some(Boolean);
			const tel = d.phone ? `<a href="tel:${esc(String(d.phone).replace(/[^0-9+]/g, ''))}">${esc(d.phone)}</a>` : '';
			const mail = d.email ? `<a href="mailto:${esc(d.email)}">${esc(d.email)}</a>` : '';
			const fields = has || contact ? `<div class="sob-fields">
					${this.ed(d, 'contact_name', __('Contact name'), { placeholder: __('Add contact name') })}
					${this.ed(d, 'phone', __('Phone'), { type: 'tel', html: tel, placeholder: __('Add phone') })}
					${this.ed(d, 'email', __('Email'), { type: 'email', html: mail, placeholder: __('Add email') })}
					${this.ed(d, 'location_address', __('Location / Address'), { type: 'textarea', placeholder: __('Add location') })}
					${this.ed(d, 'license_number', __('License #'), { placeholder: __('Add license number') })}
				</div>` : '';
			const locked = !editable && this.data.can_write ? `<div class="sob-muted">${__('Only the deal owner or a pipeline manager can edit the buyer.')}</div>` : '';
			return `<div class="sob-block"><div class="sob-cap">${__('Customer / Lead')}</div>${head}${search}</div>${fields}${locked}`;
		}

		note_section(d, f, label, editable) {
			const editing = editable && this.editing(d, 'n:' + f);
			return `<section class="sob-nsec">
				<header><span>${esc(__(label))}</span>${editable && !editing ? `<button type="button" class="sob-btn sm" data-nsec-edit="${f}">${__('Edit')}</button>` : ''}</header>
				${editing ? `<textarea class="sob-note" rows="4" data-nsec-input="${f}" data-keep="n:${f}" aria-label="${esc(__(label))}">${esc(d[f] || '')}</textarea>
					<div class="sob-row-end"><button type="button" class="sob-btn sm" data-act="ed-cancel">${__('Cancel')}</button><button type="button" class="sob-btn primary sm" data-nsec-save="${f}">${__('Save')}</button></div>`
				: `<div class="sob-nsec-body${d[f] ? '' : ' empty'}">${d[f] ? esc(d[f]) : __('Nothing added yet.')}</div>`}
			</section>`;
		}

		note_item(d, n) {
			const editing = n.can_edit && this.editing(d, 'c:' + n.name);
			const acts = !editing && (n.can_edit || n.can_delete) ? `<span class="sob-note-acts">
				${n.can_edit ? `<button type="button" class="sob-link" data-note-edit="${esc(n.name)}">${__('Edit')}</button>` : ''}
				${n.can_delete ? `<button type="button" class="sob-link danger" data-note-del="${esc(n.name)}">${__('Delete')}</button>` : ''}</span>` : '';
			return `<article class="sob-noteitem">
				<header><b>${esc(n.by)}</b><span class="sob-muted">${esc(fdt(n.on))}${n.edited ? ' · ' + __('edited') : ''}</span>${acts}</header>
				${editing ? `<textarea class="sob-note" rows="3" data-keep="c:${esc(n.name)}" data-note-input="${esc(n.name)}" aria-label="${__('Edit note')}">${esc(n.text)}</textarea>
					<div class="sob-row-end"><button type="button" class="sob-btn sm" data-act="ed-cancel">${__('Cancel')}</button><button type="button" class="sob-btn primary sm" data-note-save="${esc(n.name)}">${__('Save')}</button></div>`
				: `<div class="sob-note-text">${esc(n.text)}</div>`}
			</article>`;
		}

		notes_tab(d, field) {
			const feed = this.feed && this.feed.name === d.name ? this.feed : null;
			const notes = feed ? feed.notes : null;
			const list = notes === null ? `<div class="sob-muted">${__('Loading…')}</div>`
				: notes.length ? notes.map(n => this.note_item(d, n)).join('')
				: `<div class="sob-empty">${__('No notes yet. Add the first note above.')}</div>`;
			const editable = this.can_edit(d);
			return `
				${this.quick_notes_html()}
				<div class="sob-note-box">
					<label class="sob-cap" for="sob-note-new">${__('Add note')}</label>
					<textarea id="sob-note-new" class="sob-note" data-keep="note-new" rows="3" placeholder="${__('Write a note about this deal')}"></textarea>
					<button type="button" class="sob-btn primary sm" data-act="note">${__('Save')}</button>
				</div>
				<div class="sob-notes">${list}</div>
				<div class="sob-block">
					<div class="sob-cap">${__('Deal notes')}</div>
					${NOTE_SECTIONS.map(x => this.note_section(d, x[0], x[1], editable)).join('')}
				</div>
				<div class="sob-fields">${field(__('Payment terms'), d.payment_terms)}${field(__('Lead source'), d.lead_source)}</div>`;
		}

		quick_notes_html() {
			const qn = (this.s.lists && this.s.lists.quick_notes) || [];
			if (!qn.length) return '';
			return `<div class="sob-quick"><div class="sob-cap" id="sob-qn-label">${__('Quick notes')}</div>
				<div class="sob-pills" role="group" aria-labelledby="sob-qn-label">${qn.map(t => `<button type="button" class="sob-pill sob-qchip" data-qnote="${esc(t)}">${esc(t)}</button>`).join('')}</div>
				<div class="sob-muted">${__('One click adds the note with your name and the time.')}</div></div>`;
		}

		add_quick_note(name, text, btn) {
			const d = this.find(name);
			text = (text || '').trim();
			if (!d || !text) return Promise.resolve();
			if (btn) $(btn).prop('disabled', true);
			return frappe.xcall(M + 'add_note', { name, note: text }).then(notes => {
				this.set_notes(name, notes);
				frappe.show_alert({ message: __('Note added to {0}: {1}', [d.account, text]), indicator: 'green' });
			}).finally(() => { if (btn) $(btn).prop('disabled', false); });
		}

		quick_note_dialog(name) {
			const d = this.find(name);
			if (!d) return;
			const qn = (this.s.lists && this.s.lists.quick_notes) || [];
			const dlg = new frappe.ui.Dialog({
				title: __('Quick note: {0}', [d.account]),
				fields: [
					{ fieldname: 'chips', fieldtype: 'HTML', options: qn.length ? `<div class="sob-pills sob-dlg-quick">${qn.map(t => `<button type="button" class="sob-pill sob-qchip" data-dlg-qnote="${esc(t)}">${esc(t)}</button>`).join('')}</div>
						<p class="help-box small text-muted">${__('Click one to save it right away, or write your own note below.')}</p>` : '' },
					{ fieldname: 'note', fieldtype: 'Small Text', label: __('Note') },
				],
				primary_action_label: __('Save note'),
				primary_action: v => {
					if (!(v.note || '').trim()) { frappe.msgprint(__('Please type a note first.')); return; }
					dlg.disable_primary_action();
					this.add_quick_note(name, v.note).then(() => dlg.hide()).catch(() => dlg.enable_primary_action());
				},
			});
			dlg.$wrapper.on('click', '[data-dlg-qnote]', e => {
				this.add_quick_note(name, $(e.currentTarget).attr('data-dlg-qnote'), e.currentTarget).then(() => dlg.hide());
			});
			dlg.show();
		}

		activity_tab(d) {
			const feed = this.feed && this.feed.name === d.name ? this.feed : null;
			const items = feed ? feed.activity : null;
			if (items === null) return `<div class="sob-muted">${__('Loading…')}</div>`;
			if (!items.length) return `<div class="sob-empty">${__('No activity yet.')}</div>`;
			return `<div class="sob-activity">${items.map(a => `
				<div class="sob-act ${esc(a.kind)}"><div>${esc(a.text)}</div>
					<div class="sob-muted">${esc(fdt(a.on))}${a.detail ? ' · ' + esc(a.detail) : ''}</div></div>`).join('')}</div>`;
		}

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
			const feed = this.feed && this.feed.name === d.name ? this.feed : null;
			const n_notes = feed && feed.notes ? feed.notes.length : 0;
			const tabs = [['overview', __('Overview')], ['buyer', __('Buyer')], ['requirements', __('Requirements')],
				['notes', n_notes ? __('Notes') + ` (${n_notes})` : __('Notes')], ['activity', __('Activity')]];
			const field = (label, value, html) => (value || html) ? `<div class="sob-f"><span>${esc(label)}</span><span>${html || esc(value)}</span></div>` : '';
			let body = '';
			if (tab === 'overview') {
				const stock = d.stock ? `${n0(d.stock.grams)} g ${__('available')} (${esc(d.stock.groups.join(', '))})${d.stock.on_orders ? ` · ${n0(d.stock.on_orders)} g ${__('on open Sales Orders')}` : ''}` : '';
				const dates = EVENTS.map(e => `
					<label class="sob-date"><span class="ev-${e.key}">${svg(e.icon, 12)} ${esc(__(e.label))}</span>
						<input type="date" data-panel-field="${e.field}" value="${esc(d[e.field] || '')}"${can ? '' : ' disabled'}></label>`).join('');
				body = `
					${(d.flags || []).length ? `<div class="sob-badges">${(d.flags || []).map(f => `<span class="sob-badge ${f.kind === 'action' ? 'act' : 'info'}">${esc(f.label)}</span>`).join('')}</div>` : ''}
					${can ? `<div class="sob-block"><div class="sob-cap">${__('Stage')}</div>${BOARDS.map(b => {
					const sts = this.stages_of(b[0]);
					if (!sts.length) return '';
					return `<div class="sob-stage-group"><span class="sob-stage-board">${esc(b[0] === 'lead' ? __('Lead board') : __('Deal board'))}</span><div class="sob-moves">${sts.map(x => `<button type="button" class="sob-move${x.name === d.stage ? ' on' : ''}" data-move="${esc(x.name)}" aria-pressed="${x.name === d.stage}"${x.colour ? ` style="--sob-stage:${esc(x.colour)}"` : ''}>${esc(__(x.name))}</button>`).join('')}</div></div>`;
				}).join('')}</div>` : ''}
					${this.value_tiles(d)}
					${this.req_editor(d)}
					<div class="sob-two">
						<label class="sob-cap">${__('Owner')}
							<select data-panel-field="deal_owner"${can && this.data.is_manager ? '' : ' disabled'}>${[['', __('Unassigned')]].concat(this.owner_choices(d).map(o => [o.user, o.name])).map(o => `<option value="${esc(o[0])}"${(d.deal_owner || '') === o[0] ? ' selected' : ''}>${esc(o[1])}</option>`).join('')}</select></label>
						<label class="sob-cap">${__('Priority')}
							<select data-panel-field="priority"${can ? '' : ' disabled'}>${(this.s.lists.priority || []).map(p => `<option${p === d.priority ? ' selected' : ''}>${esc(p)}</option>`).join('')}</select></label>
					</div>
					${this.co_owner_block(d)}
					<div class="sob-dates">${dates}</div>
					<div class="sob-fields">
						${field(__('Stock available'), stock)}
						${field(__('In stage'), d.days_in_stage + ' ' + __('days') + (st.max_days ? ' ' + __('(limit {0})', [st.max_days]) : ''))}
						${field(__('Timeline'), d.timeline)}
						${field(__('Status detail'), d.status_detail)}
						${field(__('Lost reason'), d.lost_reason)}
					</div>`;
			} else if (tab === 'buyer') {
				body = this.buyer_tab(d);
			} else if (tab === 'requirements') {
				body = `${this.req_editor(d)}
					${this.value_tiles(d)}
					<div class="sob-fields">
						${field(__('Stock check'), (d.lines || []).length ? (d.short ? `${__('Short')} ${n0(d.short)} g ${__('across all requirements')}` : __('In stock for all requirements')) : '')}
						${field(__('Form'), d.form)}
						${field(__('Size per strain'), d.size_per_strain)}${field(__('Strain profiles'), d.strain_profiles)}
						${field(__('Samples'), d.samples)}${field(__('Copack'), d.copack)}${field(__('Hardware'), d.hardware)}
					</div>`;
			} else if (tab === 'notes') {
				body = this.notes_tab(d, field);
			} else {
				body = this.activity_tab(d);
			}
			const won = this.won_stage(), lost = this.lost_stage();
			// keep typed text, focus and scroll when the drawer re-renders (board reloads, saves)
			const same = this._drawer_deal === d.name;
			const kept = {};
			let focus = null, range = null;
			this.$drawer.find('[data-keep]').each((_, el) => {
				const k = el.getAttribute('data-keep');
				kept[k] = el.value;
				if (el === document.activeElement) {
					focus = k;
					try { range = [el.selectionStart, el.selectionEnd]; } catch (x) { range = null; }
				}
			});
			const scroll = same && this._drawer_tab === tab ? this.$drawer.find('.sob-d-body').scrollTop() : 0;
			this._drawer_deal = d.name;
			this._drawer_tab = tab;
			this._rendering = true;
			try {
				this.$drawer.find('.sob-drawer').html(`
					<header class="sob-d-head">
						<div class="sob-d-row">${this.stage_chip(d.stage)}<span class="sob-muted">${+st.probability || 0}% · ${esc(d.name)}</span>
							<button type="button" class="sob-x" data-act="close" aria-label="${__('Close')}">${svg(ICON.x, 16)}</button></div>
						<h2>${esc(d.account)}</h2>
						<div class="sob-muted">${esc((d.lines || []).length ? d.lines.map(l => [l.product_line, l.tier].filter(Boolean).join(' · ')).join(', ') : ([d.product_line, d.tier].filter(Boolean).join(' · ') || __('Product not set yet')))} · ${esc(d.deal_owner ? this.owner_name(d.deal_owner) : __('Unassigned'))}${this.co_list(d).length ? esc(' + ' + this.co_list(d).map(u => this.owner_name(u)).join(', ')) : ''}</div>
						<nav class="sob-d-tabs" role="tablist">${tabs.map(t => `<button type="button" role="tab" class="${t[0] === tab ? 'on' : ''}" aria-selected="${t[0] === tab}" data-tab="${t[0]}">${esc(t[1])}</button>`).join('')}</nav>
					</header>
					<div class="sob-d-body">${body}</div>
					<footer class="sob-d-foot">
						<button type="button" class="sob-btn" data-act="form">${__('Open full form')}</button>
						${this.data.can_quote ? `<button type="button" class="sob-btn" data-act="quote">${__('Create Quotation')}</button>` : ''}
						${tab === 'overview' ? this.email_button(d) : ''}
						${can && won && d.stage !== won.name ? `<button type="button" class="sob-btn won" data-act="won">${__('Mark Won')}</button>` : ''}
						${can && lost && d.stage !== lost.name ? `<button type="button" class="sob-btn lost" data-act="lost">${__('Mark Lost')}</button>` : ''}
					</footer>`);
				if (same) {
					this.$drawer.find('[data-keep]').each((_, el) => {
						const k = el.getAttribute('data-keep');
						if (Object.prototype.hasOwnProperty.call(kept, k)) el.value = kept[k];
						if (k === focus) {
							el.focus();
							if (range) { try { el.setSelectionRange(range[0], range[1]); } catch (x) { /* number/email inputs */ } }
						}
					});
				}
				if (scroll) this.$drawer.find('.sob-d-body').scrollTop(scroll);
				if (this._focus_new) {
					this._focus_new = false;
					const el = this.$drawer.find('.sob-ed-input, [data-nsec-input], [data-note-input], .sob-bsearch-input').get(0);
					if (el) {
						el.focus();
						if (el.tagName === 'INPUT') { try { el.select(); } catch (x) { /* ignore */ } }
						else { const n = el.value.length; try { el.setSelectionRange(n, n); } catch (x) { /* ignore */ } }
					}
				}
			} finally {
				this._rendering = false;
			}
			this.render_bresults();
		}

		load_feed(name) {
			return frappe.xcall(M + 'get_feed', { name }).then(r => {
				this.feed = { name, notes: r.notes || [], activity: r.activity || [] };
				if (this.state.sel === name) this.render_drawer();
			}).catch(() => { this.feed = { name, notes: [], activity: [] }; });
		}

		set_notes(name, notes) {
			if (this.feed && this.feed.name === name) this.feed.notes = notes || [];
			else this.feed = { name, notes: notes || [], activity: null };
			if (this.state.sel === name) this.render_drawer();
		}

		open(name) {
			if (this.state.sel !== name) {
				this.feed = null;
				this.editor = null;
				this.bsearch = null;
				this.bresults = null;
			}
			this.set({ sel: name, tab: this.state.sel === name ? this.state.tab : 'overview' });
			this.load_feed(name);
		}

		close_drawer(silent) {
			this.$drawer.prop('hidden', true);
			if (!silent && this.state.sel) {
				this.editor = null;
				this.bsearch = null;
				this.set({ sel: null });
			}
		}

		// ---------- inline edits, buyer and notes ----------

		start_edit(key) {
			const d = this.find(this.state.sel);
			if (!d || !this.can_edit(d)) return;
			this.editor = { deal: d.name, key };
			this._focus_new = true;
			this.render_drawer();
		}

		cancel_edit() {
			this.editor = null;
			this.render_drawer();
		}

		commit_edit(el, deal) {
			if (el._sob_done) return;
			el._sob_done = true;
			const field = el.getAttribute('data-ed-field');
			if (this.editor && this.editor.deal === deal && this.editor.key === 'f:' + field) this.editor = null;
			const d = this.find(deal);
			if (!d || !field) { this.render_drawer(); return; }
			let v = (el.value || '').trim();
			if (NUM_FIELDS.includes(field)) {
				if (v === '') v = null;
				else {
					const n = Number(v);
					if (!isFinite(n) || n < 0) {
						frappe.show_alert({ message: __('Please enter a number of 0 or more.'), indicator: 'red' });
						this.render_drawer();
						return;
					}
					v = n;
				}
				if ((+d[field] || 0) === (+v || 0)) { this.render_drawer(); return; }
			} else if (v === (d[field] || '')) { this.render_drawer(); return; }
			this.render_drawer();
			this.apply(deal, { [field]: v === '' ? null : v }, __('Saved'));
		}

		search_buyers(txt) {
			txt = (txt || '').trim();
			this.bopen = true;
			if (this.bresults && this._bq === txt) { this.render_bresults(); return; }
			const seq = (this._bseq = (this._bseq || 0) + 1);
			frappe.xcall(M + 'search_buyers', { txt }).then(r => {
				if (seq !== this._bseq) return;
				this._bq = txt;
				this.bresults = r || [];
				this.bidx = -1;
				this.render_bresults();
			});
		}

		render_bresults() {
			const $l = this.$drawer.find('.sob-bsearch-list');
			if (!$l.length) return;
			const open = !!(this.bopen && this.bresults);
			this.$drawer.find('.sob-bsearch-input').attr('aria-expanded', open ? 'true' : 'false');
			if (!open) { $l.prop('hidden', true).empty(); return; }
			const rows = this.bresults.map((r, i) => `
				<button type="button" role="option" class="sob-bs-item${i === this.bidx ? ' on' : ''}" aria-selected="${i === this.bidx}" data-pick-type="${esc(r.type)}" data-pick="${esc(r.name)}" data-title="${esc(r.title)}">
					<span class="sob-badge ${r.type === 'Customer' ? 'cust' : 'lead'}">${esc(__(r.type))}</span>
					<span class="sob-bs-title">${esc(r.title)}</span>${r.title !== r.name ? `<span class="sob-muted">${esc(r.name)}</span>` : ''}</button>`).join('');
			const none = this.bresults.length ? '' : `<div class="sob-muted sob-bs-none">${__('No matching customers or leads.')}</div>`;
			const create = this.data.can_create_customer || this.data.can_create_lead
				? `<button type="button" role="option" class="sob-bs-item create${this.bidx === this.bresults.length ? ' on' : ''}" data-act="buyer-new">${svg(ICON.plus, 14)}${__('Create new buyer')}</button>` : '';
			$l.html(rows + none + create).prop('hidden', false);
		}

		pick_buyer($it) {
			const type = $it.attr('data-pick-type'), name = $it.attr('data-pick'), title = $it.attr('data-title');
			const d = this.find(this.state.sel);
			if (!name || !d) return;
			this.bsearch = null;
			this.bresults = null;
			this.bopen = false;
			this._bq = null;
			const same = type === 'Customer' ? d.customer === name : (d.lead === name && !d.customer);
			this.render_drawer();
			if (same) return;
			this.apply(d.name, type === 'Customer' ? { customer: name } : { lead: name, customer: null }, __('Buyer set to {0}', [title]));
		}

		create_buyer(name) {
			const d = this.find(name);
			if (!d) return;
			const types = [];
			if (this.data.can_create_lead) types.push('Lead');
			if (this.data.can_create_customer) types.push('Customer');
			if (!types.length) { frappe.msgprint(__('You do not have permission to create a Customer or a Lead.')); return; }
			this.bopen = false;
			this.render_bresults();
			const won = this.won_stage();
			const def_type = won && d.stage === won.name && types.includes('Customer') ? 'Customer' : types[0];
			const need = this.missing(d, {}).filter(k => k !== 'customer');
			const fields = [
				{ fieldname: 'buyer_name', fieldtype: 'Data', label: __('Buyer Name'), reqd: 1, default: d.account },
				{ fieldname: 'buyer_type', fieldtype: 'Select', label: __('Type'), reqd: 1, options: types.map(t => ({ value: t, label: __(t) })), default: def_type,
					description: __('Use Lead for a new prospect and Customer for an account that is ready to order.') },
				{ fieldtype: 'Section Break', label: __('Contact') },
				{ fieldname: 'contact_name', fieldtype: 'Data', label: __('Contact Name'), default: d.contact_name || '' },
				{ fieldname: 'phone', fieldtype: 'Data', label: __('Phone'), default: d.phone || '' },
				{ fieldname: 'email', fieldtype: 'Data', options: 'Email', label: __('Email'), default: d.email || '' },
			];
			if (need.length) {
				fields.push({ fieldtype: 'Section Break', label: __('This deal also needs') });
				if (need.includes('deal_owner')) {
					const choices = this.owner_choices(d);
					fields.push({ fieldname: 'deal_owner', fieldtype: 'Select', label: __('Owner'), reqd: 1,
						options: choices.map(o => ({ value: o.user, label: o.name })),
						default: choices.some(o => o.user === this.data.user) ? this.data.user : (choices[0] || {}).user });
				}
				if (need.includes('next_step_due')) fields.push({ fieldname: 'next_step_due', fieldtype: 'Date', label: __('Next Follow-up'), reqd: 1, default: frappe.datetime.add_days(this.data.today, 2) });
				if (need.includes('lost_reason')) fields.push({ fieldname: 'lost_reason', fieldtype: 'Small Text', label: __('Lost Reason'), reqd: 1 });
			}
			const dlg = new frappe.ui.Dialog({
				title: __('Add buyer for {0}', [d.account]),
				fields,
				primary_action_label: __('Create and link'),
				primary_action: v => {
					const extra = {};
					need.forEach(k => { if (v[k]) extra[k] = v[k]; });
					dlg.disable_primary_action();
					frappe.xcall(M + 'create_buyer', {
						name, buyer_type: v.buyer_type, buyer_name: v.buyer_name,
						contact_name: v.contact_name || '', phone: v.phone || '', email: v.email || '', extra,
					}).then(r => {
						dlg.hide();
						this.bsearch = null;
						this.bresults = null;
						frappe.show_alert({ message: __('{0} {1} created and linked to this deal', [__(r.type), r.title]), indicator: 'green' });
						this.load();
					}).catch(() => dlg.enable_primary_action());
				},
			});
			dlg.show();
		}

		save_note_section(f) {
			const d = this.find(this.state.sel);
			if (!d) return;
			const v = (this.$drawer.find(`[data-nsec-input="${f}"]`).val() || '').trim();
			this.editor = null;
			this.render_drawer();
			if (v === (d[f] || '').trim()) return;
			this.apply(d.name, { [f]: v || null }, __('Saved'));
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
			// show the new numbers right away; the reload brings the server's figures
			if (NUM_FIELDS.some(k => k in patch)) {
				['deal_value', 'weighted_value'].forEach(k => { prev[k] = d[k]; });
				d.deal_value = (+d.value_override || 0) || this.calc_value(d) || ((+d.total_grams || 0) * (+d.price_per_gram || 0));
				d.weighted_value = d.deal_value * (+d.probability || 0) / 100;
			}
			if ('customer' in patch) d.customer_title = null;
			if ('lead' in patch) d.lead_title = null;
			this.busy[name] = true;
			this.render();
			return frappe.xcall(M + 'update_deal', { name, values: patch })
				.then(() => frappe.show_alert({ message: done_msg || __('{0} updated', [d.account]), indicator: 'green' }))
				.catch(() => Object.assign(d, prev))
				.finally(() => { delete this.busy[name]; this.load(); });
		}

		work_copy(d) {
			this.work = this.work || {};
			this._k = this._k || 0;
			if (!this.work[d.name]) this.work[d.name] = (d.lines || []).map((l, i) => Object.assign({}, l, { key: l.name || 'v' + i }));
			return this.work[d.name];
		}

		drop_work(name) {
			const w = this.work && this.work[name];
			if (w && !w.some(l => l.draft) && !this.busy[name] && !(this.req_dirty || {})[name]) delete this.work[name];
		}

		// Send the requirement lines; edits made while a save is running are sent right after it.
		save_lines(name, msg) {
			const d = this.find(name);
			if (!d) return;
			this.req_dirty = this.req_dirty || {};
			if (this.busy[name]) { this.req_dirty[name] = msg || true; return; }
			const w = this.work_copy(d);
			const sent = w.filter(l => !l.draft && l.product_line);
			const payload = sent.map(l => ({ name: l.name || null, product_line: l.product_line, tier: l.tier || '', total_grams: +l.total_grams || 0, price_per_gram: +l.price_per_gram || 0, details: l.details || '' }));
			// show the new totals right away
			d.lines = sent.map(l => Object.assign({}, l));
			const prev = { deal_value: d.deal_value, weighted_value: d.weighted_value };
			d.deal_value = (+d.value_override || 0) || this.calc_value(d);
			d.weighted_value = d.deal_value * (+d.probability || 0) / 100;
			this.busy[name] = true;
			this.render();
			frappe.xcall(M + 'update_deal', { name, values: { requirements: payload } }).then(r => {
				const names = (r && r.requirements) || [];
				sent.forEach((l, i) => { if (names[i]) { l.name = names[i]; } });
				if (msg) frappe.show_alert({ message: msg, indicator: 'green' });
			}).catch(() => {
				Object.assign(d, prev);
				delete this.work[name];
			}).finally(() => {
				delete this.busy[name];
				const again = this.req_dirty[name];
				delete this.req_dirty[name];
				if (again && this.work[name]) { this.save_lines(name, again === true ? null : again); return; }
				this.drop_work(name);
				this.load();
			});
		}

		new_deal() {
			const me = this.data.user;
			const choices = this.owner_choices(null);
			const open_stages = this.stages_of(this.state.board).filter(x => !x.is_closed);
			const def_stage = this.first_stage_of(this.state.board);
			const lines = this.s.product_lines || [];
			const prio = this.s.lists.priority || [];
			let co = [];
			const tier_opts = line => [''].concat(this.tiers_for(line));
			const render_co = () => {
				const owner = dlg.get_value('deal_owner');
				co = co.filter(u => u !== owner);
				const people = (this.s.owners || []).filter(o => o.user !== owner);
				dlg.fields_dict.co_html.$wrapper.html(`
					<div class="sob-dlg-co">
						<label class="control-label" id="sob-new-co">${__('Co-owners')}</label>
						<div class="sob-pills" role="group" aria-labelledby="sob-new-co">${people.map(p => `<button type="button" class="sob-pill sob-co-chip${co.includes(p.user) ? ' on' : ''}" data-new-co="${esc(p.user)}" aria-pressed="${co.includes(p.user)}">${p.colour ? `<span class="sob-dot" style="background:${esc(p.colour)}"></span>` : ''}${esc(p.name)}</button>`).join('')}</div>
						<p class="help-box small text-muted">${__('Optional. Co-owners see and edit the deal like the owner.')}</p>
					</div>`);
			};
			const follow_needed = st => { const x = this.stage(st) || {}; return !!x.name && !x.is_closed && x.name !== this.s.first_stage; };
			const dlg = new frappe.ui.Dialog({
				title: this.state.board === 'lead' ? __('New Lead') : __('New Deal'),
				fields: [
					{ fieldname: 'account', fieldtype: 'Data', label: __('Account'), description: __('Required unless you choose a Buyer.') },
					{ fieldname: 'customer', fieldtype: 'Link', options: 'Customer', label: __('Buyer'),
						description: __('Optional. Choose an existing Customer to fill in the account and contact details.'),
						onchange: () => {
							const v = dlg.get_value('customer');
							if (!v || dlg.get_value('account')) return;
							frappe.db.get_value('Customer', v, 'customer_name').then(r => {
								const n = r && r.message && r.message.customer_name;
								if (n && !dlg.get_value('account') && dlg.get_value('customer') === v) dlg.set_value('account', n);
							});
						} },
					{ fieldname: 'stage', fieldtype: 'Select', label: this.state.board === 'lead' ? __('Lead status') : __('Stage'), reqd: 1, options: open_stages.map(x => ({ value: x.name, label: __(x.name) })), default: def_stage,
						onchange: () => dlg.set_df_property('next_step_due', 'reqd', follow_needed(dlg.get_value('stage')) ? 1 : 0) },
					{ fieldname: 'deal_owner', fieldtype: 'Select', label: __('Owner'), reqd: 1, options: choices.map(o => ({ value: o.user, label: o.name })),
						default: choices.some(o => o.user === me) ? me : (choices[0] || {}).user, onchange: () => render_co() },
					{ fieldname: 'co_html', fieldtype: 'HTML' },
					{ fieldname: 'priority', fieldtype: 'Select', label: __('Priority'), options: prio, default: prio[Math.floor(prio.length / 2)] || '' },
					{ fieldname: 'next_step_due', fieldtype: 'Date', label: __('Next Follow-up'), reqd: follow_needed(def_stage) ? 1 : 0 },
					{ fieldtype: 'Section Break', label: __('Product') },
					{ fieldname: 'product_line', fieldtype: 'Select', label: __('Product Line'), options: [''].concat(lines), default: this.state.prods.length === 1 ? this.state.prods[0] : '',
						onchange: () => {
							const t = tier_opts(dlg.get_value('product_line'));
							dlg.set_df_property('tier', 'options', t);
							dlg.set_df_property('tier', 'read_only', t.length > 1 ? 0 : 1);
							if (!t.includes(dlg.get_value('tier'))) dlg.set_value('tier', '');
						} },
					{ fieldname: 'tier', fieldtype: 'Select', label: __('Tier'), options: tier_opts(this.state.prods.length === 1 ? this.state.prods[0] : ''), read_only: tier_opts(this.state.prods.length === 1 ? this.state.prods[0] : '').length > 1 ? 0 : 1 },
					{ fieldtype: 'Column Break' },
					{ fieldname: 'total_grams', fieldtype: 'Float', label: __('Total Grams') },
					{ fieldname: 'price_per_gram', fieldtype: 'Currency', label: __('Price per Gram') },
					{ fieldname: 'value_override', fieldtype: 'Currency', label: __('Deal Value (manual)'), description: __('Optional. Leave empty to use grams × price.') },
					{ fieldtype: 'Section Break' },
					{ fieldname: 'more_html', fieldtype: 'HTML', options: `<p class="help-box small text-muted">${__('Need more than one product? Add more requirements in the deal after it is created.')}</p>` },
				],
				primary_action_label: __('Create deal'),
				primary_action: v => {
					if (!(v.account || '').trim() && !v.customer) { frappe.msgprint(__('Please enter the Account or choose a Buyer.')); return; }
					if (follow_needed(v.stage) && !v.next_step_due) { frappe.msgprint(__('Please set a Next Follow-up date. It is required for deals in {0}.', [__(v.stage)])); return; }
					const values = {};
					['account', 'customer', 'stage', 'deal_owner', 'priority', 'next_step_due', 'product_line', 'tier', 'total_grams', 'price_per_gram', 'value_override']
						.forEach(k => { if (v[k] !== undefined && v[k] !== null && v[k] !== '' && !(NUM_FIELDS.includes(k) && !+v[k])) values[k] = v[k]; });
					if (co.length) values.co_owners = co.slice();
					dlg.disable_primary_action();
					frappe.xcall(M + 'create_deal', { values }).then(name => {
						dlg.hide();
						frappe.show_alert({ message: __('Deal {0} created', [values.account || values.customer]), indicator: 'green' });
						this.load().then(() => this.open(name));
					}).catch(() => dlg.enable_primary_action());
				},
				secondary_action_label: __('Open full form'),
				secondary_action: () => {
					const v = dlg.get_values(true) || {};
					dlg.hide();
					const opts = {};
					['account', 'customer', 'stage', 'deal_owner', 'priority', 'next_step_due', 'product_line', 'tier', 'total_grams', 'price_per_gram'].forEach(k => { if (v[k]) opts[k] = v[k]; });
					frappe.new_doc(DT, opts);
				},
			});
			dlg.$wrapper.on('click', '[data-new-co]', e => {
				const u = $(e.currentTarget).attr('data-new-co');
				co = co.includes(u) ? co.filter(x => x !== u) : co.concat([u]);
				render_co();
			});
			render_co();
			dlg.show();
			this._new_dlg = dlg;
		}

		email_to(d) { return (d && (d.email || d.customer_email)) || ''; }

		email_button(d) {
			const to = this.email_to(d);
			if (to) return `<button type="button" class="sob-btn" data-act="email" title="${esc(__('Email {0}', [to]))}">${__('Email')}</button>`;
			const tip = __("Add the buyer's email in the Buyer tab first.");
			return `<span class="sob-tip" tabindex="0" title="${esc(tip)}" aria-label="${esc(tip)}"><button type="button" class="sob-btn" disabled aria-disabled="true">${__('Email')}</button></span>`;
		}

		// Standard composer on the deal: the sent email is a Communication linked to the deal (timeline + Activity).
		email_deal(name) {
			const d = this.find(name);
			const to = this.email_to(d);
			if (!d || !to) return;
			if (!frappe.views.CommunicationComposer) { frappe.msgprint(__('The email composer could not be loaded. Please refresh the page.')); return; }
			const files = frappe.db.get_list('File', {
				filters: { attached_to_doctype: DT, attached_to_name: name }, fields: ['name', 'file_name', 'file_url', 'is_private'], limit: 50,
			}).catch(() => []);
			Promise.all([frappe.model.with_doc(DT, name), files]).then(([doc, attachments]) => {
				const Base = frappe.views.CommunicationComposer;
				class DealComposer extends Base {
					// new attachments go onto the deal, like they do from the form
					setup_attach() {
						super.setup_attach();
						$(this.dialog.fields_dict.select_attachments.wrapper).find('.add-more-attachments button').off('click').on('click', () => new frappe.ui.FileUploader({
							doctype: DT, docname: name, folder: 'Home/Attachments',
							on_success: a => { this.attachments.push(a); this.render_attachment_rows(a); },
						}));
					}
				}
				new DealComposer({
					doc: doc || frappe.get_doc(DT, name),
					recipients: to,
					subject: `Motley Terpz – ${d.account}`,
					attachments: (attachments || []).slice(),
					success: () => {
						frappe.show_alert({ message: __('Email sent to {0}', [to]), indicator: 'green' });
						this.load_feed(name);
					},
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
			$r.on('click', '[data-board]', e => this.set({ board: $(e.currentTarget).attr('data-board') }));
			$r.on('click', '[data-quick-note]', e => {
				e.preventDefault();
				e.stopPropagation();
				this.quick_note_dialog($(e.currentTarget).attr('data-quick-note'));
			});
			$r.on('mousedown dragstart', '[data-quick-note]', e => e.stopPropagation());
			$r.on('click', '[data-owner]', e => {
				const v = $(e.currentTarget).attr('data-owner');
				let owners = (this.state.owners || []).slice();
				if (!v) owners = [];
				else owners = owners.includes(v) ? owners.filter(x => x !== v) : owners.concat([v]);
				this.set({ owners });
			});
			// Product Line multi-select
			const prod_menu = open => {
				$r.find('.sob-ms-menu').prop('hidden', !open);
				$r.find('.sob-ms-btn').attr('aria-expanded', open ? 'true' : 'false');
			};
			$r.on('click', '[data-act="prod-menu"]', () => prod_menu($r.find('.sob-ms-menu').prop('hidden')));
			$r.on('change', '[data-prod]', e => {
				const v = $(e.currentTarget).attr('data-prod');
				let prods = this.state.prods.slice();
				if (!v) prods = [];
				else prods = prods.includes(v) ? prods.filter(x => x !== v) : prods.concat([v]);
				// keep Settings order so the label and URL read the same every time
				prods = (this.s.product_lines || []).filter(p => prods.includes(p));
				this.set({ prods });
			});
			$(document).on('click.sob', e => {
				if (!$(e.target).closest('.sob-ms').length) prod_menu(false);
			});
			$r.on('keydown', '.sob-ms', e => {
				if (e.key === 'Escape') { e.stopPropagation(); prod_menu(false); $r.find('.sob-ms-btn').trigger('focus'); }
			});
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
				if (e.target !== e.currentTarget && $(e.target).closest('button').length) return;
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
				this.drag = { name: $(e.currentTarget).attr('data-card'), kind: 'card', from: $(e.currentTarget).attr('data-from-owner') || null };
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
					if (drag.from && drag.from === owner) return;  // dropped back in its own column
					this.apply(drag.name, { deal_owner: owner }, __('Reassigned to {0}', [this.owner_name(owner)]));
				} else if (drag.kind === 'event' && el.hasAttribute('data-drop-date')) this.apply(drag.name, { [drag.field]: el.getAttribute('data-drop-date') });
			});

			// drawer
			$d.on('click', '[data-act="close"]', () => this.close_drawer());
			$d.on('click', '[data-tab]', e => {
				const tab = $(e.currentTarget).attr('data-tab');
				if (this.editor && this.editor.key[0] !== 'f') this.editor = null;
				this.bopen = false;
				this.set({ tab });
				if ((tab === 'activity' || tab === 'notes') && this.state.sel) this.load_feed(this.state.sel);
			});
			$d.on('click', '[data-move]', e => this.apply(this.state.sel, { stage: $(e.currentTarget).attr('data-move') }));
			$d.on('change', '[data-panel-field]', e => this.apply(this.state.sel, { [$(e.currentTarget).attr('data-panel-field')]: e.currentTarget.value || null }));
			$d.on('click', '[data-act="form"]', () => frappe.set_route('Form', DT, this.state.sel));
			$d.on('click', '[data-act="email"]', () => this.email_deal(this.state.sel));
			// quick notes
			$d.on('click', '[data-qnote]', e => this.add_quick_note(this.state.sel, $(e.currentTarget).attr('data-qnote'), e.currentTarget));
			// manual deal value
			$d.on('click', '[data-act="value-reset"]', () => this.apply(this.state.sel, { value_override: 0 }, __('Deal value now follows the requirements')));
			// requirement lines
			$d.on('click', '[data-act="req-add"]', () => {
				const d = this.find(this.state.sel);
				if (!d || !this.can_edit(d)) return;
				const w = this.work_copy(d);
				w.push({ key: 'n' + (++this._k), product_line: '', tier: '', total_grams: '', price_per_gram: '', details: '', draft: true });
				this.render_drawer();
				const el = this.$drawer.find(`[data-req="n${this._k}"] [data-req-field="product_line"]`).get(0);
				if (el) el.focus();
			});
			$d.on('click', '[data-req-remove]', e => {
				const d = this.find(this.state.sel);
				if (!d) return;
				const key = $(e.currentTarget).attr('data-req-remove');
				const w = this.work_copy(d);
				const row = w.find(x => x.key === key);
				if (!row) return;
				w.splice(w.indexOf(row), 1);
				if (row.draft) { this.render_drawer(); this.drop_work(d.name); return; }
				this.save_lines(d.name, __('Requirement removed'));
			});
			$d.on('change', '[data-req-field]', e => {
				const d = this.find(this.state.sel);
				if (!d || !this.can_edit(d)) return;
				const el = e.currentTarget;
				const key = $(el).closest('[data-req]').attr('data-req');
				const f = el.getAttribute('data-req-field');
				const row = this.work_copy(d).find(x => x.key === key);
				if (!row) return;
				let v = el.value;
				if (f === 'total_grams' || f === 'price_per_gram') {
					v = v === '' ? 0 : Number(v);
					if (!isFinite(v) || v < 0) { frappe.show_alert({ message: __('Please enter a number of 0 or more.'), indicator: 'red' }); el.value = row[f] || ''; return; }
				}
				row[f] = v;
				if (f === 'product_line' && row.tier && !this.tiers_for(v).includes(row.tier)) row.tier = '';
				if (row.draft && !row.product_line) { this.render_drawer(); return; }
				row.draft = false;
				this.save_lines(d.name, f === 'product_line' || f === 'tier' ? __('Requirement updated') : __('Saved'));
			});
			$d.on('click', '[data-co]', e => {
				const d = this.find(this.state.sel);
				if (!d || !this.can_edit_owners(d)) return;
				const u = $(e.currentTarget).attr('data-co');
				const co = this.co_list(d);
				const next = co.includes(u) ? co.filter(x => x !== u) : co.concat([u]);
				this.apply(d.name, { co_owners: next }, co.includes(u) ? __('{0} removed as a co-owner', [this.owner_name(u)]) : __('{0} added as a co-owner', [this.owner_name(u)]));
			});
			$d.on('click', '[data-act="quote"]', () => this.create_quotation(this.state.sel));
			$d.on('click', '[data-act="won"]', () => this.apply(this.state.sel, { stage: this.won_stage().name }, __('Marked as won')));
			$d.on('click', '[data-act="lost"]', () => this.apply(this.state.sel, { stage: this.lost_stage().name }, __('Marked as lost')));

			// Product Line / Tier
			$d.on('change', '[data-prod-field]', e => {
				const d = this.find(this.state.sel);
				if (!d) return;
				const f = $(e.currentTarget).attr('data-prod-field');
				const v = e.currentTarget.value || null;
				const patch = { [f]: v };
				if (f === 'product_line' && d.tier && !this.tiers_for(v).includes(d.tier)) patch.tier = null;
				this.apply(d.name, patch, f === 'tier' ? __('Tier updated') : __('Product line updated'));
			});

			// click-to-edit fields (Buyer, Overview tiles, Requirements)
			$d.on('click', '[data-ed]', e => {
				if ($(e.target).closest('a').length) return;
				this.start_edit('f:' + $(e.currentTarget).attr('data-ed'));
			});
			$d.on('keydown', '[data-ed]', e => {
				if (e.target !== e.currentTarget || (e.key !== 'Enter' && e.key !== ' ')) return;
				e.preventDefault();
				this.start_edit('f:' + $(e.currentTarget).attr('data-ed'));
			});
			$d.on('keydown', '.sob-ed-input', e => {
				const el = e.currentTarget;
				if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); el._sob_done = true; this.cancel_edit(); return; }
				if (e.key === 'Enter' && !(el.tagName === 'TEXTAREA' && e.shiftKey)) { e.preventDefault(); this.commit_edit(el, this.state.sel); }
			});
			// Leaving the field saves. With a mouse or finger, wait until the click lands so it is not lost to the re-render.
			$(document).on('mousedown.sob touchstart.sob', () => { this._ptr = true; });
			$(document).on('mouseup.sob touchend.sob touchcancel.sob', () => {
				this._ptr = false;
				const f = this._after_ptr;
				this._after_ptr = null;
				if (f) setTimeout(f, 0);
			});
			$d.on('focusout', '.sob-ed-input', e => {
				if (this._rendering) return;
				const el = e.currentTarget, deal = this.state.sel;
				if (this._ptr) this._after_ptr = () => this.commit_edit(el, deal);
				else this.commit_edit(el, deal);
			});
			$d.on('click', '[data-act="ed-cancel"]', () => this.cancel_edit());

			// buyer search and create
			$d.on('click', '[data-act="buyer-change"]', () => { this.bsearch = this.state.sel; this._focus_new = true; this.render_drawer(); });
			$d.on('click', '[data-act="buyer-cancel"]', () => { this.bsearch = null; this.bresults = null; this.bopen = false; this.render_drawer(); });
			$d.on('click', '[data-act="buyer-new"]', () => this.create_buyer(this.state.sel));
			$d.on('input', '.sob-bsearch-input', frappe.utils.debounce(e => this.search_buyers(e.target.value), 250));
			$d.on('focusin', '.sob-bsearch-input', e => { if (!this._rendering) this.search_buyers(e.target.value); });
			$d.on('focusout', '.sob-bsearch-input', () => {
				if (this._rendering) return;
				setTimeout(() => {
					if (document.activeElement && $(document.activeElement).hasClass('sob-bsearch-input')) return;
					this.bopen = false;
					this.render_bresults();
				}, 150);
			});
			$d.on('mousedown', '.sob-bs-item', e => e.preventDefault());
			$d.on('click', '.sob-bs-item[data-pick]', e => this.pick_buyer($(e.currentTarget)));
			$d.on('keydown', '.sob-bsearch-input', e => {
				const list = this.bresults || [];
				const n = list.length + (this.data.can_create_customer || this.data.can_create_lead ? 1 : 0);
				if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && n) {
					e.preventDefault();
					const i = this.bidx == null ? -1 : this.bidx;
					this.bidx = e.key === 'ArrowDown' ? (i + 1) % n : (i <= 0 ? n - 1 : i - 1);
					this.bopen = true;
					this.render_bresults();
				} else if (e.key === 'Enter') {
					e.preventDefault();
					if (this.bidx == null || this.bidx < 0) return;
					if (this.bidx < list.length) this.pick_buyer(this.$drawer.find('.sob-bs-item[data-pick]').eq(this.bidx));
					else this.create_buyer(this.state.sel);
				} else if (e.key === 'Escape') {
					e.preventDefault();
					e.stopPropagation();
					const d = this.find(this.state.sel);
					if (this.bopen) { this.bopen = false; this.render_bresults(); } else if (d && (d.customer || d.lead)) { this.bsearch = null; this.render_drawer(); }
				}
			});

			// notes
			$d.on('click', '[data-act="note"]', e => {
				const name = this.state.sel;
				const $t = $d.find('[data-keep="note-new"]');
				const note = ($t.val() || '').trim();
				if (!note) { $t.trigger('focus'); return; }
				const $b = $(e.currentTarget).prop('disabled', true);
				frappe.xcall(M + 'add_note', { name, note }).then(notes => {
					$d.find('[data-keep="note-new"]').val('');
					this.set_notes(name, notes);
					frappe.show_alert({ message: __('Note saved'), indicator: 'green' });
				}).finally(() => $b.prop('disabled', false));
			});
			$d.on('keydown', '[data-keep="note-new"]', e => {
				if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $d.find('[data-act="note"]').trigger('click'); }
			});
			$d.on('click', '[data-note-edit]', e => this.start_edit('c:' + $(e.currentTarget).attr('data-note-edit')));
			$d.on('click', '[data-note-save]', e => {
				const id = $(e.currentTarget).attr('data-note-save');
				const name = this.state.sel;
				const note = ($d.find(`[data-note-input="${CSS.escape(id)}"]`).val() || '').trim();
				if (!note) { frappe.msgprint(__('A note cannot be empty. Use Delete to remove it.')); return; }
				frappe.xcall(M + 'edit_note', { comment: id, note }).then(notes => {
					this.editor = null;
					this.set_notes(name, notes);
					frappe.show_alert({ message: __('Note updated'), indicator: 'green' });
				});
			});
			$d.on('click', '[data-note-del]', e => {
				const id = $(e.currentTarget).attr('data-note-del');
				const name = this.state.sel;
				frappe.confirm(__('Delete this note? This cannot be undone.'), () => {
					frappe.xcall(M + 'delete_note', { comment: id }).then(notes => {
						this.set_notes(name, notes);
						frappe.show_alert({ message: __('Note deleted'), indicator: 'green' });
					});
				});
			});
			$d.on('click', '[data-nsec-edit]', e => this.start_edit('n:' + $(e.currentTarget).attr('data-nsec-edit')));
			$d.on('click', '[data-nsec-save]', e => this.save_note_section($(e.currentTarget).attr('data-nsec-save')));
			$d.on('keydown', '[data-nsec-input], [data-note-input]', e => {
				if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); this.cancel_edit(); }
				else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
					e.preventDefault();
					$(e.currentTarget).closest('section, article').find('[data-nsec-save], [data-note-save]').first().trigger('click');
				}
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
