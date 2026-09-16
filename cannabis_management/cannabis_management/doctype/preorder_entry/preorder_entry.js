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

	primary_address(frm) {
		if (!frm.doc.primary_address) return;
		const region = guess_region(frm.doc.primary_address);
		if (region) {
			frm.set_value("region", region);
		}
	},
});

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
