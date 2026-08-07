frappe.pages['manufacturing-process'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Manufacturing Process',
		single_column: true,
	});

	$(wrapper).find('.layout-main-section').html(getMpHTML());
	var root = wrapper.querySelector('.mp-dash');

	var API = 'cannabis_management.api.manufacturing_process.';
	var woControl;
	var currentWorkOrder = null;

	// ── Work Order picker (searchable Link, outside a form) ─────────────────
	woControl = frappe.ui.form.make_control({
		parent: root.querySelector('#mp-wo-filter'),
		df: { fieldtype: 'Link', options: 'Work Order', fieldname: 'work_order', placeholder: __('Search a Work Order…') },
		render_input: true,
	});
	woControl.refresh();
	woControl.$input.on('change awesomplete-selectcomplete', function () {
		loadTrail(woControl.get_value());
	});

	root.querySelector('#mp-refresh-btn').addEventListener('click', function () {
		loadTrail(currentWorkOrder);
	});

	root.querySelector('#mp-new-wo-btn').addEventListener('click', function () {
		frappe.new_doc('Work Order');
	});

	root.querySelector('#mp-add-jc-btn').addEventListener('click', function () {
		if (!currentWorkOrder) return;
		frappe.new_doc('Job Card', { work_order: currentWorkOrder });
	});

	root.querySelector('#mp-add-transfer-btn').addEventListener('click', function () {
		createStockEntry('Material Transfer for Manufacture');
	});
	root.querySelector('#mp-add-manufacture-btn').addEventListener('click', function () {
		createStockEntry('Manufacture');
	});

	loadRecent();
	selectFromRoute();

	// ── If the page was opened as /app/manufacturing-process/WO-0001 ────────
	function selectFromRoute() {
		var route = frappe.get_route();
		var wo = route && route.length > 1 ? route[1] : null;
		if (wo) {
			woControl.set_value(wo);
			loadTrail(wo);
		}
	}

	function loadRecent() {
		frappe.call({
			method: API + 'get_work_order_options',
			callback: function (r) {
				var rows = r.message || [];
				var $wrap = root.querySelector('#mp-recent-chips');
				if (!rows.length) {
					$wrap.innerHTML = '<span class="mp-empty-inline">No Work Orders yet — create one to get started.</span>';
					return;
				}
				$wrap.innerHTML = rows.slice(0, 8).map(function (wo) {
					return `<span class="mp-chip" data-wo="${frappe.utils.escape_html(wo.name)}">
						${frappe.utils.escape_html(wo.name)} · ${frappe.utils.escape_html(wo.item_name || wo.production_item)}
					</span>`;
				}).join('');
				$wrap.querySelectorAll('.mp-chip').forEach(function (chip) {
					chip.addEventListener('click', function () {
						var wo = this.getAttribute('data-wo');
						woControl.set_value(wo);
						loadTrail(wo);
					});
				});
			},
		});
	}

	function createStockEntry(purpose) {
		if (!currentWorkOrder) return;
		frappe.xcall('erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry', {
			work_order_id: currentWorkOrder,
			purpose: purpose,
		}).then(function (stock_entry) {
			if (!stock_entry) return;
			frappe.model.sync(stock_entry);
			frappe.set_route('Form', stock_entry.doctype, stock_entry.name);
		});
	}

	function loadTrail(wo) {
		currentWorkOrder = wo || null;
		frappe.route_options = null;
		if (!currentWorkOrder) {
			showEmpty();
			return;
		}
		root.querySelector('#mp-content').style.opacity = '0.5';
		frappe.call({
			method: API + 'get_trail',
			args: { work_order: currentWorkOrder },
			callback: function (r) {
				root.querySelector('#mp-content').style.opacity = '1';
				var data = r.message;
				if (!data || !data.work_order) {
					showEmpty();
					return;
				}
				showContent();
				render(data);
			},
		});
	}

	function showEmpty() {
		root.querySelector('#mp-empty').style.display = '';
		root.querySelector('#mp-content').style.display = 'none';
	}
	function showContent() {
		root.querySelector('#mp-empty').style.display = 'none';
		root.querySelector('#mp-content').style.display = '';
	}

	// ── Formatters ────────────────────────────────────────────────────────
	function fmtNum(v) { return parseFloat(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 }); }
	function fmtDate(v) { return v ? frappe.datetime.str_to_user(v, true) : '—'; }
	function esc(v) { return frappe.utils.escape_html(v == null ? '' : String(v)); }
	function docLink(doctype, name, label) {
		if (!name) return '—';
		return `<a href="${frappe.utils.get_form_link(doctype, name)}" class="mp-link">${esc(label || name)}</a>`;
	}
	function pct(num, den) {
		den = flt(den);
		if (!den) return 0;
		return Math.max(0, Math.min(100, (flt(num) / den) * 100));
	}
	function flt(v) { return parseFloat(v || 0); }

	var WO_STATUS_CLASS = {
		Draft: 'grey', Submitted: 'blue', 'Not Started': 'amber', 'In Process': 'cyan',
		Completed: 'emerald', Stopped: 'rose', Closed: 'grey', Cancelled: 'rose',
	};
	var JC_STATUS_CLASS = {
		Open: 'grey', 'Work In Progress': 'cyan', 'Partially Transferred': 'amber',
		'Material Transferred': 'amber', 'On Hold': 'rose', Submitted: 'blue',
		Cancelled: 'rose', Completed: 'emerald',
	};
	function badge(text, cls) {
		return `<span class="mp-badge mp-badge-${cls || 'grey'}">${esc(text || '—')}</span>`;
	}
	function docstatusBadge(ds) {
		if (ds === 1) return badge('Submitted', 'emerald');
		if (ds === 2) return badge('Cancelled', 'rose');
		return badge('Draft', 'grey');
	}

	// ── Render ────────────────────────────────────────────────────────────
	function render(data) {
		var wo = data.work_order;
		renderStepper(data);
		renderWoCard(wo);
		renderMaterials(data.required_items, data.bom);
		renderSourceDocs(wo);
		renderJobCards(data.job_cards);
		renderStockEntries(data.stock_entries);
	}

	function renderStepper(data) {
		var wo = data.work_order;
		var jcs = data.job_cards || [];
		var jcAllDone = jcs.length > 0 && jcs.every(function (j) { return j.status === 'Completed' || j.docstatus === 2; });

		var steps = [
			{ label: 'BOM Selected', done: !!wo.bom_no, active: false },
			{ label: 'Work Order Submitted', done: wo.docstatus === 1 || wo.docstatus === 2, active: wo.docstatus === 0 },
			{ label: 'Material Transferred', done: flt(wo.material_transferred_for_manufacturing) >= flt(wo.qty) && flt(wo.qty) > 0, active: flt(wo.material_transferred_for_manufacturing) > 0 },
			{ label: 'Job Card Operations', done: jcAllDone, active: jcs.length > 0 && !jcAllDone },
			{ label: 'Manufactured', done: flt(wo.produced_qty) >= flt(wo.qty) && flt(wo.qty) > 0, active: flt(wo.produced_qty) > 0 },
		];

		root.querySelector('#mp-stepper').innerHTML = steps.map(function (s, i) {
			var cls = s.done ? 'done' : (s.active ? 'active' : 'pending');
			return `
				<div class="mp-step mp-step-${cls}">
					<div class="mp-step-dot">${s.done ? '✓' : (i + 1)}</div>
					<div class="mp-step-label">${esc(s.label)}</div>
				</div>
				${i < steps.length - 1 ? '<div class="mp-step-line mp-step-line-' + cls + '"></div>' : ''}
			`;
		}).join('');
	}

	function renderWoCard(wo) {
		var statusCls = WO_STATUS_CLASS[wo.status] || 'grey';
		root.querySelector('#mp-wo-card').innerHTML = `
			<div class="mp-wo-top">
				<div class="mp-wo-item">
					${wo.image ? `<img src="${esc(wo.image)}" class="mp-wo-img">` : `<div class="mp-wo-img mp-wo-img-ph">🏭</div>`}
					<div>
						<div class="mp-wo-name">${docLink('Work Order', wo.name)}</div>
						<div class="mp-wo-itemname">${esc(wo.item_name || wo.production_item)} <span class="mp-muted">(${esc(wo.production_item)})</span></div>
					</div>
				</div>
				<div class="mp-wo-status">${badge(wo.status, statusCls)}${docstatusBadge(wo.docstatus)}</div>
			</div>
			<div class="mp-wo-stats">
				<div class="mp-stat"><div class="mp-stat-v">${fmtNum(wo.qty)} <span class="mp-stat-u">${esc(wo.stock_uom || '')}</span></div><div class="mp-stat-l">Planned Qty</div></div>
				<div class="mp-stat"><div class="mp-stat-v">${fmtNum(wo.material_transferred_for_manufacturing)}</div><div class="mp-stat-l">Transferred</div></div>
				<div class="mp-stat"><div class="mp-stat-v">${fmtNum(wo.produced_qty)}</div><div class="mp-stat-l">Produced</div></div>
				<div class="mp-stat"><div class="mp-stat-v">${fmtNum(wo.process_loss_qty)}</div><div class="mp-stat-l">Process Loss</div></div>
			</div>
			<div class="mp-wo-grid">
				<div><span class="mp-glbl">Company</span>${esc(wo.company) || '—'}</div>
				<div><span class="mp-glbl">Planned Start</span>${fmtDate(wo.planned_start_date)}</div>
				<div><span class="mp-glbl">Planned End</span>${fmtDate(wo.planned_end_date)}</div>
				<div><span class="mp-glbl">Actual Start</span>${fmtDate(wo.actual_start_date)}</div>
				<div><span class="mp-glbl">Actual End</span>${fmtDate(wo.actual_end_date)}</div>
				<div><span class="mp-glbl">Source Warehouse</span>${docLink('Warehouse', wo.source_warehouse)}</div>
				<div><span class="mp-glbl">WIP Warehouse</span>${docLink('Warehouse', wo.wip_warehouse)}</div>
				<div><span class="mp-glbl">FG Warehouse</span>${docLink('Warehouse', wo.fg_warehouse)}</div>
			</div>
		`;
	}

	function renderMaterials(items, bom) {
		root.querySelector('#mp-bom-tag').innerHTML = bom
			? `from BOM ${docLink('BOM', bom.name)}`
			: '<span class="mp-muted">no BOM linked</span>';

		if (!items || !items.length) {
			root.querySelector('#mp-materials-body').innerHTML = '<div class="mp-empty-inline">No raw materials on this Work Order.</div>';
			return;
		}
		root.querySelector('#mp-materials-body').innerHTML = `
			<table class="mp-table">
				<thead><tr><th>Item</th><th>Required</th><th>Transferred</th><th>Consumed</th><th>Available</th></tr></thead>
				<tbody>
					${items.map(function (d) {
						return `
						<tr>
							<td><div class="mp-item-code">${docLink('Item', d.item_code)}</div><div class="mp-muted mp-sm">${esc(d.item_name)}</div></td>
							<td>${fmtNum(d.required_qty)}</td>
							<td>
								${fmtNum(d.transferred_qty)}
								<div class="mp-bar"><div class="mp-bar-fill" style="width:${pct(d.transferred_qty, d.required_qty)}%"></div></div>
							</td>
							<td>${fmtNum(d.consumed_qty)}</td>
							<td>${fmtNum(d.available_qty_at_source_warehouse)}</td>
						</tr>`;
					}).join('')}
				</tbody>
			</table>
		`;
	}

	function renderSourceDocs(wo) {
		var rows = [
			['Sales Order', wo.sales_order ? docLink('Sales Order', wo.sales_order) : '—'],
			['Production Plan', wo.production_plan ? docLink('Production Plan', wo.production_plan) : '—'],
			['Material Request', wo.material_request ? docLink('Material Request', wo.material_request) : '—'],
			['Project', wo.project ? docLink('Project', wo.project) : '—'],
		];
		root.querySelector('#mp-source-body').innerHTML = rows.map(function (r) {
			return `<div class="mp-kv"><span class="mp-glbl">${esc(r[0])}</span>${r[1]}</div>`;
		}).join('');
	}

	function renderJobCards(jcs) {
		if (!jcs || !jcs.length) {
			root.querySelector('#mp-jc-body').innerHTML = '<div class="mp-empty-inline">No Job Cards created yet for this Work Order.</div>';
			return;
		}
		root.querySelector('#mp-jc-body').innerHTML = `
			<table class="mp-table">
				<thead><tr><th>Job Card</th><th>Operation</th><th>Workstation</th><th>Status</th><th>Qty</th><th>Employees</th></tr></thead>
				<tbody>
					${jcs.map(function (jc) {
						return `
						<tr>
							<td>${docLink('Job Card', jc.name)}</td>
							<td>${esc(jc.operation)}</td>
							<td>${esc(jc.workstation) || '—'}</td>
							<td>${badge(jc.status, JC_STATUS_CLASS[jc.status] || 'grey')}</td>
							<td>
								${fmtNum(jc.total_completed_qty)} / ${fmtNum(jc.for_quantity)}
								<div class="mp-bar"><div class="mp-bar-fill" style="width:${pct(jc.total_completed_qty, jc.for_quantity)}%"></div></div>
							</td>
							<td>${(jc.employees || []).map(esc).join(', ') || '—'}</td>
						</tr>`;
					}).join('')}
				</tbody>
			</table>
		`;
	}

	function renderStockEntries(ses) {
		if (!ses || !ses.length) {
			root.querySelector('#mp-se-body').innerHTML = '<div class="mp-empty-inline">No Stock Entries created yet for this Work Order.</div>';
			return;
		}
		root.querySelector('#mp-se-body').innerHTML = `
			<table class="mp-table">
				<thead><tr><th>Stock Entry</th><th>Purpose</th><th>Posting Date</th><th>Items</th><th>FG Qty</th><th>Status</th></tr></thead>
				<tbody>
					${ses.map(function (se) {
						return `
						<tr>
							<td>${docLink('Stock Entry', se.name)}</td>
							<td>${badge(se.purpose, se.purpose === 'Manufacture' ? 'emerald' : 'blue')}</td>
							<td>${fmtDate(se.posting_date)}</td>
							<td>${se.item_count}</td>
							<td>${se.fg_completed_qty ? fmtNum(se.fg_completed_qty) : '—'}</td>
							<td>${docstatusBadge(se.docstatus)}</td>
						</tr>`;
					}).join('')}
				</tbody>
			</table>
		`;
	}

	function getMpHTML() {
		return `
		<div class="mp-dash">
			<div class="mp-header">
				<div>
					<div class="mp-brand-over">MANUFACTURING</div>
					<div class="mp-brand-name">Manufacturing Process</div>
					<div class="mp-brand-sub">One page for the whole trail — BOM → Work Order → Job Cards → Stock Entries</div>
				</div>
				<div class="mp-hdr-right">
					<button class="btn btn-sm btn-primary" id="mp-new-wo-btn">+ New Work Order</button>
				</div>
			</div>

			<div class="mp-fbar">
				<div class="mp-fg" style="flex:1; max-width:360px;">
					<label class="mp-flbl">Work Order</label>
					<div id="mp-wo-filter"></div>
				</div>
				<div class="mp-fg">
					<label class="mp-flbl">&nbsp;</label>
					<button class="btn btn-xs" id="mp-refresh-btn">⟳ Refresh</button>
				</div>
				<div class="mp-fg" style="flex:1;">
					<label class="mp-flbl">Recent Work Orders</label>
					<div class="mp-recent-chips" id="mp-recent-chips"></div>
				</div>
			</div>

			<div id="mp-body">
				<div class="mp-empty" id="mp-empty">
					Select a Work Order above (or create a new one) to see its BOM, Job Cards and Stock Entries — every document in the manufacturing process — on this one page.
				</div>

				<div id="mp-content" style="display:none;">
					<div class="mp-stepper" id="mp-stepper"></div>
					<div class="mp-card mp-wo-card" id="mp-wo-card"></div>

					<div class="mp-cols">
						<div class="mp-card">
							<div class="mp-card-head"><span>MATERIALS <span id="mp-bom-tag"></span></span></div>
							<div class="mp-card-body" id="mp-materials-body"></div>
						</div>
						<div class="mp-card">
							<div class="mp-card-head"><span>SOURCE DOCUMENTS</span></div>
							<div class="mp-card-body" id="mp-source-body"></div>
						</div>
					</div>

					<div class="mp-card">
						<div class="mp-card-head">
							<span>JOB CARDS</span>
							<button class="btn btn-xs" id="mp-add-jc-btn">+ New Job Card</button>
						</div>
						<div class="mp-card-body" id="mp-jc-body"></div>
					</div>

					<div class="mp-card">
						<div class="mp-card-head">
							<span>STOCK ENTRIES</span>
							<span class="mp-add-group">
								<button class="btn btn-xs" id="mp-add-transfer-btn">+ Material Transfer</button>
								<button class="btn btn-xs" id="mp-add-manufacture-btn">+ Manufacture Entry</button>
							</span>
						</div>
						<div class="mp-card-body" id="mp-se-body"></div>
					</div>
				</div>
			</div>
		</div>
		`;
	}
};
