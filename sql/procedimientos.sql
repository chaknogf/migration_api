--migration_api/sql/procedimientos.sql
DROP TABLE IF EXISTS procedimientos;

CREATE TABLE procedimientos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    abreviatura VARCHAR(10) UNIQUE,
    nombre VARCHAR(200) NOT NULL UNIQUE,
    descripcion TEXT,
    anestesia INT DEFAULT 0,
);

INSERT INTO
    procedimientos (
        abreviatura,
        nombre,
        descripcion
    )
VALUES (
        'CCUV',
        'Catéter Umbilical Venoso',
        'Colocación de catéter umbilical venoso'
    ),
    (
        'CCUA',
        'Catéter Umbilical Arterial',
        'Colocación de catéter umbilical arterial'
    ),
    (
        'CVC',
        'Vía Central',
        'Colocación de acceso venoso central'
    ),
    (
        'RVC',
        'Retiro de Vía Central',
        'Retiro de acceso venoso central'
    ),
    (
        'SONDA',
        'Colocación de Sonda',
        'Colocación de sonda orogástrica o Foley'
    ),
    (
        'IOT',
        'Intubación Endotraqueal',
        'Colocación de tubo endotraqueal u orotraqueal'
    ),
    (
        'SURF',
        'Administración de Surfactante',
        'Aplicación de surfactante pulmonar'
    ),
    (
        'RCP',
        'Reanimación Cardiopulmonar',
        'Maniobras de reanimación cardiopulmonar'
    ),
    (
        'IO',
        'Acceso Intraóseo',
        'Colocación de acceso intraóseo'
    ),
    (
        'VENO',
        'Venodisección',
        'Acceso venoso mediante venodisección'
    ),
    (
        'CURA',
        'Curación de Heridas',
        'Curación simple o compleja de heridas'
    ),
    (
        'VAC',
        'Manejo de VAC',
        'Colocación, cambio o retiro de sistema VAC'
    ),
    (
        'SUT',
        'Sutura de Herida',
        'Sutura y cierre de heridas'
    ),
    (
        'LYD',
        'Lavado y Debridamiento',
        'Lavado quirúrgico y debridamiento'
    ),
    (
        'DREAB',
        'Drenaje de Absceso',
        'Drenaje de abscesos y colecciones'
    ),
    (
        'DREH',
        'Drenaje de Hematoma',
        'Drenaje de hematomas'
    ),
    (
        'DREQ',
        'Drenaje de Quiste',
        'Drenaje de quistes'
    ),
    (
        'RETPT',
        'Retiro de Puntos',
        'Retiro de puntos de sutura'
    ),
    (
        'RETGR',
        'Retiro de Grapas',
        'Retiro de grapas quirúrgicas'
    ),
    (
        'RETVD',
        'Retiro de Vendaje',
        'Retiro o cambio de vendajes'
    ),
    (
        'RETCN',
        'Retiro de Canales',
        'Retiro de drenajes o canales'
    ),
    (
        'BIOP',
        'Biopsia',
        'Toma de biopsias de cualquier localización'
    ),
    (
        'EXCQ',
        'Escisión de Quiste',
        'Resección de quistes'
    ),
    (
        'EXCM',
        'Escisión de Masa',
        'Resección de masas, tumores o lipomas'
    ),
    (
        'TENO',
        'Tenorrafia',
        'Reparación quirúrgica de tendones'
    ),
    (
        'TENOT',
        'Tenotomía',
        'Sección quirúrgica de tendón'
    ),
    (
        'INJPI',
        'Injerto de Piel',
        'Toma y colocación de injerto cutáneo'
    ),
    (
        'OST',
        'Osteosíntesis',
        'Fijación quirúrgica de fracturas'
    ),
    (
        'RETMO',
        'Retiro de Material de Osteosíntesis',
        'Retiro de clavos, placas o tornillos'
    ),
    (
        'FIJEX',
        'Fijador Externo',
        'Colocación de fijador externo'
    ),
    (
        'RETFI',
        'Retiro de Fijador',
        'Retiro de fijador externo'
    ),
    (
        'MANC',
        'Manipulación Cerrada',
        'Reducción o manipulación cerrada'
    ),
    (
        'ARTC',
        'Artrocentesis',
        'Punción articular diagnóstica o terapéutica'
    ),
    (
        'ARTP',
        'Artroplastia',
        'Reemplazo articular'
    ),
    (
        'ARTD',
        'Artrodesis',
        'Fijación quirúrgica articular'
    ),
    (
        'OSTEO',
        'Osteotomía',
        'Corte quirúrgico de hueso'
    ),
    (
        'AMP',
        'Amputación',
        'Amputación de extremidad o segmento'
    ),
    (
        'CARPO',
        'Liberación de Túnel del Carpo',
        'Descompresión del nervio mediano'
    ),
    (
        'APEN',
        'Apendicectomía',
        'Resección quirúrgica del apéndice'
    ),
    (
        'COLE',
        'Colecistectomía',
        'Resección de vesícula biliar'
    ),
    (
        'LAPE',
        'Laparotomía Exploratoria',
        'Exploración quirúrgica abdominal'
    ),
    (
        'HERN',
        'Herniorrafia/Hernioplastia',
        'Reparación quirúrgica de hernia'
    ),
    (
        'HEMO',
        'Hemorroidectomía',
        'Resección quirúrgica de hemorroides'
    ),
    (
        'PARA',
        'Paracentesis',
        'Punción evacuadora abdominal'
    ),
    (
        'TORA',
        'Toracentesis',
        'Punción evacuadora pleural'
    ),
    (
        'CES',
        'Cesárea',
        'Parto por vía abdominal'
    ),
    (
        'PARTO',
        'Parto Vaginal',
        'Parto eutócico'
    ),
    (
        'AMEU',
        'AMEU',
        'Aspiración Manual Endouterina'
    ),
    (
        'LEGR',
        'Legrado Uterino',
        'Legrado instrumental uterino'
    ),
    (
        'HIST',
        'Histerectomía',
        'Extirpación quirúrgica del útero'
    ),
    (
        'MIOM',
        'Miomectomía',
        'Resección de miomas uterinos'
    ),
    (
        'OOF',
        'Ooforectomía',
        'Resección de ovario'
    ),
    (
        'CISTE',
        'Cistectomía',
        'Resección de quiste'
    ),
    (
        'CERC',
        'Cerclaje Cervical',
        'Cerclaje del cuello uterino'
    ),
    (
        'EPIS',
        'Episiotomía',
        'Incisión perineal obstétrica'
    ),
    (
        'COLPA',
        'Colporrafia',
        'Reparación de pared vaginal'
    ),
    (
        'BAKRI',
        'Balón de Bakri',
        'Colocación de balón hemostático uterino'
    ),
    (
        'BLYN',
        'Sutura B-Lynch',
        'Sutura compresiva uterina'
    ),
    (
        'OTB',
        'Oclusión Tubárica Bilateral',
        'Esterilización femenina'
    ),
    (
        'DIU',
        'Colocación de DIU',
        'Inserción de dispositivo intrauterino'
    ),
    (
        'RDIU',
        'Retiro de DIU',
        'Retiro de dispositivo intrauterino'
    ),
    (
        'JADEL',
        'Implante Jadelle',
        'Colocación o retiro de Jadelle'
    ),
    (
        'PAP',
        'Papanicolaou',
        'Citología cervical'
    ),
    (
        'COLPO',
        'Colposcopía',
        'Evaluación colposcópica'
    ),
    (
        'BIOCER',
        'Biopsia Cervical',
        'Biopsia de cuello uterino'
    ),
    (
        'ORQP',
        'Orquidopexia',
        'Corrección quirúrgica de testículo no descendido'
    ),
    (
        'ORQ',
        'Orquiectomía',
        'Resección de testículo'
    ),
    (
        'HIDR',
        'Hidrocelectomía',
        'Corrección de hidrocele'
    ),
    (
        'POST',
        'Postectomía',
        'Circuncisión'
    ),
    (
        'PROS',
        'Prostatectomía',
        'Resección de próstata'
    ),
    (
        'FAST',
        'FAST',
        'Ultrasonido FAST para trauma'
    ),
    (
        'USG',
        'Ultrasonido',
        'Estudio ultrasonográfico'
    ),
    (
        'RX',
        'Radiografía',
        'Estudio radiológico convencional'
    ),
    (
        'TAC',
        'Tomografía Computarizada',
        'Tomografía axial computarizada'
    ),
    (
        'RMN',
        'Resonancia Magnética',
        'Resonancia magnética nuclear'
    ),
    (
        'DOP',
        'Doppler',
        'Ultrasonido Doppler'
    ),
    (
        'ANGIO',
        'Angiografía',
        'Estudio angiográfico'
    ),
    (
        'ECG',
        'Electrocardiograma',
        'Registro de actividad eléctrica cardíaca'
    ),
    (
        'EMG',
        'Electromiografía',
        'Estudio electrofisiológico muscular'
    ),
    (
        'CENT',
        'Centellograma',
        'Estudio gammagráfico'
    ),
    (
        'GASO',
        'Gasometría',
        'Análisis de gases sanguíneos'
    ),
    (
        'HEMC',
        'Hemocultivo',
        'Cultivo de sangre'
    ),
    (
        'HISP',
        'Hisopado',
        'Toma de muestra por hisopado'
    ),
    (
        'GLUC',
        'Glucometría',
        'Medición de glucosa capilar'
    ),
    (
        'FOTO',
        'Fototerapia',
        'Tratamiento mediante fototerapia'
    ),
    (
        'YESO',
        'Colocación de Yeso',
        'Inmovilización con yeso'
    ),
    (
        'RETY',
        'Retiro de Yeso',
        'Retiro de inmovilización en yeso'
    ),
    (
        'INFIL',
        'Infiltración',
        'Aplicación terapéutica mediante infiltración'
    ),
    (
        'ANES',
        'Procedimiento con Anestesia',
        'Procedimiento realizado bajo anestesia'
    );

UPDATE procedimientos
SET
    anestesia = 1
WHERE
    abreviatura IN (
        'OST',
        'APEN',
        'COLE',
        'LAPE',
        'HERN',
        'HEMO',
        'ARTP',
        'ARTD',
        'OSTEO',
        'AMP',
        'CARPO',
        'TENO',
        'TENOT',
        'INJPI',
        'CES',
        'PARTO',
        'AMEU',
        'LEGR',
        'HIST',
        'MIOM',
        'OOF',
        'CISTE',
        'CERC',
        'COLPA',
        'OTB',
        'BIOCER',
        'ORQP',
        'ORQ',
        'HIDR',
        'POST',
        'PROS',
        'FIJEX'
    );