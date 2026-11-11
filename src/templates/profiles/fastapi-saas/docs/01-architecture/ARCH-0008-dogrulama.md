---
id: ARCH-0008
title: "Doğrulama: hangi kuralı ne zorlar"
status: draft
area: architecture
owner:
updated: 2026-11-10
depends_on: [ARCH-0001, ARCH-0002, ARCH-0003, ARCH-0004, ARCH-0005, ARCH-0006, ARCH-0007]
related: []
superseded_by:
code_paths: []
---

# ARCH-0008: Doğrulama: hangi kuralı ne zorlar

## Soru
Bu kararların uygulandığını kim, hangi komutla denetler?

## Karar
Bir kural ancak bir komut ya da test onu zorluyorsa kuraldır. `make check` bunların hepsini çalıştırır; iş `make check` yeşil olmadan bitmiş sayılmaz.

| Kural | Karar | Zorlayan |
|---|---|---|
| Süreçler durumsuz | ARCH-0002 | `tests/unit/test_architecture_stateless.py` |
| API ve worker bağımsız, katman yönü | ARCH-0002, 0005 | `make arch` (import-linter) |
| Dağıtım modunu yalnız izinli dosyalar okur | ARCH-0003 | `tests/unit/test_architecture_deployment_reads.py` |
| Kiracı tablosunda RLS var | ARCH-0003 | `security-reviewer` (`RLS-MISSING`) |
| SQL yalnız repo'da | ARCH-0004 | `tests/unit/test_architecture_placement.py` |
| Göç ile model uyumlu | ARCH-0004 | `make migrate-check`, `make verify-full` (göçten sonra integration testleri) |
| Servis sözleşmesi, ayarın dışarıdan gelmesi, repo'ya yalnız servisten gidilmesi, kökten kullanım | ARCH-0005, 0007 | `tests/unit/test_architecture_placement.py` |
| Yerleşim, lib yapısı, interface, adlar | ARCH-0006 | `tests/unit/test_architecture_placement.py` |
| Docstring başlığı | ARCH-0006 | `make lint` (ruff `D100`, `D104`) |
| API sözleşmesi sessizce değişmez | ARCH-0007 | `make openapi-check` |
| Test grupları ve yerleri | | `tests/unit/test_tests_layout.py` |
| Unit dal kapsamı %100 | ARCH-0001 | `make test-unit` |
| Her `tenant_id` tablosunda RLS `ENABLE`, `FORCE` ve politika | ARCH-0003 | `tests/integration/test_rls_coverage.py` |
| RLS politikası kiracıyı ayırır, kiracısız yazma reddedilir, kapsam işlemle biter | ARCH-0003 | `tests/integration/test_tenant_isolation.py` |
| Servis commit etmez, iş birimi davranışı (commit, geri alma, commit sonrası iş) | ARCH-0004, 0005 | `tests/unit/test_unit_of_work.py`, `tests/integration/test_tenant_isolation.py` |
| `/ready` veritabanını ve şema sürümünü denetler | ARCH-0002 | `tests/unit/test_http_health.py`, `tests/integration/test_http_ready.py` |
| Hata modeli ve HTTP eşlemesi tek yerde, doğrulama hatası girdiyi tekrar etmez | ARCH-0005 | `tests/unit/test_http_errors.py` |
| İstek kimliği doğrulanır ve yanıta yazılır | ARCH-0007 | `tests/unit/test_http_errors.py` |

Henüz yalnız yazılı olanlar: aşağıdaki kuralların kodu şablonda yoktur, bu yüzden testi de yoktur. Kod yazılırken testiyle birlikte gelir ve satır yukarıdaki tabloya geçer. Taşınana kadar bunları yalnız `arch-reviewer`, `security-reviewer` ve kod incelemesi yakalar.

| Kural | Karar | Gelecek denetim (glc'deki karşılığı) |
|---|---|---|
| Dört rol ve izinleri (rolleri kuran göç henüz yok) | ARCH-0003 | integration testi: rol başına izin |
| Göç disiplini (yayınlanmış liste, genişlet ve daralt, geri alma turu) | ARCH-0004 | göç zinciri AST testi, geri alma integration testi |
| Kuyruk deneme sınırı, commit sonrası yazma, süpürücü | ARCH-0002 | kuyruk ve worker unit testleri |
| Log alan listesi | ARCH-0007 | log alanı testi |

Testin göremediğini `arch-reviewer` inceler: `SERVICE-COMMITS`, `ORM-LEAK`, `MISPLACED`, `HELPER-SPRAWL`, `FAT-INTERFACE`.

Koruma: doğrulama dosyalarını (mimari testler, `.importlinter`, `Makefile` hedefleri, `pyproject.toml` araç ayarı, kural dosyaları) değiştirmek isteyen her düzenlemede `edit-guard` kullanıcıya sorar. Bir kuralı gevşetmek için önce karar belgesi yazılır.

## Neden
Yazılı ama denetlenmeyen kural zamanla uygulanmaz; ajan da insan da en kısa yolu seçer. Denetim otomatik olunca inceleme kural tartışmasına değil işe odaklanır.

## Nasıl denetlenir
Bu tablodaki her satırın bir komutu ya da testi vardır; yeni kural eklenince tabloya satır eklenir.
