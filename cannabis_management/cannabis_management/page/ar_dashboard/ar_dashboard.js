var LEGACY_CUTOFF = "2026-05-15";
var NEW_AR_START  = "2026-05-16";

frappe.pages['ar-dashboard'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Accounts Receivable',
        single_column: true
    });

    wrapper.page = page;
    page._ard_result      = null;
    page._ard_excl_motley = false;
    page._ard_can_edit    = false;
    page._ard_ar_mode     = "legacy"; // "legacy" (≤ May 15 2026) or "new" (≥ May 16 2026)

    page.main.html(`
		<div class="ard-container">
			<div class="ard-header">
				<div class="ard-header-left">
					<h2 class="ard-title">Accounts Receivable</h2>
					<p class="ard-subtitle" id="ard-subtitle">Legacy AR &mdash; invoices up to May 15, 2026</p>
				</div>
				<div class="ard-header-right">
					<span class="ard-as-of-label">As of</span>
					<span id="ard-report-date-display" class="ard-date-badge">${LEGACY_CUTOFF}</span>
				</div>
			</div>

			<div class="ard-filter-bar">
				<div class="ard-filter-group">
					<label class="ard-label">AR Mode</label>
					<div class="ard-mode-toggle">
						<button id="ard-legacy-btn" class="ard-mode-btn ard-mode-active">Legacy AR</button>
						<button id="ard-new-btn"    class="ard-mode-btn">New AR</button>
					</div>
				</div>
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
					<input type="date" id="ard-report-date" class="ard-input"
						value="${LEGACY_CUTOFF}" max="${LEGACY_CUTOFF}" />
				</div>
				<div class="ard-filter-group">
					<label class="ard-label">Ageing Based On</label>
					<select id="ard-ageing-on" class="ard-select">
						<option value="Due Date">Due Date</option>
						<option value="Posting Date">Posting Date</option>
					</select>
				</div>
				<div class="ard-filter-group">
					<label class="ard-label">Status</label>
					<select id="ard-recon-filter" class="ard-select">
						<option value="">All</option>
						<option value="Reconciled">Reconciled</option>
						<option value="Unreconciled">Unreconciled</option>
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
            page._ard_can_edit = !!r.message.can_edit_recon;
            update_motley_btn_visibility(page);
        }
    });

    page.main.find('#ard-report-date').on('change', function () {
        page.main.find('#ard-report-date-display').text($(this).val());
    });

    page.main.find('#ard-recon-filter').on('change', function () {
        render_view(page);
    });

    // Show/hide Remove Motley button whenever company changes
    page.main.find('#ard-company').on('change', function () {
        update_motley_btn_visibility(page);
    });

    page.main.find('#ard-apply-btn').on('click', function () {
        page._ard_excl_motley = false;
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
        render_view(page);
    });

    // AR Mode toggle
    page.main.find('#ard-legacy-btn').on('click', function () {
        if (page._ard_ar_mode !== 'legacy') set_ar_mode(page, 'legacy');
    });

    page.main.find('#ard-new-btn').on('click', function () {
        if (page._ard_ar_mode !== 'new') set_ar_mode(page, 'new');
    });

    // Inline recon dropdown change (event delegation for dynamic rows)
    page.main.on('change', '.ard-recon-select', function () {
        handle_recon_change(page, $(this));
    });

    // Expand / collapse invoice rows per customer
    page.main.on('click', '.ard-expand-btn', function () {
        let $btn = $(this);
        let party = $btn.data('party');
        let isExpanded = $btn.hasClass('ard-expanded');
        page.main.find('.ard-invoice-row').filter(function () {
            return $(this).data('party') === party;
        })[isExpanded ? 'hide' : 'show']();
        $btn.toggleClass('ard-expanded').html(isExpanded ? '&#9654;' : '&#9660;');
    });
};

// ─── AR Mode Switch ───────────────────────────────────────────────────────────

function set_ar_mode(page, mode) {
    page._ard_ar_mode = mode;
    let $date = page.main.find('#ard-report-date');
    let today = frappe.datetime.get_today();

    if (mode === 'legacy') {
        page.main.find('#ard-legacy-btn').addClass('ard-mode-active');
        page.main.find('#ard-new-btn').removeClass('ard-mode-active');
        $date.attr('max', LEGACY_CUTOFF).removeAttr('min');
        // Clamp date down if it's above the cutoff
        if ($date.val() > LEGACY_CUTOFF) {
            $date.val(LEGACY_CUTOFF);
            page.main.find('#ard-report-date-display').text(LEGACY_CUTOFF);
        }
        page.main.find('#ard-subtitle').html('Legacy AR &mdash; invoices up to May 15, 2026');
    } else {
        page.main.find('#ard-new-btn').addClass('ard-mode-active');
        page.main.find('#ard-legacy-btn').removeClass('ard-mode-active');
        $date.attr('min', NEW_AR_START).removeAttr('max');
        // Clamp date up if it's below the start
        if ($date.val() < NEW_AR_START) {
            $date.val(today);
            page.main.find('#ard-report-date-display').text(today);
        }
        page.main.find('#ard-subtitle').html('New AR &mdash; invoices from May 16, 2026 onwards');
    }

    // Clear results — user must re-apply
    page._ard_result = null;
    page._ard_excl_motley = false;
    page.main.find('#ard-export-btn').hide();
    page.main.find('#ard-motley-btn').hide();
    page.main.find('#ard-data-area').html(`
		<div class="ard-empty-state">
			<div class="ard-empty-icon">&#9780;</div>
			<p>Mode changed to <strong>${mode === 'legacy' ? 'Legacy AR' : 'New AR'}</strong>. Click <strong>Apply Filters</strong> to load data.</p>
		</div>
	`);
}

// ─── Visibility helpers ───────────────────────────────────────────────────────

function update_motley_btn_visibility(page) {
    let company = page.main.find('#ard-company').val() || "";
    let is_tsbc = company.toLowerCase().indexOf("tsbc ranch") !== -1 || company === "TMM Group";
    page.main.find('#ard-motley-btn').toggle(is_tsbc && !!page._ard_result);
}

// ─── Recon Status Update ──────────────────────────────────────────────────────

function handle_recon_change(page, $select) {
    if (!page._ard_can_edit) {
        frappe.show_alert({
            message: __("You do not have permission to change reconciliation status."),
            indicator: 'red'
        }, 5);
        $select.val($select.attr('data-current') || "");
        return;
    }

    let party = $select.attr('data-party');
    let new_status = $select.val();
    let old_status = $select.attr('data-current') || "";

    apply_recon_select_class($select, new_status);
    $select.prop('disabled', true);

    frappe.call({
        method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.update_recon_status",
        args: { party: party, status: new_status },
        callback: function (r) {
            $select.prop('disabled', false);
            if (r.message) {
                frappe.show_alert({ message: __("Reconciliation status updated"), indicator: 'green' }, 3);
                $select.attr('data-current', new_status);

                if (page._ard_result && page._ard_result.rows) {
                    page._ard_result.rows.forEach(function (row) {
                        if (row.party === party) row.reconciliation_status = new_status;
                    });
                }

                render_view(page);
            }
        },
        error: function () {
            $select.prop('disabled', false);
            $select.val(old_status);
            apply_recon_select_class($select, old_status);
            frappe.show_alert({ message: __("Failed to update reconciliation status"), indicator: 'red' }, 5);
        }
    });
}

function apply_recon_select_class($select, status) {
    $select.removeClass('ard-recon-reconciled ard-recon-unreconciled ard-recon-empty');
    if (status === 'Reconciled') $select.addClass('ard-recon-reconciled');
    else if (status === 'Unreconciled') $select.addClass('ard-recon-unreconciled');
    else $select.addClass('ard-recon-empty');
}

// ─── Data Loading ─────────────────────────────────────────────────────────────

function load_ar_data(page) {
    let company    = page.main.find('#ard-company').val();
    let customer   = page.main.find('#ard-customer').val().trim();
    let date       = page.main.find('#ard-report-date').val();
    let ageing_on  = page.main.find('#ard-ageing-on').val();

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
            company: company,
            report_date: date,
            customer: customer || null,
            ageing_based_on: ageing_on,
            range_str: "30, 60, 90, 120",
            ar_mode: page._ard_ar_mode,
        },
        callback: function (r) {
            if (r.message) {
                page._ard_result = r.message;
                page._ard_can_edit = !!r.message.can_edit_recon;
                render_dashboard(page, r.message);
                page.main.find('#ard-export-btn').show();
                update_motley_btn_visibility(page);
            } else {
                area.html(`<div class="ard-empty-state"><p>No data returned.</p></div>`);
            }
        }
    });
}

// ─── Filtering helper ─────────────────────────────────────────────────────────

function get_filtered_rows(page) {
    if (!page._ard_result || !page._ard_result.rows) return [];

    let rows = page._ard_result.rows;
    let display_rows = rows.filter(function (r) { return r.outstanding > 0; });

    if (page._ard_excl_motley) {
        display_rows = display_rows.filter(function (r) {
            return (r.customer_name || r.party || "").toLowerCase().indexOf("motley") === -1;
        });
    }

    let recon_filter = page.main.find('#ard-recon-filter').val();
    if (recon_filter) {
        display_rows = display_rows.filter(function (r) {
            return (r.reconciliation_status || "") === recon_filter;
        });
    }

    return display_rows;
}

function compute_view_totals(display_rows, ranges) {
    let view_totals = { invoiced: 0, paid: 0, outstanding: 0 };
    ranges.forEach(function (r) { view_totals[r.key] = 0; });
    display_rows.forEach(function (row) {
        view_totals.invoiced += row.invoiced || 0;
        view_totals.paid += row.paid || 0;
        view_totals.outstanding += row.outstanding || 0;
        ranges.forEach(function (r) { view_totals[r.key] += row[r.key] || 0; });
    });
    return view_totals;
}

// ─── Rendering ────────────────────────────────────────────────────────────────

function render_dashboard(page, result) {
    let { rows } = result;
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

    area.html(`
		<div id="ard-summary-section"></div>
		<div id="ard-aging-section"></div>
		<div id="ard-table-section"></div>
	`);

    render_view(page);
}

function render_view(page) {
    if (!page._ard_result) return;
    let { ranges } = page._ard_result;

    let display_rows = get_filtered_rows(page);
    let view_totals = compute_view_totals(display_rows, ranges);

    render_summary_cards(page, ranges, view_totals);
    render_aging_bar(page, ranges, view_totals);
    render_table(page, display_rows, view_totals);
}

function render_summary_cards(page, ranges, view_totals) {
    let range_totals_html = ranges.map(function (r, idx) {
        let cls = range_status_class(idx);
        return `
			<div class="ard-card ard-card-range ${cls}">
				<div class="ard-card-label">${r.label} Days</div>
				<div class="ard-card-value">${fmt_cur(view_totals[r.key])}</div>
			</div>
		`;
    }).join("");

    let mode_label = page._ard_ar_mode === 'legacy' ? 'Legacy AR' : 'New AR';
    let mode_cls   = page._ard_ar_mode === 'legacy' ? 'ard-mode-chip-legacy' : 'ard-mode-chip-new';

    let html = `
		<div class="ard-summary-row">
			<div class="ard-card ard-card-outstanding">
				<div class="ard-card-label">Total Outstanding <span class="ard-mode-chip ${mode_cls}">${mode_label}</span></div>
				<div class="ard-card-value">${fmt_cur(view_totals.outstanding)}</div>
			</div>
			<div class="ard-card ard-card-invoiced">
				<div class="ard-card-label">Total Invoiced</div>
				<div class="ard-card-value">${fmt_cur(view_totals.invoiced)}</div>
			</div>
			<div class="ard-card ard-card-paid">
				<div class="ard-card-label">Total Paid</div>
				<div class="ard-card-value">${fmt_cur(view_totals.paid)}</div>
			</div>
			${range_totals_html}
		</div>
	`;

    page.main.find('#ard-summary-section').html(html);
}

function render_aging_bar(page, ranges, view_totals) {
    let total_out = view_totals.outstanding || 1;
    let bar_segments = ranges.map(function (r, idx) {
        let pct = ((view_totals[r.key] / total_out) * 100).toFixed(1);
        if (parseFloat(pct) < 0.5) return "";
        let cls = range_status_class(idx);
        return `<div class="ard-bar-seg ${cls}" style="width:${pct}%" title="${r.label} Days: ${fmt_cur(view_totals[r.key])} (${pct}%)">
					<span class="ard-bar-label">${pct}%</span>
				</div>`;
    }).join("");

    let html = `
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

    page.main.find('#ard-aging-section').html(html);
}

function build_recon_cell(page, party, status) {
    if (page._ard_can_edit) {
        let select_cls = "ard-recon-select";
        if (status === "Reconciled") select_cls += " ard-recon-reconciled";
        else if (status === "Unreconciled") select_cls += " ard-recon-unreconciled";
        else select_cls += " ard-recon-empty";

        return `
			<select class="${select_cls}"
				data-party="${esc_attr(party)}"
				data-current="${esc_attr(status)}">
				<option value=""             ${status === "" ? "selected" : ""}>—</option>
				<option value="Reconciled"   ${status === "Reconciled" ? "selected" : ""}>Reconciled</option>
				<option value="Unreconciled" ${status === "Unreconciled" ? "selected" : ""}>Unreconciled</option>
			</select>
		`;
    }

    let badge_cls = "ard-recon-readonly";
    let label = "—";
    if (status === "Reconciled") {
        badge_cls += " ard-recon-reconciled";
        label = "Reconciled";
    } else if (status === "Unreconciled") {
        badge_cls += " ard-recon-unreconciled";
        label = "Unreconciled";
    } else {
        badge_cls += " ard-recon-empty";
    }
    return `<span class="${badge_cls}" title="Read-only — Account Manager role required to edit">${label}</span>`;
}

function render_table(page, display_rows, view_totals) {
    if (!page._ard_result) return;
    let { ranges, company } = page._ard_result;

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

    let customer_order = [];
    let customer_groups = {};
    display_rows.forEach(function (row) {
        let key = row.party;
        if (!customer_groups[key]) {
            customer_groups[key] = {
                name: row.customer_name || row.party,
                party: row.party,
                recon_status: row.reconciliation_status || "",
                rows: []
            };
            customer_order.push(key);
        }
        customer_groups[key].rows.push(row);
    });
    customer_order.sort(function (a, b) {
        return (customer_groups[a].name || "").localeCompare(customer_groups[b].name || "");
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
						<th class="ard-th-recon">Status</th>
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
            sub.invoiced += row.invoiced || 0;
            sub.paid += row.paid || 0;
            sub.outstanding += row.outstanding || 0;
            ranges.forEach(function (r) { sub[r.key] += row[r.key] || 0; });
        });

        let sub_range_cells = ranges.map(function (r, idx) {
            let val = sub[r.key];
            let cls = `ard-range-cell ${range_status_class(idx)}`;
            return `<td class="${cls} ard-total-cell">${val > 0 ? fmt_cur(val) : "—"}</td>`;
        }).join("");

        let recon_cell = build_recon_cell(page, group.party, group.recon_status);

        html += `
			<tr class="ard-customer-group-row" data-party="${esc_attr(party)}">
				<td class="ard-td-sticky">
					<button class="ard-expand-btn" data-party="${esc_attr(party)}" title="Expand invoices">&#9654;</button><span class="ard-customer-group-name">${esc(group.name)}</span>
					${group.name !== group.party ? `<div class="ard-customer-group-id">${esc(group.party)}</div>` : ""}
				</td>
				<td class="ard-td-recon">${recon_cell}</td>
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
				<tr class="ard-invoice-row" data-party="${esc_attr(row.party)}" style="display:none;">
					<td class="ard-td-sticky" style="padding-left:24px;">
						<a href="/app/sales-invoice/${esc(row.voucher_no)}" target="_blank" class="ard-link">${esc(row.voucher_no)}</a>
					</td>
					<td></td>
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
						<td class="ard-total-cell"></td>
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
    let { ranges, company } = page._ard_result;

    let display_rows = get_filtered_rows(page);

    display_rows = display_rows.slice().sort(function (a, b) {
        let na = (a.customer_name || a.party || "").toLowerCase();
        let nb = (b.customer_name || b.party || "").toLowerCase();
        if (na < nb) return -1;
        if (na > nb) return 1;
        return (a.posting_date || "").localeCompare(b.posting_date || "");
    });

    let range_labels = ranges.map(function (r) { return r.label + " Days"; });
    let headers = ["Customer", "Party ID", "Reconciliation", "Invoice No.", "Type", "Posting Date", "Due Date",
        "Invoiced", "Paid", "Outstanding"].concat(range_labels).concat(["Status"]);

    let csv_rows = [headers];
    display_rows.forEach(function (row) {
        let status = get_row_status(row, ranges);
        let range_vals = ranges.map(function (r) { return row[r.key] || 0; });
        csv_rows.push([
            row.customer_name || row.party,
            row.party,
            row.reconciliation_status || "",
            row.voucher_no,
            row.voucher_type,
            row.posting_date || "",
            row.due_date || "",
            row.invoiced || 0,
            row.paid || 0,
            row.outstanding || 0,
        ].concat(range_vals).concat([status.label]));
    });

    let csv = csv_rows.map(function (cols) {
        return cols.map(function (v) {
            let s = String(v == null ? "" : v);
            if (s.indexOf(",") !== -1 || s.indexOf('"') !== -1 || s.indexOf("\n") !== -1) {
                s = '"' + s.replace(/"/g, '""') + '"';
            }
            return s;
        }).join(",");
    }).join("\r\n");

    let date_str  = page.main.find('#ard-report-date').val() || frappe.datetime.get_today();
    let mode_tag  = page._ard_ar_mode === 'legacy' ? 'Legacy' : 'New';
    let filename  = "AR_" + mode_tag + "_" + company.replace(/\s+/g, "_") + "_" + date_str + ".csv";

    let blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    let url = URL.createObjectURL(blob);
    let a = document.createElement("a");
    a.href = url;
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

    if (row.outstanding <= 0) return { label: "Clear", cls: "badge-clear" };
    if (highest < 0) return { label: "Unclassified", cls: "badge-clear" };
    if (highest === 0) return { label: "Current", cls: "badge-current" };
    if (highest === 1) return { label: "30+ Days", cls: "badge-30" };
    if (highest === 2) return { label: "60+ Days", cls: "badge-60" };
    return { label: "90+ Days", cls: "badge-90" };
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

function esc_attr(val) {
    if (val === null || val === undefined) return "";
    return String(val)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}
