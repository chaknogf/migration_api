


#ejemplo de uso de los validadores en diferentes servicios
# # En el servicio de migración
# from app.services.validacion import ValidadorPaciente, ValidadorMigracion

# # Validar antes de transformar
# datos_mysql = {
#     "nombre": "Juan",
#     "apellido": "Pérez",
#     "dpi": 1234567890123,
#     "created_at": datetime.now()
# }

# valido, errores = ValidadorMigracion.validar_datos_mysql(datos_mysql)
# if not valido:
#     print(f"Datos inválidos: {errores}")

# # Validar CUI
# cui = 1234567890123
# if es_cui_valido(cui):
#     print("CUI válido")

# # Validar paciente completo después de transformar
# nombre_jsonb = {"primer_nombre": "Juan", "primer_apellido": "Pérez"}
# valido, errores = ValidadorPaciente.validar_paciente_completo(
#     expediente="12345",
#     cui=1234567890123,
#     pasaporte=None,
#     nombre=nombre_jsonb,
#     sexo="M",
#     fecha_nacimiento=date(1990, 1, 1)
# )

# if not valido:
#     print(f"Errores de validación: {errores}")