# ARCH-0002: Dağıtım modları

Durum: Kabul

## Karar
İki bağımsız yapılandırma ekseni:
- `DEPLOYMENT__TENANCY`: `shared_rls` | `db_per_tenant`. Yalnızca `infra/database/router.py` okur.
- `DEPLOYMENT__TOPOLOGY`: `saas` | `dedicated` | `on_prem`. Yalnızca `interface/http/tenant.py` ve `config/deployment.py` okur.
- Stateless her yerde kuraldır. Süreç içi durum tutulmaz; bir unit/mimari testle zorlanır.
- `schema_per_tenant` kapsam dışıdır.
- İlk sürüm yalnızca `saas` + `shared_rls` uygular. Diğer modlar arayüz seviyesinde hazır, uygulama sonra.

## Doğrulama
Modu okuyan dosyaların listesi bir mimari testle sabitlenir; başka yerde okuma testi kırar.
