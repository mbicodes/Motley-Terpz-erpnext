frappe.pages['manufacturing-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Manufacturing at a Glance',
		single_column: true,
	});

	$(wrapper).find('.layout-main-section').html(getMtmDashHTML());
	var root = wrapper.querySelector('.mtm-dash');

	var API = 'cannabis_management.api.manufacturing_dashboard.get_dashboard_data';
	var fromDate = '2000-01-01';
	var toDate   = frappe.datetime.nowdate();
	var company  = '';
	var preset   = 'all';
	var refreshTimer = null;

	// Seed filter inputs
	root.querySelector('#mtm-from-date').value = fromDate;
	root.querySelector('#mtm-to-date').value   = toDate;
	root.querySelector('#mtm-last-refresh').textContent = 'Loading…';

	// ── Wire up filter controls ──────────────────────────────────────────
	root.querySelector('#mtm-refresh-btn').addEventListener('click', loadData);
	root.querySelector('#mtm-from-date').addEventListener('change', function () {
		fromDate = this.value; loadData();
	});
	root.querySelector('#mtm-to-date').addEventListener('change', function () {
		toDate = this.value; loadData();
	});
	root.querySelector('#mtm-preset').addEventListener('change', function () {
		preset = this.value;
		if (preset === 'all') { fromDate = '2000-01-01'; }
		if (preset === '7')   { fromDate = frappe.datetime.add_days(frappe.datetime.nowdate(), -7); }
		if (preset === '30')  { fromDate = frappe.datetime.add_days(frappe.datetime.nowdate(), -30); }
		if (preset === '90')  { fromDate = frappe.datetime.add_days(frappe.datetime.nowdate(), -90); }
		toDate = frappe.datetime.nowdate();
		root.querySelector('#mtm-from-date').value = fromDate;
		root.querySelector('#mtm-to-date').value   = toDate;
		loadData();
	});

	// Auto-refresh every 5 minutes
	refreshTimer = setInterval(loadData, 5 * 60 * 1000);
	$(wrapper).on('remove', function () { clearInterval(refreshTimer); });

	loadData();

	// ── Main data load ────────────────────────────────────────────────────
	function loadData() {
		if (preset === 'all') {
			toDate = frappe.datetime.nowdate();
			root.querySelector('#mtm-to-date').value = toDate;
		}
		setLoadingKPIs();
		frappe.call({
			method: API,
			args: { from_date: fromDate, to_date: toDate },
			callback: function (r) {
				if (!r.message) return;
				renderDashboard(r.message);
				var now = new Date();
				root.querySelector('#mtm-last-refresh').textContent =
					'Last refresh: ' + now.toLocaleDateString() + ', ' +
					now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
				// Draw canvas charts after layout settles
				setTimeout(function () { drawAllCharts(r.message); }, 80);
			},
			error: function () {
				root.querySelector('#mtm-last-refresh').textContent = 'Error loading data';
			},
		});
	}

	// ── Formatters ────────────────────────────────────────────────────────
	function fmtG(v) {
		var n = parseFloat(v || 0);
		if (n >= 1000) return (n / 1000).toFixed(2) + ' kg';
		return n.toFixed(1) + ' g';
	}
	function fmtNum(v) { return parseFloat(v || 0).toLocaleString(undefined, { maximumFractionDigits: 1 }); }

	// ── Loading shimmer ───────────────────────────────────────────────────
	function setLoadingKPIs() {
		['mtm-kv-planned','mtm-kv-produced','mtm-kv-remaining','mtm-kv-loss',
		 'mtm-kv-jccount','mtm-kv-employees','mtm-kv-qph','mtm-kv-oee'].forEach(function (id) {
			var el = root.querySelector('#' + id);
			if (el) { el.innerHTML = '<span class="mtm-loader"></span>'; el.classList.remove('loaded'); }
		});
	}

	function setKpi(id, html, sub) {
		var el = root.querySelector('#' + id);
		if (el) { el.innerHTML = html; el.classList.add('loaded'); }
		if (sub) {
			var s = root.querySelector('#' + id.replace('kv', 'ks'));
			if (s) s.textContent = sub;
		}
	}

	// ── Render functions ──────────────────────────────────────────────────
	function renderDashboard(d) {
		renderKPIs(d.kpis, d.costs, d.employees);
		renderMicron(d.micron);
		renderTable(d.work_orders);
		// period label
		var pl = root.querySelector('#mtm-period-label');
		if (pl) pl.textContent = fromDate + ' – ' + toDate;
	}

	function renderKPIs(k, costs, employees) {
		var prodQty  = parseFloat(k.produced_qty || 0);
		var planQty  = parseFloat(k.planned_qty  || 0);
		var completionPct = planQty > 0 ? (prodQty / planQty * 100).toFixed(1) : '0.0';

		setKpi('mtm-kv-planned',  fmtNum(k.planned_qty),  'Work Orders: ' + k.wo_count);
		setKpi('mtm-kv-produced', fmtNum(k.produced_qty), 'Completion: ' + completionPct + '%');
		setKpi('mtm-kv-remaining',fmtNum(k.remaining_qty),'Completed WOs: ' + k.completed_wo + ' of ' + k.wo_count);
		setKpi('mtm-kv-loss',     fmtNum(k.process_loss), 'Loss Rate: ' + (planQty > 0 ? (k.process_loss / planQty * 100).toFixed(1) : '0.0') + '%');
		setKpi('mtm-kv-jccount',  k.jc_count,             'JC Completed: ' + k.jc_completed);

		var empCount = (employees || []).length;
		setKpi('mtm-kv-employees', empCount, 'Active this period');

		// qty/hour: total weighted_qty / total hours
		var totalWeightedQty = 0, totalMins = 0;
		(employees || []).forEach(function (e) {
			totalWeightedQty += parseFloat(e.weighted_qty || 0);
			totalMins += parseFloat(e.total_mins || 0);
		});
		var qph = totalMins > 0 ? (totalWeightedQty / (totalMins / 60)).toFixed(1) : '—';
		var tpu = (totalWeightedQty > 0 && totalMins > 0)
			? (totalMins / totalWeightedQty).toFixed(2) : '—';
		setKpi('mtm-kv-qph', qph, 'Time / Unit: ' + tpu + ' min');

		// OEE proxy: completion% × 100 as a proxy (efficiency)
		var oee = completionPct + '%';
		var rawCost = parseFloat((costs || {}).raw_material || 0);
		var opCost  = parseFloat((costs || {}).operating   || 0);
		var totalG  = parseFloat((costs || {}).total_produced_g || 0);
		var costPerG = totalG > 0 ? ((rawCost + opCost) / totalG).toFixed(2) : '—';
		setKpi('mtm-kv-oee', oee, 'Cost / g: $' + costPerG);
	}

	function renderMicron(micronData) {
		var wrap = root.querySelector('#mtm-micron-ladder');
		if (!wrap) return;
		if (!micronData || !micronData.length) {
			wrap.innerHTML = '<div class="mtm-empty">No micron data for this period.</div>';
			return;
		}

		var COLORS = { '150U':'#6B4020','120U':'#9A5E28','90U':'#b45309','73U':'#d97706','45U':'#ca8a04','25U':'#0891b2' };
		var FULL_MELT = ['73U','45U','25U'];
		var maxG = Math.max.apply(null, micronData.map(function (m) { return m.grams; }));
		var totalG = micronData.reduce(function (s, m) { return s + parseFloat(m.grams || 0); }, 0);
		var fullMeltTotal = micronData.filter(function (m) { return FULL_MELT.indexOf(m.micron_size) !== -1; })
			.reduce(function (s, m) { return s + parseFloat(m.grams || 0); }, 0);

		var html = '';
		var fmInserted = false;
		micronData.forEach(function (m) {
			if (!fmInserted && FULL_MELT.indexOf(m.micron_size) !== -1) {
				html += '<div class="mtm-fmbracket">Full Melt Zone</div>';
				fmInserted = true;
			}
			var color = COLORS[m.micron_size] || '#94a3b8';
			var barW  = maxG > 0 ? Math.round(parseFloat(m.grams || 0) / maxG * 100) : 0;
			var pct   = totalG > 0 ? (parseFloat(m.grams || 0) / totalG * 100).toFixed(1) : '0.0';
			html += '<div class="mtm-mrow">' +
				'<div class="mtm-mlbl" style="color:' + color + '">' + m.micron_size + '</div>' +
				'<div class="mtm-mtrack"><div class="mtm-mfill" style="width:' + barW + '%;background:' + color + '"></div></div>' +
				'<div class="mtm-mg" style="color:' + color + '">' + fmtNum(m.grams) + ' g</div>' +
				'<div class="mtm-mpct">' + pct + '%</div>' +
				'</div>';
		});

		var fmPct = totalG > 0 ? (fullMeltTotal / totalG * 100).toFixed(1) : '0.0';
		html += '<div class="mtm-mtotal">' +
			'<div class="mtm-mtlbl">Total Classified</div>' +
			'<div style="text-align:right">' +
			'<div class="mtm-mtval">' + fmtNum(totalG) + ' g</div>' +
			'<div class="mtm-mtsub">Full Melt (73U+45U+25U): ' + fmPct + '%</div>' +
			'</div></div>';

		wrap.innerHTML = html;
	}

	function renderTable(rows) {
		var tbody = root.querySelector('#mtm-wo-tbody');
		if (!tbody) return;
		if (!rows || !rows.length) {
			tbody.innerHTML = '<tr><td colspan="9" class="mtm-empty">No work orders for this period.</td></tr>';
			return;
		}
		var STATUS_CLASS = { 'Completed': 'cp', 'In Process': 'ip', 'Not Started': 'ns', 'Stopped': 'low' };
		var html = '';
		rows.forEach(function (wo) {
			var pct = parseFloat(wo.completion_pct || 0);
			var barColor = pct >= 90 ? '' : pct >= 50 ? ' mid' : ' low';
			var sc = STATUS_CLASS[wo.status] || 'ns';
			html += '<tr>' +
				'<td class="mtm-wodt">' + (wo.planned_start_date || '—') + '</td>' +
				'<td class="mtm-wodt">' + (wo.planned_end_date   || '—') + '</td>' +
				'<td><span class="mtm-woid"><a href="/app/work-order/' + wo.name + '" target="_blank">' + wo.name + '</a></span></td>' +
				'<td>' + (wo.item_name || wo.item_code || '—') + '</td>' +
				'<td class="mtm-qnum">' + fmtNum(wo.qty) + '</td>' +
				'<td class="mtm-qnum">' + fmtNum(wo.produced_qty) + '</td>' +
				'<td class="mtm-qnum">' + fmtNum(wo.remaining_qty) + '</td>' +
				'<td><div class="mtm-pbar"><div class="mtm-ptr"><div class="mtm-pfi' + barColor + '" style="width:' + Math.min(pct,100) + '%"></div></div>' + pct + '%</div></td>' +
				'<td><span class="mtm-spill ' + sc + '">' + wo.status + '</span></td>' +
				'</tr>';
		});
		tbody.innerHTML = html;
		root.querySelector('#mtm-wo-rows').textContent = 'Rows: ' + rows.length;
	}

	// ── Canvas Charts ─────────────────────────────────────────────────────
	var C = {
		text: '#1e293b', sec: '#64748b', muted: '#94a3b8',
		border: '#e2e8f0', bg: '#f1f5f9',
		emerald: '#059669', amber: '#d97706', blue: '#2563eb', rose: '#e11d48',
		planned: '#bfdbfe', surface: '#ffffff',
	};

	function ic(id) {
		var c = root.querySelector('#' + id);
		if (!c) return null;
		var dpr = window.devicePixelRatio || 1;
		var w = c.offsetWidth || 155;
		var h = c.offsetHeight || 155;
		c.width  = Math.round(w * dpr);
		c.height = Math.round(h * dpr);
		var ctx = c.getContext('2d');
		ctx.scale(dpr, dpr);
		return { ctx: ctx, w: w, h: h };
	}

	function drawDonut(id, segs, total, legendId) {
		var r = ic(id);
		if (!r) return;
		var ctx = r.ctx, w = r.w, h = r.h;
		var cx = w / 2, cy = h / 2 - 4;
		var rad = Math.min(w, h) * 0.39;
		var start = -Math.PI / 2;

		if (!total) {
			// Empty state
			ctx.beginPath(); ctx.arc(cx, cy, rad, 0, Math.PI * 2);
			ctx.arc(cx, cy, rad * 0.56, Math.PI * 2, 0, true);
			ctx.closePath(); ctx.fillStyle = '#f1f5f9'; ctx.fill();
		} else {
			segs.forEach(function (s) {
				if (!s.v) return;
				var sw = (s.v / total) * Math.PI * 2;
				ctx.beginPath();
				ctx.arc(cx, cy, rad, start, start + sw);
				ctx.arc(cx, cy, rad * 0.56, start + sw, start, true);
				ctx.closePath(); ctx.fillStyle = s.c; ctx.fill();
				start += sw;
			});
		}

		// Hole
		ctx.beginPath(); ctx.arc(cx, cy, rad * 0.56, 0, Math.PI * 2);
		ctx.fillStyle = C.surface; ctx.fill();

		// Centre label
		ctx.fillStyle = C.text;
		ctx.font = 'bold ' + Math.floor(rad * 0.44) + 'px "DM Mono","Courier New",monospace';
		ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
		ctx.fillText(total || 0, cx, cy - 5);
		ctx.font = Math.floor(rad * 0.18) + 'px system-ui';
		ctx.fillStyle = C.muted;
		ctx.fillText('total', cx, cy + rad * 0.24);

		// Build legend HTML
		if (legendId) {
			var leg = root.querySelector('#' + legendId);
			if (leg && segs.length) {
				var lhtml = '';
				segs.forEach(function (s) {
					var pct = total > 0 ? (s.v / total * 100).toFixed(1) : '0.0';
					lhtml += '<div class="mtm-drow">' +
						'<div class="mtm-ddot" style="background:' + s.c + '"></div>' +
						'<div class="mtm-dlbl">' + s.label + '</div>' +
						'<div class="mtm-dval">' + s.v + '</div>' +
						'<div class="mtm-dpct">' + pct + '%</div>' +
						'</div>';
				});
				leg.innerHTML = lhtml;
			}
		}
	}

	function drawThroughput(id, data) {
		var r = ic(id);
		if (!r) return;
		var ctx = r.ctx, w = r.w, h = r.h;
		var pl = { l: 42, r: 10, t: 22, b: 26 };
		var cw = w - pl.l - pl.r, ch = h - pl.t - pl.b;
		var n = data.length;
		if (!n) { ctx.fillStyle = C.muted; ctx.font = '11px system-ui'; ctx.textAlign = 'center'; ctx.fillText('No data', w/2, h/2); return; }
		var mx = 0;
		data.forEach(function (d) { if (parseFloat(d.planned) > mx) mx = parseFloat(d.planned); });
		mx = mx * 1.15 || 10;
		var colW = cw / n, bw = colW * 0.54;

		for (var i = 0; i <= 4; i++) {
			var y = pl.t + ch * (1 - i / 4);
			ctx.beginPath(); ctx.strokeStyle = C.border; ctx.lineWidth = 1;
			ctx.moveTo(pl.l, y); ctx.lineTo(pl.l + cw, y); ctx.stroke();
			ctx.fillStyle = C.muted; ctx.font = '9px "Courier New"';
			ctx.textAlign = 'right';
			ctx.fillText(Math.round(mx * i / 4), pl.l - 4, y + 3);
		}

		data.forEach(function (d, i) {
			var x = pl.l + colW * i + (colW - bw) / 2;
			var pH  = (parseFloat(d.planned)  / mx) * ch;
			var prH = (parseFloat(d.produced) / mx) * ch;
			ctx.fillStyle = C.planned;
			ctx.fillRect(x, pl.t + ch - pH, bw, pH);
			ctx.fillStyle = C.emerald;
			ctx.fillRect(x, pl.t + ch - prH, bw, prH);
			// Date label
			var dtLabel = String(d.dt || '').slice(5); // MM-DD
			ctx.fillStyle = C.muted; ctx.font = '9px system-ui';
			ctx.textAlign = 'center';
			ctx.fillText(dtLabel, pl.l + colW * (i + 0.5), h - 6);
			// Completion %
			var pct = parseFloat(d.planned) > 0 ? Math.round(parseFloat(d.produced) / parseFloat(d.planned) * 100) : 0;
			ctx.fillStyle = pct >= 90 ? C.emerald : pct >= 70 ? C.amber : C.rose;
			ctx.font = 'bold 9px "Courier New"';
			ctx.fillText(pct + '%', pl.l + colW * (i + 0.5), pl.t + ch - pH - 5);
		});
	}

	function drawEmployees(id, data) {
		var r = ic(id);
		if (!r) return;
		var ctx = r.ctx, w = r.w, h = r.h;
		var pl = { l: 48, r: 10, t: 22, b: 28 };
		var cw = w - pl.l - pl.r, ch = h - pl.t - pl.b;
		var n = data.length;
		if (!n) { ctx.fillStyle = C.muted; ctx.font = '11px system-ui'; ctx.textAlign = 'center'; ctx.fillText('No data', w/2, h/2); return; }
		var mx = 0;
		data.forEach(function (d) { if (parseFloat(d.qty_per_hour) > mx) mx = parseFloat(d.qty_per_hour); });
		mx = mx * 1.15 || 10;
		var colW = cw / n, bw = colW * 0.52;

		ctx.save();
		ctx.translate(12, pl.t + ch / 2); ctx.rotate(-Math.PI / 2);
		ctx.fillStyle = C.muted; ctx.font = '9px system-ui';
		ctx.textAlign = 'center'; ctx.fillText('Units / Hour', 0, 0);
		ctx.restore();

		for (var i = 0; i <= 4; i++) {
			var y = pl.t + ch * (1 - i / 4);
			ctx.beginPath(); ctx.strokeStyle = C.border; ctx.lineWidth = 1;
			ctx.moveTo(pl.l, y); ctx.lineTo(pl.l + cw, y); ctx.stroke();
			ctx.fillStyle = C.muted; ctx.font = '9px "Courier New"';
			ctx.textAlign = 'right';
			ctx.fillText(Math.round(mx * i / 4), pl.l - 4, y + 3);
		}

		data.forEach(function (d, i) {
			var x = pl.l + colW * i + (colW - bw) / 2;
			var qph = parseFloat(d.qty_per_hour || 0);
			var bh = (qph / mx) * ch;
			var ratio = qph / mx;
			ctx.fillStyle = ratio > 0.7 ? C.emerald : ratio > 0.4 ? C.amber : '#94a3b8';
			ctx.fillRect(x, pl.t + ch - bh, bw, bh);
			ctx.fillStyle = C.text; ctx.font = 'bold 9px "Courier New"';
			ctx.textAlign = 'center';
			ctx.fillText(qph.toFixed(1), pl.l + colW * (i + 0.5), pl.t + ch - bh - 5);
			// Label: first name from employee_name, fall back to employee id
			var fullName = String(d.employee_name || d.employee || '');
			var nameParts = fullName.trim().split(/\s+/);
			var lbl = nameParts[0] ? nameParts[0].slice(0, 11) : fullName.slice(0, 11);
			ctx.fillStyle = C.muted; ctx.font = '8px system-ui';
			ctx.fillText(lbl, pl.l + colW * (i + 0.5), h - 7);
		});
	}

	function drawAllCharts(d) {
		// WO Status donut — always show all 3 statuses
		var WO_ORDER  = ['Not Started', 'In Process', 'Completed', 'Stopped'];
		var WO_COLORS = { 'Not Started':'#94a3b8', 'In Process':'#d97706', 'Completed':'#059669', 'Stopped':'#e11d48' };
		var woCounts  = {};
		(d.wo_status || []).forEach(function (s) { woCounts[s.status] = parseInt(s.cnt || 0); });
		var woTotal = 0;
		var woSegs  = WO_ORDER.map(function (status) {
			var v = woCounts[status] || 0;
			woTotal += v;
			return { v: v, c: WO_COLORS[status], label: status };
		});
		drawDonut('mtm-wo-donut', woSegs, woTotal, 'mtm-wo-leg');

		// JC Status donut — always show all statuses
		var JC_ORDER  = ['Open', 'Work In Progress', 'Completed', 'On Hold'];
		var JC_COLORS = { 'Open':'#2563eb', 'Work In Progress':'#d97706', 'Completed':'#059669', 'On Hold':'#94a3b8' };
		var jcCounts  = {};
		(d.jc_status || []).forEach(function (s) { jcCounts[s.status] = parseInt(s.cnt || 0); });
		var jcTotal = 0;
		var jcSegs  = JC_ORDER.map(function (status) {
			var v = jcCounts[status] || 0;
			jcTotal += v;
			return { v: v, c: JC_COLORS[status], label: status };
		});
		drawDonut('mtm-jc-donut', jcSegs, jcTotal, 'mtm-jc-leg');

		// Throughput trend
		drawThroughput('mtm-throughput', d.throughput || []);

		// Employee productivity
		drawEmployees('mtm-emp-prod', d.employees || []);
	}

	// ── HTML template ─────────────────────────────────────────────────────
	function getMtmDashHTML() {
		return `
<div class="mtm-dash">

  <!-- HEADER -->
  <div class="mtm-header">
    <div>
      <div class="mtm-brand-over">Masters Touch Manufacturing</div>
      <div class="mtm-brand-name">Manufacturing at a Glance</div>
      <div class="mtm-brand-sub">Production Intelligence &nbsp;·&nbsp; ERPNext v15</div>
    </div>
    <div class="mtm-hdr-right">
      <div class="mtm-hdr-period" id="mtm-period-label">—</div>
      <div><span class="mtm-live-badge">● LIVE</span></div>
    </div>
  </div>

  <!-- FILTER BAR -->
  <div class="mtm-fbar">
    <div class="mtm-fg">
      <div class="mtm-flbl">Date Preset</div>
      <select id="mtm-preset" class="mtm-fsel">
        <option value="all" selected>All Time</option>
        <option value="7">Last 7 Days</option>
        <option value="30">Last 30 Days</option>
        <option value="90">Last 90 Days</option>
      </select>
    </div>
    <div class="mtm-fg">
      <div class="mtm-flbl">From Date</div>
      <input type="date" id="mtm-from-date" class="mtm-finp">
    </div>
    <div class="mtm-fg">
      <div class="mtm-flbl">To Date</div>
      <input type="date" id="mtm-to-date" class="mtm-finp">
    </div>
    <div class="mtm-fspacer"></div>
    <div class="mtm-lrefresh" id="mtm-last-refresh">—</div>
    <button id="mtm-refresh-btn" class="mtm-ebtn pri">&#8635; Refresh</button>
  </div>

  <!-- KPI GRID -->
  <div class="mtm-kpi-grid">
    <div class="mtm-kc" style="--kc:#2563eb">
      <div class="mtm-kc-accent"></div>
      <div class="mtm-kc-top"><span class="mtm-kico">📋</span><span class="mtm-klbl">Planned Input</span></div>
      <div class="mtm-kval" id="mtm-kv-planned"><span class="mtm-loader"></span></div>
      <div class="mtm-ksub" id="mtm-ks-planned">—</div>
    </div>
    <div class="mtm-kc" style="--kc:#059669">
      <div class="mtm-kc-accent"></div>
      <div class="mtm-kc-top"><span class="mtm-kico">✅</span><span class="mtm-klbl">Produced Yield</span></div>
      <div class="mtm-kval" id="mtm-kv-produced"><span class="mtm-loader"></span></div>
      <div class="mtm-ksub" id="mtm-ks-produced">—</div>
    </div>
    <div class="mtm-kc" style="--kc:#d97706">
      <div class="mtm-kc-accent"></div>
      <div class="mtm-kc-top"><span class="mtm-kico">⏳</span><span class="mtm-klbl">Remaining</span></div>
      <div class="mtm-kval" id="mtm-kv-remaining"><span class="mtm-loader"></span></div>
      <div class="mtm-ksub" id="mtm-ks-remaining">—</div>
    </div>
    <div class="mtm-kc" style="--kc:#e11d48">
      <div class="mtm-kc-accent"></div>
      <div class="mtm-kc-top"><span class="mtm-kico">⚠️</span><span class="mtm-klbl">Process Loss</span></div>
      <div class="mtm-kval" id="mtm-kv-loss"><span class="mtm-loader"></span></div>
      <div class="mtm-ksub" id="mtm-ks-loss">—</div>
    </div>
    <div class="mtm-kc" style="--kc:#94a3b8">
      <div class="mtm-kc-accent"></div>
      <div class="mtm-kc-top"><span class="mtm-kico">📑</span><span class="mtm-klbl">Job Cards</span></div>
      <div class="mtm-kval" id="mtm-kv-jccount"><span class="mtm-loader"></span></div>
      <div class="mtm-ksub" id="mtm-ks-jccount">—</div>
    </div>
    <div class="mtm-kc" style="--kc:#94a3b8">
      <div class="mtm-kc-accent"></div>
      <div class="mtm-kc-top"><span class="mtm-kico">👥</span><span class="mtm-klbl">Employees</span></div>
      <div class="mtm-kval" id="mtm-kv-employees"><span class="mtm-loader"></span></div>
      <div class="mtm-ksub" id="mtm-ks-employees">—</div>
    </div>
    <div class="mtm-kc" style="--kc:#059669">
      <div class="mtm-kc-accent"></div>
      <div class="mtm-kc-top"><span class="mtm-kico">⚡</span><span class="mtm-klbl">Qty / Hour</span></div>
      <div class="mtm-kval" id="mtm-kv-qph"><span class="mtm-loader"></span></div>
      <div class="mtm-ksub" id="mtm-ks-qph">—</div>
    </div>
    <div class="mtm-kc" style="--kc:#d97706">
      <div class="mtm-kc-accent"></div>
      <div class="mtm-kc-top"><span class="mtm-kico">📊</span><span class="mtm-klbl">OEE / Cost</span></div>
      <div class="mtm-kval" id="mtm-kv-oee"><span class="mtm-loader"></span></div>
      <div class="mtm-ksub" id="mtm-ks-oee">—</div>
    </div>
  </div>

  <!-- CHART ROW 1 -->
  <div class="mtm-crow1">
    <div class="mtm-panel">
      <div class="mtm-ptitle">Work Orders by Status</div>
      <div class="mtm-psub">Planned Qty Distribution</div>
      <div class="mtm-dwrap">
        <canvas id="mtm-wo-donut" class="mtm-donut" width="155" height="155"></canvas>
        <div class="mtm-dleg" id="mtm-wo-leg"></div>
      </div>
    </div>
    <div class="mtm-panel">
      <div class="mtm-ptitle">Job Cards by Status</div>
      <div class="mtm-psub">Count Distribution</div>
      <div class="mtm-dwrap">
        <canvas id="mtm-jc-donut" class="mtm-donut" width="155" height="155"></canvas>
        <div class="mtm-dleg" id="mtm-jc-leg"></div>
      </div>
    </div>
    <div class="mtm-panel">
      <div class="mtm-ptitle">Throughput Trend</div>
      <div class="mtm-psub">Planned vs Produced · Completion % per day</div>
      <canvas id="mtm-throughput" class="mtm-cchart"></canvas>
      <div class="mtm-chart-legend">
        <span><span class="mtm-leg-dot" style="background:#bfdbfe"></span>Planned</span>
        <span><span class="mtm-leg-dot" style="background:#059669"></span>Produced</span>
        <span>% above each column</span>
      </div>
    </div>
  </div>

  <!-- CHART ROW 2 -->
  <div class="mtm-crow2">
    <div class="mtm-panel">
      <div class="mtm-ptitle">Micron Quality Ladder</div>
      <div class="mtm-psub">Grams collected per micron size this period</div>
      <div id="mtm-micron-ladder"><div class="mtm-empty">Loading…</div></div>
    </div>
    <div class="mtm-panel">
      <div class="mtm-ptitle">Employee Productivity</div>
      <div class="mtm-psub">Qty/Hour by employee (weighted from time logs)</div>
      <canvas id="mtm-emp-prod" class="mtm-bchart"></canvas>
    </div>
  </div>

  <!-- WORK ORDERS TABLE -->
  <div class="mtm-wosec">
    <div class="mtm-sec-hdr">Work Orders</div>
    <div class="mtm-wohdr">
      <span class="mtm-wotitle">Active &amp; Recent — Current Period</span>
      <span class="mtm-wohint" id="mtm-wo-rows">—</span>
    </div>
    <div class="mtm-tscroll">
      <table class="mtm-wot">
        <thead>
          <tr>
            <th>Planned Start</th><th>Planned End</th><th>Work Order</th>
            <th>Item / Strain</th><th>Qty (g)</th><th>Produced (g)</th>
            <th>Remaining (g)</th><th>Completion</th><th>Status</th>
          </tr>
        </thead>
        <tbody id="mtm-wo-tbody">
          <tr><td colspan="9" class="mtm-empty">Loading…</td></tr>
        </tbody>
      </table>
    </div>
  </div>


</div>`;
	}
};
