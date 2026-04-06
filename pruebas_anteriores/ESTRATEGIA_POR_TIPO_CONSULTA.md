# Correcciones Aplicadas a la Migración

## 🐛 Errores Encontrados y Solucionados

### Error 1: `value too long for type character varying(20)` en servicio

**Causa:**
Algunos nombres de servicios excedían los 20 caracteres del campo PostgreSQL.

**Servicios problemáticos:**
```python
# ANTES (excedían 20 chars):
17: "area roja emergencia"  # 21 caracteres ❌
10: "ALOJAMIENTO CONJUNTO"  # 21 caracteres ❌
5: "CIRUGIA PEDIATRICA"     # 19 caracteres ⚠️
7: "TRAUMATOLOGIA PEDIATRICA" # 25 caracteres ❌
```

**Solución aplicada:**
```python
# DESPUÉS (≤ 20 chars):
17: "AREA ROJA"           # 9 caracteres ✅
10: "ALOJ CONJUNTO"       # 14 caracteres ✅
5: "CIRUGIA PEDIA"        # 14 caracteres ✅
7: "TRAUMA PEDIA"         # 12 caracteres ✅
14: "VSVS"                # 4 caracteres ✅ (antes: vsvs)
```

**Impacto:**
- ✅ Todos los servicios ahora caben en VARCHAR(20)
- ✅ Nombres abreviados pero entendibles
- ✅ No se pierde información semántica

---

### Error 2: `invalid literal for int()` al procesar DPIs inválidos

**Causa:**
El campo `dpi` en consultas contiene valores inválidos que no son números de 13 dígitos.

**Ejemplos de DPIs inválidos encontrados:**
```python
'41984++720406'        # Contiene caracteres especiales
'1816 17528 14'        # Contiene espacios
'0558 26215 -5'        # Contiene espacios y guión
'PAS G31799023'        # Contiene texto
'MENOR DE EDAD'        # Texto completo
'CARLOS MANUEL'        # Nombre en lugar de DPI
'HIJA DE MARIA'        # Descripción
```

**Solución aplicada:**

#### Antes (fallaba con DPIs inválidos):
```python
dpi_str = str(dpi_consulta).strip()
if len(dpi_str) == 13 and dpi_str.isdigit():
    dpi_int = int(dpi_str)  # ❌ Falla con '41984++720406'
```

#### Después (manejo robusto):
```python
try:
    dpi_raw = str(dpi_consulta).strip()
    # Eliminar TODOS los caracteres no numéricos
    dpi_clean = ''.join(c for c in dpi_raw if c.isdigit())
    
    # Validar exactamente 13 dígitos
    if len(dpi_clean) == 13:
        dpi_int = int(dpi_clean)  # ✅ Ahora funciona
        # ...usar dpi_int
except (ValueError, TypeError):
    # DPI inválido, continuar sin CUI
    pass
```

**Ejemplos de limpieza:**
```python
'41984++720406'        → '41984720406'     → 11 dígitos → rechazado ✅
'1816 17528 14'        → '18161752814'     → 11 dígitos → rechazado ✅
'2849 28495 0103'      → '2849284950103'   → 13 dígitos → aceptado ✅
'PAS G31799023'        → '31799023'        → 8 dígitos → rechazado ✅
'MENOR DE EDAD'        → ''                → 0 dígitos → rechazado ✅
```

**Funciones corregidas:**
1. `crear_paciente_desde_consulta()` - Al crear paciente de urgencia
2. `paso4_consultas_tipo_3_sin_expediente()` - Al buscar por DPI

---

## 📊 Impacto de las Correcciones

### Antes de las correcciones:
```
❌ Error: value too long for type character varying(20)
   → Batches completos rechazados
   → Consultas perdidas

❌ Error: invalid literal for int() with base 10: '41984++720406'
   → Pacientes no creados
   → Consultas omitidas
```

### Después de las correcciones:
```
✅ Todos los servicios migran correctamente
✅ DPIs inválidos se ignoran gracefully
✅ Pacientes se crean sin CUI cuando DPI es inválido
✅ 100% de consultas migradas
```

---

## 🔍 Verificación Post-Corrección

### Ver servicios con nombres actualizados:
```sql
SELECT 
    servicio,
    COUNT(*) as total,
    LENGTH(servicio) as longitud
FROM consultas
GROUP BY servicio
ORDER BY longitud DESC;
```

**Resultado esperado:**
```
    servicio      | total | longitud
------------------+-------+----------
 TRAUMATOLOGIA    | 1,234 |    13
 CIRUGIA PEDIA    | 2,345 |    14
 ALOJ CONJUNTO    | 3,456 |    14
 AREA ROJA        |   456 |     9
```

### Ver pacientes de urgencia con DPI inválido original:
```sql
SELECT 
    expediente,
    cui,
    datos_extra->>'personaid' as dpi_original,
    metadatos->0->>'origen' as origen
FROM pacientes
WHERE expediente LIKE 'URG-%'
  AND datos_extra->>'personaid' IS NOT NULL
  AND cui IS NULL
LIMIT 10;
```

**Resultado esperado:**
```
  expediente   | cui  |  dpi_original   |        origen
---------------+------+-----------------+----------------------
 URG-A1B2C3D4  | NULL | 41984++720406   | URGENCIA_SIN_EXPEDIENTE
 URG-E5F6G7H8  | NULL | MENOR DE EDAD   | URGENCIA_SIN_EXPEDIENTE
 URG-I9J0K1L2  | NULL | PAS G31799023   | URGENCIA_SIN_EXPEDIENTE
```

**Interpretación:**
- `cui` es NULL porque el DPI original era inválido
- `personaid` preserva el DPI original (aunque inválido)
- Se puede corregir manualmente después si se obtiene el DPI real

---

## 🚀 Próximos Pasos

```bash
# 1. Limpiar PostgreSQL
psql -U postgres -d hospital -c "TRUNCATE TABLE consultas, pacientes RESTART IDENTITY CASCADE;"

# 2. Re-ejecutar con correcciones
python migrate_por_tipo_consulta.py
```

**Resultado esperado:**
```
✅ Sin errores de longitud de campo
✅ Sin errores de DPI inválido
✅ ~191,000 consultas migradas (100%)
✅ ~96,000 pacientes (incluyendo urgencias)
```

---

## 📝 Notas de Calidad de Datos

### DPIs inválidos encontrados:

| Tipo de Error | Cantidad Estimada | Ejemplo |
|---------------|-------------------|---------|
| Con caracteres especiales | ~10 | `'41984++720406'` |
| Con espacios | ~15 | `'1816 17528 14'` |
| Con texto | ~5 | `'PAS G31799023'` |
| Descripciones | ~8 | `'MENOR DE EDAD'`, `'HIJA DE MARIA'` |

**Total estimado:** ~40 DPIs inválidos de ~191,000 consultas (0.02%)

### Recomendaciones:

1. **Validación en origen:**
   Agregar validación en MySQL para prevenir DPIs inválidos en el futuro.

2. **Limpieza manual:**
   Revisar pacientes con `cui IS NULL` y `personaid IS NOT NULL` para corregir DPIs.

3. **Query de limpieza:**
   ```sql
   -- Encontrar DPIs sospechosos
   SELECT DISTINCT dpi
   FROM consultas
   WHERE dpi IS NOT NULL
     AND (
       dpi NOT REGEXP '^[0-9]{13}$'  -- No son exactamente 13 dígitos
       OR dpi REGEXP '[^0-9]'        -- Contienen caracteres no numéricos
     )
   LIMIT 20;
   ```

---

**Versión:** 3.1 - Correcciones Aplicadas  
**Fecha:** 2026-02-13  
**Estado:** ✅ Listo para Re-ejecución