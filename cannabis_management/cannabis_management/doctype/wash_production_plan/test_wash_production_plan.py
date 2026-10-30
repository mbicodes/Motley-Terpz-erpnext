import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from cannabis_management.cannabis_management.doctype.wash_production_plan import wash_production_plan as w
from cannabis_management.doc_hooks import wash_plan_sync as sync

FRZ = "Freezer - MTM"


def _item(code, name, group):
    # Item naming may ignore item_code (series), so always use the name that was actually assigned.
    existing = frappe.db.get_value("Item", {"item_name": name, "item_group": group}, "name")
    if existing:
        return existing
    d = frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": group,
                        "stock_uom": "LBS" if "Fresh" in group else "Gram", "is_stock_item": 1}).insert()
    return d.name


def _stock(item, wh, qty, project=None):
    """Stock as the Stock Ledger sees it (project = inventory dimension) plus the Bin row."""
    frappe.get_doc({"doctype": "Stock Ledger Entry", "item_code": item, "warehouse": wh, "actual_qty": qty,
                    "project": project, "is_cancelled": 0, "posting_date": today(), "voucher_type": "Stock Entry",
                    "voucher_no": "ZZ-TEST", "company": "Master Touch Manufacturing"}).db_insert()
    if not frappe.db.exists("Bin", {"item_code": item, "warehouse": wh}):
        frappe.get_doc({"doctype": "Bin", "item_code": item, "warehouse": wh, "actual_qty": 0}).db_insert()
    frappe.db.sql("update tabBin set actual_qty = actual_qty + %s where item_code = %s and warehouse = %s", (qty, item, wh))


def _plan(rows, **kw):
    s = w.get_settings()
    d = frappe.get_doc({"doctype": "Wash Production Plan", "company": s.default_company, "plan_type": "Weekly",
                        "from_date": today(), "items": rows, **kw})
    return d


def _row(item, lbs, project=None, bh=None, rs=None, freezer=FRZ):
    return {"planned_date": today(), "fresh_frozen_item": item, "source_freezer": freezer,
            "planned_qty_lbs": lbs, "project": project, "bubble_hash_item": bh, "rosin_item": rs}


class TestWashProductionPlan(FrappeTestCase):
    def setUp(self):
        self.s = w.get_settings()
        self.ff = _item("ZZ-FF-T1", "Zztest Berry_L - Fresh Frozen", self.s.fresh_frozen_item_group)
        self.bh = _item("ZZ-BH-T1", "Zztest Berry - Bubble Hash", self.s.bubble_hash_item_group)
        self.rs = _item("ZZ-RS-T1", "Zztest Berry - Rosin", self.s.rosin_item_group)
        for dt in ("Bin", "Stock Ledger Entry"):
            frappe.db.delete(dt, {"item_code": self.ff})
        _stock(self.ff, FRZ, 100)

    def tearDown(self):
        frappe.db.rollback()  # FrappeTestCase only rolls back per class; isolate each test

    # math / names / period
    def test_math(self):
        r = frappe._dict(planned_qty_lbs=50, expected_hash_yield=2.5, expected_rosin_yield=75)
        w.row_math(r)
        self.assertAlmostEqual(r.planned_qty_grams, 22679.6, 1)
        self.assertAlmostEqual(r.expected_hash_g, 566.99, 2)
        self.assertAlmostEqual(r.expected_rosin_g, 425.24, 2)

    def test_base_names(self):
        for n, b in (("Berry Sour_L - Fresh Frozen", "Berry Sour"), ("Gary Payton_6", "Gary Payton"),
                     ("Grease Bucket_10_S", "Grease Bucket"), ("Red Lemon #3_10", "Red Lemon #3"),
                     ("Banana Zikigai x Strawberry Marmalade_10- FF", "Banana Zikigai x Strawberry Marmalade"),
                     ("Zkyscrapers #1 _10 - FF", "Zkyscrapers #1"), ("Pie Hoe_10 - FF", "Pie Hoe"),
                     ("Plain Strain - FF", "Plain Strain"), ("Plain Strain - fresh frozen", "Plain Strain")):
            self.assertEqual(w.base_name(n), b, n)

    def test_period_validation(self):
        p = _plan([_row(self.ff, 5)], plan_type="Custom", to_date=add_days(today(), -1))
        self.assertRaises(frappe.ValidationError, p.insert)

    def test_date_outside_period(self):
        r = _row(self.ff, 5); r["planned_date"] = add_days(today(), 30)
        self.assertRaises(frappe.ValidationError, _plan([r]).insert)

    # suggestions
    def test_suggest_name_fallback_and_empty(self):
        out = w.suggest_finished_items(self.ff)
        self.assertEqual((out["bubble_hash_item"], out["rosin_item"]), (self.bh, self.rs))
        other = _item("ZZ-FF-T2", "Zznomatch_3 - FF", self.s.fresh_frozen_item_group)
        out = w.suggest_finished_items(other)
        self.assertEqual((out["bubble_hash_item"], out["rosin_item"]), (None, None))

    # availability
    def test_availability_uses_actual_minus_booked(self):
        self.assertEqual(w.get_available_qty(self.ff, FRZ), 100)
        p = _plan([_row(self.ff, 30, bh=self.bh, rs=self.rs)]).insert()
        self.assertEqual(w.get_available_qty(self.ff, FRZ), 70)
        self.assertEqual(w.get_available_qty(self.ff, FRZ, p.items[0].name), 100)
        frappe.db.set_value("Bin", {"item_code": self.ff, "warehouse": FRZ}, "projected_qty", 999)
        self.assertEqual(w.get_available_qty(self.ff, FRZ), 70)

    def test_availability_per_project(self):
        _stock(self.ff, FRZ, 50, "PROJ-0055")
        self.assertEqual(w.get_available_qty(self.ff, FRZ, project="PROJ-0055"), 50)
        self.assertEqual(w.get_available_qty(self.ff, FRZ), 100)
        self.assertEqual(sorted((x.project, x.qty) for x in w.get_stock_projects(self.ff, FRZ)), [("", 100), ("PROJ-0055", 50)])
        _plan([_row(self.ff, 30, project="PROJ-0055")]).insert()
        self.assertEqual(w.get_available_qty(self.ff, FRZ, project="PROJ-0055"), 20)
        self.assertEqual(w.get_available_qty(self.ff, FRZ), 100)

    def test_project_balance_capped_by_real_stock(self):
        # 100 lbs received under a project, 80 lbs issued without one: only 20 lbs are really there
        frappe.db.delete("Stock Ledger Entry", {"item_code": self.ff})
        frappe.db.set_value("Bin", {"item_code": self.ff, "warehouse": FRZ}, "actual_qty", 0)
        _stock(self.ff, FRZ, 100, "PROJ-0055")
        _stock(self.ff, FRZ, -80)
        self.assertEqual([(x.project, x.qty, x.ledger_qty) for x in w.get_stock_projects(self.ff, FRZ)], [("PROJ-0055", 20, 100)])
        self.assertEqual(w.get_available_qty(self.ff, FRZ, project="PROJ-0055"), 20)
        p = _plan([_row(self.ff, 15, project="PROJ-0055", bh=self.bh, rs=self.rs),
                   _row(self.ff, 10, project="PROJ-0055", bh=self.bh, rs=self.rs)]).insert()
        self.assertEqual([r.available_qty_lbs for r in p.items], [20, 5])
        self.assertEqual(w.get_item_freezers(self.ff), [{"warehouse": FRZ, "qty": 20, "free": 0}])

    def test_project_less_row_blocked_when_stock_is_under_a_project(self):
        frappe.db.delete("Stock Ledger Entry", {"item_code": self.ff})
        _stock(self.ff, FRZ, 100, "PROJ-0055")
        p = _plan([_row(self.ff, 10, bh=self.bh, rs=self.rs)]).insert()
        self.assertEqual(w.create_material_requests(p.name)["made"], [])
        self.assertIn("Choose a project", " ".join(m["message"] for m in frappe.message_log))

    def test_allocation_flags_only_the_row_that_exceeds(self):
        frappe.db.delete("Stock Ledger Entry", {"item_code": self.ff})
        _stock(self.ff, FRZ, 40)
        frappe.clear_messages()
        p = _plan([_row(self.ff, 30, bh=self.bh, rs=self.rs), _row(self.ff, 20, bh=self.bh, rs=self.rs)]).insert()
        msg = " ".join(m["message"] for m in frappe.message_log)
        self.assertIn("Row 2", msg); self.assertIn("by 10", msg); self.assertNotIn("Row 1", msg)
        self.assertEqual([r.available_qty_lbs for r in p.items], [40, 10])
        res = w.create_material_requests(p.name)
        self.assertEqual([m["row"] for m in res["made"]], [1])
        self.assertEqual(len(res["skipped"]), 1)

    def test_stale_open_mr_is_listed_as_holder(self):
        mr = frappe.get_doc({"doctype": "Material Request", "material_request_type": "Manufacture",
                             "company": "Master Touch Manufacturing", "schedule_date": today(), "set_warehouse": FRZ,
                             "custom_routing": self.s.routing, "items": [{"item_code": self.ff, "qty": 25, "uom": "LBS",
                             "warehouse": FRZ, "schedule_date": today(), "conversion_factor": 1}]})
        mr.insert(); mr.db_set("docstatus", 1)
        ext, holders = w.external_holds(self.ff, FRZ)
        self.assertEqual(ext, 25)
        self.assertIn(mr.name, holders[0])
        p = _plan([_row(self.ff, 80)]).insert()
        self.assertIn(mr.name, p.items[0].stock_held_by)

    def test_new_item_codes_continue_the_series(self):
        a = w.create_finished_item("Zzseries One", "rosin")
        b = w.create_finished_item("Zzseries Two", "rosin")
        self.assertTrue(a.startswith("RS") and b.startswith("RS"))
        self.assertEqual(int(b[2:]), int(a[2:]) + 1)
        self.assertGreater(int(a[2:]), 23)

    # MR building
    def test_mr_build_project_and_empty_project(self):
        proj = frappe.db.get_value("Project", {"status": "Open"}, "name")
        _stock(self.ff, FRZ, 100, proj)
        p = _plan([_row(self.ff, 50, project=proj, bh=self.bh, rs=self.rs),
                   _row(self.ff, 10, bh=self.bh, rs=self.rs)]).insert()
        res = w.create_material_requests(p.name)
        self.assertEqual(len(res["made"]), 2, res)
        mrs = [frappe.get_doc("Material Request", m["mr"]) for m in res["made"]]
        a, b = mrs
        self.assertEqual(a.material_request_type, "Manufacture")
        self.assertEqual(a.set_warehouse, FRZ)
        self.assertEqual(a.custom_routing, self.s.routing)
        self.assertEqual(a.custom_project, proj)
        self.assertFalse(b.custom_project)
        self.assertEqual((a.items[0].item_code, a.items[0].qty, a.items[0].uom), (self.ff, 50, "LBS"))
        h, r = a.custom_finished_goods
        self.assertEqual((h.item, h.operation, h.expected_yield_), (self.bh, "Hash Processing", 2.5))
        self.assertAlmostEqual(h.finished_qty_grams, 566.99, 2)
        self.assertEqual((r.item, r.operation, r.expected_yield_), (self.rs, "Rosin Pressing", 75))
        self.assertAlmostEqual(r.finished_qty_grams, 425.24, 2)
        p.reload()
        self.assertEqual(p.status, "In Progress")
        self.assertEqual(p.items[0].row_status, "MR Created")

    def test_mr_blocked_cases(self):
        p = _plan([_row(self.ff, 150, bh=self.bh, rs=self.rs), _row(self.ff, 5)]).insert()
        res = w.create_material_requests(p.name)
        self.assertEqual(res["made"], [])
        self.assertEqual(len(res["skipped"]), 2)

    # sync
    def _linked(self):
        p = _plan([_row(self.ff, 50, bh=self.bh, rs=self.rs)]).insert()
        mr = frappe.get_doc("Material Request", w.create_material_requests(p.name)["made"][0]["mr"])
        return p, mr

    def _wo(self, mr, item, produced):
        wo = frappe.get_doc({"doctype": "Work Order", "production_item": item, "material_request": mr.name,
                             "qty": 1, "produced_qty": produced, "company": mr.company})
        wo.db_insert()
        return wo

    def test_sync_stock_entry_submit_and_cancel(self):
        p, mr = self._linked()
        hwo, rwo = self._wo(mr, self.bh, 0), self._wo(mr, self.rs, 0)
        for wo in (hwo, rwo):
            sync.work_order_after_insert(wo)
        row = frappe.get_doc("Wash Production Plan", p.name).items[0]
        self.assertEqual((row.hash_work_order, row.rosin_work_order), (hwo.name, rwo.name))
        se = lambda wo: frappe._dict(purpose="Manufacture", work_order=wo.name)
        frappe.db.set_value("Work Order", hwo.name, "produced_qty", 996)
        sync.stock_entry_sync(se(hwo))
        row = frappe.get_doc("Wash Production Plan", p.name).items[0]
        self.assertEqual((row.row_status, row.actual_hash_g), ("Washed", 996))
        self.assertAlmostEqual(row.actual_hash_yield, 996 / 22679.6 * 100, 3)
        frappe.db.set_value("Work Order", rwo.name, "produced_qty", 753)
        sync.stock_entry_sync(se(rwo))
        pl = frappe.get_doc("Wash Production Plan", p.name)
        self.assertEqual((pl.items[0].row_status, pl.status), ("Completed", "Completed"))
        frappe.db.set_value("Work Order", rwo.name, "produced_qty", 0)
        sync.stock_entry_sync(se(rwo))
        self.assertEqual(frappe.get_doc("Wash Production Plan", p.name).items[0].row_status, "Washed")
        frappe.db.set_value("Work Order", hwo.name, "produced_qty", 0)
        sync.stock_entry_sync(se(hwo))
        self.assertEqual(frappe.get_doc("Wash Production Plan", p.name).items[0].row_status, "MR Created")

    def test_mr_cancel_resets_row(self):
        p, mr = self._linked()
        sync.material_request_unlink(mr)
        pl = frappe.get_doc("Wash Production Plan", p.name)
        self.assertEqual((pl.items[0].row_status, pl.items[0].material_request, pl.status), ("Planned", None, "Draft"))

    def test_locked_row_cannot_edit(self):
        p, mr = self._linked()
        p.reload(); p.items[0].planned_qty_lbs = 5
        self.assertRaises(frappe.ValidationError, p.save)

    def test_overbook_warning_counts_own_rows_once(self):
        p = _plan([_row(self.ff, 60), _row(self.ff, 30)]).insert()  # 90 of 100: no warning
        frappe.clear_messages()
        p.append("items", _row(self.ff, 20)); p.save()  # 110 of 100: exceeds by 10 only
        msg = " ".join(m["message"] for m in frappe.message_log)
        self.assertIn("Row 3", msg)
        self.assertIn("by 10", msg)
        self.assertNotIn("Row 2", msg)
