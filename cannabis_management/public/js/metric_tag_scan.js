// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt
//
// Scan-to-select for Metric Tag.
//
// On Purchase Receipt, Delivery Note, Stock Entry, Stock Reconciliation (the
// doctypes where the "Muid" Inventory Dimension tracks quantity per physical
// tag — see metric_tag.py) and Sales Order, typing or scanning a Metric
// Tag's Tag Code or MUID into the item table's standard "Scan Barcode" field
// now opens a picker of every item + strain currently in stock under that
// tag (a physical tag can be reused over its lifetime, so more than one
// match is normal) instead of falling through to "Cannot find Item with
// this Barcode". Picking a row fills a fresh item-table row with that item,
// batch (which carries the strain via its custom_strain_name field),
// warehouse and — on the four stock doctypes, which alone carry the
// dimension field — the tag itself. Sales Order Item has no such field
// (Sales Order never touches the Stock Ledger), so there the row only gets
// item_code and warehouse.
//
// This works by patching erpnext.utils.BarcodeScanner.prototype.process_scan
// once, globally — it defers to the original barcode/serial/batch flow for
// every other doctype, and for these five falls back to it too whenever the
// scanned value isn't a known Metric Tag.
//
// The `lookup`/`render_picker` pair below is also reused as-is by
// conversion_entry.js, whose "Scan Metric Tag" field has no BarcodeScanner
// and a fixed-slot (not row-per-item) child table, so it applies a selected
// row itself instead of going through apply_row here.

frappe.provide("cannabis_management.metric_tag_scan");

(function () {
	const METRIC_TAG_DOCTYPES = [
		"Purchase Receipt",
		"Delivery Note",
		"Stock Entry",
		"Stock Reconciliation",
		"Sales Order",
	];
	const SCAN_METHOD = "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.get_metric_tag_scan";

	// Resolve `search_value` to a Metric Tag via get_metric_tag_scan. Never
	// rejects — any failure (network hiccup, an unexpected server error)
	// resolves as {found: false} so callers can always fall back safely
	// instead of being left with a dead-looking input (see
	// get_metric_tag_scan's docstring for why a hard failure here once broke
	// normal barcode scanning entirely for some users).
	cannabis_management.metric_tag_scan.lookup = function (search_value, child_doctype) {
		try {
			return frappe
				.call({
					method: SCAN_METHOD,
					args: { search_value, child_doctype },
					error: () => {},
				})
				.then((r) => (r && r.message) || { found: false })
				.catch(() => ({ found: false }));
		} catch (e) {
			console.error(e);
			return Promise.resolve({ found: false });
		}
	};

	// Show a picker for `data.rows` (from lookup()) and call on_select(row)
	// with whichever the user (or, for a single match, the code) picks — the
	// row's `qty` reflects whatever the user edited it to in the popup, not
	// necessarily the tag's full available quantity.
	//
	// A tag that resolved (data.found) but has no rows at all — the normal
	// case for a fresh/just-registered physical tag that has never carried
	// stock yet, e.g. the first time it's scanned on a Purchase Receipt —
	// calls on_select(null) instead of dead-ending with nothing to pick;
	// callers apply that by tagging a blank row for the user to fill in by
	// hand rather than silently doing nothing (which is what made scanning a
	// fresh tag look like "it doesn't work" on receiving-side doctypes).
	cannabis_management.metric_tag_scan.render_picker = function (data, on_select) {
		const rows = data.rows || [];
		if (!rows.length) {
			on_select(null);
			return;
		}

		if (rows.length === 1) {
			on_select(rows[0]);
			return;
		}

		const d = new frappe.ui.Dialog({
			title: __("Metric Tag {0} — select Item / Strain", [data.tag_name]),
			size: "large",
			fields: [{ fieldname: "picker", fieldtype: "HTML" }],
		});

		const $table = $(`
			<table class="table table-bordered" style="margin-bottom:0;">
				<thead>
					<tr>
						<th>${__("Item")}</th>
						<th>${__("Strain")}</th>
						<th>${__("Batch")}</th>
						<th>${__("Warehouse")}</th>
						<th class="text-right" style="width:140px;">${__("Qty")}</th>
						<th style="width:1px;"></th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
		`);

		rows.forEach((row, idx) => {
			$(`
				<tr data-idx="${idx}">
					<td>${frappe.utils.escape_html(row.item_name || row.item_code)}
						<br><span class="text-muted small">${frappe.utils.escape_html(row.item_code)}</span></td>
					<td>${frappe.utils.escape_html(row.strain || "")}</td>
					<td>${frappe.utils.escape_html(row.batch_no || "")}</td>
					<td>${frappe.utils.escape_html(row.warehouse || "")}</td>
					<td class="text-right">
						<input type="number" step="any" class="form-control input-sm qty-input"
							value="${row.qty}" style="display:inline-block; width:90px; text-align:right;">
						${frappe.utils.escape_html(row.uom || "")}
					</td>
					<td><button class="btn btn-xs btn-primary select-row-btn">${__("Select")}</button></td>
				</tr>
			`).appendTo($table.find("tbody"));
		});

		d.fields_dict.picker.$wrapper.empty().append($table);
		$table.find(".select-row-btn").on("click", function () {
			const $row = $(this).closest("tr");
			const idx = $row.data("idx");
			const edited_qty = flt($row.find(".qty-input").val());
			on_select(Object.assign({}, rows[idx], { qty: edited_qty }));
			d.hide();
		});

		d.show();
	};

	const patch_barcode_scanner = () => {
		if (!(window.erpnext && erpnext.utils && erpnext.utils.BarcodeScanner)) {
			setTimeout(patch_barcode_scanner, 500);
			return;
		}
		if (erpnext.utils.BarcodeScanner.prototype.process_scan._patchedByCannabis) return;

		const original_process_scan = erpnext.utils.BarcodeScanner.prototype.process_scan;

		erpnext.utils.BarcodeScanner.prototype.process_scan = function () {
			if (!METRIC_TAG_DOCTYPES.includes(this.frm.doctype)) {
				return original_process_scan.call(this);
			}

			const input = (this.scan_barcode_field.value || "").trim();
			if (!input) return Promise.resolve();

			const child_doctype = this.frm.fields_dict[this.items_table_name || "items"].grid.doctype;
			const barcode_scanner = this;

			return cannabis_management.metric_tag_scan.lookup(input, child_doctype).then((data) => {
				if (data && data.found) {
					barcode_scanner.scan_barcode_field.set_value("");
					cannabis_management.metric_tag_scan.render_picker(data, (row) =>
						apply_row(barcode_scanner, data, child_doctype, row)
					);
					return;
				}
				// Not a Metric Tag — let the normal barcode/serial/batch scan
				// handle it (field still holds the typed value).
				return original_process_scan.call(barcode_scanner);
			});
		};

		erpnext.utils.BarcodeScanner.prototype.process_scan._patchedByCannabis = true;
	};

	patch_barcode_scanner();

	function apply_row(barcode_scanner, data, child_doctype, row) {
		const frm = barcode_scanner.frm;
		const items_fieldname = barcode_scanner.items_table_name || "items";
		const tag_name = data.tag_name;

		let target = (frm.doc[items_fieldname] || []).find((r) => !r.item_code);
		if (!target) {
			target = frappe.model.add_child(frm.doc, child_doctype, items_fieldname);
			frm.script_manager.trigger(`${items_fieldname}_add`, target.doctype, target.name);
		}

		const tag_fieldname =
			frm.doctype === "Stock Entry" ? data.source_fieldname : data.row_tag_fieldname;

		if (!row) {
			// Tag resolved but has no stock yet (a fresh/just-registered tag —
			// the normal case the first time it's ever scanned on a receiving
			// doctype). Nothing to look an item up from, so just tag the row
			// and leave item/qty/warehouse for the user to fill in by hand
			// instead of silently doing nothing.
			frappe.run_serially([
				() =>
					tag_fieldname
						? frappe.model.set_value(target.doctype, target.name, tag_fieldname, tag_name)
						: null,
				() => {
					frm.refresh_field(items_fieldname);
					frappe.show_alert({
						message: __(
							"Metric Tag {0} has no stock yet — row #{1} tagged; pick the item by hand.",
							[tag_name, target.idx]
						),
						indicator: "blue",
					});
				},
			]);
			return;
		}

		// Set warehouse/batch/qty/tag context *before* item_code, same order
		// the stock BarcodeScanner itself uses — item_code's own change
		// handler fetches item defaults and takes an already-set
		// batch/warehouse/qty into account rather than clobbering it.
		const pre_values = {};

		if (frm.doctype === "Stock Entry") {
			// Stock Entry Detail carries two dimension legs (see
			// metric_tag.get_stock_entry_legs) — stock found under a scanned
			// tag is what we're taking FROM, so it belongs on the source leg,
			// which always keys off the dimension's plain source_fieldname.
			pre_values.s_warehouse = row.warehouse;
		} else if (frappe.meta.has_field(child_doctype, "warehouse")) {
			pre_values.warehouse = row.warehouse;
		}
		// row_tag_fieldname/source_fieldname is resolved server-side against
		// this exact child_doctype's actual schema — see get_row_tag_fieldname.
		if (tag_fieldname) pre_values[tag_fieldname] = tag_name;

		if (row.batch_no && frappe.meta.has_field(child_doctype, "batch_no")) {
			pre_values.batch_no = row.batch_no;
		}
		if (frappe.meta.has_field(child_doctype, "qty")) {
			pre_values.qty = row.qty;
		}

		frappe.run_serially([
			() => frappe.model.set_value(target.doctype, target.name, pre_values),
			() => frappe.model.set_value(target.doctype, target.name, "item_code", row.item_code),
			() => {
				frm.refresh_field(items_fieldname);
				frappe.show_alert({
					message: __("Row #{0}: {1} (qty {2}) set from Metric Tag {3}.", [
						target.idx,
						row.item_code,
						row.qty,
						tag_name,
					]),
					indicator: "green",
				});
			},
		]);
	}
})();
