frappe.pages["stock-summary"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Stock Summary",
        single_column: true,
    });

    page.main.html(`
        <div class="stock-summary-container">
            <div class="stock-summary-header">
                <div class="header-icon">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                        <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                        <line x1="12" y1="22.08" x2="12" y2="12"/>
                    </svg>
                </div>
                <div>
                    <h2 class="header-title">Stock Summary</h2>
                    <p class="header-subtitle">Item Group wise stock overview from Stock Balance Report</p>
                </div>
            </div>
            </div>
            
            <div class="stock-summary-filters">
                <div class="filter-group">
                    <div class="filter-wrapper" id="filter-from-date"></div>
                    <div class="filter-wrapper" id="filter-to-date"></div>
                    <div class="filter-action-wrapper">
                        <div class="control-label">&nbsp;</div>
                        <button class="btn btn-primary btn-refresh-custom">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M23 4v6h-6"></path>
                                <path d="M1 20v-6h6"></path>
                                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                            </svg>
                            Refresh
                        </button>
                    </div>
                </div>
            </div>

            <div id="stock-summary-cards" class="summary-cards"></div>
            <div id="stock-summary-table" class="summary-table-wrap">
                <div class="loading-state">
                    <div class="spinner"></div>
                    <p>Loading stock data...</p>
                </div>
            </div>
        </div>
    `);

    // Default dates
    let today = frappe.datetime.get_today();
    let last_month = frappe.datetime.add_months(today, -1);

    // Create custom filters
    page.custom_filters = {};

    let make_filter = (parent_selector, fieldname, label, default_value) => {
        let control = frappe.ui.form.make_control({
            parent: page.main.find(parent_selector),
            df: {
                fieldname: fieldname,
                label: label,
                fieldtype: "Date",
                default: default_value,
                placeholder: label,
                change: function () {
                    load_stock_summary(page);
                },
            },
            render_input: true,
        });
        control.set_value(default_value);
        page.custom_filters[fieldname] = control;
    };

    make_filter("#filter-from-date", "from_date", __("From Date"), last_month);
    make_filter("#filter-to-date", "to_date", __("To Date"), today);

    // Bind refresh button
    page.main.find(".btn-refresh-custom").on("click", function() {
        load_stock_summary(page);
    });

    load_stock_summary(page);
};

function load_stock_summary(page) {
    let table_area = page.main.find("#stock-summary-table");
    let cards_area = page.main.find("#stock-summary-cards");
    
    // Get values from custom filters
    let from_date = page.custom_filters.from_date.get_value();
    let to_date = page.custom_filters.to_date.get_value();

    table_area.html(`
        <div class="loading-state">
            <div class="spinner"></div>
            <p>Loading stock data...</p>
        </div>
    `);
    cards_area.html("");

    frappe.call({
        method: "cannabis_management.cannabis_management.page.stock_summary.stock_summary.get_stock_summary",
        args: {
            from_date: from_date,
            to_date: to_date
        },
        callback: function (r) {
            if (r.message && r.message.length) {
                render_summary(page, r.message);
            } else {
                table_area.html(`
                    <div class="empty-state">
                        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#d1d5db"
                             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                            <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                            <line x1="12" y1="22.08" x2="12" y2="12"/>
                        </svg>
                        <h3>No Data Found</h3>
                        <p>No warehouses configured in <strong>Stock Summary Setting</strong> or no stock entries found for the configured warehouses within the selected date range.</p>
                        <a href="/app/stock-summary-setting" class="btn btn-primary btn-sm mt-3">
                            Configure Warehouses
                        </a>
                    </div>
                `);
                cards_area.html("");
            }
        },
    });
}

function render_summary(page, data) {
    let total_balance = 0;
    let total_reserved = 0;
    let total_available = 0;

    data.forEach((row) => {
        total_balance += row.balance_qty;
        total_reserved += row.reserved_qty;
        total_available += row.available_qty;
    });

    // Summary cards
    page.main.find("#stock-summary-cards").html(`
        <div class="summary-card card-balance">
            <div class="card-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="1" y="3" width="15" height="13"/>
                    <polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/>
                    <circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>
                </svg>
            </div>
            <div class="card-content">
                <span class="card-label">Total Balance Qty</span>
                <span class="card-value">${format_number(total_balance)}</span>
            </div>
        </div>
        <div class="summary-card card-reserved">
            <div class="card-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
            </div>
            <div class="card-content">
                <span class="card-label">Total Reserved Qty</span>
                <span class="card-value">${format_number(total_reserved)}</span>
            </div>
        </div>
        <div class="summary-card card-available">
            <div class="card-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
            </div>
            <div class="card-content">
                <span class="card-label">Available for Sale</span>
                <span class="card-value">${format_number(total_available)}</span>
            </div>
        </div>
    `);

    // Table
    let rows_html = "";
    data.forEach((row, idx) => {
        rows_html += `
            <tr class="data-row ${idx % 2 === 0 ? 'row-even' : 'row-odd'}">
                <td class="col-index">${idx + 1}</td>
                <td class="col-group">${frappe.utils.escape_html(row.item_group)}</td>
                <td class="col-number">${format_number(row.balance_qty)}</td>
                <td class="col-number">${format_number(row.reserved_qty)}</td>
                <td class="col-number col-available">${format_number(row.available_qty)}</td>
            </tr>
        `;
    });

    page.main.find("#stock-summary-table").html(`
        <table class="stock-table">
            <thead>
                <tr>
                    <th class="col-index">#</th>
                    <th class="col-group">Item Group</th>
                    <th class="col-number">Balance Qty</th>
                    <th class="col-number">Reserved Qty</th>
                    <th class="col-number">Available for Sale</th>
                </tr>
            </thead>
            <tbody>
                ${rows_html}
            </tbody>
            <tfoot>
                <tr class="totals-row">
                    <td class="col-index"></td>
                    <td class="col-group"><strong>Total</strong></td>
                    <td class="col-number"><strong>${format_number(total_balance)}</strong></td>
                    <td class="col-number"><strong>${format_number(total_reserved)}</strong></td>
                    <td class="col-number col-available"><strong>${format_number(total_available)}</strong></td>
                </tr>
            </tfoot>
        </table>
    `);
}

function format_number(val) {
    return (val || 0).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}
