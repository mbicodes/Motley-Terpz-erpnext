(() => {
	const METHOD = 'cannabis_management.cannabis_management.page.operations_scorecard.operations_scorecard.';
	const STORE_KEY = 'osc_state';
	const COLS = [
		{ key: 'week', band: 'week' },
		{ key: 'prev_week', band: 'week' },
		{ key: 'month', band: 'month' },
		{ key: 'prev_month', band: 'month' },
	];
	const esc = (v) => frappe.utils.escape_html(v == null ? '' : String(v));

	function readStore() {
		try {
			return JSON.parse(localStorage.getItem(STORE_KEY) || '{}') || {};
		} catch (e) {
			return {};
		}
	}

	function writeStore(state) {
		try {
			localStorage.setItem(STORE_KEY, JSON.stringify({ company: state.company, open: state.open }));
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
		if (s.isSame(e, 'month')) return `${s.format('MMM D')} – ${e.format('D')}`;
		return `${s.format('MMM D')} – ${e.format('MMM D')}`;
	}

	function periodHead(p, today) {
		const t = moment(today);
		if (p.key === 'week' || p.key === 'prev_week') {
			const diff = moment(p.start).diff(t.clone().startOf('isoWeek'), 'weeks');
			const rel = diff === 0 ? __('This week') : diff === -1 ? __('Last week') : diff === 1 ? __('Next week') : null;
			return {
				title: rel || __('Week of {0}', [moment(p.start).format('MMM D')]),
				range: rangeText(p.start, p.end) + (p.partial && !p.future ? ` · ${__('to date')}` : ''),
			};
		}
		const diff = moment(p.start).diff(t.clone().startOf('month'), 'months');
		const rel = diff === 0 ? __('This month') : diff === -1 ? __('Last month') : null;
		return {
			title: rel || moment(p.start).format('MMMM YYYY'),
			range: (rel ? moment(p.start).format('MMMM YYYY') : rangeText(p.start, p.end)) +
				(p.partial && !p.future ? ` · ${__('to date')}` : ''),
		};
	}

	frappe.pages['operations-scorecard'].on_page_load = function (wrapper) {
		const page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __('Operations Scorecard'),
			single_column: true,
		});
		const saved = readStore();
		const state = {
			as_of: frappe.datetime.get_today(),
			company: saved.company || '',
			open: saved.open || {},
			data: null,
			req: 0,
		};
		const $root = $(`
			<div class="osc">
				<div class="osc-toolbar">
					<label class="osc-field">
						<span>${__('Company')}</span>
						<select class="form-control input-sm osc-company"><option value="">${__('All companies')}</option></select>
					</label>
					<div class="osc-field">
						<span>${__('Week of')}</span>
						<div class="osc-weeknav">
							<button type="button" class="btn btn-default btn-sm osc-prev" title="${__('Previous week')}" aria-label="${__('Previous week')}">&#8249;</button>
							<input type="date" class="form-control input-sm osc-date" aria-label="${__('Week of')}">
							<button type="button" class="btn btn-default btn-sm osc-next" title="${__('Next week')}" aria-label="${__('Next week')}">&#8250;</button>
						</div>
					</div>
					<button type="button" class="btn btn-default btn-sm osc-today">${__('This week')}</button>
					<span class="osc-spacer"></span>
					<button type="button" class="btn btn-default btn-sm osc-expand">${__('Expand all')}</button>
					<button type="button" class="btn btn-default btn-sm osc-collapse">${__('Collapse all')}</button>
					<button type="button" class="btn btn-default btn-sm osc-csv">${__('Export CSV')}</button>
					<button type="button" class="btn btn-default btn-sm osc-refresh">${__('Refresh')}</button>
				</div>
				<div class="osc-caption"></div>
				<div class="osc-sheet-wrap"><div class="osc-loading">${__('Loading…')}</div></div>
				<details class="osc-notes">
					<summary>${__('How these numbers are worked out')}</summary>
					<ul>
						<li>${__('Click any number to see the stock entries or invoices behind it. Weeks run Monday to Sunday.')}</li>
						<li><b>${__('Rosin inventory')}</b>: ${__('grams on hand in all warehouses at the end of each period (today for a period still running). T1 includes the old "Primes" grade and T2 the old "Subprimes" grade. Other rosin is raw rosin that is not graded yet plus Full Spec. T4 fills in once a "Tier 4" item group exists.')}</li>
						<li><b>${__('Pounds washed')}</b>: ${__('fresh frozen used up by submitted Manufacture and Repack stock entries that turned it into hash or rosin. Re-grading frozen into frozen is left out. Nature is anything washed from a Nature\'s Lab warehouse; MTM is everything else washed at Master Touch Manufacturing.')}</li>
						<li><b>${__('Kilos produced')}</b>: ${__('what came out of those washes: bubble hash for MTM washes, pressed rosin for Nature.')}</li>
						<li><b>${__('Live resin (BHO)')}</b>: ${__('fresh frozen sent to hydrocarbon extraction (Leaf, Buddies Brand). It is not a wash, so it is shown on its own and kept out of the wash totals and the average yield.')}</li>
						<li><b>${__('Sales')}</b>: ${__('submitted sales invoices to outside customers by invoice date, net of returns. Sales between our own companies are left out. Oil means rosin of every tier plus live resin.')}</li>
						<li><b>${__('Average yield')}</b>: ${__('grams produced ÷ grams of fresh frozen washed (1 lb = 453.59 g), weighted by weight.')}</li>
					</ul>
				</details>
			</div>
		`).appendTo(page.main);

		const $sheet = $root.find('.osc-sheet-wrap');
		const $company = $root.find('.osc-company');
		const $date = $root.find('.osc-date');
		$date.val(state.as_of);

		const setAsOf = (d) => {
			state.as_of = d || frappe.datetime.get_today();
			$date.val(state.as_of);
			load();
		};
		$root.find('.osc-prev').on('click', () => setAsOf(frappe.datetime.add_days(state.as_of, -7)));
		$root.find('.osc-next').on('click', () => setAsOf(frappe.datetime.add_days(state.as_of, 7)));
		$root.find('.osc-today').on('click', () => setAsOf(frappe.datetime.get_today()));
		$date.on('change', () => $date.val() && setAsOf($date.val()));
		$company.on('change', () => {
			state.company = $company.val() || '';
			writeStore(state);
			load();
		});
		$root.find('.osc-refresh').on('click', () => load());
		$root.find('.osc-expand').on('click', () => setAllOpen(true));
		$root.find('.osc-collapse').on('click', () => setAllOpen(false));
		$root.find('.osc-csv').on('click', () => exportCsv());

		$sheet.on('click', '.osc-toggle', function () {
			const id = $(this).attr('data-row');
			state.open[id] = !state.open[id];
			writeStore(state);
			render();
			$sheet.find(`.osc-toggle[data-row="${CSS.escape(id)}"]`).trigger('focus');
		});
		$sheet.on('click', '.osc-val', function () {
			const $b = $(this);
			const row = findRow($b.attr('data-row'));
			if (row && row.drill) openDrill(row, $b.attr('data-period'));
		});

		function allRows() {
			const out = [];
			const walk = (rows, section, path) => {
				let group = null;
				rows.forEach((r) => {
					if (r.sub) group = r.label;
					const base = group && !r.sub ? path.concat(group) : path;
					r._path = base;
					out.push({ row: r, section });
					walk(r.children || [], section, base.concat(r.label));
				});
			};
			(state.data ? state.data.sections : []).forEach((s) => walk(s.rows, s, []));
			return out;
		}

		function fullLabel(row) {
			return (row._path || []).concat(row.label).join(' › ');
		}

		function findRow(id) {
			const hit = allRows().find((x) => x.row.id === id);
			return hit && hit.row;
		}

		function setAllOpen(open) {
			allRows().forEach(({ row }) => {
				if ((row.children || []).length) state.open[row.id] = open;
			});
			writeStore(state);
			render();
		}

		function load() {
			const req = ++state.req;
			$sheet.addClass('is-loading');
			frappe.call({
				method: METHOD + 'get_data',
				args: { as_of: state.as_of, company: state.company },
			}).then((r) => {
				if (req !== state.req) return;
				state.data = r.message;
				fillCompanies(state.data.companies);
				render();
			}).always(() => {
				if (req === state.req) $sheet.removeClass('is-loading');
			});
		}

		function fillCompanies(companies) {
			if ($company.data('filled')) return;
			companies.forEach((c) => $company.append(`<option value="${esc(c)}">${esc(c)}</option>`));
			$company.data('filled', 1);
			if (state.company && !companies.includes(state.company)) state.company = '';
			$company.val(state.company);
		}

		function render() {
			const d = state.data;
			if (!d) return;
			const heads = d.periods.map((p) => ({ ...p, ...periodHead(p, d.today) }));
			const byKey = Object.fromEntries(heads.map((h) => [h.key, h]));
			const dot = '<span class="osc-dot">·</span>';
			$root.find('.osc-caption').html(
				`${__('Week')} <b>${esc(rangeText(heads[0].start, heads[0].end))}, ${esc(moment(heads[0].start).format('YYYY'))}</b>` +
				`${dot}${__('Month')} <b>${esc(moment(heads[2].start).format('MMMM YYYY'))}</b>` +
				`${dot}<b>${esc(d.company || __('All companies'))}</b>` +
				`${dot}${__('Click any number to see what is behind it')}`
			);

			let html = `
				<table class="osc-sheet">
					<colgroup><col class="osc-col-metric"><col class="osc-col-unit">${COLS.map(() => '<col class="osc-col-num">').join('')}</colgroup>
					<thead>
						<tr class="osc-bands">
							<th class="osc-h-metric" rowspan="2" scope="col">${__('Metric')}</th>
							<th class="osc-h-unit" rowspan="2" scope="col">${__('Unit')}</th>
							<th class="osc-band osc-band-week" colspan="2" scope="colgroup">${__('Weekly')}</th>
							<th class="osc-band osc-band-month" colspan="2" scope="colgroup">${__('Monthly')}</th>
						</tr>
						<tr class="osc-periods">
							${COLS.map((c, i) => `
								<th class="osc-h-period osc-${c.band} ${i % 2 ? 'is-prev' : 'is-cur'}" scope="col">
									<span class="osc-h-title">${esc(byKey[c.key].title)}</span>
									<span class="osc-h-range">${esc(byKey[c.key].range)}</span>
								</th>`).join('')}
						</tr>
					</thead>
					<tbody>`;
			d.sections.forEach((s) => {
				html += `
					<tr class="osc-section osc-sec-${esc(s.key)}">
						<th colspan="${COLS.length + 2}" scope="rowgroup">
							<span class="osc-sec-title">${esc(s.title)}</span>
							<span class="osc-sec-note">${esc(s.note || '')}</span>
						</th>
					</tr>`;
				s.rows.forEach((r) => { html += rowHtml(r, r.level || 0); });
			});
			html += '</tbody></table>';
			$sheet.html(html);
		}

		function rowHtml(r, level) {
			if (r.sub) {
				return `
					<tr class="osc-row osc-subhead lvl-${level}">
						<th class="osc-metric" scope="row"><span class="osc-label">${esc(r.label)}</span></th>
						<td class="osc-unit">${esc(r.unit)}</td>
						${COLS.map((c, i) => `<td class="osc-num osc-${c.band} ${i % 2 ? 'is-prev' : 'is-cur'}"></td>`).join('')}
					</tr>`;
			}
			const kids = r.children || [];
			const open = !!state.open[r.id];
			const toggle = kids.length
				? `<button type="button" class="osc-toggle${open ? ' is-open' : ''}" data-row="${esc(r.id)}"
						aria-expanded="${open}" title="${open ? __('Hide breakdown') : __('Show breakdown')}"
						aria-label="${esc((open ? __('Hide breakdown of {0}') : __('Show breakdown of {0}')).replace('{0}', r.label))}">${open ? '&minus;' : '+'}</button>`
				: '<span class="osc-toggle-gap"></span>';
			const cls = ['osc-row', `lvl-${level}`];
			if (r.total) cls.push('osc-total');
			if (level >= 2 || r.child) cls.push('osc-child');
			const cells = COLS.map((c, i) => {
				const v = r.values ? r.values[c.key] : null;
				const text = formatValue(v, r.unit);
				const tint = `osc-${c.band} ${i % 2 ? 'is-prev' : 'is-cur'}`;
				if (text == null) return `<td class="osc-num ${tint}"><span class="osc-empty">–</span></td>`;
				const neg = v < 0 ? ' is-neg' : '';
				if (!r.drill) return `<td class="osc-num ${tint}${neg}">${text}</td>`;
				return `<td class="osc-num ${tint}${neg}"><button type="button" class="osc-val" data-row="${esc(r.id)}"
					data-period="${c.key}" title="${__('See the entries behind this number')}">${text}</button></td>`;
			}).join('');
			let html = `
				<tr class="${cls.join(' ')}">
					<th class="osc-metric" scope="row">
						${toggle}<span class="osc-label${r.hint ? ' has-hint' : ''}"${r.hint ? ` title="${esc(r.hint)}"` : ''}>${esc(r.label)}</span>
					</th>
					<td class="osc-unit">${esc(r.unit)}</td>
					${cells}
				</tr>`;
			if (open) kids.forEach((k) => { html += rowHtml({ ...k, child: 1 }, (k.level || level + 1)); });
			return html;
		}

		function exportCsv() {
			const d = state.data;
			if (!d) return;
			const heads = d.periods.map((p) => periodHead(p, d.today));
			const out = [[__('Section'), __('Metric'), __('Unit'), ...heads.map((h) => `${h.title} (${h.range})`)]];
			allRows().forEach(({ row, section }) => {
				if (row.sub) return;
				out.push([section.title, fullLabel(row), row.unit, ...COLS.map((c) => {
					const v = row.values[c.key];
					return v == null ? '' : Math.round(v * 100) / 100;
				})]);
			});
			frappe.tools.downloadify(out, null, `Operations Scorecard ${state.as_of}`);
		}

		function openDrill(row, periodKey) {
			const d = state.data;
			const p = d.periods.find((x) => x.key === periodKey);
			const head = periodHead(p, d.today);
			const dialog = new frappe.ui.Dialog({
				title: esc(`${fullLabel(row)} · ${head.title} (${head.range})`),
				size: 'extra-large',
				fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
			});
			const $body = dialog.get_field('body').$wrapper;
			$body.html(`<div class="osc-drill"><div class="osc-loading">${__('Loading…')}</div></div>`);
			dialog.show();
			frappe.call({
				method: METHOD + 'get_drill',
				args: { drill: row.drill, period: periodKey, as_of: state.as_of, company: state.company },
			}).then((r) => {
				$body.find('.osc-drill').html(drillHtml(r.message));
			});
		}

		function link(doctype, name, label) {
			return `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}" target="_blank" rel="noopener">${esc(label || name)}</a>`;
		}

		function drillTable(cols, rows, total) {
			if (!rows.length) return `<div class="osc-drill-empty">${__('Nothing recorded for this period.')}</div>`;
			const cls = (c) => (c.num ? 'osc-num' : c.nowrap ? 'osc-nowrap' : '');
			const th = cols.map((c) => `<th class="${cls(c)}" scope="col">${esc(c.label)}</th>`).join('');
			const body = rows.map((r) => `<tr>${cols.map((c) => `<td class="${cls(c)}">${c.html(r)}</td>`).join('')}</tr>`).join('');
			const foot = total ? `<tfoot><tr>${cols.map((c) => `<td class="${c.num ? 'osc-num' : ''}">${total[c.key] || ''}</td>`).join('')}</tr></tfoot>` : '';
			return `<div class="osc-drill-count">${__('{0} rows', [rows.length])}</div>
				<div class="osc-drill-scroll"><table class="osc-drill-table"><thead><tr>${th}</tr></thead><tbody>${body}</tbody>${foot}</table></div>`;
		}

		function drillHtml(res) {
			const rows = res.rows || [];
			const sum = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
			const date = (r) => esc(frappe.datetime.str_to_user(r.posting_date));
			if (res.kind === 'inventory') {
				return drillTable([
					{ key: 'item', label: __('Item'), html: (r) => link('Item', r.item_code, r.item_name || r.item_code) },
					{ key: 'tier', label: __('Tier'), html: (r) => esc(r.tier) },
					{ key: 'group', label: __('Item group'), html: (r) => esc(r.item_group) },
					{ key: 'qty', label: __('On hand (g)'), num: 1, html: (r) => formatValue(r.qty, 'g') || '–' },
				], rows, { item: __('Total'), qty: formatValue(sum('qty'), 'g') });
			}
			if (res.kind === 'process') {
				const lbs = sum('lbs'), grams = sum('grams');
				return drillTable([
					{ key: 'date', label: __('Date'), html: date, nowrap: 1 },
					{ key: 'entry', label: __('Stock entry'), html: (r) => link('Stock Entry', r.name), nowrap: 1 },
					{ key: 'location', label: __('Washed by'), html: (r) => esc(r.location), nowrap: 1 },
					{ key: 'warehouse', label: __('From warehouse'), html: (r) => esc(r.warehouse) },
					{ key: 'inputs', label: __('Fresh frozen'), html: (r) => esc(r.inputs) },
					{ key: 'lbs', label: __('Lbs'), num: 1, html: (r) => formatValue(r.lbs, 'lbs') },
					{ key: 'outputs', label: __('Produced'), html: (r) => esc(r.outputs) },
					{ key: 'grams', label: __('Grams'), num: 1, html: (r) => formatValue(r.grams, 'g') },
					{ key: 'yield', label: __('Yield'), num: 1, html: (r) => formatValue(r.yield, '%') },
				], rows, {
					date: __('Total'), lbs: formatValue(lbs, 'lbs'), grams: formatValue(grams, 'g'),
					yield: lbs ? formatValue((grams / (lbs * 453.59237)) * 100, '%') : '',
				});
			}
			const qty = sum('qty'), amount = sum('amount');
			return drillTable([
				{ key: 'date', label: __('Date'), html: date, nowrap: 1 },
				{ key: 'invoice', label: __('Invoice'), html: (r) => link('Sales Invoice', r.invoice), nowrap: 1 },
				{ key: 'customer', label: __('Customer'), html: (r) => esc(r.customer) },
				{ key: 'item', label: __('Item'), html: (r) => link('Item', r.item_code, r.item_name || r.item_code) },
				{ key: 'tier', label: __('Tier'), html: (r) => esc(r.tier) },
				{ key: 'qty', label: __('Grams'), num: 1, html: (r) => formatValue(r.qty, 'g') || '–' },
				{ key: 'amount', label: __('Amount'), num: 1, html: (r) => formatValue(r.amount, '$') || '–' },
				{ key: 'price', label: __('$/g'), num: 1, html: (r) => (r.qty ? formatValue(r.amount / r.qty, '$/g') : '–') },
			], rows, {
				date: __('Total'), qty: formatValue(qty, 'g'), amount: formatValue(amount, '$'),
				price: qty ? formatValue(amount / qty, '$/g') : '',
			});
		}

		load();
	};
})();
