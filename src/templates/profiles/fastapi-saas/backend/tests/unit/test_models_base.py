"""ARCH-0004: tum modeller tek Base'den turer ve kisit adlari standarttir."""

from sqlalchemy import Column, Integer, Table

from PKG_NAME.infra.database.models import NAMING_CONVENTION, Base


def test_constraint_names_follow_the_convention():
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    table = Table("naming_probe", Base.metadata, Column("id", Integer, primary_key=True))
    try:
        assert table.primary_key.name == "pk_naming_probe"
    finally:
        Base.metadata.remove(table)
