---
paths:
  - "backend/tests/**/*.py"
---
# Backend testleri

- Dört grup: `unit`, `integration`, `e2e`, `smoke`. Marker dizinden otomatik gelir, elle yazma.
- `unit`: ağ ve DB yok (conftest engeller). Dal kapsamı %100. Komut: `make test-unit`.
- `integration`: test stack'ine bağlanır (`TEST_DATABASE_URL`, `TEST_REDIS_URL`). Komut: `make test-integration`.
- `e2e`: uçtan uca akış. `smoke`: hızlı sağlık kontrolü.
- Dış servis (LLM, ödeme, mail) testlerde hep sahte adaptörle çalışır: conftest her teste `WORKER_MODE=fake` verir. Gerçek servisi çağıran test `@pytest.mark.live` taşır (elle yazılan tek marker); `WORKER_MODE=live` yoksa atlanır. Bunları yalnız kullanıcı `make test-live` ile çalıştırır; ajan çalıştırmaz.
- Ortak yardımcılar `tests/support/` altında. `tests/` altında yalnızca bu gruplar ve `support/` olur.
- Test dosyası adı `test_` ile başlar ve bir grubun içinde durur.
- İşi bitirmeden önce `make check`.
