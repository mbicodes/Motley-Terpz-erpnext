// Copyright (c) 2026, alltechvirtual.com and contributors

frappe.ui.form.on("Wash Batch", {
    refresh(frm) {
        frm.fields_dict.wash_details.grid.set_column_disp("erpnext_batch", false);

        if (frm.doc.yield_pct && frm.doc.yield_pct < 2.5 && frm.doc.docstatus === 0) {
            frm.dashboard.add_comment(
                `⚠️ Yield ${frm.doc.yield_pct.toFixed(2)}% is below the 2.5% minimum. Supervisor approval required.`,
                "red", true
            );
        }
    },

    ff_input_g(frm) {
        frm.trigger("recalc_yield");
    },

    recalc_yield(frm) {
        let total = 0;
        (frm.doc.wash_details || []).forEach(row => { total += (row.grams_collected || 0); });
        const ff_g = frm.doc.ff_input_g || 0;
        frm.set_value("total_bubble_yield_g", Math.round(total * 100) / 100);
        frm.set_value("yield_pct", ff_g ? Math.round(total / ff_g * 10000) / 100 : 0);
    }
});

frappe.ui.form.on("Wash Detail", {
    grams_collected(frm) { frm.trigger("recalc_yield"); },
    wash_details_remove(frm) { frm.trigger("recalc_yield"); }
});
