// Copyright (c) 2026, alltechvirtual.com and contributors
// AR Hub — AR Dashboard, Categorized AR and AR Accountability on one page, one
// tab each.
//
// A tab runs that page's own script and stylesheet, fetched the way the desk
// fetches them (getpage, with the page's role check). So every filter, edit,
// export, email and weekly entry works exactly as on the page itself, and a
// change made to one of those pages shows up here with nothing to keep in step.
// A tab is offered only to someone who may open its page directly.
//
// The scripts run inside a function, not in the shared desk window. They declare
// top-level names there, and AR Accountability's are `const`s: evaluating it
// globally a second time would throw and leave that page blank the next time it
// was opened directly. This file is wrapped in its own scope for the same reason.

(function () {
const ARD_METHOD = 'cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.';
const ARL_METHOD = 'cannabis_management.cannabis_management.page.ar_legacy.ar_legacy.';

// `refresh` reloads a tab's data through its own controls, keeping its filters.
const ARH_TABS = [
	{
		key: 'dashboard', page: 'ar-dashboard', label: __('AR Dashboard'),
		ink: '#1c4587', tint: '#cfe2f3',
		// AR Dashboard has no Refresh button; a report-date change is how its own
		// filters reload. Skipped until its company list has arrived.
		refresh: ($p) => {
			if ($p.find('#ard-company').val()) $p.find('#ard-report-date').trigger('change');
		},
	},
	{
		key: 'categorized', page: 'ar-legacy', label: __('Categorized AR'),
		ink: '#5b21b6', tint: '#ede9fe',
		refresh: ($p) => $p.find('#arl-refresh').trigger('click'),
	},
	{
		key: 'accountability', page: 'ar-weekly-review', label: __('AR Accountability'),
		ink: '#990000', tint: '#f4cccc',
		refresh: ($p) => $p.find('#arw-refresh').trigger('click'),
	},
];

// Saves that change a value another tab also shows. Recon Status and the two
// Yes/No flags are on AR Dashboard and AR Accountability; Segment is on
// Categorized AR and AR Accountability. Each other open tab showing the value
// reloads the next time it is opened; the tab that saved has updated itself.
const ARH_SHOWN_ON = {
	[ARD_METHOD + 'update_recon_status']: ['dashboard', 'accountability'],
	[ARD_METHOD + 'update_ar_flag']: ['dashboard', 'accountability'],
	[ARL_METHOD + 'set_segment']: ['categorized', 'accountability'],
};

const ARH_LAST_TAB = 'ar_hub_tab';

// page name -> that page's on_page_load, evaluated once per session
const arh_modules = {};

frappe.pages['ar-hub'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('AR Hub'),
		single_column: true,
	});
	wrapper.page = page;

	const allowed = (frappe.boot && frappe.boot.page_info) || {};
	const hub = {
		tabs: ARH_TABS.filter((t) => allowed[t.page]).map((t) => Object.assign({}, t)),
		active: null,
	};
	wrapper.arh = hub;

	page.main.html(`
		<div class="arh">
			<div class="arh-tabs" role="tablist">
				${hub.tabs.map((t) => `<button type="button" class="arh-tab" role="tab" data-tab="${t.key}"
					style="--arh-ink:${t.ink};--arh-tint:${t.tint};">${frappe.utils.escape_html(t.label)}</button>`).join('')}
			</div>
			<div class="arh-panes"></div>
		</div>
	`);
	hub.$bar = page.main.find('.arh-tabs');
	hub.$panes = page.main.find('.arh-panes');

	if (!hub.tabs.length) {
		hub.$bar.hide();
		hub.$panes.html(`<div class="arh-msg">${__('You do not have access to AR Dashboard, Categorized AR or AR Accountability.')}</div>`);
		return;
	}

	// Each tab has its own route, so Back, a reload and a shared link all land
	// on the same tab. on_page_show does the switching.
	hub.$bar.on('click', '.arh-tab', function () {
		const key = $(this).attr('data-tab');
		if (key !== hub.active) frappe.set_route('ar-hub', key);
	});

	$(document).on('ajaxSuccess.arh', function (e, xhr, settings) {
		const m = /\/api\/method\/([\w.]+)/.exec((settings && settings.url) || '');
		const shown_on = m && ARH_SHOWN_ON[m[1]];
		if (!shown_on) return;
		// A save made on one of the pages opened directly marks every tab.
		const from_hub = frappe.get_route()[0] === 'ar-hub';
		hub.tabs.forEach((t) => {
			if (!t.$pane || shown_on.indexOf(t.key) === -1) return;
			if (from_hub && t.key === hub.active) return;
			t.stale = true;
		});
	});
};

// Runs on every visit, the first included: the route picks the tab.
frappe.pages['ar-hub'].on_page_show = function (wrapper) {
	const hub = wrapper.arh;
	if (!hub || !hub.tabs.length) return;
	arh_activate(hub, frappe.get_route()[1]);
};

function arh_activate(hub, key) {
	let remembered = null;
	try { remembered = localStorage.getItem(ARH_LAST_TAB); } catch (e) { /* storage blocked */ }
	const tab = hub.tabs.find((t) => t.key === key)
		|| hub.tabs.find((t) => t.key === remembered)
		|| hub.tabs[0];

	hub.active = tab.key;
	try { localStorage.setItem(ARH_LAST_TAB, tab.key); } catch (e) { /* storage blocked */ }
	hub.$bar.find('.arh-tab').each(function () {
		const on = $(this).attr('data-tab') === tab.key;
		$(this).toggleClass('is-active', on).attr('aria-selected', on ? 'true' : 'false');
	});
	hub.$bar[0].style.setProperty('--arh-active', tab.ink);
	hub.$panes.children('.arh-pane').hide();

	if (!tab.$pane) {
		arh_mount(hub, tab);
		return;
	}
	tab.$pane.show();
	if (tab.stale) {
		tab.stale = false;
		tab.refresh(tab.$pane);
	}
}

// First visit to a tab: fetch its page and let it build itself inside the pane.
// The pane stays in place afterwards, so switching back keeps its filters,
// expanded rows and unsaved typing.
function arh_mount(hub, tab) {
	tab.$pane = $(`<div class="arh-pane" data-tab="${tab.key}">
		<div class="arh-msg">${__('Loading {0}…', [frappe.utils.escape_html(tab.label)])}</div>
	</div>`).appendTo(hub.$panes);

	frappe.views.pageview.with_page(tab.page, function () {
		let on_page_load;
		try {
			on_page_load = arh_module(tab.page);
		} catch (err) {
			console.error(err);
			tab.$pane.html(`<div class="arh-msg">${__('{0} could not be loaded.', [frappe.utils.escape_html(tab.label)])}</div>`);
			return;
		}
		tab.$pane.empty();

		// The page builds a full page shell in the pane. That registers it in
		// frappe.ui.pages under this route and retitles the browser tab; both are
		// put back so the hub stays the page the desk knows about.
		const route = frappe.get_route_str();
		const had = Object.prototype.hasOwnProperty.call(frappe.ui.pages, route);
		const ui_page = frappe.ui.pages[route];
		const title = document.title;
		try {
			on_page_load(tab.$pane[0]);
		} finally {
			if (had) frappe.ui.pages[route] = ui_page;
			else delete frappe.ui.pages[route];
			document.title = title;
		}
	});
}

// Evaluate a page's script in its own scope and return its on_page_load. The
// script assigns frappe.pages[name].on_page_load, so it is handed a stand-in for
// the moment it runs; the desk's own entry for that page, if it has been opened,
// is left exactly as it was.
function arh_module(name) {
	if (arh_modules[name]) return arh_modules[name];
	const doc = locals.Page && locals.Page[name];
	if (!doc) throw new Error(`AR Hub: page ${name} is not loaded`);

	const host = {};
	const had = Object.prototype.hasOwnProperty.call(frappe.pages, name);
	const prev = frappe.pages[name];
	frappe.pages[name] = host;
	try {
		new Function(`${doc.__script || doc.script || ''}\n//# sourceURL=ar_hub/${name}.js`)();
	} finally {
		if (had) frappe.pages[name] = prev;
		else delete frappe.pages[name];
	}
	if (typeof host.on_page_load !== 'function') {
		throw new Error(`AR Hub: page ${name} did not define on_page_load`);
	}

	frappe.dom.set_style(doc.style || '', 'arh-style-' + name);
	arh_modules[name] = host.on_page_load;
	return host.on_page_load;
}
})();
