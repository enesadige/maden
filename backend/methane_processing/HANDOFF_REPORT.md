# Methane / Gas Sensor Processing Handoff Report

## 1. Amaç

Bu çalışma, **MadenGuard AI** projesinde methane / gaz sensörü verisinin işlenmesi, LiDAR tabanlı maden segmentleriyle ilişkilendirilmesi ve backend ile simulation/fusion pipeline tarafına tüketilebilir risk çıktıları üretilmesi için yapılmıştır.

Bu rapor, `feature/recep-methane-risk` branch'inde yapılan işi açıklar. Amaç, ekipteki başka bir kişinin bu branch'i açıp okuduğunda şu sorulara net cevap bulabilmesidir:

- Recep'in görev kapsamı neydi?
- Hangi dosyalar eklendi veya değiştirildi?
- Methane/gaz sensörü pipeline'ı nasıl çalışıyor?
- Hangi input verileri kullanılıyor?
- Hangi output dosyaları üretiliyor?
- Backend ve fusion pipeline tarafıyla entegrasyon nasıl sağlandı?
- Bu branch hangi işleri kapsıyor, hangi işleri kapsamıyor?

---

## 2. Görev Kapsamı

Bu branch'in sorumluluğu **methane / gaz sensörü risk işleme katmanı**dır.

Yapılan temel iş:

- OpenML methane verisini okuyup zaman serisi formatına getirmek.
- `MM263`, `MM264`, `MM256` kolonlarını ayrı gaz sensörü kanalları gibi kullanmak.
- Bu gaz sensörlerini Haki'nin LiDAR segmentleriyle eşleştirmek.
- Her zaman adımı için:
  - `methane_value`
  - `anomaly_score`
  - `methane_risk_score`
  - `environmental_risk`
  - `status`
  üretmek.
- Backend'in okuyabileceği canonical handoff dosyalarını oluşturmak.
- Mevcut simulation/fusion pipeline ile uyumlu timeline çıktısı üretmek.
- Backend API tarafında `/api/gas-sensors` ve `/api/risk/segments` endpointleriyle entegrasyonu test etmek.

Bu branch, aşağıdaki işleri **kapsamaz**:

- UWB worker tracking algoritması yazmak.
- Haki'nin LiDAR/SLAM segment üretimini değiştirmek.
- Frontend ekranı geliştirmek.
- Emergency routing veya kaçış yolu hesaplamak.
- Final risk ownership katmanını baştan yazmak.
- Gerçek fiziksel methane sensöründen canlı veri almak.

---

## 3. Branch Yapısı

Çalışma branch'i:

```text
feature/recep-methane-risk
```

Bu branch, Hüseyin'in UWB worker tracking branch'i üzerine eklenmiştir:

```text
feature/uwb-worker-tracking
```

Yapı şu şekildedir:

```text
main
 └── feature/uwb-worker-tracking
      └── feature/recep-methane-risk
```

Yani `feature/recep-methane-risk`, `feature/uwb-worker-tracking` branch'inin üzerine sadece methane/gaz sensörü işleme commit'lerini ekler.

---

## 4. Eklenen Ana Modül

Yeni modül:

```text
backend/methane_processing/
```

Bu klasör methane/gaz sensörü pipeline'ının ana kodlarını içerir.

Dosya yapısı:

```text
backend/methane_processing/
├── README.md
├── HANDOFF_REPORT.md
├── __init__.py
├── core.py
├── dataset_reader.py
├── segment_mapper.py
├── anomaly.py
├── risk_scoring.py
├── timeline_builder.py
├── validate_outputs.py
├── run_pipeline.py
└── methane_config.example.json
```

---

## 5. Dosyaların Görevleri

### 5.1. `core.py`

Pipeline genelinde kullanılan temel sabitleri, path tanımlarını ve yardımcı fonksiyonları içerir.

Önemli görevleri:

- Repo kök dizinini belirler.
- Backend sample output dizinlerini tanımlar.
- Input/output JSON path'lerini merkezi olarak yönetir.
- Methane CSV dosya yolunu environment variable veya config üzerinden okur.
- Segment ID normalizasyonu yapar.
- Risk skorunu durum seviyesine çevirir.

Önemli path'ler:

```text
backend/data_processed/sample/sensors/gas_sensors.json
backend/data_processed/sample/sensors/gas_sensor_mapping.json
backend/data_processed/sample/sensors/methane_pipeline_summary.json
backend/data_processed/sample/risk/environmental_risk.json
processed/timelines/gas_sensors_timeline.json
simulation_ready/gas_sensors_timeline.json
reports/gas_risk_report.md
```

Önemli fonksiyonlardan bazıları:

```python
normalize_segment_id(...)
risk_status(...)
methane_csv_path(...)
runtime_int(...)
read_json(...)
write_json(...)
```

---

### 5.2. `dataset_reader.py`

OpenML methane dataset CSV dosyasını okur.

Bu dosyada özellikle şu kolonlar kullanılmıştır:

```text
MM263
MM264
MM256
```

Bu kolonlar üç farklı methane/gaz sensörü kanalı gibi ele alınmıştır.

Görevleri:

- CSV dosyasını standart Python `csv.DictReader` ile okur.
- Ekstra bağımlılık kullanmaz.
- Büyük dosyalarda tüm veriyi doğrudan işlememek için örnekleme yapar.
- `max_rows` ve `target_steps` değerlerine göre zaman adımı üretir.
- Her zaman adımı için methane sensör değerlerini normalize edilmiş bir yapı halinde döndürür.

Varsayılan değerler:

```text
max_rows = 200000
target_steps = 90
```

Bunun sonucu olarak 3 sensör x 90 zaman adımı = 270 gaz sensörü kaydı üretilir.

---

### 5.3. `segment_mapper.py`

Methane/gaz sensörlerinin Haki'nin LiDAR segmentleriyle eşleştirilmesini sağlar.

Kullanılan Haki çıktıları:

```text
backend/data_processed/sample/haki_lidar/segments/map_segments.json
backend/data_processed/sample/haki_lidar/risk/geometry_risk.json
```

Ek olarak mevcut legacy fusion pipeline ile uyum için şu dosyadaki segmentler de dikkate alınır:

```text
processed/features/segments.json
```

Bu dosya eski simulation/fusion katmanının `SEG_XXX` formatındaki segmentleriyle çalıştığı için kullanılır.

Temel karar:

- Backend handoff tarafında canonical segment ID formatı `SXXX` olarak korunur.
- Legacy fusion tarafında gerekiyorsa `SEG_XXX` formatına çevrilmiş timeline ayrıca üretilir.

Segment seçimi yapılırken şu faktörler dikkate alınır:

- `geometry_risk`
- segmentin riskli olup olmaması
- junction/tünel bağlantı tipi
- ana yol rolü
- bağlantı sayısı

Bu sayede gaz sensörleri rastgele değil, dijital ikizde daha anlamlı/riskli görülen segmentlere yerleştirilir.

---

### 5.4. `anomaly.py`

Methane değerleri için anomaly score üretir.

Kullanılan yaklaşım:

- Rolling window tabanlı z-score
- Mevcut değerin geçmiş pencereye göre ne kadar saptığını ölçer.
- Pencere içinde ortalama ve standart sapma hesaplanır.
- Z-score normalize edilerek `0.0 - 1.0` aralığında anomaly score üretilir.

Temel özellik:

- Mevcut değer pencereye dahil edilmeden önce geçmişe göre değerlendirilir.
- Böylece ani değişimler daha net yakalanır.
- Çok küçük varyans durumlarında sıfıra bölme gibi durumlar kontrol edilir.

Örnek alan:

```json
"anomaly_score": 0.72
```

---

### 5.5. `risk_scoring.py`

Methane risk skorunu üretir.

Skor iki ana bileşenden oluşur:

```text
methane_risk_score = value_score + anomaly_score birleşimi
```

Kullanılan ağırlık:

```text
%60 methane değer skoru
%40 anomaly skoru
```

Basitleştirilmiş formül:

```text
methane_risk_score = 100 * (0.60 * robust_value_score + 0.40 * anomaly_score)
```

Burada `robust_value_score`, methane değerlerinin uç değerlere çok duyarlı olmaması için percentile tabanlı hesaplanır.

Durum seviyeleri:

```text
0  - 30  → normal
30 - 60  → medium
60 - 80  → high
80 - 100 → critical
```

Bu değerler sistemdeki risk gösterimi için kullanılır.

---

### 5.6. `timeline_builder.py`

Methane sensör verilerinden zaman serisi output kayıtlarını üretir.

Üretilen ana kayıt tipi:

```json
{
  "time_step": 0,
  "timestamp": "2026-01-01T00:00:00",
  "source_row": 0,
  "sensor_id": "GAS_SENSOR_01",
  "segment_id": "S006",
  "source_column": "MM263",
  "methane_value": 0.1,
  "methane_risk_score": 25.4,
  "anomaly_score": 0.0,
  "environmental_risk": 25.4,
  "status": "normal",
  "placement_reason": "haki_geometry_risk_or_junction_priority",
  "segment_type": "...",
  "segment_role": "...",
  "geometry_risk": 42.0
}
```

Üretilen iki ana veri grubu vardır:

1. Gas sensor timeline
2. Environmental risk records

Gas sensor timeline, sensör bazlı veridir.

Environmental risk records ise backend risk klasörüne yazılan çevresel risk çıktısıdır.

---

### 5.7. `validate_outputs.py`

Pipeline outputlarının beklenen şemaya uygun olup olmadığını kontrol eder.

Kontrol edilen başlıklar:

- Output boş mu?
- Zorunlu alanlar var mı?
- `sensor_id` formatı doğru mu?
- `segment_id` Haki segmentleri içinde var mı?
- Sayısal alanlar geçerli mi?
- Risk skorları `0 - 100` aralığında mı?
- `status` / `risk_level` geçerli değerlerden biri mi?

Geçerli durum değerleri:

```text
normal
low
medium
high
critical
```

Validation başarısız olursa pipeline hata verir ve bozuk output yazılmasının önüne geçilir.

---

### 5.8. `run_pipeline.py`

Methane pipeline'ın ana giriş noktasıdır.

Ana akış:

```text
1. Output dizinlerini hazırla
2. Config ve CSV path bilgisini oku
3. Haki segmentleriyle sensor mapping oluştur
4. Methane CSV örneklerini oku
5. Gas sensor timeline üret
6. Environmental risk kayıtlarını üret
7. Output validation yap
8. Backend handoff JSON dosyalarını yaz
9. Legacy fusion uyumlu simulation_ready timeline üret
10. Rapor ve summary dosyalarını yaz
```

Bu dosyada ayrıca iki farklı segment ID formatı bilinçli olarak ayrılmıştır.

Backend/API tarafı:

```text
S001, S002, S003 ...
```

Legacy simulation/fusion tarafı:

```text
SEG_001, SEG_002, SEG_003 ...
```

Bu kararın nedeni, backend tarafında Haki'nin canonical segment formatı kullanılırken, eski fusion pipeline'ın `processed/features/segments.json` üzerinden `SEG_XXX` formatıyla join yapmasıdır.

Bu yüzden:

- `backend/data_processed/sample/sensors/gas_sensors.json` dosyasında `SXXX` formatı kullanılır.
- `simulation_ready/gas_sensors_timeline.json` dosyasında legacy uyumluluk için `SEG_XXX` formatı kullanılır.
- Bu timeline içinde `canonical_segment_id` alanı da korunur.

---

## 6. Değiştirilen Script

Değiştirilen dosya:

```text
scripts/05_build_gas_timeline.py
```

Önceden bu script daha basit/placeholder timeline üretimi yapıyordu.

Yeni haliyle bu script sadece wrapper görevi görür:

```python
from backend.methane_processing.run_pipeline import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
```

Böylece mevcut pipeline çağrısı korunur:

```bash
python scripts/05_build_gas_timeline.py
```

Ama asıl iş artık modüler şekilde `backend/methane_processing` altında yapılır.

---

## 7. Input Veri

Methane/gaz sensörü pipeline'ı raw CSV dosyasını repo içine koymaz.

CSV path şu iki yoldan okunabilir:

### 7.1. Environment variable ile

```bash
export MADENGUARD_METHANE_CSV="$HOME/Desktop/methane-risk-pipeline/data_raw/methane_openml_42701.csv"
```

### 7.2. `config/paths.json` ile

Örnek yapı:

```json
{
  "paths": {
    "methane_csv": "/absolute/path/to/methane_openml_42701.csv"
  }
}
```

Raw CSV dosyası büyük ve dış veri olduğu için commit edilmez.

---

## 8. Üretilen Output Dosyaları

### 8.1. Backend Gas Sensor Handoff

```text
backend/data_processed/sample/sensors/gas_sensors.json
```

Backend'in `/api/gas-sensors` endpointi bu dosyayı okur.

Bu dosya canonical `SXXX` segment ID formatını kullanır.

Örnek alanlar:

```json
{
  "time_step": 0,
  "sensor_id": "GAS_SENSOR_01",
  "segment_id": "S006",
  "source_column": "MM263",
  "methane_value": 0.1,
  "methane_risk_score": 25.4,
  "anomaly_score": 0.0,
  "environmental_risk": 25.4,
  "status": "normal"
}
```

---

### 8.2. Environmental Risk Handoff

```text
backend/data_processed/sample/risk/environmental_risk.json
```

Bu dosya methane/gaz sensörü tabanlı çevresel risk kayıtlarını içerir.

Amaç, backend veya final risk katmanının gaz kaynaklı çevresel risk bilgisini tüketebilmesidir.

---

### 8.3. Sensor Mapping

```text
backend/data_processed/sample/sensors/gas_sensor_mapping.json
```

Bu dosya hangi OpenML kolonunun hangi gaz sensörüne ve hangi LiDAR segmentine bağlandığını gösterir.

Örnek:

```json
{
  "MM263": {
    "sensor_id": "GAS_SENSOR_01",
    "segment_id": "S006",
    "source_column": "MM263"
  }
}
```

---

### 8.4. Pipeline Summary

```text
backend/data_processed/sample/sensors/methane_pipeline_summary.json
```

Pipeline çalıştırıldığında üretilen özet bilgileri içerir.

İçeriğinde genel olarak şunlar yer alır:

- CSV path
- kullanılan satır sayısı
- hedef zaman adımı sayısı
- toplam gaz sensörü kayıt sayısı
- maksimum methane risk skoru
- sensör mapping bilgisi
- validation sonucu

---

### 8.5. Processed Timeline

```text
processed/timelines/gas_sensors_timeline.json
```

Bu dosya pipeline'ın processed timeline çıktısıdır.

Mevcut simulation/fusion pipeline ile uyumlu olacak şekilde üretilir.

---

### 8.6. Simulation Ready Timeline

```text
simulation_ready/gas_sensors_timeline.json
```

Bu dosya legacy fusion script tarafından okunur.

Önemli not:

- Backend handoff dosyaları `SXXX` kullanır.
- Bu dosya legacy uyumluluk için `SEG_XXX` kullanabilir.
- `canonical_segment_id` alanı ile orijinal `SXXX` değeri korunur.

---

### 8.7. Gas Risk Report

```text
reports/gas_risk_report.md
```

Pipeline çalışması sonrası kısa bir markdown raporu üretir.

Bu raporda:

- kayıt sayısı
- maksimum risk
- kullanılan sensör kolonları
- segment eşleşmeleri
- validation durumu

gibi bilgiler özetlenir.

---

## 9. Backend Entegrasyonu

Backend tarafında mevcut endpointler üzerinden test yapılmıştır.

Test edilen endpointler:

```text
/api/health
/api/gas-sensors?time_step=0
/api/risk/segments?time_step=0
```

Beklenen davranış:

- `/api/health` backend'in ayakta olduğunu gösterir.
- `/api/gas-sensors?time_step=0` methane/gaz sensörü kayıtlarını döndürür.
- `/api/risk/segments?time_step=0` risk segmentleri endpointinin bozulmadan çalıştığını gösterir.

Bu çalışma frontend tarafına doğrudan müdahale etmez. Frontend, backend endpointleri üzerinden bu verileri tüketebilir.

---

## 10. Fusion Pipeline Entegrasyonu

Mevcut fusion pipeline şu script ile çalıştırılır:

```bash
python scripts/07_fuse_risk_timeline.py
```

Bu script `simulation_ready/gas_sensors_timeline.json` dosyasını okuyarak final segment risk timeline içine methane/gaz risk bilgisini dahil eder.

Bu nedenle `run_pipeline.py` içinde ayrıca legacy uyumlu timeline üretilmiştir.

Kontrol edilen sonuç:

- 3 gaz sensörü aktif olarak fusion çıktısına girmelidir.
- 90 zaman adımı x 3 sensör = 270 aktif sensör kaydı beklenir.

Beklenen kontrol çıktısı:

```text
active_sensor_record_count: 270
active_sensors: ['GAS_SENSOR_01', 'GAS_SENSOR_02', 'GAS_SENSOR_03']
```

---

## 11. Çalıştırma Talimatı

Repo kök dizininde çalıştırılır:

```bash
cd ~/Desktop/maden-recep
```

Methane CSV path'i verilir:

```bash
export MADENGUARD_METHANE_CSV="$HOME/Desktop/methane-risk-pipeline/data_raw/methane_openml_42701.csv"
```

Methane/gaz timeline üretilir:

```bash
python scripts/05_build_gas_timeline.py
```

Fusion pipeline çalıştırılır:

```bash
python scripts/07_fuse_risk_timeline.py
```

Backend kontrolü için:

```bash
cd backend
source .venv/bin/activate
python manage.py check
python manage.py runserver
```

Endpoint testleri:

```bash
curl "http://localhost:8000/api/health"
curl "http://localhost:8000/api/gas-sensors?time_step=0"
curl "http://localhost:8000/api/risk/segments?time_step=0"
```

---

## 12. Validation Komutları

Pipeline sonrası fusion çıktısında gaz sensörlerinin yakalanıp yakalanmadığını kontrol etmek için:

```bash
python3 - <<'PY'
import json

with open("simulation_ready/final_segment_risk_timeline.json", "r", encoding="utf-8") as file:
    records = json.load(file)

active = [item for item in records if item.get("active_sensor_ids")]
active_sensors = sorted({sid for item in active for sid in item.get("active_sensor_ids", [])})

print("active_sensor_record_count:", len(active))
print("active_sensors:", active_sensors)
PY
```

Beklenen:

```text
active_sensor_record_count: 270
active_sensors: ['GAS_SENSOR_01', 'GAS_SENSOR_02', 'GAS_SENSOR_03']
```

---

## 13. Tasarım Kararları

### 13.1. Raw CSV Neden Commit Edilmedi?

Methane CSV dış veri kaynağıdır ve repo içinde tutulmamalıdır.

Bu yüzden dosya yolu environment variable veya config üzerinden verilir:

```bash
MADENGUARD_METHANE_CSV
```

---

### 13.2. Neden `MM263`, `MM264`, `MM256` Kullanıldı?

OpenML methane datasetindeki bu kolonlar bağımsız methane ölçüm kanalları gibi kullanıldı.

Bu sayede demo sistemde üç farklı gaz sensörü simüle edilebildi:

```text
MM263 → GAS_SENSOR_01
MM264 → GAS_SENSOR_02
MM256 → GAS_SENSOR_03
```

---

### 13.3. Neden Haki Segmentleriyle Eşleştirildi?

Projenin genel mimarisi dijital ikiz / LiDAR segmentleri üzerine kurulu olduğu için methane sensörlerinin de bu segmentlerle ilişkilendirilmesi gerekir.

Bu sayede gaz riski sadece bağımsız sensör datası olarak değil, maden haritasındaki belirli segmentlere bağlı çevresel risk olarak kullanılabilir.

---

### 13.4. Neden Hem `SXXX` Hem `SEG_XXX` Var?

Projede iki farklı segment ID standardı oluşmuş durumda:

Backend/Haki handoff tarafı:

```text
S001
S002
S003
```

Legacy simulation/fusion tarafı:

```text
SEG_001
SEG_002
SEG_003
```

Bu branch'te backend tarafında canonical `SXXX` formatı korunmuştur. Ancak mevcut fusion scriptlerinin çalışması için `simulation_ready` çıktısında `SEG_XXX` uyumluluğu sağlanmıştır.

Bu geçici/uyumluluk amaçlı bir çözümdür.

---

### 13.5. Neden Anomaly Score Kullanıldı?

Sadece methane değerine bakmak yeterli değildir. Bazı durumlarda değerin ani yükselmesi de risk sinyali olabilir.

Bu yüzden iki risk bileşeni kullanılmıştır:

- Mutlak methane seviyesi
- Geçmiş pencereye göre anomali seviyesi

Bu iki değer birleştirilerek `methane_risk_score` üretilmiştir.

---

## 14. Sınırlar ve Geliştirilebilecek Noktalar

Bu branch MVP/demo seviyesinde methane risk processing sağlar.

Gelecekte geliştirilebilecek noktalar:

- Gerçek sensör verisiyle entegrasyon.
- MQTT veya WebSocket ile canlı gaz sensörü akışı.
- Sensör konumlarının manuel/harita tabanlı atanması.
- Threshold değerlerinin domain expert bilgisiyle ayarlanması.
- Anomaly detection için Isolation Forest veya benzeri model eklenmesi.
- Methane dışında CO, CO2, sıcaklık, nem gibi çevresel sensörlerin eklenmesi.
- Backend final risk katmanında methane risk ağırlığının daha kontrollü kullanılması.
- Frontend üzerinde gaz sensörü heatmap veya segment overlay gösterimi.

---

## 15. Yapılan Testler

Aşağıdaki kontroller yapılmıştır:

```bash
python scripts/05_build_gas_timeline.py
python scripts/07_fuse_risk_timeline.py
python manage.py check
curl "http://localhost:8000/api/health"
curl "http://localhost:8000/api/gas-sensors?time_step=0"
curl "http://localhost:8000/api/risk/segments?time_step=0"
```

Pipeline çıktısında beklenen genel sonuç:

```text
gas records: 270
environmental risk records: 270
output validation: OK
```

Fusion kontrolünde beklenen genel sonuç:

```text
active_sensor_record_count: 270
active_sensors: ['GAS_SENSOR_01', 'GAS_SENSOR_02', 'GAS_SENSOR_03']
```

---

## 16. Özet

Bu branch ile MadenGuard AI projesine methane/gaz sensörü risk işleme katmanı eklenmiştir.

Özetle yapılanlar:

- OpenML methane dataset okundu.
- Üç methane kanalı gaz sensörü olarak modellendi.
- Sensörler LiDAR segmentleriyle eşleştirildi.
- Methane değerinden anomaly ve risk skorları üretildi.
- Backend için canonical JSON çıktıları oluşturuldu.
- Simulation/fusion pipeline için uyumlu timeline üretildi.
- Backend endpointleri ve fusion pipeline ile entegrasyon test edildi.
- Raw veri commit edilmeden, path tabanlı konfigürasyon yapısı kullanıldı.

Bu çalışma Recep'in methane/gaz sensörü görev kapsamını tamamlar ve takımın final risk / frontend / simulation katmanlarının bu çıktıları tüketebilmesine hazır hale getirir.
