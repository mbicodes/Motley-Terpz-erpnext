// Motley Glass page report: a Script Report shown as a Desk page in the Sales Operation Board look.
// Used by /app/toll-stock-on-hand and /app/toll-job-yield-summary. Data: cannabis_management.toll.report_pages.
(function () {
	const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
	const fmtn = (n, d) => Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
	const money = n => format_currency(n || 0, frappe.boot.sysdefaults.currency || 'USD');
	const M = 'cannabis_management.toll.report_pages.';
	const BG = '<div class="mg-bg" aria-hidden="true"><i></i></div>';

	class MGReportPage {
		// cfg: { wrapper, title, report, hint, filters: [{fieldname, label, type: 'date'|'select'|'text'|'check'|'seg', options|options_from, default}] }
		constructor(cfg) {
			this.cfg = cfg;
			this.values = {};
			this.sort = null;
			this.data = null;
			const page = cfg.page || frappe.ui.make_app_page({ parent: cfg.wrapper, title: cfg.title, single_column: true });
			this.page = page;
			$(cfg.wrapper).addClass('mg-glass-page mg-report-page');
			page.set_primary_action(__('Refresh'), () => this.load(true), 'refresh');
			page.add_inner_button(__('Export CSV'), () => this.export_csv());
			page.add_inner_button(__('Open as Standard Report'), () => frappe.set_route('query-report', cfg.report));
			if (cfg.back) page.add_inner_button(cfg.back.label, () => frappe.set_route(cfg.back.route));
			$(page.main).find('.mgr-boot').remove();
			this.el = $('<div class="mg mgr">' + BG + '<div class="mg-loading">' + __('Loading…') + '</div></div>').appendTo(page.main)[0];
			cfg.filters.forEach(f => { this.values[f.fieldname] = typeof f.default === 'function' ? f.default() : (f.default == null ? '' : f.default); });
			frappe.call({ method: M + 'get_options', args: { report: cfg.report } }).then(r => {
				this.options = r.message || {};
				this.shell();
				this.load();
			});
		}

		shell() {
			const bar = this.cfg.filters.map(f => this.filter_html(f)).join('<span class="mg-sep"></span>');
			this.el.innerHTML = BG + (this.cfg.hint ? `<div class="mg-hint">${this.cfg.hint}</div>` : '') +
				`<div class="mg-bar"><div class="mg-glass" role="toolbar" aria-label="${__('Filters')}">${bar}</div></div>
				<div class="mg-kpis mgr-kpis"></div>
				<div class="mg-table-wrap"><table class="mg-table"><thead></thead><tbody></tbody></table></div>
				<div class="mg-hint mgr-foot"></div>`;
			const $el = $(this.el);
			$el.on('change input', '[data-f]', e => {
				const t = e.currentTarget, f = this.cfg.filters.find(x => x.fieldname === t.dataset.f);
				this.values[t.dataset.f] = t.value;
				clearTimeout(this._t);
				this._t = setTimeout(() => this.load(), f && f.type === 'text' ? 350 : 0);
			});
			$el.on('click', '[data-chk]', e => {
				const k = e.currentTarget.dataset.chk, on = !this.values[k];
				this.values[k] = on ? 1 : 0;
				e.currentTarget.setAttribute('aria-pressed', on ? 'true' : 'false');
				this.load();
			});
			$el.on('click', '[data-seg]', e => {
				const b = e.currentTarget;
				this.values[b.dataset.seg] = b.dataset.v;
				$(b).siblings().attr('aria-pressed', 'false');
				b.setAttribute('aria-pressed', 'true');
				this.sort = null;
				this.load();
			});
			this.place_bar();
			$(window).on('resize', () => this.place_bar());
			$el.on('click', 'th[data-col]', e => {
				const k = e.currentTarget.dataset.col;
				this.sort = this.sort && this.sort.k === k ? { k, dir: -this.sort.dir } : { k, dir: 1 };
				this.render_table();
			});
		}

		place_bar() {
			const head = $(this.el).closest('.page-container').find('.page-head').get(0) || document.querySelector('.navbar');
			const stick = head ? Math.max(0, Math.round(head.getBoundingClientRect().bottom)) + 8 : 108;
			this.el.style.setProperty('--mg-stick', stick + 'px');
		}

		filter_html(f) {
			const v = this.values[f.fieldname];
			if (f.type === 'date') {
				return `<label class="mgr-lbl">${esc(f.label)}<input class="mg-in mgr-date" type="date" data-f="${f.fieldname}" value="${esc(v)}"></label>`;
			}
			if (f.type === 'select') {
				const list = (f.options_from ? (this.options[f.options_from] || []) : f.options).map(o => typeof o === 'string' ? { value: o, label: o } : { value: o.name, label: o.customer_name || o.name });
				return `<select class="mg-in" data-f="${f.fieldname}" aria-label="${esc(f.label)}"><option value="">${esc(f.all || f.label)}</option>` +
					list.map(o => `<option value="${esc(o.value)}"${o.value === v ? ' selected' : ''}>${esc(o.label)}</option>`).join('') + '</select>';
			}
			if (f.type === 'check') {
				return `<button class="mg-chip" data-chk="${f.fieldname}" aria-pressed="${v ? 'true' : 'false'}">${esc(f.label)}</button>`;
			}
			if (f.type === 'seg') {
				return f.options.map(o => `<button class="mg-chip" data-seg="${f.fieldname}" data-v="${esc(o)}" aria-pressed="${o === v ? 'true' : 'false'}">${esc(__(o))}</button>`).join('');
			}
			return `<input class="mg-in" data-f="${f.fieldname}" placeholder="${esc(f.label)}" value="${esc(v)}" aria-label="${esc(f.label)}">`;
		}

		load(alert) {
			const seq = (this._seq = (this._seq || 0) + 1);
			$(this.el).find('.mg-table-wrap').css('opacity', .6);
			return frappe.call({ method: M + 'get_report', args: { report: this.cfg.report, filters: this.values } }).then(r => {
				if (seq !== this._seq) return;
				this.data = r.message;
				this.render();
				if (alert) frappe.show_alert({ message: __('Report refreshed.'), indicator: 'green' }, 3);
			}).always(() => $(this.el).find('.mg-table-wrap').css('opacity', 1));
		}

		render() {
			const k = this.data.kpis || [];
			this.el.querySelector('.mgr-kpis').innerHTML = k.map(x => {
				const val = x.currency ? money(x.value) : fmtn(x.value, x.precision) + (x.unit ? (x.unit === '%' ? '%' : ' ' + x.unit) : '');
				return `<div class="mg-kpi ${x.cls || ''}"><div class="mg-kpi-label">${esc(x.label)}</div><div class="mg-kpi-value">${esc(val)}</div><div class="mg-kpi-sub">${esc(x.sub || '')}</div></div>`;
			}).join('');
			this.render_table();
		}

		rows() {
			const all = this.data.data || [];
			const total = all.length && all[all.length - 1].customer === __('Total') && !all[all.length - 1].toll_job && this.cfg.total_row ? all[all.length - 1] : null;
			let rows = total ? all.slice(0, -1) : all.slice();
			if (this.sort) {
				const { k, dir } = this.sort;
				rows.sort((a, b) => {
					const x = a[k], y = b[k];
					if (typeof x === 'number' || typeof y === 'number') return ((x || 0) - (y || 0)) * dir;
					return String(x || '').localeCompare(String(y || '')) * dir;
				});
			}
			return { rows, total };
		}

		cell(c, r, plain) {
			const v = r[c.fieldname];
			if (v == null || v === '') return '';
			if (c.fieldtype === 'Link' && c.options && !plain) return `<a href="/app/${frappe.router.slug(c.options)}/${encodeURIComponent(v)}">${esc(v)}</a>`;
			if (c.fieldtype === 'Currency') return esc(money(v));
			if (c.fieldtype === 'Percent') return esc(fmtn(v, c.precision != null ? c.precision : 2) + '%');
			if (c.fieldtype === 'Float') return esc(fmtn(v, c.precision != null ? +c.precision : 2));
			if (c.fieldtype === 'Int') return esc(fmtn(v, 0));
			if (c.fieldtype === 'Date') return esc(frappe.datetime.str_to_user(v));
			return esc(v);
		}

		render_table() {
			const cols = this.data.columns || [];
			const num = c => ['Float', 'Currency', 'Percent', 'Int'].includes(c.fieldtype);
			const arrow = c => this.sort && this.sort.k === c.fieldname ? `<span class="arrow">${this.sort.dir > 0 ? '▲' : '▼'}</span>` : '';
			this.el.querySelector('thead').innerHTML = '<tr>' + cols.map(c => `<th class="${num(c) ? 'num' : ''}" data-col="${c.fieldname}" title="${__('Sort')}">${esc(c.label)}${arrow(c)}</th>`).join('') + '</tr>';
			const { rows, total } = this.rows();
			const tr = (r, cls) => `<tr class="${cls || ''}">` + cols.map(c => `<td class="${num(c) ? 'num' : ''}">${this.cell(c, r, !!cls)}</td>`).join('') + '</tr>';
			this.el.querySelector('tbody').innerHTML = rows.length
				? rows.map(r => tr(r)).join('') + (total ? tr(total, 'mg-total') : '')
				: `<tr><td colspan="${cols.length || 1}" class="mg-empty">${__('Nothing to show for these filters.')}</td></tr>`;
			this.el.querySelector('.mgr-foot').textContent = rows.length ? __('{0} rows. Click a column to sort.', [rows.length]) : '';
		}

		export_csv() {
			if (!this.data) return;
			const cols = this.data.columns || [];
			const q = v => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
			const lines = [cols.map(c => q(c.label)).join(',')].concat((this.data.data || []).map(r => cols.map(c => q(r[c.fieldname])).join(',')));
			const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
			const a = document.createElement('a');
			a.href = URL.createObjectURL(blob);
			a.download = this.cfg.report.replace(/\s+/g, '_') + '_' + frappe.datetime.get_today() + '.csv';
			document.body.appendChild(a);
			a.click();
			setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
		}
	}

	window.MGReportPage = MGReportPage;

	// Page files call this. The page is made at once (Frappe expects it during on_page_load); the shared script is
	// loaded with a plain <script> tag, not frappe.require: frappe.require reads the path from disk, so a ?v= cache
	// buster made it throw and the page froze.
})();
