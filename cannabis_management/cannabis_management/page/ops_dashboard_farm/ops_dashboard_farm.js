const OPS_APP_MODULE = "cannabis_management.api.ops_dashboard_farm";

let ops_from_date = frappe.datetime.get_today();
let ops_to_date = frappe.datetime.get_today();

frappe.pages["ops-dashboard-farm"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Ops Dashboard - Farm",
		single_column: true,
	});

	page.main.append(`
		<div class="ops-farm-dashboard">
			<div class="ops-farm-filter-bar">
				<label style="font-size:12px;">From</label>
				<input type="date" id="ops-from-date" class="form-control input-sm" style="width:150px;">
				<label style="font-size:12px;">To</label>
				<input type="date" id="ops-to-date" class="form-control input-sm" style="width:150px;">
				<button class="btn btn-xs btn-primary" id="ops-apply-range">Apply</button>
				<button class="btn btn-xs btn-default" id="ops-reset-today">Today</button>
			</div>

			<div class="ops-farm-section-title">Daily</div>
			<div class="ops-farm-card-grid" id="daily-grid"></div>

			<div class="ops-farm-section-title">Harvest Window — Lbs Taken Down</div>
			<div id="harvest-window-table"></div>

			<div class="ops-farm-section-title">Labor Efficiency — Active Sessions</div>
			<div class="ops-farm-card-grid" id="efficiency-grid"></div>

			<div class="ops-farm-section-title">
				<span class="ops-farm-archived-toggle" id="archived-sessions-toggle">
					&#9656; Archived Labor Sessions
				</span>
			</div>
			<div class="ops-farm-archived-list" id="archived-sessions-list"></div>
		</div>
	`);

	page.wrapper.find("#ops-from-date").val(ops_from_date);
	page.wrapper.find("#ops-to-date").val(ops_to_date);

	page.wrapper.find("#ops-apply-range").on("click", function () {
		ops_from_date = page.wrapper.find("#ops-from-date").val() || frappe.datetime.get_today();
		ops_to_date = page.wrapper.find("#ops-to-date").val() || frappe.datetime.get_today();
		reload_all_sections();
	});

	page.wrapper.find("#ops-reset-today").on("click", function () {
		ops_from_date = frappe.datetime.get_today();
		ops_to_date = frappe.datetime.get_today();
		page.wrapper.find("#ops-from-date").val(ops_from_date);
		page.wrapper.find("#ops-to-date").val(ops_to_date);
		reload_all_sections();
	});

	page.wrapper.find("#archived-sessions-toggle").on("click", function () {
		page.wrapper.find("#archived-sessions-list").toggle();
	});

	reload_all_sections();
};

function reload_all_sections() {
	load_daily_summary();
	load_harvest_window();
	load_labor_efficiency();
	load_archived_sessions();
}

// ---------------------------------------------------------------------------
// Section A: Daily
// ---------------------------------------------------------------------------

function load_daily_summary() {
	frappe.call({
		method: `${OPS_APP_MODULE}.get_daily_summary`,
		args: { from_date: ops_from_date, to_date: ops_to_date },
		callback: function (r) {
			render_daily_summary(r.message || {});
		},
	});
}

function render_daily_summary(d) {
	const $grid = $("#daily-grid").empty();

	const empBreakdown = (d.employee_breakdown || [])
		.map((e) => `${frappe.utils.escape_html(e.employee)}: ${e.scouting_pct}%`)
		.join(" · ");

	$grid.append(`
		<div class="ops-farm-card">
			<div class="ops-farm-card-label">Scouting Completed</div>
			<div class="ops-farm-card-value">${d.scouting_pct ?? 0}%</div>
			<div class="ops-farm-card-sub">${empBreakdown || "No logs in range"}</div>
		</div>
		<div class="ops-farm-card">
			<div class="ops-farm-card-label">Issues Reported</div>
			<div class="ops-farm-card-value">${d.issues_count ?? 0}</div>
			<div class="ops-farm-card-sub">${d.total_logs ?? 0} total logs in range</div>
		</div>
		<div class="ops-farm-card">
			<div class="ops-farm-card-label">DCC Ready</div>
			<div class="ops-farm-card-value">${d.dcc_pct ?? 0}%</div>
			<div class="ops-farm-card-sub">Target: 100%</div>
		</div>
		<div class="ops-farm-card">
			<div class="ops-farm-card-label">METRC Open Corrections</div>
			<div class="ops-farm-card-value">${d.open_corrections ?? 0}</div>
			<div class="ops-farm-card-sub">Target: 0</div>
		</div>
	`);
}

// ---------------------------------------------------------------------------
// Section B: Harvest Window
// ---------------------------------------------------------------------------

function load_harvest_window() {
	frappe.call({
		method: `${OPS_APP_MODULE}.get_harvest_window`,
		args: { from_date: ops_from_date, to_date: ops_to_date },
		callback: function (r) {
			render_harvest_window(r.message || []);
		},
	});
}

function render_harvest_window(rows) {
	const $container = $("#harvest-window-table").empty();

	if (!rows.length) {
		$container.append(`<div class="ops-farm-empty">No harvest events in this range.</div>`);
		return;
	}

	let html = `
		<table class="ops-farm-table">
			<thead>
				<tr><th>Harvest</th><th>Date</th><th>Route</th><th>Lbs Taken Down</th></tr>
			</thead>
			<tbody>
	`;
	rows.forEach((r) => {
		html += `
			<tr>
				<td>${frappe.utils.escape_html(r.harvest_name || r.name)}</td>
				<td>${frappe.datetime.str_to_user(r.harvest_date)}</td>
				<td>${frappe.utils.escape_html(r.route || "")}</td>
				<td>${format_num(r.lbs_produced)}</td>
			</tr>
		`;
	});
	html += `</tbody></table>`;
	$container.append(html);
}

// ---------------------------------------------------------------------------
// Section C: Labor Efficiency
// ---------------------------------------------------------------------------

function load_labor_efficiency() {
	frappe.call({
		method: `${OPS_APP_MODULE}.get_labor_efficiency`,
		args: { from_date: ops_from_date, to_date: ops_to_date },
		callback: function (r) {
			render_labor_efficiency(r.message || {});
		},
	});
}

function render_labor_efficiency(data) {
	const $grid = $("#efficiency-grid").empty();

	const cards = [
		{ key: "clones", label: "Clones Taken / person / hr", archiveFn: () => archive_cloning() },
		{ key: "planting", label: "Planting Rate / person / hr", archiveFn: () => archive_task("Planting") },
		{ key: "deleaf", label: "Deleaf / person / hr", archiveFn: () => archive_task("Deleaf") },
		{ key: "bucking", label: "Bucking / person / hr", archiveFn: () => archive_task("Bucking") },
	];

	cards.forEach((c) => {
		const stat = data[c.key] || { actual: 0, target: 0 };
		const cls = stat.target && stat.actual < stat.target ? "ops-farm-eff-below" : "ops-farm-eff-above";

		const $card = $(`
			<div class="ops-farm-eff-card">
				<div class="ops-farm-eff-title">${c.label}</div>
				<div class="ops-farm-eff-row"><span>Actual</span><b class="${cls}">${stat.actual}</b></div>
				<div class="ops-farm-eff-row"><span>Target</span><span>${stat.target || "—"}</span></div>
				<div style="margin-top:8px; text-align:right;">
					<button class="btn btn-xs btn-default btn-archive-eff">Archive</button>
				</div>
			</div>
		`);

		$card.find(".btn-archive-eff").on("click", c.archiveFn);
		$grid.append($card);
	});
}

function archive_cloning() {
	frappe.call({
		method: `${OPS_APP_MODULE}.archive_cloning_batches`,
		args: { from_date: ops_from_date, to_date: ops_to_date },
		callback: function () {
			frappe.show_alert({ message: __("Cloning sessions archived"), indicator: "green" });
			load_labor_efficiency();
			load_archived_sessions();
		},
	});
}

function archive_task(task_type) {
	frappe.call({
		method: `${OPS_APP_MODULE}.archive_labor_sessions`,
		args: { task_type: task_type, from_date: ops_from_date, to_date: ops_to_date },
		callback: function () {
			frappe.show_alert({ message: __(`${task_type} sessions archived`), indicator: "green" });
			load_labor_efficiency();
			load_archived_sessions();
		},
	});
}

// ---------------------------------------------------------------------------
// Section D: Archived Sessions
// ---------------------------------------------------------------------------

function load_archived_sessions() {
	frappe.call({
		method: `${OPS_APP_MODULE}.get_archived_sessions`,
		callback: function (r) {
			render_archived_sessions(r.message || { cloning: [], labor: [] });
		},
	});
}

function render_archived_sessions(data) {
	const $list = $("#archived-sessions-list").empty();
	const cloning = data.cloning || [];
	const labor = data.labor || [];

	if (!cloning.length && !labor.length) {
		$list.append(`<div class="ops-farm-empty">No archived sessions.</div>`);
		return;
	}

	cloning.forEach((c) => {
		const $row = $(`
			<div class="ops-farm-archived-row">
				<span>Cloning &nbsp;·&nbsp; ${frappe.datetime.str_to_user(c.session_date)}
					&nbsp;·&nbsp; ${c.clones_per_hour || 0} /hr</span>
				<button class="btn btn-xs btn-default btn-restore-cloning">Restore Active</button>
			</div>
		`);
		$row.find(".btn-restore-cloning").on("click", function () {
			frappe.call({
				method: `${OPS_APP_MODULE}.restore_cloning_batch`,
				args: { name: c.name },
				callback: function () {
					load_labor_efficiency();
					load_archived_sessions();
				},
			});
		});
		$list.append($row);
	});

	labor.forEach((l) => {
		const $row = $(`
			<div class="ops-farm-archived-row">
				<span>${frappe.utils.escape_html(l.task_type)} &nbsp;·&nbsp;
					${frappe.datetime.str_to_user(l.session_date)}
					&nbsp;·&nbsp; ${l.rate_per_hour || 0} /hr</span>
				<button class="btn btn-xs btn-default btn-restore-labor">Restore Active</button>
			</div>
		`);
		$row.find(".btn-restore-labor").on("click", function () {
			frappe.call({
				method: `${OPS_APP_MODULE}.restore_labor_session`,
				args: { name: l.name },
				callback: function () {
					load_labor_efficiency();
					load_archived_sessions();
				},
			});
		});
		$list.append($row);
	});
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function format_num(val) {
	if (val === null || val === undefined || isNaN(val)) return "0";
	return Number(val).toLocaleString("en-US", { maximumFractionDigits: 2 });
}
