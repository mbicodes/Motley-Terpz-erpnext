// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Metrc Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => test_connection(frm));
		frm.add_custom_button(__("Import Facilities"), () => import_facilities(frm), __("Setup"));
		frm.add_custom_button(__("Sync Now"), () => sync_now(frm), __("Actions"));
		frm.add_custom_button(__("Drain Outbox"), () => drain_outbox(frm), __("Actions"));
		frm.add_custom_button(
			__("Sync State"),
			() => frappe.set_route("List", "Metrc Sync State"),
			__("View")
		);
		frm.add_custom_button(
			__("Outbox"),
			() => frappe.set_route("List", "Metrc Outbox"),
			__("View")
		);
		frm.add_custom_button(
			__("API Log"),
			() => frappe.set_route("List", "Metrc API Log"),
			__("View")
		);

		render_status(frm);
		warn_on_production(frm);
	},

	environment(frm) {
		warn_on_production(frm);
	},
});

function warn_on_production(frm) {
	if (frm.doc.environment !== "Production") return;
	frm.dashboard.set_headline(
		`<span style="color:var(--red-600)"><b>${__("PRODUCTION")}</b> — ${__(
			"writes go to the live California state system and cannot be undone via the API."
		)}</span>`
	);
}

function test_connection(frm) {
	frappe.call({
		method: "cannabis_management.metrc.api.test_connection",
		freeze: true,
		freeze_message: __("Contacting METRC..."),
		callback: (r) => {
			const res = r.message || {};
			if (!res.ok) {
				frappe.msgprint({
					title: __("Connection failed"),
					indicator: "red",
					message: `<p>${frappe.utils.escape_html(res.message || "")}</p>
						<p>${__("Check the integrator key, the facility user key, and that Environment matches the keys you were issued.")}</p>`,
				});
				return;
			}

			const rows = (res.facilities || [])
				.map(
					(f) => `<tr>
						<td>${frappe.utils.escape_html(f.license_number || "")}</td>
						<td>${frappe.utils.escape_html(f.name || "")}</td>
						<td>${frappe.utils.escape_html(f.license_type || "")}</td>
						<td>${f.mapped_warehouse ? frappe.utils.escape_html(f.mapped_warehouse) : "<i>unmapped</i>"}</td>
					</tr>`
				)
				.join("");

			let warning = "";
			if ((res.unreachable_configured || []).length) {
				warning = `<p style="color:var(--red-600)"><b>${__("Configured but unreachable")}:</b>
					${frappe.utils.escape_html(res.unreachable_configured.join(", "))}</p>`;
			}

			frappe.msgprint({
				title: __("Connected — {0}", [res.environment]),
				indicator: "green",
				message: `<p><b>${res.facility_count}</b> ${__("facility(ies) reachable at")}
					<code>${frappe.utils.escape_html(res.base_url)}</code></p>
					${warning}
					<table class="table table-bordered table-sm">
						<thead><tr><th>${__("License")}</th><th>${__("Name")}</th>
						<th>${__("Type")}</th><th>${__("Warehouse")}</th></tr></thead>
						<tbody>${rows}</tbody></table>`,
			});
		},
	});
}

function import_facilities(frm) {
	frappe.call({
		method: "cannabis_management.metrc.api.import_facilities",
		freeze: true,
		callback: (r) => {
			frappe.show_alert({ message: (r.message || {}).message, indicator: "blue" });
			frm.reload_doc();
		},
	});
}

function sync_now(frm) {
	frappe.confirm(__("Run a full METRC sync in the background?"), () => {
		frappe.call({
			method: "cannabis_management.metrc.api.sync_now",
			callback: (r) =>
				frappe.show_alert({ message: (r.message || {}).message, indicator: "blue" }),
		});
	});
}

function drain_outbox(frm) {
	frappe.call({
		method: "cannabis_management.metrc.api.drain_outbox",
		callback: (r) =>
			frappe.show_alert({ message: (r.message || {}).message, indicator: "blue" }),
	});
}

function render_status(frm) {
	if (!frm.doc.enabled) {
		frm.get_field("connection_status").$wrapper.html(
			`<div class="text-muted">${__("Integration is disabled.")}</div>`
		);
		return;
	}

	frappe.call({
		method: "cannabis_management.metrc.api.sync_status",
		callback: (r) => {
			const s = r.message;
			if (!s) return;

			const mode = [
				s.environment,
				s.push_enabled ? __("push on") : __("pull only"),
				s.dry_run ? __("DRY RUN") : null,
			]
				.filter(Boolean)
				.join(" · ");

			const ob = s.outbox || {};
			const v = s.variance || {};

			const card = (label, value, color) => `
				<div style="display:inline-block;min-width:110px;margin:0 12px 10px 0">
					<div style="font-size:20px;font-weight:600;color:var(--${color}-600)">${value}</div>
					<div class="text-muted" style="font-size:11px">${label}</div>
				</div>`;

			const cursors = (s.cursors || [])
				.map(
					(c) => `<tr>
						<td>${frappe.utils.escape_html(c.license_number || "")}</td>
						<td>${frappe.utils.escape_html(c.endpoint_key || "")}</td>
						<td>${c.cursor_last_modified ? frappe.datetime.str_to_user(c.cursor_last_modified) : "—"}</td>
						<td>${frappe.utils.escape_html(c.last_status || "—")}</td>
						<td align="right">${c.records_synced || 0}</td>
					</tr>`
				)
				.join("");

			frm.get_field("connection_status").$wrapper.html(`
				<div style="padding:4px 0 8px"><b>${frappe.utils.escape_html(mode)}</b></div>
				<div style="margin-bottom:6px">
					${card(__("Queued"), ob.Queued || 0, "orange")}
					${card(__("Parked"), ob.Parked || 0, "red")}
					${card(__("Variances"), v.variances || 0, "red")}
					${card(__("Untagged stock"), v.untagged_stock || 0, "red")}
					${card(__("Orphan tags"), v.orphan_tags || 0, "orange")}
					${card(__("Unmapped items"), v.unmatched_items || 0, "orange")}
				</div>
				${
					cursors
						? `<table class="table table-bordered table-sm" style="font-size:12px">
							<thead><tr><th>${__("License")}</th><th>${__("Endpoint")}</th>
							<th>${__("Cursor")}</th><th>${__("Status")}</th><th>${__("Records")}</th></tr></thead>
							<tbody>${cursors}</tbody></table>`
						: `<div class="text-muted">${__("No sync has run yet.")}</div>`
				}
			`);
		},
	});
}
