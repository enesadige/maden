import { Component, useMemo, useRef, useState, useEffect, useCallback } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Line, Html } from '@react-three/drei'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import * as THREE from 'three'
import { getRiskColor, WORKER_COLOR, WORKER_AT_RISK_COLOR, ROUTE_COLOR, RISK_COLORS } from '../utils/riskColors'
import { buildConnectionLines, buildRoutePoints } from '../utils/geometryUtils'
import { getPointCloudMetadata } from '../services/api'

const UP = new THREE.Vector3(0, 1, 0)
const FORWARD = new THREE.Vector3(0, 0, 1)

const SHORT_LABELS = {
  S001: 'Giriş',
  S002: 'Ana Yol',
  S003: 'Dar Galeri',
  S004: 'Riskli Bölge',
  S005: 'Derin Tünel'
}

// ─── Error Boundary ───────────────────────────────────────────────────────────

class ModelErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() { return { hasError: true } }
  render() {
    if (this.state.hasError) return this.props.fallback
    return this.props.children
  }
}

// ─── PLY Loader ───────────────────────────────────────────────────────────────

function LidarPointCloud({ setStatus, metadata, onLoaded }) {
  const [geometry, setGeometry] = useState(null)

  useEffect(() => {
    if (!metadata) return
    const loader = new PLYLoader()
    setStatus('loading')

    const onLoad = (geo, statusStr) => {
      geo.rotateX(-Math.PI / 2)
      geo.computeBoundingBox()
      const size = new THREE.Vector3()
      geo.boundingBox.getSize(size)
      const maxDim = Math.max(size.x, size.y, size.z)
      if (maxDim > 0 && maxDim !== Infinity) {
        const scale = 160 / maxDim
        geo.scale(scale, scale, scale)
      }
      geo.center()
      geo.computeBoundingSphere()
      geo.computeBoundingBox()
      onLoaded(geo.boundingSphere, geo.boundingBox)
      setGeometry(geo)
      setStatus(statusStr)
    }

    const tryDownsampled = () => {
      if (metadata.downsampled_url) {
        loader.load(metadata.downsampled_url, (geo) => onLoad(geo, 'downsampled'), undefined, () => setStatus('not_found'))
      } else {
        setStatus('not_found')
      }
    }

    if (metadata.preview_url) {
      loader.load(metadata.preview_url, (geo) => onLoad(geo, 'preview'), undefined, tryDownsampled)
    } else {
      tryDownsampled()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metadata])

  if (!geometry) return null
  const hasColors = geometry.hasAttribute('color')
  return (
    <points geometry={geometry}>
      <pointsMaterial
        size={0.15}
        vertexColors={hasColors}
        color={hasColors ? 0xffffff : '#34f5c5'}
        sizeAttenuation={true}
        transparent
        opacity={hasColors ? 1.0 : 0.85}
      />
    </points>
  )
}

// ─── Camera Controller ────────────────────────────────────────────────────────

function CameraController({ bounds, cameraAction, onActionComplete }) {
  const { camera } = useThree()
  const controlsRef = useRef()

  useEffect(() => {
    if (!bounds || !controlsRef.current || !cameraAction) return
    const { center, radius } = bounds

    if (cameraAction === 'reset' || cameraAction === 'initial') {
      const fov = camera.fov * (Math.PI / 180)
      const distance = Math.abs(radius / Math.sin(fov / 2)) * 1.2
      camera.position.set(center.x + distance * 0.4, center.y + distance * 0.6, center.z + distance * 0.8)
      camera.lookAt(center)
      camera.updateProjectionMatrix()
      controlsRef.current.target.copy(center)
    } else if (cameraAction === 'top') {
      camera.position.set(center.x, center.y + radius * 2.5, center.z)
      camera.lookAt(center)
      camera.updateProjectionMatrix()
      controlsRef.current.target.copy(center)
    } else if (cameraAction === 'side') {
      camera.position.set(center.x - radius * 2.5, center.y + radius * 0.2, center.z)
      camera.lookAt(center)
      camera.updateProjectionMatrix()
      controlsRef.current.target.copy(center)
    } else if (cameraAction === 'focus') {
      camera.position.set(center.x + radius * 0.2, center.y + radius * 0.1, center.z + radius * 0.6)
      camera.lookAt(center)
      camera.updateProjectionMatrix()
      controlsRef.current.target.copy(center)
    }

    controlsRef.current.update()
    if (cameraAction !== 'initial') onActionComplete()
  }, [bounds, camera, cameraAction, onActionComplete])

  return (
    <OrbitControls
      ref={controlsRef}
      enablePan={true}
      screenSpacePanning={true}
      enableZoom={true}
      enableRotate={true}
      panSpeed={0.8}
      rotateSpeed={0.8}
      zoomSpeed={1.2}
      maxPolarAngle={Math.PI - 0.05}
    />
  )
}

// ─── Placeholder Tunnel (when PLY not found) ──────────────────────────────────

function CorridorSegment({ line }) {
  const start = useMemo(() => new THREE.Vector3(...line.from), [line.from])
  const end = useMemo(() => new THREE.Vector3(...line.to), [line.to])
  const direction = useMemo(() => new THREE.Vector3().subVectors(end, start), [start, end])
  const length = direction.length()
  if (length < 0.01) return null

  const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5)
  const dirNormalized = direction.clone().normalize()
  const tubeQuaternion = new THREE.Quaternion().setFromUnitVectors(UP, dirNormalized)
  const ringQuaternion = new THREE.Quaternion().setFromUnitVectors(FORWARD, dirNormalized)

  let perp = new THREE.Vector3().crossVectors(dirNormalized, UP)
  if (perp.lengthSq() < 0.001) perp = new THREE.Vector3(1, 0, 0)
  perp.normalize().multiplyScalar(0.95)

  const floorY = -1.15
  const railA = [[start.x + perp.x, start.y + floorY, start.z + perp.z], [end.x + perp.x, end.y + floorY, end.z + perp.z]]
  const railB = [[start.x - perp.x, start.y + floorY, start.z - perp.z], [end.x - perp.x, end.y + floorY, end.z - perp.z]]
  const centerLine = [[start.x, start.y + floorY, start.z], [end.x, end.y + floorY, end.z]]
  const archCount = Math.max(2, Math.round(length / 4))
  const arches = []
  for (let i = 1; i <= archCount; i++) {
    const t = i / (archCount + 1)
    const pos = new THREE.Vector3().lerpVectors(start, end, t)
    arches.push(
      <group key={`arch-${line.key}-${i}`} position={pos} quaternion={ringQuaternion}>
        <mesh>
          <torusGeometry args={[1.35, 0.07, 8, 24]} />
          <meshStandardMaterial color="#4a5263" metalness={0.6} roughness={0.4} />
        </mesh>
      </group>
    )
  }

  return (
    <group>
      <mesh position={mid} quaternion={tubeQuaternion}>
        <cylinderGeometry args={[1.35, 1.35, length, 20, 1, true]} />
        <meshStandardMaterial color="#1a1e29" transparent opacity={0.3} side={THREE.DoubleSide} roughness={0.8} />
      </mesh>
      {arches}
      <Line points={railA} color="#525a68" lineWidth={1.2} />
      <Line points={railB} color="#525a68" lineWidth={1.2} />
      <Line points={centerLine} color="#2f3540" lineWidth={1} dashed dashSize={0.5} gapSize={0.4} />
    </group>
  )
}

function PlaceholderTunnel({ segments }) {
  const lines = useMemo(() => buildConnectionLines(segments), [segments])
  return (
    <group>
      {lines.map(line => <CorridorSegment key={line.key} line={line} />)}
      {segments.map(segment => (
        <group key={`chamber-${segment.segment_id}`} position={segment.center}>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[1.7, 1.7, 2.8, 24, 1, true]} />
            <meshStandardMaterial color="#11141c" transparent opacity={0.4} side={THREE.DoubleSide} />
          </mesh>
          <mesh position={[0, -1.15, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[1.7, 24]} />
            <meshStandardMaterial color="#0b0d14" />
          </mesh>
        </group>
      ))}
    </group>
  )
}

function BlockedMark() {
  const color = RISK_COLORS.critical
  return (
    <group position={[0, 0.1, 0]}>
      <mesh rotation={[0, 0, Math.PI / 4]}>
        <boxGeometry args={[2, 0.18, 0.18]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9} />
      </mesh>
      <mesh rotation={[0, 0, -Math.PI / 4]}>
        <boxGeometry args={[2, 0.18, 0.18]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9} />
      </mesh>
    </group>
  )
}

function DebrisField() {
  const chunks = useMemo(() => [
    { pos: [0.6, -0.9, 0.3], scale: 0.55, rot: [0.4, 0.2, 0.1] },
    { pos: [-0.7, -0.95, -0.2], scale: 0.4, rot: [0.1, 0.8, 0.3] },
    { pos: [0.1, -1.0, 0.6], scale: 0.35, rot: [0.6, 0.1, 0.5] },
    { pos: [-0.3, -0.85, 0.4], scale: 0.45, rot: [0.2, 0.5, 0.7] },
    { pos: [0.8, -0.9, -0.4], scale: 0.3, rot: [0.9, 0.3, 0.2] }
  ], [])
  return (
    <group>
      {chunks.map((c, i) => (
        <mesh key={i} position={c.pos} rotation={c.rot} scale={c.scale}>
          <dodecahedronGeometry args={[1, 0]} />
          <meshStandardMaterial color="#3c372e" roughness={0.95} />
        </mesh>
      ))}
    </group>
  )
}

// ─── Full Overlay (shown only when PLY is NOT loaded) ─────────────────────────

function WorkerHelmetGlow({ color }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current) return
    ref.current.material.opacity = 0.5 + Math.sin(clock.elapsedTime * 3) * 0.25
  })
  return (
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.42, 0.55, 24]} />
      <meshBasicMaterial color={color} transparent opacity={0.5} side={THREE.DoubleSide} />
    </mesh>
  )
}

function SegmentMarker({ segment, risk, isSelected, onSelect }) {
  const isBlocked = segment.is_blocked
  const color = getRiskColor(risk?.risk_level, segment.is_blocked)
  const isCritical = !isBlocked && risk?.risk_level === 'critical'
  const isHigh = !isBlocked && risk?.risk_level === 'high'
  const haloColor = isCritical ? RISK_COLORS.critical : isHigh ? RISK_COLORS.high : null
  const shortLabel = SHORT_LABELS[segment.segment_id]

  return (
    <group position={segment.center}>
      {haloColor && (
        <mesh>
          <sphereGeometry args={[0.5, 20, 20]} />
          <meshBasicMaterial color={haloColor} transparent opacity={isCritical ? 0.25 : 0.15} />
        </mesh>
      )}
      <mesh onClick={e => { e.stopPropagation(); onSelect(segment.segment_id) }}>
        <sphereGeometry args={[isSelected ? 0.3 : 0.18, 24, 24]} />
        <meshStandardMaterial
          color={color} emissive={color}
          emissiveIntensity={isSelected ? 0.9 : (isCritical || isHigh) ? 0.6 : 0.35}
        />
      </mesh>
      {isBlocked && <><BlockedMark /><DebrisField /></>}
      <Html distanceFactor={22} position={[0, 1.2, 0]}>
        <div className="segment-label" style={{ fontSize: '11px', whiteSpace: 'nowrap' }}>
          {segment.segment_id}{shortLabel ? ` - ${shortLabel}` : ''}
        </div>
      </Html>
    </group>
  )
}

function WorkerMarker({ worker }) {
  const isAtRisk = worker.status === 'at_risk'
  const bodyColor = isAtRisk ? WORKER_AT_RISK_COLOR : WORKER_COLOR
  return (
    <group position={worker.position}>
      {isAtRisk && <WorkerHelmetGlow color={RISK_COLORS.critical} />}
      <mesh position={[0, 0.18, 0]}>
        <cylinderGeometry args={[0.16, 0.2, 0.4, 10]} />
        <meshStandardMaterial color={bodyColor} emissive={bodyColor} emissiveIntensity={0.5} />
      </mesh>
      <mesh position={[0, 0.46, 0]}>
        <sphereGeometry args={[0.17, 14, 14]} />
        <meshStandardMaterial color="#ffd23a" emissive="#ffd23a" emissiveIntensity={0.4} />
      </mesh>
    </group>
  )
}

function GasSensorMarker({ sensor }) {
  const isAlarm = sensor.status === 'alarm'
  const color = isAlarm ? RISK_COLORS.critical : getRiskColor(sensor.risk_level)
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current || !isAlarm) return
    ref.current.material.emissiveIntensity = 0.7 + Math.sin(clock.elapsedTime * 6) * 0.4
  })
  return (
    <group position={sensor.position}>
      <mesh position={[0, -0.3, 0]}>
        <cylinderGeometry args={[0.05, 0.05, 0.6, 8]} />
        <meshStandardMaterial color="#454c58" />
      </mesh>
      <mesh ref={ref} position={[0, 0.1, 0]} rotation={[0, 0, Math.PI / 4]}>
        <octahedronGeometry args={[isAlarm ? 0.32 : 0.24, 0]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={isAlarm ? 1 : 0.4} />
      </mesh>
    </group>
  )
}

function ConnectionLines({ segments }) {
  const lines = useMemo(() => buildConnectionLines(segments), [segments])
  return (
    <group>
      {lines.map(line => (
        <Line key={line.key} points={[line.from, line.to]} color="#4a5160" lineWidth={1.2} />
      ))}
    </group>
  )
}

function EmergencyRouteLine({ emergencyRoute, segments }) {
  const routeSegments = emergencyRoute?.route_segments || emergencyRoute?.route
  if (!routeSegments?.length) return null
  const points = buildRoutePoints(routeSegments, segments)
  if (points.length < 2) return null
  const elevated = points.map(p => [p[0], p[1] + 0.4, p[2]])
  const isRouteSafe = Boolean(emergencyRoute.exit_reachable && emergencyRoute.alternative_route_available)
  if (isRouteSafe) return <Line points={elevated} color={ROUTE_COLOR} lineWidth={4} />
  return <Line points={elevated} color={RISK_COLORS.critical} lineWidth={3} dashed dashSize={0.6} gapSize={0.4} />
}

// ─── Demo Overlay (shown when PLY loaded + mode = 'demo') ─────────────────────

function DemoOverlayLayer({ segments, risks, workers, gasSensors, emergencyRoute, selectedSegmentId, onSelect }) {
  const riskBySegment = useMemo(() => {
    const map = {}
    for (const risk of risks) map[risk.segment_id] = risk
    return map
  }, [risks])

  const connLines = useMemo(() => buildConnectionLines(segments), [segments])

  const routeIds = useMemo(
    () => emergencyRoute?.route_segments || emergencyRoute?.route || [],
    [emergencyRoute]
  )
  const routePts = useMemo(() => buildRoutePoints(routeIds, segments), [routeIds, segments])
  const isRouteSafe = Boolean(emergencyRoute?.exit_reachable && emergencyRoute?.alternative_route_available)

  return (
    <group>
      {connLines.map(line => (
        <Line key={line.key} points={[line.from, line.to]} color="#1a2030" lineWidth={0.6} />
      ))}

      {segments.map(seg => {
        const risk = riskBySegment[seg.segment_id]
        const color = getRiskColor(risk?.risk_level, seg.is_blocked)
        const isSelected = selectedSegmentId === seg.segment_id
        return (
          <group key={seg.segment_id} position={seg.center}>
            <mesh onClick={e => { e.stopPropagation(); onSelect(seg.segment_id) }}>
              <sphereGeometry args={[isSelected ? 0.13 : 0.07, 10, 10]} />
              <meshBasicMaterial color={color} transparent opacity={isSelected ? 0.7 : 0.4} />
            </mesh>
            {isSelected && (
              <Html distanceFactor={18} position={[0, 0.55, 0]}>
                <div className="demo-label-chip">{seg.segment_id}</div>
              </Html>
            )}
          </group>
        )
      })}

      {workers.map(w => (
        <mesh key={w.worker_id} position={w.position}>
          <sphereGeometry args={[0.08, 8, 8]} />
          <meshBasicMaterial
            color={w.status === 'at_risk' ? WORKER_AT_RISK_COLOR : WORKER_COLOR}
            transparent opacity={0.5}
          />
        </mesh>
      ))}

      {(gasSensors || []).map(sensor => {
        const color = sensor.status === 'alarm' ? RISK_COLORS.critical : getRiskColor(sensor.risk_level)
        return (
          <mesh key={sensor.sensor_id} position={sensor.position} rotation={[0, 0, Math.PI / 4]}>
            <octahedronGeometry args={[0.09, 0]} />
            <meshBasicMaterial color={color} transparent opacity={0.5} />
          </mesh>
        )
      })}

      {routePts.length > 1 && (
        <Line
          points={routePts.map(p => [p[0], p[1] + 0.2, p[2]])}
          color={isRouteSafe ? ROUTE_COLOR : RISK_COLORS.critical}
          lineWidth={1.5}
          dashed={!isRouteSafe}
          dashSize={0.5}
          gapSize={0.4}
        />
      )}
    </group>
  )
}

// ─── Main Export ──────────────────────────────────────────────────────────────

export default function DigitalTwinViewer({
  segments,
  risks,
  workers,
  gasSensors,
  emergencyRoute,
  onSegmentSelect,
  selectedSegmentId
}) {
  const [plyStatus, setPlyStatus] = useState('loading')
  const [plyMetadata, setPlyMetadata] = useState(null)
  const [plyBounds, setPlyBounds] = useState({ center: new THREE.Vector3(6, -1, 8), radius: 20 })
  const [cameraAction, setCameraAction] = useState('initial')
  const [overlayMode, setOverlayMode] = useState('off')

  useEffect(() => {
    getPointCloudMetadata()
      .then(meta => setPlyMetadata(meta))
      .catch(() => setPlyMetadata({
        preview_url: '/models/tunnel_preview_500k.ply',
        downsampled_url: '/models/tunnel_downsampled.ply'
      }))
  }, [])

  const handlePlyLoaded = useCallback((sphere) => {
    setPlyBounds({ center: sphere.center, radius: sphere.radius })
    setCameraAction('initial')
  }, [])

  const riskBySegment = useMemo(() => {
    const map = {}
    for (const risk of risks) map[risk.segment_id] = risk
    return map
  }, [risks])

  const isRealPlyLoaded = plyStatus === 'preview' || plyStatus === 'downsampled'
  const showFullOverlays = !isRealPlyLoaded
  const showDemoOverlay = isRealPlyLoaded && overlayMode === 'demo'

  let statusText = 'Yükleniyor...'
  if (plyStatus === 'preview') {
    const file = plyMetadata?.preview_url?.split('/').pop() || 'tunnel_preview_500k.ply'
    statusText = `Gerçek LiDAR: ${file}`
  } else if (plyStatus === 'downsampled') {
    const file = plyMetadata?.downsampled_url?.split('/').pop() || 'tunnel_downsampled.ply'
    statusText = `Gerçek LiDAR: ${file}`
  } else if (plyStatus === 'not_found') {
    statusText = 'LiDAR modeli bulunamadı — placeholder gösteriliyor.'
  }

  return (
    <div className="viewer-canvas">
      {/* Status indicator */}
      <div className="viewer-status-bar">
        <span
          className="viewer-status-dot"
          style={{ background: plyStatus === 'not_found' ? '#f5a623' : plyStatus === 'loading' ? '#8a92a6' : '#34f5c5' }}
        />
        {statusText}
      </div>

      {/* Demo overlay warning strip */}
      {isRealPlyLoaded && overlayMode === 'demo' && (
        <div className="overlay-demo-warning">
          Demo overlay: segment koordinatları LiDAR ile birebir hizalı değildir.
        </div>
      )}

      {/* Controls: camera buttons + overlay toggle */}
      <div className="viewer-controls-panel">
        <div className="viewer-camera-buttons">
          <button onClick={() => setCameraAction('reset')} className="scenario-button">Reset</button>
          <button onClick={() => setCameraAction('top')} className="scenario-button">Üstten</button>
          <button onClick={() => setCameraAction('side')} className="scenario-button">Yandan</button>
          <button onClick={() => setCameraAction('focus')} className="scenario-button">Odaklan</button>
        </div>

        {isRealPlyLoaded && (
          <div className="overlay-toggle">
            <span className="overlay-toggle-label">3B Overlay:</span>
            <button
              className={`overlay-toggle-btn${overlayMode === 'off' ? ' overlay-toggle-btn--active' : ''}`}
              onClick={() => setOverlayMode('off')}
            >
              Kapalı
            </button>
            <button
              className={`overlay-toggle-btn${overlayMode === 'demo' ? ' overlay-toggle-btn--active' : ''}`}
              onClick={() => setOverlayMode('demo')}
            >
              Demo
            </button>
          </div>
        )}
      </div>

      {/* Bottom info: PLY/Map relation or off-mode note */}
      {isRealPlyLoaded && (
        <div className="ply-info-note">
          {overlayMode === 'off'
            ? '3B overlay kapalı — risk/worker/gaz detayları için Harita Görünümü\'nü kullanın.'
            : 'PLY: gerçek LiDAR tarama. Güvenilir segment/risk/worker verileri Harita Görünümü\'nde. 3B overlay Haki koordinat frame\'i hazır olunca hizalanacak.'
          }
        </div>
      )}

      {/* Three.js Canvas */}
      <Canvas camera={{ fov: 45 }}>
        <fog attach="fog" args={['#06080b', 10, 300]} />
        <color attach="background" args={['#06080b']} />
        <ambientLight intensity={0.4} />
        <directionalLight position={[15, 20, 10]} intensity={0.9} color="#e6f2ff" />
        <pointLight position={[6, 5, 8]} intensity={0.8} color="#34f5c5" distance={40} />

        <LidarPointCloud setStatus={setPlyStatus} metadata={plyMetadata} onLoaded={handlePlyLoaded} />

        {plyStatus === 'not_found' && <PlaceholderTunnel segments={segments} />}

        {showFullOverlays && (
          <>
            <ConnectionLines segments={segments} />
            {segments.map(segment => (
              <SegmentMarker
                key={segment.segment_id}
                segment={segment}
                risk={riskBySegment[segment.segment_id]}
                isSelected={selectedSegmentId === segment.segment_id}
                onSelect={onSegmentSelect}
              />
            ))}
            {workers.map(worker => <WorkerMarker key={worker.worker_id} worker={worker} />)}
            {(gasSensors || []).map(sensor => <GasSensorMarker key={sensor.sensor_id} sensor={sensor} />)}
            <EmergencyRouteLine emergencyRoute={emergencyRoute} segments={segments} />
          </>
        )}

        {showDemoOverlay && (
          <DemoOverlayLayer
            segments={segments}
            risks={risks}
            workers={workers}
            gasSensors={gasSensors}
            emergencyRoute={emergencyRoute}
            selectedSegmentId={selectedSegmentId}
            onSelect={onSegmentSelect}
          />
        )}

        <gridHelper args={[500, 500, '#1c1f27', '#0a0c11']} position={[0, -3, 0]} />
        <CameraController
          bounds={plyBounds}
          cameraAction={cameraAction}
          onActionComplete={() => setCameraAction(null)}
        />
      </Canvas>
    </div>
  )
}
