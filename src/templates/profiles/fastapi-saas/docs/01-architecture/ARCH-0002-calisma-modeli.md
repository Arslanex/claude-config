---
id: ARCH-0002
title: "Çalışma modeli: durumsuz süreçler, bağımsız API ve worker"
status: draft
area: architecture
owner:
updated: 2026-11-10
depends_on: [ARCH-0001]
related: []
superseded_by:
code_paths: []
---

# ARCH-0002: Çalışma modeli: durumsuz süreçler, bağımsız API ve worker

## Soru
Sistem hangi süreçlerden oluşur ve yük arttığında nasıl büyür?

## Karar
- Üç süreç türü vardır: `api` (HTTP isteği karşılar), `worker` (kuyruktan iş alır), `migrate` (göçü uygular ve biter). Üçü aynı imajdan, farklı komutla başlar.
- Süreçler durumsuzdur: istekler arasında süreç belleğinde veri tutulmaz. Kalıcı durum yalnız PostgreSQL'de, geçici durum Redis'te, dosyalar dosya deposundadır.
- API ve worker birbirinden bağımsızdır: biri diğerini import etmez ve doğrudan çağırmaz. Aralarındaki tek bağ kuyruk ve veritabanıdır.
- Her süreç türü kendi başına yatayda çoğaltılır: API kopya sayısı istek yüküne, worker kopya sayısı kuyruk uzunluğuna göre ayarlanır. Yapışkan oturum yoktur; herhangi bir kopya herhangi bir isteği karşılar.
- İş birimi sınırı: HTTP isteği, CLI komutu ya da worker mesajı başına bir iş birimi (ARCH-0005). Dış yan etkiler (kuyruğa iş, e-posta) yalnız commit başarılıysa çıkar.
- Worker işleri tekrar güvenlidir: kuyruk bir mesajı en az bir kez teslim eder, aynı mesaj ikinci kez gelirse sonuç değişmez.
- Ayar yalnız ortam değişkeninden gelir; giriş noktasında okunur ve içeriye parametre olarak geçer.
- Kopya düzgün kapanır: kapanma sinyalinde yeni iş almaz, elindeki işi bitirir. `/health` ucu kopyanın ayakta olduğunu söyler.
- Göç bir kurulum adımıdır; süreç açılışında çalışmaz.

## Karar: sağlık, kapanış ve kuyruk davranışı
glc'de olan ve aynen alınanlar:
- İki sağlık ucu vardır. `/health` sürecin ayakta olduğunu söyler. `/ready` veritabanına ve Redis'e erişimi ve şema sürümünün koddan geride olmadığını denetler; kurulum `/ready` yeşil olmadan trafiği çevirmez.
- Kuyruğa yazılacak iş önce veritabanında bir satırdır (durum: `queued`). Kuyruğa yazma commit sonrasında yapılır; yazma başarısız olursa süpürücü bekleyen satırı yeniden kuyruğa koyar. Zarf yalnız kimlik taşır (`tenant_id`, kayıt kimliği, `trace_id`, deneme sayısı); veri veritabanından okunur.
- İşi alan worker düzenli sinyal verir; sinyali kesilen iş belirli süre sonra başka kopyaya geçer. Yeniden deneme gecikmelidir.
- Zamanlanmış işler cron ile değil, worker içindeki bakım döngüsüyle çalışır; her iş bir Redis kilidi alır, böylece kopya sayısı kaç olursa olsun iş bir kez çalışır.
- Eşzamanlılık iş türü başına sınırlıdır; dış servis sınırları (ör. model sağlayıcı) Redis üzerinden bütün kopyalar arasında paylaşılır.
- Worker takılırsa kendini sonlandırır (bekçi iş parçacığı) ve yeniden başlatılır.

glc'de eksik olan ve burada kapatılanlar:
- Deneme sınırı: her iş türünün en çok deneme sayısı vardır. Sınır aşılınca kayıt `failed` durumuna geçer ve mesaj kuyruktan çıkar. glc'de sınır yalnız bazı işlerde var; bozuk bir mesaj sonsuza kadar dönebiliyor.
- Worker kapanış süresi: Compose'da worker için `stop_grace_period`, en uzun işin süresinden uzun yazılır. glc'de yalnız API için tanımlı; uzun iş kapanışta yarıda kesiliyor.
- Worker sağlık denetimi Compose'da tanımlanır.

## Neden
- Durumsuz süreç ölünce veri kaybolmaz ve yerine yenisi hemen geçer; yatay ölçek ancak böyle mümkündür.
- API ve worker ayrı ölçeklenir, çünkü yükleri farklıdır: uzun süren bir iş API'yi yavaşlatmamalıdır.
- Commit sonrası yan etki, geri alınan bir işlemin dışarıya iz bırakmasını önler.
- Bu model sektörde "twelve-factor" adıyla yerleşmiştir; glc aynı modelle çalışıyor.

## Seçenekler
- Tek süreçte API ve arka plan işi: basit; uzun iş istekleri bekletir ve ayrı ölçeklenemez.
- Süreç belleğinde önbellek ya da oturum: hızlı; ikinci kopyada tutarsız olur.

## Nasıl denetlenir
- `tests/unit/test_architecture_stateless.py`: modül düzeyinde değişebilir durum ve `global` yok.
- `make arch`: `interface` ve `worker` birbirini import edemez.
- `deploy/compose.yaml`: `api` ve `worker` ayrı servislerdir.
