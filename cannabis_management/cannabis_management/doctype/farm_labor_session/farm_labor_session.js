// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Farm Labor Session", {

    setup(frm) {
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
        frm.set_value("target_warehouse", null);
    },

    hours(frm) {
        calculate_totals(frm);
    },

    labor_rate(frm) {
        calculate_totals(frm);
    },

    units_completed(frm) {
        calculate_totals(frm);
    },

    validate(frm) {
        calculate_totals(frm);
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
