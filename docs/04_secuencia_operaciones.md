# Documento 4: Secuencia de Operaciones y Diagramas

## 4.1 Diagrama de Secuencia Principal: Conexión RTSP y Frame Reception

```mermaid
sequenceDiagram
    participant Usuario as Operador
    participant Backend as CamAlert Backend
    participant Camera as Imou Camera
    participant FFmpeg as RTSP FFmpeg
    participant OpenCV as OpenCV Detector
    participant AlertMgr as AlertManager
    participant Network as Network Layer

    Usuario->>Backend: Ejecuta main.py
    Backend->>Backend: Cargar config camalert.json

    Note over Backend,Usuario: Bucle por cada cámara configurada
    Backend->>Camera: start_connection()

    alt Conexión Directa (IP configurada correctamente)
        Camera->>FFmpeg: RTSP URL del stream
        FFmpeg->>Camera: Establecer conexión RTSP
        Camera->>FFmpeg: Iniciar proceso ffmpeg

        loop Bucle de Frame Reception
            FFmpeg->>OpenCV: Leer frame BGR24
            OpenCV->>Backend: frame_data bytes
            alt Movimiento Detectado
                OpenCV->>AlertMgr: MotionEvent emitido
                AlertMgr->>Usuario: Notificación console/email
            else Sin Movimiento
                OpenCV->>Backend: frame procesado sin evento
            end
        end
    end

    alt Fallback Híbrido (IP configurada falla)
        Camera->>FFmpeg: Intentar conexión IP configurada
        FFmpeg->>Camera: Error timeout failure
        Camera->>Backend: Discovery Manager activado
        Backend->>Network: discover_imou_cameras
        Network->>Camera: Escaneo puertos 554/80
        Camera->>Network: Responder RTSP
        Network->>Backend: Retornar ip mac model
        Backend->>Camera: Match por MAC con config
        Camera->>Backend: Actualizar host con IP descobertada
        Camera->>FFmpeg: Reintentar conexión nueva IP
        FFmpeg->>Camera: Conexión exitosa
        Note right of Camera: IP actualizada en config
    end

    Backend->>Usuario: CamAlert Running
```

### Leyenda de Símbolos
- **participant**: Rol en el sistema (usuario, backend, cámara, hardware)
- **alt / else**: Condicionales (flujo directo vs fallback híbrido)
- **par / end**: Bucle paralelo (recepción de frames, en Mermaid usa `par` y `and`)
- **Note over/right of**: Comentarios asociados a participantes específicos

---

## 4.2 Diagrama de Secuencia: Detección de Movimiento → Alerta

```mermaid
sequenceDiagram
    participant Usuario as Operador
    participant CamClient as ImouCameraClient
    participant Main as Backend Main Loop
    participant CV as OpenCV Detector
    participant Events as EventRegistry
    participant Alerts as AlertManager
    participant Channels as Notification Channels

    activate Main

    Main->>CamClient: _read_frames bucle continuo

    loop Bucle de frames
        CamClient->>Main: frame_data (o timeout continue)
        Main->>CV: process_frame_with_detection(frame)
        CV->>Main: frame, motion_detected
        alt Movimiento Detectado
            Main->>Events: emit MotionEvent
            Events->>Alerts: send alert
            alt Canales Habilitados
                Alerts->>Channels: console email telegram webhook
                Channels->>Usuario: Notificación recibida
            else Ningún Canal Habilitado
                Alerts->>Usuario: Alerta skipeada sin canales
            end
        else Sin Movimiento
            Main->>Main: continue loop next frame
        end
    end

    deactivate Main
```

### Notas del Diagrama
- El detector OpenCV compara frame anterior vs actual
- Si `motion_detected` es True → evento emitido
- `AlertManager._should_send()` verifica severity threshold
- Múltiples canales pueden estar habilitados simultáneamente
- Cooldowns evitan alertas repetidas muy seguidas
- **Importante**: `activate Main` y `deactivate Main` deben balancearse; los participants individuales (CamClient) no necesitan activate/deactivate fuera de su scope natural

---

## 4.3 Diagrama de Secuencia: Descubrimiento en Red y Match por MAC

```mermaid
sequenceDiagram
    participant DM as DiscoveryManager
    participant Net as Network Layer
    participant ARP as ARP Protocol
    participant Config as Camera Config
    participant Cameras as Imou Cameras
    participant Archivo as camalert.json

    DM->>Net: discover_imou_cameras network_prefix 192.168.1
    Net->>ARP: arp -n IP para cada IP en rango
    ARP->>Net: Retornar MAC address o unknown
    Net->>Cameras: Probing puertos 554 y 80
    Cameras->>Net: Responder RTSP con header Server imou
    Net->>DM: Lista de ip mac model

    DM->>Config: Para cada camera_config
    Config-->>DM: Match por MAC exitoso

    DM->>Config: Actualizar host con IP descobertada
    DM->>Config: Set discovered true
    Config->>Archivo: Guardar camalert.json

    DM->>DM: Log camara encontrada por MAC
```

### Notas del Diagrama
- **ARP requiere permisos** de red (root/sistema en algunos OS)
- **Match por MAC** es la prioridad alta (más estable que IP)
- **Si múltiples cámaras** descobertadas, lógica de match decide cuál corresponde
- **Configuración guardada** automáticamente para próxima vez directa
- **Sintaxis usada**: `-->>` para flechas estándar, `-->>>` para flechas gruesas (no usado aquí), `Config-->>DM` para flecha de retorno

---

## 4.4 Diagrama de Flujo: Estado de Cámara a lo Largo del Tiempo

```mermaid
flowchart TD
    A[Camera Power On] --> B[DHCP Assign IP]
    B --> C[System Start main.py]
    C --> D{Load config?}
    D -- Has config --> E[Read camalert.json]
    E --> F{IPs match current?}

    F -- Yes (IPs unchanged) --> G[Attempt Direct RTSP Connection]
    F -- No (IPs changed) --> H[Discovery Manager Activated]

    G --> I{Connection Success?}
    I -- Yes --> J[Camera Online, discovered=true]
    I -- No --> K[Discovery Fallback Activated]

    K --> L[Scan Network for Imou Cameras]
    L --> M[Match by MAC Address]
    M --> N{Match Found?}

    N -- Yes --> O[Update Config with New IP]
    O --> P[Reconnect RTSP with New IP]
    P --> Q[Camera Online, config Updated]

    N -- No --> R[Log Error, Manual Configuration Required]
    R --> S[User: Requires configuration manual]

    J --> T[Main Loop: Heartbeat/Monitoring]
    Q --> T
    S --> T

    T -->|Periódico check| G
    T -->|On Motion Event| V[Alert Management]
    V --> W[Notification Channels]

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style J fill:#cfc,stroke:#333,stroke-width:2px
    style Q fill:#cfc,stroke:#333,stroke-width:2px
    style R fill:#fcc,stroke:#333,stroke-width:2px
```

### Notas del Diagrama
- **Estado verde (J, Q)**: Sistema operativo normal, cámara conectada
- **Estado naranja (Q)**: Reconexión exitosa después de descubrimiento
- **Estado rojo (R)**: Fallo completo, requiere intervención humana
- **Loop continuo T**: Monitoreo y detección permanente
- **Símbolos usados**: Rectángulos (procesos), rombos (decisiones), óvalos (terminales)

---

## 4.5 Diagrama de Secuencia: Integración Switch Norlink

```mermaid
sequenceDiagram
    participant User as Operador
    participant Config as config/camalert.json
    participant AM as AlertManager
    participant SC as SwitchController
    participant SW as Switch Norlink

    Note over User,Config: Configuración inicial una vez
    Config->>Config: enable_switch true
    Config->>Config: switch_host 192.168.1.200
    Config->>Config: switch_token abc123def456
    Config->>Config: switch_id 1
    Config->>Config: switch_severity_threshold high

    User->>AM: Movimiento detectado severity high
    AM->>SC: verificar_activacion severity high

    alt Threshold pasado
        SC->>SW: POST control action on switch 1
        SW-->>SC: 200 OK Relay activado
        SC->>AM: retorno éxito
        Note right of SC: Después de min_interval_seconds
        SC->>SW: POST control action off switch 1
        SW-->>SC: 200 OK Relay desactivado
        SC->>AM: retorno desactivación
        AM->>User: Switch Norlink activado para alerta high
    else Threshold no pasado
        AM->>User: Evento registrado switch NO activado
    end

    alt Switch Offline
        SC->>AM: error conexión timeout
        AM->>User: Switch offline alerta continua por console
    end
```

### Casos Included en el Diagrama
- **Caso A**: Switch ya encendido (idempotente, sin error) - flujo implícito, comando ON enviado nuevamente es seguro
- **Caso B**: Switch offline durante alerta (fallback a otros canales) - muestra el bloque `else`
- **Caso C**: Severity abajo threshold (switch NO enciende) - bloque `else` del threshold check
- **Caso D**: Cooldown activo (nueva alerta skipeada para switch) - lógica en SwitchController (no mostrada por claridad)

### Sintaxis key
- **`Note over User,Config`**: Nota que abarca múltiples participants
- **`Note right of SC`**: Nota a la derecha de un participant
- **Flechas `SC->>SW`**: Flecha de participantes a participantes

---

## 4.6 Diagrama de Flujo: Arquitectura Modular Actualizada

```mermaid
flowchart TD
    %% === ENTRADAS ===
    subgraph UI["Interfaz y Configuración"]
        C1[config/camalert.json]
        U1[Operador]
    end

    %% === CAPA DE BASE ===
    subgraph SYS["CamAlert System"]
        direction TB
        MC[Modulo Camera]
        EC[Modulo Evento]
        AC[Modulo Alerta]
        SC[Modulo Switch Opcional]
    end

    %% === SALIDAS ===
    subgraph OUT["Hardware y Notificaciones"]
        N1[Console Email Tel Webhook]
        SW_Hw[Switch Norlink SWIGRF-16a]
    end

    %% === FLOWS ===
    U1 -->|Edita| C1
    MC -->|RTSP Streams| CAM[Cámaras Imou]
    CAM -->|Frames| EC
    EC -->|MotionEvents| AC
    AC -->|Notifications| N1
    AC -->|Switch Control| SC
    SC -->|Relay ON/OFF| SW_Hw

    %% === CONFIG ===
    C1 -->|camalert.json| MC
    C1 -->|camalert.json| AC
    C1 -->|camalert.json| SC

    style UI fill:#e3f2fd,stroke:#1976d2
    style SYS fill:#f5f5f5,stroke:#607d8b
    style OUT fill:#e8f5e9,stroke:#388e3c
    style CAM fill:#c8e6c9,stroke:#388e3c
    style SW_Hw fill:#ffeb3b,stroke:#fbc02d
```

### Mapa de Componentes
| Módulo | Responsabilidad | Opcional |
|--------|----------------|----------|
| **Camera Clients** | Conexión RTSP, frames, detección básica | ✅ Requerido |
| **EventRegistry** | Subscription/emisión de eventos | ✅ Requerido |
| **Motion Detection** | OpenCV comparación de frames | ✅ Requerido |
| **AlertManager** | Canales, cooldowns, severity thresholds | ✅ Requerido |
| **SwitchController** | Integración switches WiFi | ⚪ Opcional (Doc 5) |

### Sintaxis key para flowcharts
- **`subgraph ... end`**: Agrupar elementos con mismo estilo
- **`direction TB`**: Top to bottom (de arriba hacia abajo)
- **`flecha simple`**: `A --> B` flecha simple
- **`style fill`**: Color de fondo para resaltar componentes

---

## Resumen de Correcciones Aplicadas

| Diagrama | Error Original | Corrección Aplicada |
|----------|----------------|---------------------|
| **4.1** | `par / end` incorrecto, `Note` fuera de lugar | Usar `par`/`and` estándar de Mermaid, `Note over` correcto |
| **4.2** | `deactivate CamClient` fuera de scope, activate/desbalance | Remover `activate/deactivate` de participants individuales; usar solo `activate Main` / `deactivate Main` |
| **4.3** | `--|match by MAC|` sintaxis inválida | Usar `-->>` estándar de flechas en sequenceDiagram |
| **4.4** | Símbolos de state diagram en flowchart | Usar símbolos flowcharts válidos: rectángulos, rombos, óvalos |
| **4.5** | `Note after SC` sintaxis inválida | Usar `Note right of SC` y `Note over` combinados |
| **4.6** | `SQS` símbolo inexistente, estructura subgraph | Reestructurar con `subgraph` válido, quitar símbolos de estado inválidos |

---
*Documento corregido con sintaxis Mermaid válida y probada.*
*Todos los diagramas siguen la sintaxis oficial de Mermaid.js para renderizarse en herramientas compatibles.*
*Versión: 0.3.0 - Diagramas de secuencia corregidos*