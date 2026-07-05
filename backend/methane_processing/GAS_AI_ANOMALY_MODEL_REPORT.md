# Gas AI Anomaly Model Raporu

## 1. Amaç

Bu rapor, Recep tarafındaki gaz/metan/çevresel risk pipeline için eklenen açıklanabilir AI/ML anomaly modelini açıklar.

Model, gerçek etiketli bir classification modeli değildir. Elimizde normal/anormal etiketli saha verisi olmadığı için dependency-free, unsupervised, robust MAD tabanlı anomaly detection yaklaşımı kullanılmıştır.

## 2. Kullanılan Veri

- Input dosyası: `backend/data_processed/sample/sensors/gas_sensors.json`
- İşlenen kayıt sayısı: `270`
- Sensör sayısı: `3`
- Segment sayısı: `3`

Kullanılan input mevcut pipeline tarafından üretilen `gas_sensors.json` dosyasıdır. Raw methane CSV doğrudan bu modelde tekrar okunmamıştır; methane CSV önceki pipeline tarafından işlenmiş ve bu modele processed timeline olarak verilmiştir.

## 3. Önemli Veri Sınırı

CO, O2, sıcaklık, nem ve basınç değerleri gerçek saha sensörü ölçümü değildir. Bu değerler mevcut methane risk sinyali, anomaly score, sensor_id ve time_step üzerinden deterministic demo/simülasyon bağlamı olarak üretilmiştir.

Bu nedenle model gerçek çoklu gaz saha modeli olarak değil, mevcut methane tabanlı pipeline üzerinde çalışan açıklanabilir environmental anomaly sinyali olarak değerlendirilmelidir.

## 4. Model

- Model adı: `robust_mad_gas_anomaly_v1`
- Model versiyonu: `2026-07-05`
- Model tipi: `unsupervised robust MAD anomaly detection`
- Dependency: Ek Python paketi gerektirmez.

Model her feature için median ve MAD değerlerini öğrenir. Her sensor-time kaydı için robust z-score hesaplanır. En sapkın feature'lar ve mevcut risk bağlamı birlikte `gas_ai_anomaly_score` skoruna dönüştürülür.

## 5. Kullanılan Feature'lar

- `methane_value`
- `methane_risk_score`
- `anomaly_score`
- `environmental_risk`
- `weighted_multi_sensor_risk`
- `measurements.methane_ppm`
- `measurements.co_ppm`
- `measurements.oxygen_percent`
- `measurements.temperature_c`
- `measurements.humidity_percent`
- `measurements.pressure_hpa`
- `component_scores.methane_risk`
- `component_scores.co_risk`
- `component_scores.oxygen_risk`
- `component_scores.temperature_risk`
- `component_scores.humidity_risk`
- `component_scores.pressure_risk`
- `sensor_reliability_score`
- `confidence`

## 6. Skorlama

Model iki ana sinyali birleştirir:

```text
gas_ai_anomaly_score = 0.65 * robust_anomaly_score + 0.35 * risk_context_score
```

- `robust_anomaly_score`: Feature'ların median/MAD baseline'a göre sapması.
- `risk_context_score`: environmental_risk, methane_risk_score, weighted_multi_sensor_risk ve anomaly_score bağlamı.

Risk seviyeleri:

```text
0-29.999   -> low
30-59.999  -> medium
60-79.999  -> high
80-100     -> critical
```

## 7. Sonuç Özeti

- Level counts: `{'critical': 25, 'high': 38, 'low': 164, 'medium': 43}`
- Validation error count: `0`

## 8. En Anormal 10 Kayıt

- time_step=`3`, sensor_id=`GAS_SENSOR_01`, segment_id=`S006`, score=`100.0`, level=`critical`, reasons=`['confidence normal baseline altında', 'rolling anomaly_score normal baseline üstünde', 'component oxygen_risk normal baseline üstünde', 'component co_risk normal baseline üstünde', 'weighted_multi_sensor_risk normal baseline üstünde', 'co_ppm normal baseline üstünde', 'rolling anomaly_score çok yüksek', 'CO sinyali normal üstü risk gösteriyor']`
- time_step=`4`, sensor_id=`GAS_SENSOR_03`, segment_id=`S035`, score=`100.0`, level=`critical`, reasons=`['confidence normal baseline altında', 'rolling anomaly_score normal baseline üstünde', 'component oxygen_risk normal baseline üstünde', 'component co_risk normal baseline üstünde', 'rolling anomaly_score çok yüksek', 'sensor confidence düşük veya doğrulama gerektiriyor']`
- time_step=`29`, sensor_id=`GAS_SENSOR_02`, segment_id=`S034`, score=`100.0`, level=`critical`, reasons=`['confidence normal baseline altında', 'rolling anomaly_score normal baseline üstünde', 'component oxygen_risk normal baseline üstünde', 'component co_risk normal baseline üstünde', 'rolling anomaly_score çok yüksek', 'sensor confidence düşük veya doğrulama gerektiriyor']`
- time_step=`33`, sensor_id=`GAS_SENSOR_01`, segment_id=`S006`, score=`100.0`, level=`critical`, reasons=`['confidence normal baseline altında', 'rolling anomaly_score normal baseline üstünde', 'component oxygen_risk normal baseline üstünde', 'component co_risk normal baseline üstünde', 'co_ppm normal baseline üstünde', 'weighted_multi_sensor_risk normal baseline üstünde', 'rolling anomaly_score çok yüksek', 'CO sinyali normal üstü risk gösteriyor']`
- time_step=`46`, sensor_id=`GAS_SENSOR_03`, segment_id=`S035`, score=`100.0`, level=`critical`, reasons=`['confidence normal baseline altında', 'component oxygen_risk normal baseline üstünde', 'rolling anomaly_score normal baseline üstünde', 'component co_risk normal baseline üstünde', 'component pressure_risk normal baseline üstünde', 'component temperature_risk normal baseline üstünde', 'methane_risk_score yüksek seviyede', 'environmental_risk yüksek seviyede']`
- time_step=`72`, sensor_id=`GAS_SENSOR_01`, segment_id=`S006`, score=`100.0`, level=`critical`, reasons=`['confidence normal baseline altında', 'rolling anomaly_score normal baseline üstünde', 'component oxygen_risk normal baseline üstünde', 'component co_risk normal baseline üstünde', 'weighted_multi_sensor_risk normal baseline üstünde', 'co_ppm normal baseline üstünde', 'rolling anomaly_score çok yüksek', 'CO sinyali normal üstü risk gösteriyor']`
- time_step=`86`, sensor_id=`GAS_SENSOR_02`, segment_id=`S034`, score=`100.0`, level=`critical`, reasons=`['component humidity_risk normal baseline üstünde', 'confidence normal baseline altında', 'component oxygen_risk normal baseline üstünde', 'rolling anomaly_score normal baseline üstünde', 'component co_risk normal baseline üstünde', 'component pressure_risk normal baseline üstünde', 'methane_risk_score kritik seviyede', 'environmental_risk kritik seviyede']`
- time_step=`72`, sensor_id=`GAS_SENSOR_03`, segment_id=`S035`, score=`99.543`, level=`critical`, reasons=`['component humidity_risk normal baseline üstünde', 'confidence normal baseline altında', 'component oxygen_risk normal baseline üstünde', 'rolling anomaly_score normal baseline üstünde', 'component co_risk normal baseline üstünde', 'component pressure_risk normal baseline üstünde', 'methane_risk_score kritik seviyede', 'environmental_risk kritik seviyede']`
- time_step=`39`, sensor_id=`GAS_SENSOR_02`, segment_id=`S034`, score=`93.493`, level=`critical`, reasons=`['component humidity_risk normal baseline üstünde', 'component oxygen_risk normal baseline üstünde', 'component co_risk normal baseline üstünde', 'weighted_multi_sensor_risk normal baseline üstünde', 'rolling anomaly_score normal baseline üstünde', 'component temperature_risk normal baseline üstünde', 'methane_risk_score kritik seviyede', 'environmental_risk kritik seviyede']`
- time_step=`40`, sensor_id=`GAS_SENSOR_02`, segment_id=`S034`, score=`93.493`, level=`critical`, reasons=`['component humidity_risk normal baseline üstünde', 'component oxygen_risk normal baseline üstünde', 'component co_risk normal baseline üstünde', 'weighted_multi_sensor_risk normal baseline üstünde', 'rolling anomaly_score normal baseline üstünde', 'component temperature_risk normal baseline üstünde', 'methane_risk_score kritik seviyede', 'environmental_risk kritik seviyede']`

## 9. Output Dosyaları

- `backend/data_processed/sample/risk/environmental_ai_anomaly.json`
- `backend/data_processed/sample/risk/environmental_ai_anomaly_model_params.json`
- `backend/methane_processing/GAS_AI_ANOMALY_MODEL_REPORT.md`

## 10. MVP Kullanılabilirlik

Bu model MVP içinde güvenli şekilde ek AI anomaly sinyali olarak kullanılabilir. Final risk skorunu doğrudan ezmemeli; backend tarafında `ai_insights` veya `risk_breakdown.environmental_ai` alanlarında açıklayıcı sinyal olarak gösterilmelidir.

Modelin anlamı: Bu kayıt, kendi processed gaz timeline baseline'ına göre normal mi, yoksa çok değişkenli çevresel profil açısından sapkın mı?

## 11. Sınırlar

- Etiketli supervised model değildir.
- Gerçek CO/O2/sıcaklık/nem/basınç saha datası kullanılmamıştır.
- Model çıktısı trapped/mahsuriyet kararı değildir.
- Model çıktısı nihai güvenlik kararı değildir.
- Output sadece açıklanabilir AI anomaly sinyali olarak kullanılmalıdır.
