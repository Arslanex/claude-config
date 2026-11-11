---
paths:
  - "backend/src/**/interface/**/*.py"
  - "backend/src/**/worker/**/*.py"
---
# Interface ve worker (ARCH-0006, ARCH-0007)

- Route, komut ve worker işi yalnız çeviri yapar: girdiyi `XIn`'e çevir, tek servis metodu çağır, `XOut`'u döndür ya da yazdır. İş kuralı, sorgu ve veri işleme servistedir.
- `routes/` ve `cli/commands/` feature ağacını yansıtır: `routes/<feature>.py` ya da `routes/<feature>/<alt_feature>.py` (istisna: `health`). Birden çok alt feature'a hizmet eden modül alt feature başına ayrılır.
- Route ve komut modülü `infra`, `lib`, SQLAlchemy ve başka route/komut modülü import etmez; feature'ı paket kökünden alır; ortak olan `deps`'tedir.
- HTTP statüsü yalnız `interface/http/errors.py`'de; yalnız HTTP'ye ait güvenlik `interface/http/security/` ya da `middleware/` altında.
- CLI çıktı biçimi `cli/output.py`'de. Aynı işi API ve CLI aynı servis metoduyla yapar.
- Route imzası ya da şema değişince `make openapi` çalıştır; `docs/api/openapi.json` sözleşmedir ve onu değiştirmek mimarın kararıdır.
