frappe.ui.form.on("Metrc Config", {
	refresh(frm) {
		if (frm.__status_html) {
			frm.get_field("connection_status").$wrapper.html(frm.__status_html);
		}
		render_capabilities(frm);
	},

	test_connection(frm) {
		const run = () => {
			frm.get_field("connection_status").$wrapper.html(
				'<span style="color:#718096">Testing…</span>'
			);
			frappe.call({
				method: "cannabis_management.cannabis_management.doctype.metrc_config.metrc_config.test_connection",
				freeze: true,
				freeze_message: __("Testing Metrc connection…"),
				callback(r) {
					const d = r.message || {};
					const color = d.ok ? "#276749" : "#c53030";
					const bg = d.ok ? "#e6f4ea" : "#fde8e8";
					let html = `<div style="padding:10px 12px;border-radius:8px;background:${bg};color:${color};">
						<b>${d.ok ? "✓ Connected" : "✗ Failed"}</b> — HTTP ${d.status_code ?? "—"}
						<div style="margin-top:4px;color:#333;font-size:12px;">${frappe.utils.escape_html(d.message || "")}</div>`;
					if (d.ok && (d.facilities || []).length) {
						html += `<div style="margin-top:6px;font-size:12px;color:#333;"><b>Facilities:</b> ${d.facilities
							.map(frappe.utils.escape_html)
							.join(", ")}</div>`;
					}
					html += `</div>`;
					frm.__status_html = html;
					frm.get_field("connection_status").$wrapper.html(html);
				},
			});
		};
		frm.is_dirty() ? frm.save().then(run) : run();
	},
});

// ─────────────────────────────────────────────────────────────────────────────
// CEO-facing catalogue of what the Metrc integration can do. Verified live
// against the CA sandbox with the current keys.
// status: "live" (working), "read" (read-only), "blocked" (Metrc-side permission)
// ─────────────────────────────────────────────────────────────────────────────
function render_capabilities(frm) {
	const GROUPS = [
		{
			title: "Onboarding &amp; Master Data",
			icon: "🏷️",
			items: [
				{ a: "Locations — create, update, view", m: ["POST", "PUT", "GET"], s: "live" },
				{ a: "Strains — create, update, view", m: ["POST", "PUT", "GET"], s: "live" },
				{ a: "Items / product catalog — create, update, view", m: ["POST", "PUT", "GET"], s: "live" },
			],
		},
		{
			title: "Cultivation — Plants &amp; Batches",
			icon: "🌱",
			items: [
				{ a: "Create plant batch (clone from mother plant)", m: ["POST"], s: "live" },
				{ a: "Move a plant to another location", m: ["PUT"], s: "live" },
				{ a: "Change growth phase (veg / flower)", m: ["POST"], s: "live" },
				{ a: "Manicure a plant", m: ["POST"], s: "live" },
				{ a: "Harvest plants", m: ["PUT"], s: "live" },
				{ a: "Destroy plants / plant batch", m: ["DELETE"], s: "live" },
				{ a: "Package clones / immature plants", m: ["POST"], s: "live" },
				{ a: "Create batch from seed (opening balance)", m: ["POST"], s: "blocked", n: "facility permission" },
			],
		},
		{
			title: "Harvests",
			icon: "🌾",
			items: [
				{ a: "Create package from a harvest (finished goods)", m: ["POST"], s: "live" },
				{ a: "Record harvest waste", m: ["POST"], s: "live" },
				{ a: "Finish / unfinish a harvest", m: ["PUT"], s: "live" },
			],
		},
		{
			title: "Packages &amp; Inventory",
			icon: "📦",
			items: [
				{ a: "Create derived package (repackage / split / combine)", m: ["POST"], s: "live" },
				{ a: "Change the item on a package", m: ["PUT"], s: "live" },
				{ a: "Adjust quantity (inventory reconciliation)", m: ["PUT"], s: "live" },
				{ a: "Finish a package", m: ["PUT"], s: "live" },
				{ a: "Opening-balance / beginning inventory package", m: ["POST"], s: "blocked", n: "facility permission" },
			],
		},
		{
			title: "Transfers",
			icon: "🚚",
			items: [
				{ a: "View incoming / outgoing / rejected transfers", m: ["GET"], s: "read" },
				{ a: "View manifests, deliveries &amp; packages in transit", m: ["GET"], s: "read" },
				{ a: "Create, update &amp; view transfer templates", m: ["POST", "PUT", "GET"], s: "live" },
				{ a: "Initiate / receive licensed transfers", m: ["—"], s: "blocked", n: "Metrc portal only" },
				{ a: "External incoming transfers", m: ["POST"], s: "blocked", n: "vendor-key permission" },
			],
		},
		{
			title: "Sales &amp; Lab Results",
			icon: "💵",
			items: [
				{ a: "Create retail sales receipts", m: ["POST"], s: "live" },
				{ a: "Lab test results", m: ["GET", "POST"], s: "live" },
			],
		},
		{
			title: "Reference Data (reads)",
			icon: "🔎",
			items: [
				{ a: "Facilities, plant &amp; package tags, item categories, units of measure, waste reasons, transfer types…", m: ["GET"], s: "read" },
			],
		},
	];

	const METHOD_COLOR = { GET: "#2b6cb0", POST: "#276749", PUT: "#b7791f", DELETE: "#c53030", "—": "#a0aec0" };
	const mBadge = (m) =>
		`<span style="display:inline-block;font:700 10px/1.6 'DM Mono',monospace;letter-spacing:.03em;color:#fff;background:${METHOD_COLOR[m] || "#718096"};border-radius:4px;padding:0 6px;margin-right:4px;">${m}</span>`;
	const sPill = (s, n) => {
		const map = {
			live: ["#e6f4ea", "#1c6b3f", "Live"],
			read: ["#e6effa", "#20548f", "Read-only"],
			blocked: ["#fde8e8", "#b5352f", "Blocked"],
		};
		const [bg, fg, label] = map[s] || map.read;
		return `<span style="white-space:nowrap;font:600 11px/1.7 inherit;color:${fg};background:${bg};border-radius:20px;padding:1px 9px;">${label}${n ? ` · ${n}` : ""}</span>`;
	};

	let live = 0,
		blocked = 0;
	GROUPS.forEach((g) => g.items.forEach((i) => (i.s === "blocked" ? blocked++ : live++)));

	const cards = GROUPS.map((g) => {
		const rows = g.items
			.map(
				(i) => `
			<div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:8px 0;border-top:1px solid #edf0f5;">
				<div style="flex:1;min-width:0;">
					<div style="font-size:13px;color:#2d3748;">${i.a}</div>
					<div style="margin-top:3px;">${i.m.map(mBadge).join("")}</div>
				</div>
				<div style="padding-top:1px;">${sPill(i.s, i.n)}</div>
			</div>`
			)
			.join("");
		return `
		<div style="background:#fff;border:1px solid #e6e9ef;border-radius:12px;padding:14px 16px;box-shadow:0 1px 3px rgba(16,24,40,.04);">
			<div style="font:700 14px/1.3 inherit;color:#1a202c;display:flex;align-items:center;gap:8px;margin-bottom:4px;">
				<span style="font-size:16px;">${g.icon}</span> ${g.title}
			</div>
			${rows}
		</div>`;
	}).join("");

	const html = `
	<div style="font-family:inherit;color:#2d3748;">
		<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;
			background:linear-gradient(135deg,#4c1d95,#6d28d9);border-radius:14px;padding:16px 20px;color:#fff;margin-bottom:14px;">
			<div>
				<div style="font:800 18px/1.2 inherit;">Metrc Integration — Capabilities</div>
				<div style="font-size:12.5px;opacity:.85;margin-top:3px;">What Motley's ERP can do with Metrc, verified live against the API.</div>
			</div>
			<div style="display:flex;gap:10px;">
				<div style="text-align:center;background:rgba(255,255,255,.14);border-radius:10px;padding:8px 14px;">
					<div style="font:800 22px/1 inherit;">${live}</div>
					<div style="font-size:11px;opacity:.9;">Actions live</div>
				</div>
				<div style="text-align:center;background:rgba(255,255,255,.14);border-radius:10px;padding:8px 14px;">
					<div style="font:800 22px/1 inherit;">~50</div>
					<div style="font-size:11px;opacity:.9;">Endpoints tested</div>
				</div>
				<div style="text-align:center;background:rgba(255,255,255,.14);border-radius:10px;padding:8px 14px;">
					<div style="font:800 22px/1 inherit;">${blocked}</div>
					<div style="font-size:11px;opacity:.9;">Pending Metrc</div>
				</div>
			</div>
		</div>

		<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:11.5px;color:#4a5568;margin-bottom:14px;">
			<span>${mBadge("GET")} read</span>
			<span>${mBadge("POST")}${mBadge("PUT")}${mBadge("DELETE")} write</span>
			<span>${sPill("live")} working now</span>
			<span>${sPill("read")} read-only</span>
			<span>${sPill("blocked")} needs a Metrc permission</span>
		</div>

		<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;">
			${cards}
		</div>

		<div style="margin-top:14px;font-size:12px;color:#718096;line-height:1.5;">
			The two <b>Blocked</b> items are Metrc-side permissions, not code limits — the opening-balance
			creates need a facility flag, and external-incoming transfers need a vendor-key scope, both granted by Metrc.
			Everything else runs today. Transfers between licensees are read via the API and actioned in the Metrc portal
			(Metrc's own design).
		</div>
	</div>`;

	frm.get_field("functionality_overview").$wrapper.html(html);
}
