// Motley Glass on every custom Desk page of cannabis_management (the Sales Operation Board look, theme only).
// The pages are listed in frappe.boot.mg_glass_pages (cannabis_management/glass.py). For each one it:
//   - marks the page wrapper (.mg-glass-page .mg-auto) so motley_glass.css gives it the frosted title bar and capsules;
//   - puts the logo-gradient backdrop inside .layout-main-section (z-index 1), where the desk cannot paint over it;
//   - clears the page's own flat background (light in the light theme, dark in the dark theme) so the gradient shows,
//     leaving its cards and coloured panels as they are.
(function () {
	const BG = '<div class="mg-bg" aria-hidden="true"><i></i><i class="mg-bg-lead"></i></div>';
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
		bars(section, name);
		dedupe_title(wrapper, section);
		// pages fill in after their data arrives: look for a repeated title again while it settles
		[800, 2500].forEach(ms => setTimeout(() => { if ((frappe.get_route() || [])[0] === name) dedupe_title(wrapper, section); }, ms));
		if (!watched.has(section)) {
			watched.add(section);
			let t = null;
			// pages render after their data arrives and re-render on refresh: re-check, debounced
			new MutationObserver(() => {
				clearTimeout(t);
				t = setTimeout(() => {
					if (!section.querySelector(':scope > .mg-bg')) section.insertAdjacentHTML('afterbegin', BG);
					clear(section);
					bars(section, name);
					dedupe_title(wrapper, section);
				}, 120);
			}).observe(section, { childList: true, subtree: true });
		}
	}

	// ---------------------------------------------------------------- one title per page
	// Many pages print their own heading with the same words as the Desk title bar ("Accounts Receivable" twice).
	// The title bar stays (it carries the pin and the frosted scroll pill); the repeated heading near the top of the
	// page body is hidden, its subtitle / "As of" badge stay. Pages that hide the title bar keep their own heading.
	const norm_title = t => (t || '').toLowerCase().replace(/&/g, ' and ').replace(/[^a-z0-9]+/g, ' ')
		.replace(/\b(report|dashboard|page|board)\b/g, ' ').replace(/\s+/g, ' ').trim();
	function dedupe_title(wrapper, section) {
		const tt = wrapper.querySelector('.page-head .title-text');
		if (!tt || !tt.offsetParent) return;
		const tcs = getComputedStyle(tt);
		if (tcs.visibility === 'hidden' || +tcs.opacity < 0.2) return;
		const want = norm_title(tt.textContent);
		if (!want) return;
		// a heading hidden earlier whose words changed since (a company name filled in after the data came) is the
		// page's own information, not a repeat: show it again
		const done = section.querySelector('.mg-dup-title');
		if (done) {
			if (norm_title(done.textContent) === want) return;
			done.classList.remove('mg-dup-title');
			done._mgNotDup = true;
		}
		const top0 = section.getBoundingClientRect().top;
		for (const h of section.querySelectorAll('h1, h2, h3, h4, [class*="title"], [class*="heading"], [class*="name"]')) {
			if (h.closest('.page-form, .mg-fbar, .mg-segbar, .modal, table, .mg-card, .sob-card, .mg-pop, [data-mg-native]')) continue;
			const r = h.getBoundingClientRect();
			if (!r.height || r.top - top0 > 420) continue;
			if (h._mgNotDup || h.querySelector('input, select, button, table, canvas')) continue;
			// a heading with an empty slot still to be filled ("Inventory Movements – <span></span>") is not judged yet
			if ([...h.querySelectorAll('*')].some(x => !x.children.length && !x.textContent.trim() && !x.matches('svg *, svg, i, img, br'))) continue;
			if (parseFloat(getComputedStyle(h).fontSize) < 16 && !/^H[1-4]$/.test(h.tagName)) continue;
			if (norm_title(h.textContent) === want) { h.classList.add('mg-dup-title'); return; }
		}
	}

	// ---------------------------------------------------------------- glass filter bars
	// SOB's tool bar (one floating glass capsule: segments, search, "Owner All ▾" menus) for each page's own filter
	// block. A filter block is the outermost box around two or more filter pieces (fields, or a segmented switch /
	// view tabs) that holds nothing else: no table, chart, heading or tall content card, near the top of the page.
	// Labelled fields become one "Label  Value ▾" group each and the whole block flows as one wrapping capsule row,
	// like SOB. A switch or tab row that stands on its own (company pills, view tabs) becomes a glass capsule of
	// segments (.mg-segbar). Only classes are added (layout and looks come from motley_glass_auto.css), so the page's
	// own logic never changes. Per page: MG_BAR_EXTRA adds blocks the heuristic misses, MG_BAR_SKIP keeps a block as
	// it is, MG_PANEL keeps a page's multi-row filter grid in its own layout (glass skin only); data-mg-native on any
	// ancestor opts out too.
	const MG_BAR_EXTRA = {};
	const MG_BAR_SKIP = {};
	const MG_PANEL = {};
	const FIELD_TYPES = ['text', 'search', 'date', 'number', 'month', 'week', 'datetime-local', 'time', ''];
	const NOT_A_BAR = 'table, canvas, textarea, iframe, h1, h2, h3, h4, .datatable, .frappe-chart, .chart-container, .mg-bg, .mg-card, .sob-card';
	const OUTSIDE = 'table, .modal, .mg-pop, [data-mg-native], .datatable, .page-form, .mg-glass, .form-grid, .mg-fbar-skip, .dropdown-menu, .mg-card, .sob-card';
	// the segment that is on: the page's own state classes / aria (kept in step with motley_glass_auto.css)
	const ON = '.active, .on, .selected, .is-active, .is-on, .current, [aria-selected="true"], [aria-pressed="true"], [class*="-active"], [class*="_active"]';
	const BTN = 'button:not(.mg-selbtn):not(.mg-pop-i), .btn, [role="tab"]';
	const shown = el => el.offsetParent !== null || getComputedStyle(el).position === 'fixed';

	function filter_field(el) {
		if (el.closest(OUTSIDE)) return false;
		if (el.classList.contains('mg-selbtn')) return true;
		if (el.tagName === 'SELECT') return !el.multiple && !(el.size > 1) && !el._mgBtn && el.offsetParent !== null;
		if (el.tagName === 'INPUT') return FIELD_TYPES.includes((el.getAttribute('type') || '').toLowerCase()) && el.offsetParent !== null;
		return false;
	}
	const fields_in = el => [...el.querySelectorAll('select, input, .mg-selbtn')].filter(filter_field);

	// a segmented switch or a row of view tabs: two or more short buttons side by side in one row, one of them on
	// (or a tablist). Pager dots, card action rows and vertical menus are not.
	// a segment: a button / tab, or a clickable tab-like span ("<span class='ue-tab on' data-tab=…>")
	const SEG_KID = 'button, a, .btn, [role="tab"], [data-tab]';
	const seg_kid = k => k.matches(SEG_KID) || (/(^|[\s_-])(tab|pill|chip|seg|segment|opt)([\s_-]|$)/i.test(typeof k.className === 'string' ? k.className : '') && getComputedStyle(k).cursor === 'pointer');
	function seg_group(el) {
		if (el.children.length < 2 || el.children.length > 16 || el.closest(OUTSIDE)) return false;
		const kids = [...el.children].filter(k => !k.classList.contains('mg-thumb') && getComputedStyle(k).display !== 'none');
		const segk = kids.filter(k => seg_kid(k) && !k.matches('.mg-selbtn, .mg-pop-i') && k.textContent.trim() && k.textContent.trim().length <= 34);
		if (segk.length < 2) return false;
		// after the tabs the row may carry one or two filters of its own ("… | Retail CPG   Period: [ ]")
		const last = kids.indexOf(segk[segk.length - 1]);
		const extra = kids.filter(k => !segk.includes(k));
		if (extra.length && !(extra.length <= 2 && extra.every(x => kids.indexOf(x) > last && x.querySelector('input, select')))) return false;
		if (el.getAttribute('role') !== 'tablist' && !segk.some(k => k.matches(ON))) return false;
		const r = el.getBoundingClientRect();
		return r.width > 0 && r.height > 0 && r.height <= 60;
	}
	function segs_in(root) {
		const parents = new Set();
		root.querySelectorAll('button, [role="tab"], a.btn, [data-tab], [class*="-tab"], [class*="pill"], [class*="chip"]').forEach(b => b.parentElement && parents.add(b.parentElement));
		return [...parents].filter(seg_group);
	}
	// filter pieces inside a box: fields, switches, and loose buttons (Apply, Export)
	function pieces(el) {
		const segs = segs_in(el).concat(seg_group(el) ? [el] : []);
		const loose = [...el.querySelectorAll(BTN)].filter(b => shown(b) && !segs.some(g => g.contains(b)));
		const multi = [...el.querySelectorAll('select[multiple], select[size]:not([size="1"]):not([size="0"])')].filter(m => shown(m) && !m.closest(OUTSIDE)).length;
		return { fields: fields_in(el).length + multi, segs: segs.length, loose: loose.length };
	}

	// a box that is only filters: short, near the top, no content of its own
	function bar_like(a, top0) {
		if (a.matches(NOT_A_BAR) || a.querySelector(NOT_A_BAR)) return false;
		const r = a.getBoundingClientRect();
		if (!r.width || r.height > 240 || r.top - top0 > 760) return false;
		// every child is a filter piece: holds a field or a button, or is a short label / hint line
		for (const ch of a.children) {
			if (ch.matches('select, input, button, label, .btn, .mg-selbtn, .mg-sel-native')) continue;
			if (ch.querySelector('select, input, button, .btn, .mg-selbtn')) continue;
			if (getComputedStyle(ch).display === 'none') continue;
			if (ch.getBoundingClientRect().height > 44 || ch.textContent.trim().length > 60) return false;
		}
		return true;
	}

	// a filter block has at least one real filter piece: a menu, a date, a search box or a switch. A box of plain
	// labelled text fields (name, e-mail, licence number) is a data-entry form, never a filter bar.
	function filterish(el) {
		if (segs_in(el).length || seg_group(el) || el.querySelector('.mg-selbtn, select')) return true;
		return fields_in(el).some(i => i.tagName === 'INPUT' && (/^(search|date|month|week|datetime-local|time|number)$/i.test(i.type)
			|| /^\s*(search|filter|find)/i.test(i.placeholder || '') || /search|filter|date|picker/i.test(i.className)
			|| ['Date', 'Datetime', 'Link', 'Select'].includes((i.closest('.frappe-control[data-fieldtype]') || { dataset: {} }).dataset.fieldtype)));
	}

	function bars(section, name) {
		const skip = (MG_BAR_SKIP[name] || []).join(', ');
		const top0 = section.getBoundingClientRect().top;
		const found = new Set(), alone = new Set();
		const starts = [...fields_in(section).map(f => [f, false]), ...segs_in(section).map(g => [g, true])];
		for (const [f, is_seg] of starts) {
			if (f.closest('.mg-fbar, .mg-fpanel, .mg-segbar') || (skip && f.closest(skip))) continue;
			let best = null;
			for (let a = f.parentElement, d = 0; a && a !== section && d < 8; a = a.parentElement, d++) {
				if (!bar_like(a, top0)) break;
				const p = pieces(a);
				if (p.fields + p.segs >= 2) best = a;
			}
			if (best && seg_group(best)) alone.add(best);
			else if (best && filterish(best)) found.add(best);
			else if (is_seg) alone.add(f);
		}
		(MG_BAR_EXTRA[name] || []).forEach(s => section.querySelectorAll(s).forEach(el => found.add(el)));
		for (const b of found) {
			if (b.classList.contains('mg-fbar') || b.classList.contains('mg-fpanel') || [...found].some(o => o !== b && o.contains(b))) continue;
			mark_bar(b, name);
		}
		// bars the page re-rendered inside (new filter markup in the same box): walk them again
		section.querySelectorAll('.mg-fbar').forEach(b => { if (!found.has(b)) mark_bar(b, name); });
		for (const g of alone) {
			if (g.closest('.mg-fbar, .mg-fpanel')) continue;
			g.classList.add('mg-segbar');
			for (const k of g.children) k.classList.toggle('mg-seg-x', !!k.querySelector('input, select'));
		}
		section.querySelectorAll('.mg-fbar, .mg-segbar, .mg-fpanel').forEach(tone);
		section.querySelectorAll('.mg-segbar, .mg-fbar .mg-fseg').forEach(glide);
	}

	// the bar sits on a dark surface of the page (a navy hero, a dark page): it takes SOB's dark glass instead
	function on_dark(el) {
		for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
			const cs = getComputedStyle(a);
			let c = rgba(cs.backgroundColor);
			if (c[3] < 0.5 && cs.backgroundImage && cs.backgroundImage.includes('gradient')) {
				const cols = [...cs.backgroundImage.matchAll(/rgba?\([^)]+\)/g)].map(m => rgba(m[0])).filter(x => x[3] >= 0.5);
				if (cols.length) c = [0, 1, 2].map(i => cols.reduce((s, x) => s + x[i], 0) / cols.length).concat([1]);
			}
			if (c[3] >= 0.5) return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255 < 0.35;
			if (a.classList.contains('layout-main-section')) return is_dark();
		}
		return is_dark();
	}
	const tone = el => el.classList.toggle('mg-dk', !is_dark() && on_dark(el));

	// a quiet label beside a field: no control inside, a few words
	function label_piece(el) {
		if (el.matches('select, input, button, .btn, .mg-selbtn, .mg-sel-native, svg, i, img, br') || el.querySelector('select, input, button, .btn, .mg-selbtn')) return false;
		const t = el.textContent.trim();
		return t.length > 0 && t.length <= 40 && getComputedStyle(el).display !== 'none';
	}

	// one capsule row: a box of more than two pieces is flattened (display:contents); a box of one or two pieces (a
	// labelled field, a From / To pair, a switch with its label) stays a box and lays its label + field side by side
	// (.mg-fgroup), so its own popovers keep their anchor; a row of buttons becomes a segmented group (.mg-fseg)
	function mark_bar(b, name) {
		const p = pieces(b);
		if (!b.classList.contains('mg-fbar') && (MG_PANEL[name] || p.fields + p.segs + p.loose > 18)) {
			b.classList.add('mg-fpanel');
			b.querySelectorAll('select').forEach(s => s._mgBtn && sync(s));
			return;
		}
		b.classList.add('mg-fbar');
		const walk = (el, depth) => {
			for (const ch of el.children) {
				if (ch.matches('select, input, button, .btn, .mg-selbtn, .mg-sel-native, svg, i, img, br')) continue;
				if (ch.classList.contains('mg-fseg') || ch.classList.contains('mg-thumb')) continue;
				if (label_piece(ch)) { ch.classList.add('mg-flabel'); continue; }
				if (ch.matches('.frappe-control')) { ch.classList.add('mg-fgroup', 'mg-fctl'); continue; }
				const q = pieces(ch);
				const n = q.fields + q.segs + q.loose;
				if (!n) continue;
				if (seg_group(ch) || (!q.fields && q.loose >= 2 && [...ch.children].every(x => x.matches('button, .btn, a, .mg-thumb') || getComputedStyle(x).display === 'none'))) { ch.classList.add('mg-fseg'); continue; }
				if (ch.tagName === 'LABEL' && !q.fields && ch.querySelector('input[type="checkbox"], input[type="radio"]')) continue;
				// two labelled cells side by side are two groups, not one
				const holders = [...ch.children].filter(x => !x.matches('select, input, button, .btn, .mg-selbtn, .mg-sel-native') && (x.querySelector('select, input, button, .btn, .mg-selbtn')));
				const grp = n <= 2 && holders.length <= 1;
				ch.classList.add(grp ? 'mg-fgroup' : 'mg-fwrap');
				// "<label>Partner <select>": the label's own words become a quiet label span beside the field
				if (grp && ch.tagName === 'LABEL') {
					for (const t of [...ch.childNodes]) {
						if (t.nodeType === 3 && t.textContent.trim()) { const sp = document.createElement('span'); sp.className = 'mg-flabel'; sp.textContent = t.textContent.trim(); t.replaceWith(sp); }
					}
				}
				if (depth < 6) walk(ch, depth + 1);
			}
		};
		walk(b, 0);
		// a long hint inside a toggle button (<small>) goes to the tooltip: the capsule stays one line
		b.querySelectorAll('button small, .btn small').forEach(sm => { const t = sm.textContent.trim(); if (t.length <= 20) return; sm.classList.add('mg-fhint'); const btn = sm.closest('button, .btn'); if (btn && !btn.title) btn.title = t; });
		// a text field reads as SOB's search capsule; when the page draws its own magnifier beside it, room is left for that
		const not_search = i => { const fc = i.closest('.frappe-control[data-fieldtype]'); return (fc && !['Data', 'Link', 'Dynamic Link', 'Autocomplete'].includes(fc.dataset.fieldtype)) || /date|time|picker/i.test(i.className); };
		b.querySelectorAll('input[type="text"], input[type="search"], input:not([type])').forEach(i => !not_search(i) && i.classList.add(i.parentElement.querySelector(':scope > svg, :scope > i, :scope > .icon, :scope > [class*="icon"]') ? 'mg-fsearch-own' : 'mg-fsearch'));
		b.querySelectorAll('select').forEach(s => s._mgBtn && sync(s));
	}


	// ---------------------------------------------------------------- SOB segment motion (every page)
	// The Sales Operation Board's Leads <-> Deals movement, ported from its seg_sync / bind_segs onto every glass switch
	// and tab row: the selected segment is its own white thumb that slides to the new segment on SOB's spring;
	// pressing a segment lifts the thumb into a clear lens that swells over the labels and magnifies them, and it can
	// be dragged along the row and let go on another segment; and the page's first switch crossfades the backdrop
	// between SOB's Deals (gold) and Leads (lavender) gradients, like the Leads / Deals switch. The thumb only follows
	// the page's own "on" state (ON); a drag ends in a plain click on the chosen segment, so page logic is untouched.
	const seg_pos = {};
	const seg_items = g => [...g.children].filter(k => !k.classList.contains('mg-thumb') && !k.classList.contains('mg-seg-x') && getComputedStyle(k).display !== 'none');
	function seg_key(g) {
		const pg = g.closest('.page-container');
		return (pg ? pg.id : '') + '|' + seg_items(g).map(x => x.textContent.replace(/[\d,.$%]+/g, '').trim()).join('|').slice(0, 120);
	}
	// the page's first switch (top of the page) plays SOB's board switch: every change the user makes on it crossfades
	// the backdrop between the Deals (gold) and Leads (lavender) gradients
	let last_input = 0;
	['pointerdown', 'keydown'].forEach(t => document.addEventListener(t, () => { last_input = performance.now(); }, true));
	function board(g, idx, prev) {
		const sec = g.closest('.layout-main-section');
		if (!sec || [...sec.querySelectorAll('.mg-glide')].find(x => x.offsetParent) !== g) return;
		if (!sec.hasAttribute('data-mg-board')) sec.setAttribute('data-mg-board', 'deal');
		if (!prev || prev.idx === idx || performance.now() - last_input > 2500 || sec._mgFlipFor === last_input) return;
		// one crossfade per user action, however many times the page re-renders the switch on the way
		sec._mgFlipFor = last_input;
		sec.setAttribute('data-mg-board', sec.getAttribute('data-mg-board') === 'lead' ? 'deal' : 'lead');
	}
	function glide(g) {
		if (!g.isConnected || !g.offsetWidth) return;
		let th = g.querySelector(':scope > .mg-thumb');
		if (!th) {
			th = document.createElement('span');
			th.className = 'mg-thumb still';
			th.setAttribute('aria-hidden', 'true');
			th.innerHTML = '<span class="mg-lens"></span>';
			g.prepend(th);
			if (!g.classList.contains('mg-glide')) g.classList.add('mg-glide');
			watch_seg(g);
		}
		if (th.classList.contains('lift')) return;  // a finger is on it
		const items = seg_items(g);
		const on = items.find(k => k.matches(ON));
		if (!on || !on.offsetWidth) {
			th.style.opacity = '0';
			if (g.classList.contains('mg-has-thumb')) g.classList.remove('mg-has-thumb');
			return;
		}
		const x = on.offsetLeft, w = on.offsetWidth, idx = items.indexOf(on);
		const key = seg_key(g), prev = seg_pos[key];
		const place = (px, pw, anim) => { th.classList.toggle('still', !anim); th.style.translate = `${px}px 0`; th.style.width = `${pw}px`; };
		th.style.top = on.offsetTop + 'px';
		th.style.height = on.offsetHeight + 'px';
		th.style.borderRadius = getComputedStyle(on).borderTopLeftRadius;
		th.style.opacity = '1';
		if (!g.classList.contains('mg-has-thumb')) g.classList.add('mg-has-thumb');
		if (!th._placed && prev && (prev.x !== x || prev.w !== w)) {
			// a re-rendered row starts where its thumb was, then slides
			place(prev.x, prev.w, false);
			void th.offsetWidth;
			place(x, w, true);
		} else if (!prev || prev.x !== x || prev.w !== w || !th._placed) place(x, w, !!th._placed);
		board(g, idx, prev);
		th._placed = true;
		seg_pos[key] = { x, w, idx };
	}
	function watch_seg(g) {
		let raf = 0;
		new MutationObserver(muts => {
			if (!muts.some(m => m.target !== g && !(m.target.closest && m.target.closest('.mg-thumb')))) return;
			cancelAnimationFrame(raf);
			raf = requestAnimationFrame(() => glide(g));
		}).observe(g, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'aria-pressed', 'aria-selected'] });
	}

	// press: the thumb lifts into a lens that swells over the labels and magnifies them; drag it across, let go to choose
	(function () {
		let drag = null, seg_t = 0;
		const COPY = ['fontFamily', 'fontSize', 'fontWeight', 'letterSpacing', 'textTransform', 'gap', 'paddingLeft', 'paddingRight', 'justifyContent', 'lineHeight'];
		const fill = (g, th) => {
			// the lens shows a copy of the labels, laid out like the real ones; the lens's swell magnifies it
			const inner = document.createElement('div');
			inner.className = 'mg-lens-in';
			seg_items(g).forEach(it => {
				const c = it.cloneNode(true);
				c.removeAttribute('id');
				c.querySelectorAll('[id]').forEach(x => x.removeAttribute('id'));
				['data-tip', 'aria-describedby', 'onclick', 'name', 'for', 'href'].forEach(a => c.removeAttribute(a));
				c.setAttribute('tabindex', '-1');
				c.setAttribute('aria-hidden', 'true');
				const cs = getComputedStyle(it);
				COPY.forEach(k => { c.style[k] = cs[k]; });
				if (c.style.justifyContent === 'normal') c.style.justifyContent = 'center';
				Object.assign(c.style, { left: it.offsetLeft + 'px', top: it.offsetTop + 'px', width: it.offsetWidth + 'px', height: it.offsetHeight + 'px' });
				inner.appendChild(c);
			});
			th.querySelector('.mg-lens').replaceChildren(inner);
			return inner;
		};
		const move = (x, anim) => {
			drag.th.classList.toggle('still', !anim);
			drag.th.style.translate = `${x}px 0`;
			drag.inner.style.translate = `${-x}px ${-drag.y}px`;
			drag.x = x;
		};
		const row = d => seg_items(d.g).filter(it => it.offsetTop === d.y);
		const settle = pick => {
			const d = drag;
			drag = null;
			if (!d) return;
			d.th.classList.remove('lift');
			setTimeout(() => { if (!d.th.classList.contains('lift')) { const l = d.th.querySelector('.mg-lens'); if (l) l.replaceChildren(); } }, 320);
			// a plain tap lets the browser's own click through (the page's handlers see a normal click); a drag clicks
			// the segment it was let go on
			const target = pick && d.moved ? pick(d) : null;
			if (target && !target.matches(ON)) { seg_t = performance.now(); target.click(); }
			glide(d.g);
		};
		const nearest = d => {
			const mid = d.x + d.w / 2;
			return row(d).reduce((best, it) => (Math.abs(it.offsetLeft + it.offsetWidth / 2 - mid) < Math.abs(best.offsetLeft + best.offsetWidth / 2 - mid) ? it : best), d.item);
		};
		document.addEventListener('pointerdown', e => {
			const g = e.target.closest && e.target.closest('.mg-glide');
			if (!g || e.button !== 0 || drag) return;
			const it = [...g.children].find(c => c.contains(e.target));
			const th = g.querySelector(':scope > .mg-thumb');
			if (!it || !th || it === th || it.classList.contains('mg-seg-x') || it.disabled) return;
			drag = { g, th, item: it, start: e.clientX, x0: it.offsetLeft, x: th._placed ? parseFloat(th.style.translate) || 0 : it.offsetLeft, w: it.offsetWidth, y: it.offsetTop, moved: false, pid: e.pointerId };
			th.style.width = it.offsetWidth + 'px';
			th.style.top = it.offsetTop + 'px';
			th.style.height = it.offsetHeight + 'px';
			th.style.opacity = '1';
			if (!g.classList.contains('mg-has-thumb')) g.classList.add('mg-has-thumb');
			drag.inner = fill(g, th);
			move(drag.x, false);
			void th.offsetWidth;
			th.classList.add('lift');
			// the lens jumps under the finger, magnifying the pressed label
			move(it.offsetLeft, true);
		}, true);
		document.addEventListener('pointermove', e => {
			if (!drag || e.pointerId !== drag.pid) return;
			const dx = e.clientX - drag.start;
			if (!drag.moved && Math.abs(dx) < 4) return;
			drag.moved = true;
			const r = row(drag);
			if (!r.length) return;
			const last = r[r.length - 1];
			move(Math.max(r[0].offsetLeft, Math.min(last.offsetLeft + last.offsetWidth - drag.w, drag.x0 + dx)), false);
		}, { passive: true });
		document.addEventListener('pointerup', e => { if (drag && e.pointerId === drag.pid) settle(nearest); }, true);
		document.addEventListener('pointercancel', e => { if (drag && e.pointerId === drag.pid) settle(null); }, true);
		// the lens chose the segment already: drop the browser's own click that follows the pointerup
		document.addEventListener('click', e => {
			if (e.isTrusted && performance.now() - seg_t < 500 && e.target.closest && e.target.closest('.mg-glide')) { e.stopPropagation(); e.preventDefault(); }
		}, true);
		window.addEventListener('resize', () => document.querySelectorAll('.mg-glide').forEach(g => glide(g)), { passive: true });
	})();

	// ---------------------------------------------------------------- glass menus for native <select>s
	// SOB's "Owner  All ▾": the native select stays in the page (hidden) so every page keeps its own logic; the button
	// shows its value and opens a frosted popover. Picking an option sets the select and fires input + change.
	const CHEV = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
	const TICK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';
	const esc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
	const VALUE = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
	const on_glass = el => !!(el.closest && el.closest('.mg-glass-page .layout-main-section'));
	let pop = null;

	// the field's label; sel._mgLabelShown = that label is already printed on the page next to the field
	function label_of(sel) {
		sel._mgLabelShown = false;
		const seen = el => { if (el && el.offsetParent !== null && !el.closest('.mg-selbtn')) sel._mgLabelShown = true; };
		let l = sel.getAttribute('aria-label') || sel.getAttribute('title') || '';
		if (!l && sel.id) { const lab = document.querySelector('label[for="' + CSS.escape(sel.id) + '"]'); if (lab) { l = lab.textContent; seen(lab); } }
		if (!l) { const fc = sel.closest('.frappe-control'); const cl = fc && fc.querySelector('.control-label'); if (cl) { l = cl.textContent; seen(cl); } }
		if (!l) { const fc = sel.closest('.frappe-control'); if (fc && fc.dataset.fieldname && sel.closest('.page-form')) l = (frappe.unscrub ? frappe.unscrub(fc.dataset.fieldname) : fc.dataset.fieldname); }
		// a label next to the field inside a filter group ("<div><label>Company</label><select>")
		if (!l) { const g = sel.closest('.mg-fgroup'); const lab = g && (g.querySelector(':scope > label, :scope > .mg-flabel') || g.querySelector('label')); if (lab && !lab.contains(sel)) { l = lab.textContent; seen(lab); } }
		if (!l) { let p = sel.previousElementSibling; if (p && p.tagName === 'LABEL') { l = p.textContent; seen(p); } }
		// a label printed just above the field ("<div><label>Company</label><div><select>")
		if (!l) { const w = sel.parentElement; const p = w && w.previousElementSibling; if (p && p.tagName === 'LABEL' && p.textContent.trim().length <= 40) { l = p.textContent; seen(p); } }
		// the same words printed beside the field (an aria-label that repeats a visible "<span>Company</span>")
		const want = (l || '').replace(/\s+/g, ' ').trim().toLowerCase();
		for (let a = sel.parentElement, d = 0; want && a && d < 3 && !sel._mgLabelShown; a = a.parentElement, d++) {
			for (const ch of a.children) {
				if (ch.contains(sel) || ch.matches('.mg-selbtn, .placeholder, .select-icon, .tooltip-content, .visually-hidden, .sr-only')) continue;
				if (ch.textContent.replace(/\s+/g, ' ').trim().toLowerCase() === want) seen(ch);
			}
		}
		// "<label>Company <select>": the label's own text
		const wrap = want && !sel._mgLabelShown && sel.closest('label');
		if (wrap && [...wrap.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').replace(/\s+/g, ' ').trim().toLowerCase() === want) seen(wrap);
		return (l || '').replace(/\s+/g, ' ').trim();
	}

	function sync(sel) {
		const btn = sel._mgBtn;
		if (!btn) return;
		const o = sel.options[sel.selectedIndex];
		const text = (o ? o.text : '').trim();
		const label = label_of(sel);
		// "Owner  All ▾" carries its label inside, unless the page already prints it beside the field (no "Company Company")
		// — in a one-row glass bar the outside label is hidden by the CSS, so the button keeps it
		const shown_outside = sel._mgLabelShown && !sel.closest('.mg-fbar .mg-fgroup');
		const show = label && !shown_outside && label.length <= 24 && !text.toLowerCase().includes(label.toLowerCase());
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
