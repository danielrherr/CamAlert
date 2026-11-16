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

## Estado Actual
- [ ] Proyecto inicializado
- [ ] Investigación de APIs en curso
- [ ] Arquitectura en definición

## Requisitos
- Python 3.9+
- Acceso a red local o pública a cámaras Imou
- Sistema de notificaciones configurado