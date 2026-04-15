
frappe.ui.form.on('Manufacture Stock Entry', {
    refresh: function (frm) {
        frm.trigger('setup_batch_queries');
    },

    onload: function (frm) {
        frm.trigger('setup_batch_queries');
    },

    from_bom: function (frm) {
        if (frm.doc.from_bom) {
            frm.set_df_property('bom_no', 'hidden', 0);
        } else {
            frm.set_df_property('bom_no', 'hidden', 1);
            frm.set_value('bom_no', '');
            frm.trigger('clear_tables');
        }
        frm.trigger('toggle_fields');
    },

    type: function (frm) {
        frm.trigger('toggle_fields');
        frm.trigger('clear_tables');
        frm.set_value('bom_no', '');
        frm.set_value('bom_total', 0);
        frm.set_value('for_production_metric_ton', 0);
        frm.set_value('finished_good_quantity', 0);
        frm.set_value('previous_manufature_stock_entry', '');
    },

    bom_no: function (frm) {
        if (frm.doc.bom_no && frm.doc.type === 'Premix') {
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'BOM',
                    filters: { name: frm.doc.bom_no },
                    fieldname: 'quantity'
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value('bom_total', r.message.quantity);
                    }
                }
            });
        }

        if (frm.doc.bom_no && frm.doc.type === 'Manufacturing' && frm.doc.finished_good_quantity) {
            frm.trigger('fetch_bom_items');
        }
    },

    finished_good_quantity: function (frm) {
        if (frm.doc.type === 'Manufacturing' && frm.doc.bom_no && frm.doc.finished_good_quantity) {
            frm.trigger('fetch_bom_items');
        }
    },

    for_production_metric_ton: function (frm) {
        if (frm.doc.type === 'Premix' && frm.doc.bom_no && frm.doc.bom_total && frm.doc.for_production_metric_ton) {
            let calculated_fg_qty = frm.doc.bom_total * frm.doc.for_production_metric_ton;
            frm.set_value('finished_good_quantity', calculated_fg_qty);
            frm.trigger('fetch_bom_items');
        }
    },

    bom_total: function (frm) {
        if (frm.doc.type === 'Premix' && frm.doc.bom_no && frm.doc.bom_total && frm.doc.for_production_metric_ton) {
            let calculated_fg_qty = frm.doc.bom_total * frm.doc.for_production_metric_ton;
            frm.set_value('finished_good_quantity', calculated_fg_qty);
            frm.trigger('fetch_bom_items');
        }
    },

    get_items: function (frm) {
        frm.trigger('fetch_bom_items');
    },

    fetch_bom_items: function (frm) {
        if (!frm.doc.bom_no) {
            frappe.msgprint(__('Please select a BOM'));
            return;
        }

        if (!frm.doc.company) {
            frappe.msgprint(__('Please select a Company'));
            return;
        }

        if (frm.doc.type === 'Manufacturing' && !frm.doc.finished_good_quantity) {
            frappe.msgprint(__('Please enter Finished Good Quantity'));
            return;
        }

        if (frm.doc.type === 'Premix' && (!frm.doc.bom_total || !frm.doc.for_production_metric_ton)) {
            frappe.msgprint(__('Please enter BOM Total and For Production Metric Ton'));
            return;
        }

        frappe.call({
            method: 'cannabis_management.cannabis_management.doctype.manufacture_stock_entry.manufacture_stock_entry.get_bom_items',
            args: {
                bom_no: frm.doc.bom_no,
                type: frm.doc.type,
                company: frm.doc.company,
                finished_good_quantity: frm.doc.finished_good_quantity || 0,
                bom_total: frm.doc.bom_total || 0,
                for_production_metric_ton: frm.doc.for_production_metric_ton || 0
            },
            callback: function (r) {
                if (r.message) {
                    frm.clear_table('manufacture_raw_material');
                    frm.clear_table('manufacture_finished_goods');

                    if (frm.doc.type === 'Premix') {
                        frm.set_value('finished_good_quantity', r.message.finished_good_quantity);
                    }

                    r.message.raw_materials.forEach(function (item) {
                        let row = frm.add_child('manufacture_raw_material');
                        row.item_code = item.item_code;
                        row.item_name = item.item_name;
                        row.uom = item.uom;
                        row.warehouse = item.warehouse;
                        row.qty = item.qty;
                        row.bom_qty = item.bom_qty;
                    });

                    r.message.finished_goods.forEach(function (item) {
                        let row = frm.add_child('manufacture_finished_goods');
                        row.item_code = item.item_code;
                        row.item_name = item.item_name;
                        row.uom = item.uom;
                        row.warehouse = item.warehouse;
                        row.qty = item.qty;
                        row.bom_qty = item.bom_qty;
                    });

                    frm.refresh_fields();
                }
            }
        });
    },

    previous_manufature_stock_entry: function (frm) {
        if (frm.doc.previous_manufature_stock_entry && frm.doc.type === 'Packing') {
            frappe.call({
                method: 'cannabis_management.cannabis_management.doctype.manufacture_stock_entry.manufacture_stock_entry.get_previous_finished_goods',
                args: {
                    previous_entry: frm.doc.previous_manufature_stock_entry
                },
                callback: function (r) {
                    if (r.message) {
                        frm.clear_table('manufacture_raw_material');

                        r.message.forEach(function (item) {
                            let row = frm.add_child('manufacture_raw_material');
                            row.item_code = item.item_code;
                            row.uom = item.uom;
                            row.item_name = item.item_name;
                            row.uom = item.uom;
                            row.warehouse = item.warehouse;
                            row.qty = item.qty;
                            row.bom_qty = item.bom_qty;
                        });

                        frm.refresh_field('manufacture_raw_material');
                    }
                }
            });
        }
    },

    clear_tables: function (frm) {
        frm.clear_table('manufacture_raw_material');
        frm.clear_table('manufacture_finished_goods');
        frm.refresh_fields();
    },

    setup_batch_queries: function (frm) {
        // Setup batch_no filters for Manufacture Raw Material table
        if (frm.fields_dict['manufacture_raw_material']) {
            frm.fields_dict['manufacture_raw_material'].grid.get_field('batch_no').get_query = function (doc, cdt, cdn) {
                let child_row = locals[cdt][cdn];
                if (!child_row.item_code) {
                    frappe.msgprint(__('Please select an Item first'));
                    return {
                        filters: {
                            'name': ['=', '']
                        }
                    };
                }

                // Use ERPNext's standard batch query with formatting
                return {
                    query: "erpnext.controllers.queries.get_batch_no",
                    filters: {
                        'item_code': child_row.item_code,
                        'warehouse': child_row.warehouse || '',
                        'batch_qty': ['>', 0]
                    }
                };
            };
        }

        // Setup batch_no filters for Manufacture Finished Goods table
        if (frm.fields_dict['manufacture_finished_goods']) {
            frm.fields_dict['manufacture_finished_goods'].grid.get_field('batch_no').get_query = function (doc, cdt, cdn) {
                let child_row = locals[cdt][cdn];
                if (!child_row.item_code) {
                    frappe.msgprint(__('Please select an Item first'));
                    return {
                        filters: {
                            'name': ['=', '']
                        }
                    };
                }

                // Use ERPNext's standard batch query with formatting
                return {
                    query: "erpnext.controllers.queries.get_batch_no",
                    filters: {
                        'item_code': child_row.item_code,
                        'warehouse': child_row.warehouse || '',
                        'batch_qty': ['>', 0]
                    }
                };
            };
        }
    }
});

// Manufacture Raw Material Child Table Events
frappe.ui.form.on('Manufacture Raw Material', {
    item_code: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.item_code || !frm.doc.company) return;

        // Get warehouse for item if not set
        if (!row.warehouse) {
            frappe.call({
                method: 'cannabis_management.cannabis_management.doctype.manufacture_stock_entry.manufacture_stock_entry.get_item_warehouse',
                args: {
                    item_code: row.item_code,
                    company: frm.doc.company
                },
                callback: function (r) {
                    if (r.message) {
                        frappe.model.set_value(cdt, cdn, 'warehouse', r.message);
                    }
                }
            });
        }

        // Clear batch_no and available_qty when item changes
        frappe.model.set_value(cdt, cdn, 'batch_no', '');
        frappe.model.set_value(cdt, cdn, 'available_qty', 0);

        // Refresh the grid to update batch_no query
        frm.fields_dict['manufacture_raw_material'].grid.refresh();
    },

    warehouse: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Clear batch_no and available_qty when warehouse changes
        frappe.model.set_value(cdt, cdn, 'batch_no', '');
        frappe.model.set_value(cdt, cdn, 'available_qty', 0);

        // Refresh the grid to update batch_no query
        frm.fields_dict['manufacture_raw_material'].grid.refresh();
    },

    batch_no: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.batch_no) {
            frappe.model.set_value(cdt, cdn, 'available_qty', 0);
            return;
        }

        // Fetch available quantity from Batch doctype's batch_qty field
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'Batch',
                filters: { name: row.batch_no },
                fieldname: 'batch_qty'
            },
            callback: function (r) {
                let available_qty = 0;
                if (r.message && r.message.batch_qty) {
                    available_qty = r.message.batch_qty;
                }

                frappe.model.set_value(cdt, cdn, 'available_qty', available_qty);
            }
        });
    }
});

// Manufacture Finished Goods Child Table Events
frappe.ui.form.on('Manufacture Finished Goods', {
    item_code: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.item_code || !frm.doc.company) return;

        // Get warehouse for item if not set
        if (!row.warehouse) {
            frappe.call({
                method: 'cannabis_management.cannabis_management.doctype.manufacture_stock_entry.manufacture_stock_entry.get_item_warehouse',
                args: {
                    item_code: row.item_code,
                    company: frm.doc.company
                },
                callback: function (r) {
                    if (r.message) {
                        frappe.model.set_value(cdt, cdn, 'warehouse', r.message);
                    }
                }
            });
        }

        // Clear batch_no when item changes
        frappe.model.set_value(cdt, cdn, 'batch_no', '');
        frappe.model.set_value(cdt, cdn, 'available_qty', 0);

        // Refresh the grid to update batch_no query
        frm.fields_dict['manufacture_finished_goods'].grid.refresh();
    },

    warehouse: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Clear batch_no when warehouse changes
        frappe.model.set_value(cdt, cdn, 'batch_no', '');
        frappe.model.set_value(cdt, cdn, 'available_qty', 0);

        // Refresh the grid to update batch_no query
        frm.fields_dict['manufacture_finished_goods'].grid.refresh();
    },

    batch_no: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.batch_no) {
            frappe.model.set_value(cdt, cdn, 'available_qty', 0);
            return;
        }

        // Fetch available quantity from Batch doctype's batch_qty field
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'Batch',
                filters: { name: row.batch_no },
                fieldname: 'batch_qty'
            },
            callback: function (r) {
                let available_qty = 0;
                if (r.message && r.message.batch_qty) {
                    available_qty = r.message.batch_qty;
                }

                frappe.model.set_value(cdt, cdn, 'available_qty', available_qty);

                // Show info message for finished goods
                if (row.qty && row.qty > available_qty && available_qty > 0) {
                    frappe.msgprint({
                        title: __('Info'),
                        indicator: 'blue',
                        message: __('Current available quantity for batch {0} is {1}',
                            [row.batch_no, available_qty])
                    });
                }
            }
        });
    }
});
