/* =====================================================
   WAREHOUSE OVERVIEW — Frappe Page JS  (v4-fix)
   Place at: cannabis_management/cannabis_management/
             warehouse_overview/warehouse_overview.js

   APIs:
     • cannabis_management.cannabis_management.page.warehouse_overview.warehouse_overview.get_item_groups
     • cannabis_management.cannabis_management.page.warehouse_overview.warehouse_overview.get_stock_by_item_group
===================================================== */

frappe.pages['warehouse-overview'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: '',
        single_column: true
    });

    // Hide default Frappe page-head (we render our own header)
    $(wrapper).find('.page-head').hide();

    // ── Inject the HTML directly ──────────────────────
    // Frappe Page .html files are auto-loaded as the page wrapper,
    // but frappe.render_template() looks in the template registry.
    // Safest approach: inline the markup here.
    page.main.html(WO_PAGE_HTML);

    // Kick off
    woBindEvents();
    woLoad();
};

frappe.pages['warehouse-overview'].on_page_show = function () {
    // Data stays in memory. Uncomment to auto-refresh:
    // woLoad();
};


// ─────────────────────────────────────────────────────
// PAGE HTML TEMPLATE
// ─────────────────────────────────────────────────────

const WO_PAGE_HTML = `
<div class="wo-page">

  <!-- HEADER -->
  <div class="wo-header">
    <div class="wo-header-left">
      <div class="wo-eyebrow">Inventory Radar</div>
      <h1 class="wo-title">Warehouse Overview</h1>
      <p class="wo-subtitle">Every warehouse holding material — front and center, nothing hidden.</p>
    </div>
    <div class="wo-header-right">
      <button class="wo-btn wo-btn-refresh" id="wo-refresh-btn" type="button">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
        Refresh
      </button>
    </div>
  </div>

  <!-- COMPANY SWITCHER -->
  <div class="wo-company-bar">
    <div class="wo-company-label">Company</div>
    <div class="wo-company-pills" id="wo-company-pills">
      <button class="wo-pill wo-pill-active" data-company="all">All Companies</button>
      <button class="wo-pill wo-pill-tsbc"   data-company="TSBC">TSBC</button>
      <button class="wo-pill wo-pill-mt"     data-company="MT">MT</button>
    </div>
  </div>

  <!-- SUMMARY STRIP -->
  <div class="wo-summary-strip">
    <div class="wo-stat-card wo-stat-1">
      <div class="wo-stat-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
      </div>
      <div class="wo-stat-body">
        <div class="wo-stat-label">Active Warehouses</div>
        <div class="wo-stat-value" id="wo-total-warehouses">&mdash;</div>
      </div>
    </div>
    <div class="wo-stat-card wo-stat-2">
      <div class="wo-stat-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
      </div>
      <div class="wo-stat-body">
        <div class="wo-stat-label">Distinct Items</div>
        <div class="wo-stat-value" id="wo-total-items">&mdash;</div>
      </div>
    </div>
    <div class="wo-stat-card wo-stat-3">
      <div class="wo-stat-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="12 2 2 7 12 12 22 7 12 2"/>
          <polyline points="2 17 12 22 22 17"/>
          <polyline points="2 12 12 17 22 12"/>
        </svg>
      </div>
      <div class="wo-stat-body">
        <div class="wo-stat-label">Total Quantity</div>
        <div class="wo-stat-value" id="wo-total-qty">&mdash;</div>
      </div>
    </div>
    <div class="wo-stat-card wo-stat-4">
      <div class="wo-stat-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
          <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
        </svg>
      </div>
      <div class="wo-stat-body">
        <div class="wo-stat-label">Item Groups</div>
        <div class="wo-stat-value" id="wo-total-groups">&mdash;</div>
      </div>
    </div>
  </div>

  <!-- FILTER BAR -->
  <div class="wo-filter-bar">
    <div class="wo-search-wrap">
      <svg class="wo-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
      <input type="text" id="wo-search-box" class="wo-search-input" placeholder="Search warehouses, items, or groups…">
    </div>
    <div class="wo-filter-controls">
      <label class="wo-toggle-wrap">
        <span class="wo-toggle-label">With stock only</span>
        <div class="wo-toggle">
          <input type="checkbox" id="wo-only-stock">
          <span class="wo-toggle-slider"></span>
        </div>
      </label>
      <select id="wo-sort-by" class="wo-select">
        <option value="name">Sort: Name</option>
        <option value="qty">Sort: Total Qty</option>
        <option value="items">Sort: Item Count</option>
      </select>
      <button class="wo-btn wo-btn-reset" id="wo-reset-btn" type="button">Reset</button>
    </div>
  </div>

  <!-- WAREHOUSE GRID -->
  <div id="wo-grid" class="wo-grid">
    <div class="wo-loading">
      <div class="wo-loading-spinner"></div>
      <div class="wo-loading-text">Scanning all warehouses…</div>
    </div>
  </div>

</div>
`;


// ─────────────────────────────────────────────────────
// CONFIG  (mirrors inventory dashboard exactly)
// ─────────────────────────────────────────────────────

const WO_GROUP_ORDER = [
    'Fresh Frozen',
    'Primes',
    'Subprimes',
    'VRR',
    'O2 Vape',
    '1g O2 Vapes',
    'LIQUID LIVE RESIN',
    'Full Spec',
    'Food Grade',
    'Gummies',
    'Farm Supplies',
    'Drawings'
];

const WO_FRESH_FROZEN_MAIN = 'Fresh Frozen';
const WO_FRESH_FROZEN_SUBS = ['Fresh Frozen', 'Fresh Frozen - BHO', 'Fresh Frozen - SHO'];

const WO_DEFAULT_WAREHOUSE       = "Nature's Lab - MT";
const WO_GROUP_DEFAULT_WAREHOUSE = {
    'Fresh Frozen': 'Hemet TSBC - TSBC'
};

const WO_COMPANY_SUFFIX_MAP = {
    'MT'  : 'MT',
    'TSBC': 'TSBC'
};

const WO_COMPANY_FALLBACK_RULES = [
    { pattern: 'tsbc',    company: 'TSBC' },
    { pattern: 'hemet',   company: 'TSBC' },
    { pattern: 'leef',    company: 'MT'   },
    { pattern: 'motley',  company: 'MT'   },
    { pattern: 'terpz',   company: 'MT'   },
    { pattern: "nature",  company: 'MT'   },
];

const WO_COMPANY_ORDER      = ['TSBC', 'MT'];
const WO_COMPANY_LABELS     = { 'TSBC': 'TSBC', 'MT': 'MT' };
const WO_COMPANY_COLORS     = { 'TSBC': 'dot-sky', 'MT': 'dot-gold' };
const WO_COMPANY_CARD_CLASS = { 'TSBC': 'card-co-tsbc', 'MT': 'card-co-mt' };

const WO_LOW_STOCK_THRESHOLD = 5;

const WO_SWATCH_COUNT = 12;
let   WO_SWATCH_MAP   = {};
let   WO_SWATCH_IDX   = 0;


// ─────────────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────────────

let WO_WAREHOUSES = [];

let WO_FILTERS = {
    search       : '',
    onlyWithStock: false,
    sortBy       : 'name',
    company      : 'all'
};


// ─────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────

function woEsc(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function woNum(val) {
    const n = parseFloat(val || 0);
    return isNaN(n) ? 0 : n;
}

function woDebounce(fn, ms) {
    let t;
    return function () {
        const c = this, a = arguments;
        clearTimeout(t);
        t = setTimeout(function () { fn.apply(c, a); }, ms);
    };
}

function woEscRegex(s) {
    return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function woCleanName(itemName, itemGroup) {
    if (!itemName) return '-';
    let name = String(itemName);
    if (itemGroup) {
        name = name.replace(new RegExp('\\s*[-]\\s*' + woEscRegex(itemGroup) + '$', 'i'), '');
        name = name.replace(new RegExp('[_][A-Za-z0-9][-]' + woEscRegex(itemGroup) + '$', 'i'), '');
    }
    name = name.replace(/_CDC$/i, '').replace(/_[A-Za-z0-9]$/i, '').replace(/_/g, ' ').trim();
    return name || String(itemName);
}

function woDedupe(items) {
    const seen = {};
    return items.filter(function (item) {
        const key = [
            String(item.item_code  || '').trim(),
            String(item.warehouse  || '').trim(),
            String(item.item_group || '').trim()
        ].join('||');
        if (seen[key]) return false;
        seen[key] = true;
        return true;
    });
}

function woFmt(n) { return woNum(n).toFixed(2); }

function woGetGroupSwatch(groupName) {
    if (WO_SWATCH_MAP[groupName] === undefined) {
        WO_SWATCH_MAP[groupName] = WO_SWATCH_IDX % WO_SWATCH_COUNT;
        WO_SWATCH_IDX++;
    }
    return WO_SWATCH_MAP[groupName];
}

function woDetectCompany(warehouseName) {
    const name = String(warehouseName || '');
    const dashIdx = name.lastIndexOf(' - ');
    if (dashIdx !== -1) {
        const suffix = name.slice(dashIdx + 3).trim().toUpperCase();
        if (WO_COMPANY_SUFFIX_MAP[suffix]) return WO_COMPANY_SUFFIX_MAP[suffix];
    }
    const lower = name.toLowerCase();
    for (let i = 0; i < WO_COMPANY_FALLBACK_RULES.length; i++) {
        if (lower.includes(WO_COMPANY_FALLBACK_RULES[i].pattern)) {
            return WO_COMPANY_FALLBACK_RULES[i].company;
        }
    }
    return 'Other';
}

function woGetLoadGroups(groupName) {
    if (groupName === WO_FRESH_FROZEN_MAIN) return WO_FRESH_FROZEN_SUBS.slice();
    return [groupName];
}

function woSortGroupNames(names) {
    return names.slice().sort(function (a, b) {
        const iA = WO_GROUP_ORDER.findIndex(function (g) { return g.toLowerCase() === a.toLowerCase(); });
        const iB = WO_GROUP_ORDER.findIndex(function (g) { return g.toLowerCase() === b.toLowerCase(); });
        if (iA !== -1 && iB !== -1) return iA - iB;
        if (iA !== -1) return -1;
        if (iB !== -1) return 1;
        return a.localeCompare(b);
    });
}


// ─────────────────────────────────────────────────────
// AGGREGATES
// ─────────────────────────────────────────────────────

function woWarehouseTotalQty(wh) {
    let total = 0;
    (wh.groups || []).forEach(function (g) {
        (g.items || []).forEach(function (i) { total += woNum(i.actual_qty); });
    });
    return total;
}

function woWarehouseTotalItems(wh) {
    let count = 0;
    (wh.groups || []).forEach(function (g) { count += (g.items || []).length; });
    return count;
}

function woWarehouseGroupCount(wh) {
    return (wh.groups || []).length;
}

function woAllTotalQty(warehouses) {
    return warehouses.reduce(function (s, wh) { return s + woWarehouseTotalQty(wh); }, 0);
}

function woAllTotalItems(warehouses) {
    return warehouses.reduce(function (s, wh) { return s + woWarehouseTotalItems(wh); }, 0);
}

function woAllGroupCount(warehouses) {
    const s = new Set();
    warehouses.forEach(function (wh) {
        (wh.groups || []).forEach(function (g) { s.add(g.name); });
    });
    return s.size;
}


// ─────────────────────────────────────────────────────
// BINDINGS
// ─────────────────────────────────────────────────────

function woBindEvents() {
    const searchEl  = document.getElementById('wo-search-box');
    const stockEl   = document.getElementById('wo-only-stock');
    const sortEl    = document.getElementById('wo-sort-by');
    const resetEl   = document.getElementById('wo-reset-btn');
    const refreshEl = document.getElementById('wo-refresh-btn');
    const pillsEl   = document.getElementById('wo-company-pills');

    if (searchEl) {
        searchEl.addEventListener('input', woDebounce(function () {
            WO_FILTERS.search = this.value.trim().toLowerCase();
            woRender();
        }, 200));
    }
    if (stockEl) {
        stockEl.addEventListener('change', function () {
            WO_FILTERS.onlyWithStock = this.checked;
            woRender();
        });
    }
    if (sortEl) {
        sortEl.addEventListener('change', function () {
            WO_FILTERS.sortBy = this.value;
            woRender();
        });
    }
    if (resetEl) {
        resetEl.addEventListener('click', function () {
            woResetFilters();
            woRender();
        });
    }
    if (refreshEl) {
        refreshEl.addEventListener('click', woLoad);
    }
    if (pillsEl) {
        pillsEl.addEventListener('click', function (e) {
            const pill = e.target.closest('.wo-pill');
            if (!pill) return;
            WO_FILTERS.company = pill.dataset.company || 'all';
            pillsEl.querySelectorAll('.wo-pill').forEach(function (p) {
                p.classList.toggle('wo-pill-active', p === pill);
            });
            woRender();
        });
    }
}

function woResetFilters() {
    WO_FILTERS.search = '';
    WO_FILTERS.onlyWithStock = false;
    WO_FILTERS.sortBy = 'name';
    WO_FILTERS.company = 'all';
    const s = document.getElementById('wo-search-box');
    const c = document.getElementById('wo-only-stock');
    const o = document.getElementById('wo-sort-by');
    if (s) s.value = '';
    if (c) c.checked = false;
    if (o) o.value = 'name';
    document.querySelectorAll('.wo-pill').forEach(function (p) {
        p.classList.toggle('wo-pill-active', p.dataset.company === 'all');
    });
}


// ─────────────────────────────────────────────────────
// LOAD
// ─────────────────────────────────────────────────────

function woLoad() {
    const grid = document.getElementById('wo-grid');
    if (grid) {
        grid.innerHTML = '<div class="wo-loading"><div class="wo-loading-spinner"></div><div class="wo-loading-text">Scanning all warehouses…</div></div>';
    }

    frappe.call({
        method: 'cannabis_management.cannabis_management.page.warehouse_overview.warehouse_overview.get_item_groups',
        callback: function (r) {
            if (!(r && r.message && Array.isArray(r.message) && r.message.length)) {
                WO_WAREHOUSES = [];
                woRender();
                return;
            }

            const topLevel = r.message.filter(function (g) {
                const n = String(g.name || '').trim();
                return n !== 'Fresh Frozen - BHO' && n !== 'Fresh Frozen - SHO';
            });

            const sorted = topLevel.slice().sort(function (a, b) {
                const iA = WO_GROUP_ORDER.findIndex(function (g) { return g.toLowerCase() === String(a.name).toLowerCase(); });
                const iB = WO_GROUP_ORDER.findIndex(function (g) { return g.toLowerCase() === String(b.name).toLowerCase(); });
                if (iA !== -1 && iB !== -1) return iA - iB;
                if (iA !== -1) return -1;
                if (iB !== -1) return 1;
                return String(a.name).localeCompare(String(b.name));
            });

            const groupNames = sorted.map(function (g) { return g.name; }).filter(Boolean);
            woLoadAllGroups(groupNames);
        },
        error: function () {
            WO_WAREHOUSES = [];
            woRender();
        }
    });
}

function woLoadAllGroups(groupNames) {
    const apiCalls = [];
    groupNames.forEach(function (name) {
        const subs = woGetLoadGroups(name);
        subs.forEach(function (sub) {
            apiCalls.push({ apiGroup: sub, displayGroup: name });
        });
    });

    let pending    = apiCalls.length;
    let allRows    = [];
    let anySuccess = false;

    if (!pending) {
        WO_WAREHOUSES = [];
        woRender();
        return;
    }

    apiCalls.forEach(function (call) {
        frappe.call({
            method: 'cannabis_management.cannabis_management.page.warehouse_overview.warehouse_overview.get_stock_by_item_group',
            args  : { item_group: call.apiGroup, _: Date.now() },
            callback: function (r) {
                let items = [];
                if (r && r.message) {
                    items = Array.isArray(r.message) ? r.message
                          : Array.isArray(r.message.items) ? r.message.items : [];
                }
                items.forEach(function (item) {
                    if (!item.item_group) item.item_group = call.apiGroup;
                    item._display_group = call.displayGroup;
                });
                allRows = allRows.concat(items);
                anySuccess = true;
                if (--pending === 0) woFinalize(allRows, anySuccess);
            },
            error: function () {
                if (--pending === 0) woFinalize(allRows, anySuccess);
            }
        });
    });
}

function woFinalize(rows, anySuccess) {
    const cleaned = woDedupe(rows || []).filter(function (row) {
        return woNum(row.actual_qty) > 0 && row.warehouse;
    });

    if (!anySuccess && !cleaned.length) {
        const grid = document.getElementById('wo-grid');
        if (grid) {
            grid.innerHTML = '<div class="wo-empty"><div class="wo-empty-title">Could not load data</div><div class="wo-empty-sub">Check your connection and refresh.</div></div>';
        }
        woUpdateSummary([]);
        return;
    }

    WO_WAREHOUSES = woBuildTree(cleaned);
    woRender();
}


// ─────────────────────────────────────────────────────
// BUILD TREE
// ─────────────────────────────────────────────────────

function woBuildTree(rows) {
    const whMap = {};

    rows.forEach(function (row) {
        const wh = String(row.warehouse || '').trim();
        if (!wh) return;

        if (!whMap[wh]) {
            whMap[wh] = {
                warehouse: wh,
                company  : woDetectCompany(wh),
                groupMap : {}
            };
        }

        const grp = String(row.item_group || row._display_group || 'Other').trim();
        if (!whMap[wh].groupMap[grp]) whMap[wh].groupMap[grp] = [];

        whMap[wh].groupMap[grp].push({
            item_code   : row.item_code  || '',
            item_name   : row.item_name  || '',
            item_group  : grp,
            actual_qty  : woNum(row.actual_qty),
            reserved_qty: woNum(row.reserved_qty),
            warehouse   : wh
        });
    });

    return Object.keys(whMap)
        .sort(function (a, b) { return a.localeCompare(b); })
        .map(function (whKey) {
            const entry = whMap[whKey];
            const sortedGroupNames = woSortGroupNames(Object.keys(entry.groupMap));
            return {
                warehouse: entry.warehouse,
                company  : entry.company,
                groups   : sortedGroupNames.map(function (gName) {
                    return { name: gName, items: entry.groupMap[gName] || [] };
                })
            };
        });
}


// ─────────────────────────────────────────────────────
// RENDER
// ─────────────────────────────────────────────────────

function woRender() {
    let data = WO_WAREHOUSES.map(function (wh) {
        return {
            warehouse: wh.warehouse,
            company  : wh.company,
            groups   : wh.groups.map(function (g) {
                return { name: g.name, items: g.items.slice() };
            })
        };
    });

    if (WO_FILTERS.company !== 'all') {
        data = data.filter(function (wh) { return wh.company === WO_FILTERS.company; });
    }

    if (WO_FILTERS.search) {
        const q = WO_FILTERS.search;
        data = data
            .map(function (wh) {
                const whMatch = wh.warehouse.toLowerCase().includes(q);
                const filteredGroups = wh.groups
                    .map(function (g) {
                        const matchItems = whMatch ? g.items : g.items.filter(function (item) {
                            return (item.item_code + ' ' + item.item_name + ' ' + item.item_group)
                                .toLowerCase().includes(q);
                        });
                        return { name: g.name, items: matchItems };
                    })
                    .filter(function (g) { return g.items.length > 0; });
                return { warehouse: wh.warehouse, company: wh.company, groups: filteredGroups };
            })
            .filter(function (wh) { return wh.groups.length > 0; });
    }

    if (WO_FILTERS.onlyWithStock) {
        data = data.filter(function (wh) { return woWarehouseTotalQty(wh) > 0; });
    }

    data.sort(function (a, b) {
        if (WO_FILTERS.sortBy === 'qty')   return woWarehouseTotalQty(b) - woWarehouseTotalQty(a);
        if (WO_FILTERS.sortBy === 'items') return woWarehouseTotalItems(b) - woWarehouseTotalItems(a);
        return a.warehouse.localeCompare(b.warehouse);
    });

    woUpdateSummary(data);
    woRenderGrid(data);
}

function woUpdateSummary(data) {
    function el(id) { return document.getElementById(id); }
    const whEl  = el('wo-total-warehouses');
    const itEl  = el('wo-total-items');
    const qtyEl = el('wo-total-qty');
    const grEl  = el('wo-total-groups');
    if (whEl)  whEl.innerText = data.length;
    if (itEl)  itEl.innerText = woAllTotalItems(data);
    if (qtyEl) qtyEl.innerText = woAllTotalQty(data).toFixed(2);
    if (grEl)  grEl.innerText = woAllGroupCount(data);
}

function woRenderGrid(data) {
    const grid = document.getElementById('wo-grid');
    if (!grid) return;

    if (!data.length) {
        grid.innerHTML = `
            <div class="wo-empty">
                <div class="wo-empty-icon">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                        <polyline points="9 22 9 12 15 12 15 22"/>
                    </svg>
                </div>
                <div class="wo-empty-title">No warehouses found</div>
                <div class="wo-empty-sub">Adjust your filters or refresh the data.</div>
            </div>`;
        return;
    }

    let html = '';

    if (WO_FILTERS.company === 'all') {
        const inOrder = WO_COMPANY_ORDER.filter(function (co) {
            return data.some(function (wh) { return wh.company === co; });
        });
        const others = data.map(function (wh) { return wh.company; })
            .filter(function (co, i, arr) {
                return arr.indexOf(co) === i && WO_COMPANY_ORDER.indexOf(co) === -1;
            });

        inOrder.concat(others).forEach(function (co) {
            const coWhs = data.filter(function (wh) { return wh.company === co; });
            if (!coWhs.length) return;
            const label    = WO_COMPANY_LABELS[co] || co;
            const dotClass = WO_COMPANY_COLORS[co] || 'dot-teal';
            html += `
                <div class="wo-section-heading">
                    <span class="wo-section-dot ${dotClass}"></span>
                    ${woEsc(label)}
                    <span class="wo-section-count">${coWhs.length} warehouse${coWhs.length !== 1 ? 's' : ''}</span>
                </div>
                <div class="wo-section-grid">
                    ${coWhs.map(function (wh, idx) { return woRenderCard(wh, idx); }).join('')}
                </div>`;
        });
    } else {
        html = `<div class="wo-section-grid">
                    ${data.map(function (wh, idx) { return woRenderCard(wh, idx); }).join('')}
                </div>`;
    }

    grid.innerHTML = html;

    grid.querySelectorAll('.wo-group-header').forEach(function (hdr) {
        hdr.addEventListener('click', function () {
            const open = !this.classList.contains('is-open');
            this.classList.toggle('is-open', open);
            const body = this.nextElementSibling;
            if (body) body.classList.toggle('is-open', open);
        });
    });
}


// ─────────────────────────────────────────────────────
// CARD + GROUP RENDERING
// ─────────────────────────────────────────────────────

function woRenderCard(wh, idx) {
    const totalQty   = woWarehouseTotalQty(wh);
    const itemCount  = woWarehouseTotalItems(wh);
    const groupCount = woWarehouseGroupCount(wh);
    const dotClass   = WO_COMPANY_COLORS[wh.company] || 'dot-teal';
    const cardClass  = WO_COMPANY_CARD_CLASS[wh.company] || '';

    const groupsHtml = (wh.groups || []).map(function (group) {
        return woRenderGroupBlock(group);
    }).join('');

    return `
        <div class="wo-card ${cardClass}" style="animation-delay:${Math.min(idx * 0.05, 0.4)}s">
            <div class="wo-card-top">
                <div>
                    <h3 class="wo-card-warehouse-name">${woEsc(wh.warehouse)}</h3>
                    <div class="wo-card-company-tag">
                        <span class="wo-card-company-dot ${dotClass}"></span>
                        ${woEsc(WO_COMPANY_LABELS[wh.company] || wh.company)}
                    </div>
                </div>
                <div class="wo-live-badge">
                    <span class="wo-live-dot"></span>
                    Live
                </div>
            </div>

            <div class="wo-card-stats">
                <div class="wo-card-stat stat-qty">
                    <div class="wo-card-stat-label">Total Qty</div>
                    <div class="wo-card-stat-value">${totalQty.toFixed(2)}</div>
                </div>
                <div class="wo-card-stat stat-items">
                    <div class="wo-card-stat-label">Items</div>
                    <div class="wo-card-stat-value">${itemCount}</div>
                </div>
                <div class="wo-card-stat stat-groups">
                    <div class="wo-card-stat-label">Groups</div>
                    <div class="wo-card-stat-value">${groupCount}</div>
                </div>
            </div>

            <div class="wo-card-groups">
                ${groupsHtml || '<div class="wo-no-items">No matching items.</div>'}
            </div>
        </div>`;
}

function woRenderGroupBlock(group) {
    const swatchIdx = woGetGroupSwatch(group.name);
    const totalQty  = group.items.reduce(function (s, i) { return s + woNum(i.actual_qty); }, 0);
    const itemCount = group.items.length;

    const itemsHtml = group.items.map(function (item) {
        const available = woNum(item.actual_qty) - woNum(item.reserved_qty);
        const statusCls = available <= 0 ? 'status-out'
                        : available <= WO_LOW_STOCK_THRESHOLD ? 'status-low'
                        : 'status-ok';
        const typeLabel = woGetTypeLabel(item);
        const typeBadge = typeLabel
            ? `<span class="wo-type-badge wo-type-${typeLabel.toLowerCase()}">${typeLabel}</span>`
            : '';

        return `
            <div class="wo-item-row">
                <div class="wo-item-info">
                    <div class="wo-item-name">
                        ${woEsc(woCleanName(item.item_name, item.item_group))}
                        ${typeBadge}
                    </div>
                    <div class="wo-item-code">${woEsc(item.item_code)}</div>
                </div>
                <div class="wo-item-right">
                    <div class="wo-item-qty">${woFmt(item.actual_qty)}</div>
                    <div class="wo-item-status ${statusCls}"></div>
                </div>
            </div>`;
    }).join('');

    return `
        <div class="wo-group-block">
            <div class="wo-group-header">
                <div class="wo-group-name-wrap">
                    <span class="wo-group-swatch swatch-${swatchIdx}"></span>
                    <span class="wo-group-name">${woEsc(group.name)}</span>
                </div>
                <div class="wo-group-meta">
                    <span class="wo-group-qty-badge">${woFmt(totalQty)}</span>
                    <span class="wo-group-count">${itemCount} item${itemCount !== 1 ? 's' : ''}</span>
                    <svg class="wo-group-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="6 9 12 15 18 9"/>
                    </svg>
                </div>
            </div>
            <div class="wo-group-items">
                ${itemsHtml}
            </div>
        </div>`;
}

function woGetTypeLabel(item) {
    const g = String(item.item_group || '').trim();
    if (g === 'Fresh Frozen - BHO') return 'BHO';
    if (g === 'Fresh Frozen - SHO') return 'SHO';
    return '';
}