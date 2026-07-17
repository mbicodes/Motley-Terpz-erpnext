frappe.pages["ap-projection-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "AP Projection Dashboard",
		single_column: true,
	});

	$(wrapper).find(".page-head").hide();

	var $body = $(page.body);
	$body.html('<div class="apj-root"></div>');
	var $root = $body.find(".apj-root");

	var API = "cannabis_management.api.ap_projection_dashboard.";

	var state = {
		company: "All",
		companies: [], // [{name, abbr}]
		forecast_days: 60,
		source_filter: "All",
		search: "",
		sort_col: "date",
		sort_asc: true,
		data: null,
		chart: null,
	};

	$root.html(buildShell());
	bindControls();
	bootstrap();

	function bootstrap() {
		frappe.call({
			method: API + "get_scope_companies",
			callback: function (r) {
				state.companies = r.message || [];
				renderCompanySeg();
				loadData();
			},
		});
	}

	// ── DOM shell ────────────────────────────────────────────────────────────
	function buildShell() {
		return `
		<div class="apj-header">
			<div class="apj-title-block">
				<div class="apj-title-icon">
					<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M3 3v18h18"/><path d="M7 15l4-6 4 3 5-8"/>
					</svg>
				</div>
				<div>
					<div class="apj-title">AP Projection Dashboard</div>
					<div class="apj-subtitle">Outstanding AP + recurring bill forecast &middot; MTM, TSBC &amp; Motley Terpz</div>
				</div>
			</div>
			<div class="apj-controls">
				<div class="apj-seg" id="apj-company-seg"></div>
				<div class="apj-seg" id="apj-window-seg">
					<button class="apj-seg-btn" data-val="30">30d</button>
					<button class="apj-seg-btn active" data-val="60">60d</button>
					<button class="apj-seg-btn" data-val="90">90d</button>
				</div>
				<button class="apj-refresh-btn" id="apj-refresh">
					<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
						<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
						<path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
						<path d="M8 16H3v5"/>
					</svg>
					Refresh
				</button>
			</div>
		</div>

		<div class="apj-kpis" id="apj-kpis">
			<div class="apj-kpi-skeleton"></div>
			<div class="apj-kpi-skeleton"></div>
			<div class="apj-kpi-skeleton"></div>
		</div>

		<div class="apj-card apj-chart-card">
			<div class="apj-card-head">
				<div class="apj-card-title">Forecast Timeline</div>
				<div class="apj-legend">
					<span class="apj-legend-item"><i class="apj-dot apj-dot-outstanding"></i>Outstanding &mdash; confirmed</span>
					<span class="apj-legend-item"><i class="apj-dot apj-dot-recurring"></i>Recurring &mdash; projected estimate</span>
				</div>
			</div>
			<div id="apj-chart"></div>
		</div>

		<div class="apj-card">
			<div class="apj-card-head">
				<div class="apj-card-title">Detail</div>
				<div class="apj-table-controls">
					<div class="apj-seg apj-seg-sm" id="apj-source-seg">
						<button class="apj-seg-btn active" data-val="All">All</button>
						<button class="apj-seg-btn" data-val="Outstanding">Outstanding</button>
						<button class="apj-seg-btn" data-val="Recurring">Recurring</button>
					</div>
					<div class="apj-search-wrap">
						<svg class="apj-search-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
							<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
						</svg>
						<input class="apj-search" id="apj-search" placeholder="Search vendor…" />
					</div>
				</div>
			</div>
			<div class="apj-table-wrap">
				<table class="apj-table">
					<thead>
						<tr>
							<th data-col="company">Company</th>
							<th data-col="source_type">Source Type</th>
							<th data-col="vendor">Vendor / Expense Head</th>
							<th data-col="amount" class="apj-num">Amount</th>
							<th data-col="date">Due / Expected Date</th>
							<th>Reference</th>
						</tr>
					</thead>
					<tbody id="apj-table-body"></tbody>
				</table>
			</div>
		</div>`;
	}

	function renderCompanySeg() {
		var html = '<button class="apj-seg-btn active" data-val="All">All</button>';
		state.companies.forEach(function (c) {
			html += '<button class="apj-seg-btn" data-val="' + c.name + '">' + frappe.utils.escape_html(c.abbr) + "</button>";
		});
		$root.find("#apj-company-seg").html(html);
		wireSeg($root.find("#apj-company-seg"), function (val) {
			state.company = val;
			loadData();
		});
	}

	// ── Controls ─────────────────────────────────────────────────────────────
	function bindControls() {
		wireSeg($root.find("#apj-window-seg"), function (val) {
			state.forecast_days = parseInt(val, 10);
			loadData();
		});
		wireSeg($root.find("#apj-source-seg"), function (val) {
			state.source_filter = val;
			renderTable();
		});
		$root.find("#apj-refresh").on("click", loadData);
		$root.find("#apj-search").on("input", frappe.utils.debounce(function () {
			state.search = $root.find("#apj-search").val().toLowerCase();
			renderTable();
		}, 200));
		$root.find(".apj-table thead").on("click", "th[data-col]", function () {
			var col = $(this).data("col");
			if (state.sort_col === col) {
				state.sort_asc = !state.sort_asc;
			} else {
				state.sort_col = col;
				state.sort_asc = true;
			}
			renderTable();
		});
	}

	function wireSeg($seg, onChange) {
		$seg.on("click", ".apj-seg-btn", function () {
			$seg.find(".apj-seg-btn").removeClass("active");
			$(this).addClass("active");
			onChange($(this).data("val").toString());
		});
	}

	// ── Data ─────────────────────────────────────────────────────────────────
	function loadData() {
		$root.find("#apj-kpis").addClass("apj-loading");
		var companies = state.company === "All" ? null : [state.company];
		frappe.call({
			method: API + "get_ap_projection",
			args: { companies: companies ? JSON.stringify(companies) : null, forecast_days: state.forecast_days },
			callback: function (r) {
				state.data = r.message;
				$root.find("#apj-kpis").removeClass("apj-loading");
				renderKpis();
				renderChart();
				renderTable();
			},
		});
	}

	function money(v) {
		return format_currency(flt(v || 0));
	}
	function flt(v) {
		return v === null || v === undefined ? 0 : parseFloat(v) || 0;
	}

	// ── KPIs ─────────────────────────────────────────────────────────────────
	function renderKpis() {
		var k = (state.data && state.data.kpis) || { total_outstanding: 0, total_recurring: 0, grand_total: 0 };
		var html = `
		<div class="apj-kpi apj-kpi-outstanding">
			<div class="apj-kpi-label">Total Outstanding AP</div>
			<div class="apj-kpi-value">${money(k.total_outstanding)}</div>
			<div class="apj-kpi-tag apj-tag-confirmed">Confirmed liability</div>
		</div>
		<div class="apj-kpi apj-kpi-recurring">
			<div class="apj-kpi-label">Total Recurring (${state.forecast_days}d, projected)</div>
			<div class="apj-kpi-value">${money(k.total_recurring)}</div>
			<div class="apj-kpi-tag apj-tag-estimate">Estimate &mdash; amount/date may shift</div>
		</div>
		<div class="apj-kpi apj-kpi-grand">
			<div class="apj-kpi-label">Grand Projected Total</div>
			<div class="apj-kpi-value">${money(k.grand_total)}</div>
			<div class="apj-kpi-tag apj-tag-grand">Outstanding + Recurring</div>
		</div>`;
		$root.find("#apj-kpis").html(html);
	}

	// ── Chart ────────────────────────────────────────────────────────────────
	function renderChart() {
		var t = (state.data && state.data.timeline) || { buckets: [], outstanding: [], recurring: [] };
		var $mount = $root.find("#apj-chart");
		$mount.empty();

		if (!t.buckets.length || !(sum(t.outstanding) + sum(t.recurring) > 0)) {
			$mount.html('<div class="apj-empty">No projected AP in this window.</div>');
			return;
		}

		state.chart = new frappe.Chart($mount[0], {
			type: "bar",
			height: 260,
			colors: ["#4c1d95", "#a78bfa"],
			data: {
				labels: t.buckets,
				datasets: [
					{ name: "Outstanding", values: t.outstanding.map(round2) },
					{ name: "Recurring (est.)", values: t.recurring.map(round2) },
				],
			},
			barOptions: { stacked: 1, spaceRatio: 0.35 },
			axisOptions: { xIsSeries: 1 },
			tooltipOptions: { formatTooltipY: function (v) { return money(v); } },
		});
	}

	function sum(arr) {
		return (arr || []).reduce(function (a, b) { return a + flt(b); }, 0);
	}
	function round2(v) {
		return Math.round(flt(v) * 100) / 100;
	}

	// ── Table ────────────────────────────────────────────────────────────────
	function renderTable() {
		var rows = ((state.data && state.data.detail_rows) || []).slice();

		if (state.source_filter !== "All") {
			rows = rows.filter(function (r) { return r.source_type === state.source_filter; });
		}
		if (state.search) {
			rows = rows.filter(function (r) {
				return (r.vendor || "").toLowerCase().indexOf(state.search) !== -1;
			});
		}
		rows.sort(function (a, b) {
			var av = a[state.sort_col], bv = b[state.sort_col];
			if (state.sort_col === "amount") { av = flt(av); bv = flt(bv); }
			if (av < bv) return state.sort_asc ? -1 : 1;
			if (av > bv) return state.sort_asc ? 1 : -1;
			return 0;
		});

		var $body = $root.find("#apj-table-body");
		if (!rows.length) {
			$body.html('<tr><td colspan="6" class="apj-empty">No rows match the current filters.</td></tr>');
			return;
		}

		$body.html(
			rows
				.map(function (r) {
					var pillClass = r.source_type === "Outstanding" ? "apj-pill-outstanding" : "apj-pill-recurring";
					return `
				<tr>
					<td>${frappe.utils.escape_html(r.company || "")}</td>
					<td><span class="apj-pill ${pillClass}">${r.source_type}</span></td>
					<td>${frappe.utils.escape_html(r.vendor || "")}</td>
					<td class="apj-num">${money(r.amount)}</td>
					<td>${frappe.datetime.str_to_user(r.date)}</td>
					<td class="apj-ref">${frappe.utils.escape_html(r.reference || "")}</td>
				</tr>`;
				})
				.join("")
		);
	}
};
