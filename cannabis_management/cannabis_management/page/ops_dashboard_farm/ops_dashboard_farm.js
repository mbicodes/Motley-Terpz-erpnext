const OPS_APP_MODULE = "cannabis_management.api.ops_dashboard_farm";

let ops_from_date = frappe.datetime.get_today();
let ops_to_date = frappe.datetime.get_today();

frappe.pages["ops-dashboard-farm"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: "Ops Dashboard - Farm",
		single_column: true,
	});

	$(wrapper).find(".layout-main-section").html(getOdfHTML());
	var root = wrapper.querySelector(".odf-dash");

	root.querySelector("#odf-from-date").value = ops_from_date;
	root.querySelector("#odf-to-date").value = ops_to_date;

	root.querySelector("#odf-apply-range").addEventListener("click", function () {
		ops_from_date = root.querySelector("#odf-from-date").value || frappe.datetime.get_today();
		ops_to_date = root.querySelector("#odf-to-date").value || frappe.datetime.get_today();
		reload_all_sections(root);
	});

	root.querySelector("#odf-reset-today").addEventListener("click", function () {
		ops_from_date = frappe.datetime.get_today();
		ops_to_date = frappe.datetime.get_today();
		root.querySelector("#odf-from-date").value = ops_from_date;
		root.querySelector("#odf-to-date").value = ops_to_date;
		reload_all_sections(root);
	});

	root.querySelector("#odf-archived-toggle").addEventListener("click", function () {
		root.querySelector("#odf-archived-wrap").classList.toggle("odf-open");
	});

	reload_all_sections(root);
};

function reload_all_sections(root) {
	load_daily_summary(root);
	load_harvest_window(root);
	load_labor_efficiency(root);
	load_archived_sessions(root);
}

function num(v) {
	return frappe.format(flt(v || 0), { fieldtype: "Float", precision: 1 }, { only_value: true });
}
function flt(v) {
	return v === null || v === undefined ? 0 : parseFloat(v) || 0;
}
function dash(v) {
	return v === null || v === undefined || v === "" ? "—" : v;
}
function dateRangeLabel() {
	if (ops_from_date === ops_to_date) return frappe.datetime.str_to_user(ops_from_date);
	return frappe.datetime.str_to_user(ops_from_date) + " – " + frappe.datetime.str_to_user(ops_to_date);
}

// ---------------------------------------------------------------------------
// Section A: Daily
// ---------------------------------------------------------------------------

function load_daily_summary(root) {
	frappe.call({
		method: `${OPS_APP_MODULE}.get_daily_summary`,
		args: { from_date: ops_from_date, to_date: ops_to_date },
		callback: function (r) {
			render_daily_summary(root, r.message || {});
		},
	});
}

function render_daily_summary(root, d) {
	var hasLogs = !!d.total_logs;
	root.querySelector("#odf-daily-grid").innerHTML =
		dailyCardHTML(
			"Scouting completed",
			hasLogs ? d.scouting_pct + "%" : "—",
			"Yes / No + findings",
			"Target: 100% of days"
		) +
		dailyCardHTML(
			"Issues reported",
			hasLogs ? d.issues_count : "—",
			"Count of same-day reports",
			"Target: 100% same-day"
		) +
		dailyCardHTML(
			"DCC ready status",
			hasLogs ? d.dcc_pct + "%" : "—",
			"Pass / Fail checklist",
			"Target: 100% always"
		) +
		dailyCardHTML(
			"METRC entries current",
			hasLogs ? d.open_corrections : "—",
			"Open corrections in METRC",
			"Target: 0 open items"
		);
}

function dailyCardHTML(title, value, caption, target) {
	return '\
<div class="odf-daily-card">\
  <div class="odf-daily-card-head">' + title + '</div>\
  <div class="odf-daily-card-body">\
    <div class="odf-daily-value">' + value + '</div>\
    <div class="odf-daily-caption">' + caption + '</div>\
    <div class="odf-daily-target">' + target + '</div>\
  </div>\
</div>';
}

// ---------------------------------------------------------------------------
// Section B: Harvest Window
// ---------------------------------------------------------------------------

function load_harvest_window(root) {
	frappe.call({
		method: `${OPS_APP_MODULE}.get_harvest_window`,
		args: { from_date: ops_from_date, to_date: ops_to_date },
		callback: function (r) {
			render_harvest_window(root, r.message || {});
		},
	});
}

function render_harvest_window(root, w) {
	var target = w.target ? num(w.target) : "[TBD]";
	var actual = w.actual ? num(w.actual) : "—";
	var vsTarget = w.target && w.actual ? num(w.actual - w.target) : "—";

	root.querySelector("#odf-harvest-window").innerHTML = '\
<table class="odf-harvest-table">\
  <thead>\
    <tr><th>Metric</th><th>Current target</th><th>Actual</th><th>vs. Target</th><th>Notes</th></tr>\
  </thead>\
  <tbody>\
    <tr>\
      <td class="odf-harvest-metric">Lbs taken down (by event)</td>\
      <td class="odf-harvest-target">' + target + '</td>\
      <td>' + actual + '</td>\
      <td>' + vsTarget + '</td>\
      <td class="odf-harvest-notes">Logged per harvest event by strain and route. Single seasonal harvest — this is the number that sets the entire year.</td>\
    </tr>\
  </tbody>\
</table>';
}

// ---------------------------------------------------------------------------
// Section C: Labor Efficiency
// ---------------------------------------------------------------------------

var EFFICIENCY_CARDS = [
	{ key: "clones", label: "Clones taken per person/hr", notes: "Propagation session log", archiveFn: archive_cloning },
	{ key: "planting", label: "Plants planted per person/hr", notes: "Zero material mix-ups required alongside rate", archiveFn: function (root) { archive_task(root, "Planting"); } },
	{ key: "deleaf", label: "Deleaf per person/hr", notes: "Tracked during deleaf windows only", archiveFn: function (root) { archive_task(root, "Deleaf"); } },
	{ key: "bucking", label: "Bucking per person/hr", notes: "Fresh frozen route only", archiveFn: function (root) { archive_task(root, "Bucking"); } },
];

function load_labor_efficiency(root) {
	frappe.call({
		method: `${OPS_APP_MODULE}.get_labor_efficiency`,
		args: { from_date: ops_from_date, to_date: ops_to_date },
		callback: function (r) {
			render_labor_efficiency(root, r.message || {});
		},
	});
}

function render_labor_efficiency(root, data) {
	root.querySelector("#odf-efficiency-list").innerHTML = EFFICIENCY_CARDS.map(function (c) {
		var stat = data[c.key] || { actual: 0, target: 0 };
		return sessionCardHTML(c.key, c.label, stat, c.notes);
	}).join("");

	EFFICIENCY_CARDS.forEach(function (c) {
		var btn = root.querySelector('[data-archive-key="' + c.key + '"]');
		if (btn) btn.addEventListener("click", function () { c.archiveFn(root); });
	});
}

function sessionCardHTML(key, label, stat, notes) {
	var targetHTML = stat.target
		? '<div class="odf-stat-value">' + num(stat.target) + '</div>'
		: '<div class="odf-stat-value odf-stat-tbd">[TBD — Matt]</div>';
	var actualHTML = stat.actual
		? '<div class="odf-stat-value">' + num(stat.actual) + '</div>'
		: '<div class="odf-stat-value">—</div>';

	return '\
<div class="odf-session-card">\
  <div class="odf-session-head">\
    <div class="odf-session-title">' + label + ' <span class="odf-session-sub">[' + dateRangeLabel() + ']</span></div>\
    <div class="odf-session-actions">\
      <span class="odf-status-pill">● Active</span>\
      <button class="odf-toggle-btn" data-archive-key="' + key + '">Archive →</button>\
    </div>\
  </div>\
  <div class="odf-session-body">\
    <div>\
      <div class="odf-stat-label">TARGET RATE</div>\
      ' + targetHTML + '\
    </div>\
    <div>\
      <div class="odf-stat-label">ACTUAL RATE</div>\
      ' + actualHTML + '\
    </div>\
    <div>\
      <div class="odf-stat-label">NOTES</div>\
      <div class="odf-stat-caption">' + notes + '</div>\
    </div>\
  </div>\
</div>';
}

function archive_cloning(root) {
	frappe.call({
		method: `${OPS_APP_MODULE}.archive_cloning_batches`,
		args: { from_date: ops_from_date, to_date: ops_to_date },
		callback: function () {
			frappe.show_alert({ message: __("Cloning sessions archived"), indicator: "green" });
			load_labor_efficiency(root);
			load_archived_sessions(root);
		},
	});
}

function archive_task(root, task_type) {
	frappe.call({
		method: `${OPS_APP_MODULE}.archive_labor_sessions`,
		args: { task_type: task_type, from_date: ops_from_date, to_date: ops_to_date },
		callback: function () {
			frappe.show_alert({ message: __(task_type + " sessions archived"), indicator: "green" });
			load_labor_efficiency(root);
			load_archived_sessions(root);
		},
	});
}

// ---------------------------------------------------------------------------
// Section D: Archived Sessions
// ---------------------------------------------------------------------------

function load_archived_sessions(root) {
	frappe.call({
		method: `${OPS_APP_MODULE}.get_archived_sessions`,
		callback: function (r) {
			render_archived_sessions(root, r.message || { cloning: [], labor: [] });
		},
	});
}

function render_archived_sessions(root, data) {
	var cloning = data.cloning || [];
	var labor = data.labor || [];
	var $list = root.querySelector("#odf-archived-list");

	if (!cloning.length && !labor.length) {
		$list.innerHTML = '<div class="odf-empty">No archived sessions.</div>';
		return;
	}

	var rows = cloning.map(function (c) {
		return archivedRowHTML(
			"Cloning",
			frappe.datetime.str_to_user(c.session_date),
			c.clones_per_hour,
			c.target,
			'data-restore-cloning="' + c.name + '"'
		);
	}).concat(
		labor.map(function (l) {
			return archivedRowHTML(
				frappe.utils.escape_html(l.task_type),
				frappe.datetime.str_to_user(l.session_date),
				l.rate_per_hour,
				l.target,
				'data-restore-labor="' + l.name + '"'
			);
		})
	);

	$list.innerHTML = rows.join("");

	$list.querySelectorAll("[data-restore-cloning]").forEach(function (btn) {
		btn.addEventListener("click", function () {
			frappe.call({
				method: `${OPS_APP_MODULE}.restore_cloning_batch`,
				args: { name: btn.getAttribute("data-restore-cloning") },
				callback: function () {
					load_labor_efficiency(root);
					load_archived_sessions(root);
				},
			});
		});
	});
	$list.querySelectorAll("[data-restore-labor]").forEach(function (btn) {
		btn.addEventListener("click", function () {
			frappe.call({
				method: `${OPS_APP_MODULE}.restore_labor_session`,
				args: { name: btn.getAttribute("data-restore-labor") },
				callback: function () {
					load_labor_efficiency(root);
					load_archived_sessions(root);
				},
			});
		});
	});
}

function archivedRowHTML(taskType, dateLabel, rate, target, dataAttr) {
	return '\
<div class="odf-archived-row">\
  <div>\
    <span class="odf-archived-title">' + taskType + ' — ' + dateLabel + '</span>\
    <span class="odf-archived-meta">Rate: ' + dash(rate ? num(rate) : null) + '&nbsp;&nbsp; Target: ' + dash(target ? num(target) : null) + '</span>\
  </div>\
  <div class="odf-session-actions">\
    <span class="odf-status-pill odf-status-archived">Archived</span>\
    <button class="odf-toggle-btn odf-restore" ' + dataAttr + '>← Restore Active</button>\
  </div>\
</div>';
}

// ---------------------------------------------------------------------------
// Page HTML shell
// ---------------------------------------------------------------------------

function getOdfHTML() {
	return '\
<div class="odf-dash">\
  <div class="odf-filter-bar">\
    <label style="font-size:12px;">From</label>\
    <input type="date" id="odf-from-date" class="form-control input-sm" style="width:150px;">\
    <label style="font-size:12px;">To</label>\
    <input type="date" id="odf-to-date" class="form-control input-sm" style="width:150px;">\
    <button class="btn btn-xs btn-primary" id="odf-apply-range">Apply</button>\
    <button class="btn btn-xs btn-default" id="odf-reset-today">Today</button>\
  </div>\
\
  <div class="odf-title">Ops Dashboard — Farm</div>\
  <div class="odf-subtitle">The operational layer beneath the CEO view. This is what the ops manager tracks daily and weekly to make sure the farm is on track before it shows up in the financials. Actuals populated by system. Targets to be set.</div>\
\
  <div class="odf-section-bar">\
    <button class="odf-section-pill odf-pill-light-green">DAILY</button>\
    <div class="odf-section-line"></div>\
  </div>\
  <div class="odf-daily-grid" id="odf-daily-grid"></div>\
\
  <div class="odf-section-bar">\
    <button class="odf-section-pill">HARVEST WINDOW ONLY — TRACKED DAILY BY EVENT</button>\
    <div class="odf-section-line"></div>\
  </div>\
  <div id="odf-harvest-window"></div>\
\
  <div class="odf-section-bar">\
    <button class="odf-section-pill odf-pill-archived">LABOR EFFICIENCY — ACTIVE SESSIONS</button>\
    <div class="odf-section-line"></div>\
    <div class="odf-section-caption">Archive completed sessions · restore to active any time</div>\
  </div>\
  <div id="odf-efficiency-list"></div>\
\
  <div class="odf-section-bar">\
    <button class="odf-section-pill odf-pill-archived" id="odf-archived-toggle">▾ ARCHIVED LABOR SESSIONS</button>\
    <div class="odf-section-line"></div>\
    <div class="odf-section-caption">Click to expand · restore any session to active</div>\
  </div>\
  <div id="odf-archived-wrap" class="odf-archived-wrap">\
    <div id="odf-archived-list"></div>\
  </div>\
</div>';
}
