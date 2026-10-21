// Config for the extra Cultivation views (Plants / Teardowns / Harvests) shown
// inside the Plant Batches page. Existing doctypes / fields only.
window.CultivationConfigs = {};

CultivationConfigs['Plants'] = function () {
		const L = CultivationList;
		const phase_color = { Flowering: 'green', Vegetative: 'yellow' };
		const status_color = { Active: 'green', Harvested: 'grey', Destroyed: 'red' };
		const set = (name, values, done) => frappe.call({
			method: 'frappe.client.set_value',
			args: { doctype: 'Plant', name, fieldname: values },
			callback: done,
		});
		return {
			primary: { label: 'Create Plant', handler: (l) => {
				const d = new frappe.ui.Dialog({
					title: 'Create Plants (promote a Plant Batch)',
					fields: [
						{ fieldname: 'plant_batch', label: 'Plant Batch', fieldtype: 'Link', options: 'Plant Batch', reqd: 1,
							get_query: () => ({ filters: { status: 'Active' } }) },
						{ fieldname: 'qty', label: 'Number of Plants', fieldtype: 'Int', reqd: 1 },
						{ fieldname: 'output_location', label: 'Location', fieldtype: 'Link', options: 'Warehouse', reqd: 1 },
						{ fieldname: 'starting_tag', label: 'Starting Plant Tag', fieldtype: 'Link', options: 'Metrc Tag', reqd: 1,
							get_query: () => ({ filters: { tag_category: 'Plant', status: 'Available' } }) },
						{ fieldname: 'change_date', label: 'Date', fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
					],
					primary_action_label: 'Create',
					primary_action: (v) => {
						d.disable_primary_action();
						frappe.call({
							method: 'cannabis_management.api.plant_batches.change_growth_phase', args: v,
							callback: (r) => {
								if (!r || !r.message) { d.enable_primary_action(); return; }
								d.hide();
								frappe.show_alert({ message: `${r.message.plants_created} plants created`, indicator: 'green' });
								l.load();
							},
							error: () => d.enable_primary_action(),
						});
					},
				});
				d.show();
			} },
			title: 'Plants', noun: 'plants', doctype: 'Plant', search_field: 'plant_tag',
			search_label: 'Search by plant tag', order_by: 'plant_tag asc',
			views: [
				{ label: 'All Plants', filters: {} },
				{ label: 'Active Plants', filters: { status: 'Active' } },
				{ label: 'Flowering', filters: { growth_phase: 'Flowering', status: 'Active' } },
				{ label: 'Vegetative', filters: { growth_phase: 'Vegetative', status: 'Active' } },
				{ label: 'Harvested', filters: { status: 'Harvested' } },
				{ label: 'Destroyed', filters: { status: 'Destroyed' } },
			],
			fields: ['name', 'plant_tag', 'flowering_date', 'strain', 'location', 'growth_phase', 'status',
				'source_plant_batch', 'accumulated_cost', 'days_in_flower', 'total_age_days'],
			columns: [
				{ label: 'Plant Tag', render: (r) => L.link(r.plant_tag || r.name, 'Form', 'Plant', r.name) },
				{ label: 'Flowering Date', render: (r) => r.flowering_date ? frappe.datetime.str_to_user(r.flowering_date) : '' },
				{ label: 'Strain', render: (r) => L.link(r.strain, 'Form', 'Strain', r.strain) },
				{ label: 'Location', field: 'location' },
				{ label: 'Growth Phase', field: 'growth_phase' },
				{ label: 'Status', render: (r) => r.status === 'Active' && r.growth_phase === 'Flowering'
					? L.badge('Flowering', 'green') : L.badge(r.status, status_color[r.status]) },
				{ label: 'Source Batch', render: (r) => L.link(r.source_plant_batch, 'Form', 'Plant Batch', r.source_plant_batch) },
				{ label: 'Current Cost', align: 'right', render: (r) => L.money(r.accumulated_cost) },
				{ label: 'Days in Flower', align: 'right', field: 'days_in_flower' },
				{ label: 'Total Age (Days)', align: 'right', field: 'total_age_days' },
			],
			actions: [
				{ label: 'Move Plant', handler: (r, l) => frappe.prompt(
					{ fieldname: 'location', label: 'New Location', fieldtype: 'Link', options: 'Warehouse', reqd: 1, default: r.location },
					(v) => set(r.name, { location: v.location }, () => l.load()), 'Move Plant') },
				{ label: 'Add Cost', handler: (r) => frappe.msgprint(__('Plant cost entries are not available in this system yet.')) },
				{ label: 'Change Growth Phase', handler: (r, l) => frappe.prompt(
					{ fieldname: 'growth_phase', label: 'Growth Phase', fieldtype: 'Select', options: 'Vegetative\nFlowering', reqd: 1, default: r.growth_phase },
					(v) => set(r.name, { growth_phase: v.growth_phase }, () => l.load()), 'Change Growth Phase') },
				{ label: 'Create Plant Batch', handler: (r) => frappe.new_doc('Plant Batch', {
					source_type: 'Mother Plant', source_plant: r.name, strain: r.strain, location: r.location }) },
				{ label: 'Record Additive', handler: (r) => frappe.new_doc('Additive Application', {
					applied_to_type: 'Plant',
					targets: [{ target_doctype: 'Plant', target_name: r.name, target_title: r.plant_tag }] }) },
				{ label: 'Record Waste', handler: () => frappe.msgprint(__('Plant waste logs are not available in this system yet.')) },
				{ label: 'Destroy Plant', handler: (r, l) => frappe.confirm(
					__('Destroy plant {0}? This cannot be undone.', [r.plant_tag || r.name]),
					() => set(r.name, { status: 'Destroyed' }, () => l.load())) },
			],
		};
};

CultivationConfigs['Teardowns'] = function () {
		const L = CultivationList;
		return {
			title: 'Teardowns', noun: 'teardowns', doctype: 'Teardown', search_field: 'teardown_name',
			search_label: 'Search by teardown name',
			primary: { label: 'Create Teardown', handler: (l) => {
				const d = new frappe.ui.Dialog({
					title: 'Create Teardown',
					fields: [
						{ fieldname: 'teardown_type', label: 'Teardown Type', fieldtype: 'Select', options: 'Regular\nManicure', default: 'Regular', reqd: 1 },
						{ fieldname: 'weight_unit', label: 'Weight Unit', fieldtype: 'Select', options: 'g\nlb', default: 'g' },
						{ fieldname: 'dry_room', label: 'Dry Room', fieldtype: 'Link', options: 'Warehouse' },
						{ fieldname: 'plants', label: 'Plants', fieldtype: 'Table', reqd: 1, in_place_edit: true, data: [],
							fields: [
								{ fieldname: 'plant', label: 'Plant', fieldtype: 'Link', options: 'Plant', in_list_view: 1, reqd: 1,
									get_query: () => ({ filters: { status: 'Active', growth_phase: 'Flowering' } }) },
								{ fieldname: 'weight', label: 'Weight', fieldtype: 'Float', in_list_view: 1, reqd: 1 },
							] },
					],
					primary_action_label: 'Create',
					primary_action: (v) => {
						const stamp = frappe.datetime.now_datetime().slice(0, 16);
						frappe.call({
							method: 'frappe.client.insert',
							args: { doc: {
								doctype: 'Teardown', teardown_name: `Teardown ${stamp}`,
								teardown_type: v.teardown_type, weight_unit: v.weight_unit, dry_room: v.dry_room,
								teardown_tags: (v.plants || []).map((r) => ({ plant: r.plant, weight: r.weight, weight_source: 'Scale' })),
							} },
							callback: () => { d.hide(); frappe.show_alert({ message: 'Teardown created', indicator: 'green' }); l.load(); },
						});
					},
				});
				d.show();
			} },
			views: [
				{ label: 'All Teardowns', filters: {} },
				{ label: 'Preparing', filters: { status: 'Preparing' } },
				{ label: 'Completed', filters: { status: 'Completed' } },
			],
			fields: ['name', 'teardown_name', 'status', 'weight_unit', 'docstatus'],
			enrich: (rows) => !rows.length ? Promise.resolve() : frappe.xcall(
				'cannabis_management.api.cultivation_lists.teardown_stats', { names: rows.map((r) => r.name) })
				.then((s) => rows.forEach((r) => Object.assign(r, s[r.name] || {}))),
			columns: [
				{ label: 'Teardown Name', render: (r) => L.link(r.teardown_name || r.name, 'Form', 'Teardown', r.name) },
				{ label: 'Status', render: (r) => L.badge(r.status, r.status === 'Completed' ? 'green' : 'yellow') },
				{ label: 'Harvests', render: (r) => `${r.reviewed || 0} <span class="text-muted">/ ${r.harvests || 0} reviewed</span>` },
				{ label: 'Plants', render: (r) => r.plants || 0 },
				{ label: 'Weight Recorded', render: (r) => `${format_number(r.weight || 0, null, 2)} ${r.weight_unit || 'g'}` },
			],
			actions: [
				{ label: 'Open Teardown', handler: (r) => frappe.set_route('Form', 'Teardown', r.name) },
			],
		};
};

CultivationConfigs['Harvests'] = function () {
		const L = CultivationList;
		const status_label = { 'Partially Packaged': 'Packaging' };
		const status_color = { Finished: 'green', 'Partially Packaged': 'orange', Dried: 'yellow', Drying: 'yellow' };
		const wt = (v, u) => v ? `${format_number(v, null, 0)} ${u || 'g'}` : '';
		return {
			primary: { label: 'Create Harvest', handler: (l) => {
				const d = new frappe.ui.Dialog({
					title: 'Create Harvest',
					fields: [
						{ fieldname: 'harvest_batch_name', label: 'Harvest Name', fieldtype: 'Data', reqd: 1 },
						{ fieldname: 'teardown', label: 'Teardown', fieldtype: 'Link', options: 'Teardown', reqd: 1 },
						{ fieldname: 'strain', label: 'Strain', fieldtype: 'Link', options: 'Strain', reqd: 1 },
						{ fieldname: 'harvest_date', label: 'Harvested On', fieldtype: 'Date', default: frappe.datetime.get_today(), reqd: 1 },
						{ fieldname: 'col', fieldtype: 'Column Break' },
						{ fieldname: 'dry_room', label: 'Location', fieldtype: 'Link', options: 'Warehouse' },
						{ fieldname: 'weight_uom', label: 'Weight UOM', fieldtype: 'Link', options: 'UOM' },
						{ fieldname: 'wet_weight', label: 'Wet Weight', fieldtype: 'Float' },
						{ fieldname: 'plant_count', label: 'Plants', fieldtype: 'Int' },
					],
					primary_action_label: 'Create',
					primary_action: (v) => frappe.call({
						method: 'frappe.client.insert', args: { doc: Object.assign({ doctype: 'Harvest Batch' }, v) },
						callback: () => { d.hide(); frappe.show_alert({ message: 'Harvest created', indicator: 'green' }); l.load(); },
					}),
				});
				d.show();
			} },
			title: 'Harvests', noun: 'harvests', doctype: 'Harvest Batch', search_field: 'harvest_batch_name',
			search_label: 'Search by harvest name', order_by: 'harvest_date desc',
			views: [
				{ label: 'All Harvests', filters: {} },
				{ label: 'Drying', filters: { status: 'Drying' } },
				{ label: 'Dried', filters: { status: 'Dried' } },
				{ label: 'Packaging', filters: { status: 'Partially Packaged' } },
				{ label: 'Finished', filters: { status: 'Finished' } },
			],
			fields: ['name', 'harvest_batch_name', 'teardown', 'status', 'wet_weight', 'dry_weight', 'packaged_weight',
				'waste_weight', 'weight_uom', 'strain', 'metrc_harvest_id', 'harvest_date', 'dry_room'],
			columns: [
				{ label: 'Name', render: (r) => L.link(r.harvest_batch_name || r.name, 'Form', 'Harvest Batch', r.name) },
				{ label: 'Teardown', render: (r) => L.link(r.teardown, 'Form', 'Teardown', r.teardown) },
				{ label: 'Status', render: (r) => L.badge(status_label[r.status] || r.status, status_color[r.status]) },
				{ label: 'Weight (Wet)', align: 'right', render: (r) => wt(r.wet_weight, r.weight_uom) },
				{ label: 'Packaged', align: 'right', render: (r) => wt(r.packaged_weight, r.weight_uom) },
				{ label: 'Waste', align: 'right', render: (r) => wt(r.waste_weight, r.weight_uom) },
				{ label: 'Strain', render: (r) => L.link(r.strain, 'Form', 'Strain', r.strain) },
				{ label: 'Metrc Harvest ID', field: 'metrc_harvest_id' },
				{ label: 'Harvested On', render: (r) => r.harvest_date ? frappe.datetime.str_to_user(r.harvest_date) : '' },
				{ label: 'Location', field: 'dry_room' },
			],
			actions: [{ label: 'Create Package', handler: (r, l) => open_package_panel(r, l) }],
		};
};

function open_package_panel(hb, list) {
	const unit = hb.weight_uom || 'g';
	const total = (hb.dry_weight || hb.wet_weight || 0);
	const remaining = () => total - (hb.packaged_weight || 0) - (hb.waste_weight || 0);
	const pkgs = [];

	const $ov = $(`
		<div class="cl-overlay" style="position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:1050;">
			<div class="cl-panel" style="position:absolute;top:0;right:0;bottom:0;width:560px;max-width:100%;background:#fff;display:flex;flex-direction:column;box-shadow:-4px 0 16px rgba(0,0,0,.2);">
				<div style="padding:14px 18px;font-weight:600;border-bottom:1px solid #e4e9e6;">&rarr; Create Package from Harvest Batch</div>
				<div class="cl-body" style="flex:1;overflow:auto;padding:14px 18px;">
					<h6 class="text-muted">PACKAGING INFO</h6>
					<div class="cl-info"></div>
					<div style="display:flex;align-items:center;justify-content:space-between;margin-top:14px;">
						<h6 class="text-muted" style="margin:0;">CREATE PACKAGES</h6>
						<button class="btn btn-xs btn-primary cl-add">ADD PACKAGE TYPE</button>
					</div>
					<div class="cl-summary" style="margin:10px 0;padding:10px 14px;background:#f4f6f5;border-radius:6px;display:flex;justify-content:space-between;">
						<span><b>Harvest Batch</b><br>${L_esc(hb.harvest_batch_name || hb.name)}</span>
						<span class="cl-sum" style="text-align:right;"></span>
					</div>
					<div class="cl-rows"></div>
				</div>
				<div style="padding:12px 18px;border-top:1px solid #e4e9e6;display:flex;gap:8px;justify-content:flex-end;">
					<button class="btn btn-default cl-cancel" style="margin-right:auto;">CANCEL</button>
					<button class="btn btn-default cl-sync" disabled>CREATE &amp; SYNC TO METRC</button>
					<button class="btn btn-primary cl-create" disabled>CREATE</button>
				</div>
			</div>
		</div>`).appendTo('body');

	function L_esc(v) { return frappe.utils.escape_html(v || ''); }

	const info = new frappe.ui.FieldGroup({
		body: $ov.find('.cl-info')[0],
		fields: [
			{ fieldname: 'owner', label: 'Owner', fieldtype: 'Link', options: 'User', default: frappe.session.user },
			{ fieldname: 'destination', label: 'Destination Location', fieldtype: 'Link', options: 'Warehouse', default: hb.dry_room },
			{ fieldname: 'description', label: 'Description', fieldtype: 'Small Text' },
		],
	});
	info.make();

	function refresh() {
		const used = pkgs.reduce((a, p) => a + (flt(p.quantity) || 0), 0);
		$ov.find('.cl-sum').html(`<b>${format_number(hb.packaged_weight || 0, null, 0)} ${unit} Packaged</b><br>
			<span style="color:#c0392b;">${format_number(remaining() - used, null, 0)} ${unit} Total Weight</span>`);
		$ov.find('.cl-create,.cl-sync').prop('disabled', !pkgs.length);
		const $r = $ov.find('.cl-rows').empty();
		if (!pkgs.length) {
			$r.append('<div class="text-muted text-center" style="padding:24px;">Create Packages<br>You can create multiple packages and package types from this harvest</div>');
		}
		pkgs.forEach((p, i) => {
			const $row = $(`<div class="cl-pkg" style="border:1px solid #e4e9e6;border-radius:6px;padding:10px;margin-bottom:8px;"><div class="fields"></div>
				<button class="btn btn-xs btn-link text-danger">Remove</button></div>`);
			const g = new frappe.ui.FieldGroup({ body: $row.find('.fields')[0], fields: [
				{ fieldname: 'tag', label: 'Package Tag', fieldtype: 'Link', options: 'Metrc Tag', default: p.tag,
					change() { p.tag = g.get_value('tag'); } },
				{ fieldname: 'item_code', label: 'Item', fieldtype: 'Link', options: 'Item', default: p.item_code,
					change() { p.item_code = g.get_value('item_code'); } },
				{ fieldname: 'quantity', label: `Quantity (${unit})`, fieldtype: 'Float', default: p.quantity,
					change() { p.quantity = g.get_value('quantity'); refresh_sum(); } },
			] });
			g.make();
			$row.find('button').on('click', () => { pkgs.splice(i, 1); refresh(); });
			$r.append($row);
		});
	}
	function refresh_sum() {
		const used = pkgs.reduce((a, p) => a + (flt(p.quantity) || 0), 0);
		$ov.find('.cl-sum').html(`<b>${format_number((hb.packaged_weight || 0), null, 0)} ${unit} Packaged</b><br>
			<span style="color:#c0392b;">${format_number(remaining() - used, null, 0)} ${unit} Total Weight</span>`);
	}

	const close = () => $ov.remove();
	$ov.on('click', (e) => { if (e.target === $ov[0]) close(); });
	$ov.find('.cl-cancel').on('click', close);
	$ov.find('.cl-add').on('click', () => { pkgs.push({ uom: hb.weight_uom }); refresh(); });

	const submit = (sync) => frappe.call({
		method: 'cannabis_management.api.cultivation_lists.create_packages_from_harvest',
		args: {
			harvest_batch: hb.name, packages: pkgs,
			owner: info.get_value('owner'), destination: info.get_value('destination'),
			description: info.get_value('description'),
		},
		freeze: true,
		callback: (r) => {
			close();
			frappe.show_alert({ message: __('{0} package(s) created', [(r.message || []).length]), indicator: 'green' });
			if (sync) frappe.msgprint(__('Packages created. Sending them to Metrc is not wired to this panel yet.'));
			list.load();
		},
	});
	$ov.find('.cl-create').on('click', () => submit(false));
	$ov.find('.cl-sync').on('click', () => submit(true));
	refresh();
}
