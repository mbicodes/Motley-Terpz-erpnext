/* Toll Processing Hub (Custom HTML Block). Frappe runs this inside the block's shadow root and gives it
   `root_element`; query through it, not `document`. Source of truth: cannabis_management/toll/hub/. */
(function () {
	const $ = id => root_element.getElementById(id);
	const hub = $('hub');
	const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
	const fmt = (n, d) => Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
	const money = n => (window.format_currency ? format_currency(n || 0, (frappe.boot.sysdefaults || {}).currency || 'USD') : '$' + fmt(n, 2));
	const plural = (n, one, many) => fmt(n) + ' ' + (n === 1 ? one : many);
	const STAGES = [['Received', '#8e8e93'], ['Queued for Wash', '#5856d6'], ['Washed', '#ff9f0a'], ['Pressed', '#d2691e'],
		['Ready to Return', '#34c759'], ['Returned', '#0a84ff'], ['Invoiced', '#af52de']];
	const COLOR = Object.fromEntries(STAGES);
	const I = {
		board: '<path d="M4 5h4v14H4zM10 5h4v9h-4zM16 5h4v6h-4z"/>',
		stock: '<path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 12l9 4 9-4M3 17l9 4 9-4"/>',
		chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
		jobs: '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="M8 8h8M8 12h8M8 16h5"/>',
		users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5"/><path d="M16 4.5a3.2 3.2 0 0 1 0 6.3M21.5 20c-.5-2.6-1.9-4.3-3.8-5.1"/>',
		move: '<path d="M4 7h13l-3-3M20 17H7l3 3"/>',
		truck: '<path d="M2 6h11v10H2zM13 10h5l3 3v3h-8"/><circle cx="6" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
		invoice: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
	};
	const svg = p => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;

	// dark mode follows the desk theme (the shadow root cannot see html[data-theme])
	const sync_theme = () => hub.classList.toggle('dark', document.documentElement.getAttribute('data-theme') === 'dark');
	sync_theme();
	new MutationObserver(sync_theme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

	// the hub is the whole workspace: drop the theme's glass frame around this one widget
	try {
		const host = root_element.host && root_element.host.closest('.widget');
		if (host) host.classList.add('toll-hub-host');
		if (!document.getElementById('toll-hub-host-css')) {
			const st = document.createElement('style');
			st.id = 'toll-hub-host-css';
			st.textContent = '.widget.toll-hub-host,.widget.toll-hub-host:hover{background:transparent!important;border:0!important;box-shadow:none!important;padding:0!important;-webkit-backdrop-filter:none!important;backdrop-filter:none!important}' +
				'.widget.toll-hub-host::before,.widget.toll-hub-host::after{display:none!important}.widget.toll-hub-host>.widget-head{display:none!important}.widget.toll-hub-host>.widget-body{padding:0!important}';
			document.head.appendChild(st);
		}
	} catch (e) { /* cosmetic only */ }

	function render(d) {
		const k = d.kpis, t = d.totals;
		if (d.can && d.can.produce) {
			$('hero-acts').insertAdjacentHTML('beforeend', '<a class="btn" href="/app/toll-processing-board?receive=1">+ Receive Material</a>');
		}
		const kpi = (l, v, s, cls) => `<div class="kpi ${cls || ''}"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
		$('kpis').innerHTML =
			kpi('Open jobs', fmt(k.open_jobs), plural(t.jobs, 'job in total', 'jobs in total')) +
			kpi('FF on hand', fmt(k.ff_on_hand_lbs, 1) + ' lbs', 'in Toll Inbound') +
			kpi('Bubble Hash in WIP', fmt(k.bh_wip_grams) + ' g', 'waiting to press') +
			kpi('Ready to ship', fmt(k.output_ready_grams) + ' g', 'BH and rosin in Toll Output') +
			kpi('Past promised date', fmt(k.overdue), k.uninvoiced_returned ? plural(k.uninvoiced_returned, 'returned job not invoiced', 'returned jobs not invoiced') : 'all returns invoiced', k.overdue || k.uninvoiced_returned ? 'attn' : '');
		$('pipe').innerHTML = STAGES.map(([s, c]) =>
			`<a class="stage" href="/app/toll-processing-board" style="--c:${c}" title="Open the board"><i></i>${s}<b>${fmt(d.counts[s] || 0)}</b></a>`).join('');
		const tile = (href, icon, grad, title, desc) => `<a class="tile" href="${href}"><span class="ic" style="--g:${grad}">${svg(I[icon])}</span><div><div class="t">${title}</div><div class="d">${desc}</div></div></a>`;
		$('tiles').innerHTML = [
			tile('/app/toll-processing-board', 'board', 'linear-gradient(135deg,#6a2bc4,#4d129e)', 'Toll Processing Board', plural(k.open_jobs, 'open job', 'open jobs')),
			tile('/app/toll-stock-on-hand', 'stock', 'linear-gradient(135deg,#34c759,#248a3d)', 'Toll Stock On Hand', fmt(k.ff_on_hand_lbs, 1) + ' lbs FF, ' + fmt(k.bh_wip_grams + k.output_ready_grams) + ' g BH and rosin'),
			tile('/app/toll-job-yield-summary', 'chart', 'linear-gradient(135deg,#ff9f0a,#d2691e)', 'Toll Job Yield Summary', k.ff_washed_lbs ? 'Wash ' + fmt(k.wash_yield, 2) + '%, press ' + fmt(k.press_yield, 1) + '%' : 'no washes yet'),
			tile('/app/toll-job', 'jobs', 'linear-gradient(135deg,#5ac8fa,#0a84ff)', 'Toll Jobs', plural(t.jobs, 'job', 'jobs')),
			tile('/app/customer?customer_group=Toll%20Clients', 'users', 'linear-gradient(135deg,#bf5af2,#8944ab)', 'Toll Clients', plural(t.clients, 'client', 'clients')),
			tile('/app/stock-entry?toll_job=%5B%22is%22%2C%22set%22%5D', 'move', 'linear-gradient(135deg,#64d2ff,#30b0c7)', 'Toll Stock Entries', plural(t.stock_entries, 'stock entry', 'stock entries')),
			tile('/app/delivery-note?toll_job=%5B%22is%22%2C%22set%22%5D', 'truck', 'linear-gradient(135deg,#30d158,#00a86b)', 'Toll Returns', plural(t.returns, 'delivery note', 'delivery notes')),
			tile('/app/sales-invoice?toll_job=%5B%22is%22%2C%22set%22%5D', 'invoice', 'linear-gradient(135deg,#ff375f,#c4234a)', 'Toll Invoices', plural(t.invoices, 'invoice', 'invoices') + ' · ' + money(t.invoiced)),
		].join('');
		$('recent').innerHTML = d.recent.length ? d.recent.map(j => `<a class="row" href="/app/toll-job/${encodeURIComponent(j.name)}">
			<div class="who"><div class="n">${esc(j.name)}${j.priority === 'Rush' ? ' · Rush' : ''}</div><div class="c">${esc(j.customer_name || j.customer)}</div>
			<div class="st">${esc(j.strain)} · ${fmt(j.ff_received_lbs, 1)} lbs · ${esc(j.return_type)}</div></div>
			<span class="tag ${j.overdue ? 'late' : ''}" style="--c:${COLOR[j.status] || '#8e8e93'}"><i></i>${esc(j.overdue ? 'Overdue' : j.status)}</span></a>`).join('')
			: '<div class="empty">No toll jobs yet. Use Receive Material when a client delivers.</div>';
		const chip = (href, label, n) => `<a class="chip" href="${href}">${label}${n != null ? ` <b>${fmt(n)}</b>` : ''}</a>`;
		$('setup').innerHTML = [
			chip('/app/item?item_group=Toll%20-%20Customer%20Owned', 'Toll items'),
			chip('/app/warehouse?parent_warehouse=Toll%20Warehouses%20-%20MTM', 'Toll warehouses'),
			chip('/app/batch?toll_job=%5B%22is%22%2C%22set%22%5D', 'Toll batches', t.batches),
			chip('/app/customer?customer_group=Toll%20Clients', 'Toll clients', t.clients),
			chip('/app/item/TOLL-SVC', 'Service item TOLL-SVC'),
			chip('/app/account/view/tree', 'Chart of Accounts'),
			chip('/app/query-report/Toll Stock On Hand', 'Standard reports'),
		].join('');
		$('updated').textContent = 'Live · ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	frappe.call({ method: 'cannabis_management.toll.api.get_hub_data' })
		.then(r => render(r.message))
		.catch(() => { $('kpis').innerHTML = '<div class="empty">The toll numbers could not be loaded.</div>'; });
})();
