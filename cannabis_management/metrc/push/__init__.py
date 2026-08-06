# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Operation -> handler registry for the outbox worker.

The operation string is stored on every Metrc Outbox row, so adding a new write
means adding a handler here and nothing else. An unknown operation parks the row
rather than crashing the worker.
"""

from cannabis_management.metrc.push import packages, processing, sales, transfers

HANDLERS = {
    # Sales
    "sales.receipt.create": sales.create_receipt,
    "sales.receipt.update": sales.update_receipt,
    "sales.receipt.delete": sales.delete_receipt,
    # Packages
    "packages.create": packages.create_package,
    "packages.adjust": packages.adjust_package,
    "packages.finish": packages.finish_package,
    "packages.unfinish": packages.unfinish_package,
    "packages.change_location": packages.change_location,
    "packages.change_item": packages.change_item,
    # Transfers
    "transfers.template.create": transfers.create_template,
    "transfers.template.update": transfers.update_template,
    "transfers.external_incoming.create": transfers.create_incoming,
    # Processing
    "processing.start": processing.start_job,
    "processing.createpackages": processing.create_packages,
    "processing.finish": processing.finish_job,
}
