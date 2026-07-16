frappe.pages['weekly-ledger-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Weekly Ledger Dashboard',
		single_column: true
	});

	wrapper.page = page;

	var state = { salesperson: 'all', week: 'all', result: null };
	var CURRENCY = frappe.defaults.get_default('currency') || 'USD';

	function money(v) {
		return format_currency(v || 0, CURRENCY, 0);
	}
	function esc(s) {
		return frappe.utils.escape_html(s || '');
	}

	page.main.html(`
		<div class="wld">
			<div class="wld-hero">
				<div class="wld-hero-top">
					<div>
						<div class="wld-brand">MOTLEY TERPZ</div>
						<h2 class="wld-title">Weekly Cash Ledger</h2>
						<p class="wld-sub" id="wld-sub">Sales, cash &amp; collections — week by week</p>
					</div>
					<div class="wld-toggles">
						<div class="wld-pill-row" id="wld-sp-row">
							<button class="wld-pill wld-pill-active" data-sp="all">All Reps</button>
						</div>
						<div class="wld-pill-row" id="wld-week-row">
							<button class="wld-pill wld-pill-sm wld-pill-active" data-week="all">All Weeks</button>
						</div>
					</div>
				</div>
				<div class="wld-kpis" id="wld-kpis"></div>
			</div>

			<div class="wld-grid">
				<div class="wld-card wld-span2">
					<div class="wld-card-title">Week-by-Week Trend</div>
					<div id="wld-trend"></div>
				</div>
				<div class="wld-card">
					<div class="wld-card-title">Cash vs Bank <span class="wld-muted" id="wld-split-scope"></span></div>
					<div id="wld-split"></div>
				</div>
			</div>

			<div class="wld-grid">
				<div class="wld-card">
					<div class="wld-card-title">Product Targets vs Actual</div>
					<div id="wld-cats"></div>
				</div>
				<div class="wld-card wld-span2">
					<div class="wld-card-title">Money Lines <span class="wld-muted" id="wld-lines-count"></span></div>
					<div class="wld-table-wrap" id="wld-lines"></div>
				</div>
			</div>

			<div id="wld-loading" class="wld-loading"><div class="wld-spinner"></div></div>
		</div>
	`);

	function load() {
		page.main.find('#wld-loading').show();
		frappe.call({
			method: 'cannabis_management.cannabis_management.page.weekly_ledger_dashboard.weekly_ledger_dashboard.get_dashboard',
			args: { salesperson: state.salesperson, week: state.week },
			callback: function (r) {
				if (!r.message) return;
				state.result = r.message;
				render();
			},
			always: function () {
				page.main.find('#wld-loading').hide();
			}
		});
	}

	function render() {
		var res = state.result;
		render_toggles(res);
		render_kpis(res.kpis);
		render_charts(res);
		render_categories(res.categories, res.kpis);
		render_lines(res.lines);

		var who = state.salesperson === 'all' ? 'All reps' : state.salesperson;
		var when = state.week === 'all' ? 'all weeks' : 'week of ' + week_label(state.week);
		page.main.find('#wld-sub').text(who + ' — ' + when);
	}

	function week_label(key) {
		var w = (state.result.weeks || []).find(function (x) { return x.key === key; });
		return w ? w.label : key;
	}

	function render_toggles(res) {
		var sp_row = page.main.find('#wld-sp-row');
		sp_row.find('[data-sp]').not('[data-sp="all"]').remove();
		(res.salespersons || []).forEach(function (sp) {
			sp_row.append(`<button class="wld-pill" data-sp="${esc(sp)}">${esc(sp.split(' ')[0])}</button>`);
		});
		sp_row.find('.wld-pill').removeClass('wld-pill-active');
		sp_row.find(`[data-sp="${state.salesperson}"]`).addClass('wld-pill-active');
		sp_row.find('.wld-pill').off('click').on('click', function () {
			state.salesperson = $(this).data('sp');
			state.week = 'all';
			load();
		});

		var wk_row = page.main.find('#wld-week-row');
		wk_row.find('[data-week]').not('[data-week="all"]').remove();
		(res.weeks || []).forEach(function (w) {
			wk_row.append(`<button class="wld-pill wld-pill-sm" data-week="${esc(w.key)}">${esc(w.label)}</button>`);
		});
		wk_row.find('.wld-pill').removeClass('wld-pill-active');
		wk_row.find(`[data-week="${state.week}"]`).addClass('wld-pill-active');
		wk_row.find('.wld-pill').off('click').on('click', function () {
			state.week = String($(this).data('week'));
			load();
		});
	}

	function render_kpis(k) {
		var target = k.sales_target_total || 0;
		var pct = target ? Math.min(100, Math.round(k.sales_written_total / target * 100)) : 0;
		page.main.find('#wld-kpis').html(`
			<div class="wld-kpi">
				<div class="wld-kpi-label">Total Coming In</div>
				<div class="wld-kpi-value">${money(k.coming_in_total)}</div>
				<div class="wld-kpi-sub">
					<span class="wld-tag wld-tag-cash">Cash ${money(k.coming_in_cash)}</span>
					<span class="wld-tag wld-tag-bank">Bank ${money(k.coming_in_bank)}</span>
				</div>
			</div>
			<div class="wld-kpi">
				<div class="wld-kpi-label">Already Collected</div>
				<div class="wld-kpi-value wld-green">${money(k.collected_total)}</div>
				<div class="wld-kpi-sub">
					<span class="wld-tag wld-tag-cash">Cash ${money(k.collected_cash)}</span>
					<span class="wld-tag wld-tag-bank">Bank ${money(k.collected_bank)}</span>
				</div>
			</div>
			<div class="wld-kpi">
				<div class="wld-kpi-label">Still Coming</div>
				<div class="wld-kpi-value wld-amber">${money(k.expected_total)}</div>
				<div class="wld-kpi-sub">expected but not yet in</div>
			</div>
			<div class="wld-kpi">
				<div class="wld-kpi-label">Sales Written vs Target</div>
				<div class="wld-kpi-value">${money(k.sales_written_total)}</div>
				<div class="wld-progress"><div class="wld-progress-fill" style="width:${pct}%"></div></div>
				<div class="wld-kpi-sub">${pct}% of ${money(target)} &middot; COD ${money(k.sales_cod)} / Terms ${money(k.sales_terms)}</div>
			</div>
			<div class="wld-kpi">
				<div class="wld-kpi-label">AR Collecting</div>
				<div class="wld-kpi-value">${money(k.ar_total)}</div>
				<div class="wld-kpi-sub">${money(k.ar_collected)} in &middot; ${money(k.ar_expected)} expected</div>
			</div>
		`);
	}

	function render_charts(res) {
		if (typeof frappe.Chart === 'undefined') return;

		var t = res.trend;
		page.main.find('#wld-trend').empty();
		if (t.labels.length) {
			new frappe.Chart('#wld-trend', {
				type: 'bar',
				height: 250,
				colors: ['#10b981', '#f59e0b', '#7c3aed'],
				data: {
					labels: t.labels,
					datasets: [
						{ name: 'Collected', values: t.collected },
						{ name: 'Still Coming', values: t.expected },
						{ name: 'Sales Written', values: t.sales_written }
					]
				},
				barOptions: { spaceRatio: 0.4 },
				tooltipOptions: { formatTooltipY: function (v) { return money(v); } }
			});
		} else {
			page.main.find('#wld-trend').html('<div class="wld-empty">No ledgers yet</div>');
		}

		var k = res.kpis;
		page.main.find('#wld-split-scope').text(state.week === 'all' ? '· all weeks' : '· ' + week_label(state.week));
		page.main.find('#wld-split').empty();
		if (k.coming_in_total > 0) {
			new frappe.Chart('#wld-split', {
				type: 'donut',
				height: 250,
				colors: ['#10b981', '#3b82f6'],
				data: {
					labels: ['Cash', 'Bank'],
					datasets: [{ values: [Math.round(k.coming_in_cash), Math.round(k.coming_in_bank)] }]
				}
			});
		} else {
			page.main.find('#wld-split').html('<div class="wld-empty">No money in scope</div>');
		}
	}

	function render_categories(cats, kpis) {
		var el = page.main.find('#wld-cats');
		if (!cats || !cats.length) {
			el.html('<div class="wld-empty">No targets in scope</div>');
			return;
		}
		var html = '';
		cats.forEach(function (c) {
			var target = flt(c.target_amount), actual = flt(c.actual_amount);
			var pct = target ? Math.min(100, Math.round(actual / target * 100)) : (actual ? 100 : 0);
			var cls = pct >= 100 ? 'wld-bar-green' : pct >= 50 ? 'wld-bar-amber' : 'wld-bar-red';
			html += `
				<div class="wld-cat">
					<div class="wld-cat-head">
						<span class="wld-cat-name">${esc(c.category)}</span>
						<span class="wld-cat-nums">${money(actual)} <span class="wld-muted">/ ${money(target)}</span></span>
					</div>
					<div class="wld-progress wld-progress-lg"><div class="wld-progress-fill ${cls}" style="width:${pct}%"></div></div>
				</div>`;
		});
		el.html(html);
	}

	function render_lines(lines) {
		var el = page.main.find('#wld-lines');
		page.main.find('#wld-lines-count').text('· ' + (lines || []).length + ' rows');
		if (!lines || !lines.length) {
			el.html('<div class="wld-empty">No lines in scope</div>');
			return;
		}
		var rows = lines.map(function (l) {
			var method_cls = l.method === 'Cash' ? 'wld-tag-cash' : 'wld-tag-bank';
			var status_cls = l.status === 'Collected' ? 'wld-pill-green' : 'wld-pill-amber';
			return `<tr>
				<td class="wld-muted">${esc(l.week_label)}</td>
				<td><span class="wld-type wld-type-${l.entry_type === 'AR' ? 'ar' : 'sales'}">${esc(l.entry_type)}</span></td>
				<td class="wld-strong">${esc(l.account_name || l.customer || '—')}</td>
				<td>${esc(l.category || '—')}</td>
				<td class="wld-num">${money(l.value)}</td>
				<td><span class="wld-tag ${method_cls}">${esc(l.method)}</span></td>
				<td>${esc(l.terms)}</td>
				<td><span class="wld-status ${status_cls}">${esc(l.status)}</span></td>
				<td class="wld-muted">${esc(l.notes || '')}</td>
			</tr>`;
		}).join('');
		el.html(`
			<table class="wld-table">
				<thead><tr>
					<th>Week</th><th>Type</th><th>Account</th><th>Category</th>
					<th class="wld-num">Amount</th><th>Method</th><th>Terms</th><th>Status</th><th>Notes</th>
				</tr></thead>
				<tbody>${rows}</tbody>
			</table>
		`);
	}

	load();
};
