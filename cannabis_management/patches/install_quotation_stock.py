"""Create the Quotation Item live-stock field."""

from cannabis_management.api.quotation_stock import install_quotation_stock_fields


def execute():
    install_quotation_stock_fields()
