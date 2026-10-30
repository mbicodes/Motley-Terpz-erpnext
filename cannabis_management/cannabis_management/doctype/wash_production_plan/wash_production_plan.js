const P = "cannabis_management.cannabis_management.doctype.wash_production_plan.wash_production_plan";

frappe.ui.form.on("Wash Production Plan", {
    onload(frm) {
        // the Board is the only screen for non-admins; the form stays as storage and for System Managers
        if (!frappe.user.has_role("System Manager")) frappe.set_route("wash-plan-board", frm.is_new() ? "new" : frm.doc.name);
    },
    setup(frm) {
        frappe.db.get_single_value("Wash Plan Settings", "fresh_frozen_item_group").then(g => {
            frm.set_query("fresh_frozen_item", "items", () => ({ filters: { item_group: ["descendants of (inclusive)", g] } }));
        });
        frappe.db.get_single_value("Wash Plan Settings", "bubble_hash_item_group").then(g =>
            frm.set_query("bubble_hash_item", "items", () => ({ filters: { item_group: g } })));
        frappe.db.get_single_value("Wash Plan Settings", "rosin_item_group").then(g =>
            frm.set_query("rosin_item", "items", () => ({ filters: { item_group: g } })));
        // only projects that hold stock of this item in this freezer
        frm.set_query("project", "items", (doc, cdt, cdn) => {
            const names = ((frm.__stock_projects || {})[cdn] || []).filter(Boolean);
            return names.length ? { filters: { name: ["in", names] } } : { filters: { company: frm.doc.company } };
        });
    },
    refresh(frm) {
        frm.trigger("plan_type");
        const html = (frm.doc.__onload || {}).project_summary;
        frm.fields_dict.project_summary.$wrapper.html(html || `<span class="text-muted">${__("No washes yet.")}</span>`);
        if (frm.is_new()) return;
        frm.add_custom_button(__("Wash Plan Board"), () => frappe.set_route("wash-plan-board", frm.doc.name));
        frm.add_custom_button(__("Create Material Requests"), () => {
            const sel = (frm.fields_dict.items.grid.get_selected() || []);
            frappe.call({ method: `${P}.create_material_requests`, args: { plan: frm.doc.name, rows: sel.length ? sel : null }, freeze: true })
                .then(r => {
                    const m = r.message, parts = [];
                    if (m.made.length) parts.push("<b>" + __("Created") + "</b><br>" + m.made.map(x =>
                        `${frappe.utils.get_form_link("Material Request", x.mr, true)} — ${x.project ? __("project {0}", [x.project]) : __("no project")}`).join("<br>"));
                    if (m.skipped.length) parts.push("<b>" + __("Skipped") + "</b><br>" + m.skipped.join("<br>"));
                    frappe.msgprint({ title: __("Material Requests"), message: parts.join("<br><br>") || __("Nothing to create."), indicator: m.made.length ? "green" : "orange" });
                    frm.reload_doc();
                });
        });
    },
    plan_type(frm) {
        const ro = frm.doc.plan_type !== "Custom";
        frm.set_df_property("to_date", "read_only", ro ? 1 : 0);
        if (frm.doc.plan_type === "Daily") frm.set_value("to_date", frm.doc.from_date);
        if (frm.doc.plan_type === "Weekly" && frm.doc.from_date) frm.set_value("to_date", frappe.datetime.add_days(frm.doc.from_date, 6));
    },
    from_date(frm) { frm.trigger("plan_type"); },
});

function recalc(cdt, cdn) {
    const r = locals[cdt][cdn];
    const grams = (r.planned_qty_lbs || 0) * 453.592;
    const hash = grams * (r.expected_hash_yield || 0) / 100;
    frappe.model.set_value(cdt, cdn, {
        planned_qty_grams: grams, expected_hash_g: hash, expected_rosin_g: hash * (r.expected_rosin_yield || 0) / 100,
    });
}

function refresh_available(frm, cdt, cdn) {
    const r = locals[cdt][cdn];
    if (!r.fresh_frozen_item || !r.source_freezer) return;
    frappe.call({ method: `${P}.get_row_availability`, args: { item: r.fresh_frozen_item, freezer: r.source_freezer, project: r.project || "", plan: frm.doc.name, row: r.name } })
        .then(x => {
            frappe.model.set_value(cdt, cdn, "available_qty_lbs", x.message.available);
            frappe.model.set_value(cdt, cdn, "stock_held_by", (x.message.holders || []).join("\n"));
        });
}

// Project comes from the stock's project dimension: one project -> set it, several -> user picks.
function load_projects(frm, cdt, cdn) {
    const r = locals[cdt][cdn];
    if (!r.fresh_frozen_item || !r.source_freezer) return;
    frappe.call({ method: `${P}.get_stock_projects`, args: { item: r.fresh_frozen_item, freezer: r.source_freezer } }).then(x => {
        const list = x.message || [];
        (frm.__stock_projects = frm.__stock_projects || {})[cdn] = list.map(i => i.project);
        frm.fields_dict.items.grid.update_docfield_property("project", "description",
            list.map(i => `${i.project || __("No project")}: ${i.qty}`).join(" | "));
        if (list.length === 1) frappe.model.set_value(cdt, cdn, "project", list[0].project);
        else if (r.project && !list.some(i => i.project === r.project)) frappe.model.set_value(cdt, cdn, "project", "");
        refresh_available(frm, cdt, cdn);
    });
}

frappe.ui.form.on("Wash Production Plan Item", {
    form_render(frm, cdt, cdn) {
        const r = locals[cdt][cdn];
        const locked = r.row_status && r.row_status !== "Planned";
        frm.fields_dict.items.grid.update_docfield_property && ["planned_date", "fresh_frozen_item", "source_freezer", "planned_qty_lbs", "project", "bubble_hash_item", "rosin_item", "expected_hash_yield", "expected_rosin_yield"]
            .forEach(f => frm.fields_dict.items.grid.get_row(cdn).toggle_editable(f, !locked));
    },
    items_add(frm, cdt, cdn) {
        frappe.db.get_single_value("Wash Plan Settings", "default_hash_yield").then(v => frappe.model.set_value(cdt, cdn, "expected_hash_yield", v));
        frappe.db.get_single_value("Wash Plan Settings", "default_rosin_yield").then(v => frappe.model.set_value(cdt, cdn, "expected_rosin_yield", v));
        frappe.model.set_value(cdt, cdn, "planned_date", frm.doc.from_date);
    },
    fresh_frozen_item(frm, cdt, cdn) {
        const r = locals[cdt][cdn];
        if (!r.fresh_frozen_item) return;
        frappe.call({ method: `${P}.get_item_freezers`, args: { item: r.fresh_frozen_item, row: r.name } }).then(x => {
            const f = x.message || [];
            frm.fields_dict.items.grid.update_docfield_property("source_freezer", "description", f.map(i => `${i.warehouse}: ${i.qty} lbs, ${i.free} free`).join(" | "));
            if (f.length === 1) frappe.model.set_value(cdt, cdn, "source_freezer", f[0].warehouse);
            else if (!f.length) frappe.show_alert({ message: __("No configured freezer holds this item."), indicator: "orange" });
        });
        frappe.call({ method: `${P}.suggest_finished_items`, args: { item: r.fresh_frozen_item } }).then(x => {
            const s = x.message || {};
            frappe.model.set_value(cdt, cdn, "bubble_hash_item", s.bubble_hash_item || "");
            frappe.model.set_value(cdt, cdn, "rosin_item", s.rosin_item || "");
            r.__base = s.base;
        });
    },
    source_freezer: load_projects,
    project: refresh_available,
    planned_qty_lbs: (frm, cdt, cdn) => { recalc(cdt, cdn); },
    expected_hash_yield: (frm, cdt, cdn) => { recalc(cdt, cdn); },
    expected_rosin_yield: (frm, cdt, cdn) => { recalc(cdt, cdn); },
    create_items(frm, cdt, cdn) {
        const r = locals[cdt][cdn];
        frappe.call({ method: `${P}.suggest_finished_items`, args: { item: r.fresh_frozen_item } }).then(x => {
            const base = x.message.base, jobs = [];
            if (!r.bubble_hash_item) jobs.push(["bubble_hash", "bubble_hash_item"]);
            if (!r.rosin_item) jobs.push(["rosin", "rosin_item"]);
            if (!jobs.length) return frappe.msgprint(__("Both finished items are already set."));
            frappe.confirm(__("Create {0}?", [jobs.map(j => `${base} - ${j[0] === "rosin" ? "Rosin" : "Bubble Hash"}`).join(", ")]), () =>
                jobs.forEach(j => frappe.call({ method: `${P}.create_finished_item`, args: { base, kind: j[0] } })
                    .then(y => frappe.model.set_value(cdt, cdn, j[1], y.message))));
        });
    },
});
