// CFO Dashboard — eight analysis sections, stacked on one page, from the "Financial Dashboard – ERPNext
// v15 Functional Mapping" spec. All numbers come from
// cannabis_management.api.cfo_dashboard.get_dashboard in one call; this file
// only renders. Waterfalls are drawn as inline SVG (Frappe Charts has none).

frappe.pages["cfo-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("CFO Dashboard"), single_column: true });
	new CFODashboard(page, wrapper);
};

const CFO_API = "cannabis_management.api.cfo_dashboard.";
// Same order and titles as the eight pages of the reference dashboard
const CFO_SECTIONS = [
	["executive", __("Executive Summary for CFO")],
	["ytd", __("YTD Performance Review")],
	["variance", __("Variance and Driver Analysis")],
	["income_statement", __("Income Statement Analysis (MTD, YTD, FY)")],
	["balance_sheet", __("Detailed Balance Sheet Analysis")],
	["roe", __("Return on Equity Analysis")],
	["cash_flow", __("Detailed Cash Flow Statement Analysis")],
	["liquidity", __("Detailed Liquidity Analysis")],
];
const CFO_STATUS = {
	on_track: __("On Track"),
	watch: __("Watchlist"),
	attention: __("Attention"),
	info: "",
	na: __("n/a"),
};

class CFODashboard {
	constructor(page, wrapper) {
		this.page = page;
		this.metric = "revenue";
		this.dimension = "Project";
		this.$root = $('<div class="cfo-dash"></div>').appendTo(page.main);
		this.make_filters();
		this.init();
	}

	make_filters() {
		const reload = () => this.refresh();
		this.company = this.page.add_field({
			fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
			description: __("Blank = all companies"), change: reload,
		});
		// Same switch as ERPNext's financial statements: either a whole
		// Fiscal Year or a free From/To Date range - only one set is shown
		this.filter_based_on = this.page.add_field({
			fieldname: "filter_based_on", label: __("Filter Based On"), fieldtype: "Select",
			options: [{ value: "Fiscal Year", label: __("Fiscal Year") }, { value: "Date Range", label: __("Date Range") }],
			default: "Fiscal Year",
			change: () => this.apply_filter_based_on(),
		});
		this.fiscal_year = this.page.add_field({
			fieldname: "fiscal_year", label: __("Fiscal Year"), fieldtype: "Link", options: "Fiscal Year",
			change: () => this.apply_fiscal_year(),
		});
		this.from_date = this.page.add_field({
			fieldname: "from_date", label: __("From Date"), fieldtype: "Date", change: reload,
		});
		this.to_date = this.page.add_field({
			fieldname: "to_date", label: __("To Date"), fieldtype: "Date", change: reload,
		});
		this.cost_center = this.page.add_field({
			fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center",
			get_query: () => (this.company.get_value() ? { filters: { company: this.company.get_value() } } : {}),
			change: reload,
		});
		this.project = this.page.add_field({
			fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project", change: reload,
		});
		this.page.set_secondary_action(__("Refresh"), reload, "refresh");
		this.page.add_inner_button(__("Excel"), () => this.export_excel(), __("Export"));
		this.page.add_inner_button(__("PDF / Print"), () => this.export_pdf(), __("Export"));
	}

	async init() {
		const r = await frappe.call(CFO_API + "get_filter_defaults");
		await this.set_filters_quietly(r.message);
		this.toggle_period_fields();
		this.refresh();
	}

	by_date_range() {
		return this.filter_based_on.get_value() === "Date Range";
	}

	toggle_period_fields() {
		const range = this.by_date_range();
		this.fiscal_year.$wrapper.toggle(!range);
		this.from_date.$wrapper.toggle(range);
		this.to_date.$wrapper.toggle(range);
	}

	// Switching to Date Range starts from the chosen year's dates, so the
	// numbers on screen don't jump; switching back re-applies the year
	async apply_filter_based_on() {
		this.toggle_period_fields();
		if (this.by_date_range()) {
			if (!this.from_date.get_value() || !this.to_date.get_value()) await this.fill_dates_from_year();
			this.refresh();
		} else {
			this.apply_fiscal_year();
		}
	}

	async fill_dates_from_year() {
		if (!this.fiscal_year.get_value()) return;
		const r = await frappe.call(CFO_API + "get_fiscal_year_dates", { fiscal_year: this.fiscal_year.get_value() });
		await this.set_filters_quietly(r.message);
	}

	async set_filters_quietly(values) {
		this.silent = true;
		for (const key of ["fiscal_year", "from_date", "to_date"]) {
			if (values[key] !== undefined) await this[key].set_value(values[key]);
		}
		this.silent = false;
	}

	// Fiscal Year mode: the year's start to today (or its end, once over)
	async apply_fiscal_year() {
		if (this.silent || !this.fiscal_year.get_value() || this.by_date_range()) return;
		await this.fill_dates_from_year();
		this.refresh();
	}

	args() {
		// In Fiscal Year mode the server derives the dates from the year itself
		const range = this.by_date_range();
		return {
			company: this.company.get_value() || null,
			filter_based_on: this.filter_based_on.get_value(),
			fiscal_year: range ? null : this.fiscal_year.get_value(),
			from_date: range ? this.from_date.get_value() : null,
			to_date: range ? this.to_date.get_value() : null,
			cost_center: this.cost_center.get_value() || null,
			project: this.project.get_value() || null,
			dimension: this.dimension,
			metric: this.metric,
		};
	}

	async refresh() {
		if (this.silent) return;
		if (this.by_date_range() ? !this.from_date.get_value() || !this.to_date.get_value() : !this.fiscal_year.get_value()) return;
		if (this.by_date_range() && this.from_date.get_value() > this.to_date.get_value()) {
			frappe.msgprint(__("From Date cannot be after To Date"));
			return;
		}
		// Keep the reader's place when a filter re-renders the whole page
		this.scroll = window.scrollY;
		if (!this.data) this.$root.html(`<div class="cfo-loading">${__("Loading…")}</div>`);
		const r = await frappe.call({ method: CFO_API + "get_dashboard", args: this.args() });
		this.data = r.message;
		this.render();
	}

	export_excel() {
		const args = this.args();
		Object.keys(args).forEach((k) => args[k] === null && delete args[k]);
		window.open("/api/method/" + CFO_API + "export_dashboard?" + new URLSearchParams(args).toString());
	}

	export_pdf() {
		// Print stylesheet hides the desk chrome; "Save as PDF" in the dialog gives the file
		if (!this.data) return;
		const title = document.title;
		document.title = `CFO Dashboard ${this.data.meta.from_date} to ${this.data.meta.to_date}`;
		window.print();
		document.title = title;
	}

	// ------------------------------------------------------------------ layout

	render() {
		const m = this.data.meta;
		const scope = m.companies.length === 1 ? m.companies[0] : __("All Companies ({0})", [m.companies.length]);
		this.$root.html(`
			<div class="cfo-header">
				<div>
					<div class="cfo-title">${__("CFO Insights")} · ${frappe.utils.escape_html(scope)}</div>
					<div class="cfo-sub">${__("Period")}: ${m.period_label} · ${__("PY")}: ${m.py_label} · ${m.filter_based_on === "Date Range" ? __("Date Range") : __("FY") + " " + m.fiscal_year} · ${__("Currency")}: ${m.currency || __("mixed — companies use different currencies")}
						${m.cost_center ? " · " + __("Cost Center") + ": " + frappe.utils.escape_html(m.cost_center) : ""}
						${m.project ? " · " + __("Project") + ": " + frappe.utils.escape_html(m.project) : ""}
						${m.has_budget ? "" : " · " + __("No Budget records — budget columns empty")}</div>
				</div>
				<div class="cfo-legend">${["on_track", "watch", "attention"].map((s) => this.badge(s)).join("")}</div>
			</div>
			<div class="cfo-jump">${CFO_SECTIONS.map(([k, l], i) => `<a data-jump="${k}">${i + 1}. ${l}</a>`).join("")}</div>
			${CFO_SECTIONS.map(([k, l], i) => `<section class="cfo-section-block" data-section="${k}">
				<div class="cfo-section-title"><span class="cfo-section-no">${i + 1}</span>${l}</div>
				<div class="cfo-body"></div></section>`).join("")}`);
		CFO_SECTIONS.forEach(([k]) => {
			this["render_" + k](this.$root.find(`[data-section="${k}"] .cfo-body`), this.data[k]);
		});
		this.$root.find("[data-jump]").on("click", (e) => {
			const el = this.$root.find(`[data-section="${$(e.currentTarget).data("jump")}"]`)[0];
			if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
		});
		if (this.scroll) window.scrollTo(0, this.scroll);
	}

	// --------------------------------------------------------------- formatting

	// Every money figure carries the companies' currency symbol (from the server)
	symbol() {
		return (this.data && this.data.meta.currency_symbol) || "";
	}

	short(v) {
		if (v === null || v === undefined) return "—";
		const a = Math.abs(v);
		const s = (v < 0 ? "-" : "") + this.symbol();
		if (a >= 1e9) return s + (a / 1e9).toFixed(2) + "B";
		if (a >= 1e6) return s + (a / 1e6).toFixed(2) + "M";
		if (a >= 1e3) return s + (a / 1e3).toFixed(2) + "K";
		return s + a.toFixed(0);
	}

	full(v) {
		if (v === null || v === undefined) return "—";
		const s = this.symbol() + Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
		return v < 0 ? `(${s})` : s;
	}

	value(v, kind) {
		if (v === null || v === undefined) return "—";
		if (kind === "ratio") return v.toFixed(2) + "x";
		if (kind === "percent") return v.toFixed(2) + "%";
		return this.short(v);
	}

	badge(status) {
		if (!status || !CFO_STATUS[status]) return "";
		return `<span class="cfo-badge cfo-${status}"><span class="cfo-dot"></span>${CFO_STATUS[status]}</span>`;
	}

	kpi(k) {
		const cmp = (k.compare || [])
			.map((c) => `<span>${c.label}: ${this.value(c.value, c.kind || k.kind)}</span>`)
			.join("");
		return `<div class="cfo-card">
			<div class="cfo-card-label">${k.label}</div>
			<div class="cfo-card-value">${this.value(k.value, k.kind)}</div>
			<div class="cfo-card-foot">${this.badge(k.status)}${cmp}</div>
		</div>`;
	}

	notes(list, title) {
		return `<div class="cfo-panel cfo-notes"><div class="cfo-panel-title">${title || __("CFO – Executive Summary")}</div>
			<ul>${list.map((n) => `<li>${frappe.utils.escape_html(n)}</li>`).join("")}</ul></div>`;
	}

	panel(title, inner, cls) {
		return `<div class="cfo-panel ${cls || ""}"><div class="cfo-panel-title">${title}</div>${inner}</div>`;
	}

	// ----------------------------------------------------------------- charts

	waterfall(bars, opts) {
		opts = opts || {};
		const fmt = opts.fmt || ((v) => this.short(v));
		const W = Math.max(520, bars.length * 78), H = 260, top = 24, bottom = 58, left = 8;
		let run = 0;
		const segs = bars.map((b) => {
			let y0, y1;
			if (b.total) {
				y0 = 0; y1 = b.value; run = b.value;
			} else {
				y0 = run; y1 = run + b.value; run = y1;
			}
			return Object.assign({}, b, { y0, y1 });
		});
		const vals = segs.flatMap((s) => [s.y0, s.y1, 0]);
		const max = Math.max(...vals), min = Math.min(...vals);
		const span = max - min || 1;
		const y = (v) => top + ((max - v) / span) * (H - top - bottom);
		const slot = (W - left * 2) / segs.length;
		const bw = Math.min(46, slot * 0.6);
		let svg = `<line x1="0" x2="${W}" y1="${y(0)}" y2="${y(0)}" class="cfo-axis"/>`;
		segs.forEach((s, i) => {
			const x = left + i * slot + (slot - bw) / 2;
			const yt = y(Math.max(s.y0, s.y1)), yb = y(Math.min(s.y0, s.y1));
			const cls = s.total ? "cfo-wf-total" : s.value >= 0 ? "cfo-wf-up" : "cfo-wf-down";
			svg += `<rect x="${x}" y="${yt}" width="${bw}" height="${Math.max(1, yb - yt)}" class="${cls}" rx="2"><title>${frappe.utils.escape_html(s.label)}: ${fmt(s.value)}</title></rect>`;
			svg += `<text x="${x + bw / 2}" y="${yt - 5}" class="cfo-wf-val">${fmt(s.value)}</text>`;
			if (i < segs.length - 1) {
				const nx = left + (i + 1) * slot + (slot - bw) / 2;
				svg += `<line x1="${x + bw}" x2="${nx}" y1="${y(s.y1)}" y2="${y(s.y1)}" class="cfo-wf-link"/>`;
			}
			const label = s.label.length > 16 ? s.label.slice(0, 15) + "…" : s.label;
			svg += `<text x="${x + bw / 2}" y="${H - bottom + 16}" class="cfo-wf-lbl" transform="rotate(-25 ${x + bw / 2} ${H - bottom + 16})">${frappe.utils.escape_html(label)}</text>`;
		});
		return `<div class="cfo-wf"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${svg}</svg></div>`;
	}

	chart(el, cfg) {
		// Frappe Charts needs the element in the DOM with a width
		setTimeout(() => new frappe.Chart(el, Object.assign({ height: 220, animate: false, truncateLegends: true }, cfg)), 0);
	}

	// --------------------------------------------------------------- sections

	render_executive($b, d) {
		const block = (title, kpis, bars) =>
			`<div class="cfo-panel"><div class="cfo-panel-title">${title}</div>
				<div class="cfo-cards cfo-cards-4">${kpis.map((k) => this.kpi(k)).join("")}</div>
				${this.waterfall(bars)}</div>`;
		$b.html(`<div class="cfo-grid-3">
			${block(__("Income Statement (Period)"), d.income_kpis, d.income_bridge)}
			${block(__("Balance Sheet"), d.balance_kpis, d.balance_bridge)}
			${block(__("Cash Flow Statement (Period)"), d.cash_kpis, d.cash_bridge)}
		</div>${this.notes(d.notes)}`);
	}

	render_ytd($b, d) {
		$b.html(`<div class="cfo-split">
			<div class="cfo-panel cfo-rail"><div class="cfo-panel-title">${__("CFO Brief")}</div>
				${d.brief.map((x) => `<div class="cfo-brief"><div><b>${x.metric}</b> ${this.badge(x.status)}</div><div class="cfo-muted">${frappe.utils.escape_html(x.text)}</div></div>`).join("")}
			</div>
			<div class="cfo-grid-2">${d.charts.map((c, i) => this.panel(`${c.label} ${__("Comparison")} ${this.badge(c.status)}`, `<div class="cfo-chart" data-i="${i}"></div>`)).join("")}</div>
		</div>`);
		d.charts.forEach((c, i) => {
			const labels = [__("PY"), __("Actual")];
			const values = [c.py, c.actual];
			if (c.budget !== null) { labels.push(__("Budget")); values.push(c.budget); }
			this.chart($b.find(`.cfo-chart[data-i="${i}"]`)[0], {
				type: "bar",
				data: { labels, datasets: [{ name: c.label, values }] },
				colors: [c.status === "attention" ? "#d9534f" : c.status === "watch" ? "#e0a800" : "#2f5fa8"],
				tooltipOptions: { formatTooltipY: (v) => this.short(v) },
			});
		});
	}

	render_variance($b, d) {
		const metrics = { revenue: __("Revenue"), gross_profit: __("Gross Profit"), ebitda: __("EBITDA"), net_profit: __("Net Profit") };
		$b.html(`
			<div class="cfo-toolbar">
				${Object.entries(metrics).map(([k, l]) => `<button class="cfo-pill ${k === d.metric ? "active" : ""}" data-metric="${k}">${l}</button>`).join("")}
				<span class="cfo-spacer"></span>
				<label class="cfo-muted">${__("Group by")}</label>
				<select class="cfo-select">${["Project", "Cost Center"].map((x) => `<option ${x === this.dimension ? "selected" : ""}>${x}</option>`).join("")}</select>
			</div>
			<div class="cfo-cards cfo-cards-4">${d.kpis.map((k) => this.kpi(k)).join("")}</div>
			<div class="cfo-split">
				<div class="cfo-panel cfo-rail"><div class="cfo-panel-title">${__("Drivers by {0}", [d.dimension])}</div>
					${d.rows.length ? d.rows.slice(0, 12).map((r) => `<div class="cfo-brief"><div>${this.badge(r.status)} <b>${frappe.utils.escape_html(r.name)}</b></div>
						<div class="cfo-muted">${d.metric_label} ${this.short(r.cy)} · ${__("vs PY")} ${this.short(r.delta)} (${r.delta_pct === null ? "—" : r.delta_pct.toFixed(1) + "%"})</div></div>`).join("") : `<div class="cfo-muted">${__("No data")}</div>`}
				</div>
				${this.panel(__("{0} Contribution Analysis (PY → CY by {1})", [d.metric_label, d.dimension]), this.waterfall(d.bridge))}
			</div>`);
		$b.find(".cfo-pill").on("click", (e) => { this.metric = $(e.currentTarget).data("metric"); this.refresh(); });
		$b.find(".cfo-select").on("change", (e) => { this.dimension = e.target.value; this.refresh(); });
	}

	render_income_statement($b, d) {
		const subs = [["actual", __("Actual")], ["py", __("PY")], ["vs_py", __("vs PY")], ["budget", __("Budget")], ["vs_budget", __("vs Budget")]];
		const cell = (c, k) => {
			const v = c[k];
			let cls = "";
			if (k === "vs_py" && v) cls = c.vs_py_fav ? "cfo-pos" : "cfo-neg";
			if (k === "vs_budget" && v !== null && v) cls = c.vs_budget_fav ? "cfo-pos" : "cfo-neg";
			return `<td class="num ${cls}">${this.full(v)}</td>`;
		};
		const head1 = d.groups.map((g) => `<th colspan="5" class="cfo-group">${g.label} — ${g.period}</th>`).join("");
		const head2 = d.groups.map(() => subs.map(([, l]) => `<th class="num">${l}</th>`).join("")).join("");
		const body = d.rows.map((r) => `<tr class="${r.bold ? "cfo-bold" : ""}"><td>${r.label}</td>${d.groups.map((g) => subs.map(([k]) => cell(r[g.key], k)).join("")).join("")}</tr>`).join("");
		$b.html(this.panel(
			__("Income Statement Analysis (FTM vs Period vs Full Year)") + ` <button class="btn btn-xs btn-default cfo-open">${__("Open detailed P&L")}</button>`,
			`<div class="cfo-table-wrap"><table class="cfo-table"><thead><tr><th rowspan="2">${__("Particulars")}</th>${head1}</tr><tr>${head2}</tr></thead><tbody>${body}</tbody></table></div>
			<div class="cfo-muted cfo-foot">${__("FTM = To Date's month. Period = From Date to To Date. Full Year = 12 months ending To Date. PY = same dates one year earlier. Green = favourable, red = unfavourable.")}</div>`
		));
		$b.find(".cfo-open").on("click", () => this.open_report("Management Income Statement"));
	}

	render_balance_sheet($b, d) {
		const rows = d.table.map((r) => r.section
			? `<tr class="cfo-section"><td colspan="4">${r.section}</td></tr>`
			: `<tr class="${r.bold ? "cfo-bold" : ""}"><td>${r.label}</td><td class="num">${this.full(r.actual)}</td><td class="num">${this.full(r.opening)}</td><td class="num">${this.full(r.diff)}</td></tr>`).join("");
		$b.html(`<div class="cfo-split">
			<div>${this.notes(d.notes)}<div class="cfo-cards cfo-cards-2">${d.cards.map((k) => this.kpi(k)).join("")}</div></div>
			${this.panel(__("Balance Sheet Analysis (Actual vs Opening {0})", [d.opening_label]) + ` <button class="btn btn-xs btn-default cfo-open">${__("Open Balance Sheet")}</button>`,
				`<div class="cfo-table-wrap"><table class="cfo-table"><thead><tr><th>${__("Particulars")}</th><th class="num">${__("Actual")}</th><th class="num">${__("Opening")}</th><th class="num">${__("Diff")}</th></tr></thead><tbody>${rows}</tbody></table></div>`)}
		</div>${this.panel(__("Balance Sheet Contribution Analysis (Opening → Closing Net Assets)"), this.waterfall(d.bridge))}`);
		$b.find(".cfo-open").on("click", () => this.open_report("Balance Sheet"));
	}

	render_roe($b, d) {
		const ops = ["=", "×", "×"];
		const blocks = d.blocks.map((b, i) => `${i ? `<div class="cfo-op">${ops[i - 1]}</div>` : ""}
			<div class="cfo-card cfo-dupont"><div class="cfo-card-label">${b.label}</div>
				<div class="cfo-card-value">${this.value(b.value, b.kind)}</div>
				<div class="cfo-card-foot">${this.badge(b.status)}<span>${__("PY")}: ${this.value(b.py, b.kind)}</span></div></div>`).join("");
		$b.html(`${this.panel(__("Return on Equity Analysis (DuPont)"), `<div class="cfo-dupont-row">${blocks}</div>`)}
			<div class="cfo-split">${this.notes(d.notes)}
			${this.panel(__("ROE Movement Analysis (percentage points)"), this.waterfall(d.bridge, { fmt: (v) => v.toFixed(2) + "%" }))}</div>`);
	}

	render_cash_flow($b, d) {
		const rows = d.table.map((r) => r.section
			? `<tr class="cfo-section"><td colspan="4">${r.section}</td></tr>`
			: `<tr class="${r.bold ? "cfo-bold" : ""}"><td>${r.label}</td><td class="num">${this.full(r.actual)}</td><td class="num">${this.full(r.py)}</td><td class="num">${this.full(r.diff)}</td></tr>`).join("");
		$b.html(`<div class="cfo-split">
			<div>${this.notes(d.notes)}<div class="cfo-cards cfo-cards-2">${d.cards.map((k) => this.kpi(k)).join("")}</div></div>
			${this.panel(__("Cash Flow Statement (Period, indirect method)") + ` <button class="btn btn-xs btn-default cfo-open">${__("Open Cash Flow")}</button>`,
				`<div class="cfo-table-wrap"><table class="cfo-table"><thead><tr><th>${__("Particulars")}</th><th class="num">${__("Actual")}</th><th class="num">${__("PY")}</th><th class="num">${__("Diff")}</th></tr></thead><tbody>${rows}</tbody></table></div>`)}
		</div>${this.panel(__("Cash Flow Movement"), this.waterfall(d.bridge))}`);
		$b.find(".cfo-open").on("click", () => this.open_report("Cash Flow"));
	}

	render_liquidity($b, d) {
		$b.html(`<div class="cfo-split">${this.notes(d.notes)}
			<div class="cfo-grid-2">
				${this.panel(__("Debt Service Coverage Ratio"), '<div class="cfo-chart" data-c="dscr"></div>')}
				${this.panel(__("OPEX Coverage Ratio"), '<div class="cfo-chart" data-c="opex"></div>')}
				${this.panel(__("Free Cash Flow and Net Debt"), '<div class="cfo-chart" data-c="fcf"></div>')}
				${this.panel(__("Liquidity Position"), '<div class="cfo-chart" data-c="liq"></div>')}
			</div></div>`);
		const zero = (a) => a.map((v) => (v === null ? 0 : v));
		const ratioTip = { formatTooltipY: (v) => (v === null ? "—" : v.toFixed(2) + "x") };
		this.chart($b.find('[data-c="dscr"]')[0], { type: "line", data: { labels: d.labels, datasets: [{ name: "DSCR", values: zero(d.dscr) }] }, colors: ["#2f5fa8"], lineOptions: { dotSize: 4 }, tooltipOptions: ratioTip });
		this.chart($b.find('[data-c="opex"]')[0], { type: "line", data: { labels: d.labels, datasets: [{ name: __("OPEX Coverage"), values: zero(d.opex_coverage) }] }, colors: ["#6f42c1"], lineOptions: { dotSize: 4 }, tooltipOptions: ratioTip });
		const q = d.quarters.map((x) => x.label);
		const money = { formatTooltipY: (v) => this.short(v) };
		this.chart($b.find('[data-c="fcf"]')[0], { type: "bar", data: { labels: q, datasets: [{ name: __("Free Cash Flow"), values: d.quarters.map((x) => x.fcf) }, { name: __("Net Debt"), values: d.quarters.map((x) => x.net_debt) }] }, colors: ["#2f5fa8", "#e8804a"], tooltipOptions: money });
		this.chart($b.find('[data-c="liq"]')[0], { type: "bar", data: { labels: q, datasets: [{ name: __("Available Liquidity"), values: d.quarters.map((x) => x.liquidity) }, { name: __("Total Borrowings"), values: d.quarters.map((x) => x.borrowings) }] }, colors: ["#28a745", "#e8804a"], tooltipOptions: money });
	}

	open_report(name) {
		const filters = {
			company: this.company.get_value() || frappe.defaults.get_user_default("Company"),
			from_date: this.data.meta.from_date,
			to_date: this.data.meta.to_date,
		};
		if (name !== "Management Income Statement") {
			Object.assign(filters, { filter_based_on: "Date Range", period_start_date: filters.from_date, period_end_date: filters.to_date, periodicity: "Monthly" });
		}
		frappe.route_options = filters;
		frappe.set_route("query-report", name);
	}
}
