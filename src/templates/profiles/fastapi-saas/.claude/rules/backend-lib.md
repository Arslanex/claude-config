---
paths:
  - "backend/src/**/lib/**/*.py"
---
# lib paketleri (ARCH-0006)

- `lib/<paket>/` küçük bir kütüphanedir: kökte `__init__.py` (dış arayüz), `schema.py`, `errors.py` ve en çok bir giriş modülü (ör. `pipeline.py`); geri kalan her şey parça/aşama alt paketlerinde (`extract/`, `rules/`, `report/`).
- `lib/` kökünde gevşek modül olmaz. `__init__` yalnız dış arayüzü açar; iç modüle dışarıdan uzanılmaz.
- Saf: `features`, `interface`, `worker`, `config` import etmez. Ayar ve anahtar parametre olarak gelir; dış kapıya çağıranın verdiği `infra` nesnesiyle çıkılır.
- lib paketleri birbirini import etmez (nötr paket eklemek ADR ister).
- Paket yalnız kütüphane niteliğindeki ya da birden çok feature grubunun kullandığı kod için açılır; tek grubun kodu o grubun `helpers/`'ındadır.
