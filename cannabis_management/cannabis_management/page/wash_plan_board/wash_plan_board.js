const WPB = "cannabis_management.cannabis_management.page.wash_plan_board.wash_plan_board";
const WPP = "cannabis_management.cannabis_management.doctype.wash_production_plan.wash_production_plan";
const esc = frappe.utils.escape_html;
const num = (n, d = 0) => (Number(n) || 0).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
const call = (method, args, freeze) => frappe.call({ method, args, freeze: !!freeze }).then(r => r.message);

frappe.pages["wash-plan-board"].on_page_load = function (wrapper) {
    new WashPlanBoard(wrapper);
};

class WashPlanBoard {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Wash Plan Board"), single_column: true });
        this.state = { plan: null, data: null, day: "all", freezer: "all", expanded: {}, add: { date: "", item: "", freezer: "", project: "", lbs: 50 } };
        this.$body = $(`<div class="wpb"></div>`).appendTo(this.page.main);
        this.inject_css();
        this.setup_toolbar();
        this.bind();
        $(wrapper).on("show", () => this.on_show());
    }

    on_show() {
        const r = frappe.get_route();
        this.refresh_plans(r[1]);
    }

    setup_toolbar() {
        this.plan_field = this.page.add_field({
            fieldname: "plan", label: __("Plan"), fieldtype: "Select", options: [],
            change: () => { const v = this.plan_field.get_value(); if (v && v !== this.state.plan) this.open(v); },
        });
        this.page.set_primary_action(__("New Plan"), () => this.new_plan_dialog(), "add");
        this.page.add_inner_button(__("Open Plan Form"), () => this.state.plan && frappe.set_route("Form", "Wash Production Plan", this.state.plan));
    }

    refresh_plans(preferred) {
        return call(`${WPB}.list_plans`).then(plans => {
            const names = plans.map(p => p.name);
            if (preferred && !names.includes(preferred)) names.unshift(preferred);
            this.plan_field.df.options = names.join("\n");
            this.plan_field.refresh();
            const pick = preferred || this.state.plan || names[0];
            if (pick) { this.plan_field.set_input(pick); this.open(pick); }
            else this.$body.html(`<div class="wpb-empty text-muted">${__("No open plans. Use New Plan to start one.")}</div>`);
        });
    }

    open(plan) {
        this.state.plan = plan; this.state.day = "all"; this.state.expanded = {};
        frappe.route_options = null;
        return this.load();
    }

    load() {
        return call(`${WPB}.get_board`, { plan: this.state.plan }).then(d => {
            this.state.data = d;
            const days = this.days();
            if (!this.state.add.date || !days.includes(this.state.add.date)) this.state.add.date = days[0] || "";
            this.render();
        });
    }

    // run a server write, then reload the board; validation errors are shown by frappe
    act(method, args, msg) {
        return call(method, args, true).then(r => { if (msg) frappe.show_alert({ message: msg, indicator: "green" }); return this.load().then(() => r); },
            () => this.load());
    }

    days() {
        const p = this.state.data && this.state.data.plan, out = [];
        if (!p) return out;
        let d = moment(p.from_date); const end = moment(p.to_date);
        while (d <= end && out.length < 62) { out.push(d.format("YYYY-MM-DD")); d = d.add(1, "day"); }
        return out;
    }

    new_plan_dialog() {
        const d = new frappe.ui.Dialog({
            title: __("New Wash Production Plan"),
            fields: [
                { fieldname: "plan_type", label: __("Plan Type"), fieldtype: "Select", options: "Daily\nWeekly\nCustom", default: "Weekly", reqd: 1 },
                { fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
                { fieldname: "to_date", label: __("To Date"), fieldtype: "Date", depends_on: "eval:doc.plan_type=='Custom'" },
            ],
            primary_action_label: __("Create"),
            primary_action: v => call(`${WPB}.new_plan`, v, true).then(name => { d.hide(); this.refresh_plans(name); }),
        });
        d.show();
    }

    in_scope(rows) {
        const s = this.state;
        return rows.filter(r => (s.day === "all" || r.planned_date === s.day) && (s.freezer === "all" || r.freezer === s.freezer));
    }

    // ---------- rendering ----------
    render() {
        const { plan, rows, summary, stock, defaults } = this.state.data;
        const scoped = this.in_scope(rows), days = this.days(), s = this.state;
        const ro = !plan.writable;
        const tot = scoped.reduce((a, r) => ({ w: a.w + 1, l: a.l + (+r.lbs || 0), h: a.h + (+r.expected_hash_g || 0), r: a.r + (+r.expected_rosin_g || 0), done: a.done + (["Washed", "Completed"].includes(r.status) ? 1 : 0) }), { w: 0, l: 0, h: 0, r: 0, done: 0 });
        const eligible = scoped.filter(r => !r.block_reason);
        const ind = { Draft: "gray", "In Progress": "orange", Completed: "green", Cancelled: "red" }[plan.status] || "gray";
        const dl = k => moment(k).format("ddd, MMM D");
        let h = "";

        h += `<div class="wpb-card"><div class="wpb-head"><div><h3 class="wpb-title">${esc(plan.name)} <span class="indicator-pill ${ind}">${esc(__(plan.status))}</span></h3>
          <div class="text-muted small">${esc(__("Plan period"))}: <b>${esc(dl(plan.from_date))} – ${esc(dl(plan.to_date))}, ${moment(plan.to_date).year()}</b></div></div>
          <div class="wpb-period"><div class="btn-group" role="group">${["Daily", "Weekly", "Custom"].map(t => `<button class="btn btn-sm ${plan.plan_type === t ? "btn-primary" : "btn-default"}" data-a="ptype" data-v="${t}" ${ro ? "disabled" : ""}>${__(t)}</button>`).join("")}</div>
          ${plan.plan_type === "Custom" ? `<input type="date" class="form-control input-sm" data-c="from" value="${esc(plan.from_date)}" ${ro ? "disabled" : ""}> <input type="date" class="form-control input-sm" data-c="to" value="${esc(plan.to_date)}" ${ro ? "disabled" : ""}>` : `<input type="date" class="form-control input-sm" data-c="from" value="${esc(plan.from_date)}" ${ro ? "disabled" : ""}>`}</div></div>
          <div class="wpb-sec">${__("Project Summary")}</div><div class="wpb-cards">${summary.length ? summary.map(g => `<div class="wpb-pc"><b>${esc(g.project ? g.name || g.project : __("No Project"))}</b><div class="text-muted small">${esc(g.project || __("MR project left empty"))}</div>
            <div>${g.washes} ${g.washes === 1 ? __("wash") : __("washes")} · <b>${num(g.lbs)} lbs</b></div><div class="text-muted small">${__("Exp. hash")} ${num(g.hash)} g · ${__("rosin")} ${num(g.rosin)} g</div></div>`).join("") : `<span class="text-muted">${__("No washes in this plan yet.")}</span>`}</div></div>`;

        h += `<div class="wpb-tabs">${[["all", plan.plan_type === "Weekly" ? __("All week") : __("All days"), rows.length]].concat(days.length <= 14 ? days.map(d => [d, moment(d).format("ddd") + " " + moment(d).format("D"), rows.filter(r => r.planned_date === d).length]) : []).map(([k, l, c]) =>
            `<button class="wpb-tab ${s.day === k ? "on" : ""}" data-a="day" data-v="${k}"><b>${esc(l)}</b><span>${c} ${c === 1 ? __("wash") : __("washes")}</span></button>`).join("")}</div>`;

        h += `<div class="wpb-kpis">${[[__("Total Washes"), tot.w, `${tot.done} ${__("washed")} · ${tot.w - tot.done} ${__("still to run")}`], [__("Planned Fresh Frozen"), num(tot.l) + " lbs", num(tot.l * 0.453592) + " kg"],
            [__("Expected Bubble Hash"), num(tot.h) + " g", `${__("Default yield")} ${defaults.hash}%`], [__("Expected Rosin"), num(tot.r) + " g", `${__("Default yield")} ${defaults.rosin}% ${__("of hash")}`]].map(k =>
            `<div class="wpb-card wpb-kpi"><span class="text-muted small">${k[0]}</span><b>${k[1]}</b><span class="text-muted small">${k[2]}</span></div>`).join("")}</div>`;

        h += `<div class="wpb-card"><div class="wpb-head"><div><h4 class="wpb-h">${__("Planned Washes")}</h4><span class="text-muted small">${tot.w} ${tot.w === 1 ? __("wash") : __("washes")}</span></div>
          <div class="wpb-period"><select class="form-control input-sm" data-c="freezer"><option value="all">${__("All freezers")}</option>${[...new Set(stock.map(f => f.freezer))].map(f => `<option ${s.freezer === f ? "selected" : ""}>${esc(f)}</option>`).join("")}</select>
          <button class="btn btn-sm btn-primary" data-a="bulk" ${!eligible.length || ro ? "disabled" : ""}>${__("Create MRs for {0} planned washes", [eligible.length])}</button></div></div>`;
        h += `<div class="wpb-scroll"><table class="wpb-t"><thead><tr><th></th><th>${__("Date")}</th><th>${__("Strain / Freezer")}</th><th>${__("Project")}</th><th class="r">${__("Available")}</th><th>${__("Planned (lbs)")}</th><th class="r">${__("Exp. Hash")}</th><th class="r">${__("Exp. Rosin")}</th><th>${__("Status")}</th><th>${__("Actions")}</th></tr></thead><tbody>`;
        if (!scoped.length) h += `<tr><td colspan="10" class="text-muted wpb-empty">${__("No washes match this period and freezer. Use Add a Wash below.")}</td></tr>`;
        scoped.forEach(r => h += this.row_html(r, ro));
        h += `</tbody></table></div></div>`;

        h += `<div class="wpb-bottom">${this.add_html(ro)}${this.stock_html(stock)}</div>`;
        this.$body.html(h);
        this.mount_item_control(ro);
        this.refresh_preview();
    }

    row_html(r, ro) {
        const planned = r.status === "Planned", over = planned && r.over_by > 0, ex = !!this.state.expanded[r.name];
        const pill = { Planned: "gray", "MR Created": "blue", Washed: "orange", Completed: "green", Skipped: "red" }[r.status] || "gray";
        const cur = (r.freezers.find(f => f.warehouse === r.freezer) || { projects: [] }).projects;
        const projOpts = cur.map(p => ({ v: p.project, l: `${p.project ? p.project : __("No Project")} · ${num(p.qty, 1)} lbs` }));
        if (!projOpts.some(o => o.v === r.project)) projOpts.unshift({ v: r.project, l: r.project || __("Select project") });
        const sel = (cls, opts, val, dis) => `<select class="form-control input-sm" data-c="${cls}" data-id="${r.name}" ${dis ? "disabled" : ""}>${opts.map(o => `<option value="${esc(o.v)}" ${o.v === val ? "selected" : ""}>${esc(o.l)}</option>`).join("")}</select>`;
        const fzOpts = r.freezers.map(f => ({ v: f.warehouse, l: `${f.warehouse} · ${num(f.qty, 1)} lbs` }));
        if (!fzOpts.some(o => o.v === r.freezer)) fzOpts.unshift({ v: r.freezer, l: r.freezer });
        let h = `<tr class="${over ? "wpb-over" : ""}"><td><button class="btn btn-xs btn-default" data-a="toggle" data-id="${r.name}" aria-expanded="${ex}" title="${__("Finished goods")}">${ex ? "▾" : "▸"}</button></td>
          <td><b>${esc(moment(r.planned_date).format("ddd"))}</b><div class="text-muted small">${esc(moment(r.planned_date).format("MMM D, YYYY"))}</div></td>
          <td><b>${esc(r.item_name || r.item)}</b><div>${planned && !ro ? sel("rfreezer", fzOpts, r.freezer) : `<span class="text-muted small">${esc(r.freezer)}</span>`}</div>
            ${over ? `<div class="wpb-warn">${__("Exceeds stock in {0} by {1} lbs", [esc(r.freezer), num(r.over_by, 1)])}</div>` : ""}
            ${over && r.held_by.length ? `<div class="wpb-warn small">${__("Held by")}: ${r.held_by.map(esc).join("; ")}</div>` : ""}
            ${planned && !over && r.block_reason ? `<div class="wpb-warn small">${esc(r.block_reason)}</div>` : ""}</td>
          <td>${planned && !ro ? sel("rproject", projOpts, r.project) : `<b>${esc(r.project ? r.project_name || r.project : __("No Project"))}</b><div class="text-muted small">${esc(r.project || __("MR project left empty"))}</div>`}</td>
          <td class="r">${num(r.available, 1)}</td>
          <td>${planned && !ro ? `<div class="wpb-qty"><button class="btn btn-xs btn-default" data-a="dec" data-id="${r.name}">−</button><input type="number" min="0" step="5" class="form-control input-sm" data-c="rqty" data-id="${r.name}" value="${esc(r.lbs)}"><button class="btn btn-xs btn-default" data-a="inc" data-id="${r.name}">+</button></div>` : `<b>${num(r.lbs)} lbs</b>`}</td>
          <td class="r">${num(r.expected_hash_g)} g</td><td class="r">${num(r.expected_rosin_g)} g${r.status === "Washed" || r.status === "Completed" ? `<div class="text-muted small">${__("Actual hash")} ${num(r.actual_hash_g)} g</div>` : ""}</td>
          <td><span class="indicator-pill ${pill}">${esc(__(r.status))}</span><div class="small">${r.mr ? `<a href="/app/material-request/${encodeURIComponent(r.mr)}">${esc(r.mr)}</a>` : "—"}</div>
            <div class="small">${[r.hash_wo, r.rosin_wo].filter(Boolean).map(x => `<a href="/app/work-order/${encodeURIComponent(x)}">${esc(x)}</a>`).join(" · ")}</div></td>
          <td class="wpb-act">${planned && !ro ? `<button class="btn btn-xs btn-default" data-a="mr" data-id="${r.name}" ${r.block_reason ? "disabled" : ""} title="${esc(r.block_reason || "")}">${__("Create MR")}</button> <button class="btn btn-xs btn-default" data-a="remove" data-id="${r.name}" title="${__("Remove from plan")}">✕</button>` : ""}</td></tr>`;
        if (ex) {
            h += `<tr><td></td><td colspan="9"><div class="wpb-fg"><div class="wpb-fgh"><b>${__("Finished Goods")}</b><span class="text-muted small">${planned ? __("Copied to the MR Finished Goods table on Create MR") : __("Sent to the Finished Goods table of {0}", [esc(r.mr || "")])}</span></div>
              <table class="wpb-t"><thead><tr><th>${__("Operation")}</th><th>${__("Finished Item")}</th><th>${__("Item Group")}</th><th class="r">${__("Exp. Yield")}</th><th class="r">${__("Exp. Qty (g)")}</th><th class="r">${__("Actual Yield")}</th><th class="r">${__("Actual (g)")}</th></tr></thead><tbody>`;
            r.finished_goods.forEach(g => h += `<tr><td><b>${esc(__(g.operation))}</b></td><td>${g.item ? `<span class="mono">${esc(g.item)}</span><div class="text-muted small">${esc(g.item_name)}</div>` : `<span class="wpb-warn small">${__("Not created yet")}</span> ${planned && !ro ? `<button class="btn btn-xs btn-default" data-a="mkitem" data-id="${r.name}" data-k="${g.kind}">${__("Create Item")}</button>` : ""}`}</td>
              <td>${esc(g.item_group || "")}</td><td class="r">${num(g.expected_yield, 2)}%</td><td class="r">${num(g.expected_g)}</td><td class="r">${g.actual_yield == null ? "—" : num(g.actual_yield, 2) + "%"}</td><td class="r">${g.actual_g == null ? "—" : num(g.actual_g)}</td></tr>`);
            h += `</tbody></table><div class="text-muted small">${planned ? __("No BOM is needed at planning time. BOMs for these items are created automatically when the Material Request is submitted.") : __("BOMs for these items were created automatically when {0} was submitted.", [esc(r.mr || "")])}</div></div></td></tr>`;
        }
        return h;
    }

    add_html(ro) {
        const a = this.state.add, days = this.days();
        return `<div class="wpb-card wpb-add"><h4 class="wpb-h">${__("Add a Wash")}</h4><span class="text-muted small">${__("Project comes from the stock: one project is set automatically.")}</span>
          <div class="wpb-form"><label>${__("Planned Date")}<select class="form-control input-sm" data-c="adate" ${ro ? "disabled" : ""}>${days.map(d => `<option value="${d}" ${d === a.date ? "selected" : ""}>${esc(moment(d).format("ddd, MMM D"))}</option>`).join("")}</select></label>
          <label>${__("Planned Qty (lbs)")}<input type="number" min="0" step="5" class="form-control input-sm" data-c="albs" value="${esc(a.lbs)}" ${ro ? "disabled" : ""}></label>
          <label class="wide">${__("Fresh Frozen Item")}<div class="wpb-item"></div></label>
          <label>${__("Source Freezer")}<select class="form-control input-sm" data-c="afreezer" ${ro ? "disabled" : ""}></select></label>
          <label>${__("Project")}<select class="form-control input-sm" data-c="aproject" ${ro ? "disabled" : ""}></select></label></div>
          <div class="wpb-prev text-muted"></div><button class="btn btn-primary btn-sm" data-a="add" ${ro ? "disabled" : ""}>${__("Add to Plan")}</button></div>`;
    }

    stock_html(stock) {
        let h = `<div class="wpb-card wpb-stock"><h4 class="wpb-h">${__("Freezer Stock vs Plan")}</h4><span class="text-muted small">${__("Booked by this plan, per item and project, against the stock ledger.")}</span>`;
        stock.forEach(f => {
            h += `<div class="wpb-fz"><div class="wpb-fzh"><b>${esc(f.freezer)}</b><span class="text-muted small">${num(f.booked, 1)} / ${num(f.balance, 1)} lbs ${__("booked")}</span></div>`;
            if (!f.items.length) h += `<div class="text-muted small">${__("No fresh frozen stock.")}</div>`;
            f.items.forEach(i => {
                const over = i.booked > i.balance + 1e-6, pct = i.balance > 0 ? Math.min(100, i.booked / i.balance * 100) : 100;
                h += `<div class="wpb-bar"><div class="wpb-barh"><span>${esc(i.item_name)} <span class="text-muted small">· ${esc(i.project || __("No Project"))}</span></span><span class="text-muted small">${num(i.booked, 1)} / ${num(i.balance, 1)} lbs</span></div>
                  <div class="wpb-track"><div class="${over ? "over" : ""}" style="width:${pct}%"></div></div><span class="small ${over ? "wpb-warn" : "text-muted"}">${over ? __("Over-booked by {0} lbs", [num(i.booked - i.balance, 1)]) : __("{0} lbs free to plan", [num(i.balance - i.booked, 1)])}</span></div>`;
            });
            h += `</div>`;
        });
        return h + `</div>`;
    }

    // ---------- Add a Wash ----------
    mount_item_control(ro) {
        const $host = this.$body.find(".wpb-item");
        if (!$host.length) return;
        this.item_ctl = frappe.ui.form.make_control({
            parent: $host, df: { fieldtype: "Link", options: "Item", fieldname: "item", placeholder: __("Select a fresh frozen item"), read_only: ro ? 1 : 0,
                get_query: () => ({ filters: { item_group: ["descendants of (inclusive)", this.state.data.defaults.ff_group] } }),
                change: () => this.on_item(this.item_ctl.get_value()) },
            render_input: true,
        });
        // the Link control only reports a change after its own async validation; also react to the pick itself
        this.item_ctl.$input.on("awesomplete-selectcomplete change", () => setTimeout(() => this.on_item((this.item_ctl.get_value() || this.item_ctl.$input.val() || "").trim()), 50));
        if (this.state.add.item) this.item_ctl.set_value(this.state.add.item);
        this.fill_freezers();
    }

    on_item(item) {
        console.log("WPBDBG on_item", item, this.state.add.item);
        const a = this.state.add;
        if (item === a.item) return;
        a.item = item || ""; a.freezer = ""; a.project = "";
        this.opts = null;
        if (!item) { this.fill_freezers(); return this.refresh_preview(); }
        call(`${WPB}.get_item_options`, { item }).then(o => { this.opts = o; if (o.length === 1) a.freezer = o[0].warehouse; this.pick_project(); this.fill_freezers(); this.refresh_preview(); });
    }

    pick_project() {
        const a = this.state.add, f = (this.opts || []).find(x => x.warehouse === a.freezer);
        a.project = f && f.projects.length === 1 ? f.projects[0].project : "";
    }

    fill_freezers() {
        const a = this.state.add, o = this.opts || [];
        this.$body.find("[data-c=afreezer]").html(`<option value="">${o.length ? __("Select freezer") : __("Select an item first")}</option>` + o.map(f => `<option value="${esc(f.warehouse)}" ${f.warehouse === a.freezer ? "selected" : ""}>${esc(f.warehouse)} · ${num(f.qty, 1)} lbs</option>`).join(""));
        const f = o.find(x => x.warehouse === a.freezer), p = f ? f.projects : [];
        this.$body.find("[data-c=aproject]").html((p.length > 1 || !p.length ? `<option value="">${p.length ? __("Select project") : "—"}</option>` : "") + p.map(x => `<option value="${esc(x.project)}" ${x.project === a.project ? "selected" : ""}>${esc(x.project || __("No Project"))} · ${num(x.qty, 1)} lbs</option>`).join(""));
    }

    refresh_preview() {
        const a = this.state.add, $p = this.$body.find(".wpb-prev");
        if (!a.item || !a.freezer) return $p.text(__("Choose an item and freezer to see the expected yield and free stock."));
        call(`${WPB}.preview_row`, { item: a.item, freezer: a.freezer, project: a.project, lbs: a.lbs, plan: this.state.plan }).then(p => {
            const s = p.suggest;
            $p.html(`${__("Exp. hash")} <b>${num(p.expected_hash_g)} g</b> · ${__("Exp. rosin")} <b>${num(p.expected_rosin_g)} g</b> · ${__("Free in this freezer and project")} <b>${num(p.free, 1)} lbs</b><br>
              ${__("Bubble Hash item")} <b>${esc(s.bubble_hash_item || __("Not created yet"))}</b> · ${__("Rosin item")} <b>${esc(s.rosin_item || __("Not created yet"))}</b>
              ${p.holders.length ? `<br><span class="wpb-warn small">${__("Held by")}: ${p.holders.map(esc).join("; ")}</span>` : ""}`);
        });
    }

    // ---------- events ----------
    bind() {
        const rowQty = (id, delta) => { const r = this.state.data.rows.find(x => x.name === id); return Math.max(0, (+r.lbs || 0) + delta); };
        this.$body.on("click", "[data-a]", e => {
            const $b = $(e.currentTarget), a = $b.data("a"), id = $b.data("id"), s = this.state, plan = s.plan;
            if ($b.prop("disabled")) return;
            const w = {
                day: () => { s.day = $b.data("v"); if (s.day !== "all") s.add.date = s.day; this.render(); },
                toggle: () => { s.expanded[id] = !s.expanded[id]; this.render(); },
                ptype: () => { const p = s.data.plan, t = $b.data("v"); this.act(`${WPB}.update_period`, { plan, plan_type: t, from_date: p.from_date, to_date: t === "Custom" ? p.to_date : null }); },
                inc: () => this.act(`${WPB}.update_row`, { plan, row: id, values: { planned_qty_lbs: rowQty(id, 5) } }),
                dec: () => this.act(`${WPB}.update_row`, { plan, row: id, values: { planned_qty_lbs: rowQty(id, -5) } }),
                mr: () => this.make_mrs([id]),
                bulk: () => this.make_mrs(this.in_scope(s.data.rows).filter(r => !r.block_reason).map(r => r.name)),
                remove: () => frappe.confirm(__("Remove this wash from the plan?"), () => this.act(`${WPB}.remove_row`, { plan, row: id }, __("Wash removed."))),
                mkitem: () => this.act(`${WPB}.create_finished_item`, { plan, row: id, kind: $b.data("k") }, __("Item created.")),
                add: () => {
                    const a = s.add;
                    if (!a.item || !a.freezer) return frappe.msgprint(__("Select a fresh frozen item and a source freezer."));
                    this.act(`${WPB}.add_row`, { plan, planned_date: a.date, item: a.item, freezer: a.freezer, lbs: a.lbs, project: a.project }, __("Wash added to the plan."));
                },
            }[a];
            if (w) w();
        });
        this.$body.on("change", "[data-c]", e => {
            const $i = $(e.currentTarget), c = $i.data("c"), id = $i.data("id"), v = $i.val(), s = this.state, plan = s.plan;
            const upd = values => this.act(`${WPB}.update_row`, { plan, row: id, values });
            ({
                freezer: () => { s.freezer = v; this.render(); },
                rfreezer: () => upd({ source_freezer: v }),
                rproject: () => upd({ project: v }),
                rqty: () => upd({ planned_qty_lbs: Math.max(0, +v || 0) }),
                from: () => { const p = s.data.plan; this.act(`${WPB}.update_period`, { plan, plan_type: p.plan_type, from_date: v, to_date: p.plan_type === "Custom" ? (p.to_date < v ? v : p.to_date) : null }); },
                to: () => { const p = s.data.plan; this.act(`${WPB}.update_period`, { plan, plan_type: p.plan_type, from_date: p.from_date, to_date: v }); },
                adate: () => { s.add.date = v; },
                albs: () => { s.add.lbs = v; this.refresh_preview(); },
                afreezer: () => { s.add.freezer = v; this.pick_project(); this.fill_freezers(); this.refresh_preview(); },
                aproject: () => { s.add.project = v; this.refresh_preview(); },
            })[c]?.();
        });
    }

    make_mrs(rows) {
        if (!rows.length) return;
        call(`${WPP}.create_material_requests`, { plan: this.state.plan, rows: JSON.stringify(rows) }, true).then(m => {
            const parts = [];
            if (m.made.length) parts.push(`<b>${__("Created")}</b><br>` + m.made.map(x => `<a href="/app/material-request/${encodeURIComponent(x.mr)}">${esc(x.mr)}</a> — ${x.project ? __("project {0}", [esc(x.project)]) : __("no project")}`).join("<br>"));
            if (m.skipped.length) parts.push(`<b>${__("Skipped")}</b><br>` + m.skipped.map(esc).join("<br>"));
            frappe.msgprint({ title: __("Material Requests"), message: parts.join("<br><br>") || __("Nothing to create."), indicator: m.made.length ? "green" : "orange" });
            this.load();
        });
    }

    inject_css() {
        if (document.getElementById("wpb-css")) return;
        $(`<style id="wpb-css">
        .wpb{display:flex;flex-direction:column;gap:16px;padding:8px 0 40px}
        .wpb-card{background:var(--card-bg);border:1px solid var(--border-color);border-radius:var(--border-radius-lg);padding:16px 18px}
        .wpb-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}
        .wpb-title,.wpb-h{margin:0;font-weight:700}.wpb-period{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.wpb-period .form-control{width:auto}
        .wpb-sec{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:var(--text-muted);margin:8px 0}
        .wpb-cards,.wpb-kpis,.wpb-tabs{display:flex;flex-wrap:wrap;gap:10px}.wpb-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}
        .wpb-pc{border:1px solid var(--border-color);background:var(--control-bg);border-radius:var(--border-radius-md);padding:8px 12px;min-width:170px}
        .wpb-tab{border:1px solid var(--border-color);background:var(--card-bg);border-radius:var(--border-radius-md);padding:6px 12px;display:flex;flex-direction:column;align-items:flex-start;min-width:90px;color:var(--text-color)}
        .wpb-tab span{font-size:11px;color:var(--text-muted)}.wpb-tab.on{background:var(--primary);border-color:var(--primary);color:#fff}.wpb-tab.on span{color:#e5e5e5}
        .wpb-kpi{display:flex;flex-direction:column;gap:4px}.wpb-kpi b{font-size:24px}
        .wpb-scroll{overflow-x:auto}.wpb-t{width:100%;min-width:1100px;border-collapse:collapse}.wpb-t th{font-size:11px;text-transform:uppercase;color:var(--text-muted);padding:8px;text-align:left;background:var(--control-bg)}
        .wpb-t td{padding:8px;border-top:1px solid var(--border-color);vertical-align:top}.r{text-align:right!important}.mono{font-family:var(--font-stack-monospace,monospace)}
        .wpb-over{background:var(--bg-orange,#fff6f1)}.wpb-warn{color:var(--red-600,#b42318);font-weight:600}
        .wpb-qty{display:flex;gap:4px;align-items:center}.wpb-qty input{width:64px;text-align:center}.wpb-act{white-space:nowrap}
        .wpb-fg{border:1px solid var(--border-color);border-radius:var(--border-radius-md);overflow:hidden}.wpb-fgh{display:flex;justify-content:space-between;gap:8px;padding:8px 12px;background:var(--control-bg)}
        .wpb-fg .wpb-t{min-width:0}.wpb-bottom{display:flex;flex-wrap:wrap;gap:16px;align-items:stretch}.wpb-bottom>.wpb-card{flex:1 1 420px;min-width:0}
        .wpb-form{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}.wpb-form label{font-size:12px;font-weight:600;color:var(--text-muted);margin:0}.wpb-form .wide{grid-column:span 2}
        .wpb-prev{background:var(--control-bg);border-radius:var(--border-radius-md);padding:10px 12px;margin-bottom:12px;font-size:13px}
        .wpb-fz{border:1px solid var(--border-color);border-radius:var(--border-radius-md);padding:10px 12px;margin-top:12px;display:flex;flex-direction:column;gap:10px}
        .wpb-fzh,.wpb-barh{display:flex;justify-content:space-between;gap:8px}.wpb-track{height:8px;background:var(--border-color);border-radius:99px;overflow:hidden}
        .wpb-track div{height:8px;background:var(--primary);border-radius:99px}.wpb-track div.over{background:var(--red-500,#e24c4c)}.wpb-empty{padding:28px;text-align:center}
        </style>`).appendTo(document.head);
    }
}
