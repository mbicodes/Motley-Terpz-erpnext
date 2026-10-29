var ctd_vault_seq = 0;
function vault_svg(cls) {
	var id = 'ctdGold' + (++ctd_vault_seq);
	return `<svg class="ctd-vault-logo ${cls || ''}" viewBox="0 0 64 64" aria-hidden="true">
		<defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1">
			<stop offset="0" stop-color="#fde68a"/><stop offset=".5" stop-color="#d4a72c"/><stop offset="1" stop-color="#8a6512"/>
		</linearGradient></defs>
		<rect x="5" y="5" width="54" height="50" rx="9" fill="#1f2430" stroke="url(#${id})" stroke-width="3"/>
		<rect x="11" y="55" width="10" height="5" rx="2" fill="url(#${id})"/>
		<rect x="43" y="55" width="10" height="5" rx="2" fill="url(#${id})"/>
		<circle cx="30" cy="30" r="15" fill="#2b3240" stroke="url(#${id})" stroke-width="2.5"/>
		<g stroke="url(#${id})" stroke-width="2.5" stroke-linecap="round">
			<line x1="30" y1="18" x2="30" y2="42"/><line x1="18" y1="30" x2="42" y2="30"/>
			<line x1="21.5" y1="21.5" x2="38.5" y2="38.5"/><line x1="38.5" y1="21.5" x2="21.5" y2="38.5"/>
		</g>
		<circle cx="30" cy="30" r="4.5" fill="url(#${id})"/>
		<rect x="50" y="19" width="4" height="22" rx="2" fill="url(#${id})"/>
	</svg>`;
}

frappe.pages['cash-tracking-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Cash Tracking',
		single_column: true
	});

	wrapper.page = page;
	var state = {
		tracker: 'personal',
		person: '',
		is_admin: false,
		can_mark_processed: false,
		from_date: '',
		to_date: '',
		rows: [],
		col_filters: {},
		shown: []
	};
	page._state = state;

	page.main.html(`
		<div class="ctd-container">
			<div class="ctd-header">
				<div class="ctd-heading">
					<h2 class="ctd-title">Cash Tracking</h2>
					<p class="ctd-subtitle" id="ctd-subtitle">Cash entries</p>
				</div>
				<div class="ctd-safe-title">
					${vault_svg('ctd-safe-title-logo')}
					<div>
						<h2 class="ctd-safe-name">The Safe</h2>
						<p class="ctd-safe-sub">Cash going into and coming out of the safe</p>
					</div>
				</div>
				<div class="ctd-actions">
					<button class="ctd-refresh ctd-new" id="ctd-new-motley" title="New Motley Cash Tracking" style="display:none;">
						<span class="ctd-refresh-icon">&#43;</span> Motley Cash
					</button>
					<button class="ctd-refresh ctd-new" id="ctd-new-tsbc" title="New TSBC Cash Tracking" style="display:none;">
						<span class="ctd-refresh-icon">&#43;</span> TSBC Cash
					</button>
					<button class="ctd-refresh ctd-new ctd-new-safe" id="ctd-new-safe" title="New Safe Cash Tracking" style="display:none;">
						${vault_svg('ctd-btn-logo')} <span class="ctd-refresh-icon">&#43;</span> Safe Cash
					</button>
					<button class="ctd-refresh ctd-new" id="ctd-new-personal" title="New Personal Cash Tracking">
						<span class="ctd-refresh-icon">&#43;</span> Personal Cash
					</button>
					<button class="ctd-refresh" id="ctd-export" title="Export the rows shown to CSV (receipts not included)">
						<span class="ctd-refresh-icon">&#8615;</span> Export CSV
					</button>
					<button class="ctd-refresh" id="ctd-refresh" title="Refresh">
						<span class="ctd-refresh-icon">&#8635;</span> Refresh
					</button>
				</div>
			</div>

			<div class="ctd-filter-bar">
				<div class="ctd-filter-group">
					<label class="ctd-label">Tracker</label>
					<div class="ctd-toggle" id="ctd-tracker-toggle">
						<button class="ctd-toggle-btn" data-val="motley" id="ctd-toggle-motley" style="display:none;">Motley</button>
						<button class="ctd-toggle-btn" data-val="tsbc" id="ctd-toggle-tsbc" style="display:none;">TSBC</button>
						<button class="ctd-toggle-btn ctd-active" data-val="personal">Personal</button>
					</div>
				</div>
				<div class="ctd-filter-group" id="ctd-person-group">
					<label class="ctd-label">User</label>
					<select id="ctd-person" class="ctd-select"></select>
				</div>
				<div class="ctd-filter-group">
					<label class="ctd-label">From</label>
					<input type="date" id="ctd-from" class="ctd-input" />
				</div>
				<div class="ctd-filter-group">
					<label class="ctd-label">To</label>
					<input type="date" id="ctd-to" class="ctd-input" />
				</div>
				<div class="ctd-filter-group ctd-safe-slot" id="ctd-safe-group" style="display:none;">
					<label class="ctd-label">Vault</label>
					<button class="ctd-safe-btn" id="ctd-toggle-safe" data-val="safe" title="Open the Safe">
						${vault_svg('ctd-safe-btn-logo')}<span>Safe</span>
					</button>
				</div>
			</div>

			<div class="ctd-cards">
				<div class="ctd-card ctd-card-in">
					<div class="ctd-card-label">Money In</div>
					<div class="ctd-card-value" id="ctd-total-in">$0.00</div>
				</div>
				<div class="ctd-card ctd-card-out">
					<div class="ctd-card-label">Money Out</div>
					<div class="ctd-card-value" id="ctd-total-out">$0.00</div>
				</div>
				<div class="ctd-card ctd-card-net">
					<div class="ctd-card-label">Net</div>
					<div class="ctd-card-value" id="ctd-total-net">$0.00</div>
				</div>
				<div class="ctd-card ctd-card-count">
					<div class="ctd-card-label">Entries</div>
					<div class="ctd-card-value" id="ctd-total-count">0</div>
				</div>
			</div>

			<div class="ctd-table-wrap">
				<table class="ctd-table">
					<thead>
						<tr>
							<th>Date</th>
							<th>ID</th>
							<th>Tracker</th>
							<th class="ctd-col-user">User</th>
							<th>Type</th>
							<th>Transaction Notes</th>
							<th>Business</th>
							<th>Sales Order</th>
							<th class="ctd-num">Money In</th>
							<th class="ctd-num">Money Out</th>
							<th>Status</th>
							<th class="ctd-col-processed">Processed</th>
						</tr>
						<tr class="ctd-filter-row">
							<th><input class="ctd-col-filter" data-key="date" placeholder="Filter"></th>
							<th><input class="ctd-col-filter" data-key="name" placeholder="Filter"></th>
							<th><input class="ctd-col-filter" data-key="tracker" placeholder="Filter"></th>
							<th class="ctd-col-user"><input class="ctd-col-filter" data-key="person" placeholder="Filter"></th>
							<th><input class="ctd-col-filter" data-key="category" placeholder="Filter"></th>
							<th><input class="ctd-col-filter" data-key="notes" placeholder="Filter"></th>
							<th><input class="ctd-col-filter" data-key="business" placeholder="Filter"></th>
							<th><input class="ctd-col-filter" data-key="sales_order" placeholder="Filter"></th>
							<th><input class="ctd-col-filter ctd-num" data-key="money_in" placeholder="e.g. >100" title="Number, or >, <, >=, <=, = followed by a number"></th>
							<th><input class="ctd-col-filter ctd-num" data-key="money_out" placeholder="e.g. >100" title="Number, or >, <, >=, <=, = followed by a number"></th>
							<th><input class="ctd-col-filter" data-key="status" placeholder="Filter"></th>
							<th class="ctd-col-processed">
								<select class="ctd-col-filter" data-key="processed">
									<option value="">All</option>
									<option value="yes">Yes</option>
									<option value="no">No</option>
								</select>
							</th>
						</tr>
					</thead>
					<tbody id="ctd-tbody"></tbody>
				</table>
				<div class="ctd-empty" id="ctd-empty" style="display:none;">
					<div class="ctd-empty-icon">&#128179;</div>
					<div>No cash tracking entries for the selected filters.</div>
				</div>
			</div>
		</div>
	`);

	function fmt_money(v) {
		v = v || 0;
		return (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('en-US', {
			minimumFractionDigits: 2, maximumFractionDigits: 2
		});
	}

	function esc(s) { return frappe.utils.escape_html(s == null ? '' : String(s)); }

	function status_badge(s) {
		var cls = 'ctd-badge ctd-badge-' + (s || 'Draft').toLowerCase();
		return '<span class="' + cls + '">' + esc(s || 'Draft') + '</span>';
	}

	function tracker_badge(t) {
		var cls = 'ctd-tag ctd-tag-' + t.toLowerCase();
		return '<span class="' + cls + '">' + esc(t) + '</span>';
	}

	function show_motley(allowed) {
		$('#ctd-toggle-motley').toggle(!!allowed);
		if (!allowed && state.tracker === 'motley') {
			select_tracker('personal');
		}
	}

	function show_tsbc(allowed) {
		$('#ctd-toggle-tsbc').toggle(!!allowed);
		if (!allowed && state.tracker === 'tsbc') {
			select_tracker('personal');
		}
	}

	function show_safe(allowed) {
		$('#ctd-safe-group').toggle(!!allowed);
		if (!allowed && state.tracker === 'safe') {
			select_tracker('personal');
		}
	}

	function select_tracker(val) {
		state.tracker = val;
		$('#ctd-tracker-toggle .ctd-toggle-btn').removeClass('ctd-active');
		$('#ctd-tracker-toggle .ctd-toggle-btn[data-val="' + val + '"]').addClass('ctd-active');
		set_safe_mode(val === 'safe');
		$('.ctd-actions .ctd-new').hide();
		$('#ctd-new-' + val).show();
	}

	function set_safe_mode(on) {
		var $c = page.main.find('.ctd-container');
		var entering = on && !$c.hasClass('ctd-safe-mode');
		$c.toggleClass('ctd-safe-mode', on);
		$('body').toggleClass('ctd-safe-body', on);
		$('#ctd-toggle-safe').toggleClass('ctd-safe-on', on);
		if (entering) play_vault_door($c);
		if (!on) $c.find('.ctd-vault-overlay').remove();
	}

	function play_vault_door($c) {
		if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
		$c.find('.ctd-vault-overlay').remove();
		$c.removeClass('ctd-safe-entering');
		void $c[0].offsetWidth;
		$c.addClass('ctd-safe-entering');
		var $overlay = $(`
			<div class="ctd-vault-overlay" aria-hidden="true">
				<div class="ctd-vault-glow"></div>
				<div class="ctd-vault-frame">
					<div class="ctd-vault-door">
						<div class="ctd-vault-bolts"></div>
						<svg class="ctd-vault-wheel" viewBox="0 0 100 100">
							<circle cx="50" cy="50" r="30" fill="none" stroke="#d4a72c" stroke-width="5"/>
							<g stroke="#e9c766" stroke-width="5" stroke-linecap="round">
								<line x1="50" y1="8" x2="50" y2="92"/><line x1="8" y1="50" x2="92" y2="50"/>
								<line x1="20" y1="20" x2="80" y2="80"/><line x1="80" y1="20" x2="20" y2="80"/>
							</g>
							<circle cx="50" cy="50" r="11" fill="#d4a72c" stroke="#8a6512" stroke-width="2"/>
						</svg>
					</div>
				</div>
				<div class="ctd-vault-caption">Opening the Safe</div>
			</div>`);
		$c.append($overlay);
		setTimeout(function () { $overlay.remove(); }, 2000);
		setTimeout(function () { $c.removeClass('ctd-safe-entering'); }, 3200);
	}

	function processed_cell(r) {
		if (!state.can_mark_processed) return '';
		var checked = r.processed ? ' checked' : '';
		var title = r.processed && r.processed_by
			? esc(r.processed_by) + (r.processed_on ? ' · ' + esc(frappe.datetime.str_to_user(r.processed_on)) : '')
			: __('Mark as processed');
		return '<label class="ctd-processed" title="' + title + '">' +
			'<input type="checkbox" class="ctd-processed-box" data-name="' + esc(r.name) +
			'" data-tracker="' + esc(r.tracker.toLowerCase()) + '"' + checked + '>' +
			'</label>';
	}

	function apply_processed_visibility() {
		$('.ctd-col-processed').toggle(!!state.can_mark_processed);
	}

	function doctype_of(tracker) {
		if (tracker === 'Personal') return 'Personal Cash Tracking';
		if (tracker === 'TSBC') return 'TSBC Cash Tracking';
		if (tracker === 'Safe') return 'Safe Cash Tracking';
		return 'Motley Cash Tracking';
	}

	function render(result) {
		if (typeof result.can_mark_processed !== 'undefined') {
			state.can_mark_processed = !!result.can_mark_processed;
		}
		if (result.tracker && result.tracker !== state.tracker) {
			select_tracker(result.tracker);
		}
		state.rows = result.rows || [];
		draw();
	}

	var FILTER_TEXT = {
		date: function (r) { return (frappe.datetime.str_to_user(r.date) || '') + ' ' + (r.date || ''); },
		name: function (r) { return r.name; },
		tracker: function (r) { return r.tracker; },
		person: function (r) { return r.person || r.user; },
		category: function (r) { return r.category; },
		notes: function (r) { return r.notes; },
		business: function (r) { return r.business; },
		sales_order: function (r) { return r.sales_order; },
		status: function (r) { return r.status; }
	};

	function match_amount(value, query) {
		var m = query.replace(/[$,\s]/g, '').match(/^(>=|<=|>|<|=)?(-?\d*\.?\d+)$/);
		if (!m) return false;
		var n = parseFloat(m[2]), v = flt(value);
		switch (m[1]) {
			case '>': return v > n;
			case '<': return v < n;
			case '>=': return v >= n;
			case '<=': return v <= n;
			default: return v === n;
		}
	}

	function row_matches(r) {
		return Object.keys(state.col_filters).every(function (key) {
			var q = (state.col_filters[key] || '').trim().toLowerCase();
			if (!q) return true;
			if (key === 'money_in' || key === 'money_out') return match_amount(r[key], q);
			if (key === 'processed') return (q === 'yes') === !!r.processed;
			return String(FILTER_TEXT[key](r) || '').toLowerCase().indexOf(q) !== -1;
		});
	}

	function draw() {
		var rows = state.shown = state.rows.filter(row_matches);
		var money_in = 0, money_out = 0;
		rows.forEach(function (r) { money_in += flt(r.money_in); money_out += flt(r.money_out); });
		$('#ctd-total-in').text(fmt_money(money_in));
		$('#ctd-total-out').text(fmt_money(money_out));
		var net = money_in - money_out;
		var $net = $('#ctd-total-net').text(fmt_money(net));
		$net.closest('.ctd-card-net').toggleClass('ctd-negative', net < 0);
		$('#ctd-total-count').text(rows.length);

		var $body = $('#ctd-tbody').empty();
		apply_processed_visibility();
		if (!rows.length) {
			$('#ctd-empty').show();
			return;
		}
		$('#ctd-empty').hide();

		rows.forEach(function (r) {
			var link = '/app/' + frappe.router.slug(doctype_of(r.tracker)) + '/' + encodeURIComponent(r.name);
			var so_cell = r.sales_order
				? '<a href="/app/sales-order/' + encodeURIComponent(r.sales_order) + '" class="ctd-link">' + esc(r.sales_order) + '</a>'
				: '';
			var tr = `
				<tr>
					<td>${esc(frappe.datetime.str_to_user(r.date) || r.date || '')}</td>
					<td><a href="${link}" class="ctd-link">${esc(r.name)}</a></td>
					<td>${tracker_badge(r.tracker)}</td>
					<td class="ctd-col-user">${esc(r.person || r.user || '')}</td>
					<td class="ctd-cat">${esc(r.category || '')}</td>
					<td class="ctd-notes" title="${esc(r.notes || '')}">${esc(r.notes || '')}</td>
					<td>${esc(r.business || '')}</td>
					<td>${so_cell}</td>
					<td class="ctd-num ctd-in">${r.money_in ? fmt_money(r.money_in) : ''}</td>
					<td class="ctd-num ctd-out">${r.money_out ? fmt_money(r.money_out) : ''}</td>
					<td>${status_badge(r.status)}</td>
					<td class="ctd-col-processed">${processed_cell(r)}</td>
				</tr>`;
			$body.append(tr);
		});
		apply_processed_visibility();
	}

	function export_csv() {
		if (!state.shown.length) {
			frappe.msgprint(__('There are no rows to export.'));
			return;
		}
		var processed = state.can_mark_processed;
		var header = ['Date', 'ID', 'Tracker', 'Cash Tracker Person', 'User', 'Employee',
			'Transaction Type', 'Transaction Notes', 'Business', 'Sales Order',
			'Money In', 'Money Out', 'Status'];
		if (processed) header.push('Processed', 'Processed By', 'Processed On');

		var data = [header];
		state.shown.forEach(function (r) {
			var line = [
				frappe.datetime.str_to_user(r.date) || r.date || '', r.name, r.tracker,
				r.person || '', r.user || '', r.employee || '',
				r.category || '', r.notes || '', r.business || '', r.sales_order || '',
				flt(r.money_in), flt(r.money_out), r.status || ''
			];
			if (processed) {
				line.push(r.processed ? 'Yes' : 'No', r.processed_by || '',
					r.processed_on ? frappe.datetime.str_to_user(r.processed_on) : '');
			}
			data.push(line);
		});
		var tracker = { motley: 'Motley', tsbc: 'TSBC', safe: 'Safe' }[state.tracker] || 'Personal';
		frappe.tools.downloadify(data, null,
			'Cash Tracking - ' + tracker + ' - ' + frappe.datetime.get_today());
	}

	function load() {
		frappe.call({
			method: 'cannabis_management.cash_management.page.cash_tracking_dashboard.cash_tracking_dashboard.get_entries',
			args: {
				tracker: state.tracker,
				person: state.person,
				from_date: state.from_date,
				to_date: state.to_date
			},
			freeze: false,
			callback: function (r) {
				if (r.message) { render(r.message); }
			}
		});
	}

	function load_persons() {
		frappe.call({
			method: 'cannabis_management.cash_management.page.cash_tracking_dashboard.cash_tracking_dashboard.get_persons',
			callback: function (r) {
				var data = r.message || {};
				state.is_admin = !!data.is_admin;
				state.allow_motley = !!data.allow_motley;
				show_motley(state.allow_motley);
				state.allow_tsbc = !!data.allow_tsbc;
				show_tsbc(state.allow_tsbc);
				state.allow_safe = !!data.allow_safe;
				show_safe(state.allow_safe);

				var persons = data.persons || [];
				var shared = data.shared || [];
				var $sel = $('#ctd-person').empty();

				if (state.is_admin) {
					$sel.append('<option value="">All Users</option>');
				} else if (shared.length) {
					$sel.append('<option value="">Mine + shared</option>');
				}

				persons.forEach(function (p) {
					var is_shared = shared.indexOf(p.name) !== -1;
					$sel.append('<option value="' + esc(p.name) + '">' +
						esc(p.full_name || p.name) + (is_shared ? ' (shared)' : '') + '</option>');
				});

				if (state.is_admin) {
					$('#ctd-subtitle').text('All users — cash entries');
				} else if (shared.length) {
					$sel.prop('disabled', false);
					state.person = '';
					$sel.val('');
					$('#ctd-subtitle').text('Your cash entries, plus ' + shared.length +
						' shared with you');
				} else {
					if (persons.length) {
						state.person = persons[0].name;
						$sel.val(state.person);
					}
					$sel.prop('disabled', true);
					$('#ctd-subtitle').text('Your cash entries');
				}
				load();
			}
		});
	}

	$('#ctd-toggle-safe').on('click', function () {
		if (!state.allow_safe || state.tracker === 'safe') { return; }
		select_tracker('safe');
		load();
	});

	$('#ctd-tracker-toggle').on('click', '.ctd-toggle-btn', function () {
		var val = $(this).data('val');
		if (val === 'motley' && !state.allow_motley) { return; }
		if (val === 'tsbc' && !state.allow_tsbc) { return; }
		if (val === 'safe' && !state.allow_safe) { return; }
		select_tracker(val);
		load();
	});

	$('#ctd-person').on('change', function () {
		if ($(this).prop('disabled')) { return; }
		state.person = $(this).val();
		load();
	});

	$('#ctd-from').on('change', function () { state.from_date = $(this).val(); load(); });
	$('#ctd-to').on('change', function () { state.to_date = $(this).val(); load(); });
	page.main.on('change', '.ctd-processed-box', function () {
		var $box = $(this);
		var name = $box.data('name');
		var tracker = $box.data('tracker');
		var value = $box.is(':checked') ? 1 : 0;
		var row = state.rows.find(function (r) { return r.name === name; });

		$box.prop('disabled', true);
		frappe.call({
			method: 'cannabis_management.cash_management.page.cash_tracking_dashboard.cash_tracking_dashboard.set_processed',
			args: { tracker: tracker, name: name, processed: value },
			callback: function (r) {
				$box.prop('disabled', false);
				if (row) {
					row.processed = value;
					row.processed_by = r.message ? r.message.processed_by : null;
				}
				frappe.show_alert({
					message: value ? __('{0} marked processed', [name]) : __('{0} unmarked', [name]),
					indicator: value ? 'green' : 'orange'
				}, 3);
			},
			error: function () {
				$box.prop('disabled', false).prop('checked', !value);
			}
		});
	});

	page.main.on('input change', '.ctd-col-filter', frappe.utils.debounce(function () {
		$('.ctd-col-filter').each(function () {
			state.col_filters[$(this).data('key')] = $(this).val();
		});
		draw();
	}, 200));

	$('#ctd-export').on('click', export_csv);
	$('#ctd-refresh').on('click', function () { load(); });
	$('#ctd-new-motley').on('click', function () { frappe.new_doc('Motley Cash Tracking'); });
	$('#ctd-new-tsbc').on('click', function () { frappe.new_doc('TSBC Cash Tracking'); });
	$('#ctd-new-safe').on('click', function () { frappe.new_doc('Safe Cash Tracking'); });
	$('#ctd-new-personal').on('click', function () { frappe.new_doc('Personal Cash Tracking'); });
	function apply_route_options() {
		var opts = frappe.route_options || {};
		frappe.route_options = null;
		if (opts.tracker && opts.tracker !== 'all') { state.tracker = opts.tracker; }
		if (opts.from_date) { state.from_date = opts.from_date; }
		if (opts.to_date) { state.to_date = opts.to_date; }

		select_tracker(state.tracker);
		$('#ctd-from').val(state.from_date || '');
		$('#ctd-to').val(state.to_date || '');
	}

	$(wrapper).on('hide', function () { $('body').removeClass('ctd-safe-body'); });
	$(wrapper).on('show', function () { $('body').toggleClass('ctd-safe-body', state.tracker === 'safe'); });

	page.apply_route_options = apply_route_options;
	page.reload_data = load;

	apply_route_options();
	load_persons();
};

frappe.pages['cash-tracking-dashboard'].on_page_show = function (wrapper) {
	var page = wrapper.page;
	if (page && page.apply_route_options && frappe.route_options) {
		page.apply_route_options();
		page.reload_data();
	}
};
