// Copyright (c) 2026, alltechvirtual.com and contributors
// Unit Economics — live rebuild of "MotleyTerpz UnitEconomics" workbook (v20).
// Blue cells = editable inputs (persisted in the Unit Economics Model single);
// everything else is computed with the same formulas as the spreadsheet.

frappe.pages["unit-economics"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Unit Economics"),
		single_column: true,
	});
	new UnitEconomics(page);
};

const UE_SEED = {
	period: "Oct 2025 – today",
	tsbc: {
		crops: [
			{ name: "Fall", wet: 72000, std_cost: 15, std_price: 45 },
			{ name: "Winter", wet: 10000, std_cost: 15, std_price: 45 },
			{ name: "Spring clones", wet: 6000, std_cost: 15, std_price: 55 },
			{ name: "Autos", wet: 30000, std_cost: 10, std_price: 27 },
			{ name: "Autos — flower-destined wet", wet: 15000, std_cost: 15, std_price: 27 },
		],
		procured_lbs: 25000, procured_cost: 30,
		grow_spend: 1835000, grow_paid_pre: 1080000,
		dry_spend: 50000, conv_lbs: 15000, flower_lbs: 1000, flower_std_price: 250,
		sales: [
			{ name: "Fresh frozen — outside", qty: 52000, uom: "lb", price: 44, cost: "ff" },
			{ name: "Fresh frozen — to Lab (internal)", qty: 20000, uom: "lb", price: 45, cost: "ff", internal: 1 },
			{ name: "Cured flower — outside", qty: 1000, uom: "lb", price: 250, cost: "flower" },
			{ name: "Traded frozen — resold outside", qty: 15000, uom: "lb", price: 55, cost: "traded" },
			{ name: "Traded frozen — to Lab (internal)", qty: 5000, uom: "lb", price: 35, cost: "traded", internal: 1 },
		],
		inv: [
			{ name: "Fresh frozen (lbs) — all wet grown", key: "ff", begin: 12000, waste: 2000, physical: 55800, mkt: 42 },
			{ name: "Cured flower (lbs) — made by conversion", key: "flower", begin: 0, waste: 0, physical: 0, mkt: 250 },
			{ name: "Traded frozen (lbs) — procured", key: "traded", begin: 0, waste: 0, physical: 5000, mkt: 45 },
		],
		overhead: 900000, cash_ground: 650000, ar: 1450000, ap: 720000, deposits: 250000,
		oct1: { cash_ground: 1080000, ar: 1420000, ap: 400000, deposits: 0 },
		fin: { loans_in: 0, repaid: 0, draws: 200000 },
	},
	lab: {
		outside_lbs: 2000, outside_paid: 90000,
		wash_spend: 420000, press_spend: 0, kitchen_spend: 20000,
		hash_g: 430000, rosin_g: 325000,
		fg: [
			{ name: "Gummies", units: 240000, extract_g: 0.13, hardware: 0, direct: 0.042 },
			{ name: "Vapes / carts", units: 30000, extract_g: 0.5, hardware: 4.0, direct: 0.3 },
		],
		sales: [
			{ name: "Bulk hash", qty: 0, uom: "g", price: 5.5, cost: "hash" },
			{ name: "Bulk live rosin", qty: 210000, uom: "g", price: 8, cost: "rosin" },
			{ name: "Gummies (bulk, unpackaged)", qty: 5000, uom: "unit", price: 0.35, cost: "fg0" },
			{ name: "Vapes / carts", qty: 20000, uom: "unit", price: 14, cost: "fg1" },
			{ name: "White label", qty: 0, uom: "unit", price: 4.2, cost: 3.05, service: 1 },
			{ name: "Tolling", qty: 8000, uom: "lb", price: 44, cost: 20, service: 1 },
			{ name: "Co-pack", qty: 20000, uom: "unit", price: 1.35, cost: 0.8, service: 1 },
			{ name: "Brand services", qty: 9, uom: "month", price: 25000, cost: 5000, service: 1 },
		],
		inv: [
			{ name: "Bulk live rosin (g)", key: "rosin", begin: 50000, waste: 0, physical: 118500, mkt: 8 },
			{ name: "Gummies (units)", key: "fg0", begin: 40000, waste: 0, physical: 274800, mkt: 0.35 },
			{ name: "Vapes / carts (units)", key: "fg1", begin: 10000, waste: 0, physical: 19950, mkt: 14 },
		],
		overhead: 1350000, hardware: 310000, ar: 1600000, ap: 380000,
		oct1: { hardware: 180000, ar: 700000, ap: 250000 },
		fin: { loans_in: 400000, repaid: 150000, draws: 0 },
	},
	cpg: {
		period: "Launch — TBD",
		sales: [],
		overhead: 120000, ar: 0, ap: 0,
		oct1: { ar: 0, ap: 0 },
		fin: { loans_in: 0, repaid: 0, draws: 0 },
	},
	consol: { booked: 5790000, bank_change: 160000, fixed_assets: 850000 },
};

class UnitEconomics {
	constructor(page) {
		this.page = page;
		this.state = null;
		this.tab = "consol";
		this.$body = $('<div class="ue-root"></div>').appendTo(page.body);
		this.inject_css();

		page.set_primary_action(__("Save"), () => this.save(), "small-file");
		page.add_inner_button(__("ERP Snapshot"), () => this.show_snapshot());
		page.add_menu_item(__("Reset to v20 seed"), () => {
			frappe.confirm(__("Discard all edits and reload the v20 workbook numbers?"), () => {
				this.state = JSON.parse(JSON.stringify(UE_SEED));
				this.render();
			});
		});
		this.load();
	}

	load() {
		frappe.call({
			method: "cannabis_management.company_records.page.unit_economics.unit_economics.get_model",
			callback: (r) => {
				this.state = r.message || JSON.parse(JSON.stringify(UE_SEED));
				this.render();
			},
		});
	}

	save() {
		frappe.call({
			method: "cannabis_management.company_records.page.unit_economics.unit_economics.save_model",
			args: { inputs: this.state },
			callback: () => frappe.show_alert({ message: __("Model saved"), indicator: "green" }),
		});
	}

	// ───────────────────────────── model ─────────────────────────────
	compute() {
		const s = this.state;
		const t = this.compute_tsbc(s.tsbc);
		const l = this.compute_lab(s.lab, t);
		const g = this.compute_cpg(s.cpg);
		const c = this.compute_consol(s.consol, t, l, g);
		return { t, l, g, c };
	}

	compute_tsbc(x) {
		const wet = x.crops.reduce((a, r) => a + flt(r.wet), 0);
		const std_grow = x.crops.reduce((a, r) => a + flt(r.wet) * flt(r.std_cost), 0);
		const ff_potential = x.crops.reduce((a, r) => a + flt(r.wet) * flt(r.std_price), 0);
		const ff_cost = wet ? flt(x.grow_spend) / wet : 0;
		const proc_total = flt(x.procured_lbs) * flt(x.procured_cost);
		const conv_ff_cost = flt(x.conv_lbs) * ff_cost;
		const flower_total_cost = conv_ff_cost + flt(x.dry_spend);
		const flower_cost = flt(x.flower_lbs) ? flower_total_cost / flt(x.flower_lbs) : 0;
		const conv_yield = flt(x.conv_lbs) ? flt(x.flower_lbs) / flt(x.conv_lbs) : 0;
		const dest = x.crops.find((r) => /flower-destined/i.test(r.name));
		const conv_as_ff = flt(x.conv_lbs) * flt(dest ? dest.std_price : 0);
		const rev_potential = ff_potential - conv_as_ff + flt(x.flower_lbs) * flt(x.flower_std_price);
		const margin_potential = rev_potential - std_grow - flt(x.dry_spend);

		const unit_cost = (k) => (k === "ff" ? ff_cost : k === "flower" ? flower_cost : k === "traded" ? flt(x.procured_cost) : flt(k));
		const sales = x.sales.map((r) => {
			const cost = unit_cost(r.cost);
			const revenue = flt(r.qty) * flt(r.price);
			const cogs = flt(r.qty) * cost;
			return { ...r, cost_key: r.cost, cost, revenue, cogs, gm: revenue - cogs, gmp: revenue ? (revenue - cogs) / revenue : 0 };
		});
		const tot = (fn) => sales.reduce((a, r) => a + fn(r), 0);
		const revenue = tot((r) => r.revenue), cogs = tot((r) => r.cogs);
		const outside = tot((r) => (r.internal ? 0 : r.revenue));
		const internal = revenue - outside;

		const inv = x.inv.map((r) => {
			const made = r.key === "ff" ? wet : r.key === "flower" ? flt(x.flower_lbs) : flt(x.procured_lbs);
			let consumed = sales.filter((s2) => s2.cost_key === r.key).reduce((a, s2) => a + flt(s2.qty), 0);
			if (r.key === "ff") consumed += flt(x.conv_lbs);
			const cost = unit_cost(r.key);
			const expected = flt(r.begin) + made - consumed - flt(r.waste);
			const unacc = expected - flt(r.physical);
			return { ...r, made, consumed, cost, expected, unacc, at_cost: flt(r.physical) * cost, at_mkt: flt(r.physical) * flt(r.mkt) };
		});
		const inv_cost = inv.reduce((a, r) => a + r.at_cost, 0);
		const inv_mkt = inv.reduce((a, r) => a + r.at_mkt, 0);
		const waste_cost = inv.reduce((a, r) => a + (flt(r.waste) + r.unacc) * r.cost, 0);
		const begin_val = inv.reduce((a, r) => a + flt(r.begin) * r.cost, 0);
		const tie_src = begin_val + flt(x.grow_spend) + proc_total + flt(x.dry_spend);
		const tie_use = cogs + waste_cost + inv_cost;

		const gm = revenue - cogs - waste_cost;
		const net = gm - flt(x.overhead);
		const wc_now = inv_cost + flt(x.cash_ground) + flt(x.ar) - flt(x.ap) - flt(x.deposits);
		const wc_start = begin_val + flt(x.oct1.cash_ground) + flt(x.oct1.ar) - flt(x.oct1.ap) - flt(x.oct1.deposits);
		const wc_incr = wc_now - wc_start;
		const cash_off = net - wc_incr;
		const net_cash = cash_off + flt(x.fin.loans_in) - flt(x.fin.repaid) - flt(x.fin.draws);

		return {
			x, wet, std_grow, ff_potential, ff_cost, proc_total, conv_ff_cost, flower_total_cost,
			flower_cost, conv_yield, conv_as_ff, rev_potential, margin_potential, sales, revenue,
			cogs, outside, internal, inv, inv_cost, inv_mkt, waste_cost, begin_val, tie_src, tie_use,
			gm, net, wc_now, wc_start, wc_incr, cash_off, net_cash,
		};
	}

	compute_lab(x, t) {
		const own = t.sales.find((r) => r.internal && r.cost_key === "ff") || { qty: 0, revenue: 0 };
		const traded = t.sales.find((r) => r.internal && r.cost_key === "traded") || { qty: 0, revenue: 0 };
		const lbs_washed = flt(own.qty) + flt(traded.qty) + flt(x.outside_lbs);
		const material = flt(own.revenue) + flt(traded.revenue) + flt(x.outside_paid);
		const wash_total = material + flt(x.wash_spend);
		const hash_cost = flt(x.hash_g) ? wash_total / flt(x.hash_g) : 0;
		const wash_yield = lbs_washed ? flt(x.hash_g) / (lbs_washed * 453.592) : 0;
		const rosin_cost = flt(x.rosin_g) ? (flt(x.hash_g) * hash_cost + flt(x.press_spend)) / flt(x.rosin_g) : 0;
		const press_yield = flt(x.hash_g) ? flt(x.rosin_g) / flt(x.hash_g) : 0;

		const fg = x.fg.map((r) => {
			const extract_cost = flt(r.extract_g) * rosin_cost;
			const unit = extract_cost + flt(r.hardware) + flt(r.direct);
			return { ...r, extract_cost, unit, total: flt(r.units) * unit };
		});
		const extract_consumed = fg.reduce((a, r) => a + flt(r.units) * flt(r.extract_g), 0);
		const kitchen_alloc = fg.reduce((a, r) => a + flt(r.units) * flt(r.direct), 0);

		const unit_cost = (k) => (k === "hash" ? hash_cost : k === "rosin" ? rosin_cost : k === "fg0" ? fg[0].unit : k === "fg1" ? (fg[1] || { unit: 0 }).unit : flt(k));
		const sales = x.sales.map((r) => {
			const cost = unit_cost(r.cost);
			const revenue = flt(r.qty) * flt(r.price);
			const cogs = flt(r.qty) * cost;
			return { ...r, cost_key: r.cost, cost, revenue, cogs, gm: revenue - cogs, gmp: revenue ? (revenue - cogs) / revenue : 0 };
		});
		const revenue = sales.reduce((a, r) => a + r.revenue, 0);
		const cogs = sales.reduce((a, r) => a + r.cogs, 0);
		const product_cogs = sales.filter((r) => !r.service).reduce((a, r) => a + r.cogs, 0);

		const inv = x.inv.map((r) => {
			const made = r.key === "rosin" ? flt(x.rosin_g) - extract_consumed
				: r.key === "fg0" ? flt(fg[0].units) : flt((fg[1] || { units: 0 }).units);
			const consumed = sales.filter((s2) => s2.cost_key === r.key).reduce((a, s2) => a + flt(s2.qty), 0);
			const cost = unit_cost(r.key);
			const expected = flt(r.begin) + made - consumed - flt(r.waste);
			const unacc = expected - flt(r.physical);
			return { ...r, made, consumed, cost, expected, unacc, at_cost: flt(r.physical) * cost, at_mkt: flt(r.physical) * flt(r.mkt) };
		});
		const inv_cost = inv.reduce((a, r) => a + r.at_cost, 0);
		const inv_mkt = inv.reduce((a, r) => a + r.at_mkt, 0);
		const waste_cost = inv.reduce((a, r) => a + (flt(r.waste) + r.unacc) * r.cost, 0);
		const begin_val = inv.reduce((a, r) => a + flt(r.begin) * r.cost, 0);
		const nonextract = fg.reduce((a, r) => a + flt(r.units) * (flt(r.hardware) + flt(r.direct)), 0);
		const tie_src = begin_val + material + flt(x.wash_spend) + flt(x.press_spend) + nonextract;
		const tie_use = product_cogs + waste_cost + inv_cost;

		const gm = revenue - cogs - waste_cost;
		const net = gm - flt(x.overhead);
		const wc_now = inv_cost + flt(x.hardware) + flt(x.ar) - flt(x.ap);
		const wc_start = begin_val + flt(x.oct1.hardware) + flt(x.oct1.ar) - flt(x.oct1.ap);
		const wc_incr = wc_now - wc_start;
		const cash_off = net - wc_incr;
		const net_cash = cash_off + flt(x.fin.loans_in) - flt(x.fin.repaid) - flt(x.fin.draws);

		// potential: everything on hand + made, sold at market, plus service book
		const rev_potential = inv.reduce((a, r) => a + (flt(r.begin) + r.made) * flt(r.mkt), 0)
			+ sales.filter((r) => r.service).reduce((a, r) => a + r.revenue, 0);
		const cost_potential = inv.reduce((a, r) => a + (flt(r.begin) + r.made) * r.cost, 0)
			+ sales.filter((r) => r.service).reduce((a, r) => a + r.cogs, 0);
		const margin_potential = rev_potential - cost_potential;

		return {
			x, own, traded, lbs_washed, material, wash_total, hash_cost, wash_yield, rosin_cost,
			press_yield, fg, extract_consumed, kitchen_alloc, sales, revenue, cogs, product_cogs,
			inv, inv_cost, inv_mkt, waste_cost, begin_val, tie_src, tie_use, gm, net, wc_now,
			wc_start, wc_incr, cash_off, net_cash, rev_potential, margin_potential,
			outside: revenue, internal: 0,
		};
	}

	compute_cpg(x) {
		const sales = (x.sales || []).map((r) => {
			const revenue = flt(r.qty) * flt(r.price);
			const cogs = flt(r.qty) * flt(r.cost);
			return { ...r, revenue, cogs, gm: revenue - cogs, gmp: revenue ? (revenue - cogs) / revenue : 0 };
		});
		const revenue = sales.reduce((a, r) => a + r.revenue, 0);
		const cogs = sales.reduce((a, r) => a + r.cogs, 0);
		const gm = revenue - cogs;
		const net = gm - flt(x.overhead);
		const wc_now = flt(x.ar) - flt(x.ap);
		const wc_start = flt(x.oct1.ar) - flt(x.oct1.ap);
		const wc_incr = wc_now - wc_start;
		const cash_off = net - wc_incr;
		const net_cash = cash_off + flt(x.fin.loans_in) - flt(x.fin.repaid) - flt(x.fin.draws);
		return { x, sales, revenue, cogs, gm, net, wc_now, wc_start, wc_incr, cash_off, net_cash, outside: revenue, internal: 0, inv_cost: 0, inv_mkt: 0 };
	}

	compute_consol(c, t, l, g) {
		const segs = [
			{ name: "TSBC (farm + frozen trading)", s: t },
			{ name: "Lab (extraction, finished goods, services)", s: l },
			{ name: "Retail CPG (launching)", s: g },
		];
		const sum = (fn) => segs.reduce((a, r) => a + fn(r.s), 0);
		const outside = sum((s) => s.outside), internal = sum((s) => s.internal);
		const gm = sum((s) => s.gm), overhead = sum((s) => flt(s.x.overhead)), net = sum((s) => s.net);
		const gap = outside - flt(c.booked);
		const ar = sum((s) => flt(s.x.ar || 0));
		const collected = flt(c.booked) - ar;
		const inv_cost = sum((s) => s.inv_cost || 0), inv_mkt = sum((s) => s.inv_mkt || 0);
		const wc_now = sum((s) => s.wc_now), wc_start = sum((s) => s.wc_start);
		const wc_incr = wc_now - wc_start;
		const cash_off = net - wc_incr;
		const loans = sum((s) => flt(s.x.fin.loans_in)), repaid = sum((s) => flt(s.x.fin.repaid)), draws = sum((s) => flt(s.x.fin.draws));
		const net_cash = cash_off + loans - repaid - draws;
		const diff = net_cash - flt(c.bank_change);
		const rev_pot = t.rev_potential + l.rev_potential;
		const gm_pot = t.margin_potential + l.margin_potential;
		const net_pot = gm_pot - overhead;
		const wc_at_mkt = wc_now - inv_cost + inv_mkt;
		return {
			c, segs, outside, internal, gm, overhead, net, gap, ar, collected, inv_cost, inv_mkt,
			wc_now, wc_start, wc_incr, cash_off, loans, repaid, draws, net_cash, diff,
			rev_pot, gm_pot, net_pot, wc_at_mkt,
			wind_down: wc_now + flt(c.fixed_assets), wind_ceiling: wc_at_mkt + flt(c.fixed_assets),
		};
	}

	// ───────────────────────────── render ─────────────────────────────
	render() {
		const m = this.compute();
		const tabs = [
			["consol", "Consolidated"], ["tsbc", "1 · TSBC"], ["lab", "2 · Lab"], ["cpg", "3 · Retail CPG"],
		];
		this.$body.html(`
			<div class="ue-tabs">${tabs.map(([k, lbl]) =>
				`<span class="ue-tab ${this.tab === k ? "on" : ""}" data-tab="${k}">${lbl}</span>`).join("")}
				<span class="ue-period">Period: ${inp("period", this.state.period, "text")}</span>
			</div>
			<div class="ue-content">${
				this.tab === "consol" ? this.html_consol(m) :
				this.tab === "tsbc" ? this.html_tsbc(m.t) :
				this.tab === "lab" ? this.html_lab(m.l) : this.html_cpg(m.g)
			}</div>
			<div class="ue-foot">Blue cells are inputs — everything else is computed live.
			Lab “potential” lines use on-hand + produced at market (documented deviation from v20’s manual figure).</div>
		`);
		this.$body.find(".ue-tab").on("click", (e) => { this.tab = $(e.currentTarget).data("tab"); this.render(); });
		this.$body.find("input.ue-in").on("change", (e) => {
			const path = $(e.currentTarget).data("path");
			const raw = $(e.currentTarget).val();
			set_path(this.state, String(path), $(e.currentTarget).attr("data-type") === "text" ? raw : flt(raw));
			this.render();
		});
		this.$body.find(".ue-addrow").on("click", () => {
			this.state.cpg.sales.push({ name: "New line", qty: 0, uom: "unit", price: 0, cost: 0 });
			this.render();
		});
	}

	html_consol(m) {
		const c = m.c;
		return `
		${card("SEGMENTS — three engines, one company", table(
			["Segment", "Outside revenue", "Internal revenue", "Gross margin", "Overhead", "Net"],
			c.segs.map((r) => [r.name, money(r.s.outside), money(r.s.internal), money(r.s.gm), money(flt(r.s.x.overhead)), money(r.s.net, 1)])
				.concat([[b("COMPANY"), b(money(c.outside)), b(money(c.internal)), b(money(c.gm)), b(money(c.overhead)), b(money(c.net, 1))]])
		))}
		${card("WHERE'S THE MONEY", kv([
			["Model says invoiced (outside)", money(c.outside)],
			["Booked revenue per the books (QBO)", inp("consol.booked", c.c.booked)],
			[b("GAP — price variance + shrink (the leak line)"), b(money(c.gap, 1))],
			["less AR still uncollected (all segments)", money(c.ar)],
			[b("Cash actually collected"), b(money(c.collected))],
		]))}
		${card("WORKING CAPITAL — cash tied up", kv([
			["Inventory at cost (TSBC + Lab)", money(c.inv_cost)],
			["Hardware & packaging", money(flt(this.state.lab.hardware))],
			["Cash in the ground (next crops)", money(flt(this.state.tsbc.cash_ground))],
			["AR (all segments)", money(c.ar)],
			["less AP (all segments)", money(flt(this.state.tsbc.ap) + flt(this.state.lab.ap) + flt(this.state.cpg.ap))],
			["less customer deposits", money(flt(this.state.tsbc.deposits))],
			[b("NET CASH TIED UP — today"), b(money(c.wc_now))],
			["Cash tied up at period start (Oct 1)", money(c.wc_start)],
			[b("INCREASE in cash tied up this period"), b(money(c.wc_incr, 1))],
		]))}
		${card("CASH BRIDGE — accrual profit → bank account", kv([
			["Net to date (model, accrual)", money(c.net)],
			["less: increase in cash tied up", money(c.wc_incr)],
			[b("CASH THE BUSINESS THREW OFF"), b(money(c.cash_off, 1))],
			["+ Loans received", money(c.loans)],
			["− Loan principal repaid", money(c.repaid)],
			["− Owner draws / distributions", money(c.draws)],
			[b("NET CHANGE IN CASH (model)"), b(money(c.net_cash))],
			["Actual change in bank balances", inp("consol.bank_change", c.c.bank_change)],
			[b("DIFFERENCE — should be small"), b(money(c.diff, 1))],
		]))}
		${card("AT A GLANCE — the whole company", kv([
			["Revenue potential (if all sold)", money(c.rev_pot)],
			["Gross margin potential", money(c.gm_pot)],
			["Net potential", money(c.net_pot)],
			["ACTUAL outside revenue", money(c.outside)],
			["ACTUAL gross margin / %", `${money(c.gm)} <span class="ue-dim">${pct(c.gm / (c.outside + c.internal || 1))}</span>`],
			["ACTUAL net / %", `${money(c.net, 1)} <span class="ue-dim">${pct(c.net / (c.outside + c.internal || 1))}</span>`],
			["Money tied up (inventory at cost)", money(c.wc_now)],
			["Money tied up (inventory at market)", money(c.wc_at_mkt)],
			["Cash thrown off (operations)", money(c.cash_off, 1)],
			["Fixed assets at book", inp("consol.fixed_assets", c.c.fixed_assets)],
			[b("IF WOUND DOWN TODAY (rough floor)"), b(money(c.wind_down))],
			["Ceiling version (inventory at market)", money(c.wind_ceiling)],
		]))}`;
	}

	html_tsbc(t) {
		const x = t.x;
		return `
		${card("1 · COST ENGINE — every pound grown & bought", table(
			["Crop (all grown as FF)", "Lbs (wet)", "Std cost $/lb", "Grow cost (std)", "Std FF price $/lb", "Potential as FF"],
			x.crops.map((r, i) => [
				inp(`tsbc.crops.${i}.name`, r.name, "text"),
				inp(`tsbc.crops.${i}.wet`, r.wet),
				inp(`tsbc.crops.${i}.std_cost`, r.std_cost),
				money(flt(r.wet) * flt(r.std_cost)),
				inp(`tsbc.crops.${i}.std_price`, r.std_price),
				money(flt(r.wet) * flt(r.std_price)),
			]).concat([[b("TOTAL WET LBS / standard"), b(num(t.wet)), "", b(money(t.std_grow)), "", b(money(t.ff_potential))]])
		) + kv([
			["PROCURED — frozen bought (lbs / $ per lb)", inp("tsbc.procured_lbs", x.procured_lbs) + " " + inp("tsbc.procured_cost", x.procured_cost)],
			["ACTUAL total grow spend (books) / actual $ per wet lb", inp("tsbc.grow_spend", x.grow_spend) + ` <span class="ue-dim">${money(t.ff_cost, 2)}/lb</span>`],
			["Variance, actual vs standard", money(flt(x.grow_spend) - t.std_grow, 1)],
			["of which paid before Oct 1 / paid during period", inp("tsbc.grow_paid_pre", x.grow_paid_pre) + ` <span class="ue-dim">${money(flt(x.grow_spend) - flt(x.grow_paid_pre))}</span>`],
			["Dry, buck & trim spend", inp("tsbc.dry_spend", x.dry_spend)],
			["CONVERSION — FF lbs in / finished flower lbs out", inp("tsbc.conv_lbs", x.conv_lbs) + " → " + inp("tsbc.flower_lbs", x.flower_lbs) + ` <span class="ue-dim">yield ${pct(t.conv_yield)}, cost ${money(t.flower_cost, 2)}/lb</span>`],
			["Flower std price per finished lb", inp("tsbc.flower_std_price", x.flower_std_price)],
			[b("TOTAL REVENUE POTENTIAL / MARGIN POTENTIAL"), b(`${money(t.rev_potential)} / ${money(t.margin_potential)}`)],
		]))}
		${card("2a · SALES — every line that moved", table(
			["Sale line", "Sold", "UoM", "Price", "Revenue", "Cost/unit", "COGS", "Gross margin", "GM %"],
			t.sales.map((r, i) => [
				r.name + (r.internal ? ' <span class="ue-badge">internal</span>' : ""),
				inp(`tsbc.sales.${i}.qty`, r.qty), r.uom,
				inp(`tsbc.sales.${i}.price`, r.price),
				money(r.revenue), money(r.cost, 2), money(r.cogs), money(r.gm, 1), pct(r.gmp),
			]).concat([[b("TOTAL"), "", "", "", b(money(t.revenue)), "", b(money(t.cogs)), b(money(t.gm + t.waste_cost, 1)), b(pct((t.revenue - t.cogs) / (t.revenue || 1)))]])
		))}
		${card("2b · INVENTORY & POUNDS TIE — the shrink meter", table(
			["Item", "Begin", "+Made/bought", "−Sold/consumed", "−Waste", "Expected", "Physical", "Unaccounted", "Cost/u", "INV @ COST", "@ Market"],
			t.inv.map((r, i) => [
				r.name, inp(`tsbc.inv.${i}.begin`, r.begin), num(r.made), num(r.consumed),
				inp(`tsbc.inv.${i}.waste`, r.waste), num(r.expected),
				inp(`tsbc.inv.${i}.physical`, r.physical),
				flag(num(r.unacc), r.unacc !== 0), money(r.cost, 2), money(r.at_cost), money(r.at_mkt),
			]).concat([[b("TOTALS"), "", "", "", "", "", "", "", "", b(money(t.inv_cost)), b(money(t.inv_mkt))]])
		) + kv([
			["Waste & unaccounted at cost", money(t.waste_cost, 1)],
			["Beginning inventory value (Oct 1)", money(t.begin_val)],
			["TIE-OUT — sources / uses", `${money(t.tie_src)} / ${money(t.tie_use)}`],
			[b("DIFFERENCE — must be $0"), b(flag(money(t.tie_src - t.tie_use), Math.abs(t.tie_src - t.tie_use) > 1))],
		]))}
		${this.html_money("tsbc", t, [
			["FF + flower + traded inventory at cost", money(t.inv_cost)],
			["Cash in the ground (next crops)", inp("tsbc.cash_ground", x.cash_ground)],
			["AR — outside customers owe TSBC", inp("tsbc.ar", x.ar)],
			["less AP — TSBC owes growers/vendors", inp("tsbc.ap", x.ap)],
			["less customer deposits (pre-sold)", inp("tsbc.deposits", x.deposits)],
		], [
			["Oct 1 — cash in the ground", inp("tsbc.oct1.cash_ground", x.oct1.cash_ground)],
			["Oct 1 — AR outstanding", inp("tsbc.oct1.ar", x.oct1.ar)],
			["Oct 1 — less AP outstanding", inp("tsbc.oct1.ap", x.oct1.ap)],
			["Oct 1 — less customer deposits", inp("tsbc.oct1.deposits", x.oct1.deposits)],
		])}`;
	}

	html_lab(l) {
		const x = l.x;
		return `
		${card("1 · COST ENGINE — wash → press → kitchen", kv([
			["From TSBC — own FF (lbs / $ — from TSBC internal lines)", `${num(l.own.qty)} / ${money(l.own.revenue)}`],
			["From TSBC — traded (lbs / $)", `${num(l.traded.qty)} / ${money(l.traded.revenue)}`],
			["Direct from outside sellers (lbs / paid)", inp("lab.outside_lbs", x.outside_lbs) + " " + inp("lab.outside_paid", x.outside_paid)],
			[b("TOTAL LBS WASHED / MATERIAL $"), b(`${num(l.lbs_washed)} / ${money(l.material)}`)],
			["Wash operating spend", inp("lab.wash_spend", x.wash_spend)],
			["Hash produced (g) / wash yield / cost per g", inp("lab.hash_g", x.hash_g) + ` <span class="ue-dim">${pct(l.wash_yield, 2)} · ${money(l.hash_cost, 2)}/g</span>`],
			["Press operating spend", inp("lab.press_spend", x.press_spend)],
			["Rosin produced (g) / press yield / cost per g", inp("lab.rosin_g", x.rosin_g) + ` <span class="ue-dim">${pct(l.press_yield)} · ${money(l.rosin_cost, 2)}/g</span>`],
			["Kitchen & packaging spend / absorbed via direct $", inp("lab.kitchen_spend", x.kitchen_spend) + ` <span class="ue-dim">${money(l.kitchen_alloc)} absorbed</span>`],
		]) + table(
			["Finished good", "Units", "Extract g/u", "Extract $/u", "Hardware $/u", "Direct $/u", "COST/UNIT", "TOTAL COST"],
			l.fg.map((r, i) => [
				inp(`lab.fg.${i}.name`, r.name, "text"),
				inp(`lab.fg.${i}.units`, r.units),
				inp(`lab.fg.${i}.extract_g`, r.extract_g),
				money(r.extract_cost, 3),
				inp(`lab.fg.${i}.hardware`, r.hardware),
				inp(`lab.fg.${i}.direct`, r.direct),
				money(r.unit, 3), money(r.total),
			]).concat([[b("Extract consumed by finished goods (g)"), b(num(l.extract_consumed)), "", "", "", "", "", ""]])
		))}
		${card("2a · SALES — products and services", table(
			["Sale line", "Sold", "UoM", "Price", "Revenue", "Cost/unit", "COGS", "Gross margin", "GM %"],
			l.sales.map((r, i) => [
				r.name + (r.service ? ' <span class="ue-badge">service</span>' : ""),
				inp(`lab.sales.${i}.qty`, r.qty), r.uom,
				inp(`lab.sales.${i}.price`, r.price),
				money(r.revenue),
				typeof r.cost === "number" && typeof x.sales[i].cost === "number"
					? inp(`lab.sales.${i}.cost`, x.sales[i].cost) : money(r.cost, 2),
				money(r.cogs), money(r.gm, 1), pct(r.gmp),
			]).concat([[b("TOTAL"), "", "", "", b(money(l.revenue)), "", b(money(l.cogs)), b(money(l.revenue - l.cogs, 1)), b(pct((l.revenue - l.cogs) / (l.revenue || 1)))]])
		))}
		${card("2b · INVENTORY & UNITS TIE — the shrink meter", table(
			["Item", "Begin", "+Made", "−Sold/consumed", "−Waste", "Expected", "Physical", "Unaccounted", "Cost/u", "INV @ COST", "@ Market"],
			l.inv.map((r, i) => [
				r.name, inp(`lab.inv.${i}.begin`, r.begin), num(r.made), num(r.consumed),
				inp(`lab.inv.${i}.waste`, r.waste), num(r.expected),
				inp(`lab.inv.${i}.physical`, r.physical),
				flag(num(r.unacc), r.unacc !== 0), money(r.cost, 2), money(r.at_cost), money(r.at_mkt),
			]).concat([[b("TOTALS"), "", "", "", "", "", "", "", "", b(money(l.inv_cost)), b(money(l.inv_mkt))]])
		) + kv([
			["Waste & unaccounted at cost — live shrink meter", money(l.waste_cost, 1)],
			["Beginning inventory value (Oct 1)", money(l.begin_val)],
			["TIE-OUT — sources / uses (products only)", `${money(l.tie_src)} / ${money(l.tie_use)}`],
			[b("DIFFERENCE — must be $0"), b(flag(money(l.tie_src - l.tie_use), Math.abs(l.tie_src - l.tie_use) > 1))],
		]))}
		${this.html_money("lab", l, [
			["Product inventory at cost", money(l.inv_cost)],
			["Hardware & packaging on hand", inp("lab.hardware", x.hardware)],
			["AR — outside customers owe the Lab", inp("lab.ar", x.ar)],
			["less AP — Lab owes vendors/farms", inp("lab.ap", x.ap)],
		], [
			["Oct 1 — hardware & packaging", inp("lab.oct1.hardware", x.oct1.hardware)],
			["Oct 1 — AR outstanding", inp("lab.oct1.ar", x.oct1.ar)],
			["Oct 1 — less AP outstanding", inp("lab.oct1.ap", x.oct1.ap)],
		])}`;
	}

	html_cpg(g) {
		const x = g.x;
		return `
		${card("2a · SALES — branded goods (buys finished units from the Lab)", table(
			["Sale line", "Sold", "UoM", "Door price", "Revenue", "Transfer cost/u", "COGS", "GM", "GM %"],
			g.sales.map((r, i) => [
				inp(`cpg.sales.${i}.name`, r.name, "text"),
				inp(`cpg.sales.${i}.qty`, r.qty),
				inp(`cpg.sales.${i}.uom`, r.uom, "text"),
				inp(`cpg.sales.${i}.price`, r.price),
				money(r.revenue),
				inp(`cpg.sales.${i}.cost`, x.sales[i].cost),
				money(r.cogs), money(r.gm, 1), pct(r.gmp),
			]).concat([[b("TOTAL"), "", "", "", b(money(g.revenue)), "", b(money(g.cogs)), b(money(g.gm, 1)), ""]])
		) + `<button class="btn btn-xs btn-default ue-addrow">${__("Add sale line")}</button>`)}
		${this.html_money("cpg", g, [
			["AR — dispensaries owe CPG", inp("cpg.ar", x.ar)],
			["less AP — CPG owes vendors", inp("cpg.ap", x.ap)],
		], [
			["Oct 1 — AR outstanding", inp("cpg.oct1.ar", x.oct1.ar)],
			["Oct 1 — less AP outstanding", inp("cpg.oct1.ap", x.oct1.ap)],
		])}`;
	}

	html_money(key, s, wc_rows, oct1_rows) {
		const x = s.x;
		return card("3 · MONEY — sold basis · working capital · cash", kv([
			["Revenue (outside + internal)", money(s.revenue)],
			["COGS (sold units × actual cost)", money(s.cogs)],
			["less waste & unaccounted at cost", money(s.waste_cost || 0, 1)],
			[b("GROSS MARGIN / GM %"), b(`${money(s.gm)} <span class="ue-dim">${pct(s.gm / (s.revenue || 1))}</span>`)],
			["Segment overhead", inp(`${key}.overhead`, x.overhead)],
			[b("SEGMENT NET / net %"), b(`${money(s.net, 1)} <span class="ue-dim">${pct(s.net / (s.revenue || 1))}</span>`)],
		]) + `<div class="ue-sub">WORKING CAPITAL</div>` + kv(
			wc_rows.concat([[b("NET CASH TIED UP"), b(money(s.wc_now))]])
		) + kv(
			oct1_rows.concat([
				[b("CASH TIED UP AT PERIOD START"), b(money(s.wc_start))],
				[b("Increase in cash tied up this period"), b(money(s.wc_incr, 1))],
			])
		) + `<div class="ue-sub">CASH</div>` + kv([
			[b("CASH THE SEGMENT THREW OFF (net − increase tied up)"), b(money(s.cash_off, 1))],
			["+ Loans received", inp(`${key}.fin.loans_in`, x.fin.loans_in)],
			["− Loan principal repaid", inp(`${key}.fin.repaid`, x.fin.repaid)],
			["− Owner draws / distributions", inp(`${key}.fin.draws`, x.fin.draws)],
			[b("NET CHANGE IN SEGMENT CASH"), b(money(s.net_cash, 1))],
		]));
	}

	show_snapshot() {
		frappe.call({
			method: "cannabis_management.company_records.page.unit_economics.unit_economics.erp_snapshot",
			callback: (r) => {
				const s = r.message;
				const rows = Object.entries(s.companies).map(([company, v]) =>
					`<tr><td>${company}</td><td class="ue-num">${money(v.booked_revenue)}</td>
					<td class="ue-num">${money(v.ar_outstanding)}</td><td class="ue-num">${money(v.ap_outstanding)}</td>
					<td class="ue-num">${money(v.inventory_value)}</td><td class="ue-num">${money(v.customer_deposits)}</td></tr>`).join("");
				const t = s.totals;
				frappe.msgprint({
					title: __("ERP Snapshot — since {0}", [s.from_date]),
					wide: true,
					message: `<div class="ue-root"><table class="ue-table"><thead><tr>
						<th>Company</th><th>Booked revenue</th><th>AR outstanding</th>
						<th>AP outstanding</th><th>Inventory value</th><th>Customer deposits</th></tr></thead>
						<tbody>${rows}<tr><td><b>TOTAL</b></td><td class="ue-num"><b>${money(t.booked_revenue)}</b></td>
						<td class="ue-num"><b>${money(t.ar_outstanding)}</b></td><td class="ue-num"><b>${money(t.ap_outstanding)}</b></td>
						<td class="ue-num"><b>${money(t.inventory_value)}</b></td><td class="ue-num"><b>${money(t.customer_deposits)}</b></td></tr>
						</tbody></table>
						<p class="ue-dim" style="margin-top:8px">${__("Live from ERPNext — compare against the model's blue cells (booked revenue, AR, AP, inventory at cost, deposits) and update them.")}</p></div>`,
				});
			},
		});
	}

	inject_css() {
		if (document.getElementById("ue-style")) return;
		const css = `
		.ue-root{font-family:var(--mt-f-sans,'Archivo',sans-serif);max-width:1360px;margin:0 auto;padding-bottom:60px}
		.ue-tabs{display:flex;gap:6px;align-items:center;margin:6px 0 16px;flex-wrap:wrap}
		.ue-tab{padding:7px 16px;border:1px solid var(--mt-line-strong,#d8cceb);border-radius:9px;cursor:pointer;
			font-size:12px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--mt-ink-soft,#7a6f8a);background:var(--fg-color,#fff)}
		.ue-tab.on{background:#4d129e;border-color:#4d129e;color:#fff}
		.ue-period{margin-left:auto;font-size:12px;color:var(--mt-ink-soft,#7a6f8a)}
		.ue-card{background:var(--fg-color,#fff);border:1px solid var(--mt-line-strong,#d8cceb);border-radius:14px;margin-bottom:18px;overflow:hidden}
		.ue-card-h{padding:11px 16px;font-size:11.5px;font-weight:800;letter-spacing:1.4px;text-transform:uppercase;
			color:#4d129e;border-bottom:2px solid var(--mt-line,#eae2f4);background:var(--mt-orchid-bar,#f8f1fd)}
		.ue-card-b{padding:8px 16px 14px;overflow-x:auto}
		.ue-table{width:100%;border-collapse:collapse;font-size:12.5px;margin:6px 0}
		.ue-table th{font-size:9.5px;letter-spacing:1px;text-transform:uppercase;color:#7a5b9c;font-weight:700;
			text-align:right;padding:7px 8px;border-bottom:2px solid var(--mt-line-strong,#d8cceb);background:var(--mt-orchid-soft,#f3e6fb)}
		.ue-table th:first-child{text-align:left}
		.ue-table td{padding:6px 8px;border-bottom:1px solid var(--mt-line,#eae2f4);text-align:right;
			font-family:var(--mt-f-num,'JetBrains Mono',monospace);font-variant-numeric:tabular-nums;white-space:nowrap}
		.ue-table td:first-child{text-align:left;font-family:var(--mt-f-sans,'Archivo',sans-serif)}
		.ue-kv{width:100%;border-collapse:collapse;font-size:12.5px;margin:4px 0}
		.ue-kv td{padding:5px 8px;border-bottom:1px solid var(--mt-line,#eae2f4)}
		.ue-kv td:last-child{text-align:right;font-family:var(--mt-f-num,'JetBrains Mono',monospace);font-variant-numeric:tabular-nums;white-space:nowrap}
		.ue-in{width:96px;padding:3px 7px;border:1px solid #b9d4f7;background:#eef6ff;border-radius:6px;
			font-family:var(--mt-f-num,'JetBrains Mono',monospace);font-size:12px;text-align:right;color:#0b3f7e}
		.ue-in[data-type=text]{text-align:left;width:170px;background:#eef6ff}
		.ue-in:focus{outline:2px solid #4d129e;border-color:#4d129e}
		.ue-num{text-align:right;font-family:var(--mt-f-num,'JetBrains Mono',monospace)}
		.ue-neg{color:#c62b45;font-weight:700}.ue-pos{color:#1c8a5e}
		.ue-badge{font-size:8.5px;font-weight:800;letter-spacing:.8px;text-transform:uppercase;border:1px solid #c464e4;
			color:#8b2fc9;border-radius:4px;padding:1px 5px;margin-left:5px}
		.ue-flag{color:#c62b45;font-weight:800}
		.ue-sub{font-size:10px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:#7a5b9c;margin:14px 0 2px}
		.ue-dim{color:var(--mt-ink-soft,#8a7f9a);font-size:11px}
		.ue-foot{font-size:11px;color:var(--mt-ink-soft,#8a7f9a);margin-top:6px}`;
		$("<style id='ue-style'>").text(css).appendTo("head");
	}
}

// ── tiny render/format helpers (page-scope globals) ──
function flt(v) { return parseFloat(v) || 0; }
function money(v, prec) {
	v = flt(v);
	const d = prec !== undefined ? prec : Math.abs(v) < 10 && v !== 0 ? 3 : Math.abs(v) % 1 > 0.001 ? 2 : 0;
	const s = "$" + (v < 0 ? "−" : "") + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: d });
	return v < 0 ? `<span class="ue-neg">${s}</span>` : s;
}
function num(v) { return flt(v).toLocaleString("en-US", { maximumFractionDigits: 2 }); }
function pct(v, d) { return (flt(v) * 100).toLocaleString("en-US", { maximumFractionDigits: d !== undefined ? d : 1 }) + "%"; }
function b(s) { return `<b>${s}</b>`; }
function flag(s, bad) { return bad ? `<span class="ue-flag">${s} ⚠</span>` : s; }
function inp(path, val, type) {
	return `<input class="ue-in" data-path="${path}" data-type="${type || "number"}" value="${frappe.utils.escape_html(String(val ?? ""))}">`;
}
function card(title, body) { return `<div class="ue-card"><div class="ue-card-h">${title}</div><div class="ue-card-b">${body}</div></div>`; }
function table(head, rows) {
	return `<table class="ue-table"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
	<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
function kv(rows) {
	return `<table class="ue-kv"><tbody>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</tbody></table>`;
}
function set_path(obj, path, value) {
	const parts = path.split(".");
	let ref = obj;
	for (let i = 0; i < parts.length - 1; i++) ref = ref[parts[i]];
	ref[parts[parts.length - 1]] = value;
}
