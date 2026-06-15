frappe.pages["nikki-command-center"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Nikki's Financial Command Center",
		single_column: true,
	});

	wrapper.page = page;
	page._ncc_person = null;

	page.main.html(`
		<div class="ncc-wrap">

			<!-- Header -->
			<div class="ncc-header">
				<div class="ncc-title">NIKKI'S FINANCIAL COMMAND CENTER</div>
				<div class="ncc-entities">Motley Terpz &middot; TSBC Ranch &middot; Master Touch Manufacturing &middot; LA Canna</div>
				<div class="ncc-live-tag">&#9889; Live &mdash; all values update automatically from Cash Ledger &amp; Expense Ledger</div>
			</div>

			<!-- Person filter (Finance roles only) -->
			<div id="ncc-filter-bar" class="ncc-filter-bar" style="display:none;">
				<label style="font-weight:600;">View Person:</label>
				<select id="ncc-person-select" class="ncc-select">
					<option value="">All Persons</option>
				</select>
				<button id="ncc-refresh-btn" class="ncc-btn">&#8635; Refresh</button>
			</div>

			<!-- Summary Cards -->
			<div class="ncc-cards">
				<div class="ncc-card ncc-card-green">
					<div class="ncc-card-label">TOTAL CASH IN</div>
					<div class="ncc-card-value" id="ncc-cash-in">&mdash;</div>
					<div class="ncc-card-live">&#9650; Live</div>
				</div>
				<div class="ncc-card ncc-card-red">
					<div class="ncc-card-label">TOTAL CASH OUT</div>
					<div class="ncc-card-value" id="ncc-cash-out">&mdash;</div>
					<div class="ncc-card-live">&#9660; Live</div>
				</div>
				<div class="ncc-card ncc-card-navy">
					<div class="ncc-card-label">CASH IN HAND</div>
					<div class="ncc-card-value" id="ncc-cash-hand">&mdash;</div>
					<div class="ncc-card-live">&#9650; Live</div>
				</div>
				<div class="ncc-card ncc-card-orange">
					<div class="ncc-card-label">TOTAL EXPENSES</div>
					<div class="ncc-card-value" id="ncc-expenses">&mdash;</div>
					<div class="ncc-card-live">&#9660; Live</div>
				</div>
				<div class="ncc-card ncc-card-amber">
					<div class="ncc-card-label">REIMBURSED</div>
					<div class="ncc-card-value" id="ncc-reimbursed">&mdash;</div>
					<div class="ncc-card-live">&#9650; Live</div>
				</div>
				<div class="ncc-card ncc-card-purple">
					<div class="ncc-card-label">NET OWED TO NIKKI</div>
					<div class="ncc-card-value" id="ncc-net-owed">&mdash;</div>
					<div class="ncc-card-live">&#9650; Live</div>
				</div>
				<div class="ncc-card ncc-card-teal">
					<div class="ncc-card-label">TOTAL TXN</div>
					<div class="ncc-card-value" id="ncc-txn-count">&mdash;</div>
					<div class="ncc-card-live">&mdash; Count</div>
				</div>
			</div>

			<!-- Monthly Summary -->
			<div class="ncc-section">
				<div class="ncc-section-hdr">&#128197; MONTHLY SUMMARY &mdash; auto-updates from both ledgers</div>
				<table class="ncc-table">
					<thead>
						<tr>
							<th>Month</th>
							<th class="ncc-num">Cash In</th>
							<th class="ncc-num">Cash Out</th>
							<th class="ncc-num">Net Cash</th>
							<th class="ncc-num">Expenses</th>
							<th class="ncc-num">Reimbursed</th>
							<th class="ncc-num">Net Owed</th>
							<th class="ncc-num"># Txns</th>
						</tr>
					</thead>
					<tbody id="ncc-monthly-body">
						<tr><td colspan="8" class="ncc-empty">Loading&hellip;</td></tr>
					</tbody>
					<tfoot id="ncc-monthly-foot"></tfoot>
				</table>
			</div>

			<!-- Entity Breakdown -->
			<div class="ncc-section">
				<div class="ncc-section-hdr ncc-section-hdr-purple">&#127970; ENTITY BREAKDOWN</div>
				<table class="ncc-table">
					<thead>
						<tr>
							<th>Entity</th>
							<th class="ncc-num">Cash In</th>
							<th class="ncc-num">Cash Out</th>
							<th class="ncc-num">Net Cash</th>
							<th class="ncc-num">Expenses</th>
							<th class="ncc-num">Reimbursed</th>
							<th class="ncc-num">Net Owed</th>
						</tr>
					</thead>
					<tbody id="ncc-entity-body">
						<tr><td colspan="7" class="ncc-empty">Loading&hellip;</td></tr>
					</tbody>
					<tfoot id="ncc-entity-foot"></tfoot>
				</table>
			</div>

		</div>
	`);

	// Person filter change
	page.main.find("#ncc-person-select").on("change", function () {
		var val = $(this).val();
		page._ncc_person = val || null;
		load_data(page._ncc_person);
	});
	page.main.find("#ncc-refresh-btn").on("click", function () {
		load_data(page._ncc_person);
	});

	// Real-time refresh when a CLE or ETE is submitted
	frappe.realtime.on("list_update", function (data) {
		if (data && (data.doctype === "Cash Ledger Entry" || data.doctype === "Expense Tracker Entry" || data.doctype === "Nikki Cash Ledger Entry")) {
			load_data(page._ncc_person);
		}
	});

	load_data(null);

	function load_data(person) {
		frappe.call({
			method: "cannabis_management.api.nikki_cash_dashboard.get_full_dashboard_data",
			args: { person: person || "" },
			callback: function (r) {
				if (r.message) render(r.message);
			},
		});
	}

	function render(data) {
		var s = data.summary;

		// Summary cards
		page.main.find("#ncc-cash-in").text(fmt(s.total_cash_in));
		page.main.find("#ncc-cash-out").text(fmt(s.total_cash_out));
		page.main.find("#ncc-cash-hand").text(fmt(s.cash_in_hand));
		page.main.find("#ncc-expenses").text(fmt(s.total_expenses));
		page.main.find("#ncc-reimbursed").text(fmt(s.reimbursed));
		page.main.find("#ncc-net-owed").text(fmt(s.net_owed));
		page.main.find("#ncc-txn-count").text((s.txn_count || 0).toLocaleString());

		// Finance person filter
		if (data.is_finance && data.persons && data.persons.length) {
			var sel = page.main.find("#ncc-person-select");
			sel.find("option:not(:first)").remove();
			data.persons.forEach(function (p) {
				sel.append('<option value="' + p.name + '">' + (p.full_name || p.name) + "</option>");
			});
			if (data.current_person) sel.val(data.current_person);
			page.main.find("#ncc-filter-bar").show();
		}

		// Monthly table
		var mbody = page.main.find("#ncc-monthly-body");
		var mfoot = page.main.find("#ncc-monthly-foot");
		mbody.empty();
		mfoot.empty();

		if (!data.monthly || !data.monthly.length) {
			mbody.html('<tr><td colspan="8" class="ncc-empty">No entries yet.</td></tr>');
		} else {
			var t = { ci: 0, co: 0, nc: 0, ep: 0, rb: 0, no: 0, tx: 0 };
			data.monthly.forEach(function (row) {
				var ncCls = row.net_cash >= 0 ? "ncc-pos" : "ncc-neg";
				var noCls = row.net_owed > 0 ? "ncc-col-owed" : (row.net_owed < 0 ? "ncc-pos" : "");
				mbody.append(
					"<tr>" +
					"<td class='ncc-month'>" + row.month + "</td>" +
					"<td class='ncc-num ncc-col-in'>" + fmt(row.cash_in) + "</td>" +
					"<td class='ncc-num ncc-col-out'>" + fmt(row.cash_out) + "</td>" +
					"<td class='ncc-num " + ncCls + "'>" + fmt(row.net_cash) + "</td>" +
					"<td class='ncc-num ncc-col-exp'>" + fmt(row.expenses) + "</td>" +
					"<td class='ncc-num ncc-col-reimb'>" + fmt(row.reimbursed) + "</td>" +
					"<td class='ncc-num " + noCls + "'>" + fmt(row.net_owed) + "</td>" +
					"<td class='ncc-num ncc-col-count'>" + (row.txn_count || 0) + "</td>" +
					"</tr>"
				);
				t.ci += row.cash_in; t.co += row.cash_out; t.nc += row.net_cash;
				t.ep += row.expenses; t.rb += row.reimbursed; t.no += row.net_owed;
				t.tx += (row.txn_count || 0);
			});
			mfoot.html(
				"<tr>" +
				"<td><b>TOTAL</b></td>" +
				"<td class='ncc-num ncc-col-in'><b>" + fmt(t.ci) + "</b></td>" +
				"<td class='ncc-num ncc-col-out'><b>" + fmt(t.co) + "</b></td>" +
				"<td class='ncc-num'><b>" + fmt(t.nc) + "</b></td>" +
				"<td class='ncc-num ncc-col-exp'><b>" + fmt(t.ep) + "</b></td>" +
				"<td class='ncc-num ncc-col-reimb'><b>" + fmt(t.rb) + "</b></td>" +
				"<td class='ncc-num ncc-col-owed'><b>" + fmt(t.no) + "</b></td>" +
				"<td class='ncc-num ncc-col-count'><b>" + t.tx + "</b></td>" +
				"</tr>"
			);
		}

		// Entity table
		var ebody = page.main.find("#ncc-entity-body");
		var efoot = page.main.find("#ncc-entity-foot");
		ebody.empty();
		efoot.empty();

		if (!data.entities || !data.entities.length) {
			ebody.html('<tr><td colspan="7" class="ncc-empty">No entries yet.</td></tr>');
		} else {
			var e = { ci: 0, co: 0, nc: 0, ep: 0, rb: 0, no: 0 };
			data.entities.forEach(function (row) {
				ebody.append(
					"<tr>" +
					"<td class='ncc-entity'>" + (row.entity || "Unknown") + "</td>" +
					"<td class='ncc-num ncc-col-in'>" + fmt(row.cash_in) + "</td>" +
					"<td class='ncc-num ncc-col-out'>" + fmt(row.cash_out) + "</td>" +
					"<td class='ncc-num'>" + fmt(row.net_cash) + "</td>" +
					"<td class='ncc-num ncc-col-exp'>" + fmt(row.expenses) + "</td>" +
					"<td class='ncc-num ncc-col-reimb'>" + fmt(row.reimbursed) + "</td>" +
					"<td class='ncc-num ncc-col-owed'>" + fmt(row.net_owed) + "</td>" +
					"</tr>"
				);
				e.ci += row.cash_in; e.co += row.cash_out; e.nc += row.net_cash;
				e.ep += row.expenses; e.rb += row.reimbursed; e.no += row.net_owed;
			});
			efoot.html(
				"<tr>" +
				"<td><b>TOTAL</b></td>" +
				"<td class='ncc-num ncc-col-in'><b>" + fmt(e.ci) + "</b></td>" +
				"<td class='ncc-num ncc-col-out'><b>" + fmt(e.co) + "</b></td>" +
				"<td class='ncc-num'><b>" + fmt(e.nc) + "</b></td>" +
				"<td class='ncc-num ncc-col-exp'><b>" + fmt(e.ep) + "</b></td>" +
				"<td class='ncc-num ncc-col-reimb'><b>" + fmt(e.rb) + "</b></td>" +
				"<td class='ncc-num ncc-col-owed'><b>" + fmt(e.no) + "</b></td>" +
				"</tr>"
			);
		}
	}

	function fmt(val) {
		if (val === null || val === undefined) return "$0";
		var n = parseFloat(val);
		var neg = n < 0;
		var abs = Math.abs(n).toLocaleString("en-US", {
			minimumFractionDigits: 0,
			maximumFractionDigits: 0,
		});
		return neg ? "($" + abs + ")" : "$" + abs;
	}
};
