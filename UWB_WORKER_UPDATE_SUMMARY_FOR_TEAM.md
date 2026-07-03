# Ekip Icin UWB Worker Tracking Guncelleme Ozeti

## 1. Huseyin / UWB Worker Tracking Tarafinda Ne Degisti?

Bu guncelleme, mevcut MVP pipeline icin UWB worker-side tarafini tamamlayan bir genisletmedir. Worker tracking akisi artik config ile degistirilebilir worker sayisini destekler, varsayilan olarak 10 worker uretir, zenginlestirilmis worker timeline ciktilari olusturur ve rule-based UWB behavior anomaly analitigi ekler.

Worker uretimi UWB config/pipeline katmaninda tutuldu. Django worker uretmez; yalnizca uretilmis JSON ciktilarini okur.

Ana degisiklikler:

- `backend/uwb_processing/config_loader.py` icinde dinamik worker count destegi eklendi.
- `backend/uwb_processing/uwb_config.example.json` varsayilan olarak 10 worker olacak sekilde guncellendi.
- Yeni rule-based behavior anomaly builder eklendi: `backend/uwb_processing/behavior_anomaly_builder.py`.
- `backend/data_processed/sample/workers/` altina yeni anomaly ciktilari eklendi.
- `run_pipeline.py` icine anomaly builder entegrasyonu yapildi; dry-run/write planina ve manifest metadata alanlarina anomaly ciktilari eklendi.
- `validate_outputs.py` icine anomaly event ve anomaly summary validation eklendi.
- API testleri 3 worker varsayimina bagli kalmayacak sekilde, generated worker fixture'larini dinamik okuyacak hale getirildi.
- README ve UWB raporu mevcut UWB worker MVP davranisi ve sinirlariyla guncellendi.

## 2. Dinamik Worker Count Davranisi

Varsayilan worker count artik 10.

Worker sayisi config-driven calisir. Aktif worker listesi UWB config loader tarafindan belirlenir; Django kodu worker uretmez.

### Explicit Workers Mode

Eger `config["workers"]` mevcutsa ve bos degilse, bu liste aynen source of truth olarak kullanilir.

Bu modda `worker_defaults.default_worker_count` dikkate alinmaz. Ornegin explicit worker listesi sadece `WORKER_01` ve `WORKER_02` iceriyorsa, `default_worker_count` 10 veya 20 olsa bile aktif worker count 2 olur.

### Auto-Generated Workers Mode

Eger `config["workers"]` eksikse veya bossa ve:

```json
"worker_defaults": {
  "allow_auto_generate_workers": true
}
```

ise `config_loader.py` worker listesini su alandan uretir:

```json
"worker_defaults": {
  "default_worker_count": 10
}
```

Uretim ornekleri:

- `default_worker_count = 5` ise `WORKER_01` - `WORKER_05`, `TAG_001` - `TAG_005` uretilir.
- `default_worker_count = 10` ise `WORKER_01` - `WORKER_10`, `TAG_001` - `TAG_010` uretilir.
- `default_worker_count = 20` ise `WORKER_01` - `WORKER_20`, `TAG_001` - `TAG_020` uretilir.

Loader her zaman sunlari dondurur:

```python
config["workers"] = explicit_or_generated_workers
config["worker_count"] = len(config["workers"])
```

### Django Davranisi

Django worker uretmez.

Django yalnizca uretilmis JSON ciktilarini okur:

- `backend/data_processed/sample/workers/workers.json`
- `backend/data_processed/sample/workers/worker_segment_timeline.json`

API, bu dosyalarda hangi worker'lar varsa onlari dondurur.

## 3. Worker Movement Dogrulamasi

Mevcut sample data ile UWB worker ciktilari dogrulandi.

Final sayilar:

- `workers = 10`
- `unique_timeline_workers = 10`
- `timeline_records = 1308`
- 10 worker'in tamami timeline boyunca hareket etti

Movement dogrulamasi `worker_segment_timeline.json` uzerinden yapildi. Her worker birden fazla unique segmentte goruldu; bu da worker'larin statik olmadigini, timeline boyunca hareket ettigini dogruluyor.

API non-zero `time_step` degerleriyle historical worker state kontrolunu destekler. Mevcut latest snapshot davranisi korunmustur:

- `/api/workers` latest worker snapshot dondurur.
- `/api/workers?time_step=0` compatibility icin latest worker snapshot dondurur.
- Non-zero `time_step` degerleri historical worker state incelemek icin kullanilir.

## 4. Behavior Anomaly Sistemi

Yeni rule-based UWB behavior anomaly sistemi eklendi.

Yeni builder:

- `backend/uwb_processing/behavior_anomaly_builder.py`

Yeni generated output dosyalari:

- `backend/data_processed/sample/workers/behavior_anomaly_events.json`
- `backend/data_processed/sample/workers/behavior_anomaly_summary.json`

Desteklenen public `event_type` degerleri:

- `stationary_too_long`
- `low_position_reliability`
- `tracking_lost_in_risky_segment`
- `entered_high_risk_segment`
- `near_blocked_segment`
- `route_deviation`

Final anomaly sayisi:

- `anomaly_events = 1640`

Event type bazinda sayilar:

- `entered_high_risk_segment: 969`
- `low_position_reliability: 205`
- `tracking_lost_in_risky_segment: 205`
- `route_deviation: 261`
- `stationary_too_long: 0`
- `near_blocked_segment: 0`

Bu event'ler yalnizca rule-based MVP analytics sinyalleridir. Certified safety decision degildir, trapped karari degildir ve emergency routing ciktisi degildir.

## 5. Degisen Dosyalar

Code/config/test/docs:

- `backend/uwb_processing/config_loader.py`
- `backend/uwb_processing/uwb_config.example.json`
- `backend/uwb_processing/behavior_anomaly_builder.py`
- `backend/uwb_processing/run_pipeline.py`
- `backend/uwb_processing/validate_outputs.py`
- `backend/apps/api/tests.py`
- `README_UWB_CORE.md`
- `UWB_WORKER_TRACKING_REPORT.md`

Generated worker/UWB ciktilari:

- `backend/data_processed/sample/workers/workers.json`
- `backend/data_processed/sample/workers/worker_positions_clean.csv`
- `backend/data_processed/sample/workers/worker_positions_demo.json`
- `backend/data_processed/sample/workers/worker_segment_timeline.json`
- `backend/data_processed/sample/workers/worker_segment_timeline_summary.json`
- `backend/data_processed/sample/workers/uwb_extraction_summary.json`
- `backend/data_processed/sample/workers/behavior_anomaly_events.json`
- `backend/data_processed/sample/workers/behavior_anomaly_summary.json`
- `backend/data_processed/sample/uwb/uwb_pipeline_manifest.json`
- `backend/data_processed/sample/uwb/uwb_validation_summary.json`

## 6. Dokunulmayan Dosyalar ve Alanlar

Bu guncellemede asagidaki alanlara dokunulmadi:

- `backend/data_processed/sample/haki_lidar/`
- `backend/data_processed/sample/sensors/`
- `backend/apps/sensors/`
- `backend/apps/risk/`
- `backend/apps/routing/`
- `frontend/`
- `dashboards/`
- `pipelines/`

## 7. Enes Backend / Routing / Risk Icin Dikkat Notlari

- Worker count backend logic icinde hardcode edilmemeli.
- Django yalnizca generated JSON ciktilarini okumali.
- Worker uretimi UWB config/pipeline katmaninda kalmali.
- `/api/workers` ve `/api/workers?time_step=0` latest worker snapshot dondurur.
- Non-zero `time_step` degerleri historical worker state icin kullanilir.
- Behavior anomaly event'leri rule-based MVP analytics sinyalleridir; trapped karari degildir.
- Trapped karari backend route/simulation katmaninda kalmalidir.
- `route_deviation` graph-continuity analytics sinyalidir; emergency routing degildir.
- UWB ciktilari downstream sistemler icin worker position, reliability, exposure ve behavior anomaly sinyalleri saglar.

## 8. Selim Frontend Icin Dikkat Notlari

- Frontend 3 worker varsayimi yapmamali.
- Frontend API'den donen tum worker'lari render etmeli.
- Timeline slider historical view icin non-zero `time_step` degerlerini kullanmali.
- Anomaly event'leri warning olarak gorsellestirilebilir.
- Anomaly event'leri definite trapped status olarak gosterilmemeli.
- 3D overlay worker position, reliability ve anomaly sinyallerini kullanabilir.
- Pointcloud alignment, UWB worker/anomaly output contract'tan ayri bir konudur.

## 9. Validation Sonuclari

Final validation basarili tamamlandi:

- `python backend\uwb_processing\config_loader.py`: self-check passed
- `python backend\uwb_processing\behavior_anomaly_builder.py`: self-check passed
- `python backend\uwb_processing\run_pipeline.py --dry-run`: passed
- `python backend\uwb_processing\validate_outputs.py`: `ok=true`, `error_count=0`
- `python backend\manage.py test apps.api`: passed, 21 tests OK
- `python backend\manage.py check`: passed

Final dogrulanmis sayilar:

- `workers = 10`
- `unique_timeline_workers = 10`
- `timeline_records = 1308`
- `anomaly_events = 1640`

## 10. Limitasyonlar ve Ownership Sinirlari

Behavior anomaly ciktilari rule-based MVP analytics sinyalleridir. Warning ve inceleme yardimcisi olarak degerlendirilmelidir; certified safety decision degildir.

`route_deviation` emergency routing degildir.

Worker trapped status UWB modulunde nihai olarak uretilmez. UWB modulu worker konumu, guvenilirlik, exposure ve davranis anomaly sinyalleri uretir. Final trapped karari backend route/simulation katmaninda verilmelidir.

LOS/NLOS classifier implemente edilmemistir. Mevcut anchor visibility heuristic'tir. Gercek LOS/NLOS classifier icin labeled data gerekir.

MVP'de UTIL pose verisi worker hareket proxy'si olarak kullanilir. Gercek UWB TDoA solver deneysel altyapidir; saha kalibrasyonu ve olcum birimi dogrulamasi olmadan gercek konum dogrulugu iddiasi tasimaz.
