// Copyright (c) 2026, alltechvirtual.com and contributors
// Employee Timesheet — hours and overtime per employee, per shift day.
// All aggregation (time zone, shift-day attribution, overtime) is server-side
// in employee_timesheet.py; this renders what it returns.

const ETS = 'cannabis_management.cannabis_management.page.employee_timesheet.employee_timesheet.';

frappe.pages['employee-timesheet'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Employee Timesheet'),
		single_column: true,
	});
	wrapper.page = page;
	page.ets = { data: null, period_offset: 0, filters: {} };

	page.main.html(`
		<div class="ets-root"><div class="ets-inner">
			<div class="ets-head">
				<div>
					<div class="ets-title">${__('Employee Timesheet')}</div>
					<div class="ets-sub" id="ets-sub">${__('Loading…')}</div>
				</div>
			</div>

			<div class="ets-cards" id="ets-cards"></div>

			<div class="ets-filters">
				<div class="ets-f">
					<label>${__('Pay Period')}</label>
					<div class="ets-chips" id="ets-periods">
						<button class="ets-chip on" data-offset="0">${__('This period')}</button>
						<button class="ets-chip" data-offset="-1">${__('Last period')}</button>
						<button class="ets-chip" data-range="week">${__('This week')}</button>
						<button class="ets-chip" data-range="yesterday">${__('Yesterday')}</button>
					</div>
				</div>
				<div class="ets-f">
					<label>${__('From')}</label>
					<input type="date" id="ets-from">
				</div>
				<div class="ets-f">
					<label>${__('To')}</label>
					<input type="date" id="ets-to">
				</div>
				<div class="ets-f">
					<label>${__('Employee')}</label>
					<select id="ets-employee"><option value="">${__('All employees')}</option></select>
				</div>
				<div class="ets-f">
					<label>${__('Show')}</label>
					<div class="ets-toggles">
						<label class="ets-check" id="ets-ot-wrap">
							<input type="checkbox" id="ets-ot-only"> ${__('Overtime only')}
						</label>
						<label class="ets-check" id="ets-open-wrap">
							<input type="checkbox" id="ets-open"> ${__('Include open shifts')}
						</label>
						<button class="ets-apply" id="ets-run">${__('Apply')}</button>
						<button class="ets-pdf" id="ets-export">${__('Export PDF')}</button>
					</div>
				</div>
			</div>

			<div class="ets-tablewrap" id="ets-table">
				<div class="ets-empty">${__('Loading…')}</div>
			</div>

			<div class="ets-note" id="ets-note"></div>
		</div></div>
	`);

	bind(page);
	load_employees(page);
	set_period(page, 0);
};

function bind(page) {
	page.main.find('#ets-run').on('click', () => load(page));
	page.main.find('#ets-export').on('click', () => export_pdf(page));

	page.main.find('#ets-periods').on('click', '.ets-chip', function () {
		page.main.find('#ets-periods .ets-chip').removeClass('on');
		$(this).addClass('on');
		const offset = $(this).data('offset');
		const range = $(this).data('range');
		if (range === 'week') set_week(page);
		else if (range === 'yesterday') set_yesterday(page);
		else set_period(page, offset);
	});

	page.main.find('#ets-employee').on('change', () => load(page));
	page.main.find('#ets-ot-only, #ets-open').on('change', function () {
		$(this).closest('.ets-check').toggleClass('on', this.checked);
		load(page);
	});
	page.main.find('#ets-from, #ets-to').on('change', function () {
		// A hand-picked date range is no longer one of the presets.
		page.main.find('#ets-periods .ets-chip').removeClass('on');
		load(page);
	});
}

function load_employees(page) {
	frappe.call({
		method: 'frappe.client.get_list',
		args: {
			doctype: 'Employee', filters: { status: 'Active' },
			fields: ['name', 'employee_name'], order_by: 'employee_name', limit_page_length: 0,
		},
		callback: function (r) {
			const $sel = page.main.find('#ets-employee');
			(r.message || []).forEach((e) => {
				$sel.append(`<option value="${frappe.utils.escape_html(e.name)}">${frappe.utils.escape_html(e.employee_name || e.name)}</option>`);
			});
		},
	});
}

function set_period(page, offset) {
	frappe.call({
		method: ETS + 'get_pay_period',
		args: { offset: offset || 0 },
		callback: function (r) {
			if (!r || !r.message) return;
			page.main.find('#ets-from').val(r.message.from_date);
			page.main.find('#ets-to').val(r.message.to_date);
			load(page);
		},
	});
}

function set_week(page) {
	// Friday-to-Thursday, matching how the fortnight is cut.
	const today = frappe.datetime.get_today();
	const dow = frappe.datetime.str_to_obj(today).getDay();   // 0 Sun … 5 Fri
	const back = (dow - 5 + 7) % 7;
	const from = frappe.datetime.add_days(today, -back);
	page.main.find('#ets-from').val(from);
	page.main.find('#ets-to').val(frappe.datetime.add_days(from, 6));
	load(page);
}

function set_yesterday(page) {
	const y = frappe.datetime.add_days(frappe.datetime.get_today(), -1);
	page.main.find('#ets-from').val(y);
	page.main.find('#ets-to').val(y);
	load(page);
}

function current_filters(page) {
	return {
		from_date: page.main.find('#ets-from').val(),
		to_date: page.main.find('#ets-to').val(),
		employee: page.main.find('#ets-employee').val() || '',
		overtime_only: page.main.find('#ets-ot-only').is(':checked') ? 1 : 0,
		include_open: page.main.find('#ets-open').is(':checked') ? 1 : 0,
	};
}

function export_pdf(page) {
	const f = current_filters(page);
	if (!f.from_date || !f.to_date) return;
	// The method sets a download response, so this has to be a real navigation
	// rather than a frappe.call — the browser saves the file itself.
	const url = '/api/method/' + ETS + 'export_pdf?' + $.param(f);
	window.open(url, '_blank');
}

function load(page) {
	const f = current_filters(page);
	if (!f.from_date || !f.to_date) return;

	frappe.call({
		method: ETS + 'get_timesheet',
		args: f,
		callback: function (r) {
			if (!r || !r.message) return;
			page.ets.data = r.message;
			render(page);
		},
	});
}

function hrs(v) {
	return (v || 0).toFixed(2);
}

function render(page) {
	const d = page.ets.data;
	const s = d.summary;

	page.main.find('#ets-sub').text(
		__('{0} to {1} · {2} · {3} onwards counts as overtime',
			[d.from_date, d.to_date, d.timezone.replace('_', ' '), d.overtime_after + 'h'])
	);

	page.main.find('#ets-cards').html(`
		<div class="ets-card">
			<div class="ets-card-label">${__('TOTAL HOURS')}</div>
			<div class="ets-card-value">${hrs(s.total_hours)}</div>
			<div class="ets-card-sub">${s.employees} ${__('employees')} · ${s.days} ${__('days')}</div>
		</div>
		<div class="ets-card ok">
			<div class="ets-card-label">${__('REGULAR')}</div>
			<div class="ets-card-value">${hrs(s.regular_hours)}</div>
			<div class="ets-card-sub">${__('up to {0}h per shift day', [d.overtime_after])}</div>
		</div>
		<div class="ets-card ot">
			<div class="ets-card-label">${__('OVERTIME')}</div>
			<div class="ets-card-value">${hrs(s.overtime_hours)}</div>
			<div class="ets-card-sub">${__('beyond {0}h per shift day', [d.overtime_after])}</div>
		</div>
		<div class="ets-card mut">
			<div class="ets-card-label">${__('OPEN SHIFTS')}</div>
			<div class="ets-card-value">${s.open_sessions}</div>
			<div class="ets-card-sub">${__('still clocked in')}</div>
		</div>
	`);

	const $t = page.main.find('#ets-table');
	if (!d.rows.length) {
		$t.html(`<div class="ets-empty">${__('No timesheet entries in this range.')}</div>`);
	} else {
		$t.html(build_table(d.rows));
	}

	page.main.find('#ets-note').html(
		__('A shift is counted on the day it <b>started</b>, so a night shift running past midnight stays on that night. Overtime is calculated per employee per shift day, across all their sessions that day. Times shown in {0}.', [d.timezone])
	);
}

function build_table(rows) {
	// Group by employee so each person reads as a block with their own total.
	const order = [], byEmp = {};
	rows.forEach((r) => {
		if (!byEmp[r.employee]) { byEmp[r.employee] = []; order.push(r.employee); }
		byEmp[r.employee].push(r);
	});

	let html = `<table class="ets-table"><thead><tr>
		<th class="ets-col-emp">${__('Employee')}</th>
		<th class="ets-col-day">${__('Shift Day')}</th>
		<th class="ets-col-time">${__('First In')}</th>
		<th class="ets-col-time">${__('Last Out')}</th>
		<th class="ets-num ets-col-n">${__('Sessions')}</th>
		<th class="ets-num ets-col-h">${__('Total')}</th>
		<th class="ets-num ets-col-h">${__('Regular')}</th>
		<th class="ets-num ets-col-h">${__('Overtime')}</th>
	</tr></thead><tbody>`;

	order.forEach((emp) => {
		const list = byEmp[emp];
		const tot = list.reduce((a, r) => a + r.hours, 0);
		const reg = list.reduce((a, r) => a + r.regular_hours, 0);
		const ot = list.reduce((a, r) => a + r.overtime_hours, 0);

		const name = list[0].employee_name || '';
		const initials = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0] || '').join('').toUpperCase();
		html += `<tr class="ets-emp-row">
			<td><span class="ets-emp-name"><span class="ets-avatar">${frappe.utils.escape_html(initials)}</span>${frappe.utils.escape_html(name)}</span></td>
			<td colspan="3" class="ets-emp-meta">${list.length} ${list.length === 1 ? __('shift day') : __('shift days')}</td>
			<td class="ets-num">${list.reduce((a, r) => a + r.sessions, 0)}</td>
			<td class="ets-num">${hrs(tot)}</td>
			<td class="ets-num">${hrs(reg)}</td>
			<td class="ets-num ${ot > 0 ? 'ets-ot' : 'ets-ot-zero'}">${hrs(ot)}</td>
		</tr>`;

		list.forEach((r) => {
			html += `<tr class="ets-day-row">
				<td></td>
				<td class="ets-day-cell">${r.shift_day}
					${r.crosses_midnight ? `<span class="ets-badge">${__('overnight')}</span>` : ''}
					${r.open_sessions ? `<span class="ets-badge open">${__('open')}</span>` : ''}
				</td>
				<td class="ets-time">${(r.first_in || '').slice(11)}</td>
				<td class="ets-time">${(r.last_out || '').slice(11)}</td>
				<td class="ets-num">${r.sessions}</td>
				<td class="ets-num">${hrs(r.hours)}</td>
				<td class="ets-num">${hrs(r.regular_hours)}</td>
				<td class="ets-num ${r.overtime_hours > 0 ? 'ets-ot' : 'ets-ot-zero'}">${hrs(r.overtime_hours)}</td>
			</tr>`;
		});
	});

	return html + '</tbody></table>';
}
