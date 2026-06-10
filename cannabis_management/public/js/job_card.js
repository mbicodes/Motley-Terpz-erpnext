// Job Card — auto-populate workstation, rate, and sub-op cost on time log rows

frappe.ui.form.on('Job Card', {
    // When the Job Card's own workstation changes, backfill any rows that have no workstation yet
    workstation: function (frm) {
        (frm.doc.time_logs || []).forEach(row => {
            if (!row.custom_workstation) {
                _set_row_workstation(frm, row.doctype, row.name, frm.doc.workstation);
            }
        });
    },
});

frappe.ui.form.on('Job Card Time Log', {
    // When a row's operation changes, resolve its workstation from Operation → fallback to Job Card
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

    // When time is entered, recalculate cost
    time_in_mins: function (frm, cdt, cdn) {
        _recalc_cost(frm, cdt, cdn);
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

    custom_hour_rate: function (frm, cdt, cdn) {
        _recalc_cost(frm, cdt, cdn);
    },
});

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

function _recalc_cost(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    let hrs = flt(row.time_in_mins) / 60.0;
    let cost = hrs * flt(row.custom_hour_rate);
    frappe.model.set_value(cdt, cdn, 'custom_sub_op_cost', cost);

    // Update the Job Card total
    let total = (frm.doc.time_logs || []).reduce((s, r) => s + flt(r.custom_sub_op_cost), 0);
    frm.set_value('custom_sub_op_total_cost', total);
}
