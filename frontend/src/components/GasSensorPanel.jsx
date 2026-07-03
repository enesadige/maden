import { getRiskColor, getRiskLabel } from '../utils/riskColors'

function formatNumber(value, suffix = '') {
  if (value === undefined || value === null || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return `${value}${suffix}`
  return `${Number.isInteger(number) ? number : number.toFixed(2)}${suffix}`
}

export default function GasSensorPanel({ gasSensors }) {
  if (!gasSensors || gasSensors.length === 0) {
    return (
      <div className="panel">
        <h2 className="panel-title">Gaz Sensörleri</h2>
        <p className="panel-empty">Gaz sensör verisi bulunamadı.</p>
      </div>
    )
  }

  return (
    <div className="panel">
      <h2 className="panel-title">Gaz Sensörleri</h2>
      {gasSensors.map((sensor) => {
        const measurements = sensor.measurements || {}
        const componentScores = sensor.component_scores || {}
        const status = String(sensor.status || sensor.risk_level || 'normal').toLowerCase()
        const isAlarm = status === 'alarm' || status === 'critical' || status === 'high'

        return (
        <div
          className={`gas-sensor-card ${isAlarm ? 'gas-sensor-card--alarm' : ''}`}
          key={sensor.sensor_id}
        >
          <div className="gas-sensor-header">
            <strong>{sensor.sensor_id}</strong>
            <span
              className="risk-badge"
              style={{ backgroundColor: getRiskColor(sensor.risk_level) }}
            >
              {getRiskLabel(sensor.risk_level)}
            </span>
          </div>
          <div className="panel-row">
            <span className="panel-label">Segment</span>
            <span>{sensor.segment_id}</span>
          </div>
          <div className="panel-row">
            <span className="panel-label">Gaz Tipi</span>
            <span>{sensor.gas_type || 'Methane'}</span>
          </div>
          <div className="panel-row">
            <span className="panel-label">Metan Değeri</span>
            <span>{measurements.methane_ppm !== undefined ? formatNumber(measurements.methane_ppm, ' ppm') : `${sensor.methane_value} %`}</span>
          </div>
          {Object.keys(measurements).length > 0 && (
            <div className="panel-row panel-row--block">
              <span className="panel-label">Çevresel Ölçümler</span>
              <div className="metric-grid">
                <span>CO: <strong>{formatNumber(measurements.co_ppm, ' ppm')}</strong></span>
                <span>O2: <strong>{formatNumber(measurements.oxygen_percent, '%')}</strong></span>
                <span>Sıcaklık: <strong>{formatNumber(measurements.temperature_c, '°C')}</strong></span>
                <span>Nem: <strong>{formatNumber(measurements.humidity_percent, '%')}</strong></span>
                <span>Basınç: <strong>{formatNumber(measurements.pressure_hpa, ' hPa')}</strong></span>
              </div>
            </div>
          )}
          {Object.keys(componentScores).length > 0 && (
            <div className="panel-row panel-row--block">
              <span className="panel-label">Bileşen Riskleri</span>
              <div className="metric-grid metric-grid--scores">
                <span>CH4: <strong>{formatNumber(componentScores.methane_risk)}</strong></span>
                <span>CO: <strong>{formatNumber(componentScores.co_risk)}</strong></span>
                <span>O2: <strong>{formatNumber(componentScores.oxygen_risk)}</strong></span>
                <span>Isı: <strong>{formatNumber(componentScores.temperature_risk)}</strong></span>
                <span>Nem: <strong>{formatNumber(componentScores.humidity_risk)}</strong></span>
                <span>Basınç: <strong>{formatNumber(componentScores.pressure_risk)}</strong></span>
              </div>
            </div>
          )}
          {sensor.risk_score !== undefined && (
            <div className="panel-row">
              <span className="panel-label">Risk Skoru</span>
              <span>{sensor.risk_score}</span>
            </div>
          )}
          <div className="panel-row">
            <span className="panel-label">Durum</span>
            <span className={isAlarm ? 'text-danger' : 'text-ok'}>
              {isAlarm ? 'ALARM / RİSK' : 'Normal'}
            </span>
          </div>
          {sensor.confidence !== undefined && (
            <div className="panel-row">
              <span className="panel-label">Güven</span>
              <span>{formatNumber(Number(sensor.confidence) * 100, '%')} · {sensor.reliability_status || 'unknown'}</span>
            </div>
          )}
        </div>
        )
      })}
    </div>
  )
}
