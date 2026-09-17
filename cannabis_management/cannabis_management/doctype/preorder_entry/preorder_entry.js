frappe.ui.form.on("Preorder Entry", {
	setup(frm) {
		frm.set_query("item_code", "items", function () {
			return {
				filters: {
					item_group: [
						"in",
						[
							"Packaged goods",
							"0.5g O2 Vape",
							"0.5G Vapes (Packaged)",
							"1g Jarred Rosin",
							"1g O2 Vapes",
							"1G Vapes (Packaged)",
							"3g Jarred Rosin",
						],
					],
					disabled: 0,
				},
			};
		});
	},

	refresh(frm) {
		frm.add_custom_button(__("Create Item"), function () {
			frappe.new_doc("Item", {
				item_group: "Packaged goods",
				is_stock_item: 1,
			});
		}, __("Actions"));
	},

	primary_address(frm) {
		if (!frm.doc.primary_address) return;
		const region = guess_region(frm.doc.primary_address);
		if (region) {
			frm.set_value("region", region);
		}
	},
});

frappe.ui.form.on("Preorder Item", {
	qty(frm, cdt, cdn) {
		calc_amount(frm, cdt, cdn);
	},
	rate(frm, cdt, cdn) {
		calc_amount(frm, cdt, cdn);
	},
	item_code(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.item_code) {
			frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: "Item Price",
					filters: {
						item_code: row.item_code,
						selling: 1,
					},
					fieldname: "price_list_rate",
				},
				callback(r) {
					if (r.message && r.message.price_list_rate) {
						frappe.model.set_value(cdt, cdn, "rate", r.message.price_list_rate);
					}
				},
			});
		}
	},
});

function calc_amount(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let amount = flt(row.qty) * flt(row.rate);
	frappe.model.set_value(cdt, cdn, "amount", amount);
}

function guess_region(address) {
	const zip_match = address.match(/\b(9\d{4})\b/);
	if (!zip_match) return "";
	const zip = parseInt(zip_match[1]);

	if (zip >= 90000 && zip <= 91599) return "LA";
	if (zip >= 91600 && zip <= 91899) return "IE";
	if (zip >= 91900 && zip <= 92199) return "San Diego";
	if (zip >= 92200 && zip <= 92599) return "IE";
	if (zip >= 92600 && zip <= 92899) return "OC";
	if (zip >= 93000 && zip <= 93999) return "Central Valley";
	if (zip >= 94000 && zip <= 94999) return "Bay Area";
	if (zip >= 95000 && zip <= 96199) return "NorCal";
	return "Other";
}
