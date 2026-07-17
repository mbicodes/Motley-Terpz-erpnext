frappe.pages['mbi-dashboard'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'MBI Dashboard',
		single_column: true
	});
	init_mbi(page, wrapper);
};

function init_mbi(page, wrapper) {
	var $main = $(wrapper).find('.layout-main-section');
	$main.addClass('mbi-dash');
	$main.html(get_mbi_html());

	var root = $main[0];
	var state = { companies: 'both' };

	wire_company_toggle(root, state, page);
	wire_section_collapse(root);
	wire_tabs(root);
	wire_trigger_report(root);
	load_all(root, state);

	root.querySelector('#mbi-refresh-btn').addEventListener('click', function() {
		load_all(root, state);
	});
}

/* ─── HTML skeleton ─────────────────────────────────────────────────────── */
function get_mbi_html() {
	return `
<div class="mbi-header">
  <div class="mbi-title-wrap">
    <div class="mbi-live-dot"></div>
    <div>
      <h1 class="mbi-title">MBI Dashboard</h1>
      <div class="mbi-subtitle" id="mbi-last-refresh">Loading…</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
    <div class="mbi-co-toggle">
      <button class="mbi-co-btn tsbc" data-co="tsbc">TSBC Ranch</button>
      <button class="mbi-co-btn mtm"  data-co="mtm">MTM</button>
      <button class="mbi-co-btn both active" data-co="both">Both</button>
    </div>
    <button class="mbi-export-btn" id="mbi-refresh-btn">
      <svg class="mbi-section-icon" viewBox="0 0 24 24"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.81"/></svg>
      Refresh
    </button>
  </div>
</div>

<div class="mbi-section" id="mbi-sec-trigger">
  <div class="mbi-section-header" data-sec="trigger">
    <span class="mbi-section-title">
      <svg class="mbi-section-icon" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
      Trigger Report
    </span>
    <svg class="mbi-chevron" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
  </div>
  <div class="mbi-section-body" id="trigger-body">
    <div class="mbi-trigger-row">
      <button class="mbi-trigger-btn blue" data-target="mbi">
        <span class="mbi-trigger-icon">
          <svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </span>
        <span class="mbi-trigger-text">
          <span class="mbi-trigger-label">Send Report to MBI</span>
          <span class="mbi-trigger-emails">mbi@alltechvirtual.com</span>
        </span>
        <span class="mbi-trigger-arrow">
          <svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
        </span>
      </button>
      <button class="mbi-trigger-btn violet" data-target="team">
        <span class="mbi-trigger-icon">
          <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        </span>
        <span class="mbi-trigger-text">
          <span class="mbi-trigger-label">Send Report to Nikki, Matt &amp; Imran</span>
          <span class="mbi-trigger-emails">nikki@motleyterpz.com &middot; matt@motleyterpz.com &middot; imran@motleyterpz.com</span>
        </span>
        <span class="mbi-trigger-arrow">
          <svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
        </span>
      </button>
    </div>
    <div class="mbi-trigger-note">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
      Emails the Weekly Sale Report for the current week with the detailed PDF attached.
    </div>
  </div>
</div>

${mbi_section('kpis','kpis-body','Summary KPIs',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>`,
  '', false)}

${mbi_section('logistics','logistics-body','Logistics Circuit',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  '<span class="mbi-section-badge" id="mbi-pending-badge">…</span>', false)}

${mbi_section('docs','docs-body','Sales Documents',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`,
  '', true)}

${mbi_section('gaps','gaps-body','Gap Lists',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>`,
  '<span class="mbi-section-badge red" id="mbi-gap-badge">…</span>', false)}

${mbi_section('payments','payments-body','Invoices &amp; Payments',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`,
  '', false)}

${mbi_section('cashbank','cashbank-body','Cash &amp; Bank Payments',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>`,
  '', false)}

${mbi_section('conversion','conversion-body','Conversion Overview',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>`,
  '', false)}

${mbi_section('itemgroups','itemgroups-body','Item Group Totals',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
  '', false)}

${mbi_section('igconv','igconv-body','Item Group Conversion',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>`,
  '', false)}

${mbi_section('hardware','hardware-body','Hardware Counts',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/></svg>`,
  '', false)}

${mbi_section('tolling','tolling-body','Tolling Check (MTM)',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><path d="M14.5 10c-.83 0-1.5-.67-1.5-1.5v-5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5z"/><path d="M20.5 10H19V8.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/><path d="M9.5 14c.83 0 1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5S8 21.33 8 20.5v-5c0-.83.67-1.5 1.5-1.5z"/><path d="M3.5 14H5v1.5c0 .83-.67 1.5-1.5 1.5S2 16.33 2 15.5 2.67 14 3.5 14z"/><path d="M14 14.5c0-.83.67-1.5 1.5-1.5h5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-5c-.83 0-1.5-.67-1.5-1.5z"/><path d="M15.5 19H14v1.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5-.67-1.5-1.5-1.5z"/><path d="M10 9.5C10 8.67 9.33 8 8.5 8h-5C2.67 8 2 8.67 2 9.5S2.67 11 3.5 11h5c.83 0 1.5-.67 1.5-1.5z"/><path d="M8.5 5H10V3.5C10 2.67 9.33 2 8.5 2S7 2.67 7 3.5 7.67 5 8.5 5z"/></svg>`,
  '<span class="mbi-section-badge amber" id="mbi-tolling-badge">…</span>', false)}

${mbi_section('arap','arap-body','AR &amp; AP Summary',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>`,
  '', false)}

${mbi_section('salestype','salestype-body','Sales by Order Type',
  `<svg class="mbi-section-icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="8 12 12 16 16 12"/><line x1="12" y1="8" x2="12" y2="16"/></svg>`,
  '', false)}
`;
}

function mbi_section(id, body_id, title, icon_svg, badge_html, collapsed) {
	return `
<div class="mbi-section${collapsed ? ' collapsed' : ''}" id="mbi-sec-${id}">
  <div class="mbi-section-header" data-sec="${id}">
    <span class="mbi-section-title">${icon_svg}${title}${badge_html ? ' ' + badge_html : ''}</span>
    <svg class="mbi-chevron" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
  </div>
  <div class="mbi-section-body" id="${body_id}">
    <div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>
  </div>
</div>`;
}

/* ─── Trigger report buttons ────────────────────────────────────────────── */
var TRIGGER_TARGET_LABELS = {
	'mbi':  'mbi@alltechvirtual.com',
	'team': 'nikki@motleyterpz.com, matt@motleyterpz.com, imran@motleyterpz.com'
};

function wire_trigger_report(root) {
	root.querySelectorAll('.mbi-trigger-btn').forEach(function(btn) {
		btn.addEventListener('click', function() {
			var target = btn.dataset.target;
			var emails = TRIGGER_TARGET_LABELS[target] || target;
			frappe.confirm(
				__('Send the Weekly Sale Report to <b>{0}</b>?', [frappe.utils.escape_html(emails)]),
				function() {
					var label = btn.querySelector('.mbi-trigger-label');
					var orig = label ? label.textContent : '';
					btn.disabled = true;
					btn.classList.add('sending');
					if (label) label.textContent = __('Sending…');
					frappe.call({
						method: 'cannabis_management.api.weekly_report.trigger_report',
						args: { target: target },
						callback: function() {
							frappe.show_alert({message: __('Report sent to {0}', [frappe.utils.escape_html(emails)]), indicator: 'green'});
						},
						error: function() {
							frappe.show_alert({message: __('Failed to send report'), indicator: 'red'});
						},
						always: function() {
							btn.disabled = false;
							btn.classList.remove('sending');
							if (label) label.textContent = orig;
						}
					});
				}
			);
		});
	});
}

/* ─── Collapse / expand ─────────────────────────────────────────────────── */
function wire_section_collapse(root) {
	root.querySelectorAll('.mbi-section-header').forEach(function(hdr) {
		hdr.addEventListener('click', function() {
			var sec = hdr.closest('.mbi-section');
			sec.classList.toggle('collapsed');
		});
	});
}

/* ─── Company toggle ────────────────────────────────────────────────────── */
function wire_company_toggle(root, state, page) {
	root.querySelectorAll('.mbi-co-btn').forEach(function(btn) {
		btn.addEventListener('click', function() {
			root.querySelectorAll('.mbi-co-btn').forEach(function(b) { b.classList.remove('active'); });
			btn.classList.add('active');
			state.companies = btn.dataset.co;
			load_all(root, state);
		});
	});
}

/* ─── Tabs ──────────────────────────────────────────────────────────────── */
function wire_tabs(root) {
	root.querySelectorAll('.mbi-tab').forEach(function(tab) {
		tab.addEventListener('click', function() {
			var container = tab.closest('.mbi-tabs-wrap') || tab.parentElement.closest('.mbi-section-body') || tab.parentElement;
			var group = tab.dataset.group;
			var panel_id = tab.dataset.panel;
			container.querySelectorAll('.mbi-tab[data-group="' + group + '"]').forEach(function(t) { t.classList.remove('active'); });
			container.querySelectorAll('.mbi-tab-panel[data-group="' + group + '"]').forEach(function(p) { p.classList.remove('active'); });
			tab.classList.add('active');
			var panel = container.querySelector('#' + panel_id);
			if (panel) panel.classList.add('active');
		});
	});
}

/* ─── Load all sections ─────────────────────────────────────────────────── */
function get_companies_arg(state) {
	if (state.companies === 'tsbc') return ['TSBC Ranch'];
	if (state.companies === 'mtm')  return ['Master Touch Manufacturing'];
	return ['TSBC Ranch', 'Master Touch Manufacturing', 'Motley Terpz'];
}

function load_all(root, state) {
	var co = get_companies_arg(state);
	var ts = new Date().toLocaleTimeString();
	var subtitle = root.querySelector('#mbi-last-refresh');
	if (subtitle) subtitle.textContent = 'Last refresh: ' + ts;

	load_kpis(root, co);
	load_logistics(root, co);
	load_docs(root, co);
	load_gaps(root, co);
	load_payments(root, co);
	load_cashbank(root, co);
	load_conversion(root, co);
	load_item_groups(root, co);
	load_ig_conversion(root, co);
	load_hardware(root, co);
	load_tolling(root);
	load_arap(root, co);
	load_sales_type(root, co);
}

function api(method, args, cb) {
	frappe.call({
		method: 'cannabis_management.api.mbi.' + method,
		args: args,
		callback: function(r) { cb(r.message || {}); },
		error: function() { cb(null); }
	});
}

function fmt_currency(v) {
	if (v === null || v === undefined) return '—';
	return '$' + parseFloat(v).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}
function fmt_num(v) {
	if (v === null || v === undefined) return '—';
	return parseFloat(v).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
}
function mbi_link(doctype, name) {
	if (!name) return '—';
	var url = '/app/' + frappe.router.slug(doctype) + '/' + encodeURIComponent(name);
	return '<a class="mbi-link" href="' + url + '" target="_blank">' + frappe.utils.escape_html(name) + '</a>';
}
function status_badge(status) {
	if (!status) return '<span class="mbi-badge mbi-badge-muted">—</span>';
	var s = status.toLowerCase();
	var cls = 'mbi-badge-muted';
	if (s === 'paid' || s === 'closed out') cls = 'mbi-badge-green';
	else if (s === 'unpaid' || s === 'need to schedule') cls = 'mbi-badge-red';
	else if (s === 'overdue' || s === 'shortage') cls = 'mbi-badge-red';
	else if (s === 'partially paid') cls = 'mbi-badge-amber';
	else if (s === 'draft') cls = 'mbi-badge-muted';
	else if (s === 'submitted' || s === 'to bill' || s === 'to deliver') cls = 'mbi-badge-blue';
	else if (s === 'scheduled' || s === 'prepared') cls = 'mbi-badge-violet';
	else if (s === 'preparing' || s === 'staged') cls = 'mbi-badge-amber';
	return '<span class="mbi-badge ' + cls + '">' + frappe.utils.escape_html(status) + '</span>';
}

/* ─── 1. KPIs ───────────────────────────────────────────────────────────── */
function load_kpis(root, co) {
	var body = root.querySelector('#kpis-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_summary_kpis', {companies: JSON.stringify(co)}, function(d) {
		if (!d) { body.innerHTML = '<div class="mbi-empty">Failed to load</div>'; return; }
		var kpis = [
			{label:'Open SOs', value: fmt_num(d.open_so_count), sub: fmt_currency(d.open_so_value), color:'#2563eb'},
			{label:'Draft SIs', value: fmt_num(d.draft_si_count), sub: fmt_currency(d.draft_si_value), color:'#d97706'},
			{label:'AR Balance', value: fmt_currency(d.ar_balance), sub: 'Receivable', color:'#059669'},
			{label:'AP Balance', value: fmt_currency(d.ap_balance), sub: 'Payable', color:'#e11d48'},
			{label:'SO → No DN', value: fmt_num(d.so_no_dn_count), sub: 'Not Delivered', color:'#7c3aed'},
			{label:'SO → No SI', value: fmt_num(d.so_no_si_count), sub: 'Not Invoiced', color:'#0891b2'},
			{label:'SO → Gap', value: fmt_num(d.so_no_both_count), sub: 'No DN & No SI', color:'#ea580c'},
		];
		var html = '<div class="mbi-kpi-row">';
		kpis.forEach(function(k) {
			html += '<div class="mbi-kpi" style="--mbi-kpi-color:' + k.color + '">' +
				'<div class="mbi-kpi-bar"></div>' +
				'<div class="mbi-kpi-label">' + k.label + '</div>' +
				'<div class="mbi-kpi-value">' + k.value + '</div>' +
				'<div class="mbi-kpi-sub">' + k.sub + '</div>' +
			'</div>';
		});
		html += '</div>';
		body.innerHTML = html;
	});
}

/* ─── 2. Logistics circuit ──────────────────────────────────────────────── */
var STAGE_COLORS = ['#94a3b8','#2563eb','#d97706','#7c3aed','#0891b2','#059669','#1e293b'];
var STAGES = ['Need to Schedule','Scheduled','Preparing','Prepared','Staged','Closed Out'];
var CO_COLORS = {'TSBC Ranch': '#059669', 'Master Touch Manufacturing': '#7c3aed', 'Motley Terpz': '#d97706'};

function load_logistics(root, co) {
	var body = root.querySelector('#logistics-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_logistics_circuit', {companies: JSON.stringify(co)}, function(d) {
		if (!d) { body.innerHTML = '<div class="mbi-empty">Failed to load</div>'; return; }

		var total_pending = 0;
		Object.keys(d).forEach(function(c) { total_pending += (d[c].pending_so_count || 0); });
		var badge = root.querySelector('#mbi-pending-badge');
		if (badge) badge.textContent = fmt_num(total_pending) + ' pending';

		var html = '<div class="mbi-circuit">';
		Object.keys(d).forEach(function(company) {
			var data = d[company];
			var co_color = CO_COLORS[company] || '#2563eb';
			html += '<div style="padding:12px 18px 4px 18px;font-size:11px;font-weight:700;' +
				'color:' + co_color + ';text-transform:uppercase;letter-spacing:0.07em;">' +
				frappe.utils.escape_html(company) + '</div>';
			html += '<div class="mbi-circuit-track" style="margin-bottom:14px;">';

			html += mbi_stage(STAGE_COLORS[0], fmt_num(data.pending_so_count), 'Pending');
			STAGES.forEach(function(stage, i) {
				var key = stage.toLowerCase().replace(/ /g,'_') + '_count';
				html += mbi_stage(STAGE_COLORS[i + 1], fmt_num(data[key] || 0), stage);
			});
			html += '</div>';
		});
		html += '</div>';
		body.innerHTML = html;
	});
}

function mbi_stage(color, num, label) {
	return '<div class="mbi-stage" style="--stage-color:' + color + '">' +
		'<div class="mbi-stage-bar"></div>' +
		'<div class="mbi-stage-num">' + num + '</div>' +
		'<div class="mbi-stage-label">' + frappe.utils.escape_html(label) + '</div>' +
		'<div class="mbi-stage-arrow"></div></div>';
}

/* ─── 3. Sales documents ────────────────────────────────────────────────── */
function load_docs(root, co) {
	var body = root.querySelector('#docs-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';

	var loaded = {so: null, si: null, dn: null};
	function try_render() {
		if (loaded.so === null || loaded.si === null || loaded.dn === null) return;
		render_docs(body, loaded);
	}

	api('get_sales_orders', {companies: JSON.stringify(co), limit: 100}, function(d) {
		loaded.so = d || [];
		try_render();
	});
	api('get_sales_invoices', {companies: JSON.stringify(co), limit: 100}, function(d) {
		loaded.si = d || [];
		try_render();
	});
	api('get_delivery_notes', {companies: JSON.stringify(co), limit: 100}, function(d) {
		loaded.dn = d || [];
		try_render();
	});
}

function render_docs(body, data) {
	var html = '<div>' +
		'<div style="display:flex;border-bottom:1px solid var(--sd-border);">' +
		tab_btn('docs','tab-so','Sales Orders (' + data.so.length + ')','tab-so',true) +
		tab_btn('docs','tab-si','Sales Invoices (' + data.si.length + ')','tab-si',false) +
		tab_btn('docs','tab-dn','Delivery Notes (' + data.dn.length + ')','tab-dn',false) +
		'</div>' +
		'<div id="tab-so" class="mbi-tab-panel active" data-group="docs">' + render_so_table(data.so) + '</div>' +
		'<div id="tab-si" class="mbi-tab-panel" data-group="docs">' + render_si_table(data.si) + '</div>' +
		'<div id="tab-dn" class="mbi-tab-panel" data-group="docs">' + render_dn_table(data.dn) + '</div>' +
	'</div>';
	body.innerHTML = html;
	wire_tab_group(body, 'docs');
}

function tab_btn(group, panel, label, id, active) {
	return '<div class="mbi-tab' + (active ? ' active' : '') + '" data-group="' + group + '" data-panel="' + panel + '">' + label + '</div>';
}

function wire_tab_group(container, group) {
	container.querySelectorAll('.mbi-tab[data-group="' + group + '"]').forEach(function(tab) {
		tab.addEventListener('click', function() {
			container.querySelectorAll('.mbi-tab[data-group="' + group + '"]').forEach(function(t) { t.classList.remove('active'); });
			container.querySelectorAll('.mbi-tab-panel[data-group="' + group + '"]').forEach(function(p) { p.classList.remove('active'); });
			tab.classList.add('active');
			var panel = container.querySelector('#' + tab.dataset.panel);
			if (panel) panel.classList.add('active');
		});
	});
}

function render_so_table(rows) {
	if (!rows || !rows.length) return '<div class="mbi-empty">No sales orders found</div>';
	var html = '<div class="mbi-tbl-wrap"><table class="mbi-tbl">' +
		'<thead><tr>' +
		'<th>SO #</th><th>Date</th><th>Customer</th><th>Company</th><th>Order Type</th>' +
		'<th class="r">Grand Total</th><th>Status</th><th>Logistics</th>' +
		'</tr></thead><tbody>';
	rows.forEach(function(r) {
		html += '<tr>' +
			'<td>' + mbi_link('Sales Order', r.name) + '</td>' +
			'<td class="muted">' + (r.transaction_date || '') + '</td>' +
			'<td>' + frappe.utils.escape_html(r.customer_name || '') + '</td>' +
			'<td class="muted">' + frappe.utils.escape_html(r.company || '') + '</td>' +
			'<td class="muted">' + frappe.utils.escape_html(r.order_type || '') + '</td>' +
			'<td class="r">' + fmt_currency(r.grand_total) + '</td>' +
			'<td>' + status_badge(r.status) + '</td>' +
			'<td>' + status_badge(r.logistics_status) + '</td>' +
		'</tr>';
	});
	html += '</tbody></table></div>';
	return html;
}

function render_si_table(rows) {
	if (!rows || !rows.length) return '<div class="mbi-empty">No sales invoices found</div>';
	var html = '<div class="mbi-tbl-wrap"><table class="mbi-tbl">' +
		'<thead><tr>' +
		'<th>SI #</th><th>Date</th><th>Customer</th><th>Company</th>' +
		'<th class="r">Grand Total</th><th class="r">Paid</th><th class="r">Outstanding</th><th>Status</th>' +
		'</tr></thead><tbody>';
	rows.forEach(function(r) {
		html += '<tr>' +
			'<td>' + mbi_link('Sales Invoice', r.name) + '</td>' +
			'<td class="muted">' + (r.posting_date || '') + '</td>' +
			'<td>' + frappe.utils.escape_html(r.customer_name || '') + '</td>' +
			'<td class="muted">' + frappe.utils.escape_html(r.company || '') + '</td>' +
			'<td class="r">' + fmt_currency(r.grand_total) + '</td>' +
			'<td class="r">' + fmt_currency(r.paid_amount) + '</td>' +
			'<td class="r">' + fmt_currency(r.outstanding_amount) + '</td>' +
			'<td>' + status_badge(r.status) + '</td>' +
		'</tr>';
	});
	html += '</tbody></table></div>';
	return html;
}

function render_dn_table(rows) {
	if (!rows || !rows.length) return '<div class="mbi-empty">No delivery notes found</div>';
	var html = '<div class="mbi-tbl-wrap"><table class="mbi-tbl">' +
		'<thead><tr>' +
		'<th>DN #</th><th>Date</th><th>Customer</th><th>Company</th>' +
		'<th class="r">Grand Total</th><th>Status</th><th>Against SO</th>' +
		'</tr></thead><tbody>';
	rows.forEach(function(r) {
		html += '<tr>' +
			'<td>' + mbi_link('Delivery Note', r.name) + '</td>' +
			'<td class="muted">' + (r.posting_date || '') + '</td>' +
			'<td>' + frappe.utils.escape_html(r.customer_name || '') + '</td>' +
			'<td class="muted">' + frappe.utils.escape_html(r.company || '') + '</td>' +
			'<td class="r">' + fmt_currency(r.grand_total) + '</td>' +
			'<td>' + status_badge(r.status) + '</td>' +
			'<td class="muted">' + frappe.utils.escape_html(r.against_sales_order || '') + '</td>' +
		'</tr>';
	});
	html += '</tbody></table></div>';
	return html;
}

/* ─── 4. Gap lists ──────────────────────────────────────────────────────── */
function load_gaps(root, co) {
	var body = root.querySelector('#gaps-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_gap_lists', {companies: JSON.stringify(co)}, function(d) {
		if (!d) { body.innerHTML = '<div class="mbi-empty">Failed to load</div>'; return; }
		var total = (d.no_dn ? d.no_dn.length : 0) + (d.no_si ? d.no_si.length : 0) + (d.no_both ? d.no_both.length : 0);
		var badge = root.querySelector('#mbi-gap-badge');
		if (badge) badge.textContent = total + ' gaps';

		function gap_col(title, rows, color) {
			var count = rows ? rows.length : 0;
			var html = '<div class="mbi-gap-col">' +
				'<div class="mbi-gap-col-header">' +
				'<span>' + title + '</span>' +
				'<span class="mbi-badge mbi-badge-red">' + count + '</span>' +
			'</div><div class="mbi-gap-col-body">' +
			'<table class="mbi-tbl" style="min-width:0;">' +
			'<thead><tr><th>SO #</th><th>Customer</th><th class="r">Total</th></tr></thead><tbody>';
			if (!rows || !rows.length) {
				html += '<tr><td colspan="3" class="muted" style="text-align:center;padding:16px;">No gaps found</td></tr>';
			} else {
				rows.forEach(function(r) {
					html += '<tr>' +
						'<td>' + mbi_link('Sales Order', r.name) + '</td>' +
						'<td class="muted" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;">' + frappe.utils.escape_html(r.customer_name || '') + '</td>' +
						'<td class="r">' + fmt_currency(r.grand_total) + '</td>' +
					'</tr>';
				});
			}
			html += '</tbody></table></div></div>';
			return html;
		}

		body.innerHTML = '<div class="mbi-gap-row">' +
			gap_col('No Delivery Note', d.no_dn, 'rose') +
			gap_col('No Sales Invoice', d.no_si, 'amber') +
			gap_col('No DN & No SI', d.no_both, 'red') +
		'</div>';
	});
}

/* ─── 5. Invoices with payments ─────────────────────────────────────────── */
function load_payments(root, co) {
	var body = root.querySelector('#payments-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_invoices_with_payments', {companies: JSON.stringify(co), limit: 100}, function(d) {
		if (!d || !d.length) { body.innerHTML = '<div class="mbi-empty">No data</div>'; return; }
		var html = '<div class="mbi-tbl-wrap"><table class="mbi-tbl">' +
			'<thead><tr>' +
			'<th>Invoice #</th><th>Date</th><th>Customer</th><th>Company</th>' +
			'<th class="r">Grand Total</th><th class="r">Outstanding</th>' +
			'<th>Payment Modes</th><th>Overdue Days</th><th>Status</th>' +
			'</tr></thead><tbody>';
		d.forEach(function(r) {
			var overdue_class = (r.days_overdue > 0) ? ' class="mbi-overdue"' : '';
			html += '<tr>' +
				'<td>' + mbi_link('Sales Invoice', r.name) + '</td>' +
				'<td class="muted">' + (r.posting_date || '') + '</td>' +
				'<td>' + frappe.utils.escape_html(r.customer_name || '') + '</td>' +
				'<td class="muted">' + frappe.utils.escape_html(r.company || '') + '</td>' +
				'<td class="r">' + fmt_currency(r.grand_total) + '</td>' +
				'<td class="r">' + fmt_currency(r.outstanding_amount) + '</td>' +
				'<td class="muted">' + frappe.utils.escape_html(r.payment_modes || '—') + '</td>' +
				'<td' + overdue_class + '>' + (r.days_overdue > 0 ? r.days_overdue + ' days' : '—') + '</td>' +
				'<td>' + status_badge(r.status) + '</td>' +
			'</tr>';
		});
		html += '</tbody></table></div>';
		body.innerHTML = html;
	});
}

/* ─── 6. Cash & Bank — from Invoices ───────────────────────────────────── */
function load_cashbank(root, co) {
	var body = root.querySelector('#cashbank-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_cash_bank_payments', {companies: JSON.stringify(co)}, function(d) {
		if (!d) { body.innerHTML = '<div class="mbi-empty">No data</div>'; return; }

		var html = '<div class="mbi-pay-kpi-row">' +
			'<div class="mbi-pay-kpi">' +
				'<div class="mbi-pay-label">Total Billed</div>' +
				'<div class="mbi-pay-value" style="color:var(--sd-blue)">' + fmt_currency(d.total_billed) + '</div>' +
			'</div>' +
			'<div class="mbi-pay-kpi">' +
				'<div class="mbi-pay-label">Collected</div>' +
				'<div class="mbi-pay-value" style="color:var(--sd-emerald)">' + fmt_currency(d.total_collected) + '</div>' +
			'</div>' +
			'<div class="mbi-pay-kpi">' +
				'<div class="mbi-pay-label">Outstanding</div>' +
				'<div class="mbi-pay-value" style="color:var(--sd-rose)">' + fmt_currency(d.total_outstanding) + '</div>' +
			'</div>' +
			'<div class="mbi-pay-kpi">' +
				'<div class="mbi-pay-label">Collection %</div>' +
				'<div class="mbi-pay-value">' + (d.total_billed > 0 ? Math.round(d.total_collected / d.total_billed * 100) : 0) + '%</div>' +
			'</div>' +
		'</div>';

		if (d.by_company && d.by_company.length) {
			html += '<div class="mbi-tbl-wrap"><table class="mbi-tbl">' +
				'<thead><tr>' +
				'<th>Company</th>' +
				'<th class="r">Invoices</th>' +
				'<th class="r">Total Billed</th>' +
				'<th class="r">Collected</th>' +
				'<th class="r">Outstanding</th>' +
				'<th class="r">Coll %</th>' +
				'</tr></thead><tbody>';
			d.by_company.forEach(function(r) {
				var billed = parseFloat(r.total_billed || 0);
				var coll   = parseFloat(r.total_collected || 0);
				var pct    = billed > 0 ? Math.round(coll / billed * 100) : 0;
				html += '<tr>' +
					'<td>' + frappe.utils.escape_html(r.company || '') + '</td>' +
					'<td class="r">' + fmt_num(r.invoice_count) + '</td>' +
					'<td class="r">' + fmt_currency(billed) + '</td>' +
					'<td class="r" style="color:var(--sd-emerald)">' + fmt_currency(coll) + '</td>' +
					'<td class="r" style="color:var(--sd-rose)">' + fmt_currency(r.total_outstanding) + '</td>' +
					'<td class="r"><strong>' + pct + '%</strong></td>' +
				'</tr>';
			});
			html += '</tbody></table></div>';
		}
		body.innerHTML = html;
	});
}

/* ─── 7. Conversion overview ────────────────────────────────────────────── */
function load_conversion(root, co) {
	var body = root.querySelector('#conversion-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_conversion_overview', {companies: JSON.stringify(co)}, function(d) {
		if (!d) { body.innerHTML = '<div class="mbi-empty">No data</div>'; return; }

		function conv_step(pct, label, counts, color) {
			pct = parseFloat(pct) || 0;
			return '<div class="mbi-conv-step" style="--conv-color:' + color + '">' +
				'<div class="mbi-conv-pct">' + Math.round(pct) + '%</div>' +
				'<div class="mbi-conv-label">' + label + '</div>' +
				'<div class="mbi-conv-counts">' + frappe.utils.escape_html(counts) + '</div>' +
				'<div class="mbi-conv-bar-wrap"><div class="mbi-conv-bar" style="width:' + Math.min(100, pct) + '%"></div></div>' +
			'</div>';
		}

		var html = '<div class="mbi-conv-grid">' +
			conv_step(d.so_dn_pct, 'SO → DN', (d.so_with_dn || 0) + ' / ' + (d.total_so || 0) + ' SOs', '#2563eb') +
			conv_step(d.so_si_pct, 'SO → SI', (d.so_with_si || 0) + ' / ' + (d.total_so || 0) + ' SOs', '#7c3aed') +
			conv_step(d.so_both_pct, 'SO → Both', (d.so_with_both || 0) + ' / ' + (d.total_so || 0) + ' SOs', '#059669') +
			conv_step(d.si_paid_pct, 'SI Paid', (d.si_paid || 0) + ' / ' + (d.total_si || 0) + ' SIs', '#d97706') +
		'</div>';
		body.innerHTML = html;
	});
}

/* ─── 8. Item group totals ──────────────────────────────────────────────── */
function load_item_groups(root, co) {
	var body = root.querySelector('#itemgroups-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_item_group_totals', {companies: JSON.stringify(co)}, function(d) {
		if (!d || !d.length) { body.innerHTML = '<div class="mbi-empty">No data</div>'; return; }
		var html = '<div class="mbi-tbl-wrap"><table class="mbi-tbl mbi-ig-tbl">' +
			'<thead><tr>' +
			'<th>Item Group</th><th class="r">SO Qty</th><th class="r">SO Value</th>' +
			'<th class="r">DN Qty</th><th class="r">DN Value</th>' +
			'<th class="r">SI Qty</th><th class="r">SI Value</th>' +
			'</tr></thead><tbody>';
		var tots = {so_qty:0,so_val:0,dn_qty:0,dn_val:0,si_qty:0,si_val:0};
		d.forEach(function(r) {
			html += '<tr>' +
				'<td>' + frappe.utils.escape_html(r.item_group || '—') + '</td>' +
				'<td class="r">' + fmt_num(r.so_qty) + '</td>' +
				'<td class="r">' + fmt_currency(r.so_value) + '</td>' +
				'<td class="r">' + fmt_num(r.dn_qty) + '</td>' +
				'<td class="r">' + fmt_currency(r.dn_value) + '</td>' +
				'<td class="r">' + fmt_num(r.si_qty) + '</td>' +
				'<td class="r">' + fmt_currency(r.si_value) + '</td>' +
			'</tr>';
			tots.so_qty += parseFloat(r.so_qty||0);
			tots.so_val += parseFloat(r.so_value||0);
			tots.dn_qty += parseFloat(r.dn_qty||0);
			tots.dn_val += parseFloat(r.dn_value||0);
			tots.si_qty += parseFloat(r.si_qty||0);
			tots.si_val += parseFloat(r.si_value||0);
		});
		html += '</tbody><tfoot><tr>' +
			'<td>Total</td>' +
			'<td>' + fmt_num(tots.so_qty) + '</td>' +
			'<td>' + fmt_currency(tots.so_val) + '</td>' +
			'<td>' + fmt_num(tots.dn_qty) + '</td>' +
			'<td>' + fmt_currency(tots.dn_val) + '</td>' +
			'<td>' + fmt_num(tots.si_qty) + '</td>' +
			'<td>' + fmt_currency(tots.si_val) + '</td>' +
		'</tr></tfoot></table></div>';
		body.innerHTML = html;
	});
}

/* ─── 8b. Item Group Conversion ─────────────────────────────────────────── */
function load_ig_conversion(root, co) {
	var body = root.querySelector('#igconv-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_item_group_conversion', {companies: JSON.stringify(co)}, function(d) {
		if (!d || (!d.rm_groups && !d.fg_groups)) { body.innerHTML = '<div class="mbi-empty">No data</div>'; return; }

		var rm = d.rm_groups || [];
		var fg = d.fg_groups || [];
		var total_rm = parseFloat(d.total_rm_qty || 0);
		var total_fg = parseFloat(d.total_fg_qty || 0);
		var yield_pct = total_rm > 0 ? (total_fg / total_rm * 100).toFixed(1) : '—';

		function ig_bar(item_group, qty, pct) {
			pct = Math.min(100, parseFloat(pct) || 0);
			var bar_color = '#3b82f6';
			return '<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #f1f5f9;">' +
				'<div style="min-width:130px;font-size:12px;font-weight:600;color:#1e293b;">' + frappe.utils.escape_html(item_group) + '</div>' +
				'<div style="flex:1;height:10px;background:#f1f5f9;border-radius:5px;overflow:hidden;">' +
					'<div style="width:' + pct + '%;height:100%;background:' + bar_color + ';border-radius:5px;transition:width 0.6s;"></div>' +
				'</div>' +
				'<div style="min-width:55px;text-align:right;font-family:\'DM Mono\',monospace;font-size:11px;font-weight:700;color:#334155;">' +
					fmt_num(qty) + ' g</div>' +
				'<div style="min-width:38px;text-align:right;font-size:11px;font-weight:700;color:#64748b;">' +
					pct.toFixed(1) + '%</div>' +
			'</div>';
		}

		function conv_panel(title, accent, rows, total) {
			var inner = rows.length
				? rows.map(function(r){ return ig_bar(r.item_group, r.qty, r.pct); }).join('')
				: '<div style="color:#94a3b8;font-size:12px;padding:12px 0;">No data</div>';
			return '<div style="flex:1;min-width:0;">' +
				'<div style="display:flex;align-items:center;justify-content:space-between;' +
				'border-bottom:2px solid ' + accent + ';padding-bottom:8px;margin-bottom:10px;">' +
					'<span style="font-size:11px;font-weight:700;color:' + accent + ';text-transform:uppercase;letter-spacing:0.08em;">' + title + '</span>' +
					'<span style="font-family:\'DM Mono\',monospace;font-size:13px;font-weight:700;color:#1e293b;">' +
						fmt_num(total) + ' g total</span>' +
				'</div>' +
				inner +
			'</div>';
		}

		var html = '<div style="padding:18px;">' +
			'<div style="display:flex;gap:24px;align-items:flex-start;">' +
				conv_panel('Materials In (Raw)', '#7c3aed', rm, total_rm) +
				'<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;' +
				'padding:0 8px;min-width:72px;gap:6px;">' +
					'<div style="font-size:22px;color:#94a3b8;">→</div>' +
					'<div style="font-size:10px;font-weight:700;color:#64748b;text-align:center;text-transform:uppercase;letter-spacing:0.06em;">Yield</div>' +
					'<div style="font-size:16px;font-weight:800;color:#059669;">' + yield_pct + (yield_pct !== '—' ? '%' : '') + '</div>' +
				'</div>' +
				conv_panel('Finished Goods Out', '#059669', fg, total_fg) +
			'</div>' +
		'</div>';

		body.innerHTML = html;
	});
}

/* ─── 9. Hardware counts ────────────────────────────────────────────────── */
function load_hardware(root, co) {
	var body = root.querySelector('#hardware-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_hardware_counts', {companies: JSON.stringify(co)}, function(d) {
		if (!d || !d.length) { body.innerHTML = '<div class="mbi-empty">No data</div>'; return; }

		var max_in = Math.max.apply(null, d.map(function(r){ return r.in_qty || 0; })) || 1;

		var html = '<div style="padding:0;">' +
			'<div style="display:grid;grid-template-columns:180px 1fr 100px 100px;align-items:center;' +
			'background:#f8fafc;border-bottom:1.5px solid #e2e8f0;padding:8px 18px;' +
			'font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.07em;">' +
			'<div>Item Group</div><div style="padding-left:8px;">Total In</div>' +
			'<div style="text-align:right;">In Qty</div>' +
			'<div style="text-align:right;">On Hand</div>' +
		'</div>';

		d.forEach(function(r) {
			var in_qty  = parseFloat(r.in_qty   || 0);
			var on_hand = parseFloat(r.total_qty || 0);
			var bar_pct = in_qty > 0 ? Math.min(100, in_qty / max_in * 100) : 0;

			html += '<div style="display:grid;grid-template-columns:180px 1fr 100px 100px;align-items:center;' +
				'padding:10px 18px;border-bottom:1px solid #f8fafc;">' +
				'<div style="font-size:12px;font-weight:600;color:#1e293b;">' +
					frappe.utils.escape_html(r.item_group) + '</div>' +
				'<div style="padding-left:8px;">' +
					'<div style="height:10px;background:#f1f5f9;border-radius:5px;overflow:hidden;">' +
						'<div style="width:' + bar_pct.toFixed(1) + '%;height:100%;background:#3b82f6;border-radius:5px;transition:width 0.5s;"></div>' +
					'</div>' +
				'</div>' +
				'<div style="text-align:right;font-family:\'DM Mono\',monospace;font-size:12px;font-weight:700;' +
					'color:' + (in_qty > 0 ? '#1e293b' : '#cbd5e1') + ';">' +
					(in_qty > 0 ? fmt_num(in_qty) : '—') + '</div>' +
				'<div style="text-align:right;font-family:\'DM Mono\',monospace;font-size:12px;font-weight:600;' +
					'color:' + (on_hand > 0 ? '#059669' : '#94a3b8') + ';">' +
					(on_hand > 0 ? fmt_num(on_hand) : '—') + '</div>' +
			'</div>';
		});

		html += '</div>';
		body.innerHTML = html;
	});
}

/* ─── 10. Tolling check ─────────────────────────────────────────────────── */
function load_tolling(root) {
	var body = root.querySelector('#tolling-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_tolling_check', {}, function(d) {
		if (!d || !d.length) { body.innerHTML = '<div class="mbi-empty">No open Sales Orders found</div>'; return; }

		var shortage_sos = d.filter(function(so){ return so.has_shortage; });
		var ready_sos    = d.filter(function(so){ return so.all_covered; });

		var badge = root.querySelector('#mbi-tolling-badge');
		if (badge) {
			badge.textContent = shortage_sos.length + ' shortage' + (shortage_sos.length !== 1 ? 's' : '');
			badge.className = 'mbi-section-badge ' + (shortage_sos.length > 0 ? 'red' : 'green');
		}

		function days_ago(date_str) {
			var d = new Date(date_str), now = new Date();
			return Math.floor((now - d) / 86400000);
		}

		function stock_bar(stock, pending) {
			var pct = pending > 0 ? Math.min(100, stock / pending * 100) : 100;
			var color = pct >= 100 ? '#059669' : (pct >= 50 ? '#d97706' : '#e11d48');
			return '<div style="display:flex;align-items:center;gap:6px;">' +
				'<div style="flex:1;min-width:60px;height:7px;background:#f1f5f9;border-radius:4px;overflow:hidden;">' +
					'<div style="width:' + pct.toFixed(0) + '%;height:100%;background:' + color + ';border-radius:4px;"></div>' +
				'</div>' +
				'<span style="font-size:10px;font-weight:700;color:' + color + ';min-width:34px;text-align:right;">' + pct.toFixed(0) + '%</span>' +
			'</div>';
		}

		var html = '';

		// Summary strip
		html += '<div style="display:flex;gap:12px;padding:12px 18px;background:#f8fafc;border-bottom:1.5px solid #e2e8f0;">' +
			'<div style="display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:8px;background:#fee2e2;border:1px solid #fca5a5;">' +
				'<span style="font-size:20px;font-weight:800;color:#e11d48;">' + shortage_sos.length + '</span>' +
				'<span style="font-size:11px;font-weight:600;color:#991b1b;text-transform:uppercase;letter-spacing:0.05em;">Stock Shortages</span>' +
			'</div>' +
			'<div style="display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:8px;background:#dcfce7;border:1px solid #86efac;">' +
				'<span style="font-size:20px;font-weight:800;color:#059669;">' + ready_sos.length + '</span>' +
				'<span style="font-size:11px;font-weight:600;color:#166534;text-transform:uppercase;letter-spacing:0.05em;">Ready to Ship</span>' +
			'</div>' +
			'<div style="display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:8px;background:#f1f5f9;border:1px solid #e2e8f0;">' +
				'<span style="font-size:20px;font-weight:800;color:#475569;">' + d.length + '</span>' +
				'<span style="font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;">Total Open SOs</span>' +
			'</div>' +
		'</div>';

		// SO list — shortages first (already sorted by backend)
		d.forEach(function(so, idx) {
			var age = days_ago(so.transaction_date);
			var age_color = age > 14 ? '#e11d48' : (age > 7 ? '#d97706' : '#64748b');
			var so_border = so.has_shortage ? '#e11d48' : '#059669';
			var so_bg     = so.has_shortage ? '#fff5f5' : '#f0fdf4';
			var co_color  = CO_COLORS[so.company] || '#2563eb';
			var items_id  = 'tolling-items-' + idx;

			html += '<div style="border-left:3px solid ' + so_border + ';background:' + so_bg + ';margin:8px 18px;border-radius:0 8px 8px 0;overflow:hidden;">' +
				// SO header — clickable, collapsed by default
				'<div class="tolling-so-hdr" data-items="' + items_id + '" ' +
					'style="display:flex;align-items:center;gap:12px;padding:10px 14px;cursor:pointer;user-select:none;">' +
					'<svg class="tolling-chevron" viewBox="0 0 24 24" style="width:14px;height:14px;flex-shrink:0;transition:transform 0.2s;color:#94a3b8;">' +
						'<polyline points="6 9 12 15 18 9" fill="none" stroke="currentColor" stroke-width="2"/></svg>' +
					'<a href="/app/sales-order/' + encodeURIComponent(so.so_name) + '" target="_blank" ' +
						'onclick="event.stopPropagation();" ' +
						'style="font-size:12px;font-weight:700;color:#2563eb;text-decoration:none;">' +
						frappe.utils.escape_html(so.so_name) + '</a>' +
					'<span style="font-size:12px;font-weight:600;color:#1e293b;flex:1;">' + frappe.utils.escape_html(so.customer_name) + '</span>' +
					'<span style="font-size:10px;font-weight:600;color:' + co_color + ';background:' + co_color + '1a;padding:2px 8px;border-radius:4px;">' +
						frappe.utils.escape_html(so.company) + '</span>' +
					'<span style="font-size:11px;color:' + age_color + ';font-weight:700;">' + age + 'd ago</span>' +
					'<span style="font-size:10px;color:#94a3b8;">' + so.transaction_date + '</span>' +
					(so.has_shortage
						? '<span style="font-size:10px;font-weight:700;color:#e11d48;background:#fee2e2;padding:2px 8px;border-radius:4px;">' + so.shortage_count + ' SHORT</span>'
						: '<span style="font-size:10px;font-weight:700;color:#059669;background:#dcfce7;padding:2px 8px;border-radius:4px;">READY</span>') +
					'<span style="font-size:10px;color:#94a3b8;margin-left:2px;">' + so.items.length + ' item' + (so.items.length !== 1 ? 's' : '') + '</span>' +
				'</div>' +
				// Items — hidden by default
				'<div id="' + items_id + '" style="display:none;padding:0 0 4px 0;">' +
				'<div style="display:grid;grid-template-columns:2fr 80px 80px 80px 130px;gap:0;' +
					'padding:5px 14px;font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;border-top:1px solid rgba(0,0,0,0.06);">' +
					'<div>Item</div><div style="text-align:right;">Pending</div>' +
					'<div style="text-align:right;">In Stock</div>' +
					'<div style="text-align:right;">Shortage</div>' +
					'<div style="padding-left:8px;">Coverage</div>' +
				'</div>';

			so.items.forEach(function(item) {
				var item_color = item.covered ? '#059669' : '#e11d48';
				var short_val  = item.shortage > 0 ? ('-' + fmt_num(item.shortage)) : '—';
				html += '<div style="display:grid;grid-template-columns:2fr 80px 80px 80px 130px;gap:0;' +
					'padding:6px 14px;border-top:1px solid rgba(0,0,0,0.04);align-items:center;">' +
					'<div style="font-size:11px;color:#334155;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' +
						frappe.utils.escape_html(item.item_name) + '">' + frappe.utils.escape_html(item.item_name) + '</div>' +
					'<div style="text-align:right;font-family:\'DM Mono\',monospace;font-size:11px;color:#475569;">' + fmt_num(item.pending_qty) + '</div>' +
					'<div style="text-align:right;font-family:\'DM Mono\',monospace;font-size:11px;color:' + item_color + ';font-weight:600;">' + fmt_num(item.stock_qty) + '</div>' +
					'<div style="text-align:right;font-family:\'DM Mono\',monospace;font-size:11px;color:' + (item.shortage > 0 ? '#e11d48' : '#94a3b8') + ';font-weight:700;">' + short_val + '</div>' +
					'<div style="padding-left:8px;">' + stock_bar(item.stock_qty, item.pending_qty) + '</div>' +
				'</div>';
			});

			html += '</div></div>';
		});

		body.innerHTML = html;

		// Wire collapse toggles
		body.querySelectorAll('.tolling-so-hdr').forEach(function(hdr) {
			hdr.addEventListener('click', function() {
				var items = body.querySelector('#' + hdr.dataset.items);
				var chevron = hdr.querySelector('.tolling-chevron');
				var open = items.style.display !== 'none';
				items.style.display = open ? 'none' : 'block';
				if (chevron) chevron.style.transform = open ? '' : 'rotate(180deg)';
			});
		});
	});
}

/* ─── 11. AR / AP ───────────────────────────────────────────────────────── */
function load_arap(root, co) {
	var body = root.querySelector('#arap-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_ar_ap_summary', {companies: JSON.stringify(co)}, function(d) {
		if (!d) { body.innerHTML = '<div class="mbi-empty">Failed to load</div>'; return; }
		var html = '<div class="mbi-arap-row">' +
			render_arap_panel('AR — Receivable', d.ar || [], '#059669') +
			render_arap_panel('AP — Payable', d.ap || [], '#e11d48') +
		'</div>';
		body.innerHTML = html;
	});
}

function render_arap_panel(title, rows, color) {
	var total = rows.reduce(function(s, r) { return s + parseFloat(r.outstanding || 0); }, 0);
	var html = '<div class="mbi-arap-panel">' +
		'<div class="mbi-arap-header">' +
		'<span class="mbi-arap-title" style="color:' + color + '">' + title + '</span>' +
		'<span class="mbi-arap-total" style="color:' + color + '">' + fmt_currency(total) + '</span>' +
	'</div>' +
	'<div class="mbi-arap-body">' +
	'<table class="mbi-tbl" style="min-width:0;">' +
	'<thead><tr><th>Party</th><th class="r">Outstanding</th><th class="r">Overdue</th></tr></thead><tbody>';

	if (!rows.length) {
		html += '<tr><td colspan="3" class="muted" style="text-align:center;padding:16px;">No outstanding amounts</td></tr>';
	} else {
		rows.forEach(function(r) {
			var overdue_cls = parseFloat(r.overdue||0) > 0 ? ' class="mbi-overdue"' : '';
			html += '<tr>' +
				'<td>' + frappe.utils.escape_html(r.customer_name || r.supplier_name || r.party || '') + '</td>' +
				'<td class="r">' + fmt_currency(r.outstanding) + '</td>' +
				'<td' + overdue_cls + ' style="text-align:right">' + fmt_currency(r.overdue) + '</td>' +
			'</tr>';
		});
	}
	html += '</tbody></table></div></div>';
	return html;
}

/* ─── 12. Sales by type ─────────────────────────────────────────────────── */
function load_sales_type(root, co) {
	var body = root.querySelector('#salestype-body');
	body.innerHTML = '<div class="mbi-loading"><div class="mbi-spinner"></div>Loading…</div>';
	api('get_sales_by_type', {companies: JSON.stringify(co)}, function(d) {
		if (!d || !d.length) { body.innerHTML = '<div class="mbi-empty">No data</div>'; return; }
		var html = '<div class="mbi-tbl-wrap"><table class="mbi-tbl">' +
			'<thead><tr>' +
			'<th>Order Type</th><th>Company</th><th class="r">SO Count</th>' +
			'<th class="r">SO Value</th><th class="r">Open Count</th>' +
			'</tr></thead><tbody>';
		var tot_cnt = 0, tot_val = 0;
		d.forEach(function(r) {
			html += '<tr>' +
				'<td>' + frappe.utils.escape_html(r.type_label || '—') + '</td>' +
				'<td class="muted">' + frappe.utils.escape_html(r.company || '') + '</td>' +
				'<td class="r">' + fmt_num(r.cnt) + '</td>' +
				'<td class="r">' + fmt_currency(r.total_amount) + '</td>' +
				'<td class="r">' + fmt_num(r.open_count) + '</td>' +
			'</tr>';
			tot_cnt += parseFloat(r.cnt||0);
			tot_val += parseFloat(r.total_amount||0);
		});
		html += '</tbody><tfoot><tr>' +
			'<td>Total</td><td></td>' +
			'<td>' + fmt_num(tot_cnt) + '</td><td>' + fmt_currency(tot_val) + '</td><td></td>' +
		'</tr></tfoot></table></div>';
		body.innerHTML = html;
	});
}
