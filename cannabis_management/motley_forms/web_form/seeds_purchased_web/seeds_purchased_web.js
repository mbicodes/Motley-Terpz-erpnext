frappe.ready(function() {
    frappe.web_form.on("seed", (field, value) => {
        if (value) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Item",
                    filters: { name: value },
                    fieldname: "item_group"
                },
                callback: function(r) {
                    if (r.message) {
                        frappe.web_form.set_value("type", r.message.item_group);
                    }
                }
            });
        } else {
            frappe.web_form.set_value("type", "");
        }
    });
});