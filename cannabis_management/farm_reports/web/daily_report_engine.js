(function () {
    'use strict';

    var CFG = window.DR_CONFIG;
    var LIVE = typeof window.frappe !== 'undefined';
    var C = CFG.child;

    var PHOTO_MAX_SIDE = 1600;
    var PHOTO_QUALITY = 0.82;

    var state = {};
    var registry = [];
    var byField = {};
    var lists = { flc: [], activity: [] };
    var summaryHooks = [];
    var draftName = null;
    var els = {};

    var ICON = {
        user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/></svg>',
        cal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>',
        check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
        trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>',
        close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
        camera: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>'
    };

    function h(tag, attrs, kids) {
        var n = document.createElement(tag);
        if (attrs) {
            Object.keys(attrs).forEach(function (k) {
                var v = attrs[k];
                if (v === null || v === undefined || v === false) return;
                if (k === 'class') n.className = v;
                else if (k === 'text') n.textContent = v;
                else if (k === 'html') n.innerHTML = v;
                else if (k.indexOf('on') === 0) n.addEventListener(k.slice(2), v);
                else n.setAttribute(k, v === true ? '' : v);
            });
        }
        (kids || []).forEach(function (c) {
            if (c === null || c === undefined) return;
            n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
        });
        return n;
    }
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    function todayISO() {
        var d = new Date();
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }
    function prettyDate() {
        return new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    }
    function getCookie(name) {
        var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return m ? decodeURIComponent(m.pop()).replace(/^"|"$/g, '') : '';
    }
    function toInt(v) { var n = parseInt(v, 10); return isNaN(n) ? 0 : n; }
    function toNum(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
    function fmt(n) { return Number(n).toLocaleString('en-US', { maximumFractionDigits: 1 }); }
    function stripHtml(s) { var d = document.createElement('div'); d.innerHTML = s; return (d.textContent || '').trim(); }
    function slug(doctype) { return doctype.toLowerCase().replace(/\s+/g, '-'); }

    function parseError(j, status) {
        try {
            if (j && j._server_messages) {
                return stripHtml(JSON.parse(j._server_messages).map(function (m) {
                    try { return JSON.parse(m).message; } catch (e) { return m; }
                }).join(' '));
            }
        } catch (e) {  }
        if (j && j.exception) {
            var parts = String(j.exception).split(':');
            return stripHtml(parts.length > 1 ? parts.slice(1).join(':') : parts[0]);
        }
        if (j && typeof j.message === 'string') return stripHtml(j.message);
        return 'The server returned an error (' + status + ').';
    }
    function api(method, url, body, isForm) {
        var headers = { 'Accept': 'application/json' };
        if (window.frappe && frappe.csrf_token) headers['X-Frappe-CSRF-Token'] = frappe.csrf_token;
        var opts = { method: method, headers: headers, credentials: 'same-origin' };
        if (body) {
            if (isForm) { opts.body = body; }
            else { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
        }
        return fetch(url, opts).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (j) {
                if (!r.ok) throw new Error(parseError(j, r.status));
                return j;
            });
        });
    }
    function listUrl(doctype, fields, filters, extra) {
        return '/api/resource/' + encodeURIComponent(doctype) +
            '?fields=' + encodeURIComponent(JSON.stringify(fields)) +
            '&filters=' + encodeURIComponent(JSON.stringify(filters || [])) +
            '&limit_page_length=0' + (extra || '');
    }

    function currentUser() {
        if (!LIVE) return { id: 'preview', name: CFG.previewUser, guest: false };
        var id = getCookie('user_id') || (frappe.session && frappe.session.user) || 'Guest';
        if (id === 'Guest') return { id: id, name: '', guest: true };
        return { id: id, name: getCookie('full_name') || id, guest: false };
    }

    function isVisible(q) { return !q.showIf || !!q.showIf(state); }
    function emptyValue(q) { return (q.type === 'photos' || /_table$/.test(q.type)) ? [] : ''; }
    function hasValue(q) {
        var v = state[q.field];
        return Array.isArray(v) ? v.length > 0 : String(v || '').trim() !== '';
    }
    function rowsOf(field) { if (!Array.isArray(state[field])) state[field] = []; return state[field]; }
    function totalLaborers() {
        var q = registry.filter(function (r) { return r.q.type === 'flc_table'; })[0];
        if (!q) return 0;
        return rowsOf(q.q.field).reduce(function (s, r) { return s + toInt(r.count); }, 0);
    }
    function isFilled(q) {
        var v = state[q.field];
        switch (q.type) {
            case 'photos': return (v || []).length > 0;
            case 'flc_table':
                return rowsOf(q.field).length > 0 && rowsOf(q.field).every(function (r) { return r.flc && toInt(r.count) >= 1; });
            case 'activity_table':
                return rowsOf(q.field).length > 0 && rowsOf(q.field).every(function (r) {
                    return r.activity && toInt(r.people) >= 1 && String(r.qty) !== '' && toNum(r.qty) >= 0;
                });
            default: return String(v || '').trim() !== '';
        }
    }

    function buildChoice(q, id) {
        var group = h('div', { class: 'dr-choices', role: 'radiogroup', 'aria-labelledby': id + '-label' });
        var btns = q.options.map(function (opt) {
            var m = /^(.*?)\s*\((.*)\)$/.exec(opt);
            var b = h('button', {
                type: 'button', class: 'dr-choice', role: 'radio', 'aria-checked': 'false', 'data-value': opt,
                onclick: function () { setValue(q.field, opt); }
            }, [h('span', { text: m ? m[1] : opt }), m ? h('small', { text: m[2] }) : null]);
            group.appendChild(b);
            return b;
        });
        return {
            node: group,
            sync: function (v) { btns.forEach(function (b) { b.setAttribute('aria-checked', String(b.getAttribute('data-value') === v)); }); },
            focus: function () { btns[0].focus(); }
        };
    }

    function buildText(q, id) {
        var t = h('textarea', {
            class: 'dr-textarea', id: id, rows: 3, placeholder: q.placeholder || '',
            oninput: function () { state[q.field] = t.value; clearError(q.field); updateProgress(); }
        });
        return {
            node: t,
            sync: function (v) { if (t.value !== (v || '')) t.value = v || ''; },
            focus: function () { t.focus(); }
        };
    }

    function buildDate(q, id) {
        var d = h('input', {
            type: 'date', class: 'dr-input dr-date', id: id, min: todayISO(),
            oninput: function () { state[q.field] = d.value; clearError(q.field); updateProgress(); }
        });
        return {
            node: d,
            sync: function (v) { if (d.value !== (v || '')) d.value = v || ''; },
            focus: function () { d.focus(); }
        };
    }

    function buildPhotos(q, id) {
        var input = h('input', {
            type: 'file', accept: 'image/*', multiple: true, id: id, class: 'dr-visually-hidden', tabindex: '-1',
            onchange: function () {
                var next = (state[q.field] || []).slice();
                Array.prototype.forEach.call(input.files || [], function (f) {
                    if (f.type.indexOf('image/') === 0) next.push({ file: f, url: URL.createObjectURL(f) });
                });
                input.value = '';
                setValue(q.field, next);
            }
        });
        var grid = h('div', { class: 'dr-photos' });
        var addBtn = h('button', {
            type: 'button', class: 'dr-add-photo', id: id + '-add',
            onclick: function () { input.click(); }
        }, [h('span', { html: ICON.camera }), h('span', { text: 'Add photos' })]);

        function sync(list) {
            list = list || [];
            grid.innerHTML = '';
            list.forEach(function (p, i) {
                grid.appendChild(h('div', { class: 'dr-thumb' }, [
                    h('img', { src: p.url, alt: 'Photo ' + (i + 1) + ' of ' + list.length }),
                    h('button', {
                        type: 'button', class: 'dr-thumb-remove', 'aria-label': 'Remove photo ' + (i + 1), html: ICON.close,
                        onclick: function () {
                            var next = (state[q.field] || []).slice();
                            var gone = next.splice(i, 1)[0];
                            if (gone) URL.revokeObjectURL(gone.url);
                            setValue(q.field, next);
                            addBtn.focus();
                        }
                    })
                ]));
            });
            grid.appendChild(addBtn);
        }
        return { node: h('div', null, [input, grid]), sync: sync, focus: function () { addBtn.focus(); } };
    }

    function cell(label, control, extraClass) {
        return h('div', { class: 'dr-cell' + (extraClass ? ' ' + extraClass : '') }, [
            h('label', { class: 'dr-cell-label', for: control.id, text: label }), control
        ]);
    }

    function keepFocus(renderFn) {
        var active = document.activeElement && document.activeElement.id;
        renderFn();
        if (active) { var n = document.getElementById(active); if (n) n.focus(); }
    }

    function emptyListNote(kind) {
        var msg = kind === 'flc'
            ? 'No farm labor contractors are set up yet. Ask an administrator to add them before submitting labor.'
            : 'No farm activities are set up yet. Ask an administrator to add them before submitting labor.';
        return h('p', { class: 'dr-empty', text: msg });
    }

    function buildFlcTable(q, id) {
        var rowsEl = h('div', { class: 'dr-rows' });
        var summary = h('p', { class: 'dr-summary', 'aria-live': 'polite' });
        var addBtn = h('button', {
            type: 'button', class: 'dr-add',
            onclick: function () {
                rowsOf(q.field).push({ flc: '', count: '' });
                render(); rowsChanged();
                var n = document.getElementById(id + '-flc-' + (rowsOf(q.field).length - 1)); if (n) n.focus();
            }
        }, ['+ Add contractor']);

        function render() {
            var rows = rowsOf(q.field);
            rowsEl.innerHTML = '';
            if (!lists.flc.length) rowsEl.appendChild(emptyListNote('flc'));
            rows.forEach(function (r, i) {
                var opts = [h('option', { value: '', text: 'Select contractor' })].concat(lists.flc.map(function (o) {
                    var used = rows.some(function (x, j) { return j !== i && x.flc === o.value; });
                    return h('option', { value: o.value, text: o.label, disabled: used });
                }));
                var sel = h('select', {
                    class: 'dr-select', id: id + '-flc-' + i,
                    onchange: function () { r.flc = sel.value; keepFocus(render); rowsChanged(); }
                }, opts);
                sel.value = r.flc;
                var num = h('input', {
                    type: 'number', inputmode: 'numeric', min: '1', step: '1', class: 'dr-input', id: id + '-cnt-' + i,
                    placeholder: '0', value: r.count,
                    oninput: function () { r.count = num.value; rowsChanged(); }
                });
                rowsEl.appendChild(h('div', { class: 'dr-row dr-row-flc' }, [
                    cell('Contractor', sel),
                    cell('Laborers', num),
                    h('button', {
                        type: 'button', class: 'dr-remove', 'aria-label': 'Remove contractor row ' + (i + 1), html: ICON.trash,
                        onclick: function () { rows.splice(i, 1); render(); rowsChanged(); addBtn.focus(); }
                    })
                ]));
            });
        }
        summaryHooks.push(function () {
            var t = totalLaborers();
            summary.innerHTML = '';
            summary.appendChild(document.createTextNode('Total laborers on the farm today: '));
            summary.appendChild(h('strong', { text: fmt(t) }));
            summary.hidden = rowsOf(q.field).length === 0;
        });
        return {
            node: h('div', null, [rowsEl, addBtn, summary]),
            sync: function () { render(); },
            focus: function () { var n = rowsEl.querySelector('select, input'); (n || addBtn).focus(); },
            addRow: function () { rowsOf(q.field).push({ flc: '', count: '' }); render(); }
        };
    }

    function buildActivityTable(q, id) {
        var rowsEl = h('div', { class: 'dr-rows' });
        var summary = h('p', { class: 'dr-summary', 'aria-live': 'polite' });
        var addBtn = h('button', {
            type: 'button', class: 'dr-add',
            onclick: function () {
                rowsOf(q.field).push({ activity: '', people: '', qty: '' });
                render(); rowsChanged();
                var n = document.getElementById(id + '-act-' + (rowsOf(q.field).length - 1)); if (n) n.focus();
            }
        }, ['+ Add activity']);

        function rateText(r) {
            var p = toInt(r.people), qn = toNum(r.qty);
            if (!p || String(r.qty) === '') return null;
            return [document.createTextNode('Output per person: '), h('strong', { text: fmt(qn / p) + ' ' + CFG.activityUnit.toLowerCase() })];
        }

        function render() {
            var rows = rowsOf(q.field);
            rowsEl.innerHTML = '';
            if (!lists.activity.length) rowsEl.appendChild(emptyListNote('activity'));
            rows.forEach(function (r, i) {
                var rate = h('p', { class: 'dr-rate', 'aria-live': 'polite' });
                function paintRate() {
                    rate.innerHTML = '';
                    var t = rateText(r);
                    if (t) t.forEach(function (n) { rate.appendChild(n); });
                    rate.hidden = !t;
                }
                var sel = h('select', {
                    class: 'dr-select', id: id + '-act-' + i,
                    onchange: function () { r.activity = sel.value; rowsChanged(); }
                }, [h('option', { value: '', text: 'Select activity' })].concat(lists.activity.map(function (o) {
                    return h('option', { value: o.value, text: o.label });
                })));
                sel.value = r.activity;
                var people = h('input', {
                    type: 'number', inputmode: 'numeric', min: '1', step: '1', class: 'dr-input', id: id + '-ppl-' + i,
                    placeholder: '0', value: r.people,
                    oninput: function () { r.people = people.value; paintRate(); rowsChanged(); }
                });
                var qty = h('input', {
                    type: 'number', inputmode: 'decimal', min: '0', step: 'any', class: 'dr-input', id: id + '-qty-' + i,
                    placeholder: '0', value: r.qty,
                    oninput: function () { r.qty = qty.value; paintRate(); rowsChanged(); }
                });
                paintRate();
                rowsEl.appendChild(h('div', { class: 'dr-row dr-row-act' }, [
                    cell('Activity', sel, 'dr-cell-activity'),
                    cell('People', people),
                    cell(CFG.activityUnit + ' completed', qty),
                    h('button', {
                        type: 'button', class: 'dr-remove', 'aria-label': 'Remove activity row ' + (i + 1), html: ICON.trash,
                        onclick: function () { rows.splice(i, 1); render(); rowsChanged(); addBtn.focus(); }
                    }),
                    rate
                ]));
            });
        }
        summaryHooks.push(function () {
            var rows = rowsOf(q.field);
            var assigned = rows.reduce(function (s, r) { return s + toInt(r.people); }, 0);
            var total = totalLaborers();
            summary.innerHTML = '';
            summary.appendChild(document.createTextNode('Assigned to activities: '));
            summary.appendChild(h('strong', { text: fmt(assigned) + ' of ' + fmt(total) }));
            summary.appendChild(document.createTextNode(' laborers'));
            var over = assigned > total;
            if (over) summary.appendChild(document.createTextNode('. This is more than the total on the farm.'));
            summary.classList.toggle('is-warn', over);
            summary.hidden = rows.length === 0;
        });
        return {
            node: h('div', null, [rowsEl, addBtn, summary]),
            sync: function () { render(); },
            focus: function () { var n = rowsEl.querySelector('select, input'); (n || addBtn).focus(); },
            addRow: function () { rowsOf(q.field).push({ activity: '', people: '', qty: '' }); render(); }
        };
    }

    var BUILDERS = {
        choice: buildChoice, text: buildText, date: buildDate, photos: buildPhotos,
        flc_table: buildFlcTable, activity_table: buildActivityTable
    };

    function setValue(field, v) {
        state[field] = v;
        byField[field].ctl.sync(v);
        clearError(field);
        refresh();
    }
    function rowsChanged() {
        summaryHooks.forEach(function (fn) { fn(); });
        registry.forEach(function (r) { if (/_table$/.test(r.q.type)) clearError(r.q.field); });
        updateProgress();
    }
    function clearValue(rec) {
        var v = state[rec.q.field];
        if (rec.q.type === 'photos' && Array.isArray(v)) v.forEach(function (p) { URL.revokeObjectURL(p.url); });
        state[rec.q.field] = emptyValue(rec.q);
        rec.ctl.sync(state[rec.q.field]);
        clearError(rec.q.field);
    }
    function refresh() {
        var changed = true, guard = 0;
        while (changed && guard++ < 8) {
            changed = false;
            registry.forEach(function (rec) {
                var vis = isVisible(rec.q);
                rec.wrap.hidden = !vis;
                if (!vis && hasValue(rec.q)) { clearValue(rec); changed = true; }
                if (vis && rec.ctl.addRow && rowsOf(rec.q.field).length === 0) { rec.ctl.addRow(); }
            });
        }
        summaryHooks.forEach(function (fn) { fn(); });
        updateProgress();
    }

    function showError(field, msg) {
        var rec = byField[field];
        rec.err.textContent = msg; rec.err.hidden = false;
        rec.wrap.classList.add('has-error');
        rec.wrap.querySelectorAll('input:not([type=file]), select, textarea').forEach(function (n) { n.setAttribute('aria-invalid', 'true'); });
    }
    function clearError(field) {
        var rec = byField[field];
        if (!rec || rec.err.hidden) return;
        rec.err.textContent = ''; rec.err.hidden = true;
        rec.wrap.classList.remove('has-error');
        rec.wrap.querySelectorAll('[aria-invalid]').forEach(function (n) { n.removeAttribute('aria-invalid'); });
    }
    function requiredMessage(q) {
        switch (q.type) {
            case 'choice': return 'Select an answer.';
            case 'date': return 'Pick a date.';
            case 'photos': return 'Add at least one photo.';
            case 'flc_table': return 'Add each contractor and how many laborers they sent. Complete or remove any empty row.';
            case 'activity_table': return 'Add each activity with the number of people and ' + CFG.activityUnit.toLowerCase() + ' completed. Complete or remove any empty row.';
            default: return 'Enter the details.';
        }
    }
    function validate() {
        var errors = [];
        registry.forEach(function (rec) {
            var q = rec.q;
            clearError(q.field);
            if (!isVisible(q)) return;
            if (q.required && !isFilled(q)) { errors.push([q.field, requiredMessage(q)]); return; }
            if (q.type === 'date' && state[q.field] && state[q.field] < todayISO()) {
                errors.push([q.field, 'Pick today or a later date.']);
            }
            if (q.type === 'activity_table') {
                var assigned = rowsOf(q.field).reduce(function (s, r) { return s + toInt(r.people); }, 0);
                var total = totalLaborers();
                if (assigned > total) {
                    errors.push([q.field, 'Activities have ' + fmt(assigned) + ' people but only ' + fmt(total) + ' laborers were on the farm. Adjust the headcounts.']);
                }
            }
        });
        errors.forEach(function (e) { showError(e[0], e[1]); });
        return errors;
    }
    function remainingCount() {
        return registry.filter(function (rec) { return rec.q.required && isVisible(rec.q) && !isFilled(rec.q); }).length;
    }
    function updateProgress() {
        if (!els.progress) return;
        var left = remainingCount();
        els.progress.classList.toggle('is-done', left === 0);
        els.progress.innerHTML = '';
        if (left === 0) { els.progress.textContent = 'All questions answered'; return; }
        els.progress.appendChild(h('strong', { text: String(left) }));
        els.progress.appendChild(document.createTextNode(left === 1 ? ' question left' : ' questions left'));
    }

    function buildPayload() {
        var doc = {};
        if (CFG.dateField) doc[CFG.dateField] = todayISO();
        registry.forEach(function (rec) {
            var q = rec.q, v = state[q.field];
            if (!isVisible(q)) return;
            if (q.type === 'photos') {
                doc[q.field] = (v || []).map(function (p) {
                    var row = {}; row[C.photo] = p.fileUrl || ('[' + p.file.name + ']'); return row;
                });
            } else if (q.type === 'flc_table') {
                doc[q.field] = rowsOf(q.field).map(function (r) {
                    var row = {}; row[C.flc] = r.flc; row[C.laborers] = toInt(r.count); return row;
                });
                if (q.totalField) doc[q.totalField] = totalLaborers();
            } else if (q.type === 'activity_table') {
                doc[q.field] = rowsOf(q.field).map(function (r) {
                    var p = toInt(r.people), qn = toNum(r.qty), row = {};
                    row[C.activity] = r.activity; row[C.people] = p; row[C.quantity] = qn;
                    row[C.uom] = CFG.activityUnit; row[C.perPerson] = p ? Math.round((qn / p) * 100) / 100 : 0;
                    return row;
                });
            } else if (String(v || '').trim()) {
                doc[q.field] = String(v).trim();
            }
        });
        return doc;
    }
    function photoFields() {
        return registry.filter(function (rec) { return rec.q.type === 'photos' && isVisible(rec.q); }).map(function (rec) { return rec.q.field; });
    }
    function allPhotos() {
        var out = [];
        photoFields().forEach(function (f) { (state[f] || []).forEach(function (p) { out.push(p); }); });
        return out;
    }
    function setBusy(busy, label) {
        els.submit.disabled = busy;
        els.submit.textContent = busy ? label : CFG.submitLabel;
    }
    function shrinkPhoto(file) {
        return new Promise(function (done) {
            var settled = false;
            function resolve(v) { if (!settled) { settled = true; clearTimeout(timer); done(v); } }
            var timer = setTimeout(function () { resolve(file); }, 10000);
            var src = URL.createObjectURL(file);
            var img = new Image();
            img.onload = function () {
                URL.revokeObjectURL(src);
                var w = img.naturalWidth, ht = img.naturalHeight;
                var scale = Math.min(1, PHOTO_MAX_SIDE / Math.max(w, ht));
                if (!w || !ht || (scale === 1 && file.size < 1024 * 1024)) { resolve(file); return; }
                var canvas = document.createElement('canvas');
                canvas.width = Math.round(w * scale);
                canvas.height = Math.round(ht * scale);
                canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                if (!canvas.toBlob) { resolve(file); return; }
                canvas.toBlob(function (blob) {
                    if (!blob || blob.size >= file.size) { resolve(file); return; }
                    blob.name = file.name.replace(/\.[^.]+$/, '') + '.jpg';
                    resolve(blob);
                }, 'image/jpeg', PHOTO_QUALITY);
            };
            img.onerror = function () { URL.revokeObjectURL(src); resolve(file); };
            img.src = src;
        });
    }
    function uploadPhotos(docname) {
        var pending = allPhotos().filter(function (p) { return !p.fileUrl; });
        var i = 0;
        function next() {
            if (i >= pending.length) return Promise.resolve();
            var p = pending[i++];
            setBusy(true, 'Uploading photo ' + i + ' of ' + pending.length);
            return shrinkPhoto(p.file).then(function (blob) {
                var fd = new FormData();
                fd.append('file', blob, blob.name || p.file.name);
                fd.append('is_private', '1');
                fd.append('doctype', CFG.doctype);
                fd.append('docname', docname);
                return api('POST', '/api/method/upload_file', fd, true);
            }).then(function (j) {
                p.fileUrl = j.message && j.message.file_url;
                if (!p.fileUrl) throw new Error('A photo could not be uploaded.');
                return next();
            });
        }
        return next();
    }
    function submitLive() {
        var base = '/api/resource/' + encodeURIComponent(CFG.doctype);
        var hasPhotos = allPhotos().length > 0;
        var doc = buildPayload();

        doc.docstatus = CFG.submitOnSave ? 1 : 0;
        if (!hasPhotos) {
            setBusy(true, 'Saving report');
            if (draftName) return api('PUT', base + '/' + encodeURIComponent(draftName), doc);
            return api('POST', base, doc);
        }

        var withoutPhotos = {};
        Object.keys(doc).forEach(function (k) { if (photoFields().indexOf(k) === -1 && k !== 'docstatus') withoutPhotos[k] = doc[k]; });
        setBusy(true, 'Saving report');
        var first = draftName
            ? api('PUT', base + '/' + encodeURIComponent(draftName), withoutPhotos)
            : api('POST', base, withoutPhotos).then(function (j) { draftName = j.data.name; return j; });
        return first.then(function () { return uploadPhotos(draftName); }).then(function () {
            var finalDoc = {};
            var full = buildPayload();
            photoFields().forEach(function (f) { finalDoc[f] = full[f]; });
            if (CFG.submitOnSave) finalDoc.docstatus = 1;
            setBusy(true, 'Submitting');
            return api('PUT', base + '/' + encodeURIComponent(draftName), finalDoc);
        });
    }
    function onSubmit() {
        var errors = validate();
        if (errors.length) {
            showBanner('error', errors.length === 1 ? 'One answer needs attention before you submit.' : errors.length + ' answers need attention before you submit.');
            var rec = byField[errors[0][0]];
            rec.wrap.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(function () { rec.ctl.focus(); }, 350);
            return;
        }
        hideBanner();
        if (!LIVE) { showPreview(buildPayload()); return; }
        submitLive().then(function (j) {
            showDone(j.data.name);
        }).catch(function (e) {
            setBusy(false);
            showBanner('error', 'The report was not submitted. ' + e.message);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    function showBanner(kind, msg) {
        els.banner.className = 'dr-banner' + (kind === 'error' ? ' is-error' : '');
        els.banner.setAttribute('role', kind === 'error' ? 'alert' : 'status');
        els.banner.textContent = msg;
        els.banner.hidden = false;
    }
    function hideBanner() { if (!LIVE) { showBanner('info', CFG.previewNote); } else { els.banner.hidden = true; } }
    function setMain(node) { els.content.innerHTML = ''; els.content.appendChild(node); }
    function docUrl(name) { return '/app/' + slug(CFG.doctype) + '/' + encodeURIComponent(name); }

    function showLoading() {
        els.footer.hidden = true;
        setMain(h('div', { class: 'dr-state', role: 'status' }, [h('div', { class: 'dr-spinner' }), h('p', { text: 'Loading today’s report', style: 'margin-top:1rem' })]));
    }
    function showLoginGate() {
        els.footer.hidden = true;
        setMain(h('div', { class: 'dr-state' }, [
            h('h2', { text: 'Log in to fill out today’s report' }),
            h('p', { text: 'Your name and the date are recorded automatically from your ERP account.' }),
            h('div', { class: 'dr-state-actions' }, [
                h('a', { class: 'dr-btn', href: '/login?redirect-to=' + encodeURIComponent(location.pathname), text: 'Log in' })
            ])
        ]));
    }
    function showAlready(rec) {
        els.footer.hidden = true;
        var time = rec.creation ? new Date(rec.creation.replace(' ', 'T')).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : '';
        setMain(h('div', { class: 'dr-state' }, [
            h('div', { class: 'dr-state-icon', html: ICON.check }),
            h('h2', { text: 'Today’s report is already submitted' }),
            h('p', { text: 'You submitted ' + rec.name + (time ? ' at ' + time : '') + '. Only one report can be submitted per day.' }),
            h('div', { class: 'dr-state-actions' }, [h('a', { class: 'dr-btn is-ghost', href: docUrl(rec.name), text: 'View report' })])
        ]));
    }
    function showDone(name) {
        els.footer.hidden = true;
        els.banner.hidden = true;
        setMain(h('div', { class: 'dr-state', role: 'status' }, [
            h('div', { class: 'dr-state-icon', html: ICON.check }),
            h('h2', { text: 'Report submitted' }),
            h('p', { text: 'Today’s ' + CFG.title.toLowerCase() + ' was saved as ' + name + '. The team will receive a copy by email.' }),
            h('div', { class: 'dr-state-actions' }, [h('a', { class: 'dr-btn is-ghost', href: docUrl(name), text: 'View report' })])
        ]));
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    function showPreview(payload) {
        var dlg = h('dialog', { class: 'dr-dialog', 'aria-labelledby': 'dr-dlg-title' }, [
            h('div', { class: 'dr-dialog-head' }, [
                h('h2', { id: 'dr-dlg-title', text: 'Data that would be saved' }),
                h('p', { text: 'Preview mode: nothing was sent. In MotleyERP this creates a submitted ' + CFG.doctype + '.' })
            ]),
            h('pre', { text: JSON.stringify(Object.assign({ doctype: CFG.doctype }, payload, CFG.submitOnSave ? { docstatus: 1 } : {}), null, 2) }),
            h('div', { class: 'dr-dialog-foot' }, [h('button', { type: 'button', class: 'dr-btn', text: 'Close', onclick: function () { dlg.close(); } })])
        ]);
        dlg.addEventListener('close', function () { dlg.remove(); });
        els.root.appendChild(dlg);
        if (dlg.showModal) dlg.showModal(); else alert(JSON.stringify(payload, null, 2));
    }

    function renderForm() {
        var form = h('form', { novalidate: true, onsubmit: function (e) { e.preventDefault(); onSubmit(); } });
        form.appendChild(h('p', { class: 'dr-intro', text: CFG.intro }));
        var qn = 0;
        CFG.sections.forEach(function (sec) {
            var secEl = h('section', { class: 'dr-section', 'aria-labelledby': 'dr-sec-' + qn });
            secEl.appendChild(h('div', { class: 'dr-section-head' }, [
                h('h2', { class: 'dr-section-title', id: 'dr-sec-' + qn, text: sec.title }),
                sec.description ? h('p', { class: 'dr-section-desc', text: sec.description }) : null
            ]));
            sec.questions.forEach(function (q) {
                var id = 'dr-' + q.field;
                state[q.field] = emptyValue(q);
                var ctl = BUILDERS[q.type](q, id);
                var labelFor = (q.type === 'choice') ? null : (q.type === 'photos' ? id + '-add' : (/_table$/.test(q.type) ? null : id));
                var label = h(labelFor ? 'label' : 'p', { class: 'dr-label', id: id + '-label', for: labelFor }, [
                    q.label, q.required ? null : h('span', { class: 'dr-optional', text: '(optional)' })
                ]);
                var err = h('p', { class: 'dr-error', id: id + '-error', role: 'alert', hidden: true });
                var wrap = h('div', { class: 'dr-q' + (q.showIf ? ' is-followup' : ''), 'data-field': q.field }, [
                    label,
                    q.help ? h('p', { class: 'dr-help', text: q.help }) : null,
                    ctl.node,
                    err
                ]);
                var rec = { q: q, ctl: ctl, wrap: wrap, err: err };
                registry.push(rec); byField[q.field] = rec;
                secEl.appendChild(wrap);
                qn++;
            });
            form.appendChild(secEl);
        });
        setMain(form);
        els.form = form;
        els.footer.hidden = false;
        registry.forEach(function (rec) { rec.ctl.sync(state[rec.q.field]); });
        refresh();
    }

    function loadLists() {
        var needs = { flc: false, activity: false };
        CFG.sections.forEach(function (s) { s.questions.forEach(function (q) {
            if (q.type === 'flc_table') needs.flc = true;
            if (q.type === 'activity_table') needs.activity = true;
        }); });
        if (!LIVE) {
            Object.keys(needs).forEach(function (k) {
                if (needs[k]) lists[k] = (CFG.previewLists[k] || []).map(function (v) { return { value: v, label: v }; });
            });
            return Promise.resolve();
        }
        var jobs = Object.keys(needs).filter(function (k) { return needs[k]; }).map(function (k) {
            var src = CFG.sources[k];
            if (src.method) {
                return api('GET', '/api/method/' + src.method).then(function (j) {
                    lists[k] = (j.message || []).map(function (r) { return { value: r.value, label: r.label || r.value }; });
                });
            }
            var fields = [src.value]; if (src.label !== src.value) fields.push(src.label);
            return api('GET', listUrl(src.doctype, fields, src.filters, '&order_by=' + encodeURIComponent(src.label + ' asc'))).then(function (j) {
                lists[k] = (j.data || []).map(function (r) { return { value: r[src.value], label: r[src.label] || r[src.value] }; });
            });
        });
        return Promise.all(jobs);
    }
    function findToday(user) {
        if (!LIVE) return Promise.resolve(null);
        var filters = [[CFG.dateField, '=', todayISO()], [CFG.userField || 'owner', '=', user.id], ['docstatus', '=', 1]];
        return api('GET', listUrl(CFG.doctype, ['name', 'creation'], filters, '&limit=1')).then(function (j) {
            return (j.data && j.data[0]) || null;
        });
    }

    function init() {
        var root = document.getElementById('dr-app');
        if (!root || root.getAttribute('data-ready')) return;
        root.setAttribute('data-ready', '1');
        els.root = root;
        var user = currentUser();

        root.appendChild(h('header', { class: 'dr-header' }, [
            h('div', { class: 'dr-header-inner' }, [
                h('p', { class: 'dr-site', text: CFG.site }),
                h('h1', { class: 'dr-title', text: CFG.title }),
                h('div', { class: 'dr-meta' }, [
                    user.guest ? null : h('span', { class: 'dr-pill' }, [h('span', { html: ICON.user }), 'Filled out by ', h('strong', { text: user.name })]),
                    h('span', { class: 'dr-pill' }, [h('span', { html: ICON.cal }), h('strong', { text: prettyDate() })])
                ])
            ])
        ]));
        els.banner = h('div', { class: 'dr-banner', hidden: true });
        els.content = h('div');
        root.appendChild(h('main', { class: 'dr-main' }, [els.banner, els.content]));

        els.progress = h('p', { class: 'dr-progress', 'aria-live': 'polite' });
        els.submit = h('button', { type: 'button', class: 'dr-submit', text: CFG.submitLabel, onclick: onSubmit });
        els.footer = h('div', { class: 'dr-footer', hidden: true }, [h('div', { class: 'dr-footer-inner' }, [els.progress, els.submit])]);
        root.appendChild(els.footer);

        if (user.guest) { showLoginGate(); return; }
        if (!LIVE) showBanner('info', CFG.previewNote);
        showLoading();

        findToday(user).then(function (existing) {
            if (existing) { showAlready(existing); return; }
            return loadLists().then(renderForm, function (e) {
                renderForm();
                showBanner('error', 'Some lists could not be loaded: ' + e.message);
            });
        }).catch(function (e) {
            renderForm();
            showBanner('error', 'Could not check for an earlier report today: ' + e.message);
        });
    }

    if (window.frappe && typeof frappe.ready === 'function') frappe.ready(init);
    else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
