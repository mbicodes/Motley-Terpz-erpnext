frappe.pages['live-production-monitor'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Live Production Monitor',
		single_column: true,
	});

	$(wrapper).find('.layout-main-section').html(getLpmHTML());
	var root = wrapper.querySelector('.lpm-dash');

	var API = 'cannabis_management.api.live_production_monitor.get_live_production_data';
	var AUTO_REFRESH_MS = 24000;

	var autoRefresh = true;
	var refreshTimer = null;
	var tickTimer = null;
	var woControl, jcControl;

	// ── Filter defaults ─────────────────────────────────────────────────────
	root.querySelector('#lpm-from-date').value = frappe.datetime.add_days(frappe.datetime.get_today(), -7);
	root.querySelector('#lpm-to-date').value = frappe.datetime.get_today();
	root.querySelector('#lpm-last-refresh').textContent = 'Last refresh: —';

	// ── Link-type filters (searchable, outside a form) ──────────────────────
	woControl = frappe.ui.form.make_control({
		parent: root.querySelector('#lpm-wo-filter'),
		df: { fieldtype: 'Link', options: 'Work Order', fieldname: 'work_order', placeholder: __('Work Order') },
		render_input: true,
	});
	woControl.refresh();
	woControl.$input.on('change awesomplete-selectcomplete', loadData);

	jcControl = frappe.ui.form.make_control({
		parent: root.querySelector('#lpm-jc-filter'),
		df: { fieldtype: 'Link', options: 'Job Card', fieldname: 'job_card', placeholder: __('Job Card') },
		render_input: true,
	});
	jcControl.refresh();
	jcControl.$input.on('change awesomplete-selectcomplete', loadData);

	// ── Static filter wiring ──────────────────────────────────────────────
	['#lpm-from-date', '#lpm-to-date', '#lpm-status', '#lpm-company', '#lpm-workstation', '#lpm-operation']
		.forEach(function (sel) {
			root.querySelector(sel).addEventListener('change', loadData);
		});

	root.querySelector('#lpm-load-btn').addEventListener('click', loadData);
	root.querySelector('#lpm-reset-btn').addEventListener('click', resetFilters);

	root.querySelector('#lpm-autorefresh').addEventListener('change', function () {
		autoRefresh = this.checked;
		if (autoRefresh) startAutoRefresh(); else stopAutoRefresh();
	});

	// ── Complete / View actions (event delegation on the grid) ─────────────
	root.querySelector('#lpm-grid').addEventListener('click', function (e) {
		var btn = e.target.closest('.lpm-complete-btn');
		if (!btn || btn.disabled) return;
		completeJobCard(btn.getAttribute('data-jc'), btn.getAttribute('data-for-qty'), btn.getAttribute('data-completed-qty'));
	});

	startAutoRefresh();
	tickTimer = setInterval(tick, 1000);
	$(wrapper).on('remove', function () {
		stopAutoRefresh();
		clearInterval(tickTimer);
	});

	loadData();

	// ── Helpers ──────────────────────────────────────────────────────────────
	function startAutoRefresh() {
		stopAutoRefresh();
		refreshTimer = setInterval(loadData, AUTO_REFRESH_MS);
	}
	function stopAutoRefresh() {
		if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
	}

	function resetFilters() {
		root.querySelector('#lpm-from-date').value = frappe.datetime.add_days(frappe.datetime.get_today(), -7);
		root.querySelector('#lpm-to-date').value = frappe.datetime.get_today();
		root.querySelector('#lpm-status').value = 'All Status';
		root.querySelector('#lpm-company').value = '';
		root.querySelector('#lpm-workstation').value = '';
		root.querySelector('#lpm-operation').value = '';
		woControl.set_value('');
		jcControl.set_value('');
		loadData();
	}

	function get_filter_values() {
		return {
			from_date: root.querySelector('#lpm-from-date').value,
			to_date: root.querySelector('#lpm-to-date').value,
			status: root.querySelector('#lpm-status').value,
			work_order: woControl.get_value(),
			job_card: jcControl.get_value(),
			company: root.querySelector('#lpm-company').value,
			workstation: root.querySelector('#lpm-workstation').value,
			operation: root.querySelector('#lpm-operation').value,
		};
	}

	function loadData() {
		frappe.call({
			method: API,
			args: { filters: JSON.stringify(get_filter_values()) },
			callback: function (r) {
				if (!r.message) return;
				var d = r.message;
				renderKPIs(d.kpis);
				renderGrid(d.job_cards);
				populateDynamicOptions(d.filter_options);
				var now = new Date();
				root.querySelector('#lpm-last-refresh').textContent =
					'Last refresh: ' + now.toLocaleDateString() + ', ' +
					now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
			},
			error: function () {
				root.querySelector('#lpm-last-refresh').textContent = 'Error loading data';
			},
		});
	}

	function populateDynamicOptions(opts) {
		if (!opts) return;
		fillSelect(root.querySelector('#lpm-workstation'), opts.workstations, __('All Workstations'));
		fillSelect(root.querySelector('#lpm-operation'), opts.operations, __('All Operations'));
		fillSelect(root.querySelector('#lpm-company'), opts.companies, __('All Companies'));
	}

	function fillSelect(select, values, allLabel) {
		var current = select.value;
		var options = '<option value="">' + allLabel + '</option>' +
			(values || []).map(function (v) { return '<option value="' + frappe.utils.escape_html(v) + '">' + frappe.utils.escape_html(v) + '</option>'; }).join('');
		select.innerHTML = options;
		if (values && values.indexOf(current) !== -1) select.value = current;
	}

	// ── KPIs ──────────────────────────────────────────────────────────────
	function renderKPIs(k) {
		if (!k) return;
		root.querySelector('#lpm-kv-active').textContent = k.total_active;
		root.querySelector('#lpm-kv-wip').textContent = k.work_in_progress;
		root.querySelector('#lpm-kv-open').textContent = k.open_pending;
		root.querySelector('#lpm-kv-completed').textContent = k.completed_today;
		root.querySelector('#lpm-kv-wo').textContent = k.total_work_order;
		root.querySelector('#lpm-kv-jc').textContent = k.total_job_card;
	}

	// ── Job Card grid ────────────────────────────────────────────────────
	var STATUS_CLASS = {
		'Open': 'grey',
		'Work In Progress': 'yellow',
		'Material Transferred': 'blue',
		'On Hold': 'red',
		'Submitted': 'teal',
		'Cancelled': 'dark',
		'Completed': 'green',
	};

	function renderGrid(jobCards) {
		var grid = root.querySelector('#lpm-grid');
		if (!jobCards || !jobCards.length) {
			grid.innerHTML = '<div class="lpm-empty">No job cards match the current filters.</div>';
			return;
		}
		grid.innerHTML = jobCards.map(renderCard).join('');
		tick();
	}

	function renderCard(jc) {
		var sc = STATUS_CLASS[jc.status] || 'grey';
		var pct = flt(jc.for_quantity) > 0
			? Math.min(flt(jc.total_completed_qty) / flt(jc.for_quantity) * 100, 100)
			: 0;
		var barClass = pct >= 90 ? '' : pct >= 50 ? ' mid' : ' low';

		var isRunning = jc.status === 'Work In Progress';
		var elapsedNow = elapsedText(jc, isRunning);
		var elapsedAttrs = 'data-start="' + (jc.actual_start_date || '') + '" data-status="' + jc.status + '"';

		var canComplete = isRunning;

		return '' +
			'<div class="lpm-card">' +
				'<div class="lpm-card-top">' +
					'<div class="lpm-card-title">' + (jc.operation || __('Operation')) + ' - ' + (jc.item_name || jc.production_item || '') + '</div>' +
					'<span class="lpm-pill ' + sc + '">' + __(jc.status) + '</span>' +
				'</div>' +
				'<div class="lpm-card-ref">' +
					'<a href="/app/work-order/' + jc.work_order + '" target="_blank">' + (jc.work_order || '—') + '</a>' +
					'<span class="lpm-ref-sep">·</span>' +
					'<span>' + (jc.workstation || '—') + '</span>' +
				'</div>' +
				'<div class="lpm-card-timer-row">' +
					'<div>' +
						'<div class="lpm-timer-lbl">' + __('Elapsed') + '</div>' +
						'<div class="lpm-elapsed" ' + elapsedAttrs + '>' + elapsedNow + '</div>' +
					'</div>' +
					'<div>' +
						'<div class="lpm-timer-lbl">' + __('Started On') + '</div>' +
						'<div class="lpm-started">' + (jc.actual_start_date ? frappe.datetime.str_to_user(jc.actual_start_date) : '—') + '</div>' +
					'</div>' +
				'</div>' +
				'<div class="lpm-card-progress">' +
					'<div class="lpm-pbar">' +
						'<div class="lpm-ptr"><div class="lpm-pfi' + barClass + '" style="width:' + pct + '%"></div></div>' +
						'<span class="lpm-ppct">' + pct.toFixed(0) + '%</span>' +
					'</div>' +
					'<div class="lpm-qty-lbl">' + flt(jc.total_completed_qty) + ' / ' + flt(jc.for_quantity) + '</div>' +
				'</div>' +
				'<div class="lpm-card-meta">' +
					'<div><span class="lpm-meta-lbl">' + __('Expected Start') + '</span><span>' + (jc.expected_start_date ? frappe.datetime.str_to_user(jc.expected_start_date) : '—') + '</span></div>' +
					'<div><span class="lpm-meta-lbl">' + __('Expected End') + '</span><span>' + (jc.expected_end_date ? frappe.datetime.str_to_user(jc.expected_end_date) : '—') + '</span></div>' +
					'<div><span class="lpm-meta-lbl">' + __('Time Required') + '</span><span>' + fmtMins(jc.time_required) + '</span></div>' +
					'<div><span class="lpm-meta-lbl">' + __('Total Time') + '</span><span class="lpm-elapsed" ' + elapsedAttrs + '>' + elapsedNow + '</span></div>' +
				'</div>' +
				'<div class="lpm-card-actions">' +
					'<button class="lpm-btn lpm-complete-btn" data-jc="' + jc.name + '" data-for-qty="' + jc.for_quantity + '" data-completed-qty="' + jc.total_completed_qty + '"' + (canComplete ? '' : ' disabled') + '>&check; ' + __('Complete') + '</button>' +
					'<a class="lpm-btn lpm-btn-secondary" href="/app/job-card/' + jc.name + '" target="_blank">' + __('View Details') + '</a>' +
				'</div>' +
			'</div>';
	}

	function elapsedText(jc, isRunning) {
		if (isRunning) {
			if (!jc.actual_start_date) return '--:--:--';
			return formatDuration(new Date() - parseServerDatetime(jc.actual_start_date));
		}
		if (jc.status === 'Completed' && jc.actual_start_date && jc.actual_end_date) {
			return formatDuration(parseServerDatetime(jc.actual_end_date) - parseServerDatetime(jc.actual_start_date));
		}
		return '--:--:--';
	}

	function fmtMins(mins) {
		var m = flt(mins);
		if (!m) return '—';
		var h = Math.floor(m / 60);
		var rem = Math.round(m % 60);
		return h > 0 ? (h + 'h ' + rem + 'm') : (rem + ' min');
	}

	// ── Live ticking (independent of the 24s data refresh) ──────────────────
	function tick() {
		var now = new Date();
		root.querySelectorAll('.lpm-elapsed[data-status="Work In Progress"]').forEach(function (el) {
			var start = parseServerDatetime(el.getAttribute('data-start'));
			el.textContent = start ? formatDuration(now - start) : '--:--:--';
		});
	}

	function parseServerDatetime(v) {
		if (!v) return null;
		var d = new Date(String(v).replace(' ', 'T'));
		return isNaN(d.getTime()) ? null : d;
	}

	function formatDuration(ms) {
		if (!ms || ms < 0) ms = 0;
		var totalSec = Math.floor(ms / 1000);
		var h = Math.floor(totalSec / 3600);
		var m = Math.floor((totalSec % 3600) / 60);
		var s = totalSec % 60;
		function pad(n) { return String(n).length < 2 ? '0' + n : String(n); }
		return pad(h) + ':' + pad(m) + ':' + pad(s);
	}

	// ── Complete Job Card (reuses ERPNext's own whitelisted endpoint) ───────
	function completeJobCard(name, forQty, completedQty) {
		frappe.prompt(
			[{ fieldname: 'qty', fieldtype: 'Float', label: __('Completed Qty'), default: flt(forQty) - flt(completedQty), reqd: 1 }],
			function (data) {
				frappe.call({
					method: 'erpnext.manufacturing.doctype.job_card.job_card.make_time_log',
					args: {
						args: {
							job_card_id: name,
							complete_time: frappe.datetime.now_datetime(),
							status: 'Complete',
							completed_qty: data.qty,
						},
					},
					freeze: true,
					callback: function () { loadData(); },
				});
			},
			__('Complete Job Card'),
			__('Complete')
		);
	}

	// ── HTML shell ────────────────────────────────────────────────────────
	function getLpmHTML() {
		return `
<div class="lpm-dash">

  <!-- HEADER -->
  <div class="lpm-header">
    <div>
      <div class="lpm-brand-name">Live Production Monitor</div>
      <div class="lpm-brand-sub">Real-Time Job Card Operations</div>
    </div>
    <div class="lpm-hdr-right">
      <div class="lpm-lrefresh" id="lpm-last-refresh">—</div>
      <div class="lpm-interval-lbl">${__('Auto-Refresh every')} 24s</div>
      <label class="lpm-toggle">
        <input type="checkbox" id="lpm-autorefresh" checked>
        <span>${__('Auto-Refresh')}</span>
      </label>
      <button id="lpm-reset-btn" class="lpm-btn lpm-btn-secondary">${__('Reset')}</button>
      <button id="lpm-load-btn" class="lpm-btn">&#8635; ${__('Load')}</button>
    </div>
  </div>

  <!-- FILTER BAR -->
  <div class="lpm-fbar">
    <div class="lpm-fg">
      <div class="lpm-flbl">${__('From Date')}</div>
      <input type="date" id="lpm-from-date" class="lpm-finp">
    </div>
    <div class="lpm-fg">
      <div class="lpm-flbl">${__('To Date')}</div>
      <input type="date" id="lpm-to-date" class="lpm-finp">
    </div>
    <div class="lpm-fg">
      <div class="lpm-flbl">${__('Status')}</div>
      <select id="lpm-status" class="lpm-fsel">
        <option value="All Status" selected>${__('All Status')}</option>
        <option value="Open">${__('Open')}</option>
        <option value="Work In Progress">${__('Work In Progress')}</option>
        <option value="Completed">${__('Completed')}</option>
      </select>
    </div>
    <div class="lpm-fg">
      <div class="lpm-flbl">${__('Work Order')}</div>
      <div id="lpm-wo-filter" class="lpm-linkctrl"></div>
    </div>
    <div class="lpm-fg">
      <div class="lpm-flbl">${__('Job Card')}</div>
      <div id="lpm-jc-filter" class="lpm-linkctrl"></div>
    </div>
    <div class="lpm-fg">
      <div class="lpm-flbl">${__('Company')}</div>
      <select id="lpm-company" class="lpm-fsel"><option value="">${__('All Companies')}</option></select>
    </div>
    <div class="lpm-fg">
      <div class="lpm-flbl">${__('Workstation')}</div>
      <select id="lpm-workstation" class="lpm-fsel"><option value="">${__('All Workstations')}</option></select>
    </div>
    <div class="lpm-fg">
      <div class="lpm-flbl">${__('Operation')}</div>
      <select id="lpm-operation" class="lpm-fsel"><option value="">${__('All Operations')}</option></select>
    </div>
  </div>

  <!-- KPI STRIP -->
  <div class="lpm-kpi-grid">
    <div class="lpm-kc" style="--kc:#2563eb">
      <div class="lpm-klbl">${__('Total Active')}</div>
      <div class="lpm-kval" id="lpm-kv-active">—</div>
    </div>
    <div class="lpm-kc" style="--kc:#d97706">
      <div class="lpm-klbl">${__('Work In Progress')}</div>
      <div class="lpm-kval" id="lpm-kv-wip">—</div>
    </div>
    <div class="lpm-kc" style="--kc:#059669">
      <div class="lpm-klbl">${__('Open / Pending')}</div>
      <div class="lpm-kval" id="lpm-kv-open">—</div>
    </div>
    <div class="lpm-kc" style="--kc:#7c3aed">
      <div class="lpm-klbl">${__('Completed Today')}</div>
      <div class="lpm-kval" id="lpm-kv-completed">—</div>
    </div>
    <div class="lpm-kc" style="--kc:#db2777">
      <div class="lpm-klbl">${__('Total Work Order')}</div>
      <div class="lpm-kval" id="lpm-kv-wo">—</div>
    </div>
    <div class="lpm-kc" style="--kc:#0d9488">
      <div class="lpm-klbl">${__('Total Job Card')}</div>
      <div class="lpm-kval" id="lpm-kv-jc">—</div>
    </div>
  </div>

  <!-- JOB CARD GRID -->
  <div class="lpm-grid" id="lpm-grid">
    <div class="lpm-empty">${__('Loading…')}</div>
  </div>

</div>`;
	}
};
