"""Create the Quotation approval custom fields (discount-threshold routing)."""

from cannabis_management.overrides.quotation_approval import install_quotation_approval_fields


def execute():
    install_quotation_approval_fields()
