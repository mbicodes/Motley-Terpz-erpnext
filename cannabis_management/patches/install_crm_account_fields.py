"""Create cannabis-specific CRM account fields (license, city/state, credit)
and surface them in the CRM Lead / Organization side panels."""

from cannabis_management.api.crm_account_enhancements import install_crm_account_fields


def execute():
    install_crm_account_fields()
