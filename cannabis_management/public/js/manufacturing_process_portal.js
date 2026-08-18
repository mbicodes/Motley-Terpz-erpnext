/* Portal shell for the Manufacturing Process page.
 *
 * Two jobs only:
 *   1. Guest  → drive the code-entry form against manufacturing_portal.access.unlock
 *   2. Signed in → mount the shared app (public/js/manufacturing_process_app.js)
 *
 * All page behaviour lives in the shared module, which the Desk page mounts too.
 * Keep this file free of business logic.
 */

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

	// ── 2. unlocked: mount the shared app ────────────────────────────
	if (!appRoot) return;

	if (!window.cannabis || !cannabis.manufacturingProcess) {
		appRoot.innerHTML =
			'<div class="mpx-fatal">The Manufacturing Process module failed to load. ' +
			"Try reloading the page.</div>";
		return;
	}

	cannabis.manufacturingProcess.mount(appRoot, {
		initialWorkOrder: appRoot.dataset.initialWorkOrder || null,
	});

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
