frappe.pages["day-book-dashboard"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Cash and Bank Position",
        single_column: true,
    });

    let today = frappe.datetime.get_today();
    let from_date = today; 

    page.main.html(`
        <div class="day-book-container">
            <div class="db-header">
                <div class="db-header-icon">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                    </svg>
                </div>
                <div>
                    <h2 class="db-header-title">Cash and Bank Position</h2>
                    <p class="db-header-subtitle">Daily cash and bank position overview</p>
                </div>
            </div>

            <div class="db-filter-bar">
                <div class="db-filter-row">
                    <div class="db-filter-group">
                        <label for="db-company-filter">Company</label>
                        <div id="db-company-control"></div>
                    </div>
                    <div class="db-filter-group">
                        <label for="db-account-filter">Account</label>
                        <div id="db-account-control"></div>
                    </div>
                    <div class="db-filter-group">
                        <label for="db-from-date">From Date</label>
                        <input type="date" id="db-from-date" value="${from_date}" />
                    </div>
                    <div class="db-filter-group">
                        <label for="db-to-date">Today Date</label>
                        <input type="date" id="db-to-date" value="${today}" />
                    </div>
                    <button class="db-apply-btn" id="db-apply-btn">Apply</button>
                </div>
            </div>

            <div id="db-table-area" class="db-table-wrap">
                <div class="db-loading-state">
                    <div class="db-spinner"></div>
                    <p>Fetching data...</p>
                </div>
            </div>
        </div>
    `);

    // Initialize Company filter
    page.company_control = frappe.ui.form.make_control({
        parent: page.main.find("#db-company-control"),
        df: {
            fieldtype: "Link",
            options: "Company",
            fieldname: "company",
            placeholder: "Select Company",
            on_change: () => {
                if (page.account_control) page.account_control.set_value("");
                load_day_book_data(page);
            }
        },
        render_input: true,
    });

    // Initialize Account filter
    page.account_control = frappe.ui.form.make_control({
        parent: page.main.find("#db-account-control"),
        df: {
            fieldtype: "Link",
            options: "Account",
            fieldname: "account",
            placeholder: "Select Account",
            get_query: () => {
                let company = page.company_control.get_value();
                let filters = {
                    "is_group": 0,
                    "account_type": ["in", ["Cash", "Bank"]]
                };
                if (company) filters["company"] = company;
                return { filters: filters };
            },
            on_change: () => load_day_book_data(page)
        },
        render_input: true,
    });
    
    // Set default company and trigger load
    frappe.db.get_single_value("Global Defaults", "default_company").then(company => {
        if (company) {
            page.company_control.set_value(company, true); 
        } else {
            load_day_book_data(page);
        }
    });

    page.set_primary_action(__("Refresh"), function () {
        load_day_book_data(page);
    }, "refresh");

    page.main.find("#db-apply-btn").on("click", function () {
        load_day_book_data(page);
    });
};

function load_day_book_data(page) {
    let table_area = page.main.find("#db-table-area");
    let from_date = page.main.find("#db-from-date").val();
    let to_date = page.main.find("#db-to-date").val();
    let company = page.company_control ? page.company_control.get_value() : null;
    let account = page.account_control ? page.account_control.get_value() : null;

    table_area.html(`
        <div class="db-loading-state">
            <div class="db-spinner"></div>
            <p>Fetching data...</p>
        </div>
    `);

    frappe.call({
        method: "cannabis_management.cannabis_management.page.day_book_dashboard.day_book_dashboard.get_day_book_data",
        args: {
            from_date: from_date,
            to_date: to_date,
            company: company,
            account: account
        },
        callback: function (r) {
            if (r.message && r.message.length) {
                render_day_book_table(page, r.message);
            } else {
                table_area.html(`
                    <div class="db-empty-state">
                        <h3>No Data Found</h3>
                        <p>Try adjusting your filters.</p>
                    </div>
                `);
            }
        }
    });
}

function render_day_book_table(page, data) {
    let rows_html = "";
    
    data.forEach((row, idx) => {
        let is_header = ["Cash", "Bank"].includes(row.type);
        let is_total = ["Total Cash", "Total Bank", "Grand Total"].includes(row.type);
        
        let row_class = "";
        if (is_header) row_class = "db-row-header";
        else if (is_total) row_class = "db-row-total";
        else row_class = idx % 2 === 0 ? "db-row-even" : "db-row-odd";

        rows_html += `
            <tr class="${row_class}">
                <td class="db-col-type">${row.type}</td>
                <td class="db-col-val">${format_currency(row.opening_balance, is_header)}</td>
                <td class="db-col-val">${format_currency(row.receipt, is_header)}</td>
                <td class="db-col-val">${format_currency(row.payment, is_header)}</td>
                <td class="db-col-val">${format_currency(row.closing_balance, is_header)}</td>
            </tr>
        `;
    });

    page.main.find("#db-table-area").html(`
        <table class="db-table">
            <thead>
                <tr>
                    <th class="db-col-type">Type</th>
                    <th class="db-col-val">Opening Balance</th>
                    <th class="db-col-val">Receipt</th>
                    <th class="db-col-val">Payment</th>
                    <th class="db-col-val">Closing Balance</th>
                </tr>
            </thead>
            <tbody>
                ${rows_html}
            </tbody>
        </table>
    `);
}

function format_currency(val, is_header) {
    if (is_header || val === null || val === undefined) return "";
    return "$" + parseFloat(val).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}
