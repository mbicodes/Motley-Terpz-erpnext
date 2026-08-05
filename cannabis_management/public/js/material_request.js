frappe.ui.form.on("Material Request", {
    work_order(frm) {
        if (frm.doc.work_order && !frm.doc.set_warehouse) {
            frappe.db.get_value('Work Order', frm.doc.work_order, 'source_warehouse', (r) => {
                let src = r && r.source_warehouse;
                if (src) {
                    frm.set_value('set_warehouse', src);
                } else {
                    frappe.db.get_single_value('Manufacturing Settings', 'default_fg_warehouse')
                        .then(val => { if (val) frm.set_value('set_warehouse', val); });
                }
            });
        }
    },

    setup(frm) {
        frm.set_query('custom_project', () => ({
            filters: { company: frm.doc.company }
        }));
    },

    refresh(frm) {
        if (frm.doc.docstatus === 1
            && frm.doc.material_request_type === 'Manufacture'
            && frm.doc.custom_finished_goods
            && frm.doc.custom_finished_goods.length) {

            frm.add_custom_button(__('Work Order (FG)'), function () {
                create_fg_work_orders(frm);
            }, __('Create'));
        }

        setTimeout(() => {
            frm.page.inner_toolbar
                .find('.btn-default:contains("Work Order")')
                .filter(function () {
                    return $(this).text().trim() === 'Work Order';
                })
                .hide();
        }, 300);

        // Disable Add Row on custom_finished_goods
        disable_fg_add_row(frm);
    },

    validate(frm) {
        if (frm.doc.material_request_type === 'Manufacture') {
            validate_fg_routing(frm);
        }
    },

    custom_routing(frm) {
        if (frm.doc.custom_routing) {
            // Fetch ops, repopulate FG rows, then recalculate
            get_routing_ops(frm, function (ops) {
                if (!ops.length) return;
                populate_fg_rows(frm, ops);
            });
        } else {
            // Routing cleared — clear FG table
            frm.clear_table('custom_finished_goods');
            frm.refresh_field('custom_finished_goods');
            disable_fg_add_row(frm);
        }
    }
});

// ─── RM Item table ───
frappe.ui.form.on("Material Request Item", {
    qty(frm, cdt, cdn) {
        calculate_finished_qty(frm);
    }
});

// ─── Finished Goods child table ───
frappe.ui.form.on("Finished Goods Detail", {
    item(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item) {
            frappe.db.get_value('Item', row.item,
                ['custom_operation', 'custom_yield_percentage'], (r) => {
                    frappe.model.set_value(cdt, cdn, 'expected_yield_', r.custom_yield_percentage);
                    calculate_finished_qty(frm);
                });
        }
    },

    expected_yield_(frm) {
        calculate_finished_qty(frm);
    },

    custom_finished_goods_remove(frm) {
        calculate_finished_qty(frm);
    }
});

// ─── Helpers ───

function disable_fg_add_row(frm) {
    // Hide the "Add Row" button on the custom_finished_goods child table
    setTimeout(() => {
        let fg = frm.fields_dict['custom_finished_goods'];
        if (!fg || !fg.grid) return;   // field not installed on this site

        fg.grid.wrapper.find('.grid-add-row').hide();

        // Also disable the ability to add via keyboard / grid toolbar
        fg.grid.cannot_add_rows = true;
    }, 200);
}

function get_routing_ops(frm, callback) {
    if (!frm.doc.custom_routing) {
        callback([]);
        return;
    }

    // Use cache if routing hasn't changed
    if (frm._routing_ops_cache && frm._routing_ops_cache.routing === frm.doc.custom_routing) {
        callback(frm._routing_ops_cache.ops);
        return;
    }

    frappe.call({
        method: 'frappe.client.get',
        args: { doctype: 'Routing', name: frm.doc.custom_routing },
        callback(r) {
            let ops = (r.message.operations || [])
                .sort((a, b) => a.idx - b.idx)
                .map(o => o.operation);

            frm._routing_ops_cache = { routing: frm.doc.custom_routing, ops: ops };
            callback(ops);
        }
    });
}

function populate_fg_rows(frm, ops) {
    let rm_rows = frm.doc.items || [];
    if (!rm_rows.length) {
        frappe.msgprint(__('Please add Raw Material items before selecting a Routing.'));
        return;
    }

    // Clear existing FG rows
    frm.clear_table('custom_finished_goods');

    // For each RM × each operation, add one FG row pre-filled with the operation
    rm_rows.forEach((rm) => {
        ops.forEach((op) => {
            let new_row = frm.add_child('custom_finished_goods');
            new_row.operation = op;
            // Leave item/yield blank — user fills those in
        });
    });

    frm.refresh_field('custom_finished_goods');
    disable_fg_add_row(frm);
    calculate_finished_qty(frm);
}

function apply_routing_to_fg(frm) {
    get_routing_ops(frm, function (ops) {
        if (!ops.length) return;

        (frm.doc.custom_finished_goods || []).forEach((row, i) => {
            let op = ops[i % ops.length];
            if (row.operation !== op) {
                frappe.model.set_value(row.doctype, row.name, 'operation', op);
            }
        });
        frm.refresh_field('custom_finished_goods');
    });
}

function validate_fg_routing(frm) {
    if (!frm.doc.custom_routing || !frm.doc.custom_finished_goods || !frm.doc.custom_finished_goods.length) {
        return;
    }

    if (!frm._routing_ops_cache || frm._routing_ops_cache.routing !== frm.doc.custom_routing) {
        return; // Will be caught server-side
    }

    let ops = frm._routing_ops_cache.ops;
    if (!ops.length) return;

    let n_ops = ops.length;
    let n_fgs = frm.doc.custom_finished_goods.length;

    if (n_fgs % n_ops !== 0) {
        frappe.throw(
            __('Finished Goods must have {0} rows per raw material (matching Routing: {1}). Currently {2} rows.',
                [n_ops, ops.join(' → '), n_fgs])
        );
    }

    frm.doc.custom_finished_goods.forEach((row, i) => {
        let expected_op = ops[i % n_ops];
        if (row.operation && row.operation !== expected_op) {
            frappe.throw(
                __('Row {0}: Operation must be "{1}" (from Routing sequence), but found "{2}".',
                    [i + 1, expected_op, row.operation])
            );
        }
    });
}

function calculate_finished_qty(frm) {
    if (frm._calculating_fg) return;
    frm._calculating_fg = true;

    let fg_rows = frm.doc.custom_finished_goods || [];
    let rm_rows = frm.doc.items || [];

    if (!fg_rows.length || !rm_rows.length) {
        frm._calculating_fg = false;
        return;
    }

    let n_ops = 1;
    if (frm._routing_ops_cache && frm._routing_ops_cache.routing === frm.doc.custom_routing) {
        n_ops = frm._routing_ops_cache.ops.length || 1;
    } else {
        n_ops = Math.round(fg_rows.length / rm_rows.length) || 1;
    }

    console.log('=== calculate_finished_qty ===');
    console.log('n_ops (cycle length):', n_ops, '| n_rms:', rm_rows.length);

    let rm_idx = -1;
    let input_grams = 0;

    for (let i = 0; i < fg_rows.length; i++) {
        let cycle_pos = i % n_ops;

        if (cycle_pos === 0) {
            rm_idx++;
            let rm_row = rm_rows[rm_idx];
            input_grams = rm_row ? (rm_row.qty || 0) * 453.592 : 0;
            console.log('Cycle restart → RM', rm_idx, ':', rm_row?.item_code, '=', input_grams, 'g');
        }

        let row = fg_rows[i];
        let yield_pct = flt(row.expected_yield_);

        console.log('  Row', i + 1, '(cycle pos', cycle_pos, '):', row.item, '| yield:', yield_pct, '% | input:', input_grams, 'g');

        if (yield_pct > 0) {
            let output_grams = input_grams * (yield_pct / 100);
            row.finished_qty_grams = flt(output_grams, 4);
            row.finished_qty_pounds = flt(output_grams / 453.592, 4);
            input_grams = output_grams;
        } else {
            row.finished_qty_grams = 0;
            row.finished_qty_pounds = 0;
        }
    }

    frm._calculating_fg = false;
    frm.refresh_fields();
}

function create_fg_work_orders(frm) {
    let fg_rows = (frm.doc.custom_finished_goods || []).map((row, idx) => ({
        idx: idx + 1,
        item: row.item,
        item_name: row.item_name || row.item,
        finished_qty_grams: row.finished_qty_grams || 0,
        finished_qty_pounds: row.finished_qty_pounds || 0,
    }));

    if (!fg_rows.length) {
        frappe.msgprint(__('No Finished Goods rows found.'));
        return;
    }

    frappe.call({
        method: 'cannabis_management.api.manufacturing.create_work_orders_from_mr',
        args: { material_request: frm.doc.name },
        freeze: true,
        freeze_message: __('Creating Work Orders…'),
        callback: function (r) {
            if (r.message && r.message.length) {
                let links = r.message.map(wo =>
                    `<a href="/app/work-order/${wo}">${wo}</a>`
                ).join('<br>');
                frappe.msgprint({
                    title: __('Work Orders Created'),
                    message: links,
                    indicator: 'green'
                });
                frm.reload_doc();
            }
        }
    });
}