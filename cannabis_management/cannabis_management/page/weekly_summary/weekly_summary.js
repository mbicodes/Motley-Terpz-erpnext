frappe.pages["weekly-summary"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Business Overview",
		single_column: true,
	});

	// Store page reference
	wrapper.page = page;

	// Default dates: 4 weeks back from today
	let today_date = frappe.datetime.get_today();
	let four_weeks_ago = frappe.datetime.add_days(today_date, -28);

	page.main.html(`
        <div class="ws-container">
            <!-- Header -->
            <div class="ws-header">
                <div class="ws-header-left">
                    <div class="ws-header-icon">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                            <line x1="16" y1="2" x2="16" y2="6"></line>
                            <line x1="8" y1="2" x2="8" y2="6"></line>
                            <line x1="3" y1="10" x2="21" y2="10"></line>
                            <path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01M16 18h.01"></path>
                        </svg>
                    </div>
                    <div>
                        <h2>Business Overview</h2>
                        <p>Production, Sales, Revenue &amp; Inventory — Trailing weekly overview</p>
                    </div>
                </div>
                <div class="ws-header-actions">
                    <button class="ws-btn ws-btn-export" id="ws-export-btn">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                            <polyline points="7 10 12 15 17 10"></polyline>
                            <line x1="12" y1="15" x2="12" y2="3"></line>
                        </svg>
                        Export Excel
                    </button>
                </div>
            </div>

            <!-- Filter Bar -->
            <div class="ws-filter-bar">
                <div class="ws-filter-group">
                    <label>Company</label>
                    <select id="ws-company-filter"></select>
                </div>
                <div class="ws-filter-group">
                    <label>From Date</label>
                    <input type="date" id="ws-from-date" value="${four_weeks_ago}" />
                </div>
                <div class="ws-filter-group">
                    <label>To Date</label>
                    <input type="date" id="ws-to-date" value="${today_date}" />
                </div>
                <div class="ws-filter-group">
                    <label>Display Mode</label>
                    <div class="ws-toggle-container">
                        <button class="ws-toggle-btn active" data-mode="value">💰 Value</button>
                        <button class="ws-toggle-btn" data-mode="quantity">📦 Quantity</button>
                    </div>
                </div>
                <div class="ws-filter-group" style="margin-left: auto;">
                    <label>&nbsp;</label>
                    <button class="ws-btn ws-btn-primary" id="ws-apply-btn">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M23 4v6h-6"></path>
                            <path d="M1 20v-6h6"></path>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                        </svg>
                        Apply Filters
                    </button>
                </div>
            </div>

            <!-- Summary Cards -->
            <div id="ws-summary-cards" class="ws-summary-cards"></div>

            <!-- Data Sections -->
            <div id="ws-data-area">
                <div class="ws-loading">
                    <div class="ws-spinner"></div>
                    <p>Loading business overview data...</p>
                </div>
            </div>
        </div>
    `);

	// Load companies
	load_companies(page);

	// Toggle buttons
	page.main.find(".ws-toggle-btn").on("click", function () {
		page.main.find(".ws-toggle-btn").removeClass("active");
		$(this).addClass("active");
		load_weekly_data(page);
	});

	// Apply button
	page.main.find("#ws-apply-btn").on("click", function () {
		load_weekly_data(page);
	});

	// Export button
	page.main.find("#ws-export-btn").on("click", function () {
		export_to_excel(page);
	});

	// Enter key on date inputs
	page.main.find("#ws-from-date, #ws-to-date").on("keypress", function (e) {
		if (e.which === 13) {
			load_weekly_data(page);
		}
	});
};

function load_companies(page) {
	frappe.call({
		method: "cannabis_management.cannabis_management.page.weekly_summary.weekly_summary.get_companies",
		callback: function (r) {
			let select = page.main.find("#ws-company-filter");
			let default_company = frappe.defaults.get_user_default("Company") || "";

			if (r.message && r.message.length) {
				r.message.forEach(function (company) {
					let selected = company === default_company ? "selected" : "";
					select.append(`<option value="${frappe.utils.escape_html(company)}" ${selected}>${frappe.utils.escape_html(company)}</option>`);
				});
			}

			// Load data after companies are loaded
			load_weekly_data(page);
		},
	});
}

function load_weekly_data(page) {
	let data_area = page.main.find("#ws-data-area");
	let cards_area = page.main.find("#ws-summary-cards");

	data_area.html(`
        <div class="ws-loading">
            <div class="ws-spinner"></div>
            <p>Loading business overview data...</p>
        </div>
    `);
	cards_area.html("");

	let company = page.main.find("#ws-company-filter").val();
	let from_date = page.main.find("#ws-from-date").val();
	let to_date = page.main.find("#ws-to-date").val();
	let mode = page.main.find(".ws-toggle-btn.active").data("mode") || "value";

	frappe.call({
		method: "cannabis_management.cannabis_management.page.weekly_summary.weekly_summary.get_weekly_summary",
		args: {
			from_date: from_date,
			to_date: to_date,
			company: company,
			mode: mode,
		},
		callback: function (r) {
			if (r.message) {
				// Store data for export
				page._ws_data = r.message;
				render_weekly_summary(page, r.message);
			} else {
				data_area.html(`
                    <div class="ws-empty">
                        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                            <line x1="16" y1="2" x2="16" y2="6"/>
                            <line x1="8" y1="2" x2="8" y2="6"/>
                            <line x1="3" y1="10" x2="21" y2="10"/>
                        </svg>
                        <h3>No Data Found</h3>
                        <p>No data available for the selected filters. Try adjusting the date range or company.</p>
                    </div>
                `);
			}
		},
		error: function () {
			data_area.html(`
                <div class="ws-empty">
                    <h3>Error Loading Data</h3>
                    <p>Could not fetch weekly summary. Please check the console for details.</p>
                </div>
            `);
		},
	});
}

function render_weekly_summary(page, data) {
	let is_value = data.mode === "value";
	let weeks = data.weeks;
	let sections = data.sections;

	// Calculate totals for summary cards
	let totals = calculate_section_totals(sections, weeks);

	// Render summary cards
	render_summary_cards(page, totals, is_value, sections);

	// Render data sections
	let html = "";

	// Section configs
	let section_config = [
		{ key: "production", icon: get_production_icon(), css_class: "production" },
		{ key: "sales", icon: get_sales_icon(), css_class: "sales" },
		{ key: "revenue", icon: get_revenue_icon(), css_class: "revenue" },
		{ key: "inventory", icon: get_inventory_icon(), css_class: "inventory" },
	];

	section_config.forEach(function (cfg, idx) {
		let section = sections[cfg.key];
		if (!section) return;

		// Each section carries its own fixed_mode ("value" or "quantity")
		let section_is_value = section.fixed_mode === "value";
		html += render_section(section, weeks, section_is_value, cfg.icon, cfg.css_class, idx);
	});

	page.main.find("#ws-data-area").html(html);

	// Add event listeners for expand/collapse
	page.main.find(".ws-expand-row").on("click", function () {
		let group_id = $(this).data("group");
		let is_expanded = $(this).hasClass("expanded");

		if (is_expanded) {
			$(this).removeClass("expanded");
			page.main.find(`.ws-detail-row[data-group="${group_id}"]`).hide();
		} else {
			$(this).addClass("expanded");
			page.main.find(`.ws-detail-row[data-group="${group_id}"]`).show();
		}
	});
}

function calculate_section_totals(sections, weeks) {
	let totals = {};

	Object.keys(sections).forEach(function (key) {
		let section = sections[key];
		let total = 0;
		let prev_total = 0;

		// Identify current month and previous month for cards
		let months = weeks.filter(w => w.is_month);
		let current_month_label = months.length > 0 ? months[months.length - 1].label : null;
		let prev_month_label = months.length > 1 ? months[months.length - 2].label : null;

		Object.keys(section.rows || {}).forEach(function (cat) {
			let cat_totals = section.rows[cat].totals || {};

			if (current_month_label) {
				let val = cat_totals[current_month_label] || 0;
				if (key === "inventory") {
					total = val;
				} else {
					total += val;
				}
			}

			if (prev_month_label) {
				let val = cat_totals[prev_month_label] || 0;
				if (key === "inventory") {
					prev_total = val;
				} else {
					prev_total += val;
				}
			}
		});

		totals[key] = {
			title: section.title,
			total: total,
			prev_total: prev_total,
		};
	});

	return totals;
}

function render_summary_cards(page, totals, is_value, sections) {
	let cards_html = "";
	let card_configs = [
		{ key: "production", label: "Production Total", css: "card-production" },
		{ key: "sales", label: "Total Sales (Qty)", css: "card-sales" },
		{ key: "revenue", label: "Total Revenue ($)", css: "card-revenue" },
		{ key: "inventory", label: "Current Inventory", css: "card-inventory" },
	];

	card_configs.forEach(function (cfg) {
		let t = totals[cfg.key];
		if (!t) return;

		// Use the section's fixed_mode to determine formatting
		let section = sections[cfg.key];
		let card_is_value = section ? section.fixed_mode === "value" : is_value;
		let formatted_val = card_is_value ? format_currency(t.total) : format_qty(t.total);

		// Calculate trend
		let trend_html = "";
		if (t.prev_total !== 0) {
			let change = ((t.total - t.prev_total) / Math.abs(t.prev_total)) * 100;
			let trend_class = change >= 0 ? "up" : "down";
			let trend_icon = change >= 0 ? "↑" : "↓";
			trend_html = `<span class="ws-card-trend ${trend_class}">${trend_icon} ${Math.abs(change).toFixed(1)}% vs prev week</span>`;
		}

		cards_html += `
            <div class="ws-summary-card ${cfg.css}">
                <span class="ws-card-label">${cfg.label}</span>
                <span class="ws-card-value">${formatted_val}</span>
                ${trend_html}
            </div>
        `;
	});

	page.main.find("#ws-summary-cards").html(cards_html);
}

function render_section(section, weeks, is_value, icon, css_class, delay_idx) {
	let mode_label = is_value ? "Value ($)" : "Qty";
	let month_count = weeks.filter(w => w.is_month).length;
	let week_count = weeks.filter(w => w.is_week).length;

	let html = `
        <div class="ws-section" style="animation-delay: ${delay_idx * 0.1}s">
            <div class="ws-section-header ${css_class}">
                ${icon}
                ${section.title}
                <span style="margin-left: auto; font-size: 11px; font-weight: 500; opacity: 0.85; text-transform: none; letter-spacing: 0;">Showing: ${mode_label}</span>
            </div>
            <div class="ws-table-wrap">
                <table class="ws-table">
                    <thead>
                        <tr>
                            <th rowspan="2" style="background: var(--ws-bg); z-index: 3;">Category</th>
                            <th colspan="${month_count}" class="ws-group-header-consolidated">Consolidated</th>
                            <th colspan="${week_count}" class="ws-group-header-trailing">Trailing Weeks</th>
                        </tr>
                        <tr>
    `;

	// Week/Month headers
	weeks.forEach(function (week) {
		let extra_class = week.is_month ? "th-month" : "th-week";
		html += `<th class="${extra_class}">${week.label}</th>`;
	});

	html += `</tr></thead><tbody>`;

	// Data rows
	let consolidated_total = 0;
	let row_idx = 0;

	Object.keys(section.rows).forEach(function (cat) {
		let data = section.rows[cat];
		let totals = data.totals || {};
		let details = data.details || {};
		let has_details = Object.keys(details).length > 0;
		let row_consolidated = 0;
		let group_id = `${css_class}-${row_idx++}`;

		html += `<tr class="ws-category-row">`;
		html += `
            <td class="${has_details ? "ws-expand-row" : "ws-no-expand"}" data-group="${group_id}" style="${has_details ? '' : 'padding-left: 44px;'}">
                ${has_details ? `
                <span class="ws-arrow">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" 
                         stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </span>` : ''}
                ${frappe.utils.escape_html(cat)}
            </td>`;

		weeks.forEach(function (week) {
			let val = totals[week.label] || 0;
			let extra_class = week.is_month ? "ws-month-cell" : "ws-week-cell";
			let zero_class = val === 0 ? "ws-zero" : "";
			html += `<td class="${extra_class} ${zero_class}">${is_value ? format_currency(val) : format_qty(val)}</td>`;
		});

		html += `</tr>`;

		// Sub-rows (Details)
		Object.keys(details).forEach(function (item) {
			let item_vals = details[item];
			html += `<tr class="ws-detail-row" data-group="${group_id}" style="display: none;">`;
			html += `<td class="ws-detail-item">${frappe.utils.escape_html(item)}</td>`;

			weeks.forEach(function (week) {
				let val = item_vals[week.label] || 0;
				let extra_class = week.is_month ? "ws-month-cell" : "ws-week-cell";
				let zero_class = val === 0 ? "ws-zero" : "";
				html += `<td class="${extra_class} ${zero_class}">${is_value ? format_currency(val) : format_qty(val)}</td>`;
			});

			html += `</tr>`;
		});
	});

	// Footer totals
	html += `</tbody><tfoot><tr>`;
	html += `<td><strong>TOTAL</strong></td>`;

	weeks.forEach(function (week) {
		let week_total = 0;
		Object.keys(section.rows).forEach(function (cat) {
			week_total += section.rows[cat].totals[week.label] || 0;
		});
		let extra_class = week.is_month ? "ws-month-cell" : "ws-week-cell";
		html += `<td class="${extra_class}"><strong>${is_value ? format_currency(week_total) : format_qty(week_total)}</strong></td>`;
	});

	html += `</tr></tfoot></table></div></div>`;

	return html;
}

function export_to_excel(page) {
	let data = page._ws_data;
	if (!data) {
		frappe.msgprint(__("No data to export. Please apply filters first."));
		return;
	}

	let weeks = data.weeks;
	let sections = data.sections;

	// Build CSV content
	let rows = [];

	// Header row
	let header = ["Category"];
	weeks.forEach(function (week) {
		header.push(week.label);
	});
	rows.push(header);

	// Section order
	let section_keys = ["production", "sales", "revenue", "inventory"];

	section_keys.forEach(function (key) {
		let section = sections[key];
		if (!section) return;

		// Section header
		rows.push([""]);
		rows.push([section.title.toUpperCase()]);

		Object.keys(section.rows).forEach(function (row_key) {
			let row_data = [row_key];
			let row = section.rows[row_key];
			let row_totals = row.totals || {};

			weeks.forEach(function (week) {
				let val = row_totals[week.label] || 0;
				row_data.push(val);
			});

			rows.push(row_data);
		});

		// Totals
		let total_row = ["TOTAL"];
		weeks.forEach(function (week) {
			let week_total = 0;
			Object.keys(section.rows).forEach(function (row_key) {
				week_total += (section.rows[row_key].totals[week.label]) || 0;
			});
			total_row.push(week_total);
		});
		rows.push(total_row);
	});

	// Convert to CSV
	let csv_content = rows
		.map(function (row) {
			return row
				.map(function (cell) {
					if (typeof cell === "string") {
						return '"' + cell.replace(/"/g, '""') + '"';
					}
					return cell;
				})
				.join(",");
		})
		.join("\n");

	// Download
	let blob = new Blob([csv_content], { type: "text/csv;charset=utf-8;" });
	let link = document.createElement("a");
	let url = URL.createObjectURL(blob);
	let filename = `Business_Overview_${data.company || "All"}_${page.main.find("#ws-from-date").val()}_to_${page.main.find("#ws-to-date").val()}.csv`;

	link.setAttribute("href", url);
	link.setAttribute("download", filename);
	link.style.visibility = "hidden";
	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);

	frappe.show_alert({
		message: __("Business Overview exported successfully!"),
		indicator: "green",
	});
}

// ────── Formatters ──────

function format_currency(val) {
	return "$" + (val || 0).toLocaleString("en-US", {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2,
	});
}

function format_qty(val) {
	return (val || 0).toLocaleString("en-US", {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2,
	});
}

// ────── Section Icons ──────

function get_production_icon() {
	return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M2 20h20M5 20V10l7-7 7 7v10M9 20v-4h6v4"/>
    </svg>`;
}

function get_sales_icon() {
	return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
        <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
    </svg>`;
}

function get_revenue_icon() {
	return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
    </svg>`;
}

function get_inventory_icon() {
	return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
        <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
        <line x1="12" y1="22.08" x2="12" y2="12"/>
    </svg>`;
}