"""Motley Glass on every custom Desk page: the Sales Operation Board look (logo gradient, frosted title bar, capsule
buttons, glass filter row, frosted cards, system font). public/js/motley_glass_auto.js applies it to the pages listed
in frappe.boot.mg_glass_pages; public/css/motley_glass.css + motley_glass_auto.css hold the look."""
import frappe

# pages that draw the glass look themselves (their own markup on the Motley Glass kit, or SOB itself)
OWN_GLASS = {"sales-operation-board", "toll-processing-board", "toll-stock-on-hand", "toll-job-yield-summary",
	"wash-plan-board", "press-plan-board"}
# kill switch: page names that must keep their old look
GLASS_EXCLUDE = set()


def boot_session(bootinfo):
	try:
		modules = frappe.get_module_list("cannabis_management")
		pages = frappe.get_all("Page", filters={"module": ["in", modules], "standard": "Yes"}, pluck="name")
		bootinfo.mg_glass_pages = sorted(set(pages) - OWN_GLASS - GLASS_EXCLUDE)
	except Exception:
		bootinfo.mg_glass_pages = []
