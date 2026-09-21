document.addEventListener("DOMContentLoaded", function () {
	window._po = { items: [], inventory: [], dropdownOpen: false, editing: null };
	poSetDefaults();
	poLoadInventory();
	poLoadRecent();
	poBindEvents();
});

/* ─────────────────────────────────────────────────────
   DEFAULTS
   ───────────────────────────────────────────────────── */

function poSetDefaults() {
	var today = frappe.datetime ? frappe.datetime.get_today() : new Date().toISOString().slice(0, 10);
	var el = document.getElementById("poOrderDate");
	if (el) el.value = today;
}

/* ─────────────────────────────────────────────────────
   DATA
   ───────────────────────────────────────────────────── */

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
			poRenderRecent(r.message || []);
		},
	});
}

/* ─────────────────────────────────────────────────────
   REGION AUTO-DETECT
   ───────────────────────────────────────────────────── */

function poGuessRegion(addr) {
	var m = addr.match(/\b(9\d{4})\b/);
	if (!m) return "";
	var z = parseInt(m[1]);
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

/* ─────────────────────────────────────────────────────
   LINK-FIELD DROPDOWN
   ───────────────────────────────────────────────────── */

function poOpenDropdown(filterTerm) {
	var inv = window._po.inventory;
	var dd = document.getElementById("poLinkDropdown");

	if (filterTerm) {
		var t = filterTerm.toLowerCase();
		inv = inv.filter(function (i) {
			return i.item_name.toLowerCase().indexOf(t) > -1 ||
				   i.name.toLowerCase().indexOf(t) > -1;
		});
	}

	var showing = inv.slice(0, 40);

	var customOption = poCustomOptionHtml(filterTerm);

	if (!showing.length) {
		dd.innerHTML = customOption || '<div class="po-link-empty">No matching items found</div>';
		dd.classList.add("open");
		window._po.dropdownOpen = true;
		return;
	}

	dd.innerHTML = showing.map(function (r) {
		var sq = r.available_qty || 0;
		var cls = sq > 10 ? "in-stock" : sq > 0 ? "low-stock" : "no-stock";
		return '<div class="po-link-option" data-item=\'' + JSON.stringify(r).replace(/'/g, "&#39;") + "'>" +
			'<div class="po-link-option-left">' +
			'<div class="po-link-option-name">' + poEsc(r.item_name) + "</div>" +
			'<div class="po-link-option-code">' + poEsc(r.name) + "</div>" +
			"</div>" +
			'<div class="po-link-option-right">' +
			'<div class="po-link-option-group">' + poEsc(r.item_group) + "</div>" +
			'<div class="po-link-option-stock po-stock-qty ' + cls + '">' + sq + " avail</div>" +
			"</div>" +
			"</div>";
	}).join("") + customOption;

	dd.classList.add("open");
	window._po.dropdownOpen = true;
}

function poCustomOptionHtml(term) {
	term = (term || "").trim();
	if (!term) return "";
	return '<div class="po-link-option po-link-custom" data-custom="' + poEsc(term) + '">' +
		'<div class="po-link-option-left">' +
		'<div class="po-link-option-name">Add &ldquo;' + poEsc(term) + '&rdquo;</div>' +
		'<div class="po-link-option-code">Custom item &mdash; not in inventory</div>' +
		"</div></div>";
}

function poCloseDropdown() {
	document.getElementById("poLinkDropdown").classList.remove("open");
	window._po.dropdownOpen = false;
}

/* ─────────────────────────────────────────────────────
   ITEMS TABLE
   ───────────────────────────────────────────────────── */

// Amount is derived, never typed: Preorder Item.amount is read_only in the
// doctype and the server recomputes it on save. This is only the preview.
function poAmount(item) {
	return (parseFloat(item.rate) || 0) * (parseInt(item.qty, 10) || 0);
}

function poMoney(v) {
	return "$" + (v || 0).toLocaleString("en-US", {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2,
	});
}

function poOrderTotals() {
	return window._po.items.reduce(function (acc, i) {
		acc.qty += parseInt(i.qty, 10) || 0;
		acc.amount += poAmount(i);
		return acc;
	}, { qty: 0, amount: 0 });
}

function poTotalsRowHtml() {
	var t = poOrderTotals();
	return '<tr class="po-totals-row">' +
		'<td colspan="4" class="po-totals-label">Order total</td>' +
		'<td class="po-totals-qty">' + t.qty + "</td>" +
		"<td></td>" +
		'<td class="po-num po-totals-amount">' + poMoney(t.amount) + "</td>" +
		"<td></td></tr>";
}

function poRenderItems() {
	var body = document.getElementById("poItemsBody");
	if (!window._po.items.length) {
		body.innerHTML = '<tr class="po-empty-row"><td colspan="8" class="po-empty-items">No items added yet &mdash; click the field above to browse packaged goods</td></tr>';
		return;
	}
	body.innerHTML = window._po.items.map(function (item, idx) {
		var sq = item.available_qty || 0;
		var cls = sq > 10 ? "in-stock" : sq > 0 ? "low-stock" : "no-stock";
		return '<tr data-idx="' + idx + '">' +
			'<td class="po-row-num">' + (idx + 1) + "</td>" +
			"<td>" +
			'<div class="po-item-name">' + poEsc(item.item_name) + "</div>" +
			(item.is_custom
				? '<div class="po-item-custom-badge">Custom item</div>'
				: '<div class="po-item-code">' + poEsc(item.item_code) + "</div>") +
			"</td>" +
			'<td class="po-item-group">' + (item.is_custom ? "&mdash;" : poEsc(item.item_group)) + "</td>" +
			(item.is_custom
				? '<td class="po-stock-qty">&mdash;</td>'
				: '<td class="po-stock-qty ' + cls + '">' + sq + " " + poEsc(item.uom || "") + "</td>") +
			'<td><input type="number" min="1" step="1" value="' + (item.qty || 1) + '" class="po-item-qty"></td>' +
			'<td><input type="number" min="0" step="0.01" value="' + (item.rate != null ? item.rate : "") + '" placeholder="0.00" class="po-item-rate"></td>' +
			'<td class="po-item-amount po-num">' + poMoney(poAmount(item)) + "</td>" +
			'<td><button class="po-btn-remove po-remove-item" title="Remove">' +
			'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>' +
			"</button></td></tr>";
	}).join("") + poTotalsRowHtml();
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

// Row for something not in the catalog. item_code is a Link to Item on
// Preorder Item and cannot hold free text, so the typed text travels as
// item_name with item_code left blank.
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

// Prefer a real catalog match over free text, so typing a full SKU and
// pressing Enter does not quietly create a custom row.
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

/* ─────────────────────────────────────────────────────
   PRINT / PDF
   ───────────────────────────────────────────────────── */

var PO_PRINT_FORMAT = "Preorder Entry - Motley";

// Renders the Motley format server-side and hands back a real PDF, so the
// browser can open it in its viewer or save it straight to disk.
function poPdfUrl(name) {
	return "/api/method/frappe.utils.print_format.download_pdf" +
		"?doctype=" + encodeURIComponent("Preorder Entry") +
		"&name=" + encodeURIComponent(name) +
		"&format=" + encodeURIComponent(PO_PRINT_FORMAT) +
		"&no_letterhead=0";
}

// Real download rather than opening a tab: the PDF is served
// Content-Disposition: inline, so the anchor's download attribute is what
// actually saves it (same-origin, so the browser honours it).
function poDownloadPdf(name) {
	if (!name) return;
	var a = document.createElement("a");
	a.href = poPdfUrl(name);
	a.download = name + ".pdf";
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	// The PDF is rendered server-side, so the file can take a moment to
	// arrive and the click itself shows nothing. Say what is happening, and
	// hold it long enough to still be there when the download lands.
	frappe.show_alert({
		message: "Downloading <b>" + poEsc(name) + ".pdf</b>",
		indicator: "blue",
	}, 10);
}


/* ─────────────────────────────────────────────────────
   RECENT PREORDERS
   ───────────────────────────────────────────────────── */

function poRenderRecent(rows) {
	var body = document.getElementById("poRecentBody");
	if (!rows.length) {
		body.innerHTML = '<div class="po-entry-empty">No preorders yet</div>';
		poSetSideCount(0);
		return;
	}
	body.innerHTML = rows.map(function (row) {
		var st = row.docstatus;
		var cls = st === 1 ? "po-status-submitted" : st === 2 ? "po-status-cancelled" : "po-status-draft";
		var label = st === 1 ? "Submitted" : st === 2 ? "Cancelled" : "Draft";
		var editing = window._po.editing === row.name;
		// Only a draft can be edited -- Frappe will not let a submitted or
		// cancelled document change, so do not offer a button that cannot work.
		var draftBtns = st === 0
			? '<button class="po-entry-btn po-edit-preorder" data-name="' + poEsc(row.name) + '">' +
			  '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
			  '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>' +
			  '<path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/></svg> Edit</button>' +
			  '<button class="po-entry-btn po-submit-preorder" data-name="' + poEsc(row.name) + '" title="Submit this preorder">' +
			  '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> Submit</button>'
			: "";
		return '<div class="po-entry' + (editing ? " is-editing" : "") + '" data-name="' + poEsc(row.name) + '">' +
			'<div class="po-entry-head">' +
			'<span class="po-entry-id">' + poEsc(row.name) + "</span>" +
			'<span class="po-status-badge ' + cls + '">' + label + "</span>" +
			"</div>" +
			'<div class="po-entry-meta">' +
			poEsc(row.brand_name || row.rep_name || "\u2014") +
			(row.order_date ? ' &middot; <span class="po-entry-date">' + row.order_date + "</span>" : "") +
			"</div>" +
			'<div class="po-entry-actions">' + draftBtns +
			'<button class="po-entry-btn po-entry-btn-primary po-download-preorder" data-name="' + poEsc(row.name) + '" title="Download PDF (' + PO_PRINT_FORMAT + ')">' +
			'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download</button>' +
			"</div></div>";
	}).join("");
	poSetSideCount(rows.length);
}

// Keeps the collapsed header honest about how many entries are behind it.
function poSetSideCount(n) {
	var el = document.getElementById("poSideCount");
	if (el) el.textContent = n;
}

/* ─────────────────────────────────────────────────────
   EVENTS
   ───────────────────────────────────────────────────── */

function poBindEvents() {
	var input = document.getElementById("poItemInput");
	var arrow = document.getElementById("poLinkArrow");
	var searchTimer;

	// Click arrow or focus input → open full dropdown (like a link field)
	arrow.addEventListener("click", function (e) {
		e.stopPropagation();
		if (window._po.dropdownOpen) {
			poCloseDropdown();
		} else {
			input.focus();
			poOpenDropdown(input.value.trim());
		}
	});

	input.addEventListener("focus", function () {
		poOpenDropdown(input.value.trim());
	});

	// Type to filter
	input.addEventListener("input", function () {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(function () {
			poOpenDropdown(input.value.trim());
		}, 150);
	});

	// Click an option
	document.getElementById("poLinkDropdown").addEventListener("click", function (e) {
		var opt = e.target.closest(".po-link-option");
		if (!opt) return;
		var customText = opt.getAttribute("data-custom");
		if (customText !== null) {
			poAddCustomItem(customText);
		} else {
			poAddItem(JSON.parse(opt.getAttribute("data-item")));
		}
		input.value = "";
		poCloseDropdown();
	});

	// Close dropdown on outside click
	document.addEventListener("click", function (e) {
		if (!e.target.closest("#poLinkField")) {
			poCloseDropdown();
		}
	});

	// Escape closes the dropdown; Enter adds whatever is typed, as a catalog
	// match when one exists and as a custom free-text row otherwise.
	input.addEventListener("keydown", function (e) {
		if (e.key === "Escape") {
			poCloseDropdown();
			input.blur();
		} else if (e.key === "Enter") {
			e.preventDefault();
			poAddTypedTerm(input.value);
			input.value = "";
			poCloseDropdown();
		}
	});

	// Address → region auto-detect
	var addrTimer;
	document.getElementById("poAddress").addEventListener("input", function () {
		clearTimeout(addrTimer);
		addrTimer = setTimeout(function () {
			var addr = document.getElementById("poAddress").value;
			var region = poGuessRegion(addr);
			var badge = document.getElementById("poRegionAuto");
			if (region) {
				document.getElementById("poRegion").value = region;
				badge.classList.add("visible");
			} else {
				badge.classList.remove("visible");
			}
		}, 400);
	});

	// Qty change in items table
	// Qty / Rate edits. Both re-render so the row's Amount and the order
	// total stay in step -- amount is derived, never entered directly.
	document.getElementById("poItemsBody").addEventListener("change", function (e) {
		var tr = e.target.closest("tr[data-idx]");
		if (!tr) return;
		var idx = parseInt(tr.getAttribute("data-idx"), 10);
		if (e.target.classList.contains("po-item-qty")) {
			window._po.items[idx].qty = parseInt(e.target.value, 10) || 1;
			poRenderItems();
		} else if (e.target.classList.contains("po-item-rate")) {
			var raw = e.target.value;
			window._po.items[idx].rate = raw === "" ? null : Math.max(0, parseFloat(raw) || 0);
			poRenderItems();
		}
	});

	// Remove item
	document.getElementById("poItemsBody").addEventListener("click", function (e) {
		var btn = e.target.closest(".po-remove-item");
		if (!btn) return;
		var idx = parseInt(btn.closest("tr").getAttribute("data-idx"));
		window._po.items.splice(idx, 1);
		poRenderItems();
	});

	// Right pane: Download saves the PDF, Edit loads the entry into the form.
	document.getElementById("poRecentBody").addEventListener("click", function (e) {
		var dlBtn = e.target.closest(".po-download-preorder");
		if (dlBtn) {
			poDownloadPdf(dlBtn.getAttribute("data-name"));
			return;
		}
		var editBtn = e.target.closest(".po-edit-preorder");
		if (editBtn) {
			poEditPreorder(editBtn.getAttribute("data-name"));
			return;
		}
		var submitBtn = e.target.closest(".po-submit-preorder");
		if (submitBtn) {
			poSubmitPreorder(submitBtn.getAttribute("data-name"));
		}
	});

	// Leave edit mode without saving.
	document.addEventListener("click", function (e) {
		if (e.target.closest("#poCancelEdit")) poClear();
	});

	// Collapse/expand the entries pane. Only has a visible effect on narrow
	// screens, where the CSS hides the list unless .is-open is set.
	var sideToggle = document.getElementById("poSideToggle");
	if (sideToggle) {
		sideToggle.addEventListener("click", function () {
			this.closest(".po-side").classList.toggle("is-open");
		});
	}

	// Save
	document.getElementById("poSaveBtn").addEventListener("click", poSave);

	// Clear
	document.getElementById("poClearBtn").addEventListener("click", poClear);
}

/* ─────────────────────────────────────────────────────
   EDIT AN EXISTING ENTRY
   ───────────────────────────────────────────────────── */

function poEditPreorder(name) {
	frappe.call({
		method: "cannabis_management.cannabis_management.page.preorder.preorder.get_preorder",
		args: { name: name },
		freeze: true,
		freeze_message: "Loading " + name + "\u2026",
		callback: function (r) {
			var d = r.message;
			if (!d) return;
			var map = {
				poRepName: "rep_name", poRepEmail: "rep_email", poRepPhone: "rep_phone",
				poBrandName: "brand_name", poLicenseName: "license_name",
				poLicenseNumber: "license_number", poAddress: "primary_address",
				poRegion: "region", poOrderDate: "order_date",
				poDeliveryDate: "requested_delivery_date", poCompany: "company",
				poNotes: "notes",
			};
			Object.keys(map).forEach(function (id) {
				var el = document.getElementById(id);
				if (el) el.value = d[map[id]] || "";
			});
			window._po.items = (d.items || []).map(function (r2) {
				return {
					item_code: r2.item_code || "",
					item_name: r2.item_name || "",
					item_group: r2.item_group || "",
					uom: r2.uom || "",
					qty: r2.qty || 1,
					rate: r2.rate != null ? r2.rate : null,
					available_qty: 0,
					is_custom: !!r2.is_custom,
				};
			});
			window._po.editing = d.name;
			poRenderItems();
			poSyncEditState();
			poLoadRecent();
			window.scrollTo({ top: 0, behavior: "smooth" });
		},
	});
}

// Reflects edit mode in the header: the save button becomes an update, and a
// banner offers a way out without saving.
function poSyncEditState() {
	var editing = window._po.editing;
	var saveBtn = document.getElementById("poSaveBtn");
	var banner = document.getElementById("poEditBanner");
	if (saveBtn) {
		saveBtn.lastChild.nodeValue = editing ? " Update Preorder" : " Save Preorder";
	}
	if (banner) {
		banner.innerHTML = editing
			? 'Editing <b>' + poEsc(editing) + "</b> " +
			  '<button type="button" class="po-banner-cancel" id="poCancelEdit">Cancel</button>'
			: "";
		banner.style.display = editing ? "" : "none";
	}
}

// frappe.confirm is not guaranteed on the website bundle, so fall back to
// the browser's own dialog rather than failing silently.
function poConfirm(message, onYes) {
	if (frappe && typeof frappe.confirm === "function") {
		frappe.confirm(message, onYes);
	} else if (window.confirm(message.replace(/<[^>]+>/g, ""))) {
		onYes();
	}
}

// Submit is the point of no return for editing, so confirm first.
function poSubmitPreorder(name) {
	poConfirm(
		"Submit <b>" + poEsc(name) + "</b>?<br><br>A submitted preorder can no longer be edited.",
		function () {
			frappe.call({
				method: "cannabis_management.cannabis_management.page.preorder.preorder.submit_preorder",
				args: { name: name },
				freeze: true,
				freeze_message: "Submitting " + name + "\u2026",
				callback: function (r) {
					if (!r.message) return;
					// If this is the entry open in the form, editing it is no
					// longer possible -- drop out of edit mode.
					if (window._po.editing === name) poClear();
					frappe.show_alert({
						message: "Preorder <b>" + poEsc(name) + "</b> submitted",
						indicator: "green",
					});
					poLoadRecent();
				},
			});
		}
	);
}

/* ─────────────────────────────────────────────────────
   SAVE / CLEAR
   ───────────────────────────────────────────────────── */

function poSave() {
	var data = {
		rep_name: document.getElementById("poRepName").value,
		rep_email: document.getElementById("poRepEmail").value,
		rep_phone: document.getElementById("poRepPhone").value,
		brand_name: document.getElementById("poBrandName").value,
		license_name: document.getElementById("poLicenseName").value,
		license_number: document.getElementById("poLicenseNumber").value,
		primary_address: document.getElementById("poAddress").value,
		region: document.getElementById("poRegion").value,
		order_date: document.getElementById("poOrderDate").value,
		requested_delivery_date: document.getElementById("poDeliveryDate").value,
		company: document.getElementById("poCompany").value,
		notes: document.getElementById("poNotes").value,
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
		args: { data: data, name: window._po.editing || null },
		freeze: true,
		freeze_message: window._po.editing ? "Updating preorder..." : "Saving preorder...",
		callback: function (r) {
			if (r.message) {
				var name = r.message.name;
				frappe.show_alert({
					message: "Preorder <b>" + poEsc(name) + "</b> " +
						(r.message.updated ? "updated" : "created") + " &mdash; " +
						'<a href="' + poPdfUrl(name) + '" download="' + poEsc(name) + '.pdf">download PDF</a>',
					indicator: "green",
				}, 10);
				poClear();
				poLoadRecent();
			}
		},
	});
}

function poClear() {
	["poRepName", "poRepEmail", "poRepPhone", "poBrandName", "poLicenseName",
	 "poLicenseNumber", "poAddress", "poNotes", "poDeliveryDate"].forEach(function (id) {
		document.getElementById(id).value = "";
	});
	document.getElementById("poRegion").value = "";
	document.getElementById("poRegionAuto").classList.remove("visible");
	document.getElementById("poCompany").value = "";
	poSetDefaults();
	window._po.items = [];
	window._po.editing = null;
	poRenderItems();
	poSyncEditState();
}

/* ─────────────────────────────────────────────────────
   UTIL
   ───────────────────────────────────────────────────── */

function poEsc(str) {
	if (!str) return "";
	var d = document.createElement("div");
	d.textContent = str;
	return d.innerHTML;
}
