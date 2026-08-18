# Manufacturing Portal

Code-gated web access to the Manufacturing Process page at **`/manufacturing-process`**.

A worker opens the page, types a personal code, and gets the full Manufacturing
Process app — the same one that lives in Desk at `/app/manufacturing-process`, with
every dialog and grid intact. Every access attempt is logged.

Built 2026-08-17 on `stage.alltechvirtual.com`.

---

## How it fits together

```
/manufacturing-process
  no code session → lock screen → access.unlock(code) → login_as(user) + session flag
  code session    → controls.bundle + dialog.bundle + shared app module → mount()

every request → session_guard.guard()  (no-op unless the session carries the flag)
```

**Being signed in is not enough.** The page is code-only: an Administrator already
logged into Desk still gets the lock screen here, because the point of the page is
that access is granted by a code and recorded. Staff who need the page without a code
use the Desk version at `/app/manufacturing-process`, which is unchanged.

The gate is `context.locked = not is_code_session()` in `../www/manufacturing_process.py` —
one line, if the trade-off ever needs revisiting.

| Path | Purpose |
|---|---|
| `access.py` | Code matching, per-IP rate limit + lockout, `login_as`, audit logging. |
| `session_guard.py` | `before_request` hook confining a code session to this page. |
| `user_hooks.py` | Code uniqueness + strength validation on User. |
| `custom_fields.py` | `custom_process_code`, `custom_process_code_enabled` on User. |
| `doctype/process_access_log/` | Append-only audit trail. |
| `verify.py` | 23 server-side checks. |
| `../public/js/manufacturing_process_app.js` | **The page itself — shared by Desk and portal.** |
| `../public/js/manufacturing_process_portal.js` | Portal shell (code form / mount). |
| `../www/manufacturing-process.html` `.css` | Portal template + lock-screen styling. |
| `../www/manufacturing_process.py` | Portal controller. Note the **underscores**. |

## Setup

1. `bench migrate` (creates the doctype; `after_migrate` adds the User fields).
2. On a User: set **Manufacturing Portal Code**, tick **Manufacturing Portal Access
   Enabled**, save.
3. Make sure that user's roles can actually read Work Orders — see the blocker below.

```bash
bench --site <site> execute cannabis_management.manufacturing_portal.verify.run   # expect 23/23
```

> **A code is authentication, not authorization.** Unlocking logs the person in as
> *that user*; what they can see is still decided by that user's roles.

---

## ⚠️ Blocker found during the build: Work Orders are unreadable

A **`Custom DocPerm`** exists for Work Order on this site listing exactly one role:
`Test Consolidated Role`. In Frappe, Custom DocPerm rows **entirely replace** the
standard DocPerm rows — so `Manufacturing Manager` and `Manufacturing User` currently
have **no read access to Work Order at all**.

This is pre-existing and not caused by this module: the Desk page is equally broken
for those roles today. It surfaced here because the portal's Link autocomplete
returned 403 for a user holding `Manufacturing User`.

Until it is resolved, a code holder needs `Test Consolidated Role` (a test artifact,
by the look of the name) for the page to function. Fixing the Work Order permissions
properly is a site-wide decision and was deliberately left alone.

---

## One implementation, two shells

The page used to be 1,256 lines of Desk-only JS. It now lives once in
`public/js/manufacturing_process_app.js` exposing:

```js
cannabis.manufacturingProcess.mount(container, { initialWorkOrder });
```

* **Desk shell** — `cannabis_management/page/manufacturing_process/manufacturing_process.js`,
  ~20 lines, resolves the Work Order from the route.
* **Portal shell** — `public/js/manufacturing_process_portal.js`, resolves it from
  `?work_order=`.

The body was moved **byte-for-byte** by a script rather than retyped; only the head,
tail and `selectFromRoute()` changed. Indentation was left alone on purpose — the file
is full of multi-line template literals whose leading whitespace lands in the rendered
HTML.

**Add page behaviour to the shared module, never to a shell.** Two shells exist so the
page cannot drift; putting logic in one of them defeats the entire arrangement. Same
for CSS: `public/css/manufacturing_process.css` is the source of truth and the Desk
page's CSS file is a one-line `@import`.

### Why the Desk dialogs work outside Desk

`controls.bundle.js` and `dialog.bundle.js` are loaded in the portal template's
`{% block script %}` — the same pair Web Forms load. Together they provide
`frappe.ui.Dialog`, the Link control and the Table/grid control, which is the entire
dependency set of the 6 dialogs. No rewrite was needed.

Styling comes free: `website.bundle.css` (already on every portal page) carries 87
`frappe-control` rules, 24 grid-column rules and 28 modal rules. It has slightly fewer
than `desk.bundle.css` (119 `frappe-control`, 5 `btn-xs` vs 2), so **expect minor
cosmetic drift** between Desk and portal. `.btn-xs` is pinned in the portal CSS for
that reason. Nothing functional depends on it.

---

## Security model, stated honestly

**What protects the code:** enforced uniqueness, a minimum length with weak-pattern
rejection, a 5-attempt per-IP budget with a 15-minute lockout, the restricted session,
and an audit row for every attempt including failures.

**What does not:** hashing. The code is stored as plain text in a Data field so an
administrator can read it back to a worker. Hashing a short code buys very little —
the keyspace is enumerable offline either way — and it would break the stated
workflow. Anyone who can read User records can read every code; on this site that is
System Manager, who can already reset passwords outright.

**What the session guard buys.** It blocks *routes*: `/app`, other portal pages,
arbitrary REST endpoints. That stops someone with a code from wandering the Desk UI,
which is the realistic risk.

**What it does not buy.** It does not reduce the account's permissions. The allowlist
must include `frappe.client.insert` and `frappe.client.submit`, because that is how the
page's own dialogs create Material Requests, Work Orders, Job Cards and Stock Entries.
Someone with a code and a browser console could still insert or submit anything that
user is permitted to touch. Genuinely limiting that means giving code holders a
low-privilege role — not tightening the allowlist.

If a legitimate feature breaks, the denial is recorded as a **Blocked Route** row in
Process Access Log with the exact path. Read that log and extend the allowlist; don't
guess.

---

## Gotchas that cost time here — don't rediscover them

**Portal controllers cannot have hyphens.** `template_page.py` looks for the controller
at `basename.replace("-", "_") + ".py"`. The template is `manufacturing-process.html`;
the controller must be `manufacturing_process.py`. Name it with a hyphen and it is
silently never loaded — `get_context` never runs, every context variable is undefined,
and Jinja quietly renders the falsy branch of every `{% if %}`.

**Colocated JS is skipped when you define `{% block script %}`.** `load_colocated_files`
checks `"{% block script %}" not in self.source` before setting `colocated_js`. This
page must define that block to order the bundles, so its shell JS is loaded explicitly
from `/assets/` instead. (Colocated *CSS* still works — that check is on
`{% block style %}`, which this page does not override.)

**`frappe.Redirect` does not work in a `before_request` hook.** It is only honoured by
the website rendering layer, which runs later; raising it from a hook yields a bare 301
with **no Location header**. `PortalRedirect` in `session_guard.py` is a werkzeug
`HTTPException` instead — app.py returns those directly as responses.

**`cache.get_value` needs `expires=True` for keys set with `expires_in_sec`.**
`set_value(expires_in_sec=…)` never populates `frappe.local.cache`, while a plain
`get_value` memoises its miss there — so the rate-limit counter reads a stale `None`
for the life of the process. Frappe's own docstring says so; it is easy to miss.

**`hooks.py` changes need a web restart.** `bench migrate` is not enough — gunicorn
workers hold the imported module, so a new `before_request` entry silently does
nothing until `sudo supervisorctl restart frappe-bench-web:`.

**Assets are served by nginx, not gunicorn.** `/assets/...` 404s on `:8000` even for
core Frappe files. Test against `https://` (nginx), not `http://127.0.0.1:8000`.

**`patches.txt` is root-owned on this bench** (`-rwxrwxr-x root root`) and cannot be
appended to as the bench user, which is why the custom fields install from
`after_migrate` instead of a patch. Worth fixing the ownership at some point.

**`tabSessions` has no `modified` column**, so `frappe.db.get_value("Sessions", …)`
throws on its default ORDER BY. Use raw SQL.
