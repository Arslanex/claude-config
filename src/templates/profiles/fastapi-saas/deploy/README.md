# deploy/

Katmanli compose: `compose.yaml` (taban) + bir overlay.

| Ortam | Komut |
|---|---|
| development | `docker compose -f deploy/compose.yaml -f deploy/compose.development.yaml up` |
| test stack | `make stack-test-up` / `make stack-test-down` (postgres 55463, redis 56410) |
| production | `API_IMAGE=<imaj> docker compose -f deploy/compose.yaml -f deploy/compose.production.yaml up -d` |

Dogrulanacaklar: api/worker komut yollari (varsayim), `backend/Dockerfile` icindeki `uv` imaj surumunu sabitle.
Uretim dagitim is akisi (CI/CD, sunucu erisimi, secret) bu profilde YOK; insan onayiyla ayri eklenir.
`.env.production` repoya girmez ve ajan tarafindan okunmaz.
