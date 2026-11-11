---
id: ARCH-0007
title: "Entegrasyon: parçalar birbirine nasıl bağlanır"
status: draft
area: architecture
owner:
updated: 2026-11-10
depends_on: [ARCH-0005, ARCH-0006]
related: []
superseded_by:
code_paths: []
---

# ARCH-0007: Entegrasyon: parçalar birbirine nasıl bağlanır

## Soru
Yeni bir parça sisteme nasıl eklenir; backend, frontend ve testler aynı şeyi konuştuğundan nasıl emin oluruz?

## Karar 1: bağlantı yalnız giriş noktasında kurulur
- Ayar okunur, kapılar (`infra`) kurulur ve servise constructor'dan verilir. Bu iş yalnız üç yerde yapılır: `interface/http/deps/`, CLI çalıştırıcısı, worker girişi.
- Feature kapıyı kendisi kurmaz, global ayarı okumaz.
- Ücretli ya da dış servis çağıran her kapının (LLM, ödeme, mail ve benzeri) gerçek adaptörünün yanında aynı arayüzle sahte adaptörü olur: `infra/<kapı>/` içinde. Hangisinin kurulacağını giriş noktası `WorkerSettings().pick(live=..., fake=...)` ile seçer; `WORKER_MODE` (`fake` ya da `live`, varsayılan `fake`) yalnız `config/workers.py` içinde okunur.
- Testler ve test stack'i hep `fake` ile çalışır; üretim overlay'i `live` verir. `@pytest.mark.live` testleri gerçek servisi çağırır ve yalnız kullanıcı `make test-live` ile çalıştırır (`WORKER_MODE=live` kök `.env` dosyasında).

## Karar 2: katmanlar arası çağrı
- Feature → lib: saf fonksiyon çağrısı; gerekiyorsa kapı nesnesi parametre olarak verilir.
- Feature → infra: paket kökünden. Feature → feature: paket kökünden.
- API → worker: iş bir zarf olarak kuyruğa yazılır; yazma commit başarılıysa yapılır. Worker zarfı `XIn`'e çevirip aynı servisi çağırır.

## Karar 3: API sözleşmesi
- Tek kaynak koddur: servis şemaları ve route imzaları. `make openapi` bunlardan `docs/api/openapi.json` dosyasını üretir; dosya commit edilir.
- `make check` içindeki `openapi-check` dosyayı koddan üretilenle karşılaştırır; sözleşme sessizce değişemez.
- Frontend tipleri bu dosyadan üretilir, elle yazılmaz. Tester sözleşme testlerini bu dosyadan yazar.
- Sözleşme değişikliği (uç, alan adı, tip, statü) mimarın kararıdır.

## Karar 4: yeni bir uç eklemenin sırası
1. Mimar görev dosyasına modül planını (dosya, katman, gerekçe) ve uçların şemalarını yazar.
2. Backend yalnız `schema.py` ve route imzasını yazar, `make openapi` çalıştırır.
3. Aynı sözleşme üzerinde paralel: backend servisi, frontend ekranı, tester sözleşme ve kabul testlerini yazar.
4. Backend servisi kökten dışa açar, `deps`'e bağlar; CLI ya da worker aynı servisi çağırır.
5. `make check`; ardından tester bağımsız doğrular.

## Karar 5: HTTP ve gözlem standartları
glc'de olan ve aynen alınanlar:
- Yanıt: başarıda sarmalayıcı yoktur, route tipli şema döner. Hata gövdesi ARCH-0005'teki biçimdedir.
- Kimlik doğrulama, oran sınırı ve gövde boyutu sınırı `deps` ve `middleware` içindedir. Oran sınırı Redis'te tutulur; Redis yoksa istek reddedilir.
- CORS tam eşleşen kaynak listesiyle çalışır; middleware sırası `app.py` içinde yazılıdır.
- İz: `X-Request-Id` başlığı `trace_id` olur; log satırına, hata gövdesine ve kuyruk zarfına taşınır.
- Log JSON'dur ve alan adları izinli listeden gelir. Olay adı `<alan>.<olay>` biçimindedir.
- Metrik etiketinde kullanıcı, kiracı ve iz kimliği olmaz; yol etiketi route şablonudur.
- Dış servis kapısı: her çağrının zaman aşımı vardır; yeniden deneme sınırlıdır; yazan çağrı tekrar anahtarı (idempotency key) taşır.
- Gizli değer: ayar alanı çıktıda görünmez (`repr=False`); üretimde eksik ya da varsayılan gizli değerle süreç açılmaz; SQL parametreleri loglanmaz.

glc'de eksik olan ve burada kapatılanlar:
- API sözleşmesi dosyası ve denetimi (Karar 3): glc'de yok.
- Sürüm kuralı: sağlık uçları dışındaki bütün uçlar `/v1` altındadır. Sözleşmeyi bozan değişiklik yeni sürüm ön ekiyle gelir, eski sürüm kaldırılmadan önce duyurulur. glc'de `/v1` var, kural yok.
- Otomatik kapı: `make check` her push öncesinde çalışır (`make hooks`). glc'de test ve lint çalıştıran otomatik kapı yok.

Durum: şablonda yalnız `/health` ucu ve sözleşme üretimi var; bu standartların kodu ilk ilgili işle glc'den taşınır.

## Neden
- Bağlantının tek yerde kurulması, bir kapıyı değiştirmeyi (ör. sahte mail) tek dosyalık iş yapar.
- Sözleşme koddan üretilince backend, frontend ve test aynı dosyaya bakar; fark çalışma anında değil `make check`'te görülür. glc'de frontend tipleri elle tutuluyor ve uyumu hiçbir şey denetlemiyor.
- Sıranın sabit olması üç rolün birbirini beklemeden çalışmasını sağlar.

## Seçenekler
- Elle yazılan frontend tipleri: bağımlılık yok; uyumu hiçbir şey denetlemez.
- Önce elle yazılan OpenAPI: iki kaynak olur; Pydantic şemaları zaten tek kaynak olabiliyor.

## Nasıl denetlenir
`make openapi-check`; `tests/unit/test_architecture_placement.py` (ayarın dışarıdan gelmesi, kökten kullanım); `tests/unit/test_http_health.py` (sözleşme çıktısı deterministik); `tests/unit/test_architecture_deployment_reads.py` (worker modu tek yerde okunur), `tests/unit/test_worker_settings.py`.
