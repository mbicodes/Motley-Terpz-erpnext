frappe.ui.form.on("Cloning Batch", {
    refresh(frm) {
        calculate_totals(frm);
    },

    labour_hours(frm) {
        calculate_totals(frm);
    },

    labour_rate(frm) {
        calculate_totals(frm);
    }
});


frappe.ui.form.on("Cloning Batch Clone Detail", {

    qty(frm) {
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

    (frm.doc.clone_details || []).forEach(function(row) {
        total_clones += cint(row.qty);
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