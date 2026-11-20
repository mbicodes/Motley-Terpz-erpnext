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

	const WIDGETS_METHOD = 'cannabis_management.api.my_dashboard.get_widgets';

	const CSS = `
		.md { --md-brand: #6d28d9; font-family: inherit; color: var(--th-text, #1f272e); padding: 2px 2px 28px; }
		.md *, .md *::before, .md *::after { box-sizing: border-box; }
		.md a { color: inherit; text-decoration: none; }
		.md-card { background: var(--th-card, #fff); border: 1px solid var(--th-border, #e5e7eb); border-radius: 22px; }

		/* hero */
		.md-hero { position: relative; overflow: hidden; border-radius: 22px; padding: 26px 28px; color: #fff;
			background: linear-gradient(120deg, #4c1d95 0%, #6d28d9 45%, #a21caf 100%);
			box-shadow: 0 12px 32px -12px rgba(76, 29, 149, .55); }
		.md-hero::before, .md-hero::after { content: ""; position: absolute; border-radius: 50%; pointer-events: none;
			background: radial-gradient(circle, rgba(255, 255, 255, .22), rgba(255, 255, 255, 0) 70%); }
		.md-hero::before { width: 340px; height: 340px; right: -80px; top: -150px; }
		.md-hero::after { width: 240px; height: 240px; right: 220px; bottom: -170px; opacity: .7; }
		.md-hero-row { position: relative; z-index: 1; display: flex; flex-wrap: wrap; gap: 18px; align-items: flex-end; justify-content: space-between; }
		.md-date { font-size: 12px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; opacity: .78; }
		.md-title { font-size: 28px; font-weight: 750; line-height: 1.15; margin: 6px 0 0; color: #fff; letter-spacing: -.01em; }
		.md-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
		.md-chip { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 12px; font-size: 12px; font-weight: 600;
			border-radius: 999px; background: rgba(255, 255, 255, .16); border: 1px solid rgba(255, 255, 255, .22); backdrop-filter: blur(6px); }
		.md-hero-tools { display: flex; flex-wrap: wrap; gap: 8px; }
		.md-hbtn { height: 36px; padding: 0 14px; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; color: #fff;
			display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; border-radius: 10px;
			background: rgba(255, 255, 255, .14); border: 1px solid rgba(255, 255, 255, .28); transition: background .15s; }
		.md-hbtn:hover { background: rgba(255, 255, 255, .26); }
		.md-hbtn svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
		.md-hbtn.is-busy svg { animation: md-spin .8s linear infinite; }
		@keyframes md-spin { to { transform: rotate(360deg); } }

		/* clock */
		.md-clock { position: relative; overflow: hidden; display: flex; flex-direction: column; justify-content: center;
			min-height: 260px; padding: 28px; }
		.md-clock::after { content: ""; position: absolute; right: -90px; top: -90px; width: 260px; height: 260px; border-radius: 50%;
			background: radial-gradient(circle, color-mix(in srgb, var(--md-brand) 16%, transparent), transparent 70%); pointer-events: none; }
		.md-clock-label { font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--th-muted, #6b7280); }
		.md-clock-time { display: flex; align-items: baseline; gap: 10px; margin-top: 10px; font-variant-numeric: tabular-nums; }
		.md-clock-hm { font-size: clamp(48px, 7vw, 84px); font-weight: 750; line-height: 1; letter-spacing: -.03em;
			background: linear-gradient(120deg, #4c1d95, #7c3aed 55%, #c026d3); -webkit-background-clip: text; background-clip: text; color: transparent; }
		.md-clock-s { font-size: clamp(20px, 2.4vw, 28px); font-weight: 700; color: var(--th-muted, #6b7280); min-width: 2ch; }
		.md-clock-ap { font-size: clamp(16px, 1.8vw, 20px); font-weight: 700; color: var(--md-brand); }
		.md-clock-date { margin-top: 12px; font-size: 16px; font-weight: 600; }
		.md-clock-zone { margin-top: 4px; font-size: 12.5px; color: var(--th-muted, #6b7280); }
		.md-clock-bar { position: relative; height: 6px; margin-top: 22px; border-radius: 999px; background: var(--th-subtle, #f3f3f3); overflow: hidden; }
		.md-clock-bar i { position: absolute; inset: 0 auto 0 0; border-radius: inherit;
			background: linear-gradient(90deg, #7c3aed, #c026d3); transition: width .6s; }
		.md-clock-foot { display: flex; justify-content: space-between; margin-top: 6px; font-size: 11.5px; color: var(--th-muted, #6b7280); }

		/* panels */
		.md-panels { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 14px; margin-top: 18px; }
		.md-side { display: grid; gap: 14px; align-content: start; }
		.md-panel { padding: 18px; }
		.md-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
		.md-panel-title { font-size: 15px; font-weight: 700; margin: 0; }
		.md-link { font-size: 12px; font-weight: 600; color: var(--md-brand); }
		.md-link:hover { text-decoration: underline; }

		.md-list { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
		.md-li { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 10px; min-width: 0; }
		.md-li:hover { background: var(--th-subtle, #f3f3f3); }
		.md-dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--th-border, #d1d5db); }
		.md-dot.High { background: #ef4444; } .md-dot.Medium { background: #f59e0b; } .md-dot.Low { background: #10b981; }
		.md-li-text { flex: 1; min-width: 0; }
		.md-li-main { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.md-li-sub { font-size: 11.5px; color: var(--th-muted, #6b7280); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.md-tag { flex: none; padding: 1px 8px; font-size: 11px; font-weight: 600; border-radius: 999px;
			color: var(--th-muted, #6b7280); background: var(--th-subtle, #f3f3f3); }
		.md-tag.late { color: #b91c1c; background: color-mix(in srgb, #ef4444 14%, var(--th-card, #fff)); }
		.md-none { padding: 14px 8px; font-size: 13px; color: var(--th-muted, #6b7280); }

		/* skeleton */
		.md-skel { position: relative; overflow: hidden; background: var(--th-subtle, #f3f3f3); border-radius: 22px; }
		.md-skel::after { content: ""; position: absolute; inset: 0; transform: translateX(-100%);
			background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .45), transparent); animation: md-shine 1.3s infinite; }
		@keyframes md-shine { to { transform: translateX(100%); } }

		/* shortcuts */
		.md-section { margin-top: 26px; }
		.md-section-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; margin-bottom: 4px; }
		.md-section-title { font-size: 18px; font-weight: 700; margin: 0; }
		.md-search { height: 36px; width: 260px; max-width: 100%; padding: 0 12px; font: inherit; font-size: 13px;
			color: var(--th-text, #1f272e); background: var(--th-card, #fff);
			border: 1px solid var(--th-border, #e5e7eb); border-radius: 10px; outline: none; }
		.md-search:focus { border-color: var(--md-brand); box-shadow: 0 0 0 3px color-mix(in srgb, var(--md-brand) 18%, transparent); }
		.md-btn { height: 34px; padding: 0 12px; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer;
			color: var(--th-text, #1f272e); background: var(--th-card, #fff);
			border: 1px solid var(--th-border, #e5e7eb); border-radius: 10px;
			display: inline-flex; align-items: center; white-space: nowrap; }
		.md-btn:hover { background: var(--th-subtle, #f3f3f3); }
		.md-group { margin-top: 18px; }
		.md-group-title { display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 700; letter-spacing: .07em;
			text-transform: uppercase; color: var(--th-muted, #6b7280); margin: 0 0 10px; }
		.md-group-title span { padding: 0 7px; border-radius: 999px; background: var(--th-subtle, #f3f3f3); letter-spacing: 0; }
		.md-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
		.md-cell { position: relative; min-width: 0; }
		.md-tile { display: flex; gap: 12px; align-items: center; height: 100%; padding: 14px 40px 14px 14px; min-width: 0;
			background: var(--th-card, #fff); border: 1px solid var(--th-border, #e5e7eb); border-radius: 14px;
			transition: border-color .15s, transform .15s, box-shadow .15s; }
		.md-tile:hover { border-color: var(--md-accent); transform: translateY(-2px);
			box-shadow: 0 10px 22px -14px color-mix(in srgb, var(--md-accent) 80%, transparent); }
		.md-tile:focus-visible { outline: 2px solid var(--md-accent); outline-offset: 2px; }
		.md-icon { flex: 0 0 40px; height: 40px; border-radius: 14px; display: grid; place-items: center; color: #fff;
			background: linear-gradient(135deg, var(--md-accent), color-mix(in srgb, var(--md-accent) 65%, #000)); }
		.md-icon svg { width: 19px; height: 19px; fill: none; stroke: currentColor; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
		.md-text { min-width: 0; }
		.md-label { font-size: 14px; font-weight: 600; line-height: 1.3; overflow-wrap: anywhere; }
		.md-meta { font-size: 12px; color: var(--th-muted, #6b7280); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.md-pinned { position: absolute; top: 10px; right: 12px; width: 7px; height: 7px; border-radius: 50%; background: var(--md-brand); }
		.md-unpin { position: absolute; top: 8px; right: 8px; width: 28px; height: 28px; display: grid; place-items: center;
			padding: 0; color: var(--th-muted, #6b7280); background: var(--th-card, #fff); border: 1px solid var(--th-border, #e5e7eb);
			border-radius: 10px; cursor: pointer; opacity: 0; transition: opacity .15s; z-index: 1; }
		.md-unpin svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
		.md-cell:hover .md-unpin, .md-unpin:focus-visible { opacity: 1; }
		.md-unpin:hover { color: #b91c1c; border-color: #fca5a5; }
		@media (hover: none) { .md-unpin { opacity: 1; } }
		.md-empty { padding: 44px 20px; text-align: center; background: var(--th-card, #fff);
			border: 1px dashed var(--th-border, #e5e7eb); border-radius: 22px; margin-top: 14px; }
		.md-empty h3 { font-size: 16px; font-weight: 700; margin: 0 0 6px; }
		.md-empty p { font-size: 13px; color: var(--th-muted, #6b7280); margin: 0 0 14px; }
		.md-hidden { display: none !important; }

		@media (max-width: 900px) {
			.md-panels { grid-template-columns: 1fr; }
			.md-hero { padding: 22px 20px; }
			.md-title { font-size: 23px; }
		}
	`;

	const REFRESH_ICON = '<path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/>';
	const COG_ICON = '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>';

	function esc(value) {
		return frappe.utils.escape_html(value == null ? '' : String(value));
	}

	function greeting() {
		const hour = new Date().getHours();
		if (hour < 12) return __('Good morning');
		if (hour < 18) return __('Good afternoon');
		return __('Good evening');
	}

	// ── shortcuts ─────────────────────────────────────────────────────────────

	function tile(item) {
		const external = /^https?:\/\//i.test(item.route);
		const meta = [item.module, item.sub].filter(Boolean).join(' · ');
		return `
			<div class="md-cell" data-search="${esc((item.label + ' ' + meta).toLowerCase())}">
				<a class="md-tile" href="${esc(item.route)}" style="--md-accent:${ACCENTS[item.type] || '#64748b'}"
					${external ? 'target="_blank" rel="noopener"' : 'data-desk="1"'}>
					<span class="md-icon"><svg viewBox="0 0 24 24">${ICONS[item.type] || ICONS.URL}</svg></span>
					<span class="md-text">
						<div class="md-label">${esc(item.label)}</div>
						${meta ? `<div class="md-meta">${esc(meta)}</div>` : ''}
					</span>
				</a>
				${item.pinned ? `<span class="md-pinned" title="${__('You pinned this')}"></span>` : ''}
				<button type="button" class="md-unpin" title="${__('Remove from My Dashboard')}"
					data-type="${esc(item.type)}" data-name="${esc(item.name)}"><svg viewBox="0 0 24 24">${UNPIN_ICON}</svg></button>
			</div>`;
	}

	function shortcuts(data) {
		const total = data.groups.reduce((sum, group) => sum + group.items.length, 0);
		const setup = data.can_setup
			? `<a class="md-btn" data-desk="1" href="${esc(data.setup_route)}">${__('Set up dashboards')}</a>`
			: '';

		if (!total) {
			const message = data.configured
				? __('The shortcuts chosen for you need access you do not have yet. Ask your administrator.')
				: __('Nothing pinned yet. Use the pin icon next to any page title to add it here.');
			return `
				<section class="md-section">
					<div class="md-section-head"><h3 class="md-section-title">${__('Your shortcuts')}</h3></div>
					<div class="md-empty"><h3>${__('No shortcuts yet')}</h3><p>${message}</p>${setup}</div>
				</section>`;
		}

		const groups = data.groups
			.map(
				(group) => `
				<section class="md-group">
					<h4 class="md-group-title">${esc(group.label)} <span>${group.items.length}</span></h4>
					<div class="md-grid">${group.items.map(tile).join('')}</div>
				</section>`
			)
			.join('');

		return `
			<section class="md-section">
				<div class="md-section-head">
					<h3 class="md-section-title">${__('Your shortcuts')}</h3>
					${total > 8 ? `<input class="md-search" type="search" placeholder="${__('Search shortcuts')}">` : ''}
				</div>
				${groups}
				<div class="md-empty md-hidden" data-none><p style="margin:0">${__('No shortcuts match your search.')}</p></div>
			</section>`;
	}

	// ── widgets ───────────────────────────────────────────────────────────────

	function clock_card() {
		return `
			<div class="md-card md-clock" data-clock>
				<div class="md-clock-label">${__('Local time')}</div>
				<div class="md-clock-time">
					<span class="md-clock-hm" data-hm>--:--</span>
					<span class="md-clock-s" data-s></span>
					<span class="md-clock-ap" data-ap></span>
				</div>
				<div class="md-clock-date" data-date></div>
				<div class="md-clock-zone" data-zone></div>
				<div class="md-clock-bar" title="${__('How much of the day has passed')}"><i data-bar></i></div>
				<div class="md-clock-foot"><span>${__('Day progress')}</span><span data-pct></span></div>
			</div>`;
	}

	// One ticker per holder; it stops itself once the dashboard leaves the page.
	function start_clock(holder) {
		clearInterval(holder.__md_clock);
		const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
		const parts_fmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' });
		const date_fmt = new Intl.DateTimeFormat(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

		function tick() {
			const card = holder.querySelector('[data-clock]');
			if (!card || !card.isConnected) {
				clearInterval(holder.__md_clock);
				return;
			}
			const now = new Date();
			const parts = {};
			parts_fmt.formatToParts(now).forEach((p) => (parts[p.type] = p.value));
			card.querySelector('[data-hm]').textContent = `${parts.hour}:${parts.minute}`;
			card.querySelector('[data-s]').textContent = parts.second || '';
			card.querySelector('[data-ap]').textContent = parts.dayPeriod || '';
			card.querySelector('[data-date]').textContent = date_fmt.format(now);
			card.querySelector('[data-zone]').textContent = zone.replace(/_/g, ' ');
			const secs = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
			const pct = Math.round((secs / 86400) * 100);
			card.querySelector('[data-bar]').style.width = pct + '%';
			card.querySelector('[data-pct]').textContent = pct + '%';
		}

		tick();
		holder.__md_clock = setInterval(tick, 1000);
	}

	function todo_panel(todos, user) {
		const today = frappe.datetime.get_today();
		const rows = (todos || [])
			.map((t) => {
				const late = t.date && t.date < today;
				const tag = t.date
					? `<span class="md-tag${late ? ' late' : ''}">${esc(frappe.datetime.str_to_user(t.date))}</span>`
					: '';
				return `<li><a class="md-li" data-desk="1" href="${esc(t.route)}">
					<span class="md-dot ${esc(t.priority || '')}"></span>
					<span class="md-li-text"><div class="md-li-main">${esc(t.text)}</div>${t.ref ? `<div class="md-li-sub">${esc(t.ref)}</div>` : ''}</span>
					${tag}</a></li>`;
			})
			.join('');
		return `
			<div class="md-card md-panel">
				<div class="md-panel-head">
					<h4 class="md-panel-title">${__('My tasks')}</h4>
					<a class="md-link" data-desk="1" href="/app/todo?status=Open&allocated_to=${encodeURIComponent(user)}">${__('View all')} →</a>
				</div>
				${rows ? `<ul class="md-list">${rows}</ul>` : `<div class="md-none">${__('No open tasks. Nice.')}</div>`}
			</div>`;
	}

	function recent_panel(recent) {
		const rows = (recent || [])
			.map(
				(r) => `<li><a class="md-li" data-desk="1" href="${esc(r.route)}">
					<span class="md-dot" style="background:${'#a78bfa'}"></span>
					<span class="md-li-text"><div class="md-li-main">${esc(r.label)}</div></span>
					<span class="md-tag">${esc(r.sub)}</span></a></li>`
			)
			.join('');
		return `
			<div class="md-card md-panel">
				<div class="md-panel-head"><h4 class="md-panel-title">${__('Recently visited')}</h4></div>
				${rows ? `<ul class="md-list">${rows}</ul>` : `<div class="md-none">${__('Pages you open will show up here.')}</div>`}
			</div>`;
	}

	function widgets(w, user) {
		return `<div class="md-panels">${clock_card()}<div class="md-side">${todo_panel(w.todos, user)}${recent_panel(w.recent)}</div></div>`;
	}

	function widget_skeleton() {
		return `<div class="md-panels"><div class="md-skel" style="height:280px"></div><div class="md-skel" style="height:280px"></div></div>`;
	}

	// ── page ──────────────────────────────────────────────────────────────────

	function hero(data) {
		const first = (data.full_name || '').split(' ')[0];
		const total = data.groups.reduce((sum, group) => sum + group.items.length, 0);
		const pinned = data.groups.reduce((sum, group) => sum + group.items.filter((i) => i.pinned).length, 0);
		const date = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
		return `
			<div class="md-hero">
				<div class="md-hero-row">
					<div>
						<div class="md-date">${esc(date)}</div>
						<h2 class="md-title">${esc(greeting())}${first ? ', ' + esc(first) : ''}</h2>
						<div class="md-chips">
							<span class="md-chip">${__('{0} shortcuts', [total])}</span>
							${pinned ? `<span class="md-chip">${__('{0} pinned by you', [pinned])}</span>` : ''}
						</div>
					</div>
					<div class="md-hero-tools">
						<button type="button" class="md-hbtn" data-action="refresh"><svg viewBox="0 0 24 24">${REFRESH_ICON}</svg>${__('Refresh')}</button>
						${data.can_setup ? `<a class="md-hbtn" data-desk="1" href="${esc(data.setup_route)}"><svg viewBox="0 0 24 24">${COG_ICON}</svg>${__('Set up dashboards')}</a>` : ''}
					</div>
				</div>
			</div>`;
	}

	function load_widgets(holder, user, refresh) {
		const slot = holder.querySelector('[data-widgets]');
		if (!slot) return Promise.resolve();
		return frappe
			.xcall(WIDGETS_METHOD, { refresh: refresh ? 1 : 0 })
			.then((w) => {
				if (!slot.isConnected) return;
				slot.innerHTML = widgets(w, user);
				start_clock(holder);
			})
			.catch(() => {
				if (!slot.isConnected) return;
				slot.innerHTML = widgets({ todos: [], recent: [] }, user);
				start_clock(holder);
			});
	}

	function wire(holder) {
		// Plain left-clicks go through the desk router; modified clicks keep the
		// browser's own behaviour (new tab, new window). Bound once per holder:
		// unpinning re-renders into the same element.
		if (!holder.__md_wired) holder.addEventListener('click', function (event) {
			const target = event.target;
			const refresh = target.closest && target.closest('[data-action="refresh"]');
			if (refresh) {
				refresh.classList.add('is-busy');
				load_widgets(holder, frappe.session.user, true).finally(() => refresh.classList.remove('is-busy'));
				return;
			}
			const unpin = target.closest && target.closest('.md-unpin');
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
			const link = target.closest && target.closest('a[data-desk]');
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
		holder.innerHTML = `<style>${CSS}</style><div class="md"><div class="md-skel" style="height:150px;border-radius:22px"></div>${widget_skeleton()}</div>`;

		frappe
			.xcall(METHOD)
			.then(function (data) {
				holder.innerHTML = `<style>${CSS}</style>
					<div class="md">${hero(data)}<div data-widgets>${widget_skeleton()}</div>${shortcuts(data)}</div>`;
				wire(holder);
				load_widgets(holder, data.user, false);
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
		/* small grey pin right beside the title; brand colour once pinned (theme review #5).
		   Uses the Liquid Glass tokens when infix_theme is active, plain fallbacks otherwise. */
		.md-pin-btn { flex: none; display: inline-grid; place-items: center; width: 26px; height: 26px; margin: 0 0 0 4px;
			padding: 0; color: var(--lg-fg-3, #6b7280); background: transparent; border: 0;
			border-radius: 50%; cursor: pointer; transition: color .15s, background .15s; }
		.md-pin-btn svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2;
			stroke-linecap: round; stroke-linejoin: round; transform: rotate(35deg); transition: transform .15s; }
		.md-pin-btn:hover { color: var(--lg-fg, #1a1622); background: var(--lg-press, #f3f3f3); }
		.md-pin-btn.is-pinned { color: var(--lg-accent, #5a1ab0); }
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
