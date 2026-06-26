from django.urls import path

from apps.api import views


urlpatterns = [
    path("health", views.health, name="health"),
    path("digital-twin/segments", views.digital_twin_segments, name="digital_twin_segments"),
    path("digital-twin/graph", views.digital_twin_graph, name="digital_twin_graph"),
    path("digital-twin/pointcloud", views.digital_twin_pointcloud, name="digital_twin_pointcloud"),
    path("workers", views.workers, name="workers"),
    path("risk/segments", views.risk_segments, name="risk_segments"),
    path("risk/geometry", views.geometry_risk, name="geometry_risk"),
    path("risk/environmental", views.environmental_risk, name="environmental_risk"),
    path("gas-sensors", views.gas_sensors, name="gas_sensors"),
    path("simulation/state", views.simulation_state, name="simulation_state"),
    path("simulation/trapped", views.simulation_trapped, name="simulation_trapped"),
    path("scenarios/collapse", views.collapse_scenario, name="collapse_scenario"),
    path("routes/emergency", views.emergency_route, name="emergency_route"),
]
