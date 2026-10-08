// MT Dispatch: stage buttons on the Sales Order form.
//
// The same transitions as the Slack buttons, through
// cannabis_management.mt_dispatch.api.act. The server decides which buttons
// this user may see (api.board) and re-checks everything on click, so the
// form never has to know the rules.

frappe.provide("mt_dispatch");

const MT_API = "cannabis_management.mt_dispatch.api.";
const MT_GROUP = __("Dispatch");

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		frm._mt_board = null;
		if (frm.doc.docstatus !== 1 || frm.is_new()) return;
		frm._mt_stage = frm.doc.custom_logistic_status;
		frappe.call({
			method: MT_API + "board",
			args: { sales_order: frm.doc.name },
			callback: (r) => {
				frm._mt_board = r.message || {};
				mt_dispatch.render(frm, frm._mt_board);
				mt_dispatch.limit_stage_options(frm, frm._mt_board);
				mt_dispatch.run_pending(frm, frm._mt_board);
			},
		});
	},

	// Picking a stage in the Logistic Status field runs the step that leads
	// there -- the same one the Dispatch menu runs, with its dialogs and
	// checks. The field itself is never saved directly; the server refuses that.
	custom_logistic_status(frm) {
		if (frm._mt_reverting || frm.doc.docstatus !== 1) return;
		const chosen = frm.doc.custom_logistic_status;
		const board = frm._mt_board || {};
		// Company not on dispatch: a plain field, saved with Update like any other.
		if (!board.enabled) return;
		const a = chosen && chosen !== board.stage && mt_dispatch.ready_actions(board).find((x) => x.to === chosen);
		// Administrator may set any stage by hand: a plain field, saved with Update.
		if (!a && board.is_admin) return;
		mt_dispatch.revert_stage(frm);
		if (!chosen || chosen === board.stage) return;

		// The list only offers stages a ready step reaches, so this only misses
		// when the order moved on since the form loaded.
		if (!a) {
			frm.reload_doc();
			return;
		}
		(mt_dispatch.handlers[a.action] || mt_dispatch.confirm_and_run)(frm, a, board);
	},
});

// A step asked for from another form (the Delivery Note's button) opens here,
// where its dialog lives, once the board says it is still ready.
mt_dispatch.run_pending = function (frm, board) {
	const pending = frappe.flags.mt_dispatch_pending;
	if (!pending || pending.sales_order !== frm.doc.name) return;
	frappe.flags.mt_dispatch_pending = null;
	const a = mt_dispatch.ready_actions(board).find((x) => x.action === pending.action);
	if (a) (mt_dispatch.handlers[a.action] || mt_dispatch.confirm_and_run)(frm, a, board);
};

// Steps whose checks pass right now. A blocked step gets no button; its reason
// is shown in the headline instead of as an error after the click.
mt_dispatch.ready_actions = function (board) {
	return (board.actions || []).filter((a) => !a.blocked);
};

// Logistic Status lists the current stage and the stages one ready step away,
// so every pick is a step that will go through.
mt_dispatch.limit_stage_options = function (frm, board) {
	const field = "custom_logistic_status";
	if (!board.enabled || board.is_admin) {
		frm.set_df_property(field, "options", frappe.meta.get_docfield("Sales Order", field).options);
		return;
	}
	const options = [board.stage || ""];
	mt_dispatch.ready_actions(board).forEach((a) => {
		if (a.to && !options.includes(a.to)) options.push(a.to);
	});
	frm.set_df_property(field, "options", options.join("\n"));
};

// A dialog input problem is shown on the field itself, not as a popup.
mt_dispatch.field_error = function (d, fieldname, message) {
	d.get_field(fieldname).set_description(`<span class="text-danger">${message}</span>`);
};

mt_dispatch.revert_stage = function (frm) {
	frm._mt_reverting = true;
	frm.set_value("custom_logistic_status", frm._mt_stage || "").then(() => {
		frm._mt_reverting = false;
		// Undo the "Not Saved" state the pick left behind.
		frm.doc.__unsaved = 0;
		frm.toolbar.refresh();
	});
};

mt_dispatch.render = function (frm, board) {
	if (!board.enabled) return;

	const pay = board.payment || {};
	let headline = `${__("Dispatch stage")}: <b>${frappe.utils.escape_html(board.stage || __("none"))}</b>`;
	if (pay.gated) {
		headline += pay.short
			? ` · <span class="text-danger">${__("COD short")} ${format_currency(pay.short, frm.doc.currency)}</span>`
			: ` · <span class="text-success">${__("COD paid in full")}</span>`;
	}
	const waiting = (board.actions || [])
		.filter((a) => a.blocked)
		.map((a) => `${__(frappe.utils.to_title_case(a.label))}: ${frappe.utils.escape_html(a.blocked)}`);
	[...(board.notes || []).map(frappe.utils.escape_html), ...waiting].forEach((line) => {
		headline += `<br><span class="text-warning">${line}</span>`;
	});
	frm.dashboard.set_headline_alert(headline);

	mt_dispatch.ready_actions(board).forEach((a) => {
		const handler = mt_dispatch.handlers[a.action] || mt_dispatch.confirm_and_run;
		frm.add_custom_button(__(frappe.utils.to_title_case(a.label)), () => handler(frm, a, board), MT_GROUP);
	});
};

mt_dispatch.run = function (frm, action, payload, stage) {
	return frappe.call({
		method: MT_API + "act",
		args: {
			sales_order: frm.doc.name,
			action: action,
			expected_stage: stage,
			payload: payload ? JSON.stringify(payload) : null,
		},
		freeze: true,
		freeze_message: __("Working…"),
		callback: () => {
			frappe.show_alert({ message: __("Done"), indicator: "green" });
			frm.reload_doc();
		},
	});
};

mt_dispatch.confirm_and_run = function (frm, a, board) {
	frappe.confirm(__("{0} for {1}?", [frappe.utils.to_title_case(a.label), frm.doc.name]), () =>
		mt_dispatch.run(frm, a.action, null, board.stage)
	);
};

mt_dispatch.reason_dialog = function (frm, a, board, min_length) {
	const d = new frappe.ui.Dialog({
		title: __(frappe.utils.to_title_case(a.label)),
		fields: [{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
		primary_action_label: __("Confirm"),
		primary_action(v) {
			if (min_length && (v.reason || "").trim().length < min_length) {
				mt_dispatch.field_error(d, "reason", __("Give a reason of at least {0} characters.", [min_length]));
				return;
			}
			d.hide();
			mt_dispatch.run(frm, a.action, { reason: v.reason }, board.stage);
		},
	});
	d.show();
};

mt_dispatch.handlers = {
	hold: (frm, a, board) => mt_dispatch.reason_dialog(frm, a, board),
	release_override: (frm, a, board) => mt_dispatch.reason_dialog(frm, a, board, 15),

	create_conversion(frm) {
		// Conversions are entered on their own form in the ERP; the Slack form
		// is the short path. Prefilled with the order, company and customer.
		frappe.new_doc("Conversion Entry", {
			sales_order: frm.doc.name,
			company: frm.doc.company,
			customer: frm.doc.customer,
		});
	},

	create_delivery_note(frm, a, board) {
		frappe.call({
			method: MT_API + "line_tag_options",
			args: { sales_order: frm.doc.name },
			callback(r) {
				const lines = r.message || {};
				const fields = [];
				Object.keys(lines).forEach((so_detail) => {
					const l = lines[so_detail];
					// A tag is optional here, so a line with none to offer gets no picker.
					if (!board.tags_required && !(l.tags || []).length) return;
					const options = [""].concat((l.tags || []).map((t) => t.muid));
					fields.push({
						fieldname: so_detail,
						fieldtype: "Select",
						label: `${l.item_code} · ${l.qty} · ${l.warehouse || ""}`,
						options: options,
						default: (l.tags || []).length === 1 ? l.tags[0].muid : "",
						description: (l.tags || []).map((t) => `${t.tag_code || t.muid}: ${t.qty}`).join(", ") ||
							__("No Metric Tag holds stock here"),
					});
				});
				if (!fields.length) {
					mt_dispatch.confirm_and_run(frm, a, board);
					return;
				}
				const d = new frappe.ui.Dialog({
					title: __("Create Delivery Note"),
					fields: fields,
					primary_action_label: __("Create draft"),
					primary_action(v) {
						const muid = {};
						Object.keys(lines).forEach((k) => v[k] && (muid[k] = v[k]));
						d.hide();
						mt_dispatch.run(frm, a.action, { muid: muid }, board.stage);
					},
				});
				d.show();
			},
		});
	},

	upload_manifest(frm, a, board) {
		const d = new frappe.ui.Dialog({
			title: __("Upload manifest"),
			fields: [
				{ fieldname: "file_url", fieldtype: "Attach", label: __("Manifest file (PDF, PNG, JPG)"), reqd: 1 },
				{ fieldname: "manifest_number", fieldtype: "Data", label: __("Metrc manifest number"), reqd: 1,
					description: __("10 digits") },
			],
			primary_action_label: __("Upload"),
			primary_action(v) {
				if (!/^\d{10}$/.test((v.manifest_number || "").trim())) {
					mt_dispatch.field_error(d, "manifest_number", __("The manifest number must be 10 digits."));
					return;
				}
				d.hide();
				mt_dispatch.run(frm, a.action, { file_url: v.file_url, manifest_number: v.manifest_number.trim() }, board.stage);
			},
		});
		d.show();
	},

	record_payment(frm, a, board) {
		const pay = board.payment || {};
		const d = new frappe.ui.Dialog({
			title: __("Record payment"),
			fields: [
				{ fieldname: "amount", fieldtype: "Currency", label: __("Amount"), reqd: 1,
					default: Math.max((pay.required || 0) - (pay.paid || 0), 0) },
				{ fieldname: "mode_of_payment", fieldtype: "Link", options: "Mode of Payment", label: __("Mode of payment"), reqd: 1 },
				{ fieldname: "reference_no", fieldtype: "Data", label: __("Reference no") },
				{ fieldname: "reference_date", fieldtype: "Date", label: __("Date"), default: frappe.datetime.get_today() },
				{ fieldname: "file_url", fieldtype: "Attach", label: __("Photo") },
			],
			primary_action_label: __("Record"),
			primary_action(v) {
				d.hide();
				mt_dispatch.run(frm, a.action, v, board.stage);
			},
		});
		d.show();
	},

	mark_delivered(frm, a, board) {
		const d = new frappe.ui.Dialog({
			title: __("Confirm delivery"),
			fields: [
				{ fieldname: "file_url", fieldtype: "Attach", label: __("Signed manifest photo") },
				{ fieldname: "reason", fieldtype: "Small Text", label: __("Note") },
			],
			primary_action_label: __("Confirm"),
			primary_action(v) {
				d.hide();
				mt_dispatch.run(frm, a.action, v, board.stage);
			},
		});
		d.show();
	},
};
