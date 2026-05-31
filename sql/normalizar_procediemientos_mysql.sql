CREATE TABLE proce_medicos_backup AS SELECT * FROM proce_medicos;

UPDATE proce_medicos
SET
    procedimiento = 'Gasometría',
    abreviatura = 'GASO'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'GASOMETRA',
        'GASOMETRIA',
        'GASOMETRIA'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Curación de Heridas',
    abreviatura = 'CURA'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'CURACION HERIDAS',
        'CURACIN HERIDAS',
        'CURACIONES'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Vía Central',
    abreviatura = 'CVC'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'COLOCACIN VA CENTRAL',
        'VIA CENTRAL',
        'COLOCACION DE CATETER YUGULAR',
        'COLACION DE CATER CENTRAL SUBCLAVIO',
        'COLACIN CTETER CENTRAL SUBCLAVIO'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Intubación Endotraqueal',
    abreviatura = 'IOT'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'COLOCACIN TUBO ENDOTRAQUEAL',
        'INTUBACIÓN ENDOTRAQUEAL',
        'INTUBACION OROETRAQUEAL',
        'INTUBACIÓN OROTRAQUEAL',
        'TUBO OROTRAQUEAL'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Drenaje de Absceso',
    abreviatura = 'DREAB'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'DRENAJE DE ABSCESO',
        'DRENAJE ABSCESO',
        'DRENAJE ABSCESO'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Biopsia',
    abreviatura = 'BIOP'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'TOMA DE BIOPSIA',
        'TOMA DE BIOPSIAS',
        'BIOPSIA DE CERVIX',
        'BIOPSIA ENDOMETRIAL',
        'BIOPSIA DE TRUCUT',
        'BIOPSIA Y ESCISION DE TUMORES',
        'BIOPSIA DE TUMOR'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Osteosíntesis',
    abreviatura = 'OST'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'OSTEOSINTESIS',
        'OSTEOSINTESIS DE TIBIA',
        'OSTEOSINTESIS DE TOBILLO',
        'OSTEOSINTESIS CLAVICULA',
        'OSTEOSINTESIS HUMERO',
        'OSTEOSINTESIS DEDO ANULAR',
        'OSTEOSINTESUS DE CODO',
        'OSTEOSNTESIS'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Amputación',
    abreviatura = 'AMP'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'AMPUTACION',
        'AMPUTACIN',
        'AMPUTACION DE DEDO',
        'AMPUTACION DE DEDO DE PIE',
        'AMPUTACION DE MUÑECA',
        'AMPUTACION EN RAQUETA DE DEDO',
        'AMPUTACION INFRACONDILEA',
        'AMPUTACION SUPRACONDILEA',
        'AMPUTACION DE ARTEJOS'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Retiro de Material de Osteosíntesis',
    abreviatura = 'RETMO'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'RETIRO DE MATERIAL',
        'RETIRO MATERIAL',
        'RETIRO DE MATERIAL O/S',
        'RETIRO DE CLAVOS',
        'RETIRO DE CLAVOS IM',
        'RETIRO DE FIJACION',
        'RETIRO DE FIJADOR',
        'RETIRO DE FIJADOR EXTERNO',
        'RETIRO TRANSINDESMAL'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Herniorrafia/Hernioplastia',
    abreviatura = 'HERN'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'HERNIORRAFIAS',
        'HERMIORRAFIAS',
        'HERNIOPLASTIAS'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Histerectomía',
    abreviatura = 'HIST'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'HISTERECTOMIA',
        'HISTERECTOMIA ABDOMINAL TOTAL',
        'HISTERECTOMIA VAGINAL',
        'HISTERECTOMIA OBSTETRICA'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Ultrasonido',
    abreviatura = 'USG'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'ULTRASONIDO',
        'ULTRASONIDO GINECOLOGICO',
        'ULTRASONIDO OBSTETRICO',
        'ULTRASONIDO ENDOVAGINAL',
        'ESTUDIO USG',
        'ESTUDIO USG ',
        'USG MUSCULO ESQUELETICO',
        'USG MUSCULO ESQUELETICO SV CLINICA',
        'ULTRASONIDO MUSCULOESQUELETICO',
        'USG MUSCULO ESQUELETICO EN CLINICA'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Radiografía',
    abreviatura = 'RX'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'ESTUDIO RX',
        'RAYOS X',
        'EVALUACION RX',
        'VALORACION RX'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Tomografía Computarizada',
    abreviatura = 'TAC'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'ESTUDIO TAC',
        'TOMOGRAFIAS',
        'EVALUACION TAC',
        'VALORACION TAC',
        'VALORACION TAC 3D'
    );

UPDATE proce_medicos
SET
    procedimiento = 'Resonancia Magnética',
    abreviatura = 'RMN'
WHERE
    UPPER(TRIM(procedimiento)) IN (
        'RMN',
        'ESTUDIO RNM',
        'ESTUDIO RMN',
        'VALORACION RNM'
    );