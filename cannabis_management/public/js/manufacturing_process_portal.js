/* Portal shell for the Manufacturing Process page.
 *
 * Two jobs only:
 *   1. Guest  → drive the code-entry form against manufacturing_portal.access.unlock
 *   2. Signed in → mount the Time Clock (public/js/manufacturing_process_timer_portal.js)
 *
 * The full Work Order/BOM/Job Card trail (manufacturing_process_app.js) is a
 * Desk-only view now — the portal's whole job, once unlocked, is Start Timer.
 * Keep this file free of business logic.
 */

// Desk always populates frappe.boot.user with can_create/can_read/etc. arrays
// (permission lists the whole Link-field control relies on) — a plain website
// page like this one never gets that object at all. Several core Link-field
// code paths read it unguarded (frappe.model.can_create, the "remember last
// picked value" cache in control_link.js) and throw the moment they're hit,
// which — because it happens INSIDE the search_link success callback, before
// the line that actually shows the results — silently kills the awesomplete
// dropdown for every Link field on this page (Activity Type/Project/Task
// would search fine on the network tab, but nothing ever appeared to pick
// from). An empty-permissions stub is both safe and correct here: this
// restricted portal session shouldn't be offering "Create a new X" or any
// other permission-gated affordance anyway.
frappe.boot = frappe.boot || {};
if (!frappe.boot.user) {
	frappe.boot.user = { last_selected_values: {} };
	[
		"can_create", "can_select", "can_read", "can_write", "can_get_report",
		"can_delete", "can_submit", "can_cancel", "can_import", "can_export",
		"can_print", "can_email", "can_share",
	].forEach(function (key) {
		frappe.boot.user[key] = [];
	});
}

frappe.ready(function () {
	var ACCESS = "cannabis_management.manufacturing_portal.access.";

	var unlockForm = document.getElementById("mpxUnlockForm");
	var appRoot = document.getElementById("mpxApp");

	// ── 1. locked: code entry ────────────────────────────────────────
	if (unlockForm) {
		var codeInput = document.getElementById("mpxCode");
		var unlockBtn = document.getElementById("mpxUnlockBtn");
		var msg = document.getElementById("mpxMsg");

		var setMsg = function (text, isError) {
			msg.textContent = text || "";
			msg.className = "mpx-lock-msg" + (isError ? " is-error" : "");
		};

		unlockForm.addEventListener("submit", function (event) {
			event.preventDefault();

			var code = (codeInput.value || "").trim();
			if (!code) {
				setMsg("Enter your access code.", true);
				codeInput.focus();
				return;
			}

			unlockBtn.disabled = true;
			setMsg("Checking…", false);

			frappe
				.xcall(ACCESS + "unlock", { code: code })
				.then(function (result) {
					setMsg("Unlocked. Loading…", false);
					// Full reload rather than mounting in place: the session changed,
					// and the page needs to come back with the Desk control bundles
					// and the signed-in template branch.
					window.location.href = (result && result.redirect) || "/manufacturing-process";
				})
				.catch(function () {
					// The server states the reason (wrong code, attempts remaining,
					// locked out) in its own message dialog. Keep this line short and
					// clear the field so the next attempt starts clean.
					setMsg("Access denied.", true);
					codeInput.value = "";
					codeInput.focus();
					unlockBtn.disabled = false;
				});
		});

		codeInput.focus();
		return;
	}

	// ── 2. unlocked: mount the Time Clock ────────────────────────────
	if (!appRoot) return;

	if (!window.cannabis || !cannabis.manufacturingTimer) {
		appRoot.innerHTML =
			'<div class="mpx-fatal">The Manufacturing Process module failed to load. ' +
			"Try reloading the page.</div>";
		return;
	}

	cannabis.manufacturingTimer.mount(appRoot);

	var signOut = document.getElementById("mpxSignOut");
	if (signOut) {
		signOut.addEventListener("click", function () {
			signOut.disabled = true;
			frappe
				.xcall(ACCESS + "lock")
				.then(function () {
					window.location.href = "/manufacturing-process";
				})
				.catch(function () {
					signOut.disabled = false;
				});
		});
	}
});
