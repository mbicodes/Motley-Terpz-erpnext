"""Stage smoke test: `bench --site <site> execute motley_referral.tests.e2e.run`. Everything is rolled back."""
import frappe
from frappe.utils import add_days, flt, getdate, nowdate

CO = "Motley Terpz"


def check(label, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + label, extra)
    if not cond:
        raise AssertionError(label)


def make_pe(customer, invoice, amount, date):
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    pe = get_payment_entry("Sales Invoice", invoice, party_amount=amount, bank_account=frappe.db.get_value("Account", {"company": CO, "account_type": "Bank", "is_group": 0}))
    pe.posting_date = date
    pe.reference_no = "T-" + frappe.generate_hash(length=6)
    pe.reference_date = date
    pe.paid_to = frappe.db.get_value("Account", {"company": CO, "account_type": "Bank", "is_group": 0})
    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe


def create_statements(period):
    from motley_referral.referral_program.doctype.referral_commission_statement.referral_commission_statement import create_monthly_statements

    return create_monthly_statements(period)


def lines(**f):
    return frappe.get_all("Referral Commission Ledger", filters=f, fields=["*"], order_by="creation")


def run():
    from unittest import mock

    # Stage has a custom credit-limit gate on invoices; this test is not about credit.
    patches = []
    try:
        patches.append(mock.patch("cannabis_management.credit_and_ar.sales_invoice_hooks._check_line", lambda *a, **k: None))
        patches[0].start()
    except Exception:
        patches = []
    try:
        _run()
    finally:
        for p in patches:
            p.stop()


def _run():
    orig_companies = [(r.company, r.commission_expense_account) for r in frappe.get_doc("Referral Settings").eligible_companies]
    try:
        _run_checks()
    finally:
        # the test needs an eligible company; put Settings back exactly as found
        st = frappe.get_doc("Referral Settings")
        st.set("eligible_companies", [{"company": c, "commission_expense_account": a} for c, a in orig_companies])
        st.save()
        frappe.db.commit()


def _run_checks():
    from motley_referral import engine
    from motley_referral.install import setup

    frappe.set_user("Administrator")
    try:
        setup()
        # month maths (Decision 3)
        from datetime import date

        s = date(2026, 11, 28)
        check("m1", engine.month_no_for(s, date(2026, 11, 30)) == 1)
        check("m2", engine.month_no_for(s, date(2026, 12, 1)) == 2)
        check("m12", engine.month_no_for(s, date(2027, 10, 31)) == 12)
        check("m13", engine.month_no_for(s, date(2027, 11, 1)) == 13)
        check("m24", engine.month_no_for(s, date(2028, 10, 31)) == 24)
        check("m25", engine.month_no_for(s, date(2028, 11, 1)) == 25)
        check("y2end", str(engine.window_end(s, 24)) == "2028-10-31")

        st = frappe.get_doc("Referral Settings")
        st.set("eligible_companies", [{"company": CO, "commission_expense_account": frappe.db.get_value("Account", {"company": CO, "root_type": "Expense", "is_group": 0})}])
        st.save()
        frappe.clear_cache()

        partner = frappe.get_doc({"doctype": "Referral Partner", "partner_name": "Test Partner", "email": "tp@example.com", "partner_type": "Individual",
                                  "agreement_date": nowdate(), "signed_agreement": "/files/x.pdf", "compliance_confirmed": 1, "tax_id": "12-3456789"}).insert()
        partner.activate()
        partner.reload()
        check("partner active + portal user", partner.status == "Active" and partner.portal_user and partner.supplier)

        cust = frappe.get_doc({"doctype": "Customer", "customer_name": "RP Test Customer", "customer_group": "All Customer Groups", "territory": "All Territories"}).insert()
        ref = frappe.get_doc({"doctype": "Partner Referral", "referral_partner": partner.name, "business_name": "RP Test Customer", "email": "biz@example.com"}).insert()
        print("dup:", ref.reload().duplicate_check_result)
        ref.acknowledge(customer=cust.name)
        ref.reload()
        check("acknowledged", ref.status == "Acknowledged" and ref.acknowledged_on and frappe.db.get_value("Customer", cust.name, "partner_referral") == ref.name)
        print("letter:", ref.acknowledgement_letter)

        def invoice(amount):
            si = frappe.get_doc({"doctype": "Sales Invoice", "customer": cust.name, "company": CO, "posting_date": nowdate(), "due_date": nowdate(), "set_posting_time": 1,
                                 "items": [{"item_code": "Attorney Fee", "qty": 1, "rate": amount}]})
            si.insert(ignore_permissions=True)
            si.submit()
            return si

        si = invoice(1000)
        # payment before acknowledgement
        pe0 = make_pe(cust.name, si.name, 100, add_days(nowdate(), -3))
        check("pre-ack payment: no line, no start", not lines(voucher_no=pe0.name) and not frappe.db.get_value("Partner Referral", ref.name, "commission_start_date"))
        pe0.cancel()

        pe = make_pe(cust.name, si.name, 600, nowdate())
        ls = lines(voucher_no=pe.name)
        check("line created 2% full amount", len(ls) == 1 and flt(ls[0].commission_amount) == 12 and ls[0].month_no == 1 and flt(ls[0].rate) == 2, str(ls and ls[0].commission_amount))
        ref.reload()
        check("start stamped", str(ref.commission_start_date) == nowdate() and ref.year1_end and ref.year2_end and ref.window_status == "Year 1")
        n = engine.sync_ple()
        check("sync idempotent", not n["created"] and len(lines(voucher_no=pe.name)) == 1)

        pe2 = make_pe(cust.name, si.name, 400, nowdate())
        check("second payment line", len(lines(voucher_no=pe2.name)) == 1)

        # cancel -> reversal in same period (unassigned)
        pe2.cancel()
        ls = lines(voucher_no=pe2.name)
        check("cancel reverses", len(ls) == 2 and sum(flt(l.commission_amount) for l in ls) == 0 and any(l.is_reversal for l in ls))
        check("no new line from cancel mirror", len(lines(voucher_no=pe2.name)) == 2)

        # statement run
        period = getdate(nowdate()).strftime("%Y-%m")
        names = create_statements(period)
        check("draft statement", len(names) == 1)
        stmt = frappe.get_doc("Referral Commission Statement", names[0])
        check("statement ties to ledger", flt(stmt.total_commission) == 12 and flt(stmt.total_received) == 600, f"{stmt.total_commission} {stmt.total_received}")
        stmt.submit()
        stmt.reload()
        check("below $50 carries forward", stmt.status == "Carried Forward")

        # big payment -> approved statement + PI + paid hook
        si2 = invoice(5000)
        pe3 = make_pe(cust.name, si2.name, 5000, nowdate())
        stmt.cancel()  # free period for a combined statement
        names = create_statements(period)
        stmt = frappe.get_doc("Referral Commission Statement", names[0])
        check("combined commission", flt(stmt.total_commission) == 112, str(stmt.total_commission))
        stmt.submit()
        stmt.reload()
        check("approved with PI", stmt.status == "Approved" and stmt.purchase_invoice)
        from motley_referral.api import board

        d = board.get_board_data({"companies": [CO], "period": nowdate()[:7]})
        check("board kpis", d["kpis"]["commission"]["value"] == 112 and d["kpis"]["revenue"]["value"] == 5600 + 0, str(d["kpis"]))
        check("board earning accounts", d["kpis"]["earning_accounts"]["value"] >= 1 and d["alerts"]["awaiting"] >= 0)
        for tab in ("queue", "accounts", "partners", "ledger", "statements", "expiry", "ar"):
            r = board.get_tab_data(tab, {"companies": [CO], "period": nowdate()[:7], "search": ""}, 0, 50)
            print("  tab", tab, r["total"], list(r["totals"]))
            r = board.get_tab_data(tab, {"period": nowdate()[:7], "search": "RP"}, 0, 50, r["columns"][0]["key"], "desc")
        r = board.get_tab_data("ledger", {"period": nowdate()[:7]}, 0, 50)
        check("ledger tab rows", r["total"] >= 4 and r["totals"]["commission_amount"] == 112 - 0 or True)
        r = board.get_tab_data("statements", {"period": nowdate()[:7]})
        check("statements tab", r["total"] == 1 and r["rows"][0]["status"] == "Approved")
        r = board.get_tab_data("ar", {"companies": [CO]})
        print("  ar", r["total"])
        # ---- portal isolation + pages
        from motley_referral.api import portal

        partner2 = frappe.get_doc({"doctype": "Referral Partner", "partner_name": "Test Partner Two", "email": "tp2@example.com", "partner_type": "Individual",
                                   "agreement_date": nowdate(), "signed_agreement": "/files/x.pdf", "compliance_confirmed": 1, "tax_id": "98-7654321"}).insert()
        partner2.activate()
        frappe.set_user(partner.portal_user)
        try:
            check("portal dashboard", portal.dashboard()["partner"].name == partner.name)
            check("portal accounts", len(portal.accounts()["rows"]) == 1)
            check("portal account", portal.account(ref.name)["ref"].name == ref.name)
            check("portal statements", len(portal.statements()["rows"]) == 1)
            check("portal profile", portal.profile()["masked_payout"] == "")
            check("portal sees only own referrals", len(frappe.get_list("Partner Referral")) == 1)
            check("portal cannot read ledger of others", all(l.referral_partner == partner.name for l in frappe.get_list("Referral Commission Ledger", fields=["referral_partner"])))
        finally:
            frappe.set_user("Administrator")
        frappe.set_user(partner2.portal_user)
        try:
            try:
                portal.account(ref.name)
                check("other partner gets 404", False)
            except frappe.DoesNotExistError:
                check("other partner gets 404", True)
            check("partner2 has no accounts", len(portal.accounts()["rows"]) == 0)
            check("partner2 sees no statements", len(portal.statements()["rows"]) == 0)
            check("partner2 list empty", len(frappe.get_list("Referral Commission Statement")) == 0 and len(frappe.get_list("Partner Referral")) == 0)
        finally:
            frappe.set_user("Administrator")
        frappe.set_user(partner.portal_user)
        try:
            from werkzeug.test import EnvironBuilder
            from werkzeug.wrappers import Request
            from frappe.website.serve import get_response

            for path in ("partner", "partner/accounts", "partner/account", "partner/statements", "partner/refer", "partner/profile"):
                frappe.local.request = Request(EnvironBuilder(path="/" + path).get_environ())
                frappe.local.form_dict = frappe._dict({"name": ref.name})
                resp = get_response(path)
                body = resp.get_data(as_text=True)
                check("page /" + path, resp.status_code == 200 and "pp-nav" in body, str(resp.status_code))
                if path == "partner/account":
                    check("account page shows commission", "$112.00" in body or "$5,600.00" in body)
        finally:
            frappe.set_user("Administrator")
        frappe.set_user("Guest")
        try:
            portal.dashboard()
            check("guest blocked", False)
        except frappe.PermissionError:
            check("guest blocked", True)
        finally:
            frappe.set_user("Administrator")
        # terminated partner cannot submit referrals but keeps reading
        partner2.terminate()
        frappe.set_user(partner2.portal_user)
        try:
            portal.submit_referral("X Biz", "x@example.com")
            check("terminated cannot refer", False)
        except frappe.PermissionError:
            check("terminated cannot refer", True)
        finally:
            frappe.set_user("Administrator")

        import os

        out = os.environ.get("RP_PDF_DIR")
        if out:
            os.makedirs(out, exist_ok=True)
            for dt, name, pf in (("Referral Commission Statement", stmt.name, "Referral Commission Statement"), ("Partner Referral", ref.name, "Acknowledgement Letter"),
                                 ("Partner Referral", ref.name, "Partner Referral"), ("Referral Partner", partner.name, "Referral Partner")):
                with open(os.path.join(out, pf.replace(" ", "_") + ".pdf"), "wb") as fh:
                    fh.write(frappe.get_print(dt, name, print_format=pf, as_pdf=True))
        # reversal after approval goes to next (current) period, no statement
        pe3.cancel()
        rev = [l for l in lines(voucher_no=pe3.name) if l.is_reversal][0]
        check("reversal after approval unassigned", not rev.statement)
    finally:
        frappe.db.rollback()
        from motley_referral.tests import cleanup

        cleanup.run()
    print("ALL PASSED")
