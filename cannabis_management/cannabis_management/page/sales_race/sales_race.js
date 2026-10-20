frappe.pages['sales-race'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Sales Race',
        single_column: true
    });
    wrapper.page = page;
    $(wrapper).find('.page-head').hide();
    page.main.html('<div class="sr-root"></div>');
    var $root = page.main.find('.sr-root');
    var state = { month: null, data: null, cfg: null };

    var COLORS = ['#f97316', '#2563eb', '#16a34a', '#7c3aed', '#db2777', '#0891b2', '#ca8a04', '#dc2626'];
    var LINE_COLORS = ['#f97316', '#10b981', '#8b5cf6', '#0ea5e9', '#ec4899'];

    function esc(s) { return frappe.utils.escape_html(s == null ? '' : String(s)); }
    function money(n) { return (n < 0 ? '-' : '') + '$' + Math.round(Math.abs(n)).toLocaleString('en-US'); }
    function k(n) {
        var a = Math.abs(n), s = a >= 1000 ? '$' + (a / 1000).toFixed(1).replace(/\.0$/, '') + 'K' : '$' + Math.round(a);
        return (n < 0 ? '-' : '') + s;
    }
    function pct(a, b) { return b > 0 ? Math.round(a / b * 100) : 0; }
    function initials(n) {
        var p = String(n).trim().split(/\s+/);
        return (p[0][0] + (p[1] ? p[1][0] : (p[0][1] || ''))).toUpperCase();
    }
    function color(i) { return COLORS[i % COLORS.length]; }
    function paceClass(done, pace) { return done >= pace ? 'sr-good' : 'sr-bad'; }

    function load() {
        $root.html('<div class="sr-loading">Loading…</div>');
        frappe.call({
            method: 'cannabis_management.cannabis_management.page.sales_race.sales_race.get_race',
            args: { month: state.month },
            callback: function (r) {
                state.data = r.message;
                state.month = r.message.month;
                render();
            }
        });
    }

    function render() {
        var d = state.data, lines = d.lines, pace = d.pace * 100;
        var total = d.reps.reduce(function (a, r) { return a + r.total; }, 0);
        var should = d.plan_total * d.pace;
        var diff = total - should;
        var colorOf = {};
        d.reps.forEach(function (r, i) { colorOf[r.sales_person] = color(i); });
        var leader = d.reps[0];

        var h = '';
        h += '<div class="sr-head"><div><div class="sr-kicker">MOTLEY TERPZ</div><h1>🏁 Sales Race</h1></div>' +
            '<div class="sr-month"><div class="sr-month-nav"><button class="sr-nav" data-d="-1">‹</button>' +
            '<span class="sr-month-label">' + esc(d.month_label) + '</span><button class="sr-nav" data-d="1">›</button></div>' +
            '<div class="sr-sub">Day ' + d.day + ' of ' + d.days_in_month + ' · from ' + esc(d.basis) + 's</div></div></div>';

        h += '<div class="sr-stats">' +
            stat('TEAM SO FAR', k(total), 'of ' + k(d.plan_total) + ' · ' + pct(total, d.plan_total) + '% there', '') +
            stat('SHOULD BE AT', k(should), "by today's pace", 'sr-blue') +
            stat('VS. PACE', (diff < 0 ? '−' : '+') + k(Math.abs(diff)), diff < 0 ? 'behind, time to push' : 'ahead of pace', diff < 0 ? 'sr-bad' : 'sr-good') +
            '</div>';
        h += '<div class="sr-bar"><div class="sr-bar-fill" style="width:' + Math.min(100, pct(total, d.plan_total)) + '%"></div>' +
            '<div class="sr-pace-tick" style="left:' + pace + '%"></div></div>';

        // race track
        h += '<div class="sr-track-wrap"><div class="sr-legend"><span><i class="sr-dot sr-blue-bg"></i>Pace line: where you should be today</span>' +
            '<span>🏁 Finish line: your quota</span></div>';
        d.reps.forEach(function (r) {
            var p = pct(r.total, r.quota), w = Math.min(100, p);
            h += '<div class="sr-lane"><div class="sr-chip"><span class="sr-av" style="background:' + colorOf[r.sales_person] + '">' + esc(initials(r.sales_person)) + '</span>' +
                '<div><b>' + esc(r.sales_person) + '</b><small>' + k(r.total) + ' of ' + k(r.quota) + '</small></div></div>' +
                '<div class="sr-road"><div class="sr-road-fill" style="width:' + w + '%;background:' + colorOf[r.sales_person] + '"></div>' +
                '<div class="sr-road-pace" style="left:' + pace + '%"></div>' +
                '<div class="sr-car" style="left:' + w + '%"><span class="sr-pill ' + paceClass(p, pace) + '">' + p + '%</span><span class="sr-emoji">' + esc(r.emoji) + '</span></div>' +
                '<div class="sr-flag">🏁</div></div></div>';
        });
        h += '</div>';

        // scorecards
        h += '<div class="sr-sec-head"><h2>Scorecards</h2><span>Each product line vs. that rep\'s quota</span></div><div class="sr-cards">';
        d.reps.forEach(function (r, i) {
            h += '<div class="sr-card" style="border-top-color:' + colorOf[r.sales_person] + '"><div class="sr-card-head"><span class="sr-emoji">' + esc(r.emoji) +
                '</span><span class="sr-av sm" style="background:' + colorOf[r.sales_person] + '">' + esc(initials(r.sales_person)) + '</span><b>' + esc(r.sales_person) +
                '</b><span class="sr-muted">' + pct(r.total, r.quota) + '%</span></div>';
            lines.forEach(function (l, li) {
                var x = r.lines[l.key], p = pct(x.sold, x.quota);
                h += '<div class="sr-line"><div class="sr-line-top"><span>' + esc(l.label) + '</span><span class="sr-line-val">' + k(x.sold) + ' / ' + k(x.quota) +
                    ' · <b class="' + paceClass(p, pace) + '">' + p + '%</b></span></div>' + prog(p, pace, LINE_COLORS[li % 5]) + '</div>';
            });
            h += '</div>';
        });
        h += '</div>';

        // team by product
        h += '<div class="sr-panel"><div class="sr-sec-head tight"><h2>Team by product</h2><span>Company plan: ' +
            lines.map(function (l) { return k(l.plan); }).join(' · ') + '</span></div><div class="sr-team">';
        lines.forEach(function (l, li) {
            var sold = d.team[l.key], p = pct(sold, l.plan), vs = sold - l.plan * d.pace;
            h += '<div><div class="sr-line-top"><b><i class="sr-dot" style="background:' + LINE_COLORS[li % 5] + '"></i>' + esc(l.label) + '</b><span class="sr-muted">' + p + '%</span></div>' +
                prog(p, pace, LINE_COLORS[li % 5]) + '<div class="sr-small">' + k(sold) + ' of ' + k(l.plan) + ' · <b class="' + (vs >= 0 ? 'sr-good' : 'sr-bad') + '">' +
                (vs >= 0 ? '+' : '−') + k(Math.abs(vs)) + ' vs pace</b></div></div>';
        });
        h += '</div></div>';

        // leaderboard
        h += '<div class="sr-panel flush"><table class="sr-table"><thead><tr><th>#</th><th>REP</th><th class="r">SO FAR</th><th class="r">QUOTA</th><th class="r">% DONE</th>' +
            '<th class="r">VS. PACE</th><th class="r">BEHIND #1</th><th class="r">LAST 7 DAYS</th><th class="r">LINES ON PACE</th></tr></thead><tbody>';
        d.reps.forEach(function (r, i) {
            var p = pct(r.total, r.quota), vs = Math.round(p - pace);
            var ok = 0, n = 0;
            lines.forEach(function (l) { var x = r.lines[l.key]; if (x.quota > 0) { n++; if (pct(x.sold, x.quota) >= pace) ok++; } });
            h += '<tr><td class="sr-rank">' + (i + 1) + '</td><td><b>' + esc(r.emoji) + ' ' + esc(r.sales_person) + '</b></td><td class="r">' + money(r.total) +
                '</td><td class="r">' + money(r.quota) + '</td><td class="r">' + p + '%</td><td class="r"><span class="sr-tag ' + (vs >= 0 ? 'sr-good-bg' : 'sr-bad-bg') + '">' +
                (vs >= 0 ? '+' : '') + vs + ' pts</span></td><td class="r sr-muted">' + (i === 0 ? '—' : '−' + money(leader.total - r.total)) + '</td><td class="r">' + money(r.week) +
                '</td><td class="r"><span class="' + (n && ok === n ? 'sr-good' : ok ? '' : 'sr-bad') + '">' + ok + ' of ' + n + '</span></td></tr>';
        });
        h += '</tbody></table></div>';

        // badges
        h += '<div class="sr-badges">';
        if (leader && leader.total > 0) h += badge('🥇 Leader', leader.sales_person);
        lines.forEach(function (l) {
            var x = d.leaders[l.key];
            if (x) h += badge(esc(l.label) + ':', x.rep + ' · ' + k(x.amount));
        });
        if (d.biggest) h += badge('💰 Biggest deal:', d.biggest.rep + ' · ' + money(d.biggest.amount));
        if (d.hottest) h += badge('🔥 Hottest this week:', d.hottest.rep + ' · ' + money(d.hottest.amount));
        h += '</div>';

        // recent
        h += '<div class="sr-panel"><div class="sr-sec-head tight"><h2>Recent sales</h2></div>';
        if (!d.recent.length) h += '<div class="sr-muted">No sales yet this month.</div>';
        d.recent.forEach(function (x) {
            var l = lines.filter(function (l) { return l.key === x.line; })[0];
            h += '<div class="sr-recent"><span><b>' + esc(x.rep) + '</b> · ' + esc(l ? l.label : '') + ' · <a href="/app/' + frappe.router.slug(d.basis) + '/' + encodeURIComponent(x.doc) + '">' +
                esc(x.doc) + '</a> <span class="sr-muted">' + esc(x.customer || '') + '</span></span><span>' + money(x.amount) + ' · ' + frappe.datetime.str_to_user(x.date) + '</span></div>';
        });
        if (d.unmapped) h += '<div class="sr-note">' + money(d.unmapped) + ' sold in item groups not mapped to any product line (not counted).</div>';
        h += '</div>';

        if (d.can_edit) h += '<div class="sr-panel"><div class="sr-sec-head tight"><h2>Reps & quotas</h2></div><div id="sr-settings"></div></div>';

        $root.html(h);
        $root.find('.sr-nav').on('click', function () {
            var p = state.month.split('-'), dt = new Date(+p[0], +p[1] - 1 + (+$(this).data('d')), 1);
            state.month = dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0');
            load();
        });
        if (d.can_edit) renderSettings();
    }

    function stat(label, val, sub, cls) {
        return '<div class="sr-stat"><div class="sr-stat-label">' + label + '</div><div class="sr-stat-val ' + cls + '">' + val + '</div><div class="sr-sub">' + sub + '</div></div>';
    }
    function prog(p, pace, c) {
        return '<div class="sr-prog"><div class="sr-prog-fill" style="width:' + Math.min(100, p) + '%;background:' + c + '"></div><div class="sr-prog-pace" style="left:' + pace + '%"></div></div>';
    }
    function badge(a, b) { return '<span class="sr-badge">' + a + ' <b>' + esc(b) + '</b></span>'; }

    // ---------- settings editor ----------
    function renderSettings() {
        frappe.call({
            method: 'cannabis_management.cannabis_management.page.sales_race.sales_race.get_config',
            callback: function (r) { state.cfg = r.message.config; drawSettings(); }
        });
    }

    function drawSettings() {
        var c = state.cfg, h = '';
        h += '<div class="sr-form-row"><label>Count sales from</label><select id="sr-basis"><option>Sales Order</option><option>Sales Invoice</option></select></div>';
        h += '<table class="sr-table sr-edit"><thead><tr><th>PRODUCT LINE</th><th>COMPANY PLAN ($)</th><th>ITEM GROUPS (comma separated)</th></tr></thead><tbody>';
        c.lines.forEach(function (l, i) {
            h += '<tr><td><input data-l="' + i + '" data-f="label" value="' + esc(l.label) + '"></td><td><input type="number" data-l="' + i + '" data-f="plan" value="' + (l.plan || 0) +
                '"></td><td><input data-l="' + i + '" data-f="item_groups" value="' + esc((l.item_groups || []).join(', ')) + '"></td></tr>';
        });
        h += '</tbody></table>';
        h += '<table class="sr-table sr-edit"><thead><tr><th>ON</th><th>RIDE</th><th>SALES PERSON</th>' + c.lines.map(function (l) { return '<th>' + esc(l.label.toUpperCase()) + ' QUOTA ($)</th>'; }).join('') + '<th></th></tr></thead><tbody>';
        c.reps.forEach(function (r, i) {
            h += '<tr><td><input type="checkbox" data-r="' + i + '" data-f="active" ' + (r.active ? 'checked' : '') + '></td><td><input class="sr-emoji-in" data-r="' + i + '" data-f="emoji" value="' + esc(r.emoji) +
                '"></td><td><b>' + esc(r.sales_person) + '</b></td>';
            c.lines.forEach(function (l) { h += '<td><input type="number" data-r="' + i + '" data-q="' + l.key + '" value="' + ((r.quotas || {})[l.key] || 0) + '"></td>'; });
            h += '<td><a class="sr-del" data-r="' + i + '">remove</a></td></tr>';
        });
        h += '</tbody></table><div class="sr-actions"><button class="btn btn-default btn-sm" id="sr-add">+ Add sales person</button> ' +
            '<button class="btn btn-primary btn-sm" id="sr-save">Save setup</button></div>';
        var $s = $root.find('#sr-settings').html(h);
        $s.find('#sr-basis').val(c.basis);

        function collect() {
            c.basis = $s.find('#sr-basis').val();
            $s.find('input[data-l]').each(function () {
                var l = c.lines[$(this).data('l')], f = $(this).data('f'), v = $(this).val();
                l[f] = f === 'plan' ? flt(v) : f === 'item_groups' ? v.split(',').map(function (x) { return x.trim(); }).filter(Boolean) : v;
            });
            $s.find('input[data-r]').each(function () {
                var r = c.reps[$(this).data('r')];
                if ($(this).data('q')) { r.quotas = r.quotas || {}; r.quotas[$(this).data('q')] = flt($(this).val()); }
                else r[$(this).data('f')] = $(this).is(':checkbox') ? ($(this).is(':checked') ? 1 : 0) : $(this).val();
            });
        }
        $s.find('#sr-add').on('click', function () {
            collect();
            frappe.prompt({ fieldname: 'sp', fieldtype: 'Link', options: 'Sales Person', label: 'Sales Person', reqd: 1,
                get_query: function () { return { filters: { is_group: 0, enabled: 1 } }; } }, function (v) {
                if (c.reps.some(function (r) { return r.sales_person === v.sp; })) return;
                var q = {}; c.lines.forEach(function (l) { q[l.key] = 0; });
                c.reps.push({ sales_person: v.sp, emoji: '🏎', active: 1, quotas: q });
                drawSettings();
            }, 'Add to race');
        });
        $s.find('.sr-del').on('click', function () { collect(); c.reps.splice($(this).data('r'), 1); drawSettings(); });
        $s.find('#sr-save').on('click', function () {
            collect();
            frappe.call({
                method: 'cannabis_management.cannabis_management.page.sales_race.sales_race.save_config',
                args: { config: c }, freeze: true,
                callback: function () { frappe.show_alert({ message: 'Saved', indicator: 'green' }); load(); }
            });
        });
    }

    load();
};
