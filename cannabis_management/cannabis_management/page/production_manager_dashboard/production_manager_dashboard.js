frappe.pages['production-manager-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Production Manager',
		single_column: true,
	});

	$(wrapper).find('.layout-main-section').html(getPmHTML());
	var root = wrapper.querySelector('.pm-dash');

	var API    = 'cannabis_management.api.production_manager_dashboard.get_dashboard_data';
	var preset = 'week';
	var fromDate = getWeekStart();
	var toDate   = frappe.datetime.nowdate();
	var refreshTimer = null;

	root.querySelector('#pm-from-date').value = fromDate;
	root.querySelector('#pm-to-date').value   = toDate;
	root.querySelector('#pm-last-refresh').textContent = 'Loading…';

	// ── Helpers ───────────────────────────────────────────────────────────
	function getWeekStart() {
		var d = new Date();
		var day = d.getDay();
		var diff = (day === 0) ? 6 : day - 1;
		d.setDate(d.getDate() - diff);
		return d.toISOString().slice(0, 10);
	}
	function fmtNum(v) { return parseFloat(v || 0).toLocaleString(undefined, { maximumFractionDigits: 1 }); }
	function fmtHrs(mins) {
		var m = parseFloat(mins || 0);
		if (m < 60) return m.toFixed(0) + ' min';
		return (m / 60).toFixed(1) + ' hr';
	}

	// ── Filter wiring ─────────────────────────────────────────────────────
	root.querySelector('#pm-refresh-btn').addEventListener('click', loadData);
	root.querySelector('#pm-from-date').addEventListener('change', function () {
		preset = 'custom'; fromDate = this.value; loadData();
	});
	root.querySelector('#pm-to-date').addEventListener('change', function () {
		preset = 'custom'; toDate = this.value; loadData();
	});
	root.querySelector('#pm-preset').addEventListener('change', function () {
		preset = this.value;
		var today = frappe.datetime.nowdate();
		if (preset === 'today') { fromDate = today; }
		if (preset === 'week')  { fromDate = getWeekStart(); }
		if (preset === '7')     { fromDate = frappe.datetime.add_days(today, -7); }
		if (preset === '30')    { fromDate = frappe.datetime.add_days(today, -30); }
		if (preset === 'all')   { fromDate = '2000-01-01'; }
		toDate = today;
		root.querySelector('#pm-from-date').value = fromDate;
		root.querySelector('#pm-to-date').value   = toDate;
		loadData();
	});

	refreshTimer = setInterval(loadData, 5 * 60 * 1000);
	$(wrapper).on('remove', function () { clearInterval(refreshTimer); });

	loadData();

	// ── Load ──────────────────────────────────────────────────────────────
	function loadData() {
		if (preset === 'week' || preset === 'today' || preset === 'all') {
			toDate = frappe.datetime.nowdate();
			root.querySelector('#pm-to-date').value = toDate;
		}
		setLoading();
		frappe.call({
			method: API,
			args: { from_date: fromDate, to_date: toDate },
			callback: function (r) {
				if (!r.message) return;
				var d = r.message;
				renderKPIs(d.kpis);
				renderLbsWashed(d.lbs_washed);
				renderLogistics(d.logistics);
				renderWorkstations(d.workstations);
				renderMicron(d.micron);
				renderEmployees(d.employees);
				renderJobCards(d.job_cards);
				renderPipeline(d.pipeline);
				var pl = root.querySelector('#pm-period-label');
				if (pl) pl.textContent = fromDate + ' – ' + toDate;
				var now = new Date();
				root.querySelector('#pm-last-refresh').textContent =
					'Last refresh: ' + now.toLocaleDateString() + ', ' +
					now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
				setTimeout(function () {
					drawOpsChart(d.operations);
					drawLbsChart(d.lbs_washed ? d.lbs_washed.daily : []);
				}, 80);
			},
			error: function () {
				root.querySelector('#pm-last-refresh').textContent = 'Error loading data';
			},
		});
	}

	function setLoading() {
		['pm-kv-active','pm-kv-openjc','pm-kv-output','pm-kv-overdue'].forEach(function (id) {
			var el = root.querySelector('#' + id);
			if (el) el.innerHTML = '<span class="pm-loader"></span>';
		});
	}

	// ── KPIs ──────────────────────────────────────────────────────────────
	function renderKPIs(k) {
		function set(id, val, sub) {
			var el = root.querySelector('#' + id);
			if (el) el.textContent = val;
			if (sub) { var s = root.querySelector('#' + id.replace('kv','ks')); if (s) s.textContent = sub; }
		}
		set('pm-kv-active',  k.active_wo,    'Not Started + In Process');
		set('pm-kv-openjc',  k.open_jc,      'Open + Work In Progress');
		set('pm-kv-output',  fmtNum(k.today_output), 'grams produced today');
		set('pm-kv-overdue', k.overdue_wo,   'planned_end_date < today');
		// Highlight overdue card red when > 0
		var card = root.querySelector('#pm-overdue-card');
		if (card) { card.classList.toggle('overdue', parseInt(k.overdue_wo) > 0); }
	}

	// ── Operations horizontal bar (canvas) ────────────────────────────────
	function drawOpsChart(data) {
		var c = root.querySelector('#pm-ops-canvas');
		if (!c || !data || !data.length) return;
		var dpr = window.devicePixelRatio || 1;
		var W = c.offsetWidth || 400, H = 220;
		c.width = Math.round(W * dpr); c.height = Math.round(H * dpr);
		c.style.height = H + 'px';
		var ctx = c.getContext('2d');
		ctx.scale(dpr, dpr);

		var pl = { l: 130, r: 60, t: 16, b: 20 };
		var cw = W - pl.l - pl.r;
		var ch = H - pl.t - pl.b;
		var n  = Math.min(data.length, 8);
		var bh = Math.min(Math.floor(ch / n) - 6, 22);
		var mx = 0;
		data.forEach(function (d) { if (parseFloat(d.total_mins) > mx) mx = parseFloat(d.total_mins); });
		mx = mx * 1.1 || 60;

		var COLORS = ['#2563eb','#0891b2','#059669','#d97706','#7c3aed','#db2777','#ea580c','#65a30d'];

		for (var i = 0; i < n; i++) {
			var row = data[i];
			var y   = pl.t + i * (ch / n) + (ch / n - bh) / 2;
			var bw  = (parseFloat(row.total_mins) / mx) * cw;

			// Operation label
			ctx.fillStyle = '#64748b'; ctx.font = '11px "DM Sans",system-ui';
			ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
			var lbl = String(row.operation || 'Unknown');
			if (lbl.length > 16) lbl = lbl.slice(0, 15) + '…';
			ctx.fillText(lbl, pl.l - 6, y + bh / 2);

			// Bar
			ctx.fillStyle = COLORS[i % COLORS.length];
			ctx.beginPath();
			ctx.roundRect ? ctx.roundRect(pl.l, y, bw, bh, 3) : ctx.rect(pl.l, y, bw, bh);
			ctx.fill();

			// Value label
			ctx.fillStyle = '#1e293b'; ctx.font = 'bold 11px "DM Mono","Courier New"';
			ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
			var hrs = (parseFloat(row.total_mins) / 60).toFixed(1);
			ctx.fillText(hrs + ' hr · ' + row.jc_count + ' JC', pl.l + bw + 6, y + bh / 2);
		}
	}

	// ── Workstations ──────────────────────────────────────────────────────
	function renderWorkstations(data) {
		var wrap = root.querySelector('#pm-ws-grid');
		if (!wrap) return;
		if (!data || !data.length) { wrap.innerHTML = '<div class="pm-empty">No workstation data.</div>'; return; }
		wrap.innerHTML = data.map(function (ws) {
			var isActive = parseInt(ws.active || 0) > 0;
			var badge = isActive
				? '<span class="pm-wsbadge active">● Active</span>'
				: '<span class="pm-wsbadge idle">Idle</span>';
			return '<div class="pm-wsc">' +
				'<div class="pm-wsname">' + (ws.workstation || 'Unassigned') + '</div>' +
				badge +
				'<div class="pm-wsstat">' + ws.active + ' WIP</div>' +
				'<div class="pm-wsstat">' + ws.completed + ' Done</div>' +
				'</div>';
		}).join('');
	}

	// ── Micron ────────────────────────────────────────────────────────────
	function renderMicron(micronData) {
		var wrap = root.querySelector('#pm-micron-ladder');
		if (!wrap) return;
		if (!micronData || !micronData.length) {
			wrap.innerHTML = '<div class="pm-empty">No micron data for this period.</div>';
			return;
		}
		var COLORS = { '150U':'#6B4020','120U':'#9A5E28','90U':'#b45309','73U':'#d97706','45U':'#ca8a04','25U':'#0891b2' };
		var FULL_MELT = ['73U','45U','25U'];
		var maxG  = Math.max.apply(null, micronData.map(function (m) { return parseFloat(m.grams || 0); }));
		var totalG = micronData.reduce(function (s, m) { return s + parseFloat(m.grams || 0); }, 0);
		var fmTotal = micronData.filter(function (m) { return FULL_MELT.indexOf(m.micron_size) !== -1; })
			.reduce(function (s, m) { return s + parseFloat(m.grams || 0); }, 0);

		var html = '';
		var fmInserted = false;
		micronData.forEach(function (m) {
			if (!fmInserted && FULL_MELT.indexOf(m.micron_size) !== -1) {
				html += '<div class="pm-fmbracket">Full Melt Zone</div>';
				fmInserted = true;
			}
			var color = COLORS[m.micron_size] || '#94a3b8';
			var barW  = maxG > 0 ? Math.round(parseFloat(m.grams || 0) / maxG * 100) : 0;
			var pct   = totalG > 0 ? (parseFloat(m.grams || 0) / totalG * 100).toFixed(1) : '0.0';
			html += '<div class="pm-mrow">' +
				'<div class="pm-mlbl" style="color:' + color + '">' + m.micron_size + '</div>' +
				'<div class="pm-mtrack"><div class="pm-mfill" style="width:' + barW + '%;background:' + color + '"></div></div>' +
				'<div class="pm-mg" style="color:' + color + '">' + fmtNum(m.grams) + ' g</div>' +
				'<div class="pm-mpct">' + pct + '%</div>' +
				'</div>';
		});
		var fmPct = totalG > 0 ? (fmTotal / totalG * 100).toFixed(1) : '0.0';
		html += '<div class="pm-mtotal">' +
			'<div class="pm-mtlbl">Total Classified</div>' +
			'<div style="text-align:right">' +
			'<div class="pm-mtval">' + fmtNum(totalG) + ' g</div>' +
			'<div class="pm-mtsub">Full Melt: ' + fmPct + '%</div>' +
			'</div></div>';
		wrap.innerHTML = html;
	}

	// ── Employees ─────────────────────────────────────────────────────────
	function renderEmployees(data) {
		var tbody = root.querySelector('#pm-emp-tbody');
		if (!tbody) return;
		if (!data || !data.length) { tbody.innerHTML = '<tr><td colspan="4" class="pm-empty">No time logs for this period.</td></tr>'; return; }
		var maxMins = Math.max.apply(null, data.map(function (e) { return parseFloat(e.total_mins || 0); }));
		tbody.innerHTML = data.map(function (e) {
			var mins = parseFloat(e.total_mins || 0);
			var pct  = maxMins > 0 ? Math.round(mins / maxMins * 100) : 0;
			return '<tr>' +
				'<td>' + (e.employee_name || e.employee || '—') + '</td>' +
				'<td class="pm-qnum">' + e.jc_count + '</td>' +
				'<td>' +
					'<div class="pm-hrbar"><div class="pm-hrfill" style="width:' + pct + '%"></div></div>' +
					'<div style="font-size:10px;color:#94a3b8;font-family:\'DM Mono\',monospace;margin-top:2px">' + fmtHrs(mins) + '</div>' +
				'</td>' +
				'<td class="pm-qnum">' + (mins > 0 ? (mins / 60).toFixed(1) + ' hr' : '—') + '</td>' +
				'</tr>';
		}).join('');
	}

	// ── Job Cards table ───────────────────────────────────────────────────
	function renderJobCards(data) {
		var tbody = root.querySelector('#pm-jc-tbody');
		if (!tbody) return;
		if (!data || !data.length) { tbody.innerHTML = '<tr><td colspan="7" class="pm-empty">No job cards for this period.</td></tr>'; return; }
		var SC = { 'Completed':'cp','Work In Progress':'wip','Open':'op','On Hold':'low' };
		tbody.innerHTML = data.map(function (jc) {
			var sc = SC[jc.status] || 'ns';
			return '<tr>' +
				'<td><a href="/app/job-card/' + jc.name + '" target="_blank">' + jc.name + '</a></td>' +
				'<td>' + (jc.operation || '—') + '</td>' +
				'<td>' + (jc.workstation || '—') + '</td>' +
				'<td>' + (jc.employee_name || '—') + '</td>' +
				'<td class="pm-qnum">' + fmtNum(jc.for_quantity) + '</td>' +
				'<td>' + fmtHrs(jc.total_mins) + '</td>' +
				'<td><span class="pm-pill ' + sc + '">' + jc.status + '</span></td>' +
				'</tr>';
		}).join('');
		root.querySelector('#pm-jc-rows').textContent = 'Rows: ' + data.length;
	}

	// ── WO Pipeline ───────────────────────────────────────────────────────
	function renderPipeline(data) {
		var tbody = root.querySelector('#pm-pipe-tbody');
		if (!tbody) return;
		if (!data || !data.length) { tbody.innerHTML = '<tr><td colspan="8" class="pm-empty">No work orders for this period.</td></tr>'; return; }
		var SC = { 'Completed':'cp','In Process':'ip','Not Started':'ns','Stopped':'low' };
		tbody.innerHTML = data.map(function (wo) {
			var sc   = SC[wo.status] || 'ns';
			var pct  = parseFloat(wo.completion_pct || 0);
			var bclr = pct >= 90 ? '' : pct >= 50 ? ' mid' : ' low';
			var overdueBadge = parseInt(wo.is_overdue) ? '<span class="pm-overdue-tag">Overdue</span>' : '';
			return '<tr>' +
				'<td><a href="/app/work-order/' + wo.name + '" target="_blank">' + wo.name + '</a></td>' +
				'<td>' + (wo.item_name || wo.item_code || '—') + '</td>' +
				'<td class="pm-qnum">' + fmtNum(wo.qty) + '</td>' +
				'<td class="pm-qnum">' + fmtNum(wo.produced_qty) + '</td>' +
				'<td>' +
					'<div class="pm-pbar">' +
					'<div class="pm-ptr"><div class="pm-pfi' + bclr + '" style="width:' + Math.min(pct,100) + '%"></div></div>' +
					'<span class="pm-ppct">' + pct + '%</span>' +
					'</div>' +
				'</td>' +
				'<td>' + (wo.planned_end_date || '—') + overdueBadge + '</td>' +
				'<td><span class="pm-pill ' + sc + '">' + wo.status + '</span></td>' +
				'</tr>';
		}).join('');
		root.querySelector('#pm-pipe-rows').textContent = 'Rows: ' + data.length;
	}

	// ── LBS Washed ────────────────────────────────────────────────────────
	function renderLbsWashed(d) {
		if (!d) return;
		function setChip(id, val) { var el = root.querySelector('#' + id); if (el) el.textContent = val; }
		setChip('pm-lbs-total',  fmtNum(d.total_lbs) + ' lbs');
		setChip('pm-lbs-runs',   d.runs + ' run' + (d.runs !== 1 ? 's' : ''));
		setChip('pm-lbs-avg',    fmtNum(d.avg_per_run) + ' lbs / run');
	}

	function drawLbsChart(data) {
		var c = root.querySelector('#pm-lbs-canvas');
		if (!c) return;
		var dpr = window.devicePixelRatio || 1;
		var W = c.offsetWidth || 600, H = 160;
		c.width  = Math.round(W * dpr); c.height = Math.round(H * dpr);
		c.style.height = H + 'px';
		var ctx = c.getContext('2d');
		ctx.scale(dpr, dpr);

		if (!data || !data.length) {
			ctx.fillStyle = '#94a3b8'; ctx.font = '12px system-ui'; ctx.textAlign = 'center';
			ctx.fillText('No wash records for this period', W / 2, H / 2); return;
		}
		var pl = { l: 42, r: 14, t: 20, b: 28 };
		var cw = W - pl.l - pl.r, ch = H - pl.t - pl.b;
		var n  = data.length;
		var mx = 0;
		data.forEach(function (d) { if (parseFloat(d.total_lbs) > mx) mx = parseFloat(d.total_lbs); });
		mx = mx * 1.15 || 100;
		var colW = cw / n, bw = Math.min(colW * 0.6, 40);

		for (var i = 0; i <= 4; i++) {
			var y = pl.t + ch * (1 - i / 4);
			ctx.beginPath(); ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1;
			ctx.moveTo(pl.l, y); ctx.lineTo(pl.l + cw, y); ctx.stroke();
			ctx.fillStyle = '#94a3b8'; ctx.font = '9px "Courier New"'; ctx.textAlign = 'right';
			ctx.fillText(Math.round(mx * i / 4), pl.l - 4, y + 3);
		}

		data.forEach(function (row, i) {
			var x  = pl.l + colW * i + (colW - bw) / 2;
			var bh = (parseFloat(row.total_lbs) / mx) * ch;
			ctx.fillStyle = '#0c2340';
			ctx.beginPath();
			if (ctx.roundRect) { ctx.roundRect(x, pl.t + ch - bh, bw, bh, [3, 3, 0, 0]); } else { ctx.rect(x, pl.t + ch - bh, bw, bh); }
			ctx.fill();
			// Value above bar
			ctx.fillStyle = '#1e293b'; ctx.font = 'bold 10px "DM Mono","Courier New"';
			ctx.textAlign = 'center';
			ctx.fillText(fmtNum(row.total_lbs), pl.l + colW * (i + 0.5), pl.t + ch - bh - 5);
			// Date label
			var lbl = String(row.dt || '').slice(5);
			ctx.fillStyle = '#94a3b8'; ctx.font = '9px system-ui';
			ctx.fillText(lbl, pl.l + colW * (i + 0.5), H - 7);
		});
	}

	// ── Logistics ─────────────────────────────────────────────────────────
	function renderLogistics(d) {
		if (!d) return;
		var COLORS = { 'To Deliver and Bill':'#2563eb','To Deliver':'#059669','To Bill':'#d97706','Draft':'#94a3b8' };
		var kpis = root.querySelector('#pm-log-kpis');
		if (kpis && d.kpis && d.kpis.length) {
			kpis.innerHTML = d.kpis.map(function (k) {
				var c = COLORS[k.status] || '#64748b';
				return '<div class="pm-log-kcard" style="--lkc:' + c + '">' +
					'<div class="pm-log-klbl">' + k.status + '</div>' +
					'<div class="pm-log-knum">' + k.cnt + '</div>' +
					'<div class="pm-log-kval">$' + parseFloat(k.total_value || 0).toLocaleString(undefined, {maximumFractionDigits: 0}) + '</div>' +
					'</div>';
			}).join('');
		}

		var tbody = root.querySelector('#pm-log-tbody');
		if (!tbody) return;
		if (!d.orders || !d.orders.length) {
			tbody.innerHTML = '<tr><td colspan="6" class="pm-empty">No active orders.</td></tr>'; return;
		}
		var SC = { 'To Deliver and Bill':'op','To Deliver':'cp','To Bill':'wip','Draft':'ns' };
		tbody.innerHTML = d.orders.map(function (so) {
			var sc = SC[so.status] || 'ns';
			return '<tr>' +
				'<td><a href="/app/sales-order/' + so.name + '" target="_blank">' + so.name + '</a></td>' +
				'<td>' + (so.customer || '—') + '</td>' +
				'<td><span class="pm-pill ' + sc + '">' + so.status + '</span></td>' +
				'<td class="pm-qnum">$' + parseFloat(so.grand_total || 0).toLocaleString(undefined, {maximumFractionDigits: 0}) + '</td>' +
				'<td>' + (so.transaction_date || '—') + '</td>' +
				'<td>' + (so.delivery_date || '—') + '</td>' +
				'</tr>';
		}).join('');
		root.querySelector('#pm-log-rows').textContent = 'Rows: ' + d.orders.length;
	}

	// ── HTML ──────────────────────────────────────────────────────────────
	function getPmHTML() {
		return `
<div class="pm-dash">

  <!-- HEADER -->
  <div class="pm-header">
    <div>
      <div class="pm-brand-over">Masters Touch Manufacturing</div>
      <div class="pm-brand-name">Production Manager</div>
      <div class="pm-brand-sub">Operational Control &nbsp;·&nbsp; ERPNext v15</div>
    </div>
    <div class="pm-hdr-right">
      <div class="pm-hdr-period" id="pm-period-label">—</div>
      <div><span class="pm-live-badge">● LIVE</span></div>
    </div>
  </div>

  <!-- FILTER BAR -->
  <div class="pm-fbar">
    <div class="pm-fg">
      <div class="pm-flbl">Date Preset</div>
      <select id="pm-preset" class="pm-fsel">
        <option value="today">Today</option>
        <option value="week" selected>This Week</option>
        <option value="7">Last 7 Days</option>
        <option value="30">Last 30 Days</option>
        <option value="all">All Time</option>
      </select>
    </div>
    <div class="pm-fg">
      <div class="pm-flbl">From Date</div>
      <input type="date" id="pm-from-date" class="pm-finp">
    </div>
    <div class="pm-fg">
      <div class="pm-flbl">To Date</div>
      <input type="date" id="pm-to-date" class="pm-finp">
    </div>
    <div class="pm-fspacer"></div>
    <div class="pm-lrefresh" id="pm-last-refresh">—</div>
    <button id="pm-refresh-btn" class="pm-ebtn pri">&#8635; Refresh</button>
  </div>

  <!-- KPI STRIP -->
  <div class="pm-kpi-grid">
    <div class="pm-kc" style="--kc:#2563eb">
      <div class="pm-kc-accent"></div>
      <div class="pm-kc-top"><span class="pm-kico">🏭</span><span class="pm-klbl">Active Work Orders</span></div>
      <div class="pm-kval" id="pm-kv-active"><span class="pm-loader"></span></div>
      <div class="pm-ksub" id="pm-ks-active">Not Started + In Process</div>
    </div>
    <div class="pm-kc" style="--kc:#d97706">
      <div class="pm-kc-accent"></div>
      <div class="pm-kc-top"><span class="pm-kico">📋</span><span class="pm-klbl">Open Job Cards</span></div>
      <div class="pm-kval" id="pm-kv-openjc"><span class="pm-loader"></span></div>
      <div class="pm-ksub" id="pm-ks-openjc">Open + Work In Progress</div>
    </div>
    <div class="pm-kc" style="--kc:#059669">
      <div class="pm-kc-accent"></div>
      <div class="pm-kc-top"><span class="pm-kico">✅</span><span class="pm-klbl">Today's Output</span></div>
      <div class="pm-kval" id="pm-kv-output"><span class="pm-loader"></span></div>
      <div class="pm-ksub" id="pm-ks-output">grams produced today</div>
    </div>
    <div class="pm-kc" id="pm-overdue-card" style="--kc:#e11d48">
      <div class="pm-kc-accent"></div>
      <div class="pm-kc-top"><span class="pm-kico">⚠️</span><span class="pm-klbl">Overdue Work Orders</span></div>
      <div class="pm-kval" id="pm-kv-overdue"><span class="pm-loader"></span></div>
      <div class="pm-ksub" id="pm-ks-overdue">planned end date passed</div>
    </div>
  </div>

  <!-- LBS WASHED PER DAY -->
  <div class="pm-lbs-wrap">
    <div class="pm-ptitle">LBS Washed Per Day</div>
    <div class="pm-psub">Total material processed through hash wash — from Hash Recording</div>
    <div class="pm-lbs-kpis">
      <div class="pm-lbs-chip">
        <div class="pm-lbs-chip-lbl">Total This Period</div>
        <div class="pm-lbs-chip-val" id="pm-lbs-total">—</div>
      </div>
      <div class="pm-lbs-chip">
        <div class="pm-lbs-chip-lbl">Wash Runs</div>
        <div class="pm-lbs-chip-val" id="pm-lbs-runs">—</div>
      </div>
      <div class="pm-lbs-chip">
        <div class="pm-lbs-chip-lbl">Avg Per Run</div>
        <div class="pm-lbs-chip-val" id="pm-lbs-avg">—</div>
      </div>
    </div>
    <canvas id="pm-lbs-canvas" class="pm-lbs-canvas"></canvas>
  </div>

  <!-- ROW 2: Operations + Workstations -->
  <div class="pm-row2">
    <div class="pm-panel">
      <div class="pm-ptitle">Operations Breakdown</div>
      <div class="pm-psub">Hours logged per operation type this period</div>
      <canvas id="pm-ops-canvas" class="pm-ops-canvas"></canvas>
    </div>
    <div class="pm-panel">
      <div class="pm-ptitle">Workstation Utilization</div>
      <div class="pm-psub">Job cards by workstation — active / completed</div>
      <div class="pm-ws-grid" id="pm-ws-grid"><div class="pm-empty">Loading…</div></div>
    </div>
  </div>

  <!-- ROW 3: Micron + Employee time -->
  <div class="pm-row3">
    <div class="pm-panel">
      <div class="pm-ptitle">Micron Quality Ladder</div>
      <div class="pm-psub">Grams collected per micron size this period</div>
      <div id="pm-micron-ladder"><div class="pm-empty">Loading…</div></div>
    </div>
    <div class="pm-panel">
      <div class="pm-ptitle">Employee Time Log</div>
      <div class="pm-psub">Hours logged per employee this period</div>
      <table class="pm-emptbl">
        <thead>
          <tr><th>Employee</th><th>JCs</th><th>Time</th><th>Hours</th></tr>
        </thead>
        <tbody id="pm-emp-tbody">
          <tr><td colspan="4" class="pm-empty">Loading…</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- JOB CARDS TABLE -->
  <div class="pm-fullsec">
    <div class="pm-sec-hdr">
      Job Cards
      <span class="pm-sec-hint" id="pm-jc-rows">—</span>
    </div>
    <div class="pm-tscroll">
      <table class="pm-tbl">
        <thead>
          <tr>
            <th>Job Card</th><th>Operation</th><th>Workstation</th>
            <th>Employee</th><th>Qty</th><th>Time</th><th>Status</th>
          </tr>
        </thead>
        <tbody id="pm-jc-tbody">
          <tr><td colspan="7" class="pm-empty">Loading…</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- WO PIPELINE TABLE -->
  <div class="pm-fullsec">
    <div class="pm-sec-hdr">
      Work Order Pipeline
      <span class="pm-sec-hint" id="pm-pipe-rows">—</span>
    </div>
    <div class="pm-tscroll">
      <table class="pm-tbl">
        <thead>
          <tr>
            <th>Work Order</th><th>Item / Strain</th><th>Qty (g)</th>
            <th>Produced (g)</th><th>Completion</th><th>Planned End</th><th>Status</th>
          </tr>
        </thead>
        <tbody id="pm-pipe-tbody">
          <tr><td colspan="7" class="pm-empty">Loading…</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- MOTLEY TERPZ LOGISTICS -->
  <div class="pm-fullsec">
    <div class="pm-sec-hdr">
      Motley Terpz Logistics — Order Pipeline
      <span class="pm-sec-hint" id="pm-log-rows">Live · all active orders</span>
    </div>
    <div class="pm-log-kpis" id="pm-log-kpis"></div>
    <div class="pm-tscroll">
      <table class="pm-tbl">
        <thead>
          <tr>
            <th>Sales Order</th><th>Customer</th><th>Status</th>
            <th>Value</th><th>Order Date</th><th>Delivery Date</th>
          </tr>
        </thead>
        <tbody id="pm-log-tbody">
          <tr><td colspan="6" class="pm-empty">Loading…</td></tr>
        </tbody>
      </table>
    </div>
  </div>

</div>`;
	}
};
