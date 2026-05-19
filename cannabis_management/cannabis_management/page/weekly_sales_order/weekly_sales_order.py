import frappe
from frappe.utils import getdate, add_days, flt, now_datetime, nowdate

NIKKI_EMAIL = "nikki@motleyterpz.com"
MATT_EMAIL  = "matt@motleyterpz.com"
IMRAN_EMAIL = "imran@motleyterpz.com"


def get_context(context):
	pass


# ─────────────────────────────────────────────────────────────
#  MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard_data(from_date, to_date):
	from_date = getdate(from_date)
	to_date   = getdate(to_date)

	return {
		"week_at_a_glance":   get_week_at_a_glance(from_date, to_date),
		"customer_breakdown": get_customer_breakdown(from_date, to_date),
		"gap_report":         get_gap_report(),
		"collections_detail": get_collections_detail(from_date, to_date),
		"trajectory":         get_weekly_trajectory(from_date, to_date),
		"orders_table":       get_orders_table(from_date, to_date),
		"acknowledgment":     get_acknowledgment_status(str(from_date)),
	}


# ─────────────────────────────────────────────────────────────
#  SECTION 1 — WEEK AT A GLANCE
# ─────────────────────────────────────────────────────────────

def get_week_at_a_glance(from_date, to_date):
	so = frappe.db.sql("""
		SELECT COUNT(*) as cnt, COALESCE(SUM(IFNULL(rounded_total, grand_total)), 0) as val
		FROM `tabSales Order`
		WHERE docstatus=1 AND transaction_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)[0]

	si = frappe.db.sql("""
		SELECT COUNT(*) as cnt, COALESCE(SUM(grand_total), 0) as val
		FROM `tabSales Invoice`
		WHERE docstatus=1 AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)[0]

	dn = frappe.db.sql("""
		SELECT COUNT(*) as cnt
		FROM `tabDelivery Note`
		WHERE docstatus=1 AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)[0]

	collected = frappe.db.sql("""
		SELECT COALESCE(SUM(paid_amount), 0) as val
		FROM `tabPayment Entry`
		WHERE docstatus=1 AND payment_type='Receive'
		AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)[0]

	ar = frappe.db.sql("""
		SELECT COALESCE(SUM(outstanding_amount), 0) as val
		FROM `tabSales Invoice`
		WHERE docstatus=1 AND outstanding_amount > 0
	""", as_dict=True)[0]

	return {
		"so_count":       int(so.cnt),
		"so_value":       flt(so.val),
		"invoice_count":  int(si.cnt),
		"invoice_value":  flt(si.val),
		"dn_count":       int(dn.cnt),
		"collected":      flt(collected.val),
		"outstanding_ar": flt(ar.val),
	}


# ─────────────────────────────────────────────────────────────
#  SECTION 3 — CUSTOMER BREAKDOWN
# ─────────────────────────────────────────────────────────────

def get_customer_breakdown(from_date, to_date):
	# customers with any activity in the period
	active = frappe.db.sql("""
		SELECT DISTINCT customer FROM `tabSales Order`
		WHERE docstatus=1 AND transaction_date BETWEEN %s AND %s
		UNION
		SELECT DISTINCT customer FROM `tabSales Invoice`
		WHERE docstatus=1 AND posting_date BETWEEN %s AND %s
		UNION
		SELECT DISTINCT party as customer FROM `tabPayment Entry`
		WHERE docstatus=1 AND payment_type='Receive' AND party_type='Customer'
		AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date, from_date, to_date, from_date, to_date), as_dict=True)

	if not active:
		return []

	customers = [r.customer for r in active]
	placeholders = ", ".join(["%s"] * len(customers))

	orders = frappe.db.sql(f"""
		SELECT customer,
			COUNT(*) as order_count,
			COALESCE(SUM(IFNULL(rounded_total, grand_total)), 0) as order_value
		FROM `tabSales Order`
		WHERE docstatus=1 AND transaction_date BETWEEN %s AND %s
		AND customer IN ({placeholders})
		GROUP BY customer
	""", [from_date, to_date] + customers, as_dict=True)

	invoices = frappe.db.sql(f"""
		SELECT customer,
			COUNT(*) as inv_count,
			COALESCE(SUM(grand_total), 0) as inv_value
		FROM `tabSales Invoice`
		WHERE docstatus=1 AND posting_date BETWEEN %s AND %s
		AND customer IN ({placeholders})
		GROUP BY customer
	""", [from_date, to_date] + customers, as_dict=True)

	payments = frappe.db.sql(f"""
		SELECT party as customer,
			COALESCE(SUM(paid_amount), 0) as collected,
			MAX(posting_date) as last_payment_date
		FROM `tabPayment Entry`
		WHERE docstatus=1 AND payment_type='Receive' AND party_type='Customer'
		AND posting_date BETWEEN %s AND %s
		AND party IN ({placeholders})
		GROUP BY party
	""", [from_date, to_date] + customers, as_dict=True)

	outstanding = frappe.db.sql(f"""
		SELECT customer,
			COALESCE(SUM(outstanding_amount), 0) as outstanding,
			MAX(DATEDIFF(CURDATE(), posting_date)) as max_age
		FROM `tabSales Invoice`
		WHERE docstatus=1 AND outstanding_amount > 0
		AND customer IN ({placeholders})
		GROUP BY customer
	""", customers, as_dict=True)

	# index by customer
	ord_map  = {r.customer: r for r in orders}
	inv_map  = {r.customer: r for r in invoices}
	pay_map  = {r.customer: r for r in payments}
	out_map  = {r.customer: r for r in outstanding}

	rows = []
	for c in customers:
		o   = ord_map.get(c,  frappe._dict(order_count=0, order_value=0))
		i   = inv_map.get(c,  frappe._dict(inv_count=0, inv_value=0))
		p   = pay_map.get(c,  frappe._dict(collected=0, last_payment_date=None))
		out = out_map.get(c,  frappe._dict(outstanding=0, max_age=0))

		age = int(out.max_age or 0)
		if age > 90:
			ar_status = "90d+"
		elif age > 60:
			ar_status = "60d+"
		elif age > 30:
			ar_status = "30d+"
		else:
			ar_status = "OK"

		rows.append({
			"customer":          c,
			"order_count":       int(o.order_count),
			"order_value":       flt(o.order_value),
			"inv_count":         int(i.inv_count),
			"inv_value":         flt(i.inv_value),
			"collected":         flt(p.collected),
			"outstanding":       flt(out.outstanding),
			"last_payment_date": str(p.last_payment_date) if p.last_payment_date else None,
			"ar_status":         ar_status,
		})

	rows.sort(key=lambda r: r["order_value"], reverse=True)
	return rows


# ─────────────────────────────────────────────────────────────
#  SECTION 4 — GAP REPORT
# ─────────────────────────────────────────────────────────────

def get_gap_report():
	# Gap 1: SOs > 7 days old with no invoice
	gap1 = frappe.db.sql("""
		SELECT so.name, so.customer, so.transaction_date,
			IFNULL(so.rounded_total, so.grand_total) as grand_total,
			DATEDIFF(CURDATE(), so.transaction_date) as days_open
		FROM `tabSales Order` so
		WHERE so.docstatus=1
		AND so.transaction_date <= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
		AND NOT EXISTS (
			SELECT 1 FROM `tabSales Invoice Item` sii
			WHERE sii.sales_order=so.name AND sii.docstatus=1
		)
		ORDER BY days_open DESC
		LIMIT 100
	""", as_dict=True)

	# Gap 2: Delivery Notes with no invoice
	gap2 = frappe.db.sql("""
		SELECT dn.name, dn.customer, dn.posting_date,
			DATEDIFF(CURDATE(), dn.posting_date) as days_open
		FROM `tabDelivery Note` dn
		WHERE dn.docstatus=1
		AND NOT EXISTS (
			SELECT 1 FROM `tabSales Invoice Item` sii
			WHERE sii.delivery_note=dn.name AND sii.docstatus=1
		)
		ORDER BY days_open DESC
		LIMIT 100
	""", as_dict=True)

	# Gap 3: Invoices with no delivery note (but linked to a SO)
	gap3 = frappe.db.sql("""
		SELECT si.name, si.customer, si.posting_date, si.grand_total
		FROM `tabSales Invoice` si
		WHERE si.docstatus=1
		AND EXISTS (
			SELECT 1 FROM `tabSales Invoice Item` sii
			WHERE sii.parent=si.name AND IFNULL(sii.sales_order,'') != ''
		)
		AND NOT EXISTS (
			SELECT 1 FROM `tabSales Invoice Item` sii
			WHERE sii.parent=si.name AND IFNULL(sii.delivery_note,'') != ''
		)
		ORDER BY si.posting_date DESC
		LIMIT 100
	""", as_dict=True)

	# Gap 4: Aging AR > 30 days
	gap4 = frappe.db.sql("""
		SELECT name, customer, posting_date, grand_total, outstanding_amount,
			DATEDIFF(CURDATE(), posting_date) as age_days
		FROM `tabSales Invoice`
		WHERE docstatus=1 AND outstanding_amount > 0
		AND DATEDIFF(CURDATE(), posting_date) > 30
		ORDER BY age_days DESC
		LIMIT 200
	""", as_dict=True)

	def to_list(rows):
		result = []
		for r in rows:
			d = dict(r)
			for k, v in d.items():
				if hasattr(v, 'isoformat'):
					d[k] = str(v)
			result.append(d)
		return result

	return {
		"orders_no_invoice":    to_list(gap1),
		"dns_no_invoice":       to_list(gap2),
		"invoices_no_dn":       to_list(gap3),
		"aging_ar":             to_list(gap4),
	}


# ─────────────────────────────────────────────────────────────
#  SECTION 5 — COLLECTIONS DETAIL
# ─────────────────────────────────────────────────────────────

def get_collections_detail(from_date, to_date):
	# Get cash mode names
	cash_modes_raw = frappe.db.sql("""
		SELECT name FROM `tabMode of Payment` WHERE type='Cash'
	""", as_dict=True)
	cash_modes = [r.name for r in cash_modes_raw] or ["Cash", "Petty Cash Niki"]

	# All received payments in range
	payments = frappe.db.sql("""
		SELECT pe.name, pe.party as customer, pe.paid_amount,
			pe.mode_of_payment, pe.paid_to, pe.posting_date,
			pe.unallocated_amount, pe.company,
			mop.type as payment_type_cat
		FROM `tabPayment Entry` pe
		LEFT JOIN `tabMode of Payment` mop ON mop.name=pe.mode_of_payment
		WHERE pe.docstatus=1 AND pe.payment_type='Receive'
		AND pe.posting_date BETWEEN %s AND %s
		ORDER BY pe.posting_date DESC
	""", (from_date, to_date), as_dict=True)

	# Payment-to-invoice links for this week's payments
	pe_names = [p.name for p in payments]
	inv_refs = {}
	if pe_names:
		placeholders = ", ".join(["%s"] * len(pe_names))
		refs = frappe.db.sql(f"""
			SELECT reference_name as pe, reference_doctype, reference_name as ref_doc,
				per.parent as payment
			FROM `tabPayment Entry Reference` per
			WHERE per.parent IN ({placeholders}) AND per.docstatus=1
		""", pe_names, as_dict=True)
		for r in refs:
			inv_refs.setdefault(r.payment, []).append(r.ref_doc)

	cash_list = []
	bank_list = []
	for p in payments:
		row = {
			"name":            p.name,
			"customer":        p.customer,
			"amount":          flt(p.paid_amount),
			"mode":            p.mode_of_payment or "—",
			"account":         p.paid_to or "—",
			"date":            str(p.posting_date),
			"company":         p.company,
			"invoices":        inv_refs.get(p.name, []),
		}
		if p.payment_type_cat == "Cash" or p.mode_of_payment in cash_modes:
			cash_list.append(row)
		else:
			bank_list.append(row)

	# Unallocated payments (all time)
	unallocated = frappe.db.sql("""
		SELECT name, party as customer, paid_amount, unallocated_amount,
			posting_date, mode_of_payment
		FROM `tabPayment Entry`
		WHERE docstatus=1 AND payment_type='Receive'
		AND unallocated_amount > 0
		ORDER BY posting_date ASC
	""", as_dict=True)

	# Form 8300 pending/overdue flags
	flags_8300 = frappe.db.sql("""
		SELECT name, customer, cash_amount, transaction_date,
			filing_status, filing_deadline, payment_entry
		FROM `tabIRS Form 8300 Log`
		WHERE filing_status IN ('Pending', 'Overdue')
		ORDER BY filing_deadline ASC
	""", as_dict=True)

	def clean(rows):
		result = []
		for r in rows:
			d = dict(r)
			for k, v in d.items():
				if hasattr(v, 'isoformat'):
					d[k] = str(v)
			result.append(d)
		return result

	return {
		"cash":        cash_list,
		"bank":        bank_list,
		"unallocated": clean(unallocated),
		"flags_8300":  clean(flags_8300),
		"cash_total":  sum(r["amount"] for r in cash_list),
		"bank_total":  sum(r["amount"] for r in bank_list),
	}


# ─────────────────────────────────────────────────────────────
#  SECTION 6 — WEEKLY TRAJECTORY (last 4 weeks)
# ─────────────────────────────────────────────────────────────

def get_weekly_trajectory(from_date, to_date):
	# Build 4 week buckets ending on to_date
	weeks = []
	bucket_end = to_date
	for i in range(4):
		bucket_start = add_days(bucket_end, -6)
		weeks.insert(0, (bucket_start, bucket_end))
		bucket_end = add_days(bucket_start, -1)

	result = []
	for w_start, w_end in weeks:
		so_row = frappe.db.sql("""
			SELECT COALESCE(SUM(IFNULL(rounded_total, grand_total)), 0) as val
			FROM `tabSales Order`
			WHERE docstatus=1 AND transaction_date BETWEEN %s AND %s
		""", (w_start, w_end), as_dict=True)[0]

		si_row = frappe.db.sql("""
			SELECT COALESCE(SUM(grand_total), 0) as val
			FROM `tabSales Invoice`
			WHERE docstatus=1 AND posting_date BETWEEN %s AND %s
		""", (w_start, w_end), as_dict=True)[0]

		pe_row = frappe.db.sql("""
			SELECT COALESCE(SUM(paid_amount), 0) as val
			FROM `tabPayment Entry`
			WHERE docstatus=1 AND payment_type='Receive'
			AND posting_date BETWEEN %s AND %s
		""", (w_start, w_end), as_dict=True)[0]

		result.append({
			"week_start":    str(w_start),
			"week_end":      str(w_end),
			"so_value":      flt(so_row.val),
			"invoice_value": flt(si_row.val),
			"collected":     flt(pe_row.val),
		})

	return result


# ─────────────────────────────────────────────────────────────
#  ORDERS TABLE (existing detail table)
# ─────────────────────────────────────────────────────────────

def get_orders_table(from_date, to_date):
	orders = frappe.get_all(
		"Sales Order",
		filters={"transaction_date": ["between", [from_date, to_date]], "docstatus": 1},
		fields=["name", "transaction_date", "customer", "grand_total", "rounded_total"],
		order_by="transaction_date desc, name desc",
		limit_page_length=0
	)
	if not orders:
		return []

	so_names = [o.name for o in orders]

	# Sales persons
	sales_persons = {}
	for st in frappe.get_all("Sales Team",
		filters={"parent": ["in", so_names], "parenttype": "Sales Order"},
		fields=["parent", "sales_person"]):
		sales_persons.setdefault(st.parent, []).append(st.sales_person)

	# Delivery Notes
	delivery_notes = {}
	for item in frappe.get_all("Delivery Note Item",
		filters={"against_sales_order": ["in", so_names], "docstatus": 1},
		fields=["against_sales_order", "parent"], limit_page_length=0):
		dn_list = delivery_notes.setdefault(item.against_sales_order, [])
		if item.parent not in dn_list:
			dn_list.append(item.parent)

	# Invoices
	invoices = {}
	for item in frappe.get_all("Sales Invoice Item",
		filters={"sales_order": ["in", so_names], "docstatus": 1},
		fields=["sales_order", "parent"], limit_page_length=0):
		inv_list = invoices.setdefault(item.sales_order, [])
		if item.parent not in inv_list:
			inv_list.append(item.parent)

	# Payments against SOs
	payments = {}
	for ref in frappe.get_all("Payment Entry Reference",
		filters={"reference_doctype": "Sales Order", "reference_name": ["in", so_names], "docstatus": 1},
		fields=["reference_name", "parent", "allocated_amount"], limit_page_length=0):
		payments.setdefault(ref.reference_name, []).append({
			"name": ref.parent, "amount": flt(ref.allocated_amount)
		})

	# Payments against linked SIs
	all_invoices = []
	inv_to_so = {}
	for so, inv_list in invoices.items():
		for inv in inv_list:
			if inv not in all_invoices:
				all_invoices.append(inv)
			inv_to_so[inv] = so
	if all_invoices:
		for ref in frappe.get_all("Payment Entry Reference",
			filters={"reference_doctype": "Sales Invoice", "reference_name": ["in", all_invoices], "docstatus": 1},
			fields=["reference_name", "parent", "allocated_amount"], limit_page_length=0):
			so_name = inv_to_so.get(ref.reference_name)
			if so_name:
				pe_list = payments.setdefault(so_name, [])
				if ref.parent not in [p["name"] for p in pe_list]:
					pe_list.append({"name": ref.parent, "amount": flt(ref.allocated_amount)})

	# Payment accounts
	all_pe_names = {pe["name"] for pe_list in payments.values() for pe in pe_list}
	pe_accounts = {}
	if all_pe_names:
		for pe in frappe.get_all("Payment Entry",
			filters={"name": ["in", list(all_pe_names)]},
			fields=["name", "paid_to", "mode_of_payment"], limit_page_length=0):
			label = pe.paid_to or ""
			if pe.mode_of_payment:
				label = f"{label} - {pe.mode_of_payment}" if label else pe.mode_of_payment
			pe_accounts[pe.name] = label

	rows = []
	for o in orders:
		so_name = o.name
		pe_list = payments.get(so_name, [])
		for pe in pe_list:
			pe["account"] = pe_accounts.get(pe["name"], "")
		rows.append({
			"name":             so_name,
			"transaction_date": str(o.transaction_date),
			"customer":         o.customer,
			"grand_total":      flt(o.rounded_total or o.grand_total),
			"sales_person":     ", ".join(sales_persons.get(so_name, [])) or "",
			"delivery_notes":   delivery_notes.get(so_name, []),
			"invoices":         invoices.get(so_name, []),
			"payment_entries":  pe_list,
		})
	return rows


# ─────────────────────────────────────────────────────────────
#  SIGN-OFF FUNCTIONS
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_acknowledgment_status(week_start):
	name = f"WSR-{week_start}"

	if not frappe.db.exists("Weekly Sales Report", name):
		week_start_date = getdate(week_start)
		week_end_date   = add_days(week_start_date, 6)
		today           = getdate(nowdate())
		# Auto-create WSR for completed past weeks (don't create for current/future weeks)
		if week_end_date < today:
			_auto_create_wsr(week_start_date, week_end_date, name)
		else:
			return {"exists": False, "can_acknowledge": False}

	doc = frappe.get_doc("Weekly Sales Report", name)
	return {
		"exists":           True,
		"is_acknowledged":  bool(doc.is_acknowledged),
		"acknowledged_by":  doc.acknowledged_by or "",
		"acknowledged_at":  str(doc.acknowledged_at) if doc.acknowledged_at else "",
		"can_acknowledge":  frappe.session.user == NIKKI_EMAIL and not bool(doc.is_acknowledged),
	}


def _auto_create_wsr(week_start, week_end, name):
	"""Create a Weekly Sales Report snapshot for a past week that was not yet created."""
	kpis = get_week_at_a_glance(week_start, week_end)
	doc = frappe.get_doc({
		"doctype":           "Weekly Sales Report",
		"week_start":        str(week_start),
		"week_end":          str(week_end),
		"generated_at":      now_datetime(),
		"total_orders":      kpis["so_count"],
		"total_order_value": kpis["so_value"],
		"total_invoiced":    kpis["invoice_value"],
		"total_collected":   kpis["collected"],
		"total_outstanding": kpis["outstanding_ar"],
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()


@frappe.whitelist()
def acknowledge_weekly_report(week_start, notes=""):
	name = f"WSR-{week_start}"
	if not frappe.db.exists("Weekly Sales Report", name):
		frappe.throw(f"No weekly report found for {week_start}")

	doc = frappe.get_doc("Weekly Sales Report", name)
	if doc.is_acknowledged:
		return {"status": "already_acknowledged", "acknowledged_by": doc.acknowledged_by}

	doc.is_acknowledged    = 1
	doc.acknowledged_by    = frappe.session.user
	doc.acknowledged_at    = now_datetime()
	doc.acknowledgment_notes = notes
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	# Notify Matt and Imran
	_send_acknowledgment_notification(doc)

	return {
		"status":          "acknowledged",
		"acknowledged_by": doc.acknowledged_by,
		"acknowledged_at": str(doc.acknowledged_at),
	}


def _send_acknowledgment_notification(doc):
	recipients = [MATT_EMAIL, IMRAN_EMAIL]
	subject = f"Weekly Sales Report Acknowledged — {doc.week_start} to {doc.week_end}"
	message = f"""
		<p>The weekly sales report for <strong>{doc.week_start} to {doc.week_end}</strong>
		has been acknowledged by <strong>{doc.acknowledged_by}</strong>
		at {doc.acknowledged_at}.</p>
		{"<p><em>Notes: " + doc.acknowledgment_notes + "</em></p>" if doc.acknowledgment_notes else ""}
		<p><a href="/app/weekly-sales-report/{doc.name}">View Report</a></p>
	"""
	try:
		frappe.sendmail(recipients=recipients, subject=subject, message=message)
	except Exception:
		pass


# ─────────────────────────────────────────────────────────────
#  PDF EXPORT DATA  (separate endpoint — page display unchanged)
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_pdf_export_data(from_date, to_date):
	from_date = getdate(from_date)
	to_date   = getdate(to_date)
	return {
		"kpis":           _pdf_kpis(from_date, to_date),
		"orders_table":   get_orders_table(from_date, to_date),
		"payments_table": _pdf_payments(from_date, to_date),
		"delivery_notes": _pdf_delivery_notes(from_date, to_date),
	}


def _pdf_kpis(from_date, to_date):
	so = frappe.db.sql("""
		SELECT COUNT(*) as cnt,
		       COALESCE(SUM(IFNULL(rounded_total, grand_total)), 0) as val
		FROM `tabSales Order`
		WHERE docstatus=1 AND transaction_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)[0]

	dn = frappe.db.sql("""
		SELECT COUNT(*) as cnt FROM `tabDelivery Note`
		WHERE docstatus=1 AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)[0]

	si = frappe.db.sql("""
		SELECT COUNT(*) as cnt FROM `tabSales Invoice`
		WHERE docstatus=1 AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)[0]

	pe = frappe.db.sql("""
		SELECT COUNT(*) as cnt, COALESCE(SUM(paid_amount), 0) as val
		FROM `tabPayment Entry`
		WHERE docstatus=1 AND payment_type='Receive'
		AND posting_date BETWEEN %s AND %s
	""", (from_date, to_date), as_dict=True)[0]

	prev = frappe.db.sql("""
		SELECT COALESCE(SUM(per.allocated_amount), 0) as val
		FROM `tabPayment Entry Reference` per
		JOIN `tabPayment Entry` pe ON pe.name = per.parent
		JOIN `tabSales Invoice` si ON si.name = per.reference_name
		WHERE pe.docstatus=1 AND pe.payment_type='Receive'
		  AND pe.posting_date BETWEEN %s AND %s
		  AND per.reference_doctype = 'Sales Invoice'
		  AND si.posting_date < %s
	""", (from_date, to_date, from_date), as_dict=True)[0]

	ar = frappe.db.sql("""
		SELECT COALESCE(SUM(outstanding_amount), 0) as val
		FROM `tabSales Invoice`
		WHERE docstatus=1 AND outstanding_amount > 0
	""", as_dict=True)[0]

	return {
		"so_count":              int(so.cnt),
		"dn_count":              int(dn.cnt),
		"invoice_count":         int(si.cnt),
		"payment_count":         int(pe.cnt),
		"so_value":              flt(so.val),
		"collected":             flt(pe.val),
		"collected_prev_period": flt(prev.val),
		"outstanding_ar":        flt(ar.val),
	}


def _pdf_payments(from_date, to_date):
	payments = frappe.db.sql("""
		SELECT pe.name, pe.party as customer, pe.paid_amount,
		       pe.mode_of_payment, pe.paid_to, pe.posting_date
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus=1 AND pe.payment_type='Receive'
		  AND pe.posting_date BETWEEN %s AND %s
		ORDER BY pe.posting_date DESC, pe.name
	""", (from_date, to_date), as_dict=True)

	if not payments:
		return []

	pe_names = [p.name for p in payments]
	placeholders = ", ".join(["%s"] * len(pe_names))

	refs = frappe.db.sql(f"""
		SELECT per.parent as pname, per.reference_doctype,
		       per.reference_name, per.allocated_amount,
		       CASE WHEN per.reference_doctype='Sales Invoice'
		            THEN si.grand_total ELSE NULL END as inv_total,
		       CASE WHEN per.reference_doctype='Sales Invoice'
		            THEN si.posting_date ELSE NULL END as inv_date
		FROM `tabPayment Entry Reference` per
		LEFT JOIN `tabSales Invoice` si
		    ON si.name=per.reference_name AND per.reference_doctype='Sales Invoice'
		WHERE per.parent IN ({placeholders}) AND per.docstatus=1
	""", pe_names, as_dict=True)

	si_names = [r.reference_name for r in refs if r.reference_doctype == 'Sales Invoice']
	si_to_so = {}
	if si_names:
		si_pl = ", ".join(["%s"] * len(si_names))
		for r in frappe.db.sql(f"""
			SELECT DISTINCT sii.parent as si_name, sii.sales_order
			FROM `tabSales Invoice Item` sii
			WHERE sii.parent IN ({si_pl})
			  AND IFNULL(sii.sales_order,'') != '' AND sii.docstatus=1
		""", si_names, as_dict=True):
			si_to_so[r.si_name] = r.sales_order

	ref_map = {}
	for r in refs:
		ref_map.setdefault(r.pname, []).append(r)

	rows = []
	for p in payments:
		si_refs = [r for r in ref_map.get(p.name, []) if r.reference_doctype == 'Sales Invoice']
		if si_refs:
			for sr in si_refs:
				inv_date = getdate(sr.inv_date) if sr.inv_date else None
				is_prev  = bool(inv_date and inv_date < from_date)
				rows.append({
					"name":      p.name,
					"customer":  p.customer,
					"invoice":   sr.reference_name,
					"linked_so": si_to_so.get(sr.reference_name, ""),
					"inv_total": flt(sr.inv_total or 0),
					"paid":      flt(sr.allocated_amount or 0),
					"account":   p.paid_to or "",
					"date":      str(p.posting_date),
					"reason":    "Invoice from previous period" if is_prev else "",
				})
		else:
			rows.append({
				"name":      p.name,
				"customer":  p.customer,
				"invoice":   "",
				"linked_so": "",
				"inv_total": 0,
				"paid":      flt(p.paid_amount),
				"account":   p.paid_to or "",
				"date":      str(p.posting_date),
				"reason":    "",
			})
	return rows


def _pdf_delivery_notes(from_date, to_date):
	dns = frappe.get_all("Delivery Note",
		filters={"docstatus": 1, "posting_date": ["between", [from_date, to_date]]},
		fields=["name", "customer", "posting_date", "company"],
		order_by="posting_date asc, name asc",
		limit_page_length=0
	)
	if not dns:
		return []

	dn_names = [d.name for d in dns]
	placeholders = ", ".join(["%s"] * len(dn_names))

	dn_so = {}
	for r in frappe.db.sql(f"""
		SELECT DISTINCT dni.parent as dn_name, dni.against_sales_order
		FROM `tabDelivery Note Item` dni
		WHERE dni.parent IN ({placeholders})
		  AND IFNULL(dni.against_sales_order,'') != '' AND dni.docstatus=1
	""", dn_names, as_dict=True):
		sos = dn_so.setdefault(r.dn_name, [])
		if r.against_sales_order not in sos:
			sos.append(r.against_sales_order)

	return [{
		"name":         d.name,
		"customer":     d.customer,
		"posting_date": str(d.posting_date),
		"company":      d.company,
		"linked_sos":   dn_so.get(d.name, []),
	} for d in dns]
