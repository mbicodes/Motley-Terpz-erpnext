frappe.pages["sales-summary"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Sales Summary",
        single_column: true,
    });

    // Default dates
    let today = frappe.datetime.get_today();
    let month_start = frappe.datetime.get_today().substring(0, 8) + "01";

    page.main.html(`
        <div class="receivable-summary-container">
            <div class="receivable-summary-header">
                <div class="rs-header-icon" style="background: linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%); box-shadow: 0 4px 14px rgba(139, 92, 246, 0.35);">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="12" y1="1" x2="12" y2="23"></line>
                        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                    </svg>
                </div>
                <div>
                    <h2 class="rs-header-title">Sales Summary</h2>
                    <p class="rs-header-subtitle">Item-wise Sales Register overview — Grouped by Item Group</p>
                </div>
            </div>

            <div class="rs-filter-bar">
                <div class="rs-filter-group">
                    <label for="rs-from-date-input">From Date</label>
                    <input type="date" id="rs-from-date-input" value="${month_start}" />
                </div>
                <div class="rs-filter-group">
                    <label for="rs-to-date-input">To Date</label>
                    <input type="date" id="rs-to-date-input" value="${today}" />
                </div>
                <button class="rs-apply-btn" id="rs-apply-btn" style="background: linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%); box-shadow: 0 2px 8px rgba(139, 92, 246, 0.25);">Apply</button>
            </div>

            <div id="rs-summary-cards" class="rs-summary-cards"></div>

            <div id="rs-table-area" class="rs-table-wrap">
                <div class="rs-loading-state">
                    <div class="rs-spinner" style="border-top-color: #8b5cf6;"></div>
                    <p>Loading sales data...</p>
                </div>
            </div>
        </div>
    `);

    // Refresh button
    page.set_primary_action(__("Refresh"), function () {
        load_sales_data(page);
    }, "refresh");

    // Apply button click
    page.main.find("#rs-apply-btn").on("click", function () {
        load_sales_data(page);
    });

    // Enter key on date inputs
    page.main.find("#rs-from-date-input, #rs-to-date-input").on("keypress", function (e) {
        if (e.which === 13) {
            load_sales_data(page);
        }
    });

    load_sales_data(page);
};

function load_sales_data(page) {
    let table_area = page.main.find("#rs-table-area");
    let cards_area = page.main.find("#rs-summary-cards");
    let from_date = page.main.find("#rs-from-date-input").val();
    let to_date = page.main.find("#rs-to-date-input").val();

    table_area.html(`
        <div class="rs-loading-state">
            <div class="rs-spinner" style="border-top-color: #8b5cf6;"></div>
            <p>Loading sales data...</p>
        </div>
    `);
    cards_area.html("");

    frappe.call({
        method: "cannabis_management.cannabis_management.page.sales_summary.sales_summary.get_sales_summary",
        args: {
            from_date: from_date,
            to_date: to_date
        },
        callback: function (r) {
            if (r.message && r.message.length) {
                render_sales_summary(page, r.message);
            } else {
                table_area.html(`
                    <div class="rs-empty-state">
                        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#ddd6fe"
                             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                            <line x1="2" y1="7" x2="22" y2="7"/>
                            <line x1="12" y1="17" x2="12" y2="21"/>
                            <line x1="8" y1="21" x2="16" y2="21"/>
                        </svg>
                        <h3>No Sales Data</h3>
                        <p>No sales found for the selected period.</p>
                    </div>
                `);
                cards_area.html("");
            }
        },
        error: function () {
            table_area.html(`
                <div class="rs-empty-state">
                    <h3>Error Loading Data</h3>
                    <p>Could not fetch sales summary. Please check the console for details.</p>
                </div>
            `);
        },
    });
}

function render_sales_summary(page, data) {
    let totals = {
        stock_qty: 0,
        amount: 0
    };

    data.forEach((row) => {
        totals.stock_qty += row.stock_qty || 0;
        totals.amount += row.amount || 0;
    });

    // Summary cards
    page.main.find("#rs-summary-cards").html(`
        <div class="rs-card" style="border-left: 4px solid #8b5cf6;">
            <span class="rs-card-label" style="color: #8b5cf6;">Total Sold Qty</span>
            <span class="rs-card-value">${format_qty_val(totals.stock_qty)}</span>
        </div>
        <div class="rs-card" style="border-left: 4px solid #7c3aed;">
            <span class="rs-card-label" style="color: #7c3aed;">Total Sold Amount</span>
            <span class="rs-card-value">${format_currency_val(totals.amount)}</span>
        </div>
    `);

    // Build table rows
    let rows_html = "";
    data.forEach((row, idx) => {
        rows_html += `
            <tr class="${idx % 2 === 0 ? 'rs-row-even' : 'rs-row-odd'}">
                <td class="rs-col-index">${idx + 1}</td>
                <td class="rs-col-party">${frappe.utils.escape_html(row.item_group)}</td>
                <td class="rs-col-number">${format_qty_val(row.stock_qty)}</td>
                <td class="rs-col-number rs-col-outstanding" style="color: #8b5cf6;">${format_currency_val(row.amount)}</td>
            </tr>
        `;
    });

    page.main.find("#rs-table-area").html(`
        <table class="rs-table">
            <thead style="background: linear-gradient(135deg, #8b5cf6 0%, #a78bfa 100%);">
                <tr>
                    <th class="rs-col-index">#</th>
                    <th class="rs-col-party">Item Group</th>
                    <th class="rs-col-number">Sold Qty</th>
                    <th class="rs-col-number">Sold Amount</th>
                </tr>
            </thead>
            <tbody>
                ${rows_html}
            </tbody>
            <tfoot>
                <tr class="rs-totals-row" style="border-top: 2px solid #c4b5fd;">
                    <td class="rs-col-index"></td>
                    <td class="rs-col-party"><strong>Total</strong></td>
                    <td class="rs-col-number"><strong>${format_qty_val(totals.stock_qty)}</strong></td>
                    <td class="rs-col-number rs-col-outstanding" style="color: #8b5cf6;"><strong>${format_currency_val(totals.amount)}</strong></td>
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

function format_qty_val(val) {
    return (val || 0).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}