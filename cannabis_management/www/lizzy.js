frappe.ready(function () {
    var rootEl = document;
    var API_JAMIE = 'cannabis_management.api.jamie.';
    var now = frappe.datetime.get_today();

    // ── Date display ──
    var dateEl = rootEl.querySelector('#lz-date-display');
    if (dateEl) dateEl.textContent = frappe.datetime.str_to_user(now);

    // ── Expose reload ──
    window.lizzyDash = {
        reload: function () { loadAll(); }
    };

    // ────────────────────────────────────────────────────────────────
    // Helpers
    // ────────────────────────────────────────────────────────────────

    function fmt(val) {
        return parseFloat(val || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    function fmtCurrency(val) {
        return '$ ' + parseFloat(val || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function shimmerEl(id) {
        var el = rootEl.querySelector('#' + id);
        if (el) el.innerHTML = '<div class="nd-loading"><div class="nd-spinner"></div></div>';
    }

    function shimmerKpi(id) {
        var el = rootEl.querySelector('#' + id);
        if (el) { el.classList.remove('loaded', 'error'); el.innerHTML = '<span class="nd-shimmer"></span>'; }
    }

    var tablePages = {};

    function renderTable(containerId, columns, rows, emptyMsg) {
        var el = rootEl.querySelector('#' + containerId);
        if (!el) return;
        if (!rows || !rows.length) {
            el.innerHTML = '<p style="color:#94a3b8;font-size:13px;padding:12px 16px;">' + (emptyMsg || 'No data.') + '</p>';
            tablePages[containerId] = 0;
            return;
        }

        var PAGE_SIZE = 12;
        if (tablePages[containerId] === undefined) tablePages[containerId] = 0;

        function render(page) {
            var totalPages = Math.ceil(rows.length / PAGE_SIZE);
            page = Math.max(0, Math.min(page, totalPages - 1));
            tablePages[containerId] = page;

            var start    = page * PAGE_SIZE;
            var pageRows = rows.slice(start, start + PAGE_SIZE);

            var html = '<table class="nd-table"><thead><tr>';
            columns.forEach(function (c) { html += '<th>' + c.label + '</th>'; });
            html += '</tr></thead><tbody>';
            pageRows.forEach(function (row) {
                html += '<tr>';
                columns.forEach(function (c) {
                    var val = c.format ? c.format(row[c.key], row) : (row[c.key] != null ? row[c.key] : '—');
                    html += '<td>' + val + '</td>';
                });
                html += '</tr>';
            });
            html += '</tbody></table>';

            if (totalPages > 1) {
                var from = start + 1;
                var to   = Math.min(start + PAGE_SIZE, rows.length);
                html += '<div class="nd-pagination">'
                      + '<button class="nd-page-btn nd-page-prev" ' + (page === 0 ? 'disabled' : '') + '>'
                      + '<svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg></button>'
                      + '<span class="nd-page-info">' + from + '–' + to + ' of ' + rows.length + '</span>'
                      + '<button class="nd-page-btn nd-page-next" ' + (page >= totalPages - 1 ? 'disabled' : '') + '>'
                      + '<svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg></button>'
                      + '</div>';
            }

            el.innerHTML = html;

            var prev = el.querySelector('.nd-page-prev');
            var next = el.querySelector('.nd-page-next');
            if (prev) prev.addEventListener('click', function () { render(tablePages[containerId] - 1); });
            if (next) next.addEventListener('click', function () { render(tablePages[containerId] + 1); });
        }

        tablePages[containerId] = 0;
        render(0);
    }

    // ────────────────────────────────────────────────────────────────
    // Load: Batches in Production
    // ────────────────────────────────────────────────────────────────
    function loadBatches() {
        shimmerKpi('lz-kpi-batches');
        shimmerEl('lz-batches-table');

        frappe.call({
            method: API_JAMIE + 'get_batches_in_production',
            args: { company: 'Motley Terpz' },
            callback: function (r) {
                if (!r.message) return;
                var rows = r.message;

                var kpiEl = rootEl.querySelector('#lz-kpi-batches');
                if (kpiEl) { kpiEl.textContent = rows.length; kpiEl.classList.add('loaded'); }

                var badge = rootEl.querySelector('#lz-batches-count');
                if (badge) badge.textContent = rows.length + ' active';

                renderTable('lz-batches-table', [
                    { label: 'Batch',    key: 'name',             format: function (v) { return '<a href="/app/project/' + v + '">' + v + '</a>'; } },
                    { label: 'Name',     key: 'project_name' },
                    { label: 'Status',   key: 'status' },
                    { label: 'Due',      key: 'expected_end_date', format: function (v) { return v ? frappe.datetime.str_to_user(v) : '—'; } },
                    { label: '% Done',   key: 'percent_complete',  format: function (v) { return (v || 0) + '%'; } },
                    { label: 'Company',  key: 'company' }
                ], rows, 'No active batches.');
            },
            error: function () {
                var kpiEl = rootEl.querySelector('#lz-kpi-batches');
                if (kpiEl) { kpiEl.textContent = '–'; kpiEl.classList.add('error'); }
            }
        });
    }

    // ────────────────────────────────────────────────────────────────
    // Load: Tolling Partner Stock by Batch
    // ────────────────────────────────────────────────────────────────
    function loadTolling() {
        var grid = rootEl.querySelector('#lz-tolling-batch-grid');
        if (grid) grid.innerHTML = '<div class="nd-kpi" style="--kc:#0891b2"><div class="nd-kpi-accent"></div><div class="nd-kpi-label">Loading…</div><div class="nd-kpi-value"><span class="nd-shimmer"></span></div><div class="nd-kpi-sub">loading…</div></div>';

        shimmerKpi('lz-kpi-partners');
        shimmerKpi('lz-kpi-tolling-qty');

        frappe.call({
            method: 'cannabis_management.api.stock.get_tolling_partner_stock_by_batch',
            callback: function (r) {
                if (!grid) return;
                grid.innerHTML = '';

                if (!r.message || !r.message.length) {
                    grid.innerHTML = '<p style="color:#94a3b8;font-size:13px;">No tolling partner stock found.</p>';

                    var kpiP = rootEl.querySelector('#lz-kpi-partners');
                    if (kpiP) { kpiP.textContent = '0'; kpiP.classList.add('loaded'); }
                    var kpiQ = rootEl.querySelector('#lz-kpi-tolling-qty');
                    if (kpiQ) { kpiQ.textContent = '0'; kpiQ.classList.add('loaded'); }
                    return;
                }

                var colors = ['#0891b2','#059669','#b45309','#7c3aed','#2563eb','#e11d48','#9333ea','#0f766e'];
                var totalQty = 0;

                r.message.forEach(function (row, i) {
                    var qty     = parseFloat(row.total_qty || 0);
                    totalQty  += qty;
                    var dateStr = row.last_date ? frappe.datetime.str_to_user(row.last_date) : '—';
                    var kpi     = document.createElement('div');
                    kpi.className = 'nd-kpi';
                    kpi.style.setProperty('--kc', colors[i % colors.length]);
                    kpi.innerHTML =
                        '<div class="nd-kpi-accent"></div>' +
                        '<div class="nd-kpi-label">' + (row.project_name || row.project || '—') + '</div>' +
                        '<div class="nd-kpi-value loaded">' + qty.toLocaleString(undefined, { maximumFractionDigits: 2 }) + '</div>' +
                        '<div class="nd-kpi-sub">' + dateStr + ' · Tolling Stock</div>';
                    grid.appendChild(kpi);
                });

                var kpiP = rootEl.querySelector('#lz-kpi-partners');
                if (kpiP) { kpiP.textContent = r.message.length; kpiP.classList.add('loaded'); }

                var kpiQ = rootEl.querySelector('#lz-kpi-tolling-qty');
                if (kpiQ) { kpiQ.textContent = totalQty.toLocaleString(undefined, { maximumFractionDigits: 2 }); kpiQ.classList.add('loaded'); }
            },
            error: function () {
                if (grid) grid.innerHTML = '<p style="color:#94a3b8;font-size:13px;">Error loading tolling stock.</p>';
                ['lz-kpi-partners','lz-kpi-tolling-qty'].forEach(function (id) {
                    var el = rootEl.querySelector('#' + id);
                    if (el) { el.textContent = '–'; el.classList.add('error'); }
                });
            }
        });
    }

    // ────────────────────────────────────────────────────────────────
    // Load: Pending Purchase Requests
    // ────────────────────────────────────────────────────────────────
    function loadPendingPRs() {
        shimmerKpi('lz-kpi-pending-pr');
        shimmerEl('lz-pr-table');

        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Material Request',
                filters: [
                    ['material_request_type', '=', 'Purchase'],
                    ['status', 'in', ['Pending', 'Partially Ordered']]
                ],
                fields: ['name', 'title', 'transaction_date', 'schedule_date', 'status', 'company'],
                order_by: 'transaction_date desc',
                limit_page_length: 200
            },
            callback: function (r) {
                var rows = r.message || [];

                var kpiEl = rootEl.querySelector('#lz-kpi-pending-pr');
                if (kpiEl) { kpiEl.textContent = rows.length; kpiEl.classList.add('loaded'); }

                var badge = rootEl.querySelector('#lz-pr-count');
                if (badge) badge.textContent = rows.length + ' open';

                renderTable('lz-pr-table', [
                    { label: 'PR',           key: 'name',             format: function (v) { return '<a href="/app/material-request/' + v + '">' + v + '</a>'; } },
                    { label: 'Title',        key: 'title',            format: function (v) { return v || '—'; } },
                    { label: 'Date',         key: 'transaction_date', format: function (v) { return frappe.datetime.str_to_user(v); } },
                    { label: 'Required By',  key: 'schedule_date',    format: function (v) { return v ? frappe.datetime.str_to_user(v) : '—'; } },
                    { label: 'Company',      key: 'company' },
                    { label: 'Status',       key: 'status' }
                ], rows, 'No pending purchase requests.');
            },
            error: function () {
                var kpiEl = rootEl.querySelector('#lz-kpi-pending-pr');
                if (kpiEl) { kpiEl.textContent = '–'; kpiEl.classList.add('error'); }
            }
        });
    }

    // ────────────────────────────────────────────────────────────────
    // Purchase Request Form
    // ────────────────────────────────────────────────────────────────

    function getFormVal(id) {
        var el = rootEl.querySelector('#' + id);
        return el ? el.value.trim() : '';
    }

    function setFormStatus(msg, type) {
        var el = rootEl.querySelector('#lz-form-status');
        if (!el) return;
        el.textContent = msg;
        el.className   = 'lz-form-status ' + (type || '');
    }

    function clearForm() {
        ['lz-qty','lz-req-by','lz-notes'].forEach(function (id) {
            var el = rootEl.querySelector('#' + id);
            if (el) el.value = '';
        });
        var uomEl = rootEl.querySelector('#lz-uom');
        if (uomEl) uomEl.value = 'Nos';
        var typeEl = rootEl.querySelector('#lz-type');
        if (typeEl) typeEl.value = '';
        rootEl.querySelectorAll('.lz-input.error, .lz-select.error, .lz-textarea.error').forEach(function (el) {
            el.classList.remove('error');
        });
        setFormStatus('');
    }

    function showSuccess(docname) {
        var form  = rootEl.querySelector('#lz-pr-form');
        var succ  = rootEl.querySelector('#lz-pr-success');
        var msg   = rootEl.querySelector('#lz-success-msg');
        var link  = rootEl.querySelector('#lz-success-link');
        if (form) form.style.display = 'none';
        if (succ) succ.style.display = 'flex';
        if (msg)  msg.textContent    = docname + ' has been created and sent for approval.';
        if (link) link.href          = '/app/material-request/' + docname;
    }

    function showForm() {
        var form = rootEl.querySelector('#lz-pr-form');
        var succ = rootEl.querySelector('#lz-pr-success');
        if (form) form.style.display = '';
        if (succ) succ.style.display = 'none';
        clearForm();
    }

    function submitPR() {
        // Basic validation — only qty and req-by are required
        var qty      = getFormVal('lz-qty');
        var reqBy    = getFormVal('lz-req-by');
        var typeVal  = getFormVal('lz-type');
        var notes    = getFormVal('lz-notes');
        var uom      = getFormVal('lz-uom') || 'Nos';

        var valid = true;
        [
            { id: 'lz-qty',    val: qty   },
            { id: 'lz-req-by', val: reqBy }
        ].forEach(function (f) {
            var el = rootEl.querySelector('#' + f.id);
            if (!f.val) { if (el) el.classList.add('error'); valid = false; }
            else         { if (el) el.classList.remove('error'); }
        });

        if (!valid) {
            setFormStatus('Please fill in the required fields.', 'error');
            return;
        }

        var submitBtn = rootEl.querySelector('#lz-submit-btn');
        if (submitBtn) { submitBtn.disabled = true; submitBtn.classList.add('spinning'); }
        setFormStatus('Submitting…', 'loading');

        // Build items child table row
        frappe.call({
            method: 'cannabis_management.api.jamie.create_purchase_request',
            args: {
                qty:           parseFloat(qty),
                uom:           uom,
                schedule_date: reqBy,
                why_need:      notes   || '',
                type_val:      typeVal || ''
            },
            callback: function (r) {
                if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('spinning'); }
                if (r.message) {
                    setFormStatus('');
                    showSuccess(r.message);
                    loadPendingPRs();
                } else {
                    setFormStatus('Something went wrong. Please try again.', 'error');
                }
            },
            error: function (err) {
                if (submitBtn) { submitBtn.disabled = false; submitBtn.classList.remove('spinning'); }
                var errMsg = (err && err.message) ? err.message : 'Submission failed. Please try again.';
                setFormStatus(errMsg, 'error');
            }
        });
    }

    // Wire up form buttons
    var submitBtn  = rootEl.querySelector('#lz-submit-btn');
    var clearBtn   = rootEl.querySelector('#lz-clear-btn');
    var anotherBtn = rootEl.querySelector('#lz-another-btn');

    if (submitBtn)  submitBtn.addEventListener('click', submitPR);
    if (clearBtn)   clearBtn.addEventListener('click', clearForm);
    if (anotherBtn) anotherBtn.addEventListener('click', showForm);

    // Clear error state on input
    ['lz-qty','lz-req-by'].forEach(function (id) {
        var el = rootEl.querySelector('#' + id);
        if (el) el.addEventListener('input', function () { this.classList.remove('error'); setFormStatus(''); });
    });

    // Set default Required By to 2 weeks from today
    var reqByEl = rootEl.querySelector('#lz-req-by');
    if (reqByEl) {
        var defaultDate = frappe.datetime.add_days(now, 14);
        reqByEl.value   = defaultDate;
    }

    // ────────────────────────────────────────────────────────────────
    // Master load
    // ────────────────────────────────────────────────────────────────
    function loadAll() {
        loadBatches();
        loadTolling();
        loadPendingPRs();
    }

    loadAll();

});