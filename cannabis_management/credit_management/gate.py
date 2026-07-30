"""Credit Management — the Outbound Gate ("Gate 1").

A single decision point enforced at every outbound checkpoint (Sales Order
submit, Delivery Note submit, and later production/manifest). It enforces, in
order: company-wide freeze -> hold status -> COD default -> credit line.

Quotations are never gated (policy: "quotes may continue"). Release from a hold
is a Finance-only action.
"""

import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.credit_management.doctype.credit_profile.credit_profile import get_or_create
from cannabis_management.credit_management import tasks

# Sales Order custom_mode_of_payment values that mean "cash secured" (no
# unsecured exposure created): COD / prepaid. Anything else is credit terms.
SECURED_MODES = {"COD", "Cash", "Prepaid", "Advance"}


def _is_credit_order(mode_of_payment):
    """True when the order extends unsecured credit (Payment Terms)."""
    if not mode_of_payment:
        # No explicit mode -> treat as credit (conservative).
        return True
    return mode_of_payment not in SECURED_MODES


def evaluate(customer, mode_of_payment, projected_amount=0.0, is_physical_movement=False):
    """Return a decision dict:
        {block: bool, reason: str, warnings: [str]}

    is_physical_movement=True for steps that actually move product
    (Delivery Note, production, manifest) — a Hard/Immediate hold blocks those
    outright regardless of payment mode.
    """
    warnings = []
    if not customer:
        return {"block": False, "reason": "", "warnings": warnings}

    settings = tasks._settings()
    profile = get_or_create(customer)
    is_credit = _is_credit_order(mode_of_payment)

    # 1) Holds — hard/immediate stop everything that moves product or extends credit.
    if profile.hold_status in ("Hard Hold", "Immediate Hold"):
        if is_physical_movement or is_credit:
            return {
                "block": True,
                "reason": _(
                    "{0} is on {1}: {2}. Nothing moves into production, staging, "
                    "manifest, or credit release until Finance releases the hold."
                ).format(customer, profile.hold_status, profile.hold_reason or "past due"),
                "warnings": warnings,
            }
    elif profile.hold_status == "Warning":
        warnings.append(
            _("{0} has a past-due balance ({1}). Collect before extending more credit.").format(
                customer, profile.hold_reason or ""
            )
        )

    # 2) Company-wide freeze — no NEW unsecured exposure for anyone (COD still OK).
    if settings.is_frozen and is_credit:
        return {
            "block": True,
            "reason": _(
                "Company-wide credit freeze is active ({0}). New orders must be COD or "
                "prepaid. Freeze exceptions require CEO and MD approval."
            ).format(settings.frozen_reason or ""),
            "warnings": warnings,
        }

    # 2b) Workout accounts — zero new unsecured exposure; COD/prepaid + paydown only.
    if profile.status == "Workout":
        if is_credit:
            return {
                "block": True,
                "reason": _(
                    "{0} is a Workout account — no new unsecured exposure. New orders must "
                    "be COD/prepaid with the required paydown against old debt."
                ).format(customer),
                "warnings": warnings,
            }
        req = _workout_paydown_required(profile.customer, projected_amount)
        if req:
            warnings.append(
                _("Workout account: collect the required paydown of ${0:,.2f} against old "
                  "debt before releasing product (no paydown, no product).").format(req)
            )
        return {"block": False, "reason": "", "warnings": warnings}

    # 3) COD default — an account without approved credit cannot buy on terms.
    if is_credit and profile.status not in ("Credit Approved", "Payment Plan"):
        return {
            "block": True,
            "reason": _(
                "{0} is a COD account — credit is not formally approved. "
                "Set the order to COD/prepaid, or complete credit approval first."
            ).format(customer),
            "warnings": warnings,
        }

    # 4) Credit line — revolving exposure across the credit group must not exceed
    #    the approved line. Disputed amounts are excluded from the line. Over-line
    #    orders need a cleared deposit covering the excess (no single-order exception).
    if is_credit and profile.status in ("Credit Approved", "Payment Plan"):
        from cannabis_management.credit_management.doctype.ar_dispute.ar_dispute import disputed_total_for_customer
        snap = tasks.receivable_snapshot(tasks.group_customers(profile))
        disputed = disputed_total_for_customer(profile.customer)
        projected = max(0.0, flt(snap["total_outstanding"]) - disputed) + flt(projected_amount)
        line = flt(profile.approved_line)
        if line > 0 and projected > line:
            excess = projected - line
            deposit = _available_deposit(profile.customer)
            if deposit >= excess:
                warnings.append(
                    _("Over line by ${0:,.2f} — covered by a cleared deposit of ${1:,.2f}.").format(
                        excess, deposit
                    )
                )
            else:
                return {
                    "block": True,
                    "reason": _(
                        "Over credit line: projected exposure ${0:,.2f} exceeds the approved "
                        "line ${1:,.2f}. A cleared deposit of ${2:,.2f} is required (only "
                        "${3:,.2f} on hand). No single-order exceptions."
                    ).format(projected, line, excess, deposit),
                    "warnings": warnings,
                }

    return {"block": False, "reason": "", "warnings": warnings}


def _available_deposit(customer):
    """Unallocated advance receipts that can secure an over-line order."""
    rows = frappe.get_all(
        "Payment Entry",
        filters={
            "party_type": "Customer", "party": customer,
            "payment_type": "Receive", "docstatus": 1,
            "unallocated_amount": [">", 0],
        },
        pluck="unallocated_amount",
    )
    return sum(flt(x) for x in rows)


def _workout_paydown_required(customer, order_amount):
    """Required paydown for a workout order (fixed or % of order)."""
    from cannabis_management.credit_management.doctype.workout_terms.workout_terms import get_active_workout
    w = get_active_workout(customer)
    if not w:
        return 0.0
    if w.paydown_type == "Fixed per Order":
        return flt(w.paydown_value)
    return flt(order_amount) * flt(w.paydown_value) / 100.0


# ---------------------------------------------------------------------------
# Hook entry points
# ---------------------------------------------------------------------------

def _observe_mode():
    return (tasks._settings().enforcement_mode or "Enforce") == "Observe"


def _apply(decision, block_title):
    """Emit warnings; block only in Enforce mode. In Observe mode a would-be
    block is downgraded to a visible warning so nothing is stopped."""
    for w in decision["warnings"]:
        frappe.msgprint(w, title=_("Credit Warning"), indicator="orange", alert=True)
    if decision["block"]:
        if _observe_mode():
            frappe.msgprint(
                _("[Observe mode — not blocked] {0}").format(decision["reason"]),
                title=block_title, indicator="red",
            )
        else:
            frappe.throw(decision["reason"], title=block_title)


def check_sales_order(doc, method=None):
    """before_submit on Sales Order — Gate 1."""
    decision = evaluate(
        customer=doc.customer,
        mode_of_payment=getattr(doc, "custom_mode_of_payment", None),
        projected_amount=flt(doc.grand_total),
        is_physical_movement=False,
    )
    _apply(decision, _("Credit Hold — Order Blocked"))


def on_customer_insert(doc, method=None):
    """Every new Customer gets a default COD Credit Profile."""
    try:
        get_or_create(doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Credit Profile auto-create failed")


def check_delivery_note(doc, method=None):
    """before_submit on Delivery Note — physical movement of product."""
    decision = evaluate(
        customer=doc.customer,
        mode_of_payment=None,
        projected_amount=0.0,
        is_physical_movement=True,
    )
    _apply(decision, _("Credit Hold — Delivery Blocked"))
