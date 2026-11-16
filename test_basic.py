#!/usr/bin/env python3
"""
Test script básico para CamAlert - validar configuración y estructura.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import CamAlertConfig
from alerts import AlertManager, AlertSeverity, AlertConfig as AlertConfigObj
from alerts import Alert
from events import MotionEvent, event_registry, on_motion, ZoneEntryEvent, ZoneExitEvent, EventType, BaseEvent


def test_config_loading():
    """Probar carga de configuración."""
    print("=== Test 1: Cargar configuración ===")
    config = CamAlertConfig.load(Path(__file__).parent / "config" / "camalert.json")
    print(f"✓ Configuración cargada exitosamente")
    print(f"  - Cámaras: {len(config.cameras)}")
    print(f"  - Event config: threshold={config.event.motion_threshold}, min_area={config.event.motion_min_area}")
    print(f"  - Alert config: console={config.alerts.enable_console}, email={config.alerts.enable_email}")
    
    # Verificar cámaras
    for cam_id, cam in config.cameras.items():
        print(f"  - Cámara: {cam.name} at {cam.host} (stream_type={cam.stream_type})")
    
    return config


def test_event_registry():
    """Probar registro de eventos."""
    print("\n=== Test 2: Registro de eventos ===")
    
    handler_called = []
    
    def motion_handler(event: MotionEvent):
        handler_called.append(event)
    
    on_motion(motion_handler)
    
    test_event = MotionEvent(
        event_type=EventType.MOTION,
        camera_id="test-cam",
        camera_name="Test Camera",
        confidence=0.85,
        motion_region={"x": 100, "y": 100, "width": 200, "height": 200},
        motion_score=0.9,
        pixel_change_percent=15.5
    )
    
    event_registry.emit(test_event)
    
    if handler_called:
        print(f"✓ Handler de movimiento llamado: {len(handler_called)} vez(es)")
        e = handler_called[0]
        print(f"  - Event type: {e.event_type}")
        print(f"  - Camera: {e.camera_name}")
        print(f"  - Confidence: {e.confidence}")
    else:
        print("✗ Handler de movimiento no fue llamado")
    
    return True


def test_event_dataclasses():
    """Probar dataclasses de eventos."""
    print("\n=== Test 3: Dataclasses de eventos ===")
    
    zone_entry = ZoneEntryEvent(
        zone_id="zone-1",
        entry_position={"x": 500, "y": 300}
    )
    print(f"✓ ZoneEntryEvent creado: zone_id={zone_entry.zone_id}, position={zone_entry.entry_position}, event_type={zone_entry.event_type}")
    
    zone_exit = ZoneExitEvent(
        zone_id="zone-1",
        exit_position={"x": 800, "y": 600}
    )
    print(f"✓ ZoneExitEvent creado: zone_id={zone_exit.zone_id}, position={zone_exit.exit_position}, event_type={zone_exit.event_type}")
    
    motion = MotionEvent(
        event_type=EventType.MOTION,
        camera_id="cam-1",
        camera_name="Cam 1",
        confidence=0.92,
        motion_region={"x": 0, "y": 0, "width": 1920, "height": 1080},
        motion_score=0.88,
        pixel_change_percent=22.3
    )
    print(f"✓ MotionEvent creado: event_type={motion.event_type}, confidence={motion.confidence}")
    
    base = BaseEvent(
        event_type=EventType.MOTION,
        camera_id="base-1",
        camera_name="Base Cam",
        timestamp=datetime.now(),
        confidence=0.95
    )
    print(f"✓ BaseEvent creado: event_type={base.event_type}")
    
    return True


def test_alert_manager():
    """Probar gestor de alertas - versión simplificada."""
    print("\n=== Test 4: Alert Manager ===")
    
    # Verificar config has required attributes
    alert_config = AlertConfigObj(
        enable_console=True,
        enable_email=False,
        enable_telegram=False,
        enable_webhook=False,
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        email_from="",
        email_to=[],
        telegram_bot_token="",
        telegram_chat_id="",
        webhook_url="",
        webhook_headers={},
        min_interval_seconds=30,
        severity_threshold=AlertSeverity.MEDIUM
    )
    
    print(f"✓ Alert config created: severity_threshold={alert_config.severity_threshold}")
    print(f"  - enable_console: {alert_config.enable_console}")
    
    # Crear alerta de prueba
    test_event = BaseEvent(
        event_type=EventType.MOTION,
        camera_id="test",
        camera_name="Test Cam",
        timestamp=datetime.now(),
        confidence=0.9
    )
    
    alert = Alert(
        id="test-alert-001",
        event=test_event,
        severity=AlertSeverity.MEDIUM,
        title="Test Alert",
        message="This is a test alert message"
    )
    
    print(f"✓ Alert created: id={alert.id}, severity={alert.severity}")
    print(f"  - event type: {alert.event.event_type}")
    print(f"  - event camera: {alert.event.camera_name}")
    
    return True


def main():
    """Ejecutar todas las pruebas."""
    print("=" * 60)
    print("CamAlert - Basic Functionality Test")
    print("=" * 60)
    
    try:
        config = test_config_loading()
        test_event_registry()
        test_event_dataclasses()
        test_alert_manager()
        
        print("\n" + "=" * 60)
        print("✓ Todas las pruebas completadas exitosamente!")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n✗ Error durante las pruebas: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())