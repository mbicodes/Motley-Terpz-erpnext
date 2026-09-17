frappe.ui.form.on("Stock Entry", {
    refresh: function (frm) {
        // Source/Target Tags: only offer Metric Tags whose License matches
        // the row's Source/Target Warehouse.
        cannabis_management.metric_tag.filter_by_warehouse(frm, "tags", "s_warehouse");
        cannabis_management.metric_tag.filter_by_warehouse(frm, "to_tags", "t_warehouse");
        toggle_tag_mandatory(frm);

        frm.fields_dict.items.grid.update_docfield_property("project", "reqd", 0);
        $.each(frm.doc.items || [], function (i, item) {
            if (item.custom_project_mandatory) {
                frappe.meta.get_docfield("Stock Entry Detail", "project", frm.doc.name).reqd = 1;
            }
        });
        frm.refresh_fields();
        calculate_total_quantity(frm);

        if (frm.is_new() && frm.doc.stock_entry_type === "Manufacture" && frm.doc.work_order) {
            setTimeout(() => pin_rm_qty_from_wo(frm), 120);
            _fix_operating_cost_from_wo(frm);
        }
    },

    stock_entry_type: function (frm) {
        toggle_tag_mandatory(frm);
    },

    project: function (frm) {
        if (frm.doc.project) {
            $.each(frm.doc.items || [], function (i, item) {
                frappe.model.set_value(item.doctype, item.name, "project", frm.doc.project);
                frappe.model.set_value(item.doctype, item.name, "batch", frm.doc.project);
            });
        }
    },

    items_add: function (frm, cdt, cdn) {
        if (frm.doc.project) {
            frappe.model.set_value(cdt, cdn, "project", frm.doc.project);
            frappe.model.set_value(cdt, cdn, "batch", frm.doc.project);
        }
        toggle_tag_mandatory(frm);
        calculate_total_quantity(frm);
    },

    items_remove: function (frm) {
        calculate_total_quantity(frm);
    },
});

frappe.ui.form.on("Stock Entry Detail", {
    qty: function (frm, cdt, cdn) {
        setTimeout(() => calculate_total_quantity(frm), 300);
    },

    amount: function (frm, cdt, cdn) {
        // Repack finished-good (t_warehouse only) rows: core recalculates
        // rate/amount from the outgoing cost on every save unless
        // set_basic_rate_manually is checked, and nothing client-side keeps
        // basic_rate in step with a direct Amount edit -- so without this,
        // whatever's typed here can get overwritten before/On save.
        let row = locals[cdt][cdn];
        if (frm.doc.stock_entry_type !== "Repack" || !row.t_warehouse || row.s_warehouse) {
            return;
        }
        // Conversion Entry drafts are rebalanced against the raw material cost
        // on every save, so pinning a hand-typed amount here would only be
        // overwritten -- and would freeze the row in the meantime.
        if (frm.doc.custom_conversion_entry_reference) {
            return;
        }
        if (!row.set_basic_rate_manually) {
            frappe.model.set_value(cdt, cdn, "set_basic_rate_manually", 1);
        }
        if (flt(row.qty)) {
            frappe.model.set_value(cdt, cdn, "basic_rate", flt(row.amount) / flt(row.qty));
        }
        frappe.model.set_value(cdt, cdn, "basic_amount", flt(row.amount));
    },

    is_finished_item: function (frm, cdt, cdn) {
        setTimeout(() => calculate_total_quantity(frm), 300);
    },

    item_code: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item_code) {
            frappe.db.get_value("Item", row.item_code, "custom_project_mandatory", function (r) {
                if (r) {
                    frappe.model.set_value(cdt, cdn, "custom_project_mandatory", r.custom_project_mandatory || 0);
                }
            });
            if (frm.doc.project) {
                setTimeout(function () {
                    frappe.model.set_value(cdt, cdn, "project", frm.doc.project);
                    frappe.model.set_value(cdt, cdn, "batch", frm.doc.project);
                }, 500);
            }
        } else {
            frappe.model.set_value(cdt, cdn, "custom_project_mandatory", 0);
            frappe.model.set_value(cdt, cdn, "custom_project_back_qty", 0);
        }
    },

    custom_project_mandatory: function (frm, cdt, cdn) {
        toggle_project_mandatory(frm);
    },

    project: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.custom_project_mandatory && row.item_code && row.project && row.s_warehouse) {
            fetch_project_qty(frm, cdt, cdn, row);
        }
        if (row.project) {
            frappe.model.set_value(cdt, cdn, "batch", row.project);
        }
    },

    s_warehouse: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.custom_project_mandatory && row.item_code && row.project && row.s_warehouse) {
            fetch_project_qty(frm, cdt, cdn, row);
        }
        toggle_tag_mandatory(frm);
    },

    t_warehouse: function (frm) {
        toggle_tag_mandatory(frm);
    },
});

function toggle_project_mandatory(frm) {
    let any_mandatory = (frm.doc.items || []).some((item) => item.custom_project_mandatory);
    frm.fields_dict.items.grid.update_docfield_property("project", "reqd", any_mandatory ? 1 : 0);
    frm.refresh_fields();
}

// Repack only: Source/Target Tags become mandatory per row, based on which
// warehouse that row actually uses -- a raw-material row (Source Warehouse
// only) needs a Source Tag, a finished-good row (Target Warehouse only)
// needs a Target Tag, and never both on the same row. Outside Repack, this
// leaves the doctype's own defaults alone (Source Tags always required,
// Target Tags optional) -- only Repack rows get this per-row treatment.
// frm.set_df_property(..., row.name) scopes the change to that single grid
// row instead of the whole "tags"/"to_tags" column, which is what makes
// per-row (not per-column) mandatory possible here.
function toggle_tag_mandatory(frm) {
    let is_repack = frm.doc.stock_entry_type === "Repack";
    (frm.doc.items || []).forEach(function (row) {
        let tags_reqd = is_repack ? (row.s_warehouse ? 1 : 0) : 1;
        let to_tags_reqd = is_repack ? (row.t_warehouse ? 1 : 0) : 0;
        frm.set_df_property("items", "reqd", tags_reqd, frm.doc.name, "tags", row.name);
        frm.set_df_property("items", "reqd", to_tags_reqd, frm.doc.name, "to_tags", row.name);
    });
}

function fetch_project_qty(frm, cdt, cdn, row) {
    frappe.call({
        method: "cannabis_management.cannabis_management.custom.stock_entry.get_project_qty",
        args: {
            item_code: row.item_code,
            warehouse: row.s_warehouse,
            project: row.project,
        },
        callback: function (r) {
            if (r.message !== undefined) {
                frappe.model.set_value(cdt, cdn, "custom_project_back_qty", r.message);
            }
        },
    });
}

function pin_rm_qty_from_wo(frm) {
    frappe.call({
        method: "cannabis_management.cannabis_management.custom.stock_entry.get_wo_rm_planned_qty",
        args: { work_order: frm.doc.work_order },
        callback: function (r) {
            if (!r.message) return;
            let planned = r.message;
            let promises = [];
            (frm.doc.items || []).forEach((item) => {
                if (item.is_finished_item || item.is_scrap_item || !item.s_warehouse) return;
                let pinned = planned[item.item_code];
                if (pinned !== undefined && Math.abs(item.qty - pinned) > 0.0001) {
                    promises.push(
                        frappe.model.set_value(item.doctype, item.name, "qty", pinned)
                    );
                }
            });
            if (promises.length) {
                Promise.all(promises).then(() => frm.refresh_field("items"));
            }
        },
    });
}

function _fix_operating_cost_from_wo(frm) {
    frappe.call({
        method: "cannabis_management.doc_hooks.stock_entry.get_wo_cost_breakdown",
        args: {
            work_order: frm.doc.work_order,
            company: frm.doc.company,
            fg_completed_qty: frm.doc.fg_completed_qty,
            wo_qty: null,
        },
        callback: function (r) {
            if (!r.message || !r.message.length) return;

            // Clear all additional costs — server validate owns this field
            frm.doc.additional_costs = [];

            // Add per-account rows
            r.message.forEach(item => {
                frm.add_child("additional_costs", {
                    expense_account: item.expense_account,
                    description: item.description,
                    amount: item.amount,
                });
            });

            // Recalculate total from all rows
            let total = (frm.doc.additional_costs || []).reduce((s, c) => s + flt(c.amount), 0);
            frm.set_value("total_additional_costs", total);
            frm.refresh_field("additional_costs");
        },
    });
}

function calculate_total_quantity(frm) {
    let finished_qty = 0;
    let raw_qty = 0;

    (frm.doc.items || []).forEach((item) => {
        if (item.is_finished_item) {
            finished_qty += item.qty || 0;
        } else {
            raw_qty += item.qty || 0;
        }
    });

    const total_qty =
        frm.doc.stock_entry_type === "Repack"
            ? finished_qty
            : finished_qty + raw_qty;

    frm.doc.total_quantity = total_qty;
    frm.refresh_field("total_quantity");
}