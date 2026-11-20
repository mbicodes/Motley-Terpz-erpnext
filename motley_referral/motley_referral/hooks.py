app_name = "motley_referral"
app_title = "Motley Referral"
app_publisher = "alltechvirtual.com"
app_description = "Referral Partner Program for Motley ERPNext"
app_email = "mbi@alltechvirtual.com"
app_license = "mit"

required_apps = ["erpnext"]

after_install = "motley_referral.install.after_install"
after_migrate = "motley_referral.install.after_migrate"

# Partners land on the portal, never the desk
role_home_page = {"Referral Partner": "partner"}
# ...and their session cannot call desk APIs (workspace list etc.)
before_request = ["motley_referral.portal_user.block_desk_api"]

website_route_rules = [
    {"from_route": "/partner/accounts/<name>", "to_route": "partner/account"},
]

doc_events = {
    "Payment Ledger Entry": {"on_submit": "motley_referral.engine.on_ple_submit"},
    "Payment Entry": {
        "on_submit": [
            "motley_referral.engine.on_voucher_submit",
            "motley_referral.referral_program.doctype.referral_commission_statement.referral_commission_statement.on_payment_entry_submit",
        ],
        "on_cancel": [
            "motley_referral.engine.on_voucher_cancel",
            "motley_referral.referral_program.doctype.referral_commission_statement.referral_commission_statement.on_payment_entry_cancel",
        ],
    },
    "Journal Entry": {
        "on_submit": "motley_referral.engine.on_voucher_submit",
        "on_cancel": "motley_referral.engine.on_voucher_cancel",
    },
    "Unreconcile Payment": {"on_submit": "motley_referral.engine.on_unreconcile_submit"},
}

scheduler_events = {
    "cron": {
        "0 2 * * *": ["motley_referral.engine.daily"],  # daily 02:00 (site timezone)
        "0 * * * *": ["motley_referral.engine.hourly_statement_tick"],  # monthly run on Settings run day/hour
    }
}

permission_query_conditions = {
    "Referral Partner": "motley_referral.permissions.referral_partner_query",
    "Partner Referral": "motley_referral.permissions.partner_referral_query",
    "Referral Commission Ledger": "motley_referral.permissions.ledger_query",
    "Referral Commission Statement": "motley_referral.permissions.statement_query",
}
has_permission = {
    "Referral Partner": "motley_referral.permissions.referral_partner_has",
    "Partner Referral": "motley_referral.permissions.partner_referral_has",
    "Referral Commission Ledger": "motley_referral.permissions.ledger_has",
    "Referral Commission Statement": "motley_referral.permissions.statement_has",
}

fixtures = []

jinja = {
    "methods": [
        "motley_referral.print_utils.rp_usd",
        "motley_referral.print_utils.rp_badge",
        "motley_referral.print_utils.rp_mask",
        "motley_referral.print_utils.rp_month_label",
        "motley_referral.print_utils.rp_company_footer",
        "motley_referral.print_utils.rp_company_logo",
        "motley_referral.print_utils.rp_statement_detail",
        "motley_referral.print_utils.rp_month_strip",
        "motley_referral.print_utils.rp_partner_referrals",
        "motley_referral.print_utils.rp_partner_statements",
        "motley_referral.print_utils.rp_signatory",
        "motley_referral.print_utils.rp_default_company",
    ]
}
