frappe.ui.form.on('Conversion Entry', {
	refresh: function (frm) {
		_set_warehouse_filters(frm);

		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.trigger('prepare_timer_buttons');
		}
	},

	company: function (frm) {
		_set_warehouse_filters(frm);
		(frm.doc.items || []).forEach(function (row) {
			frappe.model.set_value(row.doctype, row.name, 'source_warehouse', '');
			frappe.model.set_value(row.doctype, row.name, 'target_warehouse', '');
		});
	},

	// ── Timer ─────────────────────────────────────────────────────────────────

	prepare_timer_buttons: function (frm) {
		frm.trigger('make_dashboard');

		if (!frm.doc.started_time && !frm.doc.current_time) {
			frm.add_custom_button(__('Start Job'), () => {
				frm.events.start_job(frm);
			}).addClass('btn-primary');

		} else if (frm.doc.timer_status === 'On Hold') {
			frm.add_custom_button(__('Resume Job'), () => {
				frm.events.start_job(frm, 'Resume Job');
			}).addClass('btn-primary');

		} else {
			frm.add_custom_button(__('Pause Job'), () => {
				frm.events.complete_job(frm, 'On Hold');
			});

			frm.add_custom_button(__('Complete Job'), () => {
				frm.events.complete_job(frm, 'Complete');
			}).addClass('btn-primary');
		}
	},

	start_job: function (frm, status) {
		if (!frm.doc.workstation) {
			frappe.msgprint(__('Please set a Workstation before starting the job.'));
			return;
		}

		frappe.db.get_value('Employee', { user_id: frappe.session.user }, 'name', function (val) {
			let default_employee = (val && val.name) || '';

			frappe.prompt(
				{
					fieldtype: 'Link',
					fieldname: 'employee',
					label: __('Employee'),
					options: 'Employee',
					default: default_employee,
				},
				function (d) {
					const args = {
						conversion_entry: frm.doc.name,
						start_time: frappe.datetime.now_datetime(),
						employee: d.employee || '',
						status: status || 'Work In Progress',
					};
					frm.events.make_time_log(frm, args);
				},
				__('Assign Job to Employee')
			);
		});
	},

	complete_job: function (frm, status) {
		const args = {
			conversion_entry: frm.doc.name,
			complete_time: frappe.datetime.now_datetime(),
			status: status,
		};
		frm.events.make_time_log(frm, args);
	},

	make_time_log: function (frm, args) {
		frappe.call({
			method: 'cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry.make_ce_time_log',
			args: { args: args },
			freeze: true,
			callback: function () {
				frm.reload_doc();
				frm.trigger('make_dashboard');
			},
		});
	},

	make_dashboard: function (frm) {
		if (frm.doc.__islocal) return;

		var currentIncrement = frm.events.get_current_time(frm);

		function updateStopwatch(increment) {
			var hours   = Math.floor(increment / 3600);
			var minutes = Math.floor((increment - hours * 3600) / 60);
			var seconds = Math.floor(increment - hours * 3600 - minutes * 60);

			$(section).find('.hours').text(hours   < 10 ? '0' + hours   : '' + hours);
			$(section).find('.minutes').text(minutes < 10 ? '0' + minutes : '' + minutes);
			$(section).find('.seconds').text(seconds < 10 ? '0' + seconds : '' + seconds);
		}

		function initialiseTimer() {
			const interval = setInterval(function () {
				currentIncrement += 1;
				updateStopwatch(currentIncrement);
			}, 1000);
		}

		const timer_html = `
			<div class="stopwatch" style="font-weight:bold;margin:0px 13px 0px 2px;
				color:#545454;font-size:18px;display:inline-block;vertical-align:text-bottom;">
				<span class="hours">00</span>
				<span class="colon">:</span>
				<span class="minutes">00</span>
				<span class="colon">:</span>
				<span class="seconds">00</span>
			</div>`;

		var section = frm.toolbar.page.add_inner_message(timer_html);

		if (frm.doc.started_time || frm.doc.current_time) {
			if (frm.doc.timer_status === 'On Hold') {
				updateStopwatch(currentIncrement);   // static — job is paused
			} else {
				initialiseTimer();                   // live — job is running
			}
		}
	},

	get_current_time: function (frm) {
		let current_time = 0;
		(frm.doc.time_logs || []).forEach(function (d) {
			if (d.to_time) {
				if (d.time_in_mins) {
					current_time += flt(d.time_in_mins, 2) * 60;
				} else {
					current_time += get_seconds_diff(d.to_time, d.from_time);
				}
			} else {
				current_time += get_seconds_diff(frappe.datetime.now_datetime(), d.from_time);
			}
		});
		return current_time;
	},
});


// ── Conversion Entry Time Log child events ────────────────────────────────────

frappe.ui.form.on('Conversion Entry Time Log', {
	from_time: function (frm, cdt, cdn) {
		_calc_ce_time_mins(frm, cdt, cdn);
	},
	to_time: function (frm, cdt, cdn) {
		_calc_ce_time_mins(frm, cdt, cdn);
	},
});

// ── Conversion Entry Item child events ────────────────────────────────────────

frappe.ui.form.on('Conversion Entry Item', {
	conversion_type: function (frm, cdt, cdn) {
		clear_hidden_fields_for_row(frm, cdt, cdn);
	},
	raw_material_1: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_1', 'rm_1_item_group'); },
	raw_material_2: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_2', 'rm_2_item_group'); },
	raw_material_3: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_3', 'rm_3_item_group'); },
	raw_material_4: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_4', 'rm_4_item_group'); },
	raw_material_5: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_5', 'rm_5_item_group'); },
	raw_material_6: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_6', 'rm_6_item_group'); },
	raw_material_7: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_7', 'rm_7_item_group'); },
	finished_good_1: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'finished_good_1', 'fg_1_item_group'); },
	finished_good_2: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'finished_good_2', 'fg_2_item_group'); },
});


// ── Helpers ───────────────────────────────────────────────────────────────────

function _calc_ce_time_mins(frm, cdt, cdn) {
	let row = frappe.get_doc(cdt, cdn);
	if (!row.from_time || !row.to_time) return;
	let mins = moment(row.to_time).diff(moment(row.from_time), 'minutes', true);
	if (mins > 0) {
		frappe.model.set_value(cdt, cdn, 'time_in_mins', flt(mins, 4));
		// Recompute total
		let total = (frm.doc.time_logs || []).reduce(function (s, r) {
			return s + flt(r.time_in_mins);
		}, 0);
		frm.set_value('total_time_in_minutes', flt(total, 4));
	}
}

function get_seconds_diff(d1, d2) {
	return moment(d1).diff(d2, 'seconds');
}

function _set_warehouse_filters(frm) {
	var company = frm.doc.company;
	frm.set_query('source_warehouse', 'items', function () {
		return { filters: { company: company } };
	});
	frm.set_query('target_warehouse', 'items', function () {
		return { filters: { company: company } };
	});
}

function _sync_item_group(cdt, cdn, item_field, group_field) {
	let row  = frappe.get_doc(cdt, cdn);
	let item = row[item_field];
	if (!item) {
		frappe.model.set_value(cdt, cdn, group_field, '');
		return;
	}
	frappe.db.get_value('Item', item, 'item_group', function (val) {
		frappe.model.set_value(cdt, cdn, group_field, (val && val.item_group) || '');
	});
}

function clear_hidden_fields_for_row(frm, cdt, cdn) {
	let row = frappe.get_doc(cdt, cdn);
	let ct  = row.conversion_type;
	if (!ct) return;

	if (!['2 to 1', '2 to 2', '3 to 1', '4 to 1', '5 to 1', '6 to 1', '7 to 1'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'raw_material_2', '');
		frappe.model.set_value(cdt, cdn, 'qty_rm_2', 0);
	}
	if (!['3 to 1', '4 to 1', '5 to 1', '6 to 1', '7 to 1'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'raw_material_3', '');
		frappe.model.set_value(cdt, cdn, 'qty_rm_3', 0);
	}
	if (!['4 to 1', '5 to 1', '6 to 1', '7 to 1'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'raw_material_4', '');
		frappe.model.set_value(cdt, cdn, 'qty_rm_4', 0);
	}
	if (!['5 to 1', '6 to 1', '7 to 1'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'raw_material_5', '');
		frappe.model.set_value(cdt, cdn, 'qty_rm_5', 0);
	}
	if (!['6 to 1', '7 to 1'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'raw_material_6', '');
		frappe.model.set_value(cdt, cdn, 'qty_rm_6', 0);
	}
	if (ct !== '7 to 1') {
		frappe.model.set_value(cdt, cdn, 'raw_material_7', '');
		frappe.model.set_value(cdt, cdn, 'qty_rm_7', 0);
	}
	if (!['1 to 2', '2 to 2'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'finished_good_2', '');
		frappe.model.set_value(cdt, cdn, 'qty_fg_2', 0);
	}
}
