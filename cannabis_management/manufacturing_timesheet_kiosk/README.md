# Manufacturing Timesheet Kiosk

Access-code kiosk at **`/manufacturing-timesheet`** for shop-floor employees to clock
in/out against an Activity Type. Clocking out generates a real ERPNext Timesheet.

Not to be confused with **Manufacturing Portal** (`/manufacturing-process`), which logs
a *User* in as themselves to use the full Manufacturing Process Desk app. This module
never authenticates as anyone - it stays fully guest/anonymous end-to-end and only ever
talks to its own two doctypes plus `Timesheet`.

```
/manufacturing-timesheet
  lock screen → api.verify_access_code(code) → 5-minute one-time token
                                              → also returns recent_timesheets
  no open session → Start screen → api.start_session(token, activity_type, start_time)
  open session    → End screen   → api.end_session(token, end_time) → Timesheet submitted
```

There is no separate "session" doctype. An open clock-in is just a **Draft Timesheet**
whose single Timesheet Detail row has `from_time` set and `to_time`/`completed` empty -
the exact shape Desk's own "Start Timer" button leaves behind (see
`erpnext/public/js/projects/timer.js`). ERPNext only enforces "hours must be > 0" at
*submit* time (`Timesheet.validate_mandatory_fields` runs from `on_submit`, not
`validate`), so a Draft can sit half-filled indefinitely - `start_session` leans on
that instead of tracking state anywhere of its own. `end_session` fills in
`to_time`/`hours`, marks the row `completed`, and submits.

## Files

| Path | Purpose |
|---|---|
| `api.py` | The whitelisted endpoints. All security lives here. |
| `custom_fields.py` | `custom_kiosk_access_code` (Data) on Employee. |
| `employee_hooks.py` | Code uniqueness validation on Employee. |
| `doctype/kiosk_access_log/` | Append-only audit trail - every attempt, success or failure. |
| `../www/manufacturing-timesheet.html` | The portal page (lock/start/end screens, no Desk controls needed). |

## Design notes

- **Data field, not Password.** The code is stored in plain text so the kiosk login
  and the uniqueness check are both single indexed DB queries instead of a
  decrypt-and-compare loop over every employee. Same reasoning as Manufacturing
  Portal's `custom_process_code` - see that module's README for the fuller
  writeup. An administrator can read a worker's code back off the Employee form.
- **One open session per employee**, enforced in `api.start_session` by checking for
  an existing incomplete Draft Timesheet row before creating another.
- **Token, not employee id, past the lock screen.** `verify_access_code` returns a
  short-lived one-time token instead of the client passing its own employee id to
  start/end session - so a guest can't skip the code check. The token is only consumed
  once the operation actually succeeds, so a rejected attempt (e.g. duplicate open
  session) doesn't strand the employee without a valid token.
- **Hours**: the kiosk's own response rounds to 2 decimals for display; the Timesheet
  Detail row is recalculated by ERPNext's own `Timesheet.calculate_hours()` from
  from_time/to_time (same formula as everywhere else in ERPNext), so the two stay
  consistent without a special case.

## Setup

```bash
bench --site <site> migrate   # creates the doctypes; after_migrate adds the Employee field
```

On an Employee: set **Kiosk Access Code**, save.

## Gotcha carried over from Manufacturing Portal

**`hooks.py` changes need a web restart.** `bench migrate` is not enough - gunicorn
workers hold the already-imported `hooks` module (and anything it points to), so a new
`doc_events`/`after_migrate` entry silently does nothing until
`sudo supervisorctl restart frappe-bench-web: frappe-bench-workers:`.
