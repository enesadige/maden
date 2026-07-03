# MadenGuard AI — UWB Worker Tracking Pipeline Raporu

## 1. Amaç ve Kapsam

Bu çalışma, MadenGuard AI için UWB worker tracking katmanını uygulamak amacıyla geliştirilmiştir. Amaç; UWB/worker hareket verisini okumak, işçi pozisyonlarını Haki maden segmentleriyle eşleştirmek, anchor-tag mesafelerini hesaplamak, takip güvenilirliğini tahmin etmek ve worker exposure çıktıları üretmektir.

Bu modül MVP/demo niteliğinde bir pipeline’dır. Sertifikalı gerçek maden güvenliği lokalizasyon sistemi değildir; gerçek UWB konum doğruluğu veya iş güvenliği uyumluluğu iddiası taşımaz. Üretilen veriler backend tarafındaki mevcut worker API’si ve ileride yapılacak risk füzyonu için hazırlanmış teknik ara çıktılardır.

UWB tarafı, işçilerin hangi segmentte bulunduğunu ve takip güvenilirliğini üretir. Nihai risk füzyonu ve acil rota kararları backend risk/routing modüllerinin sorumluluğundadır.

## 2. Kullanılan Veri Kaynakları

### 2.1 Haki LiDAR / Segment Verileri

UWB pipeline, maden haritası için Haki tarafından üretilmiş segment verilerini kaynak kabul eder. Okunan dosyalar şunlardır:

```text
backend/data_processed/sample/haki_lidar/segments/map_segments.json
backend/data_processed/sample/haki_lidar/segments/segment_metadata.json
backend/data_processed/sample/haki_lidar/graph/mine_graph.json
backend/data_processed/sample/haki_lidar/risk/geometry_risk.json
```

Haki segment haritası source of truth olarak kullanılmıştır. UWB pipeline bağımsız bir maden haritası üretmez ve Haki verilerini değiştirmez. Segment ID değerleri `S001`, `S002`, ... formatına normalize edilmiştir. Segment graph yapısı ve segment bounds verileri; segment eşleştirme, anchor yerleşimi ve graph visibility tahmini için kullanılmıştır.

Bilinen Haki veri sayıları:

| Metric | Value |
|---|---:|
| Segment count | 143 |
| Graph edge count | 219 |
| Geometry risk records | 143 |
| Exit segment count | 5 |

### 2.2 UTIL UWB Dataset

Raw UTIL UWB dataset yerel harici path üzerinden kullanılmıştır. Raw dataset repository içine kopyalanmamıştır. CSV discovery aşamasında 52 CSV dosyası bulunmuş, config ile tanımlı 3 worker trial eşleştirilmiştir.

Veri okuma aşamasında 75,819 geçerli pose sample ve 148,668 geçerli TDoA sample parse edilmiştir. Bazı pose/TDoA satırlarının reddedilmesi beklenen bir durumdur; UTIL CSV dosyalarında asenkron satırlar, boş alanlar veya malformed field değerleri bulunabilmektedir.

Önemli sınırlama:

```text
UTIL pose_x, pose_y ve pose_z değerleri gerçek UWB ile hesaplanmış işçi konumu değildir. Bu MVP’de motion-capture ground-truth proxy pozisyonları olarak kullanılmıştır.
```

### 2.3 Config Verisi

Pipeline config dosyası:

```text
backend/uwb_processing/uwb_config.example.json
```

Worker sayısı config-driven yapıdadır. Mevcut demo 3 worker ile çalışır, ancak kod dinamik worker count destekleyecek şekilde geliştirilmiştir. Worker ID ve tag ID değerleri normalize edilir. Her worker için `source_trial_hint`, ilgili trial eşleştirmesinde kullanılır. Trial reuse davranışı config içindeki `allow_trial_reuse` ayarıyla kontrol edilir.

## 3. Geliştirilen UWB Pipeline Yapısı

Pipeline kodları şu dizin altında geliştirilmiştir:

```text
backend/uwb_processing/
```

Üretilen çıktılar şu dizin altında toplanır:

```text
backend/data_processed/sample/
```

Genel akış:

```text
UTIL CSV verisi
→ dataset_reader.py
→ position_extractor.py
→ coordinate_mapper.py
→ segment_mapper.py
→ timeline_builder.py
→ anchor_planner.py
→ cable_planner.py
→ distance_matrix.py
→ timeline_enricher.py
→ exposure_builder.py
→ validate_outputs.py
→ run_pipeline.py
→ backend/data_processed/sample çıktıları
```

Bu yapı, raw hareket verisinden backend’in okuyabileceği worker snapshot ve risk ara çıktısına kadar olan süreci modüler şekilde ayırır.

## 4. Modül Modül Yapılan İşler

### core.py

Ortak dataclass yapıları ve utility fonksiyonları içerir. Point, bounds, segment, anchor, cable, distance observation ve worker timeline record gibi temel modeller burada tanımlanır. ID normalization, 2D/3D distance, reliability, tracking risk ve JSON dönüştürme yardımcıları bu modüldedir.

### config_loader.py

Config dosyasını yükler ve doğrular. Haki path’lerinin korunmasını sağlar, output root değerinin güvenli dizine işaret ettiğini kontrol eder ve pipeline parametrelerinin beklenen tip/range içinde olduğunu doğrular.

### segment_loader.py

Haki segment, metadata, graph ve geometry risk dosyalarını okur. Bunları `SegmentDataset` altında birleştirir. Segment lookup, graph neighbor, edge weight, exit segment ve risk bilgilerine pipeline genelinde standart erişim sağlar.

### anchor_planner.py

Dinamik UWB anchor pozisyonları üretir. Haki segment bounds ve graph geometrisini kullanır. Junction, dead-end, exit, risk density, curve/turn ve long-edge durumlarına göre anchor sayısını artırabilir. Sonuç olarak 283 anchor üretilmiştir.

### cable_planner.py

Anchor’lar arasında cable topology üretir. Haki graph adjacency ve wall-adjacent approximation yaklaşımı kullanılır. Sonuç olarak 642 cable link oluşturulmuştur. Bu çıktı emergency routing değildir ve exact mesh wall routing iddiası taşımaz.

### dataset_reader.py

UTIL CSV dosyalarını discover eder, config ile tanımlı trial hint değerlerine göre dosyaları eşleştirir, pose ve TDoA sample’ları bağımsız olarak parse eder. Dosya yazmaz; yalnızca in-memory dataset okuma sonucunu üretir.

### position_extractor.py

Raw pose sample değerlerini worker `RawPose` kayıtlarına dönüştürür. Worker hareketi 1 Hz zaman grid’ine resample edilir. Dinamik worker config kullanır. Sonuç olarak 379 `RawPose` kaydı üretilmiştir.

### coordinate_mapper.py

UTIL coordinate frame değerlerini Haki coordinate frame’e dönüştürür. `bounds_fit` transform kullanılır. Bu transform yaklaşık bir MVP dönüşümüdür; kalibre edilmiş UWB-to-mine registration değildir.

### segment_mapper.py

Transform edilmiş worker pozisyonlarını Haki segment ID değerleriyle eşleştirir. Kullanılan yöntemler `bounds_contains`, `nearest_center`, `continuity_fallback` ve `start_segment_seed` olarak ayrılır. Sonuç olarak 379 known mapped position üretilmiştir. Fallback record sayısı 133, mean mapping confidence değeri 0.2541’dir.

### timeline_builder.py

Base worker timeline üretir. Mapping confidence ve mapping method bilgisini korur. Sonuç olarak 379 timeline record ve 3 latest worker snapshot oluşturulmuştur.

### distance_matrix.py

Her worker-time ve anchor kombinasyonu için anchor-tag distance hesaplar. Sonuç olarak 107,257 distance observation üretilmiştir. Ayrıca visible anchor count, visible anchor list ve signal quality estimate hesaplanır.

### timeline_enricher.py

Base timeline kayıtlarına tracking status, visible anchor count ve position reliability ekler. Tracking dağılımı:

| Tracking status | Count |
|---|---:|
| full_tracking | 155 |
| degraded_tracking | 28 |
| weak_tracking | 11 |
| no_tracking | 185 |

### exposure_builder.py

Worker exposure risk çıktısını üretir. Kritik kural şudur:

- Worker bir segmente map edilmişse `worker_exposure_risk = 100.0`.
- Düşük lokalizasyon güvenilirliği exposure değerini azaltmaz.
- Düşük güvenilirlik ayrı olarak `tracking_risk_score` alanında temsil edilir.

Sonuç olarak 379 exposure record üretilmiştir ve tamamı critical occupancy contribution olarak değerlendirilmiştir.

### validate_outputs.py

Tüm in-memory pipeline kontratlarını doğrular. Structural error ile MVP warning durumlarını ayırır. Son doğrulama sonucu `ok=true`, `errors=0`, `warnings=9` olarak alınmıştır.

### run_pipeline.py

Final writer modülüdür. Default mod dry-run’dır; dosya yazmak için açıkça `--write` kullanılmalıdır. Yalnızca onaylı 14 çıktı dosyasını üretir ve Haki dizinine yazmayı engeller.

## 5. Üretilen Çıktılar

Workers:

```text
backend/data_processed/sample/workers/workers.json
backend/data_processed/sample/workers/worker_positions_clean.csv
backend/data_processed/sample/workers/worker_positions_demo.json
backend/data_processed/sample/workers/worker_segment_timeline.json
backend/data_processed/sample/workers/worker_segment_timeline_summary.json
backend/data_processed/sample/workers/uwb_extraction_summary.json
```

Anchors:

```text
backend/data_processed/sample/anchors/anchor_positions.json
backend/data_processed/sample/anchors/anchor_cables.json
backend/data_processed/sample/anchors/anchor_coverage_report.json
backend/data_processed/sample/anchors/anchor_tag_distances.json
backend/data_processed/sample/anchors/anchor_tag_distance_summary.json
```

Risk:

```text
backend/data_processed/sample/risk/worker_exposure_risk.json
```

UWB meta:

```text
backend/data_processed/sample/uwb/uwb_pipeline_manifest.json
backend/data_processed/sample/uwb/uwb_validation_summary.json
```

Toplam 14 onaylı çıktı dosyası üretildi.

## 6. Backend’e Aktarılan Veriler

Backend worker API’si şu dosyayı okur:

```text
backend/data_processed/sample/workers/workers.json
```

`workers.json`, her worker için latest snapshot kaydı içerir. Başlıca alanlar:

```text
worker_id
tag_id
time_step
latest_time_step
timestamp_s
latest_timestamp_s
current_segment
position
position_reliability
status
tracking_status
visible_anchor_count
tracking_risk_score
mapping_method
mapping_confidence
source_position_type
```

Backend compatibility alias kuralları korunmuştur:

```text
mapped_segment_id == current_segment
uwb_pose == position
motion_status == status
```

Önemli API uyumluluk düzeltmesi:

```text
workers.json latest snapshot dosyasında time_step = 0 olarak normalize edilmiştir. Orijinal worker timeline adımı latest_time_step alanında korunur. Bu sayede mevcut backend workers servisi default time_step=0 filtresiyle tüm latest worker snapshot kayıtlarını birlikte döndürür.
```

## 7. Backend API Doğrulaması

Django system check çalıştırılmıştır:

```text
python manage.py check
System check identified no issues
```

Backend server başlatılmış ve şu endpoint doğrulanmıştır:

```text
http://127.0.0.1:8000/api/workers
```

Trailing slash endpoint mevcut route olarak yapılandırılmamıştır:

```text
/api/workers/ is not the configured route
```

API sonucu 3 worker döndürmüştür:

```text
WORKER_01
WORKER_02
WORKER_03
```

Dönen worker kayıtlarında şu alanlar doğrulanmıştır:

```text
current_segment
mapped_segment_id
position
uwb_pose
tracking_status
visible_anchor_count
latest_time_step
```

## 8. Sayısal Sonuçlar

| Metric | Value |
|---|---:|
| Segment count | 143 |
| Graph edge count | 219 |
| CSV discovered | 52 |
| Matched worker trials | 3 |
| Valid pose samples | 75,819 |
| Valid TDoA samples | 148,668 |
| RawPose records | 379 |
| Mapped positions | 379 |
| Known mapped positions | 379 |
| Unknown mapped positions | 0 |
| Unique worker segments | 88 |
| Anchors | 283 |
| Cable links | 642 |
| Distance observations | 107,257 |
| Timeline records | 379 |
| Enriched timeline records | 379 |
| Exposure records | 379 |
| Latest workers | 3 |
| No-tracking records | 185 |
| Fallback mapping records | 133 |
| Worker exposure critical records | 379 |
| Validation errors | 0 |
| Validation warnings | 9 |

## 9. Validasyon ve Kontroller

Kullanılan temel kontrol komutları:

```powershell
python backend\uwb_processing\validate_outputs.py
python backend\uwb_processing\run_pipeline.py --dry-run
python backend\uwb_processing\run_pipeline.py --write
python manage.py check
Invoke-RestMethod http://127.0.0.1:8000/api/workers | ConvertTo-Json -Depth 10
```

`validate_outputs.py` sonucu `ok=true`, `errors=0` döndürmüştür. Warning kayıtları beklenen MVP sınırlamalarıdır ve structural failure değildir. Dry-run modunda pipeline build ve validation çalışır, ancak repository çıktısı yazılmaz.

## 10. Sınırlamalar ve Uyarılar

- UTIL pose_x/y/z values are motion-capture ground-truth proxy positions, not real UWB-estimated miner positions.
- bounds_fit transform is approximate and not calibrated UWB-to-mine registration.
- Segment mapping uses bounds-center graph geometry and fallback continuity.
- Anchor visibility is approximate distance/graph visibility, not calibrated RF propagation.
- Worker exposure risk is occupancy contribution only and does not include gas/geometric risk fusion.
- Final fused segment risk and emergency routing are owned by backend risk/routing modules.

Ek notlar:

- 185 `no_tracking` record safety debugging için korunmuştur.
- 133 fallback mapping kaydı düşük confidence ile açıkça işaretlenmiştir.
- Mean mapping confidence düşüktür; bunun ana nedeni transform’un MVP seviyesinde yaklaşık olmasıdır.
- `anchor_tag_distances.json` büyük bir dosyadır, yaklaşık 64.76 MB boyutundadır ve GitHub tarafından önerilen 50 MB dosya boyutu eşiğini aşar.

## 11. Bu Modülün Kapsamadığı İşler

UWB module şu işleri yapmaz:

```text
- final gas + geometry + worker risk fusion
- emergency route calculation
- certified localization
- real RF propagation modeling
- frontend/dashboard visualization
- Haki LiDAR map generation
```

Bu ayrım özellikle önemlidir: UWB pipeline worker occupancy ve takip güvenilirliği üretir; nihai segment risk ve rota kararları backend risk/routing katmanında verilmelidir.

## 12. Teslim Durumu

Çalışma branch’i:

```text
feature/uwb-worker-tracking
```

Commit:

```text
37daf2d Add UWB worker tracking pipeline
```

Push işlemi başarılıdır. PR şu adresten açılabilir:

```text
https://github.com/enesadige/maden/pull/new/feature/uwb-worker-tracking
```

Teslim edilen çalışma; UWB pipeline modüllerini, doğrulanmış çıktı dosyalarını, backend worker API uyumluluğunu ve dry-run/write güvenlik davranışını kapsamaktadır.

## 13. Gelecek İyileştirmeler

- Büyük anchor_tag_distances.json dosyası için summary-only veya compressed output seçeneği
- Gerçek UWB anchor kalibrasyonu
- Haki’den centerline/start/end veya wall polyline gelirse daha doğru segment mapping
- Daha gerçekçi RF/LOS görünürlük modeli
- Backend risk fusion ile worker exposure entegrasyonu
- Dashboard’da worker/anchor görselleştirme
- Çok daha fazla worker/trial ile config-driven test

## 14. Gerçek UWB Position Solver Genişletmesi

Mevcut MVP modu `position_source_mode = "mocap_proxy"` olarak çalışır. Bu modda `pose_x/y/z` değerleri worker hareketi için motion-capture ground-truth proxy pozisyonlarıdır. Anchor distance, takip güvenilirliği ve worker timeline bu proxy pozisyonlardan türetilir.

Yeni deneysel mod `position_source_mode = "tdoa_solver"` olarak tanımlanmıştır. In tdoa_solver mode, worker position is estimated from UWB measurements. The UTIL pose_x/y/z values are used only as motion-capture ground-truth proxy references for validation metrics, not as the primary position source.

Bu genişletme, calibrated anchor x/y/z koordinatları ve tag-anchor TDoA/ToF ölçümlerinden worker pozisyonu tahmin etme altyapısını ekler. Üretilen tahminler `pose_x/y/z` proxy ground truth ile karşılaştırılarak hata metrikleri üretir. Varsayılan konfigürasyonda solver kapalıdır ve mevcut `workers.json` veya `/api/workers` davranışını değiştirmez.

Gerçek saha kullanımı için ölçülmüş anchor koordinatları, clock synchronization, TDoA/ToF kalibrasyonu, NLOS/multipath validasyonu ve maden ortamına uygun certified/ex-proof donanım gerekir.

Bu genişletme, gerçek UWB sinyalinden konum hesaplama altyapısını ekler. Ancak gerçek saha doğruluğu, anchor kalibrasyonu ve donanım doğrulaması yapılmadan sertifikalı lokalizasyon iddiası taşımaz.

## 15. Gerçek UWB Position Solver Genişletmesi - Commit 38fe152

Yeni commit:

```text
38fe152 Add experimental UWB TDoA position solver
```

Bu commit, mevcut çalışan UWB worker tracking MVP pipeline'ını kaldırmadan deneysel gerçek UWB position solver altyapısını ekler. Projede artık iki ayrı UWB position mode açık şekilde ayrılmıştır.

### 15.1 Existing MVP mode

```text
position_source_mode = "mocap_proxy"
```

Bu mod varsayılan ve güvenli moddur. UTIL dataset içindeki `pose_x`, `pose_y`, `pose_z` değerleri motion-capture ground-truth proxy worker pozisyonları olarak kullanılır.

Bu mod, mevcut MVP pipeline çıktılarının temelidir:

```text
worker timeline
segment mapping
anchor-tag distance matrix
tracking reliability
worker exposure risk
backend-compatible workers.json
```

Mevcut `/api/workers` davranışı bu modda değişmeden korunur. Backend-compatible `workers.json` dosyası aynı latest worker snapshot sözleşmesini sürdürür.

### 15.2 New experimental real UWB solver mode

```text
position_source_mode = "tdoa_solver"
```

Bu mod yeni deneysel genişletmedir. Worker pozisyonu, kalibre edilmiş anchor koordinatları ve UWB ToF/TDoA ölçümleri kullanılarak tahmin edilir. Bu modda `pose_x/y/z` ana pozisyon kaynağı değildir.

tdoa_solver modunda worker pozisyonu UWB ölçümlerinden hesaplanır. UTIL pose_x/y/z değerleri ana konum kaynağı olarak değil, motion-capture ground-truth proxy doğrulama referansı olarak kullanılır.

Gerçek anchor calibration eksikse sistem güvenli şekilde `mocap_proxy` davranışına fallback yapabilir. Bu fallback açıkça `fallback_mocap_proxy` olarak raporlanır ve gerçek solved position iddiası üretmez.

### 15.3 Data flow

```text
Kalibre edilmiş anchor koordinatları
+ UWB tag-anchor ToF/TDoA ölçümleri
→ UWB position solver
→ estimated worker position
→ pose_x/y/z ile doğrulama
→ error metrics
→ Haki segment mapping
→ tracking reliability
→ worker exposure risk
→ backend output
```

### 15.4 Yeni dosyalar

```text
backend/uwb_processing/uwb_position_solver.py
backend/uwb_processing/uwb_anchor_calibration.example.json
```

Opsiyonel solver output dosyaları:

```text
backend/data_processed/sample/uwb/uwb_position_estimates.json
backend/data_processed/sample/uwb/uwb_solver_validation.json
```

Bu opsiyonel output dosyaları yalnızca solver output config içinde enabled olduğunda yazılır. Varsayılan config solver'ı kapalı tuttuğu için baseline 14 output dosyası değişmeden kalır.

### 15.5 Solver validation metrics

Solver validation summary aşağıdaki metrikleri destekler:

```text
mean_error_m
median_error_m
rmse_error_m
p95_error_m
max_error_m
mean_residual_rmse_m
solved_count
fallback_count
failed_count
```

### 15.6 Güncel doğrulama sonucu

Default config keeps solver disabled:

```text
enabled=false
position_source_mode=mocap_proxy
```

Existing pipeline still passes:

```text
validate_outputs.py → ok=true, error_count=0
run_pipeline.py --dry-run → baseline 14 files unchanged
run_pipeline.py --write → baseline 14 files written
python manage.py check → no issues
/api/workers → returned 3 worker snapshots
```

Targeted enabled + missing calibration check:

```text
estimate_count=379
solved_count=0
fallback_count=379
failed_count=0
```

Reason:

```text
Real field anchor calibration was not available. Therefore solver did not claim real solved positions and used explicit fallback_mocap_proxy behavior.
```

Bu genişletme gerçek UWB konum çözümü için yazılım altyapısı sağlar; gerçek saha doğruluğu için anchor kalibrasyonu, ölçüm birimi doğrulaması, clock synchronization, NLOS/multipath testi ve sertifikalı donanım gerekir.

### 15.7 Güncellenmiş sınırlamalar

- Gerçek UWB solver çıktısı, kalibre edilmiş anchor koordinatları ve doğru ToF/TDoA ölçüm birimleri sağlanmadan gerçek saha doğruluğu iddiası taşımaz.
- UTIL TDoA ölçüm birimleri açık şekilde doğrulanmalıdır; yanlış zaman/mesafe birimi solver hatasını büyütür.
- Gerçek sahada clock synchronization, anchor clock bias, NLOS/multipath ve RF zayıflaması ayrıca test edilmelidir.
- pose_x/y/z yalnızca doğrulama referansı olarak kullanılmalıdır; tdoa_solver modunda ana pozisyon kaynağı olmamalıdır.

### 15.8 Güncellenmiş gelecek iyileştirmeler

- TDoA/ToF ölçüm birimi doğrulaması
- Clock bias ve senkronizasyon düzeltmesi
- Gerçek anchor koordinatlarıyla saha kalibrasyonu
- NLOS/multipath outlier filtreleme
- Solver sonucunu güvenli şekilde workers.json backend snapshot'ına opsiyonel bağlama
- Solver error metrics dashboard gösterimi

## 16. Requirement Coverage Matrix

Review scope: Huseyin's UWB Worker Tracking MVP responsibilities only. Haki, Recep, Enes and Selim modules are considered only at integration boundaries.

Source note: `MadenGuard_AI_ML_Kullanim_Rehberi.docx` was requested as an input, but it was not present under `C:\Users\sarib\Desktop\maden_mn` during this review. The matrix below is therefore based on this report, the current `backend/uwb_processing/` implementation, generated UWB artifacts, and backend API integration points.

| Requirement | Status | Evidence | MVP classification |
|---|---|---|---|
| Read UWB/UTIL worker datasets | MVP complete | `dataset_reader.py` discovers and parses UTIL CSV pose/TDoA data; config-driven trial hints select worker trials. | Required MVP |
| Produce worker positions | MVP complete | `position_extractor.py`, `coordinate_mapper.py`, and generated `worker_positions_clean.csv` contain 379 worker position rows. | Required MVP |
| Produce worker movement over time | MVP complete | `worker_segment_timeline.json` contains 379 records across time steps 0-128. | Required MVP |
| Dynamic worker support | MVP complete | Workers are read from `uwb_config.example.json`; current demo has 3 workers, but loops and validation are config-driven. | Required MVP |
| Map workers onto Haki mine segments | MVP complete with quality warnings | `segment_mapper.py` maps all 379 positions; validation reports 0 unknown mapped positions, but 133 fallback records. | Required MVP |
| Generate `workers.json` | MVP complete | Latest worker snapshot file contains 3 backend-compatible workers. | Required MVP |
| Generate `worker_positions_clean.csv` | MVP complete | CSV has 379 rows and required position/reliability/status columns. | Required MVP |
| Generate `worker_positions_demo.json` | MVP complete | Demo JSON includes latest workers, timeline preview, summary and warnings. | Required MVP |
| Generate `worker_segment_timeline.json` | MVP complete | Timeline JSON includes worker, time, position, segment, reliability and tracking fields. | Required MVP |
| Generate `worker_exposure_risk.json` | MVP complete | Exposure file includes 379 occupancy contribution records. | Required MVP |
| Generate `current_segment` | MVP complete | Present in latest snapshots and historical timeline records. | Required MVP |
| Generate `position_reliability` | MVP complete | Computed in timeline enrichment from signal, visibility, mapping and continuity components. | Required MVP |
| Generate worker status | MVP complete | `status` is present in timeline, latest snapshots and exposure output. | Required MVP |
| Anchor generation | MVP complete | `anchor_planner.py` generates 283 anchors from segment/graph geometry. | Supporting MVP output |
| Cable generation | MVP complete | `cable_planner.py` generates 642 graph-based cable links. | Supporting MVP output |
| Anchor-tag distances | MVP complete | `distance_matrix.py` generates 107,257 distance observations. | Supporting MVP output |
| Backend API latest compatibility | MVP complete | `/api/workers` and `/api/workers?time_step=0` use latest snapshots from `workers.json`. | Required MVP |
| Backend API historical replay | MVP complete after service fix | Non-zero `/api/workers?time_step=N` reads `worker_segment_timeline.json`; unknown time step falls back to latest snapshots. | Required MVP integration |
| Generated JSON schema validity | MVP complete | `validate_outputs.py` reports `ok=true`, `error_count=0`. | Required MVP quality gate |
| Dry-run safe pipeline writer | MVP complete | `run_pipeline.py` defaults to dry-run and writes only approved output paths with `--write`. | Required MVP safety |
| Trapped status | Missing in UWB | UWB outputs do not compute route reachability or trapped state. | Other module / future integration |
| Collapse awareness | Missing in UWB | UWB module does not ingest collapse scenario state for worker status. | Other module / integration |
| LOS/NLOS classifier | Missing | Visibility is distance/graph heuristic only. | Future real-mine deployment |
| Behavior anomaly detection | Missing | No worker behavior model, speed anomaly classifier, or rule engine exists in UWB module. | Nice-to-have / future analytics |
| Real UWB TDoA localization | Experimental only | `uwb_position_solver.py` exists, but default config disables it and MVP uses mocap proxy positions. | Experimental, not MVP blocker |
| Real RF propagation model | Missing | Distance matrix explicitly does not model calibrated RF propagation. | Future real-mine deployment |
| Final gas + worker risk fusion | Missing in UWB | Exposure output is occupancy-only and intended for backend risk fusion. | Other module / future integration |
| Dashboard visualization | Missing in UWB | No frontend/dashboard work is part of this module. | Other module / future phase |

## 17. Completed Requirements

- UTIL/UWB dataset reader exists and parses configured worker trial data.
- Worker positions are produced from UTIL pose data and written to CSV/JSON artifacts.
- Worker movement timeline is dynamic over time, not a static snapshot only.
- Worker-to-segment mapping is implemented against Haki segment IDs.
- Latest worker snapshots are generated for backend consumption.
- Historical worker timeline is generated for replay and API queries.
- `current_segment`, `position_reliability`, `tracking_status`, `status`, `visible_anchor_count`, and `tracking_risk_score` are generated.
- Worker exposure risk output is generated as an occupancy contribution.
- Anchor placement is generated from segment/graph geometry.
- Cable topology is generated from anchor and graph topology.
- JSON artifacts validate with `validate_outputs.py` and current validation returns no structural errors.
- Backend API compatibility is satisfied for latest snapshots and historical replay.
- Worker configuration is data-driven; the implementation is not hardcoded to exactly 3 workers.

## 18. Partially Completed Requirements

- Segment mapping is functionally complete, but mapping quality is limited by bounds-center geometry and approximate coordinate registration. Current validation reports 133 fallback mapping records and low mean mapping confidence.
- Position reliability is implemented, but it is an MVP confidence estimate rather than a calibrated localization confidence model.
- Anchor visibility and anchor-tag distance outputs are complete as engineering approximations, but they are not RF/LOS/NLOS truth.
- Exposure risk is complete as UWB occupancy contribution, but it is not final mine risk and is not fused with gas, collapse, or geometry risk.
- Experimental TDoA solver code exists, but it is not the default localization source and is not production-calibrated.

## 19. Missing Requirements and Ownership

| Missing item | Why missing | Owner | Effort | Implementation plan |
|---|---|---|---:|---|
| Trapped status in UWB output | Trapped state requires route reachability, exits, blocked segments and graph routing, not only worker location. | Routing/backend owner, with UWB providing worker segment input | 2-4 days for integration once routing contract is fixed | Add a routing service call that accepts `worker_id`, `time_step`, `current_segment`, blocked segments and exits; return `trapped=true/false`; optionally copy result into a joined API response, not raw UWB artifacts. |
| Collapse awareness in UWB worker status | UWB pipeline does not consume collapse scenario state; it only emits worker location and tracking state. | Scenario/routing/backend owner, UWB integration support | 2-3 days | Define collapse event schema, join collapse blocked segment state with historical worker segment at API/service layer, add tests for worker in blocked/adjacent/safe segment. |
| LOS/NLOS classifier | No labeled LOS/NLOS dataset, wall mesh, RF features, or classifier model is available in UWB module. | Future localization/RF owner | 1-3 weeks after data availability | Collect labeled LOS/NLOS samples, add feature extraction from signal quality/TDoA residuals/map obstruction, train/evaluate classifier, expose LOS/NLOS flag per observation. |
| Behavior anomaly detection | MVP scope did not include anomaly analytics; no model or rules exist for abnormal movement. | Analytics/ML owner, UWB support | 3-7 days for rule-based MVP; 2-4 weeks for ML model | Start with speed/stationary/zone-entry rules over `worker_segment_timeline.json`, add thresholds to config, emit anomaly events, then evaluate ML sequence models if data is available. |
| Real calibrated UWB localization | MVP uses UTIL mocap proxy positions; experimental solver lacks field calibration and verified measurement units. | UWB localization owner | 2-6 weeks depending on calibration data | Verify TDoA/ToF units, collect calibrated anchor coordinates, handle clock bias, validate solver against ground truth, gate output by confidence, then optionally feed solver positions into backend artifacts. |
| Real RF propagation model | Current visibility is distance and graph based; no RF material model or mine wall model is available. | Future RF/localization owner | 3-6 weeks | Acquire mine geometry/material assumptions, implement path loss and obstruction model, validate against measured RSSI/UWB quality, replace or augment `distance_matrix.py` visibility. |
| Final gas + worker risk fusion | UWB exposure is intentionally occupancy-only; gas and geometry risk are separate backend domains. | Risk/backend owner, UWB as input provider | 3-5 days for first fused score | Define fused risk formula, join worker exposure with gas and geometry risk by segment/time, add API output and tests. |
| Dashboard visualization | UWB backend artifacts exist, but frontend visualization is outside this module. | Frontend/dashboard owner | 3-7 days | Add worker layer, timeline slider, anchor layer, cable layer, reliability/status colors, and API integration tests. |

## 20. Known Limitations

### MVP complete

- The MVP uses motion-capture proxy positions from UTIL `pose_x/y/z`; this is acceptable for the assigned worker tracking demo.
- Worker position reliability is an engineering confidence score, not certified localization accuracy.
- Segment mapping is approximate because the available geometry is bounds/center/graph based.
- `worker_exposure_risk` represents occupancy contribution only; it deliberately does not reduce exposure because of low tracking confidence.
- Generated outputs are file-based artifacts under `backend/data_processed/sample`, not a streaming real-time ingestion system.

### Experimental

- `uwb_position_solver.py` provides an experimental TDoA solver path.
- The solver is disabled by default with `enabled=false` and `position_source_mode=mocap_proxy`.
- Without calibrated anchor coordinates and verified TDoA units, solver output must not be treated as real mine localization.
- Solver fallback to mocap proxy is explicit and should not be presented as solved UWB positioning.

### Future real-mine deployment

- No certified UWB hardware integration exists.
- No anchor installation survey, calibration process, or clock synchronization workflow exists.
- No RF propagation, NLOS/multipath, material attenuation, or line-of-sight classifier exists.
- No production safety certification, failover, monitoring, alert audit trail, or operational deployment procedure exists.

## 21. Future Work

### MVP hardening

- Add a small generated fixture or contract test for dynamic worker counts greater than 3.
- Add schema contract tests for every generated JSON file, not only aggregate validation.
- Add API tests for `time_step=all` if full timeline replay is intended at the API boundary.
- Reduce or compress `anchor_tag_distances.json`, because the file is large for normal repository use.
- Improve coordinate registration to reduce fallback mapping and increase mapping confidence.

### Experimental track

- Validate UTIL TDoA measurement units before using solver output.
- Add calibrated anchor fixture data for repeatable solver tests.
- Add solver error thresholds and prevent low-confidence solver positions from entering backend snapshots.
- Add solver validation reports to CI when solver mode is explicitly enabled.

### Future real-mine deployment

- Build anchor calibration and survey tooling.
- Implement clock bias and synchronization correction.
- Add LOS/NLOS and multipath outlier handling.
- Integrate live UWB hardware ingestion.
- Add fused gas + geometry + worker risk in the backend risk layer.
- Add route-aware trapped detection in the routing layer.
- Add dashboard visualization for workers, anchors, cables, timeline replay and reliability states.

## 22. Worker Count and Behavior Anomaly Update

Default worker count is now 10.

Worker count is config-driven in the UWB config/pipeline layer:

- If `workers` is explicitly filled, config_loader.py uses exactly that list.
- If `workers` is empty or missing and `worker_defaults.allow_auto_generate_workers=true`, `worker_defaults.default_worker_count` generates workers.
- Worker count can be increased or decreased by config only.
- Django does not generate workers. Django only reads generated JSON outputs such as `backend/data_processed/sample/workers/workers.json` and `backend/data_processed/sample/workers/worker_segment_timeline.json`, then returns whatever workers exist in those files.

Current generated result:

| Metric | Value |
|---|---:|
| Workers count | 10 |
| Timeline record count | 1308 |
| Anomaly event count | 1640 |

New behavior anomaly outputs:

```text
backend/data_processed/sample/workers/behavior_anomaly_events.json
backend/data_processed/sample/workers/behavior_anomaly_summary.json
```

Behavior anomaly event types:

```text
stationary_too_long
low_position_reliability
tracking_lost_in_risky_segment
entered_high_risk_segment
near_blocked_segment
route_deviation
```

These behavior anomaly events are rule-based MVP analytics only. They are not certified safety decisions.

LOS/NLOS limitation: LOS/NLOS classifier is not implemented. Current anchor visibility is heuristic and based on distance/graph visibility assumptions. A real LOS/NLOS classifier requires labeled LOS/NLOS data before it can be trained, validated, and used for safety-relevant interpretation.

MVP'de UTIL pose verisi worker hareket proxy'si olarak kullanılır. Gerçek UWB TDoA solver deneysel altyapıdır; saha kalibrasyonu ve ölçüm birimi doğrulaması olmadan gerçek konum doğruluğu iddiası taşımaz.

Worker trapped durumu UWB modülünde nihai olarak üretilmez. UWB modülü worker konumu, güvenilirlik, exposure ve davranış anomaly sinyalleri üretir; trapped kararı backend route/simulation katmanında verilmelidir.
