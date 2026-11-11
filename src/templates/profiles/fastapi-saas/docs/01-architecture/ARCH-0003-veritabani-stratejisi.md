---
id: ARCH-0003
title: "Veritabanı stratejisi"
status: draft
area: architecture
owner:
updated: 2026-11-10
depends_on: [ARCH-0002]
related: []
superseded_by:
code_paths: []
---

# ARCH-0003: Veritabanı stratejisi

## Soru
Kaç veritabanı var ve kiracıların verisi birbirinden nasıl ayrılıyor?

## Karar
İki bağımsız ayar ekseni vardır.
- `DEPLOYMENT_TENANCY`: `shared_rls` ya da `db_per_tenant`. Yalnız `infra/database/router.py` ve `config/deployment.py` (ayar tanımı) okur.
- `DEPLOYMENT_TOPOLOGY`: `saas`, `dedicated` ya da `on_prem`. Yalnız `interface/http/tenant.py` ve `config/deployment.py` okur.

Varsayılan `shared_rls`:
- Tek veritabanı, tek şema. Kiracıya ait her tabloda `tenant_id` sütunu ve satır düzeyi güvenlik (RLS) politikası bulunur.
- Kiracı kapsamı her işlemin başında `SET LOCAL` ile verilir; işlem bitince kendiliğinden kalkar.
- Uygulama veritabanına tablo sahibi olmayan bir rolle bağlanır; böylece RLS onu da bağlar. Göç ve yönetim işleri ayrı rolle yapılır.

İkinci mod `db_per_tenant`: kiracı başına ayrı veritabanı. Kendine ait kurulum isteyen müşteri içindir. İlk sürümde yalnız arayüzü (router) hazırdır, uygulaması sonra yazılır.

Kapsam dışı: `schema_per_tenant`, okuma kopyası ve birden çok veritabanına dağıtım. İhtiyaç doğarsa yeni kararla ve yine router üzerinden eklenir.

## Karar: roller ve ikinci savunma hattı
glc'de olan ve aynen alınanlar:
- Dört veritabanı rolü: `migrate` (tablo sahibi, yalnız göç), `app` (RLS'i aşamaz), `admin` (kiracılar arası okuma, sütun kısıtlı), `monitor` (izleme).
- Kiracı tablosunda RLS hem açılır hem zorlanır (`ENABLE` ve `FORCE`); politika göçte ortak yardımcıyla yazılır.
- Kiracısız tabloya erişim adlandırılmış izinle olur (ör. giriş sırasında kullanıcı arama); izin listesi tek yerdedir.
- İkinci hat: repo tabanı sorguyu ayrıca kiracıya göre süzer. RLS asıl korumadır, repo süzgeci hatayı erken gösterir.
- Kiracılar arası sorgu yapan repo metotları `admin_` ile başlar ve yalnız `admin` rolüyle çalışır.

glc'de eksik olan ve burada kapatılanlar:
- glc'de tek mod vardır; router ve mod bayrağı yoktur. Burada kiracı başına veritabanı ikinci mod olarak tanımlıdır.
- Uygulama oturumu ile admin oturumu aynı istekte yazarsa iki ayrı işlem olur ve birlikte geri alınamaz. Kural: bir istek yalnız bir oturumla yazar.
- glc adlandırılmış izni kimin sahibi olarak çalıştırdığını söylemez. `FORCE` tablo sahibini de bağladığı için `SECURITY DEFINER` fonksiyonun sahibi RLS'i aşabilmelidir. Kural: bu fonksiyonların sahibi giriş yapamayan (`NOLOGIN`) ve yalnız `BYPASSRLS` taşıyan ayrı bir `auth_definer` rolüdür; `app` rolüne yalnız `EXECUTE` verilir, `migrate` `BYPASSRLS` almaz. Fonksiyonlar `search_path` sabitler ve yalnız gereken sütunları döner.

## Neden
- Tek veritabanı ve RLS: tek göç, tek yedek, tek havuz. Ayrımı veritabanı zorlar; unutulan bir `WHERE` veri sızdırmaz.
- İkinci modun arayüzü baştan hazır olursa, özel kurulum isteyen ilk müşteri kodun geri kalanını değiştirmez.
- Modu yalnız birkaç dosyanın okuması, "hangi modda ne oluyor" sorusunun cevabını tek yerde tutar.

## Seçenekler
| Seçenek | Ne zaman uygun | Neden varsayılan değil |
|---|---|---|
| Tek veritabanı, RLS | çok sayıda küçük ve orta kiracı | varsayılan budur |
| Kiracı başına veritabanı | az sayıda büyük ya da yalıtım isteyen kiracı | her kiracı için ayrı göç, yedek ve bağlantı havuzu gerekir |
| Kiracı başına şema | hiçbir zaman | göç sayısı kiracıyla çarpılır, yalıtımı veritabanı kadar güçlü değildir |
| Uygulamada filtre (RLS yok) | hiçbir zaman | tek bir unutulan filtre veri sızdırır |

## Nasıl denetlenir
- `tests/unit/test_architecture_deployment_reads.py`: modu yalnız izinli dosyalar okur.
- `security-reviewer`: kiracı tablosunda politika yoksa `RLS-MISSING`.
