(() => {
	const PAGE = 'matts-lab-dashboard';
	const METHOD = 'cannabis_management.cannabis_management.page.matts_lab_dashboard.matts_lab_dashboard.';
	const STORE_KEY = 'mld_state_v1';
	const TIERS = ['T1+', 'T1', 'T2', 'T3', 'T4', 'Ungraded'];
	const LOCATIONS = ['MTM', 'Nature'];
	const VIEWS = [
		{ value: 'week_month', label: __('Week vs month') },
		{ value: 'weeks', label: __('Weekly trend') },
		{ value: 'months', label: __('Monthly trend') },
		{ value: 'custom', label: __('Custom range') },
	];
	const BAND_LABELS = { week: __('Weekly'), month: __('Monthly'), range: __('Custom range') };
	const KPIS = [
		{ id: 'wash:lbs:total', label: __('Pounds washed'), unit: 'lbs', by: 'location' },
		{ id: 'mfg:kg:total', label: __('Kilos produced'), unit: 'kg' },
		{ id: 'yield:bh', label: __('Bubble hash yield'), unit: '%' },
		{ id: 'sales:rosin_amt', label: __('Rosin revenue'), unit: '$', by: 'tier' },
	];
	const WHERE = [
		{ value: 'main', label: __('Main Storage') },
		{ value: 'partner', label: __('Tolling partners') },
		{ value: 'other', label: __('Other warehouses') },
		{ value: 'all', label: __('Everywhere') },
	];
	const ICON = {
		chevron: '<svg class="osc-ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
		left: '<svg class="osc-ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5 5.5 8 10 12.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
		right: '<svg class="osc-ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
		info: '<svg class="osc-ico" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M8 7.25v3.75" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="5" r=".9" fill="currentColor"/></svg>',
	};
	const DEFAULT_FILTERS = {
		company: '', view: 'week_month', as_of: '', from_date: '', to_date: '', location: '', tier: '', customer: '',
	};
	const G_PER_LB = 453.59237;
	const esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));

	function readStore() {
		try {
			return JSON.parse(localStorage.getItem(STORE_KEY) || '{}') || {};
		} catch (e) {
			return {};
		}
	}

	function writeStore(state) {
		const { company, view, from_date, to_date, location, tier, customer } = state.filters;
		try {
			localStorage.setItem(STORE_KEY, JSON.stringify({
				filters: { company, view, from_date, to_date, location, tier, customer },
				open: state.open,
				closed: state.closed,
				live_tab: state.live.tab,
				live_where: state.live.where,
				live_zeros: state.live.zeros,
			}));
		} catch (e) {
			/* storage unavailable */
		}
	}

	function num(v, digits) {
		return Number(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
	}

	function formatValue(v, unit) {
		if (v == null || Math.abs(v) < 0.005) return null;
		switch (unit) {
			case '$': return (v < 0 ? '-$' : '$') + num(Math.abs(v), 0);
			case '$/g': return (v < 0 ? '-$' : '$') + num(Math.abs(v), 2);
			case '%': return num(v, 2) + '%';
			case 'lbs':
			case 'kg': return num(v, 1);
			default: return num(v, 0);
		}
	}

	function rangeText(start, end) {
		const s = moment(start), e = moment(end);
		if (!s.isSame(e, 'year')) return `${s.format('MMM D, YYYY')} – ${e.format('MMM D, YYYY')}`;
		if (s.isSame(e, 'month')) return `${s.format('MMM D')} – ${e.format('D')}`;
		return `${s.format('MMM D')} – ${e.format('MMM D')}`;
	}

	function periodHead(p, today, trend) {
		const t = moment(today), s = moment(p.start);
		const toDate = p.partial ? ` · ${__('to date')}` : '';
		if (p.band === 'week') {
			const diff = s.diff(t.clone().startOf('isoWeek'), 'weeks');
			const rel = { 0: __('This week'), '-1': __('Last week'), 1: __('Next week') }[diff];
			if (trend) return { title: rangeText(p.start, p.end), range: (rel || __('Week {0}', [s.isoWeek()])) + toDate };
			return { title: rel || __('Week of {0}', [s.format('MMM D')]), range: rangeText(p.start, p.end) + toDate };
		}
		if (p.band === 'month') {
			const diff = s.diff(t.clone().startOf('month'), 'months');
			const rel = { 0: __('This month'), '-1': __('Last month') }[diff];
			if (trend) return { title: s.format('MMM YYYY'), range: (rel || rangeText(p.start, p.end)) + toDate };
			return { title: rel || s.format('MMMM YYYY'), range: (rel ? s.format('MMMM YYYY') : rangeText(p.start, p.end)) + toDate };
		}
		return {
			title: p.key === 'range' ? __('Selected range') : __('Previous range'),
			range: rangeText(p.start, p.end) + toDate,
		};
	}

	function walkRows(sections, cb) {
		const walk = (rows, section, path) => {
			let group = null;
			rows.forEach((r) => {
				if (r.sub) group = r.label;
				const base = group && !r.sub ? path.concat(group) : path;
				r._path = base;
				cb(r, section);
				walk(r.children || [], section, base.concat(r.label));
			});
		};
		(sections || []).forEach((s) => walk(s.rows, s, []));
	}

	frappe.pages[PAGE].on_page_load = function (wrapper) {
		const page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Matt's Lab Dashboard"),
			single_column: true,
		});
		const today = frappe.datetime.get_today();
		const saved = readStore();
		const state = {
			filters: { ...DEFAULT_FILTERS, ...(saved.filters || {}), as_of: today },
			open: saved.open || {},
			closed: saved.closed || {},
			data: null,
			req: 0,
			syncing: 0,
			stock: { data: null, req: 0, key: null, loadedAt: null },
			live: {
				tab: saved.live_tab || 'T1',
				where: WHERE.some((w) => w.value === saved.live_where) ? saved.live_where : 'main',
				zeros: !!saved.live_zeros,
				search: '',
				sort: { key: 'on_hand', dir: -1 },
			},
		};
		if (!VIEWS.some((v) => v.value === state.filters.view)) state.filters.view = 'week_month';
		if (state.filters.location && !LOCATIONS.includes(state.filters.location)) state.filters.location = '';
		if (state.filters.tier && !TIERS.includes(state.filters.tier)) state.filters.tier = '';

		page.set_secondary_action(__('Export CSV'), () => exportCsv());
		page.add_action_icon('refresh', () => { load(); loadStock(); }, '', __('Refresh'));
		page.add_inner_button(__('Live inventory'), () => showLive());

		const $root = $(`
			<div class="osc">
				<section class="osc-filters" aria-label="${__('Filters')}">
					<div class="osc-filters-head">
						<span class="osc-filters-title">${__('Filters')}</span>
						<button type="button" class="btn btn-default btn-xs osc-reset">${__('Reset')}</button>
					</div>
					<div class="osc-filters-grid"></div>
				</section>
				<section class="osc-kpis" aria-label="${__('Headline numbers')}"></section>
				<section class="osc-card osc-stock" aria-label="${__('Stock right now')}">
					<header class="osc-card-head">
						<div class="osc-live-headtext">
							<div class="osc-nav-title">${__('Stock right now')}</div>
							<div class="osc-nav-sub osc-stock-sub">${__('Loading…')}</div>
						</div>
						<div class="osc-card-tools">
							<button type="button" class="btn btn-default btn-xs osc-stock-refresh">${__('Refresh')}</button>
						</div>
					</header>
					<div class="osc-stock-wrap"><div class="osc-empty-state">${__('Loading…')}</div></div>
				</section>
				<section class="osc-card osc-period">
					<header class="osc-card-head">
						<div class="osc-nav">
							<button type="button" class="osc-iconbtn osc-prev" aria-label="${__('Previous')}" title="${__('Previous')}">${ICON.left}</button>
							<div class="osc-nav-text">
								<div class="osc-nav-title"></div>
								<div class="osc-nav-sub"></div>
							</div>
							<button type="button" class="osc-iconbtn osc-next" aria-label="${__('Next')}" title="${__('Next')}">${ICON.right}</button>
							<button type="button" class="btn btn-default btn-xs osc-today">${__('Today')}</button>
						</div>
						<div class="osc-card-tools">
							<span class="osc-status" aria-live="polite"></span>
							<button type="button" class="btn btn-default btn-xs osc-expand">${__('Expand all')}</button>
							<button type="button" class="btn btn-default btn-xs osc-collapse">${__('Collapse all')}</button>
						</div>
					</header>
					<div class="osc-table-wrap"><div class="osc-empty-state">${__('Loading…')}</div></div>
				</section>
				<section class="osc-card osc-live" aria-label="${__('Live inventory by SKU')}">
					<header class="osc-card-head">
						<div class="osc-live-headtext">
							<div class="osc-nav-title">${__('Live inventory by SKU')}</div>
							<div class="osc-nav-sub osc-live-sub">${__('Loading…')}</div>
						</div>
						<div class="osc-card-tools osc-live-tools">
							<input type="search" class="form-control input-xs osc-live-search" placeholder="${__('Search SKU, strain or warehouse')}" aria-label="${__('Search SKUs')}">
							<select class="form-control input-xs osc-live-where" aria-label="${__('Where')}">
								${WHERE.map((w) => `<option value="${w.value}">${esc(w.label)}</option>`).join('')}
							</select>
							<label class="osc-live-zero"><input type="checkbox" class="osc-live-zeros"> ${__('Show zero stock')}</label>
							<button type="button" class="btn btn-default btn-xs osc-live-csv">${__('Export')}</button>
						</div>
					</header>
					<div class="osc-live-tabs" role="tablist" aria-label="${__('Product')}"></div>
					<div class="osc-live-summary"></div>
					<div class="osc-live-scroll"><div class="osc-empty-state">${__('Loading…')}</div></div>
				</section>
				<details class="osc-notes">
					<summary>${__('How these numbers are worked out')}</summary>
					<ul>
						<li>${__('Click any number, or a headline card, to see the entries, invoices or items behind it. Weeks run Monday to Sunday.')}</li>
						<li><b>${__('Rosin stock')}</b>: ${__('stock on hand right now of every rosin tier in Main Storage. T1 includes the old "Primes" grade and T2 the old "Subprimes" grade. Ungraded is raw rosin not graded yet plus Full Spec. T4 fills in once a "Tier 4" item group exists.')}</li>
						<li><b>${__('Pending batches')}</b>: ${__('stock in warehouses typed Tolling Partner, plus the quantity still open on submitted material requests that are not completed (quantity less ordered quantity). Change a warehouse\'s type on the Warehouse record to move it in or out.')}</li>
						<li><b>${__('Pounds washed')}</b>: ${__('MTM is the pounds on the material request behind every completed washing job card (Hash Processing), dated when the job card finished, each request counted once. Nature washes under tolling without job cards, so its pounds come from its tolling stock entries.')}</li>
						<li><b>${__('Kilos produced')}</b>: ${__('finished items of submitted Manufacture stock entries: bubble hash from washing and raw rosin from pressing.')}</li>
						<li><b>${__('Yield')}</b>: ${__('bubble hash out ÷ fresh frozen in, and raw rosin out ÷ bubble hash pressed, from Manufacture entries over each period.')}</li>
						<li><b>${__('Sales')}</b>: ${__('submitted sales invoices to outside customers by invoice date, net of returns; sales between our own companies are left out. Oil price is LLR revenue ÷ LLR grams.')}</li>
						<li><b>${__('Back stock')}</b>: ${__('kilos right now in Main Storage for rosin (by tier), VRR, LLR and food grade. Distillate and consumables are also Main Storage only. Other warehouses can be seen in the live inventory list with the Where switch.')}</li>
						<li><b>${__('Samples')}</b>: ${__('stock in warehouses of type Samples, one per partner (for example "Samples - Leef - MT").')}</li>
					</ul>
				</details>
			</div>
		`).appendTo(page.main);

		const $grid = $root.find('.osc-filters-grid');
		const $kpis = $root.find('.osc-kpis');
		const $wrap = $root.find('.osc-table-wrap');
		const $status = $root.find('.osc-status');
		const $stock = $root.find('.osc-stock');
		const $stockWrap = $root.find('.osc-stock-wrap');
		const $live = $root.find('.osc-live');
		const $liveTabs = $live.find('.osc-live-tabs');
		const $liveScroll = $live.find('.osc-live-scroll');
		$live.find('.osc-live-zeros').prop('checked', state.live.zeros);
		$live.find('.osc-live-where').val(state.live.where);

		const ctl = {};
		const makeControl = (df) => {
			const $slot = $(`<div class="osc-filter" data-field="${df.fieldname}"></div>`).appendTo($grid);
			const control = frappe.ui.form.make_control({
				df: { ...df, change: () => onControlChange() },
				parent: $slot,
				render_input: true,
			});
			control.refresh();
			return control;
		};
		ctl.company = makeControl({ fieldname: 'company', label: __('Company'), fieldtype: 'Link', options: 'Company', placeholder: __('All companies') });
		ctl.view = makeControl({ fieldname: 'view', label: __('View'), fieldtype: 'Select', options: VIEWS });
		ctl.as_of = makeControl({ fieldname: 'as_of', label: __('Week of'), fieldtype: 'Date' });
		ctl.from_date = makeControl({ fieldname: 'from_date', label: __('From'), fieldtype: 'Date' });
		ctl.to_date = makeControl({ fieldname: 'to_date', label: __('To'), fieldtype: 'Date' });
		ctl.location = makeControl({
			fieldname: 'location', label: __('Washed by'), fieldtype: 'Select',
			options: [{ value: '', label: __('MTM and Nature') }, ...LOCATIONS.map((l) => ({ value: l, label: l }))],
		});
		ctl.tier = makeControl({
			fieldname: 'tier', label: __('Rosin tier'), fieldtype: 'Select',
			options: [{ value: '', label: __('All tiers') }, ...TIERS.map((t) => ({ value: t, label: t }))],
		});
		ctl.customer = makeControl({ fieldname: 'customer', label: __('Customer'), fieldtype: 'Link', options: 'Customer', placeholder: __('All customers') });
		const $reset = $root.find('.osc-filters-head');

		function readControls() {
			const out = {};
			Object.keys(DEFAULT_FILTERS).forEach((k) => { out[k] = ctl[k].get_value() || ''; });
			return out;
		}

		function syncControls() {
			state.syncing += 1;
			const f = state.filters;
			const jobs = Object.keys(DEFAULT_FILTERS).map((k) => {
				const current = ctl[k].get_value() || '';
				return current === (f[k] || '') ? null : ctl[k].set_value(f[k] || '');
			});
			layoutFilters();
			return Promise.all(jobs).finally(() => { state.syncing -= 1; });
		}

		function layoutFilters() {
			const f = state.filters;
			const custom = f.view === 'custom';
			ctl.as_of.$wrapper.closest('.osc-filter').toggle(!custom);
			ctl.from_date.$wrapper.closest('.osc-filter').toggle(custom);
			ctl.to_date.$wrapper.closest('.osc-filter').toggle(custom);
			ctl.as_of.set_label(f.view === 'months' ? __('Month of') : __('Week of'));
			const active = ['company', 'location', 'tier', 'customer'].filter((k) => f[k]).length;
			$reset.find('.osc-reset').prop('disabled', !active && f.view === 'week_month' && f.as_of === today)
				.text(active ? __('Reset ({0})', [active]) : __('Reset'));
			$root.find('.osc-today').text(f.view === 'months' ? __('This month') : f.view === 'custom' ? __('Today') : __('This week'));
		}

		function onControlChange() {
			if (state.syncing) return;
			const next = readControls();
			const prev = state.filters;
			if (next.view === 'custom' && prev.view !== 'custom' && !(next.from_date && next.to_date)) {
				next.from_date = moment(next.as_of || today).startOf('month').format('YYYY-MM-DD');
				next.to_date = next.as_of || today;
			}
			if (!next.as_of) next.as_of = today;
			if (JSON.stringify(next) === JSON.stringify(prev)) return;
			if (next.tier && next.tier !== prev.tier) state.live.tab = next.tier;
			state.filters = next;
			writeStore(state);
			syncControls();
			load();
		}

		$reset.on('click', '.osc-reset', () => {
			state.filters = { ...DEFAULT_FILTERS, as_of: today };
			writeStore(state);
			syncControls();
			load();
		});

		function step(dir) {
			const f = { ...state.filters };
			if (f.view === 'custom' && f.from_date && f.to_date) {
				const span = moment(f.to_date).diff(moment(f.from_date), 'days') + 1;
				f.from_date = frappe.datetime.add_days(f.from_date, span * dir);
				f.to_date = frappe.datetime.add_days(f.to_date, span * dir);
			} else if (f.view === 'months') {
				f.as_of = frappe.datetime.add_months(f.as_of, dir);
			} else {
				f.as_of = frappe.datetime.add_days(f.as_of, 7 * dir);
			}
			state.filters = f;
			syncControls();
			load();
		}

		$root.find('.osc-prev').on('click', () => step(-1));
		$root.find('.osc-next').on('click', () => step(1));
		$root.find('.osc-today').on('click', () => {
			const f = { ...state.filters, as_of: today };
			if (f.view === 'custom' && f.from_date && f.to_date) {
				const span = moment(f.to_date).diff(moment(f.from_date), 'days');
				f.from_date = frappe.datetime.add_days(today, -span);
				f.to_date = today;
			}
			state.filters = f;
			syncControls();
			load();
		});
		$root.find('.osc-expand').on('click', () => setAllOpen(true));
		$root.find('.osc-collapse').on('click', () => setAllOpen(false));
		$root.find('.osc-stock-refresh').on('click', () => loadStock());

		const toggleRow = (render, $scope) => function () {
			const id = $(this).attr('data-row');
			state.open[id] = !state.open[id];
			writeStore(state);
			render();
			$scope.find(`.osc-toggle[data-row="${CSS.escape(id)}"]`).trigger('focus');
		};
		const toggleSection = (render, $scope) => function () {
			const key = $(this).attr('data-section');
			state.closed[key] = !state.closed[key];
			writeStore(state);
			render();
			$scope.find(`.osc-sec-btn[data-section="${CSS.escape(key)}"]`).trigger('focus');
		};
		$wrap.on('click', '.osc-toggle', toggleRow(() => renderTable(), $wrap));
		$wrap.on('click', '.osc-sec-btn', toggleSection(() => renderTable(), $wrap));
		$stockWrap.on('click', '.osc-toggle', toggleRow(() => renderStock(), $stockWrap));
		$stockWrap.on('click', '.osc-sec-btn', toggleSection(() => renderStock(), $stockWrap));
		$wrap.on('click', '.osc-val', function () {
			const row = findRow($(this).attr('data-row'));
			if (row && row.drill) openDrill(row, $(this).attr('data-period'));
		});
		$stockWrap.on('click', '.osc-val', function () {
			const row = findStockRow($(this).attr('data-row'));
			if (row && row.drill) openStockDrill(row);
		});
		$stockWrap.on('click', '.osc-live-jump', () => showLive(state.filters.tier || null));
		$kpis.on('click', '.osc-kpi', function () {
			const id = $(this).attr('data-row');
			if ($(this).attr('data-stock')) {
				const row = findStockRow(id);
				if (row && row.drill) openStockDrill(row);
				return;
			}
			const row = findRow(id);
			if (row && row.drill) openDrill(row, $(this).attr('data-period'));
		});

		const setStickyTop = () => {
			const head = wrapper.querySelector('.page-head');
			const top = head ? Math.max(0, Math.round(head.getBoundingClientRect().bottom)) : 0;
			if (top) $root[0].style.setProperty('--osc-sticky-top', `${top}px`);
		};
		$(window).on('resize.mld', frappe.utils.debounce(setStickyTop, 150));
		frappe.pages[PAGE].on_page_show = () => setTimeout(setStickyTop, 50);

		function allRows() {
			const out = [];
			walkRows(state.data && state.data.sections, (row, section) => out.push({ row, section }));
			return out;
		}

		function allStockRows() {
			const out = [];
			walkRows(state.stock.data && state.stock.data.sections, (row, section) => out.push({ row, section }));
			return out;
		}

		function fullLabel(row) {
			return (row._path || []).concat(row.label).join(' › ');
		}

		function findRow(id) {
			const hit = allRows().find((x) => x.row.id === id);
			return hit && hit.row;
		}

		function findStockRow(id) {
			const hit = allStockRows().find((x) => x.row.id === id);
			return hit && hit.row;
		}

		function setAllOpen(open) {
			allRows().concat(allStockRows()).forEach(({ row }) => {
				if ((row.children || []).length) state.open[row.id] = open;
			});
			if (open) state.closed = {};
			writeStore(state);
			renderTable();
			renderStock();
		}

		function args() {
			const f = state.filters;
			return {
				as_of: f.as_of || today,
				company: f.company,
				view: f.view,
				from_date: f.view === 'custom' ? f.from_date : '',
				to_date: f.view === 'custom' ? f.to_date : '',
				location: f.location,
				tier: f.tier,
				customer: f.customer,
			};
		}

		function load() {
			const req = ++state.req;
			$wrap.addClass('is-loading');
			$kpis.addClass('is-loading');
			$status.text(__('Updating…'));
			layoutFilters();
			if (state.stock.key !== `${state.filters.company}|${state.filters.tier}`) loadStock();
			frappe.call({ method: METHOD + 'get_data', args: args() }).then((r) => {
				if (req !== state.req) return;
				state.data = r.message;
				render();
			}).always(() => {
				if (req !== state.req) return;
				$wrap.removeClass('is-loading');
				$kpis.removeClass('is-loading');
				$status.text('');
			});
		}

		function loadStock() {
			const req = ++state.stock.req;
			state.stock.key = `${state.filters.company}|${state.filters.tier}`;
			$stock.addClass('is-loading');
			$live.addClass('is-loading');
			frappe.call({
				method: METHOD + 'get_stock',
				args: { company: state.filters.company, tier: state.filters.tier },
			}).then((r) => {
				if (req !== state.stock.req) return;
				state.stock.data = r.message;
				state.stock.loadedAt = moment();
				buildLiveItems();
				renderStock();
				renderLive();
				renderKpis();
			}).always(() => {
				if (req !== state.stock.req) return;
				$stock.removeClass('is-loading');
				$live.removeClass('is-loading');
			});
		}

		setInterval(() => {
			const route = frappe.get_route ? frappe.get_route() : [PAGE];
			if (document.visibilityState === 'visible' && route[0] === PAGE) loadStock();
		}, 120000);

		function render() {
			renderNav();
			renderKpis();
			renderTable();
			setStickyTop();
		}

		function renderNav() {
			const d = state.data;
			const ps = d.periods;
			const first = ps[0], last = ps[ps.length - 1];
			let title, sub;
			if (d.view === 'weeks') {
				title = `${rangeText(first.start, last.end)}, ${moment(last.end).format('YYYY')}`;
				sub = __('Last 6 weeks, one column per week');
			} else if (d.view === 'months') {
				title = `${moment(first.start).format('MMM YYYY')} – ${moment(last.start).format('MMM YYYY')}`;
				sub = __('Last 6 months, one column per month');
			} else if (d.view === 'custom') {
				title = `${rangeText(first.start, first.end)}, ${moment(first.end).format('YYYY')}`;
				sub = __('Compared with {0}', [rangeText(ps[1].start, ps[1].end)]);
			} else {
				title = __('Week of {0}', [`${rangeText(first.start, first.end)}, ${moment(first.end).format('YYYY')}`]);
				sub = __('and the month of {0}', [moment(ps[2].start).format('MMMM YYYY')]);
			}
			const scope = [state.filters.company || __('All companies')];
			['location', 'tier', 'customer'].forEach((k) => state.filters[k] && scope.push(state.filters[k]));
			$root.find('.osc-nav .osc-nav-title').text(title);
			$root.find('.osc-nav .osc-nav-sub').text(`${sub} · ${scope.join(' · ')}`);
		}

		function kpiCard(k, row, cur, cmp, d) {
			const hc = periodHead(cur, d.today), hp = periodHead(cmp, d.today);
			const v = row.values[cur.key], c = row.values[cmp.key];
			const additive = ['lbs', 'kg', 'g', '$'].includes(k.unit);
			const zero = k.unit === '$' ? '$0' : '0';
			const value = formatValue(v, k.unit) || (additive && v != null ? zero : null);
			const unitText = ['lbs', 'kg', 'g'].includes(k.unit) ? ` ${k.unit}` : '';
			const compare = (formatValue(c, k.unit) || (additive && c != null ? zero : '—')) + (c ? unitText : '');
			const suffix = k.by && state.filters[k.by] ? ` · ${state.filters[k.by]}` : '';
			let foot;
			if (cur.future) {
				foot = esc(__('Not started yet'));
			} else if (cur.partial) {
				foot = esc(`${Math.abs(v || 0) < 0.005 ? __('Nothing yet') : __('So far')} · ${hp.title} ${compare}`);
			} else if (v == null || c == null || (!c && k.unit !== '%')) {
				foot = esc(`${hp.title}: ${compare}`);
			} else {
				const diff = v - c;
				const flat = Math.abs(diff) < 0.005;
				const amount = k.unit === '%' ? __('{0} pts', [num(Math.abs(diff), 2)]) : `${num(Math.abs(diff / c) * 100, 1)}%`;
				foot = flat
					? esc(`${__('No change vs {0}', [hp.title.toLowerCase()])} (${compare})`)
					: `<span class="osc-delta is-${diff > 0 ? 'up' : 'down'}">${diff > 0 ? '▲ ' : '▼ '}${esc(amount)}</span> ${esc(__('vs {0}', [hp.title.toLowerCase()]))} (${esc(compare)})`;
			}
			const unit = unitText && value ? `<span class="osc-kpi-unit">${k.unit}</span>` : '';
			return `
				<button type="button" class="osc-kpi" data-row="${esc(k.id)}" data-period="${esc(cur.key)}" title="${esc(__('See what is behind this number'))}">
					<span class="osc-kpi-label">${esc(k.label + suffix)}</span>
					<span class="osc-kpi-value">${value ? esc(value) : '—'}${unit}</span>
					<span class="osc-kpi-period">${esc(hc.title)}</span>
					<span class="osc-kpi-foot">${foot}</span>
				</button>`;
		}

		function stockKpi() {
			const s = state.stock.data;
			const row = s && allStockRows().find((x) => x.row.id === 'stock:rosin:total');
			if (!row) return '';
			const r = row.row;
			const pending = allStockRows().find((x) => x.row.id === 'pending:total');
			const t1 = allStockRows().find((x) => x.row.id === 'stock:rosin:T1');
			const foot = [
				t1 && !state.filters.tier ? `T1 ${num(t1.row.qty, 0)} g` : null,
				pending ? __('{0} lbs pending', [num(pending.row.qty, 0)]) : null,
			].filter(Boolean).join(' · ');
			return `
				<button type="button" class="osc-kpi" data-row="stock:rosin:total" data-stock="1" title="${esc(__('See what is behind this number'))}">
					<span class="osc-kpi-label">${esc(__('Rosin in stock') + (state.filters.tier ? ` · ${state.filters.tier}` : ''))}</span>
					<span class="osc-kpi-value">${esc(num(r.qty, 0))}<span class="osc-kpi-unit">g</span></span>
					<span class="osc-kpi-period">${esc(__('Right now, Main Storage'))}</span>
					<span class="osc-kpi-foot">${esc(foot)}</span>
				</button>`;
		}

		function renderKpis() {
			const d = state.data;
			let html = '';
			if (d) {
				const cur = d.periods.find((p) => p.key === d.kpi.current);
				const cmp = d.periods.find((p) => p.key === d.kpi.compare);
				html = KPIS.map((k) => {
					const row = findRow(k.id);
					return row ? kpiCard(k, row, cur, cmp, d) : '';
				}).join('');
			}
			$kpis.html(html + stockKpi());
		}

		function decorate(periods) {
			const d = state.data;
			return periods.map((p, i) => ({
				...p,
				...periodHead(p, d.today, d.view === 'weeks' || d.view === 'months'),
				bandStart: i === 0 || periods[i - 1].band !== p.band,
				focus: p.key === d.kpi.current,
			}));
		}

		function cellClass(p) {
			return `osc-band-${p.band}${p.bandStart ? ' is-band-start' : ''}${p.focus ? ' is-focus' : ''}`;
		}

		function sectionHead(s, span, extra) {
			const closed = !!state.closed[s.key];
			return `
				<tr class="osc-sec-row">
					<th colspan="${span}" scope="rowgroup">
						<div class="osc-sec-head">
							<button type="button" class="osc-sec-btn" data-section="${esc(s.key)}" aria-expanded="${!closed}">
								${ICON.chevron}<span class="osc-sec-title">${esc(s.title)}</span>
								<span class="osc-sec-note">${esc(s.note || '')}</span>
							</button>
							${extra || ''}
						</div>
					</th>
				</tr>`;
		}

		function metricCell(r, level) {
			const unit = r.unit ? `<span class="osc-unit">${esc(r.unit)}</span>` : '';
			const kids = r.children || [];
			const open = !!state.open[r.id];
			const toggle = kids.length
				? `<button type="button" class="osc-toggle${open ? ' is-open' : ''}" data-row="${esc(r.id)}" aria-expanded="${open}"
						aria-label="${esc((open ? __('Hide breakdown of {0}') : __('Show breakdown of {0}')).replace('{0}', r.label))}"
						title="${open ? __('Hide breakdown') : __('Show breakdown')}">${ICON.chevron}</button>`
				: '<span class="osc-toggle-gap"></span>';
			const hint = r.hint ? `<span class="osc-hint" title="${esc(r.hint)}" aria-label="${esc(r.hint)}">${ICON.info}</span>` : '';
			return `<th class="osc-metric" scope="row"><div class="osc-mcell">${r.sub ? '' : toggle}<span class="osc-label">${esc(r.label)}</span>${hint}${unit}</div></th>`;
		}

		function rowClass(r, level) {
			const cls = ['osc-row', `lvl-${level}`];
			if (r.total) cls.push('osc-total');
			if (r.child) cls.push('osc-child');
			if (r.sub) cls.push('osc-subhead');
			return cls.join(' ');
		}

		function renderTable() {
			const d = state.data;
			if (!d) return;
			const periods = decorate(d.periods);
			const span = periods.length + 1;
			let html = `
				<table class="osc-table osc-cols-${periods.length}">
					<thead><tr>
						<th class="osc-th-metric" scope="col">${__('Metric')}</th>
						${periods.map((p) => `
							<th class="osc-th-period ${cellClass(p)}" scope="col">
								<span class="osc-th-band">${p.bandStart ? esc(BAND_LABELS[p.band]) : '&nbsp;'}</span>
								<span class="osc-th-title">${esc(p.title)}</span>
								<span class="osc-th-range">${esc(p.range)}</span>
							</th>`).join('')}
					</tr></thead>`;
			d.sections.forEach((s) => {
				const closed = !!state.closed[s.key];
				html += `<tbody class="osc-sec osc-sec-${esc(s.key)}${closed ? ' is-closed' : ''}">${sectionHead(s, span)}`;
				if (!closed) s.rows.forEach((r) => { html += rowHtml(r, r.level || 0, periods); });
				html += '</tbody>';
			});
			$wrap.html(`${html}</table>`);
		}

		function rowHtml(r, level, periods) {
			if (r.sub) {
				return `<tr class="${rowClass(r, level)}">${metricCell(r, level)}${periods.map((p) => `<td class="osc-num ${cellClass(p)}"></td>`).join('')}</tr>`;
			}
			const cells = periods.map((p) => {
				const v = r.values ? r.values[p.key] : null;
				const text = formatValue(v, r.unit);
				const neg = v < 0 ? ' is-neg' : '';
				if (text == null) return `<td class="osc-num ${cellClass(p)}"><span class="osc-blank">—</span></td>`;
				if (!r.drill) return `<td class="osc-num ${cellClass(p)}${neg}">${text}</td>`;
				return `<td class="osc-num ${cellClass(p)}${neg}"><button type="button" class="osc-val" data-row="${esc(r.id)}"
					data-period="${esc(p.key)}" title="${__('See what is behind this number')}">${text}</button></td>`;
			}).join('');
			let html = `<tr class="${rowClass(r, level)}">${metricCell(r, level)}${cells}</tr>`;
			if (state.open[r.id]) (r.children || []).forEach((k) => { html += rowHtml({ ...k, child: 1 }, k.level || level + 1, periods); });
			return html;
		}

		function stockQty(r) {
			if (r.unit === 'items') return r.qty ? num(r.qty, 0) : null;
			return formatValue(r.qty, r.unit === 'g' ? 'g' : r.unit);
		}

		function stockRowHtml(r, level) {
			const text = stockQty(r);
			const qty = text == null
				? '<span class="osc-blank">—</span>'
				: r.drill
					? `<button type="button" class="osc-val" data-row="${esc(r.id)}" title="${__('See the SKUs behind this number')}">${text}</button>`
					: text;
			const value = Math.abs(r.value || 0) >= 0.5 ? `$${num(r.value, 0)}` : '<span class="osc-blank">—</span>';
			let html = `
				<tr class="${rowClass(r, level)}">
					${metricCell(r, level)}
					<td class="osc-num osc-stock-qty${r.qty < 0 ? ' is-neg' : ''}">${qty}</td>
					<td class="osc-num">${value}</td>
					<td class="osc-num">${r.skus ? num(r.skus, 0) : '<span class="osc-blank">—</span>'}</td>
				</tr>`;
			if (state.open[r.id]) (r.children || []).forEach((k) => { html += stockRowHtml({ ...k, child: 1 }, k.level || level + 1); });
			return html;
		}

		function renderStock() {
			const s = state.stock.data;
			if (!s) return;
			$stock.find('.osc-stock-sub').text([
				__('updated {0}', [(state.stock.loadedAt || moment()).format('h:mm A')]),
				s.company || __('All companies'),
				__('refreshes every 2 minutes'),
			].join(' · '));
			let html = `
				<table class="osc-table osc-stock-table">
					<thead><tr>
						<th class="osc-th-metric" scope="col">${__('Metric')}</th>
						<th class="osc-th-period osc-band-now" scope="col"><span class="osc-th-title">${__('On hand')}</span><span class="osc-th-range">${__('right now')}</span></th>
						<th class="osc-th-period osc-band-now" scope="col"><span class="osc-th-title">${__('Stock value')}</span><span class="osc-th-range">${__('at valuation rate')}</span></th>
						<th class="osc-th-period osc-band-now" scope="col"><span class="osc-th-title">${__('SKUs')}</span><span class="osc-th-range">${__('with stock')}</span></th>
					</tr></thead>`;
			s.sections.forEach((sec) => {
				const closed = !!state.closed[`stock:${sec.key}`];
				const key = { ...sec, key: `stock:${sec.key}` };
				const jump = ['rosin', 'back'].includes(sec.key)
					? `<button type="button" class="osc-sec-link osc-live-jump">${__('By SKU')} ${ICON.right}</button>` : '';
				html += `<tbody class="osc-sec osc-sec-${esc(sec.key)}${closed ? ' is-closed' : ''}">${sectionHead(key, 4, jump)}`;
				if (!closed) sec.rows.forEach((r) => { html += stockRowHtml(r, r.level || 0); });
				html += '</tbody>';
			});
			$stockWrap.html(`${html}</table>`);
		}

		function buildLiveItems() {
			const s = state.stock.data;
			const byItem = {};
			s.bins.forEach((b) => {
				if (!b.category) return;
				(byItem[b.item_code] = byItem[b.item_code] || []).push(b);
			});
			state.live.items = s.catalog.map((c) => ({ ...c, grams: c.uom === 'Gram' ? 1 : 0, bins: byItem[c.item_code] || [] }));
		}

		const showLive = (tab) => {
			if (tab) {
				state.live.tab = tab;
				renderLive();
			}
			$live[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
		};

		$liveTabs.on('click', '.osc-live-tab', function () {
			state.live.tab = $(this).attr('data-tab');
			writeStore(state);
			renderLive();
		});
		$live.on('input', '.osc-live-search', frappe.utils.debounce((e) => {
			state.live.search = String($(e.target).val() || '').trim().toLowerCase();
			renderLive();
		}, 200));
		$live.on('change', '.osc-live-zeros', function () {
			state.live.zeros = $(this).is(':checked');
			writeStore(state);
			renderLive();
		});
		$live.on('change', '.osc-live-where', function () {
			state.live.where = $(this).val();
			writeStore(state);
			renderLive();
		});
		$live.on('click', '.osc-live-sort', function () {
			const key = $(this).attr('data-key');
			const sort = state.live.sort;
			state.live.sort = { key, dir: sort.key === key ? -sort.dir : (['item_name', 'group_label'].includes(key) ? 1 : -1) };
			renderLive();
		});
		$live.on('click', '.osc-live-csv', () => exportLive());

		function liveView(item) {
			const where = state.live.where;
			const bins = item.bins.filter((b) => where === 'all' || b.kind === where);
			const on_hand = bins.reduce((a, b) => a + (b.qty || 0), 0);
			const reserved = bins.reduce((a, b) => a + (b.reserved || 0), 0);
			return {
				...item,
				warehouses: bins.filter((b) => Math.abs(b.qty) >= 0.005).sort((a, b) => b.qty - a.qty),
				on_hand,
				reserved,
				available: on_hand - reserved,
				value: bins.reduce((a, b) => a + (b.value || 0), 0),
			};
		}

		function liveQty(v, item) {
			if (Math.abs(v) < 0.005) return '<span class="osc-blank">—</span>';
			const text = item.grams ? num(v, 0) : `${num(v, 1)} ${esc(item.uom)}`;
			return v < 0 ? `<span class="is-neg">${text}</span>` : text;
		}

		function liveTotals(items) {
			const t = { skus: items.length, in_stock: 0, on_hand: 0, reserved: 0, available: 0, value: 0, other: 0 };
			items.forEach((i) => {
				if (Math.abs(i.on_hand) >= 0.005) t.in_stock += 1;
				t.value += i.value;
				if (!i.grams) { t.other += i.on_hand; return; }
				t.on_hand += i.on_hand;
				t.reserved += i.reserved;
				t.available += i.available;
			});
			return t;
		}

		function liveVisible(items) {
			const q = state.live.search;
			return items.filter((i) => {
				if (!state.live.zeros && Math.abs(i.on_hand) < 0.005 && Math.abs(i.reserved) < 0.005) return false;
				if (!q) return true;
				return [i.item_name, i.item_code, i.group_label, ...i.warehouses.map((w) => w.warehouse)]
					.some((v) => (v || '').toLowerCase().includes(q));
			});
		}

		function liveSorted(items) {
			const { key, dir } = state.live.sort;
			return items.slice().sort((a, b) => {
				const x = a[key], y = b[key];
				if (typeof x === 'number' || typeof y === 'number') return ((x || 0) - (y || 0)) * dir;
				return String(x || '').localeCompare(String(y || '')) * dir;
			});
		}

		function liveTabItems(tab) {
			const items = (state.live.items || []).map(liveView);
			if (tab === 'all') return items;
			if (tab === 'rosin') return items.filter((i) => TIERS.includes(i.category));
			return items.filter((i) => i.category === tab);
		}

		function renderLive() {
			const s = state.stock.data;
			if (!s || !state.live.items) return;
			const tabs = ['all', 'rosin', ...s.categories.map((c) => c.key)];
			if (!tabs.includes(state.live.tab)) state.live.tab = 'T1';
			const tabLabel = (t) => (t === 'all' ? __('Everything') : t === 'rosin' ? __('All rosin') : t);
			$liveTabs.html(tabs.map((t) => {
				const tot = liveTotals(liveTabItems(t));
				const active = state.live.tab === t;
				return `<button type="button" role="tab" class="osc-live-tab${active ? ' is-active' : ''}" data-tab="${esc(t)}" aria-selected="${active}">
					<span class="osc-live-tab-name">${esc(tabLabel(t))}</span>
					<span class="osc-live-tab-qty">${tot.on_hand ? `${num(tot.on_hand, 0)} g` : '—'}</span>
				</button>`;
			}).join(''));

			const tabItems = liveTabItems(state.live.tab);
			const all = liveTotals(tabItems);
			const shown = liveVisible(tabItems);
			const whereLabel = WHERE.find((w) => w.value === state.live.where).label;
			$live.find('.osc-live-sub').text([
				__('On hand right now'),
				whereLabel,
				__('updated {0}', [(state.stock.loadedAt || moment()).format('h:mm A')]),
				s.company || __('All companies'),
			].join(' · '));
			$live.find('.osc-live-summary').html(`
				<div class="osc-live-stat"><span>${esc(tabLabel(state.live.tab))} ${__('on hand')}</span><b>${num(all.on_hand, 0)} g</b></div>
				<div class="osc-live-stat"><span>${__('Reserved for orders')}</span><b>${num(all.reserved, 0)} g</b></div>
				<div class="osc-live-stat"><span>${__('Available')}</span><b class="${all.available < 0 ? 'is-neg' : ''}">${num(all.available, 0)} g</b></div>
				<div class="osc-live-stat"><span>${__('Stock value')}</span><b>$${num(all.value, 0)}</b></div>
				<div class="osc-live-stat"><span>${__('SKUs in stock')}</span><b>${all.in_stock} <small>${__('of {0}', [all.skus])}</small></b></div>
				${all.other ? `<div class="osc-live-stat"><span>${__('Counted in units')}</span><b>${num(all.other, 1)}</b></div>` : ''}`);
			if (!shown.length) {
				$liveScroll.html(`<div class="osc-empty-state">${state.live.search ? __('No SKU matches that search.') : __('Nothing on hand here.')}</div>`);
				return;
			}
			const sortTh = (key, labelText, cls = '') => {
				const on = state.live.sort.key === key;
				const arrow = on ? (state.live.sort.dir > 0 ? ' ↑' : ' ↓') : '';
				return `<th scope="col" class="${cls}" aria-sort="${on ? (state.live.sort.dir > 0 ? 'ascending' : 'descending') : 'none'}">
					<button type="button" class="osc-live-sort" data-key="${key}">${esc(labelText)}${arrow}</button></th>`;
			};
			const head = `<thead><tr>
				${sortTh('item_name', __('SKU'))}
				${sortTh('group_label', __('Grade'))}
				<th scope="col">${__('Where it is')}</th>
				${sortTh('on_hand', __('On hand'), 'osc-num')}
				${sortTh('reserved', __('Reserved'), 'osc-num')}
				${sortTh('available', __('Available'), 'osc-num')}
				${sortTh('value', __('Value'), 'osc-num')}
				${sortTh('last_moved', __('Last moved'), 'osc-num')}
			</tr></thead>`;
			const itemRow = (i) => `
				<tr class="${i.disabled ? 'is-disabled' : ''}">
					<td class="osc-live-sku">
						<a href="/app/item/${encodeURIComponent(i.item_code)}" target="_blank" rel="noopener">${esc(i.item_name || i.item_code)}</a>
						<span class="osc-live-code">${esc(i.item_code)}${i.disabled ? ` · ${__('disabled')}` : ''}</span>
					</td>
					<td class="osc-live-grade">${esc(i.group_label)}</td>
					<td class="osc-live-where">${i.warehouses.length
						? i.warehouses.map((w) => `<div><span>${esc(w.warehouse)}${w.kind === 'partner' ? ` <em>${__('partner')}</em>` : w.kind === 'samples' ? ` <em>${__('samples')}</em>` : ''}</span><b>${liveQty(w.qty, i)}</b></div>`).join('')
						: '<span class="osc-blank">—</span>'}</td>
					<td class="osc-num osc-live-onhand">${liveQty(i.on_hand, i)}</td>
					<td class="osc-num">${liveQty(i.reserved, i)}</td>
					<td class="osc-num">${liveQty(i.available, i)}</td>
					<td class="osc-num">${Math.abs(i.value) >= 0.5 ? '$' + num(i.value, 0) : '<span class="osc-blank">—</span>'}</td>
					<td class="osc-num osc-live-date" title="${i.last_moved ? esc(moment(i.last_moved).fromNow()) : ''}">${i.last_moved ? esc(moment(i.last_moved).format(moment(i.last_moved).isSame(moment(), 'year') ? 'MMM D' : 'MMM D, YYYY')) : '<span class="osc-blank">—</span>'}</td>
				</tr>`;
			const totalRow = (t, labelText, cls, countText) => `
				<tr class="${cls}">
					<td colspan="3">${esc(labelText)} <span class="osc-live-count">${esc(countText)}</span></td>
					<td class="osc-num">${num(t.on_hand, 0)}</td>
					<td class="osc-num">${num(t.reserved, 0)}</td>
					<td class="osc-num${t.available < 0 ? ' is-neg' : ''}">${num(t.available, 0)}</td>
					<td class="osc-num">$${num(t.value, 0)}</td>
					<td></td>
				</tr>`;
			let body = '';
			if (state.live.tab === 'all' || state.live.tab === 'rosin') {
				s.categories.forEach((c) => {
					const group = shown.filter((i) => i.category === c.key);
					if (!group.length) return;
					body += `<tbody>${totalRow(liveTotals(group), c.key, 'osc-live-group', __('{0} SKUs', [group.length]))}${liveSorted(group).map(itemRow).join('')}</tbody>`;
				});
			} else {
				body = `<tbody>${liveSorted(shown).map(itemRow).join('')}</tbody>`;
			}
			const foot = `<tfoot>${totalRow(liveTotals(shown), __('Total'), 'osc-live-total', __('{0} SKUs shown', [shown.length]))}</tfoot>`;
			$liveScroll.html(`<table class="osc-live-table">${head}${body}${foot}</table>`);
		}

		function exportLive() {
			const s = state.stock.data;
			if (!s) return;
			const items = liveSorted(liveVisible(liveTabItems(state.live.tab)));
			const out = [[__('Product'), __('Grade'), __('Item code'), __('Item name'), __('Where it is'), __('On hand'), __('UOM'),
				__('Reserved'), __('Available'), __('Value'), __('Last moved')]];
			items.forEach((i) => out.push([
				i.category, i.item_group, i.item_code, i.item_name,
				i.warehouses.map((w) => `${w.warehouse}: ${Math.round(w.qty * 100) / 100}`).join('; '),
				Math.round(i.on_hand * 100) / 100, i.uom, Math.round(i.reserved * 100) / 100,
				Math.round(i.available * 100) / 100, Math.round(i.value * 100) / 100, i.last_moved || '',
			]));
			frappe.tools.downloadify(out, null, `Live inventory ${state.live.tab} ${moment().format('YYYY-MM-DD HHmm')}`);
		}

		function exportCsv() {
			const d = state.data;
			const out = [];
			if (state.stock.data) {
				out.push([__('Section'), __('Metric'), __('Unit'), __('On hand right now'), __('Stock value'), __('SKUs')]);
				allStockRows().forEach(({ row, section }) => {
					out.push([section.title, fullLabel(row), row.unit, Math.round((row.qty || 0) * 100) / 100,
						Math.round((row.value || 0) * 100) / 100, row.skus || 0]);
				});
				out.push([]);
			}
			if (d) {
				const heads = d.periods.map((p) => periodHead(p, d.today));
				out.push([__('Section'), __('Metric'), __('Unit'), ...heads.map((h) => `${h.title} (${h.range})`)]);
				allRows().forEach(({ row, section }) => {
					if (row.sub) return;
					out.push([section.title, fullLabel(row), row.unit, ...d.periods.map((p) => {
						const v = row.values[p.key];
						return v == null ? '' : Math.round(v * 100) / 100;
					})]);
				});
			}
			frappe.tools.downloadify(out, null, `Matts Lab Dashboard ${state.filters.as_of}`);
		}

		function link(doctype, name, label) {
			return `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}" target="_blank" rel="noopener">${esc(label || name)}</a>`;
		}

		function dialog(title) {
			const d = new frappe.ui.Dialog({ title: esc(title), size: 'extra-large', fields: [{ fieldtype: 'HTML', fieldname: 'body' }] });
			const $body = d.get_field('body').$wrapper;
			$body.html(`<div class="osc-drill"><div class="osc-empty-state">${__('Loading…')}</div></div>`);
			d.show();
			return $body.find('.osc-drill');
		}

		function drillTable(cols, rows, total) {
			if (!rows.length) return `<div class="osc-empty-state">${__('Nothing recorded here.')}</div>`;
			const cls = (c) => (c.num ? 'osc-num' : c.nowrap ? 'osc-nowrap' : '');
			const th = cols.map((c) => `<th class="${cls(c)}" scope="col">${esc(c.label)}</th>`).join('');
			const body = rows.map((r) => `<tr>${cols.map((c) => `<td class="${cls(c)}">${c.html(r)}</td>`).join('')}</tr>`).join('');
			const foot = total ? `<tfoot><tr>${cols.map((c) => `<td class="${cls(c)}">${total[c.key] || ''}</td>`).join('')}</tr></tfoot>` : '';
			return `<div class="osc-drill-count">${rows.length === 1 ? __('1 row') : __('{0} rows', [rows.length])}</div>
				<div class="osc-drill-scroll"><table class="osc-drill-table"><thead><tr>${th}</tr></thead><tbody>${body}</tbody>${foot}</table></div>`;
		}

		function openDrill(row, periodKey) {
			const d = state.data;
			const p = d.periods.find((x) => x.key === periodKey);
			const head = periodHead(p, d.today);
			const $out = dialog(`${fullLabel(row)} · ${head.title} (${head.range})`);
			frappe.call({ method: METHOD + 'get_drill', args: { ...args(), drill: row.drill, period: periodKey } })
				.then((r) => $out.html(drillHtml(r.message)));
		}

		function drillHtml(res) {
			const rows = res.rows || [];
			const sum = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
			const date = (r) => esc(frappe.datetime.str_to_user(r.posting_date));
			if (res.kind === 'wash') {
				return drillTable([
					{ key: 'date', label: __('Date'), html: date, nowrap: 1 },
					{ key: 'location', label: __('Washed by'), html: (r) => esc(r.location), nowrap: 1 },
					{ key: 'doc', label: __('Document'), html: (r) => link(r.doc_type, r.doc), nowrap: 1 },
					{ key: 'refs', label: __('Job card / notes'), html: (r) => esc(r.refs) },
					{ key: 'inputs', label: __('Fresh frozen'), html: (r) => esc(r.inputs) },
					{ key: 'lbs', label: __('Lbs'), num: 1, html: (r) => formatValue(r.lbs, 'lbs') || '—' },
				], rows, { date: __('Total'), lbs: formatValue(sum('lbs'), 'lbs') });
			}
			if (res.kind === 'manufacture') {
				return drillTable([
					{ key: 'date', label: __('Date'), html: date, nowrap: 1 },
					{ key: 'entry', label: __('Stock entry'), html: (r) => link('Stock Entry', r.name), nowrap: 1 },
					{ key: 'wo', label: __('Work order'), html: (r) => (r.work_order ? link('Work Order', r.work_order) : '—'), nowrap: 1 },
					{ key: 'inputs', label: __('Input'), html: (r) => esc(r.inputs) },
					{ key: 'input', label: __('In'), num: 1, html: (r) => (r.input ? `${formatValue(r.input, r.input_unit === 'lbs' ? 'lbs' : 'g')} ${esc(r.input_unit)}` : '—') },
					{ key: 'outputs', label: __('Produced'), html: (r) => esc(r.outputs) },
					{ key: 'grams', label: __('Out (g)'), num: 1, html: (r) => formatValue(r.grams, 'g') || '—' },
					{ key: 'yield', label: __('Yield'), num: 1, html: (r) => formatValue(r.yield, '%') || '—' },
				], rows, { date: __('Total'), grams: formatValue(sum('grams'), 'g') });
			}
			const qty = sum('qty'), amount = sum('amount');
			return drillTable([
				{ key: 'date', label: __('Date'), html: date, nowrap: 1 },
				{ key: 'invoice', label: __('Invoice'), html: (r) => link('Sales Invoice', r.invoice), nowrap: 1 },
				{ key: 'customer', label: __('Customer'), html: (r) => esc(r.customer) },
				{ key: 'item', label: __('Item'), html: (r) => link('Item', r.item_code, r.item_name || r.item_code) },
				{ key: 'tier', label: __('Product'), html: (r) => esc(r.tier) },
				{ key: 'qty', label: __('Grams'), num: 1, html: (r) => formatValue(r.qty, 'g') || '—' },
				{ key: 'amount', label: __('Amount'), num: 1, html: (r) => formatValue(r.amount, '$') || '—' },
				{ key: 'price', label: __('$/g'), num: 1, html: (r) => (r.qty ? formatValue(r.amount / r.qty, '$/g') : '—') },
			], rows, {
				date: __('Total'), qty: formatValue(qty, 'g'), amount: formatValue(amount, '$'),
				price: qty ? formatValue(amount / qty, '$/g') : '',
			});
		}

		function openStockDrill(row) {
			const s = state.stock.data;
			const dr = row.drill;
			const $out = dialog(`${fullLabel(row)} · ${__('right now')}`);
			if (dr.kind === 'mr') {
				const lines = s.mr_lines.filter((m) => s.ff_groups.includes(m.item_group) && (!dr.ff_group || m.item_group === dr.ff_group));
				$out.html(drillTable([
					{ key: 'date', label: __('Date'), html: (r) => esc(frappe.datetime.str_to_user(r.transaction_date)), nowrap: 1 },
					{ key: 'mr', label: __('Material request'), html: (r) => link('Material Request', r.mr), nowrap: 1 },
					{ key: 'status', label: __('Status'), html: (r) => esc(r.status), nowrap: 1 },
					{ key: 'item', label: __('Item'), html: (r) => link('Item', r.item_code, r.item_name || r.item_code) },
					{ key: 'warehouse', label: __('Warehouse'), html: (r) => esc(r.warehouse) },
					{ key: 'qty', label: __('Requested'), num: 1, html: (r) => formatValue(r.qty, 'lbs') || '—' },
					{ key: 'ordered', label: __('Ordered'), num: 1, html: (r) => formatValue(r.ordered, 'lbs') || '—' },
					{ key: 'pending', label: __('Pending (lbs)'), num: 1, html: (r) => formatValue(r.pending, 'lbs') || '—' },
				], lines, { date: __('Total'), pending: formatValue(lines.reduce((a, m) => a + m.pending, 0), 'lbs') }));
				return;
			}
			const ff = new Set(s.ff_groups), conc = new Set(s.concentrate_groups);
			const bins = s.bins.filter((b) => {
				if (Math.abs(b.qty) < 0.005) return false;
				if (b.kind !== dr.scope) return false;
				if (dr.groups && !dr.groups.includes(b.item_group)) return false;
				if (dr.warehouse && b.warehouse !== dr.warehouse) return false;
				if (dr.bucket === 'ff' && !ff.has(b.item_group)) return false;
				if (dr.bucket === 'conc' && !(conc.has(b.item_group) && b.uom === 'Gram')) return false;
				if (dr.bucket === 'other' && (ff.has(b.item_group) || (conc.has(b.item_group) && b.uom === 'Gram'))) return false;
				return true;
			}).sort((a, b) => b.qty - a.qty);
			const label = (g) => (s.group_labels[g] || g);
			const gramsOnly = bins.every((b) => b.uom === 'Gram');
			$out.html(drillTable([
				{ key: 'item', label: __('Item'), html: (r) => link('Item', r.item_code, r.item_name || r.item_code) },
				{ key: 'group', label: __('Item group'), html: (r) => esc(label(r.item_group)) },
				{ key: 'warehouse', label: __('Warehouse'), html: (r) => esc(r.warehouse) },
				{ key: 'qty', label: __('On hand'), num: 1, html: (r) => `${num(r.qty, r.uom === 'Gram' ? 0 : 1)} ${esc(r.uom === 'Gram' ? 'g' : r.uom)}` },
				{ key: 'reserved', label: __('Reserved'), num: 1, html: (r) => (Math.abs(r.reserved) >= 0.005 ? num(r.reserved, 0) : '—') },
				{ key: 'value', label: __('Value'), num: 1, html: (r) => (Math.abs(r.value) >= 0.5 ? '$' + num(r.value, 0) : '—') },
			], bins, {
				item: __('Total'),
				qty: gramsOnly ? `${num(bins.reduce((a, b) => a + b.qty, 0), 0)} g` : '',
				value: '$' + num(bins.reduce((a, b) => a + (b.value || 0), 0), 0),
			}));
		}

		syncControls();
		load();
	};
})();
