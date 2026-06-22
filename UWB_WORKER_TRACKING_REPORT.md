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
