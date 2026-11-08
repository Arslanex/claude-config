---
paths:
  - "backend/src/**/*.py"
---
# Backend mimarisi (ARCH-0001, ARCH-0002)

Zorlayan: `make arch` (import-linter) ve `tests/unit` mimari testleri. Kaynak: `docs/decisions/`.

- Katman yönü: `interface | worker` > `features` > `lib` > `infra` > `core | config`. Alttaki üsttekini import etmez.
- UoW; HTTP isteği, CLI komutu veya worker mesajı başına bir tane. Interface katmanı açar ve kapatır. Service asla commit etmez.
- Repo ORM modelini service'e döner, service Pydantic şema döner. Interface `infra.database.models` import etmez.
- Katmanlar arasında dict taşıma; şema ya da model kullan.
- Id üretimi `core` altında, tek standart.
- Feature klasörü: `service.py` (sınıf), `schemas.py`, `exceptions.py`, `helpers/`.
- Stateless: modül seviyesinde değişebilir nesne ve `global` yok.
- Dağıtım modu (`tenancy`, `topology`) yalnızca ARCH-0002'de sayılan dosyalarda okunur.
- Yeni bir desen eklemeden önce `docs/decisions/` altında karar yaz.
