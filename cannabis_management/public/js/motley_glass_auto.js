// Motley Glass on every custom Desk page of cannabis_management (the Sales Operation Board look, theme only).
// The pages are listed in frappe.boot.mg_glass_pages (cannabis_management/glass.py). For each one it:
//   - marks the page wrapper (.mg-glass-page .mg-auto) so motley_glass.css gives it the frosted title bar and capsules;
//   - puts the logo-gradient backdrop inside .layout-main-section (z-index 1), where the desk cannot paint over it;
//   - clears the page's own flat background (light in the light theme, dark in the dark theme) so the gradient shows,
//     leaving its cards and coloured panels as they are.
(function () {
	const BG = '<div class="mg-bg" aria-hidden="true"><i></i></div>';
	const watched = new WeakSet();
	let timer = null;

	const listed = name => ((frappe.boot && frappe.boot.mg_glass_pages) || []).includes(name);
	const is_dark = () => document.documentElement.getAttribute('data-theme') === 'dark';

	function rgba(c) {
		const m = /rgba?\(([^)]+)\)/.exec(c || '');
		if (!m) return [0, 0, 0, 0];
		const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
		return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
	}

	// a flat page surface: opaque, and the page tone of the current theme (near white / near black)
	function flat_surface(el) {
		const [r, g, b, a] = rgba(getComputedStyle(el).backgroundColor);
		if (a < 0.4) return null;
		const l = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
		return is_dark() ? l < 0.22 : l > 0.86;
	}

	function clear(section) {
		const visit = (el, depth) => {
			for (const ch of el.children) {
				// already-cleared surfaces are boundaries: what is inside them is the page's own cards
				if (ch.classList.contains('mg-bg') || ch.classList.contains('page-form') || ch.classList.contains('mg-clear')) continue;
				const cs = getComputedStyle(ch);
				if (cs.display === 'none' || cs.position === 'fixed') continue;
				const flat = flat_surface(ch);
				if (flat === null) {
					if (depth < 2) visit(ch, depth + 1); // a see-through wrapper: look one level down
				} else if (flat) {
					ch.classList.add('mg-clear');
				}
			}
		};
		visit(section, 0);
	}

	function apply() {
		clearTimeout(timer);
		const route = frappe.get_route ? frappe.get_route() : [];
		const name = route && route[0];
		if (!name || !listed(name)) return;
		const wrapper = document.getElementById('page-' + name);
		const section = wrapper && wrapper.querySelector('.layout-main-section');
		if (!section) { timer = setTimeout(apply, 150); return; }
		wrapper.classList.add('mg-glass-page', 'mg-auto');
		if (!section.querySelector(':scope > .mg-bg')) section.insertAdjacentHTML('afterbegin', BG);
		clear(section);
		if (!watched.has(section)) {
			watched.add(section);
			let t = null;
			// pages render after their data arrives and re-render on refresh: re-check, debounced
			new MutationObserver(() => { clearTimeout(t); t = setTimeout(() => clear(section), 120); })
				.observe(section, { childList: true, subtree: true });
		}
	}

	$(document).on('page-change', () => setTimeout(apply, 0));
	$(() => setTimeout(apply, 300));
	// theme switch: re-judge every surface
	new MutationObserver(() => {
		document.querySelectorAll('.mg-auto .mg-clear').forEach(el => el.classList.remove('mg-clear'));
		apply();
	}).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
})();
