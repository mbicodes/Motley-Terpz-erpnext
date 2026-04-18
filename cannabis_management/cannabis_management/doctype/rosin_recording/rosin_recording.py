import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class RosinRecording(Document):
	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		self.total_quantity = sum(flt(row.pounds_sent) for row in self.lab_tolling_data)
		self.tolling_partner_charges = flt(self.total_quantity) * flt(self.rate_tolling_partner)
		
		for row in self.lab_tolling_data:
			if not row.expected_rosin_yield:
				row.expected_rosin_yield = self.expected_rosin_yield

			# Prefer row-level yield, fallback to parent-level
			exp_hash_yield = flt(row.expected_hash_yield or row.expected__yield__to_hash)
			exp_rosin_yield = flt(row.expected_rosin_yield or self.expected_rosin_yield)
			
			total_hash = flt(row.total_hash)
			total_rosin = flt(row.total_rosin)
			amount_ran_grams = flt(row.amount_ran_grams)

			# 1. Calculate Actual Yields
			actual_yield_to_hash = 0
			if amount_ran_grams > 0:
				actual_yield_to_hash = (total_hash / amount_ran_grams) * 100
			row.actual_yield_to_hash = flt(actual_yield_to_hash, 2)

			actual_rosin_yield = 0
			if total_hash > 0:
				actual_rosin_yield = (total_rosin / total_hash) * 100
			row.actual_rosin_yield = flt(actual_rosin_yield, 2)

			# 2. Formula for Raw Qty using Actuals
			# Fallback to pounds_ran as a safe starting point
			raw_qty = flt(row.pounds_ran)
			if actual_yield_to_hash > 0 and actual_rosin_yield > 0 and total_hash > 0:
				raw_qty = total_hash / (actual_yield_to_hash / 100) / 453.592 / (actual_rosin_yield / 100)
			
			# Ensure it's never zero if we have inputs/outputs participation
			if raw_qty <= 0 and (total_hash > 0 or flt(row.pounds_ran) > 0):
				raw_qty = flt(row.pounds_ran) or 0
			
			# Cap at pounds_sent if calculation exceeds it
			pounds_sent = flt(row.pounds_sent)
			if raw_qty > pounds_sent and pounds_sent > 0:
				raw_qty = pounds_sent
				
			row.raw_material_quantity = flt(raw_qty, 4)

	def on_submit(self):
		# Existing lab batch status update logic
		self._update_lab_batch_status()

		# Create draft Stock Entry (Repack)
		try:
			self._create_repack_stock_entry()
		except Exception as e:
			frappe.log_error(message=frappe.get_traceback(), title="Rosin Recording Stock Entry Creation Failed")
			frappe.msgprint(_("Failed to create Stock Entry. Please check Error Log for details."), indicator="red")

		# Send batch close-out notification email
		try:
			self._send_batch_closeout_email()
		except Exception as e:
			frappe.log_error(message=frappe.get_traceback(), title="Rosin Recording Email Notification Failed")
			frappe.msgprint(_("Failed to send close-out email. Please check Error Log for details."), indicator="orange")

	def _send_batch_closeout_email(self):
		"""Send a close-out summary email when a Rosin Recording is submitted."""

		# ── 1. Find the Lab Batch Entry ──────────────────────────────────────
		lab_batch_name = frappe.db.get_value(
			"Lab Batch Entry",
			{
				"batchproject": self.batch,
				"tolling_partner": self.tolling_partner,
			},
			"name"
		)

		from_date = None
		to_date   = frappe.utils.today()

		if lab_batch_name:
			lab_batch = frappe.get_doc("Lab Batch Entry", lab_batch_name)
			if lab_batch.lab_batch_entry_child:
				from_date = lab_batch.lab_batch_entry_child[0].date_transferred

		from_date_str = str(from_date) if from_date else "2000-01-01"
		to_date_str   = str(to_date)

		# ── 2. Build the query-report link ────────────────────────────────────
		import urllib.parse
		report_url = (
			"https://erp.motleyterpz.io/app/query-report/Lab%20Tolling%20Report"
			"?tolling_partner={tp}&batch={batch}&from_date={fd}&to_date={td}".format(
				tp=urllib.parse.quote(str(self.tolling_partner or ""), safe=""),
				batch=urllib.parse.quote(str(self.batch or ""), safe=""),
				fd=urllib.parse.quote(from_date_str, safe=""),
				td=urllib.parse.quote(to_date_str, safe=""),
			)
		)

		# ── 3. Build the HTML table rows from lab_tolling_data ────────────────
		rows_html = ""
		for row in self.lab_tolling_data:
			rows_html += """
			<tr>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9">{strain}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace">{lbs_sent}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace">{lbs_ran}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace">{amt_ran_g}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace">{total_hash}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace">{actual_hash_yield}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace;color:#94a3b8">{exp_hash_yield}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace">{total_rosin}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace">{actual_rosin_yield}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace;color:#94a3b8">{exp_rosin_yield}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace;color:#059669">{prime}</td>
				<td style="padding:9px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-family:monospace;color:#d97706">{subprime}</td>
			</tr>""".format(
				strain             = frappe.utils.escape_html(str(row.strain_name or "—")),
				lbs_sent           = frappe.utils.fmt_money(row.pounds_sent or 0, precision=4),
				lbs_ran            = frappe.utils.fmt_money(row.pounds_ran or 0, precision=4),
				amt_ran_g          = frappe.utils.fmt_money(row.amount_ran_grams or 0, precision=2),
				total_hash         = frappe.utils.fmt_money(row.total_hash or 0, precision=2),
				actual_hash_yield  = "{:.2f}%".format(flt(row.actual_yield_to_hash)),
				exp_hash_yield     = "{:.2f}%".format(flt(row.expected_hash_yield or row.get("expected__yield__to_hash") or 0)),
				total_rosin        = frappe.utils.fmt_money(row.total_rosin or 0, precision=2),
				actual_rosin_yield = "{:.2f}%".format(flt(row.actual_rosin_yield)),
				exp_rosin_yield    = "{:.2f}%".format(flt(row.expected_rosin_yield or self.expected_rosin_yield or 0)),
				prime              = frappe.utils.fmt_money(row.prime_inventory_total_tolled or 0, precision=4),
				subprime           = frappe.utils.fmt_money(row.subprime_total_tolled or 0, precision=4),
			)

		message = """
<div style="font-family:Arial,sans-serif;max-width:960px;margin:0 auto;color:#1e293b">

  <div style="background:#1e293b;padding:24px 32px;border-radius:10px 10px 0 0">
    <h1 style="margin:0;font-size:20px;color:#fff;font-weight:700;letter-spacing:-0.3px">
      Batch Close-Out Report
    </h1>
    <p style="margin:6px 0 0;font-size:13px;color:#94a3b8">
      {batch} &nbsp;&middot;&nbsp; {tolling_partner} &nbsp;&middot;&nbsp; Submitted {today}
    </p>
  </div>

  <div style="background:#f8fafc;padding:20px 32px;border:1px solid #e2e8f0;border-top:none">

    <!-- Summary strip -->
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
      <tr>
        <td style="padding:12px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;text-align:center;width:25%">
          <div style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">Total Lbs Sent</div>
          <div style="font-size:22px;font-weight:700;color:#7c3aed">{total_qty}</div>
        </td>
        <td style="width:12px"></td>
        <td style="padding:12px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;text-align:center;width:25%">
          <div style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">Tolling Charges</div>
          <div style="font-size:22px;font-weight:700;color:#b45309">${tolling_charges}</div>
        </td>
        <td style="width:12px"></td>
        <td style="padding:12px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;text-align:center;width:25%">
          <div style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">Date Range</div>
          <div style="font-size:14px;font-weight:700;color:#1e293b">{from_date} &rarr; {to_date}</div>
        </td>
        <td style="width:12px"></td>
        <td style="padding:12px 20px;background:#7c3aed;border-radius:8px;text-align:center;vertical-align:middle;width:25%">
          <a href="{report_url}" style="color:#fff;font-size:13px;font-weight:700;text-decoration:none;display:block">
            View Full Report &rarr;
          </a>
        </td>
      </tr>
    </table>

    <!-- Detail table -->
    <div style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;font-size:12px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
        <thead>
          <tr style="background:#f1f5f9">
            <th style="padding:9px 12px;text-align:left;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Strain</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Lbs Sent</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Lbs Ran</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Grams Ran</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Total Hash</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Hash Yield (Act)</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Hash Yield (Exp)</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Total Rosin</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Rosin Yield (Act)</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Rosin Yield (Exp)</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Prime (lbs)</th>
            <th style="padding:9px 12px;text-align:right;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e2e8f0">Subprime (lbs)</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>

    <p style="margin:20px 0 0;font-size:11px;color:#94a3b8;text-align:center">
      Automated notification from Motley Terpz ERP &nbsp;&middot;&nbsp;
      <a href="https://erp.motleyterpz.io/app/rosin-recording/{doc_name}" style="color:#7c3aed">View Rosin Recording</a>
    </p>
  </div>
</div>
""".format(
			batch           = frappe.utils.escape_html(str(self.batch or self.name)),
			tolling_partner = frappe.utils.escape_html(str(self.tolling_partner or "")),
			today           = frappe.utils.formatdate(frappe.utils.today(), "MMM d, yyyy"),
			total_qty       = "{:.4f}".format(flt(self.total_quantity)),
			tolling_charges = "{:,.2f}".format(flt(self.tolling_partner_charges)),
			from_date       = frappe.utils.formatdate(from_date_str, "MMM d, yyyy") if from_date else "&mdash;",
			to_date         = frappe.utils.formatdate(to_date_str, "MMM d, yyyy"),
			report_url      = report_url,
			rows_html       = rows_html,
			doc_name        = self.name,
		)

		# ── 5. Resolve recipients ──────────────────────────────────────────────
		recipients = frappe.db.get_single_value("Cannabis Management Settings", "batch_closeout_email") or ""
		recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]

		# Always include the submitting user
		submitter_email = frappe.db.get_value("User", frappe.session.user, "email")
		if submitter_email and submitter_email not in recipient_list:
			recipient_list.append(submitter_email)

		if not recipient_list:
			frappe.log_error(
				message="No recipients configured for batch close-out email.",
				title="Rosin Recording Email: No Recipients"
			)
			return

		# ── 6. Send ───────────────────────────────────────────────────────────
		frappe.sendmail(
			recipients = recipient_list,
			subject    = "Batch Closed: {batch} — {tolling_partner}".format(
				batch           = self.batch or self.name,
				tolling_partner = self.tolling_partner or "",
			),
			message    = message,
			now        = True,
		)

		frappe.msgprint(
			_("Close-out email sent to: {0}").format(", ".join(recipient_list)),
			alert=True,
		)

	def _update_lab_batch_status(self):
		"""Update linked Lab Batch Entry status to Rosin Produced."""
		hash_rec_name = self.hash_reference

		if not hash_rec_name:
			return

		lab_batch_name = frappe.db.get_value(
			"Hash Recording",
			hash_rec_name,
			"lab_batch_refrence"
		)

		if lab_batch_name:
			frappe.publish_realtime(
				"lab_batch_status_update",
				{"lab_batch": lab_batch_name, "status": "Rosin Produced"},
				user=frappe.session.user
			)
			frappe.msgprint(
				_("Lab Batch Entry {0} status updated to Rosin Produced.").format(
					f'<a href="/app/lab-batch-entry/{lab_batch_name}">{lab_batch_name}</a>'
				),
				alert=True
			)

	def _create_repack_stock_entry(self):
		"""Create a draft Repack Stock Entry from Rosin Recording child rows."""
		frappe.logger().info(f"Starting Stock Entry creation for {self.name}")
		
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Repack"
		se.company = "Motley Terpz"
		se.custom_rosin_recording_reference = self.name

		has_items = False

		for row in self.lab_tolling_data:
			# ── Row 1: Raw Material (strain_name) ──
			raw_qty = flt(row.raw_material_quantity)

			if row.strain_name and raw_qty > 0:
				se.append("items", {
					"item_code": row.strain_name,
					"qty": raw_qty,
					"s_warehouse": self.tolling_partner,
					"is_finished_item": 0,
					"allow_zero_valuation_rate": 1,
				})
				has_items = True

			# ── Row 2: Prime Strain (finished good) ──
			prime_qty = flt(row.prime_inventory_total_tolled)
			if prime_qty > 0 and row.prime_strain:
				se.append("items", {
					"item_code": row.prime_strain,
					"qty": prime_qty,
					"t_warehouse": self.target_warehouse,
					"is_finished_item": 1,
				})
				has_items = True

			# ── Row 3: Subprime Strain (finished good) ──
			subprime_qty = flt(row.subprime_total_tolled)
			if subprime_qty > 0 and row.subprime_strain:
				se.append("items", {
					"item_code": row.subprime_strain,
					"qty": subprime_qty,
					"t_warehouse": self.target_warehouse,
					"is_finished_item": 1,
				})
				has_items = True

		if not has_items:
			frappe.msgprint(
				_("No items to create Stock Entry. Please ensure strain names and quantities are filled."),
				alert=True
			)
			return

		# ── Additional Cost: Tolling Partner Charges ──
		if flt(self.tolling_partner_charges) > 0 and self.expense_account:
			se.append("additional_costs", {
				"expense_account": self.expense_account,
				"description": "Tolling Partner Charges",
				"amount": flt(self.tolling_partner_charges),
			})

		se.insert(ignore_permissions=True)
		frappe.msgprint(
			_("Draft Stock Entry {0} created.").format(
				f'<a href="/app/stock-entry/{se.name}">{se.name}</a>'
			),
			alert=True,
		)


@frappe.whitelist()
def get_stock_balance_items(project, warehouse):
	if not project or not warehouse:
		return []

	from erpnext.stock.report.stock_balance.stock_balance import execute

	filters = frappe._dict({
		"from_date": "2000-01-01",
		"to_date": frappe.utils.today(),
		"warehouse": [warehouse],
		"project": [project],
		"company": "Motley Terpz",
	})

	_columns, data = execute(filters)

	return [
		{
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name") or frappe.db.get_value("Item", row.get("item_code"), "item_name") or row.get("item_code"),
			"bal_qty": flt(row.get("bal_qty")),
			"posting_date": frappe.db.get_value("Stock Ledger Entry", {
				"item_code": row.get("item_code"),
				"warehouse": warehouse,
				"project": project,
				"is_cancelled": 0
			}, "posting_date", order_by="posting_date desc")
		}
		for row in (data or [])
		if flt(row.get("bal_qty")) > 0
	]