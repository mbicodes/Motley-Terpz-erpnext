frappe.ui.form.on('Conversion Entry', {
    refresh: function (frm) {
        make_child_table_scrollable(frm);
        _set_warehouse_filters(frm);
        _render_timer_buttons(frm);

        // Resume live clock if the form is loaded while a job is running
        if (frm.doc.docstatus === 0 && frm.doc.timer_status === 'Running') {
            _start_clock(frm);
        }
    },

    company: function (frm) {
        _set_warehouse_filters(frm);
        (frm.doc.items || []).forEach(function (row) {
            frappe.model.set_value(row.doctype, row.name, 'source_warehouse', '');
            frappe.model.set_value(row.doctype, row.name, 'target_warehouse', '');
        });
    },

    before_save: function (frm) {
        _recalc_total_time(frm);
    }
});


// ── Timer buttons ────────────────────────────────────────────────────────────

function _render_timer_buttons(frm) {
    if (frm.doc.docstatus !== 0) {
        _stop_clock(frm);
        return;
    }

    const status = frm.doc.timer_status || '';

    if (status === 'Running') {
        frm.add_custom_button(__('Pause Job'), function () {
            _pause_job(frm, false);
        }).addClass('btn-warning');

        frm.add_custom_button(__('Complete Job'), function () {
            _pause_job(frm, true);
        }).addClass('btn-success');

    } else if (status === 'Paused') {
        frm.add_custom_button(__('Resume Job'), function () {
            _start_job(frm);
        }).addClass('btn-primary');

        frm.add_custom_button(__('Complete Job'), function () {
            _pause_job(frm, true);
        }).addClass('btn-success');

    } else {
        frm.add_custom_button(__('Start Job'), function () {
            _start_job(frm);
        }).addClass('btn-primary');
    }
}

function _start_job(frm) {
    if (!frm.doc.workstation) {
        frappe.msgprint(__('Please set a Workstation before starting the job.'));
        return;
    }

    // Pre-fetch the employee linked to the current user
    frappe.db.get_value('Employee', { user_id: frappe.session.user }, 'name', function (val) {
        let default_employee = val && val.name || '';

        let d = new frappe.ui.Dialog({
            title: __('Start Job'),
            fields: [{
                fieldtype: 'Link',
                fieldname: 'employee',
                label: __('Employee'),
                options: 'Employee',
                default: default_employee
            }],
            primary_action_label: __('Start'),
            primary_action(values) {
                d.hide();

                let row = frm.add_child('time_logs');
                row.employee  = values.employee || '';
                row.from_time = frappe.datetime.now_datetime();

                frm.doc.timer_status = 'Running';
                frm.refresh_field('time_logs');
                frm.refresh_field('timer_status');

                frm.save().then(() => {
                    _start_clock(frm);
                    frappe.show_alert({ message: __('Job started'), indicator: 'green' });
                    frm.refresh();
                });
            }
        });
        d.show();
    });
}

function _pause_job(frm, complete) {
    _stop_clock(frm);

    let logs = frm.doc.time_logs || [];
    let running = logs.slice().reverse().find(r => r.from_time && !r.to_time);

    if (running) {
        let to_time   = frappe.datetime.now_datetime();
        let from_dt   = moment(running.from_time, 'YYYY-MM-DD HH:mm:ss');
        let to_dt     = moment(to_time,            'YYYY-MM-DD HH:mm:ss');
        let mins      = to_dt.diff(from_dt, 'minutes', true);

        frappe.model.set_value(running.doctype, running.name, 'to_time',      to_time);
        frappe.model.set_value(running.doctype, running.name, 'time_in_mins', flt(mins, 2));
    }

    frm.doc.timer_status = complete ? '' : 'Paused';
    _recalc_total_time(frm);

    frm.refresh_field('time_logs');
    frm.refresh_field('timer_status');
    frm.refresh_field('total_time_in_minutes');

    frm.save().then(() => {
        let msg = complete ? __('Job completed') : __('Job paused');
        let ind = complete ? 'green' : 'orange';
        frappe.show_alert({ message: msg, indicator: ind });
        frm.refresh();
    });
}


// ── Live clock ───────────────────────────────────────────────────────────────

function _start_clock(frm) {
    _stop_clock(frm);

    let logs = frm.doc.time_logs || [];
    let running = logs.slice().reverse().find(r => r.from_time && !r.to_time);
    if (!running) return;

    // Time already logged in completed rows
    let prev_mins = logs
        .filter(r => r.to_time && r.time_in_mins)
        .reduce((s, r) => s + flt(r.time_in_mins), 0);

    let session_start = moment(running.from_time, 'YYYY-MM-DD HH:mm:ss').toDate();

    frm._timer_interval = setInterval(function () {
        let elapsed_ms = Date.now() - session_start.getTime() + prev_mins * 60000;
        let h = Math.floor(elapsed_ms / 3600000);
        let m = Math.floor((elapsed_ms % 3600000) / 60000);
        let s = Math.floor((elapsed_ms % 60000) / 1000);
        let display = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
        frm.page.set_title_sub('⏱ ' + display);
    }, 1000);
}

function _stop_clock(frm) {
    if (frm._timer_interval) {
        clearInterval(frm._timer_interval);
        frm._timer_interval = null;
    }
    frm.page.set_title_sub('');
}


// ── Helpers ──────────────────────────────────────────────────────────────────

function _recalc_total_time(frm) {
    let total = (frm.doc.time_logs || [])
        .filter(r => r.time_in_mins)
        .reduce((s, r) => s + flt(r.time_in_mins), 0);
    frm.doc.total_time_in_minutes = flt(total, 2);
    frm.refresh_field('total_time_in_minutes');
}

function _set_warehouse_filters(frm) {
    var company = frm.doc.company;
    frm.set_query('source_warehouse', 'items', function () {
        return { filters: { company: company } };
    });
    frm.set_query('target_warehouse', 'items', function () {
        return { filters: { company: company } };
    });
}

function make_child_table_scrollable(frm) {
    // stub — reserved for future scroll CSS injection
}


// ── Conversion Entry Item child events ───────────────────────────────────────

frappe.ui.form.on("Conversion Entry Item", {
    conversion_type: function (frm, cdt, cdn) {
        clear_hidden_fields_for_row(frm, cdt, cdn);
    },
    raw_material_1: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_1', 'rm_1_item_group'); },
    raw_material_2: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_2', 'rm_2_item_group'); },
    raw_material_3: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_3', 'rm_3_item_group'); },
    raw_material_4: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_4', 'rm_4_item_group'); },
    raw_material_5: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_5', 'rm_5_item_group'); },
    raw_material_6: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_6', 'rm_6_item_group'); },
    raw_material_7: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_7', 'rm_7_item_group'); },
    finished_good_1: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'finished_good_1', 'fg_1_item_group'); },
    finished_good_2: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'finished_good_2', 'fg_2_item_group'); },
});

function _sync_item_group(cdt, cdn, item_field, group_field) {
    let row  = frappe.get_doc(cdt, cdn);
    let item = row[item_field];
    if (!item) {
        frappe.model.set_value(cdt, cdn, group_field, '');
        return;
    }
    frappe.db.get_value('Item', item, 'item_group', function (val) {
        frappe.model.set_value(cdt, cdn, group_field, (val && val.item_group) || '');
    });
}

function clear_hidden_fields_for_row(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    let ct  = row.conversion_type;
    if (!ct) return;

    if (!["2 to 1", "2 to 2", "3 to 1", "4 to 1", "5 to 1", "6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_2", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_2", 0);
    }
    if (!["3 to 1", "4 to 1", "5 to 1", "6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_3", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_3", 0);
    }
    if (!["4 to 1", "5 to 1", "6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_4", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_4", 0);
    }
    if (!["5 to 1", "6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_5", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_5", 0);
    }
    if (!["6 to 1", "7 to 1"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "raw_material_6", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_6", 0);
    }
    if (ct !== "7 to 1") {
        frappe.model.set_value(cdt, cdn, "raw_material_7", "");
        frappe.model.set_value(cdt, cdn, "qty_rm_7", 0);
    }
    if (!["1 to 2", "2 to 2"].includes(ct)) {
        frappe.model.set_value(cdt, cdn, "finished_good_2", "");
        frappe.model.set_value(cdt, cdn, "qty_fg_2", 0);
    }
}
