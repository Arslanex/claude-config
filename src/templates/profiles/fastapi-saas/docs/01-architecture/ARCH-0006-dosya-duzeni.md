---
id: ARCH-0006
title: "Dosya düzeni: ne nereye konur, ne zaman ayrılır"
status: draft
area: architecture
owner:
updated: 2026-11-10
depends_on: [ARCH-0005]
related: []
superseded_by:
code_paths: []
---

# ARCH-0006: Dosya düzeni: ne nereye konur, ne zaman ayrılır

## Soru
Yeni bir kod parçası hangi klasöre, hangi dosyaya girer ve bir dosya ne zaman ikiye ayrılır?

## Karar 1: feature düzeni
Her feature (ve alt feature) aynı dosyalarla gelir.

| Dosya | İçerik |
|---|---|
| `service.py` | Servis sınıfı |
| `schema.py` | `XIn` ve `XOut` şemaları |
| `errors.py` | Hata kodları (HTTP statüsü yok) |
| `helpers/<amaç>.py` | Servis dışındaki yardımcı kod |
| `__init__.py` | Dışa açılan arayüz: servis, şema, hata |

## Karar 2: yeni kod nereye konur
Sorular sırayla sorulur; ilk "evet" yeri belirler.
1. Ağ, disk ya da süreç sınırı geçiyor mu (veritabanı, Redis, mail, ödeme, model, depolama)? → `infra/<kapı>/`. Sınır geçmeyen kod `infra`'ya girmez.
2. Yalnız HTTP ile mi ilgili (başlık, çerez, CORS, CSRF, oran sınırı)? → `interface/http/middleware/` ya da `interface/http/security/`.
3. Yalnız bir feature grubu mu kullanıyor? → o grubun `helpers/` dizini (tek alt feature kullanıyorsa onun `helpers/`'ı).
4. Kütüphane niteliğinde mi (kapsamlı, parçalardan ve modüllerden oluşan, feature bilmeyen) ya da birden çok feature grubu mu kullanıyor? → `lib/<paket>/`.
5. Her katmanın kullandığı temel tip mi? → `core/`.

Örnek (güvenlik): parola özeti ve JWT'yi yalnız `identity` kullanıyorsa `features/identity/helpers/`; modüler bir kütüphaneyse ya da birden çok grup kullanıyorsa `lib/security/`; güvenlik başlıkları `interface/http/security/`; dış servise giden doğrulama `infra/`. `infra/security` olmaz.

- Feature kökü helper'ı dışa açmaz. Başka grubun ihtiyacı varsa kod `lib`'e taşınır.
- Torba ad yoktur: `utils`, `common`, `misc`, `shared`, `helper`. Dosya adı amacını söyler. Tekrar eden roller sabit adla yazılır: `views.py` (model → `Out`), `policy.py` (kural, izin), `access.py` (erişim kapısı).

## Karar 3: ne zaman ayrılır
Dosya satır sayısına göre bölünmez; içeriğe göre bölünür. Ayırma nedenleri:
1. Ayrı sorumluluk: parçalar farklı nedenlerle değişiyor.
2. Farklı tüketici: bir kısmını başka modül kullanıyor, kalanını kullanmıyor.
3. Farklı bağımlılık: bir kısmı saf, bir kısmı dış kapıya gidiyor.
4. Farklı aşama: bir akışın adımları (okuma, kural, çıktı).
5. Ayrı kullanım grubu: kendi `In`/`Out` şeması ve hata kodları olan iş yeni alt feature olur.

Yalnız uzun olduğu için, tek fonksiyon için ya da "ileride lazım olur" diye dosya açılmaz. Tek kullanıcılı, tek fonksiyonluk iş servisin özel fonksiyonudur. Kullanıcısı kalmayan helper silinir.

## Karar 4: lib paketi küçük bir kütüphanedir
```
lib/<paket>/
├── __init__.py     dış arayüz: giriş fonksiyonları ve tipler
├── schema.py       dış arayüzün girdi ve çıktı tipleri
├── errors.py       paketin hata kodları
├── <giriş>.py      tek düzenleyici modül (ör. pipeline.py), gerekiyorsa
└── <parça>/        iç modüller, parçaya ya da aşamaya göre alt paket
```
- Kökte bu dosyalar dışında modül durmaz; `lib/` kökünde gevşek modül olmaz.
- Paket saftır: `features`, `interface`, `worker`, `config` import etmez; ayar parametre olarak gelir. lib paketleri birbirini import etmez.

## Karar 5: interface yalnız çeviri yapar
```
interface/http/   app.py · deps/ · middleware/ · security/ · errors.py · routes/<feature>.py
interface/cli/    manage.py · output.py · commands/<feature>.py
```
- Route, komut ve worker işi girdiyi `XIn`'e çevirir, tek servis metodu çağırır, `XOut`'u döndürür ya da yazdırır. İş kuralı ve sorgu servistedir.
- `routes/` ve `commands/` feature ağacını yansıtır (istisna: `health`). Birden çok alt feature'a hizmet eden modül alt feature başına ayrılır.
- Route ve komut `infra`, `lib` ve SQLAlchemy import etmez; ortak olan `deps`'tedir.

## Karar 6: yazım
- Her `.py` dosyası docstring ile başlar: başlık, `Ne yapar:`, `Nasıl:`. Çok satırlı docstring'de metin `"""` satırının altında başlar.
- Yorumlar düz cümledir: devrik cümle olmaz; `__`, `--`, `---` ayırıcı ya da vurgu olarak kullanılmaz.
- Adlarda `__` asla kullanılmaz (değişken, ortam değişkeni, dosya, yer tutucu): en çok tek `_`. Tek istisna Python'ın kendi adlarıdır (`__init__`).

## Neden
glc'de ölçüldü: "servis dışı her şey `helpers/`" kuralı tek başına 66 helper dosyası üretti; lib paketlerinin beşi düz dosya yığını; bir CLI komut dosyası ölçüm mantığını kendi içinde taşıyor. Yer kurala bağlanınca ajan tahmin etmez, inceleme tartışmaya dönmez.

## Nasıl denetlenir
`tests/unit/test_architecture_placement.py` (yerleşim, lib yapısı, interface, adlar), `make lint` (ruff `D100`/`D104`), `arch-reviewer` (`MISPLACED`, `HELPER-SPRAWL`, `FLAT-LIB`, `FAT-INTERFACE`).
