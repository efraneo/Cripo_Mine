from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .config import OUTPUT_DIR, ensure_directories
from .schema import (
    ACCIONES_COLUMNS,
    FIVE_WHY_COLUMNS,
    HALLAZGOS_COLUMNS,
    POSTER_FIELDS,
    BotState,
)


HEADER_FILL = PatternFill("solid", fgColor="17324D")
SUBHEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
WHITE_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(size=14, bold=True, color="17324D")


def _style_header(ws, row: int, max_col: int) -> None:
    for cell in ws[row][:max_col]:
        cell.fill = HEADER_FILL
        cell.font = WHITE_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _autosize(ws, max_width: int = 55) -> None:
    for index, col in enumerate(ws.columns, start=1):
        letter = get_column_letter(index)
        width = min(max(len(str(cell.value or "")) for cell in col) + 2, max_width)
        ws.column_dimensions[letter].width = max(width, 12)
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def _write_title(ws, title: str, columns: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    cell = ws.cell(1, 1, title)
    cell.font = TITLE_FONT
    cell.fill = SUBHEADER_FILL
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28


def _add_table_sheet(wb: Workbook, name: str, columns: list[str], rows: list[dict[str, str]]) -> None:
    ws = wb.create_sheet(name)
    _write_title(ws, name, len(columns))
    ws.append(columns)
    _style_header(ws, 2, len(columns))
    for row in rows:
        ws.append([row.get(col, "") for col in columns])
    for _ in range(max(10 - len(rows), 0)):
        ws.append([""] * len(columns))
    ws.freeze_panes = "A3"
    _autosize(ws)


def build_workbook(state: BotState, output_path: Path | None = None) -> Path:
    ensure_directories()
    if output_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"poster_sst_dataset_{stamp}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Poster"
    _write_title(ws, "Datos del poster cientifico SST", 3)
    ws.append(["Campo", "Etiqueta", "Valor"])
    _style_header(ws, 2, 3)
    for key, label in POSTER_FIELDS:
        ws.append([key, label, state.poster.get(key, "")])
    ws.freeze_panes = "A3"
    _autosize(ws)

    _add_table_sheet(wb, "Hallazgos SST", HALLAZGOS_COLUMNS, state.hallazgos)
    _add_table_sheet(wb, "Acciones Mejora", ACCIONES_COLUMNS, state.acciones)
    _add_table_sheet(wb, "5 Por Que", FIVE_WHY_COLUMNS, state.five_why)

    indicators = wb.create_sheet("Indicadores")
    _write_title(indicators, "Indicadores para graficas y seguimiento", 6)
    indicators.append(["Indicador", "Antes", "Despues", "Mejora", "Unidad", "Fuente"])
    _style_header(indicators, 2, 6)
    indicators.append(["Tiempo de cierre", 28, 9, "=IF(B3=0,\"\",(B3-C3)/B3)", "dias", "Poster"])
    indicators.append(["Recurrencia", 0.32, 0.08, "=IF(B4=0,\"\",(B4-C4)/B4)", "%", "Poster"])
    indicators.append(["Analisis causa raiz", 0.12, 0.95, "=IF(B5=0,\"\",(C5-B5)/B5)", "%", "Poster"])
    indicators.append(["Trazabilidad", 0.30, 1.00, "=IF(B6=0,\"\",(C6-B6)/B6)", "%", "Poster"])
    indicators["D3"].number_format = "0%"
    indicators["D4"].number_format = "0%"
    indicators["D5"].number_format = "0%"
    indicators["D6"].number_format = "0%"
    chart = BarChart()
    chart.title = "Antes vs despues"
    chart.y_axis.title = "Valor"
    chart.x_axis.title = "Indicador"
    data = Reference(indicators, min_col=2, max_col=3, min_row=2, max_row=6)
    cats = Reference(indicators, min_col=1, min_row=3, max_row=6)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.height = 8
    chart.width = 16
    indicators.add_chart(chart, "H3")
    _autosize(indicators)

    pred = wb.create_sheet("Predicciones Base")
    _write_title(pred, "Base para analitica predictiva SST", 9)
    pred.append(
        [
            "ID",
            "Fecha hallazgo",
            "Servicio",
            "Calificacion",
            "Estado",
            "Dias abiertos",
            "Reincidente",
            "Score riesgo",
            "Prioridad sugerida",
        ]
    )
    _style_header(pred, 2, 9)
    for row in range(3, 103):
        pred.cell(row, 1, f"=IF('Hallazgos SST'!A{row}=\"\",\"\",'Hallazgos SST'!A{row})")
        pred.cell(row, 2, f"=IF('Hallazgos SST'!C{row}=\"\",\"\",'Hallazgos SST'!C{row})")
        pred.cell(row, 3, f"=IF('Hallazgos SST'!B{row}=\"\",\"\",'Hallazgos SST'!B{row})")
        pred.cell(row, 4, f"=IF('Hallazgos SST'!E{row}=\"\",\"\",'Hallazgos SST'!E{row})")
        pred.cell(row, 5, f"=IF('Acciones Mejora'!M{row}=\"\",\"\",'Acciones Mejora'!M{row})")
        pred.cell(row, 6, f"=IF(B{row}=\"\",\"\",IFERROR(TODAY()-B{row},\"\"))")
        pred.cell(row, 7, "No")
        pred.cell(
            row,
            8,
            (
                f"=IF(A{row}=\"\",\"\",MIN(100,"
                f"IF(D{row}=\"Alta\",45,IF(D{row}=\"Media\",30,15))+"
                f"IFERROR(IF(F{row}>30,25,IF(F{row}>15,15,5)),0)+IF(G{row}=\"Si\",25,0)))"
            ),
        )
        pred.cell(row, 9, f"=IF(H{row}=\"\",\"\",IF(H{row}>=70,\"Alta\",IF(H{row}>=45,\"Media\",\"Baja\")))")
    dv = DataValidation(type="list", formula1='"Alta,Media,Baja"', allow_blank=True)
    pred.add_data_validation(dv)
    dv.add("D3:D102")
    dv2 = DataValidation(type="list", formula1='"Abierto,En proceso,Cerrado,Vencido"', allow_blank=True)
    pred.add_data_validation(dv2)
    dv2.add("E3:E102")
    _autosize(pred)

    dictionary = wb.create_sheet("Diccionario")
    _write_title(dictionary, "Diccionario de estructura del bot", 4)
    dictionary.append(["Hoja", "Campo", "Uso", "Origen"])
    _style_header(dictionary, 2, 4)
    for key, label in POSTER_FIELDS:
        dictionary.append(["Poster", key, label, "Poster y esquema resumen"])
    for col in HALLAZGOS_COLUMNS:
        dictionary.append(["Hallazgos SST", col, "Registro de inspeccion y hallazgo", "FOR-SST-19"])
    for col in ACCIONES_COLUMNS:
        dictionary.append(["Acciones Mejora", col, "Plan de mejora y cierre", "FOR-SST-20"])
    for col in FIVE_WHY_COLUMNS:
        dictionary.append(["5 Por Que", col, "Analisis causa raiz", "Poster"])
    _autosize(dictionary)

    wb.save(output_path)
    return output_path
