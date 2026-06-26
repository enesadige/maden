# Frontend Integration Contract — MadenGuard AI

Bu dosya, frontend'in diğer ekip üyelerinin (Haki, Recep, Hüseyin, Enes) çıktılarıyla nasıl birleşeceğini tanımlar. Format burada değişirse frontend kodu da değişmek zorunda kalır — bu yüzden değişiklik öncesi bu dosyayı güncelleyin ve frontend sorumlusuna (Selim) haber verin.

## 0. Zorunlu Kurallar

> **Frontend ham büyük veri okumaz.** 10GB/21GB LAS LiDAR dosyaları, büyük metan CSV'leri, UTIL/UCI ham datasetleri frontend'e asla kopyalanmaz veya frontend tarafından açılmaz. Frontend yalnızca backend API yanıtlarını veya küçük işlenmiş JSON/PLY dosyalarını okur.

> **Tüm birleşme `segment_id` üzerinden yapılır.** Risk, worker, gaz sensörü, rota ve segment metadata bu ortak anahtarla eşleşir.

> **Tek gerçek segment kaynağı Haki'nin çıktılarıdır.** Frontend kendi segment haritasını üretmez; mock mode'da geçici olarak kendi mock segment setini kullanır, ama finalde `segment_id` değerleri tamamen Haki'nin backend'e verdiği kaynaktan gelir.

> **Ortak segment ID formatı `S001`, `S002`, `S003`, ... şeklindedir** (3 haneli, sıfır dolgulu, örn. `S047`, `S120`). Worker ID formatı `W001`, `W002`, ... şeklindedir. Gaz sensörü ID formatı `GAS-001`, `GAS-002`, ... şeklindedir. Eski prototip formatları (`S01`, `S4`, `SEG_047`, `W01`) artık kullanılmaz.

> **Haki** segment_id üretmek zorunda (örn. `S001`, `S002`, ...) — tüm diğer ekip çıktıları bu ID setini referans alır.

> **Recep** environmental risk verisini segment_id ile vermek zorunda.

> **Hüseyin** worker `current_segment` bilgisini segment_id ile vermek zorunda.

> **Enes** backend bu verileri aşağıdaki API endpoint'lerinden döndürmek zorunda. Frontend sadece API response veya mock JSON okur — başka bir kaynağa bağlanmaz. **Backend source of truth'tur**: final risk skoru, senaryo sonucu ve acil rota backend'de hesaplanır. Frontend risk fusion yapmaz — mock mode'da `scenarioUtils.js` sadece demo senaryosu için görsel state türetir, API mode'da bu hesap tamamen backend'den gelir ve frontend sadece gösterir.

> **Frontend ham LAS/CSV/zip okumaz.** Sadece mock JSON veya backend API response okur. API mode için `VITE_API_BASE_URL=http://localhost:8000` kullanılır.

## 1. Frontend Hangi Dosyaları / API'leri Bekliyor?

| Amaç | Mock dosya (şu an) | Gerçek kaynak (ileride) |
|---|---|---|
| Segment listesi | `public/mock/segments.json` | `GET /api/digital-twin/segments` |
| Segment metadata | `public/mock/segment_metadata.json` | `segment_metadata.json` (mock-only, dedicated endpoint yok) |
| Bağlantı grafiği | `public/mock/mine_graph.json` | `GET /api/digital-twin/graph` |
| Worker konumları | `public/mock/workers.json` | `GET /api/workers` |
| Segment riski (birleşik) | `public/mock/risk_segments.json` | `GET /api/risk/segments` |
| Gaz sensörleri | `public/mock/gas_sensors.json` | `GET /api/gas-sensors` |
| Gaz/metan riski (detay) | `public/mock/environmental_risk.json` | mock-only, `risk_segments` fusion'ına dahil |
| Geometri riski (detay) | `public/mock/geometry_risk.json` | mock-only, `risk_segments` fusion'ına dahil |
| Senaryo listesi | `public/mock/scenarios.json` | sabit, frontend'de tanımlı kalabilir |
| Acil rota | `public/mock/emergency_route.json` | `GET /api/scenarios/collapse`, `GET /api/routes/emergency` |
| Sistem durumu | `public/mock/system_status.json` | mock-only, `GET /api/health` ile birlikte kullanılır |
| 3B model | yok → placeholder gösterilir | `public/models/tunnel_downsampled.ply` |

## 2. Haki — LiDAR / Geometri Formatı

```json
{
  "segment_id": "S004",
  "name": "Riskli Metan Bölgesi",
  "type": "risk_zone",
  "center": [18, 2, 0],
  "connected_segments": ["S003", "S005"],
  "bounds": {
    "min": [16, 1, -1],
    "max": [20, 3, 2]
  },
  "length_m": 18.7,
  "width_m": 3.2,
  "height_m": 2.6,
  "is_exit": false,
  "is_blocked": false,
  "status": "open"
}
```

- `segment_id`: `S001`, `S002`, ... formatında (3 haneli, sıfır dolgulu). Tek gerçek kaynak Haki'nin çıktısıdır.
- `center`: dünya koordinatlarında [x, y, z], metre cinsinden.
- `is_blocked`: `true`/`false` — segment kapalı/göçük mü. `status` alanı (`"open"`/`"blocked"`) görüntüleme amaçlı geriye dönük uyumluluk için ayrıca tutulur.
- `is_exit`: `true`/`false` — çıkış segmenti mi.
- `bounds`/`width_m`/`height_m`: opsiyonel, varsa frontend kullanır, yoksa "Veri yok" göstermez, sadece o alanı atlar.
- `tunnel_downsampled.ply` → `frontend/public/models/tunnel_downsampled.ply`. Yoksa/bozuksa placeholder gösterilir, hata vermez.
- `mine_graph.json`: `{"nodes": [{"segment_id": "S001", "is_exit": true}], "edges": [{"from": "S001", "to": "S002", "weight": 6}]}`.

## 3. Recep — Gaz/Metan Riski Formatı

```json
{ "segment_id": "S004", "methane_ppm": 95.6, "gas_risk_score": 92, "anomaly_detected": true }
```

Bu, Enes'in fusion backend'inde `risk_segments.json`'daki `active_reasons` içine eklenir (örn. `"metan anomalisi tespit edildi"`). Ayrıca gerçek gaz sensörü konumları varsa `gas_sensors` formatına da (bkz. madde 5) dönüştürülmeli; sensor ID'ler `GAS-001`, `GAS-002`, ... formatındadır.

## 4. Hüseyin — Worker / UWB Formatı

```json
{
  "worker_id": "W001",
  "time_step": 12,
  "position": [18, 2.6, 0.4],
  "current_segment": "S004",
  "position_reliability": 0.82,
  "status": "safe",
  "motion_status": "moving"
}
```

- `worker_id`: `W001`, `W002`, ... formatında (3 haneli, sıfır dolgulu).
- `position`: 3B sahne koordinatı, segment merkeziyle uyumlu olmalı.
- `status`: `"at_risk"` veya `"safe"`.
- `role`: Miner View'da hangi worker'ların seçilebileceğini belirler (şu an `"miner"`); mock veride mevcuttur, API şemasında zorunlu değil.
- `position_reliability`: 0–1 arası. 0.5'in altındaysa frontend otomatik uyarı gösterir.
- `time_step`: opsiyonel, simülasyon/demo zaman adımı.
- `worker_exposure_risk.json` çıktısı `risk_segments.json` fusion'ına girdi olarak kullanılır.

## 5. Enes — Backend Endpoint Beklentileri

```text
GET /api/health                  → { status, mode }
GET /api/digital-twin/segments   → segment array
GET /api/digital-twin/graph      → mine_graph şeması
GET /api/workers                 → worker array
GET /api/risk/segments           → risk array
GET /api/gas-sensors             → gas sensor array
GET /api/scenarios/collapse      → emergency route objesi
GET /api/routes/emergency        → emergency route objesi (alternatif rota sorgusu)
```

CORS, frontend'in `localhost:5173`'ten erişebilmesi için backend'de açık olmalı.

### `GET /api/digital-twin/segments`

```json
[
  {
    "segment_id": "S004",
    "name": "Riskli Metan Bölgesi",
    "center": [18, 2, 0],
    "connected_segments": ["S003", "S005"],
    "is_exit": false,
    "is_blocked": false,
    "status": "open"
  }
]
```

### `GET /api/workers`

```json
[
  {
    "worker_id": "W001",
    "current_segment": "S004",
    "position": [18, 2.6, 0.4],
    "status": "at_risk"
  }
]
```

### `GET /api/risk/segments`

```json
[
  {
    "segment_id": "S004",
    "risk_score": 87,
    "risk_level": "critical",
    "active_reasons": ["metan anomalisi tespit edildi"],
    "recommended_action": "Rota varsa tahliye ol; yoksa kurtarma talimatı bekle."
  }
]
```

`risk_level` değerleri sadece şu dördü olabilir: `low | medium | high | critical`.

### `GET /api/gas-sensors`

```json
[
  {
    "sensor_id": "GAS-001",
    "segment_id": "S004",
    "position": [18, 1.5, 0.8],
    "gas_type": "methane",
    "methane_value": 4.8,
    "anomaly_score": 0.91,
    "risk_score": 91,
    "risk_level": "critical",
    "status": "alarm"
  }
]
```

`status` değerleri: `"normal" | "alarm"`.

### `GET /api/routes/emergency` / `GET /api/scenarios/collapse`

```json
{
  "scenario_id": "collapse_s004",
  "event_type": "collapse",
  "blocked_segment": "S004",
  "affected_workers": ["W001"],
  "exit_segment": "S001",
  "exit_reachable": false,
  "alternative_route_available": false,
  "route_segments": ["S004", "S003", "S002", "S001"],
  "emergency_status": "CRITICAL_WORKER_TRAPPED",
  "message": "İşçi W001 kapalı segment bölgesinde. Alternatif rota bulunamadı."
}
```

`route_segments` yeni standart alandır. Eski `route` alanı geriye dönük uyumluluk için frontend tarafında hâlâ okunur (varsa `route_segments` öncelikli kullanılır), ama yeni entegrasyonlarda `route_segments` tercih edilmelidir.

## 6. Mock'tan Gerçek API'ye Geçiş

Tek değişiklik: `.env` dosyasında `VITE_API_BASE_URL` tanımlamak.

```bash
cp .env.example .env
# VITE_API_BASE_URL=http://localhost:8000
```

`src/services/api.js` her fonksiyonda bu değişkene bakar; tanımlıysa gerçek endpoint'e gider. **API isteği başarısız olursa (network hatası, 4xx/5xx) otomatik olarak ilgili mock dosyaya düşer** — frontend hiçbir zaman tamamen çökmez. Component kodlarında değişiklik gerekmez.

`getSegmentMetadata`, `getEnvironmentalRisk`, `getGeometryRisk`, `getSystemStatus` şu an için her zaman mock dosyaya gider çünkü Enes'in endpoint listesinde bunlara özel bir endpoint yok — bu veriler backend'de `risk_segments`/`health` fusion'ına dahil edilmiş olarak gelir. Enes ayrı endpoint açarsa bu fonksiyonlar da `fetchApiOrMock` mantığına eklenmelidir.

## 7. PLY Dosyası Nereye Konacak?

```text
frontend/public/models/tunnel_downsampled.ply
```

Sadece bu dosya. Büyük (10GB/21GB) ham LAS dosyaları **hiçbir zaman** frontend klasörüne kopyalanmamalı.

## 8. Segment ID Tutarlılığı

Haki'nin `map_segments.json`'ı, Recep'in `environmental_risk.json`'ı, Hüseyin'in `worker_positions_demo.json`'ı, gaz sensör verisi ve Enes'in `risk_segments.json`'ı **aynı `segment_id` setini** kullanmalı — ortak standart `S001`, `S002`, `S003`, ... formatıdır (3 haneli, sıfır dolgulu; örn. gerçek madende `S047`, `S120`). ID'ler uyuşmazsa frontend panelinde "Veri yok" görünür, uygulama çökmez ama bilgi eksik kalır.

Backend gelişim sürecinde eski prototip formatında (`S04`, `S4`, `SEG_047`, `W01`) bir yanıt dönerse frontend çökmez: `src/utils/idNormalize.js` içindeki `normalizeApiPayload` API mode'da gelen tüm yanıtları otomatik olarak yeni `S001`/`W001`/`GAS-001` standardına çevirir. Bu sadece geçiş dönemi için bir güvenlik ağıdır — Haki/Hüseyin/Enes'in nihai çıktısının doğrudan yeni formatta gelmesi beklenir, mock veriler zaten her zaman yeni formattadır.

## 9. Admin View / Miner View Ayrımı

Frontend tek React uygulaması, iki görünüm modu sunar (`Layout.jsx` üstünde toggle: Yönetici Görünümü / Madenci Görünümü). Backend tarafında bu ayrım için ek bir endpoint gerekmiyor — her iki görünüm de aynı veriyi (`segments`, `risks`, `workers`, `gasSensors`, `emergencyRoute`) farklı şekilde sunar. Madenci Görünümü, `workers` listesinden seçilen tek işçinin bakış açısını gösterir.

Yönetici Görünümü kendi içinde de iki sekmeye ayrılır (`AdminDashboard.jsx` içindeki local state, backend'i ilgilendirmez): **Harita Görünümü** (varsayılan, `MineMapView.jsx` — 2D top-down) ve **3B LiDAR Görünümü** (`DigitalTwinViewer.jsx`). İkisi de aynı `segments`/`risks`/`workers`/`gasSensors`/`emergencyRoute` prop'larını alır; hangi sekmenin seçili olduğu backend'e hiçbir şekilde bildirilmez ve API şemasını etkilemez.
