// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Farm Labor Session", {

    setup(frm) {
        frm.set_query("source_warehouse", "ingredients", function () {
            return {
                filters: {
                    company: frm.doc.company,
                    is_group: 0
                }
            };
        });

        frm.set_query("target_warehouse", "outputs", function () {
            return {
                filters: {
                    company: frm.doc.company,
                    is_group: 0
                }
            };
        });
    },

    refresh(frm) {
        calculate_totals(frm);
        calculate_bucking_totals(frm);
    },

    company(frm) {
        (frm.doc.ingredients || []).forEach((row) => {
            frappe.model.set_value(row.doctype, row.name, "source_warehouse", null);
        });
        (frm.doc.outputs || []).forEach((row) => {
            frappe.model.set_value(row.doctype, row.name, "target_warehouse", null);
        });
    },

    hours(frm) {
        calculate_totals(frm);
        calculate_bucking_totals(frm);
    },

    labor_rate(frm) {
        calculate_totals(frm);
        calculate_bucking_totals(frm);
    },

    units_completed(frm) {
        calculate_totals(frm);
    },

    validate(frm) {
        calculate_totals(frm);
        calculate_bucking_totals(frm);
    }
});

// --- Ingredients ---------------------------------------------------------

frappe.ui.form.on("Bucking Ingredient", {
    source_item(frm, cdt, cdn) {
        fetch_ingredient_cost(frm, cdt, cdn);
    },

    source_warehouse(frm, cdt, cdn) {
        fetch_ingredient_cost(frm, cdt, cdn);
    },

    qty_used(frm, cdt, cdn) {
        fetch_ingredient_cost(frm, cdt, cdn);
    },

    cost(frm) {
        calculate_bucking_totals(frm);
    },

    ingredients_add(frm) {
        calculate_bucking_totals(frm);
    },

    ingredients_remove(frm) {
        calculate_bucking_totals(frm);
    }
});

// --- Outputs --------------------------------------------------------------

frappe.ui.form.on("Bucking Output", {
    qty_produced(frm) {
        calculate_bucking_totals(frm);
    },

    outputs_add(frm) {
        calculate_bucking_totals(frm);
    },

    outputs_remove(frm) {
        calculate_bucking_totals(frm);
    }
});

// --- Additional Costs -------------------------------------------------------

frappe.ui.form.on("Bucking Additional Cost", {
    amount(frm) {
        calculate_bucking_totals(frm);
    },

    additional_costs_add(frm) {
        calculate_bucking_totals(frm);
    },

    additional_costs_remove(frm) {
        calculate_bucking_totals(frm);
    }
});

function calculate_totals(frm) {
    let hours = flt(frm.doc.hours);

    frm.set_value(
        "rate_per_hour",
        hours > 0 ? flt(frm.doc.units_completed) / hours : 0
    );

    frm.set_value("total_cost", hours * flt(frm.doc.labor_rate));
}

function calculate_bucking_totals(frm) {
    if (frm.doc.task_type !== "Bucking") {
        return;
    }

    let total_ingredient_cost = 0;
    let qty_used = 0;
    (frm.doc.ingredients || []).forEach((row) => {
        total_ingredient_cost += flt(row.cost);
        qty_used += flt(row.qty_used);
    });

    let total_additional_cost = 0;
    (frm.doc.additional_costs || []).forEach((row) => {
        total_additional_cost += flt(row.amount);
    });

    let qty_produced = 0;
    (frm.doc.outputs || []).forEach((row) => {
        qty_produced += flt(row.qty_produced);
    });

    frm.set_value("total_ingredient_cost", total_ingredient_cost);
    frm.set_value("total_additional_cost", total_additional_cost);
    frm.set_value(
        "total_assembly_cost",
        total_ingredient_cost + total_additional_cost + flt(frm.doc.hours) * flt(frm.doc.labor_rate)
    );
    frm.set_value("yield_pct", qty_used ? (qty_produced / qty_used) * 100 : 0);
    frm.set_value("moisture_loss_pct", qty_used ? ((qty_used - qty_produced) / qty_used) * 100 : 0);
}

function fetch_ingredient_cost(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (!row.source_item || !row.source_warehouse || !row.qty_used) {
        calculate_bucking_totals(frm);
        return;
    }

    frappe.db.get_value(
        "Bin",
        { item_code: row.source_item, warehouse: row.source_warehouse },
        "valuation_rate"
    ).then((r) => {
        let rate = flt(r.message && r.message.valuation_rate);
        if (rate) {
            frappe.model.set_value(cdt, cdn, "cost", rate * flt(row.qty_used));
        }
        calculate_bucking_totals(frm);
    });
}
