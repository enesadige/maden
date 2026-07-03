import { RISK_COLORS, WORKER_COLOR, ROUTE_COLOR } from '../utils/riskColors'

const ITEMS = [
  { label: 'Düşük Risk', color: RISK_COLORS.low, shape: 'node' },
  { label: 'Orta Risk', color: RISK_COLORS.medium, shape: 'node' },
  { label: 'Yüksek Risk', color: RISK_COLORS.high, shape: 'node' },
  { label: 'Kritik Risk', color: RISK_COLORS.critical, shape: 'node' },
  { label: 'Kapalı / Göçük', color: RISK_COLORS.blocked, shape: 'blocked' },
  { label: 'İşçi', color: WORKER_COLOR, shape: 'worker' },
  { label: 'Gaz Sensörü', color: '#f5a623', shape: 'sensor' },
  { label: 'Acil Rota', color: ROUTE_COLOR, shape: 'route' }
]

export default function SegmentLegend() {
  return (
    <div className="legend">
      {ITEMS.map((item) => (
        <div className="legend-item" key={item.label}>
          <span
            className={`legend-swatch legend-swatch--${item.shape}`}
            style={{ '--legend-color': item.color, backgroundColor: item.shape === 'route' ? 'transparent' : item.color }}
          />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  )
}
