---
id: BRIEF-0001
title: "<Ürün adı>"
status: draft
area: general
updated: 2026-01-01
---

# <Ürün adı>

<!-- BRIEF.md proje kökünde durur. 1 ile 5 arası bölümler zorunludur; boş bırakılan isteğe bağlı bölüm "varsayılan kullanılsın" demektir. Kontrol: python3 ~/.claude/skills/design-project/plan_state.py brief-check BRIEF.md -->

## 1. Ürün özeti
- Problem: <1 ile 3 cümle>
- Hedef kullanıcılar: <kimler>
- İlk başarı ölçüsü: <ölçülebilir sonuç>

## 2. Kapsam dışı
- <ilk sürümde olmayacak bir şey>

## 3. Stack
- Zorunlu: <teknolojiler>
- Tercih edilen: <teknolojiler>
- Yasak: <teknolojiler>
- Profil: <biliniyorsa profil adı, örneğin fastapi-saas>

## 4. Dağıtım ve ölçek
<!-- Sayılar sayı ya da "bilmiyorum" olur; "bilmiyorum" ara soru 1'e girer. -->
- Dağıtım: <saas, on-prem veya hibrit>
- Bölge: <bölge>
- Kiracı sayısı: <sayı veya bilmiyorum>
- Kullanıcı sayısı: <sayı veya bilmiyorum>
- Eşzamanlı kullanıcı: <sayı veya bilmiyorum>
- Veri hacmi: <sayı ve birim veya bilmiyorum>
- 12 aylık büyüme: <yüzde veya bilmiyorum>
- Plan boyutu: tam <!-- küçük ya da tam. küçük, tek kullanıcılı ürüne veya küçük bir iç araca uyar: performans ve kalite adımları atlanır, en çok 14 rol çağrısı yapılır. -->

## 5. Özellikler

### F-01 <Özellik adı>
- Amaç: <kim neyi neden yapar>
- Kim: <roller>
- Öncelik: P1
- Davranışlar:
  - <serbest yazılmış davranış>
- Kurallar: <kural>
- Notlar: <not>

<!-- Örnek:
### F-03 Fırsat panosu
- Amaç: satış ekibi açık fırsatları aşamaya göre görür.
- Kim: satış temsilcisi, satış yöneticisi.
- Öncelik: P1
- Davranışlar:
  - Kart sürüklenince aşama değişir ve geçmişe yazılır.
  - Kapalı fırsat panoda görünmez.
- Kurallar: başka şirketin fırsatı hiçbir yoldan görünmez.
- Notlar: mobilde liste görünümü yeterli.
-->

## 6. Kalite beklentileri
<!-- İsteğe bağlı: gecikme, erişilebilirlik, çalışma süresi, yedekleme, uyumluluk. -->

## 7. Entegrasyonlar
<!-- İsteğe bağlı: dış sistemler, yön, protokol. -->

## 8. Kısıtlar
<!-- İsteğe bağlı: bütçe, süre, ekip, aylık altyapı tavanı, planlama bütçesi. -->

## 9. Özel notlar
<!-- İsteğe bağlı: serbest metin. -->
