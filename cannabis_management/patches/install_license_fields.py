"""Create Customer license / compliance fields."""

from cannabis_management.overrides.license_compliance import install_license_fields


def execute():
    install_license_fields()
