# MadenGuard AI — Frontend

MadenGuard AI, LiDAR dijital ikizi üzerinde metan/gaz riski, UWB worker konumu, göçük senaryosu ve acil çıkış rotasını birleştiren web tabanlı maden güvenliği karar destek sistemidir. Bu klasör projenin **React + Three.js dashboard frontend'idir**.

Sistem gerçek maden varmış gibi tasarlanmıştır; simülasyon yalnızca gerçek maden donanımı elimizde olmadığı için demo/test amaçlı kullanılır. Frontend, backend'den (veya mock'tan) gelen **küçük işlenmiş veriyi** ekranda gösterir — büyük ham veriyi asla kendisi işlemez.

## Segment ID Standardı

- **Tek gerçek segment kaynağı Haki'nin çıktılarıdır.** Frontend kendi segment haritasını üretmez; finalde tüm `segment_id` değerleri Haki'nin backend'e verdiği kaynaktan gelir, frontend mock mode'da bunu sadece taklit eder.
- **Ortak segment ID formatı**: `S001`, `S002`, `S003`, ... (3 haneli, sıfır dolgulu). Worker ID formatı: `W001`, `W002`, ... Gaz sensörü ID formatı: `GAS-001`, `GAS-002`, ...
- **Ortak anahtar her zaman `segment_id`'dir.** Worker tarafında `current_segment` aynı ID setini kullanır.
- Risk seviyeleri sadece şu dört değeri alır: `low | medium | high | critical`.
- Kapalı/göçük segment `is_blocked: true` alanıyla işaretlenir (görüntüleme amaçlı `status: "open"|"blocked"` alanı da uyumluluk için tutulur).
- Çıkış segmenti `is_exit: true` ile işaretlenir.
- Acil rota dizisi yeni standartta `route_segments` alanındadır; eski `route` alanı geriye dönük uyumluluk için ayrıca tutulur.

## Admin View nedir?

Madeni geneliyle izleyen kontrol paneli. Üstte iki sekme var:

- **Harita Görünümü** (varsayılan) — 2D top-down dijital ikiz haritası. Segmentler risk renkli kalın tünel hatları olarak, gaz sensörleri ve worker/madenci markerları ikon olarak, kapalı/göçük segment kırmızı-siyah kesikli çizgi + X olarak, acil rota yeşil/cyan ok (varsa) veya kırmızı kesikli + "rota yok" uyarısı (yoksa) olarak gösterilir. `MineMapView.jsx` bileşeni — jüri/demo için en okunaklı görünüm.
- **3B LiDAR Görünümü** — gerçek `tunnel_downsampled.ply` geldiğinde kullanılacak 3B sahne (`DigitalTwinViewer.jsx`). PLY yoksa placeholder tünel geometrisi gösterir.

Her iki sekme de aynı segment/risk/worker/gaz/rota verisini kullanır; sağdaki risk paneli, worker paneli, gaz sensör paneli ve acil rota paneli sekmeden bağımsız olarak hep aynı kalır.

## Miner View nedir?

Tek bir madencinin göreceği sade ekran. Seçili madenci için: konumu, bulunduğu segmentin risk seviyesi, yakın gaz alarmı, güvenli çıkış rotası veya "trapped" (mahsur) uyarısı, kısa ve anlaşılır bir aksiyon mesajı. Acil durumda hızlı okunabilmesi öncelik.

Üst başlıkta **Yönetici Görünümü | Madenci Görünümü** toggle'ı ile geçiş yapılır.

## Mock Mode nasıl çalışır?

`.env` dosyası yoksa veya `VITE_API_BASE_URL` boşsa, `src/services/api.js` tüm veriyi `public/mock/*.json` dosyalarından okur. Dashboard backend olmadan tam çalışır.

## API Mode nasıl çalışır?

```bash
cp .env.example .env
# .env içinde VITE_API_BASE_URL=http://localhost:8000 olarak ayarla
npm run dev
```

`VITE_API_BASE_URL` tanımlıysa `api.js` gerçek backend'e gider. **Backend isteği başarısız olursa otomatik olarak ilgili mock dosyaya düşer** (`fetchApiOrMock` helper'ı) — dashboard çökmez, sadece mock veriyle devam eder.

**Backend source of truth'tur.** API mode'da final risk skoru, senaryo sonucu ve acil rota backend'den gelir; frontend bunları yeniden hesaplamaz, sadece gösterir. `src/utils/scenarioUtils.js` içindeki senaryo türetme mantığı **sadece mock mode'da demo amaçlı görsel state** üretir (gerçek backend fusion'ının yerini tutmaz). API isteği eski prototip ID formatında (`S04`, `S4`, `SEG_047`, `W01`) bir yanıt döndürürse, `src/utils/idNormalize.js` bunu otomatik olarak `S004`/`W001` standardına çevirir; mock veriler zaten yeni formatta olduğu için bu katmana mock mode'da hiç girilmez.

## Kurulum

```bash
cd ~/Desktop/MadenGuard_AI/frontend
npm install
npm run dev
```

Tarayıcıda `http://localhost:5173` açılır.

## Backend Bağlantısı

1. Enes'in FastAPI sunucusunu `http://localhost:8000` (veya başka bir adreste) çalıştır.
2. `.env` içine `VITE_API_BASE_URL` değerini yaz.
3. `npm run dev` ile yeniden başlat. Component kodlarında değişiklik gerekmez.

## Beklenen Endpoint'ler

```text
GET /api/health
GET /api/digital-twin/segments
GET /api/digital-twin/graph
GET /api/workers
GET /api/risk/segments
GET /api/gas-sensors
GET /api/scenarios/collapse
GET /api/routes/emergency
```

Tam response şemaları için `FRONTEND_INTEGRATION_CONTRACT.md` dosyasına bakın.

## Haki'nin PLY Dosyası Nereye Konur?

```text
frontend/public/models/tunnel_downsampled.ply
```

Dosya yoksa veya yüklenemezse 3B viewer otomatik olarak placeholder wireframe geometriye düşer, uygulama çökmez.

## Mock JSON Dosyaları Nerede?

```text
public/mock/segments.json
public/mock/segment_metadata.json
public/mock/mine_graph.json
public/mock/workers.json
public/mock/risk_segments.json
public/mock/gas_sensors.json
public/mock/environmental_risk.json
public/mock/geometry_risk.json
public/mock/scenarios.json
public/mock/emergency_route.json
public/mock/system_status.json
```

## Büyük Raw Veri Neden Frontend'e Alınmaz?

10GB/21GB LAS LiDAR dosyaları, büyük metan CSV'leri, UTIL/UCI ham datasetleri tarayıcıda asla açılamaz/render edilemez. Bu dosyalar Haki/Recep/Hüseyin tarafından işlenip küçük JSON/PLY çıktılarına dönüştürülür; frontend yalnızca bu küçük çıktıları veya backend API yanıtlarını okur.

## Klasör Yapısı

```text
frontend/
├── public/
│   ├── models/tunnel_downsampled.ply
│   └── mock/*.json
├── src/
│   ├── components/
│   │   ├── Layout.jsx              # Header + Admin/Miner toggle
│   │   ├── AdminDashboard.jsx      # Admin görünümünü birleştirir, Harita/3B sekme toggle'ı
│   │   ├── MinerDashboard.jsx      # Sade madenci görünümü
│   │   ├── MineMapView.jsx         # 2D top-down dijital ikiz haritası (varsayılan sekme)
│   │   ├── DigitalTwinViewer.jsx   # 3B sahne (3B LiDAR Görünümü sekmesi)
│   │   ├── RiskPanel.jsx
│   │   ├── WorkerPanel.jsx
│   │   ├── GasSensorPanel.jsx
│   │   ├── RouteOverlay.jsx
│   │   ├── ScenarioControls.jsx
│   │   ├── SegmentLegend.jsx
│   │   └── StatusBar.jsx
│   ├── services/api.js
│   ├── utils/
│   ├── styles/
│   ├── App.jsx
│   └── main.jsx
```

## Component Açıklamaları

| Component | Görev |
|---|---|
| `Layout` | Üst başlık, mode pill, Admin/Miner toggle, gövde |
| `AdminDashboard` | Harita/3B sekme toggle'ı + tüm paneller + senaryo butonları + legend + status bar |
| `MinerDashboard` | Seçili madenci için sade durum kartı |
| `MineMapView` | 2D top-down harita: risk renkli segment hatları, gaz/worker ikonları, acil rota |
| `DigitalTwinViewer` | 3B sahne: segmentler, worker, gaz sensörü, acil rota, PLY/placeholder |
| `RiskPanel` | Seçili (veya en kritik) segmentin risk detayları |
| `WorkerPanel` | Worker listesi ve durumları |
| `GasSensorPanel` | Gaz sensörleri ve alarm durumu |
| `RouteOverlay` | Acil rota / trapped bilgisi |
| `ScenarioControls` | 5 senaryo butonu |
| `SegmentLegend` | Risk renk açıklaması |
| `StatusBar` | Mock/API mode, segment/worker/kritik risk sayacı |

## Senaryo Butonları

| Senaryo | Admin View Etkisi | Miner View Etkisi |
|---|---|---|
| Normal Durum | Baseline veri | Normal durum mesajı |
| Metan Artışı | S004 kritik, GAS-001 alarm | W001 için gaz alarmı uyarısı |
| Göçük Senaryosu | S004 kapanır (`is_blocked: true`), acil rota paneli açılır | Trapped/mahsur uyarısı (varsa) |
| İşçi Riskte | W001 riskli işaretlenir | Kişisel risk uyarısı |
| Acil Rota Göster | Mevcut rota gösterilir | Rota veya "no alternative route" |

## Geliştirme Notları

- Frontend ham LAS/LAZ/CSV dosyalarını **asla** doğrudan okumaz.
- API isteği başarısız olursa `api.js` otomatik mock'a düşer, uygulama çökmez.
- PLY yüklenemezse placeholder geometri gösterilir.
- Tüm veri akışı `segment_id` üzerinden birleşir.
- Risk/worker/rota verisi eksikse panel "Veri yok" / "unknown" gösterir.
