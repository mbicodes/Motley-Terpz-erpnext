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
					<p class="cd-subtitle">Nikki's submitted cash entries — aggregated by entity and month</p>
					<p class="cd-live-tag">⚡ Live — values update from Nikki Cash Ledger</p>
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
					<div class="cd-hero-label" id="cd-hero-label">Net Cash</div>
					<div class="cd-hero-value" id="cd-hero-value">—</div>
					<div class="cd-hero-sub">Total Cash In minus Total Cash Out</div>
				</div>
				<div class="cd-pending-card">
					<div class="cd-pending-label">Entries Awaiting Review</div>
					<div class="cd-pending-value" id="cd-pending-value">—</div>
					<div class="cd-pending-sub">Open entries not yet reviewed</div>
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
				<div class="cd-card cd-card-dark">
					<div class="cd-card-label">TOTAL ENTRIES</div>
					<div class="cd-card-value" id="cd-txn-count">—</div>
					<div class="cd-card-live">— Count</div>
				</div>
			</div>

			<!-- Transaction List -->
			<div class="cd-section">
				<div class="cd-section-header cd-section-header-blue">
					<span>📋 SUBMITTED ENTRIES</span>
					<span class="cd-section-note" id="cd-txn-note"></span>
				</div>
				<div class="cd-table-wrap">
					<table class="cd-table">
						<thead>
							<tr>
								<th>Date</th>
								<th>Entity</th>
								<th>Direction</th>
								<th class="cd-num">Amount</th>
								<th>Type</th>
								<th>Invoice #</th>
								<th>Notes</th>
								<th>Receipt</th>
								<th>Status</th>
							</tr>
						</thead>
						<tbody id="cd-txn-body">
							<tr><td colspan="9" class="cd-empty">Loading...</td></tr>
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
								<th class="cd-num"># Entries</th>
							</tr>
						</thead>
						<tbody id="cd-monthly-body">
							<tr><td colspan="5" class="cd-empty">Loading...</td></tr>
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
							</tr>
						</thead>
						<tbody id="cd-entity-body">
							<tr><td colspan="4" class="cd-empty">Loading...</td></tr>
						</tbody>
						<tfoot id="cd-entity-foot"></tfoot>
					</table>
				</div>
			</div>

		</div>
	`);

	// Real-time update when Nikki submits a new entry
	frappe.realtime.on("list_update", function (data) {
		if (data && data.doctype === "Nikki Cash Ledger Entry") {
			load_data(page._cd_person);
		}
	});

	load_data(null);

	page.main.find("#cd-refresh-btn").on("click", function () {
		var sel = page.main.find("#cd-person-select").val();
		load_data(sel || null);
	});

	function load_data(person) {
		page._cd_person = person;
		frappe.call({
			method: "cannabis_management.api.nikki_cash_dashboard.get_dashboard_data",
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
		var heroLabel = s.display_name ? s.display_name + " — Net Cash" : "Net Cash";
		page.main.find("#cd-hero-label").text(heroLabel);
		page.main.find("#cd-hero-value").text(fmt(s.cash_in_hand));
		page.main.find("#cd-hero-value").toggleClass("cd-hero-negative", s.cash_in_hand < 0);

		// Pending
		page.main.find("#cd-pending-value").text((s.pending_approvals || 0).toLocaleString());

		// Summary cards
		page.main.find("#cd-total-in").text(fmt(s.total_cash_in));
		page.main.find("#cd-total-out").text(fmt(s.total_cash_out));
		page.main.find("#cd-txn-count").text((s.total_txns || 0).toLocaleString());

		// Finance filter
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
			tbody.html('<tr><td colspan="9" class="cd-empty">No entries yet.</td></tr>');
		} else {
			data.transactions.forEach(function (row) {
				var statusMap = {
					"Open":      "<span class='cd-badge cd-badge-pending'>Open</span>",
					"Reviewed":  "<span class='cd-badge cd-badge-info'>Reviewed</span>",
					"Completed": "<span class='cd-badge cd-badge-approved'>Completed</span>"
				};
				var statusHtml = statusMap[row.approval_status]
					|| "<span class='cd-badge cd-badge-pending'>" + (row.approval_status || "Open") + "</span>";

				var receiptHtml = row.receipt
					? '<a href="' + row.receipt + '" target="_blank" class="cd-receipt-link">📎 View</a>'
					: '<span class="cd-muted">—</span>';

				var entityHtml = row.entity
					? '<span class="cd-entity-badge">' + row.entity + "</span>"
					: '<span class="cd-muted">—</span>';

				var isIn = row.direction === "Cash In";
				var amtColor = isIn ? "cd-col-in" : "cd-col-out";
				var amtPrefix = isIn ? "▲ " : "▼ ";

				tbody.append(
					"<tr>" +
					"<td class='cd-date-cell'>" + row.date + "</td>" +
					"<td>" + entityHtml + "</td>" +
					"<td class='cd-type-cell'>" + (row.direction || "") + "</td>" +
					"<td class='cd-num " + amtColor + "'>" + amtPrefix + fmt(row.amount) + "</td>" +
					"<td class='cd-type-cell'>" + (row.transaction_type || "") + "</td>" +
					"<td class='cd-type-cell'>" + (row.invoice_number || '<span class="cd-muted">—</span>') + "</td>" +
					"<td class='cd-notes-cell'>" + (row.notes || "") + "</td>" +
					"<td>" + receiptHtml + "</td>" +
					"<td>" + statusHtml + "</td>" +
					"</tr>"
				);
			});
		}

		// Monthly table
		var mbody = page.main.find("#cd-monthly-body");
		var mfoot = page.main.find("#cd-monthly-foot");
		mbody.empty(); mfoot.empty();

		if (!data.monthly || !data.monthly.length) {
			mbody.html('<tr><td colspan="5" class="cd-empty">No entries yet.</td></tr>');
		} else {
			var tIn = 0, tOut = 0, tNet = 0, tTx = 0;
			data.monthly.forEach(function (row) {
				mbody.append(
					"<tr>" +
					"<td class='cd-month-cell'>" + row.month + "</td>" +
					"<td class='cd-num cd-col-in'>" + fmt(row.cash_in) + "</td>" +
					"<td class='cd-num cd-col-out'>" + fmt(row.cash_out) + "</td>" +
					"<td class='cd-num cd-col-net " + (row.net_cash >= 0 ? "cd-pos" : "cd-neg") + "'>" + fmt(row.net_cash) + "</td>" +
					"<td class='cd-num'>" + row.txn_count + "</td>" +
					"</tr>"
				);
				tIn += row.cash_in; tOut += row.cash_out; tNet += row.net_cash; tTx += row.txn_count;
			});
			mfoot.html(
				"<tr class='cd-total-row'><td><b>TOTAL</b></td>" +
				"<td class='cd-num'>" + fmt(tIn) + "</td>" +
				"<td class='cd-num'>" + fmt(tOut) + "</td>" +
				"<td class='cd-num'>" + fmt(tNet) + "</td>" +
				"<td class='cd-num'>" + tTx + "</td></tr>"
			);
		}

		// Entity table
		var ebody = page.main.find("#cd-entity-body");
		var efoot = page.main.find("#cd-entity-foot");
		ebody.empty(); efoot.empty();

		if (!data.entities || !data.entities.length) {
			ebody.html('<tr><td colspan="4" class="cd-empty">No entries yet.</td></tr>');
		} else {
			var eIn = 0, eOut = 0, eNet = 0;
			data.entities.forEach(function (row) {
				ebody.append(
					"<tr>" +
					"<td class='cd-entity-cell'>" + row.entity + "</td>" +
					"<td class='cd-num cd-col-in'>" + fmt(row.cash_in) + "</td>" +
					"<td class='cd-num cd-col-out'>" + fmt(row.cash_out) + "</td>" +
					"<td class='cd-num cd-col-net'>" + fmt(row.net_cash) + "</td>" +
					"</tr>"
				);
				eIn += row.cash_in; eOut += row.cash_out; eNet += row.net_cash;
			});
			efoot.html(
				"<tr class='cd-total-row'><td><b>TOTAL</b></td>" +
				"<td class='cd-num'>" + fmt(eIn) + "</td>" +
				"<td class='cd-num'>" + fmt(eOut) + "</td>" +
				"<td class='cd-num'>" + fmt(eNet) + "</td></tr>"
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
