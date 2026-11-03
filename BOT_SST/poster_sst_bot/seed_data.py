from __future__ import annotations

from .schema import BotState


def default_state() -> BotState:
    state = BotState()
    state.poster.update(
        {
            "titulo": (
                "DE LA GESTION A LA INTELIGENCIA PREVENTIVA: Ecosistema "
                "inteligente de hallazgos en SST basado en integracion de "
                "registros y analitica de datos."
            ),
            "autor": "Efrain Sarmiento Crespo",
            "institucion": "Clinica San Rafael Alta Complejidad SAS",
            "correo": "sst@clinicasanrafaelac.com",
            "resumen": (
                "La gestion de hallazgos en Seguridad y Salud en el Trabajo "
                "enfrenta limitaciones por registros fragmentados y enfoques "
                "reactivos. El sistema propone integrar inspecciones, hallazgos "
                "y planes de accion para generar trazabilidad, analisis causa "
                "raiz y una base de datos orientada a analitica predictiva."
            ),
            "palabras_clave": (
                "Seguridad y Salud en el Trabajo; Gestion del Riesgo; Analisis "
                "de Causa Raiz; Sistemas de Informacion; Prevencion de Riesgos "
                "Laborales; ISO 45001."
            ),
            "problema": (
                "Registros SST dispersos en multiples formatos que dificultan "
                "la identificacion de patrones, el cierre oportuno y la "
                "prevencion efectiva."
            ),
            "objetivo_general": (
                "Transformar los registros de inspeccion en un sistema integrado "
                "que permita generar inteligencia preventiva mediante datos "
                "estructurados y analisis sistematico de causas raiz."
            ),
            "objetivo_1": (
                "Integrar las herramientas de registro de inspecciones, "
                "hallazgos y planes de accion en un modelo unificado."
            ),
            "objetivo_2": (
                "Implementar la metodologia de analisis causa raiz 5 Por Que "
                "para acciones correctivas y preventivas."
            ),
            "objetivo_3": (
                "Reducir tiempos de cierre y recurrencia mediante trazabilidad "
                "de datos."
            ),
            "objetivo_4": (
                "Establecer una base estructurada para patrones, predicciones "
                "e inteligencia artificial en SST."
            ),
            "alcance": (
                "15 inspecciones mensuales programadas, 10 hallazgos promedio "
                "por mes y aplicacion transversal a sectores industriales."
            ),
            "normatividad": "Decreto 1295/1994, Resolucion 2013/1986.",
            "alineacion_iso": "ISO 45001:2018.",
            "metodologia": (
                "Captura de hallazgos, clasificacion, plan de accion, 5 Por Que, "
                "cierre con evidencias, indicadores y dataset para prediccion."
            ),
            "resultado_tiempo_cierre_antes": "28 dias",
            "resultado_tiempo_cierre_despues": "9 dias",
            "resultado_recurrencia_antes": "32%",
            "resultado_recurrencia_despues": "8%",
            "resultado_causa_raiz_antes": "12%",
            "resultado_causa_raiz_despues": "95%",
            "resultado_trazabilidad_antes": "30%",
            "resultado_trazabilidad_despues": "100%",
        }
    )
    return state

