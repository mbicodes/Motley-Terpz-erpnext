frappe.pages["cash-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Financial Command Center",
		single_column: true,
	});

	wrapper.page = page;
	page._cd_person  = null;
	page._cd_persons = [];
	page._cd_data    = null;

	page.main.html(`
		<div class="fcc-wrap">
			<div class="fcc-header">
				<div class="fcc-header-left">
					<div class="fcc-title" id="fcc-title">Financial Command Center</div>
					<div class="fcc-subtitle">Motley Terpz &middot; TSBC Ranch &middot; Master Touch Manufacturing &middot; LA Canna</div>
					<div class="fcc-live-tag">&#9889; Live &mdash; values update automatically from Cash Ledger &amp; Expense Ledger</div>
				</div>
				<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
					<div id="fcc-filter-bar" style="display:none;align-items:center;gap:8px;">
						<label class="fcc-filter-label">View Person</label>
						<select id="fcc-person-select" class="fcc-select">
							<option value="">All Persons</option>
						</select>
					</div>
					<button id="fcc-export-btn" class="fcc-btn fcc-btn-outline">&#8595; Export All</button>
					<button id="fcc-refresh-btn" class="fcc-btn">&#8635; Refresh</button>
				</div>
			</div>

			<div class="fcc-cards">
				<div class="fcc-card" style="--accent:#27ae60;"><div class="fcc-card-icon">&#9650;</div><div class="fcc-card-body"><div class="fcc-card-label">TOTAL CASH IN</div><div class="fcc-card-value" id="fcc-cash-in">—</div></div><div class="fcc-card-tag">Live</div></div>
				<div class="fcc-card" style="--accent:#e53935;"><div class="fcc-card-icon">&#9660;</div><div class="fcc-card-body"><div class="fcc-card-label">TOTAL CASH OUT</div><div class="fcc-card-value" id="fcc-cash-out">—</div></div><div class="fcc-card-tag">Live</div></div>
				<div class="fcc-card" style="--accent:#1565c0;"><div class="fcc-card-icon">&#128181;</div><div class="fcc-card-body"><div class="fcc-card-label">CASH IN HAND</div><div class="fcc-card-value" id="fcc-cash-hand">—</div></div><div class="fcc-card-tag">Live</div></div>
				<div class="fcc-card" style="--accent:#e65100;"><div class="fcc-card-icon">&#128203;</div><div class="fcc-card-body"><div class="fcc-card-label">TOTAL EXPENSES</div><div class="fcc-card-value" id="fcc-expenses">—</div></div><div class="fcc-card-tag">Live</div></div>
				<div class="fcc-card" style="--accent:#f57c00;"><div class="fcc-card-icon">&#8617;</div><div class="fcc-card-body"><div class="fcc-card-label">REIMBURSED</div><div class="fcc-card-value" id="fcc-reimbursed">—</div></div><div class="fcc-card-tag">Live</div></div>
				<div class="fcc-card" style="--accent:#6a1b9a;"><div class="fcc-card-icon">&#128176;</div><div class="fcc-card-body"><div class="fcc-card-label" id="fcc-owed-label">NET OWED</div><div class="fcc-card-value" id="fcc-net-owed">—</div></div><div class="fcc-card-tag">Live</div></div>
				<div class="fcc-card" style="--accent:#00695c;"><div class="fcc-card-icon">&#35;</div><div class="fcc-card-body"><div class="fcc-card-label">TOTAL TXN</div><div class="fcc-card-value" id="fcc-txn-count">—</div></div><div class="fcc-card-tag">Count</div></div>
			</div>

			<!-- Submitted Cash Entries -->
			<div class="fcc-section">
				<div class="fcc-section-hdr" style="--hdr-accent:#1565c0;">
					<span>&#128196; Cash Entries</span>
					<div style="display:flex;align-items:center;gap:12px;">
						<span class="fcc-section-note" id="fcc-txn-note"></span>
						<button class="fcc-export-section-btn" id="fcc-export-cash">&#8595; CSV</button>
					</div>
				</div>
				<div class="fcc-table-wrap">
					<table class="fcc-table">
						<thead><tr><th>Date</th><th>Entity</th><th>Direction</th><th class="fcc-num">Amount</th><th>Type</th><th>Invoice #</th><th>Notes</th><th class="fcc-num">Running Bal.</th></tr></thead>
						<tbody id="fcc-txn-body"><tr><td colspan="8" class="fcc-empty">Loading&hellip;</td></tr></tbody>
					</table>
				</div>
			</div>

			<!-- Expense Entries -->
			<div class="fcc-section">
				<div class="fcc-section-hdr" style="--hdr-accent:#e65100;">
					<span>&#128203; Expense Entries</span>
					<div style="display:flex;align-items:center;gap:12px;">
						<span class="fcc-section-note" id="fcc-exp-note"></span>
						<button class="fcc-export-section-btn" id="fcc-export-expense">&#8595; CSV</button>
					</div>
				</div>
				<div class="fcc-table-wrap">
					<table class="fcc-table">
						<thead><tr><th>Date</th><th>Entity</th><th>Direction</th><th class="fcc-num">Amount</th><th>Type</th><th>Notes</th></tr></thead>
						<tbody id="fcc-exp-body"><tr><td colspan="6" class="fcc-empty">Loading&hellip;</td></tr></tbody>
					</table>
				</div>
			</div>

			<!-- Monthly Summary -->
			<div class="fcc-section">
				<div class="fcc-section-hdr" style="--hdr-accent:#2e7d32;">
					<span>&#128197; Monthly Summary</span>
					<button class="fcc-export-section-btn" id="fcc-export-monthly">&#8595; CSV</button>
				</div>
				<div class="fcc-table-wrap">
					<table class="fcc-table">
						<thead><tr><th>Month</th><th class="fcc-num">Cash In</th><th class="fcc-num">Cash Out</th><th class="fcc-num">Net Cash</th><th class="fcc-num">Expenses</th><th class="fcc-num">Reimbursed</th><th class="fcc-num">Net Owed</th><th class="fcc-num"># Txns</th></tr></thead>
						<tbody id="fcc-monthly-body"><tr><td colspan="8" class="fcc-empty">Loading&hellip;</td></tr></tbody>
						<tfoot id="fcc-monthly-foot"></tfoot>
					</table>
				</div>
			</div>

			<!-- Entity Breakdown -->
			<div class="fcc-section">
				<div class="fcc-section-hdr" style="--hdr-accent:#6a1b9a;">
					<span>&#127970; Entity Breakdown</span>
					<button class="fcc-export-section-btn" id="fcc-export-entity">&#8595; CSV</button>
				</div>
				<div class="fcc-table-wrap">
					<table class="fcc-table">
						<thead><tr><th>Entity</th><th class="fcc-num">Cash In</th><th class="fcc-num">Cash Out</th><th class="fcc-num">Net Cash</th><th class="fcc-num">Expenses</th><th class="fcc-num">Reimbursed</th><th class="fcc-num">Net Owed</th></tr></thead>
						<tbody id="fcc-entity-body"><tr><td colspan="7" class="fcc-empty">Loading&hellip;</td></tr></tbody>
						<tfoot id="fcc-entity-foot"></tfoot>
					</table>
				</div>
			</div>
		</div>
	`);

	page.main.find("#fcc-person-select").on("change", function () {
		page._cd_person = $(this).val() || null;
		load_data(page._cd_person);
	});
	page.main.find("#fcc-refresh-btn").on("click", function () { load_data(page._cd_person); });
	page.main.find("#fcc-export-btn").on("click", function () { if (page._cd_data) export_all(page._cd_data); });
	page.main.find("#fcc-export-cash").on("click", function () {
		if (!page._cd_data) return;
		export_csv(["Date","Entity","Direction","Amount","Type","Invoice #","Notes","Running Balance"],
			(page._cd_data.transactions||[]).map(function(r){return[r.date,r.entity,r.direction,r.amount,r.transaction_type,r.invoice_number,r.notes,r.running_balance];}),
			"cash_entries");
	});
	page.main.find("#fcc-export-expense").on("click", function () {
		if (!page._cd_data) return;
		export_csv(["Date","Entity","Direction","Amount","Type","Notes"],
			(page._cd_data.expense_entries||[]).map(function(r){return[r.date,r.entity,r.direction,r.amount,r.transaction_type,r.notes];}),
			"expense_entries");
	});
	page.main.find("#fcc-export-monthly").on("click", function () {
		if (!page._cd_data) return;
		export_csv(["Month","Cash In","Cash Out","Net Cash","Expenses","Reimbursed","Net Owed","# Txns"],
			(page._cd_data.monthly||[]).map(function(r){return[r.month,r.cash_in,r.cash_out,r.net_cash,r.expenses,r.reimbursed,r.net_owed,r.txn_count];}),
			"monthly_summary");
	});
	page.main.find("#fcc-export-entity").on("click", function () {
		if (!page._cd_data) return;
		export_csv(["Entity","Cash In","Cash Out","Net Cash","Expenses","Reimbursed","Net Owed"],
			(page._cd_data.entities||[]).map(function(r){return[r.entity,r.cash_in,r.cash_out,r.net_cash,r.expenses,r.reimbursed,r.net_owed];}),
			"entity_breakdown");
	});

	frappe.realtime.on("list_update", function (data) {
		if (data && (data.doctype === "Cash Ledger Entry" || data.doctype === "Expense Tracker Entry" || data.doctype === "Nikki Cash Ledger Entry")) {
			load_data(page._cd_person);
		}
	});

	load_data(null);

	function load_data(person) {
		frappe.call({
			method: "cannabis_management.api.nikki_cash_dashboard.get_full_dashboard_data",
			args: { person: person || "" },
			callback: function (r) { if (r.message) { page._cd_data = r.message; render(r.message); } },
		});
	}

	function render(data) {
		var s = data.summary;
		var person_name = "";
		if (data.current_person && page._cd_persons && page._cd_persons.length) {
			var match = page._cd_persons.filter(function(p){return p.name===data.current_person;});
			person_name = match.length ? (match[0].full_name||match[0].name) : data.current_person;
		}
		page.main.find("#fcc-title").text(person_name ? person_name+"'s Financial Command Center" : "Financial Command Center");
		page.main.find("#fcc-owed-label").text(person_name ? "NET OWED TO "+person_name.toUpperCase() : "NET OWED");

		page.main.find("#fcc-cash-in").text(fmt(s.total_cash_in));
		page.main.find("#fcc-cash-out").text(fmt(s.total_cash_out));
		page.main.find("#fcc-cash-hand").text(fmt(s.cash_in_hand));
		page.main.find("#fcc-expenses").text(fmt(s.total_expenses));
		page.main.find("#fcc-reimbursed").text(fmt(s.reimbursed));
		page.main.find("#fcc-net-owed").text(fmt(s.net_owed));
		page.main.find("#fcc-txn-count").text((s.txn_count||0).toLocaleString());

		if (data.is_finance && data.persons && data.persons.length) {
			page._cd_persons = data.persons;
			var sel = page.main.find("#fcc-person-select");
			sel.find("option:not(:first)").remove();
			data.persons.forEach(function(p){sel.append('<option value="'+p.name+'">'+(p.full_name||p.name)+"</option>");});
			if (data.current_person) sel.val(data.current_person);
			page.main.find("#fcc-filter-bar").css("display","flex");
		}

		// Cash entries
		var tbody = page.main.find("#fcc-txn-body"); tbody.empty();
		var txns = data.transactions || [];
		page.main.find("#fcc-txn-note").text(txns.length ? "showing "+txns.length+" most recent" : "");
		if (!txns.length) {
			tbody.html('<tr><td colspan="8" class="fcc-empty">No entries yet.</td></tr>');
		} else {
			txns.forEach(function(row) {
				var isIn = row.direction==="Cash In";
				var dir = isIn ? "<span class='fcc-badge fcc-badge-in'>&#9650; Cash In</span>" : "<span class='fcc-badge fcc-badge-out'>&#9660; Cash Out</span>";
				var ent = row.entity ? "<span class='fcc-entity-chip'>"+row.entity+"</span>" : "<span class='fcc-muted'>—</span>";
				tbody.append("<tr><td class='fcc-date'>"+row.date+"</td><td>"+ent+"</td><td>"+dir+"</td>"+
					"<td class='fcc-num "+(isIn?"fcc-amt-in":"fcc-amt-out")+"'>"+fmt(row.amount)+"</td>"+
					"<td class='fcc-type'>"+(row.transaction_type||"<span class='fcc-muted'>—</span>")+"</td>"+
					"<td class='fcc-inv'>"+(row.invoice_number||"<span class='fcc-muted'>—</span>")+"</td>"+
					"<td class='fcc-notes'>"+(row.notes?row.notes.substring(0,60)+(row.notes.length>60?"…":""):"<span class='fcc-muted'>—</span>")+"</td>"+
					"<td class='fcc-num fcc-running'>"+fmt(row.running_balance)+"</td></tr>");
			});
		}

		// Expense entries
		var etbody = page.main.find("#fcc-exp-body"); etbody.empty();
		var exps = data.expense_entries || [];
		page.main.find("#fcc-exp-note").text(exps.length ? "showing "+exps.length+" most recent" : "");
		if (!exps.length) {
			etbody.html('<tr><td colspan="6" class="fcc-empty">No expense entries yet.</td></tr>');
		} else {
			exps.forEach(function(row) {
				var isExp = row.direction==="Expense";
				var dir = isExp ? "<span class='fcc-badge fcc-badge-expense'>&#128203; Expense</span>" : "<span class='fcc-badge fcc-badge-reimb'>&#8617; Reimbursement</span>";
				var ent = row.entity ? "<span class='fcc-entity-chip'>"+row.entity+"</span>" : "<span class='fcc-muted'>—</span>";
				var notes = row.notes ? row.notes.replace(/^\[.*?\]\s*/,"").substring(0,60)+(row.notes.length>60?"…":"") : "—";
				etbody.append("<tr><td class='fcc-date'>"+row.date+"</td><td>"+ent+"</td><td>"+dir+"</td>"+
					"<td class='fcc-num "+(isExp?"fcc-amt-out":"fcc-amt-in")+"'>"+fmt(row.amount)+"</td>"+
					"<td class='fcc-type'>"+(row.transaction_type||"<span class='fcc-muted'>—</span>")+"</td>"+
					"<td class='fcc-notes'>"+notes+"</td></tr>");
			});
		}

		// Monthly
		var mbody=page.main.find("#fcc-monthly-body"),mfoot=page.main.find("#fcc-monthly-foot");
		mbody.empty();mfoot.empty();
		if (!data.monthly||!data.monthly.length){mbody.html('<tr><td colspan="8" class="fcc-empty">No entries yet.</td></tr>');}
		else{
			var t={ci:0,co:0,nc:0,ep:0,rb:0,no:0,tx:0};
			data.monthly.forEach(function(row){
				var ncCls=row.net_cash>=0?"fcc-pos":"fcc-neg"; var noCls=row.net_owed>0?"fcc-owed":(row.net_owed<0?"fcc-pos":"");
				mbody.append("<tr><td class='fcc-month'>"+row.month+"</td><td class='fcc-num fcc-col-in'>"+fmt(row.cash_in)+"</td><td class='fcc-num fcc-col-out'>"+fmt(row.cash_out)+"</td><td class='fcc-num "+ncCls+"'>"+fmt(row.net_cash)+"</td><td class='fcc-num fcc-col-exp'>"+fmt(row.expenses)+"</td><td class='fcc-num fcc-col-reimb'>"+fmt(row.reimbursed)+"</td><td class='fcc-num "+noCls+"'>"+fmt(row.net_owed)+"</td><td class='fcc-num fcc-col-count'>"+(row.txn_count||0)+"</td></tr>");
				t.ci+=row.cash_in;t.co+=row.cash_out;t.nc+=row.net_cash;t.ep+=row.expenses;t.rb+=row.reimbursed;t.no+=row.net_owed;t.tx+=(row.txn_count||0);
			});
			mfoot.html("<tr><td><b>TOTAL</b></td><td class='fcc-num'><b>"+fmt(t.ci)+"</b></td><td class='fcc-num'><b>"+fmt(t.co)+"</b></td><td class='fcc-num'><b>"+fmt(t.nc)+"</b></td><td class='fcc-num'><b>"+fmt(t.ep)+"</b></td><td class='fcc-num'><b>"+fmt(t.rb)+"</b></td><td class='fcc-num'><b>"+fmt(t.no)+"</b></td><td class='fcc-num'><b>"+t.tx+"</b></td></tr>");
		}

		// Entity
		var ebody=page.main.find("#fcc-entity-body"),efoot=page.main.find("#fcc-entity-foot");
		ebody.empty();efoot.empty();
		if (!data.entities||!data.entities.length){ebody.html('<tr><td colspan="7" class="fcc-empty">No entries yet.</td></tr>');}
		else{
			var ev={ci:0,co:0,nc:0,ep:0,rb:0,no:0};
			data.entities.forEach(function(row){
				ebody.append("<tr><td class='fcc-entity-name'>"+(row.entity||"Unknown")+"</td><td class='fcc-num fcc-col-in'>"+fmt(row.cash_in)+"</td><td class='fcc-num fcc-col-out'>"+fmt(row.cash_out)+"</td><td class='fcc-num'>"+fmt(row.net_cash)+"</td><td class='fcc-num fcc-col-exp'>"+fmt(row.expenses)+"</td><td class='fcc-num fcc-col-reimb'>"+fmt(row.reimbursed)+"</td><td class='fcc-num fcc-owed'>"+fmt(row.net_owed)+"</td></tr>");
				ev.ci+=row.cash_in;ev.co+=row.cash_out;ev.nc+=row.net_cash;ev.ep+=row.expenses;ev.rb+=row.reimbursed;ev.no+=row.net_owed;
			});
			efoot.html("<tr><td><b>TOTAL</b></td><td class='fcc-num'><b>"+fmt(ev.ci)+"</b></td><td class='fcc-num'><b>"+fmt(ev.co)+"</b></td><td class='fcc-num'><b>"+fmt(ev.nc)+"</b></td><td class='fcc-num'><b>"+fmt(ev.ep)+"</b></td><td class='fcc-num'><b>"+fmt(ev.rb)+"</b></td><td class='fcc-num'><b>"+fmt(ev.no)+"</b></td></tr>");
		}
	}

	function fmt(val) {
		if (val===null||val===undefined) return "$0";
		var n=parseFloat(val); var neg=n<0;
		var abs=Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:0,maximumFractionDigits:0});
		return neg?"($"+abs+")":"$"+abs;
	}

	function export_csv(headers, rows, filename) {
		var lines=[headers.map(cc).join(",")];
		rows.forEach(function(r){lines.push(r.map(cc).join(","));});
		dl_csv(lines.join("\r\n"), filename+"_"+frappe.datetime.get_today()+".csv");
	}

	function export_all(data) {
		var today=frappe.datetime.get_today(), lines=["Financial Command Center Export — "+today];
		lines.push("","=== Cash Entries ===",["Date","Entity","Direction","Amount","Type","Invoice #","Notes","Running Balance"].map(cc).join(","));
		(data.transactions||[]).forEach(function(r){lines.push([r.date,r.entity,r.direction,r.amount,r.transaction_type,r.invoice_number,r.notes,r.running_balance].map(cc).join(","));});
		lines.push("","=== Expense Entries ===",["Date","Entity","Direction","Amount","Type","Notes"].map(cc).join(","));
		(data.expense_entries||[]).forEach(function(r){lines.push([r.date,r.entity,r.direction,r.amount,r.transaction_type,r.notes].map(cc).join(","));});
		lines.push("","=== Monthly Summary ===",["Month","Cash In","Cash Out","Net Cash","Expenses","Reimbursed","Net Owed","# Txns"].map(cc).join(","));
		(data.monthly||[]).forEach(function(r){lines.push([r.month,r.cash_in,r.cash_out,r.net_cash,r.expenses,r.reimbursed,r.net_owed,r.txn_count].map(cc).join(","));});
		lines.push("","=== Entity Breakdown ===",["Entity","Cash In","Cash Out","Net Cash","Expenses","Reimbursed","Net Owed"].map(cc).join(","));
		(data.entities||[]).forEach(function(r){lines.push([r.entity,r.cash_in,r.cash_out,r.net_cash,r.expenses,r.reimbursed,r.net_owed].map(cc).join(","));});
		dl_csv(lines.join("\r\n"),"financial_command_center_"+today+".csv");
	}

	function dl_csv(content, filename) {
		var blob=new Blob([content],{type:"text/csv"});
		var url=URL.createObjectURL(blob);
		var a=document.createElement("a"); a.href=url; a.download=filename;
		document.body.appendChild(a); a.click(); document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}

	function cc(val) {
		if (val===null||val===undefined) return "";
		var s=String(val);
		return (s.includes(",")||s.includes('"')||s.includes("\n")) ? '"'+s.replace(/"/g,'""')+'"' : s;
	}
};
