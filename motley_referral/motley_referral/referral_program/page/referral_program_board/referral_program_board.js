const RPB = "motley_referral.api.board";
const esc = frappe.utils.escape_html;
const num = (n, d = 0) => (Number(n) || 0).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
const usd = n => { const v = Number(n) || 0; return (v < 0 ? "-$" : "$") + num(Math.abs(v), 2); };
const call = (method, args, freeze) => frappe.call({ method: `${RPB}.${method}`, args, freeze: !!freeze }).then(r => r.message);
const TABS = [
    ["overview", "Overview"], ["queue", "Referral Queue"], ["accounts", "Accounts"], ["partners", "Partners"],
    ["ledger", "Commission Ledger"], ["statements", "Statements"], ["expiry", "Window Expiry"], ["ar", "Referred AR"],
];
const BADGE = {
    "Submitted": "grey", "Under Review": "amber", "Acknowledged": "green", "Rejected": "red", "Expired": "dark",
    "Draft": "grey", "Approved": "blue", "Paid": "green", "Carried Forward": "purple", "Cancelled": "red",
    "Active": "green", "Terminated": "red", "Year 1": "green", "Year 2": "blue", "Ended": "dark", "Awaiting first payment": "grey",
};

frappe.pages["referral-program-board"].on_page_load = function (wrapper) {
    new ReferralProgramBoard(wrapper);
};

class ReferralProgramBoard {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Referral Program"), single_column: true });
        this.state = { tab: "overview", filters: { companies: [], partner: "", period: moment().format("YYYY-MM"), from_date: "", to_date: "" },
                       search: "", sort: null, dir: "asc", rows: [], total: 0, totals: {}, columns: [], board: null };
        this.inject_css();
        this.$body = $(`<div class="rpb"></div>`).appendTo(this.page.main);
        this.render_shell();
        $(wrapper).on("show", () => this.on_show());
    }

    on_show() {
        const ro = frappe.route_options;
        if (ro && ro.tab) { this.state.tab = ro.tab; frappe.route_options = null; }
        this.refresh();
    }

    // ------------------------------------------------------------------ shell
    render_shell() {
        this.$body.html(`
        <div class="rpb-card rpb-no-print">
            <div class="rpb-bar">
                <h3 class="rpb-title">${__("Referral Program")}</h3>
                <div class="rpb-filters">
                    <label>${__("Company")}<select class="form-control input-sm f-company" multiple size="1"></select></label>
                    <label>${__("Partner")}<select class="form-control input-sm f-partner"></select></label>
                    <label>${__("Period")}<input type="month" class="form-control input-sm f-period"></label>
                    <label>${__("From")}<input type="date" class="form-control input-sm f-from"></label>
                    <label>${__("To")}<input type="date" class="form-control input-sm f-to"></label>
                </div>
                <div class="rpb-btns">
                    <button class="btn btn-default btn-sm b-refresh">${__("Refresh")}</button>
                    <button class="btn btn-default btn-sm b-run">${__("Run Statements")}</button>
                    <button class="btn btn-default btn-sm b-export">${__("Export Excel")}</button>
                    <button class="btn btn-primary btn-sm b-print">${__("Print")}</button>
                </div>
            </div>
        </div>
        <div class="rpb-kpis"></div>
        <div class="rpb-alerts rpb-no-print"></div>
        <div class="rpb-card">
            <div class="rpb-tabs rpb-no-print"></div>
            <div class="rpb-tools rpb-no-print"><input class="form-control input-sm rpb-search" placeholder="${__("Search")}"></div>
            <div class="rpb-content"></div>
        </div>`);
        const $b = this.$body;
        const sync = () => {
            const f = this.state.filters;
            f.companies = ($b.find(".f-company").val() || []);
            f.partner = $b.find(".f-partner").val() || "";
            f.period = $b.find(".f-period").val() || "";
            f.from_date = $b.find(".f-from").val() || "";
            f.to_date = $b.find(".f-to").val() || "";
        };
        $b.find(".f-period").val(this.state.filters.period);
        $b.on("change", ".f-company,.f-partner,.f-from,.f-to", () => { sync(); this.refresh(); });
        $b.on("change", ".f-period", () => { $b.find(".f-from,.f-to").val(""); sync(); this.refresh(); });
        $b.on("click", ".b-refresh", () => this.refresh());
        $b.on("click", ".b-run", () => this.run_statements_dialog());
        $b.on("click", ".b-export", () => this.export_excel());
        $b.on("click", ".b-print", () => window.print());
        $b.on("input", ".rpb-search", frappe.utils.debounce(e => { this.state.search = e.target.value; this.load_tab(true); }, 300));
        $b.on("click", ".rpb-tab", e => this.set_tab($(e.currentTarget).data("tab")));
        $b.on("click", ".rpb-kpi", e => this.set_tab($(e.currentTarget).data("tab")));
        $b.on("click", ".rpb-alert-link", e => { e.preventDefault(); this.set_tab($(e.currentTarget).data("tab")); });
        $b.on("click", ".rpb-th", e => this.sort_by($(e.currentTarget).data("key")));
        $b.on("click", ".rpb-more", () => this.load_tab(false));
        $b.on("click", "[data-act]", e => this.act($(e.currentTarget)));
    }

    filters_json() { return JSON.stringify({ ...this.state.filters, search: this.state.search }); }

    refresh() {
        this.skeleton(this.$body.find(".rpb-kpis"), 6);
        return call("get_board_data", { filters: JSON.stringify(this.state.filters) }).then(d => {
            this.state.board = d;
            this.fill_filters(d);
            this.render_kpis(d);
            this.render_alerts(d);
            this.render_tabs();
            this.after_tab_change();
        });
    }

    fill_filters(d) {
        const $c = this.$body.find(".f-company"), cur = this.state.filters.companies;
        $c.html(d.companies.map(c => `<option value="${esc(c)}" ${cur.includes(c) ? "selected" : ""}>${esc(c)}</option>`).join(""));
        $c.attr("size", Math.min(Math.max(d.companies.length, 1), 1));
        const $p = this.$body.find(".f-partner");
        $p.html(`<option value="">${__("All partners")}</option>` + d.partners.map(p => `<option value="${esc(p.name)}" ${this.state.filters.partner === p.name ? "selected" : ""}>${esc(p.partner_name)}</option>`).join(""));
    }

    skeleton($el, n) { $el.html(Array.from({ length: n }, () => `<div class="rpb-card rpb-sk"><i></i><b></b></div>`).join("")); }

    // ------------------------------------------------------------------ kpis, alerts
    render_kpis(d) {
        const k = d.kpis;
        const card = (key, tab, label, value, delta, invert) => {
            let dl = "";
            if (delta !== null && delta !== undefined) {
                const up = delta >= 0, good = invert ? !up : up;
                dl = `<span class="rpb-delta ${good ? "good" : "bad"}">${up ? "▲" : "▼"} ${num(Math.abs(delta), 1)}${k[key].delta_abs ? " pt" : "%"} <small>${__("vs previous period")}</small></span>`;
            }
            return `<div class="rpb-card rpb-kpi" data-tab="${tab}"><b>${value}</b><span>${__(label)}</span>${dl}</div>`;
        };
        this.$body.find(".rpb-kpis").html([
            card("active_partners", "partners", "Active Partners", num(k.active_partners.value)),
            card("earning_accounts", "accounts", "Earning Accounts", num(k.earning_accounts.value)),
            card("revenue", "ledger", "Referred Revenue Collected", usd(k.revenue.value), k.revenue.delta),
            card("commission", "ledger", "Commission Earned", usd(k.commission.value), k.commission.delta),
            card("outstanding", "statements", "Commission Outstanding", usd(k.outstanding.value)),
            card("cost_pct", "overview", "Program Cost %", num(k.cost_pct.value, 2) + "%", k.cost_pct.delta, true),
        ].join(""));
    }

    render_alerts(d) {
        const a = d.alerts, items = [];
        const link = (n, tab, text, cls) => n ? `<span class="rpb-alert ${cls}"><a href="#" class="rpb-alert-link" data-tab="${tab}"><b>${n}</b></a> ${text}</span>` : "";
        items.push(link(a.awaiting, "queue", __("referral(s) waiting for acknowledgement"), "warn"));
        items.push(link(a.overdue, "statements", __("statement(s) past due date"), "bad"));
        items.push(link(a.expiring, "expiry", __("window(s) moving to Year 2 or ending in the next 60 days"), "info"));
        const html = items.filter(Boolean).join("");
        this.$body.find(".rpb-alerts").html(html || `<span class="rpb-alert ok">${__("Nothing needs attention right now.")}</span>`);
    }

    // ------------------------------------------------------------------ tabs
    render_tabs() {
        const a = (this.state.board && this.state.board.alerts) || {};
        const badge = { queue: a.awaiting, statements: a.overdue, expiry: a.expiring };
        this.$body.find(".rpb-tabs").html(TABS.map(([k, l]) => `<button class="rpb-tab ${this.state.tab === k ? "on" : ""}" data-tab="${k}">${__(l)}${badge[k] ? ` <span class="rpb-pill">${badge[k]}</span>` : ""}</button>`).join(""));
    }

    set_tab(tab) {
        this.state.tab = tab; this.state.sort = null; this.state.dir = "asc"; this.state.search = "";
        this.$body.find(".rpb-search").val("");
        this.render_tabs();
        this.after_tab_change();
    }

    after_tab_change() {
        const ov = this.state.tab === "overview";
        this.$body.find(".rpb-tools").toggle(!ov);
        if (ov) this.render_overview(); else this.load_tab(true);
    }

    render_overview() {
        const c = this.state.board.charts, $c = this.$body.find(".rpb-content");
        $c.html(`<div class="rpb-grid">
            <div class="rpb-card"><div class="rpb-sec">${__("Referred revenue and commission, last 12 months")}</div><div id="ch-monthly"></div></div>
            <div class="rpb-card"><div class="rpb-sec">${__("Top 10 partners by commission")} <small class="text-muted">${__("(click a bar to filter)")}</small></div><div id="ch-top"></div></div>
            <div class="rpb-card"><div class="rpb-sec">${__("Referrals by status")}</div><div id="ch-ref"></div></div>
            <div class="rpb-card"><div class="rpb-sec">${__("Accounts by window status")}</div><div id="ch-win"></div></div></div>`);
        const mk = (sel, cfg, empty) => {
            const el = $c.find(sel)[0];
            if (empty) { $(el).html(`<div class="rpb-empty text-muted">${__("No data for the selected filters.")}</div>`); return null; }
            return new frappe.Chart(el, { height: 260, ...cfg });
        };
        mk("#ch-monthly", { type: "line", colors: ["#2563eb", "#1B7F4B"], data: { labels: c.monthly.labels, datasets: [{ name: __("Revenue"), values: c.monthly.revenue }, { name: __("Commission"), values: c.monthly.commission }] }, lineOptions: { regionFill: 1, hideDots: 0 }, axisOptions: { xIsSeries: 1 } },
            !c.monthly.revenue.some(Boolean) && !c.monthly.commission.some(Boolean));
        const top = mk("#ch-top", { type: "bar", colors: ["#1B7F4B"], isNavigable: 1, data: { labels: c.top_partners.map(p => p.name), datasets: [{ name: __("Commission"), values: c.top_partners.map(p => Number(p.commission)) }] } }, !c.top_partners.length);
        if (top) $c.find("#ch-top")[0].addEventListener("data-select", e => {
            const p = c.top_partners[e.index]; if (!p) return;
            this.state.filters.partner = p.id; this.$body.find(".f-partner").val(p.id); this.refresh();
        });
        mk("#ch-ref", { type: "donut", data: { labels: c.referral_status.map(r => r.status), datasets: [{ values: c.referral_status.map(r => r.n) }] }, colors: c.referral_status.map(r => ({ Submitted: "#9aa1a9", "Under Review": "#d69e2e", Acknowledged: "#1B7F4B", Rejected: "#c0392b", Expired: "#4b5563" }[r.status] || "#9aa1a9")) }, !c.referral_status.length);
        mk("#ch-win", { type: "donut", data: { labels: c.window_status.map(r => r.status), datasets: [{ values: c.window_status.map(r => r.n) }] }, colors: c.window_status.map(r => ({ "Year 1": "#1B7F4B", "Year 2": "#2563eb", Ended: "#4b5563", "Awaiting first payment": "#9aa1a9" }[r.status] || "#9aa1a9")) }, !c.window_status.length);
    }

    load_tab(reset) {
        const $c = this.$body.find(".rpb-content");
        if (reset) { this.state.rows = []; this.skeleton($c, 4); }
        const tab = this.state.tab;
        return call("get_tab_data", { tab, filters: this.filters_json(), start: reset ? 0 : this.state.rows.length, page_length: 50, sort: this.state.sort, sort_dir: this.state.dir }).then(d => {
            if (tab !== this.state.tab) return;
            this.state.rows = reset ? d.rows : this.state.rows.concat(d.rows);
            this.state.total = d.total; this.state.totals = d.totals; this.state.columns = d.columns;
            this.render_table();
        });
    }

    sort_by(key) {
        if (this.state.sort === key) this.state.dir = this.state.dir === "asc" ? "desc" : "asc"; else { this.state.sort = key; this.state.dir = "asc"; }
        this.load_tab(true);
    }

    // ------------------------------------------------------------------ table
    strip(row) {
        const cur = row.current_month_no || 0, y1 = row.y1 || 12, total = y1 + (row.y2 || 12);
        let h = `<div class="rpb-strip" title="${__("Month {0} of {1}", [cur, total])}">`;
        for (let i = 1; i <= total; i++) h += `<i class="${i <= y1 ? "y1" : "y2"}${i === cur ? " cur" : ""}${row.window_status === "Ended" ? " end" : (i < cur ? " past" : "")}"></i>`;
        return h + `</div><small class="text-muted">${cur ? __("Month {0} of {1}", [cur, total]) : __("Awaiting first payment")}</small>`;
    }

    cell(col, row) {
        const v = row[col.key];
        switch (col.type) {
            case "currency": return usd(v);
            case "int": return v === null || v === undefined ? "" : num(v);
            case "percent": return v === null || v === undefined ? "" : num(v, 2) + "%";
            case "date": return v ? frappe.datetime.str_to_user(v) : "";
            case "badge": return `<span class="rpb-badge ${BADGE[v] || "grey"}">${esc(v || "")}</span>`;
            case "strip": return this.strip(row);
            case "dup": return String(v || "").startsWith("Match")
                ? `<span class="rpb-badge amber" title="${esc(v)}">${__("Match found")}</span>` : `<span class="rpb-badge green">${__("Clear")}</span>`;
            case "customer": return v ? `<a href="/app/customer/${encodeURIComponent(v)}">${esc(v)}</a>` : "";
            case "invoice": return v ? `<a href="/app/sales-invoice/${encodeURIComponent(v)}">${esc(v)}</a>` : "";
            case "voucher": return v ? `<a href="/app/${frappe.router.slug(row.voucher_type || "payment-entry")}/${encodeURIComponent(v)}">${esc(v)}</a>` : "";
            case "statement": return v ? `<a href="/app/referral-commission-statement/${encodeURIComponent(v)}">${esc(v)}</a>` : "";
            case "link": return `<a href="/app/${this.state.tab === "partners" ? "referral-partner" : (this.state.tab === "statements" ? "referral-commission-statement" : "partner-referral")}/${encodeURIComponent(v)}">${esc(v)}</a>`;
            case "due": return v === null || v === undefined ? "" : `<span class="${v < 0 ? "rpb-bad" : ""}">${v < 0 ? __("{0} overdue", [-v]) : v}</span>`;
            case "overdue": return v > 0 ? `<span class="rpb-bad">${v}</span>` : v;
            default: return esc(v === null || v === undefined ? "" : v);
        }
    }

    actions(row) {
        const t = this.state.tab, B = (act, label, cls = "btn-default") => `<button class="btn btn-xs ${cls}" data-act="${act}" data-name="${esc(row.name || "")}" data-extra="${esc(row.purchase_invoice || "")}">${label}</button>`;
        if (t === "queue") return B("ack", __("Acknowledge"), "btn-primary") + B("rej", __("Reject")) + B("open-ref", __("Open"));
        if (t === "accounts" || t === "expiry") return B("open-ref", __("Open referral")) + (t === "accounts" ? ` <button class="btn btn-xs btn-default" data-act="open-cust" data-name="${esc(row.customer)}">${__("Customer")}</button>` : "");
        if (t === "partners") return B("open-partner", __("Open")) + (row.status !== "Active" ? B("activate", __("Activate"), "btn-primary") : B("terminate", __("Terminate")));
        if (t === "statements") {
            let h = "";
            if (row.docstatus === 0 && this.state.board.can_approve) h += B("approve", __("Approve"), "btn-primary");
            if (row.purchase_invoice) h += B("open-pi", __("Purchase Invoice"));
            h += B("open-stmt", __("Open")) + B("print-stmt", __("Print PDF"));
            if (row.docstatus === 1) h += B("email-stmt", __("Email"));
            return h;
        }
        return "";
    }

    render_table() {
        const s = this.state, $c = this.$body.find(".rpb-content"), t = s.tab;
        const hasActions = ["queue", "accounts", "partners", "statements", "expiry"].includes(t);
        if (!s.rows.length) { $c.html(`<div class="rpb-empty text-muted">${__("Nothing to show for the selected filters.")}</div>`); return; }
        const cols = s.columns;
        const head = cols.map(c => `<th class="rpb-th ${c.align === "right" ? "r" : ""}" data-key="${c.key}">${__(c.label)}${s.sort === c.key ? (s.dir === "asc" ? " ▲" : " ▼") : ""}</th>`).join("") + (hasActions ? `<th class="rpb-no-print"></th>` : "");
        let body = "";
        const line = row => `<tr class="${row.is_reversal ? "rpb-rev" : ""}">${cols.map(c => `<td class="${c.align === "right" ? "r" : ""}">${this.cell(c, row)}</td>`).join("")}${hasActions ? `<td class="rpb-act rpb-no-print">${this.actions(row)}</td>` : ""}</tr>`;
        if (t === "ledger" && !s.sort) {
            const groups = {};
            s.rows.forEach(r => { ((groups[r.partner] = groups[r.partner] || {})[r.customer] = groups[r.partner][r.customer] || []).push(r); });
            Object.keys(groups).forEach(p => {
                body += `<tr class="rpb-grp"><td colspan="${cols.length}">${esc(p)}</td></tr>`;
                Object.keys(groups[p]).forEach(cu => {
                    const rs = groups[p][cu];
                    body += rs.map(line).join("");
                    body += `<tr class="rpb-sub"><td colspan="${cols.findIndex(c => c.key === "amount_received")}">${esc(cu)} — ${__("subtotal")}</td><td class="r">${usd(rs.reduce((a, r) => a + r.amount_received, 0))}</td><td class="r">${usd(rs.reduce((a, r) => a + r.commission_amount, 0))}</td></tr>`;
                });
            });
        } else body = s.rows.map(line).join("");
        const tot = Object.keys(s.totals).length ? `<tr class="rpb-total"><td>${__("Total")}</td>${cols.slice(1).map(c => `<td class="${c.align === "right" ? "r" : ""}">${c.key in s.totals ? (c.type === "currency" ? usd(s.totals[c.key]) : num(s.totals[c.key])) : ""}</td>`).join("")}${hasActions ? "<td></td>" : ""}</tr>` : "";
        const more = s.rows.length < s.total ? `<div class="rpb-more-wrap rpb-no-print"><button class="btn btn-default btn-sm rpb-more">${__("Load more")} (${s.rows.length} / ${s.total})</button></div>` : `<div class="text-muted rpb-count">${s.total} ${__("row(s)")}</div>`;
        $c.html(`<div class="rpb-scroll"><table class="rpb-t"><thead><tr>${head}</tr></thead><tbody>${body}${tot}</tbody></table></div>${more}`);
    }

    // ------------------------------------------------------------------ actions
    act($b) {
        const a = $b.data("act"), name = $b.data("name"), row = this.state.rows.find(r => r.name === name) || {};
        const done = msg => { frappe.show_alert({ message: msg, indicator: "green" }); this.refresh(); };
        switch (a) {
            case "open-ref": return frappe.set_route("Form", "Partner Referral", name);
            case "open-cust": return frappe.set_route("Form", "Customer", name);
            case "open-partner": return frappe.set_route("Form", "Referral Partner", name);
            case "open-stmt": return frappe.set_route("Form", "Referral Commission Statement", name);
            case "open-pi": return frappe.set_route("Form", "Purchase Invoice", $b.data("extra"));
            case "print-stmt": return window.open(`/api/method/frappe.utils.print_format.download_pdf?doctype=${encodeURIComponent("Referral Commission Statement")}&name=${encodeURIComponent(name)}&format=${encodeURIComponent("Referral Commission Statement")}`);
            case "email-stmt": return call("email_statement", { name }, true).then(() => done(__("Statement emailed")));
            case "approve": return frappe.confirm(__("Approve statement {0}? A Purchase Invoice is created unless the amount is carried forward.", [name]), () => call("approve_statement", { name }, true).then(() => done(__("Statement approved"))));
            case "activate": return frappe.confirm(__("Activate this partner? A portal user and Supplier will be created and the set-password email sent."), () => call("activate_partner", { name }, true).then(() => done(__("Partner activated"))));
            case "terminate": return frappe.prompt({ fieldname: "d", label: __("Termination Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
                v => call("terminate_partner", { name, termination_date: v.d }, true).then(() => done(__("Partner terminated"))), __("Terminate Partner"), __("Terminate"));
            case "ack": return this.ack_dialog(name, row);
            case "rej": return this.reject_dialog(name);
        }
    }

    ack_dialog(name, row) {
        const d = new frappe.ui.Dialog({
            title: __("Acknowledge {0}", [row.business_name || name]),
            fields: [
                { fieldname: "mode", label: __("Customer"), fieldtype: "Select", options: "Link existing customer\nCreate new customer", default: "Link existing customer" },
                { fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer", depends_on: "eval:doc.mode=='Link existing customer'", mandatory_depends_on: "eval:doc.mode=='Link existing customer'" },
                { fieldname: "info", fieldtype: "HTML", options: `<p class="text-muted">${__("A new customer is created from the business name.")}</p>`, depends_on: "eval:doc.mode=='Create new customer'" },
            ],
            primary_action_label: __("Acknowledge"),
            primary_action: v => call("acknowledge_referral", { name, customer: v.mode === "Link existing customer" ? v.customer : null, create_customer: v.mode === "Create new customer" ? 1 : 0 }, true)
                .then(() => { d.hide(); frappe.show_alert({ message: __("Referral acknowledged. The letter was generated and emailed."), indicator: "green" }); this.refresh(); }),
        });
        d.show();
    }

    reject_dialog(name) {
        const d = new frappe.ui.Dialog({
            title: __("Reject Referral"),
            fields: [
                { fieldname: "reason", label: __("Reason"), fieldtype: "Select", options: "Existing customer\nAlready in pipeline\nNot a fit\nOther", reqd: 1 },
                { fieldname: "note", label: __("Note"), fieldtype: "Small Text", mandatory_depends_on: "eval:doc.reason=='Other'" },
            ],
            primary_action_label: __("Reject"),
            primary_action: v => call("reject_referral", { name, reason: v.reason, note: v.note }, true).then(() => { d.hide(); this.refresh(); }),
        });
        d.show();
    }

    run_statements_dialog() {
        const d = new frappe.ui.Dialog({
            title: __("Run Commission Statements"),
            fields: [{ fieldname: "period", label: __("Period (month)"), fieldtype: "Data", default: moment().subtract(1, "month").format("YYYY-MM"), reqd: 1, description: __("Format YYYY-MM. Creates one Draft statement per partner and company.") }],
            primary_action_label: __("Run"),
            primary_action: v => call("run_statements", { period: v.period }, true).then(n => { d.hide(); frappe.show_alert({ message: __("{0} statement(s) created", [n]), indicator: "green" }); this.set_tab("statements"); this.refresh(); }),
        });
        d.show();
    }

    export_excel() {
        if (this.state.tab === "overview") return frappe.msgprint(__("Select a data tab to export."));
        window.open(`/api/method/${RPB}.export_tab?tab=${this.state.tab}&filters=${encodeURIComponent(this.filters_json())}`);
    }

    // ------------------------------------------------------------------ css
    inject_css() {
        if (document.getElementById("rpb-css")) return;
        $(`<style id="rpb-css">
        .rpb{display:flex;flex-direction:column;gap:14px;padding:8px 0 40px}
        .rpb-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--border-radius-lg);padding:14px 16px}
        .rpb-bar{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;justify-content:space-between}
        .rpb-title{margin:0;font-weight:700}.rpb-filters{display:flex;flex-wrap:wrap;gap:8px}.rpb-filters label{display:flex;flex-direction:column;font-size:11px;color:var(--text-muted);margin:0;font-weight:600}
        .rpb-filters .form-control{width:auto;min-width:130px}.rpb-btns{display:flex;gap:6px;flex-wrap:wrap}
        .rpb-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
        .rpb-kpi{cursor:pointer;display:flex;flex-direction:column;gap:2px}.rpb-kpi:hover{border-color:var(--primary)}.rpb-kpi b{font-size:24px}.rpb-kpi span{font-size:12px;color:var(--text-muted)}
        .rpb-delta{font-size:12px;font-weight:600}.rpb-delta small{font-weight:400;color:var(--text-muted)}.rpb-delta.good{color:var(--green-600,#1B7F4B)}.rpb-delta.bad{color:var(--red-600,#b42318)}
        .rpb-alerts{display:flex;flex-wrap:wrap;gap:8px}.rpb-alert{padding:6px 12px;border-radius:var(--border-radius-md);font-size:13px;border:1px solid var(--border-color);background:var(--card-bg)}
        .rpb-alert.warn{border-left:4px solid #d69e2e}.rpb-alert.bad{border-left:4px solid #c0392b}.rpb-alert.info{border-left:4px solid #2563eb}.rpb-alert.ok{border-left:4px solid #1B7F4B;color:var(--text-muted)}
        .rpb-tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}.rpb-tab{border:1px solid var(--border-color);background:var(--card-bg);border-radius:var(--border-radius-md);padding:6px 12px;color:var(--text-color)}
        .rpb-tab.on{background:var(--primary);border-color:var(--primary);color:#fff}.rpb-pill{background:#c0392b;color:#fff;border-radius:99px;padding:0 7px;font-size:11px;margin-left:4px}
        .rpb-tools{margin-bottom:10px}.rpb-search{max-width:320px}
        .rpb-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:12px}.rpb-sec{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px}
        .rpb-scroll{overflow:auto;max-height:70vh}.rpb-t{width:100%;border-collapse:separate;border-spacing:0;min-width:900px}
        .rpb-t th{position:sticky;top:0;background:var(--control-bg);font-size:11px;text-transform:uppercase;color:var(--text-muted);padding:8px;text-align:left;cursor:pointer;white-space:nowrap;z-index:1}
        .rpb-t td{padding:8px;border-top:1px solid var(--border-color);vertical-align:middle}.rpb .r{text-align:right!important}
        .rpb-act{white-space:nowrap}.rpb-act .btn{margin-right:4px}.rpb-total td{font-weight:700;background:var(--control-bg)}.rpb-grp td{font-weight:700;background:var(--control-bg);color:var(--primary)}
        .rpb-sub td{font-weight:600;font-size:12px;color:var(--text-muted)}.rpb-rev td{color:var(--red-600,#b42318)}.rpb-bad{color:var(--red-600,#b42318);font-weight:600}
        .rpb-badge{display:inline-block;padding:2px 9px;border-radius:99px;font-size:11px;font-weight:600;color:#fff;background:#9aa1a9;white-space:nowrap}
        .rpb-badge.green{background:#1B7F4B}.rpb-badge.red{background:#c0392b}.rpb-badge.amber{background:#d69e2e}.rpb-badge.blue{background:#2563eb}.rpb-badge.purple{background:#7c3aed}.rpb-badge.dark{background:#4b5563}
        .rpb-strip{display:flex;gap:1px;min-width:200px}.rpb-strip i{flex:1;height:10px;border-radius:2px;background:#cfe8da}.rpb-strip i.y2{background:#c7d7f7}
        .rpb-strip i.past.y1{background:#1B7F4B}.rpb-strip i.past.y2{background:#2563eb}.rpb-strip i.cur{background:#d69e2e!important;outline:1px solid #7a5c10}.rpb-strip i.end{background:#9aa1a9}
        .rpb-empty{padding:28px;text-align:center}.rpb-more-wrap{text-align:center;margin-top:10px}.rpb-count{margin-top:8px;font-size:12px}
        .rpb-sk{height:80px;position:relative;overflow:hidden}.rpb-sk i,.rpb-sk b{display:block;height:10px;border-radius:4px;background:var(--control-bg);margin-bottom:10px;animation:rpbp 1.2s infinite}.rpb-sk b{height:22px;width:50%}
        @keyframes rpbp{0%,100%{opacity:.5}50%{opacity:1}}
        @media print{.rpb-no-print,.page-head,.navbar,.layout-side-section{display:none!important}.rpb-scroll{max-height:none;overflow:visible}.rpb-card{break-inside:avoid;border-color:#ccc}}
        </style>`).appendTo(document.head);
    }
}
