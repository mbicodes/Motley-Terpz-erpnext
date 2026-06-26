var LEGACY_CUTOFF = "2026-05-31";
var NEW_AR_START  = "2026-06-01";
var ALL_ENTITIES  = "__ALL__"; // Company-filter value that triggers the consolidated cross-entity view

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
    page._ard_ar_mode     = "all"; // default mode on open: "all" (Legacy + New combined)
    page._ard_all_mode    = false;    // true while showing the consolidated all-entities view
    page._ard_all_result  = null;     // merged result ({rows tagged with .company}) for re-render

    page.main.html(`
		<div class="ard-container">
			<div class="ard-header">
				<div class="ard-header-left">
					<h2 class="ard-title">Accounts Receivable</h2>
					<p class="ard-subtitle" id="ard-subtitle">Legacy AR &mdash; invoices up to May 31, 2026</p>
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
						<button id="ard-all-btn"    class="ard-mode-btn">Legacy + New</button>
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
					<button id="ard-copy-all-btn"     class="ard-btn-secondary" style="display:none;">&#128203; Copy All</button>
					<button id="ard-pdf-btn"          class="ard-btn-secondary" style="display:none;">&#128196; Export PDF</button>
					<button id="ard-export-btn"       class="ard-btn-secondary" style="display:none;">&#8595; Export Excel</button>
					<button id="ard-motley-btn"       class="ard-btn-danger"    style="display:none;">Remove Motley</button>
				</div>
			</div>

			<div id="ard-data-area">
				<div class="ard-loading">
					<div class="ard-spinner"></div>
					<p>Loading receivables&hellip;</p>
				</div>
			</div>
		</div>
	`);

    // ── Default the page to Legacy + New mode (UI only; data loads after companies) ──
    (function () {
        let today = frappe.datetime.get_today();
        page.main.find('#ard-all-btn').addClass('ard-mode-active');
        page.main.find('#ard-legacy-btn').removeClass('ard-mode-active');
        page.main.find('#ard-new-btn').removeClass('ard-mode-active');
        page.main.find('#ard-report-date').removeAttr('min').removeAttr('max').val(today);
        page.main.find('#ard-report-date-display').text(today);
        page.main.find('#ard-subtitle').html('All AR &mdash; Legacy + New combined');
    })();

    // ── Load companies ────────────────────────────────────────────────────────
    frappe.call({
        method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.init_page",
        callback: function (r) {
            if (!r.message) return;
            let sel = page.main.find('#ard-company');
            let default_company = frappe.defaults.get_user_default("Company") || "";
            // "All" runs the consolidated cross-entity view (one row per client).
            sel.append(`<option value="${ALL_ENTITIES}">All Entities</option>`);
            r.message.companies.forEach(function (c) {
                sel.append(`<option value="${c}" ${c === default_company ? 'selected' : ''}>${c}</option>`);
            });
            // Default selection on open: All Entities (consolidated view).
            sel.val(ALL_ENTITIES);
            page._ard_can_edit = !!r.message.can_edit_recon;
            update_motley_btn_visibility(page);
            // Auto-load now that the filters are ready (no Apply button).
            apply_filters(page);
        }
    });

    page.main.find('#ard-report-date').on('change', function () {
        page.main.find('#ard-report-date-display').text($(this).val());
        apply_filters(page);
    });

    page.main.find('#ard-ageing-on').on('change', function () {
        apply_filters(page);
    });

    page.main.find('#ard-customer').on('change', function () {
        apply_filters(page);
    });

    // Status is a client-side filter on already-loaded rows — no reload needed.
    page.main.find('#ard-recon-filter').on('change', function () {
        if (page._ard_all_mode) render_all_entities(page);
        else render_view(page);
    });

    page.main.find('#ard-company').on('change', function () {
        update_motley_btn_visibility(page);
        apply_filters(page);
    });

    page.main.find('#ard-export-btn').on('click', function () {
        export_excel(page);
    });

    page.main.find('#ard-copy-all-btn').on('click', function () {
        copy_all(page);
    });

    page.main.find('#ard-pdf-btn').on('click', function () {
        export_pdf(page);
    });

    // Per-customer copy (event delegation for dynamic rows)
    page.main.on('click', '.ard-copy-btn', function (e) {
        e.stopPropagation();
        copy_customer(page, $(this).data('party'));
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

    page.main.find('#ard-all-btn').on('click', function () {
        if (page._ard_ar_mode !== 'all') set_ar_mode(page, 'all');
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
        // Scope to this table so a customer appearing in both the Good and Bad
        // AR tables toggles only within the clicked one.
        let $scope = $btn.closest('.ard-table-wrap');
        if (!$scope.length) $scope = page.main;
        $scope.find('.ard-invoice-row').filter(function () {
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
        page.main.find('#ard-all-btn').removeClass('ard-mode-active');
        $date.attr('max', LEGACY_CUTOFF).removeAttr('min');
        if ($date.val() > LEGACY_CUTOFF) {
            $date.val(LEGACY_CUTOFF);
            page.main.find('#ard-report-date-display').text(LEGACY_CUTOFF);
        }
        page.main.find('#ard-subtitle').html('Legacy AR &mdash; invoices up to May 31, 2026');
    } else if (mode === 'new') {
        page.main.find('#ard-new-btn').addClass('ard-mode-active');
        page.main.find('#ard-legacy-btn').removeClass('ard-mode-active');
        page.main.find('#ard-all-btn').removeClass('ard-mode-active');
        $date.attr('min', NEW_AR_START).removeAttr('max');
        if ($date.val() < NEW_AR_START) {
            $date.val(today);
            page.main.find('#ard-report-date-display').text(today);
        }
        page.main.find('#ard-subtitle').html('New AR &mdash; invoices from June 1, 2026 onwards');
    } else {
        // 'all' — Legacy + New combined, no date clamping
        page.main.find('#ard-all-btn').addClass('ard-mode-active');
        page.main.find('#ard-legacy-btn').removeClass('ard-mode-active');
        page.main.find('#ard-new-btn').removeClass('ard-mode-active');
        $date.removeAttr('min').removeAttr('max');
        $date.val(today);
        page.main.find('#ard-report-date-display').text(today);
        page.main.find('#ard-subtitle').html('All AR &mdash; Legacy + New combined');
    }

    // Mode changed — reload immediately with the current filters.
    page._ard_result = null;
    page._ard_all_result = null;
    page._ard_excl_motley = false;
    apply_filters(page);
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

// Central refresh: routes to the consolidated view when "All Entities" is
// selected, otherwise loads the single selected company. Called on every
// filter change (no Apply button).
function apply_filters(page) {
    page._ard_excl_motley = false;
    if (page.main.find('#ard-company').val() === ALL_ENTITIES) {
        load_all_entities(page);
    } else {
        page._ard_all_mode = false;
        page._ard_all_result = null;
        load_ar_data(page);
    }
}

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

    show_export_buttons(page, false);
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
                update_motley_btn_visibility(page);
            } else {
                area.html(`<div class="ard-empty-state"><p>No data returned.</p></div>`);
            }
        }
    });
}

// ─── Filtering helper ─────────────────────────────────────────────────────────

function get_filtered_rows(page) {
    return filter_rows(page, page._ard_result, page._ard_excl_motley);
}

// Shared row-filtering logic, usable for either a single result or one entity in All-Entities mode.
function filter_rows(page, result, excl_motley) {
    if (!result || !result.rows) return [];

    let display_rows = result.rows.filter(function (r) { return r.outstanding > 0; });

    if (excl_motley) {
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
		<div id="ard-projection-section"></div>
		<div id="ard-aging-section"></div>
		<div id="ard-table-section"></div>
	`);

    render_view(page);
}

function render_view(page) {
    if (!page._ard_result) return;
    let { ranges } = page._ard_result;

    let display_rows = get_filtered_rows(page);

    // Headline metrics (cards, aging bar, projection) stay New-AR-only; the table
    // also lists legacy customers, so its footer totals include legacy.
    let new_rows = display_rows.filter(function (r) { return !r.is_legacy; });
    let summary_totals = compute_view_totals(new_rows, ranges);
    let table_totals = compute_view_totals(display_rows, ranges);
    render_summary_cards(page, ranges, summary_totals);
    page.main.find('#ard-projection-section').html(
        build_projection_html(new_rows, page._ard_result.report_date)
    );
    render_aging_bar(page, ranges, summary_totals);
    render_table(page, display_rows, table_totals);
    add_excel_grid(page);
    show_export_buttons(page, display_rows.length > 0);
}

// ─── 4-Week Projection (forward-looking, by due date) ──────────────────────────
// Buckets outstanding invoices by how many days until they fall due, relative to
// the report ("as of") date. Closest = red (act now), furthest = green (time left).
var PROJ_BUCKETS = [
    { key: "w1", label: "Week 1", sub: "Due in 1–7 days",   min: 0,  max: 7,  cls: "ard-proj-red" },
    { key: "w2", label: "Week 2", sub: "Due in 8–14 days",  min: 8,  max: 14, cls: "ard-proj-orange" },
    { key: "w3", label: "Week 3", sub: "Due in 15–21 days", min: 15, max: 21, cls: "ard-proj-yellow" },
    { key: "w4", label: "Week 4", sub: "Due in 22–30 days", min: 22, max: 30, cls: "ard-proj-green" },
];

function days_until_due(due_date, anchor_date) {
    if (!due_date || !anchor_date) return null;
    let due = new Date(due_date);
    let anchor = new Date(anchor_date);
    if (isNaN(due) || isNaN(anchor)) return null;
    // Normalise to midnight so partial days don't skew the bucket.
    due.setHours(0, 0, 0, 0);
    anchor.setHours(0, 0, 0, 0);
    return Math.round((due - anchor) / 86400000);
}

function compute_projection(display_rows, anchor_date) {
    let totals = { w1: 0, w2: 0, w3: 0, w4: 0 };
    let counts = { w1: 0, w2: 0, w3: 0, w4: 0 };
    display_rows.forEach(function (row) {
        if (!(row.outstanding > 0)) return;
        let d = days_until_due(row.due_date, anchor_date);
        if (d === null || d < 0 || d > 30) return; // overdue or beyond the 30-day horizon
        for (let i = 0; i < PROJ_BUCKETS.length; i++) {
            let b = PROJ_BUCKETS[i];
            if (d >= b.min && d <= b.max) {
                totals[b.key] += row.outstanding;
                counts[b.key] += 1;
                break;
            }
        }
    });
    return { totals: totals, counts: counts };
}

function build_projection_html(display_rows, anchor_date) {
    let proj = compute_projection(display_rows, anchor_date);
    let grand = proj.totals.w1 + proj.totals.w2 + proj.totals.w3 + proj.totals.w4;

    let cards = PROJ_BUCKETS.map(function (b) {
        let amt = proj.totals[b.key];
        let empty_cls = amt > 0 ? "" : " ard-proj-empty";
        return `
			<div class="ard-proj-card ${b.cls}${empty_cls}">
				<div class="ard-proj-week">${b.label}</div>
				<div class="ard-proj-sub">${b.sub}</div>
				<div class="ard-proj-value">${fmt_cur(amt)}</div>
				<div class="ard-proj-count">${proj.counts[b.key]} invoice(s)</div>
			</div>
		`;
    }).join("");

    return `
		<div class="ard-proj-wrap">
			<div class="ard-proj-header">
				<span class="ard-proj-title">4-Week Projection &mdash; upcoming due</span>
				<span class="ard-proj-total">Due in next 30 days: <strong>${fmt_cur(grand)}</strong></span>
			</div>
			<div class="ard-proj-row">${cards}</div>
		</div>
	`;
}

function build_summary_html(page, ranges, view_totals) {
    let range_totals_html = ranges.map(function (r, idx) {
        let cls = range_status_class(idx);
        return `
			<div class="ard-card ard-card-range ${cls}">
				<div class="ard-card-label">${r.label} Days</div>
				<div class="ard-card-value">${fmt_cur(view_totals[r.key])}</div>
			</div>
		`;
    }).join("");

    let mode_label = page._ard_ar_mode === 'legacy' ? 'Legacy AR' : (page._ard_ar_mode === 'new' ? 'New AR' : 'Legacy + New');
    let mode_cls   = page._ard_ar_mode === 'legacy' ? 'ard-mode-chip-legacy' : (page._ard_ar_mode === 'new' ? 'ard-mode-chip-new' : 'ard-mode-chip-all');

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

    return html;
}

function render_summary_cards(page, ranges, view_totals) {
    page.main.find('#ard-summary-section').html(build_summary_html(page, ranges, view_totals));
}

function build_aging_html(page, ranges, view_totals) {
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

    return html;
}

function render_aging_bar(page, ranges, view_totals) {
    page.main.find('#ard-aging-section').html(build_aging_html(page, ranges, view_totals));
}

function build_recon_cell(page, party, status, readonly) {
    if (page._ard_can_edit && !readonly) {
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

// Resolve the active "as of" date for New-AR term bucketing.
function get_report_date(page) {
    if (page._ard_all_mode && page._ard_all_result) return page._ard_all_result.report_date;
    if (page._ard_result) return page._ard_result.report_date;
    return page.main.find('#ard-report-date').val();
}

// Sum the New-AR term columns for a set of rows (used for group + grand totals).
function na_sum(rows, anchor) {
    let s = { total: 0, new_ar: 0, legacy_ar: 0, good: 0, bad: 0, g1: 0, g2: 0, g3: 0 };
    rows.forEach(function (row) {
        let amt = row.outstanding || 0;
        if (amt <= 0) return;
        if (row.is_legacy) return; // legacy AR is excluded from the term/aging breakdown
        let info = classify_ar_row(row, anchor);
        s.total += amt;
        if ((row.posting_date || "") >= NEW_AR_START) s.new_ar += amt; else s.legacy_ar += amt;
        if (info.section === "good") { s.good += amt; s[info.bkey] += amt; }
        else { s.bad += amt; }
    });
    return s;
}

function na_header_cells(split, show_legacy_col) {
    return `
						${split ? `<th class="ard-th-num ard-na-legacy">Legacy AR</th><th class="ard-th-num ard-na-new">New AR</th>` : ``}
						${show_legacy_col ? `<th class="ard-th-num ard-na-legacy" style="background:#fef3c7;color:#92400e;">Legacy AR</th><th class="ard-th-num ard-na-new">New AR</th>` : ``}
						<th class="ard-th-num ard-na-total">Total AR</th>
						<th class="ard-th-num ard-na-good">Total New AR on Good standing</th>
						<th class="ard-th-num ard-na-bad">Total New AR on Bad standing</th>
						<th class="ard-th-num ard-good-green">0-10<br><small>Days</small></th>
						<th class="ard-th-num ard-good-yellow">10-20<br><small>Days</small></th>
						<th class="ard-th-num ard-good-red">20-30<br><small>Days</small></th>`;
}

function na_total_cells(s, split, show_legacy_col, legacy_amt) {
    return `
					${split ? `<td class="ard-num ard-total-cell ard-na-legacy">${s.legacy_ar > 0 ? fmt_cur(s.legacy_ar) : "—"}</td><td class="ard-num ard-total-cell ard-na-new">${s.new_ar > 0 ? fmt_cur(s.new_ar) : "—"}</td>` : ``}
					${show_legacy_col ? `<td class="ard-num ard-total-cell" style="background:#fef3c7;color:#92400e;font-weight:700;">${legacy_amt > 0 ? fmt_cur(legacy_amt) : "—"}</td><td class="ard-num ard-total-cell ard-na-new">${s.total > 0 ? fmt_cur(s.total) : "—"}</td>` : ``}
					<td class="ard-num ard-total-cell ard-na-total">${fmt_cur(show_legacy_col ? (legacy_amt + s.total) : s.total)}</td>
					<td class="ard-num ard-total-cell ard-na-good">${s.good > 0 ? fmt_cur(s.good) : "—"}</td>
					<td class="ard-num ard-total-cell ard-na-bad">${s.bad > 0 ? fmt_cur(s.bad) : "—"}</td>
					<td class="ard-num ard-total-cell ard-good-green">${s.g1 > 0 ? fmt_cur(s.g1) : "—"}</td>
					<td class="ard-num ard-total-cell ard-good-yellow">${s.g2 > 0 ? fmt_cur(s.g2) : "—"}</td>
					<td class="ard-num ard-total-cell ard-good-red">${s.g3 > 0 ? fmt_cur(s.g3) : "—"}</td>`;
}

function na_invoice_cells(row, anchor, split, show_legacy_col) {
    let amt = row.outstanding || 0;
    let is_new = (row.posting_date || "") >= NEW_AR_START;
    let legacy = !!row.is_legacy;
    let info = classify_ar_row(row, anchor);
    let good = !legacy && info.section === "good";
    let g1 = good && info.bkey === "g1" ? amt : 0;
    let g2 = good && info.bkey === "g2" ? amt : 0;
    let g3 = good && info.bkey === "g3" ? amt : 0;
    return `
						${split ? `<td class="ard-num ard-na-legacy">${!is_new ? fmt_cur(amt) : "—"}</td><td class="ard-num ard-na-new">${is_new ? fmt_cur(amt) : "—"}</td>` : ``}
						${show_legacy_col ? `<td class="ard-num" style="background:#fef3c7;">${legacy ? fmt_cur(amt) : "—"}</td><td class="ard-num ard-na-new">${legacy ? "—" : fmt_cur(amt)}</td>` : ``}
						<td class="ard-num ard-na-total">${fmt_cur(amt)}</td>
						<td class="ard-num ard-na-good">${(!legacy && good) ? fmt_cur(amt) : "—"}</td>
						<td class="ard-num ard-na-bad">${(!legacy && !good) ? fmt_cur(amt) : "—"}</td>
						<td class="ard-range-cell ard-good-green">${g1 > 0 ? fmt_cur(g1) : "—"}</td>
						<td class="ard-range-cell ard-good-yellow">${g2 > 0 ? fmt_cur(g2) : "—"}</td>
						<td class="ard-range-cell ard-good-red">${g3 > 0 ? fmt_cur(g3) : "—"}</td>`;
}

function build_table_html(page, ranges, company, display_rows, view_totals, readonly, show_company) {
    if (display_rows.length === 0) {
        return (`
			<div class="ard-empty-state">
				<div class="ard-empty-icon">&#10003;</div>
				<p>No outstanding receivables found for this selection.</p>
			</div>
		`);
    }

    let show_terms = page._ard_ar_mode === 'new' || page._ard_ar_mode === 'all';
    let split_ln = page._ard_ar_mode === 'all'; // Legacy+New: split Total AR into New vs Legacy
    let show_legacy_col = page._ard_ar_mode === 'new'; // New AR: extra column showing legacy outstanding
    // Legacy outstanding is read straight off the flagged legacy rows (is_legacy).
    let na_anchor = show_terms ? get_report_date(page) : null;
    let na_grand = show_terms ? na_sum(display_rows, na_anchor) : null;

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
		<div class="ard-table-wrap ard-newar-table">
			<table class="ard-table">
				<thead>
					<!--TOP_TOTALS-->
					<tr class="ard-head-row">
						<th class="ard-th-sticky">Customer</th>
						<th class="ard-th-recon">Status</th>
						${show_company ? `<th class="ard-th-entity">Entity</th>` : ``}
						<th>Invoice No.</th>
						<th>Type</th>
						<th>Posting Date</th>
						<th>Due Date</th>
						<th class="ard-th-num">Invoiced</th>
						<th class="ard-th-num">Paid</th>
						<th class="ard-th-num">Outstanding</th>
						${show_terms ? na_header_cells(split_ln, show_legacy_col) : ``}
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
        let group_legacy = 0; // sum of this customer's legacy outstanding
        ranges.forEach(function (r) { sub[r.key] = 0; });
        group.rows.forEach(function (row) {
            sub.invoiced += row.invoiced || 0;
            sub.paid += row.paid || 0;
            sub.outstanding += row.outstanding || 0;
            if (row.is_legacy) group_legacy += row.outstanding || 0;
            ranges.forEach(function (r) { sub[r.key] += row[r.key] || 0; });
        });

        let sub_range_cells = ranges.map(function (r, idx) {
            let val = sub[r.key];
            let cls = `ard-range-cell ${range_status_class(idx)}`;
            return `<td class="${cls} ard-total-cell">${val > 0 ? fmt_cur(val) : "—"}</td>`;
        }).join("");

        let recon_cell = build_recon_cell(page, group.party, group.recon_status, readonly);

        html += `
			<tr class="ard-customer-group-row" data-party="${esc_attr(party)}">
				<td class="ard-td-sticky">
					<button class="ard-expand-btn" data-party="${esc_attr(party)}" title="Expand invoices">&#9654;</button><span class="ard-customer-group-name">${esc(group.name)}</span><button class="ard-copy-btn" data-party="${esc_attr(party)}" title="Copy this customer's summary">&#128203;</button>
					${group.name !== group.party ? `<div class="ard-customer-group-id">${esc(group.party)}</div>` : ""}
				</td>
				<td class="ard-td-recon">${recon_cell}</td>
				<td colspan="${show_company ? 5 : 4}" style="color:var(--ard-muted);font-size:12px;">${group.rows.length} invoice(s)</td>
				<td class="ard-num ard-total-cell">${fmt_cur(sub.invoiced)}</td>
				<td class="ard-num ard-total-cell">${fmt_cur(sub.paid)}</td>
				<td class="ard-num ard-total-cell ard-outstanding">${fmt_cur(sub.outstanding)}</td>
				${show_terms ? na_total_cells(na_sum(group.rows, na_anchor), split_ln, show_legacy_col, group_legacy) : ``}
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
					${show_company ? `<td class="ard-entity-cell">${esc(row.company || "")}</td>` : ``}
					<td></td>
					<td class="ard-type">${esc(row.voucher_type)}</td>
					<td class="ard-date">${fmt_date(row.posting_date)}</td>
					<td class="ard-date">${fmt_date(row.due_date)}</td>
					<td class="ard-num">${fmt_cur(row.invoiced)}</td>
					<td class="ard-num">${fmt_cur(row.paid)}</td>
					<td class="ard-num ard-outstanding">${fmt_cur(row.outstanding)}</td>
					${show_terms ? na_invoice_cells(row, na_anchor, split_ln, show_legacy_col) : ``}
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

    let grand_legacy = display_rows.reduce(function (a, r) { return a + (r.is_legacy ? (r.outstanding || 0) : 0); }, 0);
    let totals_cells = `
						<td class="ard-td-sticky ard-total-cell">${esc(company)}</td>
						<td class="ard-total-cell"></td>
						<td class="ard-total-cell" colspan="${show_company ? 5 : 4}">${total_invoices} invoice(s) &bull; ${customer_order.length} customer(s)</td>
						<td class="ard-num ard-total-cell">${fmt_cur(view_totals.invoiced)}</td>
						<td class="ard-num ard-total-cell">${fmt_cur(view_totals.paid)}</td>
						<td class="ard-num ard-total-cell ard-outstanding">${fmt_cur(view_totals.outstanding)}</td>
						${show_terms ? na_total_cells(na_grand, split_ln, show_legacy_col, grand_legacy) : ``}
						${range_total_cells}
						<td></td>`;

    html += `
				</tbody>
				<tfoot>
					<tr class="ard-totals-row">${totals_cells}</tr>
				</tfoot>
			</table>
		</div>
	`;

    // Mirror the totals row at the very top, just above the column headings.
    html = html.replace("<!--TOP_TOTALS-->", `<tr class="ard-totals-row ard-top-totals">${totals_cells}</tr>`);

    return html;
}

function render_table(page, display_rows, view_totals) {
    if (!page._ard_result) return;
    let { ranges, company } = page._ard_result;
    page.main.find('#ard-table-section').html(
        build_table_html(page, ranges, company, display_rows, view_totals, false)
    );
}

// ─── Excel-style grid (column letters A,B,C… + row numbers 1,2,3…) ──────────────

function col_letter(n) {
    // 0 -> A, 25 -> Z, 26 -> AA, …
    let s = "";
    n = n + 1;
    while (n > 0) {
        let rem = (n - 1) % 26;
        s = String.fromCharCode(65 + rem) + s;
        n = Math.floor((n - 1) / 26);
    }
    return s;
}

// Decorate every rendered table with a spreadsheet grid: a top strip of column
// letters and a sticky left column of row numbers. Column count is read from the
// DOM so it works for every mode/column combination.
function add_excel_grid(page) {
    page.main.find('#ard-data-area .ard-table').each(function () {
        let $table = $(this);
        if ($table.hasClass('ard-has-grid')) return;

        // Measure columns from the heading row (the top totals row uses colspans).
        let $headRow = $table.find('thead tr.ard-head-row').first();
        if (!$headRow.length) $headRow = $table.find('thead tr').first();
        let ncols = $headRow.children().length;
        if (!ncols) return;

        // Top strip: corner + one letter per column.
        let strip = '<th class="ard-grid-corner"></th>';
        for (let i = 0; i < ncols; i++) {
            strip += '<th class="ard-grid-col">' + col_letter(i) + '</th>';
        }
        $table.find('thead').prepend('<tr class="ard-grid-colrow">' + strip + '</tr>');

        // Number every row in order (skip the letter strip). thead rows get <th>,
        // body/footer rows get <td>.
        let n = 1;
        $table.find('thead tr, tbody tr, tfoot tr').each(function () {
            let $tr = $(this);
            if ($tr.hasClass('ard-grid-colrow')) return;
            let tag = $tr.closest('thead').length ? 'th' : 'td';
            $tr.prepend('<' + tag + ' class="ard-grid-rownum">' + (n++) + '</' + tag + '>');
        });

        $table.addClass('ard-has-grid');
    });
}

// ─── All Entities (consolidated across every company, grouped by client) ───

function load_all_entities(page) {
    // Collect every real company from the dropdown. Skip the "All" sentinel and
    // "TMM Group" (a roll-up of Motley Terpz + TSBC Ranch) to avoid double-counting.
    let companies = [];
    page.main.find('#ard-company option').each(function () {
        let v = $(this).val();
        if (v && v !== ALL_ENTITIES && v !== 'TMM Group') companies.push(v);
    });

    if (!companies.length) {
        frappe.msgprint("No companies available.");
        return;
    }

    page._ard_all_mode = true;
    page._ard_all_result = null;
    page._ard_excl_motley = false;
    show_export_buttons(page, false);
    page.main.find('#ard-motley-btn').hide();

    let customer  = page.main.find('#ard-customer').val().trim();
    let date      = page.main.find('#ard-report-date').val();
    let ageing_on = page.main.find('#ard-ageing-on').val();

    let area = page.main.find('#ard-data-area');
    area.html(`
        <div class="ard-loading" id="ard-all-loading">
            <div class="ard-spinner"></div>
            <p>Loading entity 0 of ${companies.length}&hellip;</p>
        </div>
    `);

    let idx = 0;
    let merged_rows = [];
    let ranges = null;

    function finish() {
        page._ard_all_result = {
            rows: merged_rows,
            ranges: ranges || [],
            company: "All Entities",
            report_date: date,
            ar_mode: page._ard_ar_mode,
            can_edit_recon: false,
        };
        render_all_entities(page);
    }

    function fetch_next() {
        if (idx >= companies.length) {
            finish();
            return;
        }

        let company = companies[idx];
        page.main.find('#ard-all-loading p')
            .text("Loading entity " + (idx + 1) + " of " + companies.length + " \u2014 " + company + "\u2026");

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
                    if (!ranges) ranges = r.message.ranges;
                    (r.message.rows || []).forEach(function (row) {
                        row.company = company; // tag each invoice with its source entity
                        merged_rows.push(row);
                    });
                }
                idx++;
                fetch_next();
            },
            error: function () {
                idx++;
                fetch_next();
            }
        });
    }

    fetch_next();
}

// Render the consolidated view: one group per client, with that client's
// invoices from every entity (TSBC, Motley, Master Touch, LA Canna ...) merged
// together. The Entity column shows which company each invoice belongs to.
function render_all_entities(page) {
    let result = page._ard_all_result;
    let area = page.main.find('#ard-data-area');
    if (!result) return;

    let ranges = result.ranges;
    let display_rows = filter_rows(page, result, false);

    if (!display_rows.length) {
        area.html(`
            <div class="ard-empty-state">
                <div class="ard-empty-icon">&#10003;</div>
                <p>No outstanding receivables found across any entity.</p>
            </div>
        `);
        show_export_buttons(page, false);
        return;
    }

    // Headline metrics stay New-AR-only; the table footer includes legacy.
    let new_rows = display_rows.filter(function (r) { return !r.is_legacy; });
    let summary_totals = compute_view_totals(new_rows, ranges);
    let table_totals = compute_view_totals(display_rows, ranges);

    // Recon cells are read-only here (inline editing targets the single-company
    // result); the final true enables the Entity column.
    area.html(`
        <div id="ard-summary-section">${build_summary_html(page, ranges, summary_totals)}</div>
        <div id="ard-projection-section">${build_projection_html(new_rows, result.report_date)}</div>
        <div id="ard-aging-section">${build_aging_html(page, ranges, summary_totals)}</div>
        <div id="ard-table-section">${build_table_html(page, ranges, "All Entities", display_rows, table_totals, true, true)}</div>
    `);
    add_excel_grid(page);
    show_export_buttons(page, true);
}

// ─── New AR term classification (drives the extra "AR on terms" columns) ────────
// Only used when AR Mode = "New". An invoice is "on terms" (good standing) while
// the report date is on/before its due date, bucketed by age since posting
// (0-10 green, 10-20 yellow, 20-30 red). Once the due date passes it is "overdue"
// (bad standing) — that amount stays in the existing overdue (range) columns.

function diff_days(later, earlier) {
    if (!later || !earlier) return null;
    let l = new Date(later), e = new Date(earlier);
    if (isNaN(l) || isNaN(e)) return null;
    l.setHours(0, 0, 0, 0);
    e.setHours(0, 0, 0, 0);
    return Math.round((l - e) / 86400000);
}

function classify_ar_row(row, report_date) {
    let overdue = diff_days(report_date, row.due_date); // report - due (positive = past due)
    if (overdue !== null && overdue > 0) {
        let bkey = overdue <= 30 ? "b1" : overdue <= 60 ? "b2" : overdue <= 90 ? "b3" : overdue <= 120 ? "b4" : "b5";
        return { section: "bad", bkey: bkey, days: overdue };
    }
    let age = diff_days(report_date, row.posting_date); // report - posting (days on terms)
    if (age === null || age < 0) age = 0;
    let bkey = age <= 10 ? "g1" : age <= 20 ? "g2" : "g3";
    return { section: "good", bkey: bkey, days: age };
}

// ─── Copy to clipboard (formatted client summary) ──────────────────────────────

var AR_COPY_HEADER = "📊 AR AGING REPORT — FULL CLIENT BREAKDOWN";
var AR_COPY_SEP    = "━━━━━━━━━━━━━━━━━━━━━━";

// The result + filtered rows currently on screen, whether single-company or the
// consolidated All-Entities view.
function current_result(page) {
    return (page._ard_all_mode && page._ard_all_result) ? page._ard_all_result : page._ard_result;
}
function current_display_rows(page) {
    let res = current_result(page);
    if (!res) return [];
    return filter_rows(page, res, page._ard_excl_motley);
}

function keycap(n) {
    let caps = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"];
    return (n >= 0 && n <= 10) ? caps[n] : (n + ".");
}

// Whole-dollar money for the copy text (e.g. "$18,900", or "—" when empty).
function fmt_money_short(v) {
    if (!v || Math.round(v) === 0) return "—";
    return "$" + Math.round(v).toLocaleString("en-US");
}

function aggregate_party(rows, ranges) {
    let a = { name: "", count: rows.length, invoiced: 0, paid: 0, outstanding: 0, legacy: 0, recent: 0, recon: "" };
    ranges.forEach(function (r) { a[r.key] = 0; });
    rows.forEach(function (row) {
        a.name = row.customer_name || row.party || a.name;
        a.invoiced += row.invoiced || 0;
        a.paid += row.paid || 0;
        a.outstanding += row.outstanding || 0;
        if ((row.posting_date || "") >= NEW_AR_START) a.recent += row.outstanding || 0;
        else a.legacy += row.outstanding || 0;
        ranges.forEach(function (r) { a[r.key] += row[r.key] || 0; });
        if (row.reconciliation_status) a.recon = row.reconciliation_status;
    });
    return a;
}

function build_customer_block(idx, a, ranges) {
    let recon = a.recon === "Reconciled" ? " ✅ Reconciled"
        : (a.recon === "Unreconciled" ? " ⚠️ Unreconciled" : "");
    let parts = [];
    ranges.forEach(function (r) {
        if ((a[r.key] || 0) > 0) parts.push(`${r.label} Days: ${fmt_money_short(a[r.key])}`);
    });
    let aging = parts.length ? `⏳ ${parts.join(" | ")}` : "⏳ Current / on terms";
    return [
        `${keycap(idx)} ${a.name} (${a.count} inv)${recon}`,
        `💵 Invoiced: ${fmt_money_short(a.invoiced)} | Paid: ${fmt_money_short(a.paid)}`,
        `📌 Outstanding: ${fmt_money_short(a.outstanding)}`,
        `🗂️ Legacy AR: ${fmt_money_short(a.legacy)} | New AR: ${fmt_money_short(a.recent)}`,
        aging,
    ].join("\n");
}

function copy_to_clipboard(text, msg) {
    function ok() { frappe.show_alert({ message: __(msg || "Copied to clipboard"), indicator: "green" }, 3); }
    function fallback() {
        let ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); ok(); }
        catch (e) { frappe.msgprint("Copy failed — please copy manually."); }
        document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok).catch(fallback);
    } else {
        fallback();
    }
}

function copy_customer(page, party) {
    let res = current_result(page);
    if (!res) return;
    let rows = current_display_rows(page).filter(function (r) { return r.party === party; });
    if (!rows.length) return;
    let a = aggregate_party(rows, res.ranges);
    let text = AR_COPY_HEADER + "\n" + AR_COPY_SEP + "\n\n" +
        build_customer_block(1, a, res.ranges) + "\n\n" + AR_COPY_SEP;
    copy_to_clipboard(text, "Copied " + a.name);
}

function copy_all(page) {
    let res = current_result(page);
    if (!res) return;
    let rows = current_display_rows(page);
    if (!rows.length) {
        frappe.show_alert({ message: __("No rows to copy"), indicator: "orange" }, 3);
        return;
    }
    let groups = {}, order = [];
    rows.forEach(function (r) {
        if (!groups[r.party]) { groups[r.party] = []; order.push(r.party); }
        groups[r.party].push(r);
    });
    let aggs = order.map(function (p) { return aggregate_party(groups[p], res.ranges); });
    aggs.sort(function (x, y) { return (x.name || "").localeCompare(y.name || ""); });
    let blocks = aggs.map(function (a, i) { return build_customer_block(i + 1, a, res.ranges); });
    let text = AR_COPY_HEADER + "\n" + AR_COPY_SEP + "\n\n" +
        blocks.join("\n\n" + AR_COPY_SEP + "\n\n") + "\n\n" + AR_COPY_SEP;
    copy_to_clipboard(text, aggs.length + " customer(s) copied to clipboard");
}

// ─── PDF Export (prints the on-screen dashboard view) ───────────────────────────

function export_pdf(page) {
    let container = page.main.find('.ard-container').get(0);
    if (!container) return;

    let head = "";
    document.querySelectorAll('link[rel="stylesheet"]').forEach(function (l) {
        if (l.href) head += `<link rel="stylesheet" href="${l.href}">`;
    });
    document.querySelectorAll('style').forEach(function (st) { head += st.outerHTML; });

    let w = window.open("", "_blank");
    if (!w) {
        frappe.msgprint("Please allow pop-ups for this site to export PDF.");
        return;
    }

    // Print CSS: landscape, compact cells, all invoices expanded, sticky columns
    // turned static so the wide table lays out at its full natural width.
    let print_css =
        'body{padding:0;margin:0;background:#fff;}' +
        // Kill centering/max-width so content starts at the left edge of the page
        '.ard-container{max-width:none!important;margin:0!important;padding:4px 6px!important;}' +
        '#ard-pdf-page{padding:0;}' +
        // Hide interactive UI
        '.ard-filter-bar,.ard-copy-btn,.ard-expand-btn,.ard-btn-secondary,.ard-btn-danger,' +
        '.ard-header-right,.ard-btn-group{display:none!important;}' +
        '.ard-invoice-row{display:table-row!important;}' +
        // Summary cards and header: compact
        '.ard-header{padding:4px 0!important;margin-bottom:4px!important;}' +
        '.ard-summary-row{gap:4px!important;margin-bottom:4px!important;}' +
        '.ard-card{padding:5px 8px!important;min-width:0!important;}' +
        '.ard-card-label{font-size:7px!important;}' +
        '.ard-card-value{font-size:11px!important;}' +
        '.ard-projection-wrap,.ard-aging-dist-wrap{margin-bottom:4px!important;padding:6px 8px!important;}' +
        // Remove all scroll/height constraints so scrollWidth is accurate
        '.ard-table-wrap{overflow:visible!important;max-height:none!important;height:auto!important;' +
          'border:none!important;box-shadow:none!important;border-radius:0!important;}' +
        '.ard-table{width:auto!important;}' +
        // Tight cells
        '.ard-table th,.ard-table td{font-size:7px!important;padding:1px 3px!important;white-space:nowrap;}' +
        // Neutralise sticky positioning so nothing overlaps when laid flat
        '.ard-th-sticky,.ard-td-sticky,.ard-grid-rownum,.ard-grid-corner,' +
        '.ard-table thead th{position:static!important;left:auto!important;top:auto!important;box-shadow:none!important;}' +
        '@page{size:landscape;margin:5mm;}';

    // Measure the widest .ard-table directly (not the outer wrapper — the wrapper
    // may only report viewport width before zoom is applied), then zoom the body
    // to fit within the printable landscape width.
    let fit_script =
        'window.onload=function(){' +
        '  try{' +
        '    document.querySelectorAll(".ard-table-wrap").forEach(function(el){' +
        '      el.style.overflow="visible";el.style.maxHeight="none";el.style.height="auto";' +
        '    });' +
        '    var maxW=0;' +
        '    document.querySelectorAll(".ard-table").forEach(function(t){' +
        '      if(t.scrollWidth>maxW)maxW=t.scrollWidth;' +
        '    });' +
        '    if(!maxW){var fb=document.getElementById("ard-pdf-page");maxW=fb?fb.scrollWidth:0;}' +
        '    var pageW=1080;' + // A4 landscape (297mm − 12mm margins) ≈ 1080px at 96 dpi
        '    if(maxW>pageW){document.body.style.zoom=(pageW/maxW);}' +
        '  }catch(e){}' +
        '  setTimeout(function(){window.print();},400);' +
        '};';

    w.document.write(
        '<!doctype html><html><head><meta charset="utf-8"><title>AR Aging Report</title>' + head +
        '<style>' + print_css + '</style>' +
        '<scr' + 'ipt>' + fit_script + '</scr' + 'ipt>' +
        '</head><body><div id="ard-pdf-page">' + container.outerHTML + '</div></body></html>'
    );
    w.document.close();
    w.focus();
}

// Show/hide the Copy All / PDF / Excel buttons based on whether data is on screen.
function show_export_buttons(page, has_rows) {
    let $btns = page.main.find('#ard-copy-all-btn, #ard-pdf-btn, #ard-export-btn');
    if (has_rows) $btns.show(); else $btns.hide();
}

// ─── Excel Export ─────────────────────────────────────────────────────────────

function export_excel(page) {
    let res = current_result(page);
    if (!res) return;
    let { ranges, company } = res;

    let display_rows = current_display_rows(page);

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
    let mode_tag  = page._ard_ar_mode === 'legacy' ? 'Legacy' : (page._ard_ar_mode === 'new' ? 'New' : 'All');
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
