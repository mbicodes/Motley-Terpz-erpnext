/* Manufacturing Process portal — Time Clock.
 *
 * The ONLY thing a code-unlocked worker sees on /manufacturing-process: a big,
 * presentable Start Timer / live stopwatch card. The full Work Order/BOM/Job
 * Card trail (cannabis.manufacturingProcess, in manufacturing_process_app.js)
 * is a Desk-only view now — this file replaces it as the portal's mounted app.
 *
 * Talks to the exact same backend as before (no server change needed):
 *   cannabis_management.api.manufacturing_process.get_timer_defaults
 *   cannabis_management.api.manufacturing_process.save_timer_entry
 * Employee is always resolved server-side from the signed-in user — this file
 * never asks for or sends one.
 *
 * Needs frappe.ui.Dialog + Link controls, same as the shared module — the
 * portal template loads controls.bundle.js + dialog.bundle.js before this.
 */
(function () {
	window.cannabis = window.cannabis || {};

	cannabis.manufacturingTimer = {
		/** @param {HTMLElement} container element to render into */
		mount: function (container) {
			container.innerHTML = getTimerHTML();

			var API = 'cannabis_management.api.manufacturing_process.';
			var STORAGE_KEY = 'mpx_timer_' + frappe.session.user;

			var timerState = null;
			var tickInterval = null;
			var exceededAlerted = false;

			var $idle = container.querySelector('#mpt-idle');
			var $running = container.querySelector('#mpt-running');
			var $empLine = container.querySelector('#mpt-emp-line');
			var $startBtn = container.querySelector('#mpt-start-btn');
			var $clock = container.querySelector('#mpt-clock');
			var $meta = container.querySelector('#mpt-meta');
			var $endBtn = container.querySelector('#mpt-end-btn');
			var $discardBtn = container.querySelector('#mpt-discard-btn');

			$startBtn.addEventListener('click', openStartDialog);
			$endBtn.addEventListener('click', endTimer);
			$discardBtn.addEventListener('click', function () {
				frappe.confirm(
					__('Discard this running timer without saving it as a Timesheet?'),
					function () { clearTimerState(); }
				);
			});

			checkEmployeeLink();
			resumeFromStorage();

			// ── Employee check — shown up front, not just as a failure later ──
			function checkEmployeeLink() {
				frappe.call({
					method: API + 'get_timer_defaults',
					callback: function (r) {
						var employee = r.message && r.message.employee;
						if (employee) {
							$empLine.textContent = __('Signed in as {0}', [r.message.employee_name]);
							return;
						}
						$empLine.textContent = __('No Employee record is linked to your account — ask an administrator to set that Employee\'s User ID field.');
						$empLine.classList.add('mpt-emp-warn');
						$startBtn.disabled = true;
					},
				});
			}

			// ── Start ────────────────────────────────────────────────────────
			// Same four fields, same fieldtypes, same order as core ERPNext's own
			// Timesheet "Start Timer" popup (erpnext.timesheet.timer, in
			// erpnext/public/js/projects/timer.js) — deliberately no extra
			// description text or filtering beyond what that dialog has, so this
			// reads as the same control a worker would meet inside Desk.
			function openStartDialog() {
				var dialog = new frappe.ui.Dialog({
					title: __('Start Timer'),
					fields: [
						{ fieldtype: 'Link', label: __('Activity Type'), fieldname: 'activity_type', reqd: 1, options: 'Activity Type' },
						{ fieldtype: 'Link', label: __('Project'), fieldname: 'project', options: 'Project' },
						{ fieldtype: 'Link', label: __('Task'), fieldname: 'task', options: 'Task' },
						{ fieldtype: 'Float', label: __('Expected Hrs'), fieldname: 'expected_hours' },
					],
					primary_action_label: __('Start'),
					primary_action: function () {
						var values = dialog.get_values();
						if (!values) return;
						dialog.hide();
						startTimer(values);
					},
				});
				dialog.show();
			}

			function startTimer(values) {
				timerState = {
					activity_type: values.activity_type,
					project: values.project || null,
					task: values.task || null,
					expected_hours: values.expected_hours || null,
					// Date.now() (epoch ms), NOT a formatted wall-clock string — see
					// the note on save_timer_entry for why: outside Desk,
					// frappe.datetime's Start-time and End-time helpers apply
					// different, unreliable timezone handling.
					start_ms: Date.now(),
				};
				exceededAlerted = false;
				try { localStorage.setItem(STORAGE_KEY, JSON.stringify(timerState)); } catch (e) { /* ignore */ }
				showRunning();
				frappe.show_alert({ message: __('Timer started — {0}.', [timerState.activity_type]), indicator: 'green' });
			}

			function resumeFromStorage() {
				var raw = null;
				try { raw = localStorage.getItem(STORAGE_KEY); } catch (e) { /* ignore */ }
				if (!raw) return;
				try { timerState = JSON.parse(raw); } catch (e) { timerState = null; }
				if (timerState && timerState.activity_type && timerState.start_ms) {
					showRunning();
				} else {
					clearTimerState();
				}
			}

			function showRunning() {
				$idle.style.display = 'none';
				$running.style.display = '';

				var bits = [timerState.activity_type];
				if (timerState.project) bits.push(timerState.project);
				if (timerState.task) bits.push(timerState.task);
				$meta.textContent = bits.join(' · ');

				tick();
				clearInterval(tickInterval);
				tickInterval = setInterval(tick, 1000);
			}

			function tick() {
				if (!timerState) return;
				var elapsed = Math.max(0, Math.floor((Date.now() - timerState.start_ms) / 1000));
				var h = Math.floor(elapsed / 3600);
				var m = Math.floor((elapsed % 3600) / 60);
				var s = elapsed % 60;
				var pad = function (n) { return (n < 10 ? '0' : '') + n; };
				$clock.textContent = pad(h) + ':' + pad(m) + ':' + pad(s);

				if (!exceededAlerted && timerState.expected_hours && elapsed >= timerState.expected_hours * 3600) {
					exceededAlerted = true;
					frappe.show_alert({ message: __('Timer has passed the expected {0} hour(s).', [timerState.expected_hours]), indicator: 'orange' });
				}
			}

			// ── End ──────────────────────────────────────────────────────────
			function endTimer() {
				if (!timerState) return;
				frappe.confirm(
					__('End the timer and save this as a Timesheet entry?'),
					function () {
						frappe.call({
							method: API + 'save_timer_entry',
							args: {
								activity_type: timerState.activity_type,
								project: timerState.project,
								task: timerState.task,
								expected_hours: timerState.expected_hours,
								// A plain duration, not a formatted timestamp — the
								// server stamps from_time/to_time off its own clock
								// from this. See save_timer_entry's docstring.
								elapsed_seconds: Math.max(0, Math.floor((Date.now() - timerState.start_ms) / 1000)),
							},
							freeze: true,
							freeze_message: __('Saving Timesheet…'),
							callback: function (r) {
								if (!r.message) return;
								clearTimerState();
								frappe.show_alert({
									message: __('Timesheet {0} saved — {1} hour(s) logged.', [r.message.name, (parseFloat(r.message.total_hours) || 0).toFixed(2)]),
									indicator: 'green',
								});
							},
						});
					}
				);
			}

			function clearTimerState() {
				timerState = null;
				clearInterval(tickInterval);
				tickInterval = null;
				try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* ignore */ }
				$running.style.display = 'none';
				$idle.style.display = '';
			}
		},
	};

	function getTimerHTML() {
		return `
		<div class="mpt-wrap">
			<div class="mpt-card">
				<div class="mpt-icon">⏱️</div>
				<h1 class="mpt-title">${__('Time Clock')}</h1>
				<p class="mpt-emp" id="mpt-emp-line">${__('Checking your account…')}</p>

				<div class="mpt-idle" id="mpt-idle">
					<button class="mpt-start-btn" id="mpt-start-btn">▶ ${__('Start Timer')}</button>
					<p class="mpt-hint">${__('Tap Start, tell us what you’re working on, and the clock keeps running until you end it.')}</p>
				</div>

				<div class="mpt-running" id="mpt-running" style="display:none;">
					<span class="mpt-pulse-dot"></span>
					<div class="mpt-clock" id="mpt-clock">00:00:00</div>
					<div class="mpt-meta" id="mpt-meta"></div>
					<div class="mpt-actions">
						<button class="mpt-end-btn" id="mpt-end-btn">⏹ ${__('End & Save')}</button>
						<button class="mpt-discard-btn" id="mpt-discard-btn">${__('Discard')}</button>
					</div>
				</div>
			</div>
		</div>
		`;
	}
})();
