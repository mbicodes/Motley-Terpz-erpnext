// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

const CONNECTION_TOOL_API =
	"cannabis_management.cannabis_management.doctype.connection_tool.connection_tool";

const CONNECTION_STATUS_COLOR = {
	Linked: "blue",
	Broken: "red",
	Relinked: "green",
	Locked: "gray",
};

frappe.ui.form.on("Connection Tool", {
	setup(frm) {
		frm.set_query("reference_doctype", () => ({ filters: { istable: 0, issingle: 0 } }));
		frappe.meta.docfield_map["Connection Tool Link"].status.formatter = (value) =>
			value
				? `<span class="indicator-pill ${CONNECTION_STATUS_COLOR[value] || "gray"}">${__(value)}</span>`
				: "";
	},

	refresh(frm) {
		// rows only ever come from Find Connections
		frm.fields_dict.links.grid.cannot_add_rows = true;
		frm.fields_dict.links.grid.refresh();

		if (frm.is_new()) {
			frm.set_intro(
				__("Pick the document you want to cancel or delete, then Save to list everything linked to it.")
			);
			return;
		}

		frm.set_intro(connection_tool_intro(frm), frm.doc.status === "Broken" ? "orange" : "blue");
		const has = (status) => (frm.doc.links || []).some((r) => r.status === status);
		const doc_label = frm.doc.reference_name;

		frm.add_custom_button(__("Find Connections"), () =>
			connection_tool_call(frm, "find_connections", {}, __("Finding connections..."))
		);
		// Swap btn-default out, or the skin's .btn-default:hover overrides the colour.
		if (has("Linked")) {
			frm.add_custom_button(__("Break Connections"), () => connection_tool_act(frm, "break"))
				.removeClass("btn-default")
				.addClass("btn-danger");
		}
		if (has("Broken")) {
			frm.add_custom_button(__("Make Connections"), () => connection_tool_act(frm, "make"))
				.removeClass("btn-default")
				.addClass("btn-primary");
			frm.add_custom_button(
				__("Use Amended Document"),
				() => connection_tool_use_amended(frm),
				__("Relink To")
			);
			frm.add_custom_button(
				__("Original Document"),
				() => frm.set_value("relink_to", ""),
				__("Relink To")
			);
		}
		if (frm.doc.reference_docstatus === "Submitted") {
			frm.add_custom_button(
				__("Cancel {0}", [doc_label]),
				() => connection_tool_cancel_reference(frm),
				__("Document")
			);
		}
		frm.add_custom_button(
			__("Open {0}", [doc_label]),
			() => frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name),
			__("Document")
		);
	},
});

function connection_tool_intro(frm) {
	const count = (status) => (frm.doc.links || []).filter((r) => r.status === status).length;
	const parts = [];
	if (count("Linked")) parts.push(__("{0} linked", [count("Linked")]));
	if (count("Broken")) parts.push(__("{0} broken", [count("Broken")]));
	if (count("Relinked")) parts.push(__("{0} relinked", [count("Relinked")]));
	if (count("Locked")) parts.push(__("{0} payment link(s) locked", [count("Locked")]));
	const summary = parts.length ? parts.join(", ") + ". " : __("Nothing links to this document. ");
	return (
		summary +
		__(
			"Tick rows to act on only those (none ticked = all). Break, then cancel the document; " +
				"after amending, use Relink To > Use Amended Document and Make Connections."
		)
	);
}

function connection_tool_call(frm, method, args, freeze_message) {
	return frappe
		.call({
			method: `${CONNECTION_TOOL_API}.${method}`,
			args: { name: frm.doc.name, ...args },
			freeze: true,
			freeze_message,
		})
		.then(() => frm.reload_doc());
}

async function connection_tool_act(frm, action) {
	if (frm.is_dirty()) await frm.save();

	const status = action === "break" ? "Linked" : "Broken";
	const ticked = frm.fields_dict.links.grid.get_selected_children().filter((r) => r.status === status);
	const rows = ticked.length ? ticked : (frm.doc.links || []).filter((r) => r.status === status);
	if (!rows.length) {
		frappe.msgprint(__("No rows with status {0}.", [__(status)]));
		return;
	}

	const docs = [...new Set(rows.map((r) => `${r.linked_doctype} ${r.linked_name}`))];
	const target = frm.doc.relink_to || frm.doc.reference_name;
	const message =
		action === "break"
			? __("Remove {0} link(s) to {1} from:", [rows.length, frm.doc.reference_name])
			: __("Point {0} link(s) at {1} in:", [rows.length, target]);

	frappe.confirm(
		`${message}<br><br>${docs.map((d) => frappe.utils.escape_html(d)).join("<br>")}`,
		() =>
			connection_tool_call(
				frm,
				`${action}_connections`,
				{ rows: ticked.length ? rows.map((r) => r.name) : null },
				action === "break" ? __("Breaking connections...") : __("Making connections...")
			)
	);
}

function connection_tool_use_amended(frm) {
	frappe
		.xcall(`${CONNECTION_TOOL_API}.get_latest_amendment`, {
			doctype: frm.doc.reference_doctype,
			name: frm.doc.reference_name,
		})
		.then((amended) => {
			if (!amended) {
				frappe.msgprint(__("{0} has not been amended yet.", [frm.doc.reference_name]));
				return;
			}
			frm.set_value("relink_to", amended);
			frappe.show_alert({ message: __("Relink To set to {0}", [amended]), indicator: "green" });
		});
}

function connection_tool_cancel_reference(frm) {
	const { reference_doctype: doctype, reference_name: name } = frm.doc;
	frappe.confirm(__("Cancel {0} {1}?", [__(doctype), name]), () =>
		frappe
			.xcall("frappe.client.cancel", { doctype, name })
			.then(() => {
				frappe.show_alert({ message: __("{0} cancelled", [name]), indicator: "green" });
				return connection_tool_call(frm, "find_connections", {});
			})
	);
}
