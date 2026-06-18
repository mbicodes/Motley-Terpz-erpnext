// Job Card — auto-populate workstation, rate, and sub-op cost on time log rows

frappe.ui.form.on('Job Card', {

    refresh: function (frm) {
        _load_all_rates(frm);
    },

    workstation: function (frm) {
        // Backfill rows that have no workstation yet
        (frm.doc.time_logs || []).forEach(row => {
            if (!row.custom_workstation) {
                _set_row_workstation(frm, row.doctype, row.name, frm.doc.workstation);
            }
        });
    },

    before_save: function (frm) {
        // Recalculate all costs before saving
        let total = 0;
        (frm.doc.time_logs || []).forEach(row => {
            let cost = (flt(row.custom_hour_rate) / 60) * flt(row.time_in_mins);
            row.custom_sub_op_cost = cost;
            total += cost;
        });
        frm.doc.custom_sub_op_total_cost = total;
        frm.refresh_field('time_logs');
        frm.refresh_field('custom_sub_op_total_cost');
    },
});

frappe.ui.form.on('Job Card Time Log', {

    from_time: function (frm, cdt, cdn) {
        _calc_time_from_range(frm, cdt, cdn);
    },

    to_time: function (frm, cdt, cdn) {
        _calc_time_from_range(frm, cdt, cdn);
    },

    operation: function (frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (row.operation) {
            frappe.db.get_value('Operation', row.operation, 'workstation', r => {
                _set_row_workstation(frm, cdt, cdn, r.workstation || frm.doc.workstation || '');
            });
        } else {
            _set_row_workstation(frm, cdt, cdn, frm.doc.workstation || '');
        }
    },

    custom_workstation: function (frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (row.custom_workstation) {
            frappe.db.get_value('Workstation', row.custom_workstation, 'custom_total_operating_cost', r => {
                frappe.model.set_value(cdt, cdn, 'custom_hour_rate', flt(r.custom_total_operating_cost));
                _recalc_cost(frm, cdt, cdn);
            });
        } else {
            frappe.model.set_value(cdt, cdn, 'custom_hour_rate', 0);
            _recalc_cost(frm, cdt, cdn);
        }
    },

    time_in_mins: function (frm, cdt, cdn) {
        _recalc_cost(frm, cdt, cdn);
    },

    custom_hour_rate: function (frm, cdt, cdn) {
        _recalc_cost(frm, cdt, cdn);
    },
});

// On form load: batch-fetch rates for all rows that already have a workstation
function _load_all_rates(frm) {
    let rows_needing_rate = (frm.doc.time_logs || []).filter(r => r.custom_workstation);
    if (!rows_needing_rate.length) return;

    let unique_ws = [...new Set(rows_needing_rate.map(r => r.custom_workstation))];

    frappe.db.get_list('Workstation', {
        filters: [['name', 'in', unique_ws]],
        fields: ['name', 'custom_total_operating_cost'],
        limit: unique_ws.length,
    }).then(ws_list => {
        let rate_map = {};
        ws_list.forEach(w => { rate_map[w.name] = flt(w.custom_total_operating_cost); });

        let total = 0;
        (frm.doc.time_logs || []).forEach(row => {
            if (!row.custom_workstation) return;
            let rate = rate_map[row.custom_workstation] || 0;
            let cost = (rate / 60) * flt(row.time_in_mins);
            row.custom_hour_rate = rate;
            row.custom_sub_op_cost = cost;
            total += cost;
        });
        frm.doc.custom_sub_op_total_cost = total;
        frm.refresh_field('time_logs');
        frm.refresh_field('custom_sub_op_total_cost');
    });
}

function _set_row_workstation(frm, cdt, cdn, ws) {
    frappe.model.set_value(cdt, cdn, 'custom_workstation', ws || '');
    if (ws) {
        frappe.db.get_value('Workstation', ws, 'custom_total_operating_cost', r => {
            frappe.model.set_value(cdt, cdn, 'custom_hour_rate', flt(r.custom_total_operating_cost));
            _recalc_cost(frm, cdt, cdn);
        });
    } else {
        frappe.model.set_value(cdt, cdn, 'custom_hour_rate', 0);
        _recalc_cost(frm, cdt, cdn);
    }
}

function _calc_time_from_range(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    if (!row.from_time || !row.to_time) return;
    let mins = moment(row.to_time).diff(moment(row.from_time), 'minutes', true);
    if (mins > 0) {
        frappe.model.set_value(cdt, cdn, 'time_in_mins', flt(mins, 4));
    }
}

function _recalc_cost(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    let cost = (flt(row.custom_hour_rate) / 60) * flt(row.time_in_mins);
    frappe.model.set_value(cdt, cdn, 'custom_sub_op_cost', cost);

    let total = (frm.doc.time_logs || []).reduce((s, r) => s + flt(r.custom_sub_op_cost), 0);
    frm.set_value('custom_sub_op_total_cost', total);
}
