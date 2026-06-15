// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Physical Inventory Verification", {
	onload(frm) {
		// Filter tolling_partner: Company = Motley Terpz, Warehouse Type = Tolling Partner
		frm.set_query("tolling_partner", () => ({
			filters: {
				company: "Motley Terpz",
				warehouse_type: "Tolling Partner"
			}
		}));

		// Filter batch: Company = Motley Terpz
		frm.set_query("batch", () => ({
			filters: { company: "Motley Terpz" }
		}));
	},

	refresh(frm) {
		// Add Physical Verification button only when doc is not submitted
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Physical Verification"), function () {
				physical_verification_fetch(frm);
			});
		}
	}
});

/**
 * Fetch matching Rosin Recording rows based on tolling_partner & batch,
 * then append prime_strain, subprime_strain, subprime_total_tolled,
 * and prime_inventory_total_tolled into the child table.
 */
function physical_verification_fetch(frm) {
	const tolling_partner = frm.doc.tolling_partner;
	const batch = frm.doc.batch;

	if (!tolling_partner || !batch) {
		frappe.msgprint(__("Please set both <b>Tolling Partner</b> and <b>Batch</b> before running Physical Verification."));
		return;
	}

	frappe.call({
		method: "cannabis_management.cannabis_management.doctype.physical_inventory_verification.physical_inventory_verification.get_rosin_recording_data",
		args: {
			tolling_partner: tolling_partner,
			batch: batch
		},
		freeze: true,
		freeze_message: __("Fetching data from Rosin Recording..."),
		callback: function (r) {
			if (!r.message || r.message.length === 0) {
				frappe.msgprint(__("No matching submitted Rosin Recording found for this Tolling Partner and Batch."));
				return;
			}

			// Clear existing child rows
			frm.doc.physical_inventory_verification_child = [];

			r.message.forEach(function (row) {
				const child = frm.add_child("physical_inventory_verification_child");
				child.prime_strain = row.prime_strain;
				child.subprime_strain = row.subprime_strain;
				child.subprime_total_tolled = row.subprime_total_tolled;
				child.prime_inventory_total_tolled = row.prime_inventory_total_tolled;
			});

			frm.refresh_field("physical_inventory_verification_child");
			frappe.msgprint(__("Child table populated with {0} row(s) from Rosin Recording.", [r.message.length]));
		}
	});
}
