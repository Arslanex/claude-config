---
paths:
  - "backend/src/**/*.py"
---
# Backend mimarisi (ARCH-0002, 0003, 0004, 0005, 0006)

Zorlayan: `make arch` (import-linter), `tests/unit/test_architecture_*.py`, `make lint` (ruff `D100`/`D104`). Kaynak: `docs/01-architecture/ARCH-*.md`.

- Katman yönü: `interface | worker` > `features` > `lib` > `infra` > `core | config`. Alttaki üsttekini import etmez.
- UoW; HTTP isteği, CLI komutu veya worker mesajı başına bir tane. Interface katmanı açar ve kapatır. Service asla commit etmez.
- Repo ORM modelini service'e döner, service Pydantic şema döner. Katmanlar arasında dict taşıma.
- Feature klasörü: `service.py` (sınıf), `schema.py`, `errors.py`, `helpers/`. Dışa açık servis metodu `XIn` alır, `XOut` döner; ayar ve kapılar constructor'dan gelir.
- Feature SQLAlchemy import etmez; `infra` ve `lib`'e paket kökünden girer; başka feature'ı yalnız kökünden kullanır.
- Stateless: modül seviyesinde değişebilir nesne ve `global` yok. Dağıtım modu yalnızca ARCH-0003'te sayılan dosyalarda okunur.
- Her `.py` dosyası docstring ile başlar: başlık, `Ne yapar:`, `Nasıl:`. Dışa açma yalnızca `__init__.py`'de.
- Çok satırlı docstring'de metin `"""` satırının altında başlar, yanında değil. Yorum ve docstring düz cümleyle yazılır: devrik cümle olmaz; `__`, `--`, `---` ayırıcı ya da vurgu olarak kullanılmaz. Adlarda `__` asla kullanılmaz (değişken, ortam değişkeni, dosya, yer tutucu): en çok tek `_`. Tek istisna Python'ın kendi adlarıdır (`__init__`).
- Migration: `backend/migrations/versions/` altında, `uv run alembic revision --autogenerate -m "<ad>"` ile üretilir; modeller `infra.database.models.Base`'den türer. Kontrol: `make migrate-check`.

## Yeni kod nereye (ilk "evet" belirler)
1. Ağ, disk ya da süreç sınırı geçiyor → `infra/<kapı>/`. Sınır geçmeyen kod `infra`'ya girmez; `infra/security` olmaz.
2. Yalnız HTTP ile ilgili → `interface/http/middleware/` ya da `interface/http/security/`.
3. Yalnız bir feature grubu kullanıyor → o grubun `helpers/<amaç>.py` dosyası (tek alt feature ise onun `helpers/`'ı).
4. Kütüphane niteliğinde (parçalardan oluşan, feature bilmeyen) ya da birden çok feature grubu kullanıyor → `lib/<paket>/`.
5. Her katmanın kullandığı temel tip → `core/`.

- Feature kökü helper'ı dışa açmaz. Torba ad yok: `utils`, `common`, `misc`, `shared`, `helper`.
- Tek kullanıcılı, tek fonksiyonluk iş için dosya açma: servisin özel fonksiyonu olsun.

## Ne zaman ayrılır
Satır sayısına göre değil, içeriğe göre: ayrı sorumluluk, farklı tüketici, saf/dış kapı ayrımı, farklı aşama, kendi `In`/`Out`'u olan ayrı kullanım grubu (→ yeni alt feature). Yalnız uzun diye bölme.

- Yeni dosya açmadan önce görev dosyasındaki modül planına bak; planda yoksa mimara sor.
- Yeni bir desen eklemeden önce `python3 tools/docs.py new adr "<baslik>"` ile `docs/02-decisions/` altında karar yaz.
