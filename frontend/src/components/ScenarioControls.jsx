export default function ScenarioControls({ scenarios, activeScenarioId, onSelectScenario }) {
  return (
    <div className="scenario-controls">
      {scenarios.map((scenario) => (
        <button
          key={scenario.scenario_id}
          className={`scenario-button ${activeScenarioId === scenario.scenario_id ? 'scenario-button--active' : ''}`}
          onClick={() => onSelectScenario(scenario.scenario_id)}
          title={scenario.description}
        >
          {scenario.label}
        </button>
      ))}
    </div>
  )
}
