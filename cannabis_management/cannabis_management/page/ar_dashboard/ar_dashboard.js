frappe.pages['ar-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Accounts Receivable',
		single_column: true
	});

	wrapper.page = page;

	let today = frappe.datetime.get_today();

	page.main.html(`
		<div class="ard-container">
			<div class="ard-header">
				<div class="ard-header-left">
					<h2 class="ard-title">Accounts Receivable</h2>
					<p class="ard-subtitle">Outstanding invoices with aging analysis</p>
				</div>
				<div class="ard-header-right">
					<span class="ard-as-of-label">As of</span>
					<span id="ard-report-date-display" class="ard-date-badge">${today}</span>
				</div>
			</div>

			<div class="ard-filter-bar">
				<div class="ard-filter-group">
					<label class="ard-label">Company</label>
					<select id="ard-company" class="ard-select"></select>
				</div>
				<div class="ard-filter-group">
					<label class="ard-label">Customer</label>
					<input type="text" id="ard-customer" class="ard-input" placeholder="All customers" />
				</div>
				<div class="ard-filter-group">
					<label class="ard-label">Report Date</label>
					<input type="date" id="ard-report-date" class="ard-input" value="${today}" />
				</div>
				<div class="ard-filter-group">
					<label class="ard-label">Ageing Based On</label>
					<select id="ard-ageing-on" class="ard-select">
						<option value="Due Date">Due Date</option>
						<option value="Posting Date">Posting Date</option>
					</select>
				</div>
				<div class="ard-filter-group ard-filter-action">
					<button id="ard-apply-btn" class="ard-btn-primary">Apply Filters</button>
				</div>
			</div>

			<div id="ard-data-area">
				<div class="ard-empty-state">
					<div class="ard-empty-icon">&#9780;</div>
					<p>Select a company and click <strong>Apply Filters</strong> to load data.</p>
				</div>
			</div>
		</div>
	`);

	// Load companies
	frappe.call({
		method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.init_page",
		callback: function (r) {
			if (!r.message) return;
			let sel = page.main.find('#ard-company');
			let default_company = frappe.defaults.get_user_default("Company") || "";
			r.message.companies.forEach(function (c) {
				sel.append(`<option value="${c}" ${c === default_company ? 'selected' : ''}>${c}</option>`);
			});
		}
	});

	page.main.find('#ard-report-date').on('change', function () {
		page.main.find('#ard-report-date-display').text($(this).val());
	});

	page.main.find('#ard-apply-btn').on('click', function () {
		load_ar_data(page);
	});
};

// ─── Data Loading ─────────────────────────────────────────────────────────────

function load_ar_data(page) {
	let company   = page.main.find('#ard-company').val();
	let customer  = page.main.find('#ard-customer').val().trim();
	let date      = page.main.find('#ard-report-date').val();
	let ageing_on = page.main.find('#ard-ageing-on').val();

	if (!company) {
		frappe.msgprint("Please select a Company.");
		return;
	}

	let area = page.main.find('#ard-data-area');
	area.html(`
		<div class="ard-loading">
			<div class="ard-spinner"></div>
			<p>Loading receivables&hellip;</p>
		</div>
	`);

	frappe.call({
		method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.get_ar_data",
		args: {
			company:        company,
			report_date:    date,
			customer:       customer || null,
			ageing_based_on: ageing_on,
			range_str:      "30, 60, 90, 120",
		},
		callback: function (r) {
			if (r.message) {
				render_dashboard(page, r.message);
			} else {
				area.html(`<div class="ard-empty-state"><p>No data returned.</p></div>`);
			}
		}
	});
}

// ─── Rendering ────────────────────────────────────────────────────────────────

function render_dashboard(page, result) {
	let { rows, ranges, totals, company, report_date } = result;
	let area = page.main.find('#ard-data-area');

	if (!rows || rows.length === 0) {
		area.html(`
			<div class="ard-empty-state">
				<div class="ard-empty-icon">&#10003;</div>
				<p>No outstanding receivables found for this selection.</p>
			</div>
		`);
		return;
	}

	let html = "";

	// ── Summary Cards ─────────────────────────────────────────────────────────
	let range_totals_html = ranges.map(function (r, idx) {
		let cls = range_status_class(idx, ranges.length);
		return `
			<div class="ard-card ard-card-range ${cls}">
				<div class="ard-card-label">${r.label} Days</div>
				<div class="ard-card-value">${fmt_cur(totals[r.key])}</div>
			</div>
		`;
	}).join("");

	html += `
		<div class="ard-summary-row">
			<div class="ard-card ard-card-outstanding">
				<div class="ard-card-label">Total Outstanding</div>
				<div class="ard-card-value">${fmt_cur(totals.outstanding)}</div>
			</div>
			<div class="ard-card ard-card-invoiced">
				<div class="ard-card-label">Total Invoiced</div>
				<div class="ard-card-value">${fmt_cur(totals.invoiced)}</div>
			</div>
			<div class="ard-card ard-card-paid">
				<div class="ard-card-label">Total Paid</div>
				<div class="ard-card-value">${fmt_cur(totals.paid)}</div>
			</div>
			${range_totals_html}
		</div>
	`;

	// ── Aging Distribution Bar ────────────────────────────────────────────────
	let total_out = totals.outstanding || 1;
	let bar_segments = ranges.map(function (r, idx) {
		let pct = ((totals[r.key] / total_out) * 100).toFixed(1);
		if (parseFloat(pct) < 0.5) return "";
		let cls = range_status_class(idx, ranges.length);
		return `<div class="ard-bar-seg ${cls}" style="width:${pct}%" title="${r.label} Days: ${fmt_cur(totals[r.key])} (${pct}%)">
					<span class="ard-bar-label">${pct}%</span>
				</div>`;
	}).join("");

	html += `
		<div class="ard-aging-bar-wrap">
			<div class="ard-aging-bar-title">Aging Distribution</div>
			<div class="ard-aging-bar">${bar_segments || '<div class="ard-bar-seg bar-current" style="width:100%"></div>'}</div>
			<div class="ard-aging-bar-legend">
				${ranges.map(function (r, idx) {
					return `<span class="ard-legend-dot ${range_status_class(idx, ranges.length)}"></span><span class="ard-legend-text">${r.label} Days</span>`;
				}).join("")}
			</div>
		</div>
	`;

	// ── Main Table ────────────────────────────────────────────────────────────
	let range_headers = ranges.map(function (r, idx) {
		return `<th class="ard-th-range ${range_status_class(idx, ranges.length)}">${r.label}<br><small>Days</small></th>`;
	}).join("");

	html += `
		<div class="ard-table-wrap">
			<table class="ard-table">
				<thead>
					<tr>
						<th class="ard-th-sticky">Customer</th>
						<th>Invoice No.</th>
						<th>Type</th>
						<th>Posting Date</th>
						<th>Due Date</th>
						<th class="ard-th-num">Invoiced</th>
						<th class="ard-th-num">Paid</th>
						<th class="ard-th-num">Outstanding</th>
						${range_headers}
						<th class="ard-th-status">Status</th>
					</tr>
				</thead>
				<tbody>
	`;

	rows.forEach(function (row) {
		let status = get_row_status(row, ranges);
		let range_cells = ranges.map(function (r, idx) {
			let val = row[r.key] || 0;
			let cls = val > 0 ? `ard-range-cell ${range_status_class(idx, ranges.length)}` : "ard-range-cell ard-range-zero";
			return `<td class="${cls}">${val > 0 ? fmt_cur(val) : "—"}</td>`;
		}).join("");

		html += `
			<tr>
				<td class="ard-td-sticky">
					<div class="ard-customer-name">${esc(row.customer_name || row.party)}</div>
					<div class="ard-customer-id">${row.customer_name ? esc(row.party) : ""}</div>
				</td>
				<td><a href="/app/sales-invoice/${esc(row.voucher_no)}" target="_blank" class="ard-link">${esc(row.voucher_no)}</a></td>
				<td class="ard-type">${esc(row.voucher_type)}</td>
				<td class="ard-date">${fmt_date(row.posting_date)}</td>
				<td class="ard-date">${fmt_date(row.due_date)}</td>
				<td class="ard-num">${fmt_cur(row.invoiced)}</td>
				<td class="ard-num">${fmt_cur(row.paid)}</td>
				<td class="ard-num ard-outstanding">${fmt_cur(row.outstanding)}</td>
				${range_cells}
				<td><span class="ard-badge ${status.cls}">${status.label}</span></td>
			</tr>
		`;
	});

	// Totals row
	let range_total_cells = ranges.map(function (r, idx) {
		let cls = `ard-range-cell ${range_status_class(idx, ranges.length)}`;
		return `<td class="${cls} ard-total-cell">${fmt_cur(totals[r.key])}</td>`;
	}).join("");

	html += `
				</tbody>
				<tfoot>
					<tr class="ard-totals-row">
						<td class="ard-td-sticky ard-total-cell" colspan="2">${esc(company)} — ${rows.length} invoice(s)</td>
						<td colspan="3"></td>
						<td class="ard-num ard-total-cell">${fmt_cur(totals.invoiced)}</td>
						<td class="ard-num ard-total-cell">${fmt_cur(totals.paid)}</td>
						<td class="ard-num ard-total-cell ard-outstanding">${fmt_cur(totals.outstanding)}</td>
						${range_total_cells}
						<td></td>
					</tr>
				</tfoot>
			</table>
		</div>
	`;

	area.html(html);
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function get_row_status(row, ranges) {
	// Find the highest (oldest) bucket with any amount
	let highest = -1;
	ranges.forEach(function (r, idx) {
		if ((row[r.key] || 0) > 0) highest = idx;
	});

	if (row.outstanding <= 0)  return { label: "Clear",      cls: "badge-clear" };
	if (highest < 0)           return { label: "Unclassified", cls: "badge-clear" };
	if (highest === 0)         return { label: "Current",    cls: "badge-current" };
	if (highest === 1)         return { label: "30+ Days",   cls: "badge-30" };
	if (highest === 2)         return { label: "60+ Days",   cls: "badge-60" };
	return                            { label: "90+ Days",   cls: "badge-90" };
}

// Maps a range index to a CSS modifier class
function range_status_class(idx, total) {
	if (idx === 0) return "bar-current";
	if (idx === 1) return "bar-30";
	if (idx === 2) return "bar-60";
	return "bar-90";
}

function fmt_cur(val) {
	return "$" + (val || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmt_date(val) {
	if (!val) return "—";
	let d = new Date(val);
	if (isNaN(d)) return val;
	return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

function esc(val) {
	if (!val) return "";
	return $("<div>").text(val).html();
}
