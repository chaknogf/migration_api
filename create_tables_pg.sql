-- =============================================================================
-- DDL PostgreSQL: procedimientos + proce_medicos
-- Ejecutar una sola vez (o el script de migración ya hace DROP implícito
-- vía TRUNCATE RESTART IDENTITY CASCADE).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- procedimientos  (catálogo)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS procedimientos CASCADE;

CREATE TABLE procedimientos (
    id          SERIAL PRIMARY KEY,
    abreviatura VARCHAR(10)  UNIQUE,
    nombre      VARCHAR(200) NOT NULL UNIQUE,
    descripcion TEXT,
    anestesia   SMALLINT     NOT NULL DEFAULT 0,
    activo      BOOLEAN      NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE  procedimientos             IS 'Catálogo de procedimientos médicos';
COMMENT ON COLUMN procedimientos.abreviatura IS 'Código corto único (ej: APEN, CES)';
COMMENT ON COLUMN procedimientos.anestesia   IS '1 = requiere anestesia, 0 = no';

-- -----------------------------------------------------------------------------
-- proce_medicos  (registros operativos, normalizada)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS proce_medicos CASCADE;

CREATE TABLE proce_medicos (
    id               SERIAL PRIMARY KEY,
    fecha            DATE,
    servicio         INT,
    sexo             CHAR(1)   CHECK (sexo IN ('M', 'F')),

    -- FK al catálogo (reemplaza abreviatura + procedimiento)
    id_procedimiento INT       REFERENCES procedimientos(id) ON DELETE SET NULL,

    especialidad     INT,
    cantidad         INT       NOT NULL DEFAULT 1 CHECK (cantidad >= 1),

    -- FK a médicos (ya migrada)
    medico           INT       REFERENCES medicos(id) ON DELETE SET NULL,

    anestesia        SMALLINT  NOT NULL DEFAULT 0,
    created_by       VARCHAR(10),
    created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  proce_medicos                  IS 'Registro de procedimientos realizados';
COMMENT ON COLUMN proce_medicos.id_procedimiento IS 'FK a procedimientos.id (normalizado)';
COMMENT ON COLUMN proce_medicos.cantidad         IS 'Número de veces que se realizó el procedimiento';

-- Índices útiles para consultas frecuentes
CREATE INDEX idx_proce_medicos_fecha      ON proce_medicos (fecha);
CREATE INDEX idx_proce_medicos_medico     ON proce_medicos (medico);
CREATE INDEX idx_proce_medicos_proc       ON proce_medicos (id_procedimiento);
CREATE INDEX idx_proce_medicos_servicio   ON proce_medicos (servicio);
