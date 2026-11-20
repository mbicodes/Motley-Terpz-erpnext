frappe.ui.form.on("Referral Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Run Statements Now"), () => {
            frappe.prompt({ fieldname: "period", label: __("Period (YYYY-MM)"), fieldtype: "Data", default: moment().subtract(1, "month").format("YYYY-MM"), reqd: 1 },
                v => frappe.call({
                    method: "motley_referral.referral_program.doctype.referral_commission_statement.referral_commission_statement.run_now",
                    args: { period: v.period }, freeze: true,
                }).then(r => frappe.show_alert({ message: __("{0} statement(s) created", [r.message]), indicator: "green" })),
                __("Run Commission Statements"), __("Run"));
        });
    },
});
