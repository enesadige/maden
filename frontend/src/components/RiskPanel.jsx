import { getRiskColor, getRiskLabel } from '../utils/riskColors'
import { findMostCriticalRisk } from '../utils/scenarioUtils'

function fallbackRecommendedAction(riskLevel, isBlocked) {
  if (isBlocked) return 'Segmenti tahliye et, acil rota planını uygula.'
  const actions = {
    critical: 'Bölgeyi derhal tahliye et, gaz ölçümünü doğrula.',
    high: 'İşçi erişimini sınırla, izlemeyi artır.',
    medium: 'Standart prosedürle izlemeye devam et.',
    low: 'Ek aksiyon gerekmiyor.'
  }
  return actions[riskLevel] || 'Risk verisi yetersiz, manuel kontrol gerekir.'
}

export default function RiskPanel({ segments, risks, workers, gasSensors, environmentalRisk, geometryRisk, selectedSegmentId }) {
  const risk = selectedSegmentId
    ? risks.find((r) => r.segment_id === selectedSegmentId)
    : findMostCriticalRisk(risks)

  if (!risk) {
    return (
      <div className="panel">
        <h2 className="panel-title">Risk Paneli</h2>
        <p className="panel-empty">Risk verisi bulunamadı.</p>
      </div>
    )
  }

  const segment = segments.find((s) => s.segment_id === risk.segment_id)
  // Gaz sensörü varsa (senaryoya göre güncellenir) onu kullan; yoksa statik
  // environmental_risk verisine düş, böylece Gaz Paneli ile çelişmez.
  const gasSensor = gasSensors?.find((s) => s.segment_id === risk.segment_id)
  const envRisk = environmentalRisk?.find((e) => e.segment_id === risk.segment_id)
  const geoRisk = geometryRisk?.find((g) => g.segment_id === risk.segment_id)
  const workersHere = workers.filter((w) => w.current_segment === risk.segment_id)
  const color = getRiskColor(risk.risk_level, segment?.is_blocked)

  return (
    <div className="panel">
      <h2 className="panel-title">Risk Paneli</h2>
      {!selectedSegmentId && <p className="panel-hint">Segment seçilmedi — en kritik segment gösteriliyor.</p>}

      <div className="panel-row">
        <span className="panel-label">Segment</span>
        <span>{segment?.name || risk.segment_id} ({risk.segment_id})</span>
      </div>

      <div className="panel-row">
        <span className="panel-label">Risk Skoru</span>
        <span>{risk.risk_score}</span>
      </div>

      <div className="panel-row">
        <span className="panel-label">Risk Seviyesi</span>
        <span className="risk-badge" style={{ backgroundColor: color }}>
          {getRiskLabel(segment?.is_blocked ? 'blocked' : risk.risk_level)}
        </span>
      </div>

      <div className="panel-row panel-row--block">
        <span className="panel-label">Aktif Risk Nedenleri</span>
        <ul>
          {risk.active_reasons.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      </div>

      <div className="panel-row">
        <span className="panel-label">Gaz/Metan Riski</span>
        <span className={gasSensor?.status === 'alarm' ? 'text-danger' : undefined}>
          {gasSensor
            ? `${gasSensor.methane_value}% (skor ${gasSensor.risk_score})${gasSensor.status === 'alarm' ? ' — ALARM' : ''}`
            : (envRisk ? `${envRisk.methane_ppm} ppm (skor ${envRisk.gas_risk_score})` : 'Veri yok')}
        </span>
      </div>

      <div className="panel-row">
        <span className="panel-label">Geometri Riski</span>
        <span>{geoRisk ? `Skor ${geoRisk.structural_risk_score} — ${geoRisk.notes}` : 'Veri yok'}</span>
      </div>

      <div className="panel-row">
        <span className="panel-label">İşçi Var mı?</span>
        <span>{workersHere.length > 0 ? `${workersHere.length} işçi (${workersHere.map((w) => w.worker_id).join(', ')})` : 'Yok'}</span>
      </div>

      <div className="panel-row panel-row--block">
        <span className="panel-label">Önerilen Aksiyon</span>
        <span>{risk.recommended_action || fallbackRecommendedAction(risk.risk_level, segment?.is_blocked)}</span>
      </div>
    </div>
  )
}
