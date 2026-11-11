"""ARCH-0003: dagitim modu ortam degiskenlerinden okunur, tanimsiz deger reddedilir."""

import pytest
from pydantic import ValidationError

from PKG_NAME.config.deployment import DeploymentSettings


def test_defaults_are_the_first_release_modes(monkeypatch):
    monkeypatch.delenv("DEPLOYMENT_TENANCY", raising=False)
    monkeypatch.delenv("DEPLOYMENT_TOPOLOGY", raising=False)
    settings = DeploymentSettings()
    assert (settings.tenancy, settings.topology) == ("shared_rls", "saas")


def test_modes_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_TENANCY", "db_per_tenant")
    monkeypatch.setenv("DEPLOYMENT_TOPOLOGY", "on_prem")
    settings = DeploymentSettings()
    assert (settings.tenancy, settings.topology) == ("db_per_tenant", "on_prem")


def test_unknown_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_TENANCY", "schema_per_tenant")
    with pytest.raises(ValidationError):
        DeploymentSettings()
