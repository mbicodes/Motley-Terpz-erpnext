frappe.pages['weekly-sales-order'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Weekly Sales Report',
		single_column: true
	});
	wrapper.page_instance = new WeeklySalesOrder(page);
};

frappe.pages['weekly-sales-order'].on_page_show = function(wrapper) {
	if (wrapper.page_instance) wrapper.page_instance.refresh();
};

class WeeklySalesOrder {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.setup_page();
		this.render_layout();
		this.refresh();
	}

	setup_page() {
		this.page.set_primary_action(__('Refresh'), () => this.refresh(), 'octicon octicon-sync');
	}

	// ── Date helpers ────────────────────────────────────────────────

	get_monday() {
		let d = new Date();
		let day = d.getDay();
		let diff = d.getDate() - day + (day === 0 ? -6 : 1);
		return frappe.datetime.obj_to_str(new Date(d.setDate(diff)));
	}

	get_sunday() {
		let monday = new Date(this.get_monday());
		let sunday = new Date(monday);
		sunday.setDate(sunday.getDate() + 6);
		return frappe.datetime.obj_to_str(sunday);
	}

	// ── Layout ──────────────────────────────────────────────────────

	render_layout() {
		let monday = this.get_monday();
		let sunday = this.get_sunday();

		this.wrapper.html(`
		<div class="weekly-so-wrapper">

			<!-- Header -->
			<div class="wso-header">
				<div class="wso-header-left">
					<h1>WEEKLY SALES REPORT</h1>
					<span class="wso-header-accent"></span>
				</div>
				<div class="wso-generated-date">Generated: ${frappe.datetime.str_to_user(frappe.datetime.nowdate())}</div>
			</div>

			<!-- Sign-off banner -->
			<div id="wso-signoff-banner" style="display:none;"></div>

			<!-- Filter Bar -->
			<div class="wso-filter-bar">
				<button class="wso-btn wso-btn-nav" id="wso-prev-week">&#8249; Prev Week</button>
				<div class="wso-filter-divider"></div>
				<div class="wso-filter-group">
					<label class="wso-filter-label">From</label>
					<input type="date" class="wso-date-input" id="wso-from-date" value="${monday}">
				</div>
				<span class="wso-filter-sep">—</span>
				<div class="wso-filter-group">
					<label class="wso-filter-label">To</label>
					<input type="date" class="wso-date-input" id="wso-to-date" value="${sunday}">
				</div>
				<button class="wso-btn wso-btn-primary" id="wso-apply-filter">Apply</button>
				<div class="wso-filter-divider"></div>
				<button class="wso-btn wso-btn-nav" id="wso-next-week">Next Week &#8250;</button>
				<div class="wso-filter-spacer"></div>
				<button class="wso-btn wso-btn-export" id="wso-export-pdf">
					<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" style="flex-shrink:0"><path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/><path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/></svg>
					Export PDF
				</button>
			</div>

			<!-- Loading -->
			<div id="wso-loading" class="wso-loading">
				<div class="spinner"></div>
				<div>Loading dashboard…</div>
			</div>

			<!-- Dashboard Content -->
			<div id="wso-content" style="display:none;">

				<!-- S1: Week at a Glance -->
				<div class="wso-section">
					<div class="wso-section-title">WEEK AT A GLANCE</div>
					<div class="wso-glance-grid" id="wso-glance"></div>
				</div>

				<!-- S3: Customer Breakdown -->
				<div class="wso-section">
					<div class="wso-section-title">CUSTOMER BREAKDOWN</div>
					<div class="wso-table-container">
						<div class="wso-table-wrap">
							<table class="wso-table" id="wso-customer-table">
								<thead><tr>
									<th>Customer</th>
									<th class="text-right">Orders</th>
									<th class="text-right">Order Value</th>
									<th class="text-right">Invoices</th>
									<th class="text-right">Invoiced</th>
									<th class="text-right">Collected</th>
									<th class="text-right">Outstanding</th>
									<th>Last Payment</th>
									<th>AR Status</th>
								</tr></thead>
								<tbody id="wso-customer-tbody"></tbody>
							</table>
						</div>
					</div>
				</div>

				<!-- S4: Gap Report -->
				<div class="wso-section">
					<div class="wso-section-title">GAP REPORT</div>
					<div class="wso-gap-grid" id="wso-gap-grid"></div>
				</div>

				<!-- S5: Collections Detail -->
				<div class="wso-section">
					<div class="wso-section-title">COLLECTIONS DETAIL</div>
					<div id="wso-collections"></div>
				</div>

				<!-- S6: Trajectory -->
				<div class="wso-section">
					<div class="wso-section-title">LAST 4 WEEKS — TRAJECTORY</div>
					<div class="wso-table-container">
						<div class="wso-table-wrap">
							<table class="wso-table" id="wso-trajectory-table">
								<thead><tr>
									<th>Week</th>
									<th class="text-right">SO Value</th>
									<th class="text-right">Invoiced</th>
									<th class="text-right">Collected</th>
									<th class="text-center">Trend</th>
								</tr></thead>
								<tbody id="wso-trajectory-tbody"></tbody>
							</table>
						</div>
					</div>
				</div>

				<!-- Sales Orders Detail -->
				<div class="wso-section">
					<div class="wso-table-container">
						<div class="wso-section-header">
							THIS WEEK — Sales Orders with Delivery Notes, Invoices &amp; Payments
						</div>
						<div class="wso-table-wrap">
							<table class="wso-table" id="wso-orders-table">
								<thead><tr>
									<th>Sales Order</th>
									<th>Date</th>
									<th>Customer</th>
									<th>Sales Person</th>
									<th class="text-right">SO Value ($)</th>
									<th>Delivery Notes</th>
									<th>Invoices</th>
									<th>Payment Account</th>
									<th class="text-right">Paid ($)</th>
								</tr></thead>
								<tbody id="wso-orders-tbody"></tbody>
							</table>
						</div>
					</div>
				</div>

			</div><!-- /#wso-content -->
		</div>`);

		this.bind_events();
	}

	bind_events() {
		$('#wso-apply-filter').on('click', () => this.refresh());
		$('#wso-from-date, #wso-to-date').on('change', () => this.refresh());
		$('#wso-prev-week').on('click', () => this.shift_week(-7));
		$('#wso-next-week').on('click', () => this.shift_week(7));
		$('#wso-export-pdf').on('click', () => this.print_report());
	}

	shift_week(days) {
		let from = $('#wso-from-date').val();
		let to   = $('#wso-to-date').val();
		if (!from || !to) return;
		$('#wso-from-date').val(frappe.datetime.add_days(from, days));
		$('#wso-to-date').val(frappe.datetime.add_days(to, days));
		this.refresh();
	}

	// ── Data load ───────────────────────────────────────────────────

	refresh() {
		let from_date = $('#wso-from-date').val() || this.get_monday();
		let to_date   = $('#wso-to-date').val()   || this.get_sunday();

		$('#wso-loading').show();
		$('#wso-content').hide();
		$('#wso-signoff-banner').hide();

		frappe.call({
			method: 'cannabis_management.cannabis_management.page.weekly_sales_order.weekly_sales_order.get_dashboard_data',
			args: { from_date, to_date },
			callback: (r) => {
				if (r.message) {
					let d = r.message;
					this.render_glance(d.week_at_a_glance);
					this.render_customer_breakdown(d.customer_breakdown);
					this.render_gap_report(d.gap_report);
					this.render_collections(d.collections_detail);
					this.render_trajectory(d.trajectory);
					this.render_orders_table(d.orders_table);
					this.render_signoff_banner(d.acknowledgment, from_date);
				}
				$('#wso-loading').hide();
				$('#wso-content').show();
			},
			error: () => {
				$('#wso-loading').hide();
				frappe.msgprint(__('Error loading dashboard. Please try again.'));
			}
		});
	}

	// ── Section 1: Week at a Glance ─────────────────────────────────

	render_glance(g) {
		let cards = [
			{ id: 'kpi-so',      value: `${g.so_count} <span class="wso-kpi-sub">${this.fmt_currency(g.so_value)}</span>`, label: 'Sales Orders' },
			{ id: 'kpi-inv',     value: `${g.invoice_count} <span class="wso-kpi-sub">${this.fmt_currency(g.invoice_value)}</span>`, label: 'Invoices Raised' },
			{ id: 'kpi-dn',      value: g.dn_count, label: 'Deliveries Made' },
			{ id: 'kpi-coll',    value: this.fmt_currency(g.collected), label: 'Collected This Week', highlight: true },
			{ id: 'kpi-ar',      value: this.fmt_currency(g.outstanding_ar), label: 'Total Outstanding AR', warn: g.outstanding_ar > 50000 },
		];

		$('#wso-glance').html(cards.map(c => `
			<div class="wso-glance-card ${c.highlight ? 'highlight' : ''} ${c.warn ? 'warn' : ''}">
				<div class="wso-glance-value">${c.value}</div>
				<div class="wso-glance-label">${c.label}</div>
			</div>
		`).join(''));
	}

	// ── Section 3: Customer Breakdown ────────────────────────────────

	render_customer_breakdown(rows) {
		let tbody = $('#wso-customer-tbody');
		if (!rows || !rows.length) {
			tbody.html('<tr><td colspan="9" class="wso-no-data">No customer activity this period.</td></tr>');
			return;
		}
		tbody.html(rows.map(r => {
			let status_class = { 'OK': 'ar-ok', '30d+': 'ar-30', '60d+': 'ar-60', '90d+': 'ar-90' }[r.ar_status] || '';
			return `<tr>
				<td><strong>${r.customer}</strong></td>
				<td class="text-right">${r.order_count}</td>
				<td class="text-right amount">${this.fmt_currency(r.order_value)}</td>
				<td class="text-right">${r.inv_count}</td>
				<td class="text-right amount">${this.fmt_currency(r.inv_value)}</td>
				<td class="text-right amount ${r.collected > 0 ? 'wso-paid-cell' : ''}">${r.collected > 0 ? this.fmt_currency(r.collected) : this.dash()}</td>
				<td class="text-right amount ${r.outstanding > 0 ? 'wso-ar-cell' : ''}">${r.outstanding > 0 ? this.fmt_currency(r.outstanding) : this.dash()}</td>
				<td>${r.last_payment_date ? frappe.datetime.str_to_user(r.last_payment_date) : this.dash()}</td>
				<td><span class="wso-ar-badge ${status_class}">${r.ar_status}</span></td>
			</tr>`;
		}).join(''));
	}

	// ── Section 4: Gap Report ────────────────────────────────────────

	render_gap_report(g) {
		let panels = [
			{
				title: 'Orders Without Invoices',
				subtitle: '>7 days old, no invoice raised',
				items: g.orders_no_invoice,
				render_row: r => `<span class="wso-gap-link">${this.link('Sales Order', r.name)}</span>
					<span class="wso-gap-customer">${r.customer}</span>
					<span class="wso-gap-meta">${r.days_open}d — ${this.fmt_currency(r.grand_total)}</span>`,
				icon: '📋',
			},
			{
				title: 'Deliveries Without Invoices',
				subtitle: 'Product left building, never billed',
				items: g.dns_no_invoice,
				render_row: r => `<span class="wso-gap-link">${this.link('Delivery Note', r.name)}</span>
					<span class="wso-gap-customer">${r.customer}</span>
					<span class="wso-gap-meta">${r.days_open}d old</span>`,
				icon: '🚚',
			},
			{
				title: 'Invoices Without Deliveries',
				subtitle: 'Invoice raised but no DN on record',
				items: g.invoices_no_dn,
				render_row: r => `<span class="wso-gap-link">${this.link('Sales Invoice', r.name)}</span>
					<span class="wso-gap-customer">${r.customer}</span>
					<span class="wso-gap-meta">${this.fmt_currency(r.grand_total)}</span>`,
				icon: '🧾',
			},
			{
				title: 'Aging AR — Unpaid >30 Days',
				subtitle: 'Outstanding invoices by age bucket',
				items: g.aging_ar,
				render_row: r => {
					let bucket = r.age_days > 90 ? 'ar-90' : r.age_days > 60 ? 'ar-60' : 'ar-30';
					return `<span class="wso-gap-link">${this.link('Sales Invoice', r.name)}</span>
						<span class="wso-gap-customer">${r.customer}</span>
						<span class="wso-gap-meta"><span class="wso-ar-badge ${bucket}">${r.age_days}d</span> ${this.fmt_currency(r.outstanding_amount)}</span>`;
				},
				icon: '⏰',
			},
		];

		$('#wso-gap-grid').html(panels.map(p => {
			let has_items = p.items && p.items.length > 0;
			let rows_html = has_items
				? p.items.slice(0, 10).map(r => `<div class="wso-gap-row">${p.render_row(r)}</div>`).join('')
				  + (p.items.length > 10 ? `<div class="wso-gap-more">+${p.items.length - 10} more</div>` : '')
				: `<div class="wso-gap-empty">No issues found ✓</div>`;

			return `
			<div class="wso-gap-panel ${has_items ? 'has-items' : 'is-clear'}">
				<div class="wso-gap-panel-head">
					<span class="wso-gap-icon">${p.icon}</span>
					<div>
						<div class="wso-gap-title">${p.title}</div>
						<div class="wso-gap-subtitle">${p.subtitle}</div>
					</div>
					<div class="wso-gap-count ${has_items ? 'count-alert' : 'count-ok'}">${p.items ? p.items.length : 0}</div>
				</div>
				<div class="wso-gap-body">${rows_html}</div>
			</div>`;
		}).join(''));
	}

	// ── Section 5: Collections Detail ────────────────────────────────

	render_collections(c) {
		let cash_html  = this.collections_table(c.cash,  'Cash',  c.cash_total);
		let bank_html  = this.collections_table(c.bank,  'Bank',  c.bank_total);

		let unalloc_html = '';
		if (c.unallocated && c.unallocated.length) {
			unalloc_html = `
			<div class="wso-collections-alert">
				<div class="wso-collections-alert-title">⚠ Unallocated Payments — Needs Clearing</div>
				<table class="wso-table">
					<thead><tr><th>Payment</th><th>Customer</th><th class="text-right">Paid</th><th class="text-right">Unallocated</th><th>Date</th><th>Mode</th></tr></thead>
					<tbody>${c.unallocated.map(p => `<tr>
						<td>${this.link('Payment Entry', p.name)}</td>
						<td>${p.customer}</td>
						<td class="text-right amount">${this.fmt_currency(p.paid_amount)}</td>
						<td class="text-right amount wso-ar-cell">${this.fmt_currency(p.unallocated_amount)}</td>
						<td>${frappe.datetime.str_to_user(p.posting_date)}</td>
						<td>${p.mode_of_payment || '—'}</td>
					</tr>`).join('')}</tbody>
				</table>
			</div>`;
		}

		let flags_html = '';
		if (c.flags_8300 && c.flags_8300.length) {
			flags_html = `
			<div class="wso-8300-block">
				<div class="wso-8300-title">🚨 IRS Form 8300 — Pending / Overdue Filing</div>
				<table class="wso-table">
					<thead><tr><th>Log</th><th>Payment Entry</th><th>Customer</th><th class="text-right">Cash Amount</th><th>Transaction Date</th><th>Deadline</th><th>Status</th></tr></thead>
					<tbody>${c.flags_8300.map(f => `<tr class="wso-8300-row">
						<td>${this.link('IRS Form 8300 Log', f.name)}</td>
						<td>${this.link('Payment Entry', f.payment_entry)}</td>
						<td>${f.customer}</td>
						<td class="text-right amount">${this.fmt_currency(f.cash_amount)}</td>
						<td>${frappe.datetime.str_to_user(f.transaction_date)}</td>
						<td class="${f.filing_status === 'Overdue' ? 'wso-overdue' : ''}">${frappe.datetime.str_to_user(f.filing_deadline)}</td>
						<td><span class="wso-ar-badge ${f.filing_status === 'Overdue' ? 'ar-90' : 'ar-30'}">${f.filing_status}</span></td>
					</tr>`).join('')}</tbody>
				</table>
			</div>`;
		}

		$('#wso-collections').html(`
			<div class="wso-collections-grid">
				${cash_html}
				${bank_html}
			</div>
			${unalloc_html}
			${flags_html}
		`);
	}

	collections_table(rows, label, total) {
		let icon = label === 'Cash' ? '💵' : '🏦';
		if (!rows || !rows.length) {
			return `<div class="wso-collections-col">
				<div class="wso-collections-col-head">${icon} ${label} Payments <span class="wso-col-total">${this.fmt_currency(0)}</span></div>
				<div class="wso-no-data" style="padding:20px 0;">No ${label.toLowerCase()} payments this week.</div>
			</div>`;
		}
		return `<div class="wso-collections-col">
			<div class="wso-collections-col-head">${icon} ${label} Payments <span class="wso-col-total">${this.fmt_currency(total)}</span></div>
			<table class="wso-table">
				<thead><tr><th>Payment</th><th>Customer</th><th class="text-right">Amount</th><th>Account</th><th>Date</th></tr></thead>
				<tbody>${rows.map(p => `<tr>
					<td>${this.link('Payment Entry', p.name)}</td>
					<td>${p.customer}</td>
					<td class="text-right amount wso-paid-cell">${this.fmt_currency(p.amount)}</td>
					<td class="wso-account-cell">${p.account || '—'}</td>
					<td>${frappe.datetime.str_to_user(p.date)}</td>
				</tr>`).join('')}</tbody>
			</table>
		</div>`;
	}

	// ── Section 6: Trajectory ────────────────────────────────────────

	render_trajectory(weeks) {
		if (!weeks || !weeks.length) return;
		let rows = weeks.map((w, i) => {
			let trend = '';
			if (i > 0) {
				let prev = weeks[i - 1];
				let diff = w.collected - prev.collected;
				if (diff > 0)       trend = '<span class="wso-trend-up">↑</span>';
				else if (diff < 0)  trend = '<span class="wso-trend-down">↓</span>';
				else                trend = '<span class="wso-trend-flat">→</span>';
			}
			let is_current = (i === weeks.length - 1);
			return `<tr class="${is_current ? 'wso-current-week' : ''}">
				<td>${frappe.datetime.str_to_user(w.week_start)} — ${frappe.datetime.str_to_user(w.week_end)}</td>
				<td class="text-right amount">${this.fmt_currency(w.so_value)}</td>
				<td class="text-right amount">${this.fmt_currency(w.invoice_value)}</td>
				<td class="text-right amount">${this.fmt_currency(w.collected)}</td>
				<td class="text-center">${trend}</td>
			</tr>`;
		});
		$('#wso-trajectory-tbody').html(rows.join(''));
	}

	// ── Sales Orders Detail Table ────────────────────────────────────

	render_orders_table(orders) {
		let tbody = $('#wso-orders-tbody');
		if (!orders || !orders.length) {
			tbody.html('<tr><td colspan="9" class="wso-no-data">No sales orders found for this period.</td></tr>');
			return;
		}
		tbody.html(orders.map(row => {
			let dn_links  = (row.delivery_notes || []).map(dn => this.link('Delivery Note', dn)).join('<br>') || this.dash();
			let inv_links = (row.invoices || []).map(inv => this.link('Sales Invoice', inv)).join('<br>') || this.dash();
			let pay_links = (row.payment_entries || []).map(pe => {
				let acct = pe.account ? `<br><span class="wso-sub-text">→ ${pe.account}</span>` : '';
				return this.link('Payment Entry', pe.name) + acct;
			}).join('<br>') || this.dash();
			let paid = (row.payment_entries || []).reduce((s, pe) => s + (pe.amount || 0), 0);
			return `<tr>
				<td>${this.link('Sales Order', row.name)}</td>
				<td>${frappe.datetime.str_to_user(row.transaction_date)}</td>
				<td><strong>${row.customer}</strong></td>
				<td>${row.sales_person || this.dash()}</td>
				<td class="text-right amount">${this.fmt_currency(row.grand_total)}</td>
				<td>${dn_links}</td>
				<td>${inv_links}</td>
				<td>${pay_links}</td>
				<td class="text-right amount ${paid > 0 ? 'wso-paid-cell' : ''}">${paid > 0 ? this.fmt_currency(paid) : this.dash()}</td>
			</tr>`;
		}).join(''));
	}

	// ── Sign-off Banner ──────────────────────────────────────────────

	render_signoff_banner(ack, from_date) {
		let banner = $('#wso-signoff-banner');
		if (!ack || !ack.exists) { banner.hide(); return; }

		if (ack.is_acknowledged) {
			banner.attr('class', 'wso-signoff-banner wso-signoff-green').html(`
				<span class="wso-signoff-icon">✅</span>
				<div><strong>Report Acknowledged</strong> — signed off by <strong>${ack.acknowledged_by}</strong> on ${ack.acknowledged_at}</div>
			`).show();
		} else {
			let action_html = ack.can_acknowledge
				? `<div style="margin-top:10px;">
					<textarea class="wso-signoff-notes" id="wso-ack-notes" placeholder="Optional notes…" rows="2"></textarea>
					<button class="wso-btn wso-btn-primary" id="wso-ack-btn" style="margin-top:8px;">Acknowledge This Report</button>
				   </div>`
				: `<span class="wso-signoff-sub" style="display:block;margin-top:4px;">Awaiting Nikki's acknowledgment.</span>`;

			banner.attr('class', 'wso-signoff-banner wso-signoff-amber').html(`
				<span class="wso-signoff-icon">⚠</span>
				<div class="wso-signoff-body">
					<strong>This report has not been acknowledged yet.</strong>
					${action_html}
				</div>
			`).show();

			if (ack.can_acknowledge) {
				$('#wso-ack-btn').on('click', () => {
					let notes = $('#wso-ack-notes').val() || '';
					frappe.call({
						method: 'cannabis_management.cannabis_management.page.weekly_sales_order.weekly_sales_order.acknowledge_weekly_report',
						args: { week_start: from_date, notes },
						callback: (r) => {
							if (r.message && r.message.status !== 'error') {
								this.refresh();
							}
						}
					});
				});
			}
		}
	}

	// ── Print / Export PDF ───────────────────────────────────────────

	print_report() {
		let from_date = $('#wso-from-date').val() || '';
		let to_date   = $('#wso-to-date').val()   || '';
		if (!from_date || !to_date) { frappe.msgprint(__('Please select a date range.')); return; }

		frappe.call({
			method: 'cannabis_management.cannabis_management.page.weekly_sales_order.weekly_sales_order.get_pdf_export_data',
			args: { from_date, to_date },
			callback: (r) => {
				if (!r.message) return;
				this._open_pdf_window(r.message, from_date, to_date);
			},
			error: () => frappe.msgprint(__('Error generating PDF. Please try again.'))
		});
	}

	_open_pdf_window(data, from_date, to_date) {
		let k = data.kpis || {};
		let from_str = frappe.datetime.str_to_user(from_date);
		let to_str   = frappe.datetime.str_to_user(to_date);
		let today    = frappe.datetime.str_to_user(frappe.datetime.nowdate());
		let title    = `Weekly Sales Report — ${from_str} to ${to_str}`;
		let f = v => (v == null || isNaN(v)) ? '—' : '$' + parseFloat(v).toLocaleString('en-US', {minimumFractionDigits:0, maximumFractionDigits:0});
		let lnk = (dt, name) => name ? `<a href="/app/${dt.toLowerCase().replace(/ /g,'-')}/${encodeURIComponent(name)}">${name}</a>` : '—';

		/* ── KPI Row ─────────────────────────────────────── */
		let kpi_cards = [
			{ v: k.so_count,              l: 'Sales Orders' },
			{ v: k.dn_count,              l: 'Delivery Notes (week)' },
			{ v: k.invoice_count,         l: 'Invoices (week)' },
			{ v: k.payment_count,         l: 'Payments (week)' },
			{ v: f(k.so_value),           l: 'Total Order Value' },
			{ v: f(k.collected_prev_period), l: 'Collected — Prev. Period', sub: 'SO' },
			{ v: f(k.outstanding_ar),     l: 'Outstanding', sub: 'AR' },
			{ v: f(k.collected),          l: 'Grand Total Collected', hi: true },
		].map(c => `<div class="kpi-card${c.hi?' kpi-hi':''}">
			<div class="kpi-val">${c.v}${c.sub?`<span class="kpi-sub">${c.sub}</span>`:''}</div>
			<div class="kpi-lbl">${c.l}</div>
		</div>`).join('');

		/* ── Orders Table ────────────────────────────────── */
		let orders = data.orders_table || [];
		let ord_total_so = 0, ord_total_paid = 0;
		let ord_rows = orders.map(row => {
			let dn   = (row.delivery_notes||[]).map(d=>lnk('Delivery Note',d)).join('<br>')||'—';
			let inv  = (row.invoices||[]).map(i=>lnk('Sales Invoice',i)).join('<br>')||'—';
			let pes  = row.payment_entries||[];
			let acct = pes.map(p=>p.account||p.name).join('<br>')||'—';
			let paid = pes.reduce((s,p)=>s+(p.amount||0),0);
			ord_total_so   += row.grand_total||0;
			ord_total_paid += paid;
			return `<tr>
				<td>${lnk('Sales Order',row.name)}</td>
				<td style="white-space:nowrap">${frappe.datetime.str_to_user(row.transaction_date)}</td>
				<td><b>${row.customer}</b></td>
				<td>${row.sales_person||'—'}</td>
				<td class="tr">${f(row.grand_total)}</td>
				<td>${dn}</td><td>${inv}</td>
				<td class="acct">${acct}</td>
				<td class="tr${paid>0?' paid':''}">${paid>0?f(paid):'—'}</td>
			</tr>`;
		}).join('');
		let ord_tfoot = `<tr class="tot"><td colspan="4"><b>TOTAL</b></td><td class="tr"><b>${f(ord_total_so)}</b></td><td colspan="3"></td><td class="tr"><b>${f(ord_total_paid)}</b></td></tr>`;

		/* ── Payments Table ───────────────────────────────── */
		let payments = data.payments_table || [];
		let pay_total = payments.reduce((s,p)=>s+(p.paid||0),0);
		let pay_head  = `PAYMENTS COLLECTED THIS WEEK — Against Previous Period (${payments.length} payment${payments.length!==1?'s':''} | Total: ${f(pay_total)})`;
		let pay_rows  = payments.map(p=>`<tr>
			<td>${lnk('Payment Entry',p.name)}</td>
			<td><b>${p.customer}</b></td>
			<td>${p.invoice?lnk('Sales Invoice',p.invoice):'—'}</td>
			<td>${p.linked_so?lnk('Sales Order',p.linked_so):'—'}</td>
			<td class="tr">${p.inv_total>0?f(p.inv_total):'—'}</td>
			<td class="tr paid">${f(p.paid)}</td>
			<td class="acct">${p.account||'—'}</td>
			<td class="reason">${p.reason?`<em>${p.reason}</em>`:'—'}</td>
		</tr>`).join('');
		let pay_tfoot = payments.length ? `<tr class="tot"><td colspan="5"><b>TOTAL</b></td><td class="tr"><b>${f(pay_total)}</b></td><td colspan="2"></td></tr>` : '';
		let pay_empty = !payments.length ? '<tr><td colspan="8" class="empty">No payments collected this week.</td></tr>' : '';

		/* ── Delivery Notes Table ─────────────────────────── */
		let dns      = data.delivery_notes || [];
		let dn_head  = `DELIVERY NOTES DISPATCHED THIS WEEK — Against Previous Sales Orders (${dns.length} note${dns.length!==1?'s':''})`;
		let dn_rows  = dns.map(d=>{
			let sos = (d.linked_sos||[]).map(s=>lnk('Sales Order',s)).join('<br>')||'—';
			return `<tr>
				<td>${lnk('Delivery Note',d.name)}</td>
				<td><b>${d.customer}</b></td>
				<td style="white-space:nowrap">${frappe.datetime.str_to_user(d.posting_date)}</td>
				<td>${d.company}</td>
				<td>${sos}</td>
			</tr>`;
		}).join('') || '<tr><td colspan="5" class="empty">No delivery notes this week.</td></tr>';

		/* ── Full HTML ────────────────────────────────────── */
		let html = `<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><title>${title}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
html,body{background:#fff;font-family:Arial,Helvetica,sans-serif;font-size:10.5px;color:#222;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
/* Header */
.hdr{background:#1a2744!important;color:#fff!important;display:flex;justify-content:space-between;align-items:center;padding:13px 20px;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.hdr-title{font-size:18px;font-weight:800;letter-spacing:1.2px;text-transform:uppercase;}
.hdr-meta{font-size:9.5px;opacity:.8;text-align:right;line-height:1.6;}
/* KPIs */
.kpi-row{display:grid;grid-template-columns:repeat(8,1fr);border-bottom:2px solid #cdd3de;}
.kpi-card{padding:9px 6px;text-align:center;border-right:1px solid #d4d9e8;background:#f7f9fc!important;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.kpi-card:last-child{border-right:none;}
.kpi-hi{background:#1a2744!important;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.kpi-val{font-size:14px;font-weight:800;color:#1a2744;line-height:1.2;}
.kpi-hi .kpi-val{color:#fff!important;}
.kpi-lbl{font-size:8px;color:#777;margin-top:3px;text-transform:uppercase;letter-spacing:.4px;line-height:1.3;}
.kpi-hi .kpi-lbl{color:rgba(255,255,255,.75)!important;}
.kpi-sub{font-size:8px;font-weight:normal;color:#aaa;margin-left:2px;}
.kpi-hi .kpi-sub{color:rgba(255,255,255,.55)!important;}
/* Section headers */
.sec-hd{padding:7px 14px;font-size:10px;font-weight:700;color:#fff!important;letter-spacing:.3px;text-transform:uppercase;margin-top:10px;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sec-blue{background:#1e3a5f!important;}
.sec-teal{background:#1e5f52!important;}
.sec-purple{background:#4a1e5f!important;}
/* Tables */
table{width:100%;border-collapse:collapse;font-size:9.5px;}
th{background:#2d4a6e!important;color:#fff!important;padding:5px 7px;text-align:left;font-size:8.5px;font-weight:700;border:1px solid #1a2744;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
th.tr{text-align:right;}
td{padding:4px 7px;border:1px solid #dde3ed;vertical-align:top;line-height:1.35;}
tr:nth-child(even) td{background:#eef2fb!important;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
tr:nth-child(odd) td{background:#fff!important;}
td.tr{text-align:right;}
a{color:#1e3a5f;text-decoration:none;}
.paid{color:#1a6644;font-weight:600;}
.acct{font-size:8.5px;color:#444;}
.reason{font-style:italic;color:#666;font-size:8.5px;}
.tot td{background:#e3e9f5!important;font-weight:700;border-top:2px solid #1a2744;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.empty{text-align:center;color:#999;padding:14px;font-style:italic;}
/* Footer */
.ftr{text-align:center;font-size:8.5px;color:#aaa;padding:10px;border-top:1px solid #dde3ed;margin-top:10px;}
@page{size:A4 landscape;margin:.35in .3in;}
</style>
</head><body>

<div class="hdr">
	<div class="hdr-title">WEEKLY SALES REPORT</div>
	<div class="hdr-meta">Generated: ${today}<br>${from_str} &mdash; ${to_str}</div>
</div>

<div class="kpi-row">${kpi_cards}</div>

<div class="sec-hd sec-blue">THIS WEEK &mdash; Sales Orders with Delivery Notes, Invoices &amp; Payments</div>
<table>
<thead><tr>
	<th>Sales Order</th><th>Date</th><th>Customer</th><th>Sales Person</th>
	<th class="tr">SO Value ($)</th><th>Delivery Notes</th><th>Invoices</th>
	<th>Payment Account</th><th class="tr">Paid ($)</th>
</tr></thead>
<tbody>${ord_rows||'<tr><td colspan="9" class="empty">No sales orders found for this period.</td></tr>'}</tbody>
<tfoot>${ord_tfoot}</tfoot>
</table>

<div class="sec-hd sec-teal">${pay_head}</div>
<table>
<thead><tr>
	<th>Payment ID</th><th>Customer</th><th>Invoice</th><th>Linked Sales Order</th>
	<th class="tr">Inv. Total ($)</th><th class="tr">Paid ($)</th><th>Account Paid To</th><th>Reason</th>
</tr></thead>
<tbody>${pay_rows||pay_empty}</tbody>
<tfoot>${pay_tfoot}</tfoot>
</table>

<div class="sec-hd sec-purple">${dn_head}</div>
<table>
<thead><tr>
	<th>Delivery Note ID</th><th>Customer</th><th>Dispatch Date</th><th>Company</th><th>Previous Sales Order</th>
</tr></thead>
<tbody>${dn_rows}</tbody>
</table>

<div class="ftr">Report generated: ${today} &nbsp;|&nbsp; Data sourced from ERPNext &mdash; Confidential &mdash; for internal use only</div>

<script>window.addEventListener('load',function(){setTimeout(function(){window.print();},700);window.addEventListener('afterprint',function(){window.close();});});<\/script>
</body></html>`;

		let w = window.open('', '_blank', 'width=1280,height=900');
		if (!w) { frappe.msgprint(__('Please allow pop-ups to export the report.')); return; }
		w.document.open(); w.document.write(html); w.document.close();
	}

	// ── Helpers ──────────────────────────────────────────────────────

	fmt_currency(value) {
		if (value == null || isNaN(value)) return '—';
		return '$' + parseFloat(value).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
	}

	link(doctype, name) {
		if (!name) return this.dash();
		let route = doctype.toLowerCase().replace(/ /g, '-');
		return `<a href="/app/${route}/${encodeURIComponent(name)}">${name}</a>`;
	}

	dash() {
		return '<span class="wso-empty">—</span>';
	}
}
