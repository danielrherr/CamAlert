"""
Alert System - Disparo y gestión de alertas para eventos de cámaras Imou.

Sistema de alertas con múltiples canales de notificación:
- Notificaciones locales (console, file)
- Notificaciones remotas (email, telegram, webhook)
- Filtro por nivel de severidad
- Cooldown entre alertas
"""

import logging
import asyncio
import smtplib
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime, timedelta
from pathlib import Path

from src.events import BaseEvent

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Niveles de severidad de alerta."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Estado de una alerta."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DISMISSED = "dismissed"


@dataclass
class Alert:
    """Representa una alerta generada por un evento."""
    id: str
    event: BaseEvent
    severity: AlertSeverity
    title: str
    message: str
    status: AlertStatus = AlertStatus.PENDING
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def mark_sent(self) -> None:
        """Marcar alerta como enviada."""
        self.status = AlertStatus.SENT
        self.sent_at = datetime.now()
    
    def mark_failed(self, error: str) -> None:
        """Marcar alerta como fallida."""
        self.status = AlertStatus.FAILED
        self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir alerta a diccionario."""
        return {
            "id": self.id,
            "event": self.event.to_dict() if self.event else None,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "status": self.status.value,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class AlertConfig:
    """Configuración del sistema de alertas."""
    enable_console: bool = True
    enable_email: bool = False
    enable_telegram: bool = False
    enable_webhook: bool = False
    
    # Email config
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: List[str] = field(default_factory=list)
    
    # Telegram config
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    # Webhook config
    webhook_url: str = ""
    webhook_headers: Dict[str, str] = field(default_factory=dict)
    
    # Throttling
    min_interval_seconds: int = 30  # Mínimo tiempo entre alertas mismas severidad
    cooldown_by_event_type: Dict[str, int] = field(default_factory=dict)  # event_type -> seconds
    
    # Severity thresholds
    severity_threshold: AlertSeverity = AlertSeverity.MEDIUM  # Minimum severity to trigger


@dataclass
class AlertResult:
    """Resultado del envío de una alerta."""
    alert_id: str
    success: bool
    channel: str
    response: Optional[Dict[str, Any]] = None


class AlertManager:
    """Gestor de alertas con múltiples canales de notificación."""
    
    def __init__(self, config: AlertConfig):
        self.config = config
        self._sent_timestamps: Dict[str, datetime] = {}  # alert_id -> timestamp
        self._event_cooldowns: Dict[str, datetime] = {}  # event_type_timestamp
        
    def _check_cooldown(self, alert: Alert, event_type: str) -> bool:
        """Verificar si pasó suficiente tiempo desde la última alerta similar."""
        now = datetime.now()
        
        # Verificar intervalo mínimo
        if alert.id in self._sent_timestamps:
            last_sent = self._sent_timestamps[alert.id]
            min_interval = timedelta(seconds=self.config.min_interval_seconds)
            if now - last_sent < min_interval:
                logger.debug(f"Cooldown activo para alerta {alert.id}")
                return False
        
        # Verificar cooldown por tipo de evento
        if event_type in self.config.cooldown_by_event_type:
            cooldown_key = f"{event_type}_{alert.event.event_type.value}"
            if cooldown_key in self._event_cooldowns:
                last_cooldown = self._event_cooldowns[cooldown_key]
                cooldown_seconds = self.config.cooldown_by_event_type[event_type]
                if now - last_cooldown < timedelta(seconds=cooldown_seconds):
                    logger.debug(f"Cooldown por evento {event_type}")
                    return False
        
        return True
    
    async def send(self, alert: Alert) -> AlertResult:
        """Enviar alerta por todos los canales configurados."""
        if not self._should_send(alert):
            return AlertResult(alert_id=alert.id, success=False, channel="skipped")
        
        if not self._check_cooldown(alert, alert.event.event_type.value):
            return AlertResult(alert_id=alert.id, success=False, channel="cooldown")
        
        results = []
        
        # Console
        if self.config.enable_console:
            result = await self._send_console(alert)
            results.append(result)
        
        # Email
        if self.config.enable_email:
            result = await self._send_email(alert)
            results.append(result)
        
        # Telegram
        if self.config.enable_telegram:
            result = await self._send_telegram(alert)
            results.append(result)
        
        # Webhook
        if self.config.enable_webhook:
            result = await self._send_webhook(alert)
            results.append(result)
        
        # Actualizar estado basado en resultados
        all_success = all(r.success for r in results)
        
        if all_success and results:
            alert.mark_sent()
            self._sent_timestamps[alert.id] = datetime.now()
        else:
            # Marcar como fallida si algún canal falló
            failure_reasons = [r.error or "unknown" for r in results if not r.success]
            alert.mark_failed("; ".join(failure_reasons))
        
        return AlertResult(alert_id=alert.id, success=all_success, channel=", ".join(r.channel for r in results))
    
    def _should_send(self, alert: Alert) -> bool:
        """Verificar si la alerta debería enviarse basándose en severidad."""
        if alert.severity.value < self.config.severity_threshold.value:
            logger.debug(
                f"Alerta {alert.id} abaixo del threshold {self.config.severity_threshold.value}: {alert.severity.value}"
            )
            return False
        return True
    
    async def _send_console(self, alert: Alert) -> AlertResult:
        """Enviar alerta a consola."""
        try:
            log_msg = f"[ALERT {alert.severity.value.upper()}] {alert.title}: {alert.message}"
            logger.warning(log_msg)
            print(log_msg)  # Also print to stdout
            return AlertResult(alert_id=alert.id, success=True, channel="console")
        except Exception as e:
            logger.error(f"Error sending console alert: {e}")
            return AlertResult(alert_id=alert.id, success=False, channel="console", error=str(e))
    
    async def _send_email(self, alert: Alert) -> AlertResult:
        """Enviar alerta por email."""
        if not all([self.config.smtp_username, self.config.smtp_password, 
                     self.config.email_from, self.config.email_to]):
            return AlertResult(alert_id=alert.id, success=False, channel="email", 
                              error="Configuración email incompleta")
        
        try:
            import email.message
            
            msg = email.message.EmailMessage()
            msg["Subject"] = f"[CamAlert] {alert.severity.value.upper()}: {alert.title}"
            msg["From"] = self.config.email_from
            msg["To"] = ", ".join(self.config.email_to)
            msg.set_content(f"""
            
            Alert Details:
            - Severity: {alert.severity.value}
            - Event: {alert.event.event_type.value if alert.event else "N/A"}
            - Camera: {alert.event.camera_name if alert.event else "N/A"}
            - Timestamp: {alert.event.timestamp.isoformat() if alert.event else "N/A"}
            - Message: {alert.message}
            
            """)
            
            async with asyncio.timeout(10):
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: smtplib.SMTP(self.config.smtp_host, self.config.smtp_port).starttls()
                    .login(self.config.smtp_username, self.config.smtp_password)
                    .send_message(msg)
                )
            
            return AlertResult(alert_id=alert.id, success=True, channel="email")
        except Exception as e:
            logger.error(f"Error sending email alert: {e}")
            return AlertResult(alert_id=alert.id, success=False, channel="email", error=str(e))
    
    async def _send_telegram(self, alert: Alert) -> AlertResult:
        """Enviar alerta por Telegram."""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return AlertResult(alert_id=alert.id, success=False, channel="telegram",
                              error="Configuración telegram incompleta")
        
        try:
            import aiohttp
            
            payload = {
                "chat_id": self.config.telegram_chat_id,
                "text": f"*CamAlert*\\n*Severity*: {alert.severity.value}\\n*Event*: {alert.event.event_type.value if alert.event else 'N/A'}\\n*Message*: {alert.message}",
                "parse_mode": "Markdown"
            }
            
            async with asyncio.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage",
                        json=payload
                    ) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            return AlertResult(alert_id=alert.id, success=False, channel="telegram",
                                              error=f"Telegram API error: {text}")
            
            return AlertResult(alert_id=alert.id, success=True, channel="telegram")
        except ImportError:
            return AlertResult(alert_id=alert.id, success=False, channel="telegram",
                              error="aiohttp no instalado")
        except Exception as e:
            logger.error(f"Error sending telegram alert: {e}")
            return AlertResult(alert_id=alert.id, success=False, channel="telegram", error=str(e))
    
    async def _send_webhook(self, alert: Alert) -> AlertResult:
        """Enviar alerta por webhook."""
        if not self.config.webhook_url:
            return AlertResult(alert_id=alert.id, success=False, channel="webhook",
                              error="URL webhook vacía")
        
        try:
            import aiohttp
            
            payload = {
                "alert_id": alert.id,
                "severity": alert.severity.value,
                "event": alert.event.event_type.value if alert.event else "N/A",
                "message": alert.message,
                "timestamp": alert.event.timestamp.isoformat() if alert.event else datetime.now().isoformat(),
                "camera": alert.event.camera_name if alert.event else "N/A",
            }
            payload.update(alert.event.metadata if alert.event else {})
            
            async with asyncio.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.config.webhook_url,
                        json=payload,
                        headers=self.config.webhook_headers
                    ) as resp:
                        if resp.status != 200:
                            text = await resp.text()
                            return AlertResult(alert_id=alert.id, success=False, channel="webhook",
                                              error=f"Webhook error {resp.status}: {text}")
            
            return AlertResult(alert_id=alert.id, success=True, channel="webhook")
        except ImportError:
            return AlertResult(alert_id=alert.id, success=False, channel="webhook",
                              error="aiohttp no instalado")
        except Exception as e:
            logger.error(f"Error sending webhook alert: {e}")
            return AlertResult(alert_id=alert.id, success=False, channel="webhook", error=str(e))