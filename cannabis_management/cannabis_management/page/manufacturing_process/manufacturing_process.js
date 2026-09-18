/* Manufacturing Process — production run console.
 *
 * Desk-only (deliberate, per 2026-09-18 decision): the portal twin at
 * /manufacturing-process keeps running the older, already-tested trail-view
 * module (public/js/manufacturing_process_app.js) untouched. This file no
 * longer shares code with it — do not re-introduce that coupling.
 *
 * Every number and status shown here is read live from real documents via
 * cannabis_management.api.manufacturing_run_console — there is no demo/
 * sample data anywhere in this file. Document creation reuses the exact
 * same whitelisted methods the full doctype forms call (see that module's
 * docstring), so results are identical to using the full forms.
 */
frappe.pages['manufacturing-process'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Manufacturing Process',
		single_column: true,
	});

	var route = frappe.get_route();
	var initialMr = route && route.length > 1 ? route[1] : null;

	mpcMount($(wrapper).find('.layout-main-section')[0], initialMr);
};

function mpcMount(container, initialMaterialRequest) {
	var API = 'cannabis_management.api.manufacturing_run_console.';
	var LBS_TO_GRAM = 453.592;

	var STEP_META = [
		{ title: __('Start a run'), hint: __('Creates a Material Request (Manufacture) tagged to the project.') },
		{ title: __('Release to production'), hint: __('Creates Work Orders and Job Cards for every operation on the recipe.') },
		{ title: __('Send material to WIP'), hint: __('Material Transfer for Manufacture stock entry, from source to WIP.') },
		{ title: __('Run the operations'), hint: __('Start / pause / complete each operation — time logs land on its Job Card.') },
		{ title: __('Finish & record output'), hint: __('Manufacture stock entry (WIP to Finished Goods). Yield is calculated live.') },
	];

	var state = { mr: null, data: null, defaults: {}, tickInterval: null };

	container.innerHTML = '<div class="mpc-console"></div>';
	var root = container.querySelector('.mpc-console');

	frappe.call({ method: API + 'get_defaults', callback: function (r) { state.defaults = r.message || {}; render(); } });

	if (initialMaterialRequest) {
		state.mr = initialMaterialRequest;
		loadRun();
	} else {
		render();
	}

	// ------------------------------------------------------------------ data

	function loadRun() {
		if (!state.mr) return;
		frappe.call({
			method: API + 'get_run',
			args: { material_request: state.mr },
			freeze: true,
			callback: function (r) {
				state.data = r.message || null;
				render();
			},
		});
	}

	function esc(v) { return frappe.utils.escape_html(v == null ? '' : String(v)); }
	function fmtNum(v, d) { return (parseFloat(v) || 0).toLocaleString(undefined, { maximumFractionDigits: d == null ? 2 : d }); }
	function flt(v) { return parseFloat(v) || 0; }

	// ------------------------------------------------------------------ render

	function render() {
		if (state.tickInterval) { clearInterval(state.tickInterval); state.tickInterval = null; }

		if (!state.mr || !state.data || !state.data.material_request) {
			root.innerHTML = renderPickerHtml();
			bindPickerEvents();
			loadRecent();
			return;
		}

		var data = state.data;
		root.innerHTML =
			renderHeaderHtml(data) +
			renderProgressHtml(data.step) +
			'<div class="mpc-layout"><div id="mpc-steps"></div>' + renderScoreboardHtml(data) + '</div>';

		var stepsEl = root.querySelector('#mpc-steps');
		STEP_META.forEach(function (_, i) { stepsEl.appendChild(renderStepCard(data, i)); });

		if (data.step >= 5) {
			var banner = document.createElement('div');
			banner.className = 'mpc-complete-banner';
			banner.innerHTML = __('Run complete — yield, labour and time captured against {0}.', [esc(data.material_request.project || data.material_request.name)]);
			stepsEl.appendChild(banner);
		}

		startTicker();
	}

	function renderHeaderHtml(data) {
		var mr = data.material_request;
		var fgNames = (mr.finished_goods || []).map(function (f) { return f.item_name || f.item; }).filter(Boolean);
		return (
			'<div class="mpc-header">' +
				'<div>' +
					'<div class="mpc-title">' + __('Run') + ' · ' + esc(mr.project || mr.name) +
						' <span class="mpc-muted">— ' + esc(mr.name) + '</span></div>' +
					'<div class="mpc-sub">' + esc(fgNames.join(' + ') || __('No finished goods yet')) + ' · ' + esc(mr.company || '') + '</div>' +
				'</div>' +
				'<div class="mpc-status-pill' + (data.step >= 5 ? ' mpc-complete' : '') + '">' +
					(data.step >= 5 ? __('Complete') : __('Step {0} of 5', [Math.min(data.step + 1, 5)])) +
				'</div>' +
			'</div>'
		);
	}

	function renderProgressHtml(step) {
		var html = '<div class="mpc-progress">';
		STEP_META.forEach(function (_, i) {
			var cls = i < step ? 'done' : (i === step ? 'active' : '');
			html += '<div class="' + cls + '"></div>';
		});
		return html + '</div>';
	}

	function renderScoreboardHtml(data) {
		var sb = data.scoreboard || {};
		var target = null;
		var fgs = (data.material_request.finished_goods || []).filter(function (f) { return f.expected_yield_; });
		if (fgs.length) {
			target = fgs.reduce(function (s, f) { return s + f.expected_yield_; }, 0) / fgs.length;
		}
		var actualYield = sb.grams_in ? (sb.hash_produced / sb.grams_in * 100) : 0;
		var yieldHtml = '';
		if (target != null) {
			yieldHtml = '<div class="mpc-sb-yield' + (actualYield >= target ? ' mpc-sb-good' : '') + '">' +
				fmtNum(actualYield) + '% ' + __('vs target {0}%', [fmtNum(target)]) + '</div>';
		}

		var fgRows = (sb.produced_by_item || []).map(function (r) {
			return '<div class="mpc-sb-fg-row"><span>' + esc(r.item_name || r.item) + '</span><span>' + fmtNum(r.grams) + ' g</span></div>';
		}).join('');

		return (
			'<div class="mpc-scoreboard">' +
				'<div class="mpc-scoreboard-title">' + __('Live scoreboard') + '</div>' +
				'<div class="mpc-sb-label">' + __('Grams in') + '</div>' +
				'<div class="mpc-sb-value">' + fmtNum(sb.grams_in, 0) + ' g</div>' +
				'<div class="mpc-sb-label">' + __('Produced') + '</div>' +
				'<div class="mpc-sb-value">' + fmtNum(sb.hash_produced, 0) + ' g</div>' +
				fgRows +
				yieldHtml +
				'<div class="mpc-sb-label">' + __('Labour cost') + '</div>' +
				'<div class="mpc-sb-value mpc-sb-small">' + format_currency(sb.labour_cost || 0) + '</div>' +
				'<div class="mpc-sb-label">' + __('Machine time') + '</div>' +
				'<div class="mpc-sb-value mpc-sb-small">' + Math.round(sb.machine_minutes || 0) + ' ' + __('min') + '</div>' +
			'</div>'
		);
	}

	// ------------------------------------------------------------------ step cards

	function renderStepCard(data, i) {
		var meta = STEP_META[i];
		var step = data.step;
		var done = i < step, active = i === step;

		var card = document.createElement('div');
		card.className = 'mpc-step' + (done ? ' mpc-done' : '') + (active ? ' mpc-active' : '');
		card.innerHTML =
			'<div class="mpc-step-head">' +
				'<div class="mpc-step-num">' + (done ? '<i class="ti ti-check"></i>' : (i + 1)) + '</div>' +
				'<div class="mpc-step-title">' + esc(meta.title) + '</div>' +
			'</div>';

		if (done) {
			var tag = document.createElement('div');
			tag.className = 'mpc-done-tag';
			tag.textContent = __('Done');
			card.appendChild(tag);
			return card;
		}
		if (!active) return card;

		var body = document.createElement('div');
		body.className = 'mpc-step-body';

		if (i === 0) body.appendChild(renderStep1Release(data));
		else if (i === 1) body.appendChild(renderStep2Release(data));
		else if (i === 2) body.appendChild(renderStep3Wip(data));
		else if (i === 3) body.appendChild(renderStep4Operations(data));
		else if (i === 4) body.appendChild(renderStep5Output(data));

		var hint = document.createElement('div');
		hint.className = 'mpc-hint';
		hint.textContent = meta.hint;
		body.appendChild(hint);

		card.appendChild(body);
		return card;
	}

	// Step 1 shouldn't normally be "active" once a run exists (an existing MR
	// is always at least docstatus check away) — but if a Draft slipped
	// through, offer to submit it here instead of dead-ending the console.
	function renderStep1Release(data) {
		var wrap = document.createElement('div');
		var mr = data.material_request;
		wrap.innerHTML = '<div class="mpc-step-desc">' + __('{0} is still a Draft — submit it to continue.', [esc(mr.name)]) + '</div>';
		var btn = document.createElement('button');
		btn.textContent = __('Submit request');
		btn.onclick = function () {
			frappe.call({
				method: 'frappe.client.get',
				args: { doctype: 'Material Request', name: mr.name },
				callback: function (r) {
					if (!r.message) return;
					frappe.call({
						method: 'frappe.client.submit',
						args: { doc: r.message },
						freeze: true,
						callback: function () { loadRun(); },
					});
				},
			});
		};
		wrap.appendChild(btn);
		return wrap;
	}

	function renderStep2Release(data) {
		var wrap = document.createElement('div');
		wrap.innerHTML = '<div class="mpc-step-desc">' + __('One tap builds the Work Orders and Job Cards for every finished good below.') + '</div>';
		var fgList = document.createElement('div');
		(data.material_request.finished_goods || []).forEach(function (f) {
			var row = document.createElement('div');
			row.className = 'mpc-fg-row';
			row.innerHTML = '<span>' + esc(f.item_name || f.item || __('(item not set)')) + '</span>' +
				'<span class="mpc-muted">· ' + esc(f.operation || '') + ' · ' + fmtNum(f.target_grams, 0) + ' g target</span>';
			fgList.appendChild(row);
		});
		wrap.appendChild(fgList);

		var btn = document.createElement('button');
		btn.textContent = __('Release');
		btn.disabled = !(data.material_request.finished_goods || []).length;
		btn.onclick = function () {
			btn.disabled = true;
			frappe.call({
				method: API + 'release_to_production',
				args: { material_request: data.material_request.name },
				freeze: true,
				freeze_message: __('Creating Work Orders and Job Cards…'),
				callback: function () {
					frappe.show_alert({ message: __('Released to production.'), indicator: 'green' });
					loadRun();
				},
				error: function () { btn.disabled = false; },
			});
		};
		wrap.appendChild(btn);
		return wrap;
	}

	function renderStep3Wip(data) {
		var wrap = document.createElement('div');
		var wos = data.work_orders || [];
		wrap.innerHTML = '<div class="mpc-step-desc">' + __('Move raw materials to Work In Progress for {0} Work Order(s).', [wos.length]) + '</div>';

		var btn = document.createElement('button');
		btn.textContent = __('Send to WIP');
		btn.onclick = function () {
			btn.disabled = true;
			var pending = wos.filter(function (wo) { return flt(wo.material_transferred_for_manufacturing) < flt(wo.qty) - 0.0001; });
			var chain = Promise.resolve();
			pending.forEach(function (wo) {
				chain = chain.then(function () { return sendWipTransfer(wo); });
			});
			chain.then(function () {
				frappe.show_alert({ message: __('Material transferred to WIP.'), indicator: 'green' });
				loadRun();
			}).catch(function () { btn.disabled = false; });
		};
		wrap.appendChild(btn);
		return wrap;
	}

	function sendWipTransfer(wo) {
		return frappe.xcall('erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry', {
			work_order_id: wo.name,
			purpose: 'Material Transfer for Manufacture',
		}).then(function (se) {
			if (!se) return;
			return frappe.call({ method: 'frappe.client.insert', args: { doc: se } }).then(function (r) {
				return frappe.call({ method: 'frappe.client.submit', args: { doc: r.message } });
			});
		});
	}

	function renderStep4Operations(data) {
		var wrap = document.createElement('div');
		var jobCards = data.job_cards || [];
		if (!jobCards.length) {
			wrap.innerHTML = '<div class="mpc-empty">' + __('No Job Cards yet.') + '</div>';
			return wrap;
		}
		if (!state.defaults.employee) {
			var warn = document.createElement('div');
			warn.className = 'mpc-hint';
			warn.textContent = __('No Employee is linked to your user — time logs cannot be recorded until an administrator links one.');
			wrap.appendChild(warn);
		}
		jobCards.forEach(function (jc) { wrap.appendChild(renderJobCard(jc)); });
		return wrap;
	}

	function jcStatusClass(jc) {
		if (jc.status === 'Completed') return 'mpc-complete';
		if (jc.status === 'On Hold') return 'mpc-paused';
		if (jc.started_time || flt(jc.current_time) > 0) return 'mpc-running';
		return '';
	}

	function currentSubOperation(jc) {
		var subs = (jc.sub_operations || []).filter(function (d) { return d.status !== 'Complete'; });
		return subs.length ? subs[0].sub_operation : null;
	}

	function renderJobCard(jc) {
		var card = document.createElement('div');
		card.className = 'mpc-op-card';
		card.setAttribute('data-jc', jc.name);

		var statusLabel = jc.status;
		if (jc.status !== 'Completed' && jc.status !== 'On Hold' && (jc.started_time || flt(jc.current_time) > 0)) {
			statusLabel = __('Running');
		}

		card.innerHTML =
			'<div class="mpc-op-card-head">' +
				'<div class="mpc-op-name">' + esc(jc.operation) + ' <span class="mpc-muted">· ' + esc(jc.workstation || '') + '</span></div>' +
				'<div class="mpc-op-status ' + jcStatusClass(jc) + '">' + esc(statusLabel) + '</div>' +
			'</div>';

		var subs = jc.sub_operations || [];
		var current = currentSubOperation(jc);
		if (subs.length) {
			subs.forEach(function (s) {
				var row = document.createElement('div');
				row.className = 'mpc-sub-row' + (s.sub_operation === current ? ' mpc-sub-current' : '');
				row.innerHTML = '<span>' + esc(s.sub_operation) + '</span>' +
					'<span class="mpc-sub-timer">' + (s.status === 'Complete' ? __('done') : esc(s.status)) + '</span>';
				card.appendChild(row);
			});
		}

		if (jc.status !== 'Completed' && jc.status !== 'Cancelled') {
			var actions = document.createElement('div');
			actions.className = 'mpc-op-actions';

			if (jc.status === 'On Hold') {
				actions.appendChild(makeBtn(__('Resume'), function () { startJob(jc, 'Resume Job'); }));
			} else if (jc.started_time || flt(jc.current_time) > 0) {
				actions.appendChild(makeBtn(__('Pause'), function () { pauseJob(jc); }, 'mpc-btn-secondary'));
				actions.appendChild(makeBtn(__('Complete'), function () { completeJob(jc); }));
			} else {
				actions.appendChild(makeBtn(__('Start'), function () { startJob(jc, 'Work In Progress'); }));
			}
			card.appendChild(actions);
		}

		if (jc.status === 'Work In Progress' || jc.status === 'Open') {
			var timer = document.createElement('div');
			timer.className = 'mpc-hint mpc-jc-elapsed';
			timer.setAttribute('data-started', jc.started_time || '');
			card.appendChild(timer);
		}

		return card;
	}

	function makeBtn(label, onclick, cls) {
		var b = document.createElement('button');
		if (cls) b.className = cls;
		b.textContent = label;
		b.onclick = onclick;
		return b;
	}

	function employeesArg() {
		return state.defaults.employee ? [{ employee: state.defaults.employee }] : [];
	}

	function sendTimeLog(jc, args) {
		var subOp = currentSubOperation(jc);
		if (subOp) args.sub_operation = subOp;
		args.job_card_id = jc.name;
		frappe.call({
			method: 'erpnext.manufacturing.doctype.job_card.job_card.make_time_log',
			args: { args: args },
			freeze: true,
			callback: function () { loadRun(); },
		});
	}

	function startJob(jc, status) {
		sendTimeLog(jc, { start_time: frappe.datetime.now_datetime(), employees: employeesArg(), status: status });
	}

	function pauseJob(jc) {
		sendTimeLog(jc, { complete_time: frappe.datetime.now_datetime(), status: 'On Hold' });
	}

	function completeJob(jc) {
		var subs = jc.sub_operations || [];
		var setQty = true;
		if (subs.length > 1) {
			setQty = false;
			var lastOpRow = subs[subs.length - 2];
			if (lastOpRow.status === 'Complete') setQty = true;
		}
		if (setQty) {
			frappe.prompt(
				{ fieldtype: 'Float', label: __('Completed Quantity'), fieldname: 'qty', default: flt(jc.for_quantity) - flt(jc.total_completed_qty) },
				function (data) {
					sendTimeLog(jc, { complete_time: frappe.datetime.now_datetime(), status: 'Complete', completed_qty: data.qty });
				},
				__('Enter Value')
			);
		} else {
			sendTimeLog(jc, { complete_time: frappe.datetime.now_datetime(), status: 'Complete', completed_qty: 0.0 });
		}
	}

	function startTicker() {
		state.tickInterval = setInterval(function () {
			root.querySelectorAll('.mpc-jc-elapsed').forEach(function (el) {
				var started = el.getAttribute('data-started');
				if (!started) { el.textContent = ''; return; }
				var secs = Math.max(0, Math.round((Date.now() - frappe.datetime.str_to_obj(started).getTime()) / 1000));
				var m = Math.floor(secs / 60), s = secs % 60;
				el.textContent = __('Running') + ' ' + m + 'm ' + (s < 10 ? '0' : '') + s + 's';
			});
		}, 1000);
	}

	function renderStep5Output(data) {
		var wrap = document.createElement('div');
		var wos = (data.work_orders || []).filter(function (wo) { return flt(wo.produced_qty) < flt(wo.qty) - 0.0001; });
		if (!wos.length) {
			wrap.innerHTML = '<div class="mpc-empty">' + __('Nothing pending.') + '</div>';
			return wrap;
		}
		wos.forEach(function (wo) {
			var row = document.createElement('div');
			row.className = 'mpc-fg-row';
			var remaining = flt(wo.qty) - flt(wo.produced_qty);
			row.innerHTML = '<span>' + __('Grams of {0} produced', [esc(wo.item_name || wo.production_item)]) + '</span>';

			var input = document.createElement('input');
			input.type = 'number';
			input.style.width = '120px';
			input.value = remaining;
			row.appendChild(input);

			var btn = makeBtn(__('Complete run'), function () {
				var val = parseFloat(input.value) || 0;
				btn.disabled = true;
				recordOutput(wo, val).then(function () {
					frappe.show_alert({ message: __('Output recorded for {0}.', [wo.name]), indicator: 'green' });
					loadRun();
				}).catch(function () { btn.disabled = false; });
			});
			row.appendChild(btn);
			wrap.appendChild(row);
		});
		return wrap;
	}

	function recordOutput(wo, grams) {
		return frappe.xcall('erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry', {
			work_order_id: wo.name,
			purpose: 'Manufacture',
		}).then(function (se) {
			if (!se) return;
			(se.items || []).forEach(function (row) {
				if (row.item_code === wo.production_item) row.qty = grams;
			});
			se.fg_completed_qty = grams;
			return frappe.call({ method: 'frappe.client.insert', args: { doc: se } }).then(function (r) {
				return frappe.call({ method: 'frappe.client.submit', args: { doc: r.message } });
			});
		});
	}

	// ------------------------------------------------------------------ picker / new run

	function renderPickerHtml() {
		return (
			'<div class="mpc-sub" style="margin:0 2px 10px">' + __('Start a new production run below, or jump to one already in progress.') + '</div>' +
			'<div class="mpc-field-row" style="margin-bottom:14px">' +
				'<div class="mpc-field mpc-field-wide"><label>' + __('Resume a run') + '</label><div id="mpc-recent"></div></div>' +
			'</div>' +
			'<div class="mpc-step mpc-active">' +
				'<div class="mpc-step-head"><div class="mpc-step-num">1</div><div class="mpc-step-title">' + __('Start a run') + '</div></div>' +
				'<div class="mpc-step-body" id="mpc-new-run"></div>' +
			'</div>'
		);
	}

	function bindPickerEvents() {
		var body = root.querySelector('#mpc-new-run');
		body.innerHTML =
			'<div class="mpc-step-desc">' + __('Pick a project, the Fresh Frozen (raw) item and lbs — everything else (routing, warehouses, work orders, job cards, WIP transfer) is filled in automatically.') + '</div>' +
			'<div class="mpc-field-row">' +
				field('mpc-f-project', __('Project')) +
				field('mpc-f-company', __('Company')) +
				field('mpc-f-item', __('Raw Material Item')) +
				field('mpc-f-qty', __('Qty (lbs)')) +
				field('mpc-f-routing', __('Routing')) +
			'</div>' +
			'<div id="mpc-fg-preview"></div>' +
			'<button id="mpc-create-run-btn">' + __('Start run') + '</button>';

		function field(id, label) {
			return '<div class="mpc-field"><label>' + esc(label) + '</label><div id="' + id + '"></div></div>';
		}

		var ctl = {};
		ctl.project = makeControl('mpc-f-project', 'project', 'Link', 'Project');
		ctl.company = makeControl('mpc-f-company', 'company', 'Link', 'Company', state.defaults.company);
		ctl.item_code = makeControl('mpc-f-item', 'item_code', 'Link', 'Item');
		ctl.qty = makeControl('mpc-f-qty', 'qty', 'Float');
		// "Wash" covers every real run on this site so far — pre-filled as a
		// starting point, still editable for the day a Fresh Frozen item
		// actually needs one of the other Routings.
		ctl.routing = makeControl('mpc-f-routing', 'routing', 'Link', 'Routing', 'Wash');

		function makeControl(id, fieldname, fieldtype, options, defaultVal) {
			var c = frappe.ui.form.make_control({
				parent: root.querySelector('#' + id),
				df: { fieldtype: fieldtype, options: options, ignore_link_validation: true, fieldname: fieldname, default: defaultVal },
				render_input: true,
			});
			c.refresh();
			if (defaultVal) c.set_value(defaultVal);
			return c;
		}

		var fgRows = [];
		function rebuildFg() {
			var routing = ctl.routing.get_value();
			var itemCode = ctl.item_code.get_value();
			var qty = parseFloat(ctl.qty.get_value()) || 0;
			var previewEl = root.querySelector('#mpc-fg-preview');
			if (!routing || !itemCode || !qty) { fgRows = []; previewEl.innerHTML = ''; return; }

			frappe.call({
				method: 'frappe.client.get',
				args: { doctype: 'Routing', name: routing },
				callback: function (r) {
					var opNames = ((r.message && r.message.operations) || [])
						.slice().sort(function (a, b) { return a.idx - b.idx; })
						.map(function (o) { return o.operation; });
					if (!opNames.length) { previewEl.innerHTML = '<div class="mpc-empty">' + __('Routing has no operations.') + '</div>'; return; }

					frappe.call({
						method: 'frappe.client.get_list',
						args: { doctype: 'Item', filters: { custom_operation: ['in', opNames] }, fields: ['name', 'item_name', 'custom_operation', 'custom_yield_percentage'], limit_page_length: 0 },
						callback: function (r2) {
							var itemsByOp = {};
							(r2.message || []).forEach(function (it) { (itemsByOp[it.custom_operation] = itemsByOp[it.custom_operation] || []).push(it); });

							var inputGrams = qty * LBS_TO_GRAM;
							fgRows = opNames.map(function (op) {
								var matches = itemsByOp[op] || [];
								var auto = matches.length === 1 ? matches[0] : null;
								var yieldPct = auto ? (parseFloat(auto.custom_yield_percentage) || 0) : 0;
								var grams = yieldPct > 0 ? inputGrams * (yieldPct / 100) : 0;
								inputGrams = grams || inputGrams;
								return {
									operation: op, item: auto ? auto.name : '', item_name: auto ? auto.item_name : '',
									expected_yield_: yieldPct, finished_qty_grams: grams,
								};
							});
							renderFgPreview();
						},
					});
				},
			});
		}

		function renderFgPreview() {
			var previewEl = root.querySelector('#mpc-fg-preview');
			if (!fgRows.length) { previewEl.innerHTML = ''; return; }
			previewEl.innerHTML = '<div class="mpc-sub" style="margin:8px 2px">' + __('Finished products (from Routing)') + '</div>' +
				fgRows.map(function (f, i) {
					return '<div class="mpc-fg-row">' +
						'<span style="min-width:160px">' + esc(f.operation) + '</span>' +
						'<span class="mpc-muted">' + esc(f.item_name || f.item || __('(no Item declares this Operation)')) + '</span>' +
						'<input type="number" class="mpc-fg-yield" data-i="' + i + '" value="' + f.expected_yield_ + '" style="width:70px" title="' + esc(__('Yield %')) + '">' +
						'<span class="mpc-muted">' + fmtNum(f.finished_qty_grams, 0) + ' g</span>' +
					'</div>';
				}).join('');
			previewEl.querySelectorAll('.mpc-fg-yield').forEach(function (inp) {
				inp.addEventListener('change', function () {
					var i = parseInt(this.getAttribute('data-i'), 10);
					fgRows[i].expected_yield_ = parseFloat(this.value) || 0;
					var base = i === 0 ? (parseFloat(ctl.qty.get_value()) || 0) * LBS_TO_GRAM : fgRows[i - 1].finished_qty_grams;
					fgRows[i].finished_qty_grams = base * (fgRows[i].expected_yield_ / 100);
					renderFgPreview();
				});
			});
		}

		['routing', 'item_code', 'qty'].forEach(function (key) {
			ctl[key].$input.on('change awesomplete-selectcomplete', rebuildFg);
		});

		root.querySelector('#mpc-create-run-btn').addEventListener('click', function () {
			var btn = this;
			var payload = {
				company: ctl.company.get_value(),
				custom_project: ctl.project.get_value(),
				custom_routing: ctl.routing.get_value(),
				transaction_date: frappe.datetime.get_today(),
				items: [{ item_code: ctl.item_code.get_value(), qty: ctl.qty.get_value() }],
				custom_finished_goods: fgRows.filter(function (f) { return f.operation; }),
			};
			if (!payload.company || !payload.custom_project || !payload.items[0].item_code || !payload.items[0].qty) {
				frappe.msgprint(__('Project, Company, Raw Material Item and Qty are required.'));
				return;
			}
			if (!payload.custom_finished_goods.length) {
				frappe.msgprint(__('Pick a Routing that resolves to at least one finished product.'));
				return;
			}
			btn.disabled = true;
			frappe.call({
				method: API + 'start_run',
				args: { payload: payload },
				freeze: true,
				freeze_message: __('Starting run — creating the request, releasing to production and sending material to WIP…'),
				callback: function (r) {
					if (!r.message || !r.message.material_request) return;
					state.mr = r.message.material_request.name;
					state.data = r.message;
					frappe.set_route('manufacturing-process', state.mr);
					render();
				},
				error: function () { btn.disabled = false; },
			});
		});
	}

	// A single searchable filter (by Project, not raw Material Request IDs)
	// instead of an ever-growing row of chips.
	function loadRecent() {
		var parent = root.querySelector('#mpc-recent');
		if (!parent) return;
		frappe.call({
			method: API + 'get_recent_runs',
			callback: function (r) {
				var rows = r.message || [];
				var ctl = frappe.ui.form.make_control({
					parent: parent,
					df: {
						fieldtype: 'Autocomplete', fieldname: 'resume_run',
						placeholder: rows.length ? __('Search a project or run…') : __('No runs yet'),
						options: rows.map(function (mr) { return { label: (mr.custom_project || mr.name) + ' · ' + mr.name, value: mr.name }; }),
					},
					render_input: true,
				});
				ctl.refresh();
				ctl.$input.on('change awesomplete-selectcomplete', function () {
					var mr = ctl.get_value();
					if (!mr) return;
					state.mr = mr;
					frappe.set_route('manufacturing-process', state.mr);
					loadRun();
				});
			},
		});
	}
}
