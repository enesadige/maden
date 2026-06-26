import { getRiskColor, getRiskLabel } from '../utils/riskColors'

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
      {gasSensors.map((sensor) => (
        <div
          className={`gas-sensor-card ${sensor.status === 'alarm' ? 'gas-sensor-card--alarm' : ''}`}
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
            <span>{sensor.gas_type}</span>
          </div>
          <div className="panel-row">
            <span className="panel-label">Metan Değeri</span>
            <span>{sensor.methane_value} %</span>
          </div>
          <div className="panel-row">
            <span className="panel-label">Durum</span>
            <span className={sensor.status === 'alarm' ? 'text-danger' : 'text-ok'}>
              {sensor.status === 'alarm' ? 'ALARM' : 'Normal'}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
