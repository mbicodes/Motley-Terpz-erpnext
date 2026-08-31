frappe.pages['cash-tracking-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Cash Tracking',
		single_column: true
	});

	wrapper.page = page;
	var state = {
		tracker: 'personal',   // 'motley' requires Allow For Motley on the person
		person: '',       // '' = all (admins only)
		is_admin: false,
		from_date: '',
		to_date: '',
		rows: []
	};
	page._state = state;

	page.main.html(`
		<div class="ctd-container">
			<div class="ctd-header">
				<div>
					<h2 class="ctd-title">Cash Tracking</h2>
					<p class="ctd-subtitle" id="ctd-subtitle">Cash entries</p>
				</div>
				<div class="ctd-actions">
					<button class="ctd-refresh ctd-new" id="ctd-new-motley" title="New Motley Cash Tracking" style="display:none;">
						<span class="ctd-refresh-icon">&#43;</span> Motley Cash
					</button>
					<button class="ctd-refresh ctd-new" id="ctd-new-personal" title="New Personal Cash Tracking">
						<span class="ctd-refresh-icon">&#43;</span> Personal Cash
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
							<th class="ctd-num">Money In</th>
							<th class="ctd-num">Money Out</th>
							<th>Status</th>
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

	// ---- helpers -------------------------------------------------------
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

	// "Allow For Motley" on the Cash Tracker Person decides whether the Motley
	// half of this page exists at all for the current user. The server enforces
	// it in get_entries; this only keeps the UI from offering a dead option.
	function show_motley(allowed) {
		$('#ctd-toggle-motley').toggle(!!allowed);
		$('#ctd-new-motley').toggle(!!allowed);
		if (!allowed && state.tracker === 'motley') {
			select_tracker('personal');
		}
	}

	function select_tracker(val) {
		state.tracker = val;
		$('#ctd-tracker-toggle .ctd-toggle-btn').removeClass('ctd-active');
		$('#ctd-tracker-toggle .ctd-toggle-btn[data-val="' + val + '"]').addClass('ctd-active');
	}

	function doctype_of(tracker) {
		return tracker === 'Personal' ? 'Personal Cash Tracking' : 'Motley Cash Tracking';
	}

	// ---- rendering -----------------------------------------------------
	function render(result) {
		if (result.tracker && result.tracker !== state.tracker) {
			select_tracker(result.tracker);   // server refused Motley
		}
		state.rows = result.rows || [];
		var t = result.totals || {};
		$('#ctd-total-in').text(fmt_money(t.money_in));
		$('#ctd-total-out').text(fmt_money(t.money_out));
		var net = t.net || 0;
		var $net = $('#ctd-total-net').text(fmt_money(net));
		$net.closest('.ctd-card-net').toggleClass('ctd-negative', net < 0);
		$('#ctd-total-count').text(t.count || 0);

		var $body = $('#ctd-tbody').empty();
		if (!state.rows.length) {
			$('#ctd-empty').show();
			return;
		}
		$('#ctd-empty').hide();

		state.rows.forEach(function (r) {
			var link = '/app/' + frappe.router.slug(doctype_of(r.tracker)) + '/' + encodeURIComponent(r.name);
			var tr = `
				<tr>
					<td>${esc(frappe.datetime.str_to_user(r.date) || r.date || '')}</td>
					<td><a href="${link}" class="ctd-link">${esc(r.name)}</a></td>
					<td>${tracker_badge(r.tracker)}</td>
					<td class="ctd-col-user">${esc(r.person || r.user || '')}</td>
					<td class="ctd-cat">${esc(r.category || '')}</td>
					<td class="ctd-notes" title="${esc(r.notes || '')}">${esc(r.notes || '')}</td>
					<td>${esc(r.business || '')}</td>
					<td class="ctd-num ctd-in">${r.money_in ? fmt_money(r.money_in) : ''}</td>
					<td class="ctd-num ctd-out">${r.money_out ? fmt_money(r.money_out) : ''}</td>
					<td>${status_badge(r.status)}</td>
				</tr>`;
			$body.append(tr);
		});
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

	// ---- filter wiring -------------------------------------------------
	function load_persons() {
		frappe.call({
			method: 'cannabis_management.cash_management.page.cash_tracking_dashboard.cash_tracking_dashboard.get_persons',
			callback: function (r) {
				var data = r.message || {};
				state.is_admin = !!data.is_admin;
				state.allow_motley = !!data.allow_motley;
				show_motley(state.allow_motley);

				var persons = data.persons || [];
				var shared = data.shared || [];
				var $sel = $('#ctd-person').empty();

				if (state.is_admin) {
					$sel.append('<option value="">All Users</option>');
				} else if (shared.length) {
					// Records shared through the Share panel on Cash Tracker Person.
					// "All" here means this user's own plus those — never everyone.
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
					// More than one person to look at, so the filter is live.
					$sel.prop('disabled', false);
					state.person = '';
					$sel.val('');
					$('#ctd-subtitle').text('Your cash entries, plus ' + shared.length +
						' shared with you');
				} else {
					// Exactly one person: lock the filter, as before.
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

	$('#ctd-tracker-toggle').on('click', '.ctd-toggle-btn', function () {
		var val = $(this).data('val');
		if (val === 'motley' && !state.allow_motley) { return; }
		select_tracker(val);
		load();
	});

	$('#ctd-person').on('change', function () {
		// Disabled for a user with only their own record, so reaching here means
		// there is something to switch to. The server re-derives the set anyway.
		if ($(this).prop('disabled')) { return; }
		state.person = $(this).val();
		load();
	});

	$('#ctd-from').on('change', function () { state.from_date = $(this).val(); load(); });
	$('#ctd-to').on('change', function () { state.to_date = $(this).val(); load(); });
	$('#ctd-refresh').on('click', function () { load(); });
	$('#ctd-new-motley').on('click', function () { frappe.new_doc('Motley Cash Tracking'); });
	$('#ctd-new-personal').on('click', function () { frappe.new_doc('Personal Cash Tracking'); });
// Apply options passed in from the Motley / Personal form buttons
	// (tracker to preselect + a from/to date range), then reflect them in the UI.
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

	// Expose so on_page_show can re-apply presets on repeat visits (the page
	// object is created once; on_page_load does not run again).
	page.apply_route_options = apply_route_options;
	page.reload_data = load;

	apply_route_options();
	load_persons();
};

// Fires every time the page is shown. If the user clicked a form button again
// (which sets frappe.route_options), re-apply the incoming tracker + dates.
frappe.pages['cash-tracking-dashboard'].on_page_show = function (wrapper) {
	var page = wrapper.page;
	if (page && page.apply_route_options && frappe.route_options) {
		page.apply_route_options();
		page.reload_data();
	}
};
