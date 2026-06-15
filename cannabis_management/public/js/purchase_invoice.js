frappe.ui.form.on("Purchase Invoice", {
    refresh(frm) {
        frm.add_custom_button("Get Shipments", async function () {

            if (!frm.doc.supplier) {
                frappe.msgprint("Please select Supplier first.");
                return;
            }

            frappe.call({
                method: "cannabis_management.cannabis_management.custom.purchase_invoice.get_shipments_for_invoice",
                args: { supplier: frm.doc.supplier },
                callback: async function (r) {

                    if (!r.message || r.message.length === 0) {
                        frappe.msgprint("No Shipment Found for this supplier.");
                        return;
                    }

                    // 1️ Remove default blank row
                    if (frm.doc.items && frm.doc.items.length === 1) {
                        let row = frm.doc.items[0];
                        if (!row.item_code) {
                            frm.clear_table("items");
                        }
                    }

                    // 2️ Fetch Item master details
                    let item = await frappe.db.get_value(
                        "Item",
                        "STO-ITEM-2025-00008",
                        ["item_code", "item_name", "stock_uom"]
                    );

                    // 3️ Check already added shipments → prevent duplicates
                    let existing_shipments = frm.doc.items.map(i => i.description);

                    r.message.forEach(sh => {

                        let desc = "Shipment: " + sh.name;

                        if (existing_shipments.includes(desc)) {
                            // Already added → skip
                            return;
                        }

                        let row = frm.add_child("items");
                        row.item_code = item.message.item_code;
                        row.item_name = item.message.item_name;
                        row.uom = item.message.stock_uom;
                        row.qty = 1;
                        row.rate = sh.shipment_amount || 0;
                        row.description = desc;

                        // Apply project to newly added shipment rows if project is set
                        if (frm.doc.project) {
                            row.batch = frm.doc.project;
                        }
                    });

                    frm.refresh_field("items");
                }
            });
        });
    },

    project: function (frm) {
        if (frm.doc.project) {
            $.each(frm.doc.items || [], function (i, item) {
                frappe.model.set_value(
                    item.doctype,
                    item.name,
                    "batch",
                    frm.doc.project
                );
            });
        }
    },

    items_add: function (frm, cdt, cdn) {
        if (frm.doc.project) {
            frappe.model.set_value(cdt, cdn, "batch", frm.doc.project);
        }
    },
});