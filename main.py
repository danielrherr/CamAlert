#!/usr/bin/env python3
"""
CamAlert - Monitoreo en tiempo real de cámaras Imou.

Sistema principal que coordina:
1. Conexión RTSP a cámaras Imou (bullet 2e, cruiser se+)
2. Detección de eventos (movimiento, intrusión, zonas)
3. Disparo de alertas configurables (console, email, telegram, webhook)
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, Optional
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from imou_client import ImouCameraClient, ImouCameraError
from events import EventType
from alerts import AlertManager, AlertSeverity
from config import CamAlertConfig, NetworkDiscovery

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
camera_clients: Dict[str, "ImouCameraClient"] = {}
alert_manager: Optional["AlertManager"] = None
config: Optional["CamAlertConfig"] = None
running = True


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> "CamAlertConfig":
    """Cargar configuración desde archivo."""
    global config
    try:
        config = CamAlertConfig.load(config_path)
        logger.info(f"Configuración cargada: {len(config.cameras)} cámaras configuradas")
        return config
    except Exception as e:
        logger.error(f"Error cargando configuración: {e}")
        raise


def setup_alert_manager() -> None:
    """Configurar el gestor de alertas con la configuración actual."""
    global alert_manager
    if config is None:
        raise ValueError("Configuración no cargada")

    from alerts import AlertConfig as AlertConfigObj

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
    )

    alert_manager = AlertManager(alert_config)
    logger.info("Gestor de alertas configurado")


def smart_connect_camera(camera_config: "CameraConfig") -> Optional["ImouCameraClient"]:
    """
    Conectar cámara inteligente: intenta conexión directa,
    si falla, intenta descubrimiento en red y actualiza configuración.
    
    Returns:
        Cliente conectado o None si falla todo
    """
    from imou_client import ImouCameraClient
    
    # Intento 1: Conexión con IP configurada
    try:
        client = ImouCameraClient(
            host=camera_config.host,
            username=camera_config.username or "admin",
            password=camera_config.password or "admin",
            stream_type=camera_config.stream_type,
            port=camera_config.port,
        )
        await client.start()
        camera_config.last_seen = datetime.now().isoformat()
        camera_config.discovered = True
        camera_clients[camera_config.id] = client
        logger.info(f"✓ Cámara conectada con IP configurada: {camera_config.name} ({camera_config.host})")
        return client
    except ImouCameraError as e:
        logger.warning(f"✗ Fallo conexión con IP configurada ({camera_config.host}): {e}")
    except Exception as e:
        logger.warning(f"✗ Error inesperado conectando ({camera_config.host}): {e}")
    
    # Intento 2: Descubrimiento en red
    logger.info(f"🔍 Intentando descubrimiento en red para {camera_config.name}...")
    try:
        discovered = NetworkDiscovery.discover_imou_cameras()
        
        if not discovered:
            logger.error("✗ No se encontraron cámaras en la red")
            return None
        
        # Buscar coincidencia con cámaras configuradas por MAC o IP conocida
        matched = False
        for disc_cam in discovered:
            disc_ip = disc_cam["ip"]
            disc_mac = disc_cam.get("mac", "").lower()
            
            # Verificar por MAC address (más robusto)
            if camera_config.mac_address and camera_config.mac_address.lower() == disc_mac:
                logger.info(f"✓ Cámara encontrada por MAC: {disc_ip}")
                camera_config.host = disc_ip
                camera_config.last_seen = datetime.now().isoformat()
                camera_config.discovered = True
                
                client = ImouCameraClient(
                    host=disc_ip,
                    username=camera_config.username or "admin",
                    password=camera_config.password or "admin",
                    stream_type=camera_config.stream_type,
                    port=camera_config.port,
                )
                await client.start()
                camera_clients[camera_config.id] = client
                logger.info(f"✓ Cámara reconectada después de descubrimiento: {camera_config.name} ({disc_ip})")
                return client
            
            # Verificar por nombre de cámara en el descubrimiento (si estuviera incluido)
            # Por ahora, usar primera cámara descoincidente que no esté en uso
            if not matched:
                matched = True
                logger.info(f"✓ Usando cámara descobertada: {disc_ip}")
                camera_config.host = disc_ip
                camera_config.last_seen = datetime.now().isoformat()
                camera_config.discovered = True
                
                client = ImouCameraClient(
                    host=disc_ip,
                    username=camera_config.username or "admin",
                    password=camera_config.password or "admin",
                    stream_type=camera_config.stream_type,
                    port=camera_config.port,
                )
                await client.start()
                camera_clients[camera_config.id] = client
                logger.info(f"✓ Cámara reconectada con IP descoberta: {camera_config.name} ({disc_ip})")
                return client
        
        # Si tenemos solo una cámara descobertada y coincide por IP conocida
        if len(discovered) == 1:
            disc_ip = discovered[0]["ip"]
            if camera_config.host != disc_ip:
                logger.info(f"✓ IP changed, updating: {camera_config.host} -> {disc_ip}")
                camera_config.host = disc_ip
                camera_config.last_seen = datetime.now().isoformat()
                camera_config.discovered = True
                
                client = ImouCameraClient(
                    host=disc_ip,
                    username=camera_config.username or "admin",
                    password=camera_config.password or "admin",
                    stream_type=camera_config.stream_type,
                    port=camera_config.port,
                )
                await client.start()
                camera_clients[camera_config.id] = client
                logger.info(f"✓ Cámara reconectada: {camera_config.name} ({disc_ip})")
                return client
        
    except Exception as e:
        logger.error(f"✗ Error durante descubrimiento en red: {e}")
    
    # Intento 3: Si falló todo, mantener IP original pero marcar para configuración manual
    logger.error("✗ No se pudo conectar la cámara, requiere configuración manual")
    camera_config.discovered = False
    return None


def setup_camera(camera_config: "CameraConfig") -> "ImouCameraClient":
    """Configurar y crear un cliente de cámara usando conexión inteligente."""
    import asyncio
    
    client = asyncio.run(smart_connect_camera(camera_config))
    
    if client is None:
        # Marcar como no descubierta para indicar al usuario
        camera_config.discovered = False
        logger.warning(f"Cámara {camera_config.name} no pudo conectarse automáticamente")
    
    return client


def on_motion_event(event: "MotionEvent") -> None:
    """Handler para eventos de movimiento."""
    logger.info(f"Evento de movimiento detectado: confidence={event.confidence:.2f}")

    # Crear alerta si hay gestor configurado
    if alert_manager:
        # Ejecutar de forma async para no bloquear
        pass  # Se lanzaría tarea async en producción


def start_all_cameras() -> None:
    """Iniciar todas las cámaras configuradas."""
    logger.info("Iniciando todas las cámaras configuradas...")

    for camera_id, client in camera_clients.items():
        if not client._running:
            try:
                # Importar async aquí para evitar circular
                import asyncio
                asyncio.create_task(client.start())
                logger.info(f"Conexión iniciada para {camera_id}")
            except Exception as e:
                logger.error(f"Error conectando cámara {camera_id}: {e}")


def signal_handler(signum, frame) -> None:
    """Manejar señales de salida graceful."""
    global running
    logger.info(f"Recibida señal {signum}, deteniendo sistema...")
    running = False


async def main() -> None:
    """Función principal del sistema CamAlert."""
    global running, config, alert_manager

    # Registrar handlers de señal
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=== CamAlert Starting ===")
    logger.info("Sistema de monitoreo de cámaras Imou")

    # Cargar configuración
    try:
        config = load_config()
    except Exception as e:
        logger.error("No se pudo cargar la configuración, saliendo...")
        return

    # Configurar alertas
    setup_alert_manager()

    # Configurar handlers de eventos
    from events import on_motion
    on_motion(on_motion_event)

    # Configurar cámaras
    if config.cameras:
        for camera_id, camera_config in config.cameras.items():
            setup_camera(camera_config)
    else:
        logger.warning("No hay cámaras configuradas. Agregue cámaras al config.")

    # Iniciar todas las cámaras
    start_all_cameras()

    logger.info("=== CamAlert Running ===")
    logger.info(f"Monitoreando {len(camera_clients)} cámara(s)")

    # Bucle principal - mantener vivo el sistema
    try:
        while running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Tarea cancelada")
    finally:
        # Detener todas las cámaras
        logger.info("Deteniendo todas las cámaras...")
        for camera_id, client in camera_clients.items():
            try:
                import asyncio
                asyncio.create_task(client.stop())
            except Exception:
                pass

        logger.info("=== CamAlert Stopped ===")


if __name__ == "__main__":
    asyncio.run(main())