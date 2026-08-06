// Copyright (c) 2026, alltechvirtual.com and contributors
frappe.ui.form.on("Batch", {
	refresh(frm) {
		if (!frm.doc.custom_metrc_tag) return;

		const variance = flt(frm.doc.custom_metrc_variance);
		if (Math.abs(variance) > 0.01) {
			frm.dashboard.add_indicator(
				__("METRC variance: {0}", [format_number(variance, null, 4)]),
				"red"
			);
			frm.dashboard.set_headline(
				`<span style="color:var(--red-600)"><b>${__("METRC")}:</b> ${__(
					"ERPNext holds {0} but METRC holds {1}. Investigate before selling.",
					[
						format_number(flt(frm.doc.custom_metrc_quantity) + variance, null, 4),
						format_number(frm.doc.custom_metrc_quantity, null, 4),
					]
				)}</span>`
			);
		} else if (frm.doc.custom_metrc_package_id) {
			frm.dashboard.add_indicator(__("METRC: in sync"), "green");
		}

		if (frm.doc.custom_metrc_lab_state === "Failed") {
			frm.dashboard.add_indicator(__("Lab: FAILED"), "red");
		} else if (frm.doc.custom_metrc_lab_state === "Passed") {
			frm.dashboard.add_indicator(__("Lab: passed"), "green");
		}

		frm.add_custom_button(
			__("View METRC Tag"),
			() => frappe.set_route("Form", "Metric Tag", frm.doc.custom_metrc_tag),
			__("METRC")
		);
	},
});
