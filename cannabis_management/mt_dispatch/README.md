# MT Dispatch

Slack-first order release, per company. The ERP holds the state and enforces
every rule; Slack is one of the ways to press the buttons.

Built as a module inside `cannabis_management` rather than a separate
`mt_dispatch` app, so it deploys with everything else.

## What is built

| Layer | State |
|---|---|
| Six doctypes (settings, team, reminders, stage log, slack messages, globals) | done |
| Sales Order fields, stage Select, property setters (`install.py`) | done |
| State machine — 12 transitions, row locking, stale-click detection (`flow.py`) | done |
| Gates G0–G5 and the two Delivery Note hard blocks (`gates.py`) | done |
| Payment maths and the cached gate result (`payments.py`) | done |
| Conversion Entry / Delivery Note / Payment Entry builders (`builders.py`) | done |
| Migration patch for open orders (`patches/install_mt_dispatch.py`) | done |
| Unit tests, 19 cases mapped to the spec's acceptance table | done, passing |
| Audience rules — who hears about each transition (`notify.py`) | done |
| Slack: verify, client, endpoints, Block Kit, modals, App Home, commands (`slack/`) | done |
| Posting after each transition — threads, approval DMs, dispatch, exceptions (`slack/post.py`) | done |
| Reminder job (every 15 min, working minutes) and daily digest (`reminders.py`) | done |
| Sales Order form buttons (`public/sales_order_dispatch.js`) | done |
| Roles: Compliance - Consolidated, Dispatch Approver, Dispatch Driver (`install.py`) | done |
| Unit tests: 19 flow + 33 Slack/reminder cases + 1 end-to-end walk | done, passing |

`notify.py` resolves its audience and returns quietly while there is no bot
token, so the flow is fully usable from the ERP before Slack exists.

## Nothing is switched on

There is no `Dispatch Company Settings` record on this site, and every entry
point begins with `get_company_settings(company)`. No record, or `enabled = 0`,
and every hook and gate ignores the company entirely — including the two
Delivery Note blocks. Companies get switched on one at a time by creating a
record.

## Three places the spec did not match the site

**1. `muid` is not an inventory dimension.** The spec's §6.5 `TAGS_WITH_STOCK`
selects `muid` from `tabStock Ledger Entry`. There is no such column: the only
Inventory Dimensions here are Brand and Batch, and `muid` is a plain
`Link → Metric Tag` on Delivery Note Item. Per-tag quantity lives on the Metric
Tag record (`current_qty`, `warehouse`, `status`), so `gates.tags_with_stock`
reads that instead. G3 is therefore only as accurate as whatever keeps
`Metric Tag.current_qty` in step with the ledger.

There is also almost no tag data — one record, a test row. `require_muid_on_dn`
defaults off and should stay off until that is sorted, or G3 blocks every note.

**2. Credit approval fires no document events.** §6.2 hooks
`on_update_after_submit` so a Terms order joins the flow when credit approves.
`credit_and_ar.api.approve_terms` writes with `doc.db_set(...)`, which updates
the column and runs no events at all, so that hook never fires and T02 could
never pass. `approve_terms` now calls `flow.on_terms_approved()` directly,
wrapped so a dispatch failure can never block a credit decision. The
`on_update_after_submit` hook is still wired for orders edited the ordinary way.

**3. `conversion_type` is on the child row,** not the parent, and its option
list is fixed and not exhaustive — there is no `2 to 3`, `5 to 2`, `6 to 2` or
`7 to 2`. `builders.conversion_types()` reads the options off the doctype so
this can never drift, and rejects a combination the field would not accept.
The child row holds **7** raw materials and 3 finished goods, so the spec's
3-raw-material cap on the Slack form would lose `4 to 1` … `7 to 1` at MTM. The
builder accepts all seven; the Slack form can cap itself lower if it wants.

## Two ordering problems in the spec's own guard list

G3 guards `create_delivery_note` and G4 guards `upload_manifest` — but guards
run before effects, so at guard time the note does not exist yet and the
manifest has not been attached. Both gates now check the payload when there is
one and fall back to reading the draft note when there isn't.

Same class of problem inside `transition()`: `resume` reads its target stage
from `custom_hold_from_stage`, and its own effect clears that field. The target
is now resolved before the effect runs.

## Corrections to the spec's factual claims

- Delivery Note has **no** `custom_manifest_no`. Only
  `custom_metrc_manifest_number`, set on 0 notes. §11.2's "copy old values
  over" is a no-op.
- MTM has 214 submitted orders, not 213.
- There are **six** companies. `MTPZ` and `TMM Group` are not in the spec's
  table. Both are ignored safely, but Q1 should decide them alongside Motley Terpz.
- `custom_delivery_note_created` is set by
  `overrides/delivery_note_hooks.py` from submitted notes. It reads Delivery
  Note state only and does not fight the new gate.
- No active Workflow on Delivery Note — as the spec assumed.
- Both Seans exist and are enabled: Sean Shepherd `sean.shepherd@`, Sean Carter
  `sean@`. Q2 still needs answering.
- `Fulfilment`, `Fulfilment - Consolidated` and `Fulfillment User` exist.
  `Compliance - Consolidated`, `Dispatch Approver` and `Dispatch Driver` do not.

## Switching a company on

1. Create a `Dispatch Company Settings` record. Leave `enabled` off while
   filling in the team, the channel IDs and the reminder rules.
2. Leave `require_muid_on_dn` off until Metric Tag data is real.
3. Tick `enabled`.
4. Run `bench --site <site> execute frappe.modules.patch_handler.run_single
   --kwargs "{'patchmodule': 'cannabis_management.patches.install_mt_dispatch'}"`
   to move that company's open orders onto stages. It is idempotent and posts
   nothing to Slack.

On this site that would move roughly **210** open orders, **203** of them onto
`Order Received` at once. Post threads for them deliberately, not as a side
effect of the patch.

## Design notes

- `custom_logistic_status` is written only by `flow.set_stage`.
  `guard_stage_field` rejects any save that changed it without the module's
  flag. A direct `frappe.db.set_value` still bypasses that, as it bypasses all
  Frappe validation.
- Team authority is per company and separate from ERP roles. Both must pass:
  the role grants document access, the team row grants the flow action.
  Administrator is exempt so a wrong settings record stays recoverable.
- `paid_amount` takes the **larger** of advances and settled invoices, never
  the sum, because an allocated advance appears in both. Where the two measure
  different money this understates what is in — which fails closed.
- Stage constants live in `stages.py`, not `flow.py`, because `gates.py`,
  `settings.py` and the reminder job all need them and `flow.py` imports
  `gates.py`. `flow.py` re-exports them.
- Fields are created in code and re-asserted from `after_migrate`. Not
  fixtures: an export would drag in every unrelated Custom Field on Sales Order.

## Slack

- Endpoints: `/api/method/cannabis_management.mt_dispatch.slack.endpoints.{interact,options,command,events}`.
  The module lives inside `cannabis_management`, so these paths carry that
  prefix. `slack/manifest.yml` has them ready to paste.
- `notify.slack_enabled()` needs a bot token and is always off in test mode,
  so a test run never posts to the real channels.
- Threads for orders that were open before go-live:
  `bench --site <site> execute cannabis_management.mt_dispatch.slack.post.post_open_threads --kwargs "{'company': '<company>'}"`
- Reminder rows with `after_minutes = 0` are treated as off. A company with no
  rows uses the section 9.2 defaults.
- `fulfillment_group_id` must be a Slack user group id (`S…`). Anything else is
  ignored and the fulfillment members are tagged one by one.

## Tests

```
bench --site <site> run-tests --module cannabis_management.mt_dispatch.tests.test_dispatch_flow
bench --site <site> run-tests --module cannabis_management.mt_dispatch.tests.test_slack
bench --site <site> run-tests --module cannabis_management.mt_dispatch.tests.test_integration_walk
```

The flow and walk tests replace a company's settings record while they run.
They snapshot the real record first and put it back in tearDown.

19 cases, covering T03, T05, T10, T11, T12, T13, T14, T15 and the gate
arithmetic. They run against real submitted orders rather than fixtures, and
restore every record by hand in `tearDown` — `FrappeTestCase` rolls back per
class, not per test, which is not enough when the data is a copy of production.
