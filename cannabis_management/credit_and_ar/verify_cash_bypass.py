"""Verification for the Cash (Mode of Payment = Cash On Delivery) policy bypass.

    bench --site <site> execute cannabis_management.credit_and_ar.verify_cash_bypass.run

Two halves:

* **Hold exemption matrix** — pure calls into ``hold_engine._is_exempt`` with stub
  documents, covering the Sales Order and Delivery Note combinations.
* **End-to-end** — a real Sales Order for a customer on a Hard Hold, created,
  submitted and then cancelled and deleted again.

Everything it creates is removed in the ``finally`` block. Safe to re-run.
"""

import frappe
from frappe.utils import add_days, nowdate

from cannabis_management.credit_and_ar import hold_engine, utils

_results = []
_created = {"sales_orders": []}


def _check(label, condition, detail=""):
	_results.append((label, bool(condition), detail))
	print(f"{'PASS' if condition else 'FAIL'}  {label}{'  — ' + str(detail) if detail else ''}")


# ── stub documents for the exemption matrix ──────────────────────────────────


def _so_stub(mode, order_type=None):
	return frappe._dict(
		doctype="Sales Order",
		custom_mode_of_payment=mode,
		custom_sales_order_type=order_type,
	)


def _dn_stub(against):
	"""Delivery Note carrying item rows that point back at source Sales Orders."""
	return frappe._dict(
		doctype="Delivery Note",
		items=[frappe._dict(against_sales_order=name) for name in against],
	)


def _find_held_customer():
	rows = frappe.get_all(
		"Customer",
		filters={"custom_hold_type": "Hard Hold", "custom_credit_policy_exempt": 0},
		fields=["name"],
		limit=1,
	)
	return rows[0].name if rows else None


def _sample_item():
	row = frappe.db.sql(
		"""select soi.item_code, soi.warehouse, soi.uom, so.company, so.currency
		   from `tabSales Order Item` soi join `tabSales Order` so on so.name = soi.parent
		   order by so.creation desc limit 1""",
		as_dict=True,
	)
	return row[0] if row else None


def _make_order(customer, mode, item, terms_template=None):
	doc = frappe.new_doc("Sales Order")
	doc.customer = customer
	doc.company = item.company
	doc.currency = item.currency
	doc.transaction_date = nowdate()
	doc.delivery_date = add_days(nowdate(), 7)
	doc.custom_mode_of_payment = mode
	if terms_template:
		doc.payment_terms_template = terms_template
	doc.append(
		"items",
		{
			"item_code": item.item_code,
			"qty": 1,
			"rate": 100,
			"uom": item.uom,
			"warehouse": item.warehouse,
			"delivery_date": add_days(nowdate(), 7),
		},
	)
	doc.insert(ignore_permissions=True)
	_created["sales_orders"].append(doc.name)
	return doc


def _cleanup():
	frappe.set_user("Administrator")
	for name in _created["sales_orders"]:
		if not frappe.db.exists("Sales Order", name):
			continue
		doc = frappe.get_doc("Sales Order", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Sales Order", name, force=1, ignore_permissions=True)
	frappe.db.commit()


def run():
	frappe.set_user("Administrator")

	try:
		# ── hold exemption matrix ────────────────────────────────────
		_check(
			"cash Sales Order is exempt from holds",
			hold_engine._is_exempt(_so_stub(utils.MODE_COD)),
		)
		_check(
			"terms Sales Order is NOT exempt",
			not hold_engine._is_exempt(_so_stub(utils.MODE_TERMS)),
		)
		_check(
			"sample Sales Order stays exempt",
			hold_engine._is_exempt(_so_stub(utils.MODE_TERMS, order_type="Samples")),
		)
		_check(
			"Sales Order with no mode set is treated as cash",
			hold_engine._is_exempt(_so_stub(None)),
		)

		# ── delivery notes ───────────────────────────────────────────
		_check(
			"Delivery Note with no source order is NOT exempt (fails closed)",
			not hold_engine._is_exempt(_dn_stub([])),
		)
		_check(
			"Delivery Note citing an unknown order is NOT exempt (fails closed)",
			not hold_engine._is_exempt(_dn_stub(["SAL-ORD-DOES-NOT-EXIST"])),
		)

		item = _sample_item()
		customer = _find_held_customer()
		if not item or not customer:
			_check("found a held customer and a usable item", False, "cannot run end-to-end")
			return

		_check("found a held customer and a usable item", True, f"{customer} / {item.item_code}")

		cash_so = _make_order(customer, utils.MODE_COD, item)
		terms_so = _make_order(customer, utils.MODE_TERMS, item)
		frappe.db.commit()

		_check(
			"Delivery Note from a cash order is exempt",
			hold_engine._is_exempt(_dn_stub([cash_so.name])),
		)
		_check(
			"Delivery Note from a terms order is NOT exempt",
			not hold_engine._is_exempt(_dn_stub([terms_so.name])),
		)
		_check(
			"mixed cash+terms Delivery Note is NOT exempt",
			not hold_engine._is_exempt(_dn_stub([cash_so.name, terms_so.name])),
		)

		# ── the cash order itself ────────────────────────────────────
		_check(
			"cash order needs no approval",
			cash_so.custom_approval_status == utils.APPROVAL_NOT_REQUIRED,
			cash_so.custom_approval_status,
		)
		_check("cash order is not print-blocked", not int(cash_so.custom_print_blocked or 0))
		_check("cash order carries no required deposit", not float(cash_so.custom_required_deposit or 0))
		_check(
			"cash order is NOT forced onto the COD template",
			not cash_so.payment_terms_template,
			repr(cash_so.payment_terms_template),
		)

		# A cash order that explicitly asks for a terms template keeps it — this is
		# the "default ERPNext behaviour" half of the change.
		net30 = "NET30" if frappe.db.exists("Payment Terms Template", "NET30") else None
		if net30:
			kept = _make_order(customer, utils.MODE_COD, item, terms_template=net30)
			frappe.db.commit()
			_check(
				"cash order keeps a payment terms template the user chose",
				kept.payment_terms_template == net30,
				repr(kept.payment_terms_template),
			)
			_check("…and its payment schedule survives", bool(kept.payment_schedule))

		# ── submit: cash goes through a Hard Hold, terms does not ────
		try:
			cash_so.submit()
			frappe.db.commit()
			_check("cash order SUBMITS despite the Hard Hold", cash_so.docstatus == 1)
		except Exception as exc:
			_check("cash order SUBMITS despite the Hard Hold", False, str(exc)[:160])

		try:
			terms_so.submit()
			frappe.db.commit()
			_check("terms order is still blocked", False, "it submitted")
		except Exception as exc:
			_check("terms order is still blocked", True, type(exc).__name__)

	finally:
		_cleanup()

	passed = sum(1 for _, ok, _ in _results if ok)
	total = len(_results)
	print(f"\n{'=' * 56}\n{passed}/{total} checks passed")
	failures = [label for label, ok, _ in _results if not ok]
	if failures:
		print("FAILED: " + "; ".join(failures))
	return {"passed": passed, "total": total, "failures": failures}
