frappe.pages['ar-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Accounts Receivable',
		single_column: true
	});

	wrapper.page = page;
	page._ard_result       = null;   // last data from backend
	page._ard_excl_motley  = false;  // Remove Motley toggle state

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
				<div class="ard-filter-actions">
					<button id="ard-apply-btn"        class="ard-btn-primary">Apply Filters</button>
					<button id="ard-export-btn"       class="ard-btn-secondary" style="display:none;">&#8595; Export Excel</button>
					<button id="ard-motley-btn"       class="ard-btn-danger"    style="display:none;">Remove Motley</button>
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

	// ── Load companies ────────────────────────────────────────────────────────
	frappe.call({
		method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.init_page",
		callback: function (r) {
			if (!r.message) return;
			let sel = page.main.find('#ard-company');
			let default_company = frappe.defaults.get_user_default("Company") || "";
			r.message.companies.forEach(function (c) {
				sel.append(`<option value="${c}" ${c === default_company ? 'selected' : ''}>${c}</option>`);
			});
			update_motley_btn_visibility(page);
		}
	});

	page.main.find('#ard-report-date').on('change', function () {
		page.main.find('#ard-report-date-display').text($(this).val());
	});

	// Show/hide Remove Motley button whenever company changes
	page.main.find('#ard-company').on('change', function () {
		update_motley_btn_visibility(page);
	});

	page.main.find('#ard-apply-btn').on('click', function () {
		page._ard_excl_motley = false;  // reset toggle on fresh load
		load_ar_data(page);
	});

	page.main.find('#ard-export-btn').on('click', function () {
		export_excel(page);
	});

	page.main.find('#ard-motley-btn').on('click', function () {
		page._ard_excl_motley = !page._ard_excl_motley;
		let btn = page.main.find('#ard-motley-btn');
		if (page._ard_excl_motley) {
			btn.text('Show Motley').addClass('ard-btn-active');
		} else {
			btn.text('Remove Motley').removeClass('ard-btn-active');
		}
		render_table(page);
	});
};

// ─── Visibility helpers ───────────────────────────────────────────────────────

function update_motley_btn_visibility(page) {
	let company = page.main.find('#ard-company').val() || "";
	let is_tsbc = company.toLowerCase().indexOf("tsbc ranch") !== -1;
	page.main.find('#ard-motley-btn').toggle(is_tsbc && !!page._ard_result);
}

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

	page.main.find('#ard-export-btn').hide();
	page.main.find('#ard-motley-btn').hide();

	frappe.call({
		method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.get_ar_data",
		args: {
			company:         company,
			report_date:     date,
			customer:        customer || null,
			ageing_based_on: ageing_on,
			range_str:       "30, 60, 90, 120",
		},
		callback: function (r) {
			if (r.message) {
				page._ard_result = r.message;
				render_dashboard(page, r.message);
				page.main.find('#ard-export-btn').show();
				update_motley_btn_visibility(page);
			} else {
				area.html(`<div class="ard-empty-state"><p>No data returned.</p></div>`);
			}
		}
	});
}

// ─── Rendering ────────────────────────────────────────────────────────────────

function render_dashboard(page, result) {
	let { rows, ranges, totals } = result;
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

	// ── Summary Cards (always use full totals) ────────────────────────────────
	let range_totals_html = ranges.map(function (r, idx) {
		let cls = range_status_class(idx);
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
		let cls = range_status_class(idx);
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
					return `<span class="ard-legend-dot ${range_status_class(idx)}"></span><span class="ard-legend-text">${r.label} Days</span>`;
				}).join("")}
			</div>
		</div>
	`;

	html += `<div id="ard-table-section"></div>`;

	page.main.find('#ard-data-area').html(html);
	render_table(page);
}

// Re-renders only the table section (called on toggle + initial render)
function render_table(page) {
	if (!page._ard_result) return;
	let { rows, ranges, totals, company } = page._ard_result;

	// Filter cleared rows
	let display_rows = rows.filter(function (r) { return r.outstanding > 0; });

	// Filter Motley Terpz if toggle is on
	if (page._ard_excl_motley) {
		display_rows = display_rows.filter(function (r) {
			return (r.customer_name || r.party || "").toLowerCase().indexOf("motley") === -1;
		});
	}

	let section = page.main.find('#ard-table-section');

	if (display_rows.length === 0) {
		section.html(`
			<div class="ard-empty-state">
				<div class="ard-empty-icon">&#10003;</div>
				<p>No outstanding receivables found for this selection.</p>
			</div>
		`);
		return;
	}

	// Group by customer, sorted alphabetically
	let customer_order = [];
	let customer_groups = {};
	display_rows.forEach(function (row) {
		let key = row.party;
		if (!customer_groups[key]) {
			customer_groups[key] = { name: row.customer_name || row.party, party: row.party, rows: [] };
			customer_order.push(key);
		}
		customer_groups[key].rows.push(row);
	});
	customer_order.sort(function (a, b) {
		return (customer_groups[a].name || "").localeCompare(customer_groups[b].name || "");
	});

	// Recalculate totals for displayed rows
	let view_totals = { invoiced: 0, paid: 0, outstanding: 0 };
	ranges.forEach(function (r) { view_totals[r.key] = 0; });
	display_rows.forEach(function (row) {
		view_totals.invoiced    += row.invoiced    || 0;
		view_totals.paid        += row.paid        || 0;
		view_totals.outstanding += row.outstanding || 0;
		ranges.forEach(function (r) { view_totals[r.key] += row[r.key] || 0; });
	});

	let range_headers = ranges.map(function (r, idx) {
		return `<th class="ard-th-range ${range_status_class(idx)}">${r.label}<br><small>Days</small></th>`;
	}).join("");

	let html = `
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

	let total_invoices = 0;
	customer_order.forEach(function (party) {
		let group = customer_groups[party];
		total_invoices += group.rows.length;

		let sub = { invoiced: 0, paid: 0, outstanding: 0 };
		ranges.forEach(function (r) { sub[r.key] = 0; });
		group.rows.forEach(function (row) {
			sub.invoiced    += row.invoiced    || 0;
			sub.paid        += row.paid        || 0;
			sub.outstanding += row.outstanding || 0;
			ranges.forEach(function (r) { sub[r.key] += row[r.key] || 0; });
		});

		let sub_range_cells = ranges.map(function (r, idx) {
			let val = sub[r.key];
			let cls = `ard-range-cell ${range_status_class(idx)}`;
			return `<td class="${cls} ard-total-cell">${val > 0 ? fmt_cur(val) : "—"}</td>`;
		}).join("");

		html += `
			<tr class="ard-customer-group-row">
				<td class="ard-td-sticky">
					<div class="ard-customer-group-name">${esc(group.name)}</div>
					${group.name !== group.party ? `<div class="ard-customer-group-id">${esc(group.party)}</div>` : ""}
				</td>
				<td colspan="4" style="color:var(--ard-muted);font-size:12px;">${group.rows.length} invoice(s)</td>
				<td class="ard-num ard-total-cell">${fmt_cur(sub.invoiced)}</td>
				<td class="ard-num ard-total-cell">${fmt_cur(sub.paid)}</td>
				<td class="ard-num ard-total-cell ard-outstanding">${fmt_cur(sub.outstanding)}</td>
				${sub_range_cells}
				<td></td>
			</tr>
		`;

		group.rows.forEach(function (row) {
			let status = get_row_status(row, ranges);
			let range_cells = ranges.map(function (r, idx) {
				let val = row[r.key] || 0;
				let cls = val > 0 ? `ard-range-cell ${range_status_class(idx)}` : "ard-range-cell ard-range-zero";
				return `<td class="${cls}">${val > 0 ? fmt_cur(val) : "—"}</td>`;
			}).join("");

			html += `
				<tr>
					<td class="ard-td-sticky" style="padding-left:24px;">
						<a href="/app/sales-invoice/${esc(row.voucher_no)}" target="_blank" class="ard-link">${esc(row.voucher_no)}</a>
					</td>
					<td></td>
					<td class="ard-type">${esc(row.voucher_type)}</td>
					<td class="ard-date">${fmt_date(row.posting_date)}</td>
					<td class="ard-date">${fmt_date(row.due_date)}</td>
					<td class="ard-num">${fmt_cur(row.invoiced)}</td>
					<td class="ard-num">${fmt_cur(row.paid)}</td>
					<td class="ard-num ard-outstanding">${fmt_cur(row.outstanding)}</td>
					${range_cells}
					<td style="text-align:center;"><span class="ard-badge ${status.cls}">${status.label}</span></td>
				</tr>
			`;
		});
	});

	let range_total_cells = ranges.map(function (r, idx) {
		let cls = `ard-range-cell ${range_status_class(idx)}`;
		return `<td class="${cls} ard-total-cell">${fmt_cur(view_totals[r.key])}</td>`;
	}).join("");

	html += `
				</tbody>
				<tfoot>
					<tr class="ard-totals-row">
						<td class="ard-td-sticky ard-total-cell">${esc(company)}</td>
						<td class="ard-total-cell" colspan="4">${total_invoices} invoice(s) &bull; ${customer_order.length} customer(s)</td>
						<td class="ard-num ard-total-cell">${fmt_cur(view_totals.invoiced)}</td>
						<td class="ard-num ard-total-cell">${fmt_cur(view_totals.paid)}</td>
						<td class="ard-num ard-total-cell ard-outstanding">${fmt_cur(view_totals.outstanding)}</td>
						${range_total_cells}
						<td></td>
					</tr>
				</tfoot>
			</table>
		</div>
	`;

	section.html(html);
}

// ─── Excel Export ─────────────────────────────────────────────────────────────

function export_excel(page) {
	if (!page._ard_result) return;
	let { rows, ranges, company } = page._ard_result;

	let display_rows = rows.filter(function (r) { return r.outstanding > 0; });
	if (page._ard_excl_motley) {
		display_rows = display_rows.filter(function (r) {
			return (r.customer_name || r.party || "").toLowerCase().indexOf("motley") === -1;
		});
	}

	// Sort by customer name then posting date
	display_rows = display_rows.slice().sort(function (a, b) {
		let na = (a.customer_name || a.party || "").toLowerCase();
		let nb = (b.customer_name || b.party || "").toLowerCase();
		if (na < nb) return -1;
		if (na > nb) return 1;
		return (a.posting_date || "").localeCompare(b.posting_date || "");
	});

	// Build headers
	let range_labels = ranges.map(function (r) { return r.label + " Days"; });
	let headers = ["Customer", "Party ID", "Invoice No.", "Type", "Posting Date", "Due Date",
		"Invoiced", "Paid", "Outstanding"].concat(range_labels).concat(["Status"]);

	// Build data rows
	let csv_rows = [headers];
	display_rows.forEach(function (row) {
		let status = get_row_status(row, ranges);
		let range_vals = ranges.map(function (r) { return row[r.key] || 0; });
		csv_rows.push([
			row.customer_name || row.party,
			row.party,
			row.voucher_no,
			row.voucher_type,
			row.posting_date || "",
			row.due_date     || "",
			row.invoiced     || 0,
			row.paid         || 0,
			row.outstanding  || 0,
		].concat(range_vals).concat([status.label]));
	});

	// Encode as CSV
	let csv = csv_rows.map(function (cols) {
		return cols.map(function (v) {
			let s = String(v == null ? "" : v);
			if (s.indexOf(",") !== -1 || s.indexOf('"') !== -1 || s.indexOf("\n") !== -1) {
				s = '"' + s.replace(/"/g, '""') + '"';
			}
			return s;
		}).join(",");
	}).join("\r\n");

	let date_str = page.main.find('#ard-report-date').val() || frappe.datetime.get_today();
	let filename = "AR_" + company.replace(/\s+/g, "_") + "_" + date_str + ".csv";

	let blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
	let url  = URL.createObjectURL(blob);
	let a    = document.createElement("a");
	a.href     = url;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	URL.revokeObjectURL(url);
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function get_row_status(row, ranges) {
	let highest = -1;
	ranges.forEach(function (r, idx) {
		if ((row[r.key] || 0) > 0) highest = idx;
	});

	if (row.outstanding <= 0)  return { label: "Clear",         cls: "badge-clear" };
	if (highest < 0)           return { label: "Unclassified",  cls: "badge-clear" };
	if (highest === 0)         return { label: "Current",       cls: "badge-current" };
	if (highest === 1)         return { label: "30+ Days",      cls: "badge-30" };
	if (highest === 2)         return { label: "60+ Days",      cls: "badge-60" };
	return                            { label: "90+ Days",      cls: "badge-90" };
}

function range_status_class(idx) {
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
