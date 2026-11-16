"""
Switch Controller - Control de switches WiFi (Norlink SWIGRF-16a y compatibles).

Proporciona:
- SmartSwitch: cliente HTTP simple para encender/apagar relays y consultar estado
- SwitchController: lógica de activación por severidad con auto-desactivación
- Fallos seguros: un switch caído nunca bloquea el pipeline de alertas
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Orden ordinal de severidades: nunca comparar strings lexicográficamente.
SEVERITY_ORDER: Tuple[str, ...] = ("low", "medium", "high", "critical")


def severity_rank(severity: Any) -> int:
    """Convertir severidad (str o Enum) a su rango ordinal. Desconocida -> -1."""
    value = getattr(severity, "value", severity)
    try:
        return SEVERITY_ORDER.index(str(value))
    except ValueError:
        return -1


class SwitchError(Exception):
    """Error al comunicarse con el switch."""


class UrllibTransport:
    """Transporte HTTP por defecto (solo stdlib)."""

    def request(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
    ) -> Tuple[int, str]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")


class SmartSwitch:
    """Cliente HTTP para un switch WiFi con relays."""

    CONTROL_PATH = "/control"
    STATUS_PATH = "/status"

    def __init__(
        self,
        host: str,
        token: str,
        switch_id: str = "1",
        timeout: float = 5.0,
        retries: int = 2,
        retry_delay: float = 1.0,
        transport: Optional[Any] = None,
        scheme: str = "http",
        port: Optional[int] = None,
    ):
        self.host = host
        self.token = token
        self.switch_id = str(switch_id)
        self.timeout = timeout
        self.retries = retries
        self.retry_delay = retry_delay
        self.transport = transport or UrllibTransport()
        self.scheme = scheme
        self.port = port

    @property
    def base_url(self) -> str:
        port = f":{self.port}" if self.port else ""
        return f"{self.scheme}://{self.host}{port}"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def set_switch_id(self, switch_id: str) -> None:
        """Cambiar el relay objetivo."""
        self.switch_id = str(switch_id)

    def _send_action(self, action: str) -> bool:
        if not self.host or not self.token:
            logger.error("✗ Switch sin host o token configurado, comando ignorado")
            return False

        url = f"{self.base_url}{self.CONTROL_PATH}"
        payload = {"action": action, "switch": self.switch_id}

        for attempt in range(self.retries + 1):
            try:
                status, text = self.transport.request(
                    "POST", url, body=payload, headers=self._headers(), timeout=self.timeout
                )
                if 200 <= status < 300:
                    logger.info(f"✓ Switch {self.host} relay {self.switch_id}: {action} OK")
                    return True
                logger.warning(
                    f"✗ Switch {self.host} respondió {status} a {action} (intento {attempt + 1}): {text[:120]}"
                )
            except Exception as exc:
                logger.warning(
                    f"✗ Error conectando switch {self.host} ({attempt + 1}/{self.retries + 1}): {exc}"
                )
            if attempt < self.retries and self.retry_delay:
                import time

                time.sleep(self.retry_delay)

        logger.error(f"✗ Switch {self.host} sin respuesta, comando {action} descartado")
        return False

    def turn_on(self) -> bool:
        """Encender el relay configurado. Falla de forma segura (False)."""
        return self._send_action("on")

    def turn_off(self) -> bool:
        """Apagar el relay configurado. Falla de forma segura (False)."""
        return self._send_action("off")

    def get_status(self) -> Dict[str, Any]:
        """Consultar el estado del switch. Lanza SwitchError si no responde."""
        url = f"{self.base_url}{self.STATUS_PATH}"
        last_error: Optional[str] = None

        for attempt in range(self.retries + 1):
            try:
                status, text = self.transport.request(
                    "GET", url, headers=self._headers(), timeout=self.timeout
                )
                if 200 <= status < 300:
                    return json.loads(text or "{}")
                last_error = f"HTTP {status}: {text[:120]}"
            except Exception as exc:
                last_error = str(exc)
            if attempt < self.retries and self.retry_delay:
                import time

                time.sleep(self.retry_delay)

        raise SwitchError(f"No se pudo consultar el switch {self.host}: {last_error}")


class SwitchController:
    """Activa/desactiva un switch según la severidad de la alerta."""

    def __init__(
        self,
        switch: Any,
        threshold: str = "high",
        min_interval_seconds: int = 30,
        auto_off: bool = True,
    ):
        self.switch = switch
        self.threshold = str(getattr(threshold, "value", threshold))
        self.min_interval_seconds = min_interval_seconds
        self.auto_off = auto_off
        self._pending_off: Optional[asyncio.Task] = None

    def should_activate(self, severity: Any) -> bool:
        """True si la severidad alcanza el umbral configurado."""
        return severity_rank(severity) >= severity_rank(self.threshold)

    async def trigger(self, severity: Any) -> bool:
        """
        Encender el switch si la severidad lo amerita y programar el apagado.

        Returns:
            True si el switch quedó activado.
        """
        if not self.should_activate(severity):
            logger.debug(
                f"Switch no activado: severidad {getattr(severity, 'value', severity)} "
                f"bajo el umbral {self.threshold}"
            )
            return False

        activated = await asyncio.to_thread(self.switch.turn_on)
        if not activated:
            return False

        if self.auto_off and self.min_interval_seconds > 0:
            self._cancel_pending()
            self._pending_off = asyncio.create_task(self._auto_off())

        return True

    async def _auto_off(self) -> None:
        try:
            await asyncio.sleep(self.min_interval_seconds)
            await asyncio.to_thread(self.switch.turn_off)
        except asyncio.CancelledError:
            raise

    def _cancel_pending(self) -> None:
        if self._pending_off is not None and not self._pending_off.done():
            self._pending_off.cancel()
        self._pending_off = None

    async def shutdown(self) -> None:
        """Cancelar un apagado pendiente (no apaga el switch)."""
        self._cancel_pending()
