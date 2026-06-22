// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cloning Batch', {
	refresh(frm) {
		frm.trigger('calculate_totals');
	},

	session_date(frm) {
		if (frm.doc.session_date) {
			const year = (new Date(frm.doc.session_date)).getFullYear()
			frm.set_value('season', year.toString())
		}
		frm.trigger('calculate_totals')
	},

	labour_hours(frm) { frm.trigger('calculate_totals'); },
	labour_rate(frm) { frm.trigger('calculate_totals'); },

	mom_plant_details_add(frm) { frm.trigger('calculate_totals'); },
	mom_plant_details_remove(frm) { frm.trigger('calculate_totals'); },
	material_details_add(frm) { frm.trigger('calculate_totals'); },
	material_details_remove(frm) { frm.trigger('calculate_totals'); },
	clone_details_add(frm) { frm.trigger('calculate_totals'); },
	clone_details_remove(frm) { frm.trigger('calculate_totals'); },

	calculate_totals(frm) {
		const f = v => parseFloat(v) || 0;
		let total_moms = 0;
		let total_material_qty = 0;
		let total_material_cost = 0;
		let total_clones = 0;

		(frm.doc.mom_plant_details || []).forEach(r => total_moms += f(r.cuttings_taken));
		(frm.doc.material_details || []).forEach(r => { total_material_qty += f(r.quantity); total_material_cost += f(r.amount); });
		(frm.doc.clone_details || []).forEach(r => total_clones += f(r.quantity));

		frm.set_value('total_mom_plants', total_moms);
		frm.set_value('total_material_quantity', total_material_qty);
		frm.set_value('total_material_cost', total_material_cost);
		frm.set_value('total_clone_quantity', total_clones);
		frm.set_value('total_quantity', total_clones);

		const labour = f(frm.doc.labour_hours) * f(frm.doc.labour_rate);
		frm.set_value('total_labor_cost', labour);
		frm.set_value('total_session_material_cost', total_material_cost);
		frm.set_value('total_clones_produced', Math.floor(total_clones));
		const session_cost = f(labour) + f(total_material_cost);
		frm.set_value('total_session_cost', session_cost);
		frm.set_value('cost_per_clone', (frm.doc.total_clones_produced ? session_cost / frm.doc.total_clones_produced : 0));
	}
});
