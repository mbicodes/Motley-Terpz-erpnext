"""
Slack alert utilities for Masters Touch Manufacturing module.

Webhook URLs are stored in site_config.json under keys like:
  "slack_mtm_production"   -> #mtm-production
  "slack_mtm_quality"      -> #mtm-quality
  "slack_mtm_compliance"   -> #mtm-compliance
  "slack_mtm_finance"      -> #mtm-finance

Usage:
    from cannabis_management.master_touch_manufacturing.utils.slack import send_alert
    send_alert("slack_mtm_production", "Work Order WO-001 started")
"""

import frappe
import requests


def send_alert(config_key: str, message: str, blocks: list = None) -> None:
    """
    Post a message to a Slack channel via webhook URL stored in site_config.

    Args:
        config_key:  Key in site_config.json that holds the webhook URL
        message:     Plain-text fallback message
        blocks:      Optional Slack Block Kit payload list
    """
    webhook_url = frappe.conf.get(config_key)
    if not webhook_url:
        frappe.log_error(
            f"Slack webhook not configured: {config_key}",
            "MTM Slack Alert"
        )
        return

    payload = {"text": message}
    if blocks:
        payload["blocks"] = blocks

    try:
        resp = requests.post(webhook_url, json=payload, timeout=5)
        resp.raise_for_status()
    except Exception as e:
        frappe.log_error(
            f"Slack alert failed [{config_key}]: {e}\nMessage: {message}",
            "MTM Slack Alert"
        )


# ---------------------------------------------------------------------------
# Pre-built alert helpers (called from Server Scripts / doc_events)
# ---------------------------------------------------------------------------

def alert_work_order_started(work_order_name: str, item: str, qty: float) -> None:
    """WO → In Process transition."""
    send_alert(
        "slack_mtm_production",
        f":factory: *Work Order Started*\n`{work_order_name}` | Item: {item} | Qty: {qty}"
    )


def alert_wash_batch_submitted(batch_name: str, strain: str, input_lbs: float) -> None:
    """Wash Batch submitted."""
    send_alert(
        "slack_mtm_production",
        f":droplet: *Wash Batch Submitted*\n`{batch_name}` | Strain: {strain} | Input: {input_lbs} LBS"
    )


def alert_press_batch_submitted(batch_name: str, strain: str, input_g: float) -> None:
    """Press Batch submitted."""
    send_alert(
        "slack_mtm_production",
        f":fire: *Press Batch Submitted*\n`{batch_name}` | Strain: {strain} | Input: {input_g}g"
    )


def alert_low_yield(
    doc_name: str, doc_type: str, actual_pct: float, threshold_pct: float
) -> None:
    """Yield below threshold — requires supervisor review."""
    send_alert(
        "slack_mtm_quality",
        f":warning: *Low Yield Alert*\n`{doc_type}` `{doc_name}`\n"
        f"Actual yield: *{actual_pct:.1f}%* (threshold: {threshold_pct:.1f}%)\n"
        f"Supervisor approval required before Stock Entry submission."
    )


def alert_quality_inspection_result(qi_name: str, item: str, grade: str, result: str) -> None:
    """QI completed — grade assigned."""
    emoji = ":white_check_mark:" if result == "Accepted" else ":x:"
    send_alert(
        "slack_mtm_quality",
        f"{emoji} *QI Result*\n`{qi_name}` | Item: {item} | Grade: {grade} | Result: {result}"
    )


def alert_metrc_retag_required(batch_name: str, item: str, old_tag: str) -> None:
    """METRC re-tag required after lab result grade change."""
    send_alert(
        "slack_mtm_compliance",
        f":label: *METRC Re-Tag Required*\n`{batch_name}` | Item: {item}\n"
        f"Old tag: `{old_tag}` — print new tag and scan to confirm."
    )


def alert_production_batch_completed(batch_name: str, strain: str) -> None:
    """Production Batch Group marked complete."""
    send_alert(
        "slack_mtm_production",
        f":tada: *Production Batch Complete*\n`{batch_name}` | Strain: {strain}"
    )


def alert_invoice_generated(invoice_name: str, supplier: str, amount: float) -> None:
    """Toll service invoice created."""
    send_alert(
        "slack_mtm_finance",
        f":receipt: *Toll Invoice Created*\n`{invoice_name}` | Customer: {supplier} | Amount: ${amount:,.2f}"
    )
