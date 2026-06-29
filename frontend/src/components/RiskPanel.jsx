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
  
  // Extract final risk score and levels
  const finalScore = risk.final_risk_score !== undefined ? risk.final_risk_score : risk.risk_score
  const riskLevel = risk.risk_level || 'low'
  const color = getRiskColor(riskLevel, segment?.is_blocked)

  // Extract risk breakdown details (handles flat keys and nested objects)
  const breakdown = risk.risk_breakdown || {}
  const geomRiskVal = risk.geometry_risk !== undefined ? risk.geometry_risk : breakdown.geometry
  const envRiskVal = risk.environmental_risk !== undefined ? risk.environmental_risk : breakdown.environmental
  const workerRiskVal = risk.worker_exposure_risk !== undefined ? risk.worker_exposure_risk : breakdown.worker
  const trackingRiskVal = risk.tracking_risk_score !== undefined ? risk.tracking_risk_score : (risk.tracking_risk !== undefined ? risk.tracking_risk : breakdown.tracking)

  const gasSensor = gasSensors?.find((s) => s.segment_id === risk.segment_id)
  const envRisk = environmentalRisk?.find((e) => e.segment_id === risk.segment_id)
  const geoRisk = geometryRisk?.find((g) => g.segment_id === risk.segment_id)
  const workersHere = workers.filter((w) => w.current_segment === risk.segment_id)

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
        <span>{finalScore}</span>
      </div>

      <div className="panel-row">
        <span className="panel-label">Risk Seviyesi</span>
        <span className="risk-badge" style={{ backgroundColor: color }}>
          {getRiskLabel(segment?.is_blocked ? 'blocked' : riskLevel)}
        </span>
      </div>

      {risk.active_reasons && risk.active_reasons.length > 0 && (
        <div className="panel-row panel-row--block">
          <span className="panel-label">Aktif Risk Nedenleri</span>
          <ul>
            {risk.active_reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        </div>
      )}

      {/* Detailed Risk Breakdown Section */}
      <div className="panel-row panel-row--block">
        <span className="panel-label">Risk Kırılım Detayı</span>
        <div style={{ fontSize: '12px', paddingLeft: '8px', marginTop: '4px', lineHeight: '1.6' }}>
          {geomRiskVal !== undefined && geomRiskVal !== null && (
            <div>• Geometri Yapısal Riski: <strong>{geomRiskVal}</strong></div>
          )}
          {envRiskVal !== undefined && envRiskVal !== null && (
            <div>• Çevre/Metan Gaz Riski: <strong>{envRiskVal}</strong></div>
          )}
          {workerRiskVal !== undefined && workerRiskVal !== null && (
            <div>• İşçi Yoğunluk Riski: <strong>{workerRiskVal}</strong></div>
          )}
          {trackingRiskVal !== undefined && trackingRiskVal !== null && (
            <div>• Takip Güvenilirlik Riski: <strong>{trackingRiskVal}</strong></div>
          )}
          {breakdown.scenario_boost !== undefined && breakdown.scenario_boost !== null && (
            <div>• Senaryo Risk Artışı: <strong>+{breakdown.scenario_boost}</strong></div>
          )}
        </div>
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
        <span>{risk.recommended_action || fallbackRecommendedAction(riskLevel, segment?.is_blocked)}</span>
      </div>
    </div>
  )
}
