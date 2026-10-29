(function() {
    console.log("Cannabis Management: Injecting Stock Balance filter patch...");

    const patch_add_inventory_dimensions = () => {
        if (window.erpnext && erpnext.utils && erpnext.utils.add_inventory_dimensions) {
            if (erpnext.utils.add_inventory_dimensions._patchedByCannabis) return;

            const original_fn = erpnext.utils.add_inventory_dimensions;
            erpnext.utils.add_inventory_dimensions = function(report_name, index) {
                if (report_name === "Stock Balance") {
                    console.log("Cannabis Management: Customizing Stock Balance dimensions");
                    frappe.call({
                        method: "erpnext.stock.doctype.inventory_dimension.inventory_dimension.get_inventory_dimensions",
                        callback: function (r) {
                            if (r.message && r.message.length) {
                                let filters = frappe.query_reports[report_name].filters;
                                r.message.forEach((dimension) => {
                                    let existing_filter = filters.find((el) => el.fieldname === dimension["fieldname"]);

                                    if (!existing_filter) {
                                        filters.splice(index, 0, {
                                            fieldname: dimension["fieldname"],
                                            label: __(dimension["doctype"]),
                                            fieldtype: "MultiSelectList",
                                            depends_on: "",
                                            get_data: function (txt) {
                                                return frappe.db.get_link_options(dimension["doctype"], txt);
                                            },
                                        });
                                    } else {
                                        existing_filter["fieldtype"] = "MultiSelectList";
                                        existing_filter["depends_on"] = "";
                                        existing_filter["get_data"] = function (txt) {
                                            return frappe.db.get_link_options(dimension["doctype"], txt);
                                        };
                                    }
                                });
                                if (frappe.query_report && frappe.query_report.report_name === "Stock Balance") {
                                    frappe.query_report.refresh();
                                }
                            }
                        },
                    });
                } else {
                    return original_fn.apply(this, arguments);
                }
            };
            erpnext.utils.add_inventory_dimensions._patchedByCannabis = true;
            console.log("Cannabis Management: Successfully patched add_inventory_dimensions");
        } else {
            setTimeout(patch_add_inventory_dimensions, 500);
        }
    };

    patch_add_inventory_dimensions();

    const fallback_patch = () => {
        if (frappe.query_reports && frappe.query_reports["Stock Balance"]) {
            let filters = frappe.query_reports["Stock Balance"].filters;
            let changed = false;
            filters.forEach(f => {
                if ((f.fieldname === 'project' || f.label === 'Project') && f.depends_on) {
                    f.depends_on = "";
                    changed = true;
                }
            });
            if (changed && frappe.query_report && frappe.query_report.report_name === "Stock Balance") {
                frappe.query_report.refresh();
            }
        }
    };

    setInterval(fallback_patch, 3000);
})();
