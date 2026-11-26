// Toll Processing Board: customer-owned Fresh Frozen received, washed, pressed and returned. Look: the Sales
// Operation Board (Motley Glass kit, /assets/cannabis_management/css/motley_glass.css). Every action calls
// cannabis_management.toll.api, which creates the stock documents on the server; this file only renders and calls.
const TPB_M = 'cannabis_management.toll.api.';
const TPB_LB_TO_G = 453.592;
const TPB_COLS = [
	{ k: 'Received', c: '#8e8e93' }, { k: 'Queued for Wash', c: '#5856d6' }, { k: 'Washed', c: '#ff9f0a' },
	{ k: 'Pressed', c: '#d2691e' }, { k: 'Ready to Return', c: '#34c759' }, { k: 'Returned', c: '#0a84ff' },
	{ k: 'Invoiced', c: '#af52de' },
];
const TPB_CLOSED = ['Returned', 'Invoiced'];
const TPB_EMPTY = {
	'Received': __('No material waiting. Use Receive Material when a client delivers.'),
	'Queued for Wash': __('Drag a received job here to plan its wash.'),
	'Washed': __('No bubble hash waiting to press.'),
	'Pressed': __('No partly pressed jobs.'),
	'Ready to Return': __('Nothing ready to ship back.'),
	'Returned': __('All returned jobs are invoiced.'),
	'Invoiced': __('No invoiced jobs yet.'),
};
const TPB_DOTS = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>';

const tpb_esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const tpb_fmt = (n, d = 0) => Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const tpb_date = d => d ? frappe.datetime.str_to_user(d) : '—';
const tpb_money = n => format_currency(n || 0, frappe.boot.sysdefaults.currency || 'USD');

frappe.pages['toll-processing-board'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Toll Processing Board'), single_column: true });
	$(wrapper).addClass('mg-glass-page toll-processing-board-page');
	$('<div class="mg-bg" aria-hidden="true"><i></i></div>').prependTo(wrapper);
	const root = $('<div class="mg tpb"><div class="mg-loading">' + __('Loading…') + '</div></div>').appendTo(page.main);
	wrapper.tpb = new TollProcessingBoard(root[0], page);
};

frappe.pages['toll-processing-board'].on_page_show = function (wrapper) {
	wrapper.tpb && wrapper.tpb.ready && wrapper.tpb.refresh();
};

class TollProcessingBoard {
	constructor(el, page) {
		this.el = el;
		this.page = page;
		this.ctx = null;
		this.data = null;
		this.ready = false;
		this.busy = 0;
		this.filters = { customer: '', strain: '', return_type: '', from_date: '', to_date: '', show_closed: 0 };
		this.init();
		frappe.realtime.on('list_update', d => {
			if (d && d.doctype === 'Toll Job' && this.ready && frappe.get_route()[0] === 'toll-processing-board') this.debounce(() => this.idle() && this.refresh(), 1500);
		});
		frappe.realtime.doctype_subscribe && frappe.realtime.doctype_subscribe('Toll Job');
		document.addEventListener('click', () => this.close_menus());
	}

	debounce(fn, ms) { clearTimeout(this._t); this._t = setTimeout(fn, ms); }
	idle() { return !this.busy && !(window.cur_dialog && cur_dialog.display); }

	call(method, args) {
		return frappe.call({ method: TPB_M + method, args: args || {} }).then(r => r.message);
	}

	async init() {
		try {
			this.ctx = await this.call('get_context');
		} catch (e) {
			$(this.el).html('<div class="mg-empty">' + __('The board could not be loaded.') + '</div>');
			return;
		}
		if (this.ctx.can.produce) this.page.set_primary_action(__('Receive Material'), () => this.receive_dialog(), 'add');
		this.page.set_secondary_action(__('Refresh'), () => this.refresh(true), 'refresh');
		this.shell();
		this.ready = true;
		await this.refresh();
	}

	shell() {
		const c = this.ctx;
		const opts = (list, all) => '<option value="">' + tpb_esc(all) + '</option>' + list.map(o =>
			'<option value="' + tpb_esc(o.value) + '">' + tpb_esc(o.label) + '</option>').join('');
		this.el.innerHTML = `
			<div class="mg-hint">${__('Customer-owned material received for washing and pressing. Each action creates its stock document at zero value in the Toll warehouses.')}</div>
			<div class="mg-bar"><div class="mg-glass" role="toolbar" aria-label="${__('Filters')}">
				<select class="mg-in" data-f="customer" aria-label="${__('Customer')}">${opts(c.customers.map(x => ({ value: x.name, label: x.customer_name || x.name })), __('All customers'))}</select>
				<span class="mg-sep"></span>
				<input class="mg-in" data-f="strain" placeholder="${__('Strain')}" aria-label="${__('Strain')}">
				<span class="mg-sep"></span>
				<select class="mg-in" data-f="return_type" aria-label="${__('Return Type')}">${opts(c.return_types.map(x => ({ value: x, label: __(x) })), __('All return types'))}</select>
				<span class="mg-sep"></span>
				<input class="mg-in tpb-date" type="date" data-f="from_date" title="${__('Received from')}" aria-label="${__('Received from')}">
				<input class="mg-in tpb-date" type="date" data-f="to_date" title="${__('Received to')}" aria-label="${__('Received to')}">
				<span class="mg-sep"></span>
				<button class="mg-chip" data-closed aria-pressed="false">${__('Show returned & invoiced')}</button>
			</div></div>
			<div class="mg-kpis tpb-kpis"></div>
			<div class="mg-scroll"><div class="mg-cols tpb-board"></div></div>`;
		const $el = $(this.el);
		$el.on('input change', '[data-f]', e => {
			const t = e.currentTarget;
			this.filters[t.dataset.f] = t.value;
			this.debounce(() => this.refresh(), t.dataset.f === 'strain' ? 350 : 0);
		});
		$el.on('click', '[data-closed]', e => {
			const on = !this.filters.show_closed;
			this.filters.show_closed = on ? 1 : 0;
			e.currentTarget.setAttribute('aria-pressed', on ? 'true' : 'false');
			this.refresh();
		});
		$el.on('click', '[data-act]', e => {
			e.preventDefault(); e.stopPropagation();
			this.close_menus();
			this.act(e.currentTarget.dataset.act, e.currentTarget.dataset.id);
		});
		$el.on('click', '[data-menu]', e => {
			e.stopPropagation();
			const m = this.el.querySelector('#tpb-m-' + CSS.escape(e.currentTarget.dataset.menu));
			const open = !m.hidden;
			this.close_menus();
			if (!open) { m.hidden = false; e.currentTarget.setAttribute('aria-expanded', 'true'); }
		});
	}

	close_menus() {
		this.el.querySelectorAll('.mg-menu').forEach(m => { m.hidden = true; });
		this.el.querySelectorAll('[data-menu][aria-expanded="true"]').forEach(b => b.setAttribute('aria-expanded', 'false'));
	}

	async refresh(alert) {
		if (!this.ready) return;
		const seq = (this._seq = (this._seq || 0) + 1);
		try {
			const data = await this.call('get_board_data', { filters: this.filters });
			if (seq !== this._seq) return;
			this.data = data;
			this.render();
			if (alert) frappe.show_alert({ message: __('Board refreshed.'), indicator: 'green' }, 3);
		} catch (e) { /* frappe shows the error */ }
	}

	job(id) { return (this.data && this.data.jobs || []).find(j => j.name === id); }

	render() {
		const d = this.data, k = d.kpis;
		const kpi = (label, value, sub, cls) => `<div class="mg-kpi ${cls || ''}"><div class="mg-kpi-label">${label}</div><div class="mg-kpi-value">${value}</div><div class="mg-kpi-sub">${sub}</div></div>`;
		this.el.querySelector('.tpb-kpis').innerHTML =
			kpi(__('FF on hand'), tpb_fmt(k.ff_on_hand_lbs, 1) + ' lbs', __('in Toll Inbound')) +
			kpi(__('Bubble Hash in WIP'), tpb_fmt(k.bh_wip_grams) + ' g', __('waiting to press')) +
			kpi(__('Ready to ship'), tpb_fmt(k.output_ready_grams) + ' g', __('BH and rosin in Toll Output')) +
			kpi(__('Past promised date'), k.overdue, k.overdue === 1 ? __('job') : __('jobs'), k.overdue ? 'attn' : '') +
			kpi(__('Returned, not invoiced'), k.uninvoiced_returned, k.uninvoiced_returned === 1 ? __('job') : __('jobs'), k.uninvoiced_returned ? 'attn' : '');
		const show_closed = !!this.filters.show_closed;
		const cols = TPB_COLS.filter(c => show_closed || !TPB_CLOSED.includes(c.k));
		this.el.querySelector('.tpb-board').innerHTML = cols.map(c => {
			const cards = d.jobs.filter(j => j.status === c.k);
			return `<section class="mg-col" style="--mg-stage:${c.c}" data-col="${tpb_esc(c.k)}">
				<div class="mg-col-head"><div class="mg-col-title"><span>${__(c.k)}</span><span class="mg-col-count">${cards.length}</span></div>
				<div class="mg-col-sub">${this.col_sub(c.k, cards)}</div></div>
				${cards.length ? cards.map(j => this.card(j)).join('') : `<div class="mg-col-empty">${TPB_EMPTY[c.k]}</div>`}</section>`;
		}).join('');
		this.wire_drag();
	}

	col_sub(k, cards) {
		const sum = f => cards.reduce((a, j) => a + (j[f] || 0), 0);
		if (!cards.length) return '&nbsp;';
		if (k === 'Received' || k === 'Queued for Wash') return tpb_fmt(sum('ff_balance_lbs'), 1) + ' lbs ' + __('to wash');
		if (k === 'Washed' || k === 'Pressed') return tpb_fmt(sum('bh_wip_grams')) + ' g ' + __('BH to press');
		if (k === 'Ready to Return') return tpb_fmt(sum('bh_output_grams') + sum('rosin_output_grams')) + ' g ' + __('to ship');
		if (k === 'Returned') return cards.some(j => j.rate > 0) ? tpb_money(sum('amount')) + ' ' + __('billable') : __('set a rate to bill');
		return tpb_money(sum('amount')) + ' ' + __('invoiced');
	}

	card(j) {
		const s = j.status, can = this.ctx.can;
		const pct = j.ff_received_lbs ? Math.min(100, j.ff_washed_lbs / j.ff_received_lbs * 100) : 0;
		let rows = `<span>${__('FF washed')}</span><b>${tpb_fmt(j.ff_washed_lbs, 1)} / ${tpb_fmt(j.ff_received_lbs, 1)} lbs</b>`;
		if (j.bh_grams > 0) rows += `<span>${__('Bubble hash')}</span><b>${tpb_fmt(j.bh_grams)} g · ${tpb_fmt(j.wash_yield, 2)}%</b>`;
		if (j.rosin_grams > 0) rows += `<span>${__('Rosin')}</span><b>${tpb_fmt(j.rosin_grams)} g · ${tpb_fmt(j.press_yield, 1)}%</b>`;
		if (j.bh_wip_grams > 0) rows += `<span>${__('BH in WIP')}</span><b>${tpb_fmt(j.bh_wip_grams)} g</b>`;
		if (j.bh_output_grams > 0 || j.rosin_output_grams > 0) {
			rows += `<span>${__('To ship')}</span><b>${[j.bh_output_grams > 0 ? tpb_fmt(j.bh_output_grams) + ' g BH' : '',
				j.rosin_output_grams > 0 ? tpb_fmt(j.rosin_output_grams) + ' g ' + __('rosin') : ''].filter(Boolean).join(', ')}</b>`;
		}
		if (s === 'Returned' || s === 'Invoiced') {
			rows += `<span>${__('Returned')}</span><b>${[j.returned_bh_grams ? tpb_fmt(j.returned_bh_grams) + ' g BH' : '',
				j.returned_rosin_grams ? tpb_fmt(j.returned_rosin_grams) + ' g ' + __('rosin') : ''].filter(Boolean).join(', ') || '—'}</b>`;
			if (j.rate > 0) rows += `<span>${s === 'Invoiced' ? __('Invoiced') : __('Billable')}</span><b>${tpb_money(j.amount)}</b>`;
		}
		const show_bar = (j.ff_balance_lbs > 0 && j.ff_washed_lbs > 0) || s === 'Received' || s === 'Queued for Wash';
		const drag = can.produce && (s === 'Received' || s === 'Queued for Wash');
		const menu = this.menu_items(j, s);
		const rt_cls = { 'Bubble Hash': 'warn', 'Rosin': 'act', 'Both': 'accent' }[j.return_type] || '';
		return `<article class="mg-card tpb-card" data-id="${tpb_esc(j.name)}" ${drag ? 'draggable="true"' : ''}>
			<div class="top"><a class="id" href="/app/toll-job/${encodeURIComponent(j.name)}">${tpb_esc(j.name)}</a>
				<span class="mg-badge ${rt_cls}">${tpb_esc(__(j.return_type))}</span></div>
			<div class="cust">${tpb_esc(j.customer_name || j.customer)}</div>
			<div class="strain">${tpb_esc(j.strain)}</div>
			<div class="path" aria-label="${__('Material stage')}"><span class="ff on">FF</span><span class="bh ${j.bh_grams > 0 ? 'on' : ''}">BH</span><span class="ro ${j.rosin_grams > 0 ? 'on' : ''} ${j.return_type === 'Bubble Hash' ? 'na' : ''}">${__('Rosin')}</span>
				${j.priority === 'Rush' ? `<span class="mg-badge bad">${__('Rush')}</span>` : ''}${j.overdue ? `<span class="mg-badge act">${__('Overdue')}</span>` : ''}</div>
			${show_bar ? `<div class="bar" title="${tpb_fmt(pct)}% ${__('washed')}"><i style="width:${pct}%"></i></div>` : ''}
			<div class="nums">${rows}</div>
			<div class="meta"><span>${__('Received')} ${tpb_date(j.received_date)}</span><span class="${j.overdue ? 'late' : ''}">${__('Due')} ${tpb_date(j.promised_return_date)}</span>${j.physical_location ? `<span>${tpb_esc(j.physical_location)}</span>` : ''}</div>
			<div class="acts">${this.primary_btn(j, s)}${menu ? `<div class="more"><button class="mg-btn sm icon" data-menu="${tpb_esc(j.name)}" aria-haspopup="true" aria-expanded="false" aria-label="${__('More actions')}">${TPB_DOTS}</button><div class="mg-menu" id="tpb-m-${tpb_esc(j.name)}" hidden>${menu}</div></div>` : ''}</div>
		</article>`;
	}

	primary_btn(j, s) {
		const can = this.ctx.can;
		let m = null;
		if ((s === 'Received' || s === 'Queued for Wash') && can.produce) m = ['wash', __('Record Wash')];
		else if (s === 'Washed' && can.produce && j.return_type !== 'Bubble Hash') m = ['press', __('Record Press')];
		else if (s === 'Pressed' && can.produce) m = j.return_type === 'Both' ? ['move', __('Move BH to Output')] : ['press', __('Record Press')];
		else if (s === 'Ready to Return' && can.produce) m = ['ret', __('Return to Client')];
		else if (s === 'Returned' && can.invoice) m = j.sales_invoice && j.invoice_status === 'Draft' ? ['viewinv', __('Open Draft Invoice')] : ['inv', __('Create Invoice')];
		else if (s === 'Invoiced') m = ['viewinv', __('View Invoice')];
		return m ? `<button class="mg-btn sm primary" data-act="${m[0]}" data-id="${tpb_esc(j.name)}">${m[1]}</button>` : '';
	}

	menu_items(j, s) {
		const can = this.ctx.can, it = [];
		if (can.produce) {
			if (s === 'Received') it.push(['queue', __('Move to Queued for Wash')]);
			if (s === 'Queued for Wash') it.push(['unqueue', __('Move back to Received')]);
			if (s === 'Washed' && j.return_type === 'Both') it.push(['move', __('Move BH to Output')]);
			if (s === 'Pressed' && j.return_type === 'Both') it.push(['press', __('Record Press')]);
			if (s === 'Pressed' && j.return_type === 'Rosin') it.push(['move', __('Move leftover BH to Output')]);
		}
		if (j.delivery_note && (s === 'Returned' || s === 'Invoiced')) it.push(['viewdn', __('View Delivery Note')]);
		if (s === 'Returned' && j.sales_invoice && j.invoice_status === 'Draft' && can.invoice) it.push(['viewinv', __('Open Draft Invoice')]);
		if (can.edit && s !== 'Invoiced') it.push(['edit', __('Edit Job')]);
		if (can.cancel && !(s === 'Invoiced' || (j.sales_invoice && j.invoice_status === 'Submitted'))) it.push(['cancel', __('Cancel Job'), 'danger']);
		return it.map(([a, l, cls]) => `<button class="${cls || ''}" data-act="${a}" data-id="${tpb_esc(j.name)}">${l}</button>`).join('');
	}

	wire_drag() {
		const el = this.el;
		el.querySelectorAll('.tpb-card[draggable="true"]').forEach(c => {
			c.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', c.dataset.id); c.classList.add('dragging'); });
			c.addEventListener('dragend', () => c.classList.remove('dragging'));
		});
		el.querySelectorAll('.mg-col[data-col]').forEach(z => {
			const ok = ['Received', 'Queued for Wash'].includes(z.dataset.col) && this.ctx.can.produce;
			z.addEventListener('dragover', e => { if (ok) { e.preventDefault(); z.classList.add('over'); } });
			z.addEventListener('dragleave', e => { if (!z.contains(e.relatedTarget)) z.classList.remove('over'); });
			z.addEventListener('drop', e => {
				z.classList.remove('over');
				if (!ok) return;
				e.preventDefault();
				const j = this.job(e.dataTransfer.getData('text/plain'));
				if (!j || j.status === z.dataset.col) return;
				this.run(j.name, 'set_queued', { toll_job: j.name, queued: z.dataset.col === 'Queued for Wash' ? 1 : 0 });
			});
		});
	}

	// one server action; the card dims while it runs, then the board reloads
	async run(id, method, args) {
		const card = id && this.el.querySelector('.tpb-card[data-id="' + CSS.escape(id) + '"]');
		card && card.classList.add('busy');
		this.busy++;
		try {
			const r = await this.call(method, args);
			if (r && r.message) frappe.show_alert({ message: r.message, indicator: 'green' }, 6);
			return r;
		} finally {
			this.busy--;
			card && card.classList.remove('busy');
			await this.refresh();
		}
	}

	act(a, id) {
		const j = this.job(id);
		if (!j) return;
		if (a === 'queue' || a === 'unqueue') return this.run(id, 'set_queued', { toll_job: id, queued: a === 'queue' ? 1 : 0 });
		if (a === 'wash') return this.wash_dialog(j);
		if (a === 'press') return this.press_dialog(j);
		if (a === 'move') return this.move_dialog(j);
		if (a === 'ret') return this.return_dialog(j);
		if (a === 'inv') return this.invoice_dialog(j);
		if (a === 'edit') return this.edit_dialog(j);
		if (a === 'viewinv') return window.open('/app/sales-invoice/' + encodeURIComponent(j.sales_invoice), '_blank');
		if (a === 'viewdn') return window.open('/app/delivery-note/' + encodeURIComponent(j.delivery_note), '_blank');
		if (a === 'cancel') {
			frappe.confirm(__('Cancel {0}? All its stock entries and delivery notes are cancelled (last step first){1}. Empty batches are deleted; a batch that is not empty is only disabled.',
				[j.name, j.sales_invoice && j.invoice_status === 'Draft' ? __(' and its draft invoice is deleted') : '']),
				() => this.run(id, 'cancel_toll_job', { toll_job: id }));
		}
	}

	// ------------------------------------------------------------ dialogs
	ctx_html(j) {
		return `<div class="tpb-dlg-ctx"><strong>${tpb_esc(j.name)}</strong> · ${tpb_esc(j.customer_name || j.customer)} · ${tpb_esc(j.strain)} · ${tpb_esc(__(j.return_type))}</div>`;
	}

	dialog(opts, submit) {
		const d = new frappe.ui.Dialog(Object.assign({}, opts, {
			primary_action: async values => {
				d.disable_primary_action();
				try {
					const r = await submit(values, d);
					if (r !== false) d.hide();
				} catch (e) { /* message shown by frappe.call; keep the dialog open */ }
				finally { d.enable_primary_action(); }
			},
		}));
		d.show();
		return d;
	}

	receive_dialog() {
		const c = this.ctx;
		const d = this.dialog({
			title: __('Receive Material'), size: 'extra-large', primary_action_label: __('Receive'),
			fields: [
				{ fieldname: 'customer', fieldtype: 'Link', options: 'Customer', label: __('Customer'), reqd: 1,
					get_query: () => ({ filters: { customer_group: c.customer_group, disabled: 0 } }) },
				{ fieldname: 'new_client', fieldtype: 'Button', label: __('+ New Client'), click: () => this.new_client_dialog(d) },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'received_date', fieldtype: 'Date', label: __('Received Date'), reqd: 1, default: frappe.datetime.get_today() },
				{ fieldname: 'inbound_manifest', fieldtype: 'Data', label: __('Inbound METRC Manifest') },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'physical_location', fieldtype: 'Select', label: __('Physical Location'), options: [''].concat(c.locations).join('\n'), default: 'Freezer 2' },
				{ fieldname: 'promised_return_date', fieldtype: 'Date', label: __('Promised Return Date') },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'priority', fieldtype: 'Select', label: __('Priority'), options: 'Normal\nRush', default: 'Normal' },
				{ fieldname: 'rate_basis', fieldtype: 'Select', label: __('Rate Basis'), options: c.rate_bases.join('\n'), default: c.rate_bases[0] },
				{ fieldname: 'rate', fieldtype: 'Currency', label: __('Rate'), description: __('Can be set later, before invoicing.') },
				{ fieldtype: 'Section Break', label: __('Strains') },
				{ fieldname: 'rows', fieldtype: 'Table', label: __('Strains'), in_place_edit: true, reqd: 1,
					data: [{ idx: 1, name: 'row-' + frappe.utils.get_random(6), return_type: 'Rosin' }],
					fields: [
						{ fieldname: 'strain', fieldtype: 'Data', label: __('Strain'), reqd: 1, in_list_view: 1, columns: 3 },
						{ fieldname: 'ff_lbs', fieldtype: 'Float', label: __('FF (lbs)'), reqd: 1, in_list_view: 1, columns: 2, precision: 3 },
						{ fieldname: 'return_type', fieldtype: 'Select', label: __('Return Type'), reqd: 1, in_list_view: 1, columns: 2,
							options: c.return_types.join('\n'), default: 'Rosin' },
						{ fieldname: 'inbound_tag', fieldtype: 'Data', label: __('Inbound METRC Tag'), in_list_view: 1, columns: 3,
							placeholder: __('Scan tag') },
					] },
				{ fieldname: 'scan_camera', fieldtype: 'Button', label: __('Scan Tag with Camera'),
					click: () => tpb_scan_camera(tag => {
						const rows = d.fields_dict.rows.df.data;
						const row = rows.find(r => !r.inbound_tag) || rows[rows.length - 1];
						if (row) { row.inbound_tag = tag; d.fields_dict.rows.grid.refresh(); }
					}) },
				{ fieldname: 'rows_note', fieldtype: 'HTML', options: `<div class="tpb-note">${__('Each row creates one Toll Job with its own batch and a receipt into Toll Inbound - MTM. The scanner gun types into the focused tag cell.')}</div>` },
			],
		}, async v => {
			const rows = (d.fields_dict.rows.df.data || []).filter(r => r.strain || r.ff_lbs);
			const r = await this.call('receive_material', {
				header: { customer: v.customer, received_date: v.received_date, inbound_manifest: v.inbound_manifest,
					physical_location: v.physical_location, promised_return_date: v.promised_return_date, priority: v.priority,
					rate_basis: v.rate_basis, rate: v.rate },
				rows: rows.map(r => ({ strain: r.strain, ff_lbs: r.ff_lbs, return_type: r.return_type, inbound_tag: r.inbound_tag })),
			});
			frappe.show_alert({ message: r.message, indicator: 'green' }, 7);
			await this.refresh();
		});
	}

	new_client_dialog(parent) {
		frappe.prompt([{ fieldname: 'customer_name', fieldtype: 'Data', label: __('Client Name'), reqd: 1 }], async v => {
			const name = await this.call('create_toll_client', { customer_name: v.customer_name });
			this.ctx.customers.push({ name, customer_name: v.customer_name });
			parent.set_value('customer', name);
			frappe.show_alert({ message: __('Client {0} added to {1}.', [name, this.ctx.customer_group]), indicator: 'green' });
		}, __('New Toll Client'), __('Create'));
	}

	wash_dialog(j) {
		const bal = j.ff_balance_lbs;
		const d = this.dialog({
			title: __('Record Wash'), primary_action_label: __('Record Wash'),
			fields: [
				{ fieldname: 'ctx', fieldtype: 'HTML', options: this.ctx_html(j) },
				{ fieldname: 'wash_date', fieldtype: 'Date', label: __('Wash Date'), reqd: 1, default: frappe.datetime.get_today() },
				{ fieldname: 'lbs', fieldtype: 'Float', label: __('FF Washed (lbs)'), reqd: 1, default: bal, precision: 3,
					description: __('Balance available: {0} lbs', [tpb_fmt(bal, 2)]) },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'washer', fieldtype: 'Autocomplete', label: __('Washer'), options: this.ctx.washers },
				{ fieldname: 'bh_grams', fieldtype: 'Float', label: __('Bubble Hash (g)'), reqd: 1, precision: 2,
					description: j.return_type === 'Bubble Hash' ? __('Goes to Toll Output, ready to return.') : __('Goes to Toll WIP for pressing.') },
				{ fieldtype: 'Section Break' },
				{ fieldname: 'live', fieldtype: 'HTML', options: `<div class="tpb-live">${__('Wash yield')} <b data-y>—</b></div>` },
				{ fieldname: 'notes', fieldtype: 'Small Text', label: __('Notes') },
			],
		}, async v => {
			if (v.lbs > bal + 1e-9) { frappe.msgprint(__('Quantity exceeds the available balance for this Toll Job ({0} lbs).', [tpb_fmt(bal, 2)])); return false; }
			await this.run(j.name, 'record_wash', { toll_job: j.name, wash_date: v.wash_date, lbs: v.lbs, bh_grams: v.bh_grams, washer: v.washer, notes: v.notes });
		});
		const upd = () => {
			const l = d.get_value('lbs'), g = d.get_value('bh_grams');
			d.$wrapper.find('[data-y]').text(l > 0 && g > 0 ? tpb_fmt(g / (l * TPB_LB_TO_G) * 100, 2) + '%' : '—');
		};
		['lbs', 'bh_grams'].forEach(f => d.fields_dict[f].$input.on('input change', upd));
	}

	press_dialog(j) {
		const wip = j.bh_wip_grams;
		const d = this.dialog({
			title: __('Record Press'), primary_action_label: __('Record Press'),
			fields: [
				{ fieldname: 'ctx', fieldtype: 'HTML', options: this.ctx_html(j) },
				{ fieldname: 'press_date', fieldtype: 'Date', label: __('Press Date'), reqd: 1, default: frappe.datetime.get_today() },
				{ fieldname: 'bh_grams', fieldtype: 'Float', label: __('Bubble Hash Pressed (g)'), reqd: 1, precision: 2,
					default: j.return_type === 'Both' ? null : wip,
					description: __('In Toll WIP: {0} g', [tpb_fmt(wip)]) + (j.return_type === 'Both' ? ' · ' + __('press only the part the client wants as rosin') : '') },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'rosin_grams', fieldtype: 'Float', label: __('Rosin (g)'), reqd: 1, precision: 2 },
				{ fieldtype: 'Section Break' },
				{ fieldname: 'live', fieldtype: 'HTML', options: `<div class="tpb-live">${__('Press yield')} <b data-y>—</b></div>` },
				{ fieldname: 'notes', fieldtype: 'Small Text', label: __('Notes') },
			],
		}, async v => {
			if (v.bh_grams > wip + 1e-9) { frappe.msgprint(__('Quantity exceeds the available balance for this Toll Job ({0} g in WIP).', [tpb_fmt(wip)])); return false; }
			if (v.rosin_grams > v.bh_grams) { frappe.msgprint(__('Rosin cannot be more than the bubble hash pressed.')); return false; }
			await this.run(j.name, 'record_press', { toll_job: j.name, press_date: v.press_date, bh_grams: v.bh_grams, rosin_grams: v.rosin_grams, notes: v.notes });
		});
		const upd = () => {
			const b = d.get_value('bh_grams'), r = d.get_value('rosin_grams');
			d.$wrapper.find('[data-y]').text(b > 0 && r > 0 ? tpb_fmt(r / b * 100, 1) + '%' : '—');
		};
		['bh_grams', 'rosin_grams'].forEach(f => d.fields_dict[f].$input.on('input change', upd));
	}

	move_dialog(j) {
		const wip = j.bh_wip_grams;
		this.dialog({
			title: __('Move BH to Output'), primary_action_label: __('Move to Output'),
			fields: [
				{ fieldname: 'ctx', fieldtype: 'HTML', options: this.ctx_html(j) },
				{ fieldname: 'grams', fieldtype: 'Float', label: __('Bubble Hash (g)'), reqd: 1, default: wip, precision: 2,
					description: __('In Toll WIP: {0} g. This bubble hash will be returned to the client as is.', [tpb_fmt(wip)]) },
				{ fieldname: 'move_date', fieldtype: 'Date', label: __('Date'), reqd: 1, default: frappe.datetime.get_today() },
			],
		}, async v => {
			if (!(v.grams > 0) || v.grams > wip + 1e-9) { frappe.msgprint(__('Enter grams between 1 and {0}.', [tpb_fmt(wip)])); return false; }
			await this.run(j.name, 'move_bh_to_output', { toll_job: j.name, grams: v.grams, move_date: v.move_date });
		});
	}

	return_dialog(j) {
		const lines = [];
		if (j.bh_output_grams > 0) lines.push({ item_code: 'TOLL-BH', item: __('Toll Bubble Hash'), available: j.bh_output_grams, qty: j.bh_output_grams });
		if (j.rosin_output_grams > 0) lines.push({ item_code: 'TOLL-ROSIN', item: __('Toll Rosin'), available: j.rosin_output_grams, qty: j.rosin_output_grams });
		lines.forEach((l, i) => Object.assign(l, { idx: i + 1, name: 'line-' + (i + 1) }));
		const d = this.dialog({
			title: __('Return to Client'), size: 'large', primary_action_label: __('Create Delivery Note'),
			fields: [
				{ fieldname: 'ctx', fieldtype: 'HTML', options: this.ctx_html(j) },
				{ fieldname: 'return_date', fieldtype: 'Date', label: __('Return Date'), reqd: 1, default: frappe.datetime.get_today() },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'driver', fieldtype: 'Data', label: __('Driver') },
				{ fieldtype: 'Section Break' },
				{ fieldname: 'manifest', fieldtype: 'Data', label: __('Outbound METRC Manifest') },
				{ fieldtype: 'Section Break', label: __('Items') },
				{ fieldname: 'items', fieldtype: 'Table', label: __('Items'), cannot_add_rows: true, cannot_delete_rows: true, in_place_edit: true, data: lines,
					fields: [
						{ fieldname: 'item_code', fieldtype: 'Data', label: __('Item Code'), read_only: 1 },
						{ fieldname: 'item', fieldtype: 'Data', label: __('Item'), read_only: 1, in_list_view: 1, columns: 3 },
						{ fieldname: 'available', fieldtype: 'Float', label: __('Available (g)'), read_only: 1, in_list_view: 1, columns: 2 },
						{ fieldname: 'qty', fieldtype: 'Float', label: __('Return (g)'), in_list_view: 1, columns: 2 },
						{ fieldname: 'metrc_tag', fieldtype: 'Data', label: __('Outbound METRC Tag'), in_list_view: 1, columns: 3, placeholder: __('Scan tag') },
					] },
				{ fieldname: 'scan_camera', fieldtype: 'Button', label: __('Scan Tag with Camera'),
					click: () => tpb_scan_camera(tag => {
						const row = lines.find(r => !r.metrc_tag) || lines[lines.length - 1];
						if (row) { row.metrc_tag = tag; d.fields_dict.items.grid.refresh(); }
					}) },
				{ fieldname: 'note', fieldtype: 'HTML', options: `<div class="tpb-note">${__('Rate is zero. The Delivery Note moves the stock out of Toll Output - MTM and carries the METRC tags; billing is done on the invoice.')}</div>` },
			],
		}, async v => {
			const items = (d.fields_dict.items.df.data || []).map(r => ({ item_code: r.item_code, qty: r.qty, metrc_tag: r.metrc_tag }));
			if (!items.some(r => r.qty > 0)) { frappe.msgprint(__('Enter a return quantity on at least one item.')); return false; }
			const bad = (d.fields_dict.items.df.data || []).find(r => r.qty > r.available + 1e-9);
			if (bad) { frappe.msgprint(__('Quantity exceeds the available balance for this Toll Job.')); return false; }
			await this.run(j.name, 'return_to_client', { toll_job: j.name, return_date: v.return_date, manifest: v.manifest, driver: v.driver, items });
		});
	}

	invoice_dialog(j) {
		const c = this.ctx;
		const qty_of = basis => basis === 'Per lb FF Input' ? j.ff_washed_lbs
			: basis === 'Per Gram Output' ? (j.returned_bh_grams || 0) + (j.returned_rosin_grams || 0) : 1;
		const unit = basis => basis === 'Per lb FF Input' ? ' lbs' : basis === 'Per Gram Output' ? ' g' : ' ' + __('job');
		const d = this.dialog({
			title: __('Create Invoice'), primary_action_label: __('Create Draft Invoice'),
			fields: [
				{ fieldname: 'ctx', fieldtype: 'HTML', options: this.ctx_html(j) },
				{ fieldname: 'rate_basis', fieldtype: 'Select', label: __('Rate Basis'), options: c.rate_bases.join('\n'), default: j.rate_basis || c.rate_bases[0], reqd: 1 },
				{ fieldname: 'rate', fieldtype: 'Currency', label: __('Rate'), default: j.rate, reqd: 1 },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'billable', fieldtype: 'Data', label: __('Billable Qty'), read_only: 1 },
				{ fieldname: 'amount', fieldtype: 'Data', label: __('Amount'), read_only: 1 },
				{ fieldtype: 'Section Break' },
				{ fieldname: 'note', fieldtype: 'HTML', options: `<div class="tpb-note">${__('The invoice opens as a draft in a new tab for review. Accounts submit it; the job moves to Invoiced then.')}</div>` },
			],
		}, async v => {
			if (!(v.rate > 0)) { frappe.msgprint(__('Enter a rate greater than zero.')); return false; }
			const r = await this.run(j.name, 'create_invoice', { toll_job: j.name, rate_basis: v.rate_basis, rate: v.rate });
			if (r && r.sales_invoice) window.open('/app/sales-invoice/' + encodeURIComponent(r.sales_invoice), '_blank');
		});
		const upd = () => {
			const b = d.get_value('rate_basis'), q = qty_of(b), rate = d.get_value('rate') || 0;
			d.set_value('billable', tpb_fmt(q, q % 1 ? 2 : 0) + unit(b));
			d.set_value('amount', tpb_money(q * rate));
		};
		d.fields_dict.rate_basis.$input.on('change', upd);
		d.fields_dict.rate.$input.on('input change', upd);
		upd();
	}

	edit_dialog(j) {
		const c = this.ctx, locked = j.ff_washed_lbs > 0;
		this.dialog({
			title: __('Edit Job'), primary_action_label: __('Save'),
			fields: [
				{ fieldname: 'ctx', fieldtype: 'HTML', options: this.ctx_html(j) },
				{ fieldname: 'promised_return_date', fieldtype: 'Date', label: __('Promised Return Date'), default: j.promised_return_date },
				{ fieldname: 'priority', fieldtype: 'Select', label: __('Priority'), options: 'Normal\nRush', default: j.priority || 'Normal' },
				{ fieldname: 'physical_location', fieldtype: 'Select', label: __('Physical Location'), options: [''].concat(c.locations).join('\n'), default: j.physical_location || '' },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'return_type', fieldtype: 'Select', label: __('Return Type'), options: c.return_types.join('\n'), default: j.return_type,
					read_only: locked ? 1 : 0, description: locked ? __('Locked after the first wash.') : '' },
				{ fieldname: 'rate_basis', fieldtype: 'Select', label: __('Rate Basis'), options: c.rate_bases.join('\n'), default: j.rate_basis },
				{ fieldname: 'rate', fieldtype: 'Currency', label: __('Rate'), default: j.rate },
				{ fieldtype: 'Section Break' },
				{ fieldname: 'inbound_manifest', fieldtype: 'Data', label: __('Inbound METRC Manifest'), default: j.inbound_manifest },
			],
		}, async v => {
			const values = { promised_return_date: v.promised_return_date || null, priority: v.priority, physical_location: v.physical_location,
				inbound_manifest: v.inbound_manifest, rate_basis: v.rate_basis, rate: v.rate || 0 };
			if (!locked) values.return_type = v.return_type;
			await this.run(j.name, 'update_job', { toll_job: j.name, values });
		});
	}
}

// Camera scan for METRC tags (barcode or QR), same approach as Pull Packages on the Conversion Entry: a wide, short
// box so a long Code 128 METRC barcode fits, HD constraints with a plain fallback.
function tpb_scan_camera(on_tag) {
	let scanner = null, done = false, closed = false;
	const stop = () => {
		closed = true;
		const s = scanner;
		scanner = null;
		if (s) s.stop().then(() => s.clear()).catch(() => {});
	};
	const sd = new frappe.ui.Dialog({ title: __('Scan Barcode / QR Code'), fields: [{ fieldname: 'area', fieldtype: 'HTML' }], on_hide: stop });
	sd.show();
	const $area = sd.fields_dict.area.$wrapper.empty().append(`<div style="width:100%"></div>
		<div class="text-muted small text-center mt-2">${__('Hold the barcode flat and level across the box, about 15-20 cm from the camera, or a QR code anywhere inside it.')}</div>`);
	const id = frappe.dom.set_unique_id($area.children().first());
	frappe.require('/assets/frappe/node_modules/html5-qrcode/html5-qrcode.min.js').then(() => {
		if (closed) return;
		const formats = Object.values(Html5QrcodeSupportedFormats).filter(v => typeof v === 'number'); // eslint-disable-line
		scanner = new Html5Qrcode(id, { formatsToSupport: formats, experimentalFeatures: { useBarCodeDetectorIfSupported: true }, verbose: false }); // eslint-disable-line
		const video = { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 }, advanced: [{ focusMode: 'continuous' }] };
		const box = (w, h) => ({ width: Math.max(50, Math.floor(w * 0.92)), height: Math.max(50, Math.floor(Math.min(h * 0.55, w * 0.5))) });
		const on_code = text => {
			if (done) return;
			done = true;
			sd.hide();
			on_tag(String(text || '').trim().toUpperCase());
		};
		const start = config => scanner.start({ facingMode: 'environment' }, config, on_code, () => {});
		start({ fps: 15, qrbox: box, videoConstraints: video })
			.catch(() => (scanner && !closed ? start({ fps: 15, qrbox: box }) : null))
			.catch(err => { scanner = null; sd.hide(); frappe.msgprint(__('Could not open the camera: {0}', [String(err)])); });
	});
}
