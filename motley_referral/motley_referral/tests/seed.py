"""Stage demo data built on REAL customers and REAL payments already in the system.
   bench --site <site> execute motley_referral.tests.seed.seed      (create)
   bench --site <site> execute motley_referral.tests.seed.unseed    (remove everything it created)
Everything is prefixed 'TEST' (partners, queue referrals) so it is easy to spot."""
import frappe
from frappe.utils import flt

CO = "Motley Terpz"
ACCOUNT = "Referral Commissions - MT"
PARTNERS = {
    "Alpha": {"partner_name": "TEST Partner Alpha", "email": "test.alpha@example.com"},
    "Beta": {"partner_name": "TEST Partner Beta", "email": "test.beta@example.com"},
}
# (partner, real customer, acknowledged_on)  -> real payments on/after that date earn commission
ACKED = [
    ("Alpha", "Simply Mary", "2026-01-01"),
    ("Alpha", "Maven Genetics", "2026-01-01"),
    ("Beta", "818 Brands Los Angeles LLC (Brand)", "2026-01-20"),
    ("Beta", "Goodfellas", "2026-02-01"),
    ("Beta", "Chuck", "2026-04-01"),
]
QUEUE = [("Alpha", "TEST Green Leaf Dispensary"), ("Beta", "TEST Sunset Cannabis Co"), ("Beta", "Simply Mary")]  # last one trips the duplicate check


def seed():
    from motley_referral import engine
    from motley_referral.referral_program.doctype.referral_commission_statement.referral_commission_statement import create_monthly_statements

    frappe.set_user("Administrator")
    if not frappe.db.exists("Account", ACCOUNT):
        frappe.get_doc({"doctype": "Account", "account_name": "Referral Commissions", "parent_account": "Indirect Expenses - MT", "company": CO,
                        "root_type": "Expense", "is_group": 0}).insert(ignore_permissions=True)
    st = frappe.get_doc("Referral Settings")
    st.set("eligible_companies", [{"company": CO, "commission_expense_account": ACCOUNT}])
    st.save()
    frappe.clear_cache()

    partners = {}
    for key, v in PARTNERS.items():
        if frappe.db.exists("Referral Partner", {"partner_name": v["partner_name"]}):
            partners[key] = frappe.get_doc("Referral Partner", {"partner_name": v["partner_name"]})
            continue
        p = frappe.get_doc({"doctype": "Referral Partner", **v, "partner_type": "Individual", "agreement_date": "2026-01-01", "signed_agreement": "/files/test-agreement.pdf",
                            "compliance_confirmed": 1, "tax_id": "00-0000000", "payout_method": "ACH", "payout_details": "000123456789"}).insert()
        p.activate()
        partners[key] = p

    for key, cust, ack in ACKED:
        if frappe.db.exists("Partner Referral", {"customer": cust}):
            continue
        r = frappe.get_doc({"doctype": "Partner Referral", "referral_partner": partners[key].name, "business_name": cust, "email": "contact@example.com",
                            "contact_name": "TEST Contact"}).insert()
        r.acknowledge(customer=cust)
        # back-date so the customer's real, already-posted payments qualify
        frappe.db.set_value("Partner Referral", r.name, {"acknowledged_on": ack, "submitted_on": ack}, update_modified=False)
    for key, biz in QUEUE:
        if not frappe.db.exists("Partner Referral", {"business_name": biz, "status": "Submitted", "referral_partner": partners[key].name}):
            frappe.get_doc({"doctype": "Partner Referral", "referral_partner": partners[key].name, "business_name": biz, "email": "owner@example.com",
                            "contact_name": "TEST Owner", "phone": "555-0100"}).insert()
    if not frappe.db.exists("Partner Referral", {"business_name": "TEST Bay Distro"}):
        r = frappe.get_doc({"doctype": "Partner Referral", "referral_partner": partners["Alpha"].name, "business_name": "TEST Bay Distro", "email": "bay@example.com"}).insert()
        r.reject("Not a fit")

    res = engine.sync_ple(days=400)
    engine.refresh_window_fields()
    made = []
    for period in ("2026-03", "2026-06", "2026-08"):
        made += create_monthly_statements(period)
    # approve the two oldest statements so the board shows Approved + Purchase Invoices
    for n in made[:2]:
        s = frappe.get_doc("Referral Commission Statement", n)
        if s.docstatus == 0:
            s.submit()
    frappe.db.commit()
    print("lines created:", len(res["created"]), "| statements:", made)


def unseed():
    names = [n for n in frappe.get_all("Referral Partner", filters={"partner_name": ["like", "TEST Partner %"]}, pluck="name")]
    refs = frappe.get_all("Partner Referral", filters={"referral_partner": ["in", names or [""]]}, fields=["name", "customer"])
    for s in frappe.get_all("Referral Commission Statement", filters={"referral_partner": ["in", names or [""]]}, fields=["name", "docstatus", "purchase_invoice"]):
        if s.purchase_invoice:
            for dt in ("GL Entry",):
                frappe.db.sql("delete from `tabGL Entry` where voucher_type='Purchase Invoice' and voucher_no=%s", s.purchase_invoice)
            frappe.db.sql("delete from `tabPayment Ledger Entry` where voucher_type='Purchase Invoice' and voucher_no=%s", s.purchase_invoice)
            frappe.db.sql("delete from `tabPurchase Invoice Item` where parent=%s", s.purchase_invoice)
            frappe.db.sql("delete from `tabPurchase Invoice` where name=%s", s.purchase_invoice)
        frappe.db.sql("delete from `tabReferral Commission Statement Line` where parent=%s", s.name)
        frappe.db.sql("delete from `tabReferral Commission Statement` where name=%s", s.name)
    frappe.db.sql("delete from `tabReferral Commission Ledger` where referral_partner in %s", (tuple(names) or ("",),))
    for r in refs:
        if r.customer:
            frappe.db.set_value("Customer", r.customer, {"referral_partner": None, "partner_referral": None}, update_modified=False)
    frappe.db.sql("delete from `tabPartner Referral` where referral_partner in %s", (tuple(names) or ("",),))
    for n in names:
        p = frappe.get_doc("Referral Partner", n)
        frappe.db.sql("delete from `tabReferral Partner` where name=%s", n)
        for dt, nm in (("Supplier", p.supplier), ("User", p.portal_user)):
            if nm:
                try:
                    frappe.delete_doc(dt, nm, force=1, ignore_permissions=True)
                except Exception as e:
                    print("could not delete", dt, nm, e)
    frappe.db.commit()
    print("removed", len(names), "partners")
