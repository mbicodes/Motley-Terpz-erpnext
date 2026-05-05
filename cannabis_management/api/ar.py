# apps/cannabis_management/cannabis_management/api/ar.py

import json
import frappe
from frappe.utils import flt, nowdate

# Receivable accounts that the AR Reconciliation considers.
# Equivalent to the GL Report filter: account IN (...).
DEFAULT_RECEIVABLE_ACCOUNTS = ["Debtors - MT", "Debtors - TSBC"]

# Each entry: (display_label_for_table, [erpnext_customer_names_to_sum])
AR_RECONCILIATION_ROWS = [
    ("1904 Provisions",                                ["1904 Provisions"]),
    ("A1 Extracts / The Creamery / 710 Tribe",         ["A1 Extracts - The Creamery", "The Creamery", "710 Tribe"]),
    ("BEGK Inc.",                                      ["BEGK Inc."]),
    ("Ben",                                            ["Ben"]),
    ("Brand Ambassador",                               ["Brand Ambassador - Viki"]),
    ("Buddies Brand",                                  ["Buddies Brand"]),
    ("Cali Kush Farms",                                ["Cali Kush Farms"]),
    ("CannaCraft / CRFT Manufacturing",                ["CannaCraft", "CRFT Manufacturing Inc."]),
    ("Red Dragon Extracts",                            ["Red Dragon Extracts"]),
    ("Chads Distro",                                   ["CHADS DISTRO"]),
    ("Champelli",                                      ["Champelli"]),
    ("KYLE",                                           ["Kyle"]),
    ("Reaps",                                          ["Reaps"]),
    ("Marty Motley Influencer",                        ["Marty- Motley Influencer"]),
    ("Phil",                                           ["Phil"]),
    ("Sasquatch (Lonely Hash Makers)",                 ["Sasquatch (Lonely Hash Makers)"]),
    ("Rosin Tech",                                     ["Rosin Tech"]),
    ("Chelby",                                         ["Chelby"]),
    ("Tori",                                           ["Tori"]),
    ("Crown",                                          ["Crown"]),
    ("Binesh",                                         ["Binesh"]),
    ("Greendawg",                                      ["Greendawg"]),
    ("Greenmount LLC",                                 ['"Greenmount, LLC (Cold Fire)"']),
    ("Issa",                                           ["Issa"]),
    ("Jay / Happy Dreams",                             ["Jay", "Jay/ Happy Dreams Genetics"]),
    ("Jeff",                                           ["Jeff"]),
    ("Joey",                                           ["Joey"]),
    ("Hamsa",                                          ["Hamsa"]),
    ("First Smoke of the Day",                         ["first smoke of the day"]),
    ("House of Hash",                                  ["House of Hash"]),
    ("Mellow Groups",                                  ["Mellow Group"]),
    ("Mikey - (Joey Referral)",                        ["Mikey - (Joey Referral)"]),
    ("Muha Meds",                                      ["Muha Meds"]),
    ("NATURA",                                         ["Natura"]),
    ("The Hydro Boys",                                 ["The Hydro Boys"]),
    ("Uncle Arnies",                                   ["Uncle Arnies"]),
    ("LRG Onboarding",                                 ["LRG Onboarding"]),
    ("Blue Distro",                                    ["Blue Distro"]),
    ("Supply Distro",                                  ["Supply Distro"]),
    ("Quale",                                          ["Quale"]),
    ("Ron",                                            ["Ron"]),
    ("Solex Distribution Group, INC (GOODFELLAS)",     [
        "Solex Distribution Group, INC (Goodfellas)",
        '"Solex Distribution Group, INC (Goodfellas)"',
        "Goodfellas",
    ]),
    ("Master Maker",                                   ["Master Makers"]),
    ("Babaku",                                         ["Babaku"]),
    ("Banana Pearls",                                  ["Banana Pearls"]),
    ("Karisma",                                        ["Karisma"]),
    ("Dream Field",                                    ["Dream Field"]),
    ("Lusso Extracts",                                 ["Lusso Extracts"]),
    ("Tamalpais Co-Packing",                           ["Tamalpais Co-Packing"]),
    ("TLG Management / Plug Play",                     ["TLG Management", "Plug Play"]),
    ('Cake "She hits different"',                      ['Cake "She Hits Different"']),
    ("Clone Goddess",                                  ["Clone Goddess"]),
    ("Don Perico",                                     ["Don Perico"]),
    ("7030 Haven",                                     ["7030 Haven"]),
    ("Franklin Oz",                                    ["Franklin Oz"]),
    ("WOCK",                                           ["WOCK"]),
    ("PRFCT LABS",                                     ["PRFCT Labs"]),
    ("The 10 Spot (Litto)",                            ["The 10 Spot (Litto)"]),
    ("Vuze",                                           ["Vuze"]),
    ("510 Consultants / Industries",                   ["510 Consultants", "510 Industries"]),
    ("818 Brand",                                      ["818 Brands Los Angeles LLC (Brand)"]),
    ("818 Distro",                                     ["818 Brands Los Angeles LLC (Distro)"]),
    ("818 Melts",                                      ["818 Melts"]),
    ("Alan - Broker",                                  ["Alan- broker"]),
    ("Alex",                                           ["Alex"]),
    ("Bloom Network",                                  ["Bloom Network"]),
    ("Bobby",                                          ["Bobby"]),
    ("Crysp Canna",                                    ["crysp Canna"]),
    ("Cure Company",                                   ["Cure Company"]),
    ("Dog House / Squintz",                            ["Dog House", "Dog House/SQUINTZ"]),
    ("Essential Torrance",                             ["Essential Torrance"]),
    ("EXPANDO PRODUCTS, LLC",                          ["Expando Products, LLC", '"Expando Products, LLC"']),
    ("Full Spectrum",                                  ["Full Spectrum"]),
    ("Hashrite / Ollie",                               ["Hashrite", "Ollie"]),
    ("Hollywater",                                     ["Holywater"]),
    ("Infusionals INC",                                ["Infusionals INC"]),
    ("Lyfe Sauce",                                     ["Lyfe Sauce", "Lyfe Sauce (2)"]),
    ("MAVEN GENETICS",                                 ["Maven Genetics"]),
    ("Nature's Lab",                                   ["Nature's Lab"]),
    ("PAYAM",                                          ["Payam"]),
    ("Punch Media",                                    ["Punch Media"]),
    ("SAM",                                            ["Sam"]),
    ("SEVEN ZERO SEVEN (LEEF)",                        ["Seven Zero Seven (LEEF)"]),
    ("Simply Mary",                                    ["Simply Mary"]),
    ("The Originals",                                  ["The Originals"]),
    ("Chuck",                                          ["Chuck"]),
    ("TSL MANUFACTURING (BigOil)",                     ["TSL Manufacturing (BigOil)"]),
    ("Cali Hash",                                      ["Cali Hash"]),
    ("United Medical Alliance",                        ["United Medical Alliance"]),
]


def _normalize_accounts(accounts):
    """Accept list, JSON string, or comma-separated string."""
    if not accounts:
        return list(DEFAULT_RECEIVABLE_ACCOUNTS)
    if isinstance(accounts, (list, tuple)):
        return [str(a).strip() for a in accounts if str(a).strip()]
    s = str(accounts).strip()
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [str(a).strip() for a in parsed if str(a).strip()]
    except (ValueError, TypeError):
        pass
    return [a.strip() for a in s.split(",") if a.strip()]


@frappe.whitelist()
def get_ar_reconciliation(as_on_date=None, accounts=None):
    """
    AR Reconciliation summary — mirrors the General Ledger report's Balance
    column (last value) when filtered by Party + receivable accounts.

    Outstanding per row =
        SUM(debit - credit) FROM `tabGL Entry`
        WHERE party_type='Customer' AND party IN (...row's customers)
          AND account IN (Debtors - MT, Debtors - TSBC)
          AND posting_date <= as_on_date
          AND is_cancelled = 0

    Multiple ERPNext customers behind one display label are summed together.
    """
    as_on_date = as_on_date or nowdate()
    accounts = _normalize_accounts(accounts)

    rows_config = []
    all_customers = set()
    for idx, (label, customers) in enumerate(AR_RECONCILIATION_ROWS, start=1):
        rows_config.append({
            "s_no": idx,
            "label": label,
            "customers": list(customers),
        })
        all_customers.update(customers)

    unique_customers = list(all_customers)
    if not unique_customers or not accounts:
        return {
            "rows": [],
            "grand_total": 0.0,
            "as_on_date": as_on_date,
            "accounts": accounts,
        }

    params = {
        "customers": tuple(unique_customers),
        "accounts": tuple(accounts),
        "as_on": as_on_date,
    }

    gl_results = frappe.db.sql(
        """
        SELECT party AS customer,
               COALESCE(SUM(debit - credit), 0) AS balance
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND party IN %(customers)s
          AND account IN %(accounts)s
          AND posting_date <= %(as_on)s
          AND is_cancelled = 0
        GROUP BY party
        """,
        params,
        as_dict=True,
    )
    balance_map = {r["customer"]: flt(r["balance"]) for r in gl_results}

    existing = set(
        frappe.db.sql_list(
            "SELECT name FROM `tabCustomer` WHERE name IN %s",
            (tuple(unique_customers),),
        )
        or []
    )

    rows = []
    grand_total = 0.0
    for cfg in rows_config:
        amt = sum(balance_map.get(c, 0.0) for c in cfg["customers"])
        missing = [c for c in cfg["customers"] if c not in existing]
        rows.append({
            "s_no": cfg["s_no"],
            "label": cfg["label"],
            "customers": cfg["customers"],
            "outstanding": flt(amt, 2),
            "missing": missing,
        })
        grand_total += amt

    return {
        "rows": rows,
        "grand_total": flt(grand_total, 2),
        "as_on_date": as_on_date,
        "accounts": accounts,
        "currency": frappe.defaults.get_global_default("currency") or "USD",
    }