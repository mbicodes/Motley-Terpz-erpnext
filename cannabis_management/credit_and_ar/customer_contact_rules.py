import re

import frappe
from frappe import _
from frappe.utils import validate_email_address

from cannabis_management.credit_and_ar import utils

MODE_TERMS = "Payment Terms"

EXEMPT_USERS = {"Administrator", "muhammad@motleyterpz.com"}


def _is_exempt(user=None):
	return (user or frappe.session.user) in EXEMPT_USERS


def _bulk_operation():
	f = frappe.flags
	return bool(f.in_import or f.in_patch or f.in_install or f.in_migrate)


def _norm_email(value):
	return (value or "").strip().lower()


def _norm_phone(value):
	digits = re.sub(r"\D", "", value or "")
	return digits[-10:] if len(digits) >= 10 else digits


def find_duplicate(email=None, phone=None, exclude_customer=None):
	email, phone = _norm_email(email), _norm_phone(phone)
	if not email and not phone:
		return None
	exclude = exclude_customer or ""

	if email:
		hit = frappe.db.sql(
			"""
			select name from `tabCustomer`
			where lower(trim(email_id)) = %(e)s and name != %(x)s
			union
			select dl.link_name from `tabContact Email` ce
			join `tabDynamic Link` dl on dl.parent = ce.parent and dl.parenttype = 'Contact'
			    and dl.link_doctype = 'Customer'
			where lower(trim(ce.email_id)) = %(e)s and dl.link_name != %(x)s
			limit 1
			""",
			{"e": email, "x": exclude},
		)
		if hit:
			return _("email address"), hit[0][0]

	if phone:
		rows = frappe.db.sql(
			"""
			select name, mobile_no from `tabCustomer`
			where ifnull(mobile_no, '') != '' and name != %(x)s
			union all
			select dl.link_name, cp.phone from `tabContact Phone` cp
			join `tabDynamic Link` dl on dl.parent = cp.parent and dl.parenttype = 'Contact'
			    and dl.link_doctype = 'Customer'
			where ifnull(cp.phone, '') != '' and dl.link_name != %(x)s
			""",
			{"x": exclude},
		)
		for customer, number in rows:
			if _norm_phone(number) == phone:
				return _("phone number"), customer

	return None


def _throw_duplicate(dup):
	label, customer = dup
	frappe.throw(
		_("This {0} is already used by customer {1}. Each customer needs its own.").format(
			label, frappe.bold(customer)
		),
		title=_("Duplicate contact details"),
	)


def validate_customer(doc):
	if not doc.is_new() or _bulk_operation() or _is_exempt():
		return

	email = (doc.get("email_id") or "").strip()
	phone = (doc.get("mobile_no") or "").strip()
	if email:
		validate_email_address(email, throw=True)
	dup = find_duplicate(email, phone, exclude_customer=doc.name)
	if dup:
		_throw_duplicate(dup)


def _customer_reachable(customer):
	email, mobile = frappe.db.get_value("Customer", customer, ["email_id", "mobile_no"]) or (None, None)
	if email or mobile:
		return True
	return bool(frappe.db.sql(
		"""
		select 1 from `tabContact` c
		join `tabDynamic Link` dl on dl.parent = c.name and dl.parenttype = 'Contact'
		    and dl.link_doctype = 'Customer' and dl.link_name = %s
		where ifnull(c.email_id, '') != '' or ifnull(c.mobile_no, '') != '' or ifnull(c.phone, '') != ''
		limit 1
		""",
		customer,
	))


def validate_sales_order(doc):
	if not doc.customer or _bulk_operation():
		return
	if (doc.get("custom_mode_of_payment") or "") != MODE_TERMS:
		return
	if utils.is_policy_exempt(doc.customer):
		return
	if doc.get("contact_email") or doc.get("contact_mobile") or doc.get("contact_phone"):
		return
	if _customer_reachable(doc.customer):
		return
	frappe.throw(
		_("Customer {0} has no email address or phone number. Add at least one before "
		  "saving this Sales Order: save again to be asked for them.").format(
			frappe.bold(doc.customer)
		),
		title=_("Customer contact required"),
	)


@frappe.whitelist()
def get_customer_contact(customer):
	frappe.has_permission("Customer", "read", doc=customer, throw=True)
	email, mobile, contact = frappe.db.get_value(
		"Customer", customer, ["email_id", "mobile_no", "customer_primary_contact"]
	) or (None, None, None)
	return {
		"email": email or "",
		"phone": mobile or "",
		"contact": contact or "",
		"reachable": bool(email or mobile) or _customer_reachable(customer),
		"exempt": utils.is_policy_exempt(customer),
	}


@frappe.whitelist()
def save_customer_contact(customer, email=None, phone=None):
	if not (frappe.has_permission("Sales Order", "create") or frappe.has_permission("Sales Order", "write")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	frappe.has_permission("Customer", "read", doc=customer, throw=True)

	email = (email or "").strip()
	phone = (phone or "").strip()
	if not email and not phone:
		frappe.throw(_("Enter an email address or a phone number."))
	if email:
		validate_email_address(email, throw=True)
	if not _is_exempt():
		dup = find_duplicate(email, phone, exclude_customer=customer)
		if dup:
			_throw_duplicate(dup)

	cust = frappe.get_doc("Customer", customer)
	if cust.customer_primary_contact:
		contact = frappe.get_doc("Contact", cust.customer_primary_contact)
	else:
		contact = frappe.get_doc({
			"doctype": "Contact",
			"first_name": cust.customer_name or customer,
			"is_primary_contact": 1,
			"links": [{"link_doctype": "Customer", "link_name": customer}],
		})

	if email:
		existing = next((r for r in contact.email_ids if _norm_email(r.email_id) == _norm_email(email)), None)
		for r in contact.email_ids:
			r.is_primary = 0
		if existing:
			existing.is_primary = 1
		else:
			contact.add_email(email, is_primary=True)
	if phone:
		existing = next((r for r in contact.phone_nos if _norm_phone(r.phone) == _norm_phone(phone)), None)
		for r in contact.phone_nos:
			r.is_primary_mobile_no = 0
		if existing:
			existing.is_primary_mobile_no = 1
		else:
			contact.add_phone(phone, is_primary_mobile_no=True)

	contact.flags.ignore_permissions = True
	contact.save()

	frappe.db.set_value("Customer", customer, {
		"customer_primary_contact": contact.name,
		"email_id": contact.email_id,
		"mobile_no": contact.mobile_no,
	})
	return {"contact": contact.name, "email": contact.email_id or "", "phone": contact.mobile_no or ""}
