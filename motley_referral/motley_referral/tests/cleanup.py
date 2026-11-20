"""Removes everything the Stage smoke test (tests/e2e.py) leaves behind, including accounting documents."""
import frappe

TEST_CUSTOMER = "RP Test Customer%"
TEST_SUPPLIER = "Test Partner%"


def _purge_vouchers(doctype, names):
    for n in names:
        frappe.db.sql("delete from `tabGL Entry` where voucher_type=%s and voucher_no=%s", (doctype, n))
        frappe.db.sql("delete from `tabPayment Ledger Entry` where voucher_type=%s and voucher_no=%s", (doctype, n))
        frappe.db.sql("delete from `tabPayment Ledger Entry` where against_voucher_type=%s and against_voucher_no=%s", (doctype, n))
        frappe.db.sql("delete from `tabSingles` where 0")
    return len(names)


def run():
    frappe.flags.in_test = True
    q = frappe.db.sql("select distinct parent from `tabEmail Queue Recipient` where recipient in ('tp@example.com','biz@example.com','tp2@example.com')", pluck=True)
    for n in q:
        frappe.db.sql("delete from `tabEmail Queue Recipient` where parent=%s", n)
        frappe.db.sql("delete from `tabEmail Queue` where name=%s", n)

    customers = frappe.get_all("Customer", filters={"customer_name": ["like", TEST_CUSTOMER]}, pluck="name")
    suppliers = frappe.get_all("Supplier", filters={"supplier_name": ["like", TEST_SUPPLIER]}, pluck="name")
    customers = list(set(customers) | set(frappe.db.sql("select distinct party from `tabGL Entry` where party like %s", TEST_CUSTOMER, pluck=True)))
    suppliers = list(set(suppliers) | set(frappe.db.sql("select distinct party from `tabGL Entry` where party like %s", TEST_SUPPLIER, pluck=True)))
    for dt, f in (("Referral Commission Ledger", {}), ("Referral Commission Statement", {})):
        for n in frappe.get_all(dt, pluck="name"):
            frappe.db.sql(f"delete from `tab{dt}` where name=%s", n)
    frappe.db.sql("delete from `tabReferral Commission Statement Line`")
    pe = frappe.get_all("Payment Entry", filters={"party": ["in", customers + suppliers or [""]]}, pluck="name")
    pi = frappe.get_all("Purchase Invoice", filters={"supplier": ["in", suppliers or [""]]}, pluck="name")
    si = frappe.get_all("Sales Invoice", filters={"customer": ["in", customers or [""]]}, pluck="name")
    for dt, names in (("Payment Entry", pe), ("Purchase Invoice", pi), ("Sales Invoice", si)):
        _purge_vouchers(dt, names)
        for n in names:
            for child in frappe.get_meta(dt).get_table_fields():
                frappe.db.sql(f"delete from `tab{child.options}` where parent=%s", n)
            frappe.db.sql("delete from `tabPayment Entry Reference` where reference_name=%s", n)
            frappe.db.sql(f"delete from `tab{dt}` where name=%s", n)
    for dt, filt in (("Partner Referral", {}), ("Referral Partner", {}),
                     ("Customer", {"name": ["in", customers or [""]]}), ("Supplier", {"name": ["in", suppliers or [""]]}),
                     ("User", {"name": ["in", ["tp@example.com", "tp2@example.com"]]}), ("File", {"attached_to_doctype": "Partner Referral"})):
        for n in frappe.get_all(dt, filters=filt, pluck="name"):
            try:
                frappe.delete_doc(dt, n, force=1, ignore_permissions=True)
            except Exception as e:
                print("could not delete", dt, n, e)
    frappe.db.commit()
    print("cleaned", len(q), "queue rows;", len(pe), "PE", len(si), "SI", len(pi), "PI")
