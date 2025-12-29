-- =====
-- Pacientes Table
-- =====
CREATE TABLE pacientes ( id SERIAL PRIMARY KEY,

-- 🔐 Identificadores principales
expediente VARCHAR(20) UNIQUE,
cui BIGINT UNIQUE,
pasaporte VARCHAR(50) UNIQUE,

-- 🧍‍♂️ Identificación personal
nombre JSONB NOT NULL,
sexo CHAR(2) CHECK (sexo IN ('M', 'F', 'NF')),
fecha_nacimiento DATE,

-- ☎️ Contacto
contacto JSONB,

-- 👪 Referencias familiares
referencias JSONB,

-- 🌍 Otros datos históricos y clínicos
datos_extra JSONB,

-- ⚙️ Estado del paciente
estado CHAR(1) DEFAULT 'V' CHECK (estado IN ('V', 'F')),

-- 🧾 Metadatos del sistema
metadatos JSONB,

-- ⏱️ Tiempos del sistema
creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- JSONB
CREATE INDEX idx_pacientes_nombre ON pacientes USING GIN (nombre);

CREATE INDEX idx_pacientes_contacto ON pacientes USING GIN (contacto);

CREATE INDEX idx_pacientes_referencias ON pacientes USING GIN (referencias);

CREATE INDEX idx_pacientes_datos_extra ON pacientes USING GIN (datos_extra);

-- B-Tree
CREATE INDEX idx_pacientes_estado ON pacientes (estado);

CREATE INDEX idx_pacientes_fecha_nacimiento ON pacientes (fecha_nacimiento);

CREATE INDEX idx_pacientes_estado ON pacientes (estado);

CREATE INDEX idx_pacientes_fecha_nacimiento ON pacientes (fecha_nacimiento);

--  Nota de prudencia técnica
-- •	GIN indexa estructura, no semántica
-- •	No abuses de LIKE sobre JSON
-- •	Prefiere @> o ->>

-- Ejemplo elegante:

-- SELECT *
-- FROM pacientes
-- WHERE nombre @> '{"primer_apellido": "Pérez"}';