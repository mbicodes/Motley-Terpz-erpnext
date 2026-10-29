frappe.ui.form.on('Job Card', {

    refresh: function (frm) {
        _load_all_rates(frm);
        _fix_employee_pill_remove(frm);
    },

    prepare_timer_buttons: function (frm) {
        _replace_timer_buttons(frm);
    },

    workstation: function (frm) {
        (frm.doc.time_logs || []).forEach(row => {
            if (!row.custom_workstation) {
                _set_row_workstation(frm, row.doctype, row.name, frm.doc.workstation);
            }
        });
    },

    total_completed_qty: function (frm) {
        _push_total_completed_qty_to_time_log(frm);
    },

    before_save: function (frm) {
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

frappe.ui.form.on('Micron Collection Detail', {
    grams_collected: function (frm) {
        _sync_micron_total_to_time_log(frm);
    },
    custom_micron_collection_detail_remove: function (frm) {
        _sync_micron_total_to_time_log(frm);
    },
});

function _sync_micron_total_to_time_log(frm) {
    let bags = frm.doc.custom_micron_collection_detail || [];
    let logs = frm.doc.time_logs || [];
    if (!bags.length || !logs.length || frm.doc.docstatus !== 0) return;

    let total = bags.reduce((sum, row) => sum + flt(row.grams_collected), 0);
    let with_qty = logs.filter(row => flt(row.completed_qty) > 0);
    let target = with_qty.length ? with_qty[with_qty.length - 1] : logs[logs.length - 1];
    if (flt(target.completed_qty) !== total) {
        frappe.model.set_value(target.doctype, target.name, 'completed_qty', total);
    }
}

function _push_total_completed_qty_to_time_log(frm) {
    let logs = frm.doc.time_logs || [];
    if (frm.doc.docstatus !== 0) return;
    if (!logs.length) {
        frappe.msgprint(__('Add a Time Log first -- Total Completed Qty is saved on it.'));
        return;
    }

    let total = flt(frm.doc.total_completed_qty);
    let with_qty = logs.filter(row => flt(row.completed_qty) > 0);
    let target = with_qty.length ? with_qty[with_qty.length - 1] : logs[logs.length - 1];
    let others = logs.filter(row => row !== target)
        .reduce((sum, row) => sum + flt(row.completed_qty), 0);

    if (total < others) {
        logs.forEach(row => { if (row !== target) row.completed_qty = 0; });
        others = 0;
    }
    target.completed_qty = total - others;
    frm.refresh_field('time_logs');
}

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

    employee: function (frm, cdt, cdn) {
        _refresh_labor_rate(frm, cdt, cdn);
    },

    custom_labor_rate: function (frm, cdt, cdn) {
        _recalc_cost(frm, cdt, cdn);
    },

    custom_workstation: function (frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (row.custom_workstation) {
            frappe.db.get_value('Workstation', row.custom_workstation, 'custom_total_operating_cost', r => {
                frappe.model.set_value(cdt, cdn, 'custom_hour_rate', flt(r.custom_total_operating_cost));
                _refresh_labor_rate(frm, cdt, cdn);
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

const CM_TIMER_BUTTONS = ['Start Job', 'Resume Job', 'Pause Job', 'Complete Job'];

function _replace_timer_buttons(frm) {
    CM_TIMER_BUTTONS.forEach(label => frm.remove_custom_button(__(label)));

    if (!frm.doc.started_time && !frm.doc.current_time) {
        frm.add_custom_button(__('Start Job'), () => _start_job_dialog(frm)).addClass('btn-primary');
    } else if (frm.doc.status === 'On Hold') {
        frm.add_custom_button(__('Resume Job'), () => _resume_job_dialog(frm)).addClass('btn-primary');
    } else {
        frm.add_custom_button(__('Pause Job'), () => _end_job_dialog(frm, 'On Hold'));
        frm.add_custom_button(__('Complete Job'), () => _end_job_dialog(frm, 'Complete')).addClass('btn-primary');
    }
}

function _start_job_dialog(frm) {
    const needs_employees = !frm.doc.employee || !frm.doc.employee.length;

    const selected = [];

    const fields = [];
    if (needs_employees) {
        fields.push({
            fieldtype: 'Link',
            options: 'Employee',
            label: __('Add Employee'),
            fieldname: 'employee_picker',
            get_query: () => ({ filters: { status: 'Active' } }),
        });
        fields.push({ fieldtype: 'HTML', fieldname: 'employee_list' });
    }
    fields.push({
        fieldtype: 'Datetime',
        label: __('Start Time'),
        fieldname: 'start_time',
        reqd: 1,
        default: frappe.datetime.now_datetime(),
    });

    const d = new frappe.ui.Dialog({
        title: __('Start Job'),
        fields: fields,
        primary_action_label: __('Start'),
        primary_action(values) {
            if (!values.start_time) return;
            if (needs_employees && !selected.length) {
                frappe.msgprint(__('Select at least one employee.'));
                return;
            }
            d.hide();

            const employees = needs_employees
                ? selected.map(emp => ({ employee: emp.id }))
                : frm.doc.employee;

            frm.events.make_time_log(frm, {
                job_card_id: frm.doc.name,
                start_time: values.start_time,
                employees: employees,
                status: 'Work In Progress',
            });
        },
    });

    if (needs_employees) {
        const $list = $(d.get_field('employee_list').wrapper);

        const render = () => {
            if (!selected.length) {
                $list.html(
                    `<div class="text-muted" style="font-size:12px;padding:4px 0">${
                        __('No employees selected yet')}</div>`
                );
                return;
            }
            $list.html(
                '<div class="cm-emp-pills" style="display:flex;flex-wrap:wrap;gap:6px;padding:4px 0">' +
                selected.map(emp => `
                    <span class="cm-emp-pill" style="display:inline-flex;align-items:center;gap:6px;
                        padding:3px 10px;border:1px solid var(--border-color,#d1d8dd);
                        border-radius:12px;background:var(--control-bg,#f4f5f6);font-size:12px">
                        <span>${frappe.utils.escape_html(emp.label)}</span>
                        <a href="#" class="cm-emp-remove" data-id="${frappe.utils.escape_html(emp.id)}"
                           style="text-decoration:none;color:var(--text-muted,#8d99a6);font-weight:700"
                           title="${__('Remove')}">&times;</a>
                    </span>`).join('') +
                '</div>'
            );
        };

        $list.on('click', '.cm-emp-remove', function (e) {
            e.preventDefault();
            const id = $(this).data('id');
            const i = selected.findIndex(emp => emp.id === String(id));
            if (i > -1) selected.splice(i, 1);
            render();
        });

        d.get_field('employee_picker').df.onchange = () => {
            const id = d.get_value('employee_picker');
            if (!id) return;
            if (!selected.some(emp => emp.id === id)) {
                const label = d.get_field('employee_picker').get_label_value?.() || id;
                selected.push({ id: id, label: label && label !== id ? `${label}` : id });
            }
            d.set_value('employee_picker', '');
            render();
        };

        render();
    }

    d.show();
}

function _resume_job_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __('Resume Job'),
        fields: [{
            fieldtype: 'Datetime',
            label: __('Start Time'),
            fieldname: 'start_time',
            reqd: 1,
            default: frappe.datetime.now_datetime(),
        }],
        primary_action_label: __('Resume'),
        primary_action(values) {
            if (!values.start_time) return;
            d.hide();
            frm.events.make_time_log(frm, {
                job_card_id: frm.doc.name,
                start_time: values.start_time,
                employees: frm.doc.employee,
                status: 'Resume Job',
            });
        },
    });
    d.show();
}

function _end_job_dialog(frm, status) {
    let ask_qty = status === 'Complete';
    if (ask_qty) {
        const sub_ops = frm.doc.sub_operations;
        if (sub_ops && sub_ops.length > 1) {
            const last_op_row = sub_ops[sub_ops.length - 2];
            ask_qty = last_op_row.status === 'Complete';
        }
    }

    const fields = [];
    if (ask_qty) {
        fields.push({
            fieldtype: 'Float',
            label: __('Completed Quantity'),
            fieldname: 'qty',
            default: flt(frm.doc.for_quantity) - flt(frm.doc.total_completed_qty),
        });
    }
    fields.push({
        fieldtype: 'Datetime',
        label: __('End Time'),
        fieldname: 'complete_time',
        reqd: 1,
        default: frappe.datetime.now_datetime(),
    });

    const d = new frappe.ui.Dialog({
        title: status === 'On Hold' ? __('Pause Job') : __('Complete Job'),
        fields: fields,
        primary_action_label: status === 'On Hold' ? __('Pause') : __('Complete'),
        primary_action(values) {
            if (!values.complete_time) return;
            d.hide();
            frm.events.make_time_log(frm, {
                job_card_id: frm.doc.name,
                complete_time: values.complete_time,
                status: status,
                completed_qty: ask_qty ? flt(values.qty) : 0.0,
            });
        },
    });
    d.show();
}

function _fix_employee_pill_remove(frm) {
    const ctrl = frm.fields_dict.employee;
    if (!ctrl || !ctrl.$input_area) return;

    ctrl.$input_area.off('click', '.btn-remove');
    ctrl.$input_area.off('mousedown.cm_emp');
    ctrl.$input_area.on('click', '.btn-remove', (e) => {
        e.preventDefault();
        e.stopPropagation();
    });
    ctrl.$input_area.on('mousedown.cm_emp', '.tb-selected-value', (e) => {
        const x_el = e.currentTarget.querySelector('.btn-remove');
        if (!x_el) return;
        const box = x_el.getBoundingClientRect();
        const pad = 3;
        if (e.clientX < box.left - pad || e.clientX > box.right + pad
            || e.clientY < box.top - pad || e.clientY > box.bottom + pad) return;

        e.preventDefault();
        e.stopPropagation();
        if (!frm.fields_dict.employee || frm.doc.docstatus !== 0) return;

        const value = decodeURIComponent($(e.currentTarget).attr('data-value'));
        const rows = frm.doc.employee || [];
        const keep = rows.filter(r => r.employee !== value);
        if (keep.length === rows.length) return;

        rows.filter(r => r.employee === value).forEach(r => frappe.model.clear_doc(r.doctype, r.name));
        keep.forEach((r, i) => { r.idx = i + 1; });
        frm.doc.employee = keep;

        ctrl.inside_change_event = false;
        ctrl.rows = keep;
        frm.dirty();
        frm.refresh_field('employee');
    });
}

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
    let machine = (flt(row.custom_hour_rate) / 60) * flt(row.time_in_mins);
    let labor = (flt(row.custom_labor_rate) / 60) * flt(row.time_in_mins);
    frappe.model.set_value(cdt, cdn, 'custom_labor_cost', labor);
    frappe.model.set_value(cdt, cdn, 'custom_sub_op_cost', machine + labor);

    let total = (frm.doc.time_logs || []).reduce((s, r) => s + flt(r.custom_sub_op_cost), 0);
    frm.set_value('custom_sub_op_total_cost', total);
}

function _refresh_labor_rate(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
    if (!row.custom_workstation || !row.employee) {
        frappe.model.set_value(cdt, cdn, 'custom_labor_rate', 0);
        _recalc_cost(frm, cdt, cdn);
        return;
    }
    frappe.db.get_value('Workstation', row.custom_workstation, 'custom_employee_wise_labor_cost', (ws) => {
        if (!ws || !cint(ws.custom_employee_wise_labor_cost)) {
            frappe.model.set_value(cdt, cdn, 'custom_labor_rate', 0);
            _recalc_cost(frm, cdt, cdn);
            return;
        }
        frappe.db.get_value('Employee', row.employee, 'custom_hourly_wage_rate', (emp) => {
            frappe.model.set_value(cdt, cdn, 'custom_labor_rate', flt(emp && emp.custom_hourly_wage_rate));
            _recalc_cost(frm, cdt, cdn);
        });
    });
}
