frappe.pages["payable-summary"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Payable Summary",
        single_column: true,
    });

    // Default date = today
    let today = frappe.datetime.get_today();

    page.main.html(`
        <div class="receivable-summary-container">
            <div class="receivable-summary-header">
                <div class="rs-header-icon">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                        <polyline points="10 9 9 9 8 9"></polyline>
                    </svg>
                </div>
                <div>
                    <h2 class="rs-header-title">Payable Summary</h2>
                    <p class="rs-header-subtitle">Accounts Payable aging overview — Outstanding by party</p>
                </div>
            </div>

            <div class="rs-filter-bar">
                <div class="rs-filter-group">
                    <label for="rs-company-select">Company</label>
                    <select id="rs-company-select"></select>
                </div>
                <div class="rs-filter-group">
                    <label for="rs-date-input">Report Date</label>
                    <input type="date" id="rs-date-input" value="${today}" />
                </div>
                <div class="rs-filter-group">
                    <label for="rs-based-on-input">Ageing Based On</label>
                    <select id="rs-based-on-input">
                        <option value="Due Date">Due Date</option>
                        <option value="Posting Date">Posting Date</option>
                    </select>
                </div>
                <div class="rs-filter-group">
                    <label for="rs-ageing-by-input">Ageing By</label>
                    <select id="rs-ageing-by-input">
                        <option value="Report Date">Report Date</option>
                        <option value="Today Date">Today's Date</option>
                    </select>
                </div>
                <button class="rs-apply-btn" id="rs-apply-btn">Apply</button>
            </div>

            <div id="rs-summary-cards" class="rs-summary-cards"></div>

            <div id="rs-table-area" class="rs-table-wrap">
                <div class="rs-loading-state">
                    <div class="rs-spinner"></div>
                    <p>Loading payable data...</p>
                </div>
            </div>
        </div>
    `);

    // Load companies into dropdown
    frappe.call({
        method: "cannabis_management.cannabis_management.page.payable_summary.payable_summary.get_companies",
        callback: function (r) {
            let $sel = page.main.find("#rs-company-select");
            let default_company = frappe.defaults.get_user_default("Company") || "";
            (r.message || []).forEach(function (co) {
                let selected = co === default_company ? "selected" : "";
                $sel.append(`<option value="${frappe.utils.escape_html(co)}" ${selected}>${frappe.utils.escape_html(co)}</option>`);
            });
            load_payable_data(page);
        },
    });

    // Refresh button
    page.set_primary_action(__("Refresh"), function () {
        load_payable_data(page);
    }, "refresh");

    // Apply button click
    page.main.find("#rs-apply-btn").on("click", function () {
        load_payable_data(page);
    });

    // Enter key on date input
    page.main.find("#rs-date-input").on("keypress", function (e) {
        if (e.which === 13) {
            load_payable_data(page);
        }
    });

    // Trigger refresh on select change
    page.main.find("#rs-company-select, #rs-based-on-input, #rs-ageing-by-input").on("change", function() {
        load_payable_data(page);
    });
};

function load_payable_data(page) {
    let table_area = page.main.find("#rs-table-area");
    let cards_area = page.main.find("#rs-summary-cards");
    let company = page.main.find("#rs-company-select").val();
    let report_date = page.main.find("#rs-date-input").val();
    let ageing_based_on = page.main.find("#rs-based-on-input").val();
    let calculate_ageing_with = page.main.find("#rs-ageing-by-input").val();

    table_area.html(`
        <div class="rs-loading-state">
            <div class="rs-spinner"></div>
            <p>Loading payable data...</p>
        </div>
    `);
    cards_area.html("");

    frappe.call({
        method: "cannabis_management.cannabis_management.page.payable_summary.payable_summary.get_payable_summary",
        args: {
            company: company,
            report_date: report_date,
            ageing_based_on: ageing_based_on,
            calculate_ageing_with: calculate_ageing_with
        },
        callback: function (r) {
            if (r.message && r.message.length) {
                render_payable_summary(page, r.message);
            } else {
                table_area.html(`
                    <div class="rs-empty-state">
                        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#c4b5fd"
                             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                            <line x1="2" y1="7" x2="22" y2="7"/>
                            <line x1="12" y1="17" x2="12" y2="21"/>
                            <line x1="8" y1="21" x2="16" y2="21"/>
                        </svg>
                        <h3>No Payable Data</h3>
                        <p>No outstanding payables found for the selected date. Try a different report date.</p>
                    </div>
                `);
                cards_area.html("");
            }
        },
        error: function () {
            table_area.html(`
                <div class="rs-empty-state">
                    <h3>Error Loading Data</h3>
                    <p>Could not fetch payable summary. Please check the console for details.</p>
                </div>
            `);
        },
    });
}

function render_payable_summary(page, data) {
    let totals = {
        outstanding: 0,
        range1: 0,
        range2: 0,
        range3: 0,
        range4: 0,
        range5: 0,
    };

    data.forEach((row) => {
        totals.outstanding += row.outstanding || 0;
        totals.range1 += row.range1 || 0;
        totals.range2 += row.range2 || 0;
        totals.range3 += row.range3 || 0;
        totals.range4 += row.range4 || 0;
        totals.range5 += row.range5 || 0;
    });

    // Summary cards
    page.main.find("#rs-summary-cards").html(`
        <div class="rs-card rs-card-outstanding">
            <span class="rs-card-label">Outstanding</span>
            <span class="rs-card-value">${format_currency_val(totals.outstanding)}</span>
        </div>
        <div class="rs-card rs-card-range1">
            <span class="rs-card-label">0 – 30</span>
            <span class="rs-card-value">${format_currency_val(totals.range1)}</span>
        </div>
        <div class="rs-card rs-card-range2">
            <span class="rs-card-label">31 – 60</span>
            <span class="rs-card-value">${format_currency_val(totals.range2)}</span>
        </div>
        <div class="rs-card rs-card-range3">
            <span class="rs-card-label">61 – 90</span>
            <span class="rs-card-value">${format_currency_val(totals.range3)}</span>
        </div>
        <div class="rs-card rs-card-range4">
            <span class="rs-card-label">91 – 120</span>
            <span class="rs-card-value">${format_currency_val(totals.range4)}</span>
        </div>
        <div class="rs-card rs-card-range5">
            <span class="rs-card-label">120 +</span>
            <span class="rs-card-value">${format_currency_val(totals.range5)}</span>
        </div>
    `);

    // Build table rows
    let rows_html = "";
    data.forEach((row, idx) => {
        rows_html += `
            <tr class="${idx % 2 === 0 ? 'rs-row-even' : 'rs-row-odd'}">
                <td class="rs-col-index">${idx + 1}</td>
                <td class="rs-col-party">${frappe.utils.escape_html(row.party)}</td>
                <td class="rs-col-number rs-col-outstanding">${format_currency_val(row.outstanding)}</td>
                <td class="rs-col-number">${format_currency_val(row.range1)}</td>
                <td class="rs-col-number">${format_currency_val(row.range2)}</td>
                <td class="rs-col-number">${format_currency_val(row.range3)}</td>
                <td class="rs-col-number">${format_currency_val(row.range4)}</td>
                <td class="rs-col-number rs-col-range5">${format_currency_val(row.range5)}</td>
            </tr>
        `;
    });

    page.main.find("#rs-table-area").html(`
        <table class="rs-table">
            <thead>
                <tr>
                    <th class="rs-col-index">#</th>
                    <th class="rs-col-party">Party</th>
                    <th class="rs-col-number">Outstanding</th>
                    <th class="rs-col-number">0-30</th>
                    <th class="rs-col-number">31-60</th>
                    <th class="rs-col-number">61-90</th>
                    <th class="rs-col-number">91-120</th>
                    <th class="rs-col-number">120+</th>
                </tr>
            </thead>
            <tbody>
                ${rows_html}
            </tbody>
            <tfoot>
                <tr class="rs-totals-row">
                    <td class="rs-col-index"></td>
                    <td class="rs-col-party"><strong>Total</strong></td>
                    <td class="rs-col-number rs-col-outstanding"><strong>${format_currency_val(totals.outstanding)}</strong></td>
                    <td class="rs-col-number"><strong>${format_currency_val(totals.range1)}</strong></td>
                    <td class="rs-col-number"><strong>${format_currency_val(totals.range2)}</strong></td>
                    <td class="rs-col-number"><strong>${format_currency_val(totals.range3)}</strong></td>
                    <td class="rs-col-number"><strong>${format_currency_val(totals.range4)}</strong></td>
                    <td class="rs-col-number rs-col-range5"><strong>${format_currency_val(totals.range5)}</strong></td>
                </tr>
            </tfoot>
        </table>
    `);
}

function format_currency_val(val) {
    return "$" + (val || 0).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}