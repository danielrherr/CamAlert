# Documento 1: Diseño de Integración de Cámaras Imou

## 1.1 Modelos Soportados y Capacidades

| Modelo | Capacidades Principales | Limitaciones |
|--------|------------------------|--------------|
| **Imou Bullet 2e** | - IA integrada (detección básica)<br>- RTSP/main stream a 1080p<br>- Stream sub a resolución menor<br>- Zonas de interés configurables | - Procesamiento de IA en cámara limitada<br>- Sin reconocimiento facial avanzado |
| **Imou Cruiser SE+** | - Vision mejorada<br>- Conectividad avanzada<br>- Mejor manejo de stream dual<main/sub> | - Similares limitaciones de procesamiento IA |

**Fuentes de capacitación**: Documentación oficial Imou, especificaciones de hardware de los modelos bullet 2e y cruiser se+.

## 1.2 Modos de Conexión Disponibles

### Modo A: Conexión RTSP Directa (Actual Implementación)
- **Mecanismo**: Usar IP configurada explícitamente en `config/camalert.json`
- **URL RTSP**: `rtsp://admin:admin@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0`
- **Ventajas**:
  - Baja latencia
  - Configuración estática, sin descubrimiento necesario
  - Ideal cuando la IP es fija (IP estática o DHCP reservation por MAC)
- **Desventajas**:
  - Fallo seguro si la IP cambia (reinicio cámara, renovación DHCP)
  - Requiere mantenimiento manual de la configuración

### Modo B: Descubrimiento en Red
- **Mecanismo**: Escaneo de rango IP local en busca de cámaras Imou
- **Proceso**:
  1. Pingear rango de IPs (`192.168.1.2`-`192.168.1.254`)
  2. Verificar puertos abiertos (554 RTSP, 80 HTTP)
  3. Verificar headers `Server: imou` o `dahua`
  4. Obtener dirección MAC vía ARP
  5. Matchear con cámaras configuradas por MAC o IP
- **Ventajas**:
  - Se adapta automáticamente a cambios de IP
  - Detecta cámaras nuevas en la red
  - No requiere configuración manual de IP
- **Desventajas**:
  - Operación más lenta (varía 2-10 seg dependiendo rango)
  - Requiere permisos de red (ARP)
  - Puede encontrar múltiples cámaras, requiere lógica de match
  - No funcional en redes sin permisos de ARP o con firewalls restrictivos

### Modo Híbrido (Recomendado)
- **Mecanismo**: Intentar conexión directa primero; si falla → activar descubrimiento
- **Flujo**:
  1. Intentar conectar con IP configurada
  2. Si falla (timeout, error de conexión) → iniciar descubrimiento en red
  3. Matchear cámara descobertada con configuración por MAC/name
  4. Actualizar `camera_config.host` con IP descobertada
  5. Reintentar conexión con nueva IP
  6. Si exitosa, marcar `discovered: true` y guardar configuración
  7. Si falla todo, indicar al usuario que requiere configuración manual
- **Ventajas**:
    - Lo mejor de ambos mundos
    - Transparencia para el usuario
    - Fallback gracefully cuando es necesario
- **Desventajas**:
    - Lógica ligeramente más compleja
    - Primera conexión puede ser ligeramente más lenta si requiere descubrimiento

## 1.3 Decisiones de Diseño para el Módulo de Descubrimiento

### 1.3.1 Identificación por MAC (Prefiere IP)
- **Por qué**: La dirección MAC es más estable que la dirección IP a lo largo del tiempo
- **Cómo**: El router suele asignar la misma IP a la misma MAC (DHCP reservation efectiva)
- **Implementación**: Matchear `camera_config.mac_address` con `disc_cam.mac` obtenido vía ARP

### 1.3.2 Rango de Escaneo Configurable
- **Decisión**: El rango de red (`network_prefix`) debería ser configurable
- **Default**: `192.168.1` (basado en configuración actual)
- **Por qué**: Permite adaptarse a diferentes arquitecturas de red (192.168.0, 10.0.x, etc.)

### 1.3.3 Priorización de Match
1. **Primera prioridad**: Match por dirección MAC (más robusto)
2. **Segunda prioridad**: Match por dirección IP (si la IP no ha cambiado)
3. **Tercera prioridad**: Match por nombre de cámara (si está incluida en los datos de descubrimiento)

### 1.3.4 Actualización Automática de Configuración
- Cuando se descubre una cámara matcheada, actualizar automáticamente:
  - `camera_config.host` ← IP descobertada
  - `camera_config.last_seen` ← marca de tiempo actual
  - `camera_config.discovered` ← `true`
- Opcional: Guardar la nueva configuración en `config/camalert.json` después de éxito

## 1.4 Flujos de Conexión Propuestos

### Flujo 1: Primera Conexión (Cámara Nueva o Reset de fábrica)
```
1. Usuario ingresa: nombre, modelo, IP inicial (opcional)
2. Sistema intenta conexión RTSP directa con IP proporcionada
3. Si IP no proporcionada o falla → iniciar descubrimiento en red
4. Descubrir cámara por MAC/IP
5. Actualizar configuración con IP descobertada
6. Guardar configuración
7. Probar conexión y marcar como "connected"
```

### Flujo 2: Reconexión después de Reinicio de Cámara (IP nueva)
```
1. Sistema inicia, lee configuración actual (con IP antigua)
2. Intenta conexión RTSP con IP antigua → falla (cámara nueva IP)
3. Activar módulo de descubrimiento
4. Escanear red, encontrar cámara por MAC
5. Actualizar host en configuración con nueva IP
6. Reintentar conexión RTSP
7. Éxito → sistema operativo normal
```

### Flujo 3: Nueva Cámara Agregada a Red Existente
```
1. Usuario agrega nueva cámara en config con nombre/modelo
2. Deja IP en blanco o 0.0.0.0
3. Al iniciar/setup_cameras → módulo descubrimiento
4. Encontrar cámara nueva por IP/ MAC
5. Asignar IP automáticamente a la entrada de config
6. Guardar y conectar
```

## 1.5 Consideraciones para Cambios de IP/DHCP

| Escenario | Impacto | Solución |
|-----------|---------|----------|
| **Router reinicia, asigna IPs nuevas** | Cámaras pierden conexión hasta que se actualice la config | Módulo descubrimiento al iniciar |
| **Usuario agrega nueva cámara a red** | Cámara con IP distinta a la configurada | Descubrimiento automático |
| **Cambio de red (viajar con cámara a otra casa)** | IP completamente distinta | Descubrimiento necesario, IP antigua obsoleta |
| **DHCP con lease largo (días/semanas)** | Raremente cambia IP, sistema es estable | Configuración inicial simple basta |
| **DHCP con lease corto (horas)** | IP cambia frecuentemente | Modulo descubrimiento esencial, hybrid flow recomendado |

## 1.6 Próximos Documentos Sugeridos

- **02_arquitectura_sistema.md**: Arquitectura detallada del backend, flujos de datos, componentes
- **03_casos_uso.md**: Casos de uso completos con pasos de usuario
- **04_secuencia_operaciones.md**: Diagramas de secuencia RTSP → frame → detección → alerta

---
*Documento creado para análisis de modos de integración antes de implementación.*
*Modelos: Imou Bullet 2e, Imou Cruiser SE+*
*Versión: 0.1.0 - Diseño inicial*