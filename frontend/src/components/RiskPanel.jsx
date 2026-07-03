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

function formatNumber(value, suffix = '') {
  if (value === undefined || value === null || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return `${value}${suffix}`
  return `${Number.isInteger(number) ? number : number.toFixed(2)}${suffix}`
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
  const measurements = risk.environmental_measurements || gasSensor?.measurements || envRisk?.measurements || {}
  const componentScores = risk.environmental_component_scores || gasSensor?.component_scores || envRisk?.component_scores || {}
  const environmentalReasons = risk.environmental_risk_reason || gasSensor?.environmental_risk_reason || envRisk?.environmental_risk_reason || []
  const sensorConfidence = risk.sensor_confidence ?? gasSensor?.confidence ?? envRisk?.confidence
  const sensorReliability = risk.reliability_status || gasSensor?.reliability_status || envRisk?.reliability_status
  const behaviorEventCount = risk.behavior_event_count || 0
  const criticalBehaviorEventCount = risk.critical_behavior_event_count || 0
  const behaviorEventTypes = risk.behavior_anomaly_event_types || []
  const behaviorWorkerIds = risk.behavior_anomaly_worker_ids || []

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
          {risk.worker_behavior_anomaly_score > 0 && (
            <div>• Davranış Anomali Skoru: <strong>{risk.worker_behavior_anomaly_score}</strong></div>
          )}
          {breakdown.scenario_boost !== undefined && breakdown.scenario_boost !== null && (
            <div>• Senaryo Risk Artışı: <strong>+{breakdown.scenario_boost}</strong></div>
          )}
        </div>
      </div>

      {(Object.keys(measurements).length > 0 || Object.keys(componentScores).length > 0) && (
        <div className="panel-row panel-row--block">
          <span className="panel-label">Çoklu Sensör Detayı</span>
          <div className="metric-grid">
            <span>CH4: <strong>{formatNumber(measurements.methane_ppm, ' ppm')}</strong></span>
            <span>CO: <strong>{formatNumber(measurements.co_ppm, ' ppm')}</strong></span>
            <span>O2: <strong>{formatNumber(measurements.oxygen_percent, '%')}</strong></span>
            <span>Sıcaklık: <strong>{formatNumber(measurements.temperature_c, '°C')}</strong></span>
            <span>Nem: <strong>{formatNumber(measurements.humidity_percent, '%')}</strong></span>
            <span>Basınç: <strong>{formatNumber(measurements.pressure_hpa, ' hPa')}</strong></span>
          </div>
          <div className="metric-grid metric-grid--scores">
            <span>Metan: <strong>{formatNumber(componentScores.methane_risk)}</strong></span>
            <span>CO: <strong>{formatNumber(componentScores.co_risk)}</strong></span>
            <span>O2: <strong>{formatNumber(componentScores.oxygen_risk)}</strong></span>
            <span>Isı: <strong>{formatNumber(componentScores.temperature_risk)}</strong></span>
            <span>Nem: <strong>{formatNumber(componentScores.humidity_risk)}</strong></span>
            <span>Basınç: <strong>{formatNumber(componentScores.pressure_risk)}</strong></span>
          </div>
          <div className="panel-hint">
            Weighted skor {formatNumber(risk.weighted_multi_sensor_risk || gasSensor?.weighted_multi_sensor_risk || envRisk?.weighted_multi_sensor_risk)}
            {sensorConfidence !== undefined && ` · Güven ${formatNumber(sensorConfidence * 100, '%')}`}
            {sensorReliability && ` · ${sensorReliability}`}
          </div>
          {environmentalReasons.length > 0 && (
            <ul>
              {environmentalReasons.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          )}
        </div>
      )}

      {behaviorEventCount > 0 && (
        <div className="panel-row panel-row--block">
          <span className="panel-label">UWB Davranış Uyarısı</span>
          <div>
            <strong className={criticalBehaviorEventCount > 0 ? 'text-danger' : undefined}>
              {behaviorEventCount} event
            </strong>
            {criticalBehaviorEventCount > 0 && ` · ${criticalBehaviorEventCount} kritik`}
          </div>
          {behaviorEventTypes.length > 0 && <span>{behaviorEventTypes.join(', ')}</span>}
          {behaviorWorkerIds.length > 0 && <span>İşçiler: {behaviorWorkerIds.join(', ')}</span>}
        </div>
      )}

      <div className="panel-row">
        <span className="panel-label">Gaz/Metan Riski</span>
        <span className={gasSensor?.status === 'alarm' ? 'text-danger' : undefined}>
          {gasSensor
            ? `${formatNumber(measurements.methane_ppm || gasSensor.methane_value, measurements.methane_ppm ? ' ppm' : '%')} (skor ${gasSensor.risk_score})${gasSensor.status === 'alarm' ? ' — ALARM' : ''}`
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
