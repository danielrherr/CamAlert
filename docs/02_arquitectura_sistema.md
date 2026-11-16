# Documento 2: Arquitectura del Sistema CamAlert

## 2.1 Diagrama de Arquitectura General

```mermaid
flowchart TD
    subgraph UI["Interfaz y Configuración"]
        U1[Operador] -->|Edita| C1[config/camalert.json]
    end

    subgraph BACK["CamAlert Backend"]
        direction TB
        subgraph MC["Módulo Camera"]
            C2[CameraClients Imou]
            C3[DiscoveryManager]
        end
        subgraph EC["Evento y Detección"]
            C4[EventRegistry]
            C5[OpenCV Motion Detection]
        end
        subgraph AC["Alerta y Automatización"]
            C6[AlertManager]
            C7[SwitchController]
        end
    end

    CAM[Cámaras Imou]
    N1[Console Email Tel Webhook]
    SW[Switch Norlink SWIGRF-16a]

    C2 -->|RTSP Streams| CAM
    CAM -->|Frames| C5
    C5 -->|MotionEvents| C4
    C4 -->|Events| C6
    C6 -->|Notifications| N1
    C6 -->|Switch Control| C7
    C7 -->|Relay ON/OFF| SW

    C1 -->|Config| C2
    C1 -->|Config| C6
    C1 -->|Config| C7

    style UI fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    style BACK fill:#f5f5f5,stroke:#607d8b,stroke-width:2px
    style CAM fill:#c8e6c9,stroke:#388e3c,stroke-width:2px
    style SW fill:#ffeb3b,stroke:#fbc02d,stroke-width:2px
    style N1 fill:#e8f5e9,stroke:#388e3c
```

### Leyenda de Componentes

| Símbolo | Componente | Descripción |
|---------|------------|-------------|
| 📁 | config/camalert.json | Arquitectura de configuración central |
| 📡 | Cámaras Imou | Bullet 2e, Cruiser SE+ vía RTSP |
| 🔄 | DiscoveryManager | Módulo descubrimiento en red híbrido |
| 📊 | EventRegistry | Registro de handlers por tipo de evento |
| 🎯 | MotionDetector | Detección OpenCV con OpenCV |
| ⚠️ | AlertManager | Gestión channels, cooldowns, severity |
| 💡 | SwitchController | Nueva: integración switches WiFi |
| 📢 | N1 | Canales: console, email, telegram, webhook |
| 🔌 | SW | Hardware: Norlink SWIGRF-16a (16A) |

---

## 2.2 Componentes Actuales

| Componente | Responsabilidad | Estado |
|------------|-----------------|--------|
| **Config Manager** | Cargar/guardar `camalert.json`, dataclasses `CameraConfig`, `EventConfig`, `AlertConfig` | ✅ Funcional |
| **Event System** | `EventType`, `BaseEvent`, `MotionEvent`, handlers (`on_motion`, `on_intrusion`, etc.) | ✅ Funcional |
| **Alert Manager** | Múltiples canales (console, email, telegram, webhook), throttling, cooldown | ✅ Funcional (console activada) |
| **Camera Clients** | `ImouCameraClient`, conexión RTSP vía ffmpeg, detección de movimiento OpenCV | ⚠️ Pruebas pendientes reales |
| **Network Discovery** | `NetworkDiscovery.discover_imou_cameras()`, `_get_mac_address()`, `update_camera_config_from_discovery()` | ⚠️ Parcialmente implementado |

---

## 2.3 Nuevas Componentes Necesarias

### 2.3.1 Módulo Discovery Manager (Nuevo)

**Responsabilidades:**
- Encapsular lógica de descubrimiento en red
- Gestionar estado de "último descubrimiento" por cámara
- Decision logic: directa vs descubrimiento vs híbrido
- Guardar configuración actualizada después de éxito

**Diagrama de flujo Discovery Manager:**

```mermaid
flowchart TD
    D1[check_and_reconnect cam_config] --> D2{IP configurada OK?}
    D2 -- Sí --> D3[Conectar RTSP directa]
    D2 -- No --> D4[Activar Discovery en Red]
    D4 --> D5[Escaneo rango IP]
    D5 --> D6[Match por MAC/IP]
    D6 --> D7[Actualizar config.host]
    D7 --> D8[Reintentar conexión RTSP]
    D8 --> D9{Conexión OK?}
    D9 -- Sí --> D10[return client, discovered=true]
    D9 -- No --> D11[Log error, manual config]

    style D1 fill:#e3f2fd,stroke:#1976d2
    style D10 fill:#c8e6c9,stroke:#388e3c
    style D11 fill:#ffcdd2,stroke:#b71c1c
```

### 2.3.2 Gestor de Estado de IP (Nuevo)

**Propósito:** Hacer tracking de cuándo fue el último visto cada cámara y si la IP cambió.

**Atributos clave:**
- `last_known_ip: str` - IP última vez vista exitosamente
- `discovery_timestamp: datetime` - Cuándo fue el descubrimiento
- `ip_stable: bool` - Si la IP ha sido estable en N checks recientes
- `retry_count: int` - Cuántos intentos fallidos de conexión seguidos

**Estado de IP a lo largo del tiempo:**

```mermaid
stateDiagram-v2
    [*] --> IP_Estable: Reinicio normal
    IP_Estable --> IP_Nueva: DHCP renewal
    IP_Nueva --> Descubrimiento: fallo conexión directa
    Descubrimiento --> IP_Actualizada: match MAC exitoso
    IP_Actualizada --> IP_Estable: guardado config nuevo
```

### 2.3.3 Módulo Switch Controller (Nuevo - Integración Hardware)

**Responsabilidades:**
- Gestionar conexión a switches WiFi (Norlink SWIGRF-16a compatibles)
- Enviar comandos ON/OFF a relays físicos
- Integrarse con AlertManager para activación automática
- Manejar estados y timeouts de los switches

**Integración con AlertManager:**

```mermaid
sequenceDiagram
    participant User as Operador
    participant AM as AlertManager
    participant SC as SwitchController
    participant SW as Switch Physical

    User->>AM: enable_switch=true, threshold=high
    AM->>SC: activar_switch(severity=high)
    SC->>SW: HTTP POST control action on
    SW-->>SC: 200 OK
    SC-->>AM: confirmación activación
    AM->>User: Switch activado para alerta high
```

---

## 2.4 Decisiones de Arquitectura

| Decisión | Justificación | Impacto |
|----------|---------------|---------|
| **Híbrido por defecto** | Combina velocidad directa + adaptabilidad discovery | Menor tiempo de inactividad |
| **MAC como identificador principal** | Más estable que IP (router reserva por MAC) | Reconexión automática confiable |
| **SwitchController bajo demanda** | No todos los usuarios tienen switches físicos | Arquitectura flexible, opcional |
| **AlertManager como orchestrator** | Ya existe la lógica de thresholds y cooldowns | Integración mínima, reutilización existente |

---

## 2.5 Próximos Pasos de Implementación

1. **Crear `src/discovery_manager.py`** con clase DiscoveryManager
2. **Actualizar `src/alerts.py`** para integrar SwitchController
3. **Crear `src/switch_controller.py`** con clase SmartSwitch
4. **Probar flujos**: IP unchanged, IP changed, nueva cámara, switch activation
5. **Validar con diagramas** los casos de uso críticos

---
*Documento corregido con diagramas Mermaid válidos y probados.*
*Sintaxis específica de Mermaid.js: flowchart TD, stateDiagram-v2, sequenceDiagram.*
*Versión: 0.3.0 - Arquitectura con representación visual corregida*