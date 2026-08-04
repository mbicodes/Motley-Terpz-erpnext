frappe.pages['ar-summary'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Accounts Receivable',
		single_column: true
	});
	wrapper.page = page;

	var METHOD = 'cannabis_management.cannabis_management.page.ar_summary.ar_summary';

	// company / dates are server-side filters (reload); search / status / sort
	// are applied instantly on the loaded rows. Ledger data is fetched lazily.
	var state = {
		view: 'summary',          // 'summary' | 'ledgers'
		company: '', from_date: '', to_date: '',
		search: '', status: 'all', sort: 'outstanding',
		rows: [], ledgers: null, prepared: ''
	};

	page.main.html(`
		<div class="ars-wrap">
			<header class="ars-header">
				<div class="ars-header-text">
					<h1 class="ars-h1">Accounts Receivable</h1>
					<p class="ars-sub" id="ars-prepared"></p>
				</div>
				<div class="ars-header-actions">
					<div class="ars-seg" id="ars-seg">
						<button class="ars-seg-btn is-active" data-view="summary">Summary</button>
						<button class="ars-seg-btn" data-view="ledgers">Ledgers</button>
					</div>
					<button id="ars-refresh" class="ars-icon-btn" title="Refresh"><span id="ars-refresh-ic">&#8635;</span></button>
					<button id="ars-export" class="ars-primary-btn">&#8681;&nbsp;Export to Excel</button>
				</div>
			</header>

			<section class="ars-kpis">
				<div class="ars-kpi ars-kpi--invoice">
					<div class="ars-kpi-top"><span class="ars-kpi-label">Invoice Total</span><span class="ars-kpi-dot"></span></div>
					<div class="ars-kpi-value" id="ars-k-inv">$0.00</div>
				</div>
				<div class="ars-kpi ars-kpi--paid">
					<div class="ars-kpi-top"><span class="ars-kpi-label">Paid Amount</span><span class="ars-kpi-dot"></span></div>
					<div class="ars-kpi-value" id="ars-k-paid">$0.00</div>
				</div>
				<div class="ars-kpi ars-kpi--out">
					<div class="ars-kpi-top"><span class="ars-kpi-label">Outstanding</span><span class="ars-kpi-dot"></span></div>
					<div class="ars-kpi-value" id="ars-k-out">$0.00</div>
				</div>
				<div class="ars-kpi ars-kpi--rate">
					<div class="ars-kpi-top"><span class="ars-kpi-label">Collected</span><span class="ars-kpi-dot"></span></div>
					<div class="ars-kpi-value" id="ars-k-rate">0%</div>
				</div>
				<div class="ars-kpi ars-kpi--cust">
					<div class="ars-kpi-top"><span class="ars-kpi-label">Customers</span><span class="ars-kpi-dot"></span></div>
					<div class="ars-kpi-value" id="ars-k-cust">0</div>
				</div>
			</section>

			<div class="ars-toolbar">
				<div class="ars-field ars-search-field">
					<span class="ars-search-icon">&#128269;</span>
					<input type="text" id="ars-search" class="ars-input" placeholder="Search customer" />
				</div>
				<select id="ars-company" class="ars-select" title="Company">
					<option value="">All Companies</option>
				</select>
				<select id="ars-status" class="ars-select ars-summary-only" title="Payment status">
					<option value="all">All statuses</option>
					<option value="unpaid">Unpaid</option>
					<option value="partial">Partially paid</option>
					<option value="paid">Fully paid</option>
				</select>
				<div class="ars-daterange" title="Invoice date range">
					<input type="date" id="ars-from" />
					<span class="ars-arrow">&rarr;</span>
					<input type="date" id="ars-to" />
				</div>
				<select id="ars-sort" class="ars-select ars-summary-only" title="Sort by">
					<option value="outstanding">Outstanding (high &rarr; low)</option>
					<option value="invoice_total">Invoice total (high &rarr; low)</option>
					<option value="paid">Paid (high &rarr; low)</option>
					<option value="invoices">Most invoices</option>
					<option value="customer">Customer (A &rarr; Z)</option>
				</select>
				<div class="ars-toolbar-sep"></div>
				<button id="ars-clear" class="ars-ghost-btn">Clear filters</button>
			</div>

			<div id="ars-view-summary">
				<div class="ars-table-card" id="ars-table-card">
					<div class="ars-scroll">
						<table class="ars-table">
							<thead>
								<tr>
									<th>Customer</th>
									<th class="ars-c"># Inv</th>
									<th class="ars-r">Invoice Total</th>
									<th class="ars-r">Paid Amount</th>
									<th class="ars-r">Outstanding</th>
									<th class="ars-c">Status</th>
								</tr>
							</thead>
							<tbody id="ars-body"></tbody>
							<tfoot id="ars-foot"></tfoot>
						</table>
					</div>
					<div class="ars-empty" id="ars-empty" style="display:none;">No matching customers.</div>
				</div>
				<div class="ars-footer-row" id="ars-count"></div>
			</div>

			<div id="ars-view-ledgers" style="display:none;">
				<div id="ars-ledgers"></div>
				<div class="ars-empty" id="ars-ledgers-empty" style="display:none;">No matching customers.</div>
			</div>
		</div>
	`);

	function money(v) {
		return '$' + Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}
	function esc(s) { return frappe.utils.escape_html(s == null ? '' : String(s)); }

	function status_of(r) {
		var out = flt(r.outstanding), paid = flt(r.paid);
		if (out <= 0) return 'paid';
		if (paid > 0) return 'partial';
		return 'unpaid';
	}
	var STATUS_META = {
		paid:    { cls: 'ars-pill--paid',    label: 'Paid' },
		partial: { cls: 'ars-pill--partial', label: 'Partial' },
		unpaid:  { cls: 'ars-pill--unpaid',  label: 'Unpaid' }
	};

	// map a Frappe Sales Invoice status string to a pill style
	function invoice_pill(status) {
		var s = (status || '').toLowerCase();
		var cls = 'ars-pill--unpaid';
		if (s.indexOf('overdue') !== -1) cls = 'ars-pill--overdue';
		else if (s === 'paid') cls = 'ars-pill--paid';
		else if (s.indexOf('partly') !== -1) cls = 'ars-pill--partial';
		else if (s.indexOf('return') !== -1 || s.indexOf('credit') !== -1) cls = 'ars-pill--muted';
		return '<span class="ars-pill ' + cls + '">' + esc(status || '') + '</span>';
	}

	// render a Sales Order / Delivery Note reference cell
	function ref_cell(list, doctype) {
		list = list || [];
		if (!list.length) return '<td class="ars-c ars-muted">&mdash;</td>';
		var html = list.map(function (n) {
			return '<a class="ars-inv-link" href="/app/' + doctype + '/' + encodeURIComponent(n) + '">' + esc(n) + '</a>';
		}).join(', ');
		return '<td>' + html + '</td>';
	}

	// ---------- summary view ----------
	function visible_rows() {
		var q = (state.search || '').toLowerCase();
		var rows = state.rows.filter(function (r) {
			if (q && (r.customer || '').toLowerCase().indexOf(q) === -1) return false;
			if (state.status !== 'all' && status_of(r) !== state.status) return false;
			return true;
		});
		var s = state.sort;
		rows.sort(function (a, b) {
			if (s === 'customer') return (a.customer || '').localeCompare(b.customer || '');
			if (s === 'invoices') return (b.invoices || 0) - (a.invoices || 0);
			return flt(b[s]) - flt(a[s]);
		});
		return rows;
	}

	function render_summary() {
		var rows = visible_rows();
		var $body = $('#ars-body').empty();

		rows.forEach(function (r) {
			var out = flt(r.outstanding), paid = flt(r.paid), total = flt(r.invoice_total);
			var pct = total > 0 ? Math.min(100, Math.round((paid / total) * 100)) : 0;
			var st = STATUS_META[status_of(r)];
			var link = '/app/customer/' + encodeURIComponent(r.customer);
			$body.append(
				'<tr>' +
				'<td class="ars-cust-cell">' +
					'<a class="ars-cust-name" href="' + link + '">' + esc(r.customer) + '</a>' +
					'<div class="ars-progress"><div class="ars-progress-fill" style="width:' + pct + '%"></div></div>' +
				'</td>' +
				'<td class="ars-c ars-muted">' + (r.invoices || 0) + '</td>' +
				'<td class="ars-r">' + money(total) + '</td>' +
				'<td class="ars-r ars-paid">' + money(paid) + '</td>' +
				'<td class="ars-r ars-out ' + (out > 0 ? '' : 'ars-zero') + '">' + money(out) + '</td>' +
				'<td class="ars-c"><span class="ars-pill ' + st.cls + '">' + st.label + '</span></td>' +
				'</tr>'
			);
		});
		$('#ars-empty').toggle(rows.length === 0);

		var ft = rows.reduce(function (a, r) {
			a.invoices += (r.invoices || 0); a.invoice_total += flt(r.invoice_total);
			a.paid += flt(r.paid); a.outstanding += flt(r.outstanding); return a;
		}, { invoices: 0, invoice_total: 0, paid: 0, outstanding: 0 });

		$('#ars-foot').html(rows.length ?
			('<tr class="ars-total"><td>TOTAL</td>' +
			 '<td class="ars-c">' + ft.invoices + '</td>' +
			 '<td class="ars-r">' + money(ft.invoice_total) + '</td>' +
			 '<td class="ars-r">' + money(ft.paid) + '</td>' +
			 '<td class="ars-r">' + money(ft.outstanding) + '</td><td></td></tr>') : '');

		update_kpis(ft.invoice_total, ft.paid, ft.outstanding, rows.length);
		$('#ars-count').text('Showing ' + rows.length + ' of ' + state.rows.length + ' customers');
	}

	// ---------- ledgers view ----------
	function render_ledgers() {
		var groups = (state.ledgers && state.ledgers.groups) || [];
		var q = (state.search || '').toLowerCase();
		if (q) groups = groups.filter(function (g) { return (g.customer || '').toLowerCase().indexOf(q) !== -1; });

		var $host = $('#ars-ledgers').empty();
		$('#ars-ledgers-empty').toggle(groups.length === 0);

		var tot = { invoice_total: 0, paid: 0, outstanding: 0 };

		groups.forEach(function (g) {
			var t = g.totals || {};
			tot.invoice_total += flt(t.invoice_total); tot.paid += flt(t.paid); tot.outstanding += flt(t.outstanding);

			var body = '';
			(g.invoices || []).forEach(function (inv) {
				var link = '/app/sales-invoice/' + encodeURIComponent(inv.name);
				body +=
					'<tr>' +
					'<td><a class="ars-inv-link" href="' + link + '">' + esc(inv.name) + '</a></td>' +
					ref_cell(inv.sales_order, 'sales-order') +
					'<td class="ars-muted">' + esc(inv.company) + '</td>' +
					'<td class="ars-c ars-muted">' + esc(inv.posting_date) + '</td>' +
					'<td class="ars-c ars-muted">' + esc(inv.due_date) + '</td>' +
					'<td class="ars-r">' + money(inv.invoice_total) + '</td>' +
					'<td class="ars-r ars-paid">' + money(inv.paid) + '</td>' +
					'<td class="ars-r ars-out ' + (flt(inv.outstanding) > 0 ? '' : 'ars-zero') + '">' + money(inv.outstanding) + '</td>' +
					'<td class="ars-c">' + invoice_pill(inv.status) + '</td>' +
					'</tr>';
			});

			$host.append(
				'<div class="ars-ledger">' +
					'<div class="ars-ledger-head">' +
						'<div class="ars-ledger-title">' + esc(g.customer) +
							'<span class="ars-ledger-count">' + g.count + ' invoice' + (g.count === 1 ? '' : 's') + '</span></div>' +
						'<div class="ars-ledger-out">Outstanding <b>' + money(t.outstanding) + '</b></div>' +
					'</div>' +
					'<div class="ars-scroll"><table class="ars-ltable">' +
						'<thead><tr>' +
							'<th>Invoice #</th><th>Sales Order</th><th>Company</th>' +
							'<th class="ars-c">Posting Date</th><th class="ars-c">Due Date</th>' +
							'<th class="ars-r">Invoice Total</th><th class="ars-r">Paid Amount</th>' +
							'<th class="ars-r">Outstanding</th><th class="ars-c">Status</th>' +
						'</tr></thead>' +
						'<tbody>' + body + '</tbody>' +
						'<tfoot><tr class="ars-ltotal">' +
							'<td colspan="5">TOTAL</td>' +
							'<td class="ars-r">' + money(t.invoice_total) + '</td>' +
							'<td class="ars-r">' + money(t.paid) + '</td>' +
							'<td class="ars-r ars-out">' + money(t.outstanding) + '</td><td></td>' +
						'</tr></tfoot>' +
					'</table></div>' +
				'</div>'
			);
		});

		update_kpis(tot.invoice_total, tot.paid, tot.outstanding, groups.length);
	}

	function update_kpis(invoice_total, paid, outstanding, customers) {
		var rate = invoice_total > 0 ? Math.round((paid / invoice_total) * 100) : 0;
		$('#ars-k-inv').text(money(invoice_total));
		$('#ars-k-paid').text(money(paid));
		$('#ars-k-out').text(money(outstanding));
		$('#ars-k-rate').text(rate + '%');
		$('#ars-k-cust').text(customers);
	}

	function render_active() {
		if (state.view === 'ledgers') render_ledgers();
		else render_summary();
	}

	// ---------- data loading ----------
	function set_loading(on) {
		$('#ars-table-card').toggleClass('ars-loading', on);
		$('#ars-ledgers').toggleClass('ars-loading', on);
		$('#ars-refresh-ic').toggleClass('ars-spin', on);
	}

	function load_summary(then) {
		set_loading(true);
		frappe.call({
			method: METHOD + '.get_ar_summary',
			args: { company: state.company, from_date: state.from_date, to_date: state.to_date },
			callback: function (r) {
				if (!r.message) return;
				state.rows = r.message.rows || [];
				state.prepared = r.message.prepared || '';
				$('#ars-prepared').text('Prepared ' + state.prepared + ' \u2014 Accounts Receivable');
				if (then) then();
			},
			always: function () { set_loading(false); }
		});
	}

	function load_ledgers(then) {
		set_loading(true);
		frappe.call({
			method: METHOD + '.get_ledgers',
			args: { company: state.company, from_date: state.from_date, to_date: state.to_date },
			callback: function (r) {
				if (r.message) state.ledgers = r.message;
				if (then) then();
			},
			always: function () { set_loading(false); }
		});
	}

	function reload() {
		if (state.view === 'ledgers') load_ledgers(render_ledgers);
		else load_summary(render_summary);
	}

	function switch_view(view) {
		state.view = view;
		$('#ars-seg .ars-seg-btn').removeClass('is-active')
			.filter('[data-view="' + view + '"]').addClass('is-active');
		$('#ars-view-summary').toggle(view === 'summary');
		$('#ars-view-ledgers').toggle(view === 'ledgers');
		$('.ars-summary-only').toggle(view === 'summary');

		if (view === 'ledgers') {
			if (state.ledgers) render_ledgers(); else load_ledgers(render_ledgers);
		} else {
			if (state.rows.length) render_summary(); else load_summary(render_summary);
		}
	}

	// ---------- events ----------
	$('#ars-seg').on('click', '.ars-seg-btn', function () { switch_view($(this).data('view')); });

	function server_filter_changed() { state.ledgers = null; state.rows = []; reload(); }
	$('#ars-company').on('change', function () { state.company = $(this).val(); server_filter_changed(); });
	$('#ars-from').on('change', function () { state.from_date = $(this).val(); server_filter_changed(); });
	$('#ars-to').on('change', function () { state.to_date = $(this).val(); server_filter_changed(); });
	$('#ars-refresh').on('click', server_filter_changed);

	$('#ars-search').on('input', function () { state.search = $(this).val(); render_active(); });
	$('#ars-status').on('change', function () { state.status = $(this).val(); render_summary(); });
	$('#ars-sort').on('change', function () { state.sort = $(this).val(); render_summary(); });

	$('#ars-clear').on('click', function () {
		state.search = ''; state.status = 'all'; state.sort = 'outstanding';
		state.company = ''; state.from_date = ''; state.to_date = ''; state.ledgers = null; state.rows = [];
		$('#ars-search').val(''); $('#ars-status').val('all'); $('#ars-sort').val('outstanding');
		$('#ars-company').val(''); $('#ars-from').val(''); $('#ars-to').val('');
		reload();
	});

	$('#ars-export').on('click', function () {
		open_url_post('/api/method/' + METHOD + '.export_ar_summary', {
			company: state.company || '', from_date: state.from_date || '', to_date: state.to_date || ''
		});
	});

	load_summary(render_summary);
};