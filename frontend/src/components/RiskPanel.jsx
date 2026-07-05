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
  const activeReasons = Array.isArray(risk.active_reasons) ? risk.active_reasons : []
  const recommendedAction = risk.recommended_action || fallbackRecommendedAction(riskLevel, segment?.is_blocked)
  const weightedMultiSensorRisk = risk.weighted_multi_sensor_risk || gasSensor?.weighted_multi_sensor_risk || envRisk?.weighted_multi_sensor_risk
  const aiInsights = risk.ai_insights || breakdown.ai_insights
  const aiReasons = Array.isArray(aiInsights?.reasons) ? aiInsights.reasons : []
  const aiSubModels = [
    ['Geometri', aiInsights?.geometry_model],
    ['Worker', aiInsights?.worker_behavior_model],
    ['Çevre', aiInsights?.environmental_signal]
  ].filter(([, model]) => model)

  return (
    <div className="panel">
      <h2 className="panel-title">Risk Paneli</h2>
      {!selectedSegmentId && <p className="panel-hint">Segment seçilmedi — en kritik segment gösteriliyor.</p>}

      <div className="risk-summary-card">
        <div className="risk-summary-head">
          <div>
            <span className="panel-label">Segment</span>
            <strong>{segment?.name || risk.segment_id}</strong>
            <span className="risk-segment-id">{risk.segment_id}</span>
          </div>
          <span className="risk-badge" style={{ backgroundColor: color }}>
            {getRiskLabel(segment?.is_blocked ? 'blocked' : riskLevel)}
          </span>
        </div>

        <div className="risk-score-line">
          <span className="risk-score-big">{formatNumber(finalScore)}</span>
          <span className="risk-score-copy">AI risk skoru</span>
        </div>

        {activeReasons.length > 0 ? (
          <div className="risk-chip-list" aria-label="Aktif risk nedenleri">
            {activeReasons.slice(0, 4).map((reason) => (
              <span className="risk-chip" key={reason}>{reason}</span>
            ))}
            {activeReasons.length > 4 && <span className="risk-chip risk-chip--muted">+{activeReasons.length - 4}</span>}
          </div>
        ) : (
          <p className="panel-empty">Aktif risk nedeni yok.</p>
        )}
      </div>

      <div className="risk-action-card">
        <span className="panel-label">Önerilen aksiyon</span>
        <strong>{recommendedAction}</strong>
      </div>

      {aiInsights && (
        <div className="risk-ai-card">
          <div>
            <span className="panel-label">AI/ML anomalilik</span>
            <strong>{formatNumber(aiInsights.ai_anomaly_score)}</strong>
            <span>{aiInsights.ai_anomaly_level}</span>
          </div>
          {aiSubModels.length > 0 && (
            <div className="risk-ai-model-grid">
              {aiSubModels.map(([label, model]) => (
                <span key={label}>
                  {label}
                  <strong>{formatNumber(model.score)}</strong>
                </span>
              ))}
            </div>
          )}
          <p>{aiReasons.slice(0, 2).join(' · ')}</p>
        </div>
      )}

      <div className="risk-metric-grid">
        <div className="risk-metric">
          <span>Geometri</span>
          <strong>{formatNumber(geomRiskVal)}</strong>
        </div>
        <div className="risk-metric">
          <span>Çevre</span>
          <strong>{formatNumber(envRiskVal)}</strong>
        </div>
        <div className="risk-metric">
          <span>İşçi</span>
          <strong>{formatNumber(workerRiskVal)}</strong>
        </div>
        <div className="risk-metric">
          <span>Takip</span>
          <strong>{formatNumber(trackingRiskVal)}</strong>
        </div>
      </div>

      <div className="panel-row">
        <span className="panel-label">Segmentte işçi</span>
        <span>{workersHere.length > 0 ? workersHere.map((w) => w.worker_id).join(', ') : 'Yok'}</span>
      </div>

      {(Object.keys(measurements).length > 0 || Object.keys(componentScores).length > 0) && (
        <details className="risk-details">
          <summary>Çevresel sensör detayları</summary>
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
          <p className="panel-hint">
            Weighted skor {formatNumber(weightedMultiSensorRisk)}
            {sensorConfidence !== undefined && ` · Güven ${formatNumber(sensorConfidence * 100, '%')}`}
            {sensorReliability && ` · ${sensorReliability}`}
          </p>
          {environmentalReasons.length > 0 && (
            <ul>
              {environmentalReasons.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          )}
        </details>
      )}

      {behaviorEventCount > 0 && (
        <details className="risk-details">
          <summary>UWB davranış uyarıları</summary>
          <div>
            <strong className={criticalBehaviorEventCount > 0 ? 'text-danger' : undefined}>
              {behaviorEventCount} event
            </strong>
            {criticalBehaviorEventCount > 0 && ` · ${criticalBehaviorEventCount} kritik`}
          </div>
          {behaviorEventTypes.length > 0 && <p>{behaviorEventTypes.join(', ')}</p>}
          {behaviorWorkerIds.length > 0 && <p>İşçiler: {behaviorWorkerIds.join(', ')}</p>}
        </details>
      )}

      <details className="risk-details">
        <summary>Teknik kırılım</summary>
        <div className="panel-row">
          <span className="panel-label">Gaz/Metan</span>
          <span className={gasSensor?.status === 'alarm' ? 'text-danger' : undefined}>
            {gasSensor
              ? `${formatNumber(measurements.methane_ppm || gasSensor.methane_value, measurements.methane_ppm ? ' ppm' : '%')} (skor ${gasSensor.risk_score})${gasSensor.status === 'alarm' ? ' — ALARM' : ''}`
              : (envRisk ? `${envRisk.methane_ppm} ppm (skor ${envRisk.gas_risk_score})` : 'Veri yok')}
          </span>
        </div>
        <div className="panel-row">
          <span className="panel-label">Geometri</span>
          <span>{geoRisk ? `Skor ${geoRisk.structural_risk_score} — ${geoRisk.notes}` : 'Veri yok'}</span>
        </div>
        {risk.worker_behavior_anomaly_score > 0 && (
          <div className="panel-row">
            <span className="panel-label">Anomali skoru</span>
            <span>{risk.worker_behavior_anomaly_score}</span>
          </div>
        )}
        {breakdown.scenario_boost !== undefined && breakdown.scenario_boost !== null && (
          <div className="panel-row">
            <span className="panel-label">Senaryo artışı</span>
            <span>+{breakdown.scenario_boost}</span>
          </div>
        )}
      </details>
    </div>
  )
}
