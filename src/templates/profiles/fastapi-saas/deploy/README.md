# deploy/

Katmanli compose: `compose.yaml` (taban) + bir overlay.

| Ortam | Komut |
|---|---|
| yerel calisma (varsayilan) | `deploy/start.sh`, `deploy/stop.sh`, `deploy/restart.sh`: postgres ve redis konteynerde, api, worker ve web host'ta; log `.cache/local/` |
| development (Docker) | `docker compose -f deploy/compose.yaml -f deploy/compose.development.yaml up`; kullanici Docker'a gecis deyince ekip api ve web'i buna tasir |
| test stack | `make stack-test-up` / `make stack-test-down` (postgres 55463, redis 56410) |
| arayuz e2e | `make test-ui` (Playwright konteynerde, api sahte worker'larla; profil `e2e`) |
| gercek servis testleri | `make test-live` (yalniz kullanici; kok `.env` icinde `WORKER_MODE=live`) |
| production | `API_IMAGE=<imaj> docker compose -f deploy/compose.yaml -f deploy/compose.production.yaml up -d` |

Ortam sozlesmesi: `deploy/env.example` (kullanici kok `.env` dosyasini ondan kopyalar). Migration: `make migrate` (`DATABASE_URL` ortamdan okunur); imaj `alembic.ini` ve `migrations/` icerir. Veritabanli tam tur: `make verify-full`.

Dogrulanacaklar: worker komut yolu (varsayim; api yolu `interface/http/app.py` ile dogrulandi). `backend/Dockerfile` icindeki `uv` imaj surumu sabittir (0.13.7); yukseltirken elle degistir.
Uretim dagitim is akisi (CI/CD, sunucu erisimi, secret) bu profilde YOK; insan onayiyla ayri eklenir.
`.env.production` repoya girmez ve ajan tarafindan okunmaz.
