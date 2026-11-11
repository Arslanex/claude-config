---
id: ARCH-0004
title: "Veri erişimi: SQLAlchemy, Alembic, bağlantı havuzu"
status: draft
area: architecture
owner:
updated: 2026-11-10
depends_on: [ARCH-0003]
related: []
superseded_by:
code_paths: []
---

# ARCH-0004: Veri erişimi: SQLAlchemy, Alembic, bağlantı havuzu

## Soru
Koda veritabanı nereden ve nasıl girer, şema nasıl değişir, bağlantılar nasıl yönetilir?

## Karar
Erişim:
- SQLAlchemy 2 async ve asyncpg kullanılır. Bütün modeller `infra/database/models` içindeki `Base` sınıfından türer; kısıt adları `Base`'in adlandırma standardından gelir.
- SQL yalnız repo'larda (`infra/database/repos`) yazılır. Feature ve interface SQLAlchemy import etmez.
- Repo ORM modelini servise döner; servis dışarıya Pydantic şema döner (ARCH-0005).

Göç (Alembic):
- Göç yalnız sona eklenir. Ana dala girmiş göç değiştirilmez, silinmez, yeniden adlandırılmaz; hata yeni göçle düzeltilir.
- Göç geriye uyumludur (önce genişlet, sonra daralt): ekleme önce yapılır; silme, yeniden adlandırma ve tip daraltma bir sonraki sürümde ayrı göçle yapılır. Böylece kurulum başarısız olursa önceki sürümün kodu yeni şemayla çalışır.
- Bağlantı adresi yalnız `DATABASE_URL` ortam değişkeninden okunur.

Bağlantı havuzu:
- Her süreç sınırlı bir havuz açar. Toplam bağlantı sayısı: kopya sayısı × (havuz boyutu + taşma).
- PgBouncer şimdi kurulmaz; kod baştan onun işlem moduyla uyumlu yazılır: oturum düzeyinde durum tutulmaz, kiracı kapsamı `SET LOCAL` ile işlem içinde verilir, kilitler işlem düzeyindedir, `LISTEN/NOTIFY` kullanılmaz.
- PgBouncer, toplam bağlantı sayısı veritabanının `max_connections` değerinin yaklaşık yüzde 70'ine yaklaştığında eklenir. Eklenirken hazırlanmış ifade ayarı PgBouncer ve asyncpg belgeleriyle doğrulanır.

## Karar: iş birimi, repo ve veri standartları
glc'de olan ve aynen alınanlar:
- İş birimi: oturum ilk kullanımda açılır. Başarıda commit; hata ya da 400 ve üzeri yanıtta geri alma. Commit sonrası işler `after_commit` ile kaydedilir. İstek başarısız olsa da kalması gereken kayıt (ör. denetim kaydı) ayrı iş birimiyle yazılır.
- Repo: tablo başına bir repo. Kilit `FOR UPDATE` ile alınır. Tekillik ihlali repo'da yakalanır ve alan hatasına çevrilir.
- Kimlik: uygulamada üretilen UUIDv7. Zaman: veritabanında `timestamptz` (UTC), API'de epoch milisaniye.
- Bağlantı: her bağlantıda `statement_timeout`; havuz bekleme süresi kısa; açılışta bağlantı bütçesi denetlenir (kopya × havuz, veritabanı sınırını aşamaz).
- Göç disiplini testle zorlanır: yayınlanmış göç listesi, genişlet ve daralt kuralının göç dosyasında denetimi, geri alma turu, model ile şema farkı.

glc'de eksik olan ve burada kapatılanlar:
- Sayfalama standardı: liste uçları imleç (keyset) ile sayfalar; `limit` üst sınırlıdır. glc'de yalnız offset var ve ortak kural yok.
- Yalıtım düzeyi açıkça yazılır: varsayılan `READ COMMITTED`; daha yükseğini isteyen iş bunu serviste belirtir.
- Silme: varsayılan gerçek silmedir. Yumuşak silme isteyen tablo `deleted_at` kullanır ve nedeni kararda yazar. glc'de tablo başına farklı adlar var.
- Eşzamanlı güncelleme: çakışma riski olan kayıt sürüm sütunu taşır; eski sürümle gelen yazma `VERSION_CONFLICT` döner.

Durum: şablonda `Base` ve Alembic ortamı var; iş birimi, repo tabanı ve göç disiplini testleri ilk tabloyla birlikte glc'den taşınır.

## Neden
- SQL'in tek yerde durması sorguyu bulunur, test edilir ve değiştirilebilir kılar.
- Genişlet ve daralt disiplini kesintisiz kurulumun ve güvenli geri dönüşün koşuludur.
- API ve worker yatayda çoğaldıkça (ARCH-0002) bağlantı sayısı da çarpılır; PgBouncer'a sonradan geçiş ancak kod baştan uyumluysa ucuzdur.

## Seçenekler
- PgBouncer'ı ilk günden kurmak: ölçek hazır gelir; yerelde ve testte bir servis daha çalışır.
- PgBouncer'ı hiç kullanmamak: en az parça; çok kopyada bağlantı sınırına takılır.
- Ham SQL ya da başka ORM: SQLAlchemy'nin göç ve tip desteğinden vazgeçmek demektir.

## Nasıl denetlenir
- `tests/unit/test_architecture_placement.py`: feature ve interface SQLAlchemy import etmez.
- `make migrate-check`: göçler test veritabanına uygulanır, model ile şema farkı aranır.
- `make verify-full`: veritabanlı tam tur.
