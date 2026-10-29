const IOV = 'cannabis_management.cannabis_management.page.inventory_overview.inventory_overview.';
const IOV_COLOURS = {
	'Tier 1': '#2f7d4f',
	'Tier 2': '#2563eb',
	'Tier 3': '#c2410c',
	'Raw Rosin': '#a16207',
	'Bubble Hash': '#0f766e',
	'Fresh Frozen': '#0284c7',
	'Freezer - MTM': '#4f46e5',
	'Freezer 2 - MTM': '#9333ea',
	'Freezer 3 - MTM': '#db2777',
	'Freezer 4 - MTM': '#475569',
};
const IOV_SPARE = ['#0891b2', '#65a30d', '#be123c', '#7c2d12', '#1e40af', '#6d28d9'];
const IOV_BLOCK_COLOURS = ['#2f7d4f', '#2563eb', '#a16207', '#0f766e', '#7c3aed', '#0284c7', '#db2777'];

function iov_colour(label, spare) {
	if (IOV_COLOURS[label]) return IOV_COLOURS[label];
	const i = spare.i++;
	return i < IOV_SPARE.length ? IOV_SPARE[i] : `hsl(${Math.round((i * 137.5) % 360)} 62% 36%)`;
}

frappe.pages['inventory-overview'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper, title: __('Inventory Overview'), single_column: true,
	});
	wrapper.page = page;
	page.iov = { data: null };

	page.main.html(`
		<div class="iov-root">
			<div class="iov-top">
				<span class="iov-title">${__('Inventory Overview')}</span>
				<span class="iov-sub" id="iov-sub">${__('Loading…')}</span>
				<div class="iov-spacer"></div>
				<button class="iov-btn" id="iov-print">${__('Print')}</button>
				<button class="iov-btn primary" id="iov-refresh">${__('Refresh')}</button>
			</div>
			<div class="iov-banner" id="iov-banner"></div>
			<div id="iov-blocks"><div class="iov-loading">${__('Loading stock…')}</div></div>
			<div class="iov-note">
				${__('Strain is the item name with its tier suffix removed. Batch (Fresh Frozen only) is the Project Name the stock was posted against — this site tracks batches as Projects on the Stock Ledger, so stock posted without one shows as (no batch). Reserved follows ERPNext’s own commitments: Sales Orders, Work Orders, subcontracting and production plans.')}
			</div>
		</div>
	`);

	page.main.find('#iov-refresh').on('click', () => load(page));
	page.main.find('#iov-print').on('click', () => window.print());
	load(page);
};

function iov_type(group) {
	return String(group || '').replace(/^Fresh Frozen - /, '');
}

function load(page) {
	frappe.call({
		method: IOV + 'get_overview',
		callback: (r) => {
			if (!r || !r.message) return;
			page.iov.data = r.message;
			page.main.find('#iov-sub').text(__('as of {0}', [r.message.as_of]));
			page.main.find('#iov-banner').text(__(
				'Available inventory as of {0}. Quantities in grams, subject to prior sale.',
				[frappe.datetime.str_to_user(r.message.as_of)]));
			render(page);
		},
	});
}

function num(v, dp) {
	return format_number(v || 0, null, dp === undefined ? 2 : dp);
}

function render(page) {
	const esc = frappe.utils.escape_html;
	const d = page.iov.data;

	const spare = { i: 0 };

	const html = d.blocks.map((b, bi) => {
		const cols = b.sections.map((s) => {
			const colour = iov_colour(s.label, spare);
			const head = `<tr>
				<th>${__('Strain')}</th>
				${b.multi_warehouse ? `<th>${__('Warehouse')}</th>` : ''}
				${s.batch ? `<th>${__('Batch')}</th>` : ''}
				${b.show_type ? `<th>${__('Type')}</th>` : ''}
				<th class="iov-num">${b.show_uom ? __('Qty') : __('Avail (g)')}</th>
				${b.reserved ? `<th class="iov-num">${__('Reserved Qty')}</th>
				                <th class="iov-num">${__('Available')}</th>` : ''}
			</tr>`;

			const body = s.rows.length ? s.rows.map((r) => `
				<tr>
					<td title="${esc(r.item_code)}">${esc(r.strain)}</td>
					${b.multi_warehouse ? `<td class="iov-batch">${esc(r.warehouse)}</td>` : ''}
					${s.batch ? `<td class="iov-batch">${esc(r.source_batch)}</td>` : ''}
					${b.show_type ? `<td class="iov-batch">${esc(iov_type(r.item_group))}</td>` : ''}
					<td class="iov-num">${num(r.qty)}${b.show_uom ? ` <span class="iov-uom">${esc(r.uom)}</span>` : ''}</td>
					${b.reserved ? `<td class="iov-num">${num(r.reserved_qty)}</td>
						<td class="iov-num ${r.available < 0 ? 'iov-neg' : ''}">${num(r.available)}</td>` : ''}
				</tr>`).join('')
				: `<tr><td colspan="${(b.reserved ? 4 : 2) + (s.batch ? 1 : 0) + (b.show_type ? 1 : 0) + (b.multi_warehouse ? 1 : 0)}" class="iov-empty">${__('Nothing in stock here.')}</td></tr>`;

			const strains = new Set(s.rows.map((r) => r.strain)).size;
			const total = s.rows.length ? `<tr class="iov-total">
					<td>${strains} ${strains === 1 ? __('strain') : __('strains')}</td>
					${s.batch ? '<td></td>' : ''}${b.show_type ? '<td></td>' : ''}${b.multi_warehouse ? '<td></td>' : ''}
					<td class="iov-num">${num(s.total_qty)}</td>
					${b.reserved ? `<td></td><td class="iov-num">${num(s.total_available)}</td>` : ''}
				</tr>` : '';

			return `<div class="iov-col" style="--col:${colour}">
				<div class="iov-collabel">${esc(s.label)}</div>
				<div class="iov-scroll"><table class="iov-table"><thead>${head}</thead>
				<tbody>${body}${total}</tbody></table></div>
			</div>`;
		}).join('');

		return `<div class="iov-block" style="--accent:${IOV_BLOCK_COLOURS[bi % IOV_BLOCK_COLOURS.length]}">
			<div class="iov-blockhead">${esc(b.title)}</div>
			<div class="iov-cols">${cols}</div>
		</div>`;
	}).join('');

	page.main.find('#iov-blocks').html(html);
}
