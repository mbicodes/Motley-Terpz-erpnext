frappe.pages['ceo-dashboard-farm'].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'CEO Dashboard — Farm',
		single_column: true,
	});

	$(wrapper).find('.layout-main-section').html(getCdfHTML());
	var root = wrapper.querySelector('.cdf-dash');

	var API = 'cannabis_management.api.ceo_dashboard_farm.';
	var archivedHarvestsOpen = false;
	var archivedProcurementOpen = false;

	root.querySelector('#cdf-archived-toggle').addEventListener('click', function () {
		archivedHarvestsOpen = !archivedHarvestsOpen;
		root.querySelector('#cdf-archived-wrap').classList.toggle('cdf-open', archivedHarvestsOpen);
	});

	root.querySelector('#cdf-procurement-archived-toggle').addEventListener('click', function () {
		archivedProcurementOpen = !archivedProcurementOpen;
		root.querySelector('#cdf-procurement-archived-wrap').classList.toggle('cdf-open', archivedProcurementOpen);
	});

	loadAll();

	function loadAll() {
		loadActiveHarvests();
		loadArchivedHarvests();
		loadActiveProcurement();
		loadArchivedProcurement();
	}

	function money(v) {
		return format_currency(flt(v || 0));
	}
	function num(v) {
		return frappe.format(flt(v || 0), { fieldtype: 'Float', precision: 1 }, { only_value: true });
	}
	function flt(v) { return v === null || v === undefined ? 0 : parseFloat(v) || 0; }

	function loadActiveHarvests() {
		frappe.call({
			method: API + 'get_active_harvests',
			callback: function (r) {
				var rows = r.message || [];
				var target = root.querySelector('#cdf-active-harvests');
				if (!rows.length) {
					target.innerHTML = '<div class="cdf-empty">No active harvests yet.</div>';
					return;
				}
				target.innerHTML = rows.map(function (h, i) { return harvestCardHTML(h, i); }).join('');
				rows.forEach(function (h) { wireHarvestToggle(root, h, 'Active'); });
			},
		});
	}

	function loadArchivedHarvests() {
		frappe.call({
			method: API + 'get_archived_harvests',
			callback: function (r) {
				var rows = r.message || [];
				var target = root.querySelector('#cdf-archived-harvests');
				if (!rows.length) {
					target.innerHTML = '<div class="cdf-empty">No archived harvests.</div>';
					return;
				}
				target.innerHTML = rows.map(function (h) { return archivedHarvestRowHTML(h); }).join('');
				rows.forEach(function (h) { wireHarvestToggle(root, h, 'Archived'); });
			},
		});
	}

	function loadActiveProcurement() {
		frappe.call({
			method: API + 'get_procurement_cards',
			callback: function (r) {
				var rows = r.message || [];
				var target = root.querySelector('#cdf-procurement-active');
				if (!rows.length) {
					target.innerHTML = '<div class="cdf-empty">No active Frozen Flip procurements.</div>';
				} else {
					target.innerHTML = rows.map(function (b, i) { return procurementCardHTML(b, i); }).join('');
					rows.forEach(function (b) { wireBatchToggle(root, b, 'Active'); });
				}
			},
		});
	}

	function loadArchivedProcurement() {
		frappe.call({
			method: API + 'get_archived_procurement_cards',
			callback: function (r) {
				var rows = r.message || [];
				var target = root.querySelector('#cdf-procurement-archived');
				if (!rows.length) {
					target.innerHTML = '<div class="cdf-empty">No archived procurements.</div>';
					return;
				}
				target.innerHTML = rows.map(function (b) { return archivedProcurementRowHTML(b); }).join('');
				rows.forEach(function (b) { wireBatchToggle(root, b, 'Archived'); });
			},
		});
	}

	function wireHarvestToggle(root, h, currentStatus) {
		var btn = root.querySelector('[data-harvest-toggle="' + h.name + '"]');
		if (!btn) return;
		btn.addEventListener('click', function () {
			var newStatus = currentStatus === 'Active' ? 'Archived' : 'Active';
			frappe.call({
				method: API + 'set_harvest_status',
				args: { harvest_name: h.name, new_status: newStatus },
				callback: function () {
					frappe.show_alert({ message: h.harvest_name + ' → ' + newStatus, indicator: 'green' });
					loadActiveHarvests();
					loadArchivedHarvests();
				},
			});
		});
	}

	function wireBatchToggle(root, b, currentStatus) {
		var btn = root.querySelector('[data-batch-toggle="' + b.name + '"]');
		if (!btn) return;
		btn.addEventListener('click', function () {
			var newStatus = currentStatus === 'Active' ? 'Archived' : 'Active';
			frappe.call({
				method: API + 'set_batch_status',
				args: { batch_name: b.name, new_status: newStatus },
				callback: function () {
					frappe.show_alert({ message: b.name + ' → ' + newStatus, indicator: 'green' });
					loadActiveProcurement();
					loadArchivedProcurement();
				},
			});
		});
	}

	function harvestCardHTML(h, i) {
		var shade = i % 2 === 0 ? 'cdf-green-1' : 'cdf-green-2';
		var titleSub = [h.strains, h.harvest_date ? frappe.datetime.str_to_user(h.harvest_date) : null]
			.filter(Boolean).join(' · ');
		return '\
<div class="cdf-card ' + shade + '">\
  <div class="cdf-card-head">\
    <div class="cdf-card-title">' + frappe.utils.escape_html(h.harvest_name || h.name) +
			(titleSub ? ' <span class="cdf-card-sub">[' + frappe.utils.escape_html(titleSub) + ']</span>' : '') + '</div>\
    <div class="cdf-card-actions">\
      <span class="cdf-status-pill">● Active</span>\
      <button class="cdf-toggle-btn" data-harvest-toggle="' + h.name + '">Archive →</button>\
    </div>\
  </div>\
  <div class="cdf-card-body cdf-cols-5">\
    ' + statBlock('LBS PRODUCED', num(h.lbs_produced), 'Total lbs from this harvest') + '\
    ' + statBlock('REVENUE TO DATE', money(h.revenue_to_date), '$ sold from this harvest (running)') + '\
    ' + statBlock('COSTS TO DATE', money(h.costs_to_date), 'All costs attributed to this harvest') + '\
    ' + statBlock('GROSS PROFIT TO DATE', money(h.gross_profit), 'Revenue minus COGS') + '\
    ' + statBlock('NET TO DATE', money(h.net_to_date), 'Gross profit minus overhead') + '\
  </div>\
</div>';
	}

	function archivedHarvestRowHTML(h) {
		return '\
<div class="cdf-archived-row">\
  <div>\
    <span class="cdf-archived-title">' + frappe.utils.escape_html(h.harvest_name || h.name) + '</span>\
    <span class="cdf-archived-meta">Lbs: ' + num(h.lbs_produced) + '&nbsp;&nbsp; Revenue: ' + money(h.revenue_to_date) + '&nbsp;&nbsp; Net: ' + money(h.net_to_date) + '</span>\
  </div>\
  <div class="cdf-card-actions">\
    <span class="cdf-status-pill cdf-status-archived">Archived</span>\
    <button class="cdf-toggle-btn cdf-restore" data-harvest-toggle="' + h.name + '">← Restore Active</button>\
  </div>\
</div>';
	}

	function procurementCardHTML(b, i) {
		var title = (b.item || b.name) + (b.item ? ' <span class="cdf-card-sub">[' + frappe.utils.escape_html(b.name) + ']</span>' : '');
		return '\
<div class="cdf-card cdf-navy">\
  <div class="cdf-card-head">\
    <div class="cdf-card-title">' + title + '</div>\
    <div class="cdf-card-actions">\
      <span class="cdf-status-pill">● Active</span>\
      <button class="cdf-toggle-btn" data-batch-toggle="' + b.name + '">Archive →</button>\
    </div>\
  </div>\
  <div class="cdf-card-body cdf-cols-4">\
    ' + statBlock('LBS PROCURED', num(b.lbs_procured), 'Original lbs received (fixed)') + '\
    ' + statBlock('LBS SOLD', num(b.lbs_sold), 'Lbs moved to date') + '\
    ' + statBlock('REMAINING STOCK', num(b.remaining_stock), 'Lbs left in this batch') + '\
    ' + statBlock('AVG SALES PRICE / LB', money(b.avg_price), 'Avg $/lb realized') + '\
  </div>\
</div>';
	}

	function archivedProcurementRowHTML(b) {
		var title = (b.item || b.name) + (b.item ? ' [' + b.name + ']' : '');
		return '\
<div class="cdf-archived-row">\
  <div>\
    <span class="cdf-archived-title">' + frappe.utils.escape_html(title) + '</span>\
    <span class="cdf-archived-meta">Procured: ' + num(b.lbs_procured) + '&nbsp;&nbsp; Sold: ' + num(b.lbs_sold) + '&nbsp;&nbsp; Remaining: ' + num(b.remaining_stock) + '</span>\
  </div>\
  <div class="cdf-card-actions">\
    <span class="cdf-status-pill cdf-status-archived">Archived</span>\
    <button class="cdf-toggle-btn cdf-restore" data-batch-toggle="' + b.name + '">← Restore Active</button>\
  </div>\
</div>';
	}

	function statBlock(label, value, caption) {
		return '\
<div>\
  <div class="cdf-stat-label">' + label + '</div>\
  <div class="cdf-stat-value">' + (value === undefined || value === null || value === '' ? '—' : value) + '</div>\
  <div class="cdf-stat-caption">' + caption + '</div>\
</div>';
	}

	function getCdfHTML() {
		return '\
<div class="cdf-dash">\
  <div class="cdf-header">\
    <div class="cdf-hdr-left">Farm Department — Operations &amp; KPI Framework</div>\
    <div class="cdf-hdr-right">CEO Dashboard</div>\
  </div>\
\
  <div class="cdf-title">CEO Dashboard — Farm</div>\
  <div class="cdf-subtitle">All metrics tracked per harvest — each harvest is its own row with full financials. \
Active harvests show in the main view; Matt can archive any harvest to tuck it away. \
Archived harvests are always accessible via the archive list and can be toggled back to active at any time.</div>\
\
  <div class="cdf-section-bar">\
    <button class="cdf-section-pill">ACTIVE HARVESTS</button>\
    <div class="cdf-section-line"></div>\
    <div class="cdf-section-caption">Matt manually archives · archived harvests visible below</div>\
  </div>\
  <div id="cdf-active-harvests"></div>\
  <div class="cdf-placeholder-row">+ Harvest 3, 4… — new row added for each harvest event</div>\
\
  <div class="cdf-section-bar">\
    <button class="cdf-section-pill cdf-pill-archived" id="cdf-archived-toggle">▾ ARCHIVED HARVESTS</button>\
    <div class="cdf-section-line"></div>\
    <div class="cdf-section-caption">Click to expand · toggle any archived harvest back to active</div>\
  </div>\
  <div id="cdf-archived-wrap" class="cdf-archived-wrap">\
    <div id="cdf-archived-harvests"></div>\
  </div>\
\
  <div class="cdf-section-bar">\
    <button class="cdf-section-pill cdf-pill-frozen">PER PROCUREMENT — FROZEN FLIP</button>\
    <div class="cdf-section-line"></div>\
    <div class="cdf-section-caption">Same active/archive toggle per procurement</div>\
  </div>\
  <div id="cdf-procurement-active"></div>\
  <div class="cdf-placeholder-row">+ Procurement 2, 3… — new row added for each procurement batch</div>\
\
  <div class="cdf-section-bar">\
    <button class="cdf-section-pill cdf-pill-archived" id="cdf-procurement-archived-toggle">▾ ARCHIVED PROCUREMENTS</button>\
    <div class="cdf-section-line"></div>\
    <div class="cdf-section-caption">Click to expand · toggle any archived procurement back to active</div>\
  </div>\
  <div id="cdf-procurement-archived-wrap" class="cdf-archived-wrap">\
    <div id="cdf-procurement-archived"></div>\
  </div>\
</div>';
	}
};
