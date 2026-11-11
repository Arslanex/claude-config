"""
Kiraci tablosu icin RLS komutlari (ARCH-0003).

Ne yapar: bir tabloda satir duzeyi guvenligi acar ve zorlar, kiraci politikasini yazar.
Nasil: goc dosyasi `for statement in tenant_rls_statements("notes"): op.execute(statement)` ile kullanir. Politika
`app.tenant_id` ayarini okur; ayar yoksa hicbir satir gorunmez ve yazilamaz.
"""

import re

TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
POLICY = "tenant_isolation"
SCOPE = "nullif(current_setting('app.tenant_id', true), '')::uuid"


def tenant_rls_statements(table: str) -> list[str]:
    """Tabloyu `tenant_id` sutununa gore yalitan SQL komutlari."""
    if not TABLE_NAME.match(table):
        raise ValueError(f"gecersiz tablo adi: {table!r}")
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {POLICY} ON {table} USING (tenant_id = {SCOPE}) WITH CHECK (tenant_id = {SCOPE})",
    ]


def drop_tenant_rls_statements(table: str) -> list[str]:
    """`tenant_rls_statements` geri alimi (downgrade)."""
    if not TABLE_NAME.match(table):
        raise ValueError(f"gecersiz tablo adi: {table!r}")
    return [
        f"DROP POLICY IF EXISTS {POLICY} ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]
