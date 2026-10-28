// Copyright (c) 2026, alltechvirtual.com and contributors
// Inventory Overview — the Physical Inventory Weekly sheet, live from stock.
//
// Laid out the way the sheet is: a boxed section per area of the warehouse,
// tiers side by side inside it, same column order. Reserved and Available only
// appear on the block that has them in the sheet, so a column never shows a
// number the sheet would not have carried there.

const IOV = 'cannabis_management.cannabis_management.page.inventory_overview.inventory_overview.';
const IOV_TIER_CLASS = { 'Tier 1': 't1', 'Tier 2': 't2', 'Tier 3': 't3' };

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
				${__('Strain is the item name with its tier suffix removed. Source Batch is the Project the stock was posted against — this site tracks batches as Projects on the Stock Ledger, so stock posted without one shows as (no batch). Reserved follows ERPNext’s own commitments: Sales Orders, Work Orders, subcontracting and production plans.')}
			</div>
		</div>
	`);

	page.main.find('#iov-refresh').on('click', () => load(page));
	page.main.find('#iov-print').on('click', () => window.print());
	load(page);
};

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

	const html = d.blocks.map((b) => {
		const cols = b.sections.map((s) => {
			const cls = IOV_TIER_CLASS[s.label] || 'flat';
			const head = `<tr>
				<th>${__('Strain')}</th>
				${b.multi_warehouse ? `<th>${__('Warehouse')}</th>` : ''}
				<th>${__('Source Batch')}</th>
				<th class="iov-num">${__('Avail (g)')}</th>
				${b.reserved ? `<th class="iov-num">${__('Reserved Qty')}</th>
				                <th class="iov-num">${__('Available')}</th>` : ''}
			</tr>`;

			const body = s.rows.length ? s.rows.map((r) => `
				<tr>
					<td title="${esc(r.item_code)}">${esc(r.strain)}</td>
					${b.multi_warehouse ? `<td class="iov-batch">${esc(r.warehouse)}</td>` : ''}
					<td class="iov-batch">${esc(r.source_batch)}</td>
					<td class="iov-num">${num(r.qty)}</td>
					${b.reserved ? `<td class="iov-num">${num(r.reserved_qty)}</td>
						<td class="iov-num ${r.available < 0 ? 'iov-neg' : ''}">${num(r.available)}</td>` : ''}
				</tr>`).join('')
				: `<tr><td colspan="${(b.reserved ? 5 : 3) + (b.multi_warehouse ? 1 : 0)}" class="iov-empty">${__('Nothing in stock here.')}</td></tr>`;

			// Distinct strains, not row count: one strain can hold several batches
			// and the menu counts the strain once.
			const strains = new Set(s.rows.map((r) => r.strain)).size;
			const total = s.rows.length ? `<tr class="iov-total">
					<td>${strains} ${strains === 1 ? __('strain') : __('strains')}</td>
					<td></td>${b.multi_warehouse ? '<td></td>' : ''}
					<td class="iov-num">${num(s.total_qty)}</td>
					${b.reserved ? `<td></td><td class="iov-num">${num(s.total_available)}</td>` : ''}
				</tr>` : '';

			return `<div class="iov-col ${cls}">
				<div class="iov-collabel">${esc(s.label)}</div>
				<table class="iov-table"><thead>${head}</thead>
				<tbody>${body}${total}</tbody></table>
			</div>`;
		}).join('');

		return `<div class="iov-block">
			<div class="iov-blockhead">${esc(b.title)}</div>
			<div class="iov-cols">${cols}</div>
		</div>`;
	}).join('');

	page.main.find('#iov-blocks').html(html);
}
