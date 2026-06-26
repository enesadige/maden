import { RISK_COLORS, WORKER_COLOR, ROUTE_COLOR } from '../utils/riskColors'

const ITEMS = [
  { label: 'Düşük Risk', color: RISK_COLORS.low },
  { label: 'Orta Risk', color: RISK_COLORS.medium },
  { label: 'Yüksek Risk', color: RISK_COLORS.high },
  { label: 'Kritik Risk', color: RISK_COLORS.critical },
  { label: 'Kapalı / Göçük', color: RISK_COLORS.blocked },
  { label: 'İşçi', color: WORKER_COLOR },
  { label: 'Acil Rota', color: ROUTE_COLOR }
]

export default function SegmentLegend() {
  return (
    <div className="legend">
      {ITEMS.map((item) => (
        <div className="legend-item" key={item.label}>
          <span className="legend-swatch" style={{ backgroundColor: item.color }} />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  )
}
