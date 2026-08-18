# Time Clock

Self-service clock in/out for **Users** at `/timeclock`. Adapted from the Latitude 23.5
"Time Clock Kiosk" template, but with the kiosk removed and `Employee` replaced by `User`.

Built 2026-08-17 on `stage.alltechvirtual.com`.

---

## What it is

Each person signs into ERPNext as themselves, opens `/timeclock` on a phone or laptop,
and taps one button. The direction (IN or OUT) is decided server-side from their last
punch, so there is nothing to get wrong.

```
Browser (logged-in session) ──POST──▶ @frappe.whitelist() methods ──▶ User Checkin
                                       (frappe.session.user IS the
                                        identity; no PIN anywhere)
```

## Files

| Path | Purpose |
|---|---|
| `api.py` | The whitelisted endpoints. All security lives here. |
| `pairing.py` | Shared IN/OUT → session pairing. Used by the API *and* the report so they cannot disagree. |
| `doctype/user_checkin/` | One punch. Alternation + debounce validation. |
| `doctype/user_day_note/` | One note per (user, date). Deterministic name = edit in place. |
| `report/user_time_clock_summary/` | Punches paired into hours. |
| `setup.py` | Creates the `Time Clock User` role; optional bulk grant. |
| `verify.py` | End-to-end check. `bench --site X execute cannabis_management.time_clock.verify.run` |
| `../www/timeclock.{html,css,js}` | The portal page. |

## Deployment

```bash
bench --site <site> migrate
bench --site <site> execute cannabis_management.time_clock.setup.ensure_role
# then either grant per person...
bench --site <site> execute cannabis_management.time_clock.setup.grant --kwargs "{'user':'a@b.com'}"
# ...or bulk-grant every enabled human user
bench --site <site> execute cannabis_management.time_clock.setup.grant_all_enabled_users
bench --site <site> execute cannabis_management.time_clock.verify.run   # expect 25/25
```

---

## Design decisions

### Users, not Employees — and what that costs

Requested explicitly. The consequence is worth restating, because it is not reversible
for free: **nothing in HRMS applies.** No Attendance generation, no Shift Type/Shift
Assignment, no Timesheet, no payroll, no leave interaction. `User Time Clock Summary`
exists because that entire reporting layer had to be rebuilt by hand.

If the requirement ever becomes "these are real employees", the migration path is to
add `Employee.user_id` resolution in `api.punch()` and write to `Employee Checkin`
instead — the pairing logic and portal page carry over unchanged.

### The role is the roster

Holding `Time Clock User` is what makes somebody a participant. Checked explicitly
rather than inferred from "any enabled user", so creating an ERPNext account does not
quietly add a person to the time clock. `grant_all_enabled_users` is opt-in for the
same reason — it never runs on migrate.

### Alternation is checked against both neighbours, not the last punch

`_next_log_type()` picks the next direction from the newest punch — never from the
calendar — which is what makes an 11pm→3am shift pair as one session.

But the doctype validation checks the punch *before* and the punch *after* the one
being saved. Checking only "the latest punch" would make it impossible for HR to insert
a forgotten OUT into the middle of history. Verified by the
`backdated double OUT rejected` check.

### Debounce, and the race it does not close

A portal punch within 60s of an existing punch is refused, which kills the realistic
failure (double tap, impatient reload). Manual/API punches skip the check so HR can
correct history with close timestamps.

**Known limit:** two genuinely concurrent requests could both pass `validate` before
either commits, producing two punches. Not closed because at this scale it is not a
real risk; the fix if it ever matters is a `frappe.cache()` lock keyed on the user
around the insert in `api.punch()`.

### Never link timeclock.css / timeclock.js from the template

Frappe automatically inlines a `.css`/`.js` file that sits next to a `www/` page and
shares its name. Adding `<link>` / `<script src>` tags as well loads them a **second**
time — and a second `frappe.ready()` registers a second delegated click listener, so
every tap fires two punches (the second rejected by debounce, showing the user a
spurious error). This bit during the build. The tags are gone; the comment in
`timeclock.html` says why.

Note that `../www/lizzy.html` *does* carry a redundant `<link>` tag — harmless for CSS,
but do not copy that pattern for JS.

### Times come from the site timezone

Punches are stamped with `now_datetime()`, matching every other ERPNext doctype rather
than inventing a parallel timezone scheme. The portal page measures the difference
between the server clock and the device clock on load and renders everything from the
server's, so a phone in another timezone still shows site time.

> ⚠️ **Open issue at build time:** the site's System Settings timezone is
> `America/Adak` (UTC-9), which is almost certainly wrong for this business. Every
> punch time *and every day boundary* inherits it. Fix System Settings → Time Zone
> before real use. Not changed as part of this build because it reinterprets existing
> naive timestamps across the whole site. (Same setting is already noted as a Metrc
> blocker.)

---

## Carried over from the kiosk template

- Overnight-shift-safe alternation driven by last punch, not date.
- Notes add / edit / remove, editing the same record in place.
- `data-*` attributes + one delegated listener, never inline `onclick` string
  interpolation, so a name or note containing quotes cannot break a button.
- Long note text wraps instead of overflowing its card.
- `/* REBRAND: */` markers in the CSS `:root` block.

## Deliberately dropped

| Kiosk feature | Why it is gone |
|---|---|
| `custom_checkin_pin` + numpad | The session is the identity. A PIN would add a second, weaker credential. |
| `Allow Guest` + `credentials: "omit"` | Endpoints require a real session. The opposite of the kiosk's design. |
| Punch photo | Existed solely to deter buddy-punching under a shared PIN. With per-user auth there is nothing to deter, and silently photographing an authenticated user is a privacy liability, not a control. `device_ip` + `user_agent` give a proportionate audit trail instead. |
| Employee picker grid | You can only ever punch yourself. |
| `0.0001, 0.0001` GPS placeholder | Was a workaround for HRMS "location required" validation on `Employee Checkin`. Not applicable: this is a custom doctype, and `allow_geolocation_tracking` is `0` on this site anyway. |
| Five separate Server Scripts / one `action`-dispatching script | Server Scripts live in the database — not in git, not reviewable, lost on a site rebuild. The template used them because it was a copy-paste-into-any-site deliverable. This is a real app, so these are ordinary whitelisted methods and the `action` dispatch trick is unnecessary. |

## Rebranding for another client

Only `../www/timeclock.css` needs touching — swap the values marked `/* REBRAND: */`
in the `:root` block. The page title and headings come from `timeclock.html`. Backend
files are client-agnostic.

Unlike the kiosk template, the doctypes and role **are** code, so a new site needs only
`bench migrate` plus the setup commands above — there is no manual re-creation of
custom fields.
