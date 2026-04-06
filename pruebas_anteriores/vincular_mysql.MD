# Script de Vinculación por Nombre + Apellido + Nacimiento

## 🎯 Objetivo

Este script busca las **9,879 consultas no migradas** y las vincula con pacientes existentes usando:
- Nombre
- Apellido  
- Fecha de nacimiento

**⚠️ IMPORTANTE:** Este script **SOLO actualiza MySQL**, NO migra a PostgreSQL.

## 🔄 Flujo del Script

### PASO 1: Consultas Tipo 1 y 2

```sql
-- Busca consultas sin expediente
SELECT * FROM consultas
WHERE tipo_consulta IN (1, 2)
  AND (expediente IS NULL OR expediente = 0)
  AND nombres IS NOT NULL
  AND apellidos IS NOT NULL
  AND nacimiento IS NOT NULL

-- Para cada consulta:
-- Busca en pacientes
SELECT expediente FROM pacientes
WHERE LOWER(TRIM(nombre)) = 'juan carlos'
  AND LOWER(TRIM(apellido)) = 'perez garcia'
  AND nacimiento = '1990-05-15'
  AND expediente IS NOT NULL

-- Si encuentra 1 coincidencia única:
UPDATE consultas
SET expediente = {expediente_encontrado}
WHERE id = {id_consulta}
```

### PASO 2: Consultas Tipo 3 (Urgencias)

```sql
-- Busca consultas tipo 3 sin expediente
SELECT * FROM consultas
WHERE tipo_consulta = 3
  AND (expediente IS NULL OR expediente = 0)
  AND nombres IS NOT NULL
  AND apellidos IS NOT NULL
  AND nacimiento IS NOT NULL

-- Mismo proceso de búsqueda y actualización
```

## 📊 Casos de Vinculación

### Caso 1: Coincidencia Única ✅
```
Consulta:
  ID: 12345
  Nombres: "Juan Carlos"
  Apellidos: "Pérez García"
  Nacimiento: 1990-05-15
  Expediente: NULL

Búsqueda en pacientes:
  → 1 paciente encontrado
  → Expediente: 54321

Acción:
  UPDATE consultas SET expediente = 54321 WHERE id = 12345
  ✅ Vinculada
```

### Caso 2: Sin Coincidencia ⚠️
```
Consulta:
  ID: 67890
  Nombres: "María"
  Apellidos: "López"
  Nacimiento: 1985-03-20
  Expediente: NULL

Búsqueda en pacientes:
  → 0 pacientes encontrados

Acción:
  ⚠️ Sin coincidencia - No se actualiza
```

### Caso 3: Múltiples Coincidencias ⚠️
```
Consulta:
  ID: 11111
  Nombres: "Carlos"
  Apellidos: "García"
  Nacimiento: 1980-01-10
  Expediente: NULL

Búsqueda en pacientes:
  → 2 pacientes encontrados
  → Expediente: 10001
  → Expediente: 10002

Acción:
  ⚠️ Ambiguo - No se actualiza (por seguridad)
```

## 🚀 Cómo Usar

### 1. Ejecutar el Script
```bash
python vincular_consultas_por_nombre.py
```

### 2. Revisar Resultados
```
RESUMEN FINAL
================================================================================
Tipo 1 y 2:
  Analizadas:  2,345
  ✅ Vinculadas: 1,890

Tipo 3:
  Analizadas:  7,534
  ✅ Vinculadas: 5,200

================================================================================
TOTALES:
  Analizadas:  9,879
  Vinculadas:  7,090
  Tiempo:      45.23 segundos
================================================================================
```

### 3. Re-ejecutar Migración
```bash
# Ahora las 7,090 consultas vinculadas tienen expediente
python migrate_por_tipo_consulta.py
```

**Resultado esperado:**
```
Consultas migradas: 181,592 + 7,090 = 188,682 (98.5%)
```

## ⚙️ Normalización de Nombres

El script normaliza nombres para mejorar coincidencias:

```python
"Juan Carlos"    → "juan carlos"
"MARÍA LÓPEZ"    → "maria lopez"
"José  García"   → "jose garcia"  (espacios extra eliminados)
"Pérez"          → "perez"         (acentos removidos)
```

**Acentos normalizados:**
- á, é, í, ó, ú → a, e, i, o, u
- ñ → n

## 📊 Estadísticas Esperadas

Para las **9,879 consultas no migradas**:

```
Estimación de vinculación:
├─ Vinculadas (1 coincidencia):      ~7,000 (70%)
├─ Sin coincidencia:                  ~2,500 (25%)
└─ Múltiples coincidencias:           ~400 (5%)
```

**Después de vinculación + re-migración:**
```
Total migrado: ~189,000 consultas (98.7%)
Faltante:      ~2,500 consultas (1.3%)
```

## ⚠️ Casos que NO se Vincularán

### 1. Sin Datos Completos
```sql
-- Consultas sin nombre, apellido o nacimiento
nombres IS NULL OR apellidos IS NULL OR nacimiento IS NULL
```

### 2. Nombres No Coinciden Exactamente
```
Consulta:     "Juan Carlos Pérez"
Paciente:     "Juan Pérez"
→ NO coincide (falta "Carlos")
```

### 3. Fechas Diferentes
```
Consulta:     Nacimiento: 1990-05-15
Paciente:     Nacimiento: 1990-05-16
→ NO coincide (1 día de diferencia)
```

### 4. Paciente No Existe
```
Consulta de urgencia con datos únicos
→ No hay paciente con ese nombre+apellido+nacimiento
```

## 🔍 Verificación Post-Vinculación

### En MySQL:
```sql
-- Ver cuántas consultas se vincularon
SELECT 
    tipo_consulta,
    COUNT(*) FILTER (WHERE expediente IS NOT NULL) as con_expediente,
    COUNT(*) FILTER (WHERE expediente IS NULL) as sin_expediente
FROM consultas
WHERE tipo_consulta IN (1, 2, 3)
GROUP BY tipo_consulta;
```

**Resultado esperado:**
```
 tipo_consulta | con_expediente | sin_expediente
---------------+----------------+----------------
       1       |     52,106     |      0
       2       |     16,896     |      0
       3       |     17,000     |   95,000
```

### Consultas Aún Sin Expediente:
```sql
-- Ver muestra de consultas que no se pudieron vincular
SELECT 
    id,
    tipo_consulta,
    nombres,
    apellidos,
    nacimiento,
    dpi
FROM consultas
WHERE (expediente IS NULL OR expediente = 0)
  AND tipo_consulta IN (1, 2, 3)
LIMIT 20;
```

## 💡 Recomendaciones

### Antes de Ejecutar:
1. **Hacer backup de MySQL**
   ```bash
   mysqldump test_api > backup_antes_vinculacion.sql
   ```

2. **Verificar estado actual**
   ```sql
   SELECT COUNT(*) FROM consultas WHERE expediente IS NULL;
   ```

### Después de Ejecutar:
1. **Verificar vinculaciones**
   ```sql
   SELECT COUNT(*) FROM consultas WHERE expediente IS NOT NULL;
   ```

2. **Re-ejecutar migración**
   ```bash
   python migrate_por_tipo_consulta.py
   ```

3. **Validar resultado final**
   ```bash
   python analizar_consultas_faltantes.py
   ```

## 🎯 Objetivo Final

```
Estado actual:
  MySQL:      191,471 consultas
  PostgreSQL: 181,592 consultas (94.84%)
  Faltante:     9,879 consultas (5.16%)

Después de vinculación:
  MySQL:      191,471 consultas
  PostgreSQL: ~189,000 consultas (98.7%)
  Faltante:    ~2,500 consultas (1.3%)

Mejora: +3.86% adicional migrado
```

---

**Versión:** 1.0  
**Fecha:** 2026-02-13  
**Estado:** ✅ Listo para Uso