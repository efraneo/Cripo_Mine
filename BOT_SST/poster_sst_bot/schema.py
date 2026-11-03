from __future__ import annotations

from dataclasses import dataclass, field


POSTER_FIELDS = [
    ("titulo", "Titulo del poster"),
    ("autor", "Autor"),
    ("institucion", "Institucion"),
    ("correo", "Correo"),
    ("resumen", "Resumen"),
    ("palabras_clave", "Palabras clave"),
    ("problema", "Problema o contexto"),
    ("objetivo_general", "Objetivo general"),
    ("objetivo_1", "Objetivo especifico 1"),
    ("objetivo_2", "Objetivo especifico 2"),
    ("objetivo_3", "Objetivo especifico 3"),
    ("objetivo_4", "Objetivo especifico 4"),
    ("alcance", "Alcance"),
    ("normatividad", "Normatividad"),
    ("alineacion_iso", "Alineacion ISO 45001"),
    ("metodologia", "Metodologia"),
    ("resultado_tiempo_cierre_antes", "Tiempo de cierre antes"),
    ("resultado_tiempo_cierre_despues", "Tiempo de cierre despues"),
    ("resultado_recurrencia_antes", "Recurrencia antes"),
    ("resultado_recurrencia_despues", "Recurrencia despues"),
    ("resultado_causa_raiz_antes", "Analisis causa raiz antes"),
    ("resultado_causa_raiz_despues", "Analisis causa raiz despues"),
    ("resultado_trazabilidad_antes", "Trazabilidad antes"),
    ("resultado_trazabilidad_despues", "Trazabilidad despues"),
]

HALLAZGOS_COLUMNS = [
    "ITEM",
    "LUGAR / UBICACION / SERVICIO",
    "FECHA HALLAZGO O REPORTE",
    "HALLAZGO",
    "CALIFICACION",
    "PLAN DE ACCION",
    "EVIDENCIAS DE CIERRE",
    "FECHA CIERRE",
    "OBSERVACIONES",
]

ACCIONES_COLUMNS = [
    "FECHA DE IDENTIFICACION",
    "TIPO DE ACCION",
    "DETECTADA EN",
    "REPORTADA POR",
    "CUANTIFICACION ACTO CONDICION SUBESTANDAR",
    "INTERPRETACION DE LA CUANTIFICACION",
    "DESCRIPCION",
    "CAUSA RAIZ",
    "TRATAMIENTO / CORRECCION",
    "ACCIONES",
    "FECHA PROGRAMADA DE CIERRE",
    "FECHA FINAL DE CIERRE",
    "ESTADO",
]

FIVE_WHY_COLUMNS = [
    "ID HALLAZGO",
    "PROBLEMA",
    "POR QUE 1",
    "POR QUE 2",
    "POR QUE 3",
    "POR QUE 4",
    "POR QUE 5",
    "CAUSA RAIZ VALIDADA",
    "ACCION CORRECTIVA",
    "ACCION PREVENTIVA",
]


@dataclass
class BotState:
    poster: dict[str, str] = field(default_factory=dict)
    hallazgos: list[dict[str, str]] = field(default_factory=list)
    acciones: list[dict[str, str]] = field(default_factory=list)
    five_why: list[dict[str, str]] = field(default_factory=list)
    guided_mode: bool = True

    def is_ready_for_export(self) -> bool:
        required = ["titulo", "autor", "resumen", "objetivo_general"]
        return all(self.poster.get(key, "").strip() for key in required)
