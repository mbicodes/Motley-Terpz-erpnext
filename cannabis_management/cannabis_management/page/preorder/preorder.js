frappe.pages["preorder"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "",
		single_column: true,
	});

	$(wrapper).find(".page-head").hide();
	page.main.html(PO_PAGE_HTML);

	window._po = {
		items: [],
		inventory: [],
	};

	poBindEvents();
	poLoadInventory();
	poLoadRecent();
};

frappe.pages["preorder"].on_page_show = function () {
	poLoadRecent();
};

// ─────────────────────────────────────────────────────
// PAGE HTML
// ─────────────────────────────────────────────────────

const PO_PAGE_HTML = `
<div class="po-page">

  <!-- HEADER -->
  <div class="po-header">
    <div class="po-header-left">
      <div class="po-eyebrow">Cannabis Management</div>
      <h1 class="po-title">Preorder Entry</h1>
      <p class="po-subtitle">Submit packaged goods preorders — rep info, license details, and SKU selection.</p>
    </div>
    <div class="po-header-right">
      <button class="po-btn po-btn-clear" id="po-clear-btn" type="button">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
        Clear
      </button>
      <button class="po-btn po-btn-save" id="po-save-btn" type="button">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
        Save Preorder
      </button>
    </div>
  </div>

  <!-- REP INFO + LICENSE INFO (side by side) -->
  <div class="po-two-col">
    <div class="po-card">
      <div class="po-card-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        Sales Rep
      </div>
      <div class="po-form-grid">
        <div class="po-field">
          <label>Rep Name</label>
          <input type="text" id="po-rep-name" placeholder="Full name">
        </div>
        <div class="po-field">
          <label>Rep Email</label>
          <input type="email" id="po-rep-email" placeholder="email@example.com">
        </div>
        <div class="po-field">
          <label>Rep Phone</label>
          <input type="tel" id="po-rep-phone" placeholder="(555) 000-0000">
        </div>
      </div>
    </div>

    <div class="po-card">
      <div class="po-card-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
        Brand &amp; License
      </div>
      <div class="po-form-grid">
        <div class="po-field">
          <label>Brand Name</label>
          <input type="text" id="po-brand-name" placeholder="Brand">
        </div>
        <div class="po-field">
          <label>License Name</label>
          <input type="text" id="po-license-name" placeholder="License holder name">
        </div>
        <div class="po-field">
          <label>License Number</label>
          <input type="text" id="po-license-number" placeholder="e.g. C11-0000000-LIC">
        </div>
      </div>
    </div>
  </div>

  <!-- ADDRESS & ORDER DETAILS -->
  <div class="po-card">
    <div class="po-card-title">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 6-9 13-9 13S3 16 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
      Address &amp; Order Details
    </div>
    <div class="po-form-grid">
      <div class="po-field" style="grid-column: span 2;">
        <label>Primary Address</label>
        <textarea id="po-address" placeholder="Street, City, State ZIP" rows="2"></textarea>
      </div>
      <div class="po-field">
        <label>Region <span class="po-region-badge" id="po-region-auto" style="display:none;">auto-detected</span></label>
        <select id="po-region">
          <option value="">Select Region</option>
          <option value="NorCal">NorCal</option>
          <option value="Bay Area">Bay Area</option>
          <option value="Central Valley">Central Valley</option>
          <option value="LA">LA</option>
          <option value="OC">OC</option>
          <option value="IE">IE</option>
          <option value="San Diego">San Diego</option>
          <option value="Other">Other</option>
        </select>
      </div>
      <div class="po-field">
        <label>Order Date</label>
        <input type="date" id="po-order-date">
      </div>
      <div class="po-field">
        <label>Requested Delivery Date</label>
        <input type="date" id="po-delivery-date">
      </div>
      <div class="po-field">
        <label>Company</label>
        <select id="po-company">
          <option value="">Select Company</option>
        </select>
      </div>
    </div>
  </div>

  <!-- PACKAGED GOODS ITEMS -->
  <div class="po-card">
    <div class="po-card-title">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
      Packaged Goods for Preorder
    </div>
    <div class="po-items-toolbar">
      <div class="po-picker-wrap" style="flex:1; max-width:400px;">
        <input type="text" class="po-items-search" id="po-item-search" placeholder="Search SKU or item name to add...">
        <div class="po-picker-dropdown" id="po-picker-dropdown"></div>
      </div>
      <button class="po-btn-add-item" id="po-browse-items" type="button">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        Browse Inventory
      </button>
    </div>
    <table class="po-items-table" id="po-items-table">
      <thead>
        <tr>
          <th style="width:26%">Item</th>
          <th>Group</th>
          <th>Available</th>
          <th style="width:80px">Qty</th>
          <th style="width:110px">Rate</th>
          <th style="width:110px" class="po-num">Amount</th>
          <th style="width:36px"></th>
        </tr>
      </thead>
      <tbody id="po-items-body">
        <tr class="po-empty-row"><td colspan="7" class="po-empty-items">Search above to add packaged goods to this preorder</td></tr>
      </tbody>
    </table>
  </div>

  <!-- NOTES -->
  <div class="po-card">
    <div class="po-card-title">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
      Notes
    </div>
    <div class="po-field po-field-wide">
      <textarea id="po-notes" placeholder="Special instructions, delivery notes, etc." rows="3"></textarea>
    </div>
  </div>

  <!-- RECENT PREORDERS -->
  <div class="po-card">
    <div class="po-card-title">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      Recent Preorders
    </div>
    <table class="po-recent-table" id="po-recent-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Rep</th>
          <th>Brand</th>
          <th>Region</th>
          <th>Date</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="po-recent-body">
        <tr><td colspan="6" class="po-empty-items">Loading...</td></tr>
      </tbody>
    </table>
  </div>

</div>
`;

// ─────────────────────────────────────────────────────
// REGION AUTO-DETECT
// ─────────────────────────────────────────────────────

function poGuessRegion(address) {
	const m = address.match(/\b(9\d{4})\b/);
	if (!m) return "";
	const z = parseInt(m[1]);
	if (z >= 90000 && z <= 91599) return "LA";
	if (z >= 91600 && z <= 91899) return "IE";
	if (z >= 91900 && z <= 92199) return "San Diego";
	if (z >= 92200 && z <= 92599) return "IE";
	if (z >= 92600 && z <= 92899) return "OC";
	if (z >= 93000 && z <= 93999) return "Central Valley";
	if (z >= 94000 && z <= 94999) return "Bay Area";
	if (z >= 95000 && z <= 96199) return "NorCal";
	return "Other";
}

// ─────────────────────────────────────────────────────
// ITEM TABLE HELPERS
// ─────────────────────────────────────────────────────

// Amount is always derived, never typed: Preorder Item.amount is read_only in
// the doctype and the server recomputes it on save. This is only the preview.
function poAmount(item) {
	return (parseFloat(item.rate) || 0) * (parseInt(item.qty, 10) || 0);
}

function poMoney(v) {
	return format_currency(v || 0, "USD");
}

function poOrderTotals() {
	return window._po.items.reduce(
		function (acc, i) {
			acc.qty += parseInt(i.qty, 10) || 0;
			acc.amount += poAmount(i);
			return acc;
		},
		{ qty: 0, amount: 0 }
	);
}

function poRenderItems() {
	const body = document.getElementById("po-items-body");
	if (!window._po.items.length) {
		body.innerHTML = '<tr class="po-empty-row"><td colspan="7" class="po-empty-items">Search above to add packaged goods to this preorder</td></tr>';
		return;
	}
	body.innerHTML = window._po.items
		.map(function (item, idx) {
			const sq = item.available_qty || 0;
			const cls = sq > 10 ? "in-stock" : sq > 0 ? "low-stock" : "no-stock";
			return (
				'<tr data-idx="' + idx + '">' +
				"<td>" +
				'<div class="po-item-name">' + frappe.utils.escape_html(item.item_name) + "</div>" +
				(item.is_custom
					? '<div class="po-item-custom-badge">Custom item</div>'
					: '<div class="po-item-code">' + frappe.utils.escape_html(item.item_code) + "</div>") +
				"</td>" +
				'<td class="po-item-group">' + (item.is_custom ? "&mdash;" : frappe.utils.escape_html(item.item_group)) + "</td>" +
				(item.is_custom
					? '<td class="po-stock-qty">&mdash;</td>'
					: '<td class="po-stock-qty ' + cls + '">' + sq + " " + frappe.utils.escape_html(item.uom || "") + "</td>") +
				'<td><input type="number" min="1" step="1" value="' + (item.qty || 1) + '" class="po-item-qty"></td>' +
				'<td><input type="number" min="0" step="0.01" value="' + (item.rate != null ? item.rate : "") + '" placeholder="0.00" class="po-item-rate"></td>' +
				'<td class="po-item-amount po-num">' + poMoney(poAmount(item)) + "</td>" +
				'<td><button class="po-btn-remove po-remove-item" title="Remove">' +
				'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
				"</button></td>" +
				"</tr>"
			);
		})
		.join("") + poTotalsRowHtml();
}

function poTotalsRowHtml() {
	var t = poOrderTotals();
	return (
		'<tr class="po-totals-row">' +
		'<td colspan="3" class="po-totals-label">Order total</td>' +
		'<td class="po-totals-qty">' + t.qty + "</td>" +
		"<td></td>" +
		'<td class="po-num po-totals-amount">' + poMoney(t.amount) + "</td>" +
		"<td></td>" +
		"</tr>"
	);
}

function poAddItem(inv) {
	if (window._po.items.find(function (i) { return i.item_code === inv.name; })) {
		frappe.show_alert({ message: "Item already added", indicator: "orange" });
		return;
	}
	window._po.items.push({
		item_code: inv.name,
		item_name: inv.item_name,
		item_group: inv.item_group,
		uom: inv.stock_uom,
		available_qty: inv.available_qty || 0,
		qty: 1,
		rate: null,
	});
	poRenderItems();
}

// Add a row for something that is not in the catalog. item_code stays empty --
// it is a Link to Item on Preorder Item, so free text cannot live there; the
// typed text travels as item_name and the server keeps item_code blank.
function poAddCustomItem(text) {
	text = (text || "").trim();
	if (!text) return;
	var dup = window._po.items.find(function (i) {
		return i.is_custom && (i.item_name || "").toLowerCase() === text.toLowerCase();
	});
	if (dup) {
		frappe.show_alert({ message: "Item already added", indicator: "orange" });
		return;
	}
	window._po.items.push({
		item_code: "",
		item_name: text,
		item_group: "",
		uom: "",
		available_qty: 0,
		qty: 1,
		rate: null,
		is_custom: true,
	});
	poRenderItems();
}

// Enter in the search box: prefer a real catalog match over a custom row, so
// typing a full SKU and hitting Enter does not silently create free text.
function poAddTypedTerm(term) {
	term = (term || "").trim();
	if (!term) return;
	var t = term.toLowerCase();
	var exact = window._po.inventory.find(function (i) {
		return (i.name || "").toLowerCase() === t || (i.item_name || "").toLowerCase() === t;
	});
	if (exact) poAddItem(exact);
	else poAddCustomItem(term);
}

// ─────────────────────────────────────────────────────
// PICKER DROPDOWN
// ─────────────────────────────────────────────────────

function poCustomOptionHtml(term) {
	term = (term || "").trim();
	if (!term) return "";
	return (
		'<div class="po-picker-option po-picker-custom" data-custom="' + frappe.utils.escape_html(term) + '">' +
		"<div>" +
		'<div class="po-picker-option-name">Add &ldquo;' + frappe.utils.escape_html(term) + '&rdquo;</div>' +
		'<div class="po-picker-option-code">Custom item &mdash; not in inventory</div>' +
		"</div>" +
		"</div>"
	);
}

function poRenderPicker(results, term) {
	const dd = document.getElementById("po-picker-dropdown");
	const customOption = poCustomOptionHtml(term);
	if (!results.length) {
		dd.innerHTML = customOption || '<div class="po-picker-empty">No matching items</div>';
		dd.classList.add("open");
		return;
	}
	dd.innerHTML = results
		.map(function (r) {
			const sq = r.available_qty || 0;
			const cls = sq > 10 ? "in-stock" : sq > 0 ? "low-stock" : "no-stock";
			return (
				'<div class="po-picker-option" data-item=\'' + JSON.stringify(r).replace(/'/g, "&#39;") + "'>" +
				"<div>" +
				'<div class="po-picker-option-name">' + frappe.utils.escape_html(r.item_name) + "</div>" +
				'<div class="po-picker-option-code">' + frappe.utils.escape_html(r.name) + "</div>" +
				"</div>" +
				'<div class="po-picker-option-stock po-stock-qty ' + cls + '">' + sq + " avail</div>" +
				"</div>"
			);
		})
		.join("") + customOption;
	dd.classList.add("open");
}

// ─────────────────────────────────────────────────────
// EVENTS
// ─────────────────────────────────────────────────────

function poBindEvents() {
	// Set today as default order date
	var today = frappe.datetime.get_today();
	var el = document.getElementById("po-order-date");
	if (el) el.value = today;

	// Load companies into dropdown
	frappe.call({
		method: "frappe.client.get_list",
		args: { doctype: "Company", fields: ["name"], limit_page_length: 20 },
		async: true,
		callback: function (r) {
			var sel = document.getElementById("po-company");
			(r.message || []).forEach(function (c) {
				var opt = document.createElement("option");
				opt.value = c.name;
				opt.textContent = c.name;
				sel.appendChild(opt);
			});
		},
	});

	// Address → Region auto-detect
	var addrTimeout;
	$("#po-address").on("input", function () {
		clearTimeout(addrTimeout);
		addrTimeout = setTimeout(function () {
			var addr = $("#po-address").val();
			var region = poGuessRegion(addr);
			if (region) {
				$("#po-region").val(region);
				$("#po-region-auto").show();
			} else {
				$("#po-region-auto").hide();
			}
		}, 400);
	});

	// Item search with picker
	var searchTimeout;
	$("#po-item-search").on("input", function () {
		clearTimeout(searchTimeout);
		var term = $(this).val().trim();
		if (term.length < 2) {
			$("#po-picker-dropdown").removeClass("open").empty();
			return;
		}
		searchTimeout = setTimeout(function () {
			var filtered = window._po.inventory.filter(function (i) {
				var t = term.toLowerCase();
				return (
					i.item_name.toLowerCase().indexOf(t) > -1 ||
					i.name.toLowerCase().indexOf(t) > -1
				);
			});
			poRenderPicker(filtered.slice(0, 15), term);
		}, 200);
	});

	// Enter adds whatever is typed -- a catalog match if there is one,
	// otherwise a custom free-text row.
	$("#po-item-search").on("keydown", function (e) {
		if (e.key !== "Enter") return;
		e.preventDefault();
		poAddTypedTerm($(this).val());
		$(this).val("");
		$("#po-picker-dropdown").removeClass("open").empty();
	});

	// Click picker option
	$(document).on("click", ".po-picker-option", function () {
		var customText = $(this).attr("data-custom");
		if (customText !== undefined) {
			poAddCustomItem(customText);
		} else {
			poAddItem(JSON.parse($(this).attr("data-item")));
		}
		$("#po-item-search").val("");
		$("#po-picker-dropdown").removeClass("open").empty();
	});

	// Close picker on outside click
	$(document).on("click", function (e) {
		if (!$(e.target).closest(".po-picker-wrap").length) {
			$("#po-picker-dropdown").removeClass("open");
		}
	});

	// Qty / Rate edits. Both re-render so the row's Amount and the order
	// total stay in step -- amount is derived, never entered directly.
	$(document).on("change", ".po-item-qty", function () {
		var idx = $(this).closest("tr").data("idx");
		window._po.items[idx].qty = parseInt($(this).val(), 10) || 1;
		poRenderItems();
	});

	$(document).on("change", ".po-item-rate", function () {
		var idx = $(this).closest("tr").data("idx");
		var raw = $(this).val();
		window._po.items[idx].rate = raw === "" ? null : Math.max(0, parseFloat(raw) || 0);
		poRenderItems();
	});

	// Remove item
	$(document).on("click", ".po-remove-item", function () {
		var idx = $(this).closest("tr").data("idx");
		window._po.items.splice(idx, 1);
		poRenderItems();
	});

	// Browse inventory button (opens full list)
	$("#po-browse-items").on("click", function () {
		poRenderPicker(window._po.inventory.slice(0, 30));
		$("#po-item-search").focus();
	});

	// Save
	$("#po-save-btn").on("click", poSave);

	// Clear
	$("#po-clear-btn").on("click", poClear);

	// Recent preorder click → open form
	$(document).on("click", "#po-recent-body tr", function () {
		var name = $(this).data("name");
		if (name) frappe.set_route("Form", "Preorder Entry", name);
	});
}

// ─────────────────────────────────────────────────────
// LOAD DATA
// ─────────────────────────────────────────────────────

function poLoadInventory() {
	frappe.call({
		method: "cannabis_management.cannabis_management.page.preorder.preorder.get_packaged_inventory",
		async: true,
		callback: function (r) {
			window._po.inventory = r.message || [];
		},
	});
}

function poLoadRecent() {
	frappe.call({
		method: "cannabis_management.cannabis_management.page.preorder.preorder.get_recent_preorders",
		async: true,
		callback: function (r) {
			var rows = r.message || [];
			var body = document.getElementById("po-recent-body");
			if (!rows.length) {
				body.innerHTML = '<tr><td colspan="6" class="po-empty-items">No preorders yet</td></tr>';
				return;
			}
			body.innerHTML = rows
				.map(function (row) {
					var st = row.docstatus;
					var cls = st === 1 ? "po-status-submitted" : st === 2 ? "po-status-cancelled" : "po-status-draft";
					var label = st === 1 ? "Submitted" : st === 2 ? "Cancelled" : "Draft";
					return (
						'<tr data-name="' + frappe.utils.escape_html(row.name) + '">' +
						"<td>" + frappe.utils.escape_html(row.name) + "</td>" +
						"<td>" + frappe.utils.escape_html(row.rep_name || "—") + "</td>" +
						"<td>" + frappe.utils.escape_html(row.brand_name || "—") + "</td>" +
						"<td>" + frappe.utils.escape_html(row.region || "—") + "</td>" +
						"<td>" + (row.order_date || "—") + "</td>" +
						'<td><span class="po-status-badge ' + cls + '">' + label + "</span></td>" +
						"</tr>"
					);
				})
				.join("");
		},
	});
}

// ─────────────────────────────────────────────────────
// SAVE / CLEAR
// ─────────────────────────────────────────────────────

function poSave() {
	var data = {
		rep_name: $("#po-rep-name").val(),
		rep_email: $("#po-rep-email").val(),
		rep_phone: $("#po-rep-phone").val(),
		brand_name: $("#po-brand-name").val(),
		license_name: $("#po-license-name").val(),
		license_number: $("#po-license-number").val(),
		primary_address: $("#po-address").val(),
		region: $("#po-region").val(),
		order_date: $("#po-order-date").val(),
		requested_delivery_date: $("#po-delivery-date").val(),
		company: $("#po-company").val(),
		notes: $("#po-notes").val(),
		items: window._po.items.map(function (i) {
			return {
				item_code: i.item_code,
				item_name: i.item_name,
				item_group: i.item_group,
				qty: i.qty,
				uom: i.uom,
				rate: i.rate,
			};
		}),
	};

	frappe.call({
		method: "cannabis_management.cannabis_management.page.preorder.preorder.save_preorder",
		args: { data: data },
		freeze: true,
		freeze_message: "Saving preorder...",
		callback: function (r) {
			if (r.message) {
				frappe.show_alert({
					message: "Preorder <b>" + r.message.name + "</b> created",
					indicator: "green",
				});
				poClear();
				poLoadRecent();
			}
		},
	});
}

function poClear() {
	$("#po-rep-name, #po-rep-email, #po-rep-phone").val("");
	$("#po-brand-name, #po-license-name, #po-license-number").val("");
	$("#po-address, #po-notes").val("");
	$("#po-region").val("");
	$("#po-region-auto").hide();
	$("#po-delivery-date").val("");
	$("#po-order-date").val(frappe.datetime.get_today());
	$("#po-company").val("");
	window._po.items = [];
	poRenderItems();
}
