frappe.pages['run-yields'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Run Yields'), single_column: true });
	const METHOD = 'cannabis_management.cannabis_management.page.run_yields.run_yields.get_runs';
	const GRAMS_PER_POUND = 453.592;

	const COLUMNS = [
		{ key: 'run_id', label: __('Run #'), kind: 'text', group: 'run' },
		{ key: 'batch_name', label: __('Batch'), kind: 'text', group: 'run' },
		{ key: 'status', label: __('Status'), kind: 'text', group: 'run' },
		{ key: 'input_lbs', label: __('Raw Material') + '<br>(LBS)', kind: 'num', group: 'run' },
		{ key: 'raw_material', label: __('Raw Material'), kind: 'text', group: 'run' },
		{ key: 'hash_150u', label: '150u', kind: 'g', group: 'hash' },
		{ key: 'hash_120u_73u', label: '120u–73u', kind: 'g', group: 'hash' },
		{ key: 'hash_45u', label: '45u', kind: 'g', group: 'hash' },
		{ key: 'rosin_150u', label: '150u', kind: 'g', group: 'rosin' },
		{ key: 'rosin_120u_73u', label: '120u–73u', kind: 'g', group: 'rosin' },
		{ key: 'rosin_45u', label: '45u', kind: 'g', group: 'rosin' },
		{ key: 'hash_yield', label: __('Hash Yield'), kind: 'pct', group: 'yield' },
		{ key: 'rosin_yield', label: __('Rosin Yield'), kind: 'pct', group: 'yield' },
		{ key: 'hash_to_rosin_yield', label: __('Hash to Rosin'), kind: 'pct', group: 'yield' },
	];
	const GROUPS = [
		{ key: 'run', label: __('Run details'), span: 5 },
		{ key: 'hash', label: __('Hash (g)'), span: 3 },
		{ key: 'rosin', label: __('Rosin (g)'), span: 3 },
		{ key: 'yield', label: __('Yield'), span: 3 },
	];
	const STATUSES = ['Completed', 'In Progress', 'Open'];

	const state = {
		rows: [],
		shown: [],
		loading: false,
		sort: { key: null, dir: 1 },
		f: { run: '', batch: '', status: '', material: '', started_by: '', from: '', to: '' },
	};

	const esc = (s) => frappe.utils.escape_html(s == null ? '' : String(s));
	const num = (v, d) => flt(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
	const icon = (name) => frappe.utils.icon(name, 'sm', '', '', 'ry-ico');

	$(page.body).html(`
		<div class="ry">
			<div class="ry-head">
				<p class="ry-sub">${__('Hash and rosin returned by every manufacturing run.')}</p>
				<div class="ry-actions">
					<button class="ry-btn ry-btn-outline" data-act="export">${icon('es-line-download')} ${__('Export CSV')}</button>
					<button class="ry-btn ry-btn-outline ry-btn-icon" data-act="refresh" title="${__('Refresh')}">${icon('refresh')}</button>
				</div>
			</div>

			<div class="ry-cards"></div>

			<div class="ry-panel">
				<div class="ry-toolbar">
					<label class="ry-field ry-field-run">
						<span class="ry-field-label">${__('Run #')}</span>
						<span class="ry-search">
							${icon('search')}
							<input type="text" class="ry-input" data-f="run" placeholder="${__('Search runs')}">
						</span>
					</label>
					<label class="ry-field">
						<span class="ry-field-label">${__('Batch')}</span>
						<select class="ry-input ry-select" data-f="batch"><option value="">${__('All batches')}</option></select>
					</label>
					<label class="ry-field">
						<span class="ry-field-label">${__('Status')}</span>
						<select class="ry-input ry-select" data-f="status"><option value="">${__('All statuses')}</option>
							${STATUSES.map((s) => `<option value="${s}">${__(s)}</option>`).join('')}</select>
					</label>
					<label class="ry-field ry-field-wide">
						<span class="ry-field-label">${__('Raw material')}</span>
						<select class="ry-input ry-select" data-f="material"><option value="">${__('All raw materials')}</option></select>
					</label>
					<label class="ry-field">
						<span class="ry-field-label">${__('Started by')}</span>
						<select class="ry-input ry-select" data-f="started_by"><option value="">${__('Anyone')}</option></select>
					</label>
					<div class="ry-field">
						<span class="ry-field-label">${__('Started between')}</span>
						<span class="ry-range">
							<input type="date" data-f="from" title="${__('Started on or after')}">
							<span class="ry-range-sep">→</span>
							<input type="date" data-f="to" title="${__('Started on or before')}">
						</span>
					</div>
					<div class="ry-toolbar-end">
						<button class="ry-btn ry-btn-ghost" data-act="clear" hidden>${icon('close')} ${__('Clear filters')}</button>
						<span class="ry-count"></span>
					</div>
				</div>
				<div class="ry-scroll">
					<table class="ry-table">
						<thead>
							<tr class="ry-groups">${GROUPS.map((g) =>
								`<th colspan="${g.span}" class="g-${g.key}">${g.label}</th>`).join('')}</tr>
							<tr class="ry-cols">${COLUMNS.map((c) =>
								`<th class="g-${c.group}${c.kind === 'text' ? '' : ' is-num'} c-${c.key}" data-sort="${c.key}" title="${__('Sort')}">
									<span class="ry-th"><span class="ry-th-label">${c.label}</span><span class="ry-sort"></span></span></th>`).join('')}</tr>
						</thead>
						<tbody></tbody>
						<tfoot></tfoot>
					</table>
					<div class="ry-empty" hidden></div>
				</div>
			</div>
		</div>
	`);
	const $root = $(page.body).find('.ry');

	function load() {
		state.loading = true;
		draw();
		frappe.call({
			method: METHOD,
			args: { from_date: state.f.from || null, to_date: state.f.to || null },
			callback: (r) => {
				state.rows = (r.message && r.message.rows) || [];
				fill_options();
			},
			always: () => {
				state.loading = false;
				draw();
				fit();
			},
		});
	}

	function fill_options() {
		const fill = (f, key, all_label) => {
			const values = [...new Set(state.rows.map((r) => r[key]).filter((v) => v && v !== '-'))]
				.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
			if (state.f[f] && !values.includes(state.f[f])) state.f[f] = '';
			$root.find(`[data-f="${f}"]`).html(
				`<option value="">${all_label}</option>` +
				values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join('')
			).val(state.f[f]);
		};
		fill('batch', 'batch_name', __('All batches'));
		fill('material', 'raw_material', __('All raw materials'));
		fill('started_by', 'started_by', __('Anyone'));
	}

	function filtered() {
		const f = state.f;
		const q = f.run.trim().toLowerCase();
		let rows = state.rows.filter((r) =>
			(!q || String(r.run_id).toLowerCase().includes(q)) &&
			(!f.batch || r.batch_name === f.batch) &&
			(!f.status || r.status === f.status) &&
			(!f.material || r.raw_material === f.material) &&
			(!f.started_by || r.started_by === f.started_by)
		);
		const { key, dir } = state.sort;
		if (key) {
			const col = COLUMNS.find((c) => c.key === key);
			rows = rows.slice().sort((a, b) => (col.kind === 'text'
				? String(a[key] || '').localeCompare(String(b[key] || ''), undefined, { numeric: true })
				: flt(a[key]) - flt(b[key])) * dir);
		}
		return rows;
	}

	function totals(rows) {
		const t = { runs: rows.length, done: 0, lbs: 0, hash_lbs: 0, hash_w: 0, rosin_lbs: 0, rosin_w: 0, h2r_hash: 0, h2r_rosin: 0, n_hash: 0, n_rosin: 0, n_h2r: 0 };
		COLUMNS.filter((c) => c.kind === 'g').forEach((c) => { t[c.key] = 0; });
		rows.forEach((r) => {
			const lbs = flt(r.input_lbs);
			if (r.status === 'Completed') t.done++;
			t.lbs += lbs;
			COLUMNS.filter((c) => c.kind === 'g').forEach((c) => { t[c.key] += flt(r[c.key]); });
			if (lbs && flt(r.hash_yield)) { t.hash_lbs += lbs; t.hash_w += lbs * flt(r.hash_yield); t.n_hash++; }
			if (lbs && flt(r.rosin_yield)) { t.rosin_lbs += lbs; t.rosin_w += lbs * flt(r.rosin_yield); t.n_rosin++; }
			if (lbs && flt(r.hash_yield) && flt(r.rosin_yield)) {
				t.h2r_hash += lbs * flt(r.hash_yield); t.h2r_rosin += lbs * flt(r.rosin_yield); t.n_h2r++;
			}
		});
		t.input_lbs = t.lbs;
		t.hash_yield = t.hash_lbs ? t.hash_w / t.hash_lbs : 0;
		t.rosin_yield = t.rosin_lbs ? t.rosin_w / t.rosin_lbs : 0;
		t.hash_to_rosin_yield = t.h2r_hash ? (t.h2r_rosin / t.h2r_hash) * 100 : 0;
		return t;
	}

	function cell(c, r) {
		const v = r[c.key];
		switch (c.key) {
			case 'run_id':
				return `<a class="ry-link" href="/app/material-request/${encodeURIComponent(v)}">${esc(v)}</a>
					<div class="ry-muted ry-small">${esc(frappe.datetime.str_to_user(r.started_date) || '')}</div>`;
			case 'status':
				return `<span class="ry-badge is-${esc(String(v).toLowerCase().replace(/\s+/g, '-'))}">${esc(__(v))}</span>`;
		}
		if (c.kind === 'text') return v && v !== '-' ? esc(v) : '<span class="ry-nil">—</span>';
		if (!flt(v)) return '<span class="ry-nil">—</span>';
		if (c.kind === 'pct') return num(v, 2) + '%';
		if (c.kind === 'num') return num(v, 2);
		return num(v, 0);
	}

	function draw() {
		const rows = state.shown = filtered();
		const t = totals(rows);
		const f = state.f;
		const active = !!(f.run || f.batch || f.status || f.material || f.started_by || f.from || f.to);

		$root.find('[data-act="clear"]').prop('hidden', !active);
		$root.find('.ry-count').html(state.loading ? __('Loading…')
			: active ? __('<b>{0}</b> of {1} runs', [rows.length, state.rows.length])
			: __('<b>{0}</b> runs', [rows.length]));
		$root.find('[data-f]').each(function () {
			$(this).toggleClass('is-active', !!state.f[$(this).data('f')]);
		});
		$root.find('.ry-range').toggleClass('is-active', !!(f.from || f.to));

		$root.find('.ry-cards').html([
			card(__('Runs'), t.runs.toLocaleString('en-US'), __('{0} completed', [t.done])),
			card(__('Raw material'), num(t.lbs, 2) + ' lbs', num(t.lbs * GRAMS_PER_POUND / 1000, 1) + ' kg'),
			card(__('Hash yield'), pct(t.hash_yield), runs_note(t.n_hash, __('with hash')), 'hash'),
			card(__('Rosin yield'), pct(t.rosin_yield), runs_note(t.n_rosin, __('with rosin')), 'rosin'),
			card(__('Hash to rosin'), pct(t.hash_to_rosin_yield), runs_note(t.n_h2r, __('pressed')), 'yield'),
		].join(''));

		$root.find('.ry-cols th').each(function () {
			const on = state.sort.key === $(this).data('sort');
			$(this).toggleClass('is-asc', on && state.sort.dir > 0).toggleClass('is-desc', on && state.sort.dir < 0);
		});

		const $empty = $root.find('.ry-empty');
		if (state.loading && !state.rows.length) {
			$root.find('tbody, tfoot').empty();
			$empty.prop('hidden', false).text(__('Loading runs…'));
			return;
		}
		if (!rows.length) {
			$root.find('tbody, tfoot').empty();
			$empty.prop('hidden', false).text(state.rows.length
				? __('No runs match these filters.') : __('No runs in this date range.'));
			return;
		}
		$empty.prop('hidden', true);

		$root.find('tbody').html(rows.map((r) => `<tr>${COLUMNS.map((c) =>
			`<td class="g-${c.group}${c.kind === 'text' ? '' : ' is-num'} c-${c.key}">${cell(c, r)}</td>`).join('')}</tr>`).join(''));

		$root.find('tfoot').html(`<tr>${COLUMNS.map((c) => {
			let v = '';
			if (c.key === 'run_id') v = __('Total');
			else if (c.kind !== 'text') v = cell(c, t);
			return `<td class="g-${c.group}${c.kind === 'text' ? '' : ' is-num'} c-${c.key}">${v}</td>`;
		}).join('')}</tr>`);
	}

	function card(label, value, note, tone) {
		return `<div class="ry-card${tone ? ' t-' + tone : ''}">
			<div class="ry-card-label">${label}</div>
			<div class="ry-card-value">${value}</div>
			<div class="ry-card-note ry-muted">${note}</div>
		</div>`;
	}
	function pct(v) { return v ? num(v, 2) + '%' : '—'; }
	function runs_note(n, what) { return n === 1 ? __('1 run {0}', [what]) : __('{0} runs {1}', [n, what]); }

	function export_csv() {
		if (!state.shown.length) {
			frappe.msgprint(__('There are no runs to export.'));
			return;
		}
		const head = ['Run #', 'Started', 'Batch', 'Status', 'Raw Material (LBS)', 'Raw Material',
			'150u Hash (g)', '120u-73u Hash (g)', '45u Hash (g)',
			'150u Rosin (g)', '120u-73u Rosin (g)', '45u Rosin (g)',
			'Hash Yield %', 'Rosin Yield %', 'Hash to Rosin Yield %'];
		const data = [head].concat(state.shown.map((r) => [
			r.run_id, frappe.datetime.str_to_user(r.started_date) || '', r.batch_name, r.status,
			flt(r.input_lbs), r.raw_material,
			flt(r.hash_150u), flt(r.hash_120u_73u), flt(r.hash_45u),
			flt(r.rosin_150u), flt(r.rosin_120u_73u), flt(r.rosin_45u),
			flt(r.hash_yield), flt(r.rosin_yield), flt(r.hash_to_rosin_yield),
		]));
		frappe.tools.downloadify(data, null, 'Run Yields - ' + frappe.datetime.get_today());
	}

	$root.on('input change', '[data-f]', frappe.utils.debounce(() => {
		const dates = state.f.from + '|' + state.f.to;
		$root.find('[data-f]').each(function () { state.f[$(this).data('f')] = $(this).val() || ''; });
		if (state.f.from + '|' + state.f.to !== dates) load();
		else draw();
	}, 150));

	$root.on('click', '.ry-cols th', function () {
		const key = $(this).data('sort');
		const s = state.sort;
		if (s.key !== key) Object.assign(s, { key, dir: 1 });
		else if (s.dir > 0) s.dir = -1;
		else Object.assign(s, { key: null, dir: 1 });
		draw();
	});

	$root.on('click', '[data-act]', function () {
		const act = $(this).data('act');
		if (act === 'refresh') load();
		if (act === 'export') export_csv();
		if (act === 'clear') {
			const reload = state.f.from || state.f.to;
			Object.keys(state.f).forEach((k) => { state.f[k] = ''; });
			$root.find('[data-f]').val('');
			reload ? load() : draw();
		}
	});

	function fit() {
		const $scroll = $root.find('.ry-scroll');
		$root.find('.ry-table').css('--ry-group-h', $root.find('.ry-groups').outerHeight() + 'px');
		if (window.innerWidth <= 640) return $scroll.css('max-height', '');
		const top = $scroll[0].getBoundingClientRect().top + window.scrollY;
		$scroll.css('max-height', Math.max(360, window.innerHeight - top - 24) + 'px');
	}
	$(window).on('resize', frappe.utils.debounce(fit, 150));
	$(wrapper).on('show', fit);

	load();
	setTimeout(fit, 0);
};
