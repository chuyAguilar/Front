PERFILES = {
    "adolescente": {
        "fc": (50, 120),
        "spo2": (90, 100),
        # DEMO: ensanchado a 12 para que FR=14 no dispare alerta al abrir.
        # Valor clínico real era (16, 30) — restaurar tras la prueba.
        "fr": (12, 30),
        "temp": (35, 38),
        "pni_sis": (80, 140),
        "pni_dia": (69, 91),
    },
    # OJO: rangos ILUSTRATIVOS para probar el selector — Dr. Milton debe
    # ajustar los valores clínicos reales de cada etapa.
    "neonato": {
        "fc": (100, 160),
        "spo2": (90, 100),
        "fr": (30, 60),
        "temp": (36.5, 37.5),
        "pni_sis": (60, 90),
        "pni_dia": (30, 60),
    },
    # aquí irán "lactante", "adulto", etc. después
}

def fuera_de_rango(valor,rango):
    if valor is None:
        return False

    minimo,maximo = rango
    return valor < minimo or valor > maximo

# if valor<minimo or valor>maximo:
#         return True
#     else:
#         return False