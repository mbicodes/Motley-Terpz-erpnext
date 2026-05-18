frappe.pages['weekly-sales-order'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Weekly Sales Order',
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
					<h1>WEEKLY SALES ORDER REPORT</h1>
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
		let from = $('#wso-from-date').val() || '';
		let to   = $('#wso-to-date').val()   || '';
		let title = `Weekly Sales Order Report — ${frappe.datetime.str_to_user(from)} to ${frappe.datetime.str_to_user(to)}`;
		let style_links = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
			.map(l => `<link rel="stylesheet" href="${l.href}">`)
			.join('\n');
		let content = this.wrapper.find('.weekly-so-wrapper').prop('outerHTML') || '';
		let html = `<!DOCTYPE html><html lang="en"><head>
			<meta charset="utf-8">
			<title>${title}</title>
			${style_links}
			<style>
				html,body{margin:0;padding:0;background:#fff;}
				.wso-filter-bar,.wso-signoff-banner{display:none!important;}
				.wso-header{border-radius:0!important;}
				@page{size:A4 landscape;margin:.4in .3in;}
				@media print{
					.wso-glance-grid{grid-template-columns:repeat(3,1fr)!important;}
					.wso-gap-grid{grid-template-columns:repeat(2,1fr)!important;}
					.wso-collections-grid{grid-template-columns:1fr!important;}
				}
			</style>
		</head><body>${content}
		<script>window.addEventListener('load',function(){setTimeout(function(){window.print();},600);window.addEventListener('afterprint',function(){window.close();});});<\/script>
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
