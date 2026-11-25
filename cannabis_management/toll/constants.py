"""Toll processing: names of the master data the toll flow runs on (created by toll.install)."""

COMPANY = "Master Touch Manufacturing"
ABBR = "MTM"

WH_GROUP = "Toll Warehouses - MTM"
WH_INBOUND = "Toll Inbound - MTM"
WH_WIP = "Toll WIP - MTM"
WH_OUTPUT = "Toll Output - MTM"

ITEM_GROUP = "Toll - Customer Owned"
ITEM_FF = "TOLL-FF"
ITEM_BH = "TOLL-BH"
ITEM_ROSIN = "TOLL-ROSIN"
ITEM_SVC = "TOLL-SVC"
UOM_FF = "Pound"
UOM_G = "Gram"

CUSTOMER_GROUP = "Toll Clients"
GENERIC_CUSTOMER = "Toll Client - Generic"
INCOME_ACCOUNT = "Toll Processing Income - MTM"
# expense account on toll Delivery Note rows: required by ERPNext, never posted (toll returns are zero value)
RETURN_EXPENSE_ACCOUNT = "Toll Material Returns - MTM"

LB_TO_G = 453.592

STATUSES = ("Received", "Queued for Wash", "Washed", "Pressed", "Ready to Return", "Returned", "Invoiced", "Cancelled")
RETURN_TYPES = ("Bubble Hash", "Rosin", "Both")
RATE_BASES = ("Per lb FF Input", "Per Gram Output", "Flat per Job")
LOCATIONS = ("Freezer", "Freezer 2", "Freezer 3", "Freezer 4", "Other")

# Board actions by role. Leo (Production User in the spec) holds Manufacturing User / Manager on this site.
PRODUCE_ROLES = {"Manufacturing User", "Manufacturing Manager", "Production Manager", "System Manager"}
INVOICE_ROLES = {"Accounts User", "Accounts Manager", "Production Manager", "System Manager"}
CANCEL_ROLES = {"Production Manager", "System Manager"}
VIEW_ROLES = PRODUCE_ROLES | INVOICE_ROLES

# Order of the steps; a stock document cannot be cancelled while a later step exists (rule 9).
STEP_RANK = {"Receive": 1, "Wash": 2, "Press": 3, "Move to Output": 3, "Return": 4, "Invoice": 5}
