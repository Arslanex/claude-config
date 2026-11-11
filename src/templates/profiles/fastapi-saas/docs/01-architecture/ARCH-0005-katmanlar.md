---
id: ARCH-0005
title: "Katmanlar ve bağımlılık yönü"
status: draft
area: architecture
owner:
updated: 2026-11-10
depends_on: [ARCH-0002, ARCH-0004]
related: []
superseded_by:
code_paths: []
---

# ARCH-0005: Katmanlar ve bağımlılık yönü

## Soru
Kod hangi katmanlara ayrılır ve hangi katman hangisini kullanabilir?

## Karar
```
interface | worker  >  features  >  lib  >  infra  >  core | config
```
Üstteki alttakini kullanır; alttaki üsttekini import etmez.

| Katman | Görevi |
|---|---|
| `interface` | Dış dünyayla konuşur: HTTP ve CLI. Girdiyi çevirir, servisi çağırır |
| `worker` | Kuyruktan iş alır, servisi çağırır |
| `features` | İş kuralları: her feature bir servis, şeması ve hata kodları |
| `lib` | Feature bilmeyen, saf iş kütüphaneleri |
| `infra` | Dış kapılar: veritabanı, Redis, mail, ödeme, model, dosya deposu, telemetri |
| `core` | Her katmanın kullandığı temel tipler: kimlik, hata, zaman, bağlam |
| `config` | Ayar tanımları |

- İş birimi iletişim katmanında açılır ve kapanır: HTTP isteği, CLI komutu ya da worker mesajı başına bir tane. Servis commit etmez.
- Servis sözleşmesi: dışa açık her metot girdisini `XIn` şemasıyla alır, `XOut` şeması (ya da `None`) döner. İstek bağlamı (`actor`, `client`) anahtar argümandır.
- Servis ayarı ve kapıları constructor'dan alır; global ayarı okumaz.
- Repo ORM modelini servise döner, servis şema döner. Katmanlar arasında sözlük (dict) taşınmaz.
- Paketler kökünden kullanılır: feature başka feature'ı, `infra` kapısını ve `lib` paketini yalnız paket kökünden import eder.
- Kimlik üretimi `core` altında tek standarttır.

## Karar: hata modeli ve şema tabanı
glc'de olan ve aynen alınanlar:
- Hata: `core` içinde `ErrorCode(code, kind, message)`. Feature yalnız kod ve tür bilir; HTTP statüsü yalnız `interface/http/errors.py` içinde eşlenir. Hata gövdesi `{code, message, details, trace_id}` biçimindedir.
- Şema tabanı: `XIn` bilinmeyen alanı reddeder ve değişmez; `XOut` ORM nesnesinden okunabilir.

glc'de eksik olan ve burada kapatılanlar:
- `infra` üst katmanı import edemez: glc'de yazılı ama denetlenmiyor; burada `make arch` zorlar.
- Worker ve interface repo'yu doğrudan kullanamaz, servisten geçer: glc'de worker bir repo'yu doğrudan import ediyor.
- `infra` global ayarı okumaz, ayar kapıya giriş noktasında verilir: glc'de motor global ayarı okuyor.
- Tip denetimi (`mypy`) ve kapsam eşiği zorunludur: glc'de ikisi de yok.

## Neden
- Tek yönlü bağımlılık, bir katmandaki değişikliğin nereyi etkileyeceğini önceden belli eder.
- `XIn` ve `XOut` aynı servisin API, CLI ve worker'dan aynı şekilde çağrılmasını sağlar ve API sözleşmesinin kaynağıdır (ARCH-0007).
- Ayarı dışarıdan alan servis test edilirken gerçek ortam gerekmez.
- Bu düzen sektörde katmanlı mimari ve "bağlantı noktaları ve adaptörler" adıyla bilinir; glc'de testle zorlanıyor.

## Seçenekler
- Katmansız, feature içinde her şey: küçük projede hızlı; sorgu, kural ve HTTP ayrışmaz, test zorlaşır.
- Servisin commit etmesi: basit görünür; iki servis aynı istekte çağrılınca yarım kayıt kalır.

## Nasıl denetlenir
- `make arch` (import-linter): katman yönü; `interface` ORM modelini import edemez.
- `tests/unit/test_architecture_placement.py`: servis sözleşmesi, feature ve `infra` ayarı okumaz, interface ve worker repo'ya gitmez, kökten kullanım.
- `arch-reviewer`: `SERVICE-COMMITS`, `ORM-LEAK`, `LAYER-VIOLATION`, `DEEP-IMPORT`.
