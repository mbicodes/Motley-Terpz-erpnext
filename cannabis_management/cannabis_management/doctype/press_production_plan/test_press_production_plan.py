import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_datetime, getdate, today

from cannabis_management.cannabis_management.doctype.press_production_plan import press_production_plan as ppp
from cannabis_management.doc_hooks import press_plan_sync as sync

S = frappe._dict(press_sub_operation="Press Run", whipping_sub_operation="Whipping", micron_groups=[
    frappe._dict(micron_label="150u", expected_yield=76), frappe._dict(micron_label="120u - 73u", expected_yield=73),
    frappe._dict(micron_label="45u", expected_yield=59)])
G = ppp.groups(S)


def _item(code, name, group):
    # Item naming may ignore item_code (series), so always use the name that was actually assigned.
    existing = frappe.db.get_value("Item", {"item_name": name, "item_group": group}, "name")
    if existing:
        return existing
    return frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "item_group": group,
                           "stock_uom": "Gram", "is_stock_item": 1}).insert().name


def _raw(doctype, **values):
    """Fixture row written straight to the table (submitted documents without their whole chain)."""
    values.setdefault("name", frappe.generate_hash(length=12))
    frappe.get_doc(dict(doctype=doctype, **values)).db_insert()
    return values["name"]


class TestPressPlanMath(FrappeTestCase):
    """Micron split, expected rosin, yields, METRC tag and status rules (no fixtures)."""

    def test_micron_split_read(self):
        g, u = ppp.split_microns([{"micron_size": "150u", "grams_collected": 262}, {"micron_size": "120u – 73u", "grams_collected": 708},
                                  {"micron_size": "45U", "grams_collected": 26}], G)
        self.assertEqual(g, {"150": 262, "120_73": 708, "45": 26})
        self.assertFalse(u)
        g, u = ppp.split_microns([{"micron_size": "90u", "grams_collected": 50}], G)
        self.assertEqual(u, {"90u": 50})
        self.assertIn("90u", ppp.micron_note("JC-1", g, u, 50, G))
        self.assertIn("no micron split", ppp.micron_note(None, {}, {}, 100, G))

    def test_expected_rosin_math(self):
        r = frappe._dict(bh_planned_g=996, g_150=262, g_120_73=708, g_45=26, exp_yield_150=76, exp_yield_120_73=73, exp_yield_45=59,
                         act_rosin_150=207, act_rosin_120_73=532, act_rosin_45=14, actual_rosin_g=753)
        ppp.row_math(r)
        self.assertAlmostEqual(r.expected_rosin_g, 731.3, 2)
        self.assertEqual([round(r.act_yield_150, 1), round(r.act_yield_120_73, 1), round(r.act_yield_45, 1), round(r.actual_yield, 1)],
                         [79.0, 75.1, 53.8, 75.6])
        r.bh_planned_g = 498  # pressing half the BH halves every micron
        ppp.row_math(r)
        self.assertAlmostEqual(r.expected_rosin_g, 365.65, 2)

    def test_status_and_tag(self):
        wo, jc = frappe._dict(docstatus=1, status="In Process"), frappe._dict(docstatus=1)
        ops = lambda press, whip: [frappe._dict(sub_operation="Press Run", status=press), frappe._dict(sub_operation="Whipping", status=whip)]
        self.assertEqual(ppp.press_state(wo, None, [], S), "Scheduled")
        self.assertEqual(ppp.press_state(wo, frappe._dict(docstatus=0), ops("Work In Progress", "Pending"), S), "Scheduled")
        self.assertEqual(ppp.press_state(wo, frappe._dict(docstatus=0), ops("Complete", "Pending"), S), "Pressed")
        self.assertEqual(ppp.press_state(wo, jc, ops("Pending", "Pending"), S), "Pressed")
        self.assertEqual(ppp.press_state(wo, jc, ops("Complete", "Complete"), S), "Whipped")
        self.assertEqual(ppp.press_state(frappe._dict(docstatus=2), jc, [], S), "Cancelled")
        self.assertEqual(ppp.metrc_tag('{"Press Run": "TAG: 2620"}', S), "2620")
        self.assertEqual(ppp.metrc_tag('{"Whipping": "2700"}', S), "2700")


class TestPressProductionPlan(FrappeTestCase):
    """Queue, schedule / unschedule and job card sync against fixture Work Orders and job cards."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from cannabis_management import press_plan_install
        press_plan_install.install()

    def setUp(self):
        frappe.clear_document_cache("Press Plan Settings", "Press Plan Settings")
        self.s = ppp.get_settings()
        self.wh = self.s.source_warehouse
        self.bh = _item("ZZ-PPT-BH", "Zztest Press - Bubble Hash", "Bubble Hash")
        self.rs = _item("ZZ-PPT-RS", "Zztest Press - Rosin", "Raw Rosin")
        start = get_datetime(add_days(today(), -2) + " 09:30:00")
        self.hash_wo = _raw("Work Order", name="ZZ-PPT-WOH", production_item=self.bh, material_request="ZZ-PPT-MR", docstatus=1,
                            status="Completed", produced_qty=996, qty=680, company="Master Touch Manufacturing",
                            actual_end_date=get_datetime(add_days(today(), -6) + " 08:00:00"), planned_start_date=start)
        self.wo = _raw("Work Order", name="ZZ-PPT-WOR", production_item=self.rs, material_request="ZZ-PPT-MR", docstatus=1,
                       status="Not Started", qty=510, company="Master Touch Manufacturing", project=None, planned_start_date=start,
                       planned_end_date=get_datetime(add_days(today(), -2) + " 11:30:00"), wip_warehouse="Work In Progress - MTM",
                       source_warehouse=self.wh)
        self.wo_item = _raw("Work Order Item", parent=self.wo, parenttype="Work Order", parentfield="required_items",
                            item_code=self.bh, source_warehouse=self.wh, required_qty=680.388)
        _raw("Work Order Operation", parent=self.wo, parenttype="Work Order", parentfield="operations",
             operation="Rosin Pressing", workstation=self.s.press_workstation)
        self.wash_jc = _raw("Job Card", name="ZZ-PPT-JCH", work_order=self.hash_wo, operation="Hash Processing", docstatus=1)
        for m, g in (("150u", 262), ("120u - 73u", 708), ("45u", 26)):
            _raw("Micron Collection Detail", parent=self.wash_jc, parenttype="Job Card", parentfield="custom_micron_collection_detail",
                 micron_size=m, grams_collected=g)
        self.jc = _raw("Job Card", name="ZZ-PPT-JCR", work_order=self.wo, operation="Rosin Pressing", docstatus=0,
                       expected_start_date=get_datetime(add_days(today(), -2) + " 14:00:00"))
        self.ops = {op: _raw("Job Card Operation", parent=self.jc, parenttype="Job Card", parentfield="sub_operations",
                             sub_operation=op, status="Pending") for op in ("Press Run", "Whipping")}

    def tearDown(self):
        frappe.db.rollback()  # FrappeTestCase only rolls back per class; isolate each test

    def _plan(self, day=None):
        d = frappe.get_doc({"doctype": "Press Production Plan", "plan_type": "Weekly", "from_date": today(),
                            "items": [{"planned_date": day or today(), "rosin_work_order": self.wo}]})
        return d.insert()

    def _row(self, plan):
        return frappe.get_doc("Press Plan Item", plan.items[0].name)

    def test_queue_selection(self):
        q = {x.rosin_work_order: x for x in ppp.ready_queue()}
        self.assertIn(self.wo, q)
        x = q[self.wo]
        self.assertEqual(x.bh_actual_g, 996)
        self.assertEqual((x.g_150, x.g_120_73, x.g_45), (262, 708, 26))
        self.assertEqual(x.wash_job_card, self.wash_jc)
        self.assertEqual(x.days, 6)
        frappe.db.set_value("Work Order", self.hash_wo, "status", "In Process")
        self.assertNotIn(self.wo, {x.rosin_work_order for x in ppp.ready_queue()})
        frappe.db.set_value("Work Order", self.hash_wo, "status", "Completed")
        self._plan()
        self.assertNotIn(self.wo, {x.rosin_work_order for x in ppp.ready_queue()})

    def test_schedule_dates_and_consumption(self):
        day = add_days(today(), 2)
        plan = self._plan(day)
        r = self._row(plan)
        self.assertEqual((r.row_status, r.bh_actual_g, r.bh_planned_g), ("Scheduled", 996, 996))
        self.assertAlmostEqual(r.expected_rosin_g, 731.3, 2)
        wo = frappe.db.get_value("Work Order", self.wo, ["planned_start_date", "planned_end_date"], as_dict=True)
        self.assertEqual(getdate(wo.planned_start_date), getdate(day))
        self.assertEqual(get_datetime(wo.planned_start_date).strftime("%H:%M"), "09:30")
        self.assertEqual(get_datetime(wo.planned_end_date) - get_datetime(wo.planned_start_date), get_datetime("2000-01-01 11:30") - get_datetime("2000-01-01 09:30"))
        self.assertEqual(getdate(frappe.db.get_value("Job Card", self.jc, "expected_start_date")), getdate(day))
        self.assertEqual(frappe.db.get_value("Work Order Item", self.wo_item, "required_qty"), 996)
        self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": "Work Order", "reference_name": self.wo}))
        # one open plan per Work Order
        with self.assertRaises(frappe.ValidationError):
            self._plan()

    def test_yield_edit_and_unschedule(self):
        plan = self._plan(add_days(today(), 1))
        plan.items[0].exp_yield_120_73 = 80
        plan.save()
        self.assertAlmostEqual(self._row(plan).expected_rosin_g, 199.12 + 566.4 + 15.34, 2)
        plan.remove(plan.items[0])
        plan.save()
        wo = frappe.db.get_value("Work Order", self.wo, "planned_start_date")
        self.assertEqual(get_datetime(wo), get_datetime(add_days(today(), -2) + " 09:30:00"))
        self.assertEqual(get_datetime(frappe.db.get_value("Job Card", self.jc, "expected_start_date")), get_datetime(add_days(today(), -2) + " 14:00:00"))

    def test_unschedule_blocked_after_time_log_or_stock_entry(self):
        plan = self._plan()
        _raw("Job Card Time Log", parent=self.jc, parenttype="Job Card", parentfield="time_logs", operation="Press Run",
             from_time=get_datetime(today() + " 10:00:00"))
        plan.remove(plan.items[0])
        self.assertRaises(frappe.ValidationError, plan.save)
        frappe.db.delete("Job Card Time Log", {"parent": self.jc})
        _raw("Stock Entry", work_order=self.wo, purpose="Material Transfer for Manufacture", docstatus=1)
        plan = frappe.get_doc("Press Production Plan", plan.name)
        plan.remove(plan.items[0])
        self.assertRaises(frappe.ValidationError, plan.save)

    def test_job_card_sync_whipping_and_cancel(self):
        plan = self._plan()
        for m, g in (("150u", 207), ("120u - 73u", 532), ("45u", 14)):
            _raw("Micron Collection Detail", parent=self.jc, parenttype="Job Card", parentfield="custom_micron_collection_detail",
                 micron_size=m, grams_collected=g)
        frappe.db.set_value("Job Card", self.jc, {"total_completed_qty": 753, "custom_sub_op_notes": '{"Press Run": "TAG: 2620"}'})
        frappe.db.set_value("Job Card Operation", self.ops["Press Run"], "status", "Complete")
        sync.job_card_sync(frappe._dict(work_order=self.wo))
        r = self._row(plan)
        self.assertEqual((r.row_status, r.actual_rosin_g, r.metrc_tag, r.job_card), ("Pressed", 753, "2620", self.jc))
        self.assertEqual((r.act_rosin_150, r.act_rosin_120_73, r.act_rosin_45), (207, 532, 14))
        self.assertAlmostEqual(r.actual_yield, 75.6, 1)
        self.assertEqual(frappe.db.get_value("Press Production Plan", plan.name, "status"), "In Progress")
        # locked once pressed
        plan.reload()
        plan.items[0].exp_yield_150 = 50
        self.assertRaises(frappe.ValidationError, plan.save)
        # Whipping done from the Board on the submitted job card
        frappe.db.set_value("Job Card", self.jc, "docstatus", 1)
        from cannabis_management.cannabis_management.page.press_plan_board import press_plan_board as board
        res = board.complete_whipping(r.name)
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(frappe.db.get_value("Job Card Operation", self.ops["Whipping"], "status"), "Complete")
        self.assertEqual(self._row(plan).row_status, "Whipped")
        self.assertEqual(frappe.db.get_value("Press Production Plan", plan.name, "status"), "Completed")
        # cancelling the job card reverses the row
        frappe.db.set_value("Job Card", self.jc, "docstatus", 2)
        sync.job_card_sync(frappe._dict(work_order=self.wo))
        r = self._row(plan)
        self.assertEqual((r.row_status, r.actual_rosin_g, r.job_card), ("Scheduled", 0, None))
        self.assertEqual(frappe.db.get_value("Press Production Plan", plan.name, "status"), "Draft")

    def test_work_order_cancel(self):
        plan = self._plan()
        frappe.db.set_value("Work Order", self.wo, "docstatus", 2)
        sync.work_order_sync(frappe._dict(name=self.wo))
        self.assertEqual(self._row(plan).row_status, "Cancelled")
