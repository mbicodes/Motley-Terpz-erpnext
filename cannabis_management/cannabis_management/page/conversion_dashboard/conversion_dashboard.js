// Conversion & Tolling dashboard. One server call returns both segments, so
// flipping between Tolling and Conversion re-renders without a round trip.
// All aggregation lives in conversion_dashboard.py.

const CVD_API = 'cannabis_management.cannabis_management.page.conversion_dashboard.conversion_dashboard';

frappe.pages['conversion-dashboard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Conversion & Tolling'),
		single_column: true,
	});
	new ConversionDashboard(page);
};

class ConversionDashboard {
	constructor(page) {
		this.page = page;
		this.segment = 'tolling';
		this.data = null;
		this.charts = {};
		this.page.set_secondary_action(__('Refresh'), () => this.load(), 'refresh');
		this.render_shell();
		this.make_filters();
		this.set_preset('90');
	}

	// ── Shell ─────────────────────────────────────────────────────────────

	render_shell() {
		this.$root = $(`
			<div class="cvd">
				<div class="cvd-head">
					<div>
						<h2 class="cvd-title">${__('Conversion & Tolling')}</h2>
						<p class="cvd-sub">${__('What went in, what came out, and the hardware it used. Submitted Conversion Entries only.')}</p>
					</div>
					<div class="cvd-seg">
						<button data-seg="tolling" class="active">${__('Tolling')}<span class="cvd-count" data-count="tolling"></span></button>
						<button data-seg="conversion">${__('Conversion')}<span class="cvd-count" data-count="conversion"></span></button>
					</div>
				</div>
				<div class="cvd-filters">
					<div class="cvd-f"><label>${__('Period')}</label>
						<div class="cvd-presets">
							<button data-p="30">30d</button><button data-p="90">90d</button>
							<button data-p="ytd">${__('YTD')}</button><button data-p="all">${__('All')}</button>
						</div>
					</div>
					<div class="cvd-f"><label>${__('From')}</label><input type="date" class="form-control" data-f="from"></div>
					<div class="cvd-f"><label>${__('To')}</label><input type="date" class="form-control" data-f="to"></div>
					<div class="cvd-f"><label>${__('Company')}</label><select class="form-control" data-f="company"><option value="">${__('All companies')}</option></select></div>
					<div class="cvd-f" style="min-width:200px"><label>${__('Customer')}</label><div data-f="customer"></div></div>
				</div>
				<div class="cvd-body"></div>
			</div>`).appendTo(this.page.main);

		this.$body = this.$root.find('.cvd-body');
		this.$root.find('.cvd-seg button').on('click', (e) => {
			this.segment = $(e.currentTarget).data('seg');
			this.$root.find('.cvd-seg button').removeClass('active');
			$(e.currentTarget).addClass('active');
			this.render();
		});
	}

	make_filters() {
		const $f = this.$root.find('.cvd-filters');
		$f.find('[data-p]').on('click', (e) => this.set_preset(String($(e.currentTarget).data('p'))));
		$f.find('[data-f=from], [data-f=to]').on('change', () => {
			$f.find('[data-p]').removeClass('active');
			this.load();
		});
		$f.find('[data-f=company]').on('change', () => this.load());

		this.customer = frappe.ui.form.make_control({
			parent: $f.find('[data-f=customer]'),
			df: {
				fieldtype: 'Link', options: 'Customer', fieldname: 'customer',
				placeholder: __('All customers'),
				change: () => {
					const v = this.customer.get_value() || '';
					if (v !== this._last_customer) { this._last_customer = v; this.load(); }
				},
			},
			render_input: true,
		});
		this._last_customer = '';

		frappe.call(`${CVD_API}.get_filter_options`).then((r) => {
			const $sel = $f.find('[data-f=company]');
			((r.message || {}).companies || []).sort().forEach((c) => {
				$sel.append(`<option value="${frappe.utils.escape_html(c)}">${frappe.utils.escape_html(c)}</option>`);
			});
		});
	}

	set_preset(p) {
		const today = frappe.datetime.get_today();
		const from = {
			'30': frappe.datetime.add_days(today, -30),
			'90': frappe.datetime.add_days(today, -90),
			ytd: today.slice(0, 4) + '-01-01',
			all: '',
		}[p];
		const $f = this.$root.find('.cvd-filters');
		$f.find('[data-p]').removeClass('active');
		$f.find(`[data-p="${p}"]`).addClass('active');
		$f.find('[data-f=from]').val(from);
		$f.find('[data-f=to]').val(p === 'all' ? '' : today);
		this.load();
	}

	load() {
		const $f = this.$root.find('.cvd-filters');
		this.$body.addClass('cvd-loading');
		frappe.call({
			method: `${CVD_API}.get_data`,
			args: {
				from_date: $f.find('[data-f=from]').val() || null,
				to_date: $f.find('[data-f=to]').val() || null,
				company: $f.find('[data-f=company]').val() || null,
				customer: (this.customer && this.customer.get_value()) || null,
			},
		}).then((r) => {
			this.data = r.message;
			['tolling', 'conversion'].forEach((k) => {
				this.$root.find(`[data-count=${k}]`).text(` ${this.data[k].kpis.entries}`);
			});
			this.render();
		}).always(() => this.$body.removeClass('cvd-loading'));
	}

	// ── Render ────────────────────────────────────────────────────────────

	render() {
		if (!this.data) return;
		const s = this.data[this.segment];
		const tolling = this.segment === 'tolling';
		const has_yield = s.yields.length > 0;

		this.$body.html(`
			${this.kpis_html(s)}
			${has_yield ? this.yield_strip_html(s.yield_totals, tolling) : ''}
			<div class="cvd-grid">
				<div class="cvd-card cvd-wide">
					<div class="cvd-card-head"><h4 class="cvd-card-title">${__('Weekly volume')}</h4>
						<span class="cvd-card-note">${__('Material in vs product out, kg')}</span></div>
					<div data-chart="trend"></div>
				</div>
			</div>
			<div class="cvd-grid">
				${this.card(__('What we put in'), __('Material by item group, excluding hardware'), this.bars_html(s.inputs_by_group, 'var(--cvd-in)'))}
				${this.card(__('What came out'), __('Finished goods by item group'), this.bars_html(s.outputs_by_group, 'var(--cvd-out)'))}
			</div>
			<div class="cvd-grid">
				${this.card(__('Hardware converted'), __('{0} units across {1} item(s)', [this.fmt_n(s.kpis.hardware_units), s.hardware.length]), this.hardware_html(s.hardware))}
				${this.card(__('Hardware went into'), __('Finished goods made on the same rows'), this.hardware_into_html(s.hardware_into))}
			</div>
			${has_yield ? `<div class="cvd-grid">${this.card(__('Yields by entry'), __('Fresh Frozen → Hash → Rosin, as on the floor sheet'), this.yields_table_html(s.yields), true)}</div>` : ''}
			<div class="cvd-grid">
				${this.card(__('Top inputs'), '', this.items_table_html(s.top_inputs))}
				${this.card(__('Top outputs'), '', this.items_table_html(s.top_outputs))}
			</div>
			<div class="cvd-grid">
				${this.card(tolling ? __('By tolling customer') : __('By customer'), '', this.customers_html(s.by_customer))}
				${this.card(__('Recent entries'), __('Latest 50'), this.recent_html(s.recent))}
			</div>
		`);
		this.draw_trend(s.trend);
	}

	card(title, note, body, wide) {
		return `<div class="cvd-card${wide ? ' cvd-wide' : ''}">
			<div class="cvd-card-head"><h4 class="cvd-card-title">${title}</h4>
				${note ? `<span class="cvd-card-note">${note}</span>` : ''}</div>
			${body}</div>`;
	}

	kpis_html(s) {
		const k = s.kpis;
		const kpi = (label, value, note, color) => `
			<div class="cvd-kpi" style="${color ? `--cvd-kpi:${color}` : ''}">
				<div class="cvd-kpi-label">${label}</div>
				<div class="cvd-kpi-value">${value}</div>
				${note ? `<div class="cvd-kpi-note">${note}</div>` : ''}
			</div>`;
		return `<div class="cvd-kpis">
			${kpi(__('Entries'), this.fmt_n(k.entries), __('{0} customer(s)', [k.customers]))}
			${kpi(__('Material in'), this.fmt_w(k.input_g), __('excl. hardware'), 'var(--cvd-in)')}
			${kpi(__('Product out'), this.fmt_w(k.output_g), k.units_out ? __('+ {0} units', [this.fmt_n(k.units_out)]) : '', 'var(--cvd-out)')}
			${kpi(__('Weight yield'), k.yield_pct == null ? '—' : `${k.yield_pct.toFixed(1)}%`, __('out ÷ in, by weight'))}
			${kpi(__('Hardware used'), this.fmt_n(k.hardware_units), __('units'), 'var(--cvd-hw)')}
		</div>`;
	}

	yield_strip_html(t, tolling) {
		const pct = (v) => (v == null ? '—' : `${v.toFixed(2)}%`);
		const tiers = [
			['Tier 1', t.tier_1, 'var(--cvd-t1)'],
			['Tier 2', t.tier_2, 'var(--cvd-t2)'],
			['Tier 3', t.tier_3, 'var(--cvd-t3)'],
		];
		const total = tiers.reduce((a, x) => a + x[1], 0);
		return `<div class="cvd-grid"><div class="cvd-card cvd-wide">
			<div class="cvd-card-head"><h4 class="cvd-card-title">${tolling ? __('Tolling yields') : __('Yields')}</h4>
				<span class="cvd-card-note">${__('Frozen {0} · Hash {1} · Rosin {2}', [this.fmt_w(t.frozen_g), this.fmt_w(t.hash_g), this.fmt_w(t.rosin_g)])}</span></div>
			<div class="cvd-yield">
				<div class="cvd-ratio"><div class="cvd-ratio-v">${pct(t.frozen_to_hash)}</div><div class="cvd-ratio-l">${__('FF to Hash')}</div></div>
				<div class="cvd-ratio"><div class="cvd-ratio-v">${pct(t.frozen_to_rosin)}</div><div class="cvd-ratio-l">${__('FF to Rosin')}</div></div>
				<div class="cvd-ratio"><div class="cvd-ratio-v">${pct(t.hash_to_rosin)}</div><div class="cvd-ratio-l">${__('Hash to Rosin')}</div></div>
				<div>
					<div class="cvd-card-note">${__('Rosin by tier')} · ${this.fmt_w(total)}</div>
					<div class="cvd-tiers-bar">${total ? tiers.map(([, g, c]) => `<span style="width:${(g / total) * 100}%;background:${c}"></span>`).join('') : ''}</div>
					<div class="cvd-tiers-legend">${tiers.map(([n, g, c]) =>
						`<span><span class="cvd-dot" style="background:${c}"></span>${n} <b>${this.fmt_w(g)}</b>${total ? ` <span class="text-muted">${((g / total) * 100).toFixed(0)}%</span>` : ''}</span>`).join('')}</div>
				</div>
			</div>
		</div></div>`;
	}

	bars_html(groups, color) {
		if (!groups.length) return `<div class="cvd-empty">${__('Nothing in this period.')}</div>`;
		const weighted = groups.filter((g) => g.grams);
		const counted = groups.filter((g) => !g.grams && g.units);
		const row = (name, val, max, label, c) => `
			<div class="cvd-bar-row">
				<div class="cvd-bar-name" title="${frappe.utils.escape_html(name)}">${frappe.utils.escape_html(name)}</div>
				<div class="cvd-bar-track"><div class="cvd-bar-fill" style="width:${max ? Math.max(2, (val / max) * 100) : 0}%;background:${c}"></div></div>
				<div class="cvd-bar-val">${label}</div>
			</div>`;
		const wmax = Math.max(...weighted.map((g) => g.grams), 0);
		const umax = Math.max(...counted.map((g) => g.units), 0);
		return `<div class="cvd-bars">
			${weighted.slice(0, 12).map((g) => row(g.group, g.grams, wmax, this.fmt_w(g.grams), color)).join('')}
			${counted.length ? `<div class="cvd-card-note" style="margin-top:6px">${__('Counted in units')}</div>` : ''}
			${counted.slice(0, 8).map((g) => row(g.group, g.units, umax, `${this.fmt_n(g.units)} u`, 'var(--cvd-hw)')).join('')}
		</div>`;
	}

	hardware_html(hw) {
		if (!hw.length) return `<div class="cvd-empty">${__('No hardware used in this period.')}</div>`;
		const max = Math.max(...hw.map((h) => h.qty));
		return `<div class="cvd-bars">${hw.map((h) => `
			<div class="cvd-bar-row">
				<div class="cvd-bar-name" title="${frappe.utils.escape_html(h.item_code)}">${this.item_link(h)}</div>
				<div class="cvd-bar-track"><div class="cvd-bar-fill" style="width:${Math.max(2, (h.qty / max) * 100)}%;background:var(--cvd-hw)"></div></div>
				<div class="cvd-bar-val">${this.fmt_n(h.qty)} ${frappe.utils.escape_html(h.uom || '')} · ${h.entries} ${__('runs')}</div>
			</div>`).join('')}</div>`;
	}

	hardware_into_html(rows) {
		if (!rows.length) return `<div class="cvd-empty">${__('No hardware used in this period.')}</div>`;
		return this.table(
			[__('Finished good'), __('Group'), { label: __('Qty'), num: true }],
			rows.map((r) => [this.item_link(r), `<span class="muted">${frappe.utils.escape_html(r.item_group)}</span>`,
				{ v: `${this.fmt_n(r.qty)} ${frappe.utils.escape_html(r.uom || '')}`, num: true }]),
		);
	}

	yields_table_html(rows) {
		const pill = (v, good, mid) => {
			if (v == null) return '<span class="cvd-pill none">—</span>';
			const cls = v >= good ? 'good' : v >= mid ? 'mid' : 'low';
			return `<span class="cvd-pill ${cls}">${v.toFixed(2)}%</span>`;
		};
		const g = (v) => (v ? this.fmt_g(v) : '<span class="cvd-zero">0</span>');
		const sum = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
		return this.table(
			[__('Entry'), __('Date'), __('Customer'),
				{ label: __('Frozen'), num: true }, { label: __('Hash'), num: true }, { label: __('Rosin'), num: true },
				{ label: __('FF to Hash'), num: true }, { label: __('FF to Rosin'), num: true }, { label: __('Hash to Rosin'), num: true },
				{ label: __('Tier 1 (g)'), num: true }, { label: __('Tier 2 (g)'), num: true }, { label: __('Tier 3 (g)'), num: true }],
			rows.map((r) => [
				this.entry_link(r.name), `<span class="muted">${frappe.datetime.str_to_user(r.posting_date)}</span>`,
				frappe.utils.escape_html(r.customer || ''),
				{ v: g(r.frozen_g), num: true }, { v: g(r.hash_g), num: true }, { v: g(r.rosin_g), num: true },
				{ v: pill(r.frozen_to_hash, 5, 3.5), num: true }, { v: pill(r.frozen_to_rosin, 4, 2.5), num: true },
				{ v: pill(r.hash_to_rosin, 72, 60), num: true },
				{ v: g(r.tier_1), num: true }, { v: g(r.tier_2), num: true }, { v: g(r.tier_3), num: true },
			]),
			[__('Total'), '', '', this.fmt_g(sum('frozen_g')), this.fmt_g(sum('hash_g')), this.fmt_g(sum('rosin_g')),
				'', '', '', this.fmt_g(sum('tier_1')), this.fmt_g(sum('tier_2')), this.fmt_g(sum('tier_3'))],
		);
	}

	items_table_html(rows) {
		if (!rows.length) return `<div class="cvd-empty">${__('Nothing in this period.')}</div>`;
		return this.table(
			[__('Item'), __('Group'), { label: __('Qty'), num: true }, { label: __('Runs'), num: true }],
			rows.map((r) => [this.item_link(r), `<span class="muted">${frappe.utils.escape_html(r.item_group)}</span>`,
				{ v: r.grams ? this.fmt_w(r.grams) : `${this.fmt_n(r.qty)} ${frappe.utils.escape_html(r.uom || '')}`, num: true },
				{ v: r.entries, num: true }]),
		);
	}

	customers_html(rows) {
		if (!rows.length) return `<div class="cvd-empty">${__('Nothing in this period.')}</div>`;
		return this.table(
			[__('Customer'), { label: __('Entries'), num: true }, { label: __('In'), num: true },
				{ label: __('Out'), num: true }, { label: __('Hardware'), num: true }],
			rows.map((r) => [
				r.customer === '(No customer)' ? `<span class="muted">${__('No customer')}</span>`
					: `<a href="/app/customer/${encodeURIComponent(r.customer)}">${frappe.utils.escape_html(r.customer)}</a>`,
				{ v: r.entries, num: true }, { v: this.fmt_w(r.input_g), num: true },
				{ v: this.fmt_w(r.output_g), num: true }, { v: r.hardware_units ? this.fmt_n(r.hardware_units) : '—', num: true },
			]),
		);
	}

	recent_html(rows) {
		if (!rows.length) return `<div class="cvd-empty">${__('Nothing in this period.')}</div>`;
		return this.table(
			[__('Entry'), __('Date'), __('Customer'), { label: __('In'), num: true }, { label: __('Out'), num: true }, { label: __('HW'), num: true }],
			rows.map((r) => [this.entry_link(r.name), `<span class="muted">${frappe.datetime.str_to_user(r.posting_date)}</span>`,
				frappe.utils.escape_html(r.customer || ''), { v: this.fmt_w(r.input_g), num: true },
				{ v: this.fmt_w(r.output_g), num: true }, { v: r.hardware_units ? this.fmt_n(r.hardware_units) : '—', num: true }]),
		);
	}

	table(cols, rows, foot) {
		const th = cols.map((c) => (typeof c === 'string' ? `<th>${c}</th>` : `<th class="${c.num ? 'num' : ''}">${c.label}</th>`)).join('');
		const td = (c) => (c && typeof c === 'object' ? `<td class="${c.num ? 'num' : ''}">${c.v}</td>` : `<td>${c == null ? '' : c}</td>`);
		const ft = foot ? `<tfoot><tr>${foot.map((c, i) => `<td class="${cols[i] && cols[i].num ? 'num' : ''}">${c}</td>`).join('')}</tr></tfoot>` : '';
		return `<div class="cvd-table-wrap"><table class="cvd-table">
			<thead><tr>${th}</tr></thead>
			<tbody>${rows.map((r) => `<tr>${r.map(td).join('')}</tr>`).join('')}</tbody>${ft}
		</table></div>`;
	}

	draw_trend(trend) {
		const el = this.$body.find('[data-chart=trend]')[0];
		if (!el) return;
		if (!trend.length) { $(el).html(`<div class="cvd-empty">${__('Nothing in this period.')}</div>`); return; }
		const kg = (v) => Math.round(v / 10) / 100;
		this.charts.trend = new frappe.Chart(el, {
			type: 'bar',
			height: 240,
			colors: ['#7b2fbf', '#14a37f'],
			barOptions: { spaceRatio: 0.35 },
			axisOptions: { xIsSeries: 1, shortenYAxisNumbers: 1 },
			tooltipOptions: { formatTooltipY: (v) => `${format_number(v, null, 2)} kg` },
			data: {
				labels: trend.map((t) => frappe.datetime.str_to_user(t.week)),
				datasets: [
					{ name: __('In (kg)'), values: trend.map((t) => kg(t.input_g)) },
					{ name: __('Out (kg)'), values: trend.map((t) => kg(t.output_g)) },
				],
			},
		});
	}

	// ── Formatting ────────────────────────────────────────────────────────

	fmt_n(v) { return format_number(v || 0, null, Number.isInteger(v) ? 0 : 1); }
	fmt_g(v) { return format_number(v || 0, null, 0); }
	fmt_w(g) {
		g = g || 0;
		return Math.abs(g) >= 1000 ? `${format_number(g / 1000, null, 1)} kg` : `${format_number(g, null, 0)} g`;
	}
	entry_link(name) {
		return `<a href="/app/conversion-entry/${encodeURIComponent(name)}">${frappe.utils.escape_html(name)}</a>`;
	}
	item_link(r) {
		return `<a href="/app/item/${encodeURIComponent(r.item_code)}" title="${frappe.utils.escape_html(r.item_code)}">${frappe.utils.escape_html(r.item_name || r.item_code)}</a>`;
	}
}
