// Manufacturing Dashboard — "Run" = Job Card (see manufacturing_runs.py header
// comment for why). Every number rendered here comes from a live query; there
// is no sample/mock data anywhere in this file.

frappe.pages['manufacturing-runs'].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		single_column: true,
	});
	new ManufacturingRunsDashboard(page);
};

const MRD_METHOD = 'cannabis_management.cannabis_management.page.manufacturing_runs.manufacturing_runs';
const MRD_STATUS_COLORS = { Completed: '#10b981', Open: '#3b82f6', 'In Progress': '#f59e0b' };
const MRD_SUBOP_COLORS = { Completed: '#10b981', 'In Progress': '#3b82f6', Pending: '#f59e0b' };
const MRD_TYPE_COLORS = ['#7c3aed', '#0ea5e9', '#f59e0b', '#ef4444', '#10b981', '#6366f1'];
// Runs by Operation: one dot colour per employee.
const MRD_OP_COLORS = ['#7c3aed', '#0ea5e9', '#f59e0b', '#ef4444', '#10b981', '#6366f1', '#ec4899', '#14b8a6', '#84cc16', '#f97316'];

class ManufacturingRunsDashboard {
	constructor(page) {
		this.page = page;
		let monday = this.monday_of(frappe.datetime.get_today());
		this.from_date = monday;
		this.to_date = this.add_days(monday, 6);
		this.date_preset = 'this_week';
		this.global_filters = { company: '', project: '', item: '' };
		this.runs_page = 1;
		this.runs_page_size = 8;
		this.runs_filters = { processing_type: '', status: '', run: '', batch: '', run_item: '' };
		this.render_shell();
		this.load_filter_options();
		this.reload_all();
	}

	monday_of(date_str) {
		let d = frappe.datetime.str_to_obj(date_str);
		let day = (d.getDay() + 6) % 7; // 0 = Monday
		d.setDate(d.getDate() - day);
		return frappe.datetime.obj_to_str(d).slice(0, 10);
	}

	add_days(date_str, n) {
		let d = frappe.datetime.str_to_obj(date_str);
		d.setDate(d.getDate() + n);
		return frappe.datetime.obj_to_str(d).slice(0, 10);
	}

	reload_all() {
		this.load_dashboard();
		this.load_runs_detail();
	}

	render_shell() {
		this.page.main.html(`
			<div class="mrd">
				<div class="mrd-header">
					<div>
						<div class="mrd-title">Manufacturing Dashboard</div>
					</div>
					<div class="mrd-header-controls">
						<div class="mrd-filter-company mrd-link-filter"></div>
						<div class="mrd-filter-project mrd-link-filter"></div>
						<div class="mrd-filter-item mrd-link-filter"></div>
						<div class="mrd-week-picker dropdown">
							<button class="mrd-week-btn" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
								<span class="mrd-week-icon">${frappe.utils.icon('calendar', 'md')}</span>
								<span class="mrd-week-text">
									<span class="mrd-week-preset"></span>
									<span class="mrd-week-label"></span>
								</span>
								<span class="mrd-week-chevron">${frappe.utils.icon('small-down', 'xs')}</span>
							</button>
							<div class="dropdown-menu dropdown-menu-right mrd-week-menu">
								<a class="dropdown-item mrd-week-option" data-preset="today">Today</a>
								<a class="dropdown-item mrd-week-option" data-preset="yesterday">Yesterday</a>
								<a class="dropdown-item mrd-week-option" data-preset="this_week">This Week</a>
								<a class="dropdown-item mrd-week-option" data-preset="last_week">Last Week</a>
								<div class="dropdown-divider"></div>
								<div class="mrd-week-custom">
									<label>From Date</label>
									<input type="date" class="form-control input-sm mrd-from-date">
									<label>To Date</label>
									<input type="date" class="form-control input-sm mrd-to-date">
									<button class="btn btn-primary btn-xs mrd-apply-range">Apply</button>
								</div>
							</div>
						</div>
					</div>
				</div>

				<div class="mrd-stat-row"></div>

				<div class="mrd-row mrd-row-3">
					<div class="mrd-card">
						<div class="mrd-card-title">Run Status Overview</div>
						<div class="mrd-donut-wrap" id="mrd-status-donut"></div>
						<div class="mrd-legend" id="mrd-status-legend"></div>
					</div>
					<div class="mrd-card">
						<div class="mrd-card-title">Runs by Processing Type</div>
						<div class="mrd-donut-wrap" id="mrd-type-donut"></div>
						<div class="mrd-legend" id="mrd-type-legend"></div>
					</div>
					<div class="mrd-card">
						<div class="mrd-card-title">Yield by Processing Type</div>
						<div class="mrd-yield-panels"></div>
					</div>
				</div>

				<div class="mrd-row mrd-row-3">
					<div class="mrd-card mrd-card-wide">
						<div class="mrd-card-title">Runs by Operation</div>
						<div class="mrd-op-yields" id="mrd-op-yields"></div>
						<div class="mrd-legend mrd-op-legend" id="mrd-op-legend"></div>
					</div>
				</div>

				<div class="mrd-row mrd-row-3">
					<div class="mrd-card">
						<div class="mrd-card-title">Suboperation Status (All Runs)</div>
						<div class="mrd-subop-table"></div>
					</div>
					<div class="mrd-card">
						<div class="mrd-card-title">Employee Hours</div>
						<div class="mrd-donut-wrap" id="mrd-emp-donut"></div>
						<div class="mrd-legend" id="mrd-emp-legend"></div>
					</div>
					<div class="mrd-card mrd-card-fill">
						<div class="mrd-card-title">Runs Started vs Completed</div>
						<div id="mrd-weekday-chart"></div>
					</div>
				</div>

				<div class="mrd-card mrd-runs-detail">
					<div class="mrd-runs-header">
						<div class="mrd-card-title">Runs Detail</div>
						<div class="mrd-runs-filters">
							<div class="mrd-filter-run mrd-link-filter"></div>
							<div class="mrd-filter-batch mrd-link-filter"></div>
							<div class="mrd-filter-run-item mrd-link-filter"></div>
							<select class="form-control input-sm mrd-filter-type"><option value="">All Processing Types</option></select>
							<select class="form-control input-sm mrd-filter-status">
								<option value="">All Statuses</option>
								<option value="Open">Open</option>
								<option value="In Progress">In Progress</option>
								<option value="Completed">Completed</option>
							</select>
						</div>
					</div>
					<div class="table-responsive">
						<table class="table mrd-table">
							<thead>
								<tr>
									<th>Run #</th><th>Raw Material</th><th>Batch</th><th>Status</th>
									<th>150u Hash</th><th>120u-73u Hash</th><th>45u Hash</th>
									<th>150u Rosin</th><th>120u-73u Rosin</th><th>45u Rosin</th>
									<th>Hash Yield</th><th>Rosin Yield</th><th>Hash to Rosin Yield</th>
									<th>Total Time</th><th>Started By</th><th>Started On</th><th>Completed On</th>
								</tr>
							</thead>
							<tbody class="mrd-table-body"></tbody>
						</table>
					</div>
					<div class="mrd-pagination"></div>
				</div>
			</div>
		`);

		this.page.main.find('.mrd-week-option').on('click', (e) => {
			e.preventDefault();
			let preset = $(e.currentTarget).attr('data-preset');
			let today = frappe.datetime.get_today();
			if (preset === 'today' || preset === 'yesterday') {
				let day = preset === 'yesterday' ? this.add_days(today, -1) : today;
				this.from_date = day;
				this.to_date = day;
			} else {
				let monday = this.monday_of(today);
				if (preset === 'last_week') monday = this.add_days(monday, -7);
				this.from_date = monday;
				this.to_date = this.add_days(monday, 6);
			}
			this.date_preset = preset;
			this.runs_page = 1;
			this.reload_all();
		});
		this.page.main.find('.mrd-week-custom').on('click', (e) => e.stopPropagation());
		this.page.main.find('.mrd-apply-range').on('click', () => {
			let from = this.page.main.find('.mrd-from-date').val();
			let to = this.page.main.find('.mrd-to-date').val();
			if (!from || !to) {
				frappe.show_alert({ message: __('Pick both a From Date and a To Date'), indicator: 'orange' });
				return;
			}
			this.from_date = from;
			this.to_date = to;
			this.date_preset = 'custom';
			this.runs_page = 1;
			this.reload_all();
			this.page.main.find('.mrd-week-btn').dropdown('toggle');
		});
		// Run # / Batch / Item: three Link filters on the table only.
		this.make_runs_link_filter('.mrd-filter-run', 'Material Request', 'run', 'Run #',
			() => ({ filters: { material_request_type: 'Manufacture', docstatus: 1 } }));
		this.make_runs_link_filter('.mrd-filter-batch', 'Project', 'batch', 'Batch');
		this.make_runs_link_filter('.mrd-filter-run-item', 'Item', 'run_item', 'Item');
		this.page.main.find('.mrd-filter-type').on('change', (e) => {
			this.runs_filters.processing_type = $(e.target).val();
			this.runs_page = 1;
			this.load_runs_detail();
		});
		this.page.main.find('.mrd-filter-status').on('change', (e) => {
			this.runs_filters.status = $(e.target).val();
			this.runs_page = 1;
			this.load_runs_detail();
		});
	}

	// Company/Project/Item are rendered as real Frappe Link controls
	// (search-as-you-type against the actual doctype), restricted via
	// get_query to only the values that actually appear on a Job Card —
	// picking anything else would always show an empty dashboard. Date
	// filters stay as the dropdown/date-range picker built in render_shell.
	load_filter_options() {
		frappe.call({
			method: `${MRD_METHOD}.get_filter_options`,
			callback: (r) => {
				if (!r.message) return;
				let opts = r.message;
				this.make_link_filter('.mrd-filter-company', 'Company', 'company', 'All Companies', opts.companies);
				this.make_link_filter(
					'.mrd-filter-project', 'Project', 'project', 'All Projects',
					opts.projects.map((p) => p.value)
				);
				this.make_link_filter(
					'.mrd-filter-item', 'Item', 'item', 'All Items',
					opts.items.map((i) => i.value)
				);
			},
		});
	}

	make_link_filter(selector, doctype, fieldname, placeholder, allowed_values) {
		let $wrapper = this.page.main.find(selector);
		let control = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				options: doctype,
				fieldname: fieldname,
				placeholder: placeholder,
				get_query: () => ({ filters: [['name', 'in', allowed_values]] }),
				onchange: () => {
					this.global_filters[fieldname] = control.get_value() || '';
					this.runs_page = 1;
					this.reload_all();
				},
			},
			parent: $wrapper[0],
			render_input: true,
		});
	}

	// Like make_link_filter, but for the Runs Detail table: changing one only
	// reloads the table, not the whole dashboard.
	make_runs_link_filter(selector, doctype, fieldname, placeholder, get_query) {
		let control = frappe.ui.form.make_control({
			df: {
				fieldtype: 'Link',
				options: doctype,
				fieldname: fieldname,
				placeholder: placeholder,
				get_query: get_query,
				onchange: () => {
					let value = control.get_value() || '';
					if (value === this.runs_filters[fieldname]) return;
					this.runs_filters[fieldname] = value;
					this.runs_page = 1;
					this.load_runs_detail();
				},
			},
			parent: this.page.main.find(selector)[0],
			render_input: true,
		});
		return control;
	}

	update_date_label() {
		let start = frappe.datetime.str_to_user(this.from_date);
		let end = frappe.datetime.str_to_user(this.to_date);
		let preset_labels = { today: 'Today', yesterday: 'Yesterday', this_week: 'This Week', last_week: 'Last Week', custom: 'Custom Range' };
		this.page.main.find('.mrd-week-preset').text(preset_labels[this.date_preset] || 'Custom Range');
		this.page.main.find('.mrd-week-label').text(`${start} – ${end}`);
		this.page.main.find('.mrd-from-date').val(this.from_date);
		this.page.main.find('.mrd-to-date').val(this.to_date);
	}

	load_dashboard() {
		this.update_date_label();
		frappe.call({
			method: `${MRD_METHOD}.get_dashboard_data`,
			args: Object.assign({ from_date: this.from_date, to_date: this.to_date }, this.global_filters),
			callback: (r) => {
				if (!r.message) return;
				this.data = r.message;
				this.render_stat_cards();
				this.render_status_donut();
				this.render_type_donut();
				this.render_op_work();
				this.render_yield_panels();
				this.render_subop_table();
				this.render_employee_donut();
				this.render_weekday_chart();
				this.populate_type_filter();
			},
		});
	}

	populate_type_filter() {
		let $sel = this.page.main.find('.mrd-filter-type');
		let current = $sel.val();
		let types = (this.data.processing_types || []);
		$sel.html('<option value="">All Processing Types</option>' +
			types.map((t) => `<option value="${frappe.utils.escape_html(t)}">${frappe.utils.escape_html(t)}</option>`).join(''));
		if (current) $sel.val(current);
	}

	render_stat_cards() {
		let s = this.data.stat_cards;
		let change_html = (pct) => {
			if (pct === null || pct === undefined) return '';
			let up = pct >= 0;
			return `<span class="mrd-stat-change ${up ? 'up' : 'down'}">${up ? '&uarr;' : '&darr;'} ${Math.abs(pct)}% vs previous period</span>`;
		};
		let hash_row = ((this.data.processing_type || {}).rows || []).find((r) => r.label === 'Hash Processing');
		let hash_runs = hash_row ? hash_row.count : null;
		let cards = [
			{
				label: 'Runs Planned',
				value: s.runs_planned,
				extra: change_html(s.runs_planned_change_pct) +
					'<span class="mrd-stat-note">(Material Requests created)</span>',
			},
			{
				// Washed counts Hash runs whose Wash Cycle is done, so it can be
				// lower than the Hash runs started -- say "of N" so it reads
				// against that total.
				label: 'Washed',
				value: s.washed_count,
				extra: `<span class="mrd-stat-note">${hash_runs !== null ? `of ${hash_runs} Hash run${hash_runs === 1 ? '' : 's'} &middot; ` : ''}`
					+ `${format_number(s.washed_pounds, null, 2)} lb &middot; ${format_number(s.washed_grams, null, 2)} g</span>`,
			},
		];
		this.page.main.find('.mrd-stat-row').html(cards.map((c) => `
			<div class="mrd-stat-card">
				<div class="mrd-stat-label">${c.label}</div>
				<div class="mrd-stat-value">${c.value}</div>
				${c.extra}
			</div>
		`).join(''));
	}

	render_status_donut() {
		let b = this.data.run_status_overview.buckets;
		let labels = Object.keys(b);
		let values = labels.map((k) => b[k]);
		this.page.main.find('#mrd-status-donut').html('');
		if (typeof frappe.Chart !== 'undefined' && this.data.run_status_overview.total) {
			new frappe.Chart('#mrd-status-donut', {
				type: 'donut',
				height: 200,
				colors: labels.map((l) => MRD_STATUS_COLORS[l] || '#94a3b8'),
				data: { labels, datasets: [{ values }] },
			});
		} else {
			this.page.main.find('#mrd-status-donut').html('<div class="mrd-empty">No runs in this period</div>');
		}
		this.page.main.find('#mrd-status-legend').html(
			`<div class="mrd-donut-total">${this.data.run_status_overview.total}<span>Total Runs</span></div>` +
			labels.map((l) => `
				<div class="mrd-legend-row">
					<span class="mrd-dot" style="background:${MRD_STATUS_COLORS[l] || '#94a3b8'}"></span>
					${l} <b>${b[l]}</b>
				</div>`).join('')
		);
	}

	render_type_donut() {
		let rows = this.data.processing_type.rows;
		this.page.main.find('#mrd-type-donut').html('');
		if (typeof frappe.Chart !== 'undefined' && rows.length) {
			new frappe.Chart('#mrd-type-donut', {
				type: 'donut',
				height: 200,
				colors: MRD_TYPE_COLORS,
				data: { labels: rows.map((r) => r.label), datasets: [{ values: rows.map((r) => r.count) }] },
			});
		} else {
			this.page.main.find('#mrd-type-donut').html('<div class="mrd-empty">No runs in this period</div>');
		}
		this.page.main.find('#mrd-type-legend').html(
			`<div class="mrd-donut-total">${this.data.processing_type.total}<span>Total Runs</span></div>` +
			rows.map((r, i) => `
				<div class="mrd-legend-row">
					<span class="mrd-dot" style="background:${MRD_TYPE_COLORS[i % MRD_TYPE_COLORS.length]}"></span>
					${frappe.utils.escape_html(r.label)} <b>${r.count} (${r.pct}%)</b>
				</div>`).join('')
		);
	}

	// Who worked what: each employee, with the operations they logged time
	// on underneath (time and runs), busiest first. Yield is per process, not
	// per person, so it sits once at the top -- Wash Cycle for Hash, Press
	// Run for Rosin, the same figures as Yield by Processing Type.
	render_op_work() {
		let data = this.data.operation_breakdown || { rows: [] };
		const STEP_ORDER = ['Wash Cycle', 'Collection & Weigh', 'Freeze Drying', 'Bubble Sifting',
			'Press Run', 'Jar Filling', 'Cold Cure', 'Whipping'];
		let step_rank = (op) => { let i = STEP_ORDER.indexOf(op); return i === -1 ? STEP_ORDER.length : i; };

		let yields = Object.fromEntries((this.data.yield_by_type || []).map((y) => [y.label, y]));
		let yield_for = { 'Wash Cycle': 'Hash Processing', 'Press Run': 'Rosin Pressing' };
		this.page.main.find('#mrd-op-yields').html(Object.entries(yield_for).map(([op, family]) => {
			let y = yields[family];
			return y ? `<div class="mrd-op-yield">${frappe.utils.escape_html(op)} yield <b>${y.avg_yield_pct}%</b>
				<span>${y.total_output_kg} kg from ${y.total_input_kg} kg</span></div>` : '';
		}).join(''));

		let people = {};
		(data.rows || []).forEach((r) => (r.employees || []).forEach((e) => {
			let p = (people[e.employee] = people[e.employee] || { name: e.employee, mins: 0, ops: [] });
			p.mins += flt(e.mins);
			p.ops.push({ op: r.label, mins: e.mins, runs: e.runs });
		}));
		let list = Object.values(people).sort((a, b) => b.mins - a.mins);
		list.forEach((p) => p.ops.sort((a, b) => step_rank(a.op) - step_rank(b.op)));

		this.page.main.find('#mrd-op-legend').html(list.length ? list.map((p, i) => `
			<div class="mrd-op-block">
				<div class="mrd-legend-row">
					<span class="mrd-dot" style="background:${MRD_OP_COLORS[i % MRD_OP_COLORS.length]}"></span>
					${frappe.utils.escape_html(p.name)} <b>${this.fmt_mins(p.mins)}</b>
				</div>
				${p.ops.map((o) => {
					let y = ((data.employee_yield || {})[p.name] || {})[o.op];
					return `
				<div class="mrd-op-employee">
					<span>${frappe.utils.escape_html(o.op)}</span>
					<span>${this.fmt_mins(o.mins)} &middot; ${o.runs} run${o.runs === 1 ? '' : 's'}</span>
				</div>${y ? `
				<div class="mrd-op-employee mrd-op-employee-yield">
					<span>Yield <b>${y.yield_pct}%</b></span>
					<span>${y.output_kg} kg from ${y.input_kg} kg &middot; ${y.runs} run${y.runs === 1 ? '' : 's'}</span>
				</div>` : ''}`;
				}).join('')}
			</div>`).join('') : '<div class="mrd-empty">No time logged in this period</div>');
	}

	// 95 -> "1h 35m"; under a minute shows seconds so short test logs aren't "0m".
	fmt_mins(mins) {
		mins = flt(mins);
		if (mins > 0 && mins < 1) return `${Math.round(mins * 60)}s`;
		let h = Math.floor(mins / 60), m = Math.round(mins % 60);
		if (m === 60) { h += 1; m = 0; }
		return h ? `${h}h ${m}m` : `${m}m`;
	}

	render_yield_panels() {
		let rows = this.data.yield_by_type;
		let html = rows.length ? rows.map((r, i) => `
			<div class="mrd-yield-panel">
				<div class="mrd-yield-title" style="color:${MRD_TYPE_COLORS[i % MRD_TYPE_COLORS.length]}">${frappe.utils.escape_html(r.label)}</div>
				<div class="mrd-yield-pct">${r.avg_yield_pct}%<span>Avg. Yield</span></div>
				<div class="mrd-yield-bar"><div class="mrd-yield-bar-fill" style="width:${Math.min(r.avg_yield_pct, 100)}%;background:${MRD_TYPE_COLORS[i % MRD_TYPE_COLORS.length]}"></div></div>
				<div class="mrd-yield-output">Total Output <b>${r.total_output_kg} kg</b></div>
				<div class="mrd-yield-input">(from ${r.total_input_kg} kg input)</div>
			</div>
		`).join('') : '<div class="mrd-empty">No runs in this period</div>';
		this.page.main.find('.mrd-yield-panels').html(html);
	}

	render_subop_table() {
		let rows = this.data.suboperation_status;
		if (!rows.length) {
			this.page.main.find('.mrd-subop-table').html('<div class="mrd-empty">No sub-operations in this period</div>');
			return;
		}
		let stack_bar = (row) => {
			let total = row.total || 1;
			let segs = ['Completed', 'In Progress', 'Pending']
				.filter((k) => row[k] > 0)
				.map((k) => `<div class="mrd-subop-seg" style="width:${(row[k] / total) * 100}%;background:${MRD_SUBOP_COLORS[k]}"></div>`)
				.join('');
			return `
				<div class="mrd-subop-bar-cell">
					<div class="mrd-subop-stackbar">${segs}</div>
					<span class="mrd-subop-bar-label">${row.Completed}</span>
				</div>`;
		};
		this.page.main.find('.mrd-subop-table').html(`
			<table class="table mrd-subop-inner">
				<thead><tr><th>Suboperation</th><th>Completed</th><th>Pending</th><th>Total</th></tr></thead>
				<tbody>
					${rows.map((r) => `
						<tr>
							<td>${frappe.utils.escape_html(r.name)}</td>
							<td>${stack_bar(r)}</td>
							<td>${r.Pending}</td>
							<td class="mrd-subop-total">${r.total}</td>
						</tr>
					`).join('')}
				</tbody>
			</table>
		`);
	}

	render_employee_donut() {
		let d = this.data.employee_hours;
		this.page.main.find('#mrd-emp-donut').html('');
		if (typeof frappe.Chart !== 'undefined' && d.rows.length) {
			new frappe.Chart('#mrd-emp-donut', {
				type: 'donut',
				height: 200,
				colors: MRD_TYPE_COLORS,
				data: { labels: d.rows.map((r) => r.label), datasets: [{ values: d.rows.map((r) => r.hours) }] },
			});
		} else {
			this.page.main.find('#mrd-emp-donut').html('<div class="mrd-empty">No time logged in this period</div>');
		}
		this.page.main.find('#mrd-emp-legend').html(
			`<div class="mrd-donut-total">${d.total_hours}<span>Total Hours</span></div>` +
			d.rows.map((r, i) => `
				<div class="mrd-legend-row">
					<span class="mrd-dot" style="background:${MRD_TYPE_COLORS[i % MRD_TYPE_COLORS.length]}"></span>
					${frappe.utils.escape_html(r.label)} <b>${r.hours}h (${r.pct}%)</b>
				</div>`).join('')
		);
	}

	// The chart fills its card: the row stretches every card to the tallest
	// one beside it (Suboperation Status), so the height is read off the
	// card once the old chart is cleared, and again on window resize.
	render_weekday_chart() {
		if (!this.data) return;
		let rows = this.data.started_vs_completed;
		let el = this.page.main.find('#mrd-weekday-chart')[0];
		if (!el) return;
		el.innerHTML = '';
		if (typeof frappe.Chart === 'undefined') return;
		let $card = $(el).closest('.mrd-card');
		let title = $card.find('.mrd-card-title').outerHeight(true) || 0;
		let padding = $card.innerHeight() - $card.height();
		const LEGEND = 40;  // frappe.Chart draws its legend below the given height
		let height = Math.max(220, Math.floor($card.innerHeight() - padding - title - LEGEND));
		if (!this._weekday_resize_bound) {
			this._weekday_resize_bound = true;
			$(window).on('resize.mrd-weekday', frappe.utils.debounce(() => this.render_weekday_chart(), 250));
		}
		new frappe.Chart(el, {
			type: 'bar',
			height: height,
			colors: ['#7c3aed', '#10b981'],
			data: {
				labels: rows.map((r) => r.day),
				datasets: [
					{ name: 'Started', values: rows.map((r) => r.started) },
					{ name: 'Completed', values: rows.map((r) => r.completed) },
				],
			},
			axisOptions: { xIsSeries: 1 },
			barOptions: { spaceRatio: 0.3 },
		});
	}

	load_runs_detail() {
		frappe.call({
			method: `${MRD_METHOD}.get_runs_detail`,
			args: Object.assign(
				{ from_date: this.from_date, to_date: this.to_date, page: this.runs_page, page_size: this.runs_page_size },
				this.global_filters,
				this.runs_filters
			),
			callback: (r) => {
				if (!r.message) return;
				this.render_runs_table(r.message.rows, r.message.total_count);
			},
		});
	}

	render_runs_table(rows, total_count) {
		let status_badge = (status) => {
			let color = MRD_STATUS_COLORS[({ Open: 'Open', Completed: 'Completed' }[status]) || 'In Progress'] || '#94a3b8';
			return `<span class="mrd-status-pill" style="background:${color}22;color:${color}">${frappe.utils.escape_html(status)}</span>`;
		};
		// Micron weights are grams; a run that collected nothing at a size
		// shows a dash rather than a misleading 0.0.
		let grams = (v) => (v ? `${v} g` : '-');
		let body = rows.length ? rows.map((r) => `
			<tr>
				<td><a href="/app/material-request/${encodeURIComponent(r.run_id)}">${frappe.utils.escape_html(r.run_id)}</a></td>
				<td>${frappe.utils.escape_html(r.raw_material)}</td>
				<td>${frappe.utils.escape_html(r.batch_name)}</td>
				<td>${status_badge(r.status)}</td>
				<td>${grams(r.hash_150u)}</td>
				<td>${grams(r.hash_120u_73u)}</td>
				<td>${grams(r.hash_45u)}</td>
				<td>${grams(r.rosin_150u)}</td>
				<td>${grams(r.rosin_120u_73u)}</td>
				<td>${grams(r.rosin_45u)}</td>
				<td>${r.hash_yield ? r.hash_yield + '%' : '-'}</td>
				<td>${r.rosin_yield ? r.rosin_yield + '%' : '-'}</td>
				<td>${r.hash_to_rosin_yield ? r.hash_to_rosin_yield + '%' : '-'}</td>
				<td>${r.total_time}</td>
				<td>${frappe.utils.escape_html(r.started_by)}</td>
				<td>${r.started_on}</td>
				<td>${r.completed_on}</td>
			</tr>
		`).join('') : `<tr><td colspan="17" class="mrd-empty">No runs match these filters</td></tr>`;
		this.page.main.find('.mrd-table-body').html(body);
		this.render_pagination(total_count);
	}

	render_pagination(total_count) {
		let total_pages = Math.max(1, Math.ceil(total_count / this.runs_page_size));
		let start = (this.runs_page - 1) * this.runs_page_size + (total_count ? 1 : 0);
		let end = Math.min(this.runs_page * this.runs_page_size, total_count);
		let pages = [];
		for (let p = 1; p <= total_pages; p++) pages.push(p);
		let $el = this.page.main.find('.mrd-pagination');
		$el.html(`
			<span class="mrd-page-info">Showing ${start}-${end} of ${total_count} runs</span>
			<span class="mrd-page-buttons">
				${pages.map((p) => `<button class="btn btn-xs ${p === this.runs_page ? 'btn-primary' : 'btn-default'} mrd-page-btn" data-page="${p}">${p}</button>`).join('')}
			</span>
		`);
		$el.find('.mrd-page-btn').on('click', (e) => {
			this.runs_page = parseInt($(e.target).attr('data-page'), 10);
			this.load_runs_detail();
		});
	}
}
