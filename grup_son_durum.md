# MadenGuard AI - Grup Son Durum ve Sonraki Adımlar

Bu dosya, projede bugune kadar ne yapildigini, su an hangi noktada oldugumuzu ve bundan sonra kimin neyi guncellemesi gerektigini tek yerde toplar.

## 1) Genel Durum

Su anda proje artik sadece parca parca ureten bir halden cikti. Ana veri akisi ve backend omurgasi birlestirildi.

Temel mantik artik su:
- Haki LiDAR / segment / pointcloud kaynagidir
- Recep gaz / metan risk kaynagidir
- Huseyin worker / UWB / konum kaynagidir
- Enes backend'de bunlari birlestirir
- Selim frontend'de sadece backend sonucunu gosterir

Ortak join anahtari:
- `segment_id`

Ortak zaman mantigi:
- `time_step`

---

## 2) Branch / Birlesme Durumu

Calisma branch'i:
- `integration/mvp-full-stack`

Bu branch uzerinde:
- branch birlestirme akisleri duzeltildi
- backend endpointleri guncellendi
- simulation / scenario / trapped / route / risk katmanlari bir araya getirildi
- testler calistirildi
- git push yapildi

Yani artik ekip ayni backend omurgasini kullaniyor.

---

## 3) Backend'de Yapilan Ana Guncellemeler

### 3.1 Pointcloud servis edildi

Artik backend PLY dosyalarini dogrudan verebiliyor.

Endpoint:
- `GET /api/digital-twin/pointcloud`

Backend su URL'leri donduruyor:
- `preview_url`
- `downsampled_url`

Bu sayede frontend modeli kendi icinde uretmiyor.

### 3.2 Simulation state eklendi

Endpoint:
- `GET /api/simulation/state?time_step=...`

Bu endpoint:
- segmentleri
- graph'i
- worker'lari
- gas sensor'lari
- environment risk'i
- segment risk'lerini
- trapped durumunu

tek response icinde topluyor.

### 3.3 Scenario motor eklendi

Endpoint:
- `GET /api/simulation/scenario?scenario_id=...&time_step=...`

Senaryo tipleri:
- `normal`
- `methane_spike`
- `collapse_s004`
- `worker_at_risk`
- `show_route`

Bu kisim artik frontend mock mantigina bagimli degil.

### 3.4 Trapped analizi eklendi

Endpoint:
- `GET /api/simulation/trapped?time_step=...`

Bu endpoint hangi worker'in mahsur kaldigini ve neden mahsur kaldigini donduruyor.

### 3.5 Risk motoru gelistirildi

Endpoint:
- `GET /api/risk/segments?time_step=...`

Artik risk skoru sadece tek sayi degil. Icindeki parcali mantik da gorunuyor:
- geometry
- environmental
- worker
- tracking

Risk breakdown eklendi, yani skorun neden o kadar ciktigi gorulebiliyor.

### 3.6 Emergency route daha akilli hale getirildi

Endpoint:
- `GET /api/routes/emergency?worker_id=...&time_step=...&scenario=...`

Artik rota:
- worker bazli
- scenario bazli
- blocked segment bazli
- risk agirlikli

calisiyor.

### 3.7 Integration status eklendi

Endpoint:
- `GET /api/integration/status?time_step=...&scenario_id=...`

Bu endpoint bir kontrol noktasi gibi calisiyor:
- ortak kontrat bozuldu mu
- segment_id uyumlu mu
- worker/gas/time_step birbiriyle uyumlu mu
- scenario state tutarli mi

---

## 4) Backend'de Davranis Degisiklikleri

### 4.1 Worker'lar artik sabit degil

Worker bilgisi:
- latest snapshot olarak da cekilebiliyor
- historical time_step olarak da cekilebiliyor

Bu sayede simülasyon ekraninda worker'lar sabitmis gibi durmuyor.

### 4.2 Gaz verisi worker ve segment ile baglandi

Gaz sensoru datasi artk segment bazli risk hesaplamaya giriyor.

### 4.3 Rota, worker ve risk ile birlikte hesaplandi

Kacis rotasi sadece en kisa yol mantigi degil.

Riskten etkilenen seyler:
- geometrik risk
- environmental risk
- worker occupancy
- tracking risk

### 4.4 Senaryo ve trapped backend tarafinda sahiplenildi

Frontend artik kendi kafasina gore senaryo kurmuyor.

---

## 5) Test ve Dogrulama Durumu

Backend testleri calisti.
Temel endpointler kontrol edildi.
Yeni integration contract endpointi de eklendi.

Yani mevcut durum:
- calisiyor
- testten geciyor
- pushlandi

---

## 6) Selim Tarafinda Beklenen Degisiklikler

Selim'in frontend tarafinda yapmasi gereken ana sey:
- mock veri yerine backend API'yi ana kaynak yapmak
- worker'i sabit varsaymamak
- scenario ekranini backend `simulation/scenario` ile beslemek
- acil rota panelini worker_id + time_step + scenario ile cekmek
- risk panelini `risk_breakdown` ile gostermek
- trapped durumunu backend'den okumak
- pointcloud'u backend URL'inden yuklemek

Selim icin kritik endpointler:
- `GET /api/simulation/state`
- `GET /api/simulation/scenario`
- `GET /api/simulation/trapped`
- `GET /api/integration/status`
- `GET /api/routes/emergency`
- `GET /api/risk/segments`
- `GET /api/digital-twin/pointcloud`

Selim'in en onemli duzeltme noktasi:
- simülasyon sanki sadece `WORKER_01` icin calisiyormus gibi gorunmemeli
- acil rota tek madenciye sabit kalmamalı
- UI, secili worker'a gore backend'den tekrar veri cekmeli

---

## 7) Haki Tarafinda Durum

Haki tarafinda temel is:
- LiDAR / segment source of truth
- pointcloud uretimi
- segment graph / metadata

Haki'nin verisi backend icin ana kaynak.

Haki tarafinda yeni beklenti varsa:
- segment haritasi, graph ve pointcloud standardi bozulmamalı
- `segment_id` canonical kalmali
- yeni output varsa backend endpointlerine uygun formatta gelmeli

---

## 8) Recep Tarafinda Durum

Recep tarafinda temel is:
- methane / gaz risk processing
- environmental risk ciktilari
- gas sensor timeline

Recep'in verisi risk motoruna giriyor.

Recep tarafinda önemli kural:
- gaz verisi tek basina goruntulenmek icin degil
- segment riskine girdi saglamak icin kullaniliyor

---

## 9) Huseyin Tarafinda Durum

Huseyin tarafinda temel is:
- UWB worker tracking
- worker position
- worker_segment_timeline
- worker exposure

Huseyin tarafindaki veri:
- worker'in hangi segmentte oldugu
- takip guvenilirligi
- tracking risk

Bu veri backend rota ve risk motoruna baglaniyor.

---

## 10) Enes Tarafinda Durum

Enes'in backend sorumlulugu su an:
- fusion
- routing
- scenario logic
- trapped logic
- integration status
- API contract
- frontend'e gidecek tek dogru backend akisi

Yani backend omurgasi artik yerinde.

---

## 11) Sonraki Yapilacaklar

### Backend tarafinda

Artik ana isler kapandi. Kalanlar daha cok iyilestirme:
- rota maliyeti ince ayari
- risk motoru kalibrasyonu
- yeni senaryolar
- daha fazla test fixture
- dokumantasyon / handoff notlari

### Frontend tarafinda

Selim'in guncellemesi gereken kisimlar var.
Bu kisimlar backend'e uyumlu hale getirilmeli.

### Takim icin

Ekip artik ayni API sozu ile calismali.

---

## 12) AI / ML Tarafi - Simdiki Durum ve Oneriler

Simdiye kadar proje MVP seviyesinde kurallara dayali ve veri birlestirmeli ilerledi.

AI/ML icin su an yapilmis temel bir model yok.

Ama ileride eklenebilecek alanlar:
- risk skorlama icin ML modeli
- worker davranis anomali tespiti
- gaz anomalisi siniflandirma
- rota onceliklendirme icin learning-based scoring
- scenario tahmini / erken uyarı

Simdilik dogru olan sey:
- önce pipeline calissin
- sonra ML eklenirse hangi veri uzerine eklenecegi belli olsun

Yani ML su an "goruntu olsun diye" degil, ileride saglam veri uzerine eklenmeli.

---

## 13) Kisa Ozet

Bugun yapilanlarin ozeti:
- branch'ler toparlandi
- backend omurgasi kuruldu
- simulation / scenario / trapped / route / risk birlestirildi
- integration status eklendi
- pointcloud backend'den servis edildi
- backend testleri gecildi
- frontend icin ne degisecegi netlestirildi

Bugunun sonunda durum:
- backend tarafi hazir
- frontend tarafinda revizyon gerekiyor
- ekip artik ayni ortak backend sozuyle devam edebilir

Kisa not:
- `integration/mvp-full-stack` branch'i en temiz haliyle birlestirildi.
- Backend gelistirmeleri tamamlandi.
- Raporda yazan tum son durum bu branch uzerinden ilerliyor.
- Bundan sonra herkes bu en guncel hal uzerinden devam etsin.
