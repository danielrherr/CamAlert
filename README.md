# CamAlert - Monitoreo de Cámaras Imou

## Descripción
Sistema de monitoreo en tiempo real para cámaras de seguridad Imou (modelos bullet 2e y cruiser se+).
- Conexión en tiempo real a flujos de video
- Detección de eventos definidos
- Disparo de alertas automatizadas
- Interfaz de configuración y estado

## Modelos Soportados
- **Imou Bullet 2e**: Cámara bala con capacidades de IA integrada
- **Imou Cruiser SE+**: Cámara con visión mejorada y conectividad avanzada

## Arquitectura
```
┌─────────────────────────────────────────────┐
│              Cámaras Imou                    │
│  (bullet 2e, cruiser se+)                   │
└───────────────▲───────────────▲─────────────┘
                │                   │
  RTSP / HTTP API   │   MQTT / WebSocket │
                │                   │
┌─────────────────────────────────────────────┐
│          CamAlert Backend                    │
│  • Conexión y heartbeat                     │
│  • Procesamiento de frames                  │
│  • Detección de eventos                    │
│  • Gestión de alertas                      │
└───────────────▲───────────────▲─────────────┘
                │                   │
  Notificaciones  │   Almacenamiento   │
│  (email, telegram, webhook)               │
└─────────────────────────────────────────────┘
```

## Eventos de Alerta
Por definir (pending definition):
- [ ] Movimiento detectado
- [ ] Intrusión en zona
- [ ] Pérdida de señal
- [ ] Detección de caras desconocidas
- [ ] Áreas de interés cruzadas

## Automatización con Switch WiFi (opcional)

CamAlert puede energizar un relay físico (Norlink SWIGRF-16a o compatible) cuando una
alerta alcanza el umbral configurado. Se configura en la sección `alerts`:

```json
{
  "alerts": {
    "enable_switch": true,
    "switch_host": "192.168.1.200",
    "switch_token": "YOUR_AUTH_TOKEN",
    "switch_id": "1",
    "switch_severity_threshold": "high"
  }
}
```

El switch se apaga automáticamente después de `min_interval_seconds`. Si el switch no
responde, la alerta continúa por los demás canales (fallo seguro).

## Estado Actual
- [x] Proyecto inicializado
- [x] Análisis de protocolos y arquitectura documentada (`docs/`)
- [x] Módulos `switch_controller` y `discovery_manager` implementados con tests
- [ ] Validación con cámaras y switch reales en red local

## Tests

```bash
python3 -m unittest discover -s tests -v   # unitarios + integración HTTP local
python3 test_basic.py                      # smoke test del sistema base
```

## Requisitos
- Python 3.9+
- Acceso a red local o pública a cámaras Imou
- Sistema de notificaciones configurado