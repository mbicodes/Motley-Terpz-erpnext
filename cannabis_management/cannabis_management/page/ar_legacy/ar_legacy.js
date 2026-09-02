// AR Legacy — legacy receivables filed by whose relationship the account is.
//
// Layout, in the order it is read:
//   1. KPI cards — the size of the book, and how much of it is still unfiled.
//   2. Segment cards — count and value per segment; click one to filter to it.
//   3. Filters — search, company, age, minimum balance, sort.
//   4. Sections — one per segment, each with its own subtotal.
//
// Changing a row's segment re-parents it immediately and recomputes every
// total on the page, so the effect of the choice is visible without a reload.

frappe.pages['ar-legacy'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'AR Legacy',
		single_column: true
	});

	wrapper.page = page;

	var state = {
		rows: [], segments: [], companies: [], can_edit: false,
		filters: { search: '', segment: '', company: '', age: '', min_amount: '', sort: 'outstanding' },
		collapsed: {}
	};
	page._state = state;

	var AGE_BUCKETS = [
		{ value: '', label: 'Any age' },
		{ value: '90', label: '90+ days' },
		{ value: '180', label: '180+ days' },
		{ value: '270', label: '270+ days' },
		{ value: '365', label: '1 year+' }
	];

	var SORTS = [
		{ value: 'outstanding', label: 'Largest balance' },
		{ value: 'age', label: 'Oldest first' },
		{ value: 'invoices', label: 'Most invoices' },
		{ value: 'name', label: 'Customer A–Z' }
	];

	page.main.html(`
		<div class="arl">
			<div class="arl-cards" id="arl-cards"></div>
			<div class="arl-seg-cards" id="arl-seg-cards"></div>

			<div class="arl-filters">
				<div class="arl-field arl-field-search">
					<span class="arl-search-icon">&#128269;</span>
					<input type="text" id="arl-search" class="arl-input" placeholder="Search customer…" />
				</div>
				<div class="arl-field">
					<label class="arl-label">Company</label>
					<select id="arl-company" class="arl-input"></select>
				</div>
				<div class="arl-field">
					<label class="arl-label">Age of oldest invoice</label>
					<select id="arl-age" class="arl-input"></select>
				</div>
				<div class="arl-field">
					<label class="arl-label">Min balance</label>
					<input type="number" id="arl-min" class="arl-input" placeholder="0" min="0" step="1000" />
				</div>
				<div class="arl-field">
					<label class="arl-label">Sort by</label>
					<select id="arl-sort" class="arl-input"></select>
				</div>
				<button class="arl-btn arl-btn-ghost" id="arl-clear">Clear</button>
				<button class="arl-btn" id="arl-refresh">&#8635; Refresh</button>
			</div>

			<div class="arl-active" id="arl-active"></div>

			<div id="arl-body">
				<div class="arl-loading"><div class="arl-spinner"></div><p>Loading legacy accounts…</p></div>
			</div>
		</div>
	`);

	// ---- helpers -------------------------------------------------------
	function money(v, compact) {
		v = v || 0;
		if (compact && Math.abs(v) >= 1000) {
			return '$' + (v / 1000).toFixed(v >= 100000 ? 0 : 1) + 'k';
		}
		return (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString('en-US',
			{ minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}

	function esc(s) { return frappe.utils.escape_html(s == null ? '' : String(s)); }
	function slug(s) { return (s || 'unassigned').replace(/[^a-z0-9]+/gi, '-').toLowerCase(); }
	function label_of(seg) { return seg || 'Unassigned'; }
	function sum_of(rows) { return rows.reduce(function (a, r) { return a + (r.outstanding || 0); }, 0); }

	// Segment order: Unassigned first — an unfiled account is the thing that
	// still needs a decision — then the segments as declared server-side.
	function all_segments() { return [''].concat(state.segments); }

	// Everything except the segment filter, so the segment cards can show true
	// counts while one of them is selected.
	function rows_before_segment() {
		var f = state.filters;
		var q = (f.search || '').toLowerCase();
		var min = parseFloat(f.min_amount) || 0;
		var age = parseInt(f.age, 10) || 0;

		return state.rows.filter(function (r) {
			if (q && (r.customer || '').toLowerCase().indexOf(q) === -1 &&
				(r.customer_name || '').toLowerCase().indexOf(q) === -1) return false;
			if (f.company && (r.companies || '').indexOf(f.company) === -1) return false;
			if (min && (r.outstanding || 0) < min) return false;
			if (age && (r.age_days || 0) < age) return false;
			return true;
		});
	}

	function visible_rows() {
		var f = state.filters;
		var rows = rows_before_segment();
		if (f.segment === '__unassigned__') return rows.filter(function (r) { return !r.segment; });
		if (f.segment) return rows.filter(function (r) { return r.segment === f.segment; });
		return rows;
	}

	function sorted(rows) {
		var by = state.filters.sort;
		return rows.slice().sort(function (a, b) {
			if (by === 'age') return (b.age_days || 0) - (a.age_days || 0);
			if (by === 'invoices') return (b.invoices || 0) - (a.invoices || 0);
			if (by === 'name') {
				return (a.customer_name || a.customer).localeCompare(b.customer_name || b.customer);
			}
			return (b.outstanding || 0) - (a.outstanding || 0);
		});
	}

	// ---- cards ---------------------------------------------------------
	function render_cards() {
		var rows = visible_rows();
		var unassigned = rows.filter(function (r) { return !r.segment; });
		var assigned = rows.filter(function (r) { return !!r.segment; });
		var oldest = rows.reduce(function (a, r) { return Math.max(a, r.age_days || 0); }, 0);

		var cards = [
			{ label: 'Outstanding', value: money(sum_of(rows)), sub: rows.length + ' accounts', tone: 'total' },
			{ label: 'Unfiled', value: money(sum_of(unassigned)), sub: unassigned.length + ' accounts', tone: 'warn' },
			{ label: 'Filed', value: money(sum_of(assigned)), sub: assigned.length + ' accounts', tone: 'good' },
			{ label: 'Oldest invoice', value: oldest ? oldest + ' days' : '—', sub: 'in view', tone: 'age' }
		];

		$('#arl-cards').html(cards.map(function (c) {
			return `<div class="arl-card arl-card-${c.tone}">
						<span class="arl-card-label">${esc(c.label)}</span>
						<span class="arl-card-value">${esc(c.value)}</span>
						<span class="arl-card-sub">${esc(c.sub)}</span>
					</div>`;
		}).join(''));
	}

	function render_segment_cards() {
		var base = rows_before_segment();
		var active = state.filters.segment;

		var html = all_segments().map(function (seg) {
			var key = seg === '' ? '__unassigned__' : seg;
			var rows = base.filter(function (r) { return (r.segment || '') === seg; });
			var is_active = active === key;
			return `<button class="arl-seg-card arl-sec-${slug(seg)} ${is_active ? 'is-active' : ''}"
						data-segment="${esc(key)}">
						<span class="arl-seg-dot"></span>
						<span class="arl-seg-name">${esc(label_of(seg))}</span>
						<span class="arl-seg-count">${rows.length}</span>
						<span class="arl-seg-amount">${money(sum_of(rows), true)}</span>
					</button>`;
		}).join('');

		$('#arl-seg-cards').html(html);
	}

	function render_active_filters() {
		var f = state.filters;
		var bits = [];
		if (f.search) bits.push(['search', 'Search: "' + f.search + '"']);
		if (f.company) bits.push(['company', 'Company: ' + f.company]);
		if (f.age) bits.push(['age', f.age + '+ days old']);
		if (f.min_amount) bits.push(['min_amount', 'Min ' + money(parseFloat(f.min_amount))]);
		if (f.segment) {
			bits.push(['segment', f.segment === '__unassigned__' ? 'Unassigned only' : f.segment]);
		}
		$('#arl-active').html(bits.length
			? bits.map(function (b) {
				return '<span class="arl-pill" data-clear="' + b[0] + '">' + esc(b[1]) + ' <i>&times;</i></span>';
			}).join('')
			: '');
	}

	// ---- table ---------------------------------------------------------
	function options_html(selected) {
		var out = ['<option value=""' + (selected ? '' : ' selected') + '>— Unassigned —</option>'];
		state.segments.forEach(function (s) {
			out.push('<option value="' + esc(s) + '"' + (s === selected ? ' selected' : '') + '>' +
				esc(s) + '</option>');
		});
		return out.join('');
	}

	function row_html(r) {
		var disabled = state.can_edit ? '' : ' disabled';
		var age_class = (r.age_days || 0) >= 365 ? 'arl-age-old'
			: (r.age_days || 0) >= 180 ? 'arl-age-mid' : '';
		return `
			<tr data-customer="${esc(r.customer)}">
				<td class="arl-cust">
					<a href="/app/customer/${encodeURIComponent(r.customer)}" target="_blank" rel="noopener">${esc(r.customer_name || r.customer)}</a>
					<span class="arl-co">${esc(r.companies || '')}</span>
				</td>
				<td class="arl-seg">
					<select class="arl-select arl-sec-${slug(r.segment)}" data-customer="${esc(r.customer)}"${disabled}>
						${options_html(r.segment || '')}
					</select>
				</td>
				<td class="arl-num">${money(r.outstanding)}</td>
				<td class="arl-inv-col">${r.invoices}</td>
				<td class="arl-oldest ${age_class}">
					${esc(r.oldest || '')}<span class="arl-age">${r.age_days ? r.age_days + 'd' : ''}</span>
				</td>
			</tr>`;
	}

	function section_html(seg) {
		var rows = sorted(visible_rows().filter(function (r) { return (r.segment || '') === seg; }));
		if (state.filters.segment && !rows.length) return '';

		var id = slug(seg);
		var collapsed = !!state.collapsed[seg];
		var body = rows.length
			? `<div class="arl-table-wrap"><table class="arl-table">
					<thead><tr>
						<th>Customer</th><th>Segment</th>
						<th class="arl-num">Outstanding</th><th class="arl-inv-col">Inv</th><th>Oldest</th>
					</tr></thead>
					<tbody>${rows.map(row_html).join('')}</tbody>
				</table></div>`
			: '<div class="arl-empty">Nothing filed here yet.</div>';

		return `
			<section class="arl-section arl-sec-${id} ${collapsed ? 'is-collapsed' : ''}">
				<header class="arl-sec-head" data-toggle="${esc(seg)}">
					<span class="arl-caret">&#9662;</span>
					<h3 class="arl-sec-title">${esc(label_of(seg))}</h3>
					<span class="arl-chip">${rows.length}</span>
					<span class="arl-sec-total">${money(sum_of(rows))}</span>
				</header>
				<div class="arl-sec-body">${body}</div>
			</section>`;
	}

	function render() {
		render_cards();
		render_segment_cards();
		render_active_filters();
		var html = all_segments().map(section_html).join('');
		$('#arl-body').html(html || '<div class="arl-empty arl-empty-page">No accounts match these filters.</div>');
	}

	// ---- data ----------------------------------------------------------
	function load() {
		frappe.call({
			method: 'cannabis_management.cannabis_management.page.ar_legacy.ar_legacy.get_data',
			callback: function (r) {
				if (!r.message) return;
				state.rows = r.message.rows || [];
				state.segments = r.message.segments || [];
				state.companies = r.message.companies || [];
				state.can_edit = !!r.message.can_edit;

				var $co = $('#arl-company').empty().append('<option value="">All companies</option>');
				state.companies.forEach(function (c) {
					$co.append('<option value="' + esc(c) + '">' + esc(c) + '</option>');
				});
				$co.val(state.filters.company);

				render();

				if (r.message.field_missing) {
					page.set_indicator(__('Segment field not installed'), 'orange');
					frappe.msgprint({
						title: __('Segments are read-only here'),
						indicator: 'orange',
						message: __('The AR Legacy segment field has not been installed on this site. Run:<br>' +
							'<code>bench --site &lt;site&gt; execute cannabis_management.cannabis_management.page.ar_legacy.ar_legacy.install_segment_field</code>')
					});
				}
			}
		});
	}

	// ---- events --------------------------------------------------------
	page.main.on('change', '.arl-select', function () {
		var $sel = $(this);
		var customer = $sel.data('customer');
		var segment = $sel.val();
		var row = state.rows.find(function (r) { return r.customer === customer; });
		if (!row) return;

		var previous = row.segment || '';
		row.segment = segment;      // optimistic — the row moves straight away
		render();

		frappe.call({
			method: 'cannabis_management.cannabis_management.page.ar_legacy.ar_legacy.set_segment',
			args: { customer: customer, segment: segment },
			error: function () { row.segment = previous; render(); },
			callback: function () {
				frappe.show_alert({
					message: __('{0} → {1}', [customer, segment || __('Unassigned')]),
					indicator: 'green'
				}, 3);
			}
		});
	});

	page.main.on('click', '.arl-seg-card', function () {
		var key = $(this).data('segment');
		state.filters.segment = state.filters.segment === key ? '' : key;
		render();
	});

	page.main.on('click', '.arl-sec-head', function () {
		var seg = $(this).data('toggle');
		state.collapsed[seg] = !state.collapsed[seg];
		render();
	});

	page.main.on('click', '.arl-pill', function () {
		state.filters[$(this).data('clear')] = '';
		sync_controls();
		render();
	});

	function sync_controls() {
		$('#arl-search').val(state.filters.search);
		$('#arl-company').val(state.filters.company);
		$('#arl-age').val(state.filters.age);
		$('#arl-min').val(state.filters.min_amount);
		$('#arl-sort').val(state.filters.sort);
	}

	$('#arl-age').html(AGE_BUCKETS.map(function (b) {
		return '<option value="' + b.value + '">' + b.label + '</option>';
	}).join(''));
	$('#arl-sort').html(SORTS.map(function (s) {
		return '<option value="' + s.value + '">' + s.label + '</option>';
	}).join(''));

	page.main.find('#arl-search').on('input', function () { state.filters.search = $(this).val(); render(); });
	page.main.find('#arl-company').on('change', function () { state.filters.company = $(this).val(); render(); });
	page.main.find('#arl-age').on('change', function () { state.filters.age = $(this).val(); render(); });
	page.main.find('#arl-min').on('input', function () { state.filters.min_amount = $(this).val(); render(); });
	page.main.find('#arl-sort').on('change', function () { state.filters.sort = $(this).val(); render(); });
	page.main.find('#arl-clear').on('click', function () {
		state.filters = { search: '', segment: '', company: '', age: '', min_amount: '', sort: 'outstanding' };
		sync_controls();
		render();
	});
	page.main.find('#arl-refresh').on('click', function () { load(); });

	load();
};
