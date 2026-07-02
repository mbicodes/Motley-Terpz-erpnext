"""Create the Sales Order crm_deal field for quote-to-order linkage."""

from cannabis_management.overrides.quote_to_order import install_quote_to_order_fields


def execute():
    install_quote_to_order_fields()
