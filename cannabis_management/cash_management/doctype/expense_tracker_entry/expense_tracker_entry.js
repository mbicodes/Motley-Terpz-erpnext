frappe.ui.form.on("Expense Tracker Entry", {
    refresh(frm) {
        // Auto-fill person from session user on new doc
        if (frm.is_new()) {
            frappe.db.get_value(
                "Cash Tracker Person",
                { user: frappe.session.user },
                ["name", "default_entity", "employee"],
                (r) => {
                    if (r && r.name) {
                        frm.set_value("cash_tracker_person", r.name);
                        if (r.default_entity) frm.set_value("entity", r.default_entity);
                        if (r.employee) frm.set_value("employee", r.employee);
                    }
                }
            );
        }

        // Create Accounting Entry button — Finance / Accounts Manager only
        const finance_roles = ["Finance Manager", "Accounts Manager", "System Manager"];
        const has_finance = frappe.user_roles.some(r => finance_roles.includes(r));

        if (frm.doc.docstatus === 1 && !frm.doc.gl_entry_created && has_finance) {
            frm.add_custom_button(__("Create Journal Entry"), () => {
                frappe.confirm(
                    `Create a Journal Entry for <b>${frm.doc.name}</b>?`,
                    () => {
                        frappe.call({
                            method: "cannabis_management.cash_management.utils.cash_utils.create_journal_entry",
                            args: { doctype: frm.doctype, docname: frm.doc.name },
                            callback(r) {
                                if (r.message) {
                                    frappe.show_alert({
                                        message: `Journal Entry <b>${r.message}</b> created.`,
                                        indicator: "green"
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __("Accounting"));

            frm.add_custom_button(__("Create Payment Entry"), () => {
                frappe.confirm(
                    `Create a Payment Entry for <b>${frm.doc.name}</b>?`,
                    () => {
                        frappe.call({
                            method: "cannabis_management.cash_management.utils.cash_utils.create_payment_entry",
                            args: { doctype: frm.doctype, docname: frm.doc.name },
                            callback(r) {
                                if (r.message) {
                                    frappe.show_alert({
                                        message: `Payment Entry <b>${r.message}</b> created.`,
                                        indicator: "green"
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __("Accounting"));
        }

        // Real-time balance listener
        frappe.realtime.on("cash_balance_update", (data) => {
            if (data.person === frm.doc.cash_tracker_person) {
                frappe.show_alert({
                    message: `Net Owed updated: ${format_currency(data.net_owed)}`,
                    indicator: "blue"
                }, 5);
            }
        });

        // Receipt warning for Expense direction
        if (frm.doc.direction === "Expense" && !frm.doc.receipt && frm.doc.docstatus === 0) {
            frm.dashboard.add_comment(
                "A receipt is required for Expense entries. Please attach it before submitting.",
                "orange",
                true
            );
        }
    },

    cash_tracker_person(frm) {
        if (frm.doc.cash_tracker_person) {
            frappe.db.get_value(
                "Cash Tracker Person",
                frm.doc.cash_tracker_person,
                ["employee", "default_entity"],
                (r) => {
                    if (r) {
                        if (r.employee) frm.set_value("employee", r.employee);
                        if (r.default_entity && !frm.doc.entity) {
                            frm.set_value("entity", r.default_entity);
                        }
                    }
                }
            );
        }
    },

    direction(frm) {
        // Dynamically make receipt mandatory for Expense
        frm.toggle_reqd("receipt", frm.doc.direction === "Expense");
        frm.refresh_field("receipt");
    }
});
