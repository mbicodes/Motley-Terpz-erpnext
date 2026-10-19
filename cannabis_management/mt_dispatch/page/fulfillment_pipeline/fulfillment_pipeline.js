// Fulfillment Pipeline: open Sales Orders as cards, one column per Logistic
// Status. Backend: cannabis_management.mt_dispatch.fulfillment_board.
(function () {
	const API = "cannabis_management.mt_dispatch.fulfillment_board.";
	const STAGE_COLORS = {
		"Order Received": "#64748b",
		"Awaiting Conversion": "#c0392b",
		"Order Preparing": "#2563eb",
		"Order Prepared": "#0891b2",
		"Delivery Note Ready": "#7c3aed",
		"Awaiting Release": "#b26a00",
		Released: "#1f8f4e",
		"On Hold": "#991b1b",
		Cancelled: "#991b1b",
	};
	const ON_HOLD = "On Hold";
	const WATCH = ["Sales Order", "Conversion Entry", "Delivery Note", "Sales Invoice", "Stock Reservation Entry"];
	const POLL_MS = 60000;

	const esc = (s) =>
		String(s == null ? "" : s).replace(
			/[&<>"']/g,
			(c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
		);
	const num = (v) => {
		const n = Math.round((Number(v) || 0) * 1000) / 1000;
		return n.toLocaleString(undefined, { maximumFractionDigits: 3 });
	};
	const qty = (v, uom) => num(v) + (uom ? " " + uom : "");

	// "2026-10-15 09:38:00.123" -> local Date, ignoring the zone; the server's
	// own "now" is parsed the same way, so the offset cancels out.
	function parse_dt(s) {
		const m = String(s || "").match(/(\d+)-(\d+)-(\d+)(?:[ T](\d+):(\d+):?(\d+)?)?/);
		if (!m) return null;
		return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
	}
	function md(s) {
		const d = parse_dt(s);
		return d ? d.getMonth() + 1 + "/" + d.getDate() : "";
	}
	// M/D, plus /YY when the date is not in the same year as `today`.
	function md_y(s, today) {
		const d = parse_dt(s),
			t = parse_dt(today);
		if (!d) return "-";
		const base = d.getMonth() + 1 + "/" + d.getDate();
		return t && t.getFullYear() !== d.getFullYear() ? base + "/" + String(d.getFullYear()).slice(-2) : base;
	}
	// Delivery date in the ERP's own date format (System Settings), e.g. 07-16-2026.
	function due_date(c) {
		return c.due ? frappe.datetime.str_to_user(c.due) : "-";
	}
	function day_index(s) {
		const m = String(s || "").match(/(\d+)-(\d+)-(\d+)/);
		return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) / 86400000 : null;
	}

	class FulfillmentPipeline {
		constructor(page, wrapper) {
			this.page = page;
			this.wrapper = wrapper;
			this.view = "open";
			this.open_cards = [];
			this.cx_cards = [];
			this.cx_count = 0;
			this.stages = [];
			this.can_edit = false;
			this.today = frappe.datetime.get_today();
			this.offset = 0;
			this.drag_so = null;
			this.pop_so = null;
			this.loading = false;
			this.loaded_at = 0;
			this.dirty = false;
			this.pending = {};

			this.page.set_secondary_action(__("Refresh"), () => this.load(), "refresh");
			// Back to the Sales Order list (which has a button to come here).
			this.page.add_inner_button(__("Sales Orders"), () => frappe.set_route("List", "Sales Order"));
			this.make_layout();
			this.bind_events();
			this.bind_realtime();
			this.load();
			this.poll = setInterval(() => {
				if (this.is_visible() && !this.busy()) this.load(true);
			}, POLL_MS);
		}

		// ── layout ──────────────────────────────────────────────────────────

		make_layout() {
			this.$root = $(`
				<div class="fp-root">
					<div class="fp-top">
						<div class="fp-top-row">
							<div class="fp-sub">${__(
								"Open sales orders, oldest first. Drag a card to change its Logistic Status."
							)}</div>
							<div class="fp-spacer"></div>
							<div class="fp-stats"></div>
						</div>
						<div class="fp-filters">
							<input class="fp-q" type="search" placeholder="${__(
								"Search customer, order #, strain"
							)}">
							<select class="fp-f-co"><option value="">${__("All companies")}</option></select>
							<select class="fp-f-type">
								<option value="">${__("Pickup + Dropoff")}</option>
								<option value="Pickup">${__("Pickup")}</option>
								<option value="Dropoff">${__("Dropoff")}</option>
							</select>
							<select class="fp-f-conv">
								<option value="">${__("Any stock")}</option>
								<option value="no">${__("Conversion required")}</option>
								<option value="ok">${__("No conversion required")}</option>
							</select>
							<select class="fp-f-due">
								<option value="">${__("Any delivery date")}</option>
								<option value="late">${__("Overdue")}</option>
								<option value="today">${__("Due today")}</option>
							</select>
							<div class="fp-tabs">
								<button class="fp-tab on" data-view="open">${__("Open pipeline")}</button>
								<button class="fp-tab" data-view="cancelled">${__(
									"Cancelled"
								)} <span class="fp-cxn"></span></button>
							</div>
						</div>
					</div>
					<div class="fp-ro" style="display:none">${__(
						"Read-only view: your role can see the board and print pull sheets."
					)}</div>
					<div class="fp-board"><div class="fp-loading">${__("Loading orders…")}</div></div>
				</div>`).appendTo(this.page.main);
			this.$board = this.$root.find(".fp-board");
			this.$pop = $('<div class="fp-pop"></div>').appendTo(document.body);
		}

		// ── data ────────────────────────────────────────────────────────────

		load(quiet) {
			if (this.loading) return;
			this.loading = true;
			const view = this.view;
			frappe
				.xcall(API + "get_board", { view })
				.then((m) => {
					const server_now = parse_dt(m.now);
					if (server_now) this.offset = Date.now() - server_now.getTime();
					this.today = m.today;
					this.stages = m.stages;
					this.can_edit = !!m.can_edit;
					this.can_reserve = !!m.can_reserve;
					this.cx_count = m.cancelled_count;
					if (m.view === "cancelled") this.cx_cards = m.cards;
					else this.open_cards = m.cards;
					this.loaded_at = Date.now();
					this.dirty = false;
					if (view === this.view) this.render();
				})
				.catch(() => {
					if (!quiet) this.$board.html(`<div class="fp-loading">${__("Could not load the board.")}</div>`);
				})
				.finally(() => {
					this.loading = false;
				});
		}

		find(so) {
			return this.open_cards.find((c) => c.so === so);
		}

		put(card, so) {
			// Replace, add or drop one card on the open board.
			const name = (card && card.so) || so;
			const i = this.open_cards.findIndex((c) => c.so === name);
			if (!card) {
				if (i >= 0) this.open_cards.splice(i, 1);
			} else if (i >= 0) {
				this.open_cards[i] = card;
			} else {
				this.open_cards.push(card);
				this.open_cards.sort((a, b) => (a.created < b.created ? -1 : a.created > b.created ? 1 : 0));
			}
			if (this.view === "open" && !this.drag_so) this.render();
		}

		refresh_card(so) {
			if (!so) return;
			clearTimeout(this.pending[so]);
			this.pending[so] = setTimeout(() => {
				delete this.pending[so];
				frappe.xcall(API + "get_card", { sales_order: so }).then((card) => this.put(card, so));
			}, 400);
		}

		schedule_reload() {
			clearTimeout(this.reload_timer);
			this.reload_timer = setTimeout(() => {
				if (this.is_visible() && !this.busy()) this.load(true);
				else this.dirty = true;
			}, 1500);
		}

		// ── realtime ────────────────────────────────────────────────────────

		bind_realtime() {
			this.subscribe();
			frappe.realtime.on("mt_fulfillment_update", (d) => this.on_remote(d && d.sales_order));
			frappe.realtime.on("list_update", (d) => {
				if (!d || !WATCH.includes(d.doctype)) return;
				if (d.doctype === "Sales Order") this.on_remote(d.name);
				else if (this.is_visible()) this.schedule_reload();
				else this.dirty = true;
			});
		}

		subscribe() {
			WATCH.forEach((dt) => frappe.realtime.doctype_subscribe(dt));
		}

		on_remote(so) {
			if (!this.is_visible()) {
				this.dirty = true;
				return;
			}
			if (this.view === "cancelled") this.schedule_reload();
			else this.refresh_card(so);
		}

		on_show() {
			this.subscribe();
			if (this.dirty || Date.now() - this.loaded_at > 30000) this.load(true);
		}

		is_visible() {
			return frappe.get_route_str() === "fulfillment-pipeline" && !document.hidden;
		}

		busy() {
			return !!this.drag_so || $(".modal.show").length > 0;
		}

		// ── filters & stats ─────────────────────────────────────────────────

		due_diff(c) {
			const due = day_index(c.due),
				today = day_index(this.today);
			return due == null || today == null ? null : today - due;
		}

		filtered(cards) {
			const q = (this.$root.find(".fp-q").val() || "").toLowerCase().trim();
			const co = this.$root.find(".fp-f-co").val();
			const ty = this.$root.find(".fp-f-type").val();
			const cv = this.$root.find(".fp-f-conv").val();
			const du = this.$root.find(".fp-f-due").val();
			return cards.filter((c) => {
				if (q) {
					const hay = [c.customer, c.so, c.rep, ...c.lines.map((l) => l.item_name + " " + l.item_code)]
						.join(" ")
						.toLowerCase();
					if (!hay.includes(q)) return false;
				}
				if (co && c.company !== co) return false;
				if (ty && c.type !== ty) return false;
				if (cv === "no" && !c.needs_conv) return false;
				if (cv === "ok" && c.needs_conv) return false;
				if (du) {
					const diff = this.due_diff(c);
					if (du === "late" && !(diff > 0)) return false;
					if (du === "today" && diff !== 0) return false;
				}
				return true;
			});
		}

		render_companies() {
			const $sel = this.$root.find(".fp-f-co");
			const current = $sel.val();
			const companies = [...new Set([...this.open_cards, ...this.cx_cards].map((c) => c.company))].sort();
			$sel.html(
				`<option value="">${__("All companies")}</option>` +
					companies.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")
			);
			if (companies.includes(current)) $sel.val(current);
		}

		render_stats() {
			// Section 9: over the open pipeline, Released excluded.
			const live = this.open_cards.filter((c) => c.status !== "Released");
			const tile = (n, label, cls) =>
				`<div class="fp-stat ${cls || ""}"><b>${n}</b><span>${label}</span></div>`;
			this.$root.find(".fp-stats").html(
				tile(live.length, __("Open orders")) +
					tile(live.filter((c) => this.due_diff(c) > 0).length, __("Overdue"), "red") +
					tile(live.filter((c) => c.needs_conv).length, __("Need conversion"), "red") +
					tile(live.filter((c) => c.updated).length, __("Updated"), "amber") +
					tile(live.filter((c) => !c.pull_sheet).length, __("No pull sheet"))
			);
			this.$root.find(".fp-cxn").text(`(${this.cx_count || 0})`);
		}

		// ── board ───────────────────────────────────────────────────────────

		render() {
			this.render_companies();
			this.render_stats();
			this.$root.find(".fp-ro").toggle(!this.can_edit);
			this.$root.find(".fp-tab").each((_, el) => $(el).toggleClass("on", el.dataset.view === this.view));

			const cx = this.view === "cancelled";
			const cards = this.filtered(cx ? this.cx_cards : this.open_cards);
			const cols = cx ? ["Cancelled"] : this.stages;
			const html = cols
				.map((stage) => {
					// Strict FIFO by creation: the oldest order is always on top. An
					// "Order updated" card (e.g. its delivery date moved) keeps its
					// place and only shows the banner.
					const list = cards
						.filter((c) => c.status === stage)
						.sort((a, b) => (a.created < b.created ? -1 : a.created > b.created ? 1 : 0));
					return `<div class="fp-col" data-stage="${esc(stage)}">
						<div class="fp-col-h"><span class="dot" style="background:${STAGE_COLORS[stage] || "#64748b"}"></span>
							${esc(__(stage))}<span class="n">${list.length}</span></div>
						<div class="fp-col-b">${
							list.map((c) => this.card_html(c)).join("") ||
							`<div class="fp-empty">${__("No orders")}</div>`
						}</div>
					</div>`;
				})
				.join("");
			this.$board.html(html);
			this.sync_pop();
		}

		due_chip(c) {
			const diff = this.due_diff(c);
			if (diff == null) return `<span class="fp-chip muted">${__("No date")}</span>`;
			if (diff > 0)
				return `<span class="fp-chip late">${__("Overdue {0}d · {1}", [diff, due_date(c)])}</span>`;
			if (diff === 0)
				return `<span class="fp-chip today">${__("Due today · {0}", [due_date(c)])}</span>`;
			return `<span class="fp-chip due">${__("Due {0}", [due_date(c)])}</span>`;
		}

		age(c) {
			const at = parse_dt(c.stage_at);
			if (!at) return { text: "", warn: false };
			const ms = Math.max(Date.now() - this.offset - at.getTime(), 0);
			const mins = Math.floor(ms / 60000),
				d = Math.floor(mins / 1440),
				h = Math.floor((mins % 1440) / 60);
			return { text: d ? `${d}d ${h}h` : h ? `${h}h` : `${mins % 60}m`, warn: ms > 86400000 };
		}

		steps_html(c) {
			let conv_cls, conv_label;
			if (c.conv === "submitted") [conv_cls, conv_label] = ["done", __("Conversion")];
			else if (c.needs_conv) [conv_cls, conv_label] = ["need", __("Conversion")];
			else [conv_cls, conv_label] = ["done", __("No conv.")];
			const dn_cls = c.dn_submitted ? "done" : c.dn ? "draft" : "";
			return `<div class="fp-steps">
				<div class="fp-step ${c.pull_sheet ? "done" : ""}">${__("Pull sheet")}</div>
				<div class="fp-step ${conv_cls}">${conv_label}</div>
				<div class="fp-step ${dn_cls}" title="${
					c.dn ? esc(c.dn) + (c.dn_submitted ? "" : " (" + __("draft") + ")") : ""
				}">${__("DN")}</div>
				<div class="fp-step ${c.invoiced ? "done" : ""}">${__("Invoice")}</div>
			</div>`;
		}

		card_html(c) {
			const cx = c.status === "Cancelled";
			const edit = this.can_edit && !cx;
			const tq = qty(c.total_qty, c.uom);

			const upd = c.updated
				? `<div class="fp-upd">⚠ ${__("Order updated {0}", [md(c.updated.at)])} · ${esc(c.updated.note)}${
						c.updated.more ? " " + __("(+{0} more)", [c.updated.more]) : ""
				  }${edit ? `<button data-ack="${esc(c.so)}">${__("Got it")}</button>` : ""}</div>`
				: "";
			const conv = cx
				? ""
				: c.needs_conv
				? `<div class="fp-conv no">● ${__("Conversion required · {0} of {1} items short", [
						c.short_count,
						c.lines.length,
				  ])}</div>`
				: `<div class="fp-conv ok">● ${__("No conversion required")}</div>`;

			const pay = c.cod
				? `<span class="fp-chip cod">COD${c.cod_unpaid ? " · " + __("unpaid") : ""}</span>`
				: `<span class="fp-chip" title="${esc(c.approval)}">${__("Terms")}</span>`;
			const chips = [
				this.due_chip(c),
				c.type ? `<span class="fp-chip">${esc(__(c.type))}</span>` : "",
				pay,
				c.rep ? `<span class="fp-chip">${__("Rep")}: ${esc(c.rep)}</span>` : "",
				!cx && c.reserve_state === "full"
					? `<span class="fp-chip rsv" title="${esc(__("{0} reserved", [c.reserved_text]))}">🔒 ${__(
							"Reserved"
					  )}</span>`
					: "",
				!cx && c.reserve_state === "partial"
					? `<span class="fp-chip rsv-part" title="${esc(
							__("{0} reserved, {1} not yet", [c.reserved_text, c.to_reserve_text])
					  )}">🔒 ${__("Part reserved")}</span>`
					: "",
				!cx && c.misplaced_total > 0
					? `<span class="fp-chip rsv-part" title="${esc(
							__("Stock is reserved in a warehouse this order will not ship from. Reserve moves it; Unreserve releases it.")
					  )}">⚠ ${__("Reserved elsewhere")}</span>`
					: "",
				!cx && !c.on_flow
					? `<span class="fp-chip muted" title="${esc(
							__("Logistic Status is {0}. Moving the card sets it.", [c.raw_status || __("empty")])
					  )}">${__("No stage yet")}</span>`
					: "",
			].join("");

			const hold =
				c.status === ON_HOLD
					? `<div class="fp-hold">${__("On hold")}: ${esc(c.hold_reason || "-")}${
							c.hold_from ? ` <span style="opacity:.75">(${__("from {0}", [esc(c.hold_from)])})</span>` : ""
					  }</div>`
					: "";
			const cancel = cx
				? `<div class="fp-hold">${__("Cancelled")}: ${esc(c.cancel_reason || __("no reason given"))}</div>`
				: "";
			const note = c.note ? `<div class="fp-note">${esc(c.note)}</div>` : "";
			const age = this.age(c);
			const due_diff = cx ? null : this.due_diff(c);
			const due_cls = due_diff > 0 ? "late" : due_diff === 0 ? "today" : "";

			// Reserve: stock lines still to ship and not yet reserved where they
			// ship from. Fully reserved shows "Reserved", which offers to release
			// it; anything partly reserved (or reserved in the wrong warehouse)
			// gets a separate Unreserve next to Reserve.
			let reserve_btn = "";
			if (edit && this.can_reserve) {
				const full = c.reserve_state === "full" && !(c.misplaced_total > 0);
				const can_add =
					c.reserve_state === "none" || c.reserve_state === "partial" || c.misplaced_total > 0;
				if (full) {
					reserve_btn = `<button class="fp-pv fp-rsv done" data-unreserve="${esc(c.so)}" title="${esc(
						__("{0} reserved. Click to unreserve.", [c.held_text])
					)}">✓ ${__("Reserved")}</button>`;
				} else {
					if (can_add && c.reserve_state !== "n/a") {
						const waits = c.needs_conv && c.conv !== "submitted";
						reserve_btn += `<button class="fp-pv fp-rsv" data-reserve="${esc(c.so)}" ${
							waits ? "disabled" : ""
						} title="${esc(
							waits
								? __("Reserve once the Conversion Entry is submitted.")
								: __("Reserve {0} still to ship", [c.to_reserve_text])
						)}">🔒 ${__("Reserve")}</button>`;
					}
					if (c.held_total > 0) {
						reserve_btn += `<button class="fp-pv" data-unreserve="${esc(c.so)}" title="${esc(
							__("Release the {0} reserved", [c.held_text])
						)}">${__("Unreserve")}</button>`;
					}
				}
			}

			const can_dn = !c.dn && (!c.needs_conv || c.conv === "submitted");
			const conv_enabled = !!c.conv_draft || c.needs_conv;
			const acts = cx
				? ""
				: `<div class="fp-acts">
					<button data-act="print" title="${__("Print pull sheet")}">🖨 ${__("Sheet")}</button>
					${
						edit
							? `<button data-act="attach" title="${
									c.pull_sheet ? __("Pull sheet filed") : __("Attach filled pull sheet")
							  }">${c.pull_sheet ? "✓ " + __("Filed") : "📎 " + __("Attach")}</button>
							<button data-act="conv" ${conv_enabled ? "" : "disabled"} title="${
									c.conv_draft
										? __("Open draft {0}", [esc(c.conv_draft)])
										: c.needs_conv
										? __("Create Conversion Entry")
										: __("Nothing is short")
							  }">${c.conv_draft ? __("Conv.") + " ↗" : "+ " + __("Conv.")}</button>
							<button data-act="dn" class="${can_dn ? "primary" : ""}" ${
									c.dn || can_dn ? "" : "disabled"
							  } title="${
									c.dn
										? __("Open {0}", [esc(c.dn)])
										: can_dn
										? __("Create Delivery Note")
										: __("Short items need a submitted Conversion Entry first.")
							  }">${c.dn ? __("Open DN") : "+ " + __("DN")}</button>`
							: ""
					}
				</div>`;

			return `<div class="fp-card ${c.updated ? "updated" : ""}" draggable="${edit}" data-so="${esc(c.so)}">
				${upd}${conv}
				<div class="fp-c-body">
					<div class="fp-c-row">
						<a class="fp-so" href="/app/sales-order/${encodeURIComponent(c.so)}" draggable="false">${esc(c.so)}</a>
						<span class="fp-co" title="${esc(c.company)}">${esc(c.co)}</span>
						${edit ? `<button class="fp-mv" data-move="${esc(c.so)}" title="${__("Move to…")}">⇄</button>` : ""}
					</div>
					<div class="fp-cust">${esc(c.customer)}</div>
					<div class="fp-meta">${chips}</div>
					${note}${hold}${cancel}
					<div class="fp-nums">
						<div><b>${esc(tq)}</b>${__("Total qty")}</div>
						<div><b>${c.strains}</b>${__("Strains")}</div>
						<div><b>${md_y(c.created, this.today)}</b>${__("Created")}</div>
						<div><b class="${due_cls}">${due_date(c)}</b>${__("Delivery Date")}</div>
					</div>
					${cx ? "" : this.steps_html(c)}
					<div class="fp-foot">
						${cx ? "<span></span>" : `<span class="fp-age ${age.warn ? "warn" : ""}">${__("In this stage {0}", [age.text])}</span>`}
						<span class="fp-foot-btns">${reserve_btn}<button class="fp-pv ${this.pop_so === c.so ? "on" : ""}" data-preview="${esc(c.so)}" title="${__(
							"Items, stock and shortages"
						)}">${__("Preview")}</button></span>
					</div>
				</div>
				${acts}
			</div>`;
		}

		// ── events ──────────────────────────────────────────────────────────

		card_of(el) {
			const so = $(el).closest(".fp-card").attr("data-so");
			return (this.view === "cancelled" ? this.cx_cards : this.open_cards).find((c) => c.so === so);
		}

		bind_events() {
			const me = this;
			this.$root.on("input change", ".fp-q, .fp-f-co, .fp-f-type, .fp-f-conv, .fp-f-due", () => this.render());
			this.$root.on("click", ".fp-tab", function () {
				const view = this.dataset.view;
				if (view === me.view) return;
				me.view = view;
				me.render();
				me.load(true);
			});

			// card buttons
			this.$board.on("click", "[data-ack]", function (e) {
				e.stopPropagation();
				me.hide_pop();
				me.ack(this.dataset.ack);
			});
			this.$board.on("click", "[data-move]", function (e) {
				e.stopPropagation();
				me.hide_pop();
				me.move_dialog(me.find(this.dataset.move));
			});
			this.$board.on("click", "[data-act]", function (e) {
				e.stopPropagation();
				me.hide_pop();
				const c = me.card_of(this);
				if (c) me.act(this.dataset.act, c);
			});

			// Stock reservation
			this.$board.on("click", "[data-reserve]", function (e) {
				e.stopPropagation();
				me.hide_pop();
				const c = me.find(this.dataset.reserve);
				if (c) me.reserve(c);
			});
			this.$board.on("click", "[data-unreserve]", function (e) {
				e.stopPropagation();
				me.hide_pop();
				const c = me.find(this.dataset.unreserve);
				if (c) me.unreserve(c);
			});

			// Preview: the card's item/stock detail, opened from its button
			this.$board.on("click", "[data-preview]", function (e) {
				e.stopPropagation();
				me.toggle_pop(this.dataset.preview);
			});
			this.$pop.on("click", ".fp-pop-x", () => this.hide_pop());
			$(document).on("click.fp_preview", (e) => {
				if (this.pop_so && !$(e.target).closest(".fp-pop, [data-preview]").length) this.hide_pop();
			});
			$(document).on("keydown.fp_preview", (e) => {
				if (e.key === "Escape") this.hide_pop();
			});
			// Follow the button when the page or a column scrolls (capture
			// catches scrolls inside columns, which do not bubble).
			window.addEventListener("scroll", () => this.place_pop(), true);
			window.addEventListener("resize", () => this.place_pop());

			// drag and drop
			this.$board.on("dragstart", ".fp-card", function (e) {
				me.drag_so = this.dataset.so;
				this.classList.add("dragging");
				me.hide_pop();
				const dt = e.originalEvent.dataTransfer;
				dt.effectAllowed = "move";
				dt.setData("text/plain", me.drag_so);
			});
			this.$board.on("dragend", ".fp-card", function () {
				this.classList.remove("dragging");
				me.$board.find(".fp-col").removeClass("over blocked");
				setTimeout(() => (me.drag_so = null), 0);
			});
			this.$board.on("dragover", ".fp-col", function (e) {
				const c = me.find(me.drag_so);
				if (!c) return;
				e.preventDefault();
				const blocked = !!(c.blocked || {})[this.dataset.stage];
				this.classList.toggle("blocked", blocked);
				this.classList.toggle("over", !blocked);
				e.originalEvent.dataTransfer.dropEffect = blocked ? "none" : "move";
			});
			this.$board.on("dragleave", ".fp-col", function (e) {
				if (!this.contains(e.originalEvent.relatedTarget)) this.classList.remove("over", "blocked");
			});
			this.$board.on("drop", ".fp-col", function (e) {
				e.preventDefault();
				this.classList.remove("over", "blocked");
				const so = me.drag_so || e.originalEvent.dataTransfer.getData("text/plain");
				me.drag_so = null;
				me.move(so, this.dataset.stage);
			});
		}

		// ── stage moves ─────────────────────────────────────────────────────

		move(so, to) {
			const c = this.find(so);
			if (!c || c.status === to) return;
			const go = (card) => {
				const err = (card.blocked || {})[to];
				if (err) {
					frappe.show_alert({ message: esc(err), indicator: "red" }, 6);
					return;
				}
				if (to === ON_HOLD) {
					this.ask_reason(card, (reason) => this.do_move(card, to, reason));
					return;
				}
				this.do_move(card, to);
			};
			if (!(c.blocked || {})[to]) return go(c);
			// The block may be stale (rule changed, document made since the
			// board loaded): ask the server before refusing.
			this.fresh_card(so).then((fresh) => fresh && go(fresh));
		}

		fresh_card(so) {
			return frappe.xcall(API + "get_card", { sales_order: so }).then((card) => {
				this.put(card, so);
				return card;
			});
		}

		do_move(c, to, reason) {
			const from = c.status;
			frappe
				.xcall(API + "move_stage", { sales_order: c.so, to_stage: to, reason: reason || null })
				.then((card) => {
					this.put(card, c.so);
					frappe.show_alert({ message: esc(`${c.so}: ${from} → ${to}`), indicator: "green" }, 4);
				})
				.catch(() => this.refresh_card(c.so));
		}

		ask_reason(c, cb) {
			const d = new frappe.ui.Dialog({
				title: __("Put on hold: {0}", [c.customer]),
				fields: [{ fieldname: "reason", fieldtype: "Small Text", label: __("Hold reason"), reqd: 1 }],
				primary_action_label: __("Put on hold"),
				primary_action: (v) => {
					const reason = (v.reason || "").trim();
					if (!reason) return;
					d.hide();
					cb(reason);
				},
			});
			d.show();
		}

		move_dialog(c) {
			// Always list the stages from a fresh card, never from what the
			// board loaded minutes ago.
			if (c) this.fresh_card(c.so).then((fresh) => fresh && this.show_move_dialog(fresh));
		}

		show_move_dialog(c) {
			const options = this.stages
				.filter((s) => s !== c.status)
				.map((s) => {
					const why = (c.blocked || {})[s];
					return `<button data-stage="${esc(s)}" ${why ? "disabled" : ""}>
						<span style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:${
							STAGE_COLORS[s]
						}"></span>${esc(__(s))}${why ? `<small>${esc(why)}</small>` : ""}</button>`;
				})
				.join("");
			const d = new frappe.ui.Dialog({
				title: __("Move {0}", [c.so]),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "list",
						options: `<p class="text-muted small">${__("Now at {0}", [
							esc(__(c.status)),
						])}</p><div class="fp-move-list">${options}</div>`,
					},
				],
			});
			d.$wrapper.on("click", ".fp-move-list button:not([disabled])", (e) => {
				const to = e.currentTarget.dataset.stage;
				d.hide();
				this.move(c.so, to);
			});
			d.show();
		}

		ack(so) {
			frappe.xcall(API + "ack_update", { sales_order: so }).then((card) => {
				this.put(card, so);
				frappe.show_alert({ message: __("Marked as reviewed"), indicator: "green" }, 3);
			});
		}

		// ── card actions ────────────────────────────────────────────────────

		reserve(c) {
			frappe.call({
				method: API + "reserve_stock",
				args: { sales_order: c.so },
				freeze: true,
				freeze_message: __("Reserving stock…"),
				callback: (r) => {
					const m = r.message || {};
					this.put(m.card, c.so);
					if (m.reserved_now > 0) {
						frappe.show_alert(
							{ message: __("{0}: reserved {1}", [esc(c.so), esc(m.reserved_now_text)]), indicator: "green" },
							5
						);
					} else if (m.moved) {
						frappe.show_alert({ message: __("{0}: reservation released from the wrong warehouse", [esc(c.so)]), indicator: "orange" }, 6);
					} else {
						frappe.show_alert({ message: __("{0}: no stock was free to reserve", [esc(c.so)]), indicator: "orange" }, 6);
					}
				},
			});
		}

		unreserve(c) {
			frappe.confirm(
				__("Release the {0} reserved for {1}?", [esc(c.held_text), esc(c.so)]),
				() =>
					frappe.call({
						method: API + "unreserve_stock",
						args: { sales_order: c.so },
						freeze: true,
						freeze_message: __("Unreserving stock…"),
						callback: (r) => {
							this.put(r.message, c.so);
							frappe.show_alert({ message: __("{0}: stock unreserved", [esc(c.so)]), indicator: "green" }, 4);
						},
					})
			);
		}

		act(action, c) {
			if (action === "print") return this.print_sheet(c);
			if (action === "attach") return this.attach(c);
			if (action === "conv") return this.conversion(c);
			if (action === "dn") return this.delivery_note(c);
		}

		print_sheet(c) {
			const url =
				"/printview?doctype=" +
				encodeURIComponent("Sales Order") +
				"&name=" +
				encodeURIComponent(c.so) +
				"&format=" +
				encodeURIComponent("Lab Pull Sheet") +
				"&no_letterhead=1&trigger_print=1";
			window.open(url, "_blank");
		}

		attach(c) {
			const upload = () =>
				new frappe.ui.FileUploader({
					doctype: "Sales Order",
					docname: c.so,
					folder: "Home/Attachments",
					dialog_title: __("Attach pull sheet: {0}", [c.customer]),
					restrictions: { allowed_file_types: ["image/*", "application/pdf"] },
					allow_take_photo: true,
					on_success: (file) => {
						frappe
							.xcall(API + "attach_pull_sheet", { sales_order: c.so, file_url: file.file_url })
							.then((card) => {
								this.put(card, c.so);
								frappe.show_alert(
									{ message: __("Pull sheet attached to {0}", [c.so]), indicator: "green" },
									4
								);
							});
					},
				});
			if (!c.pull_sheet) return upload();
			const d = new frappe.ui.Dialog({
				title: __("Pull sheet: {0}", [c.so]),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "info",
						options: `<p>${__("A filled pull sheet is already on this order.")}
							<a href="${esc(c.pull_sheet)}" target="_blank" rel="noopener">${__("View it")}</a></p>`,
					},
				],
				primary_action_label: __("Replace"),
				primary_action: () => {
					d.hide();
					upload();
				},
			});
			d.show();
		}

		conversion(c) {
			frappe.xcall(API + "conversion_action", { sales_order: c.so }).then((r) => {
				if (r && r.open) {
					frappe.set_route("Form", "Conversion Entry", r.open);
					return;
				}
				frappe.model.open_mapped_doc({
					method: API + "make_conversion_entry",
					source_name: c.so,
					freeze_message: __("Starting Conversion Entry…"),
				});
			});
		}

		delivery_note(c) {
			if (c.dn) {
				frappe.set_route("Form", "Delivery Note", c.dn);
				return;
			}
			frappe.call({
				method: API + "make_dn",
				args: { sales_order: c.so },
				freeze: true,
				freeze_message: __("Creating Delivery Note…"),
				callback: (r) => {
					const m = r.message;
					if (!m || !m.name) return;
					if (!m.existing) frappe.show_alert({ message: __("Draft {0} created", [m.name]), indicator: "green" }, 4);
					frappe.set_route("Form", "Delivery Note", m.name);
				},
			});
		}

		// ── preview popup ───────────────────────────────────────────────────

		toggle_pop(so) {
			if (this.pop_so === so) return this.hide_pop();
			const c = this.card_by_so(so);
			if (!c) return;
			this.pop_so = so;
			this.fill_pop(c);
			this.$board.find(".fp-pv").removeClass("on");
			this.$board.find(`[data-preview="${CSS.escape(so)}"]`).addClass("on");
			this.place_pop();
		}

		card_by_so(so) {
			return (this.view === "cancelled" ? this.cx_cards : this.open_cards).find((c) => c.so === so);
		}

		sync_pop() {
			// After a redraw: keep an open preview on its card with fresh data,
			// or close it when the card has gone (moved off the board, filtered).
			if (!this.pop_so) return;
			const c = this.card_by_so(this.pop_so);
			if (!c || !this.anchor()) return this.hide_pop();
			this.fill_pop(c);
			this.place_pop();
		}

		anchor() {
			return this.pop_so ? this.$board.find(`[data-preview="${CSS.escape(this.pop_so)}"]`)[0] : null;
		}

		place_pop() {
			if (!this.pop_so) return;
			const btn = this.anchor();
			if (!btn) return this.hide_pop();
			const r = btn.getBoundingClientRect();
			// The button scrolled out of sight (page or column): close.
			if (r.bottom < 0 || r.top > window.innerHeight || (r.width === 0 && r.height === 0)) {
				return this.hide_pop();
			}
			const p = this.$pop[0];
			p.style.display = "block";
			const w = p.offsetWidth,
				h = p.offsetHeight;
			let x = Math.min(r.left, window.innerWidth - w - 8);
			let y = r.bottom + 6;
			if (y + h > window.innerHeight - 8) y = r.top - h - 6;
			p.style.left = Math.max(8, x) + "px";
			p.style.top = Math.max(8, y) + "px";
		}

		fill_pop(c) {
			if (!c.lines) return;
			const whs = [...new Set(c.lines.map((l) => l.warehouse).filter(Boolean))].join(", ");
			const short_total = c.lines.reduce((a, l) => a + (l.short || 0), 0);
			const reserved_total = c.lines.reduce((a, l) => a + (l.reserved || 0), 0);
			const units = [...new Set(c.lines.map((l) => l.uom))];
			const unit = units.length === 1 ? units[0] : "";
			const rows = c.lines
				.map(
					(l) => `<tr class="${l.short > 0 ? "short" : ""}">
						<td>${esc(l.item_name)}</td>
						<td class="r">${esc(qty(l.need, l.uom))}</td>
						<td class="r">${l.is_stock ? esc(qty(l.available, l.uom)) : "n/a"}</td>
						<td class="r">${l.reserved > 0 ? esc(qty(l.reserved, l.uom)) : "-"}${
							l.misplaced > 0 ? ` <span title="${esc(__("reserved in another warehouse"))}">(+${esc(qty(l.misplaced, l.uom))} ⚠)</span>` : ""
						}</td>
						<td class="r">${l.short > 0 ? esc(qty(l.short, l.uom)) : "-"}</td>
					</tr>`
				)
				.join("");
			const upd = c.updated
				? `<div class="upd-list">${c.updated.all.map((n) => "• " + esc(n)).join("<br>")}</div>`
				: "";
			this.$pop.html(`
				<div class="fp-pop-h"><h4>${esc(c.customer)}</h4>
					<button class="fp-pop-x" title="${__("Close")}" aria-label="${__("Close")}">×</button></div>
				<div class="s">${esc(c.so)} · ${__("Delivery Date {0}", [due_date(c)])} · ${c.strains} ${__(
				"strains"
			)} · ${__("availability in {0}", [
				esc(whs || "-"),
			])}</div>
				<table>
					<thead><tr><th>${__("Item")}</th><th class="r">${__("To ship")}</th><th class="r">${__(
				"In stock"
			)}</th><th class="r">${__("Reserved")}</th><th class="r">${__("Short")}</th></tr></thead>
					<tbody>${rows}</tbody>
					<tfoot><tr><td>${__("Total")}</td><td class="r">${esc(qty(
				c.lines.reduce((a, l) => a + (l.need || 0), 0),
				unit
			))}</td><td></td><td class="r">${
				reserved_total > 0 ? esc(qty(reserved_total, unit)) : "-"
			}</td><td class="r">${short_total > 0 ? esc(qty(short_total, unit)) : "-"}</td></tr></tfoot>
				</table>${upd}`);
		}

		hide_pop() {
			this.pop_so = null;
			if (this.$pop) this.$pop.hide();
			if (this.$board) this.$board.find(".fp-pv").removeClass("on");
		}
	}

	frappe.pages["fulfillment-pipeline"].on_page_load = function (wrapper) {
		const page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Fulfillment Pipeline"),
			single_column: true,
		});
		wrapper.fp_board = new FulfillmentPipeline(page, wrapper);
	};

	frappe.pages["fulfillment-pipeline"].on_page_show = function (wrapper) {
		if (wrapper.fp_board) wrapper.fp_board.on_show();
	};

	frappe.pages["fulfillment-pipeline"].on_page_hide = function (wrapper) {
		if (wrapper.fp_board) wrapper.fp_board.hide_pop();
	};
})();
