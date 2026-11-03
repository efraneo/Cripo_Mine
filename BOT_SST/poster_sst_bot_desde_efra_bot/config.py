from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "poster_sst_bot"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "poster_sst_bot"

POSTER_DOCX = Path(
    r"C:/Users/sarba/OneDrive/Escritorio/para el congreso/Poster Efrain Sarmiento Crespo.docx"
)
SCHEMA_DOCX = Path(
    r"C:/Users/sarba/OneDrive/Escritorio/para el congreso/ESQUEMA RESUMEN DE PÓSTERES CIENTÍFICOS.docx"
)
CONTROL_HALLAZGOS_XLSX = Path(
    r"C:/1. Escritorio Abril 2026/SGSST/22. SGSST Gastro Bar/6. MEJORAMIENTO/6.2. MEJORA CONTINUA/CONTROL HALLAZGOS SST.xlsx"
)
MATRIZ_ACCIONES_XLS = Path(
    r"C:/1. Escritorio Abril 2026/SGSST/22. SGSST Gastro Bar/6. MEJORAMIENTO/6.2. MEJORA CONTINUA/MATRIZ ACCIONES DE MEJORA SST.xls"
)


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

