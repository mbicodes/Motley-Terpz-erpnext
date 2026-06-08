frappe.pages["cash-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Cash Command Center",
		single_column: true,
	});

	wrapper.page = page;
	page._cd_person = null;

	page.main.html(`
		<div class="cd-wrap">

			<!-- Header -->
			<div class="cd-header">
				<div>
					<h1 class="cd-title">💵 Cash Command Center</h1>
					<p class="cd-subtitle">Motley Terpz &middot; TSBC Ranch &middot; Master Touch Manufacturing &middot; LA Canna</p>
					<p class="cd-live-tag">⚡ Live — values update from Cash Ledger &amp; Expense Ledger</p>
				</div>
				<div class="cd-filter-bar" id="cd-filter-bar" style="display:none;">
					<label class="cd-label">View Person</label>
					<select id="cd-person-select" class="cd-select">
						<option value="">All Persons</option>
					</select>
					<button id="cd-refresh-btn" class="cd-btn-primary">Refresh</button>
				</div>
			</div>

			<!-- Hero + Pending row -->
			<div class="cd-hero-row">
				<div class="cd-hero-card">
					<div class="cd-hero-label" id="cd-hero-label">Cash on Hand</div>
					<div class="cd-hero-value" id="cd-hero-value">—</div>
					<div class="cd-hero-sub">Total Cash In minus Total Cash Out</div>
				</div>
				<div class="cd-pending-card">
					<div class="cd-pending-label">Transactions Needing Approval</div>
					<div class="cd-pending-value" id="cd-pending-value">—</div>
					<div class="cd-pending-sub">Submitted entries with Pending status</div>
				</div>
			</div>

			<!-- Summary Cards -->
			<div class="cd-cards">
				<div class="cd-card cd-card-green">
					<div class="cd-card-label">TOTAL CASH IN</div>
					<div class="cd-card-value" id="cd-total-in">—</div>
					<div class="cd-card-live">▲ Live</div>
				</div>
				<div class="cd-card cd-card-red">
					<div class="cd-card-label">TOTAL CASH OUT</div>
					<div class="cd-card-value" id="cd-total-out">—</div>
					<div class="cd-card-live">▼ Live</div>
				</div>
				<div class="cd-card cd-card-purple">
					<div class="cd-card-label">TOTAL EXPENSES</div>
					<div class="cd-card-value" id="cd-expenses">—</div>
					<div class="cd-card-live">▲ Live</div>
				</div>
				<div class="cd-card cd-card-teal">
					<div class="cd-card-label">REIMBURSED</div>
					<div class="cd-card-value" id="cd-reimbursed">—</div>
					<div class="cd-card-live">▼ Live</div>
				</div>
				<div class="cd-card cd-card-orange">
					<div class="cd-card-label">NET OWED</div>
					<div class="cd-card-value" id="cd-net-owed">—</div>
					<div class="cd-card-live">▲ Live</div>
				</div>
				<div class="cd-card cd-card-dark">
					<div class="cd-card-label">TOTAL TXN COUNT</div>
					<div class="cd-card-value" id="cd-txn-count">—</div>
					<div class="cd-card-live">▼ Live</div>
				</div>
			</div>

			<!-- Transaction List -->
			<div class="cd-section">
				<div class="cd-section-header cd-section-header-blue">
					<span>📋 LIST OF TRANSACTIONS</span>
					<span class="cd-section-note" id="cd-txn-note"></span>
				</div>
				<div class="cd-table-wrap">
					<table class="cd-table">
						<thead>
							<tr>
								<th>Transaction Date</th>
								<th class="cd-num cd-col-in">Money In</th>
								<th class="cd-num cd-col-out">Money Out</th>
								<th>Business</th>
								<th>Type</th>
								<th>Receipt</th>
								<th>Transaction Notes</th>
								<th>Status</th>
							</tr>
						</thead>
						<tbody id="cd-txn-body">
							<tr><td colspan="8" class="cd-empty">Loading...</td></tr>
						</tbody>
					</table>
				</div>
			</div>

			<!-- Monthly Summary -->
			<div class="cd-section">
				<div class="cd-section-header">
					<span>📅 MONTHLY SUMMARY</span>
				</div>
				<div class="cd-table-wrap">
					<table class="cd-table">
						<thead>
							<tr>
								<th>Month</th>
								<th class="cd-num cd-col-in">Cash In</th>
								<th class="cd-num cd-col-out">Cash Out</th>
								<th class="cd-num cd-col-net">Net Cash</th>
								<th class="cd-num cd-col-exp">Expenses</th>
								<th class="cd-num cd-col-reimb">Reimbursed</th>
								<th class="cd-num cd-col-owed">Net Owed</th>
								<th class="cd-num"># Txns</th>
							</tr>
						</thead>
						<tbody id="cd-monthly-body">
							<tr><td colspan="8" class="cd-empty">Loading...</td></tr>
						</tbody>
						<tfoot id="cd-monthly-foot"></tfoot>
					</table>
				</div>
			</div>

			<!-- Entity Breakdown -->
			<div class="cd-section">
				<div class="cd-section-header cd-section-header-purple">
					<span>🏢 ENTITY BREAKDOWN</span>
				</div>
				<div class="cd-table-wrap">
					<table class="cd-table">
						<thead>
							<tr>
								<th>Entity</th>
								<th class="cd-num cd-col-in">Cash In</th>
								<th class="cd-num cd-col-out">Cash Out</th>
								<th class="cd-num cd-col-net">Net Cash</th>
								<th class="cd-num cd-col-exp">Expenses</th>
								<th class="cd-num cd-col-reimb">Reimbursed</th>
								<th class="cd-num cd-col-owed">Net Owed</th>
							</tr>
						</thead>
						<tbody id="cd-entity-body">
							<tr><td colspan="7" class="cd-empty">Loading...</td></tr>
						</tbody>
						<tfoot id="cd-entity-foot"></tfoot>
					</table>
				</div>
			</div>

			<!-- Quick Links -->
			<div class="cd-quick-links">
				<a class="cd-qlink cd-qlink-purple" href="/app/expense-tracker-entry/new-expense-tracker-entry-1">+ New Expense</a>
				<a class="cd-qlink cd-qlink-blue" href="/app/cash-ledger-entry">All Cash Entries</a>
				<a class="cd-qlink cd-qlink-dark" href="/app/expense-tracker-entry">All Expenses</a>
			</div>

		</div>
	`);

	// Real-time balance update
	frappe.realtime.on("cash_balance_update", function () {
		load_data(page._cd_person);
	});

	load_data(null);

	page.main.find("#cd-refresh-btn").on("click", function () {
		var sel = page.main.find("#cd-person-select").val();
		load_data(sel || null);
	});

	function load_data(person) {
		page._cd_person = person;
		frappe.call({
			method: "cannabis_management.cannabis_management.page.cash_dashboard.cash_dashboard.get_dashboard_data",
			args: { person: person || "" },
			callback: function (r) {
				if (!r.message) return;
				render(r.message);
			},
		});
	}

	function render(data) {
		var s = data.summary;

		// Hero card
		var heroLabel = s.display_name
			? s.display_name + " — Cash on Hand"
			: "Total Cash on Hand";
		page.main.find("#cd-hero-label").text(heroLabel);
		page.main.find("#cd-hero-value").text(fmt(s.cash_in_hand));
		page.main.find("#cd-hero-value").toggleClass("cd-hero-negative", s.cash_in_hand < 0);

		// Pending approvals
		page.main.find("#cd-pending-value").text(
			(s.pending_approvals || 0).toLocaleString()
		);

		// Summary cards
		page.main.find("#cd-total-in").text(fmt(s.total_cash_in));
		page.main.find("#cd-total-out").text(fmt(s.total_cash_out));
		page.main.find("#cd-expenses").text(fmt(s.total_expenses));
		page.main.find("#cd-reimbursed").text(fmt(s.reimbursed));
		page.main.find("#cd-net-owed").text(fmt(s.net_owed));
		page.main.find("#cd-txn-count").text((s.total_txns || 0).toLocaleString());

		// Finance person filter
		if (data.is_finance && data.persons && data.persons.length) {
			var sel = page.main.find("#cd-person-select");
			sel.find("option:not(:first)").remove();
			data.persons.forEach(function (p) {
				sel.append('<option value="' + p.name + '">' + (p.full_name || p.name) + "</option>");
			});
			if (data.current_person) sel.val(data.current_person);
			page.main.find("#cd-filter-bar").show();
		}

		// Transaction list
		var tbody = page.main.find("#cd-txn-body");
		tbody.empty();
		page.main.find("#cd-txn-note").text(
			data.transactions && data.transactions.length
				? "showing " + data.transactions.length + " most recent"
				: ""
		);

		if (!data.transactions || !data.transactions.length) {
			tbody.html('<tr><td colspan="8" class="cd-empty">No transactions yet.</td></tr>');
		} else {
			data.transactions.forEach(function (row) {
				var statusClass = row.approval_status === "Approved"
					? "cd-badge-approved"
					: row.approval_status === "Rejected"
					? "cd-badge-rejected"
					: "cd-badge-pending";

				var receiptHtml = row.receipt
					? '<a href="' + row.receipt + '" target="_blank" class="cd-receipt-link">📎 View</a>'
					: '<span class="cd-muted">—</span>';

				var entityHtml = row.entity
					? '<span class="cd-entity-badge">' + row.entity + "</span>"
					: '<span class="cd-muted">—</span>';

				tbody.append(
					"<tr>" +
					"<td class='cd-date-cell'>" + row.date + "</td>" +
					"<td class='cd-num cd-col-in'>" + (row.money_in > 0 ? fmt(row.money_in) : '<span class="cd-muted">—</span>') + "</td>" +
					"<td class='cd-num cd-col-out'>" + (row.money_out > 0 ? fmt(row.money_out) : '<span class="cd-muted">—</span>') + "</td>" +
					"<td>" + entityHtml + "</td>" +
					"<td class='cd-type-cell'>" + (row.transaction_type || "") + "</td>" +
					"<td>" + receiptHtml + "</td>" +
					"<td class='cd-notes-cell'>" + (row.notes || "") + "</td>" +
					"<td><span class='cd-badge " + statusClass + "'>" + row.approval_status + "</span></td>" +
					"</tr>"
				);
			});
		}

		// Monthly table
		var mbody = page.main.find("#cd-monthly-body");
		var mfoot = page.main.find("#cd-monthly-foot");
		mbody.empty(); mfoot.empty();

		if (!data.monthly || !data.monthly.length) {
			mbody.html('<tr><td colspan="8" class="cd-empty">No entries yet.</td></tr>');
		} else {
			var tIn=0, tOut=0, tNet=0, tExp=0, tRe=0, tOw=0, tTx=0;
			data.monthly.forEach(function (row) {
				mbody.append(
					"<tr>" +
					"<td class='cd-month-cell'>" + row.month + "</td>" +
					"<td class='cd-num cd-col-in'>" + fmt(row.cash_in) + "</td>" +
					"<td class='cd-num cd-col-out'>" + fmt(row.cash_out) + "</td>" +
					"<td class='cd-num cd-col-net " + (row.net_cash >= 0 ? "cd-pos" : "cd-neg") + "'>" + fmt(row.net_cash) + "</td>" +
					"<td class='cd-num cd-col-exp'>" + fmt(row.expenses) + "</td>" +
					"<td class='cd-num cd-col-reimb'>" + fmt(row.reimbursed) + "</td>" +
					"<td class='cd-num cd-col-owed " + (row.net_owed <= 0 ? "cd-pos" : "cd-neg") + "'>" + fmt(row.net_owed) + "</td>" +
					"<td class='cd-num'>" + row.txn_count + "</td>" +
					"</tr>"
				);
				tIn+=row.cash_in; tOut+=row.cash_out; tNet+=row.net_cash;
				tExp+=row.expenses; tRe+=row.reimbursed; tOw+=row.net_owed; tTx+=row.txn_count;
			});
			mfoot.html(
				"<tr class='cd-total-row'><td><b>TOTAL</b></td>" +
				"<td class='cd-num'>" + fmt(tIn) + "</td>" +
				"<td class='cd-num'>" + fmt(tOut) + "</td>" +
				"<td class='cd-num'>" + fmt(tNet) + "</td>" +
				"<td class='cd-num'>" + fmt(tExp) + "</td>" +
				"<td class='cd-num'>" + fmt(tRe) + "</td>" +
				"<td class='cd-num'>" + fmt(tOw) + "</td>" +
				"<td class='cd-num'>" + tTx + "</td></tr>"
			);
		}

		// Entity table
		var ebody = page.main.find("#cd-entity-body");
		var efoot = page.main.find("#cd-entity-foot");
		ebody.empty(); efoot.empty();

		if (!data.entities || !data.entities.length) {
			ebody.html('<tr><td colspan="7" class="cd-empty">No entries yet.</td></tr>');
		} else {
			var eIn=0, eOut=0, eNet=0, eExp=0, eRe=0, eOw=0;
			data.entities.forEach(function (row) {
				ebody.append(
					"<tr>" +
					"<td class='cd-entity-cell'>" + row.entity + "</td>" +
					"<td class='cd-num cd-col-in'>" + fmt(row.cash_in) + "</td>" +
					"<td class='cd-num cd-col-out'>" + fmt(row.cash_out) + "</td>" +
					"<td class='cd-num cd-col-net'>" + fmt(row.net_cash) + "</td>" +
					"<td class='cd-num cd-col-exp'>" + fmt(row.expenses) + "</td>" +
					"<td class='cd-num cd-col-reimb'>" + fmt(row.reimbursed) + "</td>" +
					"<td class='cd-num cd-col-owed'>" + fmt(row.net_owed) + "</td>" +
					"</tr>"
				);
				eIn+=row.cash_in; eOut+=row.cash_out; eNet+=row.net_cash;
				eExp+=row.expenses; eRe+=row.reimbursed; eOw+=row.net_owed;
			});
			efoot.html(
				"<tr class='cd-total-row'><td><b>TOTAL</b></td>" +
				"<td class='cd-num'>" + fmt(eIn) + "</td>" +
				"<td class='cd-num'>" + fmt(eOut) + "</td>" +
				"<td class='cd-num'>" + fmt(eNet) + "</td>" +
				"<td class='cd-num'>" + fmt(eExp) + "</td>" +
				"<td class='cd-num'>" + fmt(eRe) + "</td>" +
				"<td class='cd-num'>" + fmt(eOw) + "</td></tr>"
			);
		}
	}

	function fmt(val) {
		if (val === null || val === undefined) return "$0";
		var n = parseFloat(val);
		var neg = n < 0;
		var str = "$" + Math.abs(n).toLocaleString("en-US", {
			minimumFractionDigits: 0,
			maximumFractionDigits: 0
		});
		return neg ? "-" + str : str;
	}
};
