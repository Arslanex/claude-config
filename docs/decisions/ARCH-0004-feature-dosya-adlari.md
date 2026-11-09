# ARCH-0004: Feature dosya adları (`schema.py`, `errors.py`)

Durum: Kabul

ARCH-0001'in yalnızca "Karar" bölümündeki son maddesinin dosya adı kısmının yerine geçer:
"`schemas.py` (Pydantic), `exceptions.py`". Aynı maddenin geri kalanı ve ARCH-0001'in diğer tüm maddeleri geçerlidir.

## Bağlam
- ARCH-0001 feature dosyalarını `schemas.py` / `exceptions.py`, ARCH-0003 ise `schema.py` / `errors.py` olarak adlandırıyor; iki ADR çelişiyor.
- glc ve evalos `schema.py` + `errors.py` kullanıyor ve mimari testleri bunu zorluyor:
  glc `backend/tests/unit/architecture/test_layers.py:204,251-257,269-285`, evalos aynı dosya `:255,348-352,357-372`
  (`FEATURE_FILES` dışındaki adlar `helpers/` dışında kırılır; her `service.py` yanında `schema.py` + `errors.py` aranır).

## Karar
- Feature klasöründe dosya adları: `service.py`, `schema.py` (Pydantic), `errors.py`.
- Yalnızca yeniden adlandırmadır: `schemas.py` -> `schema.py`, `exceptions.py` -> `errors.py`; içerik ve anlam ARCH-0001'deki gibidir.

## Seçenekler
- `schemas.py` / `exceptions.py` (ARCH-0001): iki gerçek repo ve testleri tersini kullanıyor; seçmek her ikisinde yeniden adlandırma demek.
- Repo başına serbest bırakmak: varsayılan belirsiz kalır, ajanlar ve şablonlar tahmin eder.

## Sonuçlar
- ARCH-0001 ile ARCH-0003 arasındaki çelişki kalkar; ARCH-0003 ve ARCH-0004 birlikte kabul edilir, biri tek başına kabul edilmez.
- glc ve evalos'ta değişiklik gerekmez.
- Aynı değişiklikte şablondaki iki kopya yeni adlara taşınır (Architect değil, ilgili rol yapar):
  `src/templates/profiles/fastapi-saas/.claude/rules/backend-architecture.md:14` ve
  `src/templates/profiles/fastapi-saas/docs/01-architecture/ARCH-0001-backend-katmanlari.md:27`.
- Kabulde ARCH-0001'in en üstüne tek satırlık durum notu eklenir: "Kısmen ARCH-0004 ile değiştirildi".
  Bu notu Architect değil, kullanıcı/kabul adımı ekler.
- Şablonda mimari test yoktur; yeni projelerde adlar yalnızca kural metni ve inceleme ile korunur.
- Şablondaki ARCH-0001 kopyası yeni adlara çekilir; durum notu taşımaz.

## Doğrulama
- glc ve evalos: `test_layers.py` (Bağlam'daki satırlar) mevcut haliyle geçer.
- İncelemede: `grep -rn "schemas\.py\|exceptions\.py" src/ docs/decisions/` yalnızca ARCH-0001'i ve bu ADR'yi döndürmeli; `src/` altında eşleşme kalmamalı.

## Kullanıcı onayı gerekenler
- ARCH-0003 ve ARCH-0004'ün birlikte `Kabul` durumuna alınması.
- ARCH-0001'in ilgili maddesinin bu ADR ile geçersiz sayılması ve en üstüne durum notunun eklenmesi.
