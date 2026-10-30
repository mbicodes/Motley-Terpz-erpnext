# Wash Production Plan: Live deployment note

Do not deploy until Leo signs off on Stage. Not deployed by Claude.

## Files changed

New
- `cannabis_management/doctype/wash_plan_freezer/`, `wash_plan_settings/`, `wash_production_plan/`, `wash_production_plan_item/`
- `cannabis_management/page/wash_plan_board/` (Wash Plan Board page)
- `cannabis_management/report/wash_plan_vs_actual/`
- `doc_hooks/wash_plan_sync.py` (Work Order / Stock Entry / Material Request sync)
- `wash_plan_install.py` (Material Request link fields, Wash Plan Settings seed)

Changed
- `hooks.py`: after_migrate install; Material Request on_cancel / on_trash; Stock Entry on_submit / on_cancel sync; Work Order after_insert
- `fixtures/custom_field.json` and `cannabis_management/custom/material_request.json`: `Material Request-custom_project` is now `reqd=0` with `mandatory_depends_on = eval:!doc.custom_wash_production_plan`
- `workspace/lab_manufacturing_process/lab_manufacturing_process.json`: "Wash Plan Board" shortcut
- `deploy_wash_plan/` (deploy.sh, this note); `wash_plan_install.verify()`

## Deploy steps

One command on the target server, as the bench user:

    cd ~/frappe-bench/apps/cannabis_management/deploy_wash_plan && ./deploy.sh <site>

It stops if the app has uncommitted changes, takes a backup, fast-forwards to origin/main, runs migrate, clear-cache and build, restarts, then runs the checks below (`bench --site <site> execute cannabis_management.wash_plan_install.verify`, or `cannabis_management.wash_plan_install.verify()` in `bench console`).

Manual equivalent: backup, `git fetch && git merge --ff-only origin/main`, `bench --site <site> migrate`, `clear-cache`, `bench build --app cannabis_management`, restart.

## Post-deploy checks

1. Wash Plan Settings: freezers are Freezer - MTM, Freezer 2 - MTM, Freezer 3 - MTM, Freezer 4 - MTM. Migrate seeds only when the table is empty, so add any missing ones by hand. Confirm company, routing "Fresh Frozen to CCR", yields 2.5 / 75 and the three item groups.
2. Material Request: a manual MR still requires Project; an MR created from a plan with no project saves with the field empty.
3. New Material Request custom fields exist: `custom_wash_production_plan`, `custom_wash_plan_row`.
4. Open a new Wash Production Plan form: freezer and project choices, availability, over-booking message, Create Material Requests.
5. Open `/app/wash-plan-board`: plan selector, day tabs, Add a Wash, Freezer Stock vs Plan, no console errors.
6. Create one small plan as Leo, create its MR, confirm the MR is Draft and carries the right project, freezer, routing and Finished Goods rows. Submit it, confirm BOMs and both Work Orders use the same project.
7. Report "Wash Plan vs Actual" returns rows with company and date filters.
8. Stock: Live has `validate_negative_stock = 0`, so a wrong-project row would not be blocked by ERPNext. Check availability per project on the first real rows.

## Rollback

- Code: `git revert` the wash-plan commit(s) (or checkout the previous commit), then `bench migrate` and `clear-cache`. The new hooks stop firing; existing MRs, Work Orders and BOMs are unaffected.
- Data: the new DocTypes and the two Material Request custom fields can stay (harmless when unused). To remove them: delete the Wash Production Plan records, then the DocTypes and the two Custom Fields from the Desk.
- Material Request Project: if the mandatory rule must be restored, set `reqd=1` and clear `mandatory_depends_on` on `Material Request-custom_project` in both fixture files and migrate.
- Take a database backup before step 2 (`bench --site erp.motleyterpz.io backup`).
