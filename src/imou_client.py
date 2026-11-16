"""
IMOU Camera Client - Conexión y gestión de cámaras Imou (bullet 2e, cruiser se+)

Proporciona:
- Conexión RTSP a cámaras Imou
- Manejo de streams principal y sub
- Detector de básico de movimiento
- Eventos y callbacks
"""

import logging
import asyncio
from typing import Optional, Callable, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class ImouCameraError(Exception):
    """Error base para operaciones de cámara Imou."""
    pass


class ImouConnectionError(ImouCameraError):
    """Error de conexión a la cámara."""
    pass


class ImouFrameError(ImouCameraError):
    """Error al obtener/decodificar frame."""
    pass


class ImouCameraClient:
    """Cliente para conectar y recibir frames de cámaras Imou vía RTSP."""
    
    # URLs RTSP padrão para cámaras Imou
    RTSP_MAIN_STREAM = "rtsp://{username}:{password}@{host}:554/cam/realmonitor?channel=1&subtype=0"
    RTSP_SUB_STREAM = "rtsp://{username}:{password}@{host}:554/cam/realmonitor?channel=1&subtype=1"
    
    # Credenciales por defecto
    DEFAULT_USERNAME = "admin"
    DEFAULT_PASSWORD = "admin"
    
    def __init__(
        self, 
        host: str, 
        username: Optional[str] = None,
        password: Optional[str] = None,
        stream_type: str = "main",  # "main" o "sub"
        port: int = 554,
    ):
        """
        Inicializar cliente de cámara Imou.
        
        Args:
            host: Dirección IP de la cámara
            username: Usuario RTSP (por defecto: admin)
            password: Contraseña RTSP (por defecto: admin)
            stream_type: "main" para alta resolución, "sub" para baja resolución/lt
            port: Puerto RTSP (por defecto: 554)
        """
        self.host = host
        self.username = username or self.DEFAULT_USERNAME
        self.password = password or self.DEFAULT_PASSWORD
        self.stream_type = stream_type
        self.port = port
        
        # Estado de conexión
        self._running = False
        self._rtsp_process: Optional[asyncio.subprocess.Process] = None
        self._frame_callback: Optional[Callable[[bytes], None]] = None
        self._event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        
        # Stream URL construido
        self._rtsp_url: Optional[str] = None
        
    @property
    def rtsp_url(self) -> str:
        """Retorna la URL RTSP construida."""
        if self._rtsp_url is None:
            if self.stream_type == "main":
                self._rtsp_url = self.RTSP_MAIN_STREAM.format(
                    username=self.username, password=self.password, host=self.host
                )
            else:
                self._rtsp_url = self.RTSP_SUB_STREAM.format(
                    username=self.username, password=self.password, host=self.host
                )
        return self._rtsp_url
    
    def set_frame_callback(self, callback: Callable[[bytes], None]) -> None:
        """Establecer callback para recibir frames de video."""
        self._frame_callback = callback
        
    def set_event_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Establecer callback para eventos de la cámara."""
        self._event_callback = callback
    
    async def start(self) -> None:
        """Iniciar conexión RTSP y comenzar a recibir frames."""
        if self._running:
            logger.warning("Cámara ya está en ejecución")
            return
        
        logger.info(f"Iniciando conexión RTSP a {self.rtsp_url}")
        self._running = True
        
        try:
            # Iniciar ffmpeg/rtsp proces
            self._rtsp_process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-rtsp_flags", "listen",
                "-i", self.rtsp_url,
                "-f", "image2pipe",
                "-vcodec", "rawvideo",
                "-pix_fmt", "bgr24",
                "-threads", "4",
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            logger.info("Proceso ffmpeg iniciado, leyendo frames...")
            
            # Leyendo frames en bucle
            await self._read_frames()
            
        except Exception as e:
            self._running = False
            logger.error(f"Error al iniciar conexión: {e}")
            raise ImouConnectionError(f"No se pudo conectar a la cámara: {e}")
    
    async def _read_frames(self) -> None:
        """Leer frames del proceso RTSP en bucle."""
        buffer = bytearray()
        frame_size = 1920 * 1080 * 3  # Aproximado para 1080p BGR24
        
        try:
            while self._running:
                chunk = await self._rtsp_process.stdout.read(4096)
                if not chunk:
                    logger.warning("Stream finalizado (chunk vacío)")
                    break
                
                buffer.extend(chunk)
                
                # Buscar frames completos (cabecera de imagen BGR24)
                while len(buffer) >= 4:
                    # Verificamos si tenemos suficientes bytes para un frame
                    potential_frame_size = len(buffer)
                    if potential_frame_size >= frame_size:
                        # Extract frame
                        frame_data = bytes(buffer[:frame_size])
                        buffer[:frame_size] = buffer[frame_size:]  # Remove from buffer
                        # Actually let's do it properly
                        del buffer[:frame_size]
                        
                        # Notificar frame
                        if self._frame_callback:
                            try:
                                self._frame_callback(frame_data)
                            except Exception as e:
                                logger.error(f"Error en callback de frame: {e}")
                    
                    else:
                        break  # Esperar más datos
                        
        except asyncio.IncompleteReadError:
            logger.info("Lectura incompleta del stream (conexión cerrada)")
        except Exception as e:
            logger.error(f"Error leyendo frames: {e}")
            raise ImouFrameError(f"Error al leer frames: {e}")
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Detener la conexión RTSP."""
        self._running = False
        
        if self._rtsp_process and self._rtsp_process.returncode is None:
            self._rtsp_process.kill()
            await self._rtsp_process.wait()
            self._rtsp_process = None
        
        logger.info("Conexión RTSP detenida")
    
    async def detect_movement(
        self, 
        frame1: bytes, 
        frame2: bytes,
        threshold: int = 25,
        min_contour_area: int = 500
    ) -> bool:
        """
        Detectar movimiento entre dos frames consecutivos.
        
        Args:
            frame1: Primer frame (BGR24 raw)
            frame2: Segundo frame (BGR24 raw)
            threshold: Umbral de diferencia de píxeles
            min_contour_area: Área mínima de contorno para considerar movimiento
            
        Returns:
            True si se detecta movimiento significativo
        """
        import cv2
        import numpy as np
        
        try:
            # Convertir a gray
            gray1 = cv2.cvtColor(
                np.frombuffer(frame1, dtype=np.uint8).reshape((1080, 1920, 3)),
                cv2.COLOR_BGR2GRAY
            )
            gray2 = cv2.cvtColor(
                np.frombuffer(frame2, dtype=np.uint8).reshape((1080, 1920, 3)),
                cv2.COLOR_BGR2GRAY
            )
            
            # Diferencia absoluta
            diff = cv2.absdiff(gray1, gray2)
            
            # Umbral
            _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
            
            # Dilatar para cerrar huecos
            dilated = cv2.dilate(thresh, None, iterations=2)
            
            # Encontrar contornos
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Verificar contornos significativos
            for contour in contours:
                if cv2.contourArea(contour) > min_contour_area:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error en detección de movimiento: {e}")
            return False
    
    async def process_frame_with_detection(
        self, 
        frame: bytes,
        motion_threshold: int = 25,
        motion_area: int = 500
    ) -> Tuple[bytes, bool]:
        """
        Procesar un frame y detectar movimiento respecto al anterior.
        
        Args:
            frame: Frame actual (BGR24 raw)
            motion_threshold: Umbral de movimiento
            motion_area: Área mínima de movimiento
            
        Returns:
            Tupla (frame procesado, movimiento_detectado)
        """
        # Esta implementación mantiene state del frame anterior
        # Por simplicidad, retornamos solo si hay movimiento
        # En una implementación completa, compararíamos con el frame anterior almacenado
        return frame, False