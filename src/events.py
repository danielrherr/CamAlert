"""
Event System - Detección y categorización de eventos de cámaras Imou.

Define los eventos que pueden desencadenar alertas:
- Movimiento detectado
- Intrusión en zona definida
- Pérdida de señal
- Detección de caras
- Áreas de interés cruzadas
"""

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Tipos de eventos que pueden detectarse."""
    MOTION = "motion"          # Movimiento detectado
    INTRUSION = "intrusion"    # Intrusión en zona definida
    ZONE_ENTRY = "zone_entry"  # Entrada a zona de interés
    ZONE_EXIT = "zone_exit"    # Salida de zona de interés
    FACE_DETECTED = "face_detected"  # Cara detectada
    SIGNAL_LOST = "signal_lost"  # Pérdida de señal de video
    RECORDING_START = "recording_start"  # Grabación iniciada
    RECORDING_STOP = "recording_stop"  # Grabación detenida


@dataclass
class BaseEvent:
    """Evento base con metadatos comunes."""
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir evento a diccionario para serialización."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "confidence": self.confidence,
        }


@dataclass
class MotionEvent(BaseEvent):
    """Evento de movimiento detectado."""
    event_type: EventType = EventType.MOTION
    motion_region: Optional[Dict[str, int]] = None  # {x, y, width, height}
    motion_score: float = 0.0  # Score de confianza 0-1
    pixel_change_percent: float = 0.0  # Percentual de píxeles cambiados


@dataclass
class IntrusionEvent(BaseEvent):
    """Evento de intrusión en zona definida."""
    event_type: EventType = EventType.INTRUSION
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    crossed_points: Optional[List[Dict[str, int]]] = None  # Puntos que cruzaron la zona


@dataclass
class ZoneEntryEvent(BaseEvent):
    """Evento de entrada a zona de interés."""
    event_type: EventType = EventType.ZONE_ENTRY
    zone_id: str = ""
    previous_zone: Optional[str] = None
    entry_position: Dict[str, int] = field(default_factory=lambda: {"x": 0, "y": 0})


@dataclass
class ZoneExitEvent(BaseEvent):
    """Evento de salida de zona de interés."""
    event_type: EventType = EventType.ZONE_EXIT
    zone_id: str = ""
    exit_position: Dict[str, int] = field(default_factory=lambda: {"x": 0, "y": 0})


@dataclass
class FaceDetectedEvent(BaseEvent):
    """Evento de cara detectada."""
    event_type: EventType = EventType.FACE_DETECTED
    face_id: Optional[str] = None
    known: bool = False  # Si la cara es conocida/registrada
    similarity: Optional[float] = None  # Similarity score si known=False


@dataclass
class SignalLostEvent(BaseEvent):
    """Evento de pérdida de señal de video."""
    event_type: EventType = EventType.SIGNAL_LOST
    duration: Optional[float] = None  # Duración sin señal (segundos)
    reconnected: bool = False


# Event handlers type
EventHandler = Callable[[BaseEvent], None]


class EventRegistry:
    """Registro de handlers para diferentes tipos de eventos."""
    
    def __init__(self):
        self._handlers: Dict[EventType, List[EventHandler]] = {
            event_type: [] for event_type in EventType
        }
    
    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Suscribir un handler para un tipo de evento."""
        if event_type in self._handlers:
            self._handlers[event_type].append(handler)
            logger.debug(f"Handler suscrito para evento {event_type.value}")
        else:
            logger.warning(f"Tipo de evento desconocido: {event_type}")
    
    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Desuscribir un handler."""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)
            logger.debug(f"Handler desuscrito para evento {event_type.value}")
    
    def emit(self, event: BaseEvent) -> None:
        """Emitir/despachar un evento a todos los handlers suscritos."""
        handlers = self._handlers.get(event.event_type, [])
        logger.info(f"Emitiendo evento {event.event_type.value}")
        
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error en handler de evento: {e}", exc_info=True)


# Registry global instance
event_registry = EventRegistry()


def on_motion(callback: Callable[[MotionEvent], None]) -> None:
    """Decorador para registrar handler de movimiento."""
    event_registry.subscribe(EventType.MOTION, lambda e: callback(e))


def on_intrusion(callback: Callable[[IntrusionEvent], None]) -> None:
    """Decorador para registrar handler de intrusión."""
    event_registry.subscribe(EventType.INTRUSION, lambda e: callback(e))


def on_zone_entry(callback: Callable[[ZoneEntryEvent], None]) -> None:
    """Decorador para registrar handler de entrada a zona."""
    event_registry.subscribe(EventType.ZONE_ENTRY, lambda e: callback(e))


def on_zone_exit(callback: Callable[[ZoneExitEvent], None]) -> None:
    """Decorador para registrar handler de salida de zona."""
    event_registry.subscribe(EventType.ZONE_EXIT, lambda e: callback(e))


def on_face_detected(callback: Callable[[FaceDetectedEvent], None]) -> None:
    """Decorador para registrar handler de cara detectada."""
    event_registry.subscribe(EventType.FACE_DETECTED, lambda e: callback(e))


def on_signal_lost(callback: Callable[[SignalLostEvent], None]) -> None:
    """Decorador para registrar handler de pérdida de señal."""
    event_registry.subscribe(EventType.SIGNAL_LOST, lambda e: callback(e))