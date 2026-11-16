"""
Discovery Manager - Reconexión híbrida de cámaras Imou.

Proporciona:
- Conexión directa con la IP configurada (camino rápido)
- Descubrimiento en red cuando la IP cambió (DHCP)
- Match por MAC (identificador estable), nunca por "primera cámara encontrada"
- Estado por cámara: última IP conocida, timestamp, estabilidad, reintentos
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.config import CameraConfig, NetworkDiscovery

logger = logging.getLogger(__name__)


@dataclass
class CameraIPState:
    """Estado de IP de una cámara a lo largo del tiempo."""
    last_known_ip: str = ""
    discovery_timestamp: Optional[datetime] = None
    ip_stable: bool = True
    retry_count: int = 0


class DiscoveryManager:
    """Decide entre conexión directa y descubrimiento en red."""

    def __init__(
        self,
        network_prefix: str = "192.168.1",
        scanner: Optional[Callable[[str], List[Dict[str, str]]]] = None,
        stable_after_checks: int = 3,
    ):
        self.network_prefix = network_prefix
        self.scanner = scanner or NetworkDiscovery.discover_imou_cameras
        self.stable_after_checks = stable_after_checks
        self._states: Dict[str, CameraIPState] = {}

    def state_for(self, camera_id: str) -> CameraIPState:
        """Obtener (creando si hace falta) el estado de una cámara."""
        if camera_id not in self._states:
            self._states[camera_id] = CameraIPState()
        return self._states[camera_id]

    def check_and_reconnect(
        self,
        cam_config: CameraConfig,
        connect: Callable[[CameraConfig], Any],
    ) -> Tuple[Any, bool]:
        """
        Conectar la cámara: directa primero, descubrimiento después.

        Args:
            cam_config: configuración de la cámara (se actualiza el host si cambia).
            connect: callable que recibe la CameraConfig y devuelve un cliente o lanza.

        Returns:
            (cliente | None, discovered: bool)
        """
        state = self.state_for(cam_config.id)

        # Intento 1: IP configurada
        try:
            client = connect(cam_config)
        except Exception as exc:
            logger.warning(f"✗ Fallo conexión directa ({cam_config.host}): {exc}")
            state.retry_count += 1
            if state.retry_count >= self.stable_after_checks:
                state.ip_stable = False
        else:
            state.last_known_ip = cam_config.host
            state.retry_count = 0
            state.ip_stable = True
            logger.info(f"✓ Cámara conectada con IP configurada: {cam_config.name} ({cam_config.host})")
            return client, False

        # Intento 2: descubrimiento en red, match por MAC
        logger.info(f"🔍 Intentando descubrimiento en red para {cam_config.name}...")
        if not cam_config.mac_address:
            logger.error(
                f"✗ {cam_config.name} sin MAC configurada: descubrimiento imposible (no se asigna una cámara arbitraria)"
            )
            return None, False

        wanted_mac = cam_config.mac_address.lower()
        try:
            discovered = self.scanner(self.network_prefix)
        except Exception as exc:
            logger.error(f"✗ Error durante descubrimiento en red: {exc}")
            return None, False

        match = next(
            (cam for cam in discovered if str(cam.get("mac", "")).lower() == wanted_mac),
            None,
        )
        if match is None:
            logger.error(f"✗ No se encontró la cámara {cam_config.name} (MAC {cam_config.mac_address}) en la red")
            return None, False

        new_ip = match["ip"]
        old_ip = cam_config.host
        if new_ip != old_ip:
            logger.info(f"✓ IP actualizada para {cam_config.name}: {old_ip} -> {new_ip}")
        cam_config.host = new_ip
        cam_config.last_seen = datetime.now().isoformat()
        cam_config.discovered = True
        state.discovery_timestamp = datetime.now()
        state.last_known_ip = new_ip

        # Intento 3: reconectar con la IP descubierta
        try:
            client = connect(cam_config)
        except Exception as exc:
            logger.error(f"✗ Cámara descubierta en {new_ip} pero no conecta: {exc}")
            return None, False

        state.retry_count = 0
        logger.info(f"✓ Cámara reconectada tras descubrimiento: {cam_config.name} ({new_ip})")
        return client, True
