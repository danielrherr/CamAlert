# Documento 5: Integración con Switches WiFi y Automatización

## 5.1 Modelo Norlink SWIGRF-16a: Descripción y Capacidades

### Especificaciones Técnicas

| Parámetro | Especificación |
|-----------|---------------|
| **Modelo** | SWIGRF-16a |
| **Marca** | Norlink |
| **Corriente Máxima** | 16 Amperios (resistivo) |
| **Voltaje** | 110-220V AC |
| **Poder máximo** | 3680W (220V × 16A) |
| **Protocolos** | WiFi 2.4GHz, HTTP API |
| **Interfaz** | Aplicación móvil, API REST |
| **Compatibilidad** | Smart Home (Tuya, Home Assistant) |

### Diagrama de Capacidades del Switch

```mermaid
flowchart LR
    SW[Switch Norlink SWIGRF-16a] --> R1[Relay 1: Iluminación]
    SW --> R2[Relay 2: Sirenas/Alerts]
    SW --> R3[Relay 3: Equipos diversos]
    SW --> R4[Relay 4: Otros dispositivos]

    style SW fill:#ffeb3b,stroke:#fbc02d,stroke-width:2px
    style R1 fill:#c8e6c9,stroke:#388e3c
    style R2 fill:#c8e6c9,stroke:#388e3c
    style R3 fill:#c8e6c9,stroke:#388e3c
    style R4 fill:#c8e6c9,stroke:#388e3c
```

### Casos de Uso para CamAlert
1. **Activar/desactivar luces** cuando detecta movimiento intruso
2. **Encender alerta sonora/visual** externa
3. **Controlar equipos** de seguridad complementarios
4. **Simular presencia** encendiéndolo/apagándose en horarios
5. **Cortar energía** a equipos en caso de emergencia crítica

---

## 5.2 Arquitectura de Integración Propuesta

### 5.2.1 Módulo `switch_controller.py` (Nuevo)

#### Diagrama de Clase SmartSwitch

```mermaid
classDiagram
    class SmartSwitch {
        +host: str
        +token: str
        +switch_id: str
        -session: object
        +__init__(host, token, switch_id)
        +turn_on() bool
        +turn_off() bool
        +get_status() dict
        +set_switch_id(switch_id) None
    }

    class HTTPClient {
        +post_control(action, switch)
        +get_status()
    }

    SmartSwitch --> HTTPClient : usa
    HTTPClient --> ControlEndpoint : envia
    ControlEndpoint --> Payload : action on/off
```

#### Interfaz de Métodos Principales

```mermaid
flowchart TD
    S1[SmartSwitch.__init__ host, token, switch_id] --> S2[Session setup con headers auth]
    S2 --> S3{Método solicitado}
    S3 -- turn_on --> S4[POST /control action=on]
    S4 --> S5[Respuesta 200 OK]
    S5 --> S6[return True]
    S3 -- turn_off --> S7[POST /control action=off]
    S7 --> S8[Respuesta 200 OK]
    S8 --> S9[return True]
    S3 -- get_status --> S10[GET /status]
    S10 --> S11[JSON status on/off]
    S11 --> S12[return parsed dict]

    style S1 fill:#e3f2fd,stroke:#1976d2
    style S6 fill:#c8e6c9,stroke:#388e3c
    style S9 fill:#c8e6c9,stroke:#388e3c
    style S12 fill:#c8e6c9,stroke:#388e3c
```

### 5.2.2 Integración con AlertManager

```mermaid
sequenceDiagram
    participant User as Operador
    participant Config as "config/camalert.json"
    participant AM as AlertManager
    participant SC as SwitchController
    participant SW as Switch Physical

    Note over User,Config: Configuración inicial
    Config->>Config: enable_switch=true
    Config->>Config: switch_host=192.168.1.200
    Config->>Config: switch_token=abc123def456
    Config->>Config: switch_id=1
    Config->>Config: switch_severity_threshold=medium

    User->>AM: Movimiento detectado (severity=high)
    AM->>SC: verificar_activacion(severity=high)
    SC->>AM: severity >= switch_threshold?

    alt Sí (threshold pasado)
        SC->>SW: POST /control action=on switch=1
        SW-->>SC: 200 OK
        SC->>AM: retorno éxito
        AM->>User: Switch Norlink activado para alerta high

        Note right of SC: Después de min_interval_seconds...
        SC->>SW: POST /control action=off switch=1
        SW-->>SC: 200 OK
        SC->>AM: retorno desactivación
    else No (threshold no pasado)
        AM->>User: Evento registrado, switch NO activado (below threshold)
    end
```

---

## 5.3 Configuración Requerida

### Agregar a config/camalert.json

```json
{
  "alerts": {
    "enable_switch": false,
    "switch_host": "192.168.1.200",
    "switch_token": "YOUR_AUTH_TOKEN",
    "switch_id": "1",
    "switch_severity_threshold": "high"
  }
}
```

### Ejemplo Configuración Completa

```mermaid
flowchart TD
    C1["enable_console: true"] --> C2["enable_email: false"]
    C2 --> C3["enable_telegram: false"]
    C3 --> C4["enable_webhook: false"]
    C4 --> C5["enable_switch: true<br/>(NUEVA)"]
    C5 --> C6["switch_host: 192.168.1.200<br/>(NUEVA)"]
    C6 --> C7["switch_token: tuya_xxxxx<br/>(NUEVA)"]
    C7 --> C8["switch_id: 1<br/>(NUEVA)"]
    C8 --> C9["switch_severity_threshold: medium<br/>(NUEVA)"]
    C9 --> C10["severity_threshold: medium<br/>(EXISTENTE)"]

    style C5 fill:#fff9c4,stroke:#fbc02d,stroke-width:2px
    style C6 fill:#fff9c4,stroke:#fbc02d,stroke-width:2px
    style C7 fill:#fff9c4,stroke:#fbc02d,stroke-width:2px
    style C8 fill:#fff9c4,stroke:#fbc02d,stroke-width:2px
    style C9 fill:#fff9c4,stroke:#fbc02d,stroke-width:2px
```

### Verificación de Configuración

```bash
# Verificar que la sección alerts tiene los nuevos campos
python3 -c "
import json
with open('/home/adminlab/proyecto/CamAlert/config/camalert.json') as f:
    config = json.load(f)
alerts = config.get('alerts', {})
nuevos = ['enable_switch', 'switch_host', 'switch_token', 'switch_id', 'switch_severity_threshold']
print('Campos nuevos presentes:', all(k in alerts for k in nuevos))
print('enable_switch:', alerts.get('enable_switch'))
"
```

---

## 5.4 Manejo de Errores y Fallbacks

### Cuadro de Errores Comunes

| Escenario | Comportamiento | Log Esperado |
|-----------|---------------|--------------|
| **Switch offline** | Log warning, alerta continúa sin activación física | `"✗ Switch offline, alerta continuando por otros canales"` |
| **Timeout respuesta** | Reintentar 2 veces, luego marcar error | `"✗ Error conectando switch: timeout after 5s"` |
| **Token inválido** | Error configuración, switch inoperable hasta corregir | `"✗ Token de auth inválido, check credentials"` |
| **Switch en modo mantenimiento** | Desactivar automáticamente, notificar al usuario | `"✗ Switch en modo mantenimiento, desactivado"` |
| **Red inaccesible** | Fallback: solo loguear, no bloquear sistema | `"✗ Network inaccesible, switch skippeado"` |

### Diagrama de Manejo de Errores

```mermaid
flowchart TD
    E1[Intentar conectar switch] --> E2{Conexión OK?}
    E2 -- Sí --> E3[Ejecutar comando ON/OFF]
    E3 --> E4[Retornar éxito]
    E2 -- No --> E5{Intentos restantes?}
    E5 -- Sí --> E6[Esperar 1s y reintentar]
    E6 --> E2
    E5 -- No --> E7[Log error, activar fallback]
    E7 --> E8[Continuar operación normal sin switch]
    E8 --> E9[Log: Switch skippeado, usar otros canales]

    style E1 fill:#e3f2fd,stroke:#1976d2
    style E4 fill:#c8e6c9,stroke:#388e3c
    style E8 fill:#c8e6c9,stroke:#388e3c
    style E9 fill:#e8f5e9,stroke:#388e3c
```

---

## 5.5 Consideraciones de Seguridad

### Checklist de Seguridad

```mermaid
flowchart TD
    S1[Seguridad Switch Integration] --> S2[Token/Authentication]
    S2 --> S3[Red local LAN only]
    S3 --> S4[Potencia máxima 16A/3680W]
    S4 --> S5[Fallos seguros]
    S5 --> S6[Backup channels notification]

    style S1 fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    style S2 fill:#ffeb3b,stroke:#fbc02d
    style S3 fill:#ffeb3b,stroke:#fbc02d
    style S4 fill:#ffeb3b,stroke:#fbc02d
    style S5 fill:#c8e6c9,stroke:#388e3c
```

### Precauciones Importantes

1. **Proteger acceso**: Nunca dejar switch sin token de autorización
2. **Red local**: Switch y CamAlert deben estar en misma red LAN
3. **No exceder 16A**: Controlar carga total conectada al switch
4. **Fallos seguros**: Si switch falla, sistema continúa con otros canales
5. **Idempotencia**: Comandos ON/OFF seguros para enviar repetidamente

---

## 5.6 Próximos Pasos de Implementación

### Fase 1: Módulo Básico (1-2 días)
- [ ] Crear `src/switch_controller.py` con clase `SmartSwitch`
- [ ] Probar conexión HTTP a switch en red local
- [ ] Verificar encendido/apagado funcional
- [ ] Loguear resultados en consola

### Fase 2: Integración con Alerts (2-3 días)
- [ ] Actualizar `src/alerts.py`:
  - Agregar `enable_switch` en `AlertConfig`
  - Agregar parámetros `switch_host`, `switch_token`, `switch_id`, `switch_severity_threshold`
  - Modificar `AlertManager.send()` para incluir canal switch
- [ ] Actualizar `src/config.py`:
  - Agregar campos nuevos a `AlertConfig` dataclass
  - Actualizar `CamAlertConfig.from_dict()` / `to_dict()`
- [ ] Probar flujo movimiento → switch → físico activation

### Fase 3: Testing y Validación (1-2 días)
- [ ] Configurar switch real en red local
- [ ] Ejecutar tests: encendido, apagado, cooldown, threshold
- [ ] Validar fallbacks: switch offline, token inválido, network down
- [ ] Documentar configuración para usuario final

### Fase 4: Release (1 día)
- [ ] Actualizar documentación (estos docs)
- [ ] Ejecutar test_basic.py para validar que nada se rompió
- [ ] Hacer release menor versión (0.2.0 o 0.3.0)

---

## 5.7 Resumen: Qué Este Documento Agrega

| Aspecto | Antes | Después de Doc 5 |
|---------|-------|------------------|
| **Módulo switches** | Inexistente | Completamente nuevo con SmartSwitch class |
| **Integración alerts** | Solo notification | + switch automation control |
| **Modelo soportado** | Ninguno | Norlink SWIGRF-16a (16A WiFi switch) |
| **Flujo evento→acción** | Solo notificaciones push | Notificación + acción física |
| **Config JSON** | 52 líneas sección alerts | +7 líneas nuevas (switch integration) |
| **Nuevo caso uso** | UC-05 (monitoreo) | UC-06 (switch automation) |

### Tabla Resumen Rápido

| Componente | Archivo | Responsabilidad |
|------------|---------|-----------------|
| **SmartSwitch** | `src/switch_controller.py` (por crear) | Lógica de conexión y comandos HTTP |
| **AlertConfig** | `src/config.py` | 5 nuevos campos en dataclass |
| **AlertManager** | `src/alerts.py` | Integración canal switch en send() |
| **Config JSON** | `config/camalert.json` | 7 nuevas líneas en sección alerts |
| **Diagramas** | `docs/05_*.md` | Visualización arquitectura y flujos |

---
*Documento corregido con diagramas Mermaid válidos y probados.*
*Sintaxis específica: flowchart LR/TD, sequenceDiagram, classDiagram.*
*Versión: 0.3.0 - Integración switches con representación visual corregida*