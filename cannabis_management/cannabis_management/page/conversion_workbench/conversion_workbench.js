// Copyright (c) 2026, alltechvirtual.com and contributors
// Conversion Workbench — "Conversion Workbench - Page Mapping (Developer Spec)", 7 Oct 2026.
//
// Pick raw materials from live stock on the left, press Convert, fill the
// finished items by hand, and one Conversion Entry is created and submitted.
// The page posts no stock itself; the entry's own on-submit logic makes the
// Draft Repack Stock Entry exactly as it does from the form.
//
// Selection is held in a Map keyed by item + warehouse so it survives changing
// group, searching and paging — the spec asks for items from several groups to
// go into one conversion.

const CWB = 'cannabis_management.cannabis_management.page.conversion_workbench.conversion_workbench.';
const CWB_MAX_RAW = 7;
const CWB_MAX_FINISHED = 3;
const CWB_ALL = '__all__';

frappe.pages['conversion-workbench'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper, title: __('Conversion Workbench'), single_column: true,
	});
	wrapper.page = page;

	page.cwb = {
		company: frappe.defaults.get_user_default('Company') || '',
		group: CWB_ALL,
		warehouse: '',
		search: '',
		items: [],
		groups: [],
		selected: new Map(),      // "item|warehouse" -> row
		types: [],
		start: 0,
		exhausted: false,
		loading: false,
	};

	page.main.html(`
		<div class="cwb-root">
			<div class="cwb-top">
				<span class="cwb-title">${__('Conversion Workbench')}</span>
				<select id="cwb-company"></select>
				<select id="cwb-warehouse"><option value="">${__('All warehouses')}</option></select>
				<input type="text" class="cwb-search" id="cwb-search" placeholder="${__('Search item code or name…')}">
				<div class="cwb-spacer"></div>
				<button class="cwb-btn cwb-btn-ghost" id="cwb-clear">${__('Clear')}</button>
				<button class="cwb-btn" id="cwb-convert" disabled>${__('Convert')}</button>
			</div>

			<div class="cwb-body">
				<div class="cwb-side">
					<h4>${__('ITEM GROUPS')}</h4>
					<div id="cwb-groups"></div>
				</div>
				<div class="cwb-main">
					<div class="cwb-list" id="cwb-list">
						<div class="cwb-empty">${__('Loading…')}</div>
					</div>
					<div class="cwb-sel" id="cwb-sel"></div>
				</div>
			</div>
		</div>
	`);

	// Bound before anything async: if the company lookup were to fail with the
	// handlers inside its callback, the Convert button would simply do nothing.
	bind(page);

	frappe.call({ method: CWB + 'get_conversion_types' })
		.then((r) => { page.cwb.types = (r && r.message) || []; });

	frappe.db.get_list('Company', { fields: ['name'], limit: 0, order_by: 'name' })
		.then((rows) => {
			const esc = frappe.utils.escape_html;
			rows = rows || [];
			if (!page.cwb.company && rows.length) page.cwb.company = rows[0].name;
			page.main.find('#cwb-company').html(
				rows.map((r) => `<option value="${esc(r.name)}">${esc(r.name)}</option>`).join('')
			).val(page.cwb.company);
			reload_all(page);
		})
		.catch(() => {
			// Still usable on the user's default company rather than a dead page.
			if (page.cwb.company) reload_all(page);
			else page.main.find('#cwb-list').html(
				`<div class="cwb-empty">${__('Could not load companies. Reload the page.')}</div>`);
		});
};

function bind(page) {
	const s = page.cwb;

	page.main.find('#cwb-company').on('change', function () {
		s.company = this.value;
		// Warehouses and stock are per company, so a selection made under the
		// previous one cannot be carried across.
		s.selected.clear();
		s.warehouse = '';
		s.group = CWB_ALL;
		reload_all(page);
	});

	page.main.find('#cwb-warehouse').on('change', function () {
		s.warehouse = this.value;
		load_items(page, true);
	});

	let timer = null;
	page.main.find('#cwb-search').on('input', function () {
		s.search = this.value;
		// Searching hits the server, so wait for a pause in typing.
		clearTimeout(timer);
		timer = setTimeout(() => load_items(page, true), 250);
	});

	page.main.on('click', '.cwb-grp', function () {
		s.group = String($(this).attr('data-group'));
		page.main.find('.cwb-grp').removeClass('on');
		$(this).addClass('on');
		load_items(page, true);
	});

	page.main.on('click', '.cwb-row', function () { toggle(page, $(this).attr('data-key')); });
	page.main.on('click', '.cwb-chip .x', function (e) {
		e.stopPropagation();
		toggle(page, $(this).attr('data-key'));
	});

	page.main.find('#cwb-clear').on('click', () => { s.selected.clear(); render(page); });
	page.main.find('#cwb-convert').on('click', () => open_convert(page));

	// Scroll-to-load: the list asks for 200 rows at a time.
	page.main.find('#cwb-list').on('scroll', function () {
		if (s.loading || s.exhausted) return;
		if (this.scrollTop + this.clientHeight >= this.scrollHeight - 120) load_items(page, false);
	});
}

function reload_all(page) {
	load_warehouses(page);
	load_groups(page);
	load_items(page, true);
}

function load_warehouses(page) {
	const esc = frappe.utils.escape_html;
	frappe.db.get_list('Warehouse', {
		filters: { company: page.cwb.company, is_group: 0, disabled: 0 },
		fields: ['name'], limit: 0, order_by: 'name',
	}).then((rows) => {
		page.main.find('#cwb-warehouse').html(
			[`<option value="">${__('All warehouses')}</option>`].concat(
				rows.map((r) => `<option value="${esc(r.name)}">${esc(r.name)}</option>`)
			).join('')
		).val(page.cwb.warehouse);
	});
}

function load_groups(page) {
	frappe.call({
		method: CWB + 'get_item_groups',
		args: { company: page.cwb.company },
		callback: (r) => {
			const esc = frappe.utils.escape_html;
			const m = (r && r.message) || { groups: [], total: 0 };
			page.cwb.groups = m.groups;
			const rows = [`<div class="cwb-grp ${page.cwb.group === CWB_ALL ? 'on' : ''}" data-group="${CWB_ALL}">
					<span>${__('All groups')}</span><span class="n">${m.total}</span></div>`]
				.concat(m.groups.map((g) => `
					<div class="cwb-grp ${page.cwb.group === g.item_group ? 'on' : ''}" data-group="${esc(g.item_group)}">
						<span>${esc(g.item_group)}</span><span class="n">${g.item_count}</span></div>`));
			page.main.find('#cwb-groups').html(rows.join(''));
		},
	});
}

function load_items(page, reset) {
	const s = page.cwb;
	if (reset) { s.start = 0; s.items = []; s.exhausted = false; }
	s.loading = true;
	frappe.call({
		method: CWB + 'get_stock_items',
		args: {
			company: s.company,
			item_group: s.group === CWB_ALL ? null : s.group,
			warehouse: s.warehouse || null,
			search: s.search || null,
			start: s.start,
		},
		callback: (r) => {
			s.loading = false;
			const m = (r && r.message) || { items: [], page_length: 200 };
			s.items = s.items.concat(m.items);
			s.start += m.items.length;
			if (m.items.length < m.page_length) s.exhausted = true;
			render(page);
		},
		error: () => { s.loading = false; },
	});
}

function key_of(row) { return row.item_code + '|' + row.warehouse; }

function toggle(page, key) {
	const s = page.cwb;
	if (s.selected.has(key)) {
		s.selected.delete(key);
		render(page);
		return;
	}
	const row = s.items.find((r) => key_of(r) === key);
	if (!row) return;

	if (s.selected.size >= CWB_MAX_RAW) {
		frappe.msgprint(__('A Conversion Entry supports up to 7 raw materials.'));
		return;
	}
	// One entry row carries one Source Warehouse, so a second warehouse cannot
	// be stored even though the picker would happily show it.
	const first = s.selected.values().next().value;
	if (first && first.warehouse !== row.warehouse) {
		frappe.msgprint(__('All raw materials must come from the same Source Warehouse.'));
		return;
	}
	// Default quantity is the whole balance; the dialog is where it is edited.
	s.selected.set(key, Object.assign({}, row, { qty: flt(row.actual_qty) }));
	render(page);
}

function render(page) {
	render_list(page);
	render_selection(page);
}

function render_list(page) {
	const s = page.cwb;
	const esc = frappe.utils.escape_html;
	if (!s.items.length) {
		page.main.find('#cwb-list').html(
			`<div class="cwb-empty">${s.loading ? __('Loading…') : __('No items with stock match this view.')}</div>`);
		return;
	}
	const body = s.items.map((r) => {
		const k = key_of(r);
		const on = s.selected.has(k);
		return `<tr class="cwb-row ${on ? 'on' : ''}" data-key="${esc(k)}">
			<td><input type="checkbox" ${on ? 'checked' : ''} tabindex="-1"></td>
			<td>${esc(r.item_code)}</td>
			<td>${esc(r.item_name || '')}<div class="cwb-dim">${esc(r.item_group || '')}</div></td>
			<td>${esc(r.warehouse)}</td>
			<td>${esc(r.stock_uom || '')}</td>
			<td class="cwb-num">${format_number(r.actual_qty, null, 2)}</td>
			<td class="cwb-num cwb-dim">${format_number(r.valuation_rate, null, 2)}</td>
		</tr>`;
	}).join('');

	page.main.find('#cwb-list').html(`
		<table class="cwb-table"><thead><tr>
			<th style="width:30px"></th>
			<th>${__('Item Code')}</th><th>${__('Item Name')}</th>
			<th>${__('Warehouse')}</th><th>${__('UOM')}</th>
			<th class="cwb-num">${__('Available Qty')}</th>
			<th class="cwb-num">${__('Valuation Rate')}</th>
		</tr></thead><tbody>${body}</tbody></table>
		${s.exhausted ? '' : `<div class="cwb-more">${__('Scroll for more…')}</div>`}`);
}

function render_selection(page) {
	const s = page.cwb;
	const esc = frappe.utils.escape_html;
	const n = s.selected.size;

	page.main.find('#cwb-convert')
		.prop('disabled', n === 0)
		.text(n ? __('Convert ({0})', [n]) : __('Convert'));

	if (!n) {
		page.main.find('#cwb-sel').html(
			`<span class="cwb-selnote">${__('Click rows to choose raw materials.')}</span>`);
		return;
	}
	const chips = [...s.selected.entries()].map(([k, r]) => `
		<span class="cwb-chip">${esc(r.item_name || r.item_code)}
			<b>${format_number(r.qty, null, 2)}</b> ${esc(r.stock_uom || '')}
			<span class="x" data-key="${esc(k)}">&times;</span></span>`).join('');
	const total = [...s.selected.values()].reduce((a, r) => a + flt(r.qty), 0);
	const uoms = new Set([...s.selected.values()].map((r) => r.stock_uom));
	page.main.find('#cwb-sel').html(chips +
		`<span class="cwb-selnote">${__('Selected: {0} raw materials', [n])}${
			uoms.size === 1 ? ` (${format_number(total, null, 2)} ${esc([...uoms][0])})` : ''}</span>`);
}


// ── Convert dialog ───────────────────────────────────────────────────────────
// Header fields mirror the Conversion Entry form, in the same order, so users
// see nothing new. Raw rows arrive from the page selection; finished rows start
// empty and are added by hand.

function open_convert(page) {
	const s = page.cwb;
	if (!s.selected.size) return;

	const source = [...s.selected.values()][0].warehouse;
	const state = {
		raws: [...s.selected.entries()].map(([k, r]) => Object.assign({ key: k }, r)),
		finished: [{ item_code: '', qty: null, tag: '' }],
	};

	const d = new frappe.ui.Dialog({
		title: __('Convert'),
		size: 'extra-large',
		fields: [
			{ fieldname: 'posting_date', fieldtype: 'Date', label: __('Posting Date'),
				reqd: 1, default: frappe.datetime.get_today() },
			{ fieldname: 'company', fieldtype: 'Link', options: 'Company', label: __('Company'),
				reqd: 1, default: s.company, read_only: 1 },
			{ fieldname: 'cb_h1', fieldtype: 'Column Break' },
			{ fieldname: 'reasons', fieldtype: 'Select', label: __('Reasons'),
				options: '\nBlending\nTolling\nCo-packing\nOthers' },
			{ fieldname: 'partners', fieldtype: 'Select', label: __('Partners'),
				options: '\nNina\nLeaf\nBIG Oil\nBloom\nNature\nOther' },
			{ fieldname: 'cb_h2', fieldtype: 'Column Break' },
			{ fieldname: 'conversion_status', fieldtype: 'Link', options: 'Conversion Status',
				label: __('Conversion Status') },
			{ fieldname: 'customer', fieldtype: 'Link', options: 'Customer', label: __('Customer') },
			{ fieldname: 'sb_party', fieldtype: 'Section Break' },
			{ fieldname: 'supplier', fieldtype: 'Link', options: 'Supplier', label: __('Supplier') },
			{ fieldname: 'sales_order', fieldtype: 'Link', options: 'Sales Order', label: __('Sales Order') },
			{ fieldname: 'cb_p1', fieldtype: 'Column Break' },
			{ fieldname: 'project', fieldtype: 'Link', options: 'Project', label: __('Project') },
			{ fieldname: 'workstation', fieldtype: 'Link', options: 'Workstation', label: __('Workstation') },

			{ fieldname: 'sb_wh', fieldtype: 'Section Break' },
			{ fieldname: 'source_warehouse', fieldtype: 'Link', options: 'Warehouse',
				label: __('Source Warehouse'), reqd: 1, default: source, read_only: 1 },
			{ fieldname: 'target_warehouse', fieldtype: 'Link', options: 'Warehouse',
				label: __('Target Warehouse'), reqd: 1, default: source,
				get_query: () => ({ filters: { company: s.company, is_group: 0, disabled: 0 } }) },
			{ fieldname: 'cb_wh', fieldtype: 'Column Break' },
			{ fieldname: 'expense_account', fieldtype: 'Link', options: 'Account',
				label: __('Expense Account'),
				get_query: () => ({ filters: { company: s.company, is_group: 0 } }) },

			{ fieldname: 'sb_tables', fieldtype: 'Section Break' },
			{ fieldname: 'tables', fieldtype: 'HTML' },
			{ fieldname: 'sb_notes', fieldtype: 'Section Break' },
			{ fieldname: 'notes', fieldtype: 'Text Editor', label: __('Notes') },
		],
		primary_action_label: __('Convert'),
		primary_action: () => submit_convert(page, d, state),
	});

	d.fields_dict.tables.$wrapper.on('input change', 'input,select', function () {
		const i = cint($(this).attr('data-i'));
		const role = $(this).attr('data-role');
		const side = $(this).attr('data-side');
		const target = side === 'raw' ? state.raws[i] : state.finished[i];
		if (!target) return;
		target[role] = (role === 'qty') ? flt(this.value) : this.value;
		if (role === 'qty') render_totals(page, d, state);
	});

	d.fields_dict.tables.$wrapper.on('click', '.cwb-rm-raw', function () {
		state.raws.splice(cint($(this).attr('data-i')), 1);
		render_tables(page, d, state);
	});
	d.fields_dict.tables.$wrapper.on('click', '.cwb-rm-fin', function () {
		state.finished.splice(cint($(this).attr('data-i')), 1);
		render_tables(page, d, state);
	});
	d.fields_dict.tables.$wrapper.on('click', '.cwb-add-fin', function () {
		if (state.finished.length >= CWB_MAX_FINISHED) return;
		state.finished.push({ item_code: '', qty: null, tag: '' });
		render_tables(page, d, state);
	});

	d.show();
	render_tables(page, d, state);
	page.cwb.dialog = d;
}

function render_tables(page, d, state) {
	const esc = frappe.utils.escape_html;

	const raw_rows = state.raws.map((r, i) => `
		<tr>
			<td>${esc(r.item_code)}<div class="cwb-dim">${esc(r.item_name || '')}</div></td>
			<td class="cwb-num cwb-dim">${format_number(r.actual_qty, null, 2)}</td>
			<td><input type="number" step="any" min="0" data-side="raw" data-role="qty"
				data-i="${i}" value="${r.qty != null ? r.qty : ''}"></td>
			<td><input type="text" data-side="raw" data-role="tag" data-i="${i}"
				value="${esc(r.tag || '')}" placeholder="${__('optional')}"></td>
			<td><span class="x cwb-rm-raw" data-i="${i}">&times;</span></td>
		</tr>`).join('');

	const fin_rows = state.finished.map((f, i) => `
		<tr>
			<td><div class="cwb-fin-item" data-i="${i}"></div></td>
			<td><input type="number" step="any" min="0" data-side="finished" data-role="qty"
				data-i="${i}" value="${f.qty != null ? f.qty : ''}"></td>
			<td><input type="text" data-side="finished" data-role="tag" data-i="${i}"
				value="${esc(f.tag || '')}" placeholder="${__('optional')}"></td>
			<td><span class="x cwb-rm-fin" data-i="${i}">&times;</span></td>
		</tr>`).join('');

	d.fields_dict.tables.$wrapper.html(`
		<div class="cwb-dlg-tables">
			<div>
				<h5>${__('RAW MATERIALS (from selection)')}</h5>
				<table class="cwb-dt"><thead><tr>
					<th>${__('Item')}</th><th class="cwb-num">${__('Avail.')}</th>
					<th>${__('Qty')}</th><th>${__('Source Tag')}</th><th></th>
				</tr></thead><tbody>${raw_rows}</tbody></table>
			</div>
			<div>
				<h5>${__('FINISHED ITEMS (add manually)')}</h5>
				<table class="cwb-dt"><thead><tr>
					<th>${__('Item')}</th><th>${__('Qty')}</th>
					<th>${__('Target Tag')}</th><th></th>
				</tr></thead><tbody>${fin_rows}</tbody></table>
				${state.finished.length < CWB_MAX_FINISHED
					? `<button class="cwb-btn cwb-btn-ghost cwb-add-fin" style="margin-top:8px;">+ ${__('Add finished item')}</button>`
					: ''}
			</div>
		</div>
		<div class="cwb-totals" id="cwb-totals"></div>
	`);

	// A real Frappe Link control per finished-item cell, so the field behaves
	// exactly like the form's Item field -- search, title display, the lot.
	// (Frappe ships Awesomplete, not jQuery UI, so $.fn.autocomplete does not
	// exist; calling it threw in here and the dialog never reached d.show().)
	state._controls = [];
	d.fields_dict.tables.$wrapper.find('.cwb-fin-item').each(function () {
		const idx = cint($(this).attr('data-i'));
		const control = frappe.ui.form.make_control({
			parent: $(this),
			df: {
				fieldtype: 'Link', options: 'Item', fieldname: 'fin_item_' + idx,
				placeholder: __('Item'),
				get_query: () => ({ filters: { disabled: 0, is_stock_item: 1 } }),
				change: function () {
					state.finished[idx].item_code = control.get_value() || '';
					render_totals(page, d, state);
				},
			},
			render_input: true,
			only_input: true,
		});
		control.set_value(state.finished[idx].item_code || '');
		control.refresh();
		state._controls.push(control);
	});

	render_totals(page, d, state);
}

function render_totals(page, d, state) {
	const raws = state.raws.filter((r) => r.item_code);
	const fins = state.finished.filter((f) => f.item_code);
	const type = `${raws.length} to ${fins.length}`;
	const allowed = (page.cwb && page.cwb.types) || [];
	const ok = allowed.length ? allowed.indexOf(type) !== -1 : true;

	// Totals use each item's own UOM; mixing them makes a single number a lie.
	const sum = (rows, qty_of) => {
		const uoms = new Set(rows.map((r) => r.stock_uom).filter(Boolean));
		if (uoms.size > 1) return __('mixed units');
		const t = rows.reduce((a, r) => a + flt(qty_of(r)), 0);
		return format_number(t, null, 2) + (uoms.size ? ' ' + [...uoms][0] : '');
	};

	d.fields_dict.tables.$wrapper.find('#cwb-totals').html(`
		<span>${__('Conversion type')}: <span class="cwb-ctype ${ok ? '' : 'bad'}">${type}</span></span>
		<span>${__('Raw total')}: <b>${sum(raws, (r) => r.qty)}</b></span>
		<span>${__('Finished total')}: <b>${sum(fins, (f) => f.qty)}</b></span>
		${ok ? '' : `<span style="color:var(--bad);font-weight:600;">${
			__('A conversion of {0} to {1} is not available. Choose a supported combination.',
				[raws.length, fins.length])}</span>`}`);
}

function submit_convert(page, d, state) {
	const v = d.get_values(true) || {};
	const raws = state.raws.filter((r) => r.item_code);
	const fins = state.finished.filter((f) => f.item_code);

	// Browser copy of the spec's section 7. The server repeats every one of
	// these; this exists so a mistake is caught before a round trip.
	if (!raws.length || !fins.length) {
		return frappe.msgprint(__('Select at least one raw material and one finished item.'));
	}
	if (raws.length > CWB_MAX_RAW || fins.length > CWB_MAX_FINISHED) {
		return frappe.msgprint(__('A Conversion Entry supports up to 7 raw materials and 3 finished items.'));
	}
	const type = `${raws.length} to ${fins.length}`;
	if ((page.cwb.types || []).length && page.cwb.types.indexOf(type) === -1) {
		return frappe.msgprint(__('A conversion of {0} to {1} is not available. Choose a supported combination.',
			[raws.length, fins.length]));
	}
	if (!v.source_warehouse || !v.target_warehouse) {
		return frappe.msgprint(__('Source Warehouse and Target Warehouse are required.'));
	}
	for (const r of raws) {
		if (!flt(r.qty)) return frappe.msgprint(__('Enter a quantity for {0}.', [r.item_code]));
		if (flt(r.qty) > flt(r.actual_qty) + 0.0001) {
			return frappe.msgprint(__('Quantity for {0} cannot exceed the available {1} {2}.',
				[r.item_code, format_number(r.actual_qty, null, 2), r.stock_uom || '']));
		}
	}
	for (const f of fins) {
		if (!flt(f.qty)) return frappe.msgprint(__('Enter a quantity for {0}.', [f.item_code]));
		if (raws.some((r) => r.item_code === f.item_code)
			&& v.source_warehouse === v.target_warehouse) {
			return frappe.msgprint(__('{0} cannot be converted into itself in the same warehouse.',
				[f.item_code]));
		}
	}

	const raw_total = raws.reduce((a, r) => a + flt(r.qty), 0);
	const fin_total = fins.reduce((a, f) => a + flt(f.qty), 0);
	const gap = flt(fin_total - raw_total, 3);

	const go = () => post_convert(page, d, v, raws, fins);
	// Rule 10 warns, it does not block: losing mass is normal in extraction.
	if (Math.abs(gap) > 0.0001) {
		frappe.confirm(
			__('Finished quantity differs from raw quantity by {0}. Continue?',
				[format_number(gap, null, 3)]),
			go);
	} else {
		go();
	}
}

function post_convert(page, d, v, raws, fins) {
	d.disable_primary_action();
	frappe.dom.freeze(__('Creating and submitting the Conversion Entry…'));

	frappe.call({
		method: CWB + 'create_conversion',
		args: {
			payload: JSON.stringify({
				posting_date: v.posting_date, company: v.company,
				reasons: v.reasons, partners: v.partners,
				conversion_status: v.conversion_status, customer: v.customer,
				supplier: v.supplier, sales_order: v.sales_order,
				project: v.project, workstation: v.workstation, notes: v.notes,
				source_warehouse: v.source_warehouse, target_warehouse: v.target_warehouse,
				expense_account: v.expense_account,
				raw_materials: raws.map((r) => ({
					item_code: r.item_code, qty: flt(r.qty),
					warehouse: r.warehouse, tag: r.tag || null,
				})),
				finished_items: fins.map((f) => ({
					item_code: f.item_code, qty: flt(f.qty), tag: f.tag || null,
				})),
			}),
		},
		callback: (r) => {
			frappe.dom.unfreeze();
			if (!r || !r.message) { d.enable_primary_action(); return; }
			const m = r.message;
			d.hide();
			page.cwb.selected.clear();
			// The counts and balances have moved, so both sides reload.
			reload_all(page);

			const links = [
				`<a href="/app/conversion-entry/${encodeURIComponent(m.conversion_entry)}">${
					frappe.utils.escape_html(m.conversion_entry)}</a>`,
			];
			if (m.stock_entry) {
				links.push(`<a href="/app/stock-entry/${encodeURIComponent(m.stock_entry)}">${
					frappe.utils.escape_html(m.stock_entry)} (${__('Draft')})</a>`);
			}
			frappe.msgprint({
				title: __('Converted'),
				indicator: 'green',
				message: __('Conversion {0} submitted.', [m.conversion_entry])
					+ '<br>' + links.join('<br>'),
			});
		},
		error: () => {
			frappe.dom.unfreeze();
			// The server ran insert and submit in one transaction, so a failure
			// has left nothing behind; the dialog stays open with its message.
			d.enable_primary_action();
		},
	});
}
