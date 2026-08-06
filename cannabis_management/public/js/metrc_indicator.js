// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

/**
 * Shared METRC form UX.
 *
 * Every document that pushes to Metrc gets the same three affordances, so the
 * integration behaves identically wherever a user meets it:
 *
 *   1. A status indicator in the form header - the answer to "is this
 *      reported?" without opening a section.
 *   2. A "METRC" button group with Resync and View Log.
 *   3. An inline alert when a push is Failed or Parked, because a silent
 *      compliance gap is the failure mode that matters.
 */

frappe.provide("cannabis_management.metrc");

cannabis_management.metrc.STATUS_COLOR = {
	Synced: "green",
	Queued: "orange",
	"In Progress": "blue",
	Failed: "red",
	Parked: "red",
	"Not Tracked": "gray",
};

cannabis_management.metrc.setup_form = function (frm, opts) {
	opts = opts || {};
	const status = frm.doc.custom_metrc_sync_status;

	if (frm.doc.docstatus !== 1 || !status) return;

	// 1. Header indicator
	const color = cannabis_management.metrc.STATUS_COLOR[status] || "gray";
	frm.dashboard.add_indicator(__("METRC: {0}", [__(status)]), color);

	// 2. Inline alert for the states that need action
	if (["Failed", "Parked"].includes(status)) {
		const msg = frm.doc.custom_metrc_message || __("No detail recorded.");
		frm.dashboard.set_headline(
			`<span style="color:var(--red-600)">
				<b>${__("METRC sync {0}", [__(status)])}:</b> ${frappe.utils.escape_html(msg)}
			</span>`
		);
	}

	// 3. Buttons
	const group = __("METRC");

	frm.add_custom_button(
		__("Resync"),
		() => {
			frappe.confirm(
				__("Re-queue this document for METRC and process it now?"),
				() => {
					frappe.call({
						method: "cannabis_management.metrc.api.resync_document",
						args: { doctype: frm.doctype, name: frm.doc.name },
						freeze: true,
						freeze_message: __("Talking to METRC..."),
						callback: (r) => {
							const res = r.message || {};
							frappe.show_alert({
								message: __("METRC: {0}", [res.custom_metrc_sync_status || "—"]),
								indicator:
									cannabis_management.metrc.STATUS_COLOR[
										res.custom_metrc_sync_status
									] || "gray",
							});
							frm.reload_doc();
						},
					});
				}
			);
		},
		group
	);

	frm.add_custom_button(
		__("View METRC Log"),
		() => {
			frappe.set_route("List", "Metrc API Log", {
				reference_doctype: frm.doctype,
				reference_name: frm.doc.name,
			});
		},
		group
	);

	frm.add_custom_button(
		__("View Outbox"),
		() => {
			frappe.set_route("List", "Metrc Outbox", {
				reference_doctype: frm.doctype,
				reference_name: frm.doc.name,
			});
		},
		group
	);
};

/**
 * Warn on item rows that will fail the push, at entry time rather than at
 * submit. A tracked item with no tagged batch is the single most common cause
 * of a parked outbox row.
 */
cannabis_management.metrc.check_rows = function (frm, table_field) {
	table_field = table_field || "items";
	const rows = frm.doc[table_field] || [];
	if (!rows.length) return;

	const codes = rows.map((r) => r.item_code).filter(Boolean);
	if (!codes.length) return;

	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Item",
			filters: { name: ["in", codes], custom_metrc_tracked: 1 },
			fields: ["name"],
			limit_page_length: 0,
		},
		callback: (r) => {
			const tracked = new Set((r.message || []).map((i) => i.name));
			if (!tracked.size) return;

			const missing = rows
				.filter((row) => tracked.has(row.item_code) && !row.batch_no)
				.map((row) => `${__("Row")} ${row.idx}: ${row.item_code}`);

			if (missing.length) {
				frm.dashboard.set_headline(
					`<span style="color:var(--orange-600)">
						<b>${__("METRC")}:</b>
						${__("These rows are METRC-tracked but have no Batch, so they cannot be reported")}
						— ${frappe.utils.escape_html(missing.join(", "))}
					</span>`
				);
			}
		},
	});
};
