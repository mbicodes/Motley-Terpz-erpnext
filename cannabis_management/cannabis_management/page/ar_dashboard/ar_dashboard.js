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
    page._ard_new_ar_only = false;
    page._ard_can_edit    = false;
    page._ard_ar_mode     = "all"; // default mode on open: "all" (Legacy + New combined)
    page._ard_all_mode    = false;    // true while showing the consolidated all-entities view
    page._ard_all_result  = null;     // merged result ({rows tagged with .company}) for re-render
    page._ard_cols_hidden = false;
    page._ard_new_ar_only = false;

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
						<option value="Reconciled collecting money">Reconciled collecting money</option>
						<option value="Reconciled trouble collecting money">Reconciled trouble collecting money</option>
						<option value="Unreconciled">Unreconciled</option>
						<option value="Dispute">Dispute</option>
						<option value="Adjustment">Adjustment</option>
					</select>
				</div>
				<div class="ard-filter-actions">
					<button id="ard-new-ar-only-btn" class="ard-btn-secondary" style="display:none;">New AR &gt; 0</button>
					<button id="ard-hide-cols-btn" class="ard-btn-secondary" style="display:none;">&#9679; Hide Columns D&ndash;K</button>
					<div class="ard-export-dd" id="ard-export-dd" style="display:none;">
						<button id="ard-export-toggle" class="ard-btn-secondary">&#8595; Export &#9662;</button>
						<div class="ard-export-menu" id="ard-export-menu" style="display:none;">
							<button id="ard-copy-all-btn" class="ard-export-item">&#128203; Copy All</button>
							<button id="ard-pdf-btn"      class="ard-export-item">&#128196; Export PDF</button>
							<button id="ard-export-btn"   class="ard-export-item">&#8595; Export Excel (This View)</button>
							<button id="ard-export-all-btn" class="ard-export-item">&#8595; Export Excel (Whole Dashboard)</button>
						</div>
					</div>
					<button id="ard-motley-btn" class="ard-btn-danger" style="display:none;">Remove Motley</button>
				</div>
			</div>

			<div id="ard-data-area">
				<div class="ard-loading">
					<div class="ard-spinner"></div>
					<p>Loading receivables&hellip;</p>
				</div>
			</div>

			<div class="ard-monthly-section">
				<div class="ard-monthly-header">
					<h3 class="ard-monthly-title">Month-wise Collection &mdash; Legacy vs New AR</h3>
					<p class="ard-monthly-subtitle">Payment entries against invoices posted before Jun 1, 2026 (Legacy) vs on/after Jun 1, 2026 (New AR). Adjustments (credit notes / journal entries) are tracked separately from cash collected.</p>
				</div>
				<div id="ard-monthly-area">
					<div class="ard-loading">
						<div class="ard-spinner"></div>
						<p>Loading month-wise collection&hellip;</p>
					</div>
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
            load_monthly_collection(page);
        }
    });

    // Month-wise Collection section follows the Company filter but is
    // independent of the AR Mode toggle (it always shows Legacy + New side by side).
    page.main.find('#ard-company').on('change', function () {
        load_monthly_collection(page);
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
        export_excel(page, false);
    });

    page.main.find('#ard-export-all-btn').on('click', function () {
        export_excel(page, true);
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

    // Inline POC dropdown change
    page.main.on('change', '.ard-poc-select', function () {
        handle_poc_change(page, $(this));
    });

    // Inline Notebox edit — save on blur (focusout bubbles; blur does not) when
    // the text changed.
    page.main.on('focusout', '.ard-notebox-input', function () {
        handle_notebox_change(page, $(this));
    });

    // Filter: show only customers with New AR > 1.
    // Applied automatically in New AR mode (see apply_filters); the button
    // remains a manual toggle to widen the view back out.
    page.main.find('#ard-new-ar-only-btn').on('click', function () {
        set_new_ar_only(page, !page._ard_new_ar_only);
        if (page._ard_all_mode) render_all_entities(page);
        else render_view(page);
    });

    // Hide / show detail columns (D–K toggle) — pure CSS, no re-render
    page.main.find('#ard-hide-cols-btn').on('click', function () {
        page._ard_cols_hidden = !page._ard_cols_hidden;
        update_hide_cols_btn(page);
        apply_col_visibility(page);
    });

    // Export dropdown toggle
    page.main.find('#ard-export-toggle').on('click', function (e) {
        e.stopPropagation();
        page.main.find('#ard-export-menu').toggle();
    });
    page.main.find('#ard-export-menu').on('click', 'button', function () {
        page.main.find('#ard-export-menu').hide();
    });
    $(document).on('click.ard-export-dd', function () {
        page.main.find('#ard-export-menu').hide();
    });

    // New AR Available toggle
    page.main.on('click', '.ard-new-ar-btn', function () {
        handle_new_ar_click(page, $(this));
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

// ─── Month-wise Collection: Legacy vs New AR ──────────────────────────────────

function load_monthly_collection(page) {
    let area = page.main.find('#ard-monthly-area');
    area.html(`
		<div class="ard-loading">
			<div class="ard-spinner"></div>
			<p>Loading month-wise collection&hellip;</p>
		</div>
	`);

    let company = page.main.find('#ard-company').val() || ALL_ENTITIES;

    frappe.call({
        method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.get_monthly_ar_collection",
        args: { company: company === ALL_ENTITIES ? null : company },
        callback: function (r) {
            if (!r.message) return;
            render_monthly_collection(page, r.message);
        },
        error: function () {
            area.html('<p class="ard-empty">Failed to load month-wise collection.</p>');
        }
    });
}

function render_monthly_collection(page, data) {
    let area = page.main.find('#ard-monthly-area');

    let totals_html = `
		<div class="ard-monthly-tiles">
			<div class="ard-monthly-tile ard-monthly-tile-legacy">
				<span>Legacy AR Balance (now)</span><b>${fmt_cur(data.totals.legacy_balance_now)}</b>
			</div>
			<div class="ard-monthly-tile">
				<span>Legacy Collected (all time)</span><b>${fmt_cur(data.totals.legacy_collected)}</b>
			</div>
			<div class="ard-monthly-tile">
				<span>Legacy Adjustments (all time)</span><b>${fmt_cur(data.totals.legacy_adjustment)}</b>
			</div>
			<div class="ard-monthly-tile ard-monthly-tile-new">
				<span>New AR Collected (all time)</span><b>${fmt_cur(data.totals.new_collected)}</b>
			</div>
		</div>
	`;

    let monthly_rows_html = data.monthly.map(function (r) {
        return `
			<tr>
				<td class="ard-monthly-month">${r.label}</td>
				<td class="ard-num">${fmt_cur(r.legacy_collected)}</td>
				<td class="ard-num ${r.legacy_adjustment ? 'ard-monthly-adj' : ''}">${r.legacy_adjustment ? fmt_cur(r.legacy_adjustment) : '&mdash;'}</td>
				<td class="ard-num ard-monthly-balance">${fmt_cur(r.legacy_balance)}</td>
				<td class="ard-num">${r.new_collected ? fmt_cur(r.new_collected) : '&mdash;'}</td>
				<td class="ard-num ${r.new_adjustment ? 'ard-monthly-adj' : ''}">${r.new_adjustment ? fmt_cur(r.new_adjustment) : '&mdash;'}</td>
			</tr>
		`;
    }).join('');

    let weekly_html = '';
    if (data.weekly && data.weekly.length) {
        let weekly_rows = data.weekly.map(function (w) {
            return `
				<tr>
					<td class="ard-monthly-month">${w.label}</td>
					<td class="ard-num">${w.legacy_collected ? fmt_cur(w.legacy_collected) : '&mdash;'}</td>
					<td class="ard-num">${w.new_collected ? fmt_cur(w.new_collected) : '&mdash;'}</td>
				</tr>
			`;
        }).join('');
        weekly_html = `
			<div class="ard-monthly-subtitle2">Trailing 4 Weeks (since Jun 1, 2026)</div>
			<div class="ard-table-wrap ard-monthly-weekly-wrap">
				<table class="ard-table">
					<thead>
						<tr>
							<th>Week</th>
							<th class="ard-num">Legacy Collected</th>
							<th class="ard-num">New AR Collected</th>
						</tr>
					</thead>
					<tbody>${weekly_rows}</tbody>
				</table>
			</div>
		`;
    }

    area.html(`
		${totals_html}
		<div class="ard-table-wrap">
			<table class="ard-table ard-monthly-table">
				<thead>
					<tr>
						<th rowspan="2">Month</th>
						<th colspan="3" class="ard-monthly-group-legacy">Legacy AR (invoices &le; May 31, 2026)</th>
						<th colspan="2" class="ard-monthly-group-new">New AR (invoices &ge; Jun 1, 2026)</th>
					</tr>
					<tr>
						<th class="ard-num">Collected</th>
						<th class="ard-num">Adjustments</th>
						<th class="ard-num">Balance (EOM)</th>
						<th class="ard-num">Collected</th>
						<th class="ard-num">Adjustments</th>
					</tr>
				</thead>
				<tbody>${monthly_rows_html || '<tr><td colspan="6" class="ard-empty">No collection activity found.</td></tr>'}</tbody>
			</table>
		</div>
		${weekly_html}
	`);
}

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
    // (apply_filters sets the New AR > 0 default for the new mode.)
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

                let update_rows = function (rows) {
                    (rows || []).forEach(function (row) {
                        if (row.party === party) row.reconciliation_status = new_status;
                    });
                };
                if (page._ard_result)     update_rows(page._ard_result.rows);
                if (page._ard_all_result) update_rows(page._ard_all_result.rows);

                if (page._ard_all_mode) render_all_entities(page);
                else render_view(page);
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

function recon_cls_for(status) {
    if (status === 'Reconciled collecting money') return 'ard-recon-reconciled';
    if (status === 'Reconciled trouble collecting money') return 'ard-recon-trouble';
    if (status === 'Unreconciled') return 'ard-recon-unreconciled';
    if (status === 'Dispute') return 'ard-recon-dispute';
    if (status === 'Adjustment') return 'ard-recon-adjustment';
    return 'ard-recon-empty';
}

function apply_recon_select_class($select, status) {
    $select.removeClass('ard-recon-reconciled ard-recon-trouble ard-recon-unreconciled ard-recon-dispute ard-recon-adjustment ard-recon-empty');
    $select.addClass(recon_cls_for(status));
}

// ─── New AR Available Toggle ──────────────────────────────────────────────────

function handle_new_ar_click(page, $btn) {
    if (!page._ard_can_edit) {
        frappe.show_alert({ message: __("Account Manager role required to change New AR status."), indicator: 'red' }, 5);
        return;
    }

    let party   = $btn.data('party');
    let new_val = $btn.hasClass('ard-new-ar-active') ? 0 : 1;

    $btn.prop('disabled', true);

    frappe.call({
        method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.update_new_ar_available",
        args: { party: party, value: new_val },
        callback: function (r) {
            $btn.prop('disabled', false);
            if (r.message) {
                if (new_val) {
                    $btn.addClass('ard-new-ar-active').html('&#10003; New AR');
                } else {
                    $btn.removeClass('ard-new-ar-active').text('New AR');
                }
                let update = function (rows) {
                    (rows || []).forEach(function (row) {
                        if (row.party === party) row.new_ar_available = !!new_val;
                    });
                };
                if (page._ard_result)     update(page._ard_result.rows);
                if (page._ard_all_result) update(page._ard_all_result.rows);
                frappe.show_alert({ message: __("New AR status updated"), indicator: 'green' }, 3);
            }
        },
        error: function () {
            $btn.prop('disabled', false);
            frappe.show_alert({ message: __("Failed to update New AR status"), indicator: 'red' }, 5);
        }
    });
}

// ─── POC Update ───────────────────────────────────────────────────────────────

function handle_poc_change(page, $select) {
    if (!page._ard_can_edit) {
        $select.val($select.attr('data-current') || "");
        return;
    }
    let party   = $select.attr('data-party');
    let new_val = $select.val();
    let old_val = $select.attr('data-current') || "";
    $select.prop('disabled', true);
    frappe.call({
        method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.update_poc",
        args: { party: party, value: new_val },
        callback: function (r) {
            $select.prop('disabled', false);
            if (r.message) {
                frappe.show_alert({ message: __("POC updated"), indicator: 'green' }, 3);
                $select.attr('data-current', new_val);
                let update = function (rows) {
                    (rows || []).forEach(function (row) {
                        if (row.party === party) row.poc = new_val;
                    });
                };
                if (page._ard_result)     update(page._ard_result.rows);
                if (page._ard_all_result) update(page._ard_all_result.rows);
            }
        },
        error: function () {
            $select.prop('disabled', false);
            $select.val(old_val);
            frappe.show_alert({ message: __("Failed to update POC"), indicator: 'red' }, 5);
        }
    });
}

// ─── Notebox Update ─────────────────────────────────────────────────────────────

function handle_notebox_change(page, $input) {
    let old_val = $input.attr('data-current') || "";
    // contenteditable div — read visible text, normalise stray whitespace.
    let new_val = ($input.text() || "").replace(/ /g, " ").trim();

    if (!page._ard_can_edit) {
        $input.text(old_val);
        frappe.show_alert({ message: __("You do not have permission to edit notes."), indicator: 'red' }, 5);
        return;
    }

    // Nothing changed — don't hit the server.
    if (new_val === old_val) return;

    let party = $input.attr('data-party');

    frappe.call({
        method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.update_notebox",
        args: { party: party, value: new_val },
        callback: function (r) {
            if (r.message) {
                frappe.show_alert({ message: __("Note saved"), indicator: 'green' }, 2);
                $input.attr('data-current', new_val);
                // Persist into the loaded row data so re-renders and exports keep the note.
                let update = function (rows) {
                    (rows || []).forEach(function (row) {
                        if (row.party === party) row.notebox = new_val;
                    });
                };
                if (page._ard_result)     update(page._ard_result.rows);
                if (page._ard_all_result) update(page._ard_all_result.rows);
            }
        },
        error: function () {
            $input.text(old_val);
            frappe.show_alert({ message: __("Failed to save note"), indicator: 'red' }, 5);
        }
    });
}

// ─── Data Loading ─────────────────────────────────────────────────────────────

// Sync the "New AR > 0" filter state and its button UI together.
function set_new_ar_only(page, on) {
    page._ard_new_ar_only = !!on;
    let $btn = page.main.find('#ard-new-ar-only-btn');
    if (on) {
        $btn.text('✓ New AR > 0').addClass('ard-btn-active');
    } else {
        $btn.text('New AR > 0').removeClass('ard-btn-active');
    }
}

// Central refresh: routes to the consolidated view when "All Entities" is
// selected, otherwise loads the single selected company. Called on every
// filter change (no Apply button).
function apply_filters(page) {
    page._ard_excl_motley = false;
    // New AR mode opens pre-filtered to customers with New AR > 0 — what the
    // "New AR > 0" button used to require a click for.
    set_new_ar_only(page, page._ard_ar_mode === 'new');
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

    if (page._ard_new_ar_only) {
        let party_new_ar = {};
        display_rows.forEach(function (r) {
            if (!party_new_ar[r.party]) party_new_ar[r.party] = 0;
            if (!r.is_legacy && (r.posting_date || "") >= NEW_AR_START) {
                party_new_ar[r.party] += r.outstanding || 0;
            }
        });
        display_rows = display_rows.filter(function (r) {
            return (party_new_ar[r.party] || 0) > 1;
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
    apply_col_visibility(page);
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

var RECON_OPTIONS = [
    { value: "",                                    label: "—" },
    { value: "Reconciled collecting money",         label: "Reconciled collecting money" },
    { value: "Reconciled trouble collecting money", label: "Reconciled trouble collecting money" },
    { value: "Unreconciled",                        label: "Unreconciled" },
    { value: "Dispute",                             label: "Dispute" },
    { value: "Adjustment",                          label: "Adjustment" },
];

function build_recon_cell(page, party, status, readonly) {
    if (page._ard_can_edit) {
        let select_cls = "ard-recon-select " + recon_cls_for(status);
        let opts = RECON_OPTIONS.map(function (o) {
            return `<option value="${esc_attr(o.value)}" ${status === o.value ? "selected" : ""}>${esc(o.label)}</option>`;
        }).join("");
        return `
			<select class="${select_cls}"
				data-party="${esc_attr(party)}"
				data-current="${esc_attr(status)}">
				${opts}
			</select>
		`;
    }

    let badge_cls = "ard-recon-readonly " + recon_cls_for(status);
    let label = status || "—";
    return `<span class="${badge_cls}" title="Read-only — Account Manager role required to edit">${esc(label)}</span>`;
}

var POC_OPTIONS = [
    { value: "",        label: "—" },
    { value: "Company", label: "Company" },
    { value: "Nikki",   label: "Nikki" },
];

function build_poc_cell(page, party, poc, readonly) {
    if (page._ard_can_edit) {
        let opts = POC_OPTIONS.map(function (o) {
            return `<option value="${esc_attr(o.value)}" ${poc === o.value ? "selected" : ""}>${esc(o.label)}</option>`;
        }).join("");
        return `<select class="ard-poc-select" data-party="${esc_attr(party)}" data-current="${esc_attr(poc)}">${opts}</select>`;
    }
    return `<span class="ard-poc-readonly">${esc(poc || "—")}</span>`;
}

function build_notebox_cell(page, party, note) {
    let val = note || "";
    if (page._ard_can_edit) {
        // Editable free-text note. Uses a contenteditable div (not a textarea) so
        // the note flows to full height and prints cleanly in the PDF export.
        // Saves to the Customer master on blur, then persists in the row data so
        // it survives re-renders and rides along in every export.
        return `<div class="ard-notebox-input" contenteditable="true"
            data-party="${esc_attr(party)}" data-current="${esc_attr(val)}"
            data-placeholder="Add note…">${esc(val)}</div>`;
    }
    return `<div class="ard-notebox-readonly">${esc(val)}</div>`;
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
						${(split || show_legacy_col) ? `<th class="ard-th-num ard-col-legacy">Legacy AR</th><th class="ard-th-num ard-na-new">New AR</th>` : ``}
						<th class="ard-th-num ard-na-total">Total AR</th>
						<th class="ard-th-num ard-na-good">Total New AR on Good standing</th>
						<th class="ard-th-num ard-na-bad">Total New AR on Bad standing</th>
						<th class="ard-th-num ard-term-red">0-10 Days<br><small>left in terms</small></th>
						<th class="ard-th-num ard-term-amber">10-20 Days<br><small>left in terms</small></th>
						<th class="ard-th-num ard-term-green">20-30 Days<br><small>left in terms</small></th>`;
}

function na_total_cells(s, split, show_legacy_col, legacy_amt) {
    return `
					${split ? `<td class="ard-num ard-total-cell ard-col-legacy">${s.legacy_ar > 0 ? fmt_cur(s.legacy_ar) : "\u2014"}</td><td class="ard-num ard-total-cell ard-na-new">${s.new_ar > 0 ? fmt_cur(s.new_ar) : "\u2014"}</td>` : ``}
					${show_legacy_col ? `<td class="ard-num ard-total-cell ard-col-legacy">${legacy_amt > 0 ? fmt_cur(legacy_amt) : "\u2014"}</td><td class="ard-num ard-total-cell ard-na-new">${s.total > 0 ? fmt_cur(s.total) : "\u2014"}</td>` : ``}
					<td class="ard-num ard-total-cell ard-na-total">${fmt_cur(show_legacy_col ? (legacy_amt + s.total) : s.total)}</td>
					<td class="ard-num ard-total-cell ard-na-good">${s.good > 0 ? fmt_cur(s.good) : "\u2014"}</td>
					<td class="ard-num ard-total-cell ard-na-bad">${s.bad > 0 ? fmt_cur(s.bad) : "\u2014"}</td>
					<td class="ard-num ard-total-cell ard-term-red">${s.g1 > 0 ? fmt_cur(s.g1) : "\u2014"}</td>
					<td class="ard-num ard-total-cell ard-term-amber">${s.g2 > 0 ? fmt_cur(s.g2) : "\u2014"}</td>
					<td class="ard-num ard-total-cell ard-term-green">${s.g3 > 0 ? fmt_cur(s.g3) : "\u2014"}</td>`;
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
						${split ? `<td class="ard-num ard-col-legacy">${!is_new ? fmt_cur(amt) : "\u2014"}</td><td class="ard-num ard-na-new">${is_new ? fmt_cur(amt) : "\u2014"}</td>` : ``}
						${show_legacy_col ? `<td class="ard-num ard-col-legacy">${legacy ? fmt_cur(amt) : "\u2014"}</td><td class="ard-num ard-na-new">${legacy ? "\u2014" : fmt_cur(amt)}</td>` : ``}
						<td class="ard-num ard-na-total">${fmt_cur(amt)}</td>
						<td class="ard-num ard-na-good">${(!legacy && good) ? fmt_cur(amt) : "\u2014"}</td>
						<td class="ard-num ard-na-bad">${(!legacy && !good) ? fmt_cur(amt) : "\u2014"}</td>
						<td class="ard-range-cell ard-term-red">${g1 > 0 ? fmt_cur(g1) : "\u2014"}</td>
						<td class="ard-range-cell ard-term-amber">${g2 > 0 ? fmt_cur(g2) : "\u2014"}</td>
						<td class="ard-range-cell ard-term-green">${g3 > 0 ? fmt_cur(g3) : "\u2014"}</td>`;
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
                poc: row.poc || "",
                new_ar_available: !!row.new_ar_available,
                notebox: row.notebox || "",
                rows: []
            };
            customer_order.push(key);
        }
        customer_groups[key].rows.push(row);
    });
    customer_order.sort(function (a, b) {
        return (customer_groups[a].name || "").localeCompare(customer_groups[b].name || "");
    });

    let total_invoices = display_rows.length;
    let grand_legacy = display_rows.reduce(function (a, r) { return a + (r.is_legacy ? (r.outstanding || 0) : 0); }, 0);

    // ── Sheet-style header block: TOTALS row on top, group bands, then column headers ──
    let range_headers = ranges.map(function (r, idx) {
        return `<th class="ard-th-range ${range_status_class(idx)}">${r.label}<br><small>Days</small></th>`;
    }).join("");

    let range_total_cells = ranges.map(function (r, idx) {
        let cls = `ard-range-cell ${range_status_class(idx)}`;
        return `<td class="${cls} ard-total-cell">${view_totals[r.key] > 0 ? fmt_cur(view_totals[r.key]) : "\u2014"}</td>`;
    }).join("");

    let totals_cells = `
					<td class="ard-td-sticky ard-total-cell">TOTALS<div class="ard-invoice-count-compact" style="color:var(--ard-muted);font-size:11px;margin-top:2px;font-weight:400;">${esc(company)} &bull; ${total_invoices} inv &bull; ${customer_order.length} cust</div></td>
					<td class="ard-total-cell"></td>
					<td class="ard-total-cell"></td>
					<td class="ard-num ard-total-cell">${fmt_cur(view_totals.invoiced)}</td>
					<td class="ard-num ard-total-cell">${fmt_cur(view_totals.paid)}</td>
					<td class="ard-num ard-total-cell ard-outstanding">${fmt_cur(view_totals.outstanding)}</td>
					${show_terms ? na_total_cells(na_grand, split_ln, show_legacy_col, grand_legacy) : ``}
					${range_total_cells}
					<td class="ard-total-cell ard-td-new-ar"></td>
					<td class="ard-total-cell ard-td-notebox"></td>`;

    let band_row = "";
    if (show_terms) {
        let lead_cols = 6 + ((split_ln || show_legacy_col) ? 2 : 0) + 3;
        band_row = `
					<tr class="ard-band-row">
						<th colspan="${lead_cols}" class="ard-band-blank"></th>
						<th colspan="3" class="ard-band-terms">New AR on Terms</th>
						<th colspan="${ranges.length}" class="ard-band-overdue">OVERDUE NEW AR</th>
						<th colspan="2" class="ard-band-blank ard-band-trail"></th>
					</tr>`;
    }

    let html = `
		<div class="ard-table-wrap ard-newar-table ard-sheet">
			<table class="ard-table">
				<thead>
					<tr class="ard-totals-row ard-top-totals">${totals_cells}
					</tr>
					${band_row}
					<tr class="ard-head-row">
						<th class="ard-th-sticky">Customer</th>
						<th class="ard-th-recon">Recon Status</th>
						<th class="ard-th-poc">POC</th>
						<th class="ard-th-num">Invoiced</th>
						<th class="ard-th-num">Paid</th>
						<th class="ard-th-num">Outstanding</th>
						${show_terms ? na_header_cells(split_ln, show_legacy_col) : ``}
						${range_headers}
						<th class="ard-th-new-ar">New AR</th>
						<th class="ard-th-notebox">Notebox</th>
					</tr>
				</thead>
				<tbody>
	`;

    customer_order.forEach(function (party) {
        let group = customer_groups[party];

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
            return `<td class="${cls} ard-total-cell">${val > 0 ? fmt_cur(val) : "\u2014"}</td>`;
        }).join("");

        let recon_cell = build_recon_cell(page, group.party, group.recon_status, readonly);
        let poc_cell   = build_poc_cell(page, group.party, group.poc, readonly);

        let new_ar_active = group.new_ar_available;
        let new_ar_cell = page._ard_can_edit
            ? `<button class="ard-new-ar-btn${new_ar_active ? ' ard-new-ar-active' : ''}" data-party="${esc_attr(party)}">${new_ar_active ? '&#10003; New AR' : 'New AR'}</button>`
            : `<span class="ard-new-ar-btn${new_ar_active ? ' ard-new-ar-active' : ''}">${new_ar_active ? '&#10003; New AR' : 'New AR'}</span>`;

        html += `
			<tr class="ard-customer-group-row" data-party="${esc_attr(party)}">
				<td class="ard-td-sticky">
					<button class="ard-expand-btn" data-party="${esc_attr(party)}" title="Expand invoices">&#9654;</button><span class="ard-customer-group-name">${esc(group.name)}</span><button class="ard-copy-btn" data-party="${esc_attr(party)}" title="Copy this customer's summary">&#128203;</button>
					${group.name !== group.party ? `<div class="ard-customer-group-id">${esc(group.party)}</div>` : ""}
					<div class="ard-invoice-count-compact" style="color:var(--ard-muted);font-size:11px;margin-top:2px;">${group.rows.length} invoice(s)</div>
				</td>
				<td class="ard-td-recon">${recon_cell}</td>
				<td class="ard-td-poc">${poc_cell}</td>
				<td class="ard-num ard-total-cell">${fmt_cur(sub.invoiced)}</td>
				<td class="ard-num ard-total-cell">${fmt_cur(sub.paid)}</td>
				<td class="ard-num ard-total-cell ard-outstanding">${fmt_cur(sub.outstanding)}</td>
				${show_terms ? na_total_cells(na_sum(group.rows, na_anchor), split_ln, show_legacy_col, group_legacy) : ``}
				${sub_range_cells}
				<td class="ard-td-new-ar">${new_ar_cell}</td>
				<td class="ard-td-notebox">${build_notebox_cell(page, group.party, group.notebox)}</td>
			</tr>
		`;

        group.rows.forEach(function (row) {
            let status = get_row_status(row, ranges);
            let range_cells = ranges.map(function (r, idx) {
                let val = row[r.key] || 0;
                let cls = val > 0 ? `ard-range-cell ${range_status_class(idx)}` : "ard-range-cell ard-range-zero";
                return `<td class="${cls}">${val > 0 ? fmt_cur(val) : "\u2014"}</td>`;
            }).join("");

            html += `
				<tr class="ard-invoice-row" data-party="${esc_attr(row.party)}" style="display:none;">
					<td class="ard-td-sticky" style="padding-left:24px;">
						<a href="/app/sales-invoice/${esc(row.voucher_no)}" target="_blank" class="ard-link">${esc(row.voucher_no)}</a>
						<div class="ard-inv-meta">${show_company && row.company ? esc(row.company) + " &bull; " : ""}${fmt_date(row.posting_date)} &rarr; ${fmt_date(row.due_date)} <span class="ard-badge ${status.cls}">${status.label}</span></div>
					</td>
					<td></td>
					<td></td>
					<td class="ard-num">${fmt_cur(row.invoiced)}</td>
					<td class="ard-num">${fmt_cur(row.paid)}</td>
					<td class="ard-num ard-outstanding">${fmt_cur(row.outstanding)}</td>
					${show_terms ? na_invoice_cells(row, na_anchor, split_ln, show_legacy_col) : ``}
					${range_cells}
					<td></td>
					<td></td>
				</tr>
			`;
        });
    });

    html += `
				</tbody>
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
        // Mark letter cells for detail columns so they hide/show together.
        let $ths = $headRow.children();
        let strip = '<th class="ard-grid-corner"></th>';
        $ths.each(function (i) {
            let extra = $(this).hasClass('ard-detail-col') ? ' ard-detail-letter' : '';
            strip += '<th class="ard-grid-col' + extra + '">' + col_letter(i) + '</th>';
        });
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
    apply_col_visibility(page);
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
    // On terms — bucket by days LEFT until the due date, matching the recon
    // sheet: 0-10 left = urgent (red), 10-20 left = amber, 20-30 left = green.
    let left = diff_days(row.due_date, report_date);
    if (left === null || left < 0) left = 0;
    let bkey = left <= 10 ? "g1" : left <= 20 ? "g2" : "g3";
    return { section: "good", bkey: bkey, days: left };
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

    // Print CSS: landscape, compact cells, sheet-only output — the PDF mirrors the
    // recon Google Sheet: a purple logo banner, then the spreadsheet table, one row
    // per customer (invoice rows collapsed), no summary cards / projection / aging bar.
    let print_css =
        'body{padding:0;margin:0;background:#fff;}' +
        // Kill centering/max-width so content starts at the left edge of the page
        '.ard-container{max-width:none!important;margin:0!important;padding:4px 6px!important;}' +
        '#ard-pdf-page{padding:0;}' +
        // Purple logo banner at the very top (matches the Google Sheet header)
        '.ard-pdf-logo-banner{background:#5a1a9e;padding:12px 18px;margin:0 0 8px;text-align:left;}' +
        '.ard-pdf-logo-banner img{height:64px;width:auto;display:inline-block;}' +
        // Hide interactive UI and the non-sheet dashboard sections
        '.ard-filter-bar,.ard-copy-btn,.ard-expand-btn,.ard-btn-secondary,.ard-btn-danger,' +
        '.ard-header-right,.ard-btn-group,' +
        '#ard-summary-section,#ard-projection-section,#ard-aging-section{display:none!important;}' +
        // Sheet shows one row per customer — keep invoice detail rows collapsed
        '.ard-invoice-row{display:none!important;}' +
        // Interactive controls print as plain text (recon / POC / New AR / Notebox)
        '.ard-recon-select,.ard-poc-select{border:none!important;background:transparent!important;' +
          '-webkit-appearance:none;appearance:none;padding:0!important;}' +
        '.ard-new-ar-btn{border:none!important;background:transparent!important;padding:0!important;' +
          'color:#202124!important;font-weight:600;}' +
        '.ard-notebox-input,.ard-notebox-readonly{border:none!important;background:transparent!important;' +
          'padding:0!important;min-height:0!important;min-width:120px;}' +
        // Notes may be long — let the Notebox column wrap instead of clipping
        '.ard-td-notebox,.ard-td-notebox *{white-space:normal!important;}' +
        '.ard-header{padding:4px 0!important;margin-bottom:4px!important;}' +
        // Remove all scroll/height constraints so scrollWidth is accurate
        '.ard-table-wrap{overflow:visible!important;max-height:none!important;height:auto!important;' +
          'border:none!important;box-shadow:none!important;border-radius:0!important;}' +
        '.ard-table{width:auto!important;}' +
        // Tight cells
        '.ard-table th,.ard-table td{font-size:7px!important;padding:1px 3px!important;white-space:nowrap;}' +
        // Neutralise sticky positioning so nothing overlaps when laid flat
        '.ard-th-sticky,.ard-td-sticky,.ard-grid-rownum,.ard-grid-corner,' +
        '.ard-table thead th{position:static!important;left:auto!important;top:auto!important;box-shadow:none!important;}' +
        // Keep the sheet column tints in the printed PDF
        '*{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important;}' +
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

    // Write the print document once we have the logo (embedded as a data URI so it
    // is guaranteed to render — no dependency on the blank window resolving /files).
    function write_doc(logo_src) {
        let logo_banner = logo_src
            ? '<div class="ard-pdf-logo-banner"><img src="' + logo_src + '" alt="Motley Terpz"></div>'
            : '';
        w.document.write(
            '<!doctype html><html><head><meta charset="utf-8"><title>AR Aging Report</title>' + head +
            '<style>' + print_css + '</style>' +
            '<scr' + 'ipt>' + fit_script + '</scr' + 'ipt>' +
            '</head><body><div id="ard-pdf-page">' + logo_banner + container.outerHTML + '</div></body></html>'
        );
        w.document.close();
        w.focus();
    }

    // Convert the (same-origin) logo to a data URI via canvas, then write. If it
    // can't be loaded for any reason, still produce the PDF without the banner.
    let img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = function () {
        try {
            let canvas = document.createElement("canvas");
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            canvas.getContext("2d").drawImage(img, 0, 0);
            write_doc(canvas.toDataURL("image/png"));
        } catch (e) {
            write_doc(window.location.origin + '/files/Motley-Terpz-Web-Logo.png');
        }
    };
    img.onerror = function () { write_doc(null); };
    img.src = window.location.origin + '/files/Motley-Terpz-Web-Logo.png';
}

// Show/hide the export wrap based on whether data is on screen.
// The sheet layout has no detail columns, so the Hide Columns D–K button stays hidden.
function show_export_buttons(page, has_rows) {
    page.main.find('#ard-export-dd, #ard-new-ar-only-btn').toggle(!!has_rows);
    if (!has_rows) page.main.find('#ard-export-menu').hide();
}

function update_hide_cols_btn(page) {
    let $btn = page.main.find('#ard-hide-cols-btn');
    if (page._ard_cols_hidden) {
        $btn.html('Show Columns D&ndash;K').removeClass('ard-btn-active');
    } else {
        $btn.html('&#9679; Hide Columns D&ndash;K').addClass('ard-btn-active');
    }
}

function apply_col_visibility(page) {
    page.main.find('#ard-data-area').toggleClass('ard-detail-hidden', !!page._ard_cols_hidden);
}

// ─── Excel Export ─────────────────────────────────────────────────────────────
// Format: Customer | Reconciliation Status | Legacy AR Outstanding | New AR Outstanding | Total
// One summary row per customer. Backend generates a real .xlsx via openpyxl.

function export_excel(page, use_all) {
    let res, display_rows, company;

    if (use_all) {
        if (!page._ard_all_result) {
            frappe.show_alert({ message: __("Load the All Entities view first to export the whole dashboard"), indicator: "orange" }, 5);
            return;
        }
        res = page._ard_all_result;
        company = "All_Entities";
        display_rows = filter_rows(page, res, page._ard_excl_motley);
    } else {
        res = current_result(page);
        if (!res) return;
        company = res.company;
        display_rows = current_display_rows(page);
    }

    if (!display_rows.length) {
        frappe.show_alert({ message: __("No rows to export"), indicator: "orange" }, 3);
        return;
    }

    let ranges = res.ranges || [];
    let cols_hidden  = !!page._ard_cols_hidden;
    let show_terms   = page._ard_ar_mode === 'new' || page._ard_ar_mode === 'all';
    let split_ln     = page._ard_ar_mode === 'all';
    let show_legacy_col = page._ard_ar_mode === 'new';
    let show_company = !!use_all;
    let na_anchor    = show_terms ? get_report_date(page) : null;

    // ── header row ──────────────────────────────────────────────────────────────
    // Excel export is always a per-customer summary (one row per customer),
    // regardless of the on-screen "Hide Columns D–K" toggle. Per-invoice-only
    // columns (Invoice No., Type, dates, Status, Entity) are omitted.
    let header = ["Customer", "Recon Status", "POC", "Invoiced", "Paid", "Outstanding"];
    if (show_terms) {
        if (split_ln)        { header.push("Legacy AR", "New AR"); }
        if (show_legacy_col) { header.push("Legacy AR", "New AR"); }
        header.push("Total AR", "Total New AR on Good standing", "Total New AR on Bad standing",
            "0-10 Days left in terms", "10-20 Days left in terms", "20-30 Days left in terms");
    }
    ranges.forEach(function (r) { header.push(r.label + " Days"); });
    header.push("New AR");
    header.push("Notebox");

    // ── group rows by customer ───────────────────────────────────────────────────
    let customer_order = [], customer_groups = {};
    display_rows.forEach(function (row) {
        let key = row.party;
        if (!customer_groups[key]) {
            customer_groups[key] = {
                name: row.customer_name || row.party, party: row.party,
                recon_status: row.reconciliation_status || "",
                poc: row.poc || "",
                new_ar_available: !!row.new_ar_available,
                notebox: row.notebox || "",
                rows: []
            };
            customer_order.push(key);
        }
        customer_groups[key].rows.push(row);
    });
    customer_order.sort(function (a, b) {
        return (customer_groups[a].name || "").toLowerCase().localeCompare((customer_groups[b].name || "").toLowerCase());
    });

    // ── build data rows ──────────────────────────────────────────────────────────
    let xrows = [header];
    let grand = { invoiced: 0, paid: 0, outstanding: 0 };
    ranges.forEach(function (r) { grand[r.key] = 0; });
    let grand_legacy = 0;
    let grand_na = show_terms ? { legacy_ar: 0, new_ar: 0, total: 0, good: 0, bad: 0, g1: 0, g2: 0, g3: 0 } : null;

    customer_order.forEach(function (party) {
        let group = customer_groups[party];
        let sub = { invoiced: 0, paid: 0, outstanding: 0 };
        let group_legacy = 0;
        ranges.forEach(function (r) { sub[r.key] = 0; });
        let group_na = show_terms ? { legacy_ar: 0, new_ar: 0, total: 0, good: 0, bad: 0, g1: 0, g2: 0, g3: 0 } : null;

        group.rows.forEach(function (row) {
            sub.invoiced    += row.invoiced    || 0;
            sub.paid        += row.paid        || 0;
            sub.outstanding += row.outstanding || 0;
            if (row.is_legacy) group_legacy += row.outstanding || 0;
            ranges.forEach(function (r) { sub[r.key] += row[r.key] || 0; });
            if (show_terms && na_anchor && !row.is_legacy) {
                let info = classify_ar_row(row, na_anchor);
                let amt  = row.outstanding || 0;
                if (amt <= 0) return;
                let is_new = (row.posting_date || "") >= NEW_AR_START;
                group_na.total     += amt;
                group_na.legacy_ar += !is_new ? amt : 0;
                group_na.new_ar    += is_new  ? amt : 0;
                let good = info.section === "good";
                group_na.good += good  ? amt : 0;
                group_na.bad  += !good ? amt : 0;
                group_na.g1   += (good && info.bkey === "g1") ? amt : 0;
                group_na.g2   += (good && info.bkey === "g2") ? amt : 0;
                group_na.g3   += (good && info.bkey === "g3") ? amt : 0;
            }
        });

        // accumulate grand totals
        grand.invoiced    += sub.invoiced;
        grand.paid        += sub.paid;
        grand.outstanding += sub.outstanding;
        grand_legacy      += group_legacy;
        ranges.forEach(function (r) { grand[r.key] += sub[r.key]; });
        if (grand_na && group_na) {
            ['legacy_ar','new_ar','total','good','bad','g1','g2','g3'].forEach(function (k) { grand_na[k] += group_na[k]; });
        }

        // one row per customer (always — collapsed summary)
        let r = [group.name, group.recon_status, group.poc, sub.invoiced, sub.paid, sub.outstanding];
        if (show_terms && group_na) {
            if (split_ln)        { r.push(group_na.legacy_ar, group_na.new_ar); }
            if (show_legacy_col) { r.push(group_legacy, group_na.total); }
            r.push(group_na.total, group_na.good, group_na.bad, group_na.g1, group_na.g2, group_na.g3);
        }
        ranges.forEach(function (rng) { r.push(sub[rng.key] || 0); });
        r.push(group.new_ar_available ? "Yes" : "");
        r.push(group.notebox || "");
        xrows.push(r);
    });

    // ── totals row ───────────────────────────────────────────────────────────────
    let totals = ["TOTAL", "", "", grand.invoiced, grand.paid, grand.outstanding];
    if (grand_na) {
        if (split_ln)        { totals.push(grand_na.legacy_ar, grand_na.new_ar); }
        if (show_legacy_col) { totals.push(grand_legacy, grand_na.total); }
        totals.push(grand_na.total, grand_na.good, grand_na.bad, grand_na.g1, grand_na.g2, grand_na.g3);
    }
    ranges.forEach(function (r) { totals.push(grand[r.key]); });
    totals.push("");  // New AR
    totals.push("");  // Notebox
    xrows.push(totals);

    let date_str = page.main.find('#ard-report-date').val() || frappe.datetime.get_today();
    let mode_tag = page._ard_ar_mode === 'legacy' ? 'Legacy' : (page._ard_ar_mode === 'new' ? 'New' : 'All');
    let filename = "AR_Summary_" + mode_tag + "_" + company.replace(/\s+/g, "_") + "_" + date_str + ".xlsx";

    frappe.call({
        method: "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.export_ar_excel_data",
        args: { rows_json: JSON.stringify(xrows), filename: filename },
        callback: function (r) {
            if (!r.message) return;
            let bytes = atob(r.message.data);
            let ab = new ArrayBuffer(bytes.length);
            let ia = new Uint8Array(ab);
            for (let i = 0; i < bytes.length; i++) ia[i] = bytes.charCodeAt(i);
            let blob = new Blob([ab], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
            let url = URL.createObjectURL(blob);
            let a = document.createElement("a");
            a.href = url;
            a.download = r.message.filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }
    });
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
