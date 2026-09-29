"""Stage names and the small vocabulary shared across the module.

These live here rather than in flow.py because gates.py, settings.py and the
reminder job all need them, and flow.py imports gates.py. flow.py re-exports
everything below, so the spec's "TRANSITIONS table, transition(), set_stage()
live in flow.py" still holds for anything importing from there.
"""

RECEIVED = "Order Received"
AWAITING_CONVERSION = "Awaiting Conversion"
PREPARING = "Order Preparing"
PREPARED = "Order Prepared"
DN_READY = "Delivery Note Ready"
AWAITING_RELEASE = "Awaiting Release"
RELEASED = "Released"
CLOSED_OUT = "Order Closed Out"
ON_HOLD = "On Hold"
CANCELLED = "Cancelled"

# Order matters: this is the Select's option order on Sales Order.
ALL_STAGES = [
	RECEIVED,
	AWAITING_CONVERSION,
	PREPARING,
	PREPARED,
	DN_READY,
	AWAITING_RELEASE,
	RELEASED,
	CLOSED_OUT,
	ON_HOLD,
	CANCELLED,
]

TERMINAL_STAGES = {CLOSED_OUT, CANCELLED}

# Team flags, as ticked on Dispatch Team Member.
FULFILLMENT = "fulfillment"
COMPLIANCE = "compliance"
APPROVER = "approver"
FINANCE = "finance"
DISPATCH = "dispatch"

ALL_FLAGS = [FULFILLMENT, COMPLIANCE, APPROVER, FINANCE, DISPATCH]

# Sales Order.custom_mode_of_payment, verbatim from the existing Select.
COD = "Cash On Delivery"
TERMS = "Payment Terms"

# Sales Order.custom_approval_status values that let an order into the flow.
APPROVAL_CLEAR = {"Approved", "Not Required"}
