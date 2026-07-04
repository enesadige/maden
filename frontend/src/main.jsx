import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles/global.css'
import './styles/dashboard.css'

function renderErrorOverlay(title, message) {
  const container = document.getElementById('root')
  if (container) {
    container.innerHTML = `
      <div style="padding: 24px; margin: 24px; background: #2d1e1f; border: 1px solid #e53e3e; border-radius: 8px; color: #fff; font-family: sans-serif; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
        <h2 style="color: #e53e3e; margin-top: 0; font-size: 20px;">MadenGuard AI — Yükleme Hatası</h2>
        <p><strong>Hata Türü:</strong> ${title}</p>
        <p style="background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; font-family: monospace;">${message}</p>
        <p style="color: #a0aec0; font-size: 13px; margin-bottom: 0;">Lütfen tarayıcı konsol loglarını ve backend sunucusunun (Port: 8000) açık olup olmadığını kontrol edin.</p>
        <button onclick="window.location.reload()" style="margin-top: 14px; padding: 8px 16px; background: #e53e3e; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 13px;">
          Sayfayı Yenile
        </button>
      </div>
    `
  }
}

function isBenignDomCleanupError(message) {
  return String(message || '').includes("Failed to execute 'removeChild' on 'Node'")
    || String(message || '').includes('The node to be removed is not a child of this node')
}

// Global error handlers
window.addEventListener('error', (event) => {
  const message = event.message || event.error?.message || ''
  if (isBenignDomCleanupError(message)) {
    event.preventDefault()
    console.warn("Ignored benign DOM cleanup error:", message)
    return
  }
  console.error("Global runtime error caught:", event.error)
  renderErrorOverlay('Global Hata', message || 'Bilinmeyen runtime hatası')
})

window.addEventListener('unhandledrejection', (event) => {
  const message = event.reason?.message || String(event.reason || '')
  if (isBenignDomCleanupError(message)) {
    event.preventDefault()
    console.warn("Ignored benign DOM cleanup rejection:", message)
    return
  }
  console.error("Unhandled promise rejection:", event.reason)
  renderErrorOverlay('Unhandled Rejection', message || 'Bilinmeyen promise reddi')
})

try {
  const rootElement = document.getElementById('root')
  if (!rootElement) {
    throw new Error('HTML gövdesinde id="root" olan ana element bulunamadı.')
  }
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>
  )
} catch (err) {
  console.error("React mount failure:", err)
  renderErrorOverlay('React Mount Hatası', err.message)
}
