// Copyright (c) 2026, alltechvirtual.com and contributors
// My Dashboard Setup — an administrator picks, per user, the shortcuts that
// appear on that user's My Dashboard (see api/my_dashboard.py).
//
// Left: every desk user, with how many shortcuts each has. Right: the selected
// user's shortcuts — add from a searchable dropdown of every workspace,
// dashboard, page, report and DocType on the site, drag to reorder, rename,
// remove. Picking a shortcut does not grant access, so each row shows whether
// that user can actually open it.
//
// Wrapped in its own scope: desk page scripts share one window.

(function () {
const METHOD = 'cannabis_management.api.my_dashboard.';
const MAX_ROWS = 150; // dropdown rows rendered at once; search narrows the rest

const TYPE_LABEL = {
	Workspace: __('Workspace'),
	Dashboard: __('Dashboard'),
	Page: __('Page'),
	Report: __('Report'),
	DocType: __('List / Form'),
	URL: __('Link'),
};

frappe.pages['my-dashboard-setup'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('My Dashboard Setup'),
		single_column: true,
	});
	wrapper.my_dashboard_setup = new MyDashboardSetup(page);
};

class MyDashboardSetup {
	constructor(page) {
		this.page = page;
		this.users = [];
		this.catalog = [];
		this.types = [];
		this.user = null;
		this.items = [];
		this.dirty = false;
		this.filter = { term: '', type: 'All', source: 'all' };

		this.$root = $(`
			<div class="mds">
				<aside class="mds-users">
					<input class="mds-input mds-user-search" type="search" placeholder="${__('Search users')}">
					<div class="mds-user-list"></div>
				</aside>
				<section class="mds-editor"></section>
			</div>`).appendTo(page.main);

		this.page.set_primary_action(__('Save'), () => this.save());
		this.page.btn_primary.prop('disabled', true);
		this.page.set_secondary_action(__('Open My Dashboard'), () => frappe.set_route('my-dashboard'));

		this.bind();
		this.render_editor();
		this.load();
	}

	// ── data ────────────────────────────────────────────────────────────────

	load() {
		Promise.all([frappe.xcall(METHOD + 'get_users'), frappe.xcall(METHOD + 'get_catalog')]).then(
			([users, catalog]) => {
				this.users = users;
				this.catalog = catalog.items;
				this.types = catalog.types;
				this.render_users();
			}
		);
	}

	select_user(name) {
		const go = () => {
			frappe.xcall(METHOD + 'get_setup', { user: name }).then((data) => {
				this.user = this.users.find((u) => u.name === name);
				this.set_items(data.items);
				this.set_dirty(false);
				this.render_users();
				this.render_editor();
			});
		};
		if (this.dirty) {
			frappe.confirm(__('Discard unsaved changes for {0}?', [this.user.full_name || this.user.name]), go);
		} else {
			go();
		}
	}

	set_items(resolved) {
		this.items = resolved.map((row) => ({
			type: row.type,
			name: row.name,
			label: row.custom_label || '',
			default_label: row.default_label || row.name,
			module: row.module,
			sub: row.sub,
			exists: row.exists,
			allowed: row.allowed,
			pinned: row.pinned ? 1 : 0,
		}));
	}

	payload() {
		return this.items.map((item) => ({
			item_type: item.type,
			link_name: item.name,
			label: item.label,
			pinned_by_user: item.pinned ? 1 : 0,
		}));
	}

	save() {
		if (!this.user) return;
		frappe
			.xcall(METHOD + 'save_setup', { user: this.user.name, items: this.payload() })
			.then((data) => {
				this.set_items(data.items);
				this.user.count = this.items.length;
				this.set_dirty(false);
				this.render_users();
				this.render_items();
				frappe.show_alert({ message: __('Dashboard saved for {0}', [this.user.full_name || this.user.name]), indicator: 'green' });
			});
	}

	// Access flags for rows that were just picked and are not saved yet.
	refresh_access() {
		clearTimeout(this._access_timer);
		this._access_timer = setTimeout(() => {
			if (!this.user || !this.items.length) return;
			const user = this.user.name;
			frappe.xcall(METHOD + 'check_access', { user: user, items: this.payload() }).then((rows) => {
				if (!this.user || this.user.name !== user) return;
				const flags = {};
				rows.forEach((row) => (flags[row.type + '::' + row.name] = row));
				this.items.forEach((item) => {
					const row = flags[item.type + '::' + item.name];
					if (row) {
						item.allowed = row.allowed;
						item.exists = row.exists;
					}
				});
				this.render_items();
			});
		}, 300);
	}

	set_dirty(dirty) {
		this.dirty = dirty;
		this.page.btn_primary.prop('disabled', !dirty);
		this.page.set_indicator(dirty ? __('Not saved') : '', dirty ? 'orange' : '');
	}

	changed() {
		this.set_dirty(true);
		this.render_items();
		this.render_picker_list();
	}

	// ── users column ────────────────────────────────────────────────────────

	render_users() {
		const term = (this.$root.find('.mds-user-search').val() || '').trim().toLowerCase();
		const rows = this.users.filter(
			(u) => !term || (u.full_name || '').toLowerCase().includes(term) || u.name.toLowerCase().includes(term)
		);
		const html = rows
			.map((u) => {
				const active = this.user && this.user.name === u.name ? ' is-active' : '';
				return `
				<button type="button" class="mds-user${active}" data-user="${frappe.utils.escape_html(u.name)}">
					<span class="mds-user-text">
						<span class="mds-user-name">${frappe.utils.escape_html(u.full_name || u.name)}</span>
						<span class="mds-user-mail">${frappe.utils.escape_html(u.role_profile_name || u.name)}</span>
					</span>
					<span class="mds-count${u.count ? ' has' : ''}">${u.count || 0}</span>
				</button>`;
			})
			.join('');
		this.$root.find('.mds-user-list').html(html || `<div class="mds-muted mds-pad">${__('No users found')}</div>`);
	}

	// ── editor ──────────────────────────────────────────────────────────────

	render_editor() {
		const $editor = this.$root.find('.mds-editor');
		if (!this.user) {
			$editor.html(`
				<div class="mds-blank">
					<h3>${__('Pick a user')}</h3>
					<p>${__('Choose someone on the left to set up the shortcuts on their My Dashboard.')}</p>
				</div>`);
			return;
		}

		const chips = [{ key: 'All', label: __('All') }]
			.concat(this.types)
			.map((t) => `<button type="button" class="mds-chip${this.filter.type === t.key ? ' is-active' : ''}" data-type="${t.key}">${frappe.utils.escape_html(t.label)}</button>`)
			.join('');

		$editor.html(`
			<div class="mds-head">
				<div>
					<h3 class="mds-title">${frappe.utils.escape_html(this.user.full_name || this.user.name)}</h3>
					<div class="mds-muted">${frappe.utils.escape_html(this.user.name)}</div>
				</div>
				<div class="mds-actions">
					<button type="button" class="mds-btn" data-action="copy-from">${__('Copy from user')}</button>
					<button type="button" class="mds-btn" data-action="copy-to">${__('Copy to users')}</button>
					<button type="button" class="mds-btn" data-action="clear">${__('Clear all')}</button>
				</div>
			</div>

			<div class="mds-picker">
				<div class="mds-picker-bar">
					<button type="button" class="mds-btn mds-btn-primary" data-action="toggle-picker">
						${__('Add shortcuts')} <span class="mds-caret">▾</span>
					</button>
					<button type="button" class="mds-btn" data-action="add-link">${__('Add custom link')}</button>
				</div>
				<div class="mds-dropdown" hidden>
					<input class="mds-input mds-pick-search" type="search" placeholder="${__('Search workspaces, dashboards, pages, reports, lists…')}">
					<div class="mds-filters">
						<div class="mds-chips">${chips}</div>
						<select class="mds-input mds-source">
							<option value="all">${__('Custom and ERPNext')}</option>
							<option value="custom">${__('Custom only')}</option>
							<option value="core">${__('ERPNext core only')}</option>
						</select>
					</div>
					<div class="mds-options"></div>
					<div class="mds-dropdown-foot">
						<span class="mds-muted mds-shown"></span>
						<button type="button" class="mds-btn" data-action="toggle-picker">${__('Done')}</button>
					</div>
				</div>
			</div>

			<div class="mds-selected"></div>`);

		$editor.find('.mds-source').val(this.filter.source);
		this.render_items();
	}

	render_items() {
		const $list = this.$root.find('.mds-selected');
		if (!$list.length) return;

		if (!this.items.length) {
			$list.html(`
				<div class="mds-blank mds-blank-small">
					<p>${__('No shortcuts yet. Use "Add shortcuts" to choose what this user sees.')}</p>
				</div>`);
			return;
		}

		const blocked = this.items.filter((item) => item.exists !== false && item.allowed === false).length;
		const note = blocked
			? `<div class="mds-note">${__('{0} shortcut(s) are marked "No access": this user lacks the role or permission to open them, so they stay hidden on their dashboard until access is granted.', [blocked])}</div>`
			: '';

		const rows = this.items
			.map((item, index) => {
				let badge = item.pinned ? `<span class="mds-badge is-pin" title="${__('The user pinned this themselves')}">${__('Pinned by user')}</span>` : '';
				if (item.exists === false) badge += `<span class="mds-badge is-bad">${__('Missing')}</span>`;
				else if (item.allowed === false) badge += `<span class="mds-badge is-warn">${__('No access')}</span>`;
				const meta = [item.type === 'URL' ? item.name : item.module, item.sub].filter(Boolean).join(' · ');
				return `
				<div class="mds-row" data-index="${index}">
					<span class="mds-drag" title="${__('Drag to reorder')}">⋮⋮</span>
					<span class="mds-type" data-kind="${item.type}">${TYPE_LABEL[item.type] || item.type}</span>
					<span class="mds-row-main">
						<input class="mds-input mds-label" type="text" value="${frappe.utils.escape_html(item.label)}"
							placeholder="${frappe.utils.escape_html(item.default_label)}" title="${__('Label shown on the tile')}">
						<span class="mds-muted mds-meta">${frappe.utils.escape_html(meta)}</span>
					</span>
					${badge}
					<button type="button" class="mds-remove" data-action="remove" title="${__('Remove')}">×</button>
				</div>`;
			})
			.join('');

		$list.html(`
			${note}
			<div class="mds-list-head mds-muted">${__('{0} shortcut(s) — shown on the dashboard grouped by type, in this order', [this.items.length])}</div>
			<div class="mds-rows">${rows}</div>`);

		if (window.Sortable) {
			new Sortable($list.find('.mds-rows')[0], {
				handle: '.mds-drag',
				animation: 150,
				onEnd: (event) => {
					if (event.oldIndex === event.newIndex) return;
					const moved = this.items.splice(event.oldIndex, 1)[0];
					this.items.splice(event.newIndex, 0, moved);
					this.set_dirty(true);
					this.render_items();
				},
			});
		}
	}

	// ── dropdown ────────────────────────────────────────────────────────────

	matches() {
		const term = this.filter.term.toLowerCase();
		return this.catalog.filter((item) => {
			if (this.filter.type !== 'All' && item.type !== this.filter.type) return false;
			if (this.filter.source === 'custom' && !item.custom) return false;
			if (this.filter.source === 'core' && item.custom) return false;
			if (!term) return true;
			return (
				item.label.toLowerCase().includes(term) ||
				item.name.toLowerCase().includes(term) ||
				(item.module || '').toLowerCase().includes(term)
			);
		});
	}

	render_picker_list() {
		const $options = this.$root.find('.mds-options');
		if (!$options.length || this.$root.find('.mds-dropdown').prop('hidden')) return;

		const picked = new Set(this.items.map((item) => item.type + '::' + item.name));
		const found = this.matches();
		const html = found
			.slice(0, MAX_ROWS)
			.map((item) => {
				const on = picked.has(item.type + '::' + item.name);
				const meta = [item.module, item.sub].filter(Boolean).join(' · ');
				return `
				<label class="mds-option${on ? ' is-on' : ''}">
					<input type="checkbox" ${on ? 'checked' : ''} data-type="${item.type}" data-name="${frappe.utils.escape_html(item.name)}">
					<span class="mds-type" data-kind="${item.type}">${TYPE_LABEL[item.type]}</span>
					<span class="mds-option-label">${frappe.utils.escape_html(item.label)}</span>
					<span class="mds-muted mds-option-meta">${frappe.utils.escape_html(meta)}</span>
				</label>`;
			})
			.join('');

		$options.html(html || `<div class="mds-muted mds-pad">${__('Nothing matches. Try another search or filter.')}</div>`);
		this.$root
			.find('.mds-shown')
			.text(
				found.length > MAX_ROWS
					? __('Showing {0} of {1} — search to narrow down', [MAX_ROWS, found.length])
					: __('{0} available', [found.length])
			);
	}

	toggle_item(type, name, on) {
		const index = this.items.findIndex((item) => item.type === type && item.name === name);
		if (on && index === -1) {
			const entry = this.catalog.find((item) => item.type === type && item.name === name);
			if (!entry) return;
			this.items.push({
				type: type,
				name: name,
				label: '',
				default_label: entry.label,
				module: entry.module,
				sub: entry.sub,
				exists: true,
				allowed: null,
			});
			this.refresh_access();
		} else if (!on && index !== -1) {
			this.items.splice(index, 1);
		}
		this.set_dirty(true);
		this.render_items();
	}

	// ── actions ─────────────────────────────────────────────────────────────

	add_link() {
		frappe.prompt(
			[
				{ fieldname: 'label', label: __('Label'), fieldtype: 'Data', reqd: 1 },
				{
					fieldname: 'url',
					label: __('Link'),
					fieldtype: 'Data',
					reqd: 1,
					description: __('A desk route such as /app/sales-order/new or a full https:// address.'),
				},
			],
			(values) => {
				const url = values.url.trim();
				if (!/^(\/|https?:\/\/)/i.test(url)) {
					frappe.msgprint(__('The link must start with / or http(s)://'));
					return;
				}
				if (this.items.some((item) => item.type === 'URL' && item.name === url)) return;
				this.items.push({
					type: 'URL', name: url, label: values.label.trim(), default_label: url,
					module: '', sub: null, exists: true, allowed: true,
				});
				this.changed();
			},
			__('Add custom link'),
			__('Add')
		);
	}

	copy_from() {
		const options = this.users.filter((u) => u.count && u.name !== this.user.name).map((u) => u.name);
		if (!options.length) {
			frappe.msgprint(__('No other user has a saved dashboard yet.'));
			return;
		}
		frappe.prompt(
			[{ fieldname: 'source', label: __('Copy shortcuts from'), fieldtype: 'Autocomplete', options: options, reqd: 1 }],
			(values) => {
				frappe.xcall(METHOD + 'get_setup', { user: values.source }).then((data) => {
					this.set_items(data.items);
					this.items.forEach((item) => (item.allowed = null));
					this.changed();
					this.refresh_access();
				});
			},
			__('Copy from user'),
			__('Copy')
		);
	}

	copy_to() {
		if (this.dirty || !this.items.length) {
			frappe.msgprint(__('Save this dashboard first, then copy it to other users.'));
			return;
		}
		const source = this.user.name;
		const dialog = new frappe.ui.Dialog({
			title: __('Copy to users'),
			fields: [
				{
					fieldname: 'targets',
					label: __('Users'),
					fieldtype: 'MultiSelectList',
					reqd: 1,
					get_data: (txt) =>
						this.users
							.filter((u) => u.name !== source)
							.filter((u) => !txt || (u.full_name + ' ' + u.name).toLowerCase().includes(txt.toLowerCase()))
							.map((u) => ({ value: u.name, description: u.full_name || '' })),
				},
				{
					fieldtype: 'HTML',
					options: `<p class="text-muted small">${__('This replaces whatever those users have on their dashboard now.')}</p>`,
				},
			],
			primary_action_label: __('Copy'),
			primary_action: (values) => {
				dialog.hide();
				frappe.xcall(METHOD + 'copy_setup', { source: source, targets: values.targets }).then((done) => {
					done.forEach((name) => {
						const user = this.users.find((u) => u.name === name);
						if (user) user.count = this.items.length;
					});
					this.render_users();
					frappe.show_alert({ message: __('Copied to {0} user(s)', [done.length]), indicator: 'green' });
				});
			},
		});
		dialog.show();
	}

	bind() {
		const $root = this.$root;

		$root.on('input', '.mds-user-search', () => this.render_users());
		$root.on('click', '.mds-user', (e) => this.select_user($(e.currentTarget).attr('data-user')));

		$root.on('click', '[data-action]', (e) => {
			const action = $(e.currentTarget).attr('data-action');
			if (action === 'toggle-picker') {
				const $dropdown = $root.find('.mds-dropdown');
				$dropdown.prop('hidden', !$dropdown.prop('hidden'));
				if (!$dropdown.prop('hidden')) {
					this.render_picker_list();
					$root.find('.mds-pick-search').trigger('focus');
				}
			} else if (action === 'add-link') {
				this.add_link();
			} else if (action === 'copy-from') {
				this.copy_from();
			} else if (action === 'copy-to') {
				this.copy_to();
			} else if (action === 'clear') {
				if (!this.items.length) return;
				frappe.confirm(__('Remove every shortcut from this dashboard?'), () => {
					this.items = [];
					this.changed();
				});
			} else if (action === 'remove') {
				this.items.splice(Number($(e.currentTarget).closest('.mds-row').attr('data-index')), 1);
				this.changed();
			}
		});

		$root.on('input', '.mds-pick-search', (e) => {
			this.filter.term = e.currentTarget.value.trim();
			this.render_picker_list();
		});
		$root.on('change', '.mds-source', (e) => {
			this.filter.source = e.currentTarget.value;
			this.render_picker_list();
		});
		$root.on('click', '.mds-chip', (e) => {
			this.filter.type = $(e.currentTarget).attr('data-type');
			$root.find('.mds-chip').removeClass('is-active');
			$(e.currentTarget).addClass('is-active');
			this.render_picker_list();
		});
		$root.on('change', '.mds-option input', (e) => {
			const box = e.currentTarget;
			$(box).closest('.mds-option').toggleClass('is-on', box.checked);
			this.toggle_item(box.getAttribute('data-type'), box.getAttribute('data-name'), box.checked);
		});

		// Typing a label must not re-render the list, or the input loses focus.
		$root.on('input', '.mds-label', (e) => {
			const index = Number($(e.currentTarget).closest('.mds-row').attr('data-index'));
			if (this.items[index]) {
				this.items[index].label = e.currentTarget.value.trim();
				this.set_dirty(true);
			}
		});
	}
}
})();
