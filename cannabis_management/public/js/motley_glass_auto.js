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


	// ---------------------------------------------------------------- glass menus for native <select>s
	// SOB's "Owner  All ▾": the native select stays in the page (hidden) so every page keeps its own logic; the button
	// shows its value and opens a frosted popover. Picking an option sets the select and fires input + change.
	const CHEV = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
	const TICK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';
	const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
	const VALUE = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
	const on_glass = el => !!(el.closest && el.closest('.mg-glass-page .layout-main-section'));
	let pop = null;

	function label_of(sel) {
		let l = sel.getAttribute('aria-label') || sel.getAttribute('title') || '';
		if (!l && sel.id) { const lab = document.querySelector('label[for="' + CSS.escape(sel.id) + '"]'); if (lab) l = lab.textContent; }
		if (!l) { const fc = sel.closest('.frappe-control'); const cl = fc && fc.querySelector('.control-label'); if (cl) l = cl.textContent; }
		if (!l) { const fc = sel.closest('.frappe-control'); if (fc && fc.dataset.fieldname && sel.closest('.page-form')) l = (frappe.unscrub ? frappe.unscrub(fc.dataset.fieldname) : fc.dataset.fieldname); }
		return (l || '').trim();
	}

	function sync(sel) {
		const btn = sel._mgBtn;
		if (!btn) return;
		const o = sel.options[sel.selectedIndex];
		const text = (o ? o.text : '').trim();
		const label = label_of(sel);
		const show = label && label.length <= 24 && !text.toLowerCase().includes(label.toLowerCase());
		btn.innerHTML = (show ? '<span class="k">' + esc(label) + '</span>' : '') + '<span class="v">' + esc(text || '—') + '</span>' + CHEV;
		btn.disabled = sel.disabled;
		btn.classList.toggle('on', sel.selectedIndex > 0 && !!sel.value);
		btn.title = label ? label + ': ' + text : text;
		sel._mgIdx = sel.selectedIndex;
	}

	function enhance(sel) {
		if (sel._mgBtn || sel.multiple || sel.size > 1 || !on_glass(sel) || sel.closest('[data-mg-native], .modal, .form-grid, .grid-body, .mg-pop')) return;
		const btn = document.createElement('button');
		btn.type = 'button';
		btn.className = 'mg-selbtn';
		btn.setAttribute('aria-haspopup', 'listbox');
		btn.setAttribute('aria-expanded', 'false');
		sel.classList.add('mg-sel-native');
		sel.tabIndex = -1;
		sel.insertAdjacentElement('afterend', btn);
		sel._mgBtn = btn;
		btn._mgSel = sel;
		Object.defineProperty(sel, 'value', { configurable: true, get() { return VALUE.get.call(this); }, set(v) { VALUE.set.call(this, v); sync(this); } });
		sel.addEventListener('change', () => sync(sel));
		btn.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); open_pop(sel, btn); });
		sync(sel);
	}

	function scan(root) {
		if (!root || !root.querySelectorAll) return;
		if (root.tagName === 'SELECT') return enhance(root);
		root.querySelectorAll('select').forEach(enhance);
	}

	function close_pop() {
		if (!pop) return;
		pop._btn && pop._btn.setAttribute('aria-expanded', 'false');
		pop.remove();
		pop = null;
	}

	function open_pop(sel, btn) {
		if (pop && pop._sel === sel) return close_pop();
		close_pop();
		const p = document.createElement('div');
		p.className = 'mg-pop' + (is_dark() ? ' dark' : '');
		p.setAttribute('role', 'listbox');
		p._sel = sel;
		p._btn = btn;
		let html = '';
		const item = (o, i) => '<button type="button" class="mg-pop-i" role="option" data-i="' + i + '" aria-selected="' + (i === sel.selectedIndex) + '"' + (o.disabled ? ' disabled' : '') + '><span class="t">' + TICK + '</span><span>' + esc(o.text) + '</span></button>';
		let i = 0;
		for (const ch of sel.children) {
			if (ch.tagName === 'OPTGROUP') {
				html += '<div class="mg-pop-h">' + esc(ch.label) + '</div>';
				for (const o of ch.children) html += item(o, Array.prototype.indexOf.call(sel.options, o));
			} else if (ch.tagName === 'OPTION') {
				html += item(ch, Array.prototype.indexOf.call(sel.options, ch));
			}
			i++;
		}
		p.innerHTML = html || '<div class="mg-pop-h">—</div>';
		document.body.appendChild(p);
		pop = p;
		btn.setAttribute('aria-expanded', 'true');
		const r = btn.getBoundingClientRect();
		p.style.minWidth = Math.max(r.width, 200) + 'px';
		const w = p.offsetWidth, h = p.offsetHeight;
		const left = Math.max(12, Math.min(r.left, window.innerWidth - w - 12));
		const below = r.bottom + 6 + h <= window.innerHeight - 8 || r.top < h + 14;
		p.style.left = left + 'px';
		p.style.top = (below ? r.bottom + 6 : Math.max(8, r.top - h - 6)) + 'px';
		p.style.setProperty('--mg-origin', (below ? 'top ' : 'bottom ') + (left < r.left + 4 ? 'left' : 'right'));
		p.addEventListener('click', e => {
			const b = e.target.closest('.mg-pop-i');
			if (!b || b.disabled) return;
			const idx = +b.dataset.i;
			close_pop();
			if (idx !== sel.selectedIndex) {
				sel.selectedIndex = idx;
				sync(sel);
				sel.dispatchEvent(new Event('input', { bubbles: true }));
				sel.dispatchEvent(new Event('change', { bubbles: true }));
				if (btn.isConnected) { btn.classList.remove('mg-just-on'); void btn.offsetWidth; btn.classList.add('mg-just-on'); setTimeout(() => btn.classList.remove('mg-just-on'), 450); }
			}
			btn.isConnected && btn.focus();
		});
		p.addEventListener('keydown', e => {
			const items = [...p.querySelectorAll('.mg-pop-i:not([disabled])')];
			const k = items.indexOf(document.activeElement);
			if (e.key === 'Escape') { e.preventDefault(); close_pop(); btn.focus(); }
			else if (e.key === 'ArrowDown') { e.preventDefault(); (items[k + 1] || items[0]).focus(); }
			else if (e.key === 'ArrowUp') { e.preventDefault(); (items[k - 1] || items[items.length - 1]).focus(); }
		});
		const cur = p.querySelector('.mg-pop-i[aria-selected="true"]') || p.querySelector('.mg-pop-i');
		cur && cur.focus({ preventScroll: true });
		cur && cur.scrollIntoView({ block: 'nearest' });
	}

	document.addEventListener('click', e => { if (pop && !pop.contains(e.target) && !(pop._btn && pop._btn.contains(e.target))) close_pop(); });
	window.addEventListener('resize', close_pop);
	window.addEventListener('scroll', e => { if (pop && !pop.contains(e.target)) close_pop(); }, true);
	$(document).on('page-change', close_pop);
	// keep the buttons true when a page changes a select from code (jQuery .val() sets option.selected directly)
	setInterval(() => document.querySelectorAll('.mg-selbtn').forEach(b => { const s = b._mgSel; if (s && s._mgIdx !== s.selectedIndex) sync(s); }), 600);
	// new markup (pages render after their data arrives; boards re-render on every change): enhance at once
	new MutationObserver(muts => {
		for (const m of muts) for (const n of m.addedNodes) if (n.nodeType === 1) scan(n);
	}).observe(document.body, { childList: true, subtree: true });

	// segmented switches: the segment that just turned on springs, like SOB's sliding thumb
	document.addEventListener('click', e => {
		const b = e.target.closest && e.target.closest('.mg-glass-page .layout-main-section button, .mg-glass-page .layout-main-section [role="tab"]');
		if (!b || b.classList.contains('mg-selbtn') || !b.parentElement || b.parentElement.querySelectorAll(':scope > button, :scope > [role="tab"]').length < 2) return;
		const text = b.textContent.trim(), page = b.closest('.page-container');
		requestAnimationFrame(() => requestAnimationFrame(() => {
			const now = [...page.querySelectorAll('[aria-pressed="true"], [aria-selected="true"], .on, .active')]
				.find(x => x.textContent.trim() === text && (x.tagName === 'BUTTON' || x.getAttribute('role') === 'tab'));
			if (!now) return;
			now.classList.remove('mg-just-on'); void now.offsetWidth; now.classList.add('mg-just-on');
			setTimeout(() => now.classList.remove('mg-just-on'), 450);
		}));
	});

	$(document).on('page-change', () => setTimeout(() => { apply(); document.querySelectorAll('.mg-glass-page .layout-main-section').forEach(scan); }, 0));
	$(() => setTimeout(apply, 300));
	// theme switch: re-judge every surface
	new MutationObserver(() => {
		document.querySelectorAll('.mg-auto .mg-clear').forEach(el => el.classList.remove('mg-clear'));
		apply();
	}).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
})();
