# Migración por Fases con Trazabilidad Completa

## 🎯 Filosofía

Esta estrategia respeta la **lógica del negocio hospitalario** donde:
- Un paciente puede cambiar de expediente
- Las consultas pueden tener expediente desactualizado
- Algunos registros históricos no tienen expediente válido
- El DPI es la identificación más confiable

## 📊 Las 4 Fases

```
┌─────────────────────────────────────────────────────────┐
│ FASE 1: Pacientes Principales + Consultas Exactas      │
├─────────────────────────────────────────────────────────┤
│ • Migra TODOS los pacientes de tabla pacientes         │
│ • Migra consultas donde expediente coincide EXACTO     │
│ • Crea mapeo: expediente → paciente_id                 │
│                                                          │
│ Resultado: 90-95% de datos migrados                    │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│ FASE 2: Consultas con Expediente Actualizado (exp_ref) │
├─────────────────────────────────────────────────────────┤
│ • Paciente cambió expediente de 12345 → 67890          │
│ • Consulta tiene expediente=12345, exp_ref=67890       │
│ • Se migra consulta con expediente actualizado         │
│                                                          │
│ Resultado: +2-3% de consultas recuperadas              │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│ FASE 3: Consultas por DPI Coincidente                  │
├─────────────────────────────────────────────────────────┤
│ • Consulta tiene expediente que no existe              │
│ • PERO su DPI coincide con un paciente                 │
│ • Se vincula por DPI                                    │
│                                                          │
│ Resultado: +1-2% de consultas recuperadas              │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│ FASE 4: Pacientes Sin Expediente + Consultas Restantes │
├─────────────────────────────────────────────────────────┤
│ • Consultas sin expediente ni DPI válido               │
│ • Agrupa por: nombre + apellido + nacimiento           │
│ • Crea paciente sintético para cada grupo único        │
│ • Migra consultas asociadas                             │
│                                                          │
│ Resultado: 100% de datos migrados                      │
└─────────────────────────────────────────────────────────┘
```

## 📋 Detalle de Cada Fase

### FASE 1: Base Sólida (90-95%)

**Entrada:**
- Tabla `pacientes` completa
- Tabla `consultas` con expediente válido

**Proceso:**
```python
1. Migrar TODOS los pacientes
   pacientes MySQL → pacientes PostgreSQL
   
2. Crear mapeo
   expediente_mysql → {paciente_id_pg, expediente_pg}
   
3. Migrar consultas
   WHERE consultas.expediente IN (expedientes_migrados)
```

**Salida:**
- ✅ 100% de pacientes migrados
- ✅ 90-95% de consultas migradas
- ✅ Mapeo expediente → paciente_id

**Ejemplo:**
```
Paciente: exp=12345, dpi=1234567890123
  Consulta 1: exp=12345 ✅ Migrada
  Consulta 2: exp=12345 ✅ Migrada
  Consulta 3: exp=99999 ❌ No migrada (fase 2 o 3)
```

### FASE 2: Expedientes Actualizados (2-3%)

**Entrada:**
- Consultas no migradas en fase 1
- Campo `exp_ref` en tabla pacientes

**Proceso:**
```sql
-- Paciente original
expediente: 12345 → actualizado a → 67890
exp_ref: 12345

-- Consulta antigua
expediente: 12345
fecha: 2020-01-01

-- La consulta se vincula al paciente con exp=67890
-- porque exp_ref=12345
```

**Lógica:**
1. Consulta tiene expediente X
2. No existe paciente con expediente X
3. PERO existe paciente con exp_ref = X
4. Vincular consulta a ese paciente

**Salida:**
- ✅ Consultas con expediente histórico migradas

### FASE 3: Vinculación por DPI (1-2%)

**Entrada:**
- Consultas aún no migradas
- DPI en consultas

**Proceso:**
```python
1. Crear mapeo: DPI → paciente_id_pg
2. Para cada consulta con DPI:
   if consulta.dpi in mapeo_dpi:
       vincular_con_paciente(mapeo_dpi[consulta.dpi])
```

**Ejemplo:**
```
Consulta:
  expediente: 99999 (no existe)
  dpi: 1234567890123 ✅ Existe

Paciente:
  expediente: 67890
  dpi: 1234567890123 ✅ Coincide

→ Consulta se vincula al paciente con exp=67890
```

**Salida:**
- ✅ Consultas vinculadas por identificación personal

### FASE 4: Datos Sin Identificación (Resto)

**Entrada:**
- Consultas sin expediente válido
- Consultas sin DPI válido

**Proceso:**
```python
1. Agrupar consultas por:
   - nombre + apellido + fecha_nacimiento
   
2. Por cada grupo único:
   - Crear paciente sintético
   - expediente = "SIN-{hash}"
   - Migrar todas sus consultas
```

**Ejemplo:**
```
Consultas sin expediente/DPI:
┌─────────────────────────────────────────┐
│ Juan Pérez, 1980-01-01 → 5 consultas   │
│ María López, 1990-05-15 → 3 consultas  │
└─────────────────────────────────────────┘

Se crean:
Paciente 1: exp="SIN-ABC123", nombre="Juan Pérez"
  → 5 consultas vinculadas
  
Paciente 2: exp="SIN-DEF456", nombre="María López"
  → 3 consultas vinculadas
```

**Salida:**
- ✅ 100% de consultas migradas
- ⚠️ Pacientes marcados como sintéticos en metadatos

## 🔧 Implementación Técnica

### Mapeos Utilizados

```python
# FASE 1
mapeo_expediente = {
    "12345": {
        "paciente_id": 1,
        "expediente_pg": "12345"
    },
    "67890": {
        "paciente_id": 2,
        "expediente_pg": "67890"
    }
}

# FASE 3
mapeo_dpi = {
    1234567890123: {
        "paciente_id": 1,
        "expediente_pg": "12345"
    }
}
```

### Manejo de Duplicados

**CUI Duplicado:**
```python
try:
    insertar_con_cui(paciente)
except UniqueViolation:
    # Guardar CUI en metadatos
    paciente.metadatos["cui_original"] = cui
    paciente.cui = None
    insertar_sin_cui(paciente)
```

**Expediente Duplicado:**
```python
# ON CONFLICT (expediente) DO UPDATE
# Actualiza datos pero mantiene el primer paciente_id
```

## 📊 Trazabilidad

Cada paciente/consulta tiene metadatos que indican su origen:

```json
{
  "accion": "CREADO",
  "origen_fase": 1,  // 1, 2, 3, o 4
  "origen_mysql_id": 12345,
  "metodo_vinculacion": "expediente_exacto",  // o "exp_ref", "dpi", "nombre"
  "expediente_duplicado": false,
  "cui_duplicado": false,
  "cui_original": "1234567890123"
}
```

## 🎯 Ventajas de Esta Estrategia

### vs Migración Directa
| Aspecto | Directa | Por Fases |
|---------|---------|-----------|
| Consultas migradas | 90% | 100% |
| Trazabilidad | Limitada | Completa |
| Datos históricos | ❌ Perdidos | ✅ Preservados |
| Manejo duplicados | Manual | ✅ Automático |

### vs Migración Unificada
| Aspecto | Unificada | Por Fases |
|---------|-----------|-----------|
| Lógica negocio | ❌ No respeta | ✅ Respeta |
| Exp. actualizados | ❌ No maneja | ✅ Maneja |
| Vinculación DPI | ❌ Básica | ✅ Avanzada |
| Consultas sin ID | ❌ Descarta | ✅ Agrupa |

## 🚀 Uso

### Pre-requisitos
```bash
# 1. Verificar estructura
mysql> DESC pacientes;
mysql> DESC consultas;

# 2. Verificar campo exp_ref
mysql> SELECT COUNT(*) FROM pacientes WHERE exp_ref IS NOT NULL;
```

### Ejecución
```bash
python migrate_por_fases.py
```

### Verificación
```sql
-- Por fase
SELECT 
    metadatos->0->>'origen_fase' as fase,
    COUNT(*) as cantidad
FROM pacientes
GROUP BY fase
ORDER BY fase;

-- Por método de vinculación
SELECT 
    ciclo->>'metodo_vinculacion' as metodo,
    COUNT(*) as consultas
FROM consultas
GROUP BY metodo;
```

## ⚠️ Consideraciones

### Fase 2 (exp_ref)
- **Requiere** que la tabla `pacientes` tenga campo `exp_ref`
- Si no existe, esta fase se omite
- Verificar con: `SHOW COLUMNS FROM pacientes LIKE 'exp_ref'`

### Fase 4 (Sin identificación)
- Crea expedientes sintéticos: `SIN-{hash}`
- Marca en metadatos: `origen: "FASE4_SIN_EXPEDIENTE"`
- **Revisar manualmente** estos casos después

### Performance
- Fase 1: ~2-5 min (para 30k pacientes, 90k consultas)
- Fase 2: ~30 seg
- Fase 3: ~1 min
- Fase 4: ~2 min
- **Total: ~5-10 minutos**

## 📝 Casos de Uso Reales

### Caso 1: Paciente cambió expediente
```
2020: Paciente con exp=OLD123 → 10 consultas
2021: Actualizado a exp=NEW456
2022: 5 consultas más con exp=NEW456

FASE 1: Migra paciente con exp=NEW456 + 5 consultas
FASE 2: Migra 10 consultas antiguas (exp_ref=OLD123)
RESULTADO: 1 paciente, 15 consultas ✅
```

### Caso 2: Error de captura en expediente
```
Paciente real: exp=12345, dpi=1234567890123
Consulta capturada mal: exp=99999, dpi=1234567890123

FASE 1: Migra paciente
FASE 3: Vincula consulta por DPI
RESULTADO: 1 paciente, consulta recuperada ✅
```

### Caso 3: Consulta histórica sin datos
```
Consulta antigua: exp=NULL, dpi=NULL
Pero tiene: nombre="Juan Pérez", nac=1980-01-01

FASE 4: Crea paciente sintético
RESULTADO: Dato preservado ✅
```

---

**Versión**: 1.0  
**Autor**: Sistema de Migración Hospitalaria  
**Fecha**: 2026-02-13