# Multi-Sensor Environmental Risk Extension Raporu

## 1. Amaç

Bu doküman, `backend/methane_processing` pipeline’ına eklenen **çoklu sensör destekli çevresel risk genişletmesini** açıklar.

Önceki sistem ağırlıklı olarak metan verisi üzerinden çalışıyordu. Seçilen metan kanallarından `methane_risk_score` üretiliyor ve bu skor doğrudan `environmental_risk` alanı olarak kullanılıyordu.

Bu geliştirme ile mevcut metan tabanlı yapı bozulmadan; CO, O2, sıcaklık, nem ve basınç gibi ek çevresel bağlam değerleri deterministic demo/simülasyon verisi olarak üretilmiştir.

Amaç, mevcut backend, frontend, simülasyon ve risk fusion entegrasyonlarını bozmadan çevresel risk çıktısını daha açıklanabilir ve çok bileşenli hale getirmektir.

---

## 2. Tasarım Prensibi

Bu geliştirme **backward-compatible** olacak şekilde tasarlanmıştır.

Mevcut alanlar korunmuştur:

```text
methane_value
methane_risk_score
anomaly_score
environmental_risk
status
risk_level
sensor_id
segment_id
```

Yeni alanlar mevcut çıktılara ek zenginleştirme olarak dahil edilmiştir:

```text
measurements
component_scores
weighted_multi_sensor_risk
sensor_reliability_score
confidence
reliability_status
reliability_reason
reliability_reasons
environmental_risk_reason
environmental_risk_formula
```

Herhangi bir endpoint path’i değiştirilmemiştir. Mevcut frontend ve backend akışı korunmuştur.

---

## 3. Eklenen Dosyalar

### `environmental_sensors.py`

Bu dosya, mevcut metan risk skoru ve anomaly skoru üzerinden deterministic çevresel ölçümler üretir.

Üretilen ölçüm alanları:

```json
{
  "methane_value": 0.0,
  "methane_ppm": 1001.58,
  "co_ppm": 14.952,
  "oxygen_percent": 20.465,
  "temperature_c": 24.515,
  "humidity_percent": 55.075,
  "pressure_hpa": 1011.234
}
```

Bu ölçümlerden her çevresel bileşen için ayrı risk skoru hesaplanır:

```json
{
  "methane_risk": 15.0,
  "co_risk": 7.074,
  "oxygen_risk": 1.4,
  "temperature_risk": 0.0,
  "humidity_risk": 0.0,
  "pressure_risk": 0.0
}
```

CH4/metan dışındaki CO, O2, sıcaklık, nem ve basınç değerleri gerçek saha sensörü ölçümü değildir. Bunlar MVP/demo amacıyla deterministik olarak üretilen simülasyon bağlam değerleridir.

Random veri kullanılmaz. Aynı input için aynı output üretilir.

---

### `reliability.py`

Bu dosya, her sensör kaydı için güvenilirlik ve karar güveni metadata’sı üretir.

Örnek çıktı:

```json
{
  "sensor_reliability_score": 1.0,
  "confidence": 1.0,
  "reliability_status": "reliable",
  "reliability_reason": "complete_plausible_demo_sensor_record",
  "reliability_reasons": [
    "complete_plausible_demo_sensor_record"
  ]
}
```

Tasarım kararı olarak `sensor_reliability_score` ve `confidence` değerleri final risk skorunu düşürmek için kullanılmaz.

Bunun nedeni güvenlik mantığıdır: Tehlikeli görünen bir ölçüm, düşük confidence nedeniyle bastırılmamalıdır. Düşük confidence durumu yalnızca metadata olarak gösterilir ve frontend/backend tarafında uyarı olarak değerlendirilebilir.

---

## 4. Risk Skoru Tasarımı

Bu geliştirme iki farklı risk değeri üretir:

```text
weighted_multi_sensor_risk
environmental_risk
```

---

### 4.1. `weighted_multi_sensor_risk`

`weighted_multi_sensor_risk`, çoklu çevresel bileşen skorlarının ağırlıklı birleşimidir.

Formül:

```text
0.40 * methane_risk
+ 0.20 * co_risk
+ 0.20 * oxygen_risk
+ 0.10 * temperature_risk
+ 0.05 * humidity_risk
+ 0.05 * pressure_risk
```

Ağırlıklandırma mantığı:

```text
methane_risk      → ana patlayıcı gaz riski
co_risk           → toksik gaz / yanma belirtisi
oxygen_risk       → solunabilir atmosfer riski
temperature_risk  → ısıl stres / yangın bağlamı
humidity_risk     → ortam koşulu bağlamı
pressure_risk     → havalandırma / basınç sapması bağlamı
```

---

### 4.2. `environmental_risk`

`environmental_risk`, backend risk fusion tarafından kullanılan final çevresel risk skorudur.

Güvenlik ve backward compatibility için final skor şu şekilde hesaplanır:

```text
environmental_risk = max(methane_risk_score, weighted_multi_sensor_risk)
```

Bu kararın amacı, yeni çoklu sensör skorunun mevcut metan tabanlı risk sinyalini bastırmasını engellemektir.

Örnek:

```text
methane_risk_score = 15.0
weighted_multi_sensor_risk = 7.695
environmental_risk = 15.0
```

Bu durumda `environmental_risk_reason` içine şu açıklama eklenir:

```text
methane_risk_floor_applied
```

Yani ek çevresel sensörler riski artırabilir veya açıklayabilir; ancak mevcut metan risk skorunu düşüremez.

---

## 5. Güncellenen Dosyalar

Kod tarafında güncellenen veya eklenen dosyalar:

```text
backend/methane_processing/environmental_sensors.py
backend/methane_processing/reliability.py
backend/methane_processing/risk_scoring.py
backend/methane_processing/timeline_builder.py
backend/methane_processing/validate_outputs.py
```

Pipeline tarafından yeniden üretilen çıktı dosyaları:

```text
backend/data_processed/sample/sensors/gas_sensors.json
backend/data_processed/sample/risk/environmental_risk.json
backend/data_processed/sample/sensors/methane_pipeline_summary.json
processed/timelines/gas_sensors_timeline.json
simulation_ready/gas_sensors_timeline.json
reports/gas_risk_report.md
```

Generated JSON ve rapor dosyaları elle düzenlenmemelidir. Bu dosyalar pipeline çalıştırılarak yeniden üretilmelidir.

---

## 6. Output Alanları

### 6.1. Korunan Alanlar

Mevcut entegrasyonun bozulmaması için aşağıdaki alanlar korunmuştur:

```text
time_step
timestamp
source_row
sensor_id
segment_id
source_column
methane_value
methane_risk_score
anomaly_score
environmental_risk
status
risk_level
placement_reason
segment_type
segment_role
geometry_risk
```

---

### 6.2. Yeni Eklenen Alanlar

Aşağıdaki alanlar yeni çoklu sensör risk açıklaması için eklenmiştir:

```text
measurements
component_scores
weighted_multi_sensor_risk
sensor_reliability_score
confidence
reliability_status
reliability_reason
reliability_reasons
environmental_risk_reason
environmental_risk_formula
```

Bu alanlar hem `gas_sensors.json` hem de `environmental_risk.json` çıktılarında bulunur.

---

## 7. Validation

`validate_outputs.py` dosyası yeni alanları kontrol edecek şekilde genişletilmiştir.

Artık aşağıdaki kontroller yapılır:

```text
measurements alanı mevcut mu?
component_scores alanı mevcut mu?
weighted_multi_sensor_risk 0-100 aralığında mı?
sensor_reliability_score 0-1 aralığında mı?
confidence 0-1 aralığında mı?
reliability_status geçerli değerlerden biri mi?
environmental_risk_reason liste formatında mı?
environmental_risk_formula geçerli mi?
risk_level / status geçerli mi?
segment_id geçerli mi?
```

Son pipeline çalıştırma sonucu:

```text
[methane] gas records: 270
[methane] environmental risk records: 270
[methane] max risk: 100.0
[methane] output validation: OK
```

---

## 8. Backend Entegrasyonu

Bu geliştirme backend tarafında breaking change oluşturmaz.

Korunan noktalar:

```text
Endpoint pathleri değişmedi.
Mevcut JSON alanları kaldırılmadı.
environmental_risk hâlâ 0-100 arası numeric skor olarak dönüyor.
risk_level ve status değerleri mevcut formatı koruyor.
Backend risk fusion environmental_risk alanını okumaya devam ediyor.
```

Test edilen endpointler:

```text
/api/health
/api/gas-sensors?time_step=0
/api/risk/environmental?time_step=0
/api/risk/segments?time_step=0
```

Tüm endpointler HTTP 200 dönmüştür.

---

## 9. Frontend Etkisi

Frontend tarafında mevcut akış bozulmaz.

Yeni alanlar şu an frontend’de ayrıca gösterilmese bile payload içinde hazırdır:

```text
measurements
component_scores
weighted_multi_sensor_risk
sensor_reliability_score
confidence
reliability_status
environmental_risk_reason
```

İleride frontend tarafında şu şekilde kullanılabilir:

```text
Gas Panel:
- CH4
- CO
- O2
- temperature
- humidity
- pressure

Risk Panel:
- methane_risk
- co_risk
- oxygen_risk
- temperature_risk
- humidity_risk
- pressure_risk

Sensor Quality:
- sensor_reliability_score
- confidence
- reliability_status

Risk Explanation:
- environmental_risk_reason
```

---

## 10. Çalıştırma Komutları

Methane CSV path’i local makineye göre verilmelidir:

```bash
export MADENGUARD_METHANE_CSV="$HOME/Desktop/methane-risk-pipeline/data_raw/methane_openml_42701.csv"
```

Pipeline çalıştırma:

```bash
python3 scripts/05_build_gas_timeline.py
```

Backend kontrol:

```bash
cd backend
source .venv/bin/activate
python manage.py check
python manage.py test apps.api
python manage.py runserver
```

API smoke test:

```bash
curl -s "http://localhost:8000/api/health"
curl -s "http://localhost:8000/api/gas-sensors?time_step=0"
curl -s "http://localhost:8000/api/risk/environmental?time_step=0"
curl -s "http://localhost:8000/api/risk/segments?time_step=0"
```

---

## 11. Teknik Sınırlar

Bu geliştirme gerçek saha sensörü entegrasyonu değildir.

Açık sınırlar:

```text
CO, O2, sıcaklık, nem ve basınç değerleri gerçek saha ölçümü değildir.
Bu değerler deterministic demo/simülasyon bağlam değerleridir.
Threshold değerleri saha kalibrasyonlu resmi güvenlik limitleri değildir.
Sistem eğitilmiş ML modeli içermez.
Sistem açıklanabilir, kural/istatistik tabanlı environmental risk scoring mantığı kullanır.
```

Bu nedenle raporda bu modül “eğitilmiş yapay zeka modeli” olarak değil, “açıklanabilir hibrit/kural tabanlı çevresel risk skorlama modülü” olarak ifade edilmelidir.

---

## 12. Gelecek Geliştirmeler

Sonraki aşamalarda yapılabilecek geliştirmeler:

```text
Gerçek CO/O2/sıcaklık/nem/basınç sensör verisi bağlamak
Frontend Gas Panel içinde çoklu sensör ölçümlerini göstermek
Frontend Risk Panel içinde component_scores açıklamasını göstermek
Düşük confidence durumunda UI uyarısı üretmek
Sensörler arası tutarlılık kontrolü eklemek
Opsiyonel Isolation Forest tabanlı anomaly detection denemek
Reliability skorunu backend risk breakdown içinde göstermek
```

---

## 13. Handoff Özeti

Bu geliştirme ile methane processing pipeline, methane-only risk çıktısından çoklu sensör destekli environmental risk çıktısına genişletilmiştir.

Final akış:

```text
Methane CSV
→ methane risk score
→ deterministic environmental context measurements
→ component risk scores
→ weighted_multi_sensor_risk
→ methane floor safety rule
→ environmental_risk
→ backend risk fusion
```

Mevcut metan risk sinyali korunur. Yeni çoklu sensör alanları çevresel risk çıktısını açıklayıcı ve zenginleştirici bağlam olarak kullanılır.

Backend ve frontend tarafında breaking change yoktur.