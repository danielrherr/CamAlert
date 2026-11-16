"""
CamAlert Configuration - Configuración centralizada para el sistema de monitoreo.

Maneja:
- Configuración de cámaras (host, credentials, stream type)
- Configuración de eventos y umbrales
- Configuración de alertas (canales, severidad, cooldown)
- Carga/guardado de configuración desde/archivo JSON
"""

import json
import logging
import subprocess
import ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Configuración de una cámara individual."""
    id: str
    name: str
    host: str
    mac_address: Optional[str] = None  # Dirección MAC para reservación DHCP
    username: Optional[str] = None
    password: Optional[str] = None
    stream_type: str = "main"  # "main" o "sub"
    port: int = 554
    enabled: bool = True
    zones: List[Dict[str, int]] = field(default_factory=list)  # Zonas de interés [{x, y, width, height}]
    last_seen: Optional[str] = None  # Cuando fue vista por última vez
    discovered: bool = False  # Fue encontrada via scan de red
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para serialización."""
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "mac_address": self.mac_address,
            "username": self.username,
            "password": self.password,
            "stream_type": self.stream_type,
            "port": self.port,
            "enabled": self.enabled,
            "zones": self.zones,
            "last_seen": self.last_seen,
            "discovered": self.discovered,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraConfig":
        """Crear desde diccionario."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", "Camera"),
            host=data.get("host", ""),
            mac_address=data.get("mac_address"),
            username=data.get("username"),
            password=data.get("password"),
            stream_type=data.get("stream_type", "main"),
            port=data.get("port", 554),
            enabled=data.get("enabled", True),
            zones=data.get("zones", []),
            last_seen=data.get("last_seen"),
            discovered=data.get("discovered", False),
        )


@dataclass
class EventConfig:
    """Configuración de detección de eventos."""
    motion_threshold: int = 25  # 0-255, umbral de diferencia de píxeles
    motion_min_area: int = 500  # Área mínima de movimiento en píxeles
    face_detection: bool = False
    zone_monitoring: bool = True
    zones: List[Dict[str, int]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "motion_threshold": self.motion_threshold,
            "motion_min_area": self.motion_min_area,
            "face_detection": self.face_detection,
            "zone_monitoring": self.zone_monitoring,
            "zones": self.zones,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventConfig":
        return cls(
            motion_threshold=data.get("motion_threshold", 25),
            motion_min_area=data.get("motion_min_area", 500),
            face_detection=data.get("face_detection", False),
            zone_monitoring=data.get("zone_monitoring", True),
            zones=data.get("zones", []),
        )


@dataclass
class AlertConfig:
    """Configuración de alertas."""
    enable_console: bool = True
    enable_email: bool = False
    enable_telegram: bool = False
    enable_webhook: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: List[str] = field(default_factory=list)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    webhook_url: str = ""
    webhook_headers: Dict[str, str] = field(default_factory=dict)
    min_interval_seconds: int = 30
    severity_threshold: str = "medium"  # low, medium, high, critical

    # Switch WiFi (Norlink SWIGRF-16a y compatibles)
    enable_switch: bool = False
    switch_host: str = ""
    switch_token: str = ""
    switch_id: str = "1"
    switch_severity_threshold: str = "high"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enable_console": self.enable_console,
            "enable_email": self.enable_email,
            "enable_telegram": self.enable_telegram,
            "enable_webhook": self.enable_webhook,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_username": self.smtp_username,
            "smtp_password": self.smtp_password,
            "email_from": self.email_from,
            "email_to": self.email_to,
            "telegram_bot_token": self.telegram_bot_token,
            "telegram_chat_id": self.telegram_chat_id,
            "webhook_url": self.webhook_url,
            "webhook_headers": dict(self.webhook_headers) if self.webhook_headers else {},
            "min_interval_seconds": self.min_interval_seconds,
            "severity_threshold": self.severity_threshold,
            "enable_switch": self.enable_switch,
            "switch_host": self.switch_host,
            "switch_token": self.switch_token,
            "switch_id": self.switch_id,
            "switch_severity_threshold": self.switch_severity_threshold,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlertConfig":
        return cls(
            enable_console=data.get("enable_console", True),
            enable_email=data.get("enable_email", False),
            enable_telegram=data.get("enable_telegram", False),
            enable_webhook=data.get("enable_webhook", False),
            smtp_host=data.get("smtp_host", "smtp.gmail.com"),
            smtp_port=data.get("smtp_port", 587),
            smtp_username=data.get("smtp_username", ""),
            smtp_password=data.get("smtp_password", ""),
            email_from=data.get("email_from", ""),
            email_to=data.get("email_to", []),
            telegram_bot_token=data.get("telegram_bot_token", ""),
            telegram_chat_id=data.get("telegram_chat_id", ""),
            webhook_url=data.get("webhook_url", ""),
            webhook_headers=data.get("webhook_headers", {}),
            min_interval_seconds=data.get("min_interval_seconds", 30),
            severity_threshold=data.get("severity_threshold", "medium"),
            enable_switch=data.get("enable_switch", False),
            switch_host=data.get("switch_host", ""),
            switch_token=data.get("switch_token", ""),
            switch_id=str(data.get("switch_id", "1")),
            switch_severity_threshold=data.get("switch_severity_threshold", "high"),
        )


@dataclass
class CamAlertConfig:
    """Configuración global de CamAlert."""
    version: str = "0.1.0"
    cameras: Dict[str, CameraConfig] = field(default_factory=dict)
    event: EventConfig = field(default_factory=EventConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "cameras": {k: v.to_dict() for k, v in self.cameras.items()},
            "event": self.event.to_dict(),
            "alerts": self.alerts.to_dict(),
            "last_updated": self.last_updated,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CamAlertConfig":
        return cls(
            version=data.get("version", "0.1.0"),
            cameras={
                k: CameraConfig.from_dict(v) 
                for k, v in data.get("cameras", {}).items()
            },
            event=EventConfig.from_dict(data.get("event", {})),
            alerts=AlertConfig.from_dict(data.get("alerts", {})),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
        )
    
    def save(self, path: Path) -> None:
        """Guardar configuración a archivo JSON."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Configuración guardada en {path}")
        except Exception as e:
            logger.error(f"Error guardando configuración: {e}")
            raise
    
    @classmethod
    def load(cls, path: Path) -> "CamAlertConfig":
        """Cargar configuración desde archivo JSON."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            config = cls.from_dict(data)
            logger.info(f"Configuración cargada desde {path}")
            return config
        except FileNotFoundError:
            logger.warning(f"Archivo de configuración no encontrado: {path}, usando defaults")
            return cls()
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            raise


# Default config path
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "camalert.json"


class NetworkDiscovery:
    """Herramientas para descubrir cámaras en la red local."""
    
    @staticmethod
    def _ping_ip(ip: str, timeout: float = 0.5) -> bool:
        """Ping simple para verificar si un IP está vivo."""
        try:
            # Usar -c 1 para un solo paquete, timeout rápido
            result = subprocess.run(
                ["ping", "-c", "1", "-W", str(timeout), ip],
                capture_output=True,
                timeout=timeout + 1
            )
            return result.returncode == 0
        except Exception:
            return False
    
    @staticmethod
    def discover_imou_cameras(network_prefix: str = "192.168.1") -> List[Dict[str, str]]:
        """
        Descubrir cámaras Imou en la red local.
        
        Escanea IPs en el rango y verifica aquellas que responden
        en el puerto RTSP (554) o HTTP (80) con headers de Imou.
        
        Returns:
            Lista de diccionarios con {'ip': str, 'mac': str, 'model': str}
        """
        cameras = []
        
        # Escaneo de rango completo (podría ser lento, así que limitado)
        # En producción usarían arp-scan o herramientas similares
        for i in range(2, 255):  # Empezar en 2 para evitar .0 y .255
            ip = f"{network_prefix}.{i}"
            
            if not NetworkDiscovery._ping_ip(ip):
                continue
            
            # Verificar puertos comunes de Imou
            for port in [554, 80]:
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.5)
                    result = sock.connect_ex((ip, port))
                    sock.close()
                    
                    if result == 0:
                        # Puerto abierto, verificar si es Imou
                        # Enviar petición HTTP mínima si es puerto 80
                        if port == 80:
                            try:
                                import urllib.request
                                req = urllib.request.Request(f"http://{ip}/")
                                resp = urllib.request.urlopen(req, timeout=1)
                                # Verificar headers de Imou
                                headers = resp.headers
                                server = headers.get('Server', '').lower()
                                if 'imou' in server or 'dahua' in server:
                                    # Probable cámara Imou/Dahua
                                    # Intentar obtener información MAC vía ARP (requiere permisos)
                                    mac = NetworkDiscovery._get_mac_address(ip)
                                    cameras.append({
                                        "ip": ip,
                                        "mac": mac or "unknown",
                                        "model": "Imou Camera"
                                    })
                                    break  # Ya la encontramos, pasar a próxima IP
                            except Exception:
                                pass
                        else:
                            # Puerto 554 (RTSP) - asumir cámara Imou
                            mac = NetworkDiscovery._get_mac_address(ip)
                            cameras.append({
                                "ip": ip,
                                "mac": mac or "unknown",
                                "model": "Imou Camera"
                            })
                            break
                except Exception:
                    continue
        
        # Remover duplicados manteniendo orden
        seen = set()
        unique_cameras = []
        for cam in cameras:
            key = cam["ip"]
            if key not in seen:
                seen.add(key)
                unique_cameras.append(cam)
        
        return unique_cameras
    
    @staticmethod
    def _get_mac_address(ip: str) -> Optional[str]:
        """
        Intentar obtener la dirección MAC de una IP usando ARP.
        Nota: Requiere permisos de root y puede no funcionar en todas redes.
        """
        try:
            # Usar arp -n para obtener entrada ARP
            result = subprocess.run(
                ["arp", "-n", ip],
                capture_output=True,
                text=True,
                timeout=2
            )
            lines = result.stdout.strip().split('\n')
            for line in lines:
                # Formato: "? (192.168.1.1) at 00:11:22:33:44:55 on eth0"
                if "at" in line and ip in line:
                    # Extraer dirección MAC después de "at"
                    parts = line.split("at")
                    if len(parts) > 1:
                        mac_part = parts[1].split()[0]
                        # Formato estándar XX:XX:XX:XX:XX:XX
                        return mac_part
        except Exception:
            pass
        return None
    
    @staticmethod
    def update_camera_config_from_discovery(
        config: "CamAlertConfig", 
        network_prefix: str = "192.168.1"
    ) -> Tuple[bool, Optional[str]]:
        """
        Intenta actualizar configuración de cámara usando descubrimiento en red.
        
        Returns:
            Tuple de (exito, ip_actualizada)
        """
        discovered_cameras = NetworkDiscovery.discover_imou_cameras(network_prefix)
        
        if not discovered_cameras:
            return False, None
        
        # Intentar matcher con cámaras configuradas
        for disc_cam in discovered_cameras:
            disc_ip = disc_cam["ip"]
            disc_mac = disc_cam["mac"].lower()
            
            # Buscar en config por MAC o IP
            for cam_key, cam_config in config.cameras.items():
                # Verificar si la IP cambió o MAC coincide
                if cam_config.host == disc_ip or (cam_config.mac_address and cam_config.mac_address.lower() == disc_mac):
                    # Actualizar host si cambió
                    if cam_config.host != disc_ip:
                        logger.info(f"Actualizando IP para {cam_config.name}: {cam_config.host} -> {disc_ip}")
                        cam_config.host = disc_ip
                        cam_config.last_seen = datetime.now().isoformat()
                        cam_config.discovered = True
                        return True, disc_ip
                    
                    # Solo actualizar timestamp si IP es misma
                    cam_config.last_seen = datetime.now().isoformat()
                    cam_config.discovered = True
                    return True, disc_ip
        
        return False, None