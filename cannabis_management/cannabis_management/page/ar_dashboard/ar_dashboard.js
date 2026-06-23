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
    page._ard_ar_mode     = "legacy"; // "legacy" (≤ May 31 2026) | "new" (≥ Jun 1 2026) | "all" (combined)
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
            // Default to a real company (not the "All Entities" sentinel) when the
            // user's default company didn't match any option.
            if (sel.val() === ALL_ENTITIES && r.message.companies.length) {
                sel.val(r.message.companies[0]);
            }
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
        if (!$date.val() || $date.val() < LEGACY_CUTOFF) {
            $date.val(today);
            page.main.find('#ard-report-date-display').text(today);
        }
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

    let view_totals = compute_view_totals(display_rows, ranges);
    render_summary_cards(page, ranges, view_totals);
    page.main.find('#ard-projection-section').html(
        build_projection_html(display_rows, page._ard_result.report_date)
    );
    render_aging_bar(page, ranges, view_totals);
    render_table(page, display_rows, view_totals);
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
    let s = { total: 0, good: 0, bad: 0, g1: 0, g2: 0, g3: 0 };
    rows.forEach(function (row) {
        let amt = row.outstanding || 0;
        if (amt <= 0) return;
        let info = classify_new_ar(row, anchor);
        s.total += amt;
        if (info.section === "good") { s.good += amt; s[info.bkey] += amt; }
        else { s.bad += amt; }
    });
    return s;
}

function na_header_cells() {
    return `
						<th class="ard-th-num ard-na-total">Total New AR</th>
						<th class="ard-th-num ard-na-good">Total AR on terms<br><small>(Good standing)</small></th>
						<th class="ard-th-num ard-na-bad">Total AR on terms<br><small>(Bad standing)</small></th>
						<th class="ard-th-num ard-good-green">0-10<br><small>Days</small></th>
						<th class="ard-th-num ard-good-yellow">10-20<br><small>Days</small></th>
						<th class="ard-th-num ard-good-red">20-30<br><small>Days</small></th>`;
}

function na_total_cells(s) {
    return `
					<td class="ard-num ard-total-cell ard-na-total">${fmt_cur(s.total)}</td>
					<td class="ard-num ard-total-cell ard-na-good">${s.good > 0 ? fmt_cur(s.good) : "—"}</td>
					<td class="ard-num ard-total-cell ard-na-bad">${s.bad > 0 ? fmt_cur(s.bad) : "—"}</td>
					<td class="ard-num ard-total-cell ard-good-green">${s.g1 > 0 ? fmt_cur(s.g1) : "—"}</td>
					<td class="ard-num ard-total-cell ard-good-yellow">${s.g2 > 0 ? fmt_cur(s.g2) : "—"}</td>
					<td class="ard-num ard-total-cell ard-good-red">${s.g3 > 0 ? fmt_cur(s.g3) : "—"}</td>`;
}

function na_invoice_cells(row, anchor) {
    let amt = row.outstanding || 0;
    let info = classify_new_ar(row, anchor);
    let good = info.section === "good";
    let g1 = good && info.bkey === "g1" ? amt : 0;
    let g2 = good && info.bkey === "g2" ? amt : 0;
    let g3 = good && info.bkey === "g3" ? amt : 0;
    return `
						<td class="ard-num ard-na-total">${fmt_cur(amt)}</td>
						<td class="ard-num ard-na-good">${good ? fmt_cur(amt) : "—"}</td>
						<td class="ard-num ard-na-bad">${!good ? fmt_cur(amt) : "—"}</td>
						<td class="ard-range-cell ${g1 > 0 ? "ard-good-green" : "ard-range-zero"}">${g1 > 0 ? fmt_cur(g1) : "—"}</td>
						<td class="ard-range-cell ${g2 > 0 ? "ard-good-yellow" : "ard-range-zero"}">${g2 > 0 ? fmt_cur(g2) : "—"}</td>
						<td class="ard-range-cell ${g3 > 0 ? "ard-good-red" : "ard-range-zero"}">${g3 > 0 ? fmt_cur(g3) : "—"}</td>`;
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

    let new_ar = page._ard_ar_mode === 'new';
    let na_anchor = new_ar ? get_report_date(page) : null;
    let na_grand = new_ar ? na_sum(display_rows, na_anchor) : null;

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
						${show_company ? `<th class="ard-th-entity">Entity</th>` : ``}
						<th>Invoice No.</th>
						<th>Type</th>
						<th>Posting Date</th>
						<th>Due Date</th>
						<th class="ard-th-num">Invoiced</th>
						<th class="ard-th-num">Paid</th>
						<th class="ard-th-num">Outstanding</th>
						${new_ar ? na_header_cells() : ``}
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

        let recon_cell = build_recon_cell(page, group.party, group.recon_status, readonly);

        html += `
			<tr class="ard-customer-group-row" data-party="${esc_attr(party)}">
				<td class="ard-td-sticky">
					<button class="ard-expand-btn" data-party="${esc_attr(party)}" title="Expand invoices">&#9654;</button><span class="ard-customer-group-name">${esc(group.name)}</span>
					${group.name !== group.party ? `<div class="ard-customer-group-id">${esc(group.party)}</div>` : ""}
				</td>
				<td class="ard-td-recon">${recon_cell}</td>
				<td colspan="${show_company ? 5 : 4}" style="color:var(--ard-muted);font-size:12px;">${group.rows.length} invoice(s)</td>
				<td class="ard-num ard-total-cell">${fmt_cur(sub.invoiced)}</td>
				<td class="ard-num ard-total-cell">${fmt_cur(sub.paid)}</td>
				<td class="ard-num ard-total-cell ard-outstanding">${fmt_cur(sub.outstanding)}</td>
				${new_ar ? na_total_cells(na_sum(group.rows, na_anchor)) : ``}
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
					${new_ar ? na_invoice_cells(row, na_anchor) : ``}
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
						<td class="ard-total-cell" colspan="${show_company ? 5 : 4}">${total_invoices} invoice(s) &bull; ${customer_order.length} customer(s)</td>
						<td class="ard-num ard-total-cell">${fmt_cur(view_totals.invoiced)}</td>
						<td class="ard-num ard-total-cell">${fmt_cur(view_totals.paid)}</td>
						<td class="ard-num ard-total-cell ard-outstanding">${fmt_cur(view_totals.outstanding)}</td>
						${new_ar ? na_total_cells(na_grand) : ``}
						${range_total_cells}
						<td></td>
					</tr>
				</tfoot>
			</table>
		</div>
	`;

    return html;
}

function render_table(page, display_rows, view_totals) {
    if (!page._ard_result) return;
    let { ranges, company } = page._ard_result;
    page.main.find('#ard-table-section').html(
        build_table_html(page, ranges, company, display_rows, view_totals, false)
    );
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
    page.main.find('#ard-export-btn').hide();
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
    let view_totals = compute_view_totals(display_rows, ranges);

    if (!display_rows.length) {
        area.html(`
            <div class="ard-empty-state">
                <div class="ard-empty-icon">&#10003;</div>
                <p>No outstanding receivables found across any entity.</p>
            </div>
        `);
        return;
    }

    // Recon cells are read-only here (inline editing targets the single-company
    // result); the final true enables the Entity column.
    area.html(`
        <div id="ard-summary-section">${build_summary_html(page, ranges, view_totals)}</div>
        <div id="ard-projection-section">${build_projection_html(display_rows, result.report_date)}</div>
        <div id="ard-aging-section">${build_aging_html(page, ranges, view_totals)}</div>
        <div id="ard-table-section">${build_table_html(page, ranges, "All Entities", display_rows, view_totals, true, true)}</div>
    `);
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

function classify_new_ar(row, report_date) {
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
