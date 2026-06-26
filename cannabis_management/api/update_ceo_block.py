import frappe

NEW_HTML = """<div class="ceo-dash">

  <!-- HERO HEADER (dark premium) -->
  <div class="ceo-hero">
    <div class="ambient-glow"></div>

    <div class="dash-header">
      <div>
        <div class="label"><span class="ceo-co-label">Motley Terpz</span></div>
        <h1>Matt's Command Center</h1>
        <p class="subtitle">All your operations at a glance — <span class="ceo-greeting"></span></p>
      </div>
      <div class="ceo-header-actions">
        <button class="ceo-refresh-btn" id="ceoRefreshBtn" onclick="ceoDash.reload()">
          <svg viewBox="0 0 24 24"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          Refresh
        </button>
      </div>
    </div>

    <!-- PERIOD TOGGLE -->
    <div class="ceo-period-bar">
      <div class="ceo-period-toggle">
        <button class="ceo-period-btn" data-period="weekly">Weekly</button>
        <button class="ceo-period-btn active" data-period="monthly">Monthly</button>
        <button class="ceo-period-btn" data-period="overall">Overall</button>
      </div>
      <div class="ceo-period-label" id="ceo-period-label">This Month</div>
    </div>
  </div>

  <!-- AT A GLANCE KPI CARDS -->
  <div class="section-title">
    <span class="section-icon"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    At a Glance
  </div>
  <div class="ceo-kpi-grid">
    <div class="ceo-kpi-card" style="--kc:var(--accent-emerald)">
      <div class="ceo-kpi-accent"></div>
      <div class="ceo-kpi-label" id="ceo-kpi-sales-label">Sales — This Month</div>
      <div class="ceo-kpi-value" id="ceo-kpi-sales"><span class="stat-loader"></span></div>
      <div class="ceo-kpi-sub" id="ceo-kpi-sales-sub">loading…</div>
    </div>
    <div class="ceo-kpi-card" style="--kc:var(--accent-amber)">
      <div class="ceo-kpi-accent"></div>
      <div class="ceo-kpi-label">AR Outstanding</div>
      <div class="ceo-kpi-value" id="ceo-kpi-ar"><span class="stat-loader"></span></div>
      <div class="ceo-kpi-sub" id="ceo-kpi-ar-sub">loading…</div>
    </div>
    <div class="ceo-kpi-card" style="--kc:var(--accent-rose)">
      <div class="ceo-kpi-accent"></div>
      <div class="ceo-kpi-label">AP Outstanding</div>
      <div class="ceo-kpi-value" id="ceo-kpi-ap"><span class="stat-loader"></span></div>
      <div class="ceo-kpi-sub" id="ceo-kpi-ap-sub">loading…</div>
    </div>
    <div class="ceo-kpi-card" style="--kc:var(--accent-violet)">
      <div class="ceo-kpi-accent"></div>
      <div class="ceo-kpi-label">Batches in Production</div>
      <div class="ceo-kpi-value" id="ceo-kpi-batches"><span class="stat-loader"></span></div>
      <div class="ceo-kpi-sub">active batches</div>
    </div>
  </div>

  <div id="ceo-pipeline-container"></div>

  <!-- PAYMENTS RECEIVED -->
  <div class="section-title" style="margin-top:32px">
    <span class="section-icon">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
           stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
        <polyline points="17 6 23 6 23 12"/>
      </svg>
    </span>
    Payments Received
  </div>
  <div class="ceo-table-card">
    <div class="ceo-table-toolbar">
      <div class="ceo-table-title" id="pr-title">Client payments into bank · last 14 days</div>
      <div class="pr-type-toggle">
        <button class="pr-type-btn active" data-type="Bank">Bank</button>
        <button class="pr-type-btn" data-type="Cash">Cash</button>
      </div>
      <div class="pr-date-wrap">
        <label class="pr-date-label" for="pr-end-date">Ending</label>
        <input type="date" id="pr-end-date" class="pr-date-input">
      </div>
      <span class="ceo-badge" id="pr-badge">loading…</span>
    </div>
    <div class="pr-scroll">
      <div id="pr-table-body">
        <div class="ceo-loading"><div class="ceo-spinner"></div></div>
      </div>
    </div>
  </div>

  <div class="section-divider" style="margin-top:32px"></div>

  <!-- TOLLING PARTNER STOCK -->
  <div class="section-title">
    <span class="section-icon"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2v-4M9 21H5a2 2 0 01-2-2v-4m0 0h18" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    Tolling Partner Stock — By Batch
  </div>
  <div class="stat-grid" id="tolling-batch-grid" style="grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));">
    <div class="stat-card" style="--stat-accent:var(--accent-cyan);--stat-accent-dim:var(--accent-cyan-dim);">
      <div class="stat-ring"><div class="stat-ring-inner"></div></div>
      <div class="stat-number"><span class="stat-loader"></span></div>
      <div class="stat-label">Loading…</div>
      <div class="stat-sub">Tolling Partner Stock</div>
    </div>
  </div>

  <div class="section-divider"></div>

  <!-- SALES TABLE -->
  <div class="section-title" id="ceo-sales-section-label">
    <span class="section-icon"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    <span id="ceo-sales-period-label">Sales — This Month</span>
  </div>
  <div class="ceo-table-card">
    <div class="ceo-table-toolbar">
      <div class="ceo-table-title">Invoice Summary</div>
      <span class="ceo-badge" id="ceo-sales-count">loading…</span>
    </div>
    <div id="ceo-sales-table"><div class="ceo-loading"><div class="ceo-spinner"></div></div></div>
  </div>

  <!-- AR TABLE -->
  <div class="section-title" style="margin-top:32px">
    <span class="section-icon"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    Accounts Receivable — All Outstanding
  </div>
  <div class="ceo-table-card">
    <div class="ceo-table-toolbar">
      <div class="ceo-table-title">Open Balances</div>
      <span class="ceo-badge" id="ceo-ar-count">loading…</span>
    </div>
    <div id="ceo-ar-table"><div class="ceo-loading"><div class="ceo-spinner"></div></div></div>
  </div>

  <!-- AP TABLE -->
  <div class="section-title" style="margin-top:32px">
    <span class="section-icon"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    Accounts Payable — All Outstanding
  </div>
  <div class="ceo-table-card">
    <div class="ceo-table-toolbar">
      <div class="ceo-table-title">Outstanding Bills</div>
      <span class="ceo-badge" id="ceo-ap-count">loading…</span>
    </div>
    <div id="ceo-ap-table"><div class="ceo-loading"><div class="ceo-spinner"></div></div></div>
  </div>

  <!-- BATCHES TABLE -->
  <div class="section-title" style="margin-top:32px">
    <span class="section-icon"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    Batches in Production
  </div>
  <div class="ceo-table-card">
    <div class="ceo-table-toolbar">
      <div class="ceo-table-title">Active Batches</div>
      <span class="ceo-badge" id="ceo-batches-count">loading…</span>
    </div>
    <div id="ceo-batches-table"><div class="ceo-loading"><div class="ceo-spinner"></div></div></div>
  </div>

  <!-- TIMESHEETS TABLE -->
  <div class="section-title" style="margin-top:32px">
    <span class="section-icon"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    <span id="ceo-ts-period-label">Timesheets — This Month</span>
  </div>
  <div class="ceo-table-card">
    <div class="ceo-table-toolbar">
      <div class="ceo-table-title">Hours Logged</div>
      <span class="ceo-badge" id="ceo-ts-count">loading…</span>
    </div>
    <div id="ceo-ts-table"><div class="ceo-loading"><div class="ceo-spinner"></div></div></div>
  </div>

  <!-- FINANCIAL REPORTS -->
  <div class="section-title">
    <span class="section-icon"><svg viewBox="0 0 24 24" width="14" height="14"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><polyline points="14 2 14 8 20 8" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><line x1="16" y1="13" x2="8" y2="13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><line x1="16" y1="17" x2="8" y2="17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><polyline points="10 9 9 9 8 9" stroke="currentColor" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
    Financial Reports
  </div>
  <div class="card-grid">
    <a class="dash-card" href="/app/query-report/Profit and Loss Statement" style="--card-accent: var(--accent-emerald); --card-accent-dim: var(--accent-emerald-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Profit &amp; Loss</h3><p>Revenue, expenses and net income over a selected period.</p></div><span class="card-tag">P&amp;L</span></a>
    <a class="dash-card" href="/app/query-report/Consolidated Financial Statement" style="--card-accent: var(--accent-rose); --card-accent-dim: var(--accent-rose-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M9 17H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><path d="M15 17h4a2 2 0 002-2V5a2 2 0 00-2-2h-4"/><line x1="12" y1="3" x2="12" y2="21"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Consolidated Financial Statement</h3><p>Group-level P&amp;L, balance sheet and cash flow across all companies.</p></div><span class="card-tag">Consolidated</span></a>
    <a class="dash-card" href="/app/query-report/General Ledger" style="--card-accent: var(--accent-blue); --card-accent-dim: var(--accent-blue-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>General Ledger</h3><p>Full transaction-level ledger entries across all accounts.</p></div><span class="card-tag">Ledger</span></a>
    <a class="dash-card" href="/app/query-report/Balance Sheet" style="--card-accent: var(--accent-violet); --card-accent-dim: var(--accent-violet-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><line x1="12" y1="2" x2="12" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/><line x1="2" y1="12" x2="22" y2="12"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Balance Sheet</h3><p>Assets, liabilities and equity snapshot at a point in time.</p></div><span class="card-tag">Balance Sheet</span></a>
    <a class="dash-card" href="/app/query-report/Trial Balance" style="--card-accent: var(--accent-amber); --card-accent-dim: var(--accent-amber-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Trial Balance</h3><p>Debit and credit totals for all ledger accounts at period end.</p></div><span class="card-tag">Trial Balance</span></a>
    <a class="dash-card" href="/app/query-report/Lab Tolling Report" style="--card-accent: var(--accent-cyan); --card-accent-dim: var(--accent-cyan-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2v-4M9 21H5a2 2 0 01-2-2v-4m0 0h18"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Lab Tolling Report</h3><p>Lab processing charges, tolling jobs and service billing summary.</p></div><span class="card-tag">Lab</span></a>
    <a class="dash-card" href="/app/query-report/Item-wise%20Sales%20History" style="--card-accent: var(--accent-orange); --card-accent-dim: var(--accent-orange-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M3 3h18v4H3z"/><path d="M7 11h10"/><path d="M7 15h7"/><path d="M7 19h5"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Sales Revenue Report</h3><p>Item-wise sales history and revenue performance across products.</p></div><span class="card-tag">Sales</span></a>
    <a class="dash-card" href="/app/query-report/Profit%20and%20Loss%20Statement" style="--card-accent: var(--accent-emerald); --card-accent-dim: var(--accent-emerald-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>P&amp;L Report</h3><p>Review revenue, expenses, and profitability for the selected period.</p></div><span class="card-tag">P&amp;L</span></a>
    <a class="dash-card" href="/app/query-report/Accounts%20Receivable" style="--card-accent: var(--accent-blue); --card-accent-dim: var(--accent-blue-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M17 20h5v-2a3 3 0 00-5.356-1.857"/><path d="M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857"/><path d="M7 20H2v-2a3 3 0 015.356-1.857"/><path d="M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>AR Report</h3><p>View outstanding customer balances and receivables aging details.</p></div><span class="card-tag">AR</span></a>
    <a class="dash-card" href="/app/ar-dashboard" style="--card-accent: var(--accent-blue); --card-accent-dim: var(--accent-blue-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M17 20h5v-2a3 3 0 00-5.356-1.857"/><path d="M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857"/><path d="M7 20H2v-2a3 3 0 015.356-1.857"/><path d="M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Aging AR Dashboard</h3><p>View outstanding customer balances and receivables aging details.</p></div><span class="card-tag">AR</span></a>
  </div>

  <!-- LOGISTICS -->
  <div class="section-title">Logistics &amp; Operations</div>
  <div class="card-grid featured">
    <a class="dash-card featured-card" href="/app/tsbc-logistics" style="--card-accent: var(--accent-emerald); --card-accent-dim: var(--accent-emerald-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>TSBC Logistics</h3><p>Track shipments, routes and delivery operations across TSBC network.</p></div><span class="card-tag">Operations</span></a>
    <a class="dash-card featured-card" href="/app/motley-logistics" style="--card-accent: var(--accent-cyan); --card-accent-dim: var(--accent-cyan-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><rect x="1" y="3" width="15" height="13" rx="2"/><polyline points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Motley Logistics</h3><p>Monitor Motley's logistics pipeline, fulfillment status and dispatch queues.</p></div><span class="card-tag">Operations</span></a>
  </div>

  <div class="section-divider"></div>

  <!-- INVENTORY -->
  <div class="section-title">Inventory &amp; Stock</div>
  <div class="card-grid">
    <a class="dash-card" href="/inventory-dashboard" style="--card-accent: var(--accent-amber); --card-accent-dim: var(--accent-amber-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Inventory Dashboard</h3><p>Real-time inventory levels, warehouse allocation and reorder alerts.</p></div><span class="card-tag">Inventory</span></a>
    <a class="dash-card" href="/app/stock-summary" style="--card-accent: var(--accent-orange); --card-accent-dim: var(--accent-orange-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Stock Summary</h3><p>Consolidated view of stock quantities, valuations and movements.</p></div><span class="card-tag">Inventory</span></a>
  </div>

  <div class="section-divider"></div>

  <!-- FINANCIAL OVERVIEW -->
  <div class="section-title">Financial Overview</div>
  <div class="card-grid">
    <a class="dash-card" href="/app/receivable-summary" style="--card-accent: var(--accent-blue); --card-accent-dim: var(--accent-blue-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Receivable Summary</h3><p>Outstanding receivables, aging analysis and collection status.</p></div><span class="card-tag">Finance</span></a>
    <a class="dash-card" href="/app/receivable-summary-c" style="--card-accent: var(--accent-violet); --card-accent-dim: var(--accent-violet-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Receivables by Client</h3><p>Client-wise breakdown of outstanding amounts and payment history.</p></div><span class="card-tag">Finance</span></a>
    <a class="dash-card" href="/app/payable-summary" style="--card-accent: var(--accent-rose); --card-accent-dim: var(--accent-rose-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Payable Summary</h3><p>Vendor payables, upcoming dues and payment scheduling overview.</p></div><span class="card-tag">Finance</span></a>
    <a class="dash-card" href="/app/payable-summary-clie" style="--card-accent: var(--accent-gold); --card-accent-dim: var(--accent-gold-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Payables by Client</h3><p>Detailed vendor-wise payable breakdown and obligation tracking.</p></div><span class="card-tag">Finance</span></a>
  </div>

  <div class="section-divider"></div>

  <!-- SALES & ACCOUNTING -->
  <div class="section-title">Sales &amp; Accounting</div>
  <div class="card-grid">
    <a class="dash-card" href="/app/sales-summary" style="--card-accent: var(--accent-emerald); --card-accent-dim: var(--accent-emerald-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Sales Summary</h3><p>Revenue metrics, sales pipeline performance and growth trends.</p></div><span class="card-tag">Revenue</span></a>
    <a class="dash-card" href="/app/day-book-dashboard" style="--card-accent: var(--accent-blue); --card-accent-dim: var(--accent-blue-dim);"><div class="card-top"><div class="card-icon"><svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg></div><div class="card-arrow"><svg viewBox="0 0 24 24"><path d="M7 17L17 7M17 7H7M17 7v10"/></svg></div></div><div class="card-body"><h3>Day Book</h3><p>Daily journal entries, transaction logs and accounting trail.</p></div><span class="card-tag">Accounting</span></a>
  </div>

</div>"""

NEW_STYLE = """.ceo-dash {
  --border: #e2e8f0; --border-hover: #cbd5e1;
  --text-primary: #1e293b; --text-secondary: #64748b; --text-muted: #94a3b8;
  --accent-gold: #b45309; --accent-gold-dim: rgba(180,83,9,0.08);
  --accent-emerald: #059669; --accent-emerald-dim: rgba(5,150,105,0.08);
  --accent-blue: #2563eb; --accent-blue-dim: rgba(37,99,235,0.08);
  --accent-rose: #e11d48; --accent-rose-dim: rgba(225,29,72,0.08);
  --accent-amber: #d97706; --accent-amber-dim: rgba(217,119,6,0.08);
  --accent-violet: #7c3aed; --accent-violet-dim: rgba(124,58,237,0.08);
  --accent-cyan: #0891b2; --accent-cyan-dim: rgba(8,145,178,0.08);
  --accent-orange: #ea580c; --accent-orange-dim: rgba(234,88,12,0.08);
  --radius: 12px; --radius-sm: 8px;
  font-family: 'DM Sans', sans-serif;
  max-width: 1280px;
  margin: 0 auto;
  padding: 28px 24px 48px;
  position: relative;
}

/* ── HERO HEADER ── */
.ceo-dash .ceo-hero {
  background: linear-gradient(135deg, #0f172a 0%, #1a2540 55%, #121d2e 100%);
  border-radius: 16px;
  padding: 32px 32px 0;
  margin-bottom: 32px;
  position: relative;
  overflow: hidden;
  box-shadow: 0 20px 40px rgba(15,23,42,0.2), 0 4px 12px rgba(15,23,42,0.12);
}
.ceo-dash .ceo-hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,0.035) 1px, transparent 0);
  background-size: 28px 28px;
  pointer-events: none;
  z-index: 0;
}
.ceo-dash .ambient-glow {
  position: absolute;
  top: -80px; right: -80px;
  width: 520px; height: 520px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(217,119,6,0.2) 0%, rgba(217,119,6,0.06) 35%, transparent 65%);
  pointer-events: none;
  z-index: 0;
}
.ceo-dash .ceo-hero .dash-header { position: relative; z-index: 1; margin-bottom: 0; }
.ceo-dash .ceo-hero .dash-header .label { color: #f59e0b; }
.ceo-dash .ceo-hero .dash-header .label::before { background: #f59e0b; }
.ceo-dash .ceo-hero .dash-header h1 { font-size: 32px; font-weight: 800; color: #f8fafc; letter-spacing: -0.8px; }
.ceo-dash .ceo-hero .dash-header .subtitle { color: rgba(248,250,252,0.5); }
.ceo-dash .ceo-hero .dash-header .subtitle span { color: #fbbf24; font-weight: 600; }
.ceo-dash .ceo-hero .ceo-refresh-btn { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.18); color: rgba(248,250,252,0.7); }
.ceo-dash .ceo-hero .ceo-refresh-btn:hover { background: rgba(255,255,255,0.14); border-color: #fbbf24; color: #fbbf24; }
.ceo-dash .ceo-hero .ceo-period-bar {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  border-bottom: none;
  border-radius: 12px 12px 0 0;
  margin-top: 28px; margin-bottom: 0;
  position: relative; z-index: 1;
}
.ceo-dash .ceo-hero .ceo-period-toggle { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.1); }
.ceo-dash .ceo-hero .ceo-period-btn { color: rgba(248,250,252,0.5); }
.ceo-dash .ceo-hero .ceo-period-btn:hover:not(.active) { background: rgba(255,255,255,0.1); color: rgba(248,250,252,0.85); }
.ceo-dash .ceo-hero .ceo-period-btn.active { background: #d97706; color: #fff; box-shadow: 0 1px 6px rgba(217,119,6,0.4); }
.ceo-dash .ceo-hero .ceo-period-label { color: rgba(248,250,252,0.45); }

/* ── Header base ── */
.ceo-dash .dash-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; flex-wrap: wrap; gap: 16px; }
.ceo-dash .dash-header .label { font-size: 11px; font-weight: 600; letter-spacing: 2px; text-transform: uppercase; color: var(--accent-gold); margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.ceo-dash .dash-header .label::before { content: ''; display: inline-block; width: 16px; height: 2px; background: var(--accent-gold); border-radius: 1px; }
.ceo-dash .dash-header h1 { font-size: 28px; font-weight: 700; color: var(--text-primary); line-height: 1.2; margin-bottom: 4px; letter-spacing: -0.5px; }
.ceo-dash .dash-header .subtitle { font-size: 13px; color: var(--text-secondary); margin: 0; }
.ceo-dash .dash-header .subtitle span { color: var(--accent-gold); font-weight: 500; }

/* ── Refresh button ── */
.ceo-header-actions { display: flex; align-items: flex-start; }
.ceo-refresh-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border: 1.5px solid var(--border); border-radius: var(--radius-sm); background: #fff; color: var(--text-secondary); font-size: 12px; font-weight: 600; font-family: 'DM Sans', sans-serif; cursor: pointer; transition: all 0.15s; }
.ceo-refresh-btn:hover { border-color: var(--accent-gold); color: var(--accent-gold); }
.ceo-refresh-btn svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.ceo-refresh-btn.spinning svg { animation: cdSpin 0.8s linear infinite; }

/* ── Period bar (default light) ── */
.ceo-period-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 28px; padding: 10px 16px; background: #f8fafc; border: 1px solid var(--border); border-radius: var(--radius); }

/* ── Payments received ── */
.pr-date-wrap { display: flex; align-items: center; gap: 8px; }
.pr-date-label { font-size: 12px; color: var(--text-secondary); font-weight: 600; white-space: nowrap; font-family: 'DM Sans', sans-serif; }
.pr-date-input { font-size: 12px; font-family: 'DM Sans', sans-serif; padding: 5px 10px; border-radius: var(--radius-sm); border: 1.5px solid var(--border); background: #fff; color: var(--text-primary); cursor: pointer; transition: border-color 0.15s; }
.pr-date-input:hover, .pr-date-input:focus { border-color: var(--accent-gold); outline: none; }
.pr-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.pr-pivot-table { width: 100%; border-collapse: collapse; min-width: 900px; table-layout: auto; }
.pr-pivot-table thead th { font-size: 10.5px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.07em; padding: 10px 14px; text-align: left; background: #fafbfc; border-bottom: 1px solid #f1f5f9; white-space: nowrap; }
.pr-pivot-table thead th.pr-num { text-align: right; }
.pr-pivot-table thead th.pr-sticky { position: sticky; left: 0; z-index: 2; background: #fafbfc; border-right: 1px solid #f1f5f9; min-width: 160px; }
.pr-pivot-table thead th.pr-total-col { background: #f1f5f9; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; }
.pr-pivot-table tbody tr { border-bottom: 1px solid #f8fafc; transition: background 0.12s; }
.pr-pivot-table tbody tr:last-child { border-bottom: none; }
.pr-pivot-table tbody tr:hover { background: #fafbfc; }
.pr-pivot-table tbody tr:hover td.pr-sticky { background: #fafbfc; }
.pr-pivot-table tbody td { padding: 10px 14px; font-size: 13px; color: var(--text-secondary); white-space: nowrap; }
.pr-pivot-table tbody td.pr-sticky { position: sticky; left: 0; background: #fff; border-right: 1px solid #f1f5f9; font-weight: 600; color: var(--text-primary); z-index: 1; }
.pr-pivot-table tbody td.pr-num { text-align: right; font-family: 'DM Mono', monospace; font-size: 12px; }
.pr-pivot-table tbody td.pr-total-col { text-align: right; font-family: 'DM Mono', monospace; font-size: 12px; font-weight: 700; color: var(--text-primary); background: #fafbfc; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; }
.pr-pivot-table tbody td.pr-zero { color: #e2e8f0; text-align: right; }
.pr-pivot-table tfoot tr { border-top: 2px solid #e2e8f0; }
.pr-pivot-table tfoot td { padding: 10px 14px; font-size: 12px; font-weight: 700; color: var(--text-primary); background: #f1f5f9; white-space: nowrap; }
.pr-pivot-table tfoot td.pr-sticky { position: sticky; left: 0; background: #e8edf3; border-right: 1px solid #e2e8f0; z-index: 1; }
.pr-pivot-table tfoot td.pr-num { text-align: right; font-family: 'DM Mono', monospace; }
.pr-pivot-table tfoot td.pr-total-col { text-align: right; font-family: 'DM Mono', monospace; background: #e8edf3; border-left: 1px solid #d1d9e2; border-right: 1px solid #d1d9e2; }
.pr-day-date { display: block; font-weight: 400; font-size: 10px; opacity: 0.65; text-transform: none; letter-spacing: 0; margin-top: 2px; }
.pr-empty { text-align: center; padding: 40px; color: var(--text-muted); font-size: 13px; }
.pr-type-toggle { display: flex; gap: 0; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 3px; }
.pr-type-btn { padding: 5px 16px; border: none; border-radius: 6px; background: transparent; font-size: 12px; font-weight: 600; font-family: 'DM Sans', sans-serif; color: var(--text-secondary); cursor: pointer; transition: all 0.18s; white-space: nowrap; }
.pr-type-btn:hover:not(.active) { background: #f1f5f9; color: var(--text-primary); }
.pr-type-btn.active { background: #1e293b; color: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }

/* ── Period toggle (light) ── */
.ceo-period-toggle { display: flex; gap: 4px; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 3px; }
.ceo-period-btn { padding: 6px 20px; border: none; border-radius: 6px; background: transparent; font-size: 12px; font-weight: 600; font-family: 'DM Sans', sans-serif; color: var(--text-secondary); cursor: pointer; transition: all 0.18s; white-space: nowrap; }
.ceo-period-btn:hover:not(.active) { background: #f1f5f9; color: var(--text-primary); }
.ceo-period-btn.active { background: #1e293b; color: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
.ceo-period-label { font-size: 12px; font-weight: 600; color: var(--text-secondary); font-family: 'DM Mono', monospace; letter-spacing: 0.03em; }

/* ── KPI CARDS ── */
.ceo-kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 36px; }
.ceo-kpi-card { position: relative; background: #fff; border: 1px solid var(--border); border-radius: var(--radius); padding: 24px 22px 20px; overflow: hidden; transition: all 0.2s; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.ceo-kpi-card:hover { border-color: var(--kc); transform: translateY(-3px); box-shadow: 0 8px 28px rgba(0,0,0,0.09); }
.ceo-kpi-accent { position: absolute; top: 0; left: 0; right: 0; height: 4px; background: var(--kc); }
.ceo-kpi-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 14px; }
.ceo-kpi-value { font-size: 38px; font-weight: 800; color: var(--kc); line-height: 1; margin-bottom: 8px; min-height: 44px; display: flex; align-items: flex-end; letter-spacing: -1.5px; }
.ceo-kpi-value.loaded { animation: cdNumberPop 0.35s cubic-bezier(0.34,1.56,0.64,1) both; }
.ceo-kpi-value.error { font-size: 14px; font-weight: 500; color: var(--text-muted); letter-spacing: 0; }
.ceo-kpi-sub { font-size: 11px; color: var(--text-muted); font-family: 'DM Mono', monospace; }

/* ── SECTION TITLES ── */
.ceo-dash .section-title { font-size: 12px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--text-secondary); margin-bottom: 16px; display: flex; align-items: center; gap: 8px; padding-left: 12px; border-left: 3px solid var(--accent-gold); border-radius: 0 2px 2px 0; }
.ceo-dash .section-icon { display: inline-flex; align-items: center; color: var(--accent-gold); }
.ceo-dash .section-divider { height: 1px; background: var(--border); margin: 8px 0 28px; }

/* ── PIPELINE STAT CARDS ── */
.ceo-dash .stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 32px; }
.ceo-dash .stat-card { position: relative; background: #fff; border: 1px solid var(--border); border-radius: var(--radius); padding: 24px 20px 20px; overflow: hidden; transition: all 0.25s ease; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.ceo-dash .stat-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 4px; background: var(--stat-accent); }
.ceo-dash .stat-card:hover { border-color: var(--stat-accent); transform: translateY(-3px); box-shadow: 0 8px 28px rgba(0,0,0,0.09); }
.ceo-dash .stat-ring { position: absolute; top: -20px; right: -20px; width: 80px; height: 80px; border-radius: 50%; border: 1.5px solid var(--stat-accent); opacity: 0.12; pointer-events: none; }
.ceo-dash .stat-ring-inner { position: absolute; top: 10px; left: 10px; width: 60px; height: 60px; border-radius: 50%; border: 1px solid var(--stat-accent); opacity: 0.35; }
.ceo-dash .stat-number { font-size: 42px; font-weight: 800; color: var(--stat-accent); line-height: 1; margin-bottom: 10px; min-height: 44px; display: flex; align-items: flex-end; letter-spacing: -1.5px; }
.ceo-dash .stat-label { font-size: 13px; font-weight: 600; color: var(--text-primary); line-height: 1.35; margin-bottom: 4px; }
.ceo-dash .stat-sub { font-size: 11px; color: var(--text-muted); font-weight: 400; }
.ceo-dash .stat-loader { display: inline-block; width: 44px; height: 32px; border-radius: 6px; background: linear-gradient(110deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%); background-size: 200% 100%; animation: cdShimmer 1.5s ease-in-out infinite; }
.ceo-dash .stat-number.loaded { animation: cdNumberPop 0.35s cubic-bezier(0.34,1.56,0.64,1) both; }
.ceo-dash .stat-number.error { font-size: 14px; font-weight: 500; color: var(--text-muted); letter-spacing: 0; }

/* ── TABLE CARDS ── */
.ceo-table-card { background: #fff; border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; margin-bottom: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }
.ceo-table-toolbar { display: flex; align-items: center; gap: 12px; padding: 14px 20px; border-bottom: 1px solid #f1f5f9; flex-wrap: wrap; }
.ceo-table-title { font-size: 14px; font-weight: 700; color: var(--text-primary); flex: 1; }
.ceo-badge { font-size: 11px; background: #f1f5f9; color: #64748b; border-radius: 20px; padding: 3px 10px; font-weight: 600; white-space: nowrap; }
.ceo-dash .ceo-data-table { width: 100%; border-collapse: collapse; }
.ceo-dash .ceo-data-table thead th { font-size: 10.5px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.07em; padding: 11px 16px; text-align: left; background: #fafbfc; border-bottom: 1px solid #f1f5f9; white-space: nowrap; }
.ceo-dash .ceo-data-table tbody tr { border-bottom: 1px solid #f8fafc; transition: background 0.12s; }
.ceo-dash .ceo-data-table tbody tr:nth-child(even) { background: #fafcff; }
.ceo-dash .ceo-data-table tbody tr:last-child { border-bottom: none; }
.ceo-dash .ceo-data-table tbody tr:hover { background: #f0f4ff; }
.ceo-dash .ceo-data-table tbody td { padding: 11px 16px; font-size: 13px; color: var(--text-secondary); white-space: nowrap; }
.ceo-dash .ceo-data-table a { color: var(--accent-blue); text-decoration: none; font-family: 'DM Mono', monospace; font-size: 12px; font-weight: 500; }
.ceo-dash .ceo-data-table a:hover { text-decoration: underline; }

/* ── Pagination ── */
.ceo-pagination { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 10px 16px; border-top: 1px solid #f1f5f9; }
.ceo-page-btn { display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; border: 1.5px solid var(--border); border-radius: 6px; background: #fff; cursor: pointer; transition: all 0.15s; padding: 0; }
.ceo-page-btn:hover:not([disabled]) { border-color: var(--accent-gold); color: var(--accent-gold); }
.ceo-page-btn[disabled] { opacity: 0.35; cursor: not-allowed; }
.ceo-page-btn svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
.ceo-page-info { font-size: 11px; font-weight: 600; color: var(--text-muted); font-family: 'DM Mono', monospace; min-width: 80px; text-align: center; }

/* ── Loading ── */
.ceo-loading { text-align: center; padding: 50px; }
.ceo-spinner { display: inline-block; width: 24px; height: 24px; border: 2px solid #e2e8f0; border-top-color: var(--accent-gold); border-radius: 50%; animation: cdSpin 0.7s linear infinite; }

/* ── NAV CARDS ── */
.ceo-dash .card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px,1fr)); gap: 14px; margin-bottom: 32px; }
.ceo-dash .card-grid.featured { grid-template-columns: repeat(auto-fill, minmax(320px,1fr)); gap: 16px; margin-bottom: 36px; }
.ceo-dash .dash-card { position: relative; background: #fff; border: 1px solid var(--border); border-radius: var(--radius); padding: 24px 22px; cursor: pointer; transition: all 0.25s ease; overflow: hidden; text-decoration: none; display: flex; flex-direction: column; gap: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.ceo-dash .dash-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--card-accent); opacity: 0; transition: opacity 0.25s ease; }
.ceo-dash .dash-card:hover { border-color: var(--border-hover); transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.08); }
.ceo-dash .dash-card:hover::before { opacity: 1; }
.ceo-dash .dash-card:hover .card-icon { transform: scale(1.05); }
.ceo-dash .dash-card:hover .card-arrow { opacity: 1; transform: translateX(0); }
.ceo-dash .card-top { display: flex; align-items: flex-start; justify-content: space-between; }
.ceo-dash .card-icon { width: 44px; height: 44px; border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; background: var(--card-accent-dim); transition: transform 0.25s ease; }
.ceo-dash .card-icon svg { width: 20px; height: 20px; stroke: var(--card-accent); fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.ceo-dash .card-arrow { width: 28px; height: 28px; border-radius: 6px; display: flex; align-items: center; justify-content: center; opacity: 0; transform: translateX(-4px); transition: all 0.25s ease; }
.ceo-dash .card-arrow svg { width: 14px; height: 14px; stroke: var(--text-muted); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.ceo-dash .card-body h3 { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; line-height: 1.3; }
.ceo-dash .card-body p { font-size: 12.5px; color: var(--text-secondary); line-height: 1.5; }
.ceo-dash .card-tag { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; color: var(--card-accent); opacity: 0.7; margin-top: auto; }
.ceo-dash .card-tag::before { content: ''; width: 4px; height: 4px; border-radius: 50%; background: var(--card-accent); opacity: 0.5; }
.ceo-dash .dash-card.featured-card { padding: 28px 26px; }
.ceo-dash .dash-card.featured-card .card-icon { width: 48px; height: 48px; }
.ceo-dash .dash-card.featured-card .card-icon svg { width: 22px; height: 22px; }
.ceo-dash .dash-card.featured-card .card-body h3 { font-size: 17px; }

/* ── Animations ── */
@keyframes cdShimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
@keyframes cdSpin { to { transform: rotate(360deg); } }
@keyframes cdNumberPop { 0% { opacity: 0; transform: scale(0.7) translateY(8px); } 100% { opacity: 1; transform: scale(1) translateY(0); } }

/* ── Responsive ── */
@media (max-width: 1100px) {
  .ceo-dash .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .ceo-kpi-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 768px) {
  .ceo-dash { padding: 0 0 36px; }
  .ceo-dash .ceo-hero { border-radius: 0; padding: 24px 16px 0; }
  .ceo-dash .dash-header { flex-direction: column; }
  .ceo-dash .dash-header h1 { font-size: 24px; }
  .ceo-dash .card-grid, .ceo-dash .card-grid.featured { grid-template-columns: 1fr; }
  .ceo-dash .stat-grid { grid-template-columns: 1fr; }
  .ceo-dash .stat-number { font-size: 34px; }
  .ceo-period-bar { flex-direction: column; align-items: flex-start; }
}
@media (max-width: 640px) {
  .ceo-kpi-grid { grid-template-columns: 1fr; }
  .ceo-period-toggle { width: 100%; }
  .ceo-period-btn { flex: 1; text-align: center; }
}"""


def execute():
    frappe.db.set_value("Custom HTML Block", "CEO", {
        "html": NEW_HTML,
        "style": NEW_STYLE,
    })
    frappe.db.commit()
    print("CEO block HTML and CSS updated successfully.")
