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
					<p class="cd-subtitle">Motley Terpz · TSBC Ranch · Master Touch Manufacturing · LA Canna</p>
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

			<!-- Summary Cards -->
			<div class="cd-cards" id="cd-cards">
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
				<div class="cd-card cd-card-blue">
					<div class="cd-card-label">CASH IN HAND</div>
					<div class="cd-card-value" id="cd-cash-hand">—</div>
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

			<!-- Monthly Summary -->
			<div class="cd-section">
				<div class="cd-section-header">
					<span>📅 MONTHLY SUMMARY — auto-updates from both ledgers</span>
				</div>
				<div class="cd-table-wrap">
					<table class="cd-table" id="cd-monthly-table">
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
					<table class="cd-table" id="cd-entity-table">
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
				<a class="cd-qlink cd-qlink-green" href="/app/cash-ledger-entry/new-cash-ledger-entry-1">+ New Cash Entry</a>
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

		// Cards
		page.main.find("#cd-total-in").text(fmt(s.total_cash_in));
		page.main.find("#cd-total-out").text(fmt(s.total_cash_out));
		page.main.find("#cd-cash-hand").text(fmt(s.cash_in_hand));
		page.main.find("#cd-expenses").text(fmt(s.total_expenses));
		page.main.find("#cd-reimbursed").text(fmt(s.reimbursed));
		page.main.find("#cd-net-owed").text(fmt(s.net_owed));
		page.main.find("#cd-txn-count").text(s.total_txns.toLocaleString());

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

		// Monthly table
		var mbody = page.main.find("#cd-monthly-body");
		var mfoot = page.main.find("#cd-monthly-foot");
		mbody.empty();
		mfoot.empty();

		if (!data.monthly || !data.monthly.length) {
			mbody.html('<tr><td colspan="8" class="cd-empty">No entries yet.</td></tr>');
		} else {
			var totIn=0, totOut=0, totNet=0, totExp=0, totRe=0, totOwed=0, totTxn=0;
			data.monthly.forEach(function (row) {
				var netClass = row.net_cash >= 0 ? "cd-pos" : "cd-neg";
				var owedClass = row.net_owed >= 0 ? "cd-neg" : "cd-pos";
				mbody.append(
					"<tr>" +
					"<td class='cd-month-cell'>" + row.month + "</td>" +
					"<td class='cd-num cd-col-in'>" + fmt(row.cash_in) + "</td>" +
					"<td class='cd-num cd-col-out'>" + fmt(row.cash_out) + "</td>" +
					"<td class='cd-num cd-col-net " + netClass + "'>" + fmt(row.net_cash) + "</td>" +
					"<td class='cd-num cd-col-exp'>" + fmt(row.expenses) + "</td>" +
					"<td class='cd-num cd-col-reimb'>" + fmt(row.reimbursed) + "</td>" +
					"<td class='cd-num cd-col-owed " + owedClass + "'>" + fmt(row.net_owed) + "</td>" +
					"<td class='cd-num'>" + row.txn_count + "</td>" +
					"</tr>"
				);
				totIn += row.cash_in; totOut += row.cash_out;
				totNet += row.net_cash; totExp += row.expenses;
				totRe += row.reimbursed; totOwed += row.net_owed;
				totTxn += row.txn_count;
			});
			mfoot.html(
				"<tr class='cd-total-row'>" +
				"<td><b>TOTAL</b></td>" +
				"<td class='cd-num'>" + fmt(totIn) + "</td>" +
				"<td class='cd-num'>" + fmt(totOut) + "</td>" +
				"<td class='cd-num'>" + fmt(totNet) + "</td>" +
				"<td class='cd-num'>" + fmt(totExp) + "</td>" +
				"<td class='cd-num'>" + fmt(totRe) + "</td>" +
				"<td class='cd-num'>" + fmt(totOwed) + "</td>" +
				"<td class='cd-num'>" + totTxn + "</td>" +
				"</tr>"
			);
		}

		// Entity table
		var ebody = page.main.find("#cd-entity-body");
		var efoot = page.main.find("#cd-entity-foot");
		ebody.empty();
		efoot.empty();

		if (!data.entities || !data.entities.length) {
			ebody.html('<tr><td colspan="7" class="cd-empty">No entries yet.</td></tr>');
		} else {
			var eTotIn=0, eTotOut=0, eTotNet=0, eTotExp=0, eTotRe=0, eTotOwed=0;
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
				eTotIn += row.cash_in; eTotOut += row.cash_out;
				eTotNet += row.net_cash; eTotExp += row.expenses;
				eTotRe += row.reimbursed; eTotOwed += row.net_owed;
			});
			efoot.html(
				"<tr class='cd-total-row'>" +
				"<td><b>TOTAL</b></td>" +
				"<td class='cd-num'>" + fmt(eTotIn) + "</td>" +
				"<td class='cd-num'>" + fmt(eTotOut) + "</td>" +
				"<td class='cd-num'>" + fmt(eTotNet) + "</td>" +
				"<td class='cd-num'>" + fmt(eTotExp) + "</td>" +
				"<td class='cd-num'>" + fmt(eTotRe) + "</td>" +
				"<td class='cd-num'>" + fmt(eTotOwed) + "</td>" +
				"</tr>"
			);
		}
	}

	function fmt(val) {
		if (val === null || val === undefined) return "$0";
		var n = parseFloat(val);
		var neg = n < 0;
		var abs = Math.abs(n);
		var str = "$" + abs.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
		return neg ? "-" + str : str;
	}
};
