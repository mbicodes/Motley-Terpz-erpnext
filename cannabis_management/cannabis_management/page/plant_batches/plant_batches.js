// Cannabis Management > Plant Batches
// Single-page list + row actions matching the reference video's UX, built
// entirely on the EXISTING "Plant Batch" doctype (and its existing
// growth_phase_log / packaging_log / loss_log child tables, plus the
// existing "Growth Phase Change" / "Additive Application" compliance
// doctypes for the two actions that need METRC tag handling). No new
// doctypes or fields were created.

frappe.pages['plant-batches'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Plant Batches',
		single_column: true,
	});

	new CultivationPlantBatches(page);
};

class CultivationPlantBatches {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.filter_status = 'Active';
		this.setup_header();
		this.setup_table();
		this.load_batches();
	}

	// ---------------------------------------------------------------
	// HEADER: filter + Create Plant Batch button
	// ---------------------------------------------------------------
	setup_header() {
		this.page.set_primary_action('Create Plant Batch', () => this.open_create_dialog(), 'add');

		this.page.add_field({
			fieldname: 'status_filter',
			label: 'Filter',
			fieldtype: 'Select',
			options: 'All Plant Batches\nActive Plant Batches\nInactive Plant Batches',
			default: 'Active Plant Batches',
			change: () => {
				const val = this.page.fields_dict.status_filter.get_value();
				this.filter_status =
					val === 'Active Plant Batches' ? 'Active' :
					val === 'Inactive Plant Batches' ? 'Inactive' : null;
				this.load_batches();
			},
		});
	}

	// ---------------------------------------------------------------
	// LIST TABLE
	// ---------------------------------------------------------------
	setup_table() {
		this.wrapper.append(`
			<div class="cultivation-list-wrap" style="margin-top:10px;overflow-x:auto;">
				<table class="table table-bordered" style="background:#fff;margin-bottom:0;">
					<thead>
						<tr>
							<th style="width:40px;"></th>
							<th style="width:32px;"><input type="checkbox" class="pb-select-all"></th>
							<th>Name</th><th>Strain</th><th>Location</th><th>Room/Row</th>
							<th>Age (Days)</th><th># Plants</th><th># Tagged</th>
							<th># Destroyed</th><th># Packaged</th><th>Source</th>
							<th>Planted Date</th><th>Current Cost</th><th>Status</th>
						</tr>
					</thead>
					<tbody class="cultivation-tbody">
						<tr><td colspan="15" class="text-muted">Loading...</td></tr>
					</tbody>
				</table>
			</div>
		`);
		this.tbody = this.wrapper.find('.cultivation-tbody');
		this.wrapper.find('.pb-select-all').on('change', (e) => {
			this.tbody.find('.pb-row-select').prop('checked', e.target.checked);
		});
	}

	load_batches() {
		const filters = {};
		if (this.filter_status) filters.status = this.filter_status;

		frappe.call({
			method: 'cannabis_management.api.plant_batches.get_list',
			args: { filters },
			callback: (r) => this.render_rows(r.message || []),
		});
	}

	render_rows(rows) {
		this.tbody.empty();
		if (!rows.length) {
			this.tbody.append('<tr><td colspan="15" class="text-muted">No plant batches yet.</td></tr>');
			return;
		}
		rows.forEach((r) => {
			const source = r.source_plant || r.source_batch_no || '-';
			const tr = $(`
				<tr>
					<td><button class="btn btn-xs btn-default pb-actions">⋮</button></td>
					<td><input type="checkbox" class="pb-row-select"></td>
					<td><a href="#" class="pb-open">${frappe.utils.escape_html(r.batch_name || r.name)}</a></td>
					<td>${frappe.utils.escape_html(r.strain || '')}</td>
					<td>${frappe.utils.escape_html(r.location || '')}</td>
					<td>${frappe.utils.escape_html(r.room_row || '')}</td>
					<td>${r.age_days ?? ''}</td>
					<td>${r.plants_live ?? 0}</td>
					<td>${r.plants_promoted ?? 0}</td>
					<td>${r.plants_destroyed ?? 0}</td>
					<td>${r.plants_packaged ?? 0}</td>
					<td>${frappe.utils.escape_html(source)}</td>
					<td>${frappe.datetime.str_to_user(r.planting_date) || ''}</td>
					<td>${format_currency(r.total_input_cost || 0)}</td>
					<td>${frappe.utils.escape_html(r.status || '')}</td>
				</tr>
			`);
			tr.find('.pb-open').on('click', (e) => {
				e.preventDefault();
				frappe.set_route('Form', 'Plant Batch', r.name);
			});
			tr.find('.pb-actions').on('click', (e) => this.open_row_actions(e, r));
			this.tbody.append(tr);
		});
	}

	// ---------------------------------------------------------------
	// ROW ACTIONS MENU
	// ---------------------------------------------------------------
	open_row_actions(e, row) {
		e.preventDefault();
		e.stopPropagation();
		const batch_name = row.name;
		// Same order/items as the reference video's kebab menu. Every item is
		// backed by the existing Plant Batch fields/child-tables, or the
		// existing Growth Phase Change / Additive Application doctypes.
		// Adjust Quantity / Split Batch have no existing schema behind them
		// (no adjustment window, no split mechanism) so — exactly like the
		// video itself shows for an expired Adjust Quantity — they render
		// disabled with an explanatory note instead of faking a feature.
		const items = [
			{ label: 'Move Plant Batch', action: () => this.open_move_dialog(batch_name) },
			{ label: 'Change Growth Phase', action: () => this.open_growth_phase_dialog(batch_name) },
			{ label: 'Adjust Quantity', disabled: true, note: 'No quantity-adjustment window exists for this batch' },
			{ label: 'Add Cost', action: () => this.open_additive_dialog(batch_name, 'Add Cost') },
			{ label: 'Record Additive', action: () => this.open_additive_dialog(batch_name, 'Record Additive') },
			{ label: 'Split Batch', disabled: true, note: 'Splitting a batch is not supported by Plant Batch' },
			{ label: 'Package Plant Batch', action: () => this.open_package_dialog(batch_name) },
			{ label: 'Rename Plant Batch', action: () => this.open_rename_dialog(batch_name, row.batch_name) },
			{ label: 'Change Strain', action: () => this.open_change_strain_dialog(batch_name) },
			{ label: 'Destroy Plant Batch', action: () => this.confirm_destroy(batch_name) },
			{ label: 'Record Waste', action: () => this.open_waste_dialog(batch_name) },
		];

		const $menu = $('<div class="dropdown-menu" style="display:block;position:absolute;z-index:1050;max-height:340px;overflow-y:auto;"></div>');
		items.forEach((it) => {
			if (it.disabled) {
				$menu.append(`
					<div class="dropdown-item pb-disabled" style="padding:6px 14px;color:#a7b2ac;cursor:default;">
						${it.label}
						<div style="font-size:11px;color:#c0392b;line-height:1.3;">${it.note}</div>
					</div>
				`);
				return;
			}
			const $item = $(`<a class="dropdown-item" href="#" style="display:block;padding:6px 14px;">${it.label}</a>`);
			$item.on('click', (ev) => {
				ev.preventDefault();
				$menu.remove();
				it.action();
			});
			$menu.append($item);
		});

		$('body').append($menu);
		const offset = $(e.currentTarget).offset();
		const btn_width = $(e.currentTarget).outerWidth();
		const menu_width = $menu.outerWidth();
		const viewport_width = $(window).width();

		let left = offset.left; // open to the right of the ⋮ button by default
		if (left + menu_width > viewport_width - 10) {
			left = offset.left + btn_width - menu_width; // flip to the left if it would overflow
		}
		left = Math.max(10, left);

		$menu.css({ top: offset.top + 20, left });
		$(document).one('click', () => $menu.remove());
	}

	// ---------------------------------------------------------------
	// CREATE PLANT BATCH — mirrors the video's inline dialog
	// ---------------------------------------------------------------
	open_create_dialog() {
		const dialog = new frappe.ui.Dialog({
			title: 'Create Plant Batch',
			size: 'large',
			fields: [
				{
					fieldname: 'source_type', label: 'Source', fieldtype: 'Select',
					options: 'Mother Plant\nPackage',
					default: 'Mother Plant', reqd: 1,
					onchange: () => this.toggle_source_fields(dialog),
				},
				{ fieldname: 'col_1', fieldtype: 'Column Break' },
				{
					fieldname: 'source_plant', label: 'Mother Plant', fieldtype: 'Link',
					options: 'Plant',
					depends_on: 'eval:doc.source_type=="Mother Plant"',
					get_query: () => ({ filters: { is_mother: 1 } }),
					onchange: () => this.on_mother_plant_change(dialog),
				},
				{
					fieldname: 'source_batch_no', label: 'Source Package', fieldtype: 'Link',
					options: 'Metrc Package',
					depends_on: 'eval:doc.source_type=="Package"',
				},
				{ fieldname: 'sb_1', fieldtype: 'Section Break' },
				{
					fieldname: 'location', label: 'Output Location', fieldtype: 'Link',
					options: 'Warehouse', reqd: 1,
				},
				{ fieldname: 'col_2', fieldtype: 'Column Break' },
				{ fieldname: 'strain', label: 'Strain', fieldtype: 'Link', options: 'Strain', reqd: 1 },
				{ fieldname: 'col_3', fieldtype: 'Column Break' },
				{
					fieldname: 'batch_type', label: 'Plant Batch Type', fieldtype: 'Select',
					options: 'Clone\nSeed', reqd: 1,
				},
				{ fieldname: 'col_4', fieldtype: 'Column Break' },
				{
					fieldname: 'planting_date', label: 'Planting Date', fieldtype: 'Date',
					default: frappe.datetime.get_today(), reqd: 1,
				},
				{ fieldname: 'sb_2', fieldtype: 'Section Break', label: 'New Plant Batches' },
				{ fieldname: 'new_batches_html', fieldtype: 'HTML' },
			],
			primary_action_label: 'Create Plant Batch',
			primary_action: () => this.submit_create(dialog),
		});

		this.new_batch_rows = [{ batch_name: '', plant_count: '' }];
		this.render_new_batch_rows(dialog);
		dialog.show();
		this.toggle_source_fields(dialog);
	}

	toggle_source_fields(dialog) {
		const source = dialog.get_value('source_type');
		dialog.set_df_property('source_plant', 'hidden', source !== 'Mother Plant');
		dialog.set_df_property('source_batch_no', 'hidden', source !== 'Package');
		if (source === 'Mother Plant') {
			dialog.set_value('batch_type', 'Clone');
		}
	}

	on_mother_plant_change(dialog) {
		const val = dialog.get_value('source_plant');
		if (!val) return;
		frappe.db.get_value('Plant', val, ['strain', 'location']).then((r) => {
			if (r && r.message) {
				dialog.set_value('strain', r.message.strain);
				if (r.message.location) dialog.set_value('location', r.message.location);
			}
		});
	}

	render_new_batch_rows(dialog) {
		const wrap = dialog.fields_dict.new_batches_html.$wrapper;
		wrap.empty();
		wrap.append('<div class="pb-new-batches"></div>');
		const list = wrap.find('.pb-new-batches');

		this.new_batch_rows.forEach((row, idx) => {
			const line = $(`
				<div class="pb-new-batch-row" style="display:flex;gap:14px;align-items:flex-start;margin-bottom:10px;">
					<div style="flex-grow:1;">
						<label style="font-size:11px;text-transform:uppercase;color:#6b7d73;">Name</label>
						<input type="text" class="form-control pb-batch-name" value="${frappe.utils.escape_html(row.batch_name)}" placeholder="New Plant Batch">
						<div class="cultivation-field-error pb-name-error" style="display:none;">Plant batch name is required and must be unique</div>
					</div>
					<div style="width:120px;">
						<label style="font-size:11px;text-transform:uppercase;color:#6b7d73;"># Plants</label>
						<input type="number" min="0" class="form-control pb-plant-count" value="${frappe.utils.escape_html(row.plant_count)}" placeholder="0">
						<div class="cultivation-field-error pb-count-error" style="display:none;">Must be greater than zero</div>
					</div>
					<button class="btn btn-xs btn-default pb-remove-row" style="margin-top:22px;" ${this.new_batch_rows.length <= 1 ? 'disabled' : ''}>✕</button>
				</div>
			`);
			line.find('.pb-batch-name').on('input', (e) => { row.batch_name = e.target.value; });
			line.find('.pb-plant-count').on('input', (e) => { row.plant_count = e.target.value; });
			line.find('.pb-remove-row').on('click', () => {
				this.new_batch_rows.splice(idx, 1);
				this.render_new_batch_rows(dialog);
			});
			list.append(line);
		});

		wrap.append(`<button class="btn btn-sm btn-default pb-add-row" style="margin-top:4px;">+ Add New Plant Batches</button>`);
		wrap.find('.pb-add-row').on('click', () => {
			this.new_batch_rows.push({ batch_name: '', plant_count: '' });
			this.render_new_batch_rows(dialog);
		});
	}

	submit_create(dialog) {
		const values = dialog.get_values();
		if (!values) return;

		const seen = new Set();
		let has_error = false;
		this.new_batch_rows.forEach((row) => {
			const name_ok = row.batch_name && !seen.has(row.batch_name);
			const count_ok = row.plant_count && Number(row.plant_count) > 0;
			seen.add(row.batch_name);
			if (!name_ok || !count_ok) has_error = true;
		});
		if (!this.new_batch_rows.length || has_error) {
			frappe.msgprint('Every plant batch row needs a unique name and a plant count greater than zero.');
			return;
		}

		dialog.set_primary_action('Creating...', null);
		frappe.call({
			method: 'cannabis_management.api.plant_batches.create_plant_batches',
			args: {
				data: {
					source_type: values.source_type,
					source_plant: values.source_plant,
					source_batch_no: values.source_batch_no,
					location: values.location,
					strain: values.strain,
					batch_type: values.batch_type,
					planting_date: values.planting_date,
					new_batches: this.new_batch_rows,
				},
			},
			callback: (r) => {
				if (r.message && r.message.ok) {
					frappe.show_alert({ message: 'Plant batch(es) created', indicator: 'green' });
					dialog.hide();
					this.load_batches();
				}
			},
			error: () => {
				dialog.set_primary_action('Create Plant Batch', () => this.submit_create(dialog));
			},
		});
	}

	// ---------------------------------------------------------------
	// MOVE PLANT BATCH
	// ---------------------------------------------------------------
	open_move_dialog(batch_name) {
		const dialog = new frappe.ui.Dialog({
			title: `Move Plant Batch — ${batch_name}`,
			fields: [
				{ fieldname: 'location', label: 'Destination Location', fieldtype: 'Link', options: 'Warehouse', reqd: 1 },
				{ fieldname: 'col_1', fieldtype: 'Column Break' },
				{ fieldname: 'move_date', label: 'Move Date', fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
			],
			primary_action_label: 'Submit',
			primary_action: (values) => {
				frappe.call({
					method: 'cannabis_management.api.plant_batches.move_plant_batch',
					args: { plant_batch: batch_name, location: values.location, move_date: values.move_date },
					callback: () => {
						frappe.show_alert({ message: 'Plant batch moved', indicator: 'green' });
						dialog.hide();
						this.load_batches();
					},
				});
			},
		});
		dialog.show();
	}

	// ---------------------------------------------------------------
	// CHANGE GROWTH PHASE — existing "Growth Phase Change" doctype
	// (Promote Batch to Plants), created + submitted in-dialog, no page nav.
	// ---------------------------------------------------------------
	open_growth_phase_dialog(batch_name) {
		const dialog = new frappe.ui.Dialog({
			title: `Change Growth Phase — ${batch_name}`,
			fields: [
				{ fieldname: 'info', fieldtype: 'HTML', options: '<div class="alert alert-warning">This action will be queued for compliance submission</div>' },
				{
					fieldname: 'tag_allocation', label: 'Plant Tag Allocation', fieldtype: 'Link',
					options: 'METRC Tag Allocation', reqd: 1,
					get_query: () => ({ filters: { tag_type: 'Plant', status: 'Active' } }),
				},
				{ fieldname: 'qty_to_promote', label: '# Immatures Changing Phase', fieldtype: 'Int', reqd: 1 },
				{ fieldname: 'col_1', fieldtype: 'Column Break' },
				{ fieldname: 'output_location', label: 'Output Location', fieldtype: 'Link', options: 'Warehouse', reqd: 1 },
				{ fieldname: 'change_date', label: 'Change Date', fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
			],
			primary_action_label: 'Change Plants',
			primary_action: (values) => {
				dialog.set_primary_action('Submitting...', null);
				frappe.call({
					method: 'cannabis_management.api.plant_batches.promote_growth_phase',
					args: { plant_batch: batch_name, ...values },
					callback: () => {
						frappe.show_alert({ message: 'Growth phase change submitted for compliance', indicator: 'orange' });
						dialog.hide();
						this.load_batches();
					},
					error: () => dialog.get_primary_btn().prop('disabled', false).text('Change Plants'),
				});
			},
		});
		dialog.show();
	}

	// ---------------------------------------------------------------
	// ADD COST / RECORD ADDITIVE — existing "Additive Application" doctype,
	// created + submitted in-dialog, no page navigation.
	// ---------------------------------------------------------------
	open_additive_dialog(batch_name, title) {
		const dialog = new frappe.ui.Dialog({
			title: `${title} — ${batch_name}`,
			fields: [
				{ fieldname: 'additive_template', label: 'Additive Template', fieldtype: 'Link', options: 'Additive Template', reqd: 1 },
				{ fieldname: 'item', label: 'Item', fieldtype: 'Link', options: 'Item', reqd: 1 },
				{ fieldname: 'col_1', fieldtype: 'Column Break' },
				{ fieldname: 'qty_applied', label: 'Qty Applied', fieldtype: 'Float', reqd: 1 },
				{ fieldname: 'uom', label: 'UOM', fieldtype: 'Link', options: 'UOM', reqd: 1 },
				{ fieldname: 'sb_1', fieldtype: 'Section Break' },
				{ fieldname: 'source_warehouse', label: 'Source Warehouse', fieldtype: 'Link', options: 'Warehouse', reqd: 1 },
				{ fieldname: 'source_batch', label: 'Source Batch (optional)', fieldtype: 'Link', options: 'Batch' },
				{ fieldname: 'col_2', fieldtype: 'Column Break' },
				{ fieldname: 'rate', label: 'Rate', fieldtype: 'Data', reqd: 1 },
				{ fieldname: 'volume', label: 'Volume', fieldtype: 'Data', reqd: 1 },
				{ fieldname: 'additive_date', label: 'Date Applied', fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
			],
			primary_action_label: title,
			primary_action: (values) => {
				dialog.set_primary_action('Saving...', null);
				frappe.call({
					method: 'cannabis_management.api.plant_batches.record_additive',
					args: { plant_batch: batch_name, ...values },
					callback: () => {
						frappe.show_alert({ message: 'Additive application submitted', indicator: 'green' });
						dialog.hide();
						this.load_batches();
					},
					error: () => dialog.get_primary_btn().prop('disabled', false).text(title),
				});
			},
		});
		dialog.show();
	}

	// ---------------------------------------------------------------
	// PACKAGE PLANT BATCH
	// ---------------------------------------------------------------
	open_package_dialog(batch_name) {
		const dialog = new frappe.ui.Dialog({
			title: `Package Plant Batch — ${batch_name}`,
			fields: [
				{ fieldname: 'qty', label: '# Plants Packaged', fieldtype: 'Int', reqd: 1 },
				{ fieldname: 'package_date', label: 'Package Date', fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: 'metrc_package_tag', label: 'METRC Package Tag', fieldtype: 'Data' },
				{ fieldname: 'note', label: 'Note', fieldtype: 'Small Text' },
			],
			primary_action_label: 'Package',
			primary_action: (values) => {
				frappe.call({
					method: 'cannabis_management.api.plant_batches.package_plant_batch',
					args: { plant_batch: batch_name, ...values },
					callback: () => {
						frappe.show_alert({ message: 'Plant batch packaged', indicator: 'green' });
						dialog.hide();
						this.load_batches();
					},
				});
			},
		});
		dialog.show();
	}

	// ---------------------------------------------------------------
	// RENAME
	// ---------------------------------------------------------------
	open_rename_dialog(batch_name, current_name) {
		const dialog = new frappe.ui.Dialog({
			title: `Rename Plant Batch — ${batch_name}`,
			fields: [
				{ fieldname: 'batch_name', label: 'New Name', fieldtype: 'Data', reqd: 1, default: current_name },
			],
			primary_action_label: 'Rename',
			primary_action: (values) => {
				frappe.call({
					method: 'cannabis_management.api.plant_batches.rename_plant_batch',
					args: { plant_batch: batch_name, batch_name: values.batch_name },
					callback: () => {
						frappe.show_alert({ message: 'Renamed', indicator: 'green' });
						dialog.hide();
						this.load_batches();
					},
				});
			},
		});
		dialog.show();
	}

	// ---------------------------------------------------------------
	// CHANGE STRAIN
	// ---------------------------------------------------------------
	open_change_strain_dialog(batch_name) {
		const dialog = new frappe.ui.Dialog({
			title: `Change Strain — ${batch_name}`,
			fields: [
				{ fieldname: 'strain', label: 'New Strain', fieldtype: 'Link', options: 'Strain', reqd: 1 },
			],
			primary_action_label: 'Update',
			primary_action: (values) => {
				frappe.call({
					method: 'cannabis_management.api.plant_batches.change_strain',
					args: { plant_batch: batch_name, strain: values.strain },
					callback: () => {
						frappe.show_alert({ message: 'Strain updated', indicator: 'green' });
						dialog.hide();
						this.load_batches();
					},
				});
			},
		});
		dialog.show();
	}

	// ---------------------------------------------------------------
	// RECORD WASTE
	// ---------------------------------------------------------------
	open_waste_dialog(batch_name) {
		const dialog = new frappe.ui.Dialog({
			title: `Record Waste — ${batch_name}`,
			fields: [
				{ fieldname: 'qty_lost', label: 'Qty Lost', fieldtype: 'Int', reqd: 1 },
				{
					fieldname: 'reason', label: 'Reason', fieldtype: 'Select',
					options: 'Pest\nDisease\nMale Plant\nEnvironmental\nOther', reqd: 1,
				},
				{ fieldname: 'loss_date', label: 'Date', fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: 'logged_by', label: 'Logged By', fieldtype: 'Link', options: 'Employee' },
			],
			primary_action_label: 'Record Waste',
			primary_action: (values) => {
				frappe.call({
					method: 'cannabis_management.api.plant_batches.record_waste',
					args: { plant_batch: batch_name, ...values },
					callback: () => {
						frappe.show_alert({ message: 'Waste recorded', indicator: 'orange' });
						dialog.hide();
						this.load_batches();
					},
				});
			},
		});
		dialog.show();
	}

	// ---------------------------------------------------------------
	// DESTROY
	// ---------------------------------------------------------------
	confirm_destroy(batch_name) {
		frappe.confirm(
			`Are you sure you want to destroy all remaining live plants in <b>${batch_name}</b>?`,
			() => {
				frappe.call({
					method: 'cannabis_management.api.plant_batches.destroy_plant_batch',
					args: { plant_batch: batch_name },
					callback: () => {
						frappe.show_alert({ message: 'Plant batch destroyed', indicator: 'red' });
						this.load_batches();
					},
				});
			}
		);
	}
}
