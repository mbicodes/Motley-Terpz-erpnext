// Sales Operation Board. Leads: one card per account (Sales Pipeline Account) by lead status, with the volume it
// procures or produces and what it wants from us (Board · By Owner · Projection · List). Deals: Sales Pipeline Deal by
// stage (Board · By Owner · Calendar · List), several per account. Stages, statuses, owners, lists, alert rules and
// stock come from the server (Sales Pipeline Settings); this file renders and calls.
(function () {
	const ROUTE = 'sales-operation-board';
	const M = 'cannabis_management.cannabis_management.page.sales_operation_board.sales_operation_board.';
	const DT = 'Sales Pipeline Deal';
	const ACC_DT = 'Sales Pipeline Account';
	const NONE = '__none';
	const LS_COLS = 'sob_list_cols_v2';
	const LS_ACC_COLS = 'sob_acc_cols_v2';
	const VIEWS = {
		lead: [['board', 'Board'], ['owner', 'By Owner'], ['projection', 'Projection'], ['list', 'List']],
		deal: [['board', 'Board'], ['owner', 'By Owner'], ['calendar', 'Calendar'], ['list', 'List']],
	};
	const ALL_VIEWS = ['board', 'owner', 'calendar', 'list', 'projection'];
	// grams per unit for the volume rows, weeks in a month (52 / 12)
	const UNITS = { g: 1, kg: 1000, lb: 453.59237 };
	const WPM = 52 / 12;
	// record type from its ID (accounts are SPA-, deals SPD-), so it works before the board has loaded
	const dt_of = name => (/^SPA-/.test(String(name || '')) ? ACC_DT : DT);
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
		search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
		check: '<path d="M20 6 9 17l-5-5"/>',
		receipt: '<path d="M4 2v20l3-2 3 2 3-2 3 2 3-2 1 .7V2l-1 .7-3-2-3 2-3-2-3 2-3-2z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
		box: '<path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
		clock: '<path d="M21 7.5V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h3.5"/><path d="M16 2v4M8 2v4M3 10h5"/><path d="M17.5 17.5 16 16.3V14"/><circle cx="16" cy="16" r="6"/>',
		move: '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/><path d="m12 16 4-4-4-4"/>',
		mail: '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
		undo: '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/>',
		scale: '<path d="M12 3v18M5 21h14M3 7h18"/><path d="m6 7-3 7a3 3 0 0 0 6 0zM18 7l-3 7a3 3 0 0 0 6 0z"/>',
		deal: '<path d="M3 7h18v13H3z"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
	};
	// One line-icon style everywhere (lucide shapes): stroke 1.5, colour from the text it sits in.
	const svg = (p, size) => `<svg width="${size || 14}" height="${size || 14}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;

	// Liquid Glass kit (JS half): edge refraction in Chromium, tone flipping everywhere. From the liquid-glass skill,
	// unchanged except that it is called by the page instead of on DOMContentLoaded (desk pages mount later).
	const LG = (() => {
		const chromium = !!(navigator.userAgentData && navigator.userAgentData.brands && navigator.userAgentData.brands.some(b => b.brand === 'Chromium'));
		const calm = () => matchMedia('(prefers-reduced-transparency: reduce), (prefers-contrast: more)').matches;
		const NS = 'http://www.w3.org/2000/svg';
		let host, uid = 0;
		function lensMap(w, h, r, bezel) {
			const c = document.createElement('canvas');
			c.width = w; c.height = h;
			const ctx = c.getContext('2d');
			const img = ctx.createImageData(w, h);
			r = Math.min(r, w / 2, h / 2);
			bezel = Math.min(bezel, r);
			for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
				const px = x + .5 - w / 2, py = y + .5 - h / 2;
				const qx = Math.abs(px) - (w / 2 - r), qy = Math.abs(py) - (h / 2 - r);
				const out = Math.hypot(Math.max(qx, 0), Math.max(qy, 0));
				const d = r - out - Math.min(Math.max(qx, qy), 0);
				let dx = 0, dy = 0;
				if (d >= 0 && d < bezel) {
					const t = 1 - d / bezel, mag = t * t * t;
					let nx, ny;
					if (qx > 0 && qy > 0) { nx = qx / out; ny = qy / out; }
					else if (qx > qy) { nx = 1; ny = 0; }
					else { nx = 0; ny = 1; }
					dx = -Math.sign(px) * nx * mag;
					dy = -Math.sign(py) * ny * mag;
				}
				const i = (y * w + x) * 4;
				img.data[i] = 128 + dx * 127; img.data[i + 1] = 128 + dy * 127; img.data[i + 2] = 128; img.data[i + 3] = 255;
			}
			ctx.putImageData(img, 0, 0);
			return c.toDataURL();
		}
		function refract(el, o) {
			o = Object.assign({ bezel: 14, strength: 14, blur: 4, saturate: 1.7 }, o || {});
			if (!chromium || calm() || el._lg) return;
			el._lg = true;
			if (!host) {
				host = document.createElementNS(NS, 'svg');
				host.setAttribute('aria-hidden', 'true');
				host.style.cssText = 'position:absolute;width:0;height:0';
				document.body.append(host);
			}
			const id = `sob-lg-${++uid}`;
			const build = () => {
				const w = Math.round(el.offsetWidth), h = Math.round(el.offsetHeight);
				if (!w || !h) return;
				const r = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
				const old = host.querySelector(`#${id}`);
				if (old) old.remove();
				host.insertAdjacentHTML('beforeend', `<filter id="${id}" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse" x="0" y="0" width="${w}" height="${h}" color-interpolation-filters="sRGB">
					<feGaussianBlur in="SourceGraphic" stdDeviation="${o.blur}" result="b"/>
					<feImage href="${lensMap(w, h, r, o.bezel)}" x="0" y="0" width="${w}" height="${h}" preserveAspectRatio="none" result="m"/>
					<feDisplacementMap in="b" in2="m" scale="${o.strength * 2}" xChannelSelector="R" yChannelSelector="G" result="d"/>
					<feColorMatrix in="d" type="saturate" values="${o.saturate}"/>
				</filter>`);
				el.style.backdropFilter = `url(#${id})`;
			};
			build();
			let last = `${el.offsetWidth}x${el.offsetHeight}`;
			new ResizeObserver(() => {
				const now = `${el.offsetWidth}x${el.offsetHeight}`;
				if (now !== last) { last = now; build(); }
			}).observe(el);
		}
		function adapt(els) {
			let queued = false;
			const run = () => {
				queued = false;
				for (const el of els) {
					const r = el.getBoundingClientRect();
					if (!r.width) continue;
					const pts = [.1, .3, .5, .7, .9].map(f => [r.left + r.width * f, r.top + r.height / 2]);
					pts.push([r.left + r.width / 2, r.top + 2], [r.left + r.width / 2, r.bottom - 2]);
					const tones = new Set();
					for (const [x, y] of pts) {
						const hit = document.elementsFromPoint(x, y).find(n => !el.contains(n) && n.closest('[data-tone]'));
						const t = hit && hit.closest('[data-tone]').dataset.tone;
						if (t) tones.add(t);
					}
					if (tones.size) el.dataset.on = tones.size > 1 || tones.has('mixed') ? 'mixed' : [...tones][0];
				}
			};
			const queue = () => { if (!queued) { queued = true; requestAnimationFrame(run); } };
			addEventListener('scroll', queue, { passive: true, capture: true });
			addEventListener('resize', queue, { passive: true });
			run();
			return queue;
		}
		return { refract, adapt };
	})();
	// Event colours live in the stylesheet (.ev-<key>) so they follow light and dark themes.
	const EVENTS = [
		{ key: 'followup', field: 'next_step_due', label: 'Follow-up', icon: ICON.phone },
		{ key: 'sample', field: 'sample_date', label: 'Sample', icon: ICON.flask },
		{ key: 'close', field: 'expected_close', label: 'Close', icon: ICON.flag },
		{ key: 'delivery', field: 'delivery_pickup', label: 'Delivery', icon: ICON.truck },
	];
	const LIST_COLS = [
		['stage', 'Stage', 'stage'], ['account', 'Account'], ['deal_owner', 'Owner', 'owner'], ['priority', 'Priority', 'priority'],
		['product_line', 'Product Line'], ['tier', 'Tier'], ['total_grams', 'Quantity', 'dqty'], ['price_per_gram', 'Price', 'dprice'],
		['deal_value', 'Deal Value', 'money'], ['weighted_value', 'Weighted', 'money'], ['next_step_due', 'Next Follow-up', 'date_edit'],
		['expected_close', 'Expected Close', 'date'], ['modified', 'Last Updated', 'datetime'],
		['co_owners', 'Co-owners', 'co'], ['contact_name', 'Contact'], ['phone', 'Phone'], ['email', 'Email'], ['customer', 'Customer'], ['lead', 'Lead'],
		['timeline', 'Timeline'], ['status_detail', 'Status Detail'], ['samples', 'Samples'], ['copack', 'Copack'],
		['hardware', 'Hardware'], ['sample_date', 'Sample Date', 'date'], ['delivery_pickup', 'Delivery / Pickup', 'date'],
		['days_in_stage', 'Days in Stage', 'num'], ['probability', 'Win %', 'pct'], ['value_override', 'Value Override', 'money'],
		['payment_terms', 'Payment Terms'], ['lead_source', 'Lead Source'], ['form', 'Form'], ['size_per_strain', 'Size per Strain'],
		['strain_profiles', 'Strain Profiles'], ['location_address', 'Location'], ['license_number', 'License #'],
	];
	const DEFAULT_COLS = ['stage', 'account', 'deal_owner', 'product_line', 'tier', 'total_grams', 'price_per_gram', 'deal_value', 'next_step_due',
		'contact_name', 'phone', 'email', 'expected_close', 'samples', 'modified'];
	// Leads board list: one row per account
	const ACC_COLS = [
		['lead_status', 'Lead Status', 'stage'], ['account', 'Account'], ['account_owner', 'Relationship Manager', 'owner'],
		['products', 'Product Lines'], ['vol_week', 'Volume / Week', 'qty'], ['vol_month', 'Wants / Month', 'qty'],
		['monthly_potential', 'Potential / Month', 'money'], ['weighted_potential', 'Weighted / Month', 'money'],
		['open_deals', 'Open Deals', 'num'], ['open_value', 'Open Deal Value', 'money'], ['next_step_due', 'Next Follow-up', 'date_edit'],
		['modified', 'Last Updated', 'datetime'], ['customer', 'Customer'], ['lead', 'Lead'], ['contact_name', 'Contact'],
		['phone', 'Phone'], ['email', 'Email'], ['won_value', 'Won Value', 'money'], ['lost_deals', 'Lost Deals', 'num'],
		['days_in_stage', 'Days in Status', 'num'], ['probability', 'Status %', 'pct'], ['lead_source', 'Lead Source'],
		['location_address', 'Location'], ['license_number', 'License #'], ['relationship_notes', 'Notes'],
	];
	const ACC_DEFAULT_COLS = ['lead_status', 'account', 'account_owner', 'contact_name', 'phone', 'email', 'products', 'vol_week', 'vol_month',
		'monthly_potential', 'open_value', 'next_step_due', 'lead_source', 'modified'];
	// List view cells that can be filled in place: text, phone, email, number, date, a Settings list, fixed options,
	// or a button that opens the product / volume editor or the buyer tab
	const DEAL_EDIT = {
		contact_name: 'text', phone: 'tel', email: 'email', timeline: 'text', status_detail: 'text', form: 'text',
		size_per_strain: 'text', strain_profiles: 'text', location_address: 'text', license_number: 'text',
		samples: 'list:samples', copack: 'opts:YES|NO', hardware: 'list:hardware', payment_terms: 'list:payment_terms', lead_source: 'list:lead_source',
		sample_date: 'date', delivery_pickup: 'date', expected_close: 'date', next_step_due: 'date',
		value_override: 'num', deal_value: 'override',
		product_line: 'reqs', tier: 'reqs', total_grams: 'reqs', price_per_gram: 'reqs',
		customer: 'buyer', lead: 'buyer',
	};
	const ACC_EDIT = {
		contact_name: 'text', phone: 'tel', email: 'email', location_address: 'text', license_number: 'text', relationship_notes: 'text',
		lead_source: 'list:lead_source', next_step_due: 'date',
		products: 'vol', vol_week: 'vol', vol_month: 'vol', monthly_potential: 'vol',
		customer: 'buyer', lead: 'buyer',
	};
	const ACC_NOTE_SECTIONS = [['relationship_notes', 'Relationship Notes']];
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
	const nq = n => (+n || 0).toLocaleString('en-US', { maximumFractionDigits: 2 });
	// weights on cards and widgets: grams up to a kilo, then kilos
	const wt = g => { g = +g || 0; return g >= 1000 ? (Math.round(g / 100) / 10).toLocaleString('en-US') + ' kg' : n0(g) + ' g'; };
	// Quantities in the unit the team counts them in: lb for fresh frozen, g or kg for extracts (Settings > Product Lines > Unit)
	const LB = 453.59237;
	const FAMS = ['lb', 'g'];
	const fmt_lb = lb => { lb = +lb || 0; return (Math.abs(lb) >= 100 ? n0(lb) : (Math.round(lb * 10) / 10).toLocaleString('en-US')) + ' lb'; };
	const qty = (g, fam) => (fam === 'lb' ? fmt_lb((+g || 0) / LB) : wt(g));
	const qty_pair = by => FAMS.filter(f => +by[f] > 0).map(f => qty(by[f], f)).join(' · ');
	const r2 = n => Math.round((+n || 0) * 100) / 100;
	const r3 = n => Math.round((+n || 0) * 1000) / 1000;
	const MEASURES = [['money', 'Dollars'], ['volume', 'Volume']];
	// "1 deal", "3 deals"
	const pl = (n, one, many) => `${n0(n)} ${n === 1 ? one : many}`;
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
				view: 'board', board: 'deal', measure: 'money', kgroup: '', need: false, owners: null, prods: [], priority: '', q: '', attn: false, closed: false,
				cal_mode: 'month', cal_date: null, cal_type: 'all', sort: { key: '', dir: 1 }, sel: null, tab: 'overview',
			};
			this.cols = this.read_cols(LS_COLS, LIST_COLS, DEFAULT_COLS);
			this.acc_cols = this.read_cols(LS_ACC_COLS, ACC_COLS, ACC_DEFAULT_COLS);

			page.set_primary_action(__('New Deal'), () => this.new_deal(), 'add');
			page.add_button(__('Export'), () => this.export_xlsx());
			page.add_menu_item(__('Deal List'), () => frappe.set_route('List', DT));
			page.add_menu_item(__('Account List'), () => frappe.set_route('List', ACC_DT));
			page.add_menu_item(__('Sales Pipeline Settings'), () => frappe.set_route('Form', 'Sales Pipeline Settings'));

			// Two layers. Content (KPIs, columns, cards, list, calendar) stays plain; the controls float above it
			// on Liquid Glass: three capsules in a sticky bar, their menus, and the deal sheet. Menus sit beside
			// the capsules, not inside them, because a backdrop filter inside another one cannot see the page.
			const menu_btn = (key, label) => `<button type="button" class="lg-item sob-mbtn" data-menu="${key}" aria-haspopup="true" aria-expanded="false">
				<span class="sob-mbtn-k">${label}</span><span class="sob-mbtn-v" data-menu-value="${key}"></span>${svg(ICON.down, 14)}</button>`;
			this.$root = $(`
				<div class="sob" data-tone="light" data-board="deal">
					<div class="sob-bg" aria-hidden="true"><i class="sob-bg-lead"></i><i class="sob-bg-deal"></i></div>
					<div class="lg-edge sob-edge" aria-hidden="true"></div>
					<div class="sob-bar">
						<div class="lg lg-group sob-boards" role="group" aria-label="${__('Board')}" data-seg="boards" data-lg-adapt data-lg-refract>
							${BOARDS.map(b => `<button type="button" class="lg-item sob-board-btn" data-board="${b[0]}" aria-pressed="false" data-tip="${esc(b[0] === 'lead'
								? __('One card per account and where the relationship stands. An account can have several deals')
								: __('Every sale being worked, by stage. Each deal belongs to an account on Leads'))}">${__(b[1])}<span class="sob-board-n"></span></button>`).join('')}
						</div>
						<div class="lg lg-group sob-tabs" role="tablist" aria-label="${__('Views')}" data-seg="views" data-lg-adapt data-lg-refract></div>
						<div class="lg lg-group sob-measure" role="group" aria-label="${__('Show amounts in')}" data-seg="measure" data-lg-adapt data-lg-refract>
							${MEASURES.map(m => `<button type="button" class="lg-item" data-measure="${m[0]}" aria-pressed="false" data-tip="${esc(m[0] === 'money'
								? __('Cards and totals in dollars: open deals and monthly potential')
								: __('Cards and totals in volume: lb for fresh frozen, g and kg for extracts'))}">${__(m[1])}</button>`).join('')}
						</div>
						<div class="lg lg-group sob-tools" data-lg-adapt data-lg-refract>
							<label class="lg-item sob-search">${svg(ICON.search, 16)}<input type="search" class="sob-q" autocomplete="off" aria-label="${__('Search deals')}" placeholder="${__('Search deals')}"></label>
							<span class="sob-owner-group">${menu_btn('owner', __('Owner'))}</span>
							${menu_btn('prod', __('Product line'))}
							${menu_btn('more', __('Filters'))}
						</div>
						<div class="lg lg--thick sob-menu lg-in" data-menu-panel="owner" role="group" aria-label="${__('Owner')}" hidden><div class="sob-owner-pills"></div></div>
						<div class="lg lg--thick sob-menu lg-in" data-menu-panel="prod" role="group" aria-label="${__('Product line')}" hidden><div class="sob-ms-menu"></div></div>
						<div class="lg lg--thick sob-menu lg-in" data-menu-panel="more" role="group" aria-label="${__('Filters')}" hidden>
							<label class="sob-mrow" for="sob-prio"><span>${__('Priority')}</span><select id="sob-prio" class="sob-select sob-prio"></select></label>
							<button type="button" class="lg-item sob-mi sob-toggle" data-toggle="attn" role="switch" aria-checked="false"></button>
							<button type="button" class="lg-item sob-mi sob-toggle" data-toggle="closed" role="switch" aria-checked="false"></button>
							<button type="button" class="lg-item sob-mi sob-toggle" data-tips-toggle role="switch" aria-checked="true"><span>${__('Show tips on hover')}</span><span class="sob-switch" aria-hidden="true"></span></button>
						</div>
					</div>
					<div class="sob-kpis"></div>
					<div class="sob-view"><div class="sob-loading">${__('Loading…')}</div></div>
				</div>`).appendTo(page.main);

			this.$drawer = $(`<div class="sob-drawer-wrap" hidden><div class="sob-drawer-backdrop" data-act="close"></div>
				<aside class="sob-drawer lg lg--thick lg-in" role="dialog" aria-modal="false" aria-label="${__('Deal')}"></aside></div>`).appendTo(page.main);

			this.$pop = $(`<div class="sob-pop lg lg--thick lg-in" role="dialog" aria-modal="false" hidden></div>`).appendTo(page.main);
			// hover tutorials: one glass tooltip for every [data-tip]
			this.$tip = $(`<div class="sob-tipbox lg lg--thick" id="sob-tip" role="tooltip" hidden></div>`).appendTo(page.main);
			this.bind();
			this.bind_pop();
			this.bind_tips();
			this.bind_segs();
			this.mount_glass();
			frappe.realtime.on('sales_pipeline_update', msg => this.queue_reload(msg));
		}

		// ---------- Liquid Glass: tones, refraction, sticky bar ----------

		// Which gradient shows, and the tone the glass reads: the bare backdrop is light on Leads and dark on
		// Deals; the frosted panels and cards are light (dark in the dark theme); menus and the sheet follow the theme.
		apply_tones() {
			const dark = document.documentElement.getAttribute('data-theme') === 'dark';
			const board = this.state.board === 'lead' ? 'lead' : 'deal';
			const panel = dark ? 'dark' : 'light';
			this.$root.attr('data-board', board).attr('data-tone', dark ? 'dark' : 'light');
			this.$root.find('.sob-kpis, .sob-col, .sob-table-wrap, .sob-cal, .sob-agenda').attr('data-tone', panel);
			this.$root.find('.sob-menu, .sob-colpick-menu').attr('data-on', panel);
			this.$drawer.find('.sob-drawer').attr('data-on', panel);
			if (this.$pop) this.$pop.attr('data-on', panel);
			// in the dark theme the columns are dark frost holding cards, so the glass over them takes the heavier fill
			if (dark) this.$root.find('.sob-col').attr('data-tone', 'mixed');
			// re-read what sits under the glass bar now that the tones changed
			if (this._adapt) this._adapt();
		}

		mount_glass() {
			this.apply_tones();
			const bar = this.$root.find('.sob-bar').get(0);
			// refraction needs a settled size, so wait for the brand fonts
			const go = () => {
				bar.querySelectorAll('[data-lg-refract]').forEach(el => LG.refract(el));
				this._adapt = LG.adapt([...bar.querySelectorAll('[data-lg-adapt]')]);
			};
			(document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(go);
			new MutationObserver(() => this.apply_tones()).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
			// the desk scrolls inside .app-content (Motley theme), not the window, so listen in the capture phase
			const place = () => { this._raf = 0; this.place_bar(); };
			const queue = () => { if (!this._raf) this._raf = requestAnimationFrame(place); };
			window.addEventListener('scroll', queue, { capture: true, passive: true });
			window.addEventListener('resize', queue, { passive: true });
		}

		// The bar sticks right under the desk header; the scroll edge shows only once content runs under it.
		place_bar() {
			if (frappe.get_route_str() !== ROUTE) return;
			const root = this.$root.get(0);
			const head = $(this.wrapper).find('.page-head').get(0) || document.querySelector('.navbar');
			const stick = head ? Math.max(0, Math.round(head.getBoundingClientRect().bottom)) : 0;
			const r = root.getBoundingClientRect();
			root.style.setProperty('--sob-stick', stick + 'px');
			root.style.setProperty('--sob-edge-left', Math.round(r.left) + 'px');
			root.style.setProperty('--sob-edge-width', Math.round(r.width) + 'px');
			const bar = this.$root.find('.sob-bar').get(0);
			this.$root.toggleClass('stuck', !!bar && r.top < stick - 4 && bar.getBoundingClientRect().top <= stick + 1);
		}

		// ---------- state and URL ----------

		read_cols(ls, all, def) {
			try {
				const c = JSON.parse(localStorage.getItem(ls) || 'null');
				if (Array.isArray(c) && c.length) return c.filter(k => all.some(x => x[0] === k));
			} catch (e) { /* storage off */ }
			return def.slice();
		}

		read_url() {
			const p = new URLSearchParams(window.location.search);
			const ro = frappe.route_options || {};
			frappe.route_options = null;
			const s = this.state;
			if (BOARDS.some(b => b[0] === p.get('board'))) s.board = p.get('board');
			if (p.get('view') && ALL_VIEWS.includes(p.get('view'))) s.view = p.get('view');
			if (p.has('owner')) s.owners = p.get('owner') ? p.get('owner').split(',') : [];
			if (p.has('product_line')) s.prods = (p.get('product_line') || '').split(',').map(x => x.trim()).filter(Boolean);
			else if (p.has('prod')) s.prods = p.get('prod') ? [p.get('prod')] : [];  // links saved before the multi-select
			if (p.has('priority')) s.priority = p.get('priority');
			if (p.has('q')) s.q = p.get('q');
			if (p.has('attn')) s.attn = p.get('attn') === '1';
			if (p.has('closed')) s.closed = p.get('closed') === '1';
			if (p.get('measure') === 'volume' || p.get('measure') === 'money') s.measure = p.get('measure');
			if (p.has('totals')) s.kgroup = p.get('totals') || '';
			if (p.has('missing')) s.need = p.get('missing') === '1';
			if (p.get('cal') === 'week' || p.get('cal') === 'month') s.cal_mode = p.get('cal');
			if (p.get('date') && pd(p.get('date'))) s.cal_date = p.get('date');
			if (p.get('show')) s.cal_type = p.get('show');
			const deal = ro.account || p.get('account') || ro.deal || p.get('deal');
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
			if (s.measure === 'volume') p.set('measure', 'volume');
			if (this.data && this.kgroup()) p.set('totals', this.kgroup());
			if (s.need && s.view === 'list') p.set('missing', '1');
			if (s.view === 'calendar') {
				p.set('cal', s.cal_mode);
				if (s.cal_date) p.set('date', s.cal_date);
				if (s.cal_type !== 'all') p.set('show', s.cal_type);
			}
			if (s.sel) p.set(dt_of(s.sel) === ACC_DT ? 'account' : 'deal', s.sel);
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
				r.accounts = r.accounts || [];
				r.accounts.forEach(a => { a._acc = true; a.account = a.account_name; });
				this.data = r;
				this.s = r.settings;
				this.s.lead_statuses = this.s.lead_statuses || [];
				// sales people only ever see the deals they are assigned to, so they get no owner filter
				if (!r.is_manager || this.state.owners === null) this.state.owners = [];
				if (!this.state.cal_date) this.state.cal_date = r.today;
				this._prim = null;
				this.render();
				if (this.state.sel) this.load_feed(this.state.sel);
			}).catch(() => {
				this.$root.find('.sob-view').html(`<div class="sob-loading">${__('The board could not be loaded. Please refresh the page.')}</div>`);
			});
		}

		// ---------- lookups ----------

			stage(name) { return (this.s.stages || []).find(x => x.name === name) || null; }
			status(name) { return (this.s.lead_statuses || []).find(x => x.name === name) || null; }
			// a deal's stage or an account's lead status (same colour / probability shape)
			stage_of(d) { return d && d._acc ? this.status(d.lead_status) : this.stage(d && d.stage); }
			stage_name(d) { return d && d._acc ? d.lead_status : d && d.stage; }
			stage_patch(d, name) { return d && d._acc ? { lead_status: name } : { stage: name }; }
			stages_of(board) { return board === 'lead' ? (this.s.lead_statuses || []) : (this.s.stages || []); }
			first_stage_of(board) { const open = this.stages_of(board).filter(x => !x.is_closed); return (open[0] || this.stages_of(board)[0] || {}).name || this.s.first_stage; }
			own(d) { return d && d._acc ? d.account_owner : d && d.deal_owner; }
			own_field(d) { return d && d._acc ? 'account_owner' : 'deal_owner'; }
			acc_of(d) { return d && d.pipeline_account ? (this.data.accounts || []).find(a => a.name === d.pipeline_account) || null : null; }
			deals_of(a) { return (this.data.deals || []).filter(d => d.pipeline_account === a.name); }
			unit_of(line) { return ((this.s && this.s.line_units) || {})[line] || 'g'; }
			fam_of(line) { return this.unit_of(line) === 'lb' ? 'lb' : 'g'; }
			// what a family of lines is called: "Fresh Frozen & Tolling" (lb), "Extracts" (g and kg)
			fam_name(f) {
				const names = (this.s.product_lines || []).filter(l => this.fam_of(l) === f);
				if (f === 'g' && names.length > 2) return __('Extracts');
				return names.length ? names.join(' & ') : (f === 'lb' ? __('By the lb') : __('By the gram'));
			}
			// grams a deal asks for, per family
			// grams a deal asks for, per family; g = a product group ('' = every group)
			deal_qty(d, g) {
				const by = { lb: 0, g: 0 };
				this.deal_lines_in(d, g || '').forEach(l => { by[this.fam_of(l.product_line)] += +l.total_grams || 0; });
				return by;
			}
			// grams an account moves a week and wants a month, per family
			// grams an account moves a week and wants a month, per family; g = a product group ('' = every group)
			acc_qty(a, g) {
				const week = { lb: 0, g: 0 }, month = { lb: 0, g: 0 };
				(a.volume || []).filter(v => !g || this.group_of(v.product_line) === g).forEach(v => {
					const c = this.vol_calc(v);
					const f = this.fam_of(v.product_line);
					week[f] += c.weekly_grams;
					month[f] += c.monthly_grams;
				});
				return { week, month };
			}
			// ---- product groups (Settings > Product Lines > Group): Extracts, Fresh Frozen, Tolling ----
			group_of(line) { return ((this.s && this.s.line_groups) || {})[line] || line || __('Other'); }
			groups() {
				const out = [];
				(this.s.product_lines || []).forEach(l => { const g = this.group_of(l); if (!out.includes(g)) out.push(g); });
				return out;
			}
			// the group the totals show ('' = all), kept valid when Settings change
			kgroup() { return this.groups().includes(this.state.kgroup) ? this.state.kgroup : ''; }
			// a deal's requirement lines (or its own product line) in group g
			deal_lines_in(d, g) {
				const lines = this.lines_of(d).filter(l => l.product_line);
				const src = lines.length ? lines : (d.product_line || +d.total_grams ? [{ product_line: d.product_line, tier: d.tier, total_grams: d.total_grams, price_per_gram: d.price_per_gram, short: d.short }] : []);
				return g ? src.filter(l => this.group_of(l.product_line) === g) : src;
			}
			in_group(d, g) { return !g || this.deal_lines_in(d, g).length > 0; }
			// the part of a deal's value that belongs to group g: its lines' amounts, scaled to a manual value when there is one
			deal_val(d, g) {
				const value = +d.deal_value || 0;
				if (!g) return value;
				const all = this.deal_lines_in(d, '');
				const mine = this.deal_lines_in(d, g);
				if (!mine.length) return 0;
				const amt = l => (+l.total_grams || 0) * (+l.price_per_gram || 0);
				const tot = all.reduce((s, l) => s + amt(l), 0);
				if (!tot) return mine.length === all.length ? value : 0;
				return value * mine.reduce((s, l) => s + amt(l), 0) / tot;
			}
			deal_short(d, g) { return this.deal_lines_in(d, g).reduce((s, l) => s + (+l.short || 0), 0); }
			acc_in(a, g) { return !g || (a.volume || []).some(v => this.group_of(v.product_line) === g) || this.deals_of(a).some(d => this.in_group(d, g)); }
			acc_open(a, g) { return g ? this.deals_of(a).filter(d => !d.is_closed).reduce((s, d) => s + this.deal_val(d, g), 0) : (+a.open_value || 0); }
			acc_pot(a, g) {
				if (!g) return +a.monthly_potential || 0;
				return (a.volume || []).filter(v => this.group_of(v.product_line) === g).reduce((s, v) => s + this.vol_calc(v).monthly_value, 0);
			}
			lines_of(d) {
				const w = this.work && this.work[d.name];
				return (w || d.lines || []).filter(l => !l.draft || w);
			}
			calc_value(d) { return this.lines_of(d).filter(l => l.product_line).reduce((a, l) => a + (+l.total_grams || 0) * (+l.price_per_gram || 0), 0); }
		won_stage() { return (this.s.stages || []).find(x => x.is_closed && x.is_won); }
		lost_stage() { return (this.s.stages || []).find(x => x.is_closed && !x.is_won); }
		owner(user) { return (this.s.all_owners || []).find(o => o.user === user) || null; }
		owner_name(user) { const o = this.owner(user); return o ? o.name : (user || __('Unassigned')); }
		find(name) {
			if (!this.data || !name) return undefined;
			return (dt_of(name) === ACC_DT ? this.data.accounts : this.data.deals || []).find(d => d.name === name);
		}
		prio_rank(p) { const i = (this.s.lists.priority || []).indexOf(p); return i < 0 ? 99 : i; }
		is_top_priority(p) { return p && (this.s.lists.priority || [])[0] === p; }

		filtered(opts) {
			opts = opts || {};
			const s = this.state;
			const q = (s.q || '').trim().toLowerCase();
			const owners = s.owners || [];
			return (this.data ? this.data.deals : []).filter(d =>
				(opts.keep_hidden || s.closed || !d.hidden_closed) &&
				(opts.any_owner || !owners.length || owners.includes(d.deal_owner || NONE) || (d.co_owners || []).some(u => owners.includes(u))) &&
				(!s.prods.length || (d.lines && d.lines.length ? d.lines.some(l => s.prods.includes(l.product_line)) : s.prods.includes(d.product_line))) &&
				(!s.priority || d.priority === s.priority) &&
				(!q || [d.name, d.account, d.contact_name, d.customer, d.email, d.phone, d.timeline, d.status_detail,
					d.buyer_notes, d.deal_notes, d.next_steps, d.fulfillment_notes, d.ops_notes, d.strain_profiles]
					.join(' ').toLowerCase().indexOf(q) >= 0) &&
				(!s.attn || d.attention));
		}

		// Leads board: accounts under the same owner, product line, search and attention filters
		filtered_acc() {
			const s = this.state;
			const q = (s.q || '').trim().toLowerCase();
			const owners = s.owners || [];
			return (this.data ? this.data.accounts : []).filter(a =>
				(!owners.length || owners.includes(a.account_owner || NONE)) &&
				(!s.prods.length || (a.volume || []).some(v => s.prods.includes(v.product_line))) &&
				(!q || [a.name, a.account_name, a.lead_status, a.contact_name, a.customer, a.customer_title, a.lead_title, a.email, a.phone,
					a.relationship_notes, (a.volume || []).map(v => v.product_line + ' ' + (v.notes || '')).join(' ')]
					.join(' ').toLowerCase().indexOf(q) >= 0) &&
				(!s.attn || a.attention));
		}

		// overdue follow-ups first, then the biggest monthly potential
		sorted_accs(list) {
			const today = this.data.today;
			const late = a => (a.next_step_due && a.next_step_due < today && !a.is_closed ? 0 : 1);
			return list.slice().sort((a, b) => (late(a) - late(b)) || ((+b.monthly_potential || 0) - (+a.monthly_potential || 0)) ||
				String(a.account).localeCompare(String(b.account)));
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
			const views = VIEWS[s.board] || VIEWS.deal;
			if (!views.some(v => v[0] === s.view)) s.view = 'board';
			const tips = {
				board: s.board === 'lead' ? __('Columns by lead status. Drag an account to change its status') : __('Columns by stage. Drag a deal to move it on'),
				owner: s.board === 'lead' ? __('One column per relationship manager. Drag to reassign') : __('One column per owner. Drag to reassign; the new owner is notified'),
				projection: __('What accounts want each month, added up by product line and lead status'),
				calendar: __('Follow-ups, samples, closes and deliveries by date. Drag to reschedule'),
				list: __('Every card as a sheet: sort, choose columns, edit in place'),
			};
			// the views differ per board (Projection on Leads, Calendar on Deals); rebuilt only when the board changes
			const $tabs = this.$root.find('.sob-tabs');
			if ($tabs.attr('data-board') !== s.board) {
				$tabs.attr('data-board', s.board).html(views.map(v => `<button type="button" class="lg-item sob-tab" role="tab" data-view="${v[0]}" aria-selected="false" data-tip="${esc(tips[v[0]])}">${__(v[1])}</button>`).join(''));
			}
			$tabs.find('.sob-tab').each((_, el) => {
				const on = $(el).attr('data-view') === s.view;
				$(el).toggleClass('on', on).attr('aria-selected', on);
			});
			this.$root.find('[data-measure]').each((_, el) => el.setAttribute('aria-pressed', String(el.getAttribute('data-measure') === s.measure)));
			const counts = { lead: this.filtered_acc().length, deal: this.filtered().length };
			this.$root.find('.sob-board-btn').each((_, el) => {
				const b = $(el).attr('data-board');
				const on = b === s.board;
				$(el).toggleClass('on', on).attr('aria-pressed', on).find('.sob-board-n').text(counts[b]);
			});
			this.render_filters();
			const $v = this.$root.find('.sob-view');
			if (s.board === 'lead') {
				const accs = this.filtered_acc();
				this.render_kpis_acc(accs);
				if (s.view === 'owner') this.render_owner($v, accs);
				else if (s.view === 'projection') this.render_projection($v, accs);
				else if (s.view === 'list') this.render_list($v, accs);
				else this.render_board_acc($v, accs);
			} else {
				this.render_kpis(this.filtered({ keep_hidden: true }));
				const list = this.filtered();
				if (s.view === 'owner') this.render_owner($v, list);
				else if (s.view === 'calendar') this.render_calendar($v, list);
				else if (s.view === 'list') this.render_list($v, list);
				else this.render_board($v, list);
			}
			this.set_primary();
			this.render_drawer();
			this._quiet = Date.now();  // the re-render restores scroll positions; that is not the user scrolling
			this.render_pop();
			this.write_url();
			this.apply_tones();
			this.place_bar();
			this.$root.find('[data-seg]').each((_, g) => this.seg_sync(g));
		}

		// Deals: the open pipeline as one figure and one grape funnel bar (stage by stage), then four compact stats
		// Deals: the open pipeline as one figure and one grape funnel bar (stage by stage), then four compact stats.
		// The arrows above step the totals through All, Extracts, Fresh Frozen and Tolling.
		render_kpis(list) {
			const g = this.kgroup();
			const scoped = list.filter(d => this.in_group(d, g));
			const open = scoped.filter(d => !d.is_closed);
			const val = d => this.deal_val(d, g);
			const sum = (arr, f) => arr.reduce((a, d) => a + (+f(d) || 0), 0);
			const won = scoped.filter(d => d.won_this_month);
			const attn = open.filter(d => d.attention);
			const count = k => open.filter(d => (d.flags || []).some(f => f.key === k)).length;
			const month = MONTHS[pd(this.data.today).getMonth()];
			const lost = scoped.filter(d => d.is_lost).length;
			const stages = this.stages_of('deal').filter(st => !st.is_closed);
			const fam_sum = (arr, f) => arr.reduce((a, d) => a + this.deal_qty(d, g)[f], 0);
			const weighted = sum(open, d => val(d) * (+d.probability || 0) / 100);
			const attention = [__('Needs attention'), n0(attn.length), `${count('overdue')} ${__('overdue')} · ${count('stalled')} ${__('stalled')} · ${count('no_owner')} ${__('no owner')} · ${count('short')} ${__('short')}`,
				attn.length ? 'attn' : '', __('Open deals with an overdue follow-up, too long in one stage, no owner or not enough stock')];
			let hero, stats;
			if (this.state.measure === 'volume') {
				const tot = { lb: fam_sum(open, 'lb'), g: fam_sum(open, 'g') };
				const won_q = { lb: fam_sum(won, 'lb'), g: fam_sum(won, 'g') };
				hero = {
					label: __('In open deals'), tip: __('Everything the open deals ask for, in lb for fresh frozen and tolling, g or kg for extracts'),
					figures: FAMS.filter(f => tot[f]).map(f => [qty(tot[f], f), g ? '' : this.fam_name(f)]),
					sub: __('{0} open deals · {1} with a quantity', [open.length, open.filter(d => qty_pair(this.deal_qty(d, g))).length]),
					bars: FAMS.filter(f => tot[f]).map(f => ({ caption: g || FAMS.filter(x => tot[x]).length < 2 ? '' : this.fam_name(f), parts: stages.map(st => ({ name: st.name, colour: st.colour,
						value: fam_sum(open.filter(d => d.stage === st.name), f), text: v => qty(v, f) })) })),
					empty: __('No quantities on open deals yet'),
				};
				stats = [
					[__('Open deals'), n0(open.length), __('{0} lost deals kept in {1}', [lost, this.first_stage_of('deal')]), '', __('Deals not won or lost yet')],
					[__('Won in {0}', [month]), qty_pair(won_q) || '—', pl(won.length, __('deal won'), __('deals won')), won.length ? 'good' : '', __('Quantity of the deals won this month')],
					[__('Short in stock'), wt(sum(open, d => this.deal_short(d, g))), __('Needed beyond what is available'), '', __('Grams the open deals need beyond the stock on hand (sellable warehouses)')],
					attention,
				];
			} else {
				const value = sum(open, val);
				const won_value = sum(won, val);
				const loose = g ? 0 : sum(open.filter(d => !this.deal_lines_in(d, '').length), val);
				hero = {
					label: __('Open pipeline'), tip: __('Value of every open deal: quantity × price, or the manual value'),
					figures: [[usd(value), '']],
					sub: `${pl(open.length, __('open deal'), __('open deals'))} · ${__('{0} weighted by stage', [usd(weighted)])}${loose ? ' · ' + __('{0} on deals with no product line, counted only here', [usd(loose)]) : ''}`,
					bars: [{ caption: '', parts: stages.map(st => ({ name: st.name, colour: st.colour, value: sum(open.filter(d => d.stage === st.name), val), text: usd })) }],
					empty: __('No open deal has a value yet'),
				};
				stats = [
					[__('Weighted value'), usd(weighted), __('Value × stage probability'), '', __('What the pipeline is likely worth: each deal\'s value times its stage\'s win probability')],
					[__('Won in {0}', [month]), usd(won_value), pl(won.length, __('deal won'), __('deals won')), won_value ? 'good' : '', __('Deals moved to Closed Won this month')],
					[__('Lost deals'), n0(lost), __('Kept in {0} to win back', [this.first_stage_of('deal')]), '', __('Lost deals stay at the bottom of Active Opportunity with their reason')],
					attention,
				];
			}
			this.kpi_html(hero, stats);
		}

		// Leads board widgets: what the accounts move, what they want from us and what that is worth
		// Leads: dollars in open deals (or the volume they want) by lead status, then four compact stats
		// Leads: dollars in open deals (or the volume they want) by lead status, then four compact stats,
		// for All products or one group at a time
		render_kpis_acc(list) {
			const g = this.kgroup();
			const accs = list.filter(a => this.acc_in(a, g));
			const sum = (arr, f) => arr.reduce((a, x) => a + (+f(x) || 0), 0);
			const customers = accs.filter(a => a.is_customer).length;
			const attn = accs.filter(a => a.attention);
			const count = k => accs.filter(a => (a.flags || []).some(f => f.key === k)).length;
			const statuses = this.stages_of('lead');
			const with_vol = accs.filter(a => (a.volume || []).some(v => !g || this.group_of(v.product_line) === g));
			const deals = accs.flatMap(a => this.deals_of(a)).filter(d => this.in_group(d, g));
			const open_deals = deals.filter(d => !d.is_closed);
			const won_deals = deals.filter(d => d.is_won);
			const attention = [__('Needs attention'), n0(attn.length), `${count('overdue')} ${__('overdue')} · ${count('stalled')} ${__('stalled')} · ${count('no_owner')} ${__('no owner')}`,
				attn.length ? 'attn' : '', __('Accounts with an overdue follow-up, too long in one status, or no relationship manager')];
			let hero, stats;
			if (this.state.measure === 'volume') {
				const q = accs.map(a => [a, this.acc_qty(a, g)]);
				const tot = k => ({ lb: q.reduce((s, x) => s + x[1][k].lb, 0), g: q.reduce((s, x) => s + x[1][k].g, 0) });
				const month = tot('month'), week = tot('week');
				const fams = FAMS.filter(f => month[f]);
				hero = {
					label: __('Wanted each month'), tip: __('What accounts told us they want from us, per month. Per-week amounts count 52 / 12 weeks a month'),
					figures: fams.map(f => [qty(month[f], f), g ? '' : this.fam_name(f)]),
					sub: __('From {0} of {1} accounts with volume recorded', [with_vol.length, accs.length]),
					bars: fams.map(f => ({ caption: g || fams.length < 2 ? '' : this.fam_name(f), parts: statuses.map(st => ({ name: st.name, colour: st.colour,
						value: q.filter(x => x[0].lead_status === st.name).reduce((s, x) => s + x[1].month[f], 0), text: v => qty(v, f) })) })),
					empty: g ? __('No volume recorded for {0} yet', [g]) : __('No volume recorded yet. Open an account and add what it buys each week'),
				};
				stats = [
					[__('Moves each week'), qty_pair(week) || '—', __('What they procure or produce'), '', __('How much these accounts buy from anyone or make themselves in a week: the size of each account')],
					[__('Wants each week'), qty_pair({ lb: month.lb / WPM, g: month.g / WPM }) || '—', __('Monthly demand ÷ 4.33'), '', __('The monthly demand spread over a week')],
					[__('Accounts with volume'), `${with_vol.length} / ${accs.length}`, __('Record the rest to complete the projection'), '', __('Accounts that have at least one volume row')],
					attention,
				];
			} else {
				const open = sum(accs, a => this.acc_open(a, g));
				const pot = sum(accs, a => this.acc_pot(a, g));
				const loose = g ? 0 : sum(open_deals.filter(d => !this.deal_lines_in(d, '').length), d => +d.deal_value || 0);
				const with_open = accs.filter(a => this.acc_open(a, g) > 0).length;
				hero = {
					label: __('In open deals'), tip: __('The value of the open deals with these accounts, by the account\'s lead status'),
					figures: [[usd(open), '']],
					sub: `${pl(open_deals.length, __('open deal'), __('open deals'))} ${__('with')} ${pl(with_open, __('account'), __('accounts'))} · ${__('{0} weighted by stage', [usd(sum(open_deals, d => this.deal_val(d, g) * (+d.probability || 0) / 100))])}${loose ? ' · ' + __('{0} on deals with no product line, counted only here', [usd(loose)]) : ''}`,
					bars: [{ caption: '', parts: statuses.map(st => ({ name: st.name, colour: st.colour, value: sum(accs.filter(a => a.lead_status === st.name), a => this.acc_open(a, g)), text: usd })) }],
					empty: g ? __('No open {0} deal has a value yet', [g]) : __('No open deal with these accounts has a value yet'),
				};
				stats = [
					[__('Potential / month'), usd(pot), usd(pot * 12) + ' ' + __('a year'), '', __('What the accounts want each month × their price: the business they could bring every month')],
					[__('Won'), usd(sum(won_deals, d => this.deal_val(d, g))), pl(won_deals.length, __('deal won'), __('deals won')), '', __('Value of every Closed Won deal with these accounts')],
					[__('Accounts'), n0(accs.length), __('{0} customers · {1} leads', [customers, accs.length - customers]), '', g ? __('Accounts with volume or deals in {0}', [g]) : __('Customers are accounts in Active or Recurring Customer')],
					attention,
				];
			}
			this.kpi_html(hero, stats);
		}

		// Arrows above the KPI strip: All products, then each product group, one at a time
		kpage_html() {
			const pages = [''].concat(this.groups());
			const cur = this.kgroup();
			const i = Math.max(0, pages.indexOf(cur));
			const name = p => p || __('All products');
			const lines = p => { const l = (p ? (this.s.product_lines || []).filter(x => this.group_of(x) === p) : this.groups()).join(', '); return l === p ? '' : l; };
			const prev = pages[(i - 1 + pages.length) % pages.length], next = pages[(i + 1) % pages.length];
			return `<div class="sob-kpage" role="group" aria-label="${esc(__('Totals for'))}">
				<button type="button" class="sob-kpage-btn" data-kpage="-1" aria-label="${esc(__('Show {0}', [name(prev)]))}" data-tip="${esc(__('Show {0}', [name(prev)]))}">${svg(ICON.left, 16)}</button>
				<div class="sob-kpage-name" aria-live="polite"><b>${esc(name(cur))}</b><span>${esc(lines(cur))}</span></div>
				<button type="button" class="sob-kpage-btn" data-kpage="1" aria-label="${esc(__('Show {0}', [name(next)]))}" data-tip="${esc(__('Show {0}', [name(next)]))}">${svg(ICON.right, 16)}</button>
				<div class="sob-kpage-dots">${pages.map((p, j) => `<button type="button" class="${j === i ? 'on' : ''}" data-kgroup="${esc(p)}" aria-label="${esc(name(p))}" aria-pressed="${j === i}" data-tip="${esc(name(p))}"></button>`).join('')}</div>
			</div>`;
		}

		set_kgroup(step, to) {
			const pages = [''].concat(this.groups());
			const i = Math.max(0, pages.indexOf(this.kgroup()));
			const j = to !== undefined ? Math.max(0, pages.indexOf(to)) : (i + step + pages.length) % pages.length;
			if (j === i) return;
			this._kanim = (to !== undefined ? j > i : step > 0) ? 'next' : 'prev';
			this.set({ kgroup: pages[j] });
		}

		// The KPI strip: one hero panel (figure, sub line, thin segmented bars with a legend) and compact stat tiles.
		// Bar colours are the stage colours (one grape ramp, light to dark along the pipeline); hovering a part
		// gives its name, amount and share.
		kpi_html(hero, stats) {
			const total = b => b.parts.reduce((a, p) => a + p.value, 0);
			const bar = b => {
				const t = total(b);
				const parts = b.parts.filter(p => p.value > 0);
				const label = parts.map(p => `${__(p.name)} ${p.text(p.value)} (${Math.round(p.value / t * 100)}%)`).join(', ');
				return `<div class="sob-pipe">
					${b.caption ? `<div class="sob-pipe-cap"><span>${esc(b.caption)}</span></div>` : ''}
					<div class="sob-pipe-bar" role="img" aria-label="${esc((b.caption ? b.caption + ': ' : '') + label)}">${parts.map(p =>
						`<i style="--sob-stage:${esc(p.colour || '#A1A1AA')};flex-grow:${p.value}" data-tip="${esc(`${__(p.name)}: ${p.text(p.value)} · ${Math.round(p.value / t * 100)}%`)}"></i>`).join('')}</div>
				</div>`;
			};
			const shown = (hero.bars || []).filter(b => total(b) > 0);
			// legend in pipeline order (every bar lists the parts in the same order)
			const names = shown.length ? shown[0].parts.map(p => p.name).filter(n => shown.some(b => b.parts.some(p => p.name === n && p.value > 0))) : [];
			const colours = {};
			shown.forEach(b => b.parts.forEach(p => { colours[p.name] = p.colour; }));
			const one = shown.length === 1 ? shown[0] : null;
			const legend = names.map(n => {
				const p = one && one.parts.find(x => x.name === n);
				return `<span style="--sob-stage:${esc(colours[n] || '#A1A1AA')}"><i class="sob-stage-dot"></i>${esc(__(n))}${p ? `<b>${esc(p.text(p.value))}</b>` : ''}</span>`;
			}).join('');
			const figures = (hero.figures || []).length ? hero.figures : [['—', '']];
			// a group change slides the numbers in from the side the arrow points to
			const $k = this.$root.find('.sob-kpis').attr('data-anim', this._kanim || null);
			this._kanim = null;
			$k.html(`${this.kpage_html()}
				<section class="sob-hero" data-tip="${esc(hero.tip || '')}">
					<div class="sob-kpi-label">${esc(hero.label)}</div>
					<div class="sob-hero-figs">${figures.map(f => `<div class="sob-hero-fig"><b>${esc(f[0])}</b>${f[1] && figures.length > 1 ? `<span>${esc(f[1])}</span>` : ''}</div>`).join('')}</div>
					<div class="sob-kpi-sub">${esc(hero.sub || '')}</div>
					${shown.length ? `${shown.map(bar).join('')}<div class="sob-pipe-legend">${legend}</div>` : `<div class="sob-pipe-empty">${esc(hero.empty || '')}</div>`}
				</section>
				<div class="sob-stats">${stats.map(k => `
					<div class="sob-kpi${k[3] ? ' ' + k[3] : ''}" data-tip="${esc(k[4] || '')}">
						<div class="sob-kpi-label">${esc(k[0])}</div>
						<div class="sob-kpi-value">${esc(k[1])}</div>
						<div class="sob-kpi-sub">${esc(k[2])}</div>
					</div>`).join('')}</div>`);
		}

		// New Lead on the Leads board, New Deal on the Deals board
		set_primary() {
			const lead = this.state.board === 'lead';
			const key = lead ? 'lead' : 'deal';
			if (this._prim === key) return;
			this._prim = key;
			if (lead ? this.data.can_create_account : this.data.can_create) {
				this.page.set_primary_action(lead ? __('New Lead') : __('New Deal'), () => (this.state.board === 'lead' ? this.new_account() : this.new_deal()), 'add');
			} else this.page.clear_primary_action();
		}

		render_filters() {
			const s = this.state;
			const owners = s.owners || [];
			const lead = s.board === 'lead';
			// priority and closed deals mean nothing on accounts
			this.$root.find('.sob-mrow').toggle(!lead);
			this.$root.find('[data-toggle="closed"]').toggle(!lead);
			this.$root.find('.sob-q').attr('placeholder', lead ? __('Search leads') : __('Search deals')).attr('aria-label', lead ? __('Search leads') : __('Search deals'));
			const tick = `<span class="sob-tick">${svg(ICON.check, 14)}</span>`;
			const value = (key, text, on) => this.$root.find(`[data-menu-value="${key}"]`).text(text)
				.closest('.sob-mbtn').toggleClass('on', !!on).attr('title', text);
			// Owner (managers only): rows with the owner's colour swatch; rebuilt only when the owners change,
			// so a click inside the open menu never removes the row under the pointer
			this.$root.find('.sob-owner-group').toggle(!!this.data.is_manager);
			const people = [['', __('All'), '']].concat((this.s.owners || []).map(o => [o.user, o.name, o.colour]), [[NONE, __('Unassigned'), '']]);
			const $own = this.$root.find('.sob-owner-pills');
			const osig = people.map(p => p[0] + p[2]).join('|');
			if ($own.attr('data-sig') !== osig) {
				$own.attr('data-sig', osig).html(people.map(p => `<button type="button" class="lg-item sob-mi" data-owner="${esc(p[0])}" aria-pressed="false">${tick}${p[2] ? `<span class="sob-dot" style="background:${esc(p[2])}"></span>` : ''}<span>${esc(p[1])}</span></button>`).join(''));
			}
			$own.find('[data-owner]').each((_, el) => {
				const v = el.getAttribute('data-owner');
				el.setAttribute('aria-pressed', String(v ? owners.includes(v) : !owners.length));
			});
			const names = owners.map(u => (u === NONE ? __('Unassigned') : this.owner_name(u)));
			value('owner', !names.length ? __('All') : names.length <= 2 ? names.join(', ') : __('{0} people', [names.length]), names.length);
			const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(label)}</option>`;
			// Product line: checkbox rows, rebuilt only when the lines change so keyboard focus stays on the ticked box
			const lines = this.s.product_lines || [];
			s.prods = s.prods.filter(p => lines.includes(p));
			const picked = s.prods;
			value('prod', !picked.length ? __('All') : picked.length <= 2 ? picked.join(', ') : __('{0} lines', [picked.length]), picked.length);
			const box = (v, text, on) => `<label class="lg-item sob-mi"><input type="checkbox" data-prod="${esc(v)}"${on ? ' checked' : ''}><span>${esc(text)}</span></label>`;
			const $menu = this.$root.find('.sob-ms-menu');
			const sig = lines.join('|');
			if ($menu.attr('data-sig') !== sig) $menu.attr('data-sig', sig).html(box('', __('All'), !picked.length) + lines.map(p => box(p, p, picked.includes(p))).join(''));
			$menu.find('[data-prod]').each((_, el) => {
				const v = el.getAttribute('data-prod');
				el.checked = v ? picked.includes(v) : !picked.length;
			});
			// Filters: priority and the two switches; the button counts what is on
			const $prio = this.$root.find('.sob-prio');
			const psig = (this.s.lists.priority || []).join('|');
			if ($prio.attr('data-sig') !== psig) $prio.attr('data-sig', psig).html(opt('', __('All'), s.priority) + (this.s.lists.priority || []).map(p => opt(p, p, s.priority)).join(''));
			$prio.val(s.priority || '');
			const more = (lead ? [s.attn] : [s.priority, s.attn, s.closed]).filter(Boolean).length;
			value('more', more ? String(more) : '', more);
			const $q = this.$root.find('.sob-q');
			if ($q.val() !== s.q && document.activeElement !== $q.get(0)) $q.val(s.q);
			const toggle = (k, label) => {
				const $b = this.$root.find(`[data-toggle="${k}"]`);
				if (!$b.children().length) $b.html(`<span>${esc(label)}</span><span class="sob-switch" aria-hidden="true"></span>`);
				$b.attr('aria-checked', String(!!s[k]));
			};
			toggle('attn', __('Needs attention only'));
			this.$root.find('[data-tips-toggle]').attr('aria-checked', String(!this.tips_off));
			toggle('closed', __('Show closed'));
			this.$root.find('[data-toggle="closed"]').attr('title', __('Closed deals hide {0} days after closing', [this.s.hide_closed_after_days || 0]));
		}

		// One menu open at a time; it opens out of its button (Liquid Glass) and keeps inside the page width.
		menu(key, open) {
			const $bar = this.$root.find('.sob-bar');
			$bar.find('[data-menu-panel]').each((_, p) => {
				const on = !!open && p.getAttribute('data-menu-panel') === key;
				if (!on) { p.hidden = true; return; }
				const btn = $bar.find(`[data-menu="${key}"]`).get(0);
				const b = btn.getBoundingClientRect(), r = $bar.get(0).getBoundingClientRect();
				p.hidden = false;
				const w = p.offsetWidth;
				const left = Math.min(b.left - r.left, Math.max(0, r.width - w));
				p.style.left = Math.max(0, left) + 'px';
				p.style.top = (b.bottom - r.top + 8) + 'px';
				p.style.setProperty('--lg-origin', left < b.left - r.left - 1 ? 'top right' : 'top left');
			});
			$bar.find('[data-menu]').each((_, b) => b.setAttribute('aria-expanded', String(!!open && b.getAttribute('data-menu') === key)));
			this._menu = open ? key : null;
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

		co_list(d) { return d._acc ? [] : (d.co_owners || []).filter(u => u && u !== d.deal_owner); }

		// Primary owner, then up to two co-owners overlapped, then "+N".
		avatar(d) {
			const one = (user, cls, role) => {
				const o = this.owner(user);
				const name = o ? o.name : user;
				return `<span class="sob-av${cls}" style="background:${esc((o && o.colour) || '#18181B')}" data-tip="${esc(name + role)}">${esc((name[0] || '?').toUpperCase())}</span>`;
			};
			const co = this.co_list(d);
			const ow = this.own(d);
			const parts = [ow ? one(ow, '', ' (' + (d._acc ? __('relationship manager') : __('owner')) + ')') : `<span class="sob-av none" data-tip="${__('Unassigned')}">?</span>`];
			co.slice(0, 2).forEach(u => parts.push(one(u, ' co', ' (' + __('co-owner') + ')')));
			if (co.length > 2) parts.push(`<span class="sob-av more" data-tip="${esc(co.slice(2).map(u => this.owner_name(u)).join(', '))}">+${co.length - 2}</span>`);
			if (!co.length) return parts[0];
			const label = (d.deal_owner ? this.owner_name(d.deal_owner) : __('Unassigned')) + ' · ' + __('Co-owners') + ': ' + co.map(u => this.owner_name(u)).join(', ');
			return `<span class="sob-avs" role="img" aria-label="${esc(label)}">${parts.join('')}</span>`;
		}

		// a stage or lead status as quiet text with its dot; the colour lives in the dot only
		stage_chip(stage, acc) {
			const st = (acc ? this.status(stage) : this.stage(stage)) || {};
			return `<span class="sob-stage-chip" style="--sob-stage:${esc(st.colour || '#A1A1AA')}"><i class="sob-stage-dot"></i>${esc(__(stage))}</span>`;
		}

		// One deal. Dollars or volume lead depending on the switch; quantities are in lb for fresh frozen, g / kg for extracts.
		card(d, opts) {
			opts = opts || {};
			const lines = d.lines || [];
			const by = this.deal_qty(d);
			const fams = FAMS.filter(f => by[f] > 0);
			let amount = '';
			if (fams.length === 1) {
				const f = fams[0];
				const ppg = lines.length < 2 ? (+(lines[0] || {}).price_per_gram || +d.price_per_gram || 0) : 0;
				amount = qty(by[f], f) + (ppg ? ' @ ' + (f === 'lb' ? money2(ppg * LB) + '/lb' : money2(ppg) + '/g') : '');
			} else if (fams.length) amount = qty_pair(by);
			const prods = lines.length ? lines.map(l => [l.product_line, l.tier].filter(Boolean).join(' · ') + (lines.length > 1 && +l.total_grams ? ' · ' + qty(l.total_grams, this.fam_of(l.product_line)) : ''))
				: [[d.product_line, d.tier].filter(Boolean).join(' · ')].filter(Boolean);
			const volume = this.state.measure === 'volume';
			const big = volume ? (qty_pair(by) || '—') : (d.deal_value ? usd(d.deal_value) : '—');
			const small = volume ? (d.deal_value ? usd(d.deal_value) : '') : amount;
			const line = this.next_date_line(d);
			const meta = this.card_meta(d);
			const flags = this.badges(d);
			const st = this.stage(d.stage) || {};
			const lost = d.is_lost ? `<div class="sob-lost-tag">${svg(ICON.x, 14)}<span>${esc(__('Lost'))}${d.lost_reason ? ' · ' + esc(d.lost_reason) : ''}</span></div>` : '';
			return `
				<div class="sob-card${this.state.sel === d.name ? ' sel' : ''}${this.busy[d.name] ? ' busy' : ''}${opts.co ? ' co' : ''}${d.is_lost ? ' lost' : ''}" role="button" tabindex="0"
					draggable="${this.data.can_write ? 'true' : 'false'}" data-card="${esc(d.name)}"${opts.col ? ` data-from-owner="${esc(opts.col)}"` : ''}
					aria-label="${esc(d.account + (opts.co ? ' (' + __('Co-owner') + ')' : ''))}"
					style="--sob-stage:${esc(st.colour || '#A1A1AA')}">
					${opts.co ? `<span class="sob-card-tag">${__('Co-owner')}</span>` : ''}
					<div class="sob-card-top">
						<span class="sob-card-acc">${this.is_top_priority(d.priority) ? `<span class="sob-prio-dot" data-tip="${esc(__('Priority') + ': ' + d.priority)}"></span>` : ''}${esc(d.account)}</span>
						<span class="sob-card-side">${this.avatar(d)}</span>
					</div>
					${opts.stage_chip && !d.is_lost ? this.stage_chip(d.stage) : ''}
					${lost}
					${prods.length ? `<div class="sob-prods">${prods.map(p => `<span class="sob-prod">${esc(p)}</span>`).join('')}</div>` : ''}
					<div class="sob-card-nums"><b>${esc(big)}</b><span>${esc(small)}</span></div>
					${d.timeline ? `<div class="sob-card-when">${esc(d.timeline)}</div>` : ''}
					${meta ? `<div class="sob-card-meta">${esc(meta)}</div>` : ''}
					${line}
					${flags ? `<div class="sob-badges">${flags}</div>` : ''}
					${this.card_acts(d)}
				</div>`;
		}

		// Shortcuts on every card: work on the deal without opening it. Notes, requirements, follow-up and
		// stage open a pop-up from the button; call, email and purchases appear when the deal has them.
		card_acts(d) {
			const can = this.data.can_write;
			const b = (attrs, icon, label) => `<button type="button" class="sob-ca" ${attrs} draggable="false" data-tip="${esc(label)}" aria-label="${esc(label + ': ' + d.account)}">${svg(icon, 16)}</button>`;
			const n = esc(d.name);
			const acts = [
				b(`data-pop="notes" data-deal="${n}" aria-haspopup="dialog"`, NOTE_ICON, __('Notes: add one or read the latest')),
				b(`data-pop="reqs" data-deal="${n}" aria-haspopup="dialog"`, ICON.box, __('Requirements: product lines, quantity and price')),
			];
			if (can) {
				acts.push(b(`data-pop="follow" data-deal="${n}" aria-haspopup="dialog"`, ICON.clock, __('Set the next follow-up')));
				if (d.is_lost) acts.push(b(`data-reopen="${n}"`, ICON.undo, __('Reopen in {0}', [this.first_stage_of('deal')])));
				else acts.push(b(`data-pop="stage" data-deal="${n}" aria-haspopup="dialog"`, ICON.move, __('Move to another stage')));
			}
			const side = [];
			if (d.phone) side.push(`<a class="sob-ca" data-card-call href="tel:${esc(String(d.phone).replace(/[^0-9+]/g, ''))}" draggable="false" data-tip="${esc(__('Call {0}', [d.phone]))}" aria-label="${esc(__('Call {0}', [d.phone]))}">${svg(ICON.phone, 16)}</a>`);
			if (this.email_to(d)) side.push(b(`data-card-email="${n}"`, ICON.mail, __('Email {0}', [this.email_to(d)])));
			if (this.has_buyer(d)) side.push(b(`data-card-hist="${n}"`, ICON.receipt, __('What this buyer has bought from us')));
			return `<div class="sob-card-acts" role="toolbar" aria-label="${esc(__('Shortcuts'))}">${acts.join('')}${side.length ? `<span class="sob-ca-gap"></span>${side.join('')}` : ''}</div>`;
		}

		// One account on the Leads board: what it is worth a month, what it wants and moves, and its deals.
		// One account on the Leads board. Dollars: its open deals and monthly potential. Volume: what it wants from us
		// each month per product line, in lb or g / kg, and what it moves a week.
		acc_card(a, opts) {
			opts = opts || {};
			const vols = a.volume || [];
			const money = this.state.measure !== 'volume';
			const open = this.deals_of(a).filter(d => !d.is_closed);
			const st = this.status(a.lead_status) || {};
			const flags = this.badges(a);
			const deals = [];
			if (a.open_deals) deals.push(`<span class="sob-dc open" data-tip="${esc(__('Deals still in progress with {0}', [a.account]))}">${svg(ICON.deal, 14)}<b>${a.open_deals}</b>${esc(a.open_deals === 1 ? __('open deal') : __('open deals'))}</span>`);
			if (a.won_deals) deals.push(`<span class="sob-dc won"><b>${a.won_deals}</b>${esc(__('won'))}</span>`);
			if (a.lost_deals) deals.push(`<span class="sob-dc lost"><b>${a.lost_deals}</b>${esc(__('lost'))}</span>`);
			let body;
			if (money) {
				// what they buy (volume rows), else what the open deals are for
				const src = vols.length ? vols : open.flatMap(d => ((d.lines || []).length ? d.lines : [d]));
				const prods = [...new Set(src.map(x => [x.product_line, x.tier].filter(Boolean).join(' · ')).filter(Boolean))];
				const nums = +a.open_value || +a.monthly_potential;
				body = `${prods.length ? `<div class="sob-prods">${prods.map(p => `<span class="sob-prod">${esc(p)}</span>`).join('')}</div>` : ''}
					${nums ? `<div class="sob-card-nums"><b>${+a.open_value ? usd(a.open_value) : ''}</b><span${+a.monthly_potential ? ` data-tip="${esc(__('Monthly potential from the volume they want'))}"` : ''}>${+a.monthly_potential ? esc(usd(a.monthly_potential) + '/' + __('mo')) : ''}</span></div>` : ''}`;
			} else if (vols.length) {
				const rows = vols.slice(0, 3).map(v => {
					const c = this.vol_calc(v);
					const f = this.fam_of(v.product_line);
					const moves = +v.weekly_volume ? (v.activity === 'Produce' ? __('makes {0} a week', [qty(c.weekly_grams, f)]) : __('buys {0} a week', [qty(c.weekly_grams, f)])) : '';
					return `<div class="sob-vrow"><span>${esc([v.product_line, v.tier].filter(Boolean).join(' · '))}</span><b>${c.monthly_grams ? esc(qty(c.monthly_grams, f) + '/' + __('mo')) : '—'}</b></div>
						${moves ? `<div class="sob-vrow-sub">${esc(moves)}</div>` : ''}`;
				}).join('');
				body = `<div class="sob-vrows">${rows}${vols.length > 3 ? `<div class="sob-vrow-sub">${esc(__('+{0} more product lines', [vols.length - 3]))}</div>` : ''}</div>`;
			} else {
				body = `<div class="sob-card-meta sob-novol">${__('No volume yet')}</div>`;
			}
			return `
				<div class="sob-card sob-acc${this.state.sel === a.name ? ' sel' : ''}${this.busy[a.name] ? ' busy' : ''}" role="button" tabindex="0"
					draggable="${this.can_edit(a) ? 'true' : 'false'}" data-card="${esc(a.name)}"${opts.col ? ` data-from-owner="${esc(opts.col)}"` : ''}
					aria-label="${esc(a.account)}" style="--sob-stage:${esc(st.colour || '#A1A1AA')}">
					<div class="sob-card-top">
						<span class="sob-card-acc">${esc(a.account)}</span>
						<span class="sob-card-side">${this.avatar(a)}</span>
					</div>
					${opts.stage_chip ? this.stage_chip(a.lead_status, true) : ''}
					${body}
					${deals.length ? `<div class="sob-card-deals">${deals.join('')}</div>` : ''}
					${this.next_date_line(a)}
					${flags ? `<div class="sob-badges">${flags}</div>` : ''}
					${this.acc_acts(a)}
				</div>`;
		}

		acc_acts(a) {
			const can = this.can_edit(a);
			const b = (attrs, icon, label) => `<button type="button" class="sob-ca" ${attrs} draggable="false" data-tip="${esc(label)}" aria-label="${esc(label + ': ' + a.account)}">${svg(icon, 16)}</button>`;
			const n = esc(a.name);
			const acts = [
				b(`data-pop="notes" data-deal="${n}" aria-haspopup="dialog"`, NOTE_ICON, __('Notes: add one or read the latest')),
				b(`data-pop="vol" data-deal="${n}" aria-haspopup="dialog"`, ICON.scale, __('Volume: what they buy each week and want from us')),
			];
			if (can) {
				acts.push(b(`data-pop="follow" data-deal="${n}" aria-haspopup="dialog"`, ICON.clock, __('Set the next follow-up')));
				acts.push(b(`data-pop="stage" data-deal="${n}" aria-haspopup="dialog"`, ICON.move, __('Change the lead status')));
			}
			if (this.data.can_create) acts.push(b(`data-new-deal="${n}"`, ICON.plus, __('Start a new deal with this account')));
			const side = [];
			if (a.phone) side.push(`<a class="sob-ca" data-card-call href="tel:${esc(String(a.phone).replace(/[^0-9+]/g, ''))}" draggable="false" data-tip="${esc(__('Call {0}', [a.phone]))}" aria-label="${esc(__('Call {0}', [a.phone]))}">${svg(ICON.phone, 16)}</a>`);
			if (this.email_to(a)) side.push(b(`data-card-email="${n}"`, ICON.mail, __('Email {0}', [this.email_to(a)])));
			if (this.has_buyer(a)) side.push(b(`data-card-hist="${n}"`, ICON.receipt, __('What this buyer has bought from us')));
			return `<div class="sob-card-acts" role="toolbar" aria-label="${esc(__('Shortcuts'))}">${acts.join('')}${side.length ? `<span class="sob-ca-gap"></span>${side.join('')}` : ''}</div>`;
		}

		acc_col_sub(items) {
			const n = `${items.length} ${items.length === 1 ? __('account') : __('accounts')}`;
			if (this.state.measure === 'volume') {
				const by = { lb: 0, g: 0 };
				items.forEach(a => { const q = this.acc_qty(a); by.lb += q.month.lb; by.g += q.month.g; });
				return `${n} · ${qty_pair(by) ? qty_pair(by) + '/' + __('mo') : __('no volume yet')}`;
			}
			const open = items.reduce((a, x) => a + (+x.open_value || 0), 0);
			const pot = items.reduce((a, x) => a + (+x.monthly_potential || 0), 0);
			return `${n} · ${usd(open)}${pot ? ` · ${usd(pot)}/${__('mo')}` : ''}`;
		}

		render_board_acc($v, list) {
			const html = this.stages_of('lead').map(st => {
				const items = this.sorted_accs(list.filter(a => a.lead_status === st.name));
				return `
					<section class="sob-col" data-lg-col data-drop-stage="${esc(st.name)}" aria-label="${esc(st.name)}" style="--sob-stage:${esc(st.colour || '#A1A1AA')}">
						<header class="sob-col-head">
							<div class="sob-col-title"><span>${esc(__(st.name))}</span><span class="sob-col-prob" data-tip="${esc(__('Weighted figures count {0}% of the potential of accounts in {1}', [+st.probability, __(st.name)]))}">${+st.probability}%</span></div>
							<div class="sob-col-sub">${esc(this.acc_col_sub(items))}</div>
						</header>
						${items.map(a => this.acc_card(a)).join('')}
						${items.length ? '' : `<div class="sob-col-empty">${this.data.can_write_account ? __('Drop an account here') : __('No accounts')}</div>`}
					</section>`;
			}).join('');
			this.keep_scroll($v, `<div class="sob-hint">${__('One card per account. Drag it to change its lead status, or open it to record volume, see its deals and start a new one.')}</div><div class="sob-scroll" data-lg-hscroll><div class="sob-columns">${html}</div></div>`, '.sob-scroll');
		}

		col_sub(items) {
			const n = `${items.length} ${items.length === 1 ? __('deal') : __('deals')}`;
			if (this.state.measure === 'volume') {
				const by = { lb: 0, g: 0 };
				items.forEach(d => { const q = this.deal_qty(d); by.lb += q.lb; by.g += q.g; });
				return `${n} · ${qty_pair(by) || __('no quantity yet')}`;
			}
			const v = items.reduce((a, d) => a + (+d.deal_value || 0), 0);
			const w = items.reduce((a, d) => a + (+d.weighted_value || 0), 0);
			return `${n} · ${usd(v)} · ${usd(w)} ${__('weighted')}`;
		}

		keep_scroll($v, html, sel) {
			const left = $v.find(sel).scrollLeft() || 0;
			$v.html(html);
			$v.find(sel).scrollLeft(left);
		}

		// Lost deals get no column of their own: they stay at the foot of the first stage (Active Opportunity),
		// where they can be reopened or dragged back into the pipeline.
		render_board($v, list) {
			const lost = this.lost_stage();
			const first = this.first_stage_of('deal');
			const gone = lost ? list.filter(d => d.stage === lost.name).sort((a, b) => ((b.stage_changed_on || b.modified || '') > (a.stage_changed_on || a.modified || '') ? 1 : -1)) : [];
			const html = this.stages_of('deal').filter(st => !lost || st.name !== lost.name).map(st => {
				const items = this.sorted_cards(list.filter(d => d.stage === st.name));
				const extra = st.name === first ? gone : [];
				return `
					<section class="sob-col" data-lg-col data-drop-stage="${esc(st.name)}" aria-label="${esc(st.name)}" style="--sob-stage:${esc(st.colour || '#A1A1AA')}">
						<header class="sob-col-head">
							<div class="sob-col-title"><span>${esc(__(st.name))}</span><span class="sob-col-prob" data-tip="${esc(__('Chance to win from {0}. Weighted value = value × {1}%', [__(st.name), +st.probability]))}">${+st.probability}%</span></div>
							<div class="sob-col-sub">${esc(this.col_sub(items))}</div>
						</header>
						${items.map(d => this.card(d)).join('')}
						${items.length || extra.length ? '' : `<div class="sob-col-empty">${this.data.can_write ? __('Drop a deal here') : __('No deals')}</div>`}
						${extra.length ? `<div class="sob-lost-sep" role="separator" data-tip="${esc(__('Lost deals stay here with their reason. Drag one into a stage or press Reopen to work on it again'))}"><span>${esc(__('Lost'))} · ${extra.length}</span><small>${esc(__('Drag back or reopen to work on it again'))}</small></div>${extra.map(d => this.card(d)).join('')}` : ''}
					</section>`;
			}).join('');
			this.keep_scroll($v, `<div class="sob-hint">${__('Drag a card to another stage, or click it to open the deal. Lost deals stay at the bottom of {0}.', [esc(first)])}</div><div class="sob-scroll" data-lg-hscroll><div class="sob-columns">${html}</div></div>`, '.sob-scroll');
		}

		// Deals by owner, or accounts by relationship manager on the Leads board
		render_owner($v, list) {
			const s = this.state;
			const acc = s.board === 'lead';
			const picked = s.owners || [];
			let cols = (this.s.owners || []).filter(o => !picked.length || picked.includes(o.user)).map(o => ({ id: o.user, name: o.name, colour: o.colour }));
			if (this.data.is_manager) {
				if (!picked.length || picked.includes(NONE)) cols.push({ id: NONE, name: __('Unassigned'), colour: '' });
			} else {
				cols = cols.filter(c => c.id === this.data.user);
				if (!cols.length) cols = [{ id: this.data.user, name: acc ? __('My accounts') : __('My deals'), colour: '' }];
			}
			const today = this.data.today;
			const sts = this.stages_of(acc ? 'lead' : 'deal');
			const order = st => { const i = sts.findIndex(x => x.name === st); return i < 0 ? 99 : i; };
			const html = cols.map(c => {
				const shared = d => c.id !== NONE && this.own(d) !== c.id && this.co_list(d).includes(c.id);
				const items = list.filter(d => (this.own(d) || NONE) === c.id || shared(d))
					.sort((a, b) => order(this.stage_name(a)) - order(this.stage_name(b)) ||
						(acc ? (+b.monthly_potential || 0) - (+a.monthly_potential || 0) : this.prio_rank(a.priority) - this.prio_rank(b.priority)));
				const overdue = items.filter(d => !d.is_closed && d.next_step_due && d.next_step_due < today).length;
				const unassigned = c.id === NONE;
				return `
					<section class="sob-col sob-owner-col${unassigned && items.length ? ' warn' : ''}" ${unassigned ? '' : `data-drop-owner="${esc(c.id)}"`} aria-label="${esc(c.name)}">
						<header class="sob-col-head">
							<div class="sob-col-title"><span>${c.colour ? `<span class="sob-dot" style="background:${esc(c.colour)}"></span>` : ''}${esc(c.name)}</span>
								${overdue ? `<span class="sob-badge act">${overdue} ${__('overdue')}</span>` : ''}</div>
							<div class="sob-col-sub">${esc(acc ? this.acc_col_sub(items) : this.col_sub(items))}</div>
							${unassigned && items.length ? `<div class="sob-col-note">${acc ? __('Drag these accounts to a relationship manager') : __('Drag these deals to an owner')}</div>` : ''}
						</header>
						${items.map(d => (acc ? this.acc_card(d, { stage_chip: true, col: c.id }) : this.card(d, { stage_chip: true, co: shared(d), col: c.id }))).join('')}
						${items.length ? '' : `<div class="sob-col-empty">${unassigned ? (acc ? __('Every account has an owner') : __('Every deal has an owner')) : (acc ? __('Drop an account here to reassign') : __('Drop a deal here to reassign'))}</div>`}
					</section>`;
			}).join('');
			const hint = acc ? __('Drag an account to another relationship manager. They are notified.')
				: __('Drag a card to another owner to change its owner. The new owner is notified. Shared deals also appear in each co-owner\'s column.');
			this.keep_scroll($v, `<div class="sob-hint">${hint}</div><div class="sob-scroll" data-lg-hscroll><div class="sob-columns">${html}</div></div>`, '.sob-scroll');
		}

		// ---------- projection (Leads board): the volume recorded on accounts, rolled up ----------

		// Projection (Leads board): the volume and demand recorded on accounts, added up. Each product line is shown in its
		// own unit (lb for fresh frozen, g / kg for extracts); rows that mix lines show both.
		render_projection($v, list) {
			const blank = () => ({ accounts: new Set(), with_vol: new Set(), week: { lb: 0, g: 0 }, month: { lb: 0, g: 0 }, value: 0, weighted: 0, deals: 0 });
			const lines = {}, statuses = {};
			const add = (r, a, v) => {
				r.accounts.add(a.name);
				if (!v) return;
				const c = this.vol_calc(v);
				const f = this.fam_of(v.product_line);
				r.with_vol.add(a.name);
				r.week[f] += c.weekly_grams;
				r.month[f] += c.monthly_grams;
				r.value += c.monthly_value;
				r.weighted += c.monthly_value * (+a.probability || 0) / 100;
			};
			list.forEach(a => {
				const st = statuses[a.lead_status] = statuses[a.lead_status] || Object.assign(blank(), { key: a.lead_status });
				add(st, a, null);
				st.deals += +a.open_value || 0;
				(a.volume || []).forEach(v => {
					const k = v.product_line || __('Other');
					add(lines[k] = lines[k] || Object.assign(blank(), { key: k }), a, v);
					add(st, a, v);
				});
			});
			const order = this.s.product_lines || [];
			const line_rows = Object.values(lines).sort((a, b) => b.value - a.value || order.indexOf(a.key) - order.indexOf(b.key));
			const status_rows = this.stages_of('lead').map(st => statuses[st.name]).filter(Boolean);
			const tot = rows => rows.reduce((t, r) => {
				FAMS.forEach(f => { t.week[f] += r.week[f]; t.month[f] += r.month[f]; });
				t.value += r.value; t.weighted += r.weighted; t.deals += r.deals;
				r.accounts.forEach(x => t.accounts.add(x)); r.with_vol.forEach(x => t.with_vol.add(x));
				return t;
			}, blank());
			const q = by => esc(qty_pair(by));
			const wk = by => ({ lb: by.lb / WPM, g: by.g / WPM });
			const m = n => (n ? usd(n) : '');
			const head = (first, deals) => `<thead><tr><th><span>${esc(first)}</span></th>
				<th class="r"><span>${__('Accounts')}</span></th>
				${deals ? `<th class="r"><span data-tip="${esc(__('Accounts in this status that have volume recorded'))}">${__('With volume')}</span></th>` : ''}
				<th class="r"><span data-tip="${esc(__('What they procure or produce in a week'))}">${__('Volume / week')}</span></th>
				<th class="r"><span data-tip="${esc(__('Monthly demand spread over 4.33 weeks'))}">${__('Wants / week')}</span></th>
				<th class="r"><span data-tip="${esc(__('What they want from us each month'))}">${__('Wants / month')}</span></th>
				<th class="r money"><span data-tip="${esc(__('Wants / month × price'))}">${__('Potential / month')}</span></th>
				<th class="r money"><span data-tip="${esc(__('Potential × the lead-status probability'))}">${__('Weighted / month')}</span></th>
				<th class="r money"><span>${__('Potential / year')}</span></th>
				${deals ? `<th class="r money"><span data-tip="${esc(__('Value of the open deals with these accounts'))}">${__('Open deals')}</span></th>` : ''}</tr></thead>`;
			const cells = (r, deals) => `<td class="r">${r.accounts.size}</td>${deals ? `<td class="r">${r.with_vol.size}</td>` : ''}
				<td class="r">${q(r.week)}</td><td class="r">${q(wk(r.month))}</td><td class="r">${q(r.month)}</td>
				<td class="r money">${m(r.value)}</td><td class="r money">${m(r.weighted)}</td><td class="r money">${m(r.value * 12)}</td>
				${deals ? `<td class="r money">${m(r.deals)}</td>` : ''}`;
			const table = (first, rows, opts) => `<div class="sob-table-wrap"><table class="sob-table sob-proj-t">${head(first, opts.deals)}
				<tbody>${rows.map(r => `<tr class="sob-proj-row"${opts.colour ? ` style="--sob-stage:${esc(opts.colour(r.key))}"` : ''}>
					<td>${opts.colour ? '<i class="sob-stage-dot"></i>' : ''}<b>${esc(__(r.key))}</b>${opts.unit ? `<span class="sob-unit">${esc(this.fam_of(r.key) === 'lb' ? 'lb' : 'g / kg')}</span>` : ''}</td>${cells(r, opts.deals)}</tr>`).join('') ||
					`<tr><td colspan="${opts.deals ? 10 : 8}" class="sob-empty">${__('No volume recorded yet. Open an account and add what it procures or produces and what it wants from us')}</td></tr>`}</tbody>
				<tfoot><tr><td>${__('Total')}</td>${cells(tot(rows), opts.deals)}</tr></tfoot></table></div>`;
			const top = list.filter(a => +a.monthly_potential > 0).sort((a, b) => b.monthly_potential - a.monthly_potential).slice(0, 15);
			const probs = this.stages_of('lead').map(st => `${__(st.name)} ${+st.probability}%`).join(' · ');
			$v.html(`<div class="sob-proj">
				<div class="sob-hint">${__('From the volume and demand recorded on each account, in lb for fresh frozen and g or kg for extracts. Weighted uses the lead-status probability: {0}', [esc(probs)])}</div>
				<section class="sob-proj-sec"><h3>${__('By product line')}</h3>${table(__('Product line'), line_rows, { unit: true })}</section>
				<section class="sob-proj-sec"><h3>${__('By lead status')}</h3>${table(__('Lead status'), status_rows, { deals: true, colour: k => (this.status(k) || {}).colour || '#A1A1AA' })}</section>
				<section class="sob-proj-sec"><h3>${__('Biggest accounts')}</h3>
					<div class="sob-table-wrap"><table class="sob-table">
						<thead><tr><th><span>${__('Account')}</span></th><th><span>${__('Lead status')}</span></th><th><span>${__('Products')}</span></th>
							<th class="r"><span>${__('Volume / week')}</span></th><th class="r"><span>${__('Wants / month')}</span></th>
							<th class="r money"><span>${__('Potential / month')}</span></th><th class="r money"><span>${__('Weighted / month')}</span></th><th class="r money"><span>${__('Open deals')}</span></th></tr></thead>
						<tbody>${top.map(a => { const aq = this.acc_qty(a); return `<tr data-open="${esc(a.name)}" class="${this.state.sel === a.name ? 'sel' : ''}">
							<td><b>${esc(a.account)}</b></td><td>${this.stage_chip(a.lead_status, true)}</td>
							<td>${esc([...new Set((a.volume || []).map(v => v.product_line))].join(', '))}</td>
							<td class="r">${q(aq.week)}</td><td class="r">${q(aq.month)}</td>
							<td class="r money">${m(a.monthly_potential)}</td><td class="r money">${m(a.weighted_potential)}</td><td class="r money">${m(a.open_value)}</td></tr>`; }).join('') ||
							`<tr><td colspan="8" class="sob-empty">${__('No account has a monthly potential yet')}</td></tr>`}</tbody>
					</table></div></section>
			</div>`);
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
				<div class="sob-scroll" data-lg-hscroll><div class="sob-cal ${s.cal_mode}">
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
				case 'owner': return v ? this.owner_name(v) : __('Unassigned');
				case 'qty': return qty_pair(this.acc_qty(d)[c[0] === 'vol_week' ? 'week' : 'month']);
				case 'dqty': return qty_pair(this.deal_qty(d));
				case 'dprice': {
					const by = this.deal_qty(d);
					const fams = FAMS.filter(f => by[f] > 0);
					if (fams.length !== 1) return '';
					const grams = by[fams[0]], value = this.calc_value(d);
					return value ? money2(fams[0] === 'lb' ? value / (grams / LB) : value / grams) + '/' + (fams[0] === 'lb' ? 'lb' : 'g') : '';
				}
				default:
					if ((c[0] === 'product_line' || c[0] === 'tier') && (d.lines || []).length > 1) return [...new Set(d.lines.map(l => l[c[0]]).filter(Boolean))].join(', ');
					if (c[0] === 'products') return [...new Set((d.volume || []).map(x => x.product_line))].join(', ');
					if (c[0] === 'customer' && d.customer_title) return d.customer_title;
					if (c[0] === 'lead' && d.lead_title) return d.lead_title;
					return v == null ? '' : v;
			}
		}

		// The details a record still needs, as the List view columns to highlight. Closed records need none.
		need_of(d) {
			const n = [];
			if (d._acc) {
				if (d.is_closed) return n;
				if (!d.account_owner) n.push('account_owner');
				if (!d.contact_name) n.push('contact_name');
				if (!d.phone && !d.email) n.push('phone', 'email');
				if (!(d.volume || []).length) n.push('products', 'vol_week', 'vol_month');
				return n;
			}
			if (d.is_closed) return d.is_lost && !d.lost_reason ? ['lost_reason'] : n;
			if (!d.deal_owner) n.push('deal_owner');
			if (!this.lines_of(d).some(l => l.product_line) && !d.product_line) n.push('product_line');
			if (!+d.deal_value) n.push('deal_value', 'total_grams', 'price_per_gram');
			const st = this.stage(d.stage) || {};
			if (st.name && st.name !== this.s.first_stage && !d.next_step_due) n.push('next_step_due');
			if (!d.contact_name) n.push('contact_name');
			if (!d.phone && !d.email && !d.customer_email) n.push('phone', 'email');
			return n;
		}

		// One cell the user can fill in place. Text saves on Enter or when leaving the cell; Enter moves down a row.
		edit_cell(d, c, kind) {
			const [k, arg] = kind.split(':');
			const name = esc(d.name);
			const need = this.need_of(d).includes(c[0]);
			const ph = need ? __('Add') : '';
			const label = esc(__(c[1]) + ' · ' + d.account);
			const shown = this.cell_value(d, c);
			const input = (type, field, v, extra) => `<input class="sob-inline sob-cell-in" type="${type}" data-inline="${name}" data-field="${field}" data-orig="${esc(v == null ? '' : v)}"
				value="${esc(v == null ? '' : v)}" placeholder="${esc(ph)}" aria-label="${label}"${extra || ''}>`;
			const money_in = (field, v, extra) => `<input class="sob-inline sob-cell-in" type="text" inputmode="decimal" data-money="1" data-inline="${name}" data-field="${field}"
				data-orig="${v ? esc(v) : ''}" data-raw="${v ? esc(v) : ''}" value="${v ? esc(usd(v)) : ''}" placeholder="${esc(ph)}" aria-label="${label}"${extra}>`;
			const select = (field, opts) => {
				const cur = d[field] || '';
				if (cur && !opts.includes(cur)) opts = opts.concat([cur]);
				return `<select class="sob-inline sob-cell-in" data-inline="${name}" data-field="${field}" data-orig="${esc(cur)}" aria-label="${label}">
					${[''].concat(opts).map(o => `<option value="${esc(o)}"${o === cur ? ' selected' : ''}>${esc(o || (need ? __('Add') : '—'))}</option>`).join('')}</select>`;
			};
			const btn = (attrs, text, empty) => `<button type="button" class="sob-cell-btn${text || empty === '—' ? '' : ' empty'}" ${attrs} aria-label="${label}">${esc(text || empty)}</button>`;
			switch (k) {
				case 'text': case 'tel': case 'email': return input(k, c[0], d[c[0]], k === 'text' ? '' : ' inputmode="' + k + '"');
				// money cells read "$8,000" and turn into a plain number while being edited
				case 'num': return money_in(c[0], +d[c[0]] || 0, '');
				// typing a deal value sets the manual value; empty goes back to quantity × price
				case 'override': return money_in('value_override', +d.deal_value || 0, ' data-tip="' + esc(__('Typing a value sets it by hand; clear it to use quantity × price')) + '"');
				case 'date': return input('date', c[0], d[c[0]] || '');
				case 'list': return select(c[0], ((this.s.lists || {})[arg] || []).slice());
				case 'opts': return select(c[0], arg.split('|'));
				case 'reqs': return btn(`data-pop="reqs" data-deal="${name}" aria-haspopup="dialog"`, shown,
					{ product_line: __('Add product'), tier: '—', total_grams: __('Add quantity'), price_per_gram: __('Add price') }[c[0]] || __('Add'));
				case 'vol': return btn(`data-pop="vol" data-deal="${name}" aria-haspopup="dialog"`, shown, __('Add volume'));
				case 'buyer': return btn(`data-cell-buyer="${name}"`, shown, __('Link buyer'));
				default: return esc(shown);
			}
		}

		// The sheet. Most cells can be filled in place; product and volume cells open their editors; cells a record
		// still needs are tinted, and "Missing info" keeps only the records with gaps. Focus and typing survive saves.
		render_list($v, list) {
			const s = this.state;
			const acc = s.board === 'lead';
			const ALL = acc ? ACC_COLS : LIST_COLS;
			const EDIT = acc ? ACC_EDIT : DEAL_EDIT;
			const cols = (acc ? this.acc_cols : this.cols).map(k => ALL.find(c => c[0] === k)).filter(Boolean);
			const sk = ALL.some(c => c[0] === s.sort.key) ? s.sort.key : '';
			const gaps = list.filter(d => this.need_of(d).length).length;
			const rows = s.need ? list.filter(d => this.need_of(d).length) : list.slice();
			if (sk) {
				const col = ALL.find(c => c[0] === sk) || [];
				const numeric = ['num', 'money', 'money2', 'pct', 'qty', 'dqty'].includes(col[2]);
				const sts = this.stages_of(acc ? 'lead' : 'deal');
				// quantities sort by grams (lb rows counted in grams too)
				const grams = d => { const q = this.acc_qty(d)[sk === 'vol_week' ? 'week' : 'month']; return q.lb + q.g; };
				const val = d => col[2] === 'owner' ? (d[sk] ? this.owner_name(d[sk]) : '') : col[2] === 'stage' ? sts.findIndex(x => x.name === this.stage_name(d))
					: sk === 'priority' ? this.prio_rank(d.priority) : sk === 'products' ? this.cell_value(d, col) : col[2] === 'qty' ? grams(d)
					: col[2] === 'dqty' ? this.deal_qty(d).lb + this.deal_qty(d).g : d[sk];
				rows.sort((a, b) => {
					let x = val(a), y = val(b);
					if (numeric) return ((+x || 0) - (+y || 0)) * s.sort.dir;
					if (col[2] === 'stage' || sk === 'priority') return ((+val(a)) - (+val(b))) * s.sort.dir;
					x = x == null || x === '' ? null : String(x).toLowerCase(); y = y == null || y === '' ? null : String(y).toLowerCase();
					if (x === null) return 1; if (y === null) return -1;
					return (x < y ? -1 : x > y ? 1 : 0) * s.sort.dir;
				});
			}
			const sel = (d, field, cur, opts, c) => `<select class="sob-inline sob-cell-in" data-inline="${esc(d.name)}" data-field="${field}" data-orig="${esc(cur || '')}" aria-label="${esc(__(c[1]) + ' · ' + d.account)}">${opts.map(o => `<option value="${esc(o[0])}"${(cur || '') === o[0] ? ' selected' : ''}>${esc(o[1])}</option>`).join('')}</select>`;
			const owner_opts = d => [['', __('Unassigned')]].concat(this.owner_choices(d).map(o => [o.user, o.name]));
			const editable = (d, c) => {
				const can = acc ? this.can_edit(d) : this.data.can_write;
				if (!can) return false;
				if (['stage', 'priority', 'date_edit'].includes(c[2])) return true;
				if (c[2] === 'owner') return !acc || this.data.is_manager;
				return !!EDIT[c[0]] && this.can_edit(d);
			};
			const cell = (d, c) => {
				if (editable(d, c)) {
					if (c[2] === 'stage') return sel(d, acc ? 'lead_status' : 'stage', this.stage_name(d), this.stages_of(acc ? 'lead' : 'deal').map(x => [x.name, __(x.name)]), c);
					if (c[2] === 'owner') return sel(d, this.own_field(d), this.own(d), owner_opts(d), c);
					if (c[2] === 'priority') return sel(d, 'priority', d.priority, (this.s.lists.priority || []).map(x => [x, x]), c);
					return this.edit_cell(d, c, EDIT[c[0]] || 'date');
				}
				if (c[0] === 'account') return `<b>${esc(d.account)}</b>${(d.flags || []).some(f => f.kind === 'action') ? ' <span class="sob-flag-dot" data-tip="' + esc(d.flags.map(f => f.label).join(', ')) + '"></span>' : ''}`;
				return esc(this.cell_value(d, c));
			};
			const total = k => rows.reduce((a, d) => a + (+d[k] || 0), 0);
			const fam_total = f => { const by = { lb: 0, g: 0 }; rows.forEach(d => { const q = f(d); by.lb += q.lb; by.g += q.g; }); return qty_pair(by); };
			const totals = cols.map((c, i) => {
				if (c[2] === 'dqty') return fam_total(d => this.deal_qty(d));
				if (['money', 'money2'].includes(c[2]) && c[0] !== 'value_override') return usd(total(c[0]));
				if (acc && c[2] === 'num' && c[0] !== 'days_in_stage') return n0(total(c[0]));
				if (c[2] === 'qty') return fam_total(d => this.acc_qty(d)[c[0] === 'vol_week' ? 'week' : 'month']);
				return i === 0 ? __('Total') + ` (${rows.length})` : '';
			});
			// sheet colours: money columns carry a blue tint, an overdue follow-up date gets the red aging fill, gaps get amber
			const today = this.data.today;
			const kls = (c, d) => [
				['num', 'money', 'money2', 'pct', 'qty', 'dqty', 'dprice'].includes(c[2]) ? 'r' : '',
				['money', 'money2'].includes(c[2]) ? 'money' : '',
				d && c[0] === 'next_step_due' && !d.is_closed && d.next_step_due && d.next_step_due < today ? 'late' : '',
				d && editable(d, c) ? 'ed' : '',
				d && this.need_of(d).includes(c[0]) ? 'need' : '',
				c[0] === 'account' ? 'pin' : '',
			].filter(Boolean).join(' ');
			const arrow = c => sk === c[0] ? svg(s.sort.dir > 0 ? ICON.up : ICON.down, 12) : '';
			// keep the cell being typed in (and what is typed) across the re-render a save causes
			const act = document.activeElement;
			const keep = act && $v.get(0).contains(act) && act.matches('.sob-cell-in') ? {
				name: act.getAttribute('data-inline'), field: act.getAttribute('data-field'), value: act.value,
				typed: act.value !== (act.getAttribute('data-orig') || ''), range: (() => { try { return [act.selectionStart, act.selectionEnd]; } catch (x) { return null; } })(),
			} : null;
			const left = $v.find('.sob-table-wrap').scrollLeft() || 0;
			const picked = acc ? this.acc_cols : this.cols;
			const what = acc ? __('owner, contact, phone or email, volume') : __('owner, product, value, follow-up, contact, phone or email');
			// replacing a focused, edited input makes the browser fire "change" with a half-typed value: ignore it
			this._list_rendering = true;
			$v.html(`
				<div class="sob-list-bar">
					<span class="sob-muted">${pl(rows.length, acc ? __('account') : __('deal'), acc ? __('accounts') : __('deals'))}${s.need ? ' ' + __('with missing info') : ''}</span>
					<div class="sob-list-acts">
						<button type="button" class="sob-btn sm${s.need ? ' primary' : ''}" data-act="need" aria-pressed="${!!s.need}"
							data-tip="${esc(__('Only the rows that still need: {0}. Those cells are tinted', [what]))}">${__('Missing info')} · ${n0(gaps)}</button>
						<div class="sob-colpick">
							<button type="button" class="sob-btn sm" data-act="cols" aria-expanded="false">${__('Columns')}</button>
							<div class="sob-colpick-menu lg lg--thick lg-in" style="--lg-origin: top right" hidden>
								${ALL.map(c => `<label><input type="checkbox" data-col="${c[0]}"${picked.includes(c[0]) ? ' checked' : ''}> ${esc(__(c[1]))}</label>`).join('')}
								<button type="button" class="sob-btn sm" data-act="cols-reset">${__('Reset to default')}</button>
							</div>
						</div>
					</div>
				</div>
				<div class="sob-table-wrap"><table class="sob-table">
					<thead><tr>${cols.map(c => `<th class="${kls(c)}"><button type="button" data-sort="${c[0]}" class="${sk === c[0] ? 'on' : ''}">${esc(__(c[1]))}${arrow(c)}</button></th>`).join('')}</tr></thead>
					<tbody>${rows.map(d => `<tr data-open="${esc(d.name)}" class="${s.sel === d.name ? 'sel' : ''}${this.busy[d.name] ? ' busy' : ''}">${cols.map(c => `<td class="${kls(c, d)}">${cell(d, c)}</td>`).join('')}</tr>`).join('') ||
						`<tr><td colspan="${cols.length}" class="sob-empty">${s.need ? __('Nothing missing. Every row has the details it needs') : acc ? __('No accounts match these filters') : __('No deals match these filters')}</td></tr>`}</tbody>
					<tfoot><tr>${totals.map((t, i) => `<td class="${kls(cols[i])}">${esc(t)}</td>`).join('')}</tr></tfoot>
				</table></div>`);
			this._list_rendering = false;
			$v.find('.sob-table-wrap').scrollLeft(left);
			if (keep) {
				const el = $v.find(`.sob-cell-in[data-inline="${CSS.escape(keep.name)}"][data-field="${CSS.escape(keep.field)}"]`).get(0);
				if (el) {
					if (keep.typed && el.tagName === 'INPUT') el.value = keep.value;
					el.focus({ preventScroll: true });
					if (keep.range) { try { el.setSelectionRange(keep.range[0], keep.range[1]); } catch (x) { /* date / number inputs */ } }
				}
			}
		}

		owner_choices(d) {
			const all = this.s.owners || [];
			if (this.data.is_manager) return all;
			return all.filter(o => o.user === this.data.user || (d && o.user === this.own(d)));
		}

		// ---------- drawer ----------

		// Buyer, product and notes: owners on their own deals, pipeline managers on any deal (server checks the same).
		can_edit(d) {
			if (d && d._acc) {
				// the relationship manager, anyone working a deal on the account, or a pipeline manager (server checks the same)
				const u = this.data.user;
				return !!(this.data.can_write_account && (this.data.is_manager || d.account_owner === u ||
					this.deals_of(d).some(x => x.deal_owner === u || this.co_list(x).includes(u))));
			}
			return !!(d && this.data.can_write && (this.data.is_manager || d.deal_owner === this.data.user || this.co_list(d).includes(this.data.user)));
		}

		// Only the primary owner or a pipeline manager changes the co-owners.
		can_edit_owners(d) {
			return !!(d && !d._acc && this.data.can_write && (this.data.is_manager || d.deal_owner === this.data.user));
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
			if (tile) return `<div class="sob-tile sob-ed" role="button" tabindex="0" data-ed="${field}" data-tip="${esc(__('Click to edit, Enter to save'))}"><span>${esc(label)} ${pen}</span><b>${shown || empty}</b></div>`;
			return `<div class="sob-f sob-ed" role="button" tabindex="0" data-ed="${field}" data-tip="${esc(__('Click to edit, Enter to save'))}"><span>${esc(label)}</span><span>${shown || empty}${pen}</span></div>`;
		}

		// Requirement lines: a deal can ask for several product lines. Changes save as soon as a field changes.
		// Requirement lines: a deal can ask for several product lines. Fresh frozen is entered in lb and $/lb, extracts in g
		// and $/g; everything is stored in grams. Changes save as soon as a field changes.
		req_editor(d, opts) {
			opts = opts || {};
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
				const lb = this.fam_of(l.product_line) === 'lb';
				const f = lb ? 'lb' : 'g';
				const amount = (+l.total_grams || 0) * (+l.price_per_gram || 0);
				const stock = l.stock_grams == null || l.draft ? '' : (+l.short > 0
					? `<span class="sob-badge act" data-tip="${esc(__('{0} available in the sellable warehouses', [qty(l.stock_grams, f)]))}">${__('Short')} ${esc(qty(l.short, f))}</span>`
					: `<span class="sob-badge ok" data-tip="${esc(__('{0} available in the sellable warehouses', [qty(l.stock_grams, f)]))}">${__('In stock')}</span>`);
				const dis = editable ? '' : ' disabled';
				const k = esc(l.key);
				const q = +l.total_grams ? (lb ? r3(l.total_grams / LB) : r3(l.total_grams)) : '';
				const p = +l.price_per_gram ? (lb ? r2(l.price_per_gram * LB) : r3(l.price_per_gram)) : '';
				return `<div class="sob-req${l.draft ? ' draft' : ''}" data-req="${k}">
					<div class="sob-req-head"><span class="sob-req-n">${i + 1}</span>
						<select data-req-field="product_line" aria-label="${esc(__('Product line, requirement {0}', [i + 1]))}"${dis}>${line_opts}</select>
						<select data-req-field="tier" aria-label="${esc(__('Tier, requirement {0}', [i + 1]))}"${editable && tiers.length ? '' : ' disabled'}>${tier_opts}</select>
						${editable ? `<button type="button" class="sob-x sm" data-req-remove="${k}" aria-label="${esc(__('Remove requirement {0}', [i + 1]))}" data-tip="${esc(__('Remove this line'))}">${svg(ICON.x, 14)}</button>` : ''}
					</div>
					<div class="sob-req-nums">
						<label data-tip="${esc(lb ? __('Fresh frozen is counted in lb') : __('Extracts are counted in grams'))}">${lb ? __('Pounds') : __('Grams')}<input type="number" min="0" step="any" inputmode="decimal" data-req-field="total_grams" data-unit="${f}" data-keep="req:${k}:g" value="${esc(q)}"${dis}></label>
						<label data-tip="${esc(lb ? __('Price per lb') : __('Price per gram'))}">${lb ? __('Price / lb') : __('Price / g')}<input type="number" min="0" step="any" inputmode="decimal" data-req-field="price_per_gram" data-unit="${f}" data-keep="req:${k}:p" value="${esc(p)}"${dis}></label>
						<div class="sob-req-amt"><span>${__('Amount')}</span><b>${amount ? usd(amount) : '—'}</b></div>
						<div class="sob-req-stock">${stock}</div>
					</div>
				</div>`;
			};
			return `<div class="sob-block sob-reqs${busy}">
				${opts.bare ? '' : `<div class="sob-cap">${__('Requirements')}</div>`}
				${lines.length ? lines.map(row).join('') : `<div class="sob-muted">${__('No product requirements yet')}</div>`}
				${editable ? `<button type="button" class="sob-btn sm sob-req-add" data-act="req-add">${svg(ICON.plus, 14)}${__('Add requirement')}</button>` : ''}
			</div>`;
		}

		value_tiles(d) {
			const calc = this.calc_value(d);
			const manual = +d.value_override > 0;
			const value = manual ? +d.value_override : calc;
			const st = this.stage(d.stage) || {};
			const by = this.deal_qty(d);
			const fams = FAMS.filter(f => by[f] > 0);
			// average price in the one unit the deal uses; a deal mixing lb and g lines shows none
			const f = fams.length === 1 ? fams[0] : null;
			const avg = f ? calc / (f === 'lb' ? by.lb / LB : by.g) : 0;
			const lines = this.lines_of(d).filter(l => l.product_line);
			const shown = (value ? usd(value) : '—') + (manual ? ` <span class="sob-badge manual">${__('Manual')}</span>` : '');
			const tile = this.can_edit(d)
				? this.ed(d, 'value_override', __('Deal value'), { tile: true, type: 'number', html: shown, value: value || '' })
				: `<div class="sob-tile"><span>${__('Deal value')}</span><b>${shown}</b></div>`;
			return `<div class="sob-tiles">
				${tile}
				<div class="sob-tile" data-tip="${esc(__('Deal value × {0}% for {1}', [+st.probability || 0, __(d.stage)]))}"><span>${__('Weighted')}</span><b>${value ? usd(value * (+st.probability || 0) / 100) : '—'}</b></div>
				<div class="sob-tile"><span>${__('Quantity')}</span><b>${esc(qty_pair(by) || '—')}</b></div>
				<div class="sob-tile"><span>${lines.length > 1 ? __('Avg price') : __('Price')}</span><b>${avg ? money2(avg) + '/' + (f === 'lb' ? 'lb' : 'g') : '—'}</b></div>
			</div>${manual ? `<div class="sob-manual-note"><span class="sob-muted">${__('Manual deal value. Calculated from the requirements: {0}.', [calc ? usd(calc) : '$0'])}</span>
				${this.can_edit(d) ? `<button type="button" class="sob-link" data-act="value-reset">${__('Use calculated value')}</button>` : ''}</div>`
				: (this.can_edit(d) ? `<div class="sob-muted">${__('Click Deal value to enter it by hand')}</div>` : '')}`;
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
							<div class="sob-muted">${editable ? __('Create a new Customer or Lead, or search for an existing one below.') : __('The owner or a pipeline manager can add the buyer.')}</div></div>
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
			const locked = !editable && this.data.can_write ? `<div class="sob-muted">${d._acc ? __('Only the relationship manager, people with a deal here or a pipeline manager can edit the buyer.') : __('Only the deal owner or a pipeline manager can edit the buyer.')}</div>` : '';
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
					<textarea id="sob-note-new" class="sob-note" data-keep="note-new" rows="3" placeholder="${d._acc ? __('Write a note about this account') : __('Write a note about this deal')}"></textarea>
					<button type="button" class="sob-btn primary sm" data-act="note">${__('Save')}</button>
				</div>
				<div class="sob-notes">${list}</div>
				<div class="sob-block">
					<div class="sob-cap">${d._acc ? __('Relationship notes') : __('Deal notes')}</div>
					${(d._acc ? ACC_NOTE_SECTIONS : NOTE_SECTIONS).map(x => this.note_section(d, x[0], x[1], editable)).join('')}
				</div>
				${d._acc ? '' : `<div class="sob-fields">${field(__('Payment terms'), d.payment_terms)}${field(__('Lead source'), d.lead_source)}</div>`}`;
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
			return frappe.xcall(M + 'add_note', { name, note: text, doctype: dt_of(name) }).then(notes => {
				this.set_notes(name, notes);
				frappe.show_alert({ message: __('Note added to {0}: {1}', [d.account, text]), indicator: 'green' });
				return notes;
			}).finally(() => { if (btn) $(btn).prop('disabled', false); });
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

		// ---------- buyer purchase history (Sales Invoices of the linked Customer, or of the Customer made from the Lead) ----------

		has_buyer(d) { return !!(d && (d.customer || d.lead)); }

		// Fetched once per deal and buyer; the drawer renders again when it lands.
		hist_of(d) {
			if (!this.has_buyer(d)) return null;
			const key = (d.customer || '') + '|' + (d.lead || '');
			const h = this.hist;
			if (h && h.name === d.name && h.key === key) return h;
			const mine = { name: d.name, key, data: null };
			this.hist = mine;
			const land = data => {
				if (this.hist !== mine) return;
				mine.data = data;
				if (this.state.sel === d.name) this.render_drawer();
			};
			frappe.xcall(M + 'get_buyer_history', { name: d.name, doctype: dt_of(d.name) }).then(land)
				.catch(() => land({ error: true, invoices: [], by_line: [], totals: {} }));
			return mine;
		}

		inv_status(i) {
			const label = i.is_return ? __('Return') : __(i.status);
			const kind = i.is_return || /Credit Note|Return/.test(i.status || '') ? '' : i.status === 'Paid' ? ' ok' : i.status === 'Overdue' ? ' bad' : ' act';
			return `<span class="sob-badge${kind}">${esc(label)}</span>`;
		}

		hist_tiles(r) {
			const t = r.totals || {};
			return `<div class="sob-tiles">
				<div class="sob-tile"><span>${__('Billed')}</span><b>${usd(t.billed)}</b></div>
				<div class="sob-tile"><span>${__('Invoices')}</span><b>${n0(t.count)}</b></div>
				<div class="sob-tile${t.outstanding >= 1 ? ' due' : ''}"><span>${__('Outstanding')}</span><b>${usd(t.outstanding)}</b></div>
				<div class="sob-tile"><span>${__('Last bought')}</span><b>${t.last ? esc(fdate(t.last)) : '—'}</b></div>
			</div>`;
		}

		inv_rows(r, limit) {
			const list = limit ? r.invoices.slice(0, limit) : r.invoices;
			const multi = (r.totals || {}).companies > 1;
			const no = i => (r.can_open ? `<a href="/app/sales-invoice/${encodeURIComponent(i.name)}">${esc(i.name)}</a>` : esc(i.name));
			return `<div class="sob-inv">${list.map(i => {
				const meta = [multi ? i.company : '', i.due && !i.is_return ? __('Due {0}', [fdate(i.due)]) : '', i.outstanding >= 1 ? __('{0} outstanding', [usd(i.outstanding)]) : '']
					.filter(Boolean).map(esc).join(' · ');
				return `<details class="sob-inv-row">
					<summary>
						<span class="sob-inv-date">${esc(fdate(i.date))}</span>
						<span class="sob-inv-main"><span class="sob-inv-no">${no(i)}</span><span class="sob-inv-items">${esc(i.items.map(x => x.item_name).join(', '))}</span></span>
						${this.inv_status(i)}
						<span class="sob-inv-amt">${usd(i.amount)}</span>
						<span class="sob-inv-chev">${svg(ICON.down, 14)}</span>
					</summary>
					<table class="sob-mini">
						<thead><tr><th>${__('Item')}</th><th class="r">${__('Qty')}</th><th class="r">${__('Rate')}</th><th class="r money">${__('Amount')}</th></tr></thead>
						<tbody>${i.items.map(x => `<tr><td>${esc(x.item_name)}</td><td class="r">${nq(x.qty)} ${esc(x.uom || '')}</td><td class="r">${money2(x.rate)}</td><td class="r money">${usd(x.amount)}</td></tr>`).join('')}</tbody>
					</table>
					${meta ? `<div class="sob-muted sob-inv-meta">${meta}</div>` : ''}
				</details>`;
			}).join('')}</div>`;
		}

		// Overview: what this buyer already bought, before anything else about the deal.
		history_block(d) {
			const h = this.hist_of(d);
			if (!h) return '';
			const r = h.data;
			const head = extra => `<header><span class="sob-hist-t">${svg(ICON.receipt, 16)}${__('Purchase history')}</span>${extra || ''}</header>`;
			let body;
			if (!r) body = `<div class="sob-hist-note sob-muted">${__('Loading invoices…')}</div>`;
			else if (r.error) body = `<div class="sob-hist-note sob-muted">${__('The purchase history could not be loaded')}</div>`;
			else if (!r.customer) body = `<div class="sob-hist-note sob-muted">${__('No purchases yet. This lead is not a customer.')}</div>`;
			else if (!r.invoices.length) body = `<div class="sob-hist-note sob-muted">${__('{0} has no invoices yet', [esc(r.customer_title)])}</div>`;
			else {
				const more = r.invoices.length > 3 ? `<button type="button" class="sob-link" data-tab="purchases">${__('All {0} invoices', [r.invoices.length])}</button>` : '';
				return `<section class="sob-hist">${head(more)}${this.hist_tiles(r)}${this.inv_rows(r, 3)}</section>`;
			}
			return `<section class="sob-hist">${head()}${body}</section>`;
		}

		purchases_tab(d) {
			const h = this.hist_of(d);
			if (!h) return `<div class="sob-empty">${__('Link a buyer on the Buyer tab to see what they bought')}</div>`;
			const r = h.data;
			if (!r) return `<div class="sob-muted">${__('Loading invoices…')}</div>`;
			if (r.error) return `<div class="sob-empty">${__('The purchase history could not be loaded')}</div>`;
			if (!r.customer) return `<div class="sob-empty">${__('No purchases yet. This lead is not a customer.')}</div>`;
			if (!r.invoices.length) return `<div class="sob-empty">${__('{0} has no invoices yet', [esc(r.customer_title)])}</div>`;
			const t = r.totals;
			const sub = [r.via_lead ? __('Customer created from this lead') : '', t.first ? __('Buying since {0}', [fdate(t.first)]) : '',
				t.returns ? __('{0} returns', [t.returns]) : ''].filter(Boolean).map(esc).join(' · ');
			const qty = x => [x.grams ? n0(x.grams) + ' g' : '', x.units ? nq(x.units) + ' ' + (x.units === 1 ? __('unit') : __('units')) : ''].filter(Boolean).join(' · ');
			return `
				<div class="sob-block">
					<div class="sob-cap">${esc(r.customer_title)}</div>
					${sub ? `<div class="sob-muted">${sub}</div>` : ''}
					${this.hist_tiles(r)}
				</div>
				<div class="sob-block">
					<div class="sob-cap">${__('What they buy')}</div>
					<table class="sob-mini"><thead><tr><th>${__('Product')}</th><th class="r">${__('Quantity')}</th><th class="r money">${__('Amount')}</th></tr></thead>
						<tbody>${r.by_line.map(x => `<tr><td>${esc(x.label)}</td><td class="r">${qty(x)}</td><td class="r money">${usd(x.amount)}</td></tr>`).join('')}</tbody></table>
				</div>
				<div class="sob-block">
					<div class="sob-cap">${__('Invoices')}</div>
					<div class="sob-muted">${__('Newest first. Open a row for its items.')}</div>
					${this.inv_rows(r)}
				</div>`;
		}

		// The sheet for a deal or an account: header, segmented tabs, body, footer. Typed text, focus and scroll
		// survive a re-render (board reloads, saves).
		render_drawer() {
			const d = this.state.sel ? this.find(this.state.sel) : null;
			if (!d) { this.close_drawer(true); return; }
			const nav = document.querySelector('header.navbar, .navbar');
			const top = nav ? Math.max(0, nav.getBoundingClientRect().bottom) : 0;
			// the sheet floats inset from the window edges, over a dimmed board
			this.$drawer.prop('hidden', false).find('.sob-drawer').css('top', (top + 8) + 'px');
			this.$drawer.find('.sob-drawer-backdrop').css('top', top + 'px');
			const field = (label, value, html) => (value || html) ? `<div class="sob-f"><span>${esc(label)}</span><span>${html || esc(value)}</span></div>` : '';
			const tabs = d._acc ? this.acc_tabs(d) : this.deal_tabs(d);
			if (!tabs.some(x => x[0] === this.state.tab)) this.state.tab = 'overview';
			const tab = this.state.tab;
			const parts = d._acc ? this.acc_sheet(d, tab, field) : this.deal_sheet(d, tab, field);
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
				this.$drawer.find('.sob-drawer').attr('aria-label', d._acc ? __('Account') : __('Deal')).html(`
					<header class="sob-d-head">
						${parts.head}
						<div class="sob-d-tabs lg-group" role="tablist" data-seg="drawer">${tabs.map(t => `<button type="button" role="tab" class="lg-item${t[0] === tab ? ' on' : ''}" aria-selected="${t[0] === tab}" data-tab="${t[0]}">${esc(t[1])}</button>`).join('')}</div>
					</header>
					<div class="sob-d-body">${parts.body}</div>
					<footer class="sob-d-foot">${parts.foot}</footer>`);
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
			this.seg_sync(this.$drawer.find('.sob-d-tabs').get(0));
		}

		// When the deal should happen: the buyer's target, the four dates and how long it has sat in its stage
		timeline_block(d, dates, st) {
			const days = +d.days_in_stage || 0;
			const limit = +st.max_days || 0;
			const late = !d.is_closed && limit && days > limit;
			const age = `<span class="sob-tl-age${late ? ' late' : ''}">${esc(days === 1 ? __('1 day') : __('{0} days', [days]))}${limit ? `<small>${esc(__('of {0}', [limit]))}</small>` : ''}</span>`;
			return `<section class="sob-block sob-timeline" aria-label="${esc(__('Timeline'))}">
				<div class="sob-tl-head">
					<div class="sob-cap">${__('Timeline')}</div>
					<span class="sob-tl-stage" style="--sob-stage:${esc(st.colour || 'var(--sob-accent)')}" data-tip="${esc(late ? __('Over the {0}-day limit for {1}', [limit, d.stage]) : __('Days in {0}', [d.stage]))}"><span class="sob-stage-dot"></span>${esc(__('In {0}', [__(d.stage)]))} ${age}</span>
				</div>
				<div class="sob-fields">${this.ed(d, 'timeline', __('Buyer target'))}</div>
				<div class="sob-dates">${dates}</div>
			</section>`;
		}

		deal_tabs(d) {
			const feed = this.feed && this.feed.name === d.name ? this.feed : null;
			const n_notes = feed && feed.notes ? feed.notes.length : 0;
			const hist = this.hist_of(d);
			const n_inv = hist && hist.data && hist.data.invoices ? hist.data.invoices.length : 0;
			return [['overview', __('Overview')], ['buyer', __('Buyer')]]
				.concat(hist ? [['purchases', n_inv ? __('Purchases') + ` (${n_inv})` : __('Purchases')]] : [])
				.concat([['requirements', __('Requirements')], ['notes', n_notes ? __('Notes') + ` (${n_notes})` : __('Notes')], ['activity', __('Activity')]]);
		}

		// The account a deal belongs to, as a link back to the Leads card
		acc_link(d) {
			const a = this.acc_of(d);
			if (!a) return '';
			const st = this.status(a.lead_status) || {};
			// the deal usually carries the account's name already; then the link only needs the status
			const label = a.account !== d.account ? a.account : __('Account');
			return `<button type="button" class="sob-acc-link" data-open-acc="${esc(a.name)}" style="--sob-stage:${esc(st.colour || '#A1A1AA')}" data-tip="${esc(__('Open {0} on the Leads board', [a.account]))}">
				<span class="sob-stage-dot"></span><span>${esc(label)}</span><span class="sob-muted">${esc(__(a.lead_status))}</span>${svg(ICON.right, 12)}</button>`;
		}

		deal_sheet(d, tab, field) {
			const can = this.data.can_write;
			const st = this.stage(d.stage) || {};
			const first = this.first_stage_of('deal');
			let body = '';
			if (tab === 'overview') {
				const stock = d.stock ? `${n0(d.stock.grams)} g ${__('available')} (${esc(d.stock.groups.join(', '))})${d.stock.on_orders ? ` · ${n0(d.stock.on_orders)} g ${__('on open Sales Orders')}` : ''}` : '';
				const dates = EVENTS.map(e => `
					<label class="sob-date"><span class="ev-${e.key}">${svg(e.icon, 12)} ${esc(__(e.label))}</span>
						<input type="date" data-panel-field="${e.field}" value="${esc(d[e.field] || '')}"${can ? '' : ' disabled'}></label>`).join('');
				const lost = d.is_lost ? `<div class="sob-lost-banner" role="status">
						<div><b>${__('Lost')}</b>${d.lost_reason ? `<span>${esc(d.lost_reason)}</span>` : ''}<small>${esc(__('Kept in {0} so it can be won back', [first]))}</small></div>
						${can ? `<button type="button" class="sob-btn sm" data-reopen="${esc(d.name)}">${svg(ICON.undo, 14)}${esc(__('Reopen'))}</button>` : ''}
					</div>` : '';
				body = `
					${lost}
					${(d.flags || []).length ? `<div class="sob-badges">${(d.flags || []).map(f => `<span class="sob-badge ${f.kind === 'action' ? 'act' : 'info'}">${esc(f.label)}</span>`).join('')}</div>` : ''}
					${this.history_block(d)}
					${can ? `<div class="sob-block"><div class="sob-cap">${__('Stage')}</div><div class="sob-moves">${this.stages_of('deal').map(x => `<button type="button" class="sob-move${x.name === d.stage ? ' on' : ''}" data-move="${esc(x.name)}" aria-pressed="${x.name === d.stage}"${x.colour ? ` style="--sob-stage:${esc(x.colour)}"` : ''}>${esc(__(x.name))}</button>`).join('')}</div></div>` : ''}
					${this.value_tiles(d)}
					${this.timeline_block(d, dates, st)}
					${this.req_editor(d)}
					<div class="sob-two">
						<label class="sob-cap">${__('Owner')}
							<select data-panel-field="deal_owner"${can && this.data.is_manager ? '' : ' disabled'}>${[['', __('Unassigned')]].concat(this.owner_choices(d).map(o => [o.user, o.name])).map(o => `<option value="${esc(o[0])}"${(d.deal_owner || '') === o[0] ? ' selected' : ''}>${esc(o[1])}</option>`).join('')}</select></label>
						<label class="sob-cap">${__('Priority')}
							<select data-panel-field="priority"${can ? '' : ' disabled'}>${(this.s.lists.priority || []).map(p => `<option${p === d.priority ? ' selected' : ''}>${esc(p)}</option>`).join('')}</select></label>
					</div>
					${this.co_owner_block(d)}
					<div class="sob-fields">
						${field(__('Stock available'), stock)}
						${field(__('Status detail'), d.status_detail)}
						${d.is_lost ? '' : field(__('Lost reason'), d.lost_reason)}
					</div>`;
			} else if (tab === 'purchases') {
				body = this.purchases_tab(d);
			} else if (tab === 'buyer') {
				body = this.deal_account_block(d) + this.buyer_tab(d);
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
			const head = `
				<div class="sob-d-row">${this.stage_chip(d.stage)}<span class="sob-muted">${+st.probability || 0}% · ${esc(d.name)}</span>
					<button type="button" class="sob-x" data-act="close" aria-label="${__('Close')}">${svg(ICON.x, 16)}</button></div>
				<h2>${esc(d.account)}</h2>
				${this.acc_link(d)}
				<div class="sob-muted">${esc((d.lines || []).length ? d.lines.map(l => [l.product_line, l.tier].filter(Boolean).join(' · ')).join(', ') : ([d.product_line, d.tier].filter(Boolean).join(' · ') || __('Product not set yet')))} · ${esc(d.deal_owner ? this.owner_name(d.deal_owner) : __('Unassigned'))}${this.co_list(d).length ? esc(' + ' + this.co_list(d).map(u => this.owner_name(u)).join(', ')) : ''}</div>`;
			const foot = `
				<button type="button" class="sob-btn" data-act="form">${__('Open full form')}</button>
				${this.data.can_quote ? `<button type="button" class="sob-btn" data-act="quote">${__('Create Quotation')}</button>` : ''}
				${tab === 'overview' ? this.email_button(d) : ''}
				${can && won && d.stage !== won.name && !d.is_lost ? `<button type="button" class="sob-btn won" data-act="won">${__('Mark Won')}</button>` : ''}
				${can && lost && d.stage !== lost.name ? `<button type="button" class="sob-btn lost" data-act="lost">${__('Mark Lost')}</button>` : ''}
				${can && d.is_lost ? `<button type="button" class="sob-btn primary" data-reopen="${esc(d.name)}">${svg(ICON.undo, 14)}${__('Reopen in {0}', [esc(first)])}</button>` : ''}`;
			return { head, body, foot };
		}

		// Buyer tab of a deal: which account (Leads card) it belongs to, and moving it to another one
		deal_account_block(d) {
			const accs = (this.data.accounts || []).slice().sort((a, b) => String(a.account).localeCompare(String(b.account)));
			const cur = this.acc_of(d);
			const editable = this.can_edit(d);
			return `<div class="sob-block">
				<div class="sob-cap">${__('Lead / Account')}</div>
				${cur ? this.acc_link(d) : `<div class="sob-muted">${__('Not linked to an account yet. Saving the deal links it.')}</div>`}
				${editable && accs.length ? `<label class="sob-cap sob-move-acc"><span class="sob-muted">${__('Move this deal to another account')}</span>
					<select data-panel-field="pipeline_account">${(cur ? [] : [['', '']]).concat(accs.map(a => [a.name, a.account + ' · ' + __(a.lead_status)])).map(o => `<option value="${esc(o[0])}"${(d.pipeline_account || '') === o[0] ? ' selected' : ''}>${esc(o[1])}</option>`).join('')}</select></label>` : ''}
			</div>`;
		}

		acc_tabs(a) {
			const feed = this.feed && this.feed.name === a.name ? this.feed : null;
			const n_notes = feed && feed.notes ? feed.notes.length : 0;
			const hist = this.hist_of(a);
			const n_inv = hist && hist.data && hist.data.invoices ? hist.data.invoices.length : 0;
			const n_deals = this.deals_of(a).length;
			return [['overview', __('Overview')], ['volume', (a.volume || []).length ? __('Volume') + ` (${a.volume.length})` : __('Volume')],
				['deals', n_deals ? __('Deals') + ` (${n_deals})` : __('Deals')], ['buyer', __('Buyer')]]
				.concat(hist ? [['purchases', n_inv ? __('Purchases') + ` (${n_inv})` : __('Purchases')]] : [])
				.concat([['notes', n_notes ? __('Notes') + ` (${n_notes})` : __('Notes')], ['activity', __('Activity')]]);
		}

		acc_tiles(a) {
			const q = this.acc_qty(a);
			return `<div class="sob-tiles">
				<div class="sob-tile" data-tip="${esc(__('What they procure or produce in a week'))}"><span>${__('Volume / week')}</span><b>${esc(qty_pair(q.week) || '—')}</b></div>
				<div class="sob-tile" data-tip="${esc(__('What they want from us each month'))}"><span>${__('Wants / month')}</span><b>${esc(qty_pair(q.month) || '—')}</b></div>
				<div class="sob-tile" data-tip="${esc(__('Wants / month × price'))}"><span>${__('Potential / month')}</span><b>${+a.monthly_potential ? usd(a.monthly_potential) : '—'}</b></div>
				<div class="sob-tile" data-tip="${esc(__('Potential × {0}% for {1}', [+a.probability || 0, __(a.lead_status)]))}"><span>${__('Weighted / month')}</span><b>${+a.weighted_potential ? usd(a.weighted_potential) : '—'}</b></div>
			</div>`;
		}

		// The account's deals as an inset list; lost deals stay listed so the history is visible
		acc_deals(a, limit) {
			const order = st => { const i = (this.s.stages || []).findIndex(x => x.name === st); return i < 0 ? 99 : i; };
			const all = this.deals_of(a).sort((x, y) => (x.is_closed - y.is_closed) || order(x.stage) - order(y.stage));
			const list = limit ? all.slice(0, limit) : all;
			if (!all.length) return `<div class="sob-empty sob-deals-empty">${__('No deals with {0} yet.', [esc(a.account)])}</div>`;
			const rows = list.map(d => {
				const st = this.stage(d.stage) || {};
				const prods = (d.lines || []).length ? d.lines.map(l => [l.product_line, l.tier].filter(Boolean).join(' · ')).join(', ') : ([d.product_line, d.tier].filter(Boolean).join(' · ') || __('Product not set yet'));
				const meta = [__(d.stage), d.deal_owner ? this.owner_name(d.deal_owner) : __('Unassigned'),
					d.is_lost && d.lost_reason ? d.lost_reason : (d.next_step_due && !d.is_closed ? __('Follow-up {0}', [nice(d.next_step_due)]) : '')].filter(Boolean).join(' · ');
				return `<button type="button" class="sob-deal-row${d.is_lost ? ' lost' : ''}" data-open-deal="${esc(d.name)}" style="--sob-stage:${esc(st.colour || '#A1A1AA')}">
					<span class="sob-stage-dot"></span>
					<span class="sob-deal-main"><b>${esc(prods)}</b><span class="sob-muted">${esc(meta)}</span></span>
					<span class="sob-deal-val">${+d.deal_value ? usd(d.deal_value) : '—'}</span>${svg(ICON.right, 14)}</button>`;
			}).join('');
			const more = limit && all.length > limit ? `<button type="button" class="sob-link" data-tab="deals">${__('All {0} deals', [all.length])}</button>` : '';
			return `<div class="sob-deals">${rows}</div>${more}`;
		}

		acc_sheet(a, tab, field) {
			const can = this.can_edit(a);
			const st = this.status(a.lead_status) || {};
			const new_deal = this.data.can_create ? `<button type="button" class="sob-btn sm" data-new-deal="${esc(a.name)}">${svg(ICON.plus, 14)}${__('New deal')}</button>` : '';
			let body = '';
			if (tab === 'overview') {
				const sources = [''].concat(this.s.lists.lead_source || []);
				if (a.lead_source && !sources.includes(a.lead_source)) sources.push(a.lead_source);
				body = `
					${(a.flags || []).length ? `<div class="sob-badges">${a.flags.map(f => `<span class="sob-badge ${f.kind === 'action' ? 'act' : 'info'}">${esc(f.label)}</span>`).join('')}</div>` : ''}
					${this.history_block(a)}
					${can ? `<div class="sob-block"><div class="sob-cap">${__('Lead status')}</div><div class="sob-moves">${this.stages_of('lead').map(x => `<button type="button" class="sob-move${x.name === a.lead_status ? ' on' : ''}" data-move="${esc(x.name)}" aria-pressed="${x.name === a.lead_status}"${x.colour ? ` style="--sob-stage:${esc(x.colour)}"` : ''}>${esc(__(x.name))}</button>`).join('')}</div></div>` : ''}
					<div class="sob-block">
						<div class="sob-cap sob-cap-row"><span>${__('Volume and demand')}</span><button type="button" class="sob-link" data-tab="volume">${(a.volume || []).length ? __('Edit') : __('Add')}</button></div>
						${this.acc_tiles(a)}
						${(a.volume || []).length ? `<div class="sob-muted">${esc(a.volume.map(v => this.vol_text(v)).join(' · '))}</div>` : `<div class="sob-muted">${__('Record what they procure or produce each week and what they want from us; it feeds the Projection.')}</div>`}
					</div>
					<div class="sob-block">
						<div class="sob-cap sob-cap-row"><span>${__('Deals')}</span>${new_deal}</div>
						${this.acc_deals(a, 4)}
					</div>
					<div class="sob-two">
						<label class="sob-cap">${__('Relationship manager')}
							<select data-panel-field="account_owner"${can && this.data.is_manager ? '' : ' disabled'}>${this.owner_choices(a).map(o => [o.user, o.name]).map(o => `<option value="${esc(o[0])}"${(a.account_owner || '') === o[0] ? ' selected' : ''}>${esc(o[1])}</option>`).join('')}</select></label>
						<label class="sob-cap">${__('Lead source')}
							<select data-panel-field="lead_source"${can ? '' : ' disabled'}>${sources.map(p => `<option value="${esc(p)}"${p === (a.lead_source || '') ? ' selected' : ''}>${esc(p || '—')}</option>`).join('')}</select></label>
					</div>
					<div class="sob-dates"><label class="sob-date"><span class="ev-followup">${svg(ICON.phone, 12)} ${__('Next follow-up')}</span>
						<input type="date" data-panel-field="next_step_due" value="${esc(a.next_step_due || '')}"${can ? '' : ' disabled'}></label></div>
					<div class="sob-fields">
						${field(__('In this status'), a.days_in_stage + ' ' + __('days') + (st.max_days ? ' ' + __('(limit {0})', [st.max_days]) : ''))}
						${field(__('Weighting'), __('{0}% for {1}', [+st.probability || 0, __(a.lead_status)]))}
						${this.ed(a, 'relationship_notes', __('Relationship notes'), { type: 'textarea', placeholder: __('Add notes about the relationship') })}
					</div>`;
			} else if (tab === 'volume') {
				body = `${this.vol_editor(a)}${this.acc_tiles(a)}
					<div class="sob-muted">${__('Wants per week counts as {0} weeks a month. The price per gram starts from the product line\'s default price in Sales Pipeline Settings.', [WPM.toFixed(2)])}</div>`;
			} else if (tab === 'deals') {
				body = `<div class="sob-block"><div class="sob-cap sob-cap-row"><span>${__('Deals with {0}', [esc(a.account)])}</span>${new_deal}</div>${this.acc_deals(a)}</div>
					<div class="sob-tiles sob-tiles-3">
						<div class="sob-tile"><span>${__('Open deal value')}</span><b>${+a.open_value ? usd(a.open_value) : '—'}</b></div>
						<div class="sob-tile"><span>${__('Weighted')}</span><b>${+a.open_weighted ? usd(a.open_weighted) : '—'}</b></div>
						<div class="sob-tile"><span>${__('Won')}</span><b>${+a.won_value ? usd(a.won_value) : '—'}</b></div>
					</div>`;
			} else if (tab === 'buyer') {
				body = this.buyer_tab(a);
			} else if (tab === 'purchases') {
				body = this.purchases_tab(a);
			} else if (tab === 'notes') {
				body = this.notes_tab(a, field);
			} else {
				body = this.activity_tab(a);
			}
			const head = `
				<div class="sob-d-row">${this.stage_chip(a.lead_status, true)}<span class="sob-muted">${+st.probability || 0}% · ${esc(a.name)}</span>
					<button type="button" class="sob-x" data-act="close" aria-label="${__('Close')}">${svg(ICON.x, 16)}</button></div>
				<h2>${esc(a.account)}</h2>
				<div class="sob-muted">${esc(a.account_owner ? this.owner_name(a.account_owner) : __('Unassigned'))}${a.customer || a.lead ? ' · ' + esc(a.customer ? (a.customer_title || a.customer) : (a.lead_title || a.lead)) : ''}${a.open_deals ? ' · ' + esc(__('{0} open {1}', [a.open_deals, a.open_deals === 1 ? __('deal') : __('deals')])) : ''}</div>`;
			const foot = `
				<button type="button" class="sob-btn" data-act="form">${__('Open full form')}</button>
				${this.data.can_create ? `<button type="button" class="sob-btn primary" data-new-deal="${esc(a.name)}">${svg(ICON.plus, 14)}${__('New deal')}</button>` : ''}
				${tab === 'overview' ? this.email_button(a) : ''}`;
			return { head, body, foot };
		}

		vol_text(v) {
			const c = this.vol_calc(v);
			const f = this.fam_of(v.product_line);
			const parts = [[v.product_line, v.tier].filter(Boolean).join(' ')];
			if (+v.weekly_volume) parts.push(v.activity === 'Produce' ? __('makes {0}/wk', [qty(c.weekly_grams, f)]) : __('buys {0}/wk', [qty(c.weekly_grams, f)]));
			if (+v.wants_qty) parts.push(__('wants {0}/mo', [qty(c.monthly_grams, f)]));
			return parts.join(', ');
		}

		// Volume rows of an account, edited like requirement lines: every change saves.
		// Volume rows of an account, edited like requirement lines: every change saves. The unit follows the product
		// line's SKUs: lb for fresh frozen, g or kg for extracts; the price is per lb or per gram to match.
		vol_editor(a, opts) {
			opts = opts || {};
			const editable = this.can_edit(a);
			const w = this.work && this.work[a.name];
			const rows = w || (a.volume || []).map((v, i) => Object.assign({}, v, { key: v.name || 'v' + i }));
			const all_lines = this.s.product_lines || [];
			const o = (v, t, cur) => `<option value="${esc(v)}"${(cur || '') === v ? ' selected' : ''}>${esc(t)}</option>`;
			const busy = this.busy[a.name] ? ' busy' : '';
			const dis = editable ? '' : ' disabled';
			const row = (v, i) => {
				const tiers = this.tiers_for(v.product_line);
				if (v.tier && !tiers.includes(v.tier)) tiers.unshift(v.tier);
				const line_opts = o('', __('Choose a product line'), v.product_line) + all_lines.map(x => o(x, x, v.product_line)).join('') +
					(v.product_line && !all_lines.includes(v.product_line) ? o(v.product_line, v.product_line, v.product_line) : '');
				const tier_opts = tiers.length ? o('', __('No tier'), v.tier) + tiers.map(x => o(x, x, v.tier)).join('')
					: o('', v.product_line ? __('No tiers for this line') : __('Tier'), '');
				const f = this.fam_of(v.product_line);
				const units = f === 'lb' ? [['lb', 'lb']] : [['g', 'g'], ['kg', 'kg']];
				const c = this.vol_calc(v);
				const k = esc(v.key);
				const num = (fld, label, keep, tip) => `<label data-tip="${esc(tip)}">${label}<input type="number" min="0" step="any" inputmode="decimal" data-vol-field="${fld}" data-keep="vol:${k}:${keep}" value="${+v[fld] ? esc(v[fld]) : ''}"${dis}></label>`;
				const pick = (fld, label, list, cur, tip, lock) => `<label data-tip="${esc(tip)}">${label}<select data-vol-field="${fld}"${dis || (lock ? ' disabled' : '')}>${list.map(x => o(x[0], x[1], cur || list[0][0])).join('')}</select></label>`;
				return `<div class="sob-req sob-vol${v.draft ? ' draft' : ''}" data-vol="${k}">
					<div class="sob-req-head"><span class="sob-req-n">${i + 1}</span>
						<select data-vol-field="product_line" aria-label="${esc(__('Product line, row {0}', [i + 1]))}"${dis}>${line_opts}</select>
						<select data-vol-field="tier" aria-label="${esc(__('Tier, row {0}', [i + 1]))}"${editable && tiers.length ? '' : ' disabled'}>${tier_opts}</select>
						${editable ? `<button type="button" class="sob-x sm" data-vol-remove="${k}" aria-label="${esc(__('Remove row {0}', [i + 1]))}" data-tip="${esc(__('Remove this product line'))}">${svg(ICON.x, 14)}</button>` : ''}
					</div>
					<div class="sob-vol-grid">
						${pick('activity', __('They'), [['Procure', __('Procure (buy)')], ['Produce', __('Produce (make)')]], v.activity, __('Procure: they buy it from suppliers. Produce: they make it themselves'))}
						${num('weekly_volume', __('Volume / week'), 'w', __('How much they buy or make in a normal week, in the unit on the right'))}
						${pick('uom', __('Unit'), units, units.some(u => u[0] === v.uom) ? v.uom : units[0][0], f === 'lb' ? __('Fresh frozen is always counted in lb') : __('Extracts are counted in g or kg'), units.length < 2)}
						${num('wants_qty', __('Wants from us'), 'q', __('How much of it they would take from us'))}
						${pick('wants_per', __('Per'), [['Month', __('Month')], ['Week', __('Week')]], v.wants_per, __('Whether that amount is each week or each month'))}
						${num('price', f === 'lb' ? __('Price / lb') : __('Price / g'), 'p', __('What they would pay. Empty uses the default price of the product line'))}
					</div>
					<div class="sob-vol-sum">${c.monthly_grams ? `<span>${esc(__('{0} a month', [qty(c.monthly_grams, f)]))}</span><b>${c.monthly_value ? usd(c.monthly_value) + '/' + __('mo') : esc(__('Add a price'))}</b>` : `<span class="sob-muted">${__('Enter what they want from us to see the monthly potential')}</span>`}</div>
				</div>`;
			};
			return `<div class="sob-block sob-reqs${busy}">
				${opts.bare ? '' : `<div class="sob-cap">${__('Volume and demand')}</div><div class="sob-muted">${__('Per product line: what they procure or produce each week, and what they want from us')}</div>`}
				${rows.length ? rows.map(row).join('') : `<div class="sob-muted">${__('No volume recorded yet')}</div>`}
				${editable ? `<button type="button" class="sob-btn sm sob-req-add" data-act="vol-add">${svg(ICON.plus, 14)}${__('Add product line')}</button>` : ''}
			</div>`;
		}

		load_feed(name) {
			return frappe.xcall(M + 'get_feed', { name, doctype: dt_of(name) }).then(r => {
				this.feed = { name, notes: r.notes || [], activity: r.activity || [] };
				if (this.state.sel === name) this.render_drawer();
			}).catch(() => { this.feed = { name, notes: [], activity: [] }; });
		}

		set_notes(name, notes) {
			if (this.feed && this.feed.name === name) this.feed.notes = notes || [];
			else this.feed = { name, notes: notes || [], activity: null };
			if (this.state.sel === name) this.render_drawer();
		}

		open(name, tab) {
			this.close_pop();
			if (this.state.sel !== name) {
				this.feed = null;
				this.editor = null;
				this.bsearch = null;
				this.bresults = null;
			}
			this.set({ sel: name, tab: tab || (this.state.sel === name ? this.state.tab : 'overview') });
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
			const def_type = ((won && d.stage === won.name) || d.is_customer) && types.includes('Customer') ? 'Customer' : types[0];
			const need = d._acc ? [] : this.missing(d, {}).filter(k => k !== 'customer');
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
				if (need.includes('next_step_due')) fields.push({ fieldname: 'next_step_due', fieldtype: 'Date', label: __('Next Follow-up'), reqd: 1, description: __('Pick the date you will follow up. It shows on the calendar.') });
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
						contact_name: v.contact_name || '', phone: v.phone || '', email: v.email || '', extra, doctype: dt_of(name),
					}).then(r => {
						dlg.hide();
						this.bsearch = null;
						this.bresults = null;
						frappe.show_alert({ message: d._acc ? __('{0} {1} created and linked to this account', [__(r.type), r.title]) : __('{0} {1} created and linked to this deal', [__(r.type), r.title]), indicator: 'green' });
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
			if (!d) return;
			if (this.busy[name]) { this.queue(name, patch); return; }
			if (d._acc) return this.apply_acc(name, patch, done_msg);
			const lost = this.lost_stage();
			// every way of losing a deal (drag, Mark Lost, stage pop-up, list) goes through the lost prompt
			if (lost && patch.stage === lost.name && d.stage !== lost.name && !patch._sure) { this.lose(name, patch); return; }
			patch = Object.assign({}, patch);
			delete patch._sure;
			// a reopened deal drops its lost reason (Activity keeps it)
			if (d.is_lost && lost && patch.stage && patch.stage !== lost.name && !('lost_reason' in patch)) patch.lost_reason = null;
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
			if (need.includes('next_step_due')) fields.push({ fieldname: 'next_step_due', fieldtype: 'Date', label: __('Next Follow-up'), reqd: 1, description: __('Pick the date you will follow up. It shows on the calendar.') });
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

		// The little prompt when a deal is lost: why, what happened, when to try again. The deal then waits at the
		// bottom of the first stage (Active Opportunity) so it can be won back.
		lose(name, patch) {
			const d = this.find(name);
			const lost = this.lost_stage();
			if (!d || !lost) return;
			const first = this.first_stage_of('deal');
			const acc = this.acc_of(d);
			const others = acc ? this.deals_of(acc).filter(x => x.name !== d.name && !x.is_closed) : [];
			const end = (this.s.lead_statuses || []).find(x => x.is_closed);
			const reasons = (this.s.lists && this.s.lists.lost_reasons) || [];
			const value = +d.deal_value ? usd(d.deal_value) : '';
			const fields = [
				{ fieldtype: 'HTML', options: `<p class="sob-lose-intro">${esc([d.account, value].filter(Boolean).join(' · '))}<br>
					<span class="text-muted">${esc(__('It stays at the bottom of {0}, so it can be reopened later.', [first]))}</span></p>` },
				{ fieldname: 'reason', fieldtype: 'Select', label: __('Why was it lost?'), reqd: 1, options: [''].concat(reasons) },
				{ fieldname: 'details', fieldtype: 'Small Text', label: __('What happened'), description: __('Optional. Price they wanted, who they went with, what would win it back.') },
				{ fieldname: 'revisit', fieldtype: 'Date', label: __('Try again on'), description: __('Optional. Sets the next follow-up, so it comes back on the calendar.') },
			];
			if (acc && end && acc.lead_status !== end.name && !others.length) {
				fields.push({ fieldname: 'acc_lost', fieldtype: 'Check', label: __('Also mark {0} as {1}', [acc.account, __(end.name)]),
					description: __('Only if the whole relationship has ended. {0} has no other open deals.', [acc.account]) });
			}
			const dlg = new frappe.ui.Dialog({
				title: __('Mark {0} as lost?', [d.account]),
				size: 'small',
				fields,
				primary_action_label: __('Mark as lost'),
				primary_action: v => {
					const reason = [v.reason, (v.details || '').trim()].filter(Boolean).join(': ');
					const p = Object.assign({}, patch, { lost_reason: reason, _sure: true });
					if (v.revisit) p.next_step_due = v.revisit;
					dlg.hide();
					this.apply(name, p, __('{0} marked as lost. It stays in {1}.', [d.account, first]));
					if (v.acc_lost && acc && end) setTimeout(() => this.apply(acc.name, { lead_status: end.name }, __('{0} is now {1}', [acc.account, __(end.name)])), 600);
				},
			});
			dlg.show();
			this.render();
		}

		reopen(name) {
			const d = this.find(name);
			if (!d || !d.is_lost) return;
			const first = this.first_stage_of('deal');
			this.apply(name, { stage: first, lost_reason: null }, __('{0} reopened in {1}', [d.account, first]));
		}

		apply_acc(name, patch, done_msg) {
			const a = this.find(name);
			if (!a) return;
			if (this.busy[name]) { this.queue(name, patch); return; }
			const changed = Object.keys(patch).some(k => (patch[k] || '') !== (a[k] || ''));
			if (!changed) return;
			if ('account_owner' in patch && !patch.account_owner) {
				frappe.msgprint(__('Every account needs a relationship manager.'));
				this.render();
				return;
			}
			const prev = {};
			Object.keys(patch).forEach(k => { prev[k] = a[k]; a[k] = patch[k]; });
			if ('lead_status' in patch) {
				const st = this.status(patch.lead_status) || {};
				['probability', 'weighted_potential', 'is_customer'].forEach(k => { prev[k] = a[k]; });
				a.probability = +st.probability || 0;
				a.weighted_potential = (+a.monthly_potential || 0) * a.probability / 100;
				a.is_customer = st.is_active_customer;
			}
			if ('customer' in patch) a.customer_title = null;
			if ('lead' in patch) a.lead_title = null;
			this.busy[name] = true;
			this.render();
			return frappe.xcall(M + 'update_account', { name, values: patch })
				.then(() => frappe.show_alert({ message: done_msg || __('{0} updated', [a.account]), indicator: 'green' }))
				.catch(() => Object.assign(a, prev))
				.finally(() => { delete this.busy[name]; this.flush(name); this.load(); });
		}

		// edits that arrive while a record is saving (fast tabbing in the List view) are merged and sent next
		queue(name, patch) {
			this._queue = this._queue || {};
			this._queue[name] = Object.assign(this._queue[name] || {}, patch);
		}

		flush(name) {
			const q = this._queue && this._queue[name];
			if (!q) return;
			delete this._queue[name];
			this.apply(name, q, __('Saved'));
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
				.finally(() => { delete this.busy[name]; this.flush(name); this.load(); });
		}

		work_copy(d) {
			this.work = this.work || {};
			this._k = this._k || 0;
			if (!this.work[d.name]) this.work[d.name] = ((d._acc ? d.volume : d.lines) || []).map((l, i) => Object.assign({}, l, { key: l.name || 'v' + i }));
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
				this.flush(name);
				this.drop_work(name);
				this.load();
			});
		}

		// ---------- requirement edits (shared by the drawer and the pop-up) ----------

		refresh_req(name) {
			if (this.state.sel === name) this.render_drawer();
			if (this.pop && this.pop.name === name) this.render_pop();
		}

		req_add(name, $host) {
			const d = this.find(name);
			if (!d || !this.can_edit(d)) return;
			this.work_copy(d).push({ key: 'n' + (++this._k), product_line: '', tier: '', total_grams: '', price_per_gram: '', details: '', draft: true });
			this.refresh_req(name);
			const el = $host.find(`[data-req="n${this._k}"] [data-req-field="product_line"]`).get(0);
			if (el) el.focus();
		}

		req_remove(name, key) {
			const d = this.find(name);
			if (!d) return;
			const w = this.work_copy(d);
			const row = w.find(x => x.key === key);
			if (!row) return;
			w.splice(w.indexOf(row), 1);
			if (row.draft) { this.refresh_req(name); this.drop_work(name); return; }
			this.save_lines(name, __('Requirement removed'));
		}

		req_change(name, el) {
			const d = this.find(name);
			if (!d || !this.can_edit(d)) return;
			const key = $(el).closest('[data-req]').attr('data-req');
			const f = el.getAttribute('data-req-field');
			const row = this.work_copy(d).find(x => x.key === key);
			if (!row) return;
			let v = el.value;
			if (f === 'total_grams' || f === 'price_per_gram') {
				v = v === '' ? 0 : Number(v);
				if (!isFinite(v) || v < 0) { frappe.show_alert({ message: __('Please enter a number of 0 or more.'), indicator: 'red' }); el.value = row[f] || ''; return; }
				// fresh frozen is typed in lb and $/lb; stored in grams and $/g
				if (el.getAttribute('data-unit') === 'lb') v = f === 'total_grams' ? v * LB : v / LB;
			}
			row[f] = v;
			if (f === 'product_line' && row.tier && !this.tiers_for(v).includes(row.tier)) row.tier = '';
			if (row.draft && !row.product_line) { this.refresh_req(name); return; }
			row.draft = false;
			this.save_lines(name, f === 'product_line' || f === 'tier' ? __('Requirement updated') : __('Saved'));
		}

		// ---------- volume rows of an account (shared by the drawer and the pop-up) ----------

		vol_calc(v) {
			const per = UNITS[v.uom || 'g'] || 1;
			const monthly = (+v.wants_qty || 0) * per * ((v.wants_per || 'Month') === 'Week' ? WPM : 1);
			const pu = UNITS[v.price_unit || (this.fam_of(v.product_line) === 'lb' ? 'lb' : 'g')] || 1;
			return { weekly_grams: (+v.weekly_volume || 0) * per, monthly_grams: monthly, monthly_value: monthly / pu * (+v.price || 0) };
		}

		save_vol(name, msg) {
			const a = this.find(name);
			if (!a) return;
			this.req_dirty = this.req_dirty || {};
			if (this.busy[name]) { this.req_dirty[name] = msg || true; return; }
			const w = this.work_copy(a);
			const sent = w.filter(v => !v.draft && v.product_line);
			const payload = sent.map(v => ({
				name: v.name || null, product_line: v.product_line, tier: v.tier || '', activity: v.activity || 'Procure',
				weekly_volume: +v.weekly_volume || 0, wants_qty: +v.wants_qty || 0, wants_per: v.wants_per || 'Month', uom: v.uom || 'g',
				price: +v.price || 0, notes: v.notes || '',
			}));
			// show the new totals right away; the reload brings the server's figures (and default prices)
			const prev = { volume: a.volume, weekly_volume: a.weekly_volume, monthly_demand: a.monthly_demand, monthly_potential: a.monthly_potential, weighted_potential: a.weighted_potential };
			a.volume = sent.map(v => Object.assign({}, v, this.vol_calc(v)));
			a.weekly_volume = a.volume.reduce((s, v) => s + v.weekly_grams, 0);
			a.monthly_demand = a.volume.reduce((s, v) => s + v.monthly_grams, 0);
			a.monthly_potential = a.volume.reduce((s, v) => s + v.monthly_value, 0);
			a.weighted_potential = a.monthly_potential * (+a.probability || 0) / 100;
			this.busy[name] = true;
			this.render();
			frappe.xcall(M + 'update_account', { name, values: { volume: payload } }).then(r => {
				const names = (r && r.volume) || [];
				sent.forEach((v, i) => { if (names[i]) v.name = names[i]; });
				if (msg) frappe.show_alert({ message: msg, indicator: 'green' });
			}).catch(() => {
				Object.assign(a, prev);
				delete this.work[name];
			}).finally(() => {
				delete this.busy[name];
				const again = this.req_dirty[name];
				delete this.req_dirty[name];
				if (again && this.work[name]) { this.save_vol(name, again === true ? null : again); return; }
				this.flush(name);
				// the server may have filled the default price: take its rows on the next load
				const ww = this.work && this.work[name];
				if (ww && !ww.some(v => v.draft)) delete this.work[name];
				this.load();
			});
		}

		vol_add(name, $host) {
			const a = this.find(name);
			if (!a || !this.can_edit(a)) return;
			this.work_copy(a).push({ key: 'n' + (++this._k), product_line: '', tier: '', activity: 'Procure', weekly_volume: '', wants_qty: '', wants_per: 'Month', uom: 'g', price: '', notes: '', draft: true });
			this.refresh_req(name);
			const el = $host.find(`[data-vol="n${this._k}"] [data-vol-field="product_line"]`).get(0);
			if (el) el.focus();
		}

		vol_remove(name, key) {
			const a = this.find(name);
			if (!a) return;
			const w = this.work_copy(a);
			const row = w.find(x => x.key === key);
			if (!row) return;
			w.splice(w.indexOf(row), 1);
			if (row.draft) { this.refresh_req(name); this.drop_work(name); return; }
			this.save_vol(name, __('Volume row removed'));
		}

		vol_change(name, el) {
			const a = this.find(name);
			if (!a || !this.can_edit(a)) return;
			const key = $(el).closest('[data-vol]').attr('data-vol');
			const f = el.getAttribute('data-vol-field');
			const row = this.work_copy(a).find(x => x.key === key);
			if (!row) return;
			let v = el.value;
			if (['weekly_volume', 'wants_qty', 'price'].includes(f)) {
				v = v === '' ? 0 : Number(v);
				if (!isFinite(v) || v < 0) { frappe.show_alert({ message: __('Please enter a number of 0 or more.'), indicator: 'red' }); el.value = row[f] || ''; return; }
			}
			row[f] = v;
			if (f === 'product_line') {
				if (row.tier && !this.tiers_for(v).includes(row.tier)) row.tier = '';
				// the unit follows the line's SKUs; a new row takes the line's own unit
				const fam = this.fam_of(v);
				const allowed = fam === 'lb' ? ['lb'] : ['g', 'kg'];
				if (row.draft || !allowed.includes(row.uom)) row.uom = allowed.includes(this.unit_of(v)) ? this.unit_of(v) : allowed[0];
				const pu = fam === 'lb' ? 'lb' : 'g';
				if (row.price_unit && row.price_unit !== pu) row.price = '';
				row.price_unit = pu;
			}
			if (row.draft && !row.product_line) { this.refresh_req(name); return; }
			row.draft = false;
			this.save_vol(name, f === 'product_line' || f === 'tier' ? __('Volume updated') : __('Saved'));
		}

		// ---------- card pop-up: notes, requirements, follow-up, stage without opening the deal ----------

		open_pop(kind, name, btn) {
			if (this.pop && this.pop.kind === kind && this.pop.name === name) { this.close_pop(); return; }
			const d = this.find(name);
			if (!d) return;
			this.close_pop();
			// focusing the button can nudge the sheet into view; that scroll is not the user leaving
			this._quiet = Date.now();
			const r = btn.getBoundingClientRect();
			this.pop = { kind, name, anchor: { left: r.left, right: r.right, top: r.top, bottom: r.bottom }, notes: null };
			if (kind === 'notes') {
				frappe.xcall(M + 'get_feed', { name }).then(f => {
					if (this.pop && this.pop.name === name && this.pop.kind === 'notes') { this.pop.notes = f.notes || []; this.render_pop(); }
				}).catch(() => { if (this.pop && this.pop.name === name) { this.pop.notes = []; this.render_pop(); } });
			}
			this.$pop.prop('hidden', false);
			this.render_pop();
			this.place_pop();
			const first = this.$pop.find('textarea, [data-req-field]:not([disabled]), [data-vol-field]:not([disabled]), [data-pop-date], .sob-mi').get(0);
			if (first) first.focus({ preventScroll: true });
		}

		close_pop() {
			if (!this.pop) return;
			const name = this.pop.name;
			this.pop = null;
			this.$pop.prop('hidden', true).empty();
			this.drop_work(name);
		}

		// Below the button, or above it when there is no room; always inside the window.
		place_pop() {
			if (!this.pop) return;
			const el = this.$pop.get(0), a = this.pop.anchor, m = 12;
			const w = el.offsetWidth, h = el.offsetHeight, vw = window.innerWidth, vh = window.innerHeight;
			const below = vh - a.bottom - m >= h || a.top < vh / 2;
			const top = below ? Math.min(a.bottom + 8, vh - h - m) : Math.max(m, a.top - h - 8);
			const left = Math.max(m, Math.min(a.left - 8, vw - w - m));
			el.style.top = Math.max(m, Math.min(top, vh - h - m)) + 'px';
			el.style.left = left + 'px';
			el.style.setProperty('--lg-origin', `${below ? 'top' : 'bottom'} ${left < a.left - 40 ? 'right' : 'left'}`);
		}

		render_pop() {
			if (!this.pop) return;
			const d = this.find(this.pop.name);
			if (!d) { this.close_pop(); return; }
			const kind = this.pop.kind;
			const titles = { notes: __('Notes'), reqs: __('Requirements'), vol: __('Volume and demand'), follow: __('Next follow-up'), stage: d._acc ? __('Lead status') : __('Move to') };
			let body = '';
			if (kind === 'notes') body = this.pop_notes(d);
			else if (kind === 'reqs') body = this.pop_reqs(d);
			else if (kind === 'vol') body = this.pop_vol(d);
			else if (kind === 'follow') body = this.pop_follow(d);
			else body = this.pop_stage(d);
			// keep what is typed and where the cursor is when the pop-up re-renders (saves, board reloads)
			const kept = {};
			let focus = null, range = null;
			this.$pop.find('[data-keep]').each((_, el) => {
				const k = el.getAttribute('data-keep');
				kept[k] = el.value;
				if (el === document.activeElement) { focus = k; try { range = [el.selectionStart, el.selectionEnd]; } catch (x) { range = null; } }
			});
			this.$pop.attr('aria-label', titles[kind] + ': ' + d.account).attr('data-kind', kind).html(`
				<header class="sob-pop-h">
					<div class="sob-pop-t"><b>${esc(titles[kind])}</b><span>${esc(d.account)}</span></div>
					<button type="button" class="sob-x sm" data-pop-close aria-label="${__('Close')}">${svg(ICON.x, 14)}</button>
				</header>
				<div class="sob-pop-b">${body}</div>`);
			this.$pop.find('[data-keep]').each((_, el) => {
				const k = el.getAttribute('data-keep');
				if (Object.prototype.hasOwnProperty.call(kept, k)) el.value = kept[k];
				if (k === focus) { el.focus({ preventScroll: true }); if (range) { try { el.setSelectionRange(range[0], range[1]); } catch (x) { /* number inputs */ } } }
			});
		}

		pop_notes(d) {
			const qn = (this.s.lists && this.s.lists.quick_notes) || [];
			const notes = this.pop.notes;
			const list = notes === null ? `<div class="sob-muted">${__('Loading notes…')}</div>`
				: notes.length ? notes.slice(0, 3).map(n => `<article class="sob-noteitem"><header><b>${esc(n.by)}</b><span class="sob-muted">${esc(fdt(n.on))}</span></header><div class="sob-note-text">${esc(n.text)}</div></article>`).join('')
				: `<div class="sob-muted">${__('No notes yet')}</div>`;
			return `
				${qn.length ? `<div class="sob-pills sob-pop-chips">${qn.map(t => `<button type="button" class="sob-pill sob-qchip" data-pop-qnote="${esc(t)}">${esc(t)}</button>`).join('')}</div>` : ''}
				<textarea class="sob-note" rows="3" data-keep="pop-note" data-pop-note aria-label="${__('Note')}" placeholder="${__('Write a note')}"></textarea>
				<div class="sob-row-end">
					<button type="button" class="sob-btn sm" data-pop-open="notes">${__('All notes')}</button>
					<button type="button" class="sob-btn primary sm" data-pop-act="note-save">${__('Save note')}</button>
				</div>
				<div class="sob-pop-sec">${__('Latest')}</div>
				<div class="sob-notes">${list}</div>`;
		}

		pop_reqs(d) {
			const value = +d.deal_value || 0;
			const locked = this.can_edit(d) ? '' : `<div class="sob-muted">${__('Only the deal owner or a pipeline manager can change the requirements.')}</div>`;
			return `
				${this.req_editor(d, { bare: true })}
				${locked}
				<div class="sob-pop-foot">
					<span class="sob-pop-val"><span>${__('Deal value')}</span><b>${value ? usd(value) : '—'}</b>${+d.value_override > 0 ? `<span class="sob-badge manual">${__('Manual')}</span>` : ''}</span>
					<button type="button" class="sob-btn sm" data-pop-open="requirements">${__('Open deal')}</button>
				</div>`;
		}

		pop_vol(a) {
			const locked = this.can_edit(a) ? '' : `<div class="sob-muted">${__('Only the relationship manager, people with a deal here or a pipeline manager can change this.')}</div>`;
			return `
				${this.vol_editor(a, { bare: true })}
				${locked}
				<div class="sob-pop-foot">
					<span class="sob-pop-val"><span>${__('Potential')}</span><b>${+a.monthly_potential ? usd(a.monthly_potential) + '/' + __('mo') : '—'}</b></span>
					<button type="button" class="sob-btn sm" data-pop-open="volume">${__('Open account')}</button>
				</div>`;
		}

		pop_follow(d) {
			const today = pd(this.data.today);
			const nextMonday = addDays(today, ((8 - today.getDay()) % 7) || 7);
			const picks = [[__('Today'), today], [__('Tomorrow'), addDays(today, 1)], [__('In 3 days'), addDays(today, 3)],
				[__('Next Monday'), nextMonday], [__('In 2 weeks'), addDays(today, 14)]];
			const cur = d.next_step_due;
			const over = cur && cur < this.data.today && !d.is_closed;
			return `
				<div class="sob-pop-now${over ? ' over' : ''}">${cur ? (over ? __('Overdue since {0}', [nice(cur)]) : __('Now {0}', [nice(cur)])) : __('No follow-up set')}</div>
				<div class="sob-pop-list">${picks.filter((p, i) => picks.findIndex(q => key(q[1]) === key(p[1])) === i).map(p => {
					const k = key(p[1]);
					return `<button type="button" class="lg-item sob-mi" data-pop-date="${k}" aria-pressed="${k === cur}"><span class="sob-tick">${svg(ICON.check, 14)}</span><span>${esc(p[0])}</span><span class="sob-mi-r">${esc(nice(k))}</span></button>`;
				}).join('')}</div>
				<div class="sob-pop-pick">
					<input type="date" class="sob-ed-input" data-keep="pop-date" value="${esc(cur || '')}" aria-label="${__('Pick a date')}">
					<button type="button" class="sob-btn primary sm" data-pop-act="date-set">${__('Set')}</button>
					${cur ? `<button type="button" class="sob-btn sm" data-pop-act="date-clear">${__('Clear')}</button>` : ''}
				</div>`;
		}

		pop_stage(d) {
			const cur = this.stage_name(d);
			const sts = this.stages_of(d._acc ? 'lead' : 'deal');
			return `<div class="sob-pop-list">${sts.map(x => `<button type="button" class="lg-item sob-mi" data-pop-stage="${esc(x.name)}" aria-pressed="${x.name === cur}"${x.colour ? ` style="--sob-stage:${esc(x.colour)}"` : ''}>
				<span class="sob-tick">${svg(ICON.check, 14)}</span><span class="sob-stage-dot"></span><span>${esc(__(x.name))}</span><span class="sob-mi-r">${+x.probability || 0}%</span></button>`).join('')}</div>`;
		}

		// ---------- hover tutorials: one glass tooltip for every [data-tip] ----------

		// Mouse and trackpad only (touch has no hover). Shows after a short rest, at once when moving between tips,
		// and on keyboard focus. Off with "Show tips on hover" in Filters.
		bind_tips() {
			try { this.tips_off = localStorage.getItem('sob_tips_off') === '1'; } catch (e) { this.tips_off = false; }
			const $t = this.$tip;
			const hover = window.matchMedia && matchMedia('(hover: hover)').matches;
			let timer = 0, cur = null, warm = 0;
			const ours = el => !!(el && el.closest('.sob, .sob-drawer, .sob-pop'));
			const hide = () => {
				clearTimeout(timer);
				if (cur) { cur.removeAttribute('aria-describedby'); warm = Date.now(); }
				cur = null;
				$t.prop('hidden', true);
			};
			const show = el => {
				const text = el.getAttribute('data-tip');
				if (!text || this.tips_off || frappe.get_route_str() !== ROUTE || !document.contains(el)) return;
				cur = el;
				$t.text(text).prop('hidden', false);
				el.setAttribute('aria-describedby', 'sob-tip');
				const r = el.getBoundingClientRect(), w = $t.outerWidth(), h = $t.outerHeight(), m = 8;
				let top = r.top - h - 8, side = 'above';
				if (top < 56) { top = r.bottom + 8; side = 'below'; }
				const left = Math.max(m, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - m));
				$t.css({ top: Math.round(top) + 'px', left: Math.round(left) + 'px' }).attr('data-side', side);
			};
			const later = el => {
				clearTimeout(timer);
				timer = setTimeout(() => show(el), Date.now() - warm < 600 ? 60 : 450);
			};
			if (hover) {
				document.addEventListener('mouseover', e => {
					const el = e.target.closest && e.target.closest('[data-tip]');
					if (el === cur) return;
					if (cur) hide();
					if (el && ours(el) && !this.drag) later(el);
					else clearTimeout(timer);
				}, { passive: true });
			}
			document.addEventListener('focusin', e => {
				const el = e.target.closest && e.target.closest('[data-tip]');
				if (el && ours(el) && e.target.matches && e.target.matches(':focus-visible')) { hide(); show(el); }
			});
			document.addEventListener('focusout', () => { if (cur) hide(); });
			['pointerdown', 'dragstart', 'wheel'].forEach(t => document.addEventListener(t, () => { if (cur || timer) hide(); }, { capture: true, passive: true }));
			window.addEventListener('scroll', () => { if (cur) hide(); }, { capture: true, passive: true });
			document.addEventListener('keydown', e => { if (e.key === 'Escape' && cur) hide(); });
			this.hide_tip = hide;
		}

		// ---------- segmented controls: a sliding thumb that lifts into a magnifying lens (iOS 26) ----------

		// The selected segment's thumb is its own element, so it slides between segments. Pressing a segment lifts the
		// thumb into a lens that swells and magnifies the labels under it; drag it across and let go to choose.
		seg_sync(g) {
			if (!g || !g.offsetWidth) return;
			let th = g.querySelector(':scope > .sob-thumb');
			if (!th) {
				th = document.createElement('span');
				th.className = 'sob-thumb still';
				th.setAttribute('aria-hidden', 'true');
				th.innerHTML = '<span class="sob-lens"></span>';
				g.prepend(th);
				g.classList.add('sob-glide');
			}
			g.classList.toggle('scrolls', g.scrollWidth > g.clientWidth + 2);
			if (th.classList.contains('lift')) return;  // a finger is on it
			const on = g.querySelector(':scope > .lg-item[aria-pressed="true"], :scope > .lg-item[aria-selected="true"]');
			if (!on) { th.style.opacity = '0'; return; }
			const key = g.getAttribute('data-seg');
			const x = on.offsetLeft, w = on.offsetWidth;
			const segs = this._segs = this._segs || {};
			const place = (px, pw, anim) => { th.classList.toggle('still', !anim); th.style.translate = `${px}px 0`; th.style.width = `${pw}px`; };
			th.style.top = on.offsetTop + 'px';
			th.style.height = on.offsetHeight + 'px';
			th.style.opacity = '1';
			const prev = segs[key];
			if (!th._placed && prev && (prev.x !== x || prev.w !== w)) {
				// a re-rendered group (drawer tabs) starts where its thumb was, then slides
				place(prev.x, prev.w, false);
				void th.offsetWidth;
				place(x, w, true);
			} else if (!prev || prev.x !== x || prev.w !== w || !th._placed) place(x, w, !!th._placed);
			th._placed = true;
			segs[key] = { x, w };
		}

		bind_segs() {
			let drag = null;
			const items = g => [...g.querySelectorAll(':scope > .lg-item')];
			const fill = (g, th) => {
				// the lens shows a copy of the labels, laid out like the real ones; the lens's swell magnifies it
				const inner = document.createElement('div');
				inner.className = 'sob-lens-in';
				items(g).forEach(it => {
					const c = it.cloneNode(true);
					['data-tip', 'id', 'aria-describedby', 'data-board', 'data-view', 'data-measure', 'data-tab'].forEach(a => c.removeAttribute(a));
					c.setAttribute('tabindex', '-1');
					Object.assign(c.style, { left: it.offsetLeft + 'px', top: it.offsetTop + 'px', width: it.offsetWidth + 'px', height: it.offsetHeight + 'px' });
					inner.appendChild(c);
				});
				th.querySelector('.sob-lens').replaceChildren(inner);
				return inner;
			};
			const move = (x, anim) => {
				drag.th.classList.toggle('still', !anim);
				drag.th.style.translate = `${x}px 0`;
				drag.inner.style.translate = `${-x}px ${-drag.y}px`;
				drag.x = x;
			};
			const settle = (pick) => {
				const d = drag;
				drag = null;
				if (!d) return;
				d.th.classList.remove('lift');
				setTimeout(() => { if (!d.th.classList.contains('lift')) d.th.querySelector('.sob-lens').replaceChildren(); }, 320);
				const target = pick && pick(d);
				if (target && target.getAttribute('aria-pressed') !== 'true' && target.getAttribute('aria-selected') !== 'true') {
					this._seg_t = performance.now();
					target.click();
				}
				this.seg_sync(d.g);
			};
			const nearest = d => {
				if (!d.moved) return d.item;
				const mid = d.x + d.w / 2;
				return items(d.g).reduce((best, it) => (Math.abs(it.offsetLeft + it.offsetWidth / 2 - mid) < Math.abs(best.offsetLeft + best.offsetWidth / 2 - mid) ? it : best));
			};
			document.addEventListener('pointerdown', e => {
				const g = e.target.closest && e.target.closest('.sob-glide');
				if (!g || e.button !== 0 || drag) return;
				const it = e.target.closest('.lg-item');
				const th = g.querySelector(':scope > .sob-thumb');
				if (!it || it.parentNode !== g || !th || it.disabled) return;
				drag = { g, th, item: it, start: e.clientX, x0: it.offsetLeft, x: th._placed ? parseFloat(th.style.translate) || 0 : it.offsetLeft, w: it.offsetWidth, y: it.offsetTop, moved: false, pid: e.pointerId };
				th.style.width = it.offsetWidth + 'px';
				th.style.top = it.offsetTop + 'px';
				th.style.opacity = '1';
				drag.inner = fill(g, th);
				move(drag.x, false);
				void th.offsetWidth;
				th.classList.add('lift');
				// the lens jumps under the finger, magnifying the pressed label
				move(it.offsetLeft, true);
				if (!g.classList.contains('scrolls')) { try { g.setPointerCapture(e.pointerId); } catch (x) { /* old browsers */ } }
			});
			document.addEventListener('pointermove', e => {
				if (!drag || e.pointerId !== drag.pid || drag.g.classList.contains('scrolls')) return;
				const dx = e.clientX - drag.start;
				if (!drag.moved && Math.abs(dx) < 4) return;
				drag.moved = true;
				const last = items(drag.g).slice(-1)[0];
				const max = last.offsetLeft + last.offsetWidth - drag.w;
				move(Math.max(items(drag.g)[0].offsetLeft, Math.min(max, drag.x0 + dx)), false);
			}, { passive: true });
			document.addEventListener('pointerup', e => { if (drag && e.pointerId === drag.pid) settle(nearest); });
			document.addEventListener('pointercancel', e => { if (drag && e.pointerId === drag.pid) settle(null); });
			// the lens chose the segment already; drop the browser's own click that follows the pointerup
			document.addEventListener('click', e => {
				if (e.isTrusted && this._seg_t && performance.now() - this._seg_t < 500 && e.target.closest && e.target.closest('.sob-glide')) {
					e.stopPropagation();
					e.preventDefault();
				}
			}, true);
			window.addEventListener('resize', () => this.$root.find('[data-seg]').each((_, g) => this.seg_sync(g)), { passive: true });
		}

		bind_pop() {
			const $p = this.$pop;
			$p.on('click', '[data-pop-close]', () => this.close_pop());
			$p.on('click', '[data-pop-open]', e => { const name = this.pop && this.pop.name; const tab = $(e.currentTarget).attr('data-pop-open'); if (name) this.open(name, tab); });
			$p.on('click', '[data-pop-qnote]', e => {
				const name = this.pop && this.pop.name;
				if (!name) return;
				this.add_quick_note(name, $(e.currentTarget).attr('data-pop-qnote'), e.currentTarget).then(notes => this.pop_notes_landed(name, notes));
			});
			$p.on('click', '[data-pop-act="note-save"]', e => {
				const name = this.pop && this.pop.name;
				const $t = $p.find('[data-pop-note]');
				const text = ($t.val() || '').trim();
				if (!name || !text) { $t.trigger('focus'); return; }
				this.add_quick_note(name, text, e.currentTarget).then(notes => { $t.val(''); this.pop_notes_landed(name, notes); });
			});
			$p.on('keydown', '[data-pop-note]', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $p.find('[data-pop-act="note-save"]').trigger('click'); } });
			$p.on('click', '[data-pop-date]', e => this.pop_set_date($(e.currentTarget).attr('data-pop-date')));
			$p.on('click', '[data-pop-act="date-set"]', () => { const v = $p.find('[data-keep="pop-date"]').val(); if (v) this.pop_set_date(v); });
			$p.on('click', '[data-pop-act="date-clear"]', () => this.pop_set_date(null));
			$p.on('click', '[data-pop-stage]', e => {
				const name = this.pop && this.pop.name;
				const st = $(e.currentTarget).attr('data-pop-stage');
				if (!name) return;
				this.close_pop();
				this.apply(name, this.stage_patch(this.find(name), st), __('Moved to {0}', [__(st)]));
			});
			$p.on('click', '[data-act="vol-add"]', () => this.pop && this.vol_add(this.pop.name, $p));
			$p.on('click', '[data-vol-remove]', e => this.pop && this.vol_remove(this.pop.name, $(e.currentTarget).attr('data-vol-remove')));
			$p.on('change', '[data-vol-field]', e => this.pop && this.vol_change(this.pop.name, e.currentTarget));
			$p.on('click', '[data-act="req-add"]', () => this.pop && this.req_add(this.pop.name, $p));
			$p.on('click', '[data-req-remove]', e => this.pop && this.req_remove(this.pop.name, $(e.currentTarget).attr('data-req-remove')));
			$p.on('change', '[data-req-field]', e => this.pop && this.req_change(this.pop.name, e.currentTarget));
			$p.on('keydown', e => {
				if (e.key === 'Escape') { e.stopPropagation(); this.close_pop(); }
			});
			// close on a click outside, or when the board scrolls under it
			$(document).on('click.sobpop', e => {
				if (!this.pop) return;
				const path = (e.originalEvent && e.originalEvent.composedPath && e.originalEvent.composedPath()) || [];
				if (path.some(n => n === $p.get(0) || (n.nodeType === 1 && (n.hasAttribute('data-pop') || n.classList.contains('modal'))))) return;
				this.close_pop();
			});
			window.addEventListener('scroll', e => {
				if (!this.pop || $p.get(0).contains(e.target) || Date.now() - (this._quiet || 0) < 400) return;
				this.close_pop();
			}, { capture: true, passive: true });
			window.addEventListener('resize', () => this.close_pop(), { passive: true });
		}

		// add_note answers with the deal's notes, newest first
		pop_notes_landed(name, notes) {
			if (this.pop && this.pop.name === name && this.pop.kind === 'notes') { this.pop.notes = notes || []; this.render_pop(); }
		}

		pop_set_date(v) {
			const name = this.pop && this.pop.name;
			if (!name) return;
			this.close_pop();
			this.apply(name, { next_step_due: v || null }, v ? __('Follow-up set for {0}', [nice(v)]) : __('Follow-up cleared'));
		}

		// New Deal: for an account on the Leads board (preset when started from one), or a new account by name / Customer
		new_deal(opts) {
			opts = opts || {};
			const me = this.data.user;
			const choices = this.owner_choices(null);
			const open_stages = this.stages_of('deal').filter(x => !x.is_closed);
			const def_stage = this.first_stage_of('deal');
			const preset = opts.account ? this.find(opts.account) : null;
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
				title: preset ? __('New deal for {0}', [preset.account]) : __('New Deal'),
				fields: [
					{ fieldname: 'pipeline_account', fieldtype: 'Link', options: ACC_DT, label: __('Lead / Account'), default: preset ? preset.name : '',
						description: __('The account on the Leads board. Leave empty to start a new account.') },
					{ fieldname: 'account', fieldtype: 'Data', label: __('New account name'), depends_on: 'eval:!doc.pipeline_account',
						description: __('Required unless you choose an account or a Buyer.') },
					{ fieldname: 'customer', fieldtype: 'Link', options: 'Customer', label: __('Buyer'), depends_on: 'eval:!doc.pipeline_account',
						description: __('Optional. Choose an existing Customer to fill in the account and contact details.'),
						onchange: () => {
							const v = dlg.get_value('customer');
							if (!v || dlg.get_value('account')) return;
							frappe.db.get_value('Customer', v, 'customer_name').then(r => {
								const n = r && r.message && r.message.customer_name;
								if (n && !dlg.get_value('account') && dlg.get_value('customer') === v) dlg.set_value('account', n);
							});
						} },
					{ fieldname: 'stage', fieldtype: 'Select', label: __('Stage'), reqd: 1, options: open_stages.map(x => ({ value: x.name, label: __(x.name) })), default: def_stage,
						onchange: () => dlg.set_df_property('next_step_due', 'reqd', follow_needed(dlg.get_value('stage')) ? 1 : 0) },
					{ fieldname: 'deal_owner', fieldtype: 'Select', label: __('Owner'), reqd: 1, options: choices.map(o => ({ value: o.user, label: o.name })),
						default: choices.some(o => o.user === me) ? me : (choices[0] || {}).user, onchange: () => render_co() },
					{ fieldname: 'co_html', fieldtype: 'HTML' },
					{ fieldname: 'priority', fieldtype: 'Select', label: __('Priority'), options: prio, default: prio[Math.floor(prio.length / 2)] || '' },
					{ fieldname: 'next_step_due', fieldtype: 'Date', label: __('Next Follow-up'), reqd: follow_needed(def_stage) ? 1 : 0 },
					{ fieldtype: 'Section Break', label: __('Product') },
					{ fieldname: 'product_line', fieldtype: 'Select', label: __('Product Line'), options: [''].concat(lines), default: this.state.prods.length === 1 ? this.state.prods[0] : '',
						onchange: () => {
							const line = dlg.get_value('product_line');
							const t = tier_opts(line);
							dlg.set_df_property('tier', 'options', t);
							dlg.set_df_property('tier', 'read_only', t.length > 1 ? 0 : 1);
							if (!t.includes(dlg.get_value('tier'))) dlg.set_value('tier', '');
							// fresh frozen is quoted in lb and $/lb, extracts in grams and $/g
							const lb = this.fam_of(line) === 'lb';
							dlg.set_df_property('total_grams', 'label', lb ? __('Pounds') : __('Total Grams'));
							dlg.set_df_property('price_per_gram', 'label', lb ? __('Price per lb') : __('Price per Gram'));
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
					if (!v.pipeline_account && !(v.account || '').trim() && !v.customer) { frappe.msgprint(__('Please choose the account, or enter a new account name.')); return; }
					if (follow_needed(v.stage) && !v.next_step_due) { frappe.msgprint(__('Please set a Next Follow-up date. It is required for deals in {0}.', [__(v.stage)])); return; }
					const values = {};
					const keys = v.pipeline_account ? ['pipeline_account'] : ['account', 'customer'];
					keys.concat(['stage', 'deal_owner', 'priority', 'next_step_due', 'product_line', 'tier', 'total_grams', 'price_per_gram', 'value_override'])
						.forEach(k => { if (v[k] !== undefined && v[k] !== null && v[k] !== '' && !(NUM_FIELDS.includes(k) && !+v[k])) values[k] = v[k]; });
					if (co.length) values.co_owners = co.slice();
					if (this.fam_of(values.product_line) === 'lb') {
						if (values.total_grams) values.total_grams = +values.total_grams * LB;
						if (values.price_per_gram) values.price_per_gram = +values.price_per_gram / LB;
					}
					const acc = v.pipeline_account ? this.find(v.pipeline_account) : null;
					dlg.disable_primary_action();
					frappe.xcall(M + 'create_deal', { values }).then(name => {
						dlg.hide();
						frappe.show_alert({ message: __('Deal created for {0}', [acc ? acc.account : (values.account || values.customer)]), indicator: 'green' });
						this.load().then(() => this.open(name));
					}).catch(() => dlg.enable_primary_action());
				},
				secondary_action_label: __('Open full form'),
				secondary_action: () => {
					const v = dlg.get_values(true) || {};
					dlg.hide();
					const opts = {};
					['pipeline_account', 'account', 'customer', 'stage', 'deal_owner', 'priority', 'next_step_due', 'product_line', 'tier', 'total_grams', 'price_per_gram'].forEach(k => { if (v[k]) opts[k] = v[k]; });
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

		// New Lead (Leads board): the account, its status and owner, contact, and optionally the first volume row
		new_account() {
			const me = this.data.user;
			const choices = this.owner_choices(null);
			const statuses = this.stages_of('lead');
			const lines = this.s.product_lines || [];
			const tier_opts = line => [''].concat(this.tiers_for(line));
			const dlg = new frappe.ui.Dialog({
				title: __('New Lead'),
				fields: [
					{ fieldname: 'account_name', fieldtype: 'Data', label: __('Account'), description: __('Required unless you choose a Customer.') },
					{ fieldname: 'customer', fieldtype: 'Link', options: 'Customer', label: __('Customer'),
						description: __('Optional. For an existing customer: fills the name and contact details.'),
						onchange: () => {
							const c = dlg.get_value('customer');
							if (!c || dlg.get_value('account_name')) return;
							frappe.db.get_value('Customer', c, 'customer_name').then(r => {
								const n = r && r.message && r.message.customer_name;
								if (n && !dlg.get_value('account_name') && dlg.get_value('customer') === c) dlg.set_value('account_name', n);
							});
						} },
					{ fieldname: 'lead_status', fieldtype: 'Select', label: __('Lead status'), reqd: 1, options: statuses.map(x => ({ value: x.name, label: __(x.name) })), default: this.s.first_status || (statuses[0] || {}).name },
					{ fieldname: 'account_owner', fieldtype: 'Select', label: __('Relationship manager'), reqd: 1, options: choices.map(o => ({ value: o.user, label: o.name })),
						default: choices.some(o => o.user === me) ? me : (choices[0] || {}).user },
					{ fieldname: 'next_step_due', fieldtype: 'Date', label: __('Next Follow-up') },
					{ fieldtype: 'Column Break' },
					{ fieldname: 'contact_name', fieldtype: 'Data', label: __('Contact Name') },
					{ fieldname: 'phone', fieldtype: 'Data', label: __('Phone') },
					{ fieldname: 'email', fieldtype: 'Data', options: 'Email', label: __('Email') },
					{ fieldname: 'lead_source', fieldtype: 'Select', label: __('Lead Source'), options: [''].concat(this.s.lists.lead_source || []) },
					{ fieldtype: 'Section Break', label: __('Volume and demand'), description: __('Optional. More product lines can be added on the account.') },
					{ fieldname: 'product_line', fieldtype: 'Select', label: __('Product Line'), options: [''].concat(lines),
						onchange: () => {
							const line = dlg.get_value('product_line');
							const t = tier_opts(line);
							dlg.set_df_property('tier', 'options', t);
							dlg.set_df_property('tier', 'read_only', t.length > 1 ? 0 : 1);
							if (!t.includes(dlg.get_value('tier'))) dlg.set_value('tier', '');
							// the unit comes from the line's SKUs: lb for fresh frozen, g or kg for extracts
							const lb = this.fam_of(line) === 'lb';
							const units = lb ? ['lb'] : ['g', 'kg'];
							dlg.set_df_property('uom', 'options', units);
							dlg.set_value('uom', units.includes(this.unit_of(line)) ? this.unit_of(line) : units[0]);
							dlg.set_df_property('uom', 'read_only', lb ? 1 : 0);
							dlg.set_df_property('price', 'label', lb ? __('Price per lb') : __('Price per Gram'));
						} },
					{ fieldname: 'tier', fieldtype: 'Select', label: __('Tier'), options: [''], read_only: 1 },
					{ fieldname: 'activity', fieldtype: 'Select', label: __('They'), options: [{ value: 'Procure', label: __('Procure (buy)') }, { value: 'Produce', label: __('Produce (make)') }], default: 'Procure' },
					{ fieldname: 'weekly_volume', fieldtype: 'Float', label: __('Volume / week') },
					{ fieldtype: 'Column Break' },
					{ fieldname: 'wants_qty', fieldtype: 'Float', label: __('Wants from us') },
					{ fieldname: 'wants_per', fieldtype: 'Select', label: __('Per'), options: [{ value: 'Month', label: __('Month') }, { value: 'Week', label: __('Week') }], default: 'Month' },
					{ fieldname: 'uom', fieldtype: 'Select', label: __('Unit'), options: ['g', 'kg'], default: 'g', description: __('Set by the product line: lb for fresh frozen, g or kg for extracts') },
					{ fieldname: 'price', fieldtype: 'Currency', label: __('Price per Gram'), description: __('Empty uses the product line\'s default price') },
				],
				primary_action_label: __('Create lead'),
				primary_action: v => {
					if (!(v.account_name || '').trim() && !v.customer) { frappe.msgprint(__('Please enter the account name or choose a Customer.')); return; }
					const values = {};
					['account_name', 'customer', 'lead_status', 'account_owner', 'next_step_due', 'contact_name', 'phone', 'email', 'lead_source']
						.forEach(k => { if (v[k]) values[k] = v[k]; });
					if (v.product_line) {
						values.volume = [{ product_line: v.product_line, tier: v.tier || '', activity: v.activity || 'Procure', weekly_volume: +v.weekly_volume || 0,
							wants_qty: +v.wants_qty || 0, wants_per: v.wants_per || 'Month', uom: v.uom || 'g', price: +v.price || 0 }];
					}
					dlg.disable_primary_action();
					frappe.xcall(M + 'create_account', { values }).then(name => {
						dlg.hide();
						frappe.show_alert({ message: __('{0} added to the Leads board', [values.account_name || values.customer]), indicator: 'green' });
						this.load().then(() => this.open(name, values.volume ? 'overview' : 'volume'));
					}).catch(() => dlg.enable_primary_action());
				},
			});
			dlg.show();
		}

		email_to(d) { return (d && (d.email || d.customer_email)) || ''; }

		email_button(d) {
			const to = this.email_to(d);
			if (to) return `<button type="button" class="sob-btn" data-act="email" data-tip="${esc(__('Email {0}', [to]))}">${__('Email')}</button>`;
			const tip = __("Add the buyer's email in the Buyer tab first.");
			return `<span class="sob-tip" tabindex="0" data-tip="${esc(tip)}" aria-label="${esc(tip)}"><button type="button" class="sob-btn" disabled aria-disabled="true">${__('Email')}</button></span>`;
		}

		// Standard composer on the deal: the sent email is a Communication linked to the deal (timeline + Activity).
		email_deal(name) {
			const d = this.find(name);
			const to = this.email_to(d);
			if (!d || !to) return;
			const dt = dt_of(name);
			if (!frappe.views.CommunicationComposer) { frappe.msgprint(__('The email composer could not be loaded. Please refresh the page.')); return; }
			const files = frappe.db.get_list('File', {
				filters: { attached_to_doctype: dt, attached_to_name: name }, fields: ['name', 'file_name', 'file_url', 'is_private'], limit: 50,
			}).catch(() => []);
			Promise.all([frappe.model.with_doc(dt, name), files]).then(([doc, attachments]) => {
				const Base = frappe.views.CommunicationComposer;
				class DealComposer extends Base {
					// new attachments go onto the deal, like they do from the form
					setup_attach() {
						super.setup_attach();
						$(this.dialog.fields_dict.select_attachments.wrapper).find('.add-more-attachments button').off('click').on('click', () => new frappe.ui.FileUploader({
							doctype: dt, docname: name, folder: 'Home/Attachments',
							on_success: a => { this.attachments.push(a); this.render_attachment_rows(a); },
						}));
					}
				}
				new DealComposer({
					doc: doc || frappe.get_doc(dt, name),
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
			const lead = this.state.board === 'lead';
			const names = (this.state.view === 'list' ? this.list_order() : (lead ? this.filtered_acc() : this.filtered())).map(d => d.name);
			if (!names.length) { frappe.msgprint(lead ? __('No accounts match the current filters.') : __('No deals match the current filters.')); return; }
			open_url_post('/api/method/' + M + (lead ? 'export_accounts_xlsx' : 'export_xlsx'), { names: JSON.stringify(names) });
		}

		list_order() {
			// export in the order shown in List view
			const order = [];
			this.$root.find('.sob-table tbody tr[data-open]').each((_, el) => order.push($(el).attr('data-open')));
			const all = this.state.board === 'lead' ? this.filtered_acc() : this.filtered();
			return order.length ? order.map(n => all.find(d => d.name === n)).filter(Boolean) : all;
		}

		// ---------- events ----------

		bind() {
			const $r = this.$root, $d = this.$drawer;
			$r.on('click', '[data-view]', e => this.set({ view: $(e.currentTarget).attr('data-view') }));
			$r.on('click', '[data-board]', e => this.set({ board: $(e.currentTarget).attr('data-board') }));
			$r.on('click', '[data-measure]', e => this.set({ measure: $(e.currentTarget).attr('data-measure') }));
			// totals for All products, Extracts, Fresh Frozen, Tolling: arrows, dots, arrow keys and a swipe on touch
			$r.on('click', '[data-kpage]', e => this.set_kgroup(+$(e.currentTarget).attr('data-kpage')));
			$r.on('click', '[data-kgroup]', e => this.set_kgroup(0, $(e.currentTarget).attr('data-kgroup')));
			$r.on('keydown', '.sob-kpage', e => {
				if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
				e.preventDefault();
				this.set_kgroup(e.key === 'ArrowRight' ? 1 : -1);
				this.$root.find(`.sob-kpage [data-kpage="${e.key === 'ArrowRight' ? 1 : -1}"]`).trigger('focus');
			});
			let swipe = null;
			$r.on('pointerdown', '.sob-kpis', e => { const o = e.originalEvent; swipe = o.pointerType === 'touch' ? { x: o.clientX, y: o.clientY } : null; });
			$r.on('pointerup', '.sob-kpis', e => {
				const o = e.originalEvent;
				if (!swipe) return;
				const dx = o.clientX - swipe.x, dy = o.clientY - swipe.y;
				swipe = null;
				if (Math.abs(dx) > 48 && Math.abs(dy) < 32) this.set_kgroup(dx < 0 ? 1 : -1);
			});
			$r.on('click', '[data-tips-toggle]', () => {
				this.tips_off = !this.tips_off;
				try { localStorage.setItem('sob_tips_off', this.tips_off ? '1' : '0'); } catch (x) { /* storage off */ }
				if (this.hide_tip) this.hide_tip();
				this.render_filters();
			});
			// card shortcuts: keep their clicks and drags away from the card (which opens or drags the deal)
			$r.on('mousedown dragstart', '.sob-card-acts', e => e.stopPropagation());
			$r.on('click', '[data-pop]', e => {
				e.preventDefault();
				e.stopPropagation();
				const el = e.currentTarget;
				this.open_pop(el.getAttribute('data-pop'), el.getAttribute('data-deal'), el);
			});
			$r.on('click', '[data-card-call]', e => e.stopPropagation());
			$r.on('click', '[data-card-email]', e => { e.preventDefault(); e.stopPropagation(); this.email_deal($(e.currentTarget).attr('data-card-email')); });
			$r.on('click', '[data-card-hist]', e => { e.preventDefault(); e.stopPropagation(); this.open($(e.currentTarget).attr('data-card-hist'), 'purchases'); });
			$r.on('click', '[data-reopen]', e => { e.preventDefault(); e.stopPropagation(); this.reopen($(e.currentTarget).attr('data-reopen')); });
			$r.on('click', '[data-new-deal]', e => { e.preventDefault(); e.stopPropagation(); this.new_deal({ account: $(e.currentTarget).attr('data-new-deal') }); });
			$r.on('click', '[data-owner]', e => {
				const v = $(e.currentTarget).attr('data-owner');
				let owners = (this.state.owners || []).slice();
				if (!v) owners = [];
				else owners = owners.includes(v) ? owners.filter(x => x !== v) : owners.concat([v]);
				this.set({ owners });
			});
			// Owner, Product line and Filters menus
			$r.on('click', '[data-menu]', e => {
				const k = $(e.currentTarget).attr('data-menu');
				this.menu(k, this._menu !== k);
			});
			$r.on('change', '[data-prod]', e => {
				const v = $(e.currentTarget).attr('data-prod');
				let prods = this.state.prods.slice();
				if (!v) prods = [];
				else prods = prods.includes(v) ? prods.filter(x => x !== v) : prods.concat([v]);
				// keep Settings order so the label and URL read the same every time
				prods = (this.s.product_lines || []).filter(p => prods.includes(p));
				this.set({ prods });
			});
			// close on a click outside; the event path is read at dispatch, so a row re-rendered by the click still counts as inside
			$(document).on('click.sob', e => {
				if (!this._menu) return;
				const path = (e.originalEvent && e.originalEvent.composedPath && e.originalEvent.composedPath()) || [];
				const inside = path.some(n => n.nodeType === 1 && (n.hasAttribute('data-menu-panel') || n.hasAttribute('data-menu')));
				if (!inside) this.menu(null, false);
			});
			$r.on('keydown', '[data-menu-panel], [data-menu]', e => {
				if (e.key === 'Escape' && this._menu) {
					e.stopPropagation();
					const k = this._menu;
					this.menu(null, false);
					$r.find(`[data-menu="${k}"]`).trigger('focus');
				}
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
				if (e.target !== e.currentTarget && $(e.target).closest('button, a').length) return;
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
			// List view cells: save on change; wait a tick so Tab or Enter has moved focus before the sheet re-renders
			$r.on('change', '.sob-inline', e => {
				const el = e.currentTarget;
				if (this._list_rendering || !document.contains(el)) return;
				const name = el.getAttribute('data-inline'), field = el.getAttribute('data-field');
				let v = el.value;
				if (el.type === 'number' || el.hasAttribute('data-money')) {
					v = String(v || '').replace(/[$,\s]/g, '');
					v = v === '' ? null : Number(v);
					if (v !== null && (!isFinite(v) || v < 0)) { frappe.show_alert({ message: __('Please enter a number of 0 or more.'), indicator: 'red' }); el.value = el.getAttribute('data-orig') || ''; return; }
				} else v = (v || '').trim() || null;
				if (String(v == null ? '' : v) === (el.getAttribute('data-orig') || '')) return;
				el.setAttribute('data-orig', v == null ? '' : String(v));
				setTimeout(() => this.apply(name, { [field]: v }, __('Saved')), 0);
			});
			// Enter moves down to the same column (spreadsheet), Escape puts the old value back
			$r.on('keydown', '.sob-cell-in', e => {
				const el = e.currentTarget;
				if (e.key === 'Escape') {
					e.preventDefault();
					e.stopPropagation();
					el.value = el.getAttribute('data-orig') || '';
					el.blur();
				} else if (e.key === 'Enter' && el.tagName === 'INPUT') {
					e.preventDefault();
					const field = el.getAttribute('data-field');
					const next = $(el).closest('tr').nextAll('tr').find(`.sob-cell-in[data-field="${field}"]`).get(0);
					if (next) { next.focus(); try { next.select(); } catch (x) { /* date inputs */ } } else el.blur();
				}
			});
			$r.on('click', '[data-act="need"]', () => this.set({ need: !this.state.need }));
			$r.on('focus', '[data-money]', e => { const el = e.currentTarget; el.value = el.getAttribute('data-raw') || ''; try { el.select(); } catch (x) { /* ignore */ } });
			$r.on('blur', '[data-money]', e => {
				const el = e.currentTarget;
				const n = Number(String(el.value || '').replace(/[$,\s]/g, ''));
				if (el.value !== '' && isFinite(n)) setTimeout(() => { if (document.contains(el) && document.activeElement !== el) el.value = usd(n); }, 0);
			});
			$r.on('click', '[data-cell-buyer]', e => { e.stopPropagation(); this.open($(e.currentTarget).attr('data-cell-buyer'), 'buyer'); });
			$r.on('click', '[data-act="cols"]', e => {
				const $m = $r.find('.sob-colpick-menu');
				const open = $m.prop('hidden');
				$m.prop('hidden', !open);
				$(e.currentTarget).attr('aria-expanded', open);
			});
			$r.on('change', '[data-col]', () => {
				const acc = this.state.board === 'lead';
				const cols = [];
				$r.find('[data-col]:checked').each((_, el) => cols.push($(el).attr('data-col')));
				let next = (acc ? ACC_COLS : LIST_COLS).map(c => c[0]).filter(k => cols.includes(k));
				if (!next.length) next = ['account'];
				if (acc) this.acc_cols = next; else this.cols = next;
				try { localStorage.setItem(acc ? LS_ACC_COLS : LS_COLS, JSON.stringify(next)); } catch (x) { /* storage off */ }
				this.render();
				$r.find('.sob-colpick-menu').prop('hidden', false);
			});
			$r.on('click', '[data-act="cols-reset"]', () => {
				const acc = this.state.board === 'lead';
				if (acc) this.acc_cols = ACC_DEFAULT_COLS.slice(); else this.cols = DEFAULT_COLS.slice();
				try { localStorage.removeItem(acc ? LS_ACC_COLS : LS_COLS); } catch (x) { /* storage off */ }
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
				const card = drag.kind === 'card' ? this.find(drag.name) : null;
				if (card && el.hasAttribute('data-drop-stage')) {
					// cards only drop on their own board's columns
					if (!!card._acc !== (this.state.board === 'lead')) return;
					this.apply(drag.name, this.stage_patch(card, el.getAttribute('data-drop-stage')));
				} else if (card && el.hasAttribute('data-drop-owner')) {
					const owner = el.getAttribute('data-drop-owner');
					if (drag.from && drag.from === owner) return;  // dropped back in its own column
					this.apply(drag.name, { [this.own_field(card)]: owner }, __('Reassigned to {0}', [this.owner_name(owner)]));
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
			$d.on('click', '[data-move]', e => this.apply(this.state.sel, this.stage_patch(this.find(this.state.sel), $(e.currentTarget).attr('data-move'))));
			$d.on('change', '[data-panel-field]', e => this.apply(this.state.sel, { [$(e.currentTarget).attr('data-panel-field')]: e.currentTarget.value || null }));
			$d.on('click', '[data-act="form"]', () => frappe.set_route('Form', dt_of(this.state.sel), this.state.sel));
			$d.on('click', '[data-open-acc]', e => this.open($(e.currentTarget).attr('data-open-acc')));
			$d.on('click', '[data-open-deal]', e => this.open($(e.currentTarget).attr('data-open-deal')));
			$d.on('click', '[data-new-deal]', e => this.new_deal({ account: $(e.currentTarget).attr('data-new-deal') }));
			$d.on('click', '[data-reopen]', e => this.reopen($(e.currentTarget).attr('data-reopen')));
			// volume rows of an account
			$d.on('click', '[data-act="vol-add"]', () => this.vol_add(this.state.sel, this.$drawer));
			$d.on('click', '[data-vol-remove]', e => this.vol_remove(this.state.sel, $(e.currentTarget).attr('data-vol-remove')));
			$d.on('change', '[data-vol-field]', e => this.vol_change(this.state.sel, e.currentTarget));
			$d.on('click', '[data-act="email"]', () => this.email_deal(this.state.sel));
			// quick notes
			$d.on('click', '[data-qnote]', e => this.add_quick_note(this.state.sel, $(e.currentTarget).attr('data-qnote'), e.currentTarget));
			// manual deal value
			$d.on('click', '[data-act="value-reset"]', () => this.apply(this.state.sel, { value_override: 0 }, __('Deal value now follows the requirements')));
			// requirement lines
			$d.on('click', '[data-act="req-add"]', () => this.req_add(this.state.sel, this.$drawer));
			$d.on('click', '[data-req-remove]', e => this.req_remove(this.state.sel, $(e.currentTarget).attr('data-req-remove')));
			$d.on('change', '[data-req-field]', e => this.req_change(this.state.sel, e.currentTarget));
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
				frappe.xcall(M + 'add_note', { name, note, doctype: dt_of(name) }).then(notes => {
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
		if (wrapper.sob_board) { wrapper.sob_board.$drawer.prop('hidden', true); wrapper.sob_board.close_pop(); }
	};
})();
