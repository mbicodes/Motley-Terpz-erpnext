frappe.pages['monthly-sales-target'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Monthly Sales Target',
		single_column: true
	});

	wrapper.page = page;

	let today = new Date();
	let current_year = today.getFullYear();
	let current_month = today.getMonth() + 1; // 1-12
	let current_date = today.getDate();
	let current_week = 1;
	if (current_date >= 22) current_week = 4;
	else if (current_date >= 15) current_week = 3;
	else if (current_date >= 8) current_week = 2;

	let months_html = "";
	const month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
	for (let i = 1; i <= 12; i++) {
		months_html += `<option value="${i}" ${i === current_month ? 'selected' : ''}>${month_names[i - 1]}</option>`;
	}

	let years_html = "";
	for (let y = current_year - 2; y <= current_year + 1; y++) {
		years_html += `<option value="${y}" ${y === current_year ? 'selected' : ''}>${y}</option>`;
	}

	page.main.html(`
        <div class="mst-container">
            <div class="mst-header">
                <div>
                    <h2>Monthly Sales Target</h2>
                    <p>Track targets vs actual sales across months, weeks, and days</p>
                </div>
            </div>

            <div class="mst-filter-bar">
                <div class="mst-filter-group">
                    <label>Company</label>
                    <select id="mst-company-filter"></select>
                </div>
                <div class="mst-filter-group">
                    <label>Territory (Targets)</label>
                    <select id="mst-territory-filter">
                        <option value="">Select Territory</option>
                    </select>
                </div>
                <div class="mst-filter-group">
                    <label>Year</label>
                    <select id="mst-year-filter">${years_html}</select>
                </div>
                <div class="mst-filter-group">
                    <label>Month</label>
                    <select id="mst-month-filter">${months_html}</select>
                </div>
                <div class="mst-filter-group">
                    <label>Week (For Daily Data)</label>
                    <select id="mst-week-filter">
                        <!-- Options generated dynamically -->
                    </select>
                </div>
                <div class="mst-filter-group" style="margin-left: auto;">
                    <button class="mst-btn-primary" id="mst-apply-btn">Apply Filters</button>
                </div>
            </div>

            <div id="mst-data-area">
                <div class="mst-empty">Select a Territory and click Apply Filters to load data.</div>
            </div>
        </div>
    `);

	function update_week_dropdown() {
		let y = parseInt(page.main.find('#mst-year-filter').val() || current_year);
		let m = parseInt(page.main.find('#mst-month-filter').val() || current_month);
		let last_day = new Date(y, m, 0).getDate();
		let m_name = month_names[m - 1];

		let week_html = `
			<option value="1" ${current_week === 1 ? 'selected' : ''}>Week 1 (${m_name} 1 - ${m_name} 7)</option>
			<option value="2" ${current_week === 2 ? 'selected' : ''}>Week 2 (${m_name} 8 - ${m_name} 14)</option>
			<option value="3" ${current_week === 3 ? 'selected' : ''}>Week 3 (${m_name} 15 - ${m_name} 21)</option>
			<option value="4" ${current_week === 4 ? 'selected' : ''}>Week 4 (${m_name} 22 - ${m_name} ${last_day})</option>
		`;
		page.main.find('#mst-week-filter').html(week_html);
	}

	page.main.find('#mst-year-filter').on('change', update_week_dropdown);
	page.main.find('#mst-month-filter').on('change', update_week_dropdown);
	update_week_dropdown();

	// Load initial data (Companies and Territories)
	frappe.call({
		method: "cannabis_management.cannabis_management.page.monthly_sales_target.monthly_sales_target.init_page",
		callback: function (r) {
			if (r.message) {
				let company_select = page.main.find('#mst-company-filter');
				let default_company = frappe.defaults.get_user_default("Company") || "";

				r.message.companies.forEach(function (c) {
					let selected = c === default_company ? "selected" : "";
					company_select.append(`<option value="${c}" ${selected}>${c}</option>`);
				});

				let territory_select = page.main.find('#mst-territory-filter');
				r.message.territories.forEach(function (t) {
					territory_select.append(`<option value="${t}">${t}</option>`);
				});
			}
		}
	});

	page.main.find('#mst-apply-btn').on('click', function () {
		load_target_data(page);
	});
};

function load_target_data(page) {
	let company = page.main.find('#mst-company-filter').val();
	let territory = page.main.find('#mst-territory-filter').val();
	let year = page.main.find('#mst-year-filter').val();
	let month = page.main.find('#mst-month-filter').val();
	let week = page.main.find('#mst-week-filter').val();

	let data_area = page.main.find('#mst-data-area');

	if (!territory) {
		frappe.msgprint("Please select a Territory to view targets.");
		return;
	}

	data_area.html(`<div class="mst-loading">Loading sales targets and actuals...</div>`);

	frappe.call({
		method: "cannabis_management.cannabis_management.page.monthly_sales_target.monthly_sales_target.get_sales_data",
		args: {
			company: company,
			territory: territory,
			year: year,
			month: month,
			week: week
		},
		callback: function (r) {
			if (r.message) {
				render_tables(page, r.message);
			}
		}
	});
}

function format_currency(val) {
	return "$" + (val || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function format_qty(val) {
	return (val || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function render_tables(page, data) {
	let company = data.company;
	let targets = data.targets || [];

	let html = "";

	// 1. MONTHLY SECTION
	html += render_section("MONTHLY", data.months, targets, data.month_data, company);

	// 2. WEEKLY SECTION
	html += render_section("WEEKLY", data.weeks, targets, data.week_data, company);

	// 3. DAILY SECTION
	html += render_section("DAILY", data.days, targets, data.day_data, company);

	page.main.find('#mst-data-area').html(html);
}

function render_section(title, periods, targets, actual_data, company) {
	let html = `
    <div class="mst-section">
        <div class="mst-section-title">${title}</div>
        <div class="mst-table-wrap">
            <table class="mst-table">
                <thead>
                    <tr>
                        <th>${title}</th>
                        <th>Target units Month</th>
                        <th>Avg sales price</th>
                        <th>Target Rev</th>
    `;

	periods.forEach(p => {
		html += `<th>${p.label}</th>`;
	});

	html += `</tr></thead><tbody>`;

	// Totals for the sum row
	let sum_qty = 0;
	let sum_rev = 0;
	let sum_actuals = {};
	periods.forEach(p => { sum_actuals[p.key] = 0; });

	targets.forEach(t => {
		let ig = t.item_group;
		html += `<tr>`;
		html += `<td>${ig}</td>`;
		html += `<td class="col-target">${format_qty(t.target_qty)}</td>`;
		html += `<td class="col-target">${format_currency(t.average_rate)}</td>`;
		html += `<td class="col-target">${format_currency(t.target_amount)}</td>`;

		sum_qty += t.target_qty;
		sum_rev += t.target_amount;

		periods.forEach(p => {
			let val = actual_data[ig] ? (actual_data[ig][p.key] || 0) : 0;
			sum_actuals[p.key] += val;
			html += `<td>${format_currency(val)}</td>`;
		});

		html += `</tr>`;
	});

	// Summary Row (Company name)
	html += `<tr class="mst-sum-row">`;
	html += `<td>${company}</td>`;
	html += `<td>${format_qty(sum_qty)}</td>`;
	html += `<td></td>`; // Avg sales price sum is blank
	html += `<td>${format_currency(sum_rev)}</td>`;

	periods.forEach(p => {
		html += `<td>${format_currency(sum_actuals[p.key])}</td>`;
	});

	html += `</tr>`;

	html += `</tbody></table></div></div>`;
	return html;
}