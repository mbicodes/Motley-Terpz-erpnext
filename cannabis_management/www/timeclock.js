/* Time Clock — portal page logic
 *
 * No PIN, no employee picker, no camera: the Frappe session is the identity, so the
 * only thing this page has to decide is which direction the next punch goes — and
 * even that is confirmed server-side.
 *
 * All clicks go through one delegated listener reading data-* attributes. Nothing is
 * ever built with inline onclick="..." string interpolation, so a name or note
 * containing quotes or angle brackets can never break a button.
 */

frappe.ready(function () {
	const API = "cannabis_management.time_clock.api.";

	const el = (id) => document.getElementById(id);
	const wrap = el("tcWrap");
	if (!wrap) return;

	const canManageNotes = wrap.dataset.canManageNotes === "1";

	// Difference between site time and this device's clock. The site runs on its own
	// timezone setting, which may not match the phone's, so every displayed time is
	// derived from the server's clock rather than the browser's.
	let serverSkewMs = 0;
	let status = null;
	let noteTarget = null;

	// ── helpers ──────────────────────────────────────────────────

	/* Escape for BOTH text and quoted-attribute contexts.
	 *
	 * The textContent/innerHTML trick escapes & < > but leaves quotes intact, which
	 * is safe in a text node and unsafe inside data-note="...": a note containing a
	 * double quote would close the attribute and let the rest inject markup. Notes
	 * are free text typed by one user and rendered in another's browser, so they are
	 * treated as hostile.
	 */
	function escapeHtml(value) {
		return String(value == null ? "" : value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	/* Parse a naive "YYYY-MM-DD HH:MM:SS[.ffffff]" site timestamp.
	 * Built and read back as local components so the wall-clock digits survive
	 * regardless of the device's own timezone. */
	function parseNaive(text) {
		if (!text) return null;
		const cleaned = String(text).replace(" ", "T").split(".")[0];
		const date = new Date(cleaned);
		return isNaN(date.getTime()) ? null : date;
	}

	function siteNow() {
		return new Date(Date.now() + serverSkewMs);
	}

	function fmtTime(date) {
		if (!date) return "—";
		return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
	}

	function fmtDuration(totalSeconds) {
		const seconds = Math.max(0, Math.floor(totalSeconds || 0));
		const hours = Math.floor(seconds / 3600);
		const minutes = Math.floor((seconds % 3600) / 60);
		if (!hours) return `${minutes}m`;
		return `${hours}h ${String(minutes).padStart(2, "0")}m`;
	}

	function setMessage(text, kind) {
		const target = el("tcMsg");
		if (!target) return;
		target.textContent = text || "";
		target.className = "tc-msg" + (kind ? ` is-${kind}` : "");
	}

	// ── rendering ────────────────────────────────────────────────

	function renderClockFace() {
		const now = siteNow();
		const nowEl = el("tcNow");
		const todayEl = el("tcToday");
		if (nowEl) nowEl.textContent = fmtTime(now);
		if (todayEl) {
			todayEl.textContent = now.toLocaleDateString([], {
				weekday: "long",
				month: "short",
				day: "numeric",
			});
		}
		renderElapsed();
	}

	function renderElapsed() {
		const target = el("tcElapsed");
		if (!target) return;

		if (!status || !status.open_since) {
			target.textContent = "";
			return;
		}

		const since = parseNaive(status.open_since);
		if (!since) {
			target.textContent = "";
			return;
		}

		const seconds = (siteNow().getTime() - since.getTime()) / 1000;
		target.textContent = `On the clock for ${fmtDuration(seconds)} · since ${fmtTime(since)}`;
	}

	function renderStatus() {
		if (!status) return;

		const stateEl = el("tcState");
		const buttonEl = el("tcPunchBtn");
		const clockedIn = !!status.is_clocked_in;

		if (stateEl) {
			stateEl.className = "tc-state " + (clockedIn ? "is-in" : "is-out");
			const textEl = stateEl.querySelector(".tc-state-text");
			if (textEl) textEl.textContent = clockedIn ? "Clocked in" : "Clocked out";
		}

		if (buttonEl) {
			const willClockIn = status.next_action === "IN";
			buttonEl.disabled = false;
			buttonEl.className = "tc-punch " + (willClockIn ? "will-clock-in" : "will-clock-out");
			buttonEl.querySelector(".tc-punch-label").textContent = willClockIn
				? "Clock In"
				: "Clock Out";
			buttonEl.dataset.action = "punch";
		}

		renderSessions();
		renderMyNote();
		renderElapsed();
	}

	function renderSessions() {
		const target = el("tcSessions");
		const totalEl = el("tcTotal");
		if (!target) return;

		const sessions = (status && status.today_sessions) || [];

		if (totalEl) {
			totalEl.textContent = sessions.length
				? `${fmtDuration(status.today_seconds)} total`
				: "";
		}

		if (!sessions.length) {
			target.innerHTML = '<div class="tc-empty">No punches yet today.</div>';
			return;
		}

		target.innerHTML = sessions
			.map(function (session) {
				const inTime = fmtTime(parseNaive(session.in_time));
				const outTime = session.is_open ? null : fmtTime(parseNaive(session.out_time));
				const tail = session.is_open
					? '<span class="tc-session-open">in progress</span>'
					: `<span class="tc-session-dur">${escapeHtml(fmtDuration(session.seconds))}</span>`;

				return (
					'<div class="tc-session">' +
					`<div class="tc-session-times">${escapeHtml(inTime)} &rarr; ${escapeHtml(outTime || "—")}</div>` +
					tail +
					"</div>"
				);
			})
			.join("");
	}

	function renderMyNote() {
		const target = el("tcMyNote");
		if (!target) return;

		const note = status && status.day_note;
		if (!note || !note.note) {
			target.hidden = true;
			target.textContent = "";
			return;
		}

		target.hidden = false;
		target.innerHTML = `<strong>Note:</strong> ${escapeHtml(note.note)}`;
	}

	function renderRoster(payload) {
		const target = el("tcRoster");
		if (!target) return;

		const roster = (payload && payload.roster) || [];
		if (!roster.length) {
			target.innerHTML =
				'<div class="tc-empty">Nobody holds the Time Clock User role yet.</div>';
			return;
		}

		target.innerHTML = roster
			.map(function (row) {
				const pill = row.is_clocked_in
					? '<span class="tc-pill is-in">IN</span>'
					: '<span class="tc-pill is-out">OUT</span>';

				const last = row.last_punch
					? `${row.last_punch.log_type} at ${fmtTime(parseNaive(row.last_punch.time))}`
					: "no punches";

				const noteText = row.day_note && row.day_note.note;
				const noteBlock = noteText
					? `<div class="tc-roster-note">&#9679; ${escapeHtml(noteText)}</div>`
					: "";

				// Values ride in data-* attributes, read by the delegated listener.
				const buttonLabel = noteText ? "Edit note" : "Add note";

				return (
					'<div class="tc-roster-row">' +
					pill +
					'<div class="tc-roster-main">' +
					`<div class="tc-roster-name">${escapeHtml(row.full_name)}</div>` +
					`<div class="tc-roster-sub">${escapeHtml(last)} &middot; ${escapeHtml(fmtDuration(row.seconds))} today</div>` +
					noteBlock +
					"</div>" +
					`<button class="tc-mini-btn" data-action="note" data-user="${escapeHtml(row.user)}" ` +
					`data-name="${escapeHtml(row.full_name)}" data-note="${escapeHtml(noteText || "")}">` +
					`${buttonLabel}</button>` +
					"</div>"
				);
			})
			.join("");
	}

	// ── data loading ─────────────────────────────────────────────

	function syncSkew(serverTime) {
		const parsed = parseNaive(serverTime);
		if (parsed) serverSkewMs = parsed.getTime() - Date.now();
	}

	function loadStatus() {
		return frappe
			.xcall(API + "get_my_status")
			.then(function (result) {
				status = result;
				syncSkew(result.server_time);
				renderClockFace();
				renderStatus();
			})
			.catch(function () {
				setMessage("Could not load your status. Pull to refresh.", "error");
			});
	}

	function loadRoster() {
		if (!canManageNotes) return Promise.resolve();

		return frappe
			.xcall(API + "get_roster")
			.then(renderRoster)
			.catch(function () {
				const target = el("tcRoster");
				if (target) {
					target.innerHTML = '<div class="tc-empty">Could not load the team list.</div>';
				}
			});
	}

	function doPunch(button) {
		// Guard against a double tap racing two inserts through.
		button.disabled = true;
		setMessage("");

		frappe
			.xcall(API + "punch")
			.then(function (result) {
				status = result;
				syncSkew(result.server_time);
				renderClockFace();
				renderStatus();
				setMessage(
					result.punched === "IN" ? "Clocked in. Have a good shift." : "Clocked out. Thanks!",
					"ok"
				);
				loadRoster();
			})
			.catch(function () {
				// Frappe surfaces the server's reason in its own dialog; keep the
				// inline line short and re-enable so the user can retry.
				setMessage("Punch not recorded.", "error");
				loadStatus();
			});
	}

	// ── note editor ──────────────────────────────────────────────

	function openNoteModal(user, fullName, existingNote) {
		noteTarget = user;
		const modal = el("tcNoteModal");
		if (!modal) return;

		el("tcNoteModalTitle").textContent = `Day note — ${fullName}`;
		el("tcNoteText").value = existingNote || "";
		el("tcNoteMsg").textContent = "";
		el("tcNoteRemove").hidden = !existingNote;
		modal.hidden = false;
		el("tcNoteText").focus();
	}

	function closeNoteModal() {
		noteTarget = null;
		const modal = el("tcNoteModal");
		if (modal) modal.hidden = true;
	}

	function saveNote() {
		const text = (el("tcNoteText").value || "").trim();
		if (!text) {
			el("tcNoteMsg").textContent = "Please enter a note, or press Remove.";
			return;
		}

		el("tcNoteSave").disabled = true;
		frappe
			.xcall(API + "set_day_note", { user: noteTarget, note: text })
			.then(function () {
				closeNoteModal();
				loadRoster();
				loadStatus();
			})
			.catch(function () {
				el("tcNoteMsg").textContent = "Could not save the note.";
			})
			.finally(function () {
				el("tcNoteSave").disabled = false;
			});
	}

	function removeNote() {
		el("tcNoteRemove").disabled = true;
		frappe
			.xcall(API + "remove_day_note", { user: noteTarget })
			.then(function () {
				closeNoteModal();
				loadRoster();
				loadStatus();
			})
			.catch(function () {
				el("tcNoteMsg").textContent = "Could not remove the note.";
			})
			.finally(function () {
				el("tcNoteRemove").disabled = false;
			});
	}

	// ── one delegated listener for every click ───────────────────

	document.addEventListener("click", function (event) {
		const trigger = event.target.closest("[data-action]");

		if (trigger) {
			const action = trigger.dataset.action;

			if (action === "punch") {
				doPunch(trigger);
				return;
			}

			if (action === "note") {
				openNoteModal(trigger.dataset.user, trigger.dataset.name, trigger.dataset.note);
				return;
			}
		}

		if (event.target.id === "tcRosterRefresh") loadRoster();
		if (event.target.id === "tcNoteSave") saveNote();
		if (event.target.id === "tcNoteRemove") removeNote();
		if (event.target.id === "tcNoteCancel") closeNoteModal();

		// Click the backdrop to dismiss.
		if (event.target.id === "tcNoteModal") closeNoteModal();
	});

	document.addEventListener("keydown", function (event) {
		if (event.key === "Escape") closeNoteModal();
	});

	// ── boot ─────────────────────────────────────────────────────

	renderClockFace();
	loadStatus();
	loadRoster();

	setInterval(renderClockFace, 1000);
	// Keep a long-open tab honest without hammering the server.
	setInterval(loadStatus, 120000);
});
