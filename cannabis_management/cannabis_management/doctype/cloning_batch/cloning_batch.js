// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cloning Batch", {

    setup(frm) {
        // Target Warehouse filter: sirf selected company ke warehouses show hon
        frm.set_query("target_warehouse", function () {
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
    },

    company(frm) {
        // Company change hone par purana warehouse clear kar do
        // taake dusri company ka warehouse selected na reh jaye
        frm.set_value("target_warehouse", null);
    },

    labour_hours(frm) {
        calculate_totals(frm);
    },

    labour_rate(frm) {
        calculate_totals(frm);
    }
});


frappe.ui.form.on("Cloning Batch Clone Detail", {

    quantity(frm) {
        calculate_totals(frm);
    },

    clone_details_add(frm) {
        calculate_totals(frm);
    },

    clone_details_remove(frm) {
        calculate_totals(frm);
    }

});


function calculate_totals(frm) {

    let total_clones = 0;

    (frm.doc.clone_details || []).forEach(function (row) {
        total_clones += cint(row.quantity);
    });

    // Total Labor Cost
    let labour_cost =
        flt(frm.doc.labour_hours) *
        flt(frm.doc.labour_rate);

    // Agar ye fields DocType mein hain to update karega
    if (frm.fields_dict.total_labor_cost) {
        frm.set_value("total_labor_cost", labour_cost);
    }

    if (frm.fields_dict.total_clones_produced) {
        frm.set_value("total_clones_produced", total_clones);
    }

    if (frm.fields_dict.total_session_cost) {
        frm.set_value("total_session_cost", labour_cost);
    }

    if (frm.fields_dict.cost_per_clone) {
        frm.set_value(
            "cost_per_clone",
            total_clones > 0 ? labour_cost / total_clones : 0
        );
    }
}