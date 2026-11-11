---
id: ARCH-0001
title: "Stack"
status: draft
area: architecture
owner:
updated: 2026-11-10
depends_on: []
related: []
superseded_by:
code_paths: []
---

# ARCH-0001: Stack

Karar sırası: 0001 stack, 0002 çalışma modeli, 0003 veritabanı stratejisi, 0004 veri erişimi, 0005 katmanlar, 0006 dosya düzeni, 0007 entegrasyon, 0008 doğrulama. Her belge bir öncekine dayanır.

## Soru
Bu sistemi hangi teknolojilerle yazıyoruz?

## Karar
| Alan | Seçim |
|---|---|
| Dil | Python 3.12 ve üzeri |
| API | FastAPI, Pydantic v2 |
| Veritabanı | PostgreSQL 16 |
| Veri erişimi | SQLAlchemy 2 (async), asyncpg, Alembic |
| Ayar | pydantic-settings; değerler yalnız ortam değişkeninden gelir |
| Önbellek ve kuyruk | Redis 7; kuyruk kendi Redis kuyruğumuzdur (glc'deki yapı), ek kuyruk kütüphanesi yok |
| Paket ve kilit | uv, `uv.lock` |
| Kalite | ruff, mypy, pytest (unit dal kapsamı %100), import-linter |
| Çalıştırma | Docker, Compose; API ve worker aynı imajdan çıkar |
| Arayüz | React, TypeScript, Vite (`frontend/` açıldığında) |

## Neden
- FastAPI ve Pydantic: şema hem doğrulama hem API sözleşmesidir (ARCH-0007); async çalışır.
- PostgreSQL: satır düzeyi güvenlik (RLS) kiracı ayrımını veritabanında zorlar (ARCH-0003).
- SQLAlchemy async ve Alembic: Python'da en yerleşik ikili; göç geçmişi kodla birlikte sürümlenir.
- Kendi Redis kuyruğumuz: glc'de çalışıyor, davranışı (zarf, yeniden deneme, süpürme) bizim elimizde ve yeni bağımlılık getirmiyor.
- uv: tek araçla kurulum ve kilit; sürümler `uv.lock` ile sabit.

## Seçenekler
- Django: kendi ORM'i ve proje düzeni katmanlı yapımızla (ARCH-0005) örtüşmez.
- arq ya da Celery: daha az kod yazdırır; yeni bağımlılık getirir ve glc'deki yapıdan ayrışır.
- MySQL: satır düzeyi güvenlik yok.

## Durum
Kuyruk iskeleti şablonda henüz yok; ilk worker işiyle birlikte glc'deki yapıdan taşınır.

## Nasıl denetlenir
`backend/pyproject.toml` ve `uv.lock`; yeni bağımlılık mimarın kararıdır; `dep-guard` yalnız şüpheli bir adda (popüler bir paketin bir harf farklısı) veya kayıt dışı bir kaynakta sorar.
