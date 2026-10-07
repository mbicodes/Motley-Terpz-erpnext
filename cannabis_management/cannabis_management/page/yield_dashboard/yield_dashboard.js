// Copyright (c) 2026, alltechvirtual.com and contributors
// Yield Dashboard — what every conversion actually returned.
//
// Yields come from the conversions themselves (Raw Material 1 in, Finished
// Good 1 out, both in grams), not from the micron fields: those are new and
// empty on every row today, while the conversions go back 264 entries.
//
// The headline per stage is weighted (total out / total in), not an average of
// run percentages — otherwise a 4 lb run counts as much as a 60 lb one. The
// mean is shown beside it, because a gap between the two is itself the signal.

const YD_METHOD = 'cannabis_management.cannabis_management.page.yield_dashboard.yield_dashboard.';

frappe.pages['yield-dashboard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper, title: __('Yield Dashboard'), single_column: true,
	});
	wrapper.page = page;

	const today = frappe.datetime.get_today();
	page.yd = {
		runs: [], summary: [], meta: {},
		filters: {
			from_date: frappe.datetime.add_months(today, -3),
			to_date: today,
			company: '', project: '', reasons: '', source: '',
			stage: '', search: '', hide_flagged: 0,
		},
		groupby: 'stage',
		open: {},          // run key -> expanded?
	};

	page.main.html(`
		<div class="yd-root">
			<div class="yd-head">
				<div>
					<div class="yd-title">${__('Yields — Conversion Performance')}</div>
					<div class="yd-sub" id="yd-sub">${__('Loading…')}</div>
				</div>
				<div>
					<button class="btn btn-default btn-sm" id="yd-excel" style="margin-right:6px;">${__('Export to Excel')}</button>
					<button class="btn btn-default btn-sm" id="yd-csv" style="margin-right:6px;">${__('Export to CSV')}</button>
					<button class="btn btn-default btn-sm" id="yd-refresh">${__('Refresh')}</button>
				</div>
			</div>

			<div class="yd-seg yd-seg-lg" id="yd-sourceseg">
				<button data-source="" class="on">${__('Both')}</button>
				<button data-source="Conversion">${__('Conversion yields')}</button>
				<button data-source="Manufacturing">${__('Manufacturing yields')}</button>
			</div>

			<div class="yd-kpis" id="yd-kpis"></div>

			<div class="yd-toolbar">
				<div class="yd-f"><label>${__('From')}</label><input type="date" id="yd-from"></div>
				<div class="yd-f"><label>${__('To')}</label><input type="date" id="yd-to"></div>
				<div class="yd-f"><label>${__('Company')}</label><select id="yd-company"></select></div>
				<div class="yd-f"><label>${__('Reason')}</label><select id="yd-reasons">
					<option value="">${__('All reasons')}</option>
					<option value="Tolling">Tolling</option>
					<option value="Blending">Blending</option>
					<option value="Co-packing">Co-packing</option>
					<option value="Others">Others</option>
				</select></div>
				<div class="yd-f"><label>${__('Stage')}</label><select id="yd-stage"></select></div>
				<div class="yd-f"><label>${__('Search')}</label>
					<input type="text" id="yd-search" placeholder="${__('entry, item, project…')}"></div>
				<div class="yd-f"><label>&nbsp;</label>
					<label style="font-weight:400;font-size:12px;display:flex;align-items:center;gap:6px;">
						<input type="checkbox" id="yd-hideflag" style="min-width:auto;">${__('Hide flagged')}</label></div>
			</div>

			<div class="yd-sec" style="display:flex;align-items:center;gap:12px;">
				<span>${__('Summary')}</span>
				<div class="yd-seg" id="yd-groupseg">
					<button data-group="stage" class="on">${__('By stage')}</button>
					<button data-group="material">${__('By raw material')}</button>
				</div>
			</div>
			<div id="yd-stages"></div>

			<div class="yd-sec">${__('Every run, newest first — click a row for its raw materials')}</div>
			<div id="yd-runs"><div class="yd-loading">${__('Loading runs…')}</div></div>

			<div class="yd-foot">
				${__('Yield = total output grams ÷ total input grams × 100, counting every Raw Material 1–7 and Finished Good 1–3 on the row, each converted by its own UOM. A run with a material that has no gram conversion (anything in Nos) shows no percentage — a partial denominator would be worse than a blank. Anything over 100% is flagged rather than averaged in: a pure extraction cannot return more than went in.')}
			</div>
		</div>
	`);

	bind(page);
	load(page);
};

function bind(page) {
	const f = page.yd.filters;
	page.main.find('#yd-from').val(f.from_date);
	page.main.find('#yd-to').val(f.to_date);

	page.main.find('#yd-refresh').on('click', () => load(page));
	page.main.find('#yd-from').on('change', function () { f.from_date = this.value; load(page); });
	page.main.find('#yd-to').on('change', function () { f.to_date = this.value; load(page); });
	page.main.find('#yd-company').on('change', function () { f.company = this.value; load(page); });
	page.main.find('#yd-reasons').on('change', function () { f.reasons = this.value; load(page); });
	page.main.find('#yd-sourceseg button').on('click', function () {
		page.main.find('#yd-sourceseg button').removeClass('on');
		$(this).addClass('on');
		f.source = String($(this).attr('data-source') || '');
		// Stage options differ per source, so a stage picked under one book must
		// not silently filter everything out under the other.
		f.stage = '';
		load(page);
	});

	page.main.find('#yd-groupseg button').on('click', function () {
		page.main.find('#yd-groupseg button').removeClass('on');
		$(this).addClass('on');
		page.yd.groupby = $(this).data('group');
		render(page);
	});

	// A run expands to one line per raw material it consumed.
	page.main.on('click', '.yd-runline', function () {
		const key = $(this).data('runkey');
		page.yd.open[key] = !page.yd.open[key];
		render(page);
	});
	// Stage and search are client-side: the rows are already here, and a round
	// trip to narrow a list you can see is just latency.
	page.main.find('#yd-stage').on('change', function () { f.stage = this.value; render(page); });
	page.main.find('#yd-search').on('input', function () { f.search = this.value; render(page); });
	page.main.find('#yd-hideflag').on('change', function () { f.hide_flagged = this.checked ? 1 : 0; render(page); });

	page.main.find('#yd-excel').on('click', () => download(page, 'xlsx'));
	page.main.find('#yd-csv').on('click', () => download(page, 'csv'));
}

function server_filters(page) {
	const f = page.yd.filters;
	return { from_date: f.from_date, to_date: f.to_date, company: f.company,
		reasons: f.reasons, source: f.source };
}

function download(page, format) {
	if (!page.yd.runs.length) {
		frappe.msgprint(__('Nothing to export yet.'));
		return;
	}
	frappe.dom.freeze(format === 'csv' ? __('Building CSV…') : __('Building workbook…'));
	open_url_post(frappe.request.url, {
		cmd: YD_METHOD + (format === 'csv' ? 'export_csv' : 'export_xlsx'),
		filters: JSON.stringify(server_filters(page)),
	});
	setTimeout(() => frappe.dom.unfreeze(), 3000);
}

function load(page) {
	frappe.call({
		method: YD_METHOD + 'get_data',
		args: { filters: JSON.stringify(server_filters(page)) },
		callback: (r) => {
			if (!r || !r.message) return;
			page.yd.runs = r.message.runs || [];
			page.yd.summary = r.message.summary || [];
			page.yd.materials = r.message.materials || [];
			page.yd.meta = r.message;
			fill_selects(page);
			const book = page.yd.filters.source || __('Conversion + Manufacturing');
			page.main.find('#yd-sub').text(
				__('{0} · {1} runs · as of {2}',
					[book, page.yd.runs.length, r.message.as_of]));
			render(page);
		},
	});
}

function fill_selects(page) {
	const esc = frappe.utils.escape_html;
	const f = page.yd.filters;

	const $co = page.main.find('#yd-company');
	if (!$co.find('option').length) {
		$co.html(['<option value="">' + __('All companies') + '</option>'].concat(
			(page.yd.meta.companies || []).map((c) => `<option value="${esc(c)}">${esc(c)}</option>`)
		).join('')).val(f.company);
	}

	// Stages are rebuilt each load: which pairs exist depends on the date range.
	const seen = [];
	page.yd.runs.forEach((r) => {
		if (!seen.some((s) => s.key === r.stage)) seen.push({ key: r.stage, label: r.stage_label });
	});
	page.main.find('#yd-stage').html(
		['<option value="">' + __('All stages') + '</option>'].concat(
			seen.map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`)
		).join('')
	).val(f.stage);
}

function visible(page) {
	const f = page.yd.filters;
	const q = (f.search || '').toLowerCase();
	return page.yd.runs.filter((r) => {
		if (f.stage && r.stage !== f.stage) return false;
		if (f.hide_flagged && r.flag) return false;
		if (q) {
			const hay = [r.entry, r.rm_name, r.fg_name, r.project, r.party, r.company]
				.join(' ').toLowerCase();
			if (hay.indexOf(q) === -1) return false;
		}
		return true;
	});
}

function g(n) { return Math.round(n || 0).toLocaleString('en-US'); }
function pct(n) { return (n === null || n === undefined) ? '—' : n.toFixed(2) + '%'; }

// Bands are stage-relative: 60% is a poor rosin press and an impossible hash
// wash, so a fixed threshold would mislabel one of them.
function pct_class(value, median) {
	if (value === null || value === undefined || !median) return '';
	if (value >= median * 1.1) return 'good';
	if (value >= median * 0.75) return 'mid';
	return 'bad';
}

function render(page) {
	const rows = visible(page);
	render_kpis(page, rows);
	if (page.yd.groupby === 'material') render_materials(page, rows);
	else render_stages(page, rows);
	render_runs(page, rows);
}

function render_kpis(page, rows) {
	const clean = rows.filter((r) => !r.flag && r.yield_pct !== null);
	const in_g = clean.reduce((s, r) => s + r.in_grams, 0);
	const out_g = clean.reduce((s, r) => s + r.out_grams, 0);
	const flagged = rows.filter((r) => r.flag);
	const nopct = rows.filter((r) => r.yield_pct === null);

	const kpis = [
		{ label: __('RUNS IN VIEW'), value: rows.length.toLocaleString('en-US'),
			sub: clean.length + ' ' + __('with a usable yield') },
		{ label: __('INPUT'), value: g(in_g) + ' g',
			sub: (in_g / 453.592).toFixed(1) + ' ' + __('lbs') },
		{ label: __('OUTPUT'), value: g(out_g) + ' g',
			sub: __('across all stages in view') },
		flagged.length
			? { cls: 'bad', label: __('NEEDS CHECKING'), value: flagged.length.toLocaleString('en-US'),
				sub: __('over 100% — likely a keying error') }
			: { cls: nopct.length ? 'warn' : '', label: __('NO PERCENTAGE'),
				value: nopct.length.toLocaleString('en-US'),
				sub: __('output counted in Nos') },
	];

	page.main.find('#yd-kpis').html(kpis.map((k) => `
		<div class="yd-kpi ${k.cls || ''}">
			<div class="yd-kpi-label">${k.label}</div>
			<div class="yd-kpi-value">${k.value}</div>
			<div class="yd-kpi-sub">${k.sub}</div>
		</div>`).join(''));
}

function render_stages(page, rows) {
	const esc = frappe.utils.escape_html;
	// Recomputed from the visible rows so the cards always agree with the table
	// below them, even under a client-side stage or search filter.
	const by = {};
	rows.forEach((r) => {
		const s = by[r.stage] = by[r.stage] || {
			label: r.stage_label, runs: 0, in_g: 0, out_g: 0, pcts: [], flagged: 0,
		};
		s.runs++;
		if (r.flag) { s.flagged++; return; }
		s.in_g += r.in_grams; s.out_g += r.out_grams;
		if (r.yield_pct !== null) s.pcts.push(r.yield_pct);
	});

	const named = (page.yd.meta.stages || []).map((s) => s.key);
	const list = Object.keys(by).map((k) => Object.assign({ key: k }, by[k]))
		.sort((a, b) => {
			const ai = named.indexOf(a.key), bi = named.indexOf(b.key);
			if (ai !== bi) return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
			return b.in_g - a.in_g;
		});

	if (!list.length) {
		page.main.find('#yd-stages').html(`<div class="yd-empty">${__('No runs match these filters.')}</div>`);
		return;
	}

	page.main.find('#yd-stages').html('<div class="yd-stagecard">' + list.map((s) => {
		const weighted = s.in_g ? (s.out_g / s.in_g * 100) : null;
		const avg = s.pcts.length ? s.pcts.reduce((a, b) => a + b, 0) / s.pcts.length : null;
		const sorted = s.pcts.slice().sort((a, b) => a - b);
		const med = sorted.length
			? (sorted.length % 2 ? sorted[(sorted.length - 1) / 2]
				: (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2)
			: null;
		return `<div class="yd-sc">
			<div class="yd-sc-name">${esc(s.label)}</div>
			<div class="yd-dim">${s.runs} ${s.runs === 1 ? __('run') : __('runs')}${
				s.flagged ? ` · <span style="color:var(--bad)">${s.flagged} ${__('flagged')}</span>` : ''}</div>
			<div class="yd-sc-big">${pct(weighted)}</div>
			<div class="yd-dim">${__('weighted — total out ÷ total in')}</div>
			<div class="yd-sc-row"><span>${__('Average run')}</span><b>${pct(avg)}</b></div>
			<div class="yd-sc-row"><span>${__('Median run')}</span><b>${pct(med)}</b></div>
			<div class="yd-sc-row"><span>${__('Best / worst')}</span><b>${
				sorted.length ? pct(sorted[sorted.length - 1]) + ' / ' + pct(sorted[0]) : '—'}</b></div>
			<div class="yd-sc-row"><span>${__('In → out')}</span><b>${g(s.in_g)} → ${g(s.out_g)} g</b></div>
		</div>`;
	}).join('') + '</div>');
}

// Yield per raw material, apportioning each run's output across its inputs by
// their share of the input grams. Exact for a single-input run; an assumption
// for a blend, so the blend count is shown beside it rather than hidden.
function render_materials(page, rows) {
	const esc = frappe.utils.escape_html;
	const by = {};
	rows.forEach((r) => {
		if (r.flag) return;
		(r.materials || []).forEach((m) => {
			const b = by[m.item_code] = by[m.item_code] || {
				code: m.item_code, label: m.item_name, group: m.item_group,
				runs: 0, blended: 0, in_g: 0, out_g: 0, pcts: [], sources: {},
			};
			b.runs++;
			if (r.rm_count > 1) b.blended++;
			b.sources[r.source] = 1;
			b.in_g += m.grams;
			b.out_g += m.out_grams;
			if (m.yield_pct !== null && m.yield_pct !== undefined) b.pcts.push(m.yield_pct);
		});
	});

	const list = Object.keys(by).map((k) => by[k]).sort((a, b) => b.in_g - a.in_g);
	if (!list.length) {
		page.main.find('#yd-stages').html(`<div class="yd-empty">${__('No runs match these filters.')}</div>`);
		return;
	}

	// Median across materials, so a material is coloured against its peers
	// rather than an absolute number that means different things per process.
	const all = list.map((b) => b.in_g ? b.out_g / b.in_g * 100 : null).filter((v) => v !== null).sort((a, b) => a - b);
	const med = all.length ? (all.length % 2 ? all[(all.length - 1) / 2]
		: (all[all.length / 2 - 1] + all[all.length / 2]) / 2) : null;

	const body = list.map((b) => {
		const weighted = b.in_g ? (b.out_g / b.in_g * 100) : null;
		const avg = b.pcts.length ? b.pcts.reduce((x, y) => x + y, 0) / b.pcts.length : null;
		return `<tr>
			<td><span class="yd-strong">${esc(b.label)}</span>
				<div class="yd-dim">${esc(b.code)} · ${esc(b.group || '—')}</div></td>
			<td class="yd-num">${b.runs}${b.blended ? `<div class="yd-dim">${b.blended} ${__('blended')}</div>` : ''}</td>
			<td class="yd-num">${g(b.in_g)} g<div class="yd-dim">${(b.in_g / 453.592).toFixed(1)} lbs</div></td>
			<td class="yd-num">${g(b.out_g)} g</td>
			<td class="yd-num"><span class="yd-pct ${pct_class(weighted, med)}">${pct(weighted)}</span></td>
			<td class="yd-num">${pct(avg)}</td>
			<td class="yd-dim">${esc(Object.keys(b.sources).join(', '))}</td>
		</tr>`;
	}).join('');

	page.main.find('#yd-stages').html(`
		<table class="yd-table"><thead><tr>
			<th>${__('Raw material')}</th>
			<th class="yd-num">${__('Runs')}</th>
			<th class="yd-num">${__('Input')}</th>
			<th class="yd-num">${__('Output credited')}</th>
			<th class="yd-num">${__('Weighted yield')}</th>
			<th class="yd-num">${__('Average run')}</th>
			<th>${__('Source')}</th>
		</tr></thead><tbody>${body}</tbody></table>
		<div class="yd-dim" style="margin-top:7px;">${
			__('A blended run credits its output to each input by that input\'s share of the grams that went in. For a single-material run the figure is exact.')}</div>`);
}

function render_runs(page, rows) {
	const esc = frappe.utils.escape_html;
	if (!rows.length) {
		page.main.find('#yd-runs').html(`<div class="yd-empty">${__('No runs match these filters.')}</div>`);
		return;
	}

	// Median per stage, so a run is coloured against its own process.
	const meds = {};
	rows.forEach((r) => {
		if (r.flag || r.yield_pct === null) return;
		(meds[r.stage] = meds[r.stage] || []).push(r.yield_pct);
	});
	Object.keys(meds).forEach((k) => {
		const s = meds[k].sort((a, b) => a - b);
		meds[k] = s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
	});

	const route = (r) => r.source === 'Manufacturing'
		? '/app/stock-entry/' + encodeURIComponent(r.entry)
		: '/app/conversion-entry/' + encodeURIComponent(r.entry);

	const body = rows.map((r) => {
		const key = r.source + '|' + r.row_id;
		const open = !!page.yd.open[key];
		// Expanding is worth offering only where there is more than one input to
		// break out; a 1-to-1 run would just repeat the line above it.
		const expandable = (r.materials || []).length > 1;
		let html = `
		<tr class="${r.flag ? 'yd-flagged' : ''}${expandable ? ' yd-runline' : ''}${open ? ' open' : ''}"
			data-runkey="${esc(key)}">
			<td>${expandable ? `<span class="yd-arrow">${open ? '▾' : '▸'}</span> ` : ''}${esc(r.posting_date)}</td>
			<td><a href="${route(r)}" onclick="event.stopPropagation()">${esc(r.entry)}</a>
				<div class="yd-dim">${esc(r.source)} · ${esc(r.stage_label)}</div></td>
			<td>${esc(r.rm_name)}<div class="yd-dim">${esc(r.rm_group)}${
				r.rm_count > 1 ? ` · ${r.rm_count} ${__('inputs')}` : ''}</div></td>
			<td class="yd-num">${g(r.in_grams)} g</td>
			<td>${esc(r.fg_name)}<div class="yd-dim">${esc(r.fg_group)}${
				r.fg_count > 1 ? ` · ${r.fg_count} ${__('outputs')}` : ''}</div></td>
			<td class="yd-num">${g(r.out_grams)} g</td>
			<td class="yd-num">${r.flag
				? `<span class="yd-flag">${pct(r.yield_pct)} — ${__('check entry')}</span>`
				: `<span class="yd-pct ${pct_class(r.yield_pct, meds[r.stage])}">${pct(r.yield_pct)}</span>`}</td>
			<td>${esc(r.project || '—')}<div class="yd-dim">${esc(r.party || '')}</div></td>
			<td class="yd-dim">${esc(r.company)}</td>
		</tr>`;

		if (open) {
			html += (r.materials || []).map((m) => `
				<tr class="yd-sub">
					<td></td>
					<td colspan="2">${esc(m.item_name)}
						<div class="yd-dim">${esc(m.item_code)} · ${esc(m.item_group || '—')}</div></td>
					<td class="yd-num">${m.qty.toLocaleString('en-US')} ${esc(m.uom)}
						<div class="yd-dim">${g(m.grams)} g · ${
							m.share_pct === null ? '—' : m.share_pct.toFixed(1) + '% ' + __('of input')}</div></td>
					<td class="yd-num">${g(m.out_grams)} g
						<div class="yd-dim">${__('credited')}</div></td>
					<td class="yd-num"><span class="yd-pct">${pct(m.yield_pct)}</span></td>
					<td colspan="2"></td>
				</tr>`).join('');
		}
		return html;
	}).join('');

	page.main.find('#yd-runs').html(`
		<table class="yd-table"><thead><tr>
			<th>${__('Date')}</th><th>${__('Entry')}</th>
			<th>${__('Raw materials')}</th><th class="yd-num">${__('In (g)')}</th>
			<th>${__('Finished goods')}</th><th class="yd-num">${__('Out (g)')}</th>
			<th class="yd-num">${__('Yield')}</th>
			<th>${__('Project')}</th><th>${__('Company')}</th>
		</tr></thead><tbody>${body}</tbody></table>`);
}
