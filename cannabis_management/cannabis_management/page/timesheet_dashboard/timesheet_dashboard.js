frappe.pages["timesheet-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Timesheet Dashboard",
		single_column: true,
	});

	// ─── CSS ───────────────────────────────────────────────────────────────────
	$(`<style>
		@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

		.tsd-root {
			display: flex;
			height: calc(100vh - 60px);
			font-family: 'DM Sans', sans-serif;
			background: #f5f6fa;
		}

		/* ── Sidebar ── */
		.tsd-sidebar {
			width: 220px;
			flex-shrink: 0;
			background: #fff;
			border-right: 1px solid #e8eaf0;
			display: flex;
			flex-direction: column;
			overflow: hidden;
		}
		.tsd-sidebar-header {
			padding: 18px 16px 12px;
			border-bottom: 1px solid #f0f2f7;
		}
		.tsd-sidebar-header h4 {
			margin: 0 0 10px;
			font-size: 11px;
			font-weight: 700;
			text-transform: uppercase;
			letter-spacing: 0.08em;
			color: #8e98a8;
		}
		.tsd-search {
			width: 100%;
			padding: 7px 10px;
			border: 1px solid #e8eaf0;
			border-radius: 6px;
			font-size: 13px;
			font-family: 'DM Sans', sans-serif;
			background: #f8f9fc;
			color: #2d3748;
			outline: none;
			box-sizing: border-box;
		}
		.tsd-search:focus { border-color: #5c6ac4; background: #fff; }
		.tsd-emp-list { flex: 1; overflow-y: auto; padding: 8px 0; }
		.tsd-emp-item {
			display: flex;
			align-items: center;
			gap: 10px;
			padding: 9px 16px;
			cursor: pointer;
			transition: background 0.12s;
			border-left: 3px solid transparent;
		}
		.tsd-emp-item:hover { background: #f5f6fa; }
		.tsd-emp-item.active { background: #eef0fd; border-left-color: #5c6ac4; }
		.tsd-emp-avatar {
			width: 30px; height: 30px;
			border-radius: 50%;
			color: #fff; font-size: 12px; font-weight: 700;
			display: flex; align-items: center; justify-content: center;
			flex-shrink: 0;
		}
		.tsd-emp-name {
			font-size: 13px; font-weight: 500; color: #2d3748;
			white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
		}
		.tsd-emp-item.active .tsd-emp-name { font-weight: 700; color: #3d4eac; }

		/* ── Main ── */
		.tsd-main { flex: 1; overflow-y: auto; padding: 28px 32px; min-width: 0; }
		.tsd-emp-header {
			display: flex; justify-content: space-between;
			align-items: flex-start; margin-bottom: 20px;
			flex-wrap: wrap; gap: 12px;
		}
		.tsd-emp-header h2 { font-size: 22px; font-weight: 700; color: #1a202c; margin: 0 0 3px; }
		.tsd-period { font-size: 12px; color: #8e98a8; font-family: 'DM Mono', monospace; }

		/* Toggle */
		.tsd-toggle-btn {
			display: inline-flex; align-items: center; gap: 6px;
			padding: 7px 14px; border-radius: 7px;
			font-size: 12px; font-weight: 600;
			font-family: 'DM Sans', sans-serif;
			cursor: pointer;
			border: 1.5px solid #e8eaf0;
			background: #fff; color: #4a5568;
			transition: all 0.15s; white-space: nowrap;
		}
		.tsd-toggle-btn:hover { border-color: #5c6ac4; color: #5c6ac4; }
		.tsd-toggle-btn.active { background: #5c6ac4; border-color: #5c6ac4; color: #fff; }

		/* Table card */
		.tsd-table-card {
			background: #fff; border: 1px solid #e8eaf0;
			border-radius: 10px; overflow: hidden;
		}
		.tsd-tc-header {
			display: flex; justify-content: space-between; align-items: center;
			padding: 14px 20px; border-bottom: 1px solid #f0f2f7;
		}
		.tsd-tc-header h3 { font-size: 13px; font-weight: 700; color: #2d3748; margin: 0; }
		.tsd-tc-badge {
			font-size: 11px; background: #eef0fd; color: #5c6ac4;
			border-radius: 20px; padding: 3px 10px; font-weight: 600;
		}

		/* Table */
		.tsd-table { width: 100%; border-collapse: collapse; }
		.tsd-table thead th {
			font-size: 11px; font-weight: 700; color: #8e98a8;
			text-transform: uppercase; letter-spacing: 0.06em;
			padding: 11px 16px; text-align: left;
			background: #fafbfc; border-bottom: 1px solid #f0f2f7;
			white-space: nowrap;
		}
		.tsd-table tbody tr { border-bottom: 1px solid #f5f6fa; transition: background 0.12s; }
		.tsd-table tbody tr:last-child { border-bottom: none; }
		.tsd-table tbody tr:hover { background: #fafbfc; }
		.tsd-table tbody td {
			padding: 11px 16px; font-size: 13px;
			color: #4a5568; white-space: nowrap; vertical-align: middle;
		}
		.td-date { font-weight: 600; color: #2d3748; font-family: 'DM Mono', monospace; font-size: 12px; }
		.td-time { font-family: 'DM Mono', monospace; font-size: 12px; }
		.td-hours { font-weight: 700; font-family: 'DM Mono', monospace; }
		.td-hours.pos { color: #3d4eac; }
		.td-hours.neg { color: #e53e3e; }
		.td-cost { font-weight: 700; font-family: 'DM Mono', monospace; }
		.td-cost.pos { color: #276749; }
		.td-cost.neg { color: #e53e3e; }
		.td-ts a { color: #5c6ac4; text-decoration: none; font-family: 'DM Mono', monospace; font-size: 11px; }
		.td-ts a:hover { text-decoration: underline; }
		.status-pill {
			display: inline-block; padding: 2px 9px;
			border-radius: 20px; font-size: 11px; font-weight: 600;
		}
		.status-pill.submitted { background: #e6f4ea; color: #276749; }
		.status-pill.draft     { background: #fff3cd; color: #856404; }
		.status-pill.cancelled { background: #fde8e8; color: #c53030; }

		.tsd-ibar { display: flex; align-items: center; gap: 7px; }
		.tsd-ibar-bg { width: 50px; height: 4px; background: #e8eaf0; border-radius: 2px; overflow: hidden; flex-shrink: 0; }
		.tsd-ibar-fill { height: 100%; border-radius: 2px; background: #5c6ac4; }
		.tsd-ibar-fill.neg { background: #e53e3e; }

		.tsd-spinner-wrap { text-align: center; padding: 60px; }
		.tsd-spinner {
			display: inline-block; width: 26px; height: 26px;
			border: 2px solid #e8eaf0; border-top-color: #5c6ac4;
			border-radius: 50%; animation: spin .7s linear infinite;
		}
		@keyframes spin { to { transform: rotate(360deg); } }
		.tsd-empty { text-align: center; padding: 70px 20px; }
		.tsd-empty svg { margin-bottom: 12px; opacity: 0.3; }
		.tsd-empty p { font-size: 14px; color: #8e98a8; margin: 0; }
		.tsd-no-sel {
			display: flex; flex-direction: column;
			align-items: center; justify-content: center;
			height: 100%; color: #8e98a8; gap: 12px;
		}
		.tsd-no-sel svg { opacity: 0.25; }
		.tsd-no-sel p { font-size: 15px; margin: 0; }
	</style>`).appendTo("head");

	// ─── Skeleton HTML ─────────────────────────────────────────────────────────
	$(wrapper).find(".page-content").html(`
		<div class="tsd-root">
			<div class="tsd-sidebar">
				<div class="tsd-sidebar-header">
					<h4>Employees</h4>
					<input class="tsd-search" id="tsd-search" placeholder="Search…" autocomplete="off"/>
				</div>
				<div class="tsd-emp-list" id="tsd-emp-list">
					<div class="tsd-spinner-wrap"><div class="tsd-spinner"></div></div>
				</div>
			</div>
			<div class="tsd-main" id="tsd-main">
				<div class="tsd-no-sel">
					<svg width="56" height="56" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.2"
							d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/>
					</svg>
					<p>Select an employee to view their timesheet</p>
				</div>
			</div>
		</div>
	`);

	// ─── Helpers ───────────────────────────────────────────────────────────────
	const AVATAR_COLORS = [
		"#5c6ac4","#00848e","#de3618","#9c6ade","#006fbb",
		"#c05717","#108043","#bf0711","#47c1bf","#f49342",
	];
	const avatarColor = name => {
		let h = 0;
		for (let i = 0; i < (name || "").length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
		return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
	};
	const initials = name =>
		(name || "?").split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();

	const fmtDate = val => {
		if (!val) return "–";
		try { return frappe.datetime.str_to_user(val.toString().split(" ")[0]); }
		catch(e) { return val; }
	};
	const fmtDatetime = val => {
		if (!val) return "–";
		try {
			const [d, t] = val.toString().split(" ");
			return `${frappe.datetime.str_to_user(d)} ${(t || "").slice(0, 5)}`;
		} catch(e) { return val; }
	};
	const fmtCurrency = val => {
		const n = parseFloat(val);
		return isNaN(n) ? "–" : frappe.format(n, { fieldtype: "Currency" });
	};

	// ─── State ─────────────────────────────────────────────────────────────────
	let allEmployees = [], activeEmpId = null, allRows = [], monthOnly = false;
	const monthStart = frappe.datetime.month_start();
	const today      = frappe.datetime.get_today();

	// ─── Only show specific employees ────────────────────────────────────────────
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Employee",
			fields: ["name", "employee_name"],
			filters: [["employee_name", "in", ["Cassidy Jerome Gurske", "Nikki Manilig", "Wolf", "Tori Sutliff", "Elizabeth Brooks"]]],
			order_by: "employee_name asc",
			limit: 10,
		},
		callback(r) {
			allEmployees = r.message || [];
			renderSidebar(allEmployees);
		},
	});

	function renderSidebar(list) {
		if (!list.length) {
			$("#tsd-emp-list").html(`<div style="padding:20px;text-align:center;color:#8e98a8;font-size:13px">No employees found</div>`);
			return;
		}
		$("#tsd-emp-list").html(
			list.map(e => `
				<div class="tsd-emp-item" data-id="${e.name}" data-name="${e.employee_name}">
					<div class="tsd-emp-avatar" style="background:${avatarColor(e.employee_name || e.name)}">${initials(e.employee_name || e.name)}</div>
					<div class="tsd-emp-name">${e.employee_name || e.name}</div>
				</div>`).join("")
		);
		if (activeEmpId) $(`[data-id="${activeEmpId}"]`).addClass("active");

		$("#tsd-emp-list").off("click").on("click", ".tsd-emp-item", function () {
			$(".tsd-emp-item").removeClass("active");
			$(this).addClass("active");
			monthOnly = false;
			loadEmployee($(this).data("id"), $(this).data("name"));
		});
	}

	$(wrapper).on("input", "#tsd-search", function () {
		const q = $(this).val().toLowerCase();
		renderSidebar(q
			? allEmployees.filter(e => (e.employee_name || e.name).toLowerCase().includes(q))
			: allEmployees
		);
	});

	// ─── Load employee data via page Python method ─────────────────────────────
	function loadEmployee(empId, empName) {
		activeEmpId = empId;
		allRows = [];

		$("#tsd-main").html(`
			<div class="tsd-emp-header">
				<div>
					<h2>${empName}</h2>
					<div class="tsd-period" id="tsd-period-lbl">All time entries · newest first</div>
				</div>
				<button class="tsd-toggle-btn" id="tsd-month-btn">
					<svg width="13" height="13" fill="none" viewBox="0 0 24 24" stroke="currentColor">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
							d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
					</svg>
					Current Month Only
				</button>
			</div>
			<div class="tsd-table-card">
				<div class="tsd-tc-header">
					<h3>Timesheet Entries</h3>
					<span class="tsd-tc-badge" id="tsd-count">Loading…</span>
				</div>
				<div id="tsd-tbody">
					<div class="tsd-spinner-wrap"><div class="tsd-spinner"></div></div>
				</div>
			</div>
		`);

		$(wrapper).off("click", "#tsd-month-btn").on("click", "#tsd-month-btn", function () {
			monthOnly = !monthOnly;
			$(this).toggleClass("active", monthOnly);
			renderTable();
		});

		// ── Calls the @frappe.whitelist() method in timesheet_dashboard.py ──────
		frappe.call({
			method: "cannabis_management.cannabis_management.page.timesheet_dashboard.timesheet_dashboard.get_employee_timesheet_details",
			args: { employee: empId },
			callback(r) {
				allRows = r.message || [];
				renderTable();
			},
			error(err) {
				console.error("Timesheet load error", err);
				renderError();
			},
		});
	}

	// ─── Render table ──────────────────────────────────────────────────────────
	function renderTable() {
		if (!allRows.length) { renderEmpty(); return; }

		let rows = monthOnly
			? allRows.filter(r => {
				const d = new Date((r.from_time || "").split(" ")[0]);
				return d >= new Date(monthStart) && d <= new Date(today + "T23:59:59");
			})
			: [...allRows];

		// Sort descending — SQL already does this but re-sort after client filter
		rows.sort((a, b) => new Date(b.from_time || 0) - new Date(a.from_time || 0));

		$("#tsd-period-lbl").text(
			monthOnly
				? `${frappe.datetime.str_to_user(monthStart)} → ${frappe.datetime.str_to_user(today)}`
				: "All time entries · newest first"
		);
		$("#tsd-count").text(`${rows.length} ${rows.length === 1 ? "entry" : "entries"}`);

		if (!rows.length) { renderEmpty(true); return; }

		const maxHrs = Math.max(...rows.map(r => Math.abs(parseFloat(r.hours || 0))), 0.01);

		const trs = rows.map(r => {
			const hrs  = parseFloat(r.hours || 0);
			const cost = parseFloat(r.billing_amount || 0);
			const pct  = (Math.abs(hrs) / maxHrs * 100).toFixed(1);
			const hc   = hrs  < 0 ? "neg" : "pos";
			const cc   = cost < 0 ? "neg" : "pos";
			const dateStr   = (r.from_time || "").split(" ")[0];
			const statusRaw = (r.ts_status || "").toLowerCase();
			const statusPill = r.ts_status
				? `<span class="status-pill ${statusRaw}">${r.ts_status}</span>`
				: "–";

			return `<tr>
				<td class="td-date">${fmtDate(dateStr)}</td>
				<td class="td-time">${fmtDatetime(r.from_time)}</td>
				<td class="td-time">${fmtDatetime(r.to_time)}</td>
				<td class="td-hours ${hc}">
					<div class="tsd-ibar">
						<span>${hrs.toFixed(2)}</span>
						<div class="tsd-ibar-bg">
							<div class="tsd-ibar-fill ${hc}" style="width:${pct}%"></div>
						</div>
					</div>
				</td>
				<td class="td-cost ${cc}">${fmtCurrency(r.billing_amount)}</td>
				<td>${r.activity_type || "–"}</td>
				<td class="td-ts"><a href="/app/timesheet/${r.timesheet}" target="_blank">${r.timesheet}</a></td>
				<td>${statusPill}</td>
				<td>${r.project || "–"}</td>
				<td>${r.task || "–"}</td>
			</tr>`;
		}).join("");

		$("#tsd-tbody").html(`
			<div style="overflow-x:auto">
				<table class="tsd-table">
					<thead><tr>
						<th>Date</th>
						<th>Time In</th>
						<th>Time Out</th>
						<th>Hours Worked</th>
						<th>Cost</th>
						<th>Activity Type</th>
						<th>Timesheet</th>
						<th>Status</th>
						<th>Project</th>
						<th>Task</th>
					</tr></thead>
					<tbody>${trs}</tbody>
				</table>
			</div>
		`);
	}

	function renderEmpty(filtered = false) {
		$("#tsd-count").text("0 entries");
		$("#tsd-tbody").html(`
			<div class="tsd-empty">
				<svg width="44" height="44" fill="none" viewBox="0 0 24 24" stroke="#c0c8d8">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.4"
						d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
				</svg>
				<p>${filtered ? "No entries for the current month" : "No timesheet entries found"}</p>
			</div>
		`);
	}

	function renderError() {
		$("#tsd-count").text("Error");
		$("#tsd-tbody").html(`
			<div class="tsd-empty">
				<svg width="44" height="44" fill="none" viewBox="0 0 24 24" stroke="#fc8181">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.4"
						d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
				</svg>
				<p>Failed to load — check browser console</p>
			</div>
		`);
	}
};