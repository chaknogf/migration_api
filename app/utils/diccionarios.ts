

export interface Especialidad {
    value: number;
    label: string;
}

export const servicio: Especialidad[] = [
    { value: 1, label: 'Medicina Interna' },
    { value: 2, label: 'Pediatria' },
    { value: 3, label: 'Ginecologia y Obstetricia' },
    { value: 4, label: 'Cirugia' },
    { value: 5, label: 'Traumatologia' },
    { value: 6, label: 'Psicologia' },
    { value: 7, label: 'Nutrición' },



]


export interface Citas {
    value: number;
    label: string;
}

export const citas: Citas[] = [
    { value: 1, label: 'Medicina Interna' }, // MEDI
    { value: 2, label: 'Pediatria' }, // PEDI
    { value: 3, label: 'Ginecologia' }, // GINE
    { value: 4, label: 'Cirugia' }, // CIRU
    { value: 5, label: 'Traumatologia' }, // TRAU
    { value: 6, label: 'Psicologia' }, // PSIC
    { value: 7, label: 'Nutrición' }, // NUTR
    { value: 8, label: 'Obstetricia' }, // OBST
    { value: 9, label: 'especial medicina' } // ESPE


]

export interface Especialistas {
    value: number;
    label: string;
}

export const especialista: Especialistas[] = [
    { value: 1, label: 'Médico Internista' },
    { value: 2, label: 'Médico Pediatria' },
    { value: 3, label: 'Médico Ginecólogo' },
    { value: 4, label: 'Médico Cirujano' },
    { value: 5, label: 'Médico Traumatologo' },
    { value: 6, label: 'Psicologo' },
    { value: 7, label: 'Nutricionista' },
    { value: 8, label: 'Médico General' },


]
export interface Tipos {
    value: number;
    label: string;
}

export const tipo: Tipos[] = [
    { value: 1, label: 'Coex' },
    { value: 2, label: 'Hosp' },
    { value: 3, label: 'Emergencia' },


]
export interface Servicios {
    value: number;
    label: string;
}
export const servicios: Servicios[] = [
    { value: 1, label: 'SOP' },
    { value: 2, label: 'Maternidad' },
    { value: 3, label: 'Ginecologia' },
    { value: 4, label: 'Cirugia' },
    { value: 5, label: 'Cirugia pedia' },
    { value: 6, label: 'Trauma' },
    { value: 7, label: 'Trauma pedia' },
    { value: 8, label: 'CRN' },
    { value: 9, label: 'Pediatria' },
    { value: 10, label: 'RN' },
    { value: 11, label: 'Neonatos' },
    //{ value: 12, label: 'Medicina hombres' },
    //{ value: 13, label: 'Medicina mujeres' },
    //{ value: 14, label: 'vsvs' },
    //{ value: 15, label: 'Covid' },
    //{ value: 16, label: 'labor & parto' },
    { value: 17, label: 'area roja emergencia' },
    { value: 18, label: 'Medicina' },
    { value: 19, label: 'UCIN' },
    { value: 20, label: 'COEX' },
    { value: 21, label: 'Emergencia' },

]

export interface TodoServicios {
    value: number;
    label: string;
}
export const todoservicios: TodoServicios[] = [

    { value: 0, label: 'Emergencia' },
    { value: 1, label: 'SOP' },
    { value: 2, label: 'Maternidad' },
    { value: 3, label: 'Ginecologia' },
    { value: 4, label: 'Cirugia' },
    { value: 5, label: 'Cirugia pedia' },
    { value: 6, label: 'Trauma' },
    { value: 7, label: 'Trauma pedia' },
    { value: 8, label: 'CRN' },
    { value: 9, label: 'Pediatria' },
    { value: 10, label: 'Alojamiento RN' },
    { value: 11, label: 'Neonatos' },
    { value: 12, label: 'Medicina hombres' },
    { value: 13, label: 'Medicina mujeres' },
    { value: 14, label: 'vsvs' },
    { value: 15, label: 'Covid' },
    { value: 16, label: 'labor & parto' },
    { value: 17, label: 'area roja emergencia' },
    { value: 18, label: 'Medicina' },
    { value: 19, label: 'UCIN' },
    { value: 20, label: 'COEX' },
    { value: 21, label: 'Emergencia' },

]

export interface Encamamiento {
    value: number;
    label: string;
}
export const encamamiento: Encamamiento[] = [

    { value: 2, label: 'Maternidad' },
    { value: 3, label: 'Ginecologia' },
    { value: 4, label: 'Cirugia' },
    { value: 5, label: 'Cirugia pedia' },
    { value: 6, label: 'Trauma' },
    { value: 7, label: 'Trauma pedia' },
    { value: 8, label: 'CRN' },
    { value: 9, label: 'Pediatria' },
    { value: 10, label: 'Alojamiento RN' },
    { value: 11, label: 'Neonatos' },
    // { value: 15, label: 'Covid' },
    { value: 18, label: 'Medicina' },
    { value: 19, label: 'UCIN' },




]


export interface Nacionalidad {
    value: number;
    label: string;
}
export const nation: Nacionalidad[] = [

    { value: 1, label: 'Guatemalteca' },
    { value: 2, label: 'Beliceña' },
    { value: 3, label: 'Salvadoreña' },
    { value: 4, label: 'Hondureña' },
    { value: 5, label: 'Nicaragüense' },
    { value: 6, label: 'Costarricense' },
    { value: 7, label: 'Panameña' },
    { value: 8, label: 'Mexicana' },
    { value: 9, label: 'Otro pais' },
    { value: 0, label: 'No indica' },

]



export interface Etnias {
    value: number;
    label: string;
}

export const etnias: Etnias[] = [
    { value: 1, label: 'Ladino' },
    { value: 2, label: 'Maya' },
    { value: 3, label: 'Garífuna' },
    { value: 4, label: 'Xinca' },
    { value: 5, label: 'Otros' },
    { value: 6, label: 'No indica' },
]

export interface Ecivil {
    value: number;
    label: string;
}

export const ecivil: Ecivil[] = [
    { value: 1, label: 'Casado' },
    { value: 2, label: 'Unido' },
    { value: 3, label: 'Soltero' },
]

export interface Academic {
    value: number;
    label: string;
}

export const academic: Academic[] = [
    { value: 1, label: 'No aplica' },
    { value: 2, label: 'Pre Primaria' },
    { value: 3, label: 'Primaria' },
    { value: 4, label: 'Básicos' },
    { value: 5, label: 'Diversificado' },
    { value: 6, label: 'Universidad' },
    { value: 7, label: 'Ninguno' },
    { value: 8, label: 'Otro' },
    { value: 9, label: 'No indica' },
]

export interface Parents {
    value: number;
    label: string;
}

export const parents: Parents[] = [
    { value: 1, label: 'Madre/Padre' },
    { value: 2, label: 'Hijo/a' },
    { value: 3, label: 'Hermano/a' },
    { value: 4, label: 'Abuelo/a' },
    { value: 5, label: 'Tío/a' },
    { value: 6, label: 'Primo/a' },
    { value: 7, label: 'Sobrino/a' },
    { value: 8, label: 'Yerno/Nuera' },
    { value: 9, label: 'Esposo/a' },
    { value: 10, label: 'Suegro/a' },
    { value: 11, label: 'Tutor' },
    { value: 12, label: 'Amistad' },
    { value: 13, label: 'Novio/a' },
    { value: 14, label: 'Cuñado/a' },
    { value: 15, label: 'Nieto/a' },
    { value: 16, label: 'Hijastros' },
    { value: 17, label: 'Padrastros' },
    { value: 18, label: 'Otro' },
]

export interface Lenguage {
    value: number;
    label: string;
}

export const lenguaje: Lenguage[] = [
    { value: 1, label: 'Achi' },
    { value: 2, label: 'Akateka' },
    { value: 3, label: 'Awakateka' },
    { value: 4, label: 'Chorti' },
    { value: 5, label: 'Chalchiteka' },
    { value: 6, label: 'Chuj' },
    { value: 7, label: 'Itza' },
    { value: 8, label: 'Ixil' },
    { value: 9, label: 'Jakalteka' },
    { value: 10, label: 'Kaqchikel' },
    { value: 11, label: 'Kiche' },
    { value: 12, label: 'Mam' },
    { value: 13, label: 'Mopan' },
    { value: 14, label: 'Poqomam' },
    { value: 15, label: 'Pocomchi' },
    { value: 16, label: 'Qanjobal' },
    { value: 17, label: 'Qeqchi' },
    { value: 18, label: 'Sakapulteka' },
    { value: 19, label: 'Sipakapensa' },
    { value: 20, label: 'Tektiteka' },
    { value: 21, label: 'Tzutujil' },
    { value: 22, label: 'Uspanteka' },
    { value: 23, label: 'No indica' },
    { value: 24, label: 'Español' },
    { value: 25, label: 'Otro' },
]
//     lenguage: ""

export interface Status {
    value: number;
    label: string;
}

export const status: Status[] = [
    { value: 1, label: 'activo' },
    { value: 2, label: 'archivado' },
    { value: 3, label: 'prestamo' },
    { value: 4, label: 'egresado' }

]

export interface Estado {
    value: number;
    label: string;
}

export const estado: Estado[] = [
    { value: 1, label: 'Estable' },
    { value: 2, label: 'Delicado' },
    { value: 3, label: 'Fallecido' }
]


export interface Situacion {
    value: number;
    label: string;
}

export const situacion: Situacion[] = [
    { value: 1, label: 'Hospitalizado' },
    { value: 2, label: 'Observación' },
    { value: 3, label: 'Recuperado' },
    { value: 4, label: 'Referido' },
    { value: 5, label: 'Trasladado' },
    { value: 6, label: 'Fugado' },
    { value: 7, label: 'Fallecido' },
]

export interface Referencia {
    value: number;
    label: string;
}

export const referencia: Referencia[] = [
    { value: 1, label: 'Hospital General San Juan De Dios - Guatemala' },
    { value: 2, label: 'Hospital Roosevelt - Guatemala' },
    { value: 3, label: 'Hospital Villa Nueva - Guatemala' },
    { value: 4, label: 'Hospital Regional De Amatitlán - Guatemala' },
    { value: 5, label: 'Hospital Nacional Pedro De Bethancourt - Sacatepequez' },
    { value: 6, label: 'Hospital Nacional Chimaltenango - Chimaltenango' },
    { value: 7, label: 'Hospital Distrital De Tiquisate - Escuintla' },
    { value: 8, label: 'Hospital Regional De Escuitla - Escuintal' },
    { value: 9, label: 'Hospital Intregado El Progreso - El Progreso' },
    { value: 10, label: 'Hospital Regional De Cuilapa - Santa Rosa' },
    { value: 11, label: 'Hospital Nacional Juan De Dios Rodas - Sololá' },
    { value: 12, label: 'Hospital Nacional Dr Jose Felipe Flores-  Totonicapán' },
    { value: 13, label: 'Hospital Nacional Dr Juan Jose Ortega - Quetzaltenango' },
    { value: 14, label: 'Hospital Regional De Occidente San Juan De Dios - Quetzaltenango' },
    { value: 15, label: 'Hospital Antituberculoso Dr Rodolfo Robles - Quetzaltenango' },
    { value: 16, label: 'Hospital Nacional De Mazatenango - Suchitepequez' },
    { value: 17, label: 'Hospital Nacional de Retalhuleu - Retalhuleu' },
    { value: 18, label: 'Hospital Distrital De Malacatán - San Marcos' },
    { value: 19, label: 'Hospital Nacional De San Marcos - San Marcos' },
    { value: 20, label: 'Hospital Distrital De Joyabaj - Quiché' },
    { value: 21, label: 'Hospital Distrital Uspantán - Quiché' },
    { value: 22, label: 'Hospital Nacional Santa Elena - Qiché' },
    { value: 23, label: 'Hospital Nacional De Salamá - Baja Verapaz' },
    { value: 24, label: 'Hospital Distrital Fray Bartolome De Las Casas - Alta Verapaz' },
    { value: 25, label: 'Hospital Nacional Hellen Lossi De Laugerud - Alta Verapaz' },
    { value: 26, label: 'Hospital Distrital La Tinta - Alta Verapaz' },
    { value: 27, label: 'Hospital Regional Dr Antonio Penado - Petén' },
    { value: 28, label: 'Hospital Distrital Melchor De Mencos - Petén' },
    { value: 29, label: 'Hospital Distrital De Sayaxché - Petén' },
    { value: 30, label: 'Hospital Distrital De Poptún - Petén' },
    { value: 31, label: 'Hospital Infantil Elisa Mrtinez - Izabal' },
    { value: 32, label: 'Hospital Nacional De La Amistad Guatemala Japon  - Izabal' },
    { value: 33, label: 'Hospital Regional De Zaacapa - Zacapa' },
    { value: 34, label: 'Hospital Modular Carlos Arana Osorio - Chiquimula' },
    { value: 35, label: 'Hospital Nacional Nicolasa Cruz - Jalapa' },
    { value: 36, label: 'Hospital Nacional Ernestina Viuda De Recinos - Jutiapa' },
    { value: 37, label: 'Hospital Distrital Nebaj - Qiché' },
    { value: 38, label: 'Hospital Antituberculoso San Vicente - Guatemala' },
    { value: 39, label: 'Hospital Infantil de Infectología y Rehabilitación - Guatemala' },
    { value: 40, label: 'Hospital de Salud Mental Dr Federico Mora - Guatemala' },
    { value: 41, label: 'Hospital de Ortopedia y Rehabilitación Dr Jorge V - Guatemala' },
    { value: 42, label: 'IGSS - especificar en notas' },
    { value: 43, label: 'Privado - especificar en notas' },
]

export interface Estadia {
    value: number;
    label: string;
}


export const estadia: Estadia[] = [
    { value: 1, label: 'cama' },
    { value: 2, label: 'camilla' },
    { value: 3, label: 'silla de ruedas' },
    { value: 4, label: 'no aplica' },
    { value: 5, label: 'otro' },
]

export interface Serv {
    value: number;
    label: string;
}


export const serv: Serv[] = [
    { value: 1, label: 'COEX' },
    { value: 2, label: 'Encamamiento' },
    { value: 3, label: 'Emergencia' },
    { value: 4, label: 'SOP emergencia' },
    { value: 5, label: 'SOP electiva' },
    { value: 6, label: 'Maternidad' },
]

export interface Tipo_citas {
    value: number;
    label: string;
}

export const tipo_citas: Tipo_citas[] = [
    { value: 1, label: 'Consulta' },
    { value: 2, label: 'Ingreso - Operatorio' },
    { value: 3, label: 'USG Obstetrico' },
    { value: 4, label: 'USG Pelvico' },
    { value: 5, label: 'Colposcopia' },
    { value: 9, label: 'Especial' },
    { value: 10, label: 'prestamo' }
]

export interface Consult_Coex {
    value: number;
    label: string;
}

export const consult_coex: Consult_Coex[] = [

    { value: 3, label: 'USG Obstetrico' },
    { value: 4, label: 'USG Pelvico' },
    { value: 5, label: 'Colposcopia' },

]

