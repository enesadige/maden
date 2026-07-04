import { isApiMode } from '../services/api'

export default function Layout({ viewMode, onChangeViewMode, activeScenarioLabel, apiModeActive = isApiMode(), children }) {
  return (
    <div className="layout">
      <header className="layout-header">
        <div className="layout-header-title">
          <h1>MadenGuard AI</h1>
          <span className="layout-subtitle">Maden Güvenliği Karar Destek Dashboard'u</span>
        </div>

        <div className="layout-header-meta">
          <span className={`status-pill ${apiModeActive ? 'status-pill--api' : 'status-pill--mock'}`}>
            {apiModeActive ? 'API Mode' : 'Mock Mode'}
          </span>
          <span className="status-item">Senaryo: <strong>{activeScenarioLabel}</strong></span>

          <div className="view-toggle">
            <button
              className={`view-toggle-button ${viewMode === 'admin' ? 'view-toggle-button--active' : ''}`}
              onClick={() => onChangeViewMode('admin')}
            >
              Yönetici Görünümü
            </button>
            <button
              className={`view-toggle-button ${viewMode === 'miner' ? 'view-toggle-button--active' : ''}`}
              onClick={() => onChangeViewMode('miner')}
            >
              Madenci Görünümü
            </button>
          </div>
        </div>
      </header>

      <div className="layout-body">{children}</div>
    </div>
  )
}
