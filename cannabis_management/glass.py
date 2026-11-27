"""Motley Glass on every Desk page (Page doctype): the Sales Operation Board look (logo gradient, no bar behind the
title, capsule buttons, glass filter row, frosted cards, system font). public/js/motley_glass_auto.js applies it to the
pages listed in frappe.boot.mg_glass_pages; public/css/motley_glass.css + motley_glass_auto.css hold the look.
Since 2026-11-27 ("ERP System - Global UI Changes" PDF) this covers the pages of every installed app, not only
cannabis_management, minus the tools below that are not filter pages."""
import frappe

# pages that draw the glass look themselves (their own markup on the Motley Glass kit, or SOB itself)
OWN_GLASS = {"sales-operation-board", "toll-processing-board", "toll-stock-on-hand", "toll-job-yield-summary",
	"wash-plan-board", "press-plan-board"}
# pages that keep their own look: print preview / builders (their white sheet is the document itself), the setup
# wizard, the till (Point of Sale is a full-screen cashier app, not a filter page), the workflow canvas, and
# Insights (opens its own app at /insights)
NOT_DESK_PAGES = {"print", "print-format-builder", "print-format-builder-beta", "setup-wizard", "point-of-sale",
	"workflow-builder", "insights"}
# kill switch: page names that must keep their old look
GLASS_EXCLUDE = set()


def boot_session(bootinfo):
	try:
		pages = frappe.get_all("Page", filters={"standard": "Yes"}, pluck="name")
		bootinfo.mg_glass_pages = sorted(set(pages) - OWN_GLASS - NOT_DESK_PAGES - GLASS_EXCLUDE)
	except Exception:
		bootinfo.mg_glass_pages = []
