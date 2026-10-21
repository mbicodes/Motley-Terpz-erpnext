frappe.pages['sales-race'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Sales Race',
        single_column: true
    });
    wrapper.page = page;
    $(wrapper).find('.page-head').hide();
    page.main.html('<div class="sr-root"><div class="sr-filters"></div><div class="sr-body"></div></div>');
    var $root = page.main.find('.sr-body');
    var state = { data: null, seq: 0 };

    var COLORS = ['#f97316', '#2563eb', '#16a34a', '#7c3aed', '#db2777', '#0891b2', '#ca8a04', '#dc2626'];
    var LINE_COLORS = ['#f97316', '#10b981', '#8b5cf6', '#0ea5e9', '#ec4899', '#ca8a04', '#64748b', '#0891b2'];

    function esc(s) { return frappe.utils.escape_html(s == null ? '' : String(s)); }
    function money(n) { return (n < 0 ? '-' : '') + '$' + Math.round(Math.abs(n)).toLocaleString('en-US'); }
    function pct(a, b) { return b > 0 ? Math.round(a / b * 100) : 0; }
    function initials(n) {
        var p = String(n).trim().split(/\s+/);
        return (p[0][0] + (p[1] ? p[1][0] : (p[0][1] || ''))).toUpperCase();
    }
    function color(i) { return COLORS[i % COLORS.length]; }
    function paceClass(done, pace) { return done >= pace ? 'sr-good' : 'sr-bad'; }

    var filters = {};
    function addFilter(df) {
        var $f = $('<div class="sr-filter"></div>').appendTo(page.main.find('.sr-filters'));
        filters[df.fieldname] = frappe.ui.form.make_control({
            parent: $f, df: Object.assign({ change: load }, df), render_input: true
        });
    }
    // Select, not Link: a Link cannot offer an explicit "All Companies" entry.
    var ALL = 'All Companies';
    addFilter({ fieldname: 'company', label: 'Company', fieldtype: 'Select', options: [ALL], default: ALL });
    filters.company.set_value(ALL);
    frappe.db.get_list('Company', { fields: ['name'], limit: 0, order_by: 'name asc' }).then(function (rows) {
        var current = filters.company.get_value() || ALL;
        filters.company.df.options = [ALL].concat(rows.map(function (r) { return r.name; }));
        filters.company.refresh();
        filters.company.set_value(current);
    });
    addFilter({ fieldname: 'basis', label: 'Basis', fieldtype: 'Select', options: 'Sales Invoice\nSales Order', default: 'Sales Invoice' });
    addFilter({ fieldname: 'from_date', label: 'From Date', fieldtype: 'Date', default: frappe.datetime.month_start() });
    addFilter({ fieldname: 'to_date', label: 'To Date', fieldtype: 'Date', default: frappe.datetime.month_end() });
    filters.from_date.set_value(frappe.datetime.month_start());
    filters.to_date.set_value(frappe.datetime.month_end());

    var lastArgs = null;
    function load() {
        var args = {
            company: (filters.company.get_value() === ALL ? null : filters.company.get_value()) || null,
            basis: filters.basis.get_value() || 'Sales Invoice',
            from_date: filters.from_date.get_value(),
            to_date: filters.to_date.get_value()
        };
        if (!args.from_date || !args.to_date) return;
        if (JSON.stringify(args) === lastArgs) return;
        lastArgs = JSON.stringify(args);
        var seq = ++state.seq;
        $root.html('<div class="sr-loading">Loading…</div>');
        frappe.call({
            method: 'cannabis_management.cannabis_management.page.sales_race.sales_race.get_race',
            args: args,
            callback: function (r) {
                if (seq !== state.seq) return;  // a newer filter change is in flight
                state.data = r.message;
                render();
            }
        });
    }

    function render() {
        var d = state.data, lines = d.lines, pace = d.pace * 100;
        var total = d.sold;
        var should = d.target_amount * d.pace;
        var diff = total - should;
        var colorOf = {};
        d.reps.forEach(function (r, i) { colorOf[r.sales_person] = color(i); });
        var leader = d.reps[0];

        var h = '';
        h += '<div class="sr-head"><div><div class="sr-kicker">MOTLEY TERPZ</div><h1>🏁 Sales Race</h1></div>' +
            '<div class="sr-month"><div class="sr-month-label">' + esc(frappe.datetime.str_to_user(d.from_date)) + ' – ' + esc(frappe.datetime.str_to_user(d.to_date)) + '</div>' +
            '<div class="sr-sub">' + (d.company ? esc(d.company) + ' · ' : '') + 'Day ' + d.day + ' of ' + d.days + ' · from ' + esc(d.basis) + 's</div></div></div>';

        h += '<div class="sr-stats">' +
            stat('TEAM SO FAR', money(total), 'of ' + money(d.target_amount) + ' · ' + pct(total, d.target_amount) + '% there', '') +
            stat('SHOULD BE AT', money(should), "by today's pace", 'sr-blue') +
            stat('VS. PACE', (diff < 0 ? '−' : '+') + money(Math.abs(diff)), diff < 0 ? 'behind, time to push' : 'ahead of pace', diff < 0 ? 'sr-bad' : 'sr-good') +
            '</div>';
        h += '<div class="sr-bar"><div class="sr-bar-fill" style="width:' + Math.min(100, pct(total, d.target_amount)) + '%"></div>' +
            '<div class="sr-pace-tick" style="left:' + pace + '%"></div></div>';

        // race track
        h += '<div class="sr-track-wrap"><div class="sr-legend"><span><i class="sr-dot sr-blue-bg"></i>Pace line: where you should be today</span>' +
            '<span>🏁 Finish line: your quota</span></div>';
        d.reps.forEach(function (r) {
            var p = pct(r.sold, r.target_amount), w = Math.min(100, p);
            h += '<div class="sr-lane"><div class="sr-chip"><span class="sr-av" style="background:' + colorOf[r.sales_person] + '">' + esc(initials(r.sales_person)) + '</span>' +
                '<div><b>' + esc(r.sales_person) + '</b><small>' + money(r.sold) + ' of ' + money(r.target_amount) + '</small></div></div>' +
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
                '</b><span class="sr-muted">' + pct(r.sold, r.target_amount) + '%</span></div>';
            lines.forEach(function (l, li) {
                var x = r.lines[l.key], p = pct(x.sold, x.quota);
                h += '<div class="sr-line"><div class="sr-line-top"><span>' + esc(l.label) + '</span><span class="sr-line-val">' + money(x.sold) + ' / ' + money(x.quota) +
                    ' · <b class="' + paceClass(p, pace) + '">' + p + '%</b></span></div>' + prog(p, pace, LINE_COLORS[li % LINE_COLORS.length]) + '</div>';
            });
            h += '</div>';
        });
        h += '</div>';

        // team by product
        h += '<div class="sr-panel"><div class="sr-sec-head tight"><h2>Team by product</h2><span>Company plan: ' +
            lines.map(function (l) { return money(l.plan); }).join(' · ') + '</span></div><div class="sr-team">';
        lines.forEach(function (l, li) {
            var sold = d.team[l.key], p = pct(sold, l.plan), vs = sold - l.plan * d.pace;
            h += '<div><div class="sr-line-top"><b><i class="sr-dot" style="background:' + LINE_COLORS[li % LINE_COLORS.length] + '"></i>' + esc(l.label) + '</b><span class="sr-muted">' + p + '%</span></div>' +
                prog(p, pace, LINE_COLORS[li % LINE_COLORS.length]) + '<div class="sr-small">' + money(sold) + ' of ' + money(l.plan) + ' · <b class="' + (vs >= 0 ? 'sr-good' : 'sr-bad') + '">' +
                (vs >= 0 ? '+' : '−') + money(Math.abs(vs)) + ' vs pace</b></div></div>';
        });
        h += '</div></div>';

        // leaderboard
        h += '<div class="sr-panel flush"><table class="sr-table"><thead><tr><th>#</th><th>REP</th><th class="r">SO FAR</th><th class="r">QUOTA</th><th class="r">% DONE</th>' +
            '<th class="r">VS. PACE</th><th class="r">BEHIND #1</th><th class="r">LAST 7 DAYS</th><th class="r">LINES ON PACE</th></tr></thead><tbody>';
        d.reps.forEach(function (r, i) {
            var p = pct(r.sold, r.target_amount), vs = Math.round(p - pace);
            var ok = 0, n = 0;
            lines.forEach(function (l) { var x = r.lines[l.key]; if (x.quota > 0) { n++; if (pct(x.sold, x.quota) >= pace) ok++; } });
            h += '<tr><td class="sr-rank">' + (i + 1) + '</td><td><b>' + esc(r.emoji) + ' ' + esc(r.sales_person) + '</b></td><td class="r">' + money(r.sold) +
                '</td><td class="r">' + money(r.target_amount) + '</td><td class="r">' + p + '%</td><td class="r"><span class="sr-tag ' + (vs >= 0 ? 'sr-good-bg' : 'sr-bad-bg') + '">' +
                (vs >= 0 ? '+' : '') + vs + ' pts</span></td><td class="r sr-muted">' + (i === 0 ? '—' : '−' + money(leader.sold - r.sold)) + '</td><td class="r">' + money(r.week) +
                '</td><td class="r"><span class="' + (n && ok === n ? 'sr-good' : ok ? '' : 'sr-bad') + '">' + ok + ' of ' + n + '</span></td></tr>';
        });
        h += '</tbody></table></div>';

        // badges
        h += '<div class="sr-badges">';
        if (leader && leader.sold > 0) h += badge('🥇 Leader', leader.sales_person);
        lines.forEach(function (l) {
            var x = d.leaders[l.key];
            if (x) h += badge(esc(l.label) + ':', x.rep + ' · ' + money(x.amount));
        });
        if (d.biggest) h += badge('💰 Biggest deal:', d.biggest.rep + ' · ' + money(d.biggest.amount));
        if (d.hottest) h += badge('🔥 Hottest this week:', d.hottest.rep + ' · ' + money(d.hottest.amount));
        h += '</div>';

        // collection
        var pay = d.payments;
        h += '<div class="sr-sec-head"><h2>Collection</h2><span>' + pay.count + ' payment' + (pay.count === 1 ? '' : 's') +
            ' · ' + money(pay.total) + ' · allocated against Sales Invoices</span></div>';
        if (pay.by_rep.length) {
            h += '<div class="sr-badges">';
            pay.by_rep.forEach(function (x) { h += badge('💵 ' + esc(x.sales_person) + ':', money(x.amount)); });
            h += '</div>';
        }
        h += '<div class="sr-panel flush sr-pay"><table class="sr-table"><thead><tr><th>DATE</th><th>PAYMENT</th><th>CUSTOMER</th>' +
            '<th>SALES PERSON</th><th>MODE</th><th>REF NO</th><th>AGAINST</th><th class="r">AMOUNT</th></tr></thead><tbody>';
        if (!pay.rows.length) h += '<tr><td colspan="8" class="sr-muted">No collection in this period.</td></tr>';
        pay.rows.forEach(function (x) {
            var against = x.against.map(function (a) {
                return '<a href="/app/' + frappe.router.slug(a.doctype) + '/' + encodeURIComponent(a.name) + '">' + esc(a.name) + '</a> <span class="sr-muted">' + money(a.amount) + '</span>';
            });
            if (x.unallocated) against.push('<span class="sr-muted">Unallocated ' + money(x.unallocated) + '</span>');
            h += '<tr><td>' + frappe.datetime.str_to_user(x.date) + '</td><td><a href="/app/payment-entry/' + encodeURIComponent(x.name) + '">' + esc(x.name) + '</a>' +
                (d.company ? '' : '<br><span class="sr-muted">' + esc(x.company) + '</span>') + '</td><td>' + esc(x.customer) + '</td><td>' + esc(x.reps.join(', ')) +
                '</td><td>' + esc(x.mode || '') + '</td><td>' + esc(x.ref_no || '') + '</td><td>' + (against.join('<br>') || '—') +
                '</td><td class="r"><b>' + money(x.amount) + '</b>' +
                (Math.abs(x.received - x.amount) >= 0.5 ? '<br><span class="sr-muted">received ' + money(x.received) + '</span>' : '') + '</td></tr>';
        });
        h += '</tbody></table></div>';

        $root.html(h);
    }

    function stat(label, val, sub, cls) {
        return '<div class="sr-stat"><div class="sr-stat-label">' + label + '</div><div class="sr-stat-val ' + cls + '">' + val + '</div><div class="sr-sub">' + sub + '</div></div>';
    }
    function prog(p, pace, c) {
        return '<div class="sr-prog"><div class="sr-prog-fill" style="width:' + Math.min(100, p) + '%;background:' + c + '"></div><div class="sr-prog-pace" style="left:' + pace + '%"></div></div>';
    }
    function badge(a, b) { return '<span class="sr-badge">' + a + ' <b>' + esc(b) + '</b></span>'; }

    load();
};
