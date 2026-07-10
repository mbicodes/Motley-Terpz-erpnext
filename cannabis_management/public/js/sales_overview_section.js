// Shared Sales Overview component.
// Rendered standalone on the /app/sales-overview page and embedded in the
// Matt Sales Target dashboard. Load via:
//   frappe.require([
//     '/assets/cannabis_management/css/sales_overview_section.css',
//     '/assets/cannabis_management/js/sales_overview_section.js'
//   ], () => cannabis_management.sales_overview.render(container, opts));

frappe.provide('cannabis_management.sales_overview');

cannabis_management.sales_overview.render = function (container, opts) {
	opts = opts || {};
	var $c = $(container);

	var state = {
		salesperson: 'all',
		salespersons: [],
		company: '',
		from_date: '',
		to_date: '',
		active_tab: 'invoices',
		result: null
	};

	var CURRENCY = frappe.defaults.get_default('currency') || 'USD';

	function money(v) {
		return format_currency(v || 0, CURRENCY);
	}

	var header_left = opts.show_title === false
		? `<p class="svo-subtitle" id="svo-subtitle">All sales &mdash; invoices, orders, delivery notes &amp; payments received (excl. intercompany)</p>`
		: `<h2 class="svo-title">Sales Overview</h2>
		   <p class="svo-subtitle" id="svo-subtitle">All sales &mdash; invoices, orders, delivery notes &amp; payments received (excl. intercompany)</p>`;

	$c.html(`
		<div class="svo-container">
			<div class="svo-header">
				<div class="svo-header-left">${header_left}</div>
				<div class="svo-sp-toggle" id="svo-sp-toggle">
					<button class="svo-sp-btn svo-sp-active" data-sp="all">All</button>
				</div>
			</div>

			<div class="svo-filter-bar">
				<div class="svo-filter-group">
					<label class="svo-label">Company</label>
					<select id="svo-company" class="svo-select">
						<option value="">All Companies</option>
					</select>
				</div>
				<div class="svo-filter-group">
					<label class="svo-label">Period</label>
					<select id="svo-preset" class="svo-select">
						<option value="this_month">This Month</option>
						<option value="last_30">Last 30 Days</option>
						<option value="this_quarter">This Quarter</option>
						<option value="ytd" selected>Year to Date</option>
						<option value="all">All Time</option>
						<option value="custom">Custom</option>
					</select>
				</div>
				<div class="svo-filter-group">
					<label class="svo-label">From</label>
					<input type="date" id="svo-from" class="svo-input" />
				</div>
				<div class="svo-filter-group">
					<label class="svo-label">To</label>
					<input type="date" id="svo-to" class="svo-input" />
				</div>
				<div class="svo-filter-actions">
					<button id="svo-refresh" class="svo-btn-secondary">&#8635; Refresh</button>
				</div>
			</div>

			<div id="svo-data-area">
				<div class="svo-loading">
					<div class="svo-spinner"></div>
					<p>Loading sales overview&hellip;</p>
				</div>
			</div>
		</div>
	`);

	// ── Date presets ──────────────────────────────────────────────────────
	function apply_preset(preset) {
		var today = frappe.datetime.get_today();
		var d = frappe.datetime.str_to_obj(today);
		var from = '', to = today;
		if (preset === 'this_month') {
			from = frappe.datetime.month_start();
		} else if (preset === 'last_30') {
			from = frappe.datetime.add_days(today, -30);
		} else if (preset === 'this_quarter') {
			var qm = Math.floor(d.getMonth() / 3) * 3;
			from = frappe.datetime.obj_to_str(new Date(d.getFullYear(), qm, 1));
		} else if (preset === 'ytd') {
			from = frappe.datetime.obj_to_str(new Date(d.getFullYear(), 0, 1));
		} else if (preset === 'all') {
			from = '';
			to = '';
		} else {
			return; // custom: keep whatever is typed
		}
		state.from_date = from;
		state.to_date = to;
		$c.find('#svo-from').val(from);
		$c.find('#svo-to').val(to);
	}

	// ── Data loading ──────────────────────────────────────────────────────
	function load_data() {
		$c.find('#svo-data-area').html(`
			<div class="svo-loading"><div class="svo-spinner"></div><p>Loading sales overview&hellip;</p></div>
		`);
		frappe.call({
			method: 'cannabis_management.cannabis_management.page.sales_overview.sales_overview.get_dashboard_data',
			args: {
				salesperson: state.salesperson,
				from_date: state.from_date || null,
				to_date: state.to_date || null,
				company: state.company || null
			},
			callback: function (r) {
				if (!r.message) return;
				state.result = r.message;
				render_result();
			},
			error: function () {
				$c.find('#svo-data-area').html(
					'<div class="svo-empty">Failed to load data. Please try again.</div>');
			}
		});
	}

	// ── Rendering ─────────────────────────────────────────────────────────
	function render_result() {
		var res = state.result;
		var k = res.kpis;

		var who = state.salesperson === 'all'
			? 'All sales'
			: res.salesperson + "'s sales";
		$c.find('#svo-subtitle').text(
			who + ' — invoices, orders, delivery notes & payments received (excl. intercompany)');

		$c.find('#svo-data-area').html(`
			<div class="svo-kpi-row">
				<div class="svo-kpi-card">
					<div class="svo-kpi-label">Invoiced</div>
					<div class="svo-kpi-value">${money(k.invoices.total)}</div>
					<div class="svo-kpi-sub">${k.invoices.count} invoices &middot; ${money(k.invoices.outstanding)} outstanding</div>
				</div>
				<div class="svo-kpi-card">
					<div class="svo-kpi-label">Sales Orders</div>
					<div class="svo-kpi-value">${money(k.orders.total)}</div>
					<div class="svo-kpi-sub">${k.orders.count} orders</div>
				</div>
				<div class="svo-kpi-card">
					<div class="svo-kpi-label">Delivery Notes</div>
					<div class="svo-kpi-value">${money(k.delivery_notes.total)}</div>
					<div class="svo-kpi-sub">${k.delivery_notes.count} delivery notes</div>
				</div>
				<div class="svo-kpi-card svo-kpi-payments">
					<div class="svo-kpi-label">Payments Received</div>
					<div class="svo-kpi-value">${money(k.payments.total)}</div>
					<div class="svo-kpi-sub">
						<span class="svo-tag svo-tag-cash">Cash ${money(k.payments.cash)} (${k.payments.cash_count})</span>
						<span class="svo-tag svo-tag-bank">Bank ${money(k.payments.bank)} (${k.payments.bank_count})</span>
					</div>
				</div>
			</div>

			<div class="svo-charts-row">
				<div class="svo-chart-card svo-chart-wide">
					<div class="svo-chart-title">Monthly Trend</div>
					<div class="svo-trend-chart"></div>
				</div>
				<div class="svo-chart-card">
					<div class="svo-chart-title">Payments: Cash vs Bank</div>
					<div class="svo-split-chart"></div>
				</div>
			</div>

			<div class="svo-tabs" id="svo-tabs">
				<button class="svo-tab" data-tab="invoices">Invoices (${res.list_totals.invoices})</button>
				<button class="svo-tab" data-tab="orders">Orders (${res.list_totals.orders})</button>
				<button class="svo-tab" data-tab="delivery_notes">Delivery Notes (${res.list_totals.delivery_notes})</button>
				<button class="svo-tab" data-tab="payments">Payments (${res.list_totals.payments})</button>
			</div>
			<div id="svo-list-area"></div>
		`);

		render_charts();
		set_tab(state.active_tab);

		$c.find('#svo-tabs .svo-tab').on('click', function () {
			set_tab($(this).data('tab'));
		});
	}

	function render_charts() {
		var res = state.result;
		if (typeof frappe.Chart === 'undefined') return;

		var t = res.trend;
		var trend_el = $c.find('.svo-trend-chart')[0];
		if (t.labels.length) {
			new frappe.Chart(trend_el, {
				type: 'bar',
				height: 260,
				colors: ['#7c3aed', '#f59e0b', '#10b981'],
				data: {
					labels: t.labels,
					datasets: [
						{ name: 'Invoiced', values: t.invoiced },
						{ name: 'Ordered', values: t.ordered },
						{ name: 'Received', values: t.received }
					]
				},
				axisOptions: { xIsSeries: 0 },
				tooltipOptions: { formatTooltipY: function (v) { return money(v); } }
			});
		} else {
			$(trend_el).html('<div class="svo-empty">No data in this period</div>');
		}

		var p = res.kpis.payments;
		var split_el = $c.find('.svo-split-chart')[0];
		if (p.total > 0) {
			new frappe.Chart(split_el, {
				type: 'donut',
				height: 260,
				colors: ['#10b981', '#3b82f6'],
				data: {
					labels: ['Cash', 'Bank'],
					datasets: [{ values: [Math.round(p.cash * 100) / 100, Math.round(p.bank * 100) / 100] }]
				}
			});
		} else {
			$(split_el).html('<div class="svo-empty">No payments in this period</div>');
		}
	}

	function doc_link(doctype, name) {
		var route = '/app/' + frappe.router.slug(doctype) + '/' + encodeURIComponent(name);
		return `<a href="${route}">${name}</a>`;
	}

	function status_pill(status) {
		return `<span class="svo-pill">${frappe.utils.escape_html(status || '')}</span>`;
	}

	var TABS = {
		invoices: {
			columns: ['Invoice', 'Date', 'Customer', 'Company', 'Grand Total', 'Outstanding', 'Status'],
			row: function (r) {
				return [
					doc_link('Sales Invoice', r.name),
					frappe.datetime.str_to_user(r.posting_date),
					frappe.utils.escape_html(r.customer_name || r.customer || ''),
					frappe.utils.escape_html(r.company || ''),
					money(r.grand_total),
					money(r.outstanding_amount),
					status_pill(r.status)
				];
			}
		},
		orders: {
			columns: ['Order', 'Date', 'Customer', 'Company', 'Grand Total', '% Billed', 'Status'],
			row: function (r) {
				return [
					doc_link('Sales Order', r.name),
					frappe.datetime.str_to_user(r.posting_date),
					frappe.utils.escape_html(r.customer_name || r.customer || ''),
					frappe.utils.escape_html(r.company || ''),
					money(r.grand_total),
					flt(r.per_billed).toFixed(0) + '%',
					status_pill(r.status)
				];
			}
		},
		delivery_notes: {
			columns: ['Delivery Note', 'Date', 'Customer', 'Company', 'Grand Total', 'Status'],
			row: function (r) {
				return [
					doc_link('Delivery Note', r.name),
					frappe.datetime.str_to_user(r.posting_date),
					frappe.utils.escape_html(r.customer_name || r.customer || ''),
					frappe.utils.escape_html(r.company || ''),
					money(r.grand_total),
					status_pill(r.status)
				];
			}
		},
		payments: {
			columns: ['Payment', 'Date', 'Customer', 'Company', 'Amount', 'Received In', 'Account'],
			row: function (r) {
				var tag_cls = r.receipt_type === 'Cash' ? 'svo-tag-cash' : 'svo-tag-bank';
				return [
					doc_link('Payment Entry', r.name),
					frappe.datetime.str_to_user(r.posting_date),
					frappe.utils.escape_html(r.party_name || r.party || ''),
					frappe.utils.escape_html(r.company || ''),
					money(r.paid_amount),
					`<span class="svo-tag ${tag_cls}">${r.receipt_type}</span>`,
					frappe.utils.escape_html(r.paid_to || '')
				];
			}
		}
	};

	function set_tab(tab) {
		state.active_tab = tab;
		$c.find('#svo-tabs .svo-tab').removeClass('svo-tab-active');
		$c.find(`#svo-tabs .svo-tab[data-tab="${tab}"]`).addClass('svo-tab-active');

		var cfg = TABS[tab];
		var rows = state.result.lists[tab] || [];
		var total = state.result.list_totals[tab];

		if (!rows.length) {
			$c.find('#svo-list-area').html('<div class="svo-empty">No records in this period</div>');
			return;
		}

		var thead = cfg.columns.map(function (c) { return `<th>${c}</th>`; }).join('');
		var tbody = rows.map(function (r) {
			return '<tr>' + cfg.row(r).map(function (c) { return `<td>${c}</td>`; }).join('') + '</tr>';
		}).join('');
		var note = total > rows.length
			? `<div class="svo-list-note">Showing latest ${rows.length} of ${total} records</div>`
			: '';

		$c.find('#svo-list-area').html(`
			<div class="svo-table-wrap">
				<table class="svo-table">
					<thead><tr>${thead}</tr></thead>
					<tbody>${tbody}</tbody>
				</table>
			</div>
			${note}
		`);
	}

	// ── Init: salesperson buttons + companies ─────────────────────────────
	frappe.call({
		method: 'cannabis_management.cannabis_management.page.sales_overview.sales_overview.init_page',
		callback: function (r) {
			if (!r.message) return;
			state.salespersons = r.message.salespersons || [];

			var toggle = $c.find('#svo-sp-toggle');
			state.salespersons.forEach(function (sp) {
				toggle.append(
					`<button class="svo-sp-btn" data-sp="${frappe.utils.escape_html(sp.key)}"
						title="${frappe.utils.escape_html(sp.full_name)}">${frappe.utils.escape_html(sp.label)}</button>`
				);
			});
			toggle.find('.svo-sp-btn').on('click', function () {
				toggle.find('.svo-sp-btn').removeClass('svo-sp-active');
				$(this).addClass('svo-sp-active');
				state.salesperson = $(this).data('sp');
				load_data();
			});

			var sel = $c.find('#svo-company');
			(r.message.companies || []).forEach(function (c) {
				sel.append(`<option value="${frappe.utils.escape_html(c)}">${frappe.utils.escape_html(c)}</option>`);
			});

			apply_preset('ytd');
			load_data();
		}
	});

	// ── Filter events ─────────────────────────────────────────────────────
	$c.find('#svo-company').on('change', function () {
		state.company = $(this).val();
		load_data();
	});
	$c.find('#svo-preset').on('change', function () {
		apply_preset($(this).val());
		load_data();
	});
	$c.find('#svo-from, #svo-to').on('change', function () {
		$c.find('#svo-preset').val('custom');
		state.from_date = $c.find('#svo-from').val();
		state.to_date = $c.find('#svo-to').val();
		load_data();
	});
	$c.find('#svo-refresh').on('click', load_data);
};
