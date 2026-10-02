// MT Dispatch on the Delivery Note form.
//
// A note for an order on the dispatch flow is created by the order's "Create
// the Delivery Note" step and submitted by its Release; the server refuses
// either from here. So instead of a Save or Submit that can only fail, the
// form sends the user to that step on the Sales Order, where its dialog lives.

frappe.provide("mt_dispatch_dn");

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		// Administrator saves and submits these notes like any other.
		if (mt_dispatch_dn.is_admin() || frm.doc.docstatus !== 0 || frm.is_new()) return;
		const sales_order = mt_dispatch_dn.sales_order(frm);
		if (!sales_order) return;
		// Hidden until the board says whether core's Submit stands, so it
		// can't be clicked in the moment before.
		if (!frm.doc.__unsaved) frm.page.btn_primary.addClass("hide");
		mt_dispatch_dn.board(sales_order).then((board) => {
			if (!board.enabled) {
				frm.page.btn_primary.removeClass("hide");
				return;
			}
			mt_dispatch_dn.render(frm, sales_order, board);
		});
	},

	// A new note drawn from a dispatch order (Get Items From, a "+" button) is
	// not saved here: its order's step makes it instead.
	before_save(frm) {
		if (mt_dispatch_dn.is_admin() || !frm.is_new()) return;
		const sales_order = mt_dispatch_dn.sales_order(frm);
		if (!sales_order) return;
		return mt_dispatch_dn.board(sales_order).then((board) => {
			if (!board.enabled) return;
			frappe.validated = false;
			frappe.show_alert({
				message: __("Delivery Notes for {0} are made by its Dispatch step. Opening it.", [sales_order]),
				indicator: "blue",
			});
			frappe.flags.mt_dispatch_pending = { sales_order: sales_order, action: "create_delivery_note" };
			frappe.set_route("Form", "Sales Order", sales_order);
		});
	},
});

mt_dispatch_dn.is_admin = function () {
	return frappe.session.user === "Administrator";
};

mt_dispatch_dn.sales_order = function (frm) {
	return (frm.doc.items || []).map((r) => r.against_sales_order).find(Boolean);
};

mt_dispatch_dn.board = function (sales_order) {
	return frappe
		.call({ method: "cannabis_management.mt_dispatch.api.board", args: { sales_order: sales_order } })
		.then((r) => r.message || {});
};

// Steps worth offering from the note, in the order they come up.
mt_dispatch_dn.NEXT = ["upload_manifest", "record_payment", "release", "release_override"];

mt_dispatch_dn.render = function (frm, sales_order, board) {
	// The form may have moved on while the board loaded.
	if (!board.enabled || frm.doc.docstatus !== 0 || frm.is_new()) return;

	const ready = (board.actions || []).filter((a) => !a.blocked);
	const next = mt_dispatch_dn.NEXT.map((name) => ready.find((a) => a.action === name)).find(Boolean);
	const title = (a) => __(frappe.utils.to_title_case(a.label));

	let headline =
		`${__("Dispatch stage")}: <b>${frappe.utils.escape_html(board.stage || __("none"))}</b> · ` +
		__("Release on {0} submits this note.", [frappe.utils.escape_html(sales_order)]);
	(board.actions || [])
		.filter((a) => a.blocked)
		.forEach((a) => {
			headline += `<br><span class="text-warning">${title(a)}: ${frappe.utils.escape_html(a.blocked)}</span>`;
		});
	frm.dashboard.set_headline_alert(headline);

	const open_order = (action) => {
		frappe.flags.mt_dispatch_pending = action ? { sales_order: sales_order, action: action } : null;
		frappe.set_route("Form", "Sales Order", sales_order);
	};

	// Unsaved edits keep core's Save; this refresh runs again after the save.
	if (!frm.doc.__unsaved) {
		frm.page.set_primary_action(next ? title(next) : __("Open {0}", [sales_order]), () =>
			open_order(next && next.action)
		);
	}
	frm.add_custom_button(sales_order, () => open_order(null), __("Dispatch"));
};
