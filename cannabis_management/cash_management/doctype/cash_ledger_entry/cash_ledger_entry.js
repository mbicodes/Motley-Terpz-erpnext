frappe.ui.form.on("Cash Ledger Entry", {
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
            // ── Create Payment Entry ──────────────────────────────────────────
            frm.add_custom_button(__("Create Payment Entry"), () => {
                const doc = frm.doc;
                const is_inflow = doc.direction === "Cash In";
                const employee  = doc.employee || "";

                const remarks = "[Cash Ledger Entry " + doc.name + "] "
                    + (doc.transaction_type || "")
                    + (doc.notes ? " — " + doc.notes : "")
                    + (employee ? " | Employee: " + employee : "");

                // Only pre-fill stable fields — mode_of_payment / amounts / party_type
                // are set after the form loads to avoid ERPNext clearing the party field
                // and collapsing child-table sections.
                frappe.route_options = {
                    payment_type:   is_inflow ? "Receive" : "Pay",
                    posting_date:   doc.date,
                    company:        doc.company,
                    reference_no:   doc.invoice_number || doc.name,
                    reference_date: doc.date,
                    remarks:        remarks,
                };

                // Stash post-load values in a flag (no global-state race possible since
                // Frappe navigates synchronously before the next user action).
                window._cle_pe_pending = {
                    mode_of_payment:  "Cash",
                    paid_amount:      doc.amount,
                    received_amount:  doc.amount,
                    party_type:       employee ? "Employee" : "",
                    party:            employee,
                };

                frappe.new_doc("Payment Entry");

                // Apply party + amounts after the PE form has finished loading.
                // frappe.after_ajax fires after the next async cycle (form render).
                frappe.after_ajax(function() {
                    const pending = window._cle_pe_pending;
                    if (!pending || !cur_frm || cur_frm.doctype !== "Payment Entry" || !cur_frm.is_new()) return;
                    window._cle_pe_pending = null;

                    cur_frm.set_value("mode_of_payment", pending.mode_of_payment);

                    if (pending.party_type) {
                        cur_frm.set_value("party_type", pending.party_type);
                        // Wait for party_type's change event (which clears party) to settle,
                        // then set party and amounts.
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

            // ── Create Journal Entry ──────────────────────────────────────────
            frm.add_custom_button(__("Create Journal Entry"), () => {
                const doc = frm.doc;

                frappe.route_options = {
                    company:      doc.company,
                    posting_date: doc.date,
                    user_remark:  "[Cash Ledger Entry " + doc.name + "] "
                        + (doc.transaction_type || "")
                        + (doc.notes ? " — " + doc.notes : ""),
                };

                frappe.new_doc("Journal Entry");
            }, __("Accounting"));

            // ── Link existing PE/JE ───────────────────────────────────────────
            if (!frm.doc.payment_entry && !frm.doc.journal_entry) {
                frm.add_custom_button(__("Link Payment / Journal Entry"), () => {
                    const d = new frappe.ui.Dialog({
                        title: "Link Accounting Entry",
                        fields: [
                            {
                                label: "Entry Type",
                                fieldname: "entry_type",
                                fieldtype: "Select",
                                options: "\nPayment Entry\nJournal Entry",
                                reqd: 1,
                            },
                            {
                                label: "Entry Name",
                                fieldname: "entry_name",
                                fieldtype: "Dynamic Link",
                                options: "entry_type",
                                reqd: 1,
                            },
                        ],
                        primary_action_label: "Link",
                        primary_action(vals) {
                            const field = vals.entry_type === "Payment Entry"
                                ? "payment_entry" : "journal_entry";
                            frappe.db.set_value(
                                "Cash Ledger Entry", frm.doc.name,
                                { [field]: vals.entry_name, gl_entry_created: 1 }
                            ).then(() => {
                                d.hide();
                                frm.reload_doc();
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
                    message: "Balance updated — Net Cash: " + format_currency(data.net_cash),
                    indicator: "blue"
                }, 5);
            }
        });

        // Form 8300 warning banner
        if (frm.doc.form_8300_required && !frm.doc.form_8300_filed) {
            frm.dashboard.add_comment(
                "⚠️  IRS Form 8300 required for this transaction. Please file within 15 days of the transaction date.",
                "red",
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

    amount(frm) {
        if (frm.doc.direction === "Cash In" && frm.doc.amount >= 10000) {
            frappe.show_alert({
                message: "⚠️  Amount ≥ $10,000. IRS Form 8300 will be required upon submission.",
                indicator: "orange"
            }, 8);
        }
    },

    direction(frm) {
        frm.trigger("amount");
    }
});
