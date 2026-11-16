#!/usr/bin/env python3
"""
CamAlert - Monitoreo en tiempo real de cámaras Imou.

Sistema principal que coordina:
1. Conexión RTSP a cámaras Imou (bullet 2e, cruiser se+)
2. Reconexión híbrida: IP configurada -> descubrimiento en red por MAC
3. Detección de eventos (movimiento, intrusión, zonas)
4. Disparo de alertas configurables (console, email, telegram, webhook, switch WiFi)
"""

import asyncio
import logging
import signal
import socket
import sys
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path

# Add src to path (permite ejecutar `python3 main.py` desde la raíz)
sys.path.insert(0, str(Path(__file__).parent))

from src.imou_client import ImouCameraClient
from src.events import MotionEvent, on_motion
from src.alerts import Alert, AlertManager, AlertSeverity
from src.config import CamAlertConfig, CameraConfig
from src.discovery_manager import DiscoveryManager
from src.switch_controller import SwitchController, SmartSwitch

# Default config path - defined early for use in function defaults
DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "camalert.json"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("CamAlert")


# Global state
camera_clients: Dict[str, ImouCameraClient] = {}
alert_manager: Optional[AlertManager] = None
discovery_manager: Optional[DiscoveryManager] = None
config: Optional[CamAlertConfig] = None
running = True


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> CamAlertConfig:
    """Cargar configuración desde archivo."""
    global config
    config = CamAlertConfig.load(config_path)
    logger.info(f"Configuración cargada: {len(config.cameras)} cámaras configuradas")
    return config


def setup_alert_manager() -> None:
    """Configurar el gestor de alertas con la configuración actual."""
    global alert_manager
    if config is None:
        raise ValueError("Configuración no cargada")

    from src.alerts import AlertConfig as AlertConfigObj

    alert_config = AlertConfigObj(
        enable_console=config.alerts.enable_console,
        enable_email=config.alerts.enable_email,
        enable_telegram=config.alerts.enable_telegram,
        enable_webhook=config.alerts.enable_webhook,
        smtp_host=config.alerts.smtp_host,
        smtp_port=config.alerts.smtp_port,
        smtp_username=config.alerts.smtp_username,
        smtp_password=config.alerts.smtp_password,
        email_from=config.alerts.email_from,
        email_to=config.alerts.email_to,
        telegram_bot_token=config.alerts.telegram_bot_token,
        telegram_chat_id=config.alerts.telegram_chat_id,
        webhook_url=config.alerts.webhook_url,
        webhook_headers=config.alerts.webhook_headers,
        min_interval_seconds=config.alerts.min_interval_seconds,
        severity_threshold=config.alerts.severity_threshold,
        enable_switch=config.alerts.enable_switch,
        switch_host=config.alerts.switch_host,
        switch_token=config.alerts.switch_token,
        switch_id=config.alerts.switch_id,
        switch_severity_threshold=config.alerts.switch_severity_threshold,
    )

    alert_manager = AlertManager(alert_config)
    if alert_manager.switch_controller is not None:
        logger.info(
            f"Gestor de alertas configurado con switch {config.alerts.switch_host} "
            f"(threshold {alert_manager.config.switch_severity_threshold.value})"
        )
    else:
        logger.info("Gestor de alertas configurado (switch deshabilitado)")


def _probe_camera(camera_config: CameraConfig) -> str:
    """Verificación síncrona rápida de que la cámara responde en su puerto RTSP."""
    with socket.create_connection(
        (camera_config.host, camera_config.port), timeout=2
    ):
        return camera_config.host


async def connect_camera(camera_config: CameraConfig) -> Optional[ImouCameraClient]:
    """
    Conectar cámara de forma inteligente: IP configurada primero,
    descubrimiento en red (match por MAC) si la IP cambió.
    """
    if discovery_manager is None:
        raise RuntimeError("DiscoveryManager no inicializado")

    host, discovered = discovery_manager.check_and_reconnect(
        camera_config, _probe_camera
    )

    if host is None:
        camera_config.discovered = False
        logger.error(f"✗ No se pudo conectar la cámara {camera_config.name}")
        return None

    client = ImouCameraClient(
        host=camera_config.host,
        username=camera_config.username or "admin",
        password=camera_config.password or "admin",
        stream_type=camera_config.stream_type,
        port=camera_config.port,
    )
    try:
        await client.start()
    except Exception as exc:
        camera_config.discovered = False
        logger.error(f"✗ Cámara {camera_config.name} responde pero no entrega stream: {exc}")
        return None

    camera_config.last_seen = datetime.now().isoformat()
    camera_config.discovered = True
    camera_clients[camera_config.id] = client
    logger.info(
        f"✓ Cámara conectada: {camera_config.name} ({camera_config.host})"
        f"{' [descubierta]' if discovered else ''}"
    )
    return client


def on_motion_event(event: MotionEvent) -> None:
    """Handler para eventos de movimiento: genera alerta asíncrona."""
    logger.info(
        f"Evento de movimiento detectado: {event.camera_name} (confidence={event.confidence:.2f})"
    )
    if alert_manager is None:
        return

    alert = Alert(
        id=f"{event.camera_id}-{int(event.timestamp.timestamp())}",
        event=event,
        severity=AlertSeverity.HIGH,
        title=f"Movimiento detectado: {event.camera_name}",
        message=(
            f"Movimiento en {event.camera_name} "
            f"(confidence={event.confidence:.2f}, cambio={event.pixel_change_percent:.1f}%)"
        ),
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("Sin event loop activo, alerta de movimiento descartada")
        return
    loop.create_task(alert_manager.send(alert))


def signal_handler(signum, frame) -> None:
    """Manejar señales de salida graceful."""
    global running
    logger.info(f"Recibida señal {signum}, deteniendo sistema...")
    running = False


async def main() -> None:
    """Función principal del sistema CamAlert."""
    global running, config, alert_manager, discovery_manager

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=== CamAlert Starting ===")
    logger.info("Sistema de monitoreo de cámaras Imou")

    try:
        load_config()
    except Exception:
        logger.error("No se pudo cargar la configuración, saliendo...")
        return

    setup_alert_manager()
    discovery_manager = DiscoveryManager()
    on_motion(on_motion_event)

    if not config.cameras:
        logger.warning("No hay cámaras configuradas. Agregue cámaras al config.")
        return

    for camera_id, camera_config in config.cameras.items():
        if not camera_config.enabled:
            logger.info(f"Cámara {camera_config.name} deshabilitada, se omite")
            continue
        await connect_camera(camera_config)

    logger.info("=== CamAlert Running ===")
    logger.info(f"Monitoreando {len(camera_clients)} cámara(s)")

    try:
        while running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Tarea cancelada")
    finally:
        logger.info("Deteniendo todas las cámaras...")
        for camera_id, client in camera_clients.items():
            try:
                await client.stop()
            except Exception as exc:
                logger.debug(f"Error deteniendo {camera_id}: {exc}")
        if alert_manager and alert_manager.switch_controller:
            await alert_manager.switch_controller.shutdown()
        logger.info("=== CamAlert Stopped ===")


if __name__ == "__main__":
    asyncio.run(main())
