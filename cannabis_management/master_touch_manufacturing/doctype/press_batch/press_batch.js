// Copyright (c) 2026, alltechvirtual.com and contributors

frappe.ui.form.on("Press Batch", {
    refresh(frm) {
        if (frm.doc.yield_pct && frm.doc.yield_pct < 10 && frm.doc.docstatus === 0) {
            frm.dashboard.add_comment(
                `⚠️ Press yield ${frm.doc.yield_pct.toFixed(2)}% is below 10%. Supervisor approval required.`,
                "red", true
            );
        }
        if (frm.doc.discrepancy_g && Math.abs(frm.doc.discrepancy_g) > 0.01 && frm.doc.docstatus === 0) {
            frm.dashboard.add_comment(
                `⚠️ Discrepancy of ${frm.doc.discrepancy_g.toFixed(2)}g — please resolve before submitting.`,
                "orange", true
            );
        }
    },

    bubble_hash_input_g(frm) {
        frm.trigger("recalc_yield");
    },

    recalc_yield(frm) {
        let total = 0;
        (frm.doc.press_details || []).forEach(row => { total += (row.grams_rosin || 0); });
        const bh_g = frm.doc.bubble_hash_input_g || 0;
        frm.set_value("total_rosin_yield_g", Math.round(total * 100) / 100);
        frm.set_value("yield_pct", bh_g ? Math.round(total / bh_g * 10000) / 100 : 0);
        frm.set_value("discrepancy_g", Math.round((bh_g - total) * 100) / 100);
    }
});

frappe.ui.form.on("Press Detail", {
    grams_rosin(frm) { frm.trigger("recalc_yield"); },
    press_details_remove(frm) { frm.trigger("recalc_yield"); }
});
