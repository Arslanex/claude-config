# ARCH-0001: Backend katman mimarisi

Durum: Kabul (stack varsayımı onay bekliyor: FastAPI + SQLAlchemy async)

## Karar
- Katmanlar, bağımlılık yönü yukarıdan aşağıya: `interfaces | workers` > `features` > `lib` > `infra` > `core` | `config`.
  Kural `import-linter` ile zorlanır (`make arch`), tavsiye olarak bırakılmaz.
- Unit of Work, iletişim protokolünün seviyesinde başlar: HTTP isteği, CLI komutu veya worker mesajı başına bir UoW.
  Servisler asla commit etmez.
- `infra/database/` altında modeller ve repolar birebir eşleşir. Engine ve session yöneticisi aynı yerde ayrı scriptlerdir.
- Repo ORM modelini service'e döner, service Pydantic şema döner. Interface katmanı `infra.database.models` import edemez.
- Katmanlar arası veri dict olarak taşınmaz; şema ya da model taşınır.
- Id üretimi ve standardı `core` altındadır, tüm modellerde aynıdır.
- Feature klasörü: `service.py` (OOP), `schemas.py` (Pydantic), `exceptions.py`; yardımcılar `helpers/` altında.

## Minimal ortak desenler (10)
1. `core/events.py` + outbox relay
2. `processed_message` ile idempotency
3. `core/errors.py`: AppError + RFC 9457 hata yanıtı
4. `core/authz.py`
5. `make openapi` + CI diff
6. Migration disiplini: `migrate-check`, up/down/up testi, expand/contract
7. `infra/http_client.py`: timeout/retry fabrikası
8. `core/context.py`: contextvar (tenant_id, actor_id, request_id)
9. `config/features.py`
10. Üç kuyruk metriği

## Doğrulama
`make arch` (import-linter), unit ve mimari testler, `make migrate-check`.

## Açık
- Kuyruk kütüphanesi (arq/RQ/Dramatiq) async kararına bağlı, henüz seçilmedi.
