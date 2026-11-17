// My Dashboard — renders the shortcuts an administrator picked for the signed-in
// user. Called from the "My Dashboard" Custom HTML Block on the workspace of the
// same name; the block only holds a one-line call so the code stays in the app.
//
// The block lives in a shadow root, so the styles are injected here (page CSS
// does not reach in) and links are routed by hand (Frappe's own link handler
// cannot see anchors inside a shadow root, which would mean a full page reload).
// Colours use the --th-* theme bridge variables, which do inherit into the
// shadow root, so light and dark both work.

(function () {
	frappe.provide('cannabis_management.my_dashboard');

	const METHOD = 'cannabis_management.api.my_dashboard.get_my_dashboard';
	const PIN_METHOD = 'cannabis_management.api.my_dashboard.';

	const ICONS = {
		Workspace: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
		Dashboard: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
		Page: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
		Report: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/>',
		DocType: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
		URL: '<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
	};

	const PIN_ICON = '<path d="M12 17v5"/><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3z"/>';
	const UNPIN_ICON = '<path d="M12 17v5"/><path d="M9 3h6l-1 6 3 3v2H7v-2l3-3z"/><path d="M3 3l18 18"/>';

	const ACCENTS = {
		Workspace: '#6366f1',
		Dashboard: '#0ea5e9',
		Page: '#10b981',
		Report: '#f59e0b',
		DocType: '#8b5cf6',
		URL: '#64748b',
	};

	const CSS = `
		.md { font-family: inherit; color: var(--th-text, #1f272e); padding: 4px 2px 24px; }
		.md-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; justify-content: space-between; margin-bottom: 20px; }
		.md-title { font-size: 22px; font-weight: 700; line-height: 1.2; margin: 0; }
		.md-sub { font-size: 13px; color: var(--th-muted, #6b7280); margin-top: 4px; }
		.md-tools { display: flex; gap: 8px; align-items: center; }
		.md-search { height: 34px; width: 240px; max-width: 100%; padding: 0 12px; font: inherit; font-size: 13px;
			color: var(--th-text, #1f272e); background: var(--th-control, #f0f0f0);
			border: 1px solid var(--th-border, #e5e7eb); border-radius: 8px; outline: none; }
		.md-search:focus { border-color: #6366f1; }
		.md-btn { height: 34px; padding: 0 12px; font: inherit; font-size: 13px; font-weight: 500; cursor: pointer;
			color: var(--th-text, #1f272e); background: var(--th-card, #fff);
			border: 1px solid var(--th-border, #e5e7eb); border-radius: 8px; text-decoration: none;
			display: inline-flex; align-items: center; white-space: nowrap; }
		.md-btn:hover { background: var(--th-subtle, #f3f3f3); }
		.md-group { margin-top: 22px; }
		.md-group-title { font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
			color: var(--th-muted, #6b7280); margin: 0 0 10px; }
		.md-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
		.md-tile { display: flex; gap: 12px; align-items: center; padding: 14px; min-width: 0;
			background: var(--th-card, #fff); border: 1px solid var(--th-border, #e5e7eb); border-radius: 12px;
			color: inherit; text-decoration: none; transition: border-color .15s, transform .15s, box-shadow .15s; }
		.md-tile:hover { border-color: var(--md-accent); transform: translateY(-1px); box-shadow: 0 4px 14px rgba(0, 0, 0, .08); }
		.md-tile:focus-visible { outline: 2px solid var(--md-accent); outline-offset: 2px; }
		.md-icon { flex: 0 0 38px; height: 38px; border-radius: 10px; display: grid; place-items: center;
			color: var(--md-accent); background: color-mix(in srgb, var(--md-accent) 14%, var(--th-card, #fff)); }
		.md-icon svg { width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 1.8;
			stroke-linecap: round; stroke-linejoin: round; }
		.md-text { min-width: 0; }
		.md-label { font-size: 14px; font-weight: 600; line-height: 1.3; overflow-wrap: anywhere; }
		.md-meta { font-size: 12px; color: var(--th-muted, #6b7280); margin-top: 2px;
			white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.md-empty { padding: 48px 20px; text-align: center; background: var(--th-card, #fff);
			border: 1px dashed var(--th-border, #e5e7eb); border-radius: 12px; }
		.md-empty h3 { font-size: 16px; font-weight: 600; margin: 0 0 6px; }
		.md-empty p { font-size: 13px; color: var(--th-muted, #6b7280); margin: 0 0 14px; }
		.md-cell { position: relative; min-width: 0; }
		.md-cell .md-tile { height: 100%; padding-right: 40px; }
		.md-unpin { position: absolute; top: 8px; right: 8px; width: 28px; height: 28px; display: grid; place-items: center;
			padding: 0; color: var(--th-muted, #6b7280); background: var(--th-card, #fff); border: 1px solid var(--th-border, #e5e7eb);
			border-radius: 8px; cursor: pointer; opacity: 0; transition: opacity .15s; }
		.md-unpin svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
		.md-cell:hover .md-unpin, .md-unpin:focus-visible { opacity: 1; }
		.md-unpin:hover { color: #b91c1c; border-color: #fca5a5; }
		@media (hover: none) { .md-unpin { opacity: 1; } }
		.md-hidden { display: none !important; }
	`;

	function esc(value) {
		return frappe.utils.escape_html(value == null ? '' : String(value));
	}

	function greeting() {
		const hour = new Date().getHours();
		if (hour < 12) return __('Good morning');
		if (hour < 18) return __('Good afternoon');
		return __('Good evening');
	}

	function tile(item) {
		const external = /^https?:\/\//i.test(item.route);
		const meta = [item.module, item.sub].filter(Boolean).join(' · ');
		return `
			<div class="md-cell" data-search="${esc((item.label + ' ' + meta).toLowerCase())}">
			<a class="md-tile" href="${esc(item.route)}" style="--md-accent:${ACCENTS[item.type] || '#64748b'}"
				data-search="${esc((item.label + ' ' + meta).toLowerCase())}"
				${external ? 'target="_blank" rel="noopener"' : 'data-desk="1"'}>
				<span class="md-icon"><svg viewBox="0 0 24 24">${ICONS[item.type] || ICONS.URL}</svg></span>
				<span class="md-text">
					<div class="md-label">${esc(item.label)}</div>
					${meta ? `<div class="md-meta">${esc(meta)}</div>` : ''}
				</span>
			</a>
			<button type="button" class="md-unpin" title="${__('Remove from My Dashboard')}"
				data-type="${esc(item.type)}" data-name="${esc(item.name)}"><svg viewBox="0 0 24 24">${UNPIN_ICON}</svg></button>
			</div>`;
	}

	function body(data) {
		const first = (data.full_name || '').split(' ')[0];
		const total = data.groups.reduce((sum, group) => sum + group.items.length, 0);
		const setup = data.can_setup
			? `<a class="md-btn" data-desk="1" href="${esc(data.setup_route)}">${__('Set up dashboards')}</a>`
			: '';

		let content;
		if (!total) {
			const message = data.configured
				? __('The shortcuts chosen for you need access you do not have yet. Ask your administrator.')
				: __('Your administrator has not set up your dashboard yet.');
			content = `<div class="md-empty"><h3>${__('Nothing here yet')}</h3><p>${message}</p>${setup}</div>`;
		} else {
			content = data.groups
				.map(
					(group) => `
					<section class="md-group">
						<h4 class="md-group-title">${esc(group.label)}</h4>
						<div class="md-grid">${group.items.map(tile).join('')}</div>
					</section>`
				)
				.join('');
			content += `<div class="md-empty md-hidden" data-none><p style="margin:0">${__('No shortcuts match your search.')}</p></div>`;
		}

		return `
			<div class="md">
				<div class="md-head">
					<div>
						<h2 class="md-title">${esc(greeting())}${first ? ', ' + esc(first) : ''}</h2>
						<div class="md-sub">${__('Your shortcuts')}</div>
					</div>
					<div class="md-tools">
						${total > 8 ? `<input class="md-search" type="search" placeholder="${__('Search shortcuts')}">` : ''}
						${total ? setup : ''}
					</div>
				</div>
				${content}
			</div>`;
	}

	function wire(holder) {
		// Plain left-clicks go through the desk router; modified clicks keep the
		// browser's own behaviour (new tab, new window). Bound once per holder:
		// unpinning re-renders into the same element.
		if (!holder.__md_wired) holder.addEventListener('click', function (event) {
			const unpin = event.target.closest && event.target.closest('.md-unpin');
			if (unpin) {
				event.preventDefault();
				unpin.disabled = true;
				frappe
					.xcall(PIN_METHOD + 'unpin', { item_type: unpin.dataset.type, link_name: unpin.dataset.name })
					.then(function (routes) {
						pins.set(routes);
						cannabis_management.my_dashboard.render(holder);
						frappe.show_alert({ message: __('Removed from My Dashboard'), indicator: 'blue' });
					})
					.catch(function () { unpin.disabled = false; });
				return;
			}
			const link = event.target.closest && event.target.closest('a[data-desk]');
			if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
			event.preventDefault();
			frappe.set_route(link.getAttribute('href'));
		});
		holder.__md_wired = true;

		const search = holder.querySelector('.md-search');
		if (!search) return;
		search.addEventListener('input', function () {
			const term = search.value.trim().toLowerCase();
			let shown = 0;
			holder.querySelectorAll('.md-group').forEach(function (group) {
				let visible = 0;
				group.querySelectorAll('.md-cell').forEach(function (el) {
					const match = !term || el.dataset.search.indexOf(term) !== -1;
					el.classList.toggle('md-hidden', !match);
					if (match) visible++;
				});
				group.classList.toggle('md-hidden', !visible);
				shown += visible;
			});
			holder.querySelector('[data-none]').classList.toggle('md-hidden', shown > 0);
		});
	}

	cannabis_management.my_dashboard.render = function (root) {
		const holder = root.querySelector('.my-dashboard-root') || root;
		holder.innerHTML = `<style>${CSS}</style><div class="md"><div class="md-sub">${__('Loading…')}</div></div>`;

		frappe
			.xcall(METHOD)
			.then(function (data) {
				holder.innerHTML = `<style>${CSS}</style>${body(data)}`;
				wire(holder);
			})
			.catch(function () {
				holder.innerHTML = `<style>${CSS}</style><div class="md"><div class="md-empty"><p style="margin:0">${__('Could not load your dashboard. Refresh to try again.')}</p></div></div>`;
			});
	};
	// ── pin button on every desk page ──────────────────────────────────────
	//
	// A pin sits beside the title of every desk page (workspaces, reports,
	// dashboards, pages, lists, forms). Hover shows what it does; a click adds
	// the page to the user's own My Dashboard, or takes it off again. The state
	// comes from one call at load and the reply of each pin/unpin.

	const pins = {
		routes: null,
		set(routes) { this.routes = new Set(routes || []); },
		load() {
			if (this._loading) return this._loading;
			this._loading = frappe.xcall(PIN_METHOD + 'get_my_pins').then((routes) => {
				this.set(routes);
				return this.routes;
			}).catch(() => { this._loading = null; });
			return this._loading;
		},
		has(path) { return !!this.routes && this.routes.has(norm(path)); },
	};

	function norm(path) {
		let value = path || '';
		try { value = decodeURIComponent(value); } catch (e) { /* keep as is */ }
		return value.split('?')[0].split('#')[0].replace(/\/+$/, '').toLowerCase();
	}

	function current_path() {
		return window.location.pathname;
	}

	function pinnable() {
		const route = frappe.get_route() || [];
		if (!window.location.pathname.startsWith('/app/') || !route.length) return false;
		if (route[0] === 'my-dashboard-setup') return false;
		if (route[0] === 'Workspaces' && route[route.length - 1] === 'My Dashboard') return false;
		if (route[0] === 'Workspaces' && route.length === 1) return false;
		if (route[0] === 'Form' && route[2] && String(route[2]).startsWith('new-')) return false;
		return true;
	}

	function page_title($page) {
		const text = ($page.find('.page-head .title-text').first().text() || document.title || '').trim();
		return text.replace(/\s+/g, ' ');
	}

	const PIN_CSS = `
		.md-pin-btn { flex: none; display: inline-grid; place-items: center; width: 30px; height: 30px; margin: 0 6px 0 8px;
			padding: 0; color: var(--th-muted, #6b7280); background: transparent; border: 1px solid transparent;
			border-radius: 8px; cursor: pointer; transition: color .15s, background .15s, border-color .15s; }
		.md-pin-btn svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 2;
			stroke-linecap: round; stroke-linejoin: round; transform: rotate(35deg); transition: transform .15s; }
		.md-pin-btn:hover { color: #6366f1; background: var(--th-subtle, #f3f3f3); border-color: var(--th-border, #e5e7eb); }
		.md-pin-btn.is-pinned { color: #6366f1; }
		.md-pin-btn.is-pinned svg { fill: currentColor; transform: rotate(0deg); }
		.md-pin-btn[disabled] { opacity: .5; cursor: progress; }
	`;

	function ensure_css() {
		if (document.getElementById('md-pin-css')) return;
		const style = document.createElement('style');
		style.id = 'md-pin-css';
		style.textContent = PIN_CSS;
		document.head.appendChild(style);
	}

	function paint($btn) {
		const on = pins.has(current_path());
		const tip = on ? __('Pinned to My Dashboard — click to remove') : __('Pin to My Dashboard');
		$btn.toggleClass('is-pinned', on).attr({ title: tip, 'aria-label': tip, 'aria-pressed': on ? 'true' : 'false' });
	}

	function place_button() {
		const $page = $(frappe.container && frappe.container.page);
		if (!$page.length) return;
		const $area = $page.find('.page-head .title-area').first();
		let $btn = $page.find('.md-pin-btn');

		if (!pinnable() || !$area.length) {
			$btn.remove();
			return;
		}
		if (!$btn.length) {
			$btn = $(`<button type="button" class="md-pin-btn"><svg viewBox="0 0 24 24">${PIN_ICON}</svg></button>`);
			const $title_block = $area.children().first();
			if ($title_block.length) $title_block.after($btn);
			else $area.prepend($btn);
		}
		paint($btn);
	}

	function toggle_pin(btn) {
		const $btn = $(btn);
		const path = current_path();
		const was = pins.has(path);
		$btn.prop('disabled', true);

		const call = was
			? frappe.xcall(PIN_METHOD + 'unpin', { path: path })
			: frappe.xcall(PIN_METHOD + 'pin', {
				route: frappe.get_route(),
				path: path + window.location.search,
				title: page_title($(frappe.container.page)),
			});

		call.then((routes) => {
			pins.set(routes);
			frappe.show_alert({
				message: was ? __('Removed from My Dashboard') : __('Pinned to My Dashboard'),
				indicator: was ? 'blue' : 'green',
			});
		}).finally(() => {
			$btn.prop('disabled', false);
			paint($btn);
		});
	}

	function refresh_soon() {
		[50, 400, 1200].forEach((delay) => setTimeout(place_button, delay));
	}

	$(document).on('click', '.md-pin-btn', function (event) {
		event.preventDefault();
		event.stopPropagation();
		toggle_pin(this);
	});

	$(function () {
		if (!frappe.session || frappe.session.user === 'Guest' || !frappe.router) return;
		ensure_css();
		pins.load().then(refresh_soon);
		frappe.router.on('change', refresh_soon);
		// Forms and reports often redraw their header after the route settles.
		$(document).on('form-refresh page-change', refresh_soon);
	});
})();
