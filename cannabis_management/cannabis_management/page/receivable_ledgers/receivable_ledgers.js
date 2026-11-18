// Accounts Receivable Report: port of the claude.ai "Accounts Receivable Report — Live ERP" dashboard.
// Server: cannabis_management.api.receivable_ledgers returns the same rows the dashboard's datasets
// read; the ledger, totals and strain calculations below are the dashboard's own, unchanged.

(() => {
const COS = ["TSBC Ranch", "Master Touch Manufacturing", "Motley Terpz"];
const IC_NAMES = new Set(COS);
const MIN = "2018-01-01", MAX = "2030-12-31";
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const LABEL = { si: "Sales invoice", so: "Sales order", dn: "Delivery note" };

const num = (v) => Number(v) || 0;
const money = (v) => (v == null ? "" : (v < 0 ? "−$" : "$") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const qty = (v) => (v == null ? "" : (v < 0 ? "−" : "") + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 2 }));
const P = (s) => { const [y, m, d] = String(s).split("-").map(Number); return { y, m, d }; };
const iso = (y, m, d) => new Date(Date.UTC(y, m - 1, d)).toISOString().slice(0, 10);
const addDays = (s, days) => { const { y, m, d } = P(s); return iso(y, m, d + days); };
const ord = (d) => d + (d % 100 >= 11 && d % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][d % 10] || "th");
const long = (s) => { const { y, m, d } = P(s); return ord(d) + " " + MONTHS[m - 1] + " " + y; };
const short = (s) => { if (!s) return ""; const { y, m, d } = P(s); return d + " " + MONTHS[m - 1].slice(0, 3) + " " + y; };
const clamp = (s) => (s < MIN ? MIN : s > MAX ? MAX : s);
const localToday = () => { const d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); };
const isIC = (name, account) => IC_NAMES.has(name) || /inter-?company|\bic receivable/i.test(account || "");
const byDate = (a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
const groupBy = (arr, f) => { const m = new Map(); for (const x of arr) { const k = f(x); if (!m.has(k)) m.set(k, []); m.get(k).push(x); } return m; };
const el = (tag, attrs, ...kids) => {
	const e = document.createElement(tag);
	if (attrs) for (const k in attrs) {
		if (attrs[k] == null || attrs[k] === false) continue;
		if (k === "class") e.className = attrs[k];
		else if (k === "text") e.textContent = attrs[k];
		else e.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
	}
	for (const k of kids) if (k != null) e.append(k);
	return e;
};
const skel = (e, status) => { e.classList.toggle("dash-skeleton", status === "loading"); };
const coChip = (co) => { const i = COS.indexOf(co); return el("span", { class: "ar-co c" + Math.max(0, i), title: co || "", text: ["TSBC", "MTM", "Motley"][i] || (co || "—") }); };

// Journal entries: receipts a sister company collected (traced to the bank or cash account), else adjustments.
function journalPays(jv, bank, cust, withCompany) {
	const isICacct = (a) => /^IC Receivable|Inter-?Company Receivable/i.test(a || "");
	const byV = new Map();
	for (const l of jv || []) { if (!byV.has(l.voucher_no)) byV.set(l.voucher_no, []); byV.get(l.voucher_no).push(l); }
	const usedBank = new Set();
	const findBank = (co, amt, date) => {
		let best = -1, bd = 1e9;
		(bank || []).forEach((b, i) => {
			if (usedBank.has(i) || b.company !== co || Math.abs(num(b.credit) - amt) > 0.005) return;
			const d = Math.abs(Date.parse(b.posting_date) - Date.parse(date)) / 864e5;
			if (d <= 7 && d < bd) { bd = d; best = i; }
		});
		if (best < 0) return null;
		usedBank.add(best); return bank[best];
	};
	for (const [v, lines] of byV) {
		const ic = lines.find((l) => IC_NAMES.has(l.party) && isICacct(l.account) && num(l.amount) > 0);
		let kind = "adjustment", medium = "Journal entry", acct = null, doc = v;
		if (ic) {
			const b = findBank(ic.party, num(ic.amount), ic.posting_date);
			kind = "payment"; medium = "Received by " + ic.party;
			acct = b ? b.against : null; doc = b ? b.voucher_no + " / " + v : v;
		}
		for (const l of lines) {
			if (IC_NAMES.has(l.party) || !l.party) continue;
			const ref = l.against_voucher_type === "Sales Invoice" ? l.against_voucher_no : null;
			const c = cust(l.party);
			if (withCompany) c.cos.add(l.company);
			const e = { date: l.posting_date, kind, medium, account: acct, doc, amount: -num(l.amount), ref, refType: ref ? "Sales Invoice" : "On account" };
			if (withCompany) e.company = l.company;
			c.pays.push(e);
		}
	}
}

// Single company: each customer's opening balance, invoices, and what was matched to each invoice.
function calcLedger(collection, payments, opening, jv, bank) {
	const custs = new Map();
	const cust = (c) => { if (!custs.has(c)) custs.set(c, { opening: 0, invoices: [], returns: [], pays: [], accounts: new Set(), cos: new Set() }); return custs.get(c); };
	for (const o of opening) if (o.party && Math.abs(num(o.outstanding)) > 0.004) cust(o.party).opening = num(o.outstanding);
	for (const r of collection) {
		if (!r.invoice || !r.customer) continue;
		const c = cust(r.customer);
		if (r.receivable_account) c.accounts.add(r.receivable_account);
		if (r.return_against || r.status === "Return") c.returns.push(r); else c.invoices.push(r);
	}
	const unalloc = new Set();
	for (const p of payments) {
		if (!p.party) continue;
		const c = cust(p.party);
		if (p.ref && num(p.alloc)) c.pays.push({ date: p.posting_date, kind: "payment", medium: p.mode_of_payment || "Payment", account: p.paid_to, doc: p.name, amount: num(p.alloc), ref: p.ref_type === "Sales Invoice" ? p.ref : null, refType: p.ref_type });
		if (num(p.unallocated_amount) > 0.004 && !unalloc.has(p.name)) { unalloc.add(p.name); c.pays.push({ date: p.posting_date, kind: "payment", medium: p.mode_of_payment || "Payment", account: p.paid_to, doc: p.name, amount: num(p.unallocated_amount), ref: null, refType: "On account" }); }
	}
	journalPays(jv, bank, cust, false);
	const rows = [];
	for (const [name, c] of [...custs].sort((a, b) => a[0].localeCompare(b[0]))) {
		let bal = c.opening, n = 0;
		const id = () => name + " #" + (n++);
		const account = [...c.accounts].join(", ");
		rows.push({ row_id: id(), customer: name, kind: "opening", inv_date: null, invoice: null, status: null, debit: c.opening >= 0 ? c.opening : null, cr_date: null, medium: null, account: null, doc: null, credit_kind: null, credit: c.opening < 0 ? -c.opening : null, balance: bal, receivable_account: account, ref: null });
		const mine = new Set(c.invoices.map((i) => i.invoice));
		const credits = new Map(); const prior = [];
		const entries = c.pays.concat(c.returns.map((r) => ({ date: r.posting_date, kind: "credit_note", medium: "Credit note", account: null, doc: r.invoice, amount: -num(r.invoice_amount), ref: r.return_against || null, refType: "Sales Invoice" })));
		for (const e of entries) { if (e.ref && mine.has(e.ref)) { if (!credits.has(e.ref)) credits.set(e.ref, []); credits.get(e.ref).push(e); } else prior.push(e); }
		prior.sort(byDate);
		for (const e of prior) { bal -= e.amount; rows.push({ row_id: id(), customer: name, kind: "prior", inv_date: null, invoice: null, status: null, debit: null, cr_date: e.date, medium: e.medium, account: e.account, doc: e.doc, credit_kind: e.kind, credit: e.amount, credit_paid: e.kind === "payment" ? e.amount : 0, credit_cn: e.kind !== "payment" ? e.amount : 0, entries: [{ date: e.date, kind: e.kind, medium: e.medium, account: e.account || null, doc: e.doc, amount: e.amount }], outstanding: null, balance: bal, receivable_account: account, ref: e.ref || e.refType || null }); }
		c.invoices.sort((a, b) => (a.posting_date < b.posting_date ? -1 : a.posting_date > b.posting_date ? 1 : a.invoice.localeCompare(b.invoice)));
		for (const inv of c.invoices) {
			const cr = (credits.get(inv.invoice) || []).sort(byDate);
			const amt = num(inv.invoice_amount);
			const paid = cr.filter((e) => e.kind === "payment").reduce((a, e) => a + e.amount, 0);
			const cn = cr.filter((e) => e.kind !== "payment").reduce((a, e) => a + e.amount, 0);
			bal += amt - paid - cn;
			rows.push({ row_id: id(), customer: name, kind: "invoice", inv_date: inv.posting_date, invoice: inv.invoice, status: inv.status, debit: amt,
				cr_date: cr.length ? cr[0].date : null, medium: cr.length ? cr.map((e) => e.medium).join(", ") : null, account: null, doc: null,
				credit_kind: cr.length ? (cr.every((e) => e.kind === cr[0].kind) ? cr[0].kind : "mixed") : null, credit: cr.length ? paid + cn : null,
				credit_paid: paid, credit_cn: cn, entries: cr.map((e) => ({ date: e.date, kind: e.kind, medium: e.medium, account: e.account || null, doc: e.doc, amount: e.amount })),
				outstanding: amt - paid - cn, balance: bal, receivable_account: account, ref: null });
		}
	}
	return rows;
}

function calcTotals(ledger) {
	const t = new Map();
	for (const r of ledger || []) {
		if (!t.has(r.customer)) t.set(r.customer, { customer: r.customer, receivable_account: r.receivable_account, opening: 0, invoiced: 0, received: 0, credit_notes: 0, closing: 0 });
		const x = t.get(r.customer);
		if (r.kind === "opening") x.opening = (r.debit || 0) - (r.credit || 0);
		if (r.kind === "invoice") x.invoiced += r.debit || 0;
		x.received += r.credit_paid || 0;
		x.credit_notes += r.credit_cn || 0;
		x.closing = r.balance;
	}
	return [...t.values()];
}

// All companies combined: the same ledger across TSBC Ranch, Master Touch Manufacturing and Motley Terpz.
function calcLedgerAll(collection, opening, payments, jv, bank) {
	const custs = new Map();
	const cust = (c) => { if (!custs.has(c)) custs.set(c, { opening: new Map(), invoices: [], returns: [], pays: [], accounts: new Set(), cos: new Set() }); return custs.get(c); };
	for (const o of opening) if (o.party && Math.abs(num(o.outstanding)) > 0.004) { const c = cust(o.party); c.opening.set(o.company, (c.opening.get(o.company) || 0) + num(o.outstanding)); c.cos.add(o.company); }
	for (const r of collection) {
		if (!r.invoice || !r.customer) continue;
		const c = cust(r.customer); c.cos.add(r.company);
		if (r.receivable_account) c.accounts.add(r.receivable_account);
		if (r.return_against || r.status === "Return") c.returns.push(r); else c.invoices.push(r);
	}
	const unalloc = new Set();
	for (const p of payments) {
		if (!p.party) continue;
		const c = cust(p.party); c.cos.add(p.company);
		if (p.ref && num(p.alloc)) c.pays.push({ date: p.posting_date, company: p.company, kind: "payment", medium: p.mode_of_payment || "Payment", account: p.paid_to, doc: p.name, amount: num(p.alloc), ref: p.ref_type === "Sales Invoice" ? p.ref : null, refType: p.ref_type });
		if (num(p.unallocated_amount) > 0.004 && !unalloc.has(p.name)) { unalloc.add(p.name); c.pays.push({ date: p.posting_date, company: p.company, kind: "payment", medium: p.mode_of_payment || "Payment", account: p.paid_to, doc: p.name, amount: num(p.unallocated_amount), ref: null, refType: "On account" }); }
	}
	journalPays(jv, bank, cust, true);
	const rows = [];
	for (const [name, c] of [...custs].sort((a, b) => a[0].localeCompare(b[0]))) {
		let bal = 0, n = 0;
		const id = () => name + " #" + (n++);
		const account = [...c.accounts].join(", ");
		const companies = COS.filter((x) => c.cos.has(x)).join(", ");
		const base = { customer: name, receivable_account: account, companies, company_count: c.cos.size };
		const opens = COS.filter((co) => c.opening.has(co));
		if (!opens.length) rows.push({ ...base, row_id: id(), kind: "opening", company: null, inv_date: null, invoice: null, status: null, debit: null, cr_date: null, medium: null, account: null, doc: null, credit_kind: null, credit: null, balance: 0, ref: null });
		for (const co of opens) {
			const v = c.opening.get(co); bal += v;
			rows.push({ ...base, row_id: id(), kind: "opening", company: co, inv_date: null, invoice: null, status: null, debit: v >= 0 ? v : null, cr_date: null, medium: null, account: null, doc: null, credit_kind: null, credit: v < 0 ? -v : null, balance: bal, ref: null });
		}
		const mine = new Set(c.invoices.map((i) => i.invoice));
		const credits = new Map(); const prior = [];
		const entries = c.pays.concat(c.returns.map((r) => ({ date: r.posting_date, company: r.company, kind: "credit_note", medium: "Credit note", account: null, doc: r.invoice, amount: -num(r.invoice_amount), ref: r.return_against || null, refType: "Sales Invoice" })));
		for (const e of entries) { if (e.ref && mine.has(e.ref)) { if (!credits.has(e.ref)) credits.set(e.ref, []); credits.get(e.ref).push(e); } else prior.push(e); }
		prior.sort(byDate);
		for (const e of prior) { bal -= e.amount; rows.push({ ...base, row_id: id(), kind: "prior", company: e.company, inv_date: null, invoice: null, status: null, debit: null, cr_date: e.date, medium: e.medium, account: e.account, doc: e.doc, credit_kind: e.kind, credit: e.amount, credit_paid: e.kind === "payment" ? e.amount : 0, credit_cn: e.kind !== "payment" ? e.amount : 0, entries: [{ date: e.date, kind: e.kind, medium: e.medium, account: e.account || null, doc: e.doc, amount: e.amount }], outstanding: null, balance: bal, ref: e.ref || e.refType || null }); }
		c.invoices.sort((a, b) => (a.posting_date < b.posting_date ? -1 : a.posting_date > b.posting_date ? 1 : a.invoice.localeCompare(b.invoice)));
		for (const inv of c.invoices) {
			const cr = (credits.get(inv.invoice) || []).sort(byDate);
			const amt = num(inv.invoice_amount);
			const paid = cr.filter((e) => e.kind === "payment").reduce((a, e) => a + e.amount, 0);
			const cn = cr.filter((e) => e.kind !== "payment").reduce((a, e) => a + e.amount, 0);
			bal += amt - paid - cn;
			rows.push({ ...base, row_id: id(), company: inv.company, kind: "invoice", inv_date: inv.posting_date, invoice: inv.invoice, status: inv.status, debit: amt,
				cr_date: cr.length ? cr[0].date : null, medium: cr.length ? cr.map((e) => e.medium).join(", ") : null, account: null, doc: null,
				credit_kind: cr.length ? (cr.every((e) => e.kind === cr[0].kind) ? cr[0].kind : "mixed") : null, credit: cr.length ? paid + cn : null,
				credit_paid: paid, credit_cn: cn, entries: cr.map((e) => ({ date: e.date, kind: e.kind, medium: e.medium, account: e.account || null, doc: e.doc, amount: e.amount })),
				outstanding: amt - paid - cn, balance: bal, ref: null });
		}
	}
	return rows;
}

function calcAllTotals(ledger) {
	const t = new Map();
	for (const r of ledger || []) {
		if (!t.has(r.customer)) t.set(r.customer, { customer: r.customer, companies: r.companies, company_count: r.company_count, receivable_account: r.receivable_account, opening: 0, invoiced: 0, received: 0, credit_notes: 0, closing: 0 });
		const x = t.get(r.customer);
		if (r.kind === "opening") x.opening += (r.debit || 0) - (r.credit || 0);
		if (r.kind === "invoice") x.invoiced += r.debit || 0;
		x.received += r.credit_paid || 0;
		x.credit_notes += r.credit_cn || 0;
		x.closing = r.balance;
	}
	return [...t.values()];
}

// For every SI, SO and DN: quantity and amount of each strain on the SO, the invoices and the delivery notes sharing its lines.
function calcStrains(si_lines, so_lines, dn_lines) {
	const soBy = new Map(); for (const l of so_lines) soBy.set(l.so_detail, l);
	const siBy = new Map(), dnBy = new Map();
	const push = (m, k, v) => { if (!k) return; if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
	for (const l of si_lines) push(siBy, l.so_detail, l);
	for (const l of dn_lines) push(dnBy, l.so_detail, l);
	const anchors = new Map();
	const addA = (type, l) => { const k = type + "|" + l.name; if (!anchors.has(k)) anchors.set(k, { type, doc: l.name, lines: [] }); anchors.get(k).lines.push(l); };
	for (const l of si_lines) addA("si", l);
	for (const l of so_lines) addA("so", l);
	for (const l of dn_lines) addA("dn", l);
	const out = [];
	for (const { type, doc, lines } of anchors.values()) {
		const st = new Map(); const rel = { so: new Set(), si: new Set(), dn: new Set() };
		const s = (l) => { const k = (l.item_name || "(no name)") + "|" + (l.uom || ""); if (!st.has(k)) st.set(k, { strain: l.item_name || "(no name)", uom: l.uom || "", so_qty: null, si_qty: null, dn_qty: null, so_amt: null, si_amt: null, dn_amt: null }); return st.get(k); };
		const add = (t, l) => { const x = s(l); x[t + "_qty"] = (x[t + "_qty"] || 0) + num(l.qty); x[t + "_amt"] = (x[t + "_amt"] || 0) + num(l.amount); rel[t].add(l.name); };
		const dets = new Set();
		for (const l of lines) { if (l.so_detail) dets.add(l.so_detail); else add(type, l); }
		if (type !== "so") for (const l of lines) if (l.so_detail) add(type, l);
		for (const d of dets) {
			if (soBy.has(d)) add("so", soBy.get(d));
			if (type !== "si") for (const l of siBy.get(d) || []) add("si", l);
			if (type !== "dn") for (const l of dnBy.get(d) || []) add("dn", l);
		}
		const uoms = new Set(); const tot = { so_qty: 0, si_qty: 0, dn_qty: 0, so_amt: 0, si_amt: 0, dn_amt: 0 };
		for (const x of st.values()) { uoms.add(x.uom); for (const f in tot) tot[f] += x[f] || 0; out.push({ key: type + "|" + doc + "|" + x.strain + "|" + x.uom, doc, doc_type: type, ...x, related: null }); }
		const one = uoms.size === 1;
		out.push({ key: type + "|" + doc + "|Total", doc, doc_type: type, strain: "Total", uom: one ? [...uoms][0] : "mixed",
			so_qty: one ? tot.so_qty : null, si_qty: one ? tot.si_qty : null, dn_qty: one ? tot.dn_qty : null,
			so_amt: tot.so_amt, si_amt: tot.si_amt, dn_amt: tot.dn_amt,
			related: ["so", "si", "dn"].map((t) => [...rel[t]].sort().join(", ")).join(" | ") });
	}
	return out;
}

const SHELL = `
<header class="ar-hero" id="report-heading">
	<h1 class="ar-title">Accounts receivable</h1>
	<p class="ar-sub">
		<span class="ar-pill"><b data-draw="hdr-company">—</b></span>
		<span class="ar-pill resin" data-draw="hdr-range">—</span>
		<span class="ar-pill plain" data-draw="hdr-cust">—</span>
		<span class="ar-pill plain" data-ic="off">Inter-company excluded</span>
		<span class="ar-pill resin" data-ic="on" hidden>Inter-company included</span>
	</p>
	<p class="ar-take" id="takeaway">Closing receivable is <b data-draw="take-closing">—</b> after <b data-draw="take-invoiced">—</b> invoiced and <b data-draw="take-collected">—</b> collected in the period.</p>
</header>
<div class="ar-filters ar-glass" id="filters">
	<label class="ar-field" id="f-company"><span>Company</span>
		<select class="dash-select" id="ar-company" aria-label="Company"></select>
	</label>
	<div class="ar-field" id="f-range"><span>Date range</span>
		<button type="button" class="ar-trigger" id="ar-range-btn" aria-haspopup="dialog" aria-expanded="false"><span data-draw="range-label">—</span><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M2 6.5h12M5 1.5v3M11 1.5v3" stroke="currentColor" stroke-width="1.4"/></svg></button>
		<div class="ar-pop cal" id="ar-cal-pop" role="dialog" aria-label="Pick a date range" hidden><div data-draw="cal"></div></div>
	</div>
	<div class="ar-field" id="f-dates"><span>From date and to date</span>
		<div class="ar-dates">
			<input type="date" id="ar-from" aria-label="From date" min="2018-01-01" max="2030-12-31">
			<input type="date" id="ar-to" aria-label="To date" min="2018-01-01" max="2030-12-31">
		</div>
	</div>
	<div class="ar-field" id="f-customers"><span>Customers</span>
		<button type="button" class="ar-trigger" id="ar-cust-btn" aria-haspopup="dialog" aria-expanded="false"><span data-draw="cust-label">—</span><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg></button>
		<div class="ar-pop cust" id="ar-cust-pop" role="dialog" aria-label="Choose customers" hidden><div data-draw="cust-list"></div></div>
	</div>
	<div class="ar-field" id="f-intercompany"><span>Inter-company transactions</span>
		<button type="button" class="ar-toggle" id="ar-ic-btn" aria-pressed="false"><span class="track" aria-hidden="true"></span><span><span data-ic="off">Excluded</span><span data-ic="on" hidden>Included</span><small>Sales between TSBC Ranch, Master Touch Manufacturing and Motley Terpz</small></span></button>
	</div>
</div>
<div class="ar-tabs ar-glass" role="tablist" id="tabs">
	<button type="button" class="ar-tab" role="tab" data-tab="ledgers" aria-selected="true">Receivable ledgers</button>
	<button type="button" class="ar-tab" role="tab" data-tab="sales" aria-selected="false">Sales detail</button>
</div>
<section id="ledgers">
	<div class="ar-strip ar-glass" id="period-totals">
		<div class="ar-stat"><span>Opening balance</span><b data-draw="tot-opening">—</b></div>
		<div class="ar-stat"><span>Invoiced</span><b data-draw="tot-invoiced">—</b></div>
		<div class="ar-stat"><span>Payments received</span><b data-draw="tot-received">—</b></div>
		<div class="ar-stat"><span>Credit notes and adjustments</span><b data-draw="tot-credit">—</b></div>
		<div class="ar-stat"><span>Closing balance</span><b data-draw="tot-closing">—</b></div>
	</div>
	<label class="ar-multi" id="multi-company-only" hidden><input type="checkbox" id="ar-multi-cb"> Only customers who deal with two or more of the companies</label>
	<div class="ar-ledgers" id="customer-ledgers" data-draw="ledgers">—</div>
	<p class="ar-note" id="ledger-note">Each invoice sits on one row. Every payment, credit note and journal adjustment matched to it is listed separately on the credit side of that same row. Payments a sister company collected show as Received by that company, with the bank or cash account that took the money, and Outstanding shows what is still owed on the invoice after them. Receipts and credit notes against invoices dated before the period appear right after the opening balance. Click an invoice number to see what was sold on it. Invoice status is as it stands in the ERP today.</p>
</section>
<section id="sales" hidden>
	<div class="ar-sdbar ar-glass" id="sales-filters">
		<label class="ar-field"><span>Customer</span>
			<select class="dash-select" data-draw="sd-cust" aria-label="Customer for sales detail"></select>
		</label>
		<div class="ar-field"><span>Find by</span>
			<div class="ar-seg" role="group" aria-label="Document type">
				<button type="button" data-doctype="si" aria-pressed="true">Sales invoice</button>
				<button type="button" data-doctype="so" aria-pressed="false">Sales order</button>
				<button type="button" data-doctype="dn" aria-pressed="false">Delivery note</button>
			</div>
		</div>
		<label class="ar-field"><span>Document number</span>
			<input type="search" class="ar-docsearch" id="ar-docsearch" placeholder="Type part of a number, e.g. 00775" aria-label="Search document number">
		</label>
	</div>
	<div class="ar-picker ar-glass" id="document-picker" data-draw="sd-picker">—</div>
	<div class="ar-sdt ar-glass" id="quantity-table">
		<h3>Quantity by strain</h3>
		<p>Sales order, sales invoice and delivery note quantities for each strain, linked through the sales order line. Figures that disagree are shown in red.</p>
		<div class="ar-scroll" data-draw="sd-qty">—</div>
	</div>
	<div class="ar-sdt ar-glass" id="amount-table">
		<h3>Amount by strain</h3>
		<p>Line amounts in USD before freight and other charges, from the same three documents.</p>
		<div class="ar-scroll" data-draw="sd-amt">—</div>
	</div>
</section>`;

class ReceivableLedgers {
	constructor(page) {
		this.page = page;
		this.$root = $('<div class="ar" id="ar-top"></div>').appendTo(page.main);
		this.root = this.$root[0];
		Object.assign(this, { includeIC: false, custSel: null, combined: false, multiOnly: false, calView: null, pickA: null, pickB: null, hover: null,
			sdType: "si", sdDocs: [], sdCustomer: "", search: "", custSearch: "" });
		this.raw = null; this.rawStatus = "idle"; this.req = 0;
		this.sales = null; this.salesStatus = "idle"; this.salesKey = null; this.sreq = 0;
		this.root.innerHTML = SHELL;
		this._init();
	}

	api(method, args) { return frappe.xcall("cannabis_management.api.receivable_ledgers." + method, args); }
	q(s) { return this.root.querySelector(s); }
	qa(s) { return this.root.querySelectorAll(s); }
	draw(name) { const fn = this["draw_" + name.replace(/-/g, "_")]; for (const e of this.qa('[data-draw="' + name + '"]')) fn.call(this, e); }

	async _init() {
		try { this.companies = await this.api("get_companies"); } catch (e) { this.companies = []; }
		if (!this.companies.length) { this.root.replaceChildren(el("div", { class: "ar-empty ar-glass", text: "You do not have access to TSBC Ranch, Master Touch Manufacturing or Motley Terpz." })); return; }
		let saved = {};
		try { saved = JSON.parse(localStorage.getItem("ar_params") || "{}") || {}; } catch (e) { }
		const today = localToday();
		this.p = {
			company: this.companies.includes(saved.company) ? saved.company : (this.companies.includes("TSBC Ranch") ? "TSBC Ranch" : this.companies[0]),
			from_date: saved.from_date || today.slice(0, 4) + "-01-01",
			to_date: saved.to_date || today,
			sd_customer: "",
		};
		const sel = this.q("#ar-company");
		for (const c of this.companies) sel.append(new Option(c, c));
		if (this.companies.length > 1) sel.append(new Option("All companies (combined)", "__all__"));
		this.mount_cust_list();
		this._bind();
		if (location.hash === "#sales") this.show_tab("sales");
		this.load();
	}

	set_params(patch) {
		this.p = Object.assign({}, this.p, patch);
		try { localStorage.setItem("ar_params", JSON.stringify({ company: this.p.company, from_date: this.p.from_date, to_date: this.p.to_date })); } catch (e) { }
		this.load();
	}

	// ---------- data ----------
	async load() {
		const cos = this.combined ? this.companies : [this.p.company];
		const r = this.raw;
		if (r && r.from_date === this.p.from_date && r.to_date === this.p.to_date && cos.every((c) => r.companies.includes(c))) {
			this.recompute(); this.redraw(); this.load_sales(); return;
		}
		const req = ++this.req;
		this.rawStatus = "loading";
		this.root.classList.add("ar-refreshing");
		this.recompute(); this.redraw();
		try {
			const data = await this.api("get_ledger_data", { companies: cos, from_date: this.p.from_date, to_date: this.p.to_date });
			if (req !== this.req) return;
			this.raw = data; this.rawStatus = "ok";
		} catch (e) {
			if (req !== this.req) return;
			this.raw = null; this.rawStatus = "error";
		}
		this.root.classList.remove("ar-refreshing");
		this.recompute(); this.redraw(); this.load_sales();
	}

	recompute() {
		const r = this.raw;
		this.ledger = this.ledger_totals = this.ledger_all = this.ledger_all_totals = null;
		if (!r || this.rawStatus !== "ok") return;
		if (r.companies.includes(this.p.company)) {
			const by = (rows) => rows.filter((x) => x.company === this.p.company);
			this.ledger = calcLedger(by(r.collection), by(r.payments), by(r.opening), by(r.jv), r.bank);
			this.ledger_totals = calcTotals(this.ledger);
		}
		if (this.combined && this.companies.every((c) => r.companies.includes(c))) {
			this.ledger_all = calcLedgerAll(r.collection, r.opening, r.payments, r.jv, r.bank);
			this.ledger_all_totals = calcAllTotals(this.ledger_all);
		}
	}

	async load_sales() {
		if (this.q("#sales").hidden && !this.sdDocs.length) return;
		const key = [this.p.company, this.p.from_date, this.p.to_date, this.p.sd_customer].join("|");
		if (this.salesKey === key && this.salesStatus !== "error") return;
		this.salesKey = key;
		const req = ++this.sreq;
		this.sales = null; this.strains = null; this.salesStatus = "loading";
		["sd-picker", "sd-qty", "sd-amt"].forEach((n) => this.draw(n));
		try {
			const d = await this.api("get_sales_lines", { company: this.p.company, from_date: this.p.from_date, to_date: this.p.to_date, customer: this.p.sd_customer || null });
			if (req !== this.sreq) return;
			this.sales = d; this.salesStatus = "ok";
			this.strains = calcStrains(d.si_lines, d.so_lines, d.dn_lines);
		} catch (e) {
			if (req !== this.sreq) return;
			this.salesStatus = "error";
		}
		["sd-cust", "sd-picker", "sd-qty", "sd-amt"].forEach((n) => this.draw(n));
	}

	// dash.data() of the dashboard: {status, data}
	D(name) {
		if (["si_lines", "so_lines", "dn_lines"].includes(name)) return this.sales ? { status: "ok", data: this.sales[name] } : { status: this.salesStatus === "error" ? "error" : "loading", data: [] };
		if (name === "strains") return this.strains ? { status: "ok", data: this.strains } : { status: this.salesStatus === "error" ? "error" : "loading", data: [] };
		if (this[name]) return { status: "ok", data: this[name] };
		return { status: this.rawStatus === "error" ? "error" : "loading", data: [] };
	}
	L() { return this.combined ? "ledger_all" : "ledger"; }
	TT() { return this.combined ? "ledger_all_totals" : "ledger_totals"; }
	icByName() { const t = this.D(this.TT()); const m = new Map(); if (t.status === "ok") for (const r of t.data) m.set(r.customer, isIC(r.customer, r.receivable_account)); return m; }
	custHidden(name) { return !this.includeIC && (IC_NAMES.has(name) || this.icByName().get(name) === true); }
	visibleTotals(name) {
		const t = this.D(name || this.TT());
		return t.status === "ok" ? t.data.filter((r) => (this.includeIC || !isIC(r.customer, r.receivable_account)) && (name || !this.combined || !this.multiOnly || r.company_count >= 2)) : [];
	}
	selectedCustomers() { const all = this.visibleTotals().map((r) => r.customer); return this.custSel ? all.filter((c) => this.custSel.has(c)) : all; }

	// ---------- actions ----------
	redraw() {
		const p = this.p;
		const sync = (s, v) => { const e = this.q(s); if (e && document.activeElement !== e) e.value = v; };
		sync("#ar-company", this.combined ? "__all__" : p.company); sync("#ar-from", p.from_date); sync("#ar-to", p.to_date);
		["hdr-company", "hdr-range", "range-label", "sd-cust", "sd-picker", "sd-qty", "sd-amt", "hdr-cust", "cust-label", "cust-list", "ledgers",
			"tot-opening", "tot-invoiced", "tot-received", "tot-credit", "tot-closing", "take-closing", "take-invoiced", "take-collected"].forEach((n) => this.draw(n));
		if (!this.q("#ar-cal-pop").hidden) this.draw("cal");
	}

	set_range(from, to) {
		from = clamp(from); to = clamp(to); if (to < from) [from, to] = [to, from];
		this.set_params({ from_date: from, to_date: to });
	}

	show_tab(id) {
		for (const s of this.qa("#ledgers, #sales")) s.hidden = s.id !== id;
		for (const b of this.qa(".ar-tab")) b.setAttribute("aria-selected", String(b.dataset.tab === id));
		try { history.replaceState(history.state, "", location.pathname + location.search + "#" + id); } catch (e) { }
		if (id === "sales") this.load_sales();
	}

	open_invoice(inv, customer, company) {
		this.sdType = "si"; this.sdDocs = [{ type: "si", name: inv }]; this.sdCustomer = customer || ""; this.search = "";
		const np = { sd_customer: customer || "" };
		if (company && company !== this.p.company) np.company = company;
		Object.assign(this.p, np);
		this.show_tab("sales");
		for (const b of this.qa("[data-doctype]")) b.setAttribute("aria-pressed", String(b.dataset.doctype === "si"));
		for (const s of this.qa("#ar-docsearch")) s.value = "";
		this.set_params({});
		const t = this.q("#quantity-table"); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	set_combined(on, onlyCustomer) {
		this.combined = on;
		this.custSel = onlyCustomer ? new Set([onlyCustomer]) : null;
		this.q("#ar-company").value = on ? "__all__" : this.p.company;
		this.q("#multi-company-only").hidden = !on;
		this.load();
	}

	sync_ic() {
		this.q("#ar-ic-btn").setAttribute("aria-pressed", String(this.includeIC));
		for (const e of this.qa("[data-ic]")) e.hidden = (e.dataset.ic === "on") !== this.includeIC;
	}

	_bind() {
		for (const b of this.qa(".ar-tab")) b.addEventListener("click", () => this.show_tab(b.dataset.tab));
		this.sync_ic();
		this.q("#ar-ic-btn").addEventListener("click", () => {
			this.includeIC = !this.includeIC;
			if (!this.includeIC) {
				if (this.custSel) for (const n of [...this.custSel]) if (this.custHidden(n)) this.custSel.delete(n);
				if (this.sdCustomer && this.custHidden(this.sdCustomer)) { this.sdCustomer = ""; this.sdDocs = []; this.p.sd_customer = ""; this.load_sales(); }
			}
			this.sync_ic();
			this.redraw();
		});
		const sel = this.q("#ar-company");
		sel.addEventListener("change", () => {
			if (sel.value === "__all__") { this.set_combined(true); return; }
			const was = this.combined;
			this.combined = false; this.custSel = null; this.sdDocs = []; this.sdCustomer = "";
			this.q("#multi-company-only").hidden = true;
			if (sel.value !== this.p.company) this.set_params({ company: sel.value, sd_customer: "" });
			else if (was) this.load();
		});
		this.q("#ar-multi-cb").addEventListener("change", (ev) => { this.multiOnly = ev.target.checked; this.redraw(); });
		const dateOk = (e) => e.value && e.validity.valid;
		for (const e of this.qa("#ar-from, #ar-to")) {
			e.addEventListener("change", () => {
				const f = this.q("#ar-from"), t = this.q("#ar-to");
				if (dateOk(f) && dateOk(t)) this.set_range(f.value, t.value);
			});
			e.addEventListener("blur", () => { e.value = e.id === "ar-from" ? this.p.from_date : this.p.to_date; });
		}
		const toggle = (btnId, popId, key, drawName) => {
			const btn = this.q("#" + btnId);
			btn.addEventListener("click", (ev) => {
				ev.stopPropagation();
				const pop = this.q("#" + popId);
				const willOpen = pop.hidden;
				for (const other of this.qa(".ar-pop")) other.hidden = true;
				for (const b of this.qa(".ar-trigger")) b.setAttribute("aria-expanded", "false");
				pop.hidden = !willOpen; btn.setAttribute("aria-expanded", String(willOpen));
				if (willOpen) { if (key === "cal") { this.pickA = null; this.pickB = null; this.calView = this.p.from_date.slice(0, 7); } this.draw(drawName); }
			});
		};
		toggle("ar-range-btn", "ar-cal-pop", "cal", "cal");
		toggle("ar-cust-btn", "ar-cust-pop", "cust", "cust-list");
		document.addEventListener("click", (ev) => {
			if (!this.root.isConnected) return;
			for (const pop of this.qa(".ar-pop")) if (!pop.hidden && !pop.parentElement.contains(ev.target)) pop.hidden = true;
			for (const b of this.qa(".ar-trigger")) { const pop = b.parentElement.querySelector(".ar-pop"); if (pop && pop.hidden) b.setAttribute("aria-expanded", "false"); }
		});
		document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && this.root.isConnected) for (const pop of this.qa(".ar-pop")) pop.hidden = true; });
		for (const b of this.qa("[data-doctype]")) b.addEventListener("click", () => {
			this.sdType = b.dataset.doctype;
			for (const o of this.qa("[data-doctype]")) o.setAttribute("aria-pressed", String(o === b));
			this.draw("sd-picker");
		});
		this.q("#ar-docsearch").addEventListener("input", (ev) => { this.search = ev.target.value.trim().toLowerCase(); this.draw("sd-picker"); });
	}

	// ---------- heading ----------
	draw_hdr_company(e) { e.textContent = this.combined ? "All companies (combined)" : this.p.company; }
	draw_hdr_range(e) { e.textContent = long(this.p.from_date) + " to " + long(this.p.to_date); }
	draw_range_label(e) { e.textContent = short(this.p.from_date) + " – " + short(this.p.to_date); }
	cust_label() {
		if (this.D(this.TT()).status !== "ok") return null;
		const all = this.visibleTotals().length, sel = this.selectedCustomers();
		if (!this.custSel || sel.length === all) return "All customers";
		if (sel.length === 0) return "No customers selected";
		if (sel.length === 1) return sel[0];
		return "Multiple customers (" + sel.length + ")";
	}
	draw_hdr_cust(e) { const s = this.cust_label(); e.textContent = s || "—"; skel(e, s ? "ok" : "loading"); }
	draw_cust_label(e) { const s = this.cust_label(); e.textContent = s || "Loading customers…"; }
	sum_sel(field) {
		const t = this.D(this.TT());
		if (t.status !== "ok") return null;
		const sel = new Set(this.selectedCustomers());
		return t.data.filter((r) => sel.has(r.customer)).reduce((a, r) => a + (r[field] || 0), 0);
	}
	draw_total(e, field) {
		const v = this.sum_sel(field);
		if (v == null) { e.textContent = "—"; skel(e, this.D(this.TT()).status); return; }
		skel(e, "ok");
		e.replaceChildren(el("span", { text: money(v) }));
	}
	draw_tot_opening(e) { this.draw_total(e, "opening"); }
	draw_tot_invoiced(e) { this.draw_total(e, "invoiced"); }
	draw_tot_received(e) { this.draw_total(e, "received"); }
	draw_tot_credit(e) { this.draw_total(e, "credit_notes"); }
	draw_tot_closing(e) { this.draw_total(e, "closing"); }
	draw_take_closing(e) { this.draw_total(e, "closing"); }
	draw_take_invoiced(e) { this.draw_total(e, "invoiced"); }
	draw_take_collected(e) { this.draw_total(e, "received"); }

	// ---------- the range calendar (2018 to 2030) ----------
	draw_cal(e) {
		const p = this.p;
		const today = localToday();
		if (!this.calView) this.calView = p.from_date.slice(0, 7);
		const [vy, vm] = this.calView.split("-").map(Number);
		const a = this.pickA || p.from_date, b = this.pickA ? (this.pickB || this.hover || this.pickA) : p.to_date;
		const lo = a < b ? a : b, hi = a < b ? b : a;
		const t = P(today), q = Math.floor((t.m - 1) / 3) * 3 + 1;
		const lastDay = (y, m) => iso(y, m + 1, 0);
		const presets = [
			["This month", iso(t.y, t.m, 1), lastDay(t.y, t.m)],
			["Last month", iso(t.y, t.m - 1, 1), lastDay(t.y, t.m - 1)],
			["This quarter", iso(t.y, q, 1), lastDay(t.y, q + 2)],
			["Year to date", iso(t.y, 1, 1), today],
			["Last year", iso(t.y - 1, 1, 1), iso(t.y - 1, 12, 31)],
			["Last 12 months", addDays(today, -364), today],
			["Everything since 2018", MIN, today],
		];
		const close = () => { this.q("#ar-cal-pop").hidden = true; this.q("#ar-range-btn").setAttribute("aria-expanded", "false"); };
		const pre = el("div", { class: "ar-presets" });
		for (const [label, f, to] of presets) {
			const bt = el("button", { type: "button", class: "ar-chip" + (f === p.from_date && to === p.to_date ? " on" : ""), text: label });
			bt.onclick = (ev) => { ev.stopPropagation(); close(); this.set_range(f, to); };
			pre.append(bt);
		}
		const nav = el("div", { class: "ar-calnav" });
		const go = (dm) => { const d = new Date(Date.UTC(vy, vm - 1 + dm, 1)); const s = d.toISOString().slice(0, 7); if (s >= "2018-01" && s <= "2030-12") { this.calView = s; this.draw("cal"); } };
		const prev = el("button", { type: "button", "aria-label": "Previous month", text: "‹" }); prev.onclick = (ev) => { ev.stopPropagation(); go(-1); };
		const next = el("button", { type: "button", "aria-label": "Next month", text: "›" }); next.onclick = (ev) => { ev.stopPropagation(); go(1); };
		const ms = el("select", { class: "dash-select", "aria-label": "Month" });
		MONTHS.forEach((m, i) => ms.append(new Option(m, String(i + 1))));
		ms.value = String(vm);
		const ys = el("select", { class: "dash-select", "aria-label": "Year" });
		for (let y = 2018; y <= 2030; y++) ys.append(new Option(String(y), String(y)));
		ys.value = String(vy);
		const jump = () => { this.calView = ys.value + "-" + String(ms.value).padStart(2, "0"); this.draw("cal"); };
		ms.onchange = jump; ys.onchange = jump;
		for (const x of [ms, ys]) x.onclick = (ev) => ev.stopPropagation();
		nav.append(prev, ms, ys, next);
		const months = el("div", { class: "ar-months" });
		const narrow = e.clientWidth && e.clientWidth < 460;
		for (let k = 0; k < (narrow ? 1 : 2); k++) {
			const d0 = new Date(Date.UTC(vy, vm - 1 + k, 1));
			const y = d0.getUTCFullYear(), m = d0.getUTCMonth() + 1;
			if (y > 2030) break;
			const box = el("div", { class: "ar-month" }, el("h4", { text: MONTHS[m - 1] + " " + y }));
			const g = el("div", { class: "ar-grid", role: "grid" });
			for (const w of ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]) g.append(el("div", { class: "dow", text: w }));
			const lead = (d0.getUTCDay() + 6) % 7;
			for (let i = 0; i < lead; i++) g.append(el("span"));
			const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
			for (let d = 1; d <= days; d++) {
				const s = iso(y, m, d);
				const cls = ["ar-day"];
				if (s === lo || s === hi) cls.push("edge"); else if (s > lo && s < hi) cls.push("in");
				if (s === today) cls.push("today");
				const bt = el("button", { type: "button", class: cls.join(" "), text: String(d), "aria-label": long(s), disabled: s < MIN || s > MAX });
				bt.onclick = (ev) => {
					ev.stopPropagation();
					if (!this.pickA || this.pickB) { this.pickA = s; this.pickB = null; this.hover = null; this.draw("cal"); }
					else { this.pickB = s; const f = this.pickA; this.pickA = null; this.pickB = null; close(); this.set_range(f, s); }
				};
				bt.onmouseenter = () => { if (this.pickA && !this.pickB && this.hover !== s) { this.hover = s; this.draw("cal"); } };
				g.append(bt);
			}
			box.append(g); months.append(box);
		}
		const hint = el("p", { class: "ar-calhint", text: this.pickA ? "Start: " + long(this.pickA) + ". Now click the end date." : "Click a start date, then an end date. Any day from 2018 to 2030 can be picked." });
		e.replaceChildren(el("div", { class: "ar-cal" }, pre, el("div", null, nav, months, hint)));
	}

	// ---------- customer picker ----------
	mount_cust_list() {
		const e = this.q('[data-draw="cust-list"]');
		const search = el("input", { type: "search", class: "ar-custsearch", placeholder: "Search customers", "aria-label": "Search customers" });
		const all = el("button", { type: "button", class: "ar-chip", text: "Select all" });
		const none = el("button", { type: "button", class: "ar-chip", text: "Clear" });
		const list = el("div", { class: "ar-custlist", role: "listbox", "aria-multiselectable": "true" });
		e.replaceChildren(search, el("div", { class: "ar-custacts" }, all, none), list);
		for (const x of [search, all, none, list]) x.addEventListener("click", (ev) => ev.stopPropagation());
		search.addEventListener("input", () => { this.custSearch = search.value.trim().toLowerCase(); this.render_cust_list(); });
		all.addEventListener("click", () => { this.custSel = null; this.redraw(); });
		none.addEventListener("click", () => { this.custSel = new Set(); this.redraw(); });
		this.cust_list_el = list;
	}
	draw_cust_list() { this.render_cust_list(); }
	render_cust_list() {
		const list = this.cust_list_el;
		if (!list) return;
		if (this.D(this.TT()).status !== "ok") { list.replaceChildren(el("div", { class: "ar-empty", text: "Loading customers…" })); return; }
		const rows = this.visibleTotals().filter((r) => !this.custSearch || r.customer.toLowerCase().includes(this.custSearch));
		list.replaceChildren(...rows.map((r) => {
			const on = !this.custSel || this.custSel.has(r.customer);
			const cb = el("input", { type: "checkbox" }); cb.checked = on;
			const lab = el("label", { class: "ar-custrow" }, cb, el("span", { text: r.customer }), el("span", { class: "amt", text: money(r.closing) }));
			cb.addEventListener("change", () => {
				const names = this.visibleTotals().map((x) => x.customer);
				const set = this.custSel ? new Set(this.custSel) : new Set(names);
				if (cb.checked) set.add(r.customer); else set.delete(r.customer);
				this.custSel = set.size === names.length ? null : set;
				this.redraw();
			});
			return lab;
		}));
		if (!rows.length) list.replaceChildren(el("div", { class: "ar-empty", text: "No customer matches that search." }));
	}

	// ---------- the receivable ledgers ----------
	draw_ledgers(e) {
		const Ld = this.D(this.L()), T = this.D(this.TT()), CMB = this.combined;
		if (Ld.status !== "ok" || T.status !== "ok") {
			const st = Ld.status === "ok" ? T.status : Ld.status;
			e.classList.toggle("dash-skeleton", st === "loading");
			e.replaceChildren(st === "error" ? el("div", { class: "ar-empty ar-glass", text: "The ledgers failed to load from the ERP." }) : document.createTextNode("—"));
			return;
		}
		e.classList.remove("dash-skeleton");
		const sel = this.selectedCustomers();
		if (!sel.length) { e.replaceChildren(el("div", { class: "ar-empty ar-glass", text: CMB && this.multiOnly ? "No selected customer deals with two or more of the companies in this period." : "No customers selected. Open the Customers filter to choose some." })); return; }
		const tot = new Map(T.data.map((r) => [r.customer, r]));
		const byCust = groupBy(Ld.data, (r) => r.customer);
		const openAll = sel.length <= 4;
		const cards = sel.map((name) => {
			const x = tot.get(name), rows = byCust.get(name) || [];
			const det = el("details", { class: "ar-cust ar-glass", id: "ledger-" + name.replace(/[^\p{L}\p{N}]+/gu, "-").toLowerCase() });
			if (openAll) det.open = true;
			const owed = Math.max(0, x.opening + x.invoiced), paid = x.received + x.credit_notes;
			const pct = owed > 0 ? Math.max(0, Math.min(100, (paid / owed) * 100)) : 100;
			const kv = (label, field, cls) => el("span", { class: "kv" + (cls ? " " + cls : "") }, label, el("b", { text: money(x[field]) }));
			const sum = el("summary", null,
				el("span", { class: "nm" }, name, CMB ? el("small", null, ...String(x.companies || "").split(", ").filter(Boolean).map(coChip)) : el("small", { text: x.receivable_account || "Receivable account" })),
				CMB || this.companies.length < 2 ? null : (() => { const b = el("button", { type: "button", class: "ar-combo", text: "Combined ledger", title: "See this customer across all three companies" }); b.addEventListener("click", (ev) => { ev.preventDefault(); ev.stopPropagation(); this.set_combined(true, name); }); return b; })(),
				kv("Opening", "opening"), kv("Invoiced", "invoiced"), kv("Received", "received"), kv("Credit notes and adjustments", "credit_notes"), kv("Closing balance", "closing", "close"),
				el("span", { class: "chev", "aria-hidden": "true", text: "›" }),
				el("span", { class: "ar-bar", role: "img", "aria-label": Math.round(pct) + "% of what was owed has been settled" }, el("i", { style: "width:" + pct.toFixed(1) + "%" })));
			const table = el("table", { class: "ar-t", "aria-label": "Receivable ledger for " + name });
			const head = el("thead", null,
				el("tr", { class: "side" }, el("th", { colspan: CMB ? 5 : 4, class: "dr", text: "Debit: invoices" }), el("th", { colspan: 3, class: "cr spine", text: "Credit: payments and credit notes" }), el("th", { class: "num", text: "" })),
				el("tr", null,
					el("th", { class: "dr", text: "Invoice date" }), CMB ? el("th", { class: "dr", text: "Company" }) : null, el("th", { class: "dr", text: "Invoice number" }), el("th", { class: "dr num", text: "Amount" }), el("th", { class: "dr num", text: "Outstanding" }),
					el("th", { class: "cr spine", text: "Date received" }), el("th", { class: "cr", text: "Received through" }), el("th", { class: "cr num", text: "Amount" }),
					el("th", { class: "num", text: "Balance" })));
			const body = el("tbody");
			for (const r of rows) {
				const tr = el("tr", { class: r.kind === "opening" ? "open" : (r.kind === "more" || r.kind === "prior") ? "cont" : null });
				let invCell;
				if (r.kind === "opening") invCell = el("td", { class: "dr", text: CMB && r.company ? "Opening balance with " + r.company : "Opening balance" });
				else if (r.kind === "invoice") {
					const bt = el("button", { type: "button", class: "ar-inv", text: r.invoice, title: "Show what was sold on this invoice" });
					bt.addEventListener("click", () => this.open_invoice(r.invoice, name, r.company));
					invCell = el("td", { class: "dr" }, bt, r.status ? el("span", { class: "ar-st " + r.status.replace(/\s+/g, ""), text: r.status }) : null);
				} else if (r.kind === "more") invCell = el("td", { class: "dr", text: "more against " + r.ref });
				else invCell = el("td", { class: "dr", text: r.ref && r.ref !== "On account" ? "against " + r.ref : "on account" });
				const ents = Array.isArray(r.entries) ? r.entries : [];
				const ln = (cls, ...kids) => el("div", { class: "ar-line" + (cls ? " " + cls : "") }, ...kids);
				const dCell = el("td", { class: "cr spine" }, ...ents.map((x2) => ln("", short(x2.date))));
				const mCell = el("td", { class: "cr ar-med" }, ...ents.map((x2) => ln("", x2.kind === "credit_note" ? el("span", { class: "ar-st cn", text: "Credit note" }) : x2.kind === "adjustment" ? el("span", { class: "ar-st", text: "Journal entry" }) : (x2.medium || "Payment"),
					el("small", { text: x2.kind === "credit_note" ? x2.doc : [x2.account, x2.doc].filter(Boolean).join(", ") }))));
				const total = r.credit == null ? null : el("span", { text: money(r.credit) });
				const aCell = el("td", { class: "cr num" });
				if (ents.length > 1) for (const x2 of ents) aCell.append(ln("", money(x2.amount)));
				else if (total) aCell.append(total);
				const osd = r.kind === "invoice" ? el("td", { class: "dr num osd " + (Math.abs(r.outstanding || 0) < 0.005 ? "clear" : "due"), text: money(r.outstanding || 0) }) : el("td", { class: "dr num" });
				tr.append(
					el("td", { class: "dr", text: r.kind === "opening" ? short(this.p.from_date) : short(r.inv_date) }),
					CMB ? el("td", { class: "dr" }, r.company ? coChip(r.company) : null) : null,
					invCell,
					el("td", { class: "dr num", text: money(r.debit) }),
					osd, dCell, mCell, aCell,
					el("td", { class: "num bal", text: money(r.balance) }));
				body.append(tr);
			}
			table.append(head, body);
			det.append(sum, el("div", { class: "ar-scroll" }, table));
			return det;
		});
		e.replaceChildren(...cards);
	}

	// ---------- sales detail ----------
	draw_sd_cust(s) {
		const names = this.visibleTotals("ledger_totals").map((r) => r.customer);
		if (this.sdCustomer && !names.includes(this.sdCustomer)) names.push(this.sdCustomer);
		s.replaceChildren(new Option("All customers", ""), ...names.sort((a, b) => a.localeCompare(b)).map((n) => new Option(n, n)));
		s.value = this.sdCustomer || "";
		s.onchange = () => { this.sdCustomer = s.value; this.sdDocs = []; this.p.sd_customer = s.value; this.load_sales(); ["sd-picker", "sd-qty", "sd-amt"].forEach((n) => this.draw(n)); };
	}
	docs_of(type) {
		const p = this.p;
		const src = { si: "si_lines", so: "so_lines", dn: "dn_lines" }[type];
		const dateF = type === "so" ? "transaction_date" : "posting_date";
		const d = this.D(src);
		if (d.status !== "ok") return { status: d.status, docs: [] };
		const m = new Map();
		for (const l of d.data) {
			if (this.sdCustomer && l.customer !== this.sdCustomer) continue;
			if (this.custHidden(l.customer)) continue;
			const dt = l[dateF];
			if (dt < p.from_date || dt > p.to_date) continue;
			if (!m.has(l.name)) m.set(l.name, { name: l.name, date: dt, customer: l.customer });
		}
		return { status: "ok", docs: [...m.values()].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0)) };
	}
	draw_sd_picker(e) {
		const r = this.docs_of(this.sdType);
		if (r.status !== "ok") { e.classList.toggle("dash-skeleton", r.status === "loading"); e.replaceChildren(r.status === "error" ? el("div", { class: "ar-empty", text: "The documents failed to load from the ERP." }) : document.createTextNode("—")); return; }
		e.classList.remove("dash-skeleton");
		const shown = r.docs.filter((d) => !this.search || d.name.toLowerCase().includes(this.search));
		const isOn = (n) => this.sdDocs.some((x) => x.name === n && x.type === this.sdType);
		const redraw = () => ["sd-picker", "sd-qty", "sd-amt"].forEach((n) => this.draw(n));
		const allBt = el("button", { type: "button", class: "ar-chip", text: "Select all shown" });
		allBt.onclick = () => { for (const d of shown) if (!isOn(d.name)) this.sdDocs.push({ type: this.sdType, name: d.name }); redraw(); };
		const clrBt = el("button", { type: "button", class: "ar-chip", text: "Clear selection" });
		clrBt.onclick = () => { this.sdDocs = []; redraw(); };
		const head = el("div", { class: "ar-pickhead" }, el("span", { text: shown.length + " " + LABEL[this.sdType].toLowerCase() + (shown.length === 1 ? "" : "s") + " in the period, " + this.sdDocs.length + " selected" }), allBt, clrBt);
		const list = el("div", { class: "ar-picklist" });
		for (const d of shown.slice(0, 300)) {
			const bt = el("button", { type: "button", class: "ar-pick", "aria-pressed": String(isOn(d.name)) }, d.name, el("small", { text: short(d.date) + (this.sdCustomer ? "" : ", " + d.customer) }));
			bt.onclick = () => { if (isOn(d.name)) this.sdDocs = this.sdDocs.filter((x) => !(x.name === d.name && x.type === this.sdType)); else this.sdDocs.push({ type: this.sdType, name: d.name }); redraw(); };
			list.append(bt);
		}
		if (!shown.length) list.append(el("span", { class: "ar-empty", text: "No " + LABEL[this.sdType].toLowerCase() + " matches in this period." }));
		const others = this.sdDocs.filter((x) => x.type !== this.sdType);
		const extra = others.length ? el("p", { class: "ar-note", text: "Also selected: " + others.map((x) => LABEL[x.type] + " " + x.name).join(", ") }) : null;
		e.replaceChildren(head, list, extra);
	}
	sd_table(e, kind) {
		const S = this.D("strains");
		if (S.status !== "ok") { e.classList.toggle("dash-skeleton", S.status === "loading"); e.replaceChildren(S.status === "error" ? el("div", { class: "ar-empty", text: "This table failed to load from the ERP." }) : document.createTextNode("—")); return; }
		e.classList.remove("dash-skeleton");
		if (!this.sdDocs.length) { e.replaceChildren(el("div", { class: "ar-empty", text: "Select one or more documents above, or click an invoice number in a ledger." })); return; }
		const groups = this.sdDocs.map((d) => ({ ...d, rows: S.data.filter((r) => r.doc === d.name && r.doc_type === d.type) }));
		const strainKeys = [];
		const seen = new Set();
		for (const g of groups) for (const r of g.rows) if (r.strain !== "Total") { const k = r.strain + "|" + r.uom; if (!seen.has(k)) { seen.add(k); strainKeys.push({ strain: r.strain, uom: r.uom }); } }
		strainKeys.sort((a, b) => a.strain.localeCompare(b.strain));
		const f = kind === "qty" ? ["so_qty", "si_qty", "dn_qty"] : ["so_amt", "si_amt", "dn_amt"];
		const fmt = kind === "qty" ? qty : money;
		const top = el("tr", null, el("th", { rowspan: 2, text: "Strain" }), kind === "qty" ? el("th", { rowspan: 2, text: "Unit" }) : null);
		const sub = el("tr");
		for (const g of groups) {
			const t = g.rows.find((r) => r.strain === "Total");
			const rel = t && t.related ? t.related.split(" | ") : ["", "", ""];
			const note = ["Sales order: " + (rel[0] || "none"), "Invoice: " + (rel[1] || "none"), "Delivery note: " + (rel[2] || "none")].join(". ");
			top.append(el("th", { colspan: 3, class: "grp" }, LABEL[g.type] + " " + g.name, el("small", { text: note })));
			sub.append(el("th", { class: "num g0", text: "Sales order" }), el("th", { class: "num", text: "Sales invoice" }), el("th", { class: "num", text: "Delivery note" }));
		}
		const body = el("tbody");
		const cells = (tr, g, row) => {
			const vals = f.map((k) => (row ? row[k] : null));
			const present = vals.filter((v) => v != null);
			const differ = present.length > 1 && present.some((v) => Math.abs(v - present[0]) > 0.005);
			f.forEach((k, i) => {
				const v = vals[i];
				tr.append(el("td", { class: "num" + (i === 0 ? " g0" : "") + (v == null ? " nil" : differ ? " diff" : ""), text: v == null ? "–" : fmt(v) }));
			});
		};
		for (const s of strainKeys) {
			const tr = el("tr", null, el("td", { class: "strain", text: s.strain }), kind === "qty" ? el("td", { text: s.uom }) : null);
			for (const g of groups) cells(tr, g, g.rows.find((r) => r.strain === s.strain && r.uom === s.uom));
			body.append(tr);
		}
		const totTr = el("tr", { class: "tot" }, el("td", { text: "Total" }), kind === "qty" ? el("td", { text: "" }) : null);
		for (const g of groups) cells(totTr, g, g.rows.find((r) => r.strain === "Total"));
		body.append(totTr);
		e.replaceChildren(el("table", { class: "ar-t", "aria-label": kind === "qty" ? "Quantity by strain" : "Amount by strain" }, el("thead", null, top, sub), body));
	}
	draw_sd_qty(e) { this.sd_table(e, "qty"); }
	draw_sd_amt(e) { this.sd_table(e, "amt"); }
}

frappe.pages["receivable-ledgers"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: "Accounts Receivable Report", single_column: true });
	new ReceivableLedgers(page);
};
window.ReceivableLedgers = ReceivableLedgers;
})();
