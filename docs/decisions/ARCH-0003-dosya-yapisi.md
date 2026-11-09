# ARCH-0003: Dosya yapısı varsayılanı

Durum: Kabul

## Karar
Yeni projeler için kısa varsayılan. Mevcut bir repoda onun yazılı kuralları önceliklidir. Katman yönü ARCH-0001'dedir.
- Feature'da `service.py`, `schema.py` ve `errors.py` birlikte durur; servis dışı her şey `helpers/` altındadır, dosya adı amacını söyler (`consents.py`).
- Boş iskelet dosya ve tek fonksiyonluk dosya açılmaz; `utils.py`, `common.py`, `misc.py` yoktur.
- `infra/database/models` ve `repos`: repoyu izle. glc'de aynı isimli çift, evalos'ta modeller alan, repo'lar tablo başına. Yeni projede alan başına aynı isimli çift.
- Dışa açma yalnızca `__init__.py`'dedir; içe aktarma paketten yapılır, dosya yolundan değil.
- Her `.py` dosyası kısa bir docstring ile başlar: başlık, `Ne yapar:`, `Nasıl:` (Türkçe). Mevcut repoda onun biçimi izlenir.
- ~600 satırı geçen dosya amaca göre bölmeyi düşündürür; sert kural değildir.

## Doğrulama
Başlık kuralı ruff `D100`/`D104` ile denetlenir. Geri kalanına incelemede bakılır.
