frappe.ui.form.on('Conversion Entry', {
	onload: function (frm) {
		// Default the company on new entries, then run the company handler
		// (applies warehouse filters). Guarded to new docs so opening an
		// existing entry never overwrites its saved company.
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value('company', 'Master Touch Manufacturing');
			frm.trigger('company');
		}
	},

	setup: function (frm) {
		_set_tag_filters(frm);
		_set_raw_material_queries(frm);

		// A retired status stays readable on old entries but is not offered
		// for new ones — see the Conversion Status doctype's `disabled` flag.
		frm.set_query('conversion_status', function () {
			return { filters: { disabled: 0 } };
		});
	},

	refresh: function (frm) {
		_set_warehouse_filters(frm);

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__('Pull Items from Project'), () => _pull_project_items(frm));
		}

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

	// ── Scan-to-select Metric Tag ────────────────────────────────────────────
	// Conversion Entry has no BarcodeScanner and its item table is a fixed
	// set of Raw Material 1-7 / Finished Good 1-3 slots per row rather than
	// one row per item, so it can't reuse metric_tag_scan.js's own
	// apply_row — it reuses that file's lookup()/render_picker() and applies
	// the pick itself. See metric_tag.get_metric_tag_scan.
	scan_metric_tag: function (frm) {
		const value = (frm.doc.scan_metric_tag || '').trim();
		if (!value) return;
		frm.set_value('scan_metric_tag', '');

		cannabis_management.metric_tag_scan.lookup(value, 'Conversion Entry Item').then((data) => {
			if (!data || !data.found) {
				frappe.show_alert({
					message: __('{0} is not a known Metric Tag.', [value]),
					indicator: 'orange',
				});
				return;
			}
			cannabis_management.metric_tag_scan.render_picker(data, (row) =>
				_apply_metric_tag_to_next_rm_slot(frm, data.tag_name, row)
			);
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
	// Opening a row recomputes it, so a row saved before these fields existed
	// -- or edited in another tab -- shows live figures rather than blanks.
	form_render: function (frm, cdt, cdn) {
		for (let n = 1; n <= 7; n++) _sync_grams(frm, cdt, cdn, n);
		_micron_total(frm, cdt, cdn, 'bh');
		_micron_total(frm, cdt, cdn, 'rosin');
	},
	is_bubble_hash: function (frm, cdt, cdn) { _micron_product_toggled(frm, cdt, cdn, 'bh'); },
	bh_micron_150u: function (frm, cdt, cdn) { _micron_toggled(frm, cdt, cdn, 'bh', '150u'); },
	bh_grams_150u: function (frm, cdt, cdn) { _micron_total(frm, cdt, cdn, 'bh'); },
	bh_micron_120u_73u: function (frm, cdt, cdn) { _micron_toggled(frm, cdt, cdn, 'bh', '120u_73u'); },
	bh_grams_120u_73u: function (frm, cdt, cdn) { _micron_total(frm, cdt, cdn, 'bh'); },
	bh_micron_45u: function (frm, cdt, cdn) { _micron_toggled(frm, cdt, cdn, 'bh', '45u'); },
	bh_grams_45u: function (frm, cdt, cdn) { _micron_total(frm, cdt, cdn, 'bh'); },
	is_rosin: function (frm, cdt, cdn) { _micron_product_toggled(frm, cdt, cdn, 'rosin'); },
	rosin_micron_150u: function (frm, cdt, cdn) { _micron_toggled(frm, cdt, cdn, 'rosin', '150u'); },
	rosin_grams_150u: function (frm, cdt, cdn) { _micron_total(frm, cdt, cdn, 'rosin'); },
	rosin_micron_120u_73u: function (frm, cdt, cdn) { _micron_toggled(frm, cdt, cdn, 'rosin', '120u_73u'); },
	rosin_grams_120u_73u: function (frm, cdt, cdn) { _micron_total(frm, cdt, cdn, 'rosin'); },
	rosin_micron_45u: function (frm, cdt, cdn) { _micron_toggled(frm, cdt, cdn, 'rosin', '45u'); },
	rosin_grams_45u: function (frm, cdt, cdn) { _micron_total(frm, cdt, cdn, 'rosin'); },
	qty_rm_1: function (frm, cdt, cdn) { _sync_grams(frm, cdt, cdn, 1); },
	qty_rm_2: function (frm, cdt, cdn) { _sync_grams(frm, cdt, cdn, 2); },
	qty_rm_3: function (frm, cdt, cdn) { _sync_grams(frm, cdt, cdn, 3); },
	qty_rm_4: function (frm, cdt, cdn) { _sync_grams(frm, cdt, cdn, 4); },
	qty_rm_5: function (frm, cdt, cdn) { _sync_grams(frm, cdt, cdn, 5); },
	qty_rm_6: function (frm, cdt, cdn) { _sync_grams(frm, cdt, cdn, 6); },
	qty_rm_7: function (frm, cdt, cdn) { _sync_grams(frm, cdt, cdn, 7); },
	raw_material_1: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_1', 'rm_1_item_group'); _sync_grams(frm, cdt, cdn, 1); },
	raw_material_2: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_2', 'rm_2_item_group'); _sync_grams(frm, cdt, cdn, 2); },
	raw_material_3: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_3', 'rm_3_item_group'); _sync_grams(frm, cdt, cdn, 3); },
	raw_material_4: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_4', 'rm_4_item_group'); _sync_grams(frm, cdt, cdn, 4); },
	raw_material_5: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_5', 'rm_5_item_group'); _sync_grams(frm, cdt, cdn, 5); },
	raw_material_6: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_6', 'rm_6_item_group'); _sync_grams(frm, cdt, cdn, 6); },
	raw_material_7: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'raw_material_7', 'rm_7_item_group'); _sync_grams(frm, cdt, cdn, 7); },
	finished_good_1: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'finished_good_1', 'fg_1_item_group'); },
	finished_good_2: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'finished_good_2', 'fg_2_item_group'); },
	finished_good_3: function (frm, cdt, cdn) { _sync_item_group(cdt, cdn, 'finished_good_3', 'fg_3_item_group'); },
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

// Fills the first empty Raw Material slot (1..7, but never past however many
// this row's conversion_type actually calls for — e.g. "2 to 1" only ever
// fills RM1/RM2) with the picked item, defaulting its qty to what's
// available under the tag and recording the tag on that slot's hidden
// rm_N_tag field for traceability. Starts a new Conversion Entry Item row
// once the current last row's active slots are all full (or there is no row
// yet); a fresh row always starts at RM1.
function _apply_metric_tag_to_next_rm_slot(frm, tag_name, row) {
	function rm_count_for(conversion_type) {
		const match = /^(\d+) to \d+$/.exec(conversion_type || '');
		return match ? Number(match[1]) : 1;
	}

	function first_empty_slot(item_row) {
		const count = Math.min(7, Math.max(1, rm_count_for(item_row.conversion_type)));
		for (let n = 1; n <= count; n++) {
			if (!item_row['raw_material_' + n]) return n;
		}
		return null;
	}

	const items = frm.doc.items || [];
	let target = items.length ? items[items.length - 1] : null;
	let slot = target ? first_empty_slot(target) : null;

	if (!target || slot === null) {
		target = frappe.model.add_child(frm.doc, 'Conversion Entry Item', 'items');
		frm.script_manager.trigger('items_add', target.doctype, target.name);
		slot = 1;
	}

	const rm_field = 'raw_material_' + slot;
	const qty_field = 'qty_rm_' + slot;
	const tag_field = 'rm_' + slot + '_tag';

	if (!row) {
		// Tag resolved but has no stock yet (a fresh/just-registered tag) —
		// nothing to look an item up from, so just record the tag on this
		// slot and leave the item/qty for the user to fill in by hand.
		frappe.model.set_value(target.doctype, target.name, tag_field, tag_name).then(() => {
			frm.refresh_field('items');
			frappe.show_alert({
				message: __('Metric Tag {0} has no stock yet — row #{1}, RM {2} tagged; pick the item by hand.', [tag_name, target.idx, slot]),
				indicator: 'blue',
			});
		});
		return;
	}

	frappe.run_serially([
		() => frappe.model.set_value(target.doctype, target.name, tag_field, tag_name),
		() => frappe.model.set_value(target.doctype, target.name, qty_field, row.qty),
		() => frappe.model.set_value(target.doctype, target.name, rm_field, row.item_code),
		() => {
			frm.refresh_field('items');
			frappe.show_alert({
				message: __('Row #{0}, RM {1}: {2} (qty {3}) set from Metric Tag {4}.', [target.idx, slot, row.item_code, row.qty, tag_name]),
				indicator: 'green',
			});
		},
	]);
}

function clear_hidden_fields_for_row(frm, cdt, cdn) {
	let row = frappe.get_doc(cdt, cdn);
	let ct  = row.conversion_type;
	if (!ct) return;

	if (!['2 to 1', '2 to 2', '3 to 1', '3 to 2', '3 to 3', '4 to 1', '4 to 2', '4 to 3', '5 to 1', '6 to 1', '7 to 1'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'raw_material_2', '');
		frappe.model.set_value(cdt, cdn, 'qty_rm_2', 0);
	}
	if (!['3 to 1', '3 to 2', '3 to 3', '4 to 1', '4 to 2', '4 to 3', '5 to 1', '6 to 1', '7 to 1'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'raw_material_3', '');
		frappe.model.set_value(cdt, cdn, 'qty_rm_3', 0);
	}
	if (!['4 to 1', '4 to 2', '4 to 3', '5 to 1', '6 to 1', '7 to 1'].includes(ct)) {
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
	if (!['1 to 2', '2 to 2', '1 to 3', '3 to 2', '3 to 3', '4 to 2', '4 to 3'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'finished_good_2', '');
		frappe.model.set_value(cdt, cdn, 'qty_fg_2', 0);
	}
	if (!['1 to 3', '3 to 3', '4 to 3'].includes(ct)) {
		frappe.model.set_value(cdt, cdn, 'finished_good_3', '');
		frappe.model.set_value(cdt, cdn, 'qty_fg_3', 0);
	}
}


// ── Source / Target Tag pickers ──────────────────────────────────────────────
// Each Source Tag N follows Raw Material N (filtered by the row's Source
// Warehouse), each Target Tag N follows Finished Good N (Target Warehouse).
// Both restrictions are enforced server-side in custom/metric_tag.py:
//   Source Tag -> status=Active, tag's Licence must equal the warehouse's
//                 METRC Licence #.
//   Target Tag -> status=Unused, same Licence match, but tags that have not
//                 been assigned a Licence yet are allowed through too.
// The status is pinned inside those query methods rather than passed as a
// filter, so it holds even if nothing on the client sends one.
const CE_SOURCE_TAG_QUERY =
	'cannabis_management.cannabis_management.custom.metric_tag.conversion_source_tags';
const CE_TARGET_TAG_QUERY =
	'cannabis_management.cannabis_management.custom.metric_tag.conversion_target_tags';

function _set_tag_filters(frm) {
	// metric_tag_query.js is an app_include_js; guard anyway so a load failure
	// degrades to an unfiltered picker instead of breaking the form.
	if (!window.cannabis_management || !cannabis_management.metric_tag) return;

	for (let n = 1; n <= 7; n++) {
		cannabis_management.metric_tag.filter_by_warehouse(
			frm, 'rm_' + n + '_tag', 'source_warehouse', 'items', CE_SOURCE_TAG_QUERY
		);
	}
	for (let n = 1; n <= 3; n++) {
		cannabis_management.metric_tag.filter_by_warehouse(
			frm, 'fg_' + n + '_tag', 'target_warehouse', 'items', CE_TARGET_TAG_QUERY
		);
	}
}


// ── Raw Material picker ──────────────────────────────────────────────────────
// Shows each item's quantity in that row's Source Warehouse, with the
// in-stock items first. Server side: conversion_entry.raw_material_stock_query.
const CE_RM_QUERY =
	'cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry.raw_material_stock_query';

function _set_raw_material_queries(frm) {
	for (let n = 1; n <= 7; n++) {
		frm.set_query('raw_material_' + n, 'items', function (doc, cdt, cdn) {
			const row = locals[cdt][cdn] || {};
			return {
				query: CE_RM_QUERY,
				// Read live off the row, so changing Source Warehouse re-quotes
				// the quantities on the next search without a reload.
				filters: { warehouse: row.source_warehouse },
			};
		});
	}
}


// ── Yields ───────────────────────────────────────────────────────────────────
// Frozen to Hash % = Hash (g) / Frozen (g) * 100
// Hash to Rosin %  = Rosin (g) / Hash (g) * 100
// Frozen to Rosin % = Rosin (g) / Frozen (g) * 100
// Frozen (g) is every Raw Material quantity in grams, so a multi-material row
// yields against everything it consumed. validate() recomputes all of this
// server-side; this is just so the figures move as you type.
function _sync_yield(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) return;
	let frozen = 0;
	for (let n = 1; n <= 7; n++) frozen += flt(row['qty_rm_' + n + '_g']);
	const hash_g = flt(row.bh_total_grams);
	const rosin_g = flt(row.rosin_total_grams);
	const pct = (num, den) => (den ? flt(num / den * 100, 2) : 0);

	frappe.model.set_value(cdt, cdn, 'total_frozen_grams', flt(frozen, 2));
	frappe.model.set_value(cdt, cdn, 'frozen_to_hash_pct', pct(hash_g, frozen));
	frappe.model.set_value(cdt, cdn, 'hash_to_rosin_pct', pct(rosin_g, hash_g));
	frappe.model.set_value(cdt, cdn, 'frozen_to_rosin_pct', pct(rosin_g, frozen));
	_repaint(frm, cdn, ['total_frozen_grams', 'frozen_to_hash_pct',
		'hash_to_rosin_pct', 'frozen_to_rosin_pct']);
}

// A read-only field in an open grid row keeps showing the value it was drawn
// with, so the figure has to be pushed back onto the row form explicitly --
// otherwise it only appears once the row is reopened or the document saved.
function _repaint(frm, cdn, fieldnames) {
	const grid = frm.get_field('items').grid;
	const grid_row = (grid.grid_rows_by_docname || {})[cdn];
	if (!grid_row || !grid_row.grid_form) return;
	fieldnames.forEach((f) => {
		const control = (grid_row.grid_form.fields_dict || {})[f];
		if (control) control.refresh();
	});
}


// ── Microns ──────────────────────────────────────────────────────────────────
// A tolling row records what was run: tick the product, tick each micron it was
// run at, and enter the grams that came off it. Untick anything and the figures
// below it are cleared, so a stale gram count can never outlive its tick.
const _MICRON_SIZES = ['150u', '120u_73u', '45u'];

function _micron_total(frm, cdt, cdn, prefix) {
	const row = locals[cdt][cdn];
	if (!row) return;
	const total = _MICRON_SIZES.reduce(
		(sum, s) => sum + (row[prefix + '_micron_' + s] ? flt(row[prefix + '_grams_' + s]) : 0), 0);
	frappe.model.set_value(cdt, cdn, prefix + '_total_grams', flt(total, 2));
	_repaint(frm, cdn, [prefix + '_total_grams']);
	_sync_yield(frm, cdt, cdn);
}

function _micron_toggled(frm, cdt, cdn, prefix, size) {
	const row = locals[cdt][cdn];
	if (!row) return;
	if (!row[prefix + '_micron_' + size] && flt(row[prefix + '_grams_' + size])) {
		frappe.model.set_value(cdt, cdn, prefix + '_grams_' + size, 0);
	}
	_micron_total(frm, cdt, cdn, prefix);
}

function _micron_product_toggled(frm, cdt, cdn, prefix) {
	const row = locals[cdt][cdn];
	if (!row) return;
	const on = prefix === 'bh' ? row.is_bubble_hash : row.is_rosin;
	if (!on) {
		_MICRON_SIZES.forEach((s) => {
			if (row[prefix + '_micron_' + s]) frappe.model.set_value(cdt, cdn, prefix + '_micron_' + s, 0);
			if (flt(row[prefix + '_grams_' + s])) frappe.model.set_value(cdt, cdn, prefix + '_grams_' + s, 0);
		});
	}
	_micron_total(frm, cdt, cdn, prefix);
}


// ── Gram equivalents ─────────────────────────────────────────────────────────
// The pullable stock is held in LBS but the tolling floor thinks in grams, so
// every Raw Material qty carries a read-only gram mirror. It is a display only:
// qty_rm_N stays in the item's own UOM because the Stock Entry line uses it
// verbatim, and writing grams there would issue 453x the stock.
const _ce_uom_of_item = {};
const _ce_grams_per_uom = {};

function _ce_item_uom(item_code) {
	if (_ce_uom_of_item[item_code] !== undefined) {
		return Promise.resolve(_ce_uom_of_item[item_code]);
	}
	return frappe.db.get_value('Item', item_code, 'stock_uom').then((r) => {
		const uom = (r.message || {}).stock_uom || '';
		_ce_uom_of_item[item_code] = uom;
		return uom;
	});
}

function _ce_grams_per_unit(uom) {
	if (!uom) return Promise.resolve(0);
	if (_ce_grams_per_uom[uom] !== undefined) return Promise.resolve(_ce_grams_per_uom[uom]);
	return frappe.call({
		method: 'cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry.grams_per_unit',
		args: { uom: uom },
	}).then((r) => {
		const v = flt(r.message);
		_ce_grams_per_uom[uom] = v;
		return v;
	});
}

function _sync_grams(frm, cdt, cdn, n) {
	const row = locals[cdt][cdn];
	if (!row) return;
	const target = 'qty_rm_' + n + '_g';
	const item = row['raw_material_' + n];
	const qty = flt(row['qty_rm_' + n]);
	// No item or no quantity means nothing to convert — and an item with no
	// gram conversion on file (Nos, for instance) leaves the mirror empty
	// rather than inventing a number.
	if (!item || !qty) {
		if (flt(row[target])) frappe.model.set_value(cdt, cdn, target, 0);
		_sync_yield(frm, cdt, cdn);
		return;
	}
	_ce_item_uom(item)
		.then(_ce_grams_per_unit)
		.then((factor) => frappe.model.set_value(cdt, cdn, target, flt(qty * factor, 2)))
		.then(() => {
			_repaint(frm, cdn, [target]);
			_sync_yield(frm, cdt, cdn);
		});
}


// ── Pull Items from Project ──────────────────────────────────────────────────
// Asks for a Warehouse and, optionally, a Project. With a Project it lists what
// was billed against that pair (Sales Invoice and Purchase Invoice lines both
// carry project + warehouse); with the Warehouse alone it lists what is in
// stock there. Whatever is ticked becomes Conversion Items rows — one row per
// item, its quantity carried across.
function _pull_project_items(frm) {
	const d = new frappe.ui.Dialog({
		title: __('Pull Items from Project'),
		size: 'large',
		fields: [
			{
				fieldname: 'warehouse', fieldtype: 'Link', options: 'Warehouse',
				label: __('Warehouse'), reqd: 1,
				get_query: () => ({ filters: { is_group: 0, disabled: 0 } }),
			},
			{
				fieldname: 'project', fieldtype: 'Link', options: 'Project',
				label: __('Project'),
				description: __('Optional. Leave blank to list what is in stock in the warehouse.'),
			},
			{ fieldname: 'fetch', fieldtype: 'Button', label: __('Show Items') },
			{ fieldname: 'results', fieldtype: 'HTML' },
		],
		primary_action_label: __('Add Selected'),
		primary_action() {
			// The row takes the quantity typed in Qty to Pull, not the listed one.
			const picked = d.$wrapper.find('.ce-pull-row:checked').map((i, el) => {
				const item = JSON.parse($(el).attr('data-row'));
				item.pull_qty = flt($(el).closest('tr').find('.ce-pull-qty').val());
				return item;
			}).get();
			if (!picked.length) {
				frappe.msgprint(__('Tick at least one item.'));
				return;
			}
			const no_qty = picked.filter((it) => it.pull_qty <= 0);
			if (no_qty.length) {
				frappe.msgprint(__('Enter a Qty to Pull for: {0}',
					[no_qty.map((it) => frappe.utils.escape_html(it.item_name)).join(', ')]));
				return;
			}
			// A new Conversion Entry opens with an untouched first row, so pulled
			// items would otherwise stack underneath an empty one that then fails
			// its own mandatory checks. Only rows with nothing in them go: a row
			// someone has started is never discarded.
			const is_blank = (r) => !r.raw_material_1 && !r.finished_good_1
				&& !flt(r.qty_rm_1) && !flt(r.qty_fg_1);
			const grid = frm.get_field('items').grid;
			(frm.doc.items || []).filter(is_blank).forEach((r) => {
				const grid_row = (grid.grid_rows_by_docname || {})[r.name];
				if (grid_row) {
					grid_row.remove();
				} else {
					// The grid has not rendered that row yet, so take it off the
					// document directly and let the refresh below redraw.
					frm.doc.items = frm.doc.items.filter((x) => x.name !== r.name);
					frappe.model.clear_doc(r.doctype, r.name);
				}
			});
			(frm.doc.items || []).forEach((r, i) => { r.idx = i + 1; });

			picked.forEach((item) => {
				const row = frm.add_child('items', {
					// One row per item: the puller picks the conversion type and
					// the finished good, which this cannot know.
					conversion_type: '1 to 1',
					source_warehouse: d.get_value('warehouse'),
					raw_material_1: item.item_code,
					qty_rm_1: item.pull_qty,
					// grams_per_unit comes from the server, so the row shows grams
					// the moment it lands instead of waiting on a round trip.
					qty_rm_1_g: flt(item.pull_qty * (item.grams_per_unit || 0), 2),
				});
				row.__ce_pulled = true;
			});
			(frm.doc.items || []).forEach((r) => {
				if (r.__ce_pulled) _sync_yield(frm, r.doctype, r.name);
			});
			frm.refresh_field('items');
			if (!frm.doc.project && d.get_value('project')) frm.set_value('project', d.get_value('project'));
			d.hide();
			frappe.show_alert({
				message: __('{0} item(s) added', [picked.length]), indicator: 'green',
			}, 5);
		},
	});

	const render = (items) => {
		const $area = d.fields_dict.results.$wrapper;
		if (!items.length) {
			$area.html(`<div style="color:var(--text-muted);padding:12px 0">${
				d.get_value('project')
					? __('Nothing was billed against that project out of that warehouse.')
					: __('Nothing is in stock in that warehouse.')}</div>`);
			return;
		}
		// With a Project the listed Qty is what was billed; without one it is the
		// stock itself, so the Billed column would only repeat In Warehouse.
		const billed = !!d.get_value('project');
		const td = 'padding:6px 8px';
		const muted = 'color:var(--text-muted);font-size:11px';
		const g_note = (qty, it) => (it.grams_per_unit && qty
			? `${format_number(qty * it.grams_per_unit, null, 2)} g` : '');
		const rows = items.map((it) => `
			<tr>
				<td style="${td}"><input type="checkbox" class="ce-pull-row"
					data-row='${frappe.utils.escape_html(JSON.stringify(it))}'></td>
				<td style="${td}"><b>${frappe.utils.escape_html(it.item_name)}</b>
					<div style="${muted}">${frappe.utils.escape_html(it.item_code)}</div></td>
				${billed ? `<td style="${td};text-align:right">${format_number(it.qty, null, 3)} ${frappe.utils.escape_html(it.uom || '')}
					<div style="${muted}">${g_note(it.qty, it)}</div></td>` : ''}
				<td style="${td};text-align:right">${format_number(it.stock_qty, null, 3)} ${frappe.utils.escape_html(it.uom || '')}
					<div style="${muted}">${g_note(it.stock_qty, it)}</div></td>
				<td style="${td};text-align:right;width:130px">
					<input type="number" min="0" step="any" class="form-control input-xs ce-pull-qty"
						style="text-align:right" placeholder="0">
					<div class="ce-pull-g" style="${muted}"></div></td>
				<td style="${td};${muted}">${frappe.utils.escape_html(it.sources)}</td>
			</tr>`).join('');
		const th = (label, right) => `<th style="${td};text-align:${right ? 'right' : 'left'};font-size:11px">${label}</th>`;
		$area.html(`
			<div style="max-height:380px;overflow:auto;border:1px solid var(--border-color);border-radius:6px">
			<table style="width:100%;border-collapse:collapse">
				<thead><tr style="position:sticky;top:0;background:var(--control-bg);z-index:1">
					<th style="${td}"><input type="checkbox" class="ce-pull-all"></th>
					${th(__('Item'))}
					${billed ? th(__('Billed'), true) : ''}
					${th(__('Qty in Warehouse'), true)}
					${th(__('Qty to Pull'), true)}
					${th(__('Source'))}
				</tr></thead>
				<tbody>${rows}</tbody>
			</table></div>`);
		$area.find('.ce-pull-all').on('change', function () {
			$area.find('.ce-pull-row').prop('checked', this.checked);
		});
		// Typing a quantity ticks the row; clearing it unticks. Pulling more
		// than the warehouse holds is flagged, not blocked.
		$area.find('.ce-pull-qty').on('input', function () {
			const $tr = $(this).closest('tr');
			const it = JSON.parse($tr.find('.ce-pull-row').attr('data-row'));
			const qty = flt(this.value);
			$tr.find('.ce-pull-row').prop('checked', qty > 0);
			$tr.find('.ce-pull-g').text(g_note(qty, it));
			$(this).css('border-color', qty > flt(it.stock_qty) ? 'var(--orange-500, #e8833a)' : '');
			$(this).attr('title', qty > flt(it.stock_qty) ? __('More than the warehouse holds') : '');
		});
	};

	const fetch = () => {
		if (!d.get_value('warehouse')) {
			frappe.msgprint(__('Pick a Warehouse first.'));
			return;
		}
		frappe.call({
			method: 'cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry.get_project_items',
			args: {
				// No company: a warehouse belongs to exactly one, so the server
				// reads it off the warehouse. Sending the form's company here is
				// what used to blank the list — a new Conversion Entry defaults to
				// Master Touch Manufacturing and hid every other company's invoices.
				project: d.get_value('project') || null,
				warehouse: d.get_value('warehouse'),
			},
			callback: (r) => render(r.message || []),
		});
	};

	d.fields_dict.fetch.$input.on('click', fetch);
	// Picking a value is usually enough — fetch without a second click.
	d.fields_dict.warehouse.$input.on('change', () => setTimeout(fetch, 200));
	d.fields_dict.project.$input.on('change', () => setTimeout(() => {
		if (d.get_value('warehouse')) fetch();
	}, 200));
	d.show();
}
