// Shared list shell for the Cultivation pages (Plants / Teardowns / Harvests).
// Same look and behaviour as Plant Batches: view dropdown, search, rows-per-page
// pagination, "Showing x of y" footer, status badges, row action menu.
// Built only on existing doctypes and fields.

window.CultivationList = class CultivationList {
	// cfg: {title, doctype, columns:[{label, field?, render?(row)}], fields:[], views:[{label, filters}],
	//       search_field, actions:[{label, icon, handler(row, list)}], order_by, noun}
	constructor(parent, cfg) {
		this.cfg = cfg;
		this.wrapper = $(parent);
		this.start = 0;
		this.page_len = 40;
		this.view = cfg.views[0];
		this.search = '';
		this.setup();
		this.load();
	}

	setup() {
		const cfg = this.cfg;
		const opts = cfg.views.map((v) => `<option>${v.label}</option>`).join('');
		this.wrapper.append(`
			<div class="cl-toolbar" style="display:flex;gap:10px;align-items:center;margin-bottom:6px;">
				<select class="form-control input-sm cl-view" style="width:auto;">${opts}</select>
				<input class="form-control input-sm cl-search" style="max-width:260px;" placeholder="${cfg.search_label || 'Search'}">
				${cfg.primary ? `<button class="btn btn-primary btn-sm cl-primary" style="margin-left:auto;">${cfg.primary.label}</button>` : ''}
			</div>`);
		this.wrapper.find('.cl-view').on('change', (e) => {
			this.view = cfg.views.find((v) => v.label === e.target.value) || cfg.views[0];
			this.start = 0;
			this.load();
		});
		this.wrapper.find('.cl-search').on('change', (e) => {
			this.search = (e.target.value || '').trim();
			this.start = 0;
			this.load();
		});
		this.wrapper.find('.cl-primary').on('click', () => cfg.primary.handler(this));

		const head = cfg.columns.map((c) => `<th>${c.label}</th>`).join('');
		this.wrapper.append(`
			<div class="cultivation-list-wrap" style="margin-top:10px;overflow-x:auto;">
				<table class="table table-bordered" style="background:#fff;margin-bottom:0;">
					<thead><tr><th style="width:40px;"></th>${head}</tr></thead>
					<tbody class="cl-tbody"><tr><td colspan="${cfg.columns.length + 1}" class="text-muted">Loading...</td></tr></tbody>
				</table>
			</div>
			<div class="cl-footer" style="display:flex;align-items:center;gap:14px;padding:10px 4px;font-size:12px;color:#6b7d73;">
				<button class="btn btn-xs btn-default cl-prev">&lsaquo;</button>
				<button class="btn btn-xs btn-default cl-next">&rsaquo;</button>
				<span class="cl-count"></span>
				<span style="margin-left:auto;">Rows per page:
					<select class="cl-rows"><option>20</option><option selected>40</option><option>100</option></select>
				</span>
			</div>`);
		this.tbody = this.wrapper.find('.cl-tbody');
		this.wrapper.find('.cl-prev').on('click', () => { this.start = Math.max(0, this.start - this.page_len); this.load(); });
		this.wrapper.find('.cl-next').on('click', () => { if (this.start + this.page_len < this.total) { this.start += this.page_len; this.load(); } });
		this.wrapper.find('.cl-rows').on('change', (e) => { this.page_len = cint(e.target.value); this.start = 0; this.load(); });
	}

	filters() {
		const f = Object.assign({}, this.view.filters || {});
		const out = Object.keys(f).map((k) => [this.cfg.doctype, k, ...(Array.isArray(f[k]) ? f[k] : ['=', f[k]])]);
		if (this.search) out.push([this.cfg.doctype, this.cfg.search_field, 'like', `%${this.search}%`]);
		return out;
	}

	load() {
		const cfg = this.cfg;
		frappe.call({
			method: 'frappe.client.get_count',
			args: { doctype: cfg.doctype, filters: this.filters() },
			callback: (c) => {
				this.total = c.message || 0;
				frappe.call({
					method: 'frappe.client.get_list',
					args: {
						doctype: cfg.doctype, fields: cfg.fields, filters: this.filters(),
						order_by: cfg.order_by || 'creation desc',
						limit_start: this.start, limit_page_length: this.page_len,
					},
					callback: (r) => {
						const rows = r.message || [];
						if (cfg.enrich) cfg.enrich(rows).then(() => this.render(rows));
						else this.render(rows);
					},
				});
			},
		});
	}

	render(rows) {
		const cfg = this.cfg;
		this.tbody.empty();
		if (!rows.length) {
			this.tbody.append(`<tr><td colspan="${cfg.columns.length + 1}" class="text-muted">No ${cfg.noun} found.</td></tr>`);
		}
		rows.forEach((row) => {
			const cells = cfg.columns.map((c) => {
				const v = c.render ? c.render(row) : CultivationList.esc(row[c.field]);
				return `<td style="${c.align ? 'text-align:' + c.align : ''}">${v === '' || v == null ? '&mdash;' : v}</td>`;
			}).join('');
			const $tr = $(`<tr><td><div class="dropdown"><button class="btn btn-xs btn-default" data-toggle="dropdown">⋮</button><ul class="dropdown-menu cl-menu"></ul></div></td>${cells}</tr>`);
			(cfg.actions || []).forEach((a) => {
				const $li = $(`<li><a class="dropdown-item" href="#">${a.label}</a></li>`);
				$li.find('a').on('click', (e) => { e.preventDefault(); a.handler(row, this); });
				$tr.find('.cl-menu').append($li);
			});
			$tr.find('a[data-route]').on('click', (e) => {
				e.preventDefault();
				frappe.set_route(...String($(e.currentTarget).data('route')).split('|'));
			});
			this.tbody.append($tr);
		});
		const from = this.total ? this.start + 1 : 0;
		const to = Math.min(this.start + this.page_len, this.total);
		this.wrapper.find('.cl-count').text(`Showing ${from} - ${to} of ${this.total} ${cfg.noun}`);
	}

	static esc(v) { return frappe.utils.escape_html(v == null ? '' : String(v)); }
	static link(label, ...route) {
		if (!label) return '';
		return `<a href="#" data-route="${route.join('|')}">${CultivationList.esc(label)}</a>`;
	}
	static badge(text, color) {
		if (!text) return '';
		const c = { green: '#2f8a5a', orange: '#d9822b', yellow: '#e0b422', red: '#c0392b', grey: '#8a9690' }[color] || '#8a9690';
		return `<span style="background:${c};color:#fff;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:3px;text-transform:uppercase;">${CultivationList.esc(text)}</span>`;
	}
	static money(v) { return v ? format_currency(v) : '$--'; }
};
