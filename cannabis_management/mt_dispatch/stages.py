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

FULFILLMENT = "fulfillment"
COMPLIANCE = "compliance"
APPROVER = "approver"
FINANCE = "finance"
DISPATCH = "dispatch"

ALL_FLAGS = [FULFILLMENT, COMPLIANCE, APPROVER, FINANCE, DISPATCH]

COD = "Cash On Delivery"
TERMS = "Payment Terms"

APPROVAL_CLEAR = {"Approved", "Not Required"}
