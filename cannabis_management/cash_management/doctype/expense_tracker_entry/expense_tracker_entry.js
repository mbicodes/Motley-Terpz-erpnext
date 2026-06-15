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

        const finance_roles = ["Finance Manager", "Accounts Manager", "System Manager"];
        const has_finance = frappe.user_roles.some(r => finance_roles.includes(r));

        if (frm.doc.docstatus === 1 && has_finance) {
            const doc      = frm.doc;
            const employee = doc.employee || "";

            const remarks = "[Expense Tracker Entry " + doc.name + "] "
                + (doc.direction || "")
                + (doc.transaction_type ? " — " + doc.transaction_type : "")
                + (doc.notes ? " | " + doc.notes.substring(0, 80) : "")
                + (employee ? " | Employee: " + employee : "");

            // ── Create Payment Entry ─────────────────────────────────────────
            // Navigates Finance to a new Pay entry pre-filled from this ETE.
            frm.add_custom_button(__("Create Payment Entry"), () => {
                frappe.route_options = {
                    payment_type:   "Pay",       // expenses & reimbursements both pay out
                    posting_date:   doc.date,
                    company:        doc.company,
                    reference_no:   doc.name,
                    reference_date: doc.date,
                    remarks:        remarks,
                };

                window._ete_pe_pending = {
                    mode_of_payment: "Cash",
                    paid_amount:     doc.amount,
                    received_amount: doc.amount,
                    party_type:      employee ? "Employee" : "",
                    party:           employee,
                };

                frappe.new_doc("Payment Entry");

                frappe.after_ajax(function() {
                    var pending = window._ete_pe_pending;
                    if (!pending || !cur_frm || cur_frm.doctype !== "Payment Entry" || !cur_frm.is_new()) return;
                    window._ete_pe_pending = null;

                    cur_frm.set_value("mode_of_payment", pending.mode_of_payment);
                    if (pending.party_type) {
                        cur_frm.set_value("party_type", pending.party_type);
                        setTimeout(function() {
                            if (pending.party) cur_frm.set_value("party", pending.party);
                            cur_frm.set_value("paid_amount",     pending.paid_amount);
                            cur_frm.set_value("received_amount", pending.received_amount);
                        }, 400);
                    } else {
                        cur_frm.set_value("paid_amount",     pending.paid_amount);
                        cur_frm.set_value("received_amount", pending.received_amount);
                    }
                });
            }, __("Accounting"));

            // ── Create Journal Entry ─────────────────────────────────────────
            frm.add_custom_button(__("Create Journal Entry"), () => {
                frappe.route_options = {
                    company:      doc.company,
                    posting_date: doc.date,
                    user_remark:  remarks,
                };
                frappe.new_doc("Journal Entry");
            }, __("Accounting"));

            // ── Link existing PE/JE ──────────────────────────────────────────
            if (!frm.doc.payment_entry && !frm.doc.journal_entry) {
                frm.add_custom_button(__("Link Payment / Journal Entry"), () => {
                    const d = new frappe.ui.Dialog({
                        title: "Link Accounting Entry",
                        fields: [
                            { label: "Entry Type", fieldname: "entry_type", fieldtype: "Select", options: "\nPayment Entry\nJournal Entry", reqd: 1 },
                            { label: "Entry Name", fieldname: "entry_name", fieldtype: "Dynamic Link", options: "entry_type", reqd: 1 },
                        ],
                        primary_action_label: "Link",
                        primary_action(vals) {
                            const field = vals.entry_type === "Payment Entry" ? "payment_entry" : "journal_entry";
                            frappe.db.set_value("Expense Tracker Entry", frm.doc.name,
                                { [field]: vals.entry_name, gl_entry_created: 1 }
                            ).then(() => {
                                d.hide(); frm.reload_doc();
                                frappe.show_alert({ message: "Entry linked.", indicator: "green" });
                            });
                        },
                    });
                    d.show();
                }, __("Accounting"));
            }
        }

        // Real-time balance listener
        frappe.realtime.on("cash_balance_update", (data) => {
            if (data.person === frm.doc.cash_tracker_person) {
                frappe.show_alert({
                    message: "Net Owed updated: " + format_currency(data.net_owed),
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
                        if (r.default_entity && !frm.doc.entity) frm.set_value("entity", r.default_entity);
                    }
                }
            );
        }
    },

    direction(frm) {
        frm.toggle_reqd("receipt", frm.doc.direction === "Expense");
        frm.refresh_field("receipt");
    }
});
