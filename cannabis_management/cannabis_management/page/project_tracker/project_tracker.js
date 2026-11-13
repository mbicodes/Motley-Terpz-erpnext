// Project Tracker: Fresh Frozen toll and in-house projects end to end. Layout follows the Motley Project Tracker
// prototype. Read-only: every figure is computed on the server from submitted documents; buttons open standard forms.
const PTK_M = 'cannabis_management.cannabis_management.page.project_tracker.project_tracker.';
const PTK_LB = 453.592;

const ptk_esc = v => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const ptk_n0 = n => Math.round(n || 0).toLocaleString('en-US');
const ptk_lbs = n => ptk_n0(n) + ' lbs';
const ptk_g = n => ptk_n0(n) + ' g';
const ptk_pct = (n, d) => (n == null ? '—' : Number(n).toFixed(d == null ? 2 : d) + '%');
const ptk_usd = n => (n == null ? '—' : '$' + ptk_n0(n));
const ptk_usd2 = n => (n == null ? '—' : '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const ptk_date = s => {
	if (!s) return '—';
	const d = new Date(String(s).slice(0, 10) + 'T00:00:00');
	return isNaN(d) ? ptk_esc(s) : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
};
const ptk_iso = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
const ptk_slug = dt => dt.toLowerCase().replace(/ /g, '-');

const PTK_CHIP = {
	'Completed': 'ptk-chip--done',
	'In Progress': 'ptk-chip--prog',
	'At Partner': 'ptk-chip--partner',
	'Planned': 'ptk-chip--plan',
	'Received': 'ptk-chip--done',
	'Hash only': 'ptk-chip--prog',
	'At partner': 'ptk-chip--partner',
	'In production': 'ptk-chip--partner',
};
const ptk_chip = s => '<span class="ptk-chip ' + (PTK_CHIP[s] || 'ptk-chip--plan') + '">' + ptk_esc(s) + '</span>';

frappe.pages['project-tracker'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Project Tracker'), single_column: true });
	$(wrapper).addClass('project-tracker-page');
	frappe.breadcrumbs.add('Manufacturing');
	wrapper.ptk = new ProjectTracker(page, wrapper);
};

frappe.pages['project-tracker'].on_page_show = function (wrapper) {
	if (wrapper.ptk) wrapper.ptk.on_show();
};

class ProjectTracker {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.partners = [];
		this.data = null;
		this.details = {};
		this.loading = false;
		this.state = this.read_url();
		this.$root = $('<div class="ptk"></div>').appendTo(page.main);
		this.bind();
		this.render_shell();
		frappe.call(PTK_M + 'get_partners').then(r => {
			this.partners = r.message || [];
			this.render_filters();
		});
		this.load();
	}

	// ------------------------------------------------------------ state / url

	default_period() {
		const t = new Date();
		const q = new Date(t.getFullYear(), Math.floor(t.getMonth() / 3) * 3, 1);
		return { from: ptk_iso(q), to: ptk_iso(t) };
	}

	read_url() {
		const q = frappe.utils.get_query_params() || {};
		const p = this.default_period();
		return {
			partner: q.partner || 'All',
			status: q.status || 'All',
			from: q.from || p.from,
			to: q.to || p.to,
			q: q.q || '',
			sel: q.project || null,
			tab: q.tab || 'overview',
		};
	}

	write_url() {
		const s = this.state, p = this.default_period(), out = {};
		if (s.partner !== 'All') out.partner = s.partner;
		if (s.status !== 'All') out.status = s.status;
		if (s.from !== p.from) out.from = s.from;
		if (s.to !== p.to) out.to = s.to;
		if (s.q) out.q = s.q;
		if (s.sel) out.project = s.sel;
		if (s.tab !== 'overview') out.tab = s.tab;
		const qs = new URLSearchParams(out).toString();
		window.history.replaceState(null, '', '/app/project-tracker' + (qs ? '?' + qs : ''));
	}

	filters() {
		const s = this.state;
		return { partner: s.partner, status: s.status, from_date: s.from, to_date: s.to, search: s.q };
	}

	on_show() {
		if (this.data && this.loaded_at && Date.now() - this.loaded_at > 5 * 60 * 1000) this.load();
	}

	// ------------------------------------------------------------ data

	load(refresh) {
		this.loading = true;
		this.render_list();
		if (refresh) this.details = {};
		return frappe
			.call({ method: PTK_M + 'get_tracker_summary', args: Object.assign(this.filters(), { refresh: refresh ? 1 : 0 }) })
			.then(r => {
				this.loading = false;
				this.loaded_at = Date.now();
				this.data = r.message;
				const ids = this.data.projects.map(p => p.id);
				if (!this.state.sel || !ids.includes(this.state.sel)) this.state.sel = ids[0] || null;
				this.write_url();
				this.render_all();
				if (this.state.sel) this.load_detail(this.state.sel, refresh);
			})
			.catch(() => {
				this.loading = false;
				this.render_list();
			});
	}

	load_detail(project, refresh) {
		if (this.details[project] && !refresh) {
			this.render_detail();
			return;
		}
		this.render_detail(true);
		frappe.call({ method: PTK_M + 'get_project_detail', args: { project, refresh: refresh ? 1 : 0 } }).then(r => {
			this.details[project] = r.message;
			if (this.state.sel === project) this.render_detail();
		});
	}

	// ------------------------------------------------------------ events

	bind() {
		const me = this;
		this.$root.on('click', '[data-act]', function (e) {
			const $t = $(this), act = $t.attr('data-act'), v = $t.attr('data-v');
			if (act === 'partner' || act === 'status') {
				me.state[act] = v;
				me.load();
			} else if (act === 'pick') {
				me.state.sel = v;
				me.write_url();
				me.render_list();
				me.load_detail(v);
				if (window.innerWidth < 960) me.$root.find('.ptk-detail')[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
			} else if (act === 'tab') {
				me.state.tab = v;
				me.write_url();
				me.render_detail();
			} else if (act === 'refresh') {
				me.load(true);
			} else if (act === 'export') {
				const qs = new URLSearchParams(me.filters()).toString();
				window.open('/api/method/' + PTK_M + 'export_tracker?' + qs);
			} else if (act === 'new') {
				frappe.new_doc('Project', { custom_processing_type: 'Toll' });
			} else if (act === 'open-project') {
				frappe.set_route('Form', 'Project', v);
			} else if (act === 'record-return') {
				me.record_return(v);
			} else if (act === 'add-cost') {
				me.add_cost(v);
			} else {
				return;
			}
			e.preventDefault();
		});
		this.$root.on('change', '[data-change]', function () {
			const k = $(this).attr('data-change');
			me.state[k] = $(this).val();
			me.load();
		});
		let timer = null;
		this.$root.on('input', '[data-input="q"]', function () {
			clearTimeout(timer);
			const v = $(this).val();
			timer = setTimeout(() => {
				me.state.q = v.trim();
				me.load();
			}, 350);
		});
	}

	record_return(project) {
		const d = this.details[project];
		if (!d) return;
		const row = d.row;
		frappe.new_doc('Conversion Entry', { project: project, company: d.company }, doc => {
			if (d.supplier) doc.supplier = d.supplier;
			doc.reasons = 'Tolling';
			const it = frappe.model.add_child(doc, 'items');
			if (d.partner_warehouse) {
				it.source_warehouse = d.partner_warehouse;
				it.target_warehouse = d.partner_warehouse;
			}
		});
	}

	add_cost(project) {
		const d = this.details[project];
		if (!d) return;
		frappe.new_doc('Purchase Invoice', { project: project, company: d.company, supplier: d.supplier || undefined });
	}

	// ------------------------------------------------------------ render

	render_shell() {
		this.$root.html(
			'<div class="ptk-top">' +
				'<div class="ptk-top-title">' +
				'<div class="ptk-crumb"><a href="/app/manufacturing">' + __('Manufacturing') + '</a> › ' + __('Project Tracker') + '</div>' +
				'<h1>' + __('Project Tracker') + '</h1>' +
				'</div>' +
				'<div class="ptk-top-actions">' +
				'<button class="ptk-btn" data-act="refresh">' + __('Refresh') + '</button>' +
				'<button class="ptk-btn" data-act="export">' + __('Export to Excel') + '</button>' +
				'<button class="ptk-btn ptk-btn--dark" data-act="new">+ ' + __('New Toll Project') + '</button>' +
				'</div>' +
			'</div>' +
			'<div class="ptk-main">' +
				'<div class="ptk-card ptk-filters"></div>' +
				'<div class="ptk-kpis"></div>' +
				'<div class="ptk-split">' +
					'<div class="ptk-card ptk-list"></div>' +
					'<div class="ptk-card ptk-detail"></div>' +
				'</div>' +
				'<div class="ptk-bottom">' +
					'<div class="ptk-card ptk-scorecard"></div>' +
					'<div class="ptk-card ptk-aging"></div>' +
				'</div>' +
			'</div>'
		);
		this.render_filters();
	}

	render_all() {
		this.render_filters();
		this.render_kpis();
		this.render_list();
		this.render_detail();
		this.render_scorecard();
		this.render_aging();
	}

	render_filters() {
		const s = this.state;
		const pill = (act, v, label, on) =>
			'<button class="ptk-pill' + (on ? ' is-on' : '') + '" data-act="' + act + '" data-v="' + ptk_esc(v) + '">' + ptk_esc(label) + '</button>';
		const partners = [{ value: 'All', label: __('All') }].concat(this.partners);
		const known = partners.map(p => p.value);
		if (s.partner !== 'All' && !known.includes(s.partner)) partners.push({ value: s.partner, label: s.partner });
		const $f = this.$root.find('.ptk-filters');
		const had_focus = document.activeElement && document.activeElement.getAttribute('data-input') === 'q';
		$f.html(
			'<div class="ptk-fgroup"><span class="ptk-flabel">' + __('Partner') + '</span>' +
				partners.map(p => pill('partner', p.value, p.label, s.partner === p.value)).join('') + '</div>' +
			'<div class="ptk-fgroup"><span class="ptk-flabel">' + __('Status') + '</span>' +
				[['All', __('All')], ['Active', __('Active')], ['Completed', __('Completed')]].map(x => pill('status', x[0], x[1], s.status === x[0])).join('') +
			'</div>' +
			'<div class="ptk-fgroup ptk-fgroup--right">' +
				'<label class="ptk-flabel" for="ptk-from">' + __('Period') + '</label>' +
				'<input id="ptk-from" type="date" class="ptk-input ptk-input--date" data-change="from" value="' + ptk_esc(s.from) + '" aria-label="' + __('From date') + '">' +
				'<span class="ptk-dash">–</span>' +
				'<input type="date" class="ptk-input ptk-input--date" data-change="to" value="' + ptk_esc(s.to) + '" aria-label="' + __('To date') + '">' +
				'<label class="ptk-flabel" for="ptk-q">' + __('Search') + '</label>' +
				'<input id="ptk-q" class="ptk-input ptk-input--search" data-input="q" placeholder="' + __('Project, strain or METRC tag') + '" value="' + ptk_esc(s.q) + '">' +
			'</div>'
		);
		if (had_focus) {
			const el = $f.find('[data-input="q"]')[0];
			el.focus();
			el.setSelectionRange(el.value.length, el.value.length);
		}
	}

	render_kpis() {
		const k = this.data.kpis, show_cost = this.data.show_cost;
		const card = (label, value, sub) =>
			'<div class="ptk-card ptk-kpi"><div class="ptk-kpi-label">' + label + '</div><div class="ptk-kpi-value">' + value + '</div><div class="ptk-kpi-sub">' + sub + '</div></div>';
		let h =
			card(__('FF sent'), ptk_lbs(k.ff_sent), __('{0} project(s) in view', [k.projects])) +
			card(__('Still at partner'), ptk_lbs(k.pending), __('Fresh Frozen not yet processed')) +
			card(__('Hash yield'), ptk_pct(k.hash_pct), __('Of FF washed · target {0}', [ptk_pct(k.hash_target)])) +
			card(__('Rosin yield'), ptk_pct(k.rosin_pct, 1), __('Of hash pressed · target {0}', [ptk_pct(k.rosin_target, 0)])) +
			card(__('Rosin received'), ptk_g(k.rosin), __('{0} lbs equivalent', [(k.rosin / PTK_LB).toFixed(2)]));
		if (show_cost) {
			h += card(__('Total cost'), ptk_usd(k.cost), k.cpg != null ? __('{0} per g rosin', [ptk_usd2(k.cpg)]) : __('No output yet'));
		}
		this.$root.find('.ptk-kpis').html(h);
	}

	render_list() {
		const $l = this.$root.find('.ptk-list');
		const rows = this.data ? this.data.projects : [];
		const show_cost = this.data && this.data.show_cost;
		let h =
			'<div class="ptk-list-head"><div class="ptk-h2">' + __('Projects') + '</div><div class="ptk-muted ptk-small">' +
			(this.loading ? __('Loading…') : __('{0} shown', [rows.length])) + '</div></div>';
		if (!this.data && this.loading) {
			h += '<div class="ptk-empty">' + __('Loading projects…') + '</div>';
		} else if (!rows.length) {
			h += '<div class="ptk-empty">' + __('No projects match these filters.') + '</div>';
		} else {
			h += '<div class="ptk-list-body">';
			rows.forEach(p => {
				const on = p.id === this.state.sel;
				const hp_low = p.hash_pct != null && p.hash_pct < p.hash_target;
				h +=
					'<button class="ptk-prow' + (on ? ' is-on' : '') + '" data-act="pick" data-v="' + ptk_esc(p.id) + '">' +
					'<div class="ptk-prow-top"><span class="ptk-id">' + ptk_esc(p.id) + '</span>' + ptk_chip(p.status) + '</div>' +
					'<div class="ptk-prow-name">' + ptk_esc(p.name) + '</div>' +
					'<div class="ptk-prow-meta">' + ptk_esc(p.partner) + (p.dispatch ? ' · ' + ptk_date(p.dispatch) : '') + '</div>' +
					'<div class="ptk-prow-grid' + (show_cost ? '' : ' ptk-prow-grid--3') + '">' +
					'<div><span>' + __('FF sent') + '</span><b>' + ptk_lbs(p.ff_sent) + '</b></div>' +
					'<div><span>' + __('Hash yield') + '</span><b class="' + (hp_low ? 'ptk-warn' : '') + '">' + ptk_pct(p.hash_pct) + '</b></div>' +
					'<div><span>' + __('Rosin') + '</span><b>' + (p.rosin ? ptk_g(p.rosin) : '—') + '</b></div>' +
					(show_cost ? '<div><span>' + __('Cost / g') + '</span><b>' + ptk_usd2(p.cpg) + '</b></div>' : '') +
					'</div></button>';
			});
			h += '</div>';
		}
		$l.html(h);
	}

	render_detail(loading) {
		const $d = this.$root.find('.ptk-detail');
		if (!this.data) {
			$d.html('<div class="ptk-empty ptk-empty--big">' + __('Loading…') + '</div>');
			return;
		}
		if (!this.data.projects.length) {
			$d.html('<div class="ptk-empty ptk-empty--big">' + __('Select a filter with at least one project.') + '</div>');
			return;
		}
		const d = this.details[this.state.sel];
		if (!d || loading) {
			$d.html('<div class="ptk-empty ptk-empty--big">' + __('Loading project…') + '</div>');
			return;
		}
		const r = d.row, show_cost = d.show_cost;
		const tabs = [['overview', __('Overview')], ['strains', __('Strains')]];
		if (show_cost) tabs.push(['cost', __('Cost')]);
		tabs.push(['docs', __('Documents')]);
		if (!tabs.some(t => t[0] === this.state.tab)) this.state.tab = 'overview';
		const meta = [ptk_esc(r.partner)];
		if (r.ptype === 'Toll' && d.partner_warehouse) meta.push(ptk_esc(d.partner_warehouse));
		meta.push(r.dispatch ? __('Sent {0}', [ptk_date(r.dispatch)]) : __('Not dispatched yet'));
		meta.push(r.returned ? __('Returned {0}', [ptk_date(r.returned)]) : __('Not fully returned'));

		let h =
			'<div class="ptk-dhead">' +
			'<div class="ptk-dhead-l"><div class="ptk-dhead-top"><span class="ptk-id">' + ptk_esc(r.id) + '</span>' + ptk_chip(r.status) + '</div>' +
			'<h2>' + ptk_esc(r.name) + '</h2><div class="ptk-muted ptk-13">' + meta.join(' · ') + '</div></div>' +
			'<div class="ptk-dhead-r">' +
			'<button class="ptk-btn ptk-btn--sm" data-act="record-return" data-v="' + ptk_esc(r.id) + '">' + __('Record Return') + '</button>' +
			(show_cost ? '<button class="ptk-btn ptk-btn--sm" data-act="add-cost" data-v="' + ptk_esc(r.id) + '">' + __('Add Cost') + '</button>' : '') +
			'<button class="ptk-btn ptk-btn--sm ptk-btn--blue" data-act="open-project" data-v="' + ptk_esc(r.id) + '">' + __('Open Project') + '</button>' +
			'</div></div>' +
			'<div class="ptk-tabs" role="tablist">' +
			tabs.map(t => '<button role="tab" class="ptk-tab' + (this.state.tab === t[0] ? ' is-on' : '') + '" data-act="tab" data-v="' + t[0] + '">' + t[1] + '</button>').join('') +
			'</div>';
		if (this.state.tab === 'overview') h += this.tab_overview(d);
		else if (this.state.tab === 'strains') h += this.tab_strains(d);
		else if (this.state.tab === 'cost') h += this.tab_cost(d);
		else h += this.tab_docs(d);
		$d.html(h);
	}

	tab_overview(d) {
		const r = d.row, toll = r.ptype === 'Toll';
		const chip = (good, text) => '<span class="ptk-ychip ' + (good ? 'is-good' : 'is-low') + '">' + text + '</span>';
		const overall_t = (r.hash_target * r.rosin_target) / 100;
		const sub4 = d.show_cost && d.unit_costs && d.unit_costs.per_g_rosin != null
			? __('{0} per g rosin', [ptk_usd2(d.unit_costs.per_g_rosin)])
			: (r.rosin ? __('{0} lbs rosin', [(r.rosin / PTK_LB).toFixed(2)]) : __('No rosin yet'));
		const stages = [
			[__('Fresh Frozen sent'), ptk_lbs(r.ff_sent), ptk_g(r.ff_sent * PTK_LB),
				chip(!(r.pending > 0.01), r.pending > 0.01 ? __('{0} pending', [ptk_lbs(r.pending)]) : __('All processed'))],
			[__('Hash received'), r.hash ? ptk_g(r.hash) : '—', __('From {0} washed', [ptk_lbs(r.hash_base)]),
				chip(r.hash_pct == null || r.hash_pct >= r.hash_target, __('Yield {0}', [ptk_pct(r.hash_pct)]))],
			[__('Rosin received'), r.rosin ? ptk_g(r.rosin) : '—', __('From {0} hash pressed', [ptk_g(r.hash_pressed)]),
				chip(r.rosin_pct == null || r.rosin_pct >= r.rosin_target, __('Yield {0}', [ptk_pct(r.rosin_pct, 1)]))],
			[__('Overall FF → rosin'), ptk_pct(r.overall_pct), sub4,
				chip(r.overall_pct == null || r.overall_pct >= overall_t, __('Target {0}', [ptk_pct(overall_t)]))],
		];
		let h = '<div class="ptk-pane">';
		h += '<div class="ptk-sec"><div class="ptk-sec-title">' + __('Material flow') + '</div><div class="ptk-stages">';
		stages.forEach(s => {
			h += '<div class="ptk-stage"><div class="ptk-stage-label">' + s[0] + '</div><div class="ptk-stage-value">' + s[1] + '</div><div class="ptk-muted ptk-small">' + s[2] + '</div>' + s[3] + '</div>';
		});
		h += '</div></div>';

		const recon = [
			[__('Fresh Frozen sent'), ptk_lbs(r.ff_sent)],
			[__('Processed (output received)'), ptk_lbs(r.processed)],
			[toll ? __('Still at partner (not returned)') : __('In production, not yet washed'), ptk_lbs(r.pending)],
		];
		if (r.ff_returned > 0.01) recon.push([__('Returned unprocessed'), ptk_lbs(r.ff_returned)]);
		recon.push([__('Hash received, rosin pending'), ptk_g(r.hash_waiting)]);
		recon.push([__('Expected rosin still to come (at targets)'), r.expected_rosin > 0.5 ? '≈ ' + ptk_g(r.expected_rosin) : '0 g']);
		recon.push([r.returned ? __('Turnaround') : __('Days since dispatch'), r.days == null ? '—' : __('{0} days', [r.days])]);

		const scale_h = Math.max(4, Math.ceil(Math.max(r.hash_pct || 0, r.hash_target) * 1.25));
		const bar = (val, max, low) =>
			'<div class="ptk-tbar-fill' + (low ? ' is-low' : '') + '" style="width:' + Math.max(0, Math.min(100, ((val || 0) / max) * 100)).toFixed(1) + '%"></div>';
		const mark = (t, max) => '<div class="ptk-tbar-mark" style="left:' + Math.min(100, (t / max) * 100).toFixed(1) + '%"></div>';
		const targets = [
			[__('Hash yield (of FF)'), ptk_pct(r.hash_pct), bar(r.hash_pct, scale_h, r.hash_pct != null && r.hash_pct < r.hash_target), mark(r.hash_target, scale_h),
				__('Scale 0–{0}% · marker = {1} target', [scale_h, ptk_pct(r.hash_target)])],
			[__('Rosin yield (of hash)'), ptk_pct(r.rosin_pct, 1), bar(r.rosin_pct, 100, r.rosin_pct != null && r.rosin_pct < r.rosin_target), mark(r.rosin_target, 100),
				__('Scale 0–100% · marker = {0} target', [ptk_pct(r.rosin_target, 0)])],
		];
		h += '<div class="ptk-two">';
		h += '<div class="ptk-box"><div class="ptk-box-title">' + __('Sent vs received') + '</div>' +
			recon.map(x => '<div class="ptk-recon"><span>' + x[0] + '</span><b>' + x[1] + '</b></div>').join('') + '</div>';
		h += '<div class="ptk-box ptk-box--gap"><div class="ptk-box-title">' + __('Yield vs target') + '</div>';
		targets.forEach(t => {
			h += '<div class="ptk-tg"><div class="ptk-tg-row"><span>' + t[0] + '</span><b>' + t[1] + '</b></div><div class="ptk-tbar">' + t[2] + t[3] + '</div><div class="ptk-muted ptk-small">' + t[4] + '</div></div>';
		});
		const tcol = { 'Tier 1': '#1E3A8A', 'Tier 2': '#3B82F6', 'Tier 3': '#BFDBFE', 'Untiered': '#A1A1AA' };
		h += '<div class="ptk-tg"><div class="ptk-13 ptk-sub">' + __('Rosin grade split') + '</div><div class="ptk-tiers">';
		d.tiers.forEach(t => {
			h += '<div style="width:' + (t.pct || 0).toFixed(1) + '%;background:' + tcol[t.label] + '" title="' + ptk_esc(t.label) + '"></div>';
		});
		h += '</div><div class="ptk-legend">';
		if (!d.tiers.length) h += '<span class="ptk-muted ptk-small">' + __('No rosin yet') + '</span>';
		d.tiers.forEach(t => {
			h += '<span><i style="background:' + tcol[t.label] + '"></i>' + __(t.label) + ' · ' + ptk_g(t.g) + ' (' + Math.round(t.pct || 0) + '%)</span>';
		});
		h += '</div></div></div></div>';

		h += '<div class="ptk-sec"><div class="ptk-sec-title">' + __('Exceptions') + '</div>';
		if (!d.alerts.length) {
			h += '<div class="ptk-alert is-info"><span class="ptk-atag">' + __('OK') + '</span><span>' + __('No exceptions. All strains returned and yields are within target.') + '</span></div>';
		}
		d.alerts.forEach(a => {
			h += '<div class="ptk-alert ' + (a.severity === 'warning' ? 'is-warn' : 'is-info') + '"><span class="ptk-atag">' + __(a.tag) + '</span><span>' + ptk_esc(a.text) + '</span></div>';
		});
		h += '</div></div>';
		return h;
	}

	tab_strains(d) {
		const r = d.row, toll = r.ptype === 'Toll';
		const lab_note = d.strains.some(s => s.hash_from_lab)
			? ' ' + __('Hash marked “lab” comes from the lab’s Rosin Recording, because the partner returns rosin straight from Fresh Frozen.')
			: '';
		let h = '<div class="ptk-pane ptk-pane--tight"><div class="ptk-muted ptk-13">' +
			__('One row per Fresh Frozen item. Below-target cells are marked in orange (hash target {0}, rosin target {1}).', [ptk_pct(r.hash_target), ptk_pct(r.rosin_target, 0)]) +
			lab_note + '</div>';
		h += '<div class="ptk-tablewrap"><div class="ptk-table ptk-table--strains">';
		h += '<div class="ptk-tr ptk-th"><span>' + __('Strain') + '</span><span>' + __('FF (lbs)') + '</span><span>' + __('Hash (g)') + '</span><span>' + __('Hash %') +
			'</span><span>' + __('Rosin (g)') + '</span><span>' + __('Rosin %') + '</span><span>' + __('Status') + '</span></div>';
		if (!d.strains.length) h += '<div class="ptk-empty">' + __('No Fresh Frozen recorded for this project yet.') + '</div>';
		d.strains.forEach(s => {
			const hl = s.hash_pct != null && s.hash_pct < r.hash_target;
			const rl = s.rosin_pct != null && s.rosin_pct < r.rosin_target;
			h += '<div class="ptk-tr"><span class="ptk-b" title="' + ptk_esc(s.key) + '">' + ptk_esc(s.name) + '</span>' +
				'<span>' + ptk_n0(s.lbs) + '</span>' +
				'<span>' + (s.hash ? ptk_n0(s.hash) + (s.hash_from_lab ? ' <small class="ptk-lab">' + __('lab') + '</small>' : '') : '—') + '</span>' +
				'<span class="' + (hl ? 'ptk-warn' : '') + '">' + ptk_pct(s.hash_pct) + '</span>' +
				'<span>' + (s.rosin ? ptk_n0(s.rosin) : '—') + '</span>' +
				'<span class="' + (rl ? 'ptk-warn' : '') + '">' + ptk_pct(s.rosin_pct, 1) + '</span>' +
				'<span>' + ptk_chip(s.status === 'At partner' && !toll ? 'In production' : s.status) + '</span></div>';
		});
		h += '<div class="ptk-tr ptk-tfoot"><span>' + __('Total') + '</span><span>' + ptk_n0(r.ff_sent) + '</span><span>' + ptk_n0(r.hash) + '</span><span>' + ptk_pct(r.hash_pct) +
			'</span><span>' + ptk_n0(r.rosin) + '</span><span>' + ptk_pct(r.rosin_pct, 1) + '</span><span></span></div>';
		h += '</div></div></div>';
		return h;
	}

	tab_cost(d) {
		const r = d.row, u = d.unit_costs || {};
		const units = [
			[__('Cost per g rosin'), ptk_usd2(u.per_g_rosin)],
			[__('Cost per g hash'), ptk_usd2(u.per_g_hash)],
			[__('Cost per lb FF'), ptk_usd2(u.per_lb_ff)],
			[r.ptype === 'Toll' ? __('Toll / labor per g rosin') : __('Labor / overhead per g rosin'), ptk_usd2(u.toll_per_g)],
		];
		let h = '<div class="ptk-pane"><div class="ptk-stages">';
		units.forEach(x => {
			h += '<div class="ptk-stage"><div class="ptk-stage-label">' + x[0] + '</div><div class="ptk-stage-value">' + x[1] + '</div></div>';
		});
		h += '</div><div class="ptk-costs">';
		if (!d.costs.length) h += '<div class="ptk-muted ptk-13">' + __('No costs are linked to this project yet.') + '</div>';
		d.costs.forEach(c => {
			const links = c.docs.slice(0, 6).map(x => '<a href="/app/' + ptk_slug(x.doctype) + '/' + encodeURIComponent(x.name) + '">' + ptk_esc(x.name) + '</a>').join(', ') +
				(c.docs.length > 6 ? ' ' + __('and {0} more', [c.docs.length - 6]) : '');
			h += '<div class="ptk-cost"><div class="ptk-cost-row"><span>' + ptk_esc(c.label) + '</span><b>' + ptk_usd(c.amount) + ' · ' + Math.round(c.pct || 0) + '%</b></div>' +
				'<div class="ptk-cbar"><div style="width:' + Math.max(0, Math.min(100, c.pct || 0)).toFixed(1) + '%"></div></div>' +
				(links ? '<div class="ptk-small ptk-muted">' + __('Source') + ': ' + links + '</div>' : '') + '</div>';
		});
		h += '<div class="ptk-cost"><div class="ptk-cost-row"><span class="ptk-b">' + __('Total project cost') + '</span><b>' + ptk_usd(d.cost_total) + '</b></div>' +
			'<div class="ptk-cbar"><div class="is-total" style="width:100%"></div></div></div>';
		h += '</div><div class="ptk-small ptk-muted ptk-note">' +
			(r.status === 'Completed'
				? __('All costs pulled from documents tagged with this project: stock valuation of Fresh Frozen sent, Purchase Invoices for toll fees, freight and testing, and Journal Entries for labor.')
				: __('Provisional: the full Fresh Frozen cost is included, but only part of the output has been returned, so cost per gram will fall as the remaining output arrives.')) +
			'</div></div>';
		return h;
	}

	tab_docs(d) {
		let h = '<div class="ptk-pane ptk-docs"><div class="ptk-docs-col"><div class="ptk-box-title">' + __('Linked documents') + '</div>';
		if (!d.docs.length) h += '<div class="ptk-muted ptk-13">' + __('No documents linked yet.') + '</div>';
		d.docs.forEach(x => {
			const href = x.doctype === 'File' ? x.url : '/app/' + ptk_slug(x.doctype) + '/' + encodeURIComponent(x.name);
			h += '<a class="ptk-doc" href="' + ptk_esc(href) + '"' + (x.doctype === 'File' ? ' target="_blank" rel="noopener"' : '') + '>' +
				'<span class="ptk-doc-l"><span class="ptk-small ptk-muted">' + ptk_esc(__(x.type)) + '</span><span class="ptk-doc-id">' + ptk_esc(x.label || x.name) + '</span></span>' +
				'<span class="ptk-doc-r"><span class="ptk-small ptk-muted">' + ptk_date(x.date) + '</span><span class="ptk-small ptk-b' + (x.status === 'Duplicate' ? ' ptk-warn' : '') + '">' + ptk_esc(__(x.status || '')) + '</span></span></a>';
		});
		h += '</div><div class="ptk-docs-col ptk-docs-col--tl"><div class="ptk-box-title">' + __('Timeline') + '</div>';
		if (!d.timeline.length) h += '<div class="ptk-muted ptk-13">' + __('Nothing recorded yet.') + '</div>';
		d.timeline.forEach(e => {
			h += '<div class="ptk-tl"><span class="ptk-tl-dot"></span><span class="ptk-tl-body"><span class="ptk-small ptk-muted ptk-b">' + ptk_date(e.date) + '</span><span class="ptk-13">' + ptk_esc(e.text) + '</span></span></div>';
		});
		h += '</div></div>';
		return h;
	}

	render_scorecard() {
		const rows = this.data.scorecard, show_cost = this.data.show_cost;
		let h = '<div class="ptk-bhead"><div class="ptk-h2">' + __('Partner scorecard') + '</div><div class="ptk-muted ptk-small">' +
			__('All projects in period · weighted by weight processed') + '</div></div>';
		h += '<div class="ptk-tablewrap ptk-tablewrap--flat"><div class="ptk-table ptk-table--score' + (show_cost ? '' : ' ptk-table--score-nc') + '">';
		h += '<div class="ptk-tr ptk-th"><span>' + __('Partner') + '</span><span>' + __('FF sent') + '</span><span>' + __('Hash %') + '</span><span>' + __('Rosin %') + '</span>' +
			(show_cost ? '<span>' + __('Cost / g') + '</span>' : '') + '<span>' + __('Turnaround') + '</span></div>';
		if (!rows.length) h += '<div class="ptk-empty">' + __('No projects in this period.') + '</div>';
		rows.forEach(s => {
			const target = this.data.kpis.hash_target;
			h += '<div class="ptk-tr"><span class="ptk-b">' + ptk_esc(s.partner) + ' <small class="ptk-muted">(' + s.projects + ')</small></span><span>' + ptk_lbs(s.ff) + '</span>' +
				'<span class="' + (s.hash_pct != null && s.hash_pct < target ? 'ptk-warn' : '') + '">' + ptk_pct(s.hash_pct) + '</span><span>' + ptk_pct(s.rosin_pct, 1) + '</span>' +
				(show_cost ? '<span>' + ptk_usd2(s.cpg) + '</span>' : '') + '<span>' + (s.tat == null ? '—' : __('{0} days', [Math.round(s.tat)])) + '</span></div>';
		});
		h += '</div></div>';
		this.$root.find('.ptk-scorecard').html(h);
	}

	render_aging() {
		const rows = this.data.aging, limit = this.data.pending_days;
		let h = '<div class="ptk-h2">' + __('Material still at partner') + '</div>';
		if (!rows.length) h += '<div class="ptk-muted ptk-13">' + __('Nothing pending — all material returned.') + '</div>';
		rows.forEach(g => {
			const late = (g.days || 0) > limit;
			h += '<div class="ptk-age"><div class="ptk-age-row"><a href="#" data-act="pick" data-v="' + ptk_esc(g.id) + '" class="ptk-b">' + ptk_esc(g.id) + ' · ' + ptk_esc(g.partner) + '</a>' +
				'<span class="ptk-sub">' + ptk_lbs(g.pending) + ' · ' + __('{0} days', [g.days == null ? '—' : g.days]) + '</span></div>' +
				'<div class="ptk-cbar"><div class="' + (late ? 'is-late' : '') + '" style="width:' + Math.min(100, ((g.days || 0) / (limit * 2)) * 100).toFixed(1) + '%"></div></div></div>';
		});
		h += '<div class="ptk-muted ptk-small">' + __('Bar turns orange after {0} days without a return entry.', [limit]) + '</div>';
		this.$root.find('.ptk-aging').html(h);
	}
}
