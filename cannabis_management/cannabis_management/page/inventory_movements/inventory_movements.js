// Inventory Movements: port of the claude.ai "Inventory Movements" dashboard.
// Server (cannabis_management.api.inventory_movements) classifies each stock ledger entry;
// this page builds the monthly tables, the drill-down and the linked SO · SI · DN view.

frappe.pages["inventory-movements"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: "Inventory Movements", single_column: true });
	new InventoryMovements(page);
};

const IM_LABELS = {
	opening: "Opening Balance", purchases: "add Purchases", yield: "add Yield / Receipts", production: "add Production",
	issued: "less Issued to Production", sales: "less Sales", adjust: "± Loss / Adjustments", transfer: "± Transfers (net)",
	closing: "Closing Balance",
};
const IM_ORDER = ["opening", "purchases", "yield", "production", "issued", "sales", "adjust", "transfer", "closing"];
const IM_UOM_LABEL = { LBS: "Pounds (LBS)", Grams: "Grams", Grains: "Grains", Nos: "Units (Nos)" };
const IM_GROUPS = ["LBS", "Grams", "Grains", "Nos"];
const IM_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const im_fmt = (v) => {
	if (v == null || Math.abs(v) < 0.005) return "-";
	const s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	return v < 0 ? "(" + s + ")" : s;
};
const im_month_name = (per) => per === "total" ? "Total" : IM_MONTHS[Number(per.slice(5, 7)) - 1] + " " + per.slice(0, 4);
const im_nice_date = (s) => {
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || ""));
	return m ? m[3] + " " + IM_MONTHS[Number(m[2]) - 1] + " " + m[1] : String(s || "");
};
const im_ymd = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
const im_today = () => im_ymd(new Date());
const im_erp = (doctype, name) => "/app/" + String(doctype).toLowerCase().replace(/\s+/g, "-") + "/" + encodeURIComponent(name);
const im_mk = (tag, cls, text) => {
	const n = document.createElement(tag);
	if (cls) n.className = cls;
	if (text != null) n.textContent = text;
	return n;
};
const im_link = (doctype, name) => {
	const a = im_mk("a", null, name);
	a.href = im_erp(doctype, name); a.target = "_blank"; a.rel = "noopener";
	return a;
};
const im_sum = (arr, f) => arr.reduce((s, x) => s + (Number(f(x)) || 0), 0);

class InventoryMovements {
	constructor(page) {
		this.page = page;
		this.$wrap = $('<div class="im-wrap"></div>').appendTo(page.main);
		this.wrap = this.$wrap[0];
		this.companies = [];
		this.status = "idle";
		this.ledger_all = [];
		this.loaded = null;
		this.names = {};
		this.sel = null;
		this.sales_view = "standard";
		this.linked = {};
		this.req = 0;
		this._render_shell();
		this._init();
	}

	api(method, args) {
		return frappe.xcall("cannabis_management.api.inventory_movements." + method, args);
	}

	async _init() {
		try {
			this.companies = await this.api("get_companies");
		} catch (e) {
			this.companies = [];
		}
		const saved = this._saved_params();
		const year = im_today().slice(0, 4);
		const company = this.companies.includes(saved.company) ? saved.company
			: (this.companies.includes("Master Touch Manufacturing") ? "Master Touch Manufacturing" : this.companies[0]);
		this.p = {
			company,
			from_date: saved.from_date || year + "-01-01",
			to_date: saved.to_date || im_today(),
			opening_docs: saved.opening_docs != null ? saved.opening_docs : "MAT-RECO-2026-00015",
		};
		const sel = this.wrap.querySelector(".im-company");
		sel.replaceChildren(...this.companies.map(c => { const o = im_mk("option", null, c); o.value = c; return o; }));
		this._bind();
		this._load();
	}

	_saved_params() {
		try { return JSON.parse(localStorage.getItem("im_params") || "{}") || {}; } catch (e) { return {}; }
	}

	set_params(patch) {
		const prev = this.p;
		this.p = Object.assign({}, this.p, patch);
		try { localStorage.setItem("im_params", JSON.stringify(this.p)); } catch (e) { }
		const needs_fetch = !this.loaded || this.p.company !== this.loaded.company || this.p.to_date > this.loaded.to_date;
		if (needs_fetch) this._load();
		else if (prev.opening_docs !== this.p.opening_docs || prev.to_date !== this.p.to_date || prev.from_date !== this.p.from_date) {
			this._recompute();
			this.draw_all();
		}
	}

	async _load() {
		const req = ++this.req;
		this.status = "loading";
		this.wrap.classList.add("im-refreshing");
		this.draw_all();
		try {
			const r = await this.api("get_ledger", { company: this.p.company, to_date: this.p.to_date });
			if (req !== this.req) return;
			const cols = r.columns;
			this.ledger_all = r.rows.map(row => { const o = {}; cols.forEach((c, i) => { o[c] = row[i]; }); return o; });
			this.names = r.item_names || {};
			this.loaded = { company: this.p.company, to_date: r.to_date };
			this.linked = {};
			this.status = "ok";
		} catch (e) {
			if (req !== this.req) return;
			this.status = "error";
			this.error = e && (e.message || e);
		}
		this.wrap.classList.remove("im-refreshing");
		this._recompute();
		this.draw_all();
	}

	// Ledger lines of the current view: up to To date, with the "counted in opening" flag.
	_recompute() {
		if (this.status !== "ok") { this.ledger = null; this.movement = null; return; }
		const op_docs = new Set(String(this.p.opening_docs || "").split(/[\s,;]+/).map(s => s.trim().toUpperCase()).filter(Boolean));
		const to = String(this.p.to_date);
		this.ledger = this.ledger_all.filter(l => l.date <= to).map(l => Object.assign({}, l, { op: op_docs.has(String(l.voucher_no).toUpperCase()) }));
		this.movement = this._movement(this.ledger);
	}

	_period() {
		let from = String(this.p.from_date || ""), to = String(this.p.to_date || "");
		if (from > to) { const x = from; from = to; to = x; }
		return [from, to];
	}

	_movement(ledger) {
		const [from, to] = this._period();
		const months = [];
		let y = Number(from.slice(0, 4)), m = Number(from.slice(5, 7));
		const ey = Number(to.slice(0, 4)), em = Number(to.slice(5, 7));
		while ((y < ey || (y === ey && m <= em)) && months.length < 60) { months.push(y + "-" + String(m).padStart(2, "0")); m++; if (m > 12) { m = 1; y++; } }
		const cats = ["purchases", "yield", "production", "issued", "sales", "adjust", "transfer"];
		const sign = { issued: -1, sales: -1 };
		const acc = {}, open = {};
		for (const g of IM_GROUPS) {
			open[g] = { q: 0, v: 0 }; acc[g] = {};
			for (const c of cats) { acc[g][c] = { total: { q: 0, v: 0 } }; for (const mo of months) acc[g][c][mo] = { q: 0, v: 0 }; }
		}
		for (const l of ledger) {
			if (!acc[l.uom]) continue;
			if (l.date < from || l.op) { open[l.uom].q += l.qty; open[l.uom].v += l.value; continue; }
			if (l.date > to) continue;
			const mo = l.date.slice(0, 7);
			const cell = acc[l.uom][l.cat];
			if (cell[mo]) { cell[mo].q += l.qty; cell[mo].v += l.value; }
			cell.total.q += l.qty; cell.total.v += l.value;
		}
		const r2 = (x) => { const v = Math.round(x * 100) / 100; return Object.is(v, -0) ? 0 : v; };
		const out = [];
		for (const g of IM_GROUPS) {
			let oq = open[g].q, ov = open[g].v;
			for (const per of months.concat(["total"])) {
				const startQ = per === "total" ? open[g].q : oq;
				const startV = per === "total" ? open[g].v : ov;
				let nq = 0, nv = 0;
				out.push({ key: g + "|opening|" + per, uom: g, movement: "opening", period: per, qty: r2(startQ), value: r2(startV) });
				for (const c of cats) {
					const s = acc[g][c][per];
					nq += s.q; nv += s.v;
					const k = sign[c] || 1;
					out.push({ key: g + "|" + c + "|" + per, uom: g, movement: c, period: per, qty: r2(k * s.q), value: r2(k * s.v) });
				}
				out.push({ key: g + "|closing|" + per, uom: g, movement: "closing", period: per, qty: r2(startQ + nq), value: r2(startV + nv) });
				if (per !== "total") { oq = startQ + nq; ov = startV + nv; }
			}
		}
		return out;
	}

	_window(per) {
		const [from, to] = this._period();
		if (per === "total") return [from, to];
		const y = Number(per.slice(0, 4)), m = Number(per.slice(5, 7));
		const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
		const s = per + "-01", e = per + "-" + String(last).padStart(2, "0");
		return [s < from ? from : s, e > to ? to : e];
	}

	// ---------- Shell ----------
	_render_shell() {
		const unit = (g, id) => `
			<div class="im-uom" data-uom="${g}">
				<h2 class="im-uom-h">${IM_UOM_LABEL[g]}</h2>
				<div class="im-pair">
					<div id="${id}-qty"><div class="im-band im-band-q">QUANTITIES</div><div class="im-scroll" data-draw="mtable" data-uom="${g}" data-kind="qty"></div></div>
					<div id="${id}-val"><div class="im-band im-band-v">VALUES</div><div class="im-scroll" data-draw="mtable" data-uom="${g}" data-kind="value"></div></div>
				</div>
			</div>`;
		this.$wrap.html(`
			<h1 class="im-title">Inventory Movements – <span data-draw="cohead">—</span></h1>
			<p class="im-sub" data-draw="takeaway">—</p>
			<div class="im-filters">
				<label class="im-field">Company
					<select class="im-company" aria-label="Company"></select>
				</label>
				<label class="im-field">From date
					<input type="date" class="im-from" min="2020-01-01" max="2030-12-31">
				</label>
				<label class="im-field">To date
					<input type="date" class="im-to" min="2020-01-01" max="2030-12-31">
				</label>
				<button class="im-btn im-ytd" type="button">This year to date</button>
				<button class="im-btn im-last6" type="button">Last 6 months</button>
			</div>
			<div class="im-tabs" role="tablist">
				<button class="im-tab" type="button" role="tab" data-tab="report" aria-selected="true">Inventory report</button>
				<button class="im-tab" type="button" role="tab" data-tab="drill" aria-selected="false">Drill-down history</button>
			</div>
			<section class="im-sec" data-sec="report">
				<div class="im-status" data-draw="status">—</div>
				<p class="im-note">Click any number to open the documents behind it in the Drill-down history tab.</p>
				${unit("LBS", "lbs")}${unit("Grams", "grams")}${unit("Grains", "grains")}${unit("Nos", "nos")}
				<details class="im-note">
					<summary>How each row is worked out</summary>
					<p>Every row comes from submitted Stock Ledger Entries of the selected company. Opening Balance is everything posted before the period starts. Purchases are Purchase Receipts and Purchase Invoices. Yield / Receipts are Stock Entries of type Material Receipt. Production is the output side of Manufacture, Repack, Conversion and Disassemble entries (and Subcontracting Receipts). Issued to Production is the input side of those entries plus Material Issue and Material Consumption for Manufacture. Sales are Delivery Notes, Sales Invoices and POS Invoices (returns reduce the figure). Loss / Adjustments are Stock Reconciliations and anything else. Transfers between warehouses of the same company net to zero and only show if they don't. Values are the stock value change recorded on each ledger entry. “Less” rows are shown as positive amounts that are subtracted; negatives are in brackets.</p>
					<p data-draw="otheruom">—</p>
					<label class="im-field" style="max-width:520px">Counted in the opening balance (document numbers, separated by commas)
						<input type="text" class="im-opdocs" placeholder="e.g. MAT-RECO-2026-00015">
					</label>
					<p>Stock from these documents is added to the Opening Balance of every month in the period instead of appearing as a movement in the month it was posted.</p>
				</details>
			</section>
			<section class="im-sec im-drill" data-sec="drill" hidden>
				<div data-draw="drill">—</div>
			</section>`);
	}

	_bind() {
		const w = this.wrap;
		w.querySelectorAll(".im-tab").forEach(b => b.addEventListener("click", () => this.show_tab(b.getAttribute("data-tab"))));
		const company = w.querySelector(".im-company");
		company.addEventListener("change", () => this.set_params({ company: company.value }));
		const date = (cls, name) => {
			const el = w.querySelector(cls);
			el.addEventListener("change", () => { if (el.value && el.validity.valid) this.set_params({ [name]: el.value }); });
			el.addEventListener("blur", () => { el.value = this.p[name] || ""; });
		};
		date(".im-from", "from_date");
		date(".im-to", "to_date");
		const op = w.querySelector(".im-opdocs");
		op.addEventListener("change", () => this.set_params({ opening_docs: op.value.trim() }));
		op.addEventListener("keydown", (ev) => { if (ev.key === "Enter") op.blur(); });
		w.querySelector(".im-ytd").addEventListener("click", () => { const t = im_today(); this.set_params({ from_date: t.slice(0, 4) + "-01-01", to_date: t }); });
		w.querySelector(".im-last6").addEventListener("click", () => {
			const d = new Date();
			this.set_params({ from_date: im_ymd(new Date(d.getFullYear(), d.getMonth() - 5, 1)), to_date: im_today() });
		});
	}

	show_tab(name) {
		this.wrap.querySelectorAll(".im-sec").forEach(s => { s.hidden = s.getAttribute("data-sec") !== name; });
		this.wrap.querySelectorAll(".im-tab").forEach(b => b.setAttribute("aria-selected", b.getAttribute("data-tab") === name ? "true" : "false"));
		if (name === "drill") this.draw_drill();
		window.scrollTo({ top: 0 });
	}

	open_drill(sel) {
		this.sel = sel;
		this.show_tab("drill");
	}

	// ---------- Drawing ----------
	draw_all() {
		const w = this.wrap, p = this.p;
		const sync = (cls, v) => { const el = w.querySelector(cls); if (el && document.activeElement !== el) el.value = v || ""; };
		sync(".im-company", p.company); sync(".im-from", p.from_date); sync(".im-to", p.to_date); sync(".im-opdocs", p.opening_docs);
		w.querySelector('[data-draw="cohead"]').textContent = p.company || "—";
		if (this.status === "ok" && this.ledger) {
			const used = new Set(this.ledger.map(l => l.uom));
			w.querySelectorAll(".im-uom[data-uom]").forEach(sec => { sec.hidden = !used.has(sec.getAttribute("data-uom")); });
		} else if (this.status !== "loading") {
			w.querySelectorAll(".im-uom[data-uom]").forEach(sec => { sec.hidden = false; });
		}
		this.draw_status();
		this.draw_takeaway();
		w.querySelectorAll('[data-draw="mtable"]').forEach(el => this.draw_mtable(el));
		this.draw_otheruom();
		if (!w.querySelector('[data-sec="drill"]').hidden) this.draw_drill();
	}

	draw_status() {
		const el = this.wrap.querySelector('[data-draw="status"]');
		if (this.status === "loading") { el.textContent = "Reading the stock ledger for " + this.p.company + " from the ERP… large companies can take a minute."; return; }
		if (this.status === "error") { el.textContent = "The stock ledger failed to load." + (this.error ? " " + this.error : ""); return; }
		if (this.status !== "ok") { el.textContent = "—"; return; }
		el.textContent = this.ledger.length.toLocaleString("en-US") + " ledger entries read up to " + im_nice_date(String(this.p.to_date)) + ".";
	}

	draw_takeaway() {
		const el = this.wrap.querySelector('[data-draw="takeaway"]');
		el.replaceChildren();
		if (!this.movement) { el.textContent = "—"; return; }
		const p = this.p;
		el.append("Closing stock at " + im_nice_date(String(p.to_date > p.from_date ? p.to_date : p.from_date)) + ": ");
		const unit = { LBS: " lbs", Grams: " g", Grains: " gr", Nos: " units" };
		let first = true;
		for (const g of IM_GROUPS) {
			const r = this.movement.find(x => x.key === g + "|closing|total");
			if (!r || (Math.abs(r.qty) < 0.005 && Math.abs(r.value) < 0.005)) continue;
			if (!first) el.append("; ");
			first = false;
			el.append(im_mk("b", "im-num", im_fmt(r.qty)), unit[g] + " worth $", im_mk("b", "im-num", im_fmt(r.value)));
		}
		el.append(first ? "no stock in these units." : ".");
	}

	draw_mtable(el) {
		const uom = el.getAttribute("data-uom"), kind = el.getAttribute("data-kind");
		el.replaceChildren();
		if (!this.movement) {
			el.append(im_mk("div", "im-empty", this.status === "error" ? "Failed to load" : "Loading…"));
			return;
		}
		const rows = this.movement.filter(r => r.uom === uom);
		const periods = Array.from(new Set(rows.map(r => r.period)));
		const by_key = new Map(rows.map(r => [r.key, r]));
		const any = rows.some(r => Math.abs(r.qty) >= 0.005 || Math.abs(r.value) >= 0.005);
		if (!any) { el.append(im_mk("div", "im-empty", "No stock or movements in this unit for the selected company and period.")); return; }
		const show_transfer = rows.some(r => r.movement === "transfer" && (Math.abs(r.qty) >= 0.005 || Math.abs(r.value) >= 0.005));
		const tbl = im_mk("table", "im-tbl");
		const hr = tbl.createTHead().insertRow();
		hr.append(im_mk("th", null, "Movement"));
		for (const per of periods) hr.append(im_mk("th", null, per === "total" ? "Period Total" : im_month_name(per)));
		const tb = tbl.createTBody();
		for (const mv of IM_ORDER) {
			if (mv === "transfer" && !show_transfer) continue;
			const tr = tb.insertRow();
			if (mv === "closing") tr.className = "im-close";
			tr.insertCell().textContent = IM_LABELS[mv];
			for (const per of periods) {
				const r = by_key.get(uom + "|" + mv + "|" + per);
				const td = tr.insertCell();
				td.textContent = im_fmt(r ? r[kind] : 0);
				td.className = "im-c" + (per === "total" ? " im-tot" : "");
				td.tabIndex = 0;
				const go = () => this.open_drill({ uom, movement: mv, period: per, kind });
				td.addEventListener("click", go);
				td.addEventListener("keydown", (ev) => { if (ev.key === "Enter") go(); });
			}
		}
		el.append(tbl);
	}

	draw_otheruom() {
		const el = this.wrap.querySelector('[data-draw="otheruom"]');
		if (!this.ledger) { el.textContent = "—"; return; }
		const other = new Set(this.ledger.filter(l => l.uom === "Other").map(l => l.stock_uom));
		el.textContent = other.size
			? "Items in other units are not shown in the tables above: " + Array.from(other).join(", ") + "."
			: "Every item of this company is stocked in LBS, Grams, Grains or Nos.";
	}

	draw_drill() {
		const el = this.wrap.querySelector('[data-draw="drill"]');
		el.replaceChildren();
		const sel = this.sel;
		if (!sel) { el.append(im_mk("p", "im-empty", "Click any number in the Inventory report tab to see the documents behind it here.")); return; }
		if (this.status !== "ok" || !this.ledger) { el.append(im_mk("p", "im-empty", "Loading…")); return; }
		const names = this.names, p = this.p;
		const [ws, we] = this._window(sel.period);
		const head = im_mk("div", "im-dhead");
		const back = im_mk("button", "im-btn", "← Back to report"); back.type = "button";
		back.addEventListener("click", () => this.show_tab("report"));
		head.append(im_mk("h2", "im-dtitle", IM_LABELS[sel.movement] + " · " + IM_UOM_LABEL[sel.uom] + " · " + (sel.period === "total" ? "whole period" : im_month_name(sel.period))), back);
		el.append(head);
		const is_bal = sel.movement === "opening" || sel.movement === "closing";
		const cutoff = sel.movement === "opening" ? ws : we;
		el.append(im_mk("p", "im-note", p.company + " · " + (is_bal
			? (sel.movement === "opening" ? "stock on hand before " + im_nice_date(ws) : "stock on hand at the end of " + im_nice_date(we))
			: im_nice_date(ws) + " to " + im_nice_date(we))));

		const cards = im_mk("div", "im-cards");
		const card = (k, v) => { const c = im_mk("div", "im-card"); c.append(im_mk("div", "k", k), im_mk("div", "v", v)); cards.append(c); };
		const search = im_mk("input", "im-search"); search.type = "search"; search.placeholder = "Filter by document, item or warehouse"; search.setAttribute("aria-label", "Filter");
		const body = im_mk("div");

		if (is_bal) {
			const lines = this.ledger.filter(l => l.uom === sel.uom && (l.op || (sel.movement === "opening" ? l.date < cutoff : l.date <= cutoff)));
			const by = new Map();
			for (const l of lines) {
				const k = l.item_code + "\u0001" + l.warehouse;
				const o = by.get(k) || { item: l.item_code, wh: l.warehouse, uom: l.stock_uom, q: 0, v: 0, n: 0 };
				o.q += l.qty; o.v += l.value; o.n++; by.set(k, o);
			}
			const list = Array.from(by.values()).filter(o => Math.abs(o.q) >= 0.005 || Math.abs(o.v) >= 0.005).sort((a, b) => b.v - a.v);
			card("Quantity", im_fmt(im_sum(list, o => o.q))); card("Value", "$" + im_fmt(im_sum(list, o => o.v))); card("Item × warehouse lines", list.length.toLocaleString("en-US"));
			el.append(cards, search, body);
			const render = () => {
				body.replaceChildren();
				const f = search.value.trim().toLowerCase();
				const rows = list.filter(o => !f || (o.item + " " + (names[o.item] || "") + " " + o.wh).toLowerCase().includes(f));
				body.append(im_mk("h3", "im-h3", "Balance by item and warehouse (" + rows.length + ")"));
				const wrap = im_mk("div", "im-scroll"); wrap.style.borderTop = "1px solid var(--im-line)";
				const tbl = im_mk("table", "im-tbl im-dtbl");
				const hr = tbl.createTHead().insertRow();
				for (const h of ["Item", "Item name", "Warehouse", "UOM", "Ledger entries", "Quantity", "Value"]) hr.append(im_mk("th", null, h));
				const tb = tbl.createTBody();
				for (const o of rows.slice(0, 2000)) {
					const tr = tb.insertRow();
					tr.insertCell().append(im_link("Item", o.item));
					tr.insertCell().textContent = names[o.item] || "";
					tr.insertCell().textContent = o.wh;
					tr.insertCell().textContent = o.uom;
					const c1 = tr.insertCell(); c1.className = "r"; c1.textContent = o.n;
					const c2 = tr.insertCell(); c2.className = "r"; c2.textContent = im_fmt(o.q);
					const c3 = tr.insertCell(); c3.className = "r"; c3.textContent = im_fmt(o.v);
				}
				wrap.append(tbl); body.append(wrap);
				if (rows.length > 2000) body.append(im_mk("p", "im-note", "Showing the first 2,000 of " + rows.length + " lines; use the filter to narrow."));
			};
			search.addEventListener("input", render); render();
			return;
		}

		const lines = this.ledger.filter(l => l.uom === sel.uom && l.cat === sel.movement && !l.op && l.date >= ws && l.date <= we)
			.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.voucher_no < b.voucher_no ? -1 : 1));
		const docs = new Map();
		for (const l of lines) {
			const o = docs.get(l.voucher_no) || { vt: l.voucher_type, no: l.voucher_no, date: l.date, et: l.entry_type, n: 0, q: 0, v: 0 };
			o.n++; o.q += l.qty; o.v += l.value; docs.set(l.voucher_no, o);
		}
		const doc_list = Array.from(docs.values());
		// "less" rows (Sales, Issued to Production) are shown as positive amounts, the same way the report shows them.
		const sg = (sel.movement === "issued" || sel.movement === "sales") ? -1 : 1;
		card("Documents", doc_list.length.toLocaleString("en-US")); card("Quantity", im_fmt(sg * im_sum(lines, l => l.qty))); card("Value", "$" + im_fmt(sg * im_sum(lines, l => l.value)));
		el.append(cards);
		if (sg < 0) el.append(im_mk("p", "im-note", "Shown as positive amounts going out, matching the report. A return shows in brackets because it reduces the total."));
		if (sel.movement === "sales") {
			const sw = im_mk("div", "im-switch"); sw.setAttribute("role", "tablist");
			for (const [k, label] of [["standard", "Standard view"], ["linked", "Linked documents view (SO · SI · DN)"]]) {
				const bt = im_mk("button", "im-btn" + (this.sales_view === k ? " im-on" : ""), label); bt.type = "button";
				bt.setAttribute("aria-pressed", this.sales_view === k ? "true" : "false");
				bt.addEventListener("click", () => { this.sales_view = k; this.draw_drill(); });
				sw.append(bt);
			}
			el.append(sw);
		}
		el.append(search, body);
		const render = () => {
			body.replaceChildren();
			const f = search.value.trim().toLowerCase();
			const match = (l) => !f || (l.voucher_no + " " + l.voucher_type + " " + l.item_code + " " + (names[l.item_code] || "") + " " + l.warehouse + " " + l.entry_type).toLowerCase().includes(f);
			const fl = lines.filter(match);
			const fd = doc_list.filter(d => !f || fl.some(l => l.voucher_no === d.no));
			if (sel.movement === "sales" && this.sales_view === "linked") {
				this.linked_table(body, fd, fl, sg, doc_list, () => { if (this.sel === sel) render(); });
			} else {
				body.append(im_mk("h3", "im-h3", "Documents (" + fd.length + ")"));
				const w1 = im_mk("div", "im-scroll"); w1.style.borderTop = "1px solid var(--im-line)";
				const t1 = im_mk("table", "im-tbl im-dtbl");
				const h1 = t1.createTHead().insertRow();
				for (const h of ["Date", "Document type", "Document", "Entry type", "Lines", "Quantity", "Value"]) h1.append(im_mk("th", null, h));
				const b1 = t1.createTBody();
				for (const d of fd) {
					const tr = b1.insertRow();
					tr.insertCell().textContent = im_nice_date(d.date);
					tr.insertCell().textContent = d.vt;
					tr.insertCell().append(im_link(d.vt, d.no));
					tr.insertCell().textContent = d.et;
					const c1 = tr.insertCell(); c1.className = "r"; c1.textContent = d.n;
					const c2 = tr.insertCell(); c2.className = "r"; c2.textContent = im_fmt(sg * d.q);
					const c3 = tr.insertCell(); c3.className = "r"; c3.textContent = im_fmt(sg * d.v);
				}
				w1.append(t1); body.append(w1);
				if (!fd.length) body.append(im_mk("p", "im-empty", "No documents."));
			}

			body.append(im_mk("h3", "im-h3", "Line items (" + fl.length + ")"));
			const w2 = im_mk("div", "im-scroll"); w2.style.borderTop = "1px solid var(--im-line)";
			const t2 = im_mk("table", "im-tbl im-dtbl");
			const h2 = t2.createTHead().insertRow();
			for (const h of ["Date", "Document", "Item", "Item name", "Warehouse", "UOM", "Quantity", "Value"]) h2.append(im_mk("th", null, h));
			const b2 = t2.createTBody();
			for (const l of fl.slice(0, 3000)) {
				const tr = b2.insertRow();
				tr.insertCell().textContent = l.date;
				tr.insertCell().append(im_link(l.voucher_type, l.voucher_no));
				tr.insertCell().append(im_link("Item", l.item_code));
				tr.insertCell().textContent = names[l.item_code] || "";
				tr.insertCell().textContent = l.warehouse;
				tr.insertCell().textContent = l.stock_uom;
				const c2 = tr.insertCell(); c2.className = "r"; c2.textContent = im_fmt(sg * l.qty);
				const c3 = tr.insertCell(); c3.className = "r"; c3.textContent = im_fmt(sg * l.value);
			}
			w2.append(t2); body.append(w2);
			if (fl.length > 3000) body.append(im_mk("p", "im-note", "Showing the first 3,000 of " + fl.length + " lines; use the filter to narrow."));
		};
		search.addEventListener("input", render); render();
	}

	// Linked view for Sales: each source document with its Sales Order, Sales Invoice and Delivery Note, linked row by row.
	linked_table(body, docs, lines, sg, all_docs, redraw) {
		body.append(im_mk("h3", "im-h3", "Documents with linked Sales Order, Sales Invoice and Delivery Note (" + docs.length + ")"));
		const key = this.p.company + "|" + all_docs.map(d => d.no).join(",");
		const cached = this.linked[key];
		if (!cached) {
			this.linked[key] = { status: "loading" };
			this.api("get_linked_sales", {
				company: this.p.company,
				delivery_notes: all_docs.filter(d => d.vt === "Delivery Note").map(d => d.no),
				sales_invoices: all_docs.filter(d => d.vt === "Sales Invoice").map(d => d.no),
			}).then(r => { this.linked[key] = { status: "ok", data: r }; redraw(); })
				.catch(() => { this.linked[key] = { status: "error" }; redraw(); });
		}
		const state = this.linked[key];
		if (state.status === "error") { body.append(im_mk("p", "im-empty", "Failed to load the linked sales documents.")); return; }
		if (state.status !== "ok") { body.append(im_mk("p", "im-empty", "Loading Sales Orders, Sales Invoices and Delivery Notes from the ERP…")); return; }
		const so = state.data.so_items, si = state.data.si_items, dn = state.data.dn_items;

		const so_row = new Map(so.map(r => [r.row, r]));
		const si_row = new Map(si.map(r => [r.row, r]));
		const dn_row = new Map(dn.map(r => [r.row, r]));
		const group = (arr, key_fn) => { const m = new Map(); for (const r of arr) { const v = key_fn(r); if (!v) continue; if (!m.has(v)) m.set(v, []); m.get(v).push(r); } return m; };
		const si_by_parent = group(si, r => r.name), dn_by_parent = group(dn, r => r.name);
		const si_by_dn_detail = group(si, r => r.dn_detail), dn_by_si_detail = group(dn, r => r.si_detail);
		// Fallback through the Sales Order: same Sales Order line, or else same Sales Order and item.
		const si_by_so_detail = group(si, r => r.so_detail), dn_by_so_detail = group(dn, r => r.so_detail);
		const si_by_so_item = group(si, r => (r.sales_order ? r.sales_order + "\u0001" + r.item_code : null));
		const dn_by_so_item = group(dn, r => (r.against_sales_order ? r.against_sales_order + "\u0001" + r.item_code : null));
		const items_of = new Map();
		for (const l of lines) { if (!items_of.has(l.voucher_no)) items_of.set(l.voucher_no, new Set()); items_of.get(l.voucher_no).add(l.item_code); }
		// Collect linked rows as {r, via} where via is 'direct' or 'so'.
		const add = (map, r, via) => { if (!r) return; const cur = map.get(r.row); if (!cur || (cur.via === "so" && via === "direct")) map.set(r.row, { r, via }); };
		const result = docs.map(d => {
			const items = items_of.get(d.no) || new Set();
			const keep = (r) => items.has(r.item_code);
			const so_m = new Map(), si_m = new Map(), dn_m = new Map();
			if (d.vt === "Delivery Note") {
				for (const r of (dn_by_parent.get(d.no) || []).filter(keep)) {
					add(dn_m, r, "direct");
					add(so_m, so_row.get(r.so_detail), "direct");
					const direct = [];
					if (si_row.get(r.si_detail)) direct.push(si_row.get(r.si_detail));
					for (const x of si_by_dn_detail.get(r.row) || []) direct.push(x);
					if (direct.length) { for (const x of direct) add(si_m, x, "direct"); }
					else {
						const via_so = (r.so_detail && si_by_so_detail.get(r.so_detail)) || (r.against_sales_order && si_by_so_item.get(r.against_sales_order + "\u0001" + r.item_code)) || [];
						for (const x of via_so) add(si_m, x, "so");
					}
				}
			} else if (d.vt === "Sales Invoice") {
				for (const r of (si_by_parent.get(d.no) || []).filter(keep)) {
					add(si_m, r, "direct");
					add(so_m, so_row.get(r.so_detail), "direct");
					const direct = [];
					if (dn_row.get(r.dn_detail)) direct.push(dn_row.get(r.dn_detail));
					for (const x of dn_by_si_detail.get(r.row) || []) direct.push(x);
					if (direct.length) { for (const x of direct) add(dn_m, x, "direct"); }
					else {
						const via_so = (r.so_detail && dn_by_so_detail.get(r.so_detail)) || (r.sales_order && dn_by_so_item.get(r.sales_order + "\u0001" + r.item_code)) || [];
						for (const x of via_so) add(dn_m, x, "so");
					}
				}
			}
			// Group linked rows by document, keeping each document's own quantity and amount.
			const by_doc = (m) => {
				const o = new Map();
				for (const { r, via } of m.values()) {
					const g = o.get(r.name) || { name: r.name, q: 0, v: 0, via };
					g.q += Number(r.stock_qty) || 0; g.v += Number(r.base_net_amount) || 0;
					if (via === "direct") g.via = "direct";
					o.set(r.name, g);
				}
				return Array.from(o.values()).sort((a, b) => (a.name < b.name ? -1 : 1));
			};
			return { d, so: by_doc(so_m), si: by_doc(si_m), dn: by_doc(dn_m) };
		});

		const w = im_mk("div", "im-scroll"); w.style.borderTop = "1px solid var(--im-line)";
		const t = im_mk("table", "im-tbl im-dtbl");
		const th = t.createTHead();
		const g = th.insertRow();
		const gh = (text, span, cls) => { const c = im_mk("th", cls || null, text); c.colSpan = span; g.append(c); };
		gh("", 2); gh("Documents", 4, "im-grp"); gh("Quantity", 4, "im-grp"); gh("Value", 4, "im-grp");
		const h = th.insertRow();
		for (const x of ["Date", "Source type", "Source document", "Sales Order", "Sales Invoice", "Delivery Note", "Source", "Sales Order", "Sales Invoice", "Delivery Note", "Source (stock cost)", "Sales Order", "Sales Invoice", "Delivery Note"]) h.append(im_mk("th", null, x));
		const b = t.createTBody();
		// Several documents in one cell sit side by side; a document found through the Sales Order is marked "via SO".
		const doc_cell = (tr, type, list, gl) => {
			const c = tr.insertCell(); c.className = "im-links" + (gl ? " im-gl" : "");
			for (const x of list) {
				const chip = im_mk("span", "im-chip" + (x.via === "so" ? " im-viaso" : "") + (x.q < 0 ? " im-ret" : ""));
				chip.append(im_link(type, x.name));
				if (x.q < 0) chip.append(im_mk("span", "im-tag", "return"));
				if (x.via === "so") chip.append(im_mk("span", "im-tag", "via SO"));
				c.append(chip);
			}
		};
		const num_cell = (tr, list, k, gl) => {
			const c = tr.insertCell(); c.className = "r" + (gl ? " im-gl" : "");
			if (!list.length) return null;
			const total = list.reduce((s, x) => s + x[k], 0);
			if (list.length === 1) { c.textContent = im_fmt(total); return total; }
			const row = im_mk("span", "im-split");
			for (const x of list) row.append(im_mk("span", "im-chip" + (x[k] < 0 ? " im-ret" : ""), im_fmt(x[k])));
			c.append(row, im_mk("b", "im-net", "= " + im_fmt(total)));
			return total;
		};
		const plain = (tr, v, gl) => { const c = tr.insertCell(); c.className = "r" + (gl ? " im-gl" : ""); c.textContent = v == null ? "" : im_fmt(v); };
		const tot = { sq: 0, soQ: 0, siQ: 0, dnQ: 0, sv: 0, soV: 0, siV: 0, dnV: 0 };
		let via_so = 0;
		for (const r of result) {
			const tr = b.insertRow();
			tr.insertCell().textContent = im_nice_date(r.d.date);
			tr.insertCell().textContent = r.d.vt;
			doc_cell(tr, r.d.vt, [{ name: r.d.no, q: sg * r.d.q, via: "direct" }], true);
			doc_cell(tr, "Sales Order", r.so);
			doc_cell(tr, "Sales Invoice", r.si);
			doc_cell(tr, "Delivery Note", r.dn);
			if (r.si.some(x => x.via === "so") || r.dn.some(x => x.via === "so")) via_so++;
			plain(tr, sg * r.d.q, true);
			tot.soQ += num_cell(tr, r.so, "q") || 0; tot.siQ += num_cell(tr, r.si, "q") || 0; tot.dnQ += num_cell(tr, r.dn, "q") || 0;
			plain(tr, sg * r.d.v, true);
			tot.soV += num_cell(tr, r.so, "v") || 0; tot.siV += num_cell(tr, r.si, "v") || 0; tot.dnV += num_cell(tr, r.dn, "v") || 0;
			tot.sq += sg * r.d.q; tot.sv += sg * r.d.v;
		}
		const ft = t.createTFoot().insertRow(); ft.className = "im-close";
		const c0 = ft.insertCell(); c0.colSpan = 6; c0.textContent = "Total";
		plain(ft, tot.sq, true); plain(ft, tot.soQ); plain(ft, tot.siQ); plain(ft, tot.dnQ);
		plain(ft, tot.sv, true); plain(ft, tot.soV); plain(ft, tot.siV); plain(ft, tot.dnV);
		w.append(t); body.append(w);
		if (!docs.length) body.append(im_mk("p", "im-empty", "No documents."));
		body.append(im_mk("p", "im-note", "Links are matched line by line on the items of this unit. Where a Delivery Note and Sales Invoice are not linked to each other, they are matched through their Sales Order (marked “via SO”). When several invoices or returns share a cell they are shown side by side, with their net total after “=”. Sales Order, Sales Invoice and Delivery Note quantities are in stock units; their amounts are selling amounts before tax, while the source value is the stock cost from the ledger. An empty cell means no linked document of that kind was found." + (via_so ? " " + via_so + " of these rows use a match through the Sales Order." : "")));
	}
}
