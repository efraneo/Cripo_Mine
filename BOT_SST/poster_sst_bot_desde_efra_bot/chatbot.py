from __future__ import annotations

from .schema import ACCIONES_COLUMNS, FIVE_WHY_COLUMNS, HALLAZGOS_COLUMNS, POSTER_FIELDS, BotState


class PosterSSTChatbot:
    def __init__(self, state: BotState):
        self.state = state

    def welcome(self) -> str:
        return (
            "Hola. Soy el bot SST para tu poster. Puedo capturar datos del poster, "
            "hallazgos, acciones de mejora, 5 Por Que y generar el Excel para "
            "graficas y predicciones. Escribe: poster, hallazgo, accion, 5 por que, "
            "resumen o exportar. Si quieres que te lleve paso a paso, escribe guiar."
        )

    def handle(self, message: str) -> str:
        text = message.strip()
        low = text.lower()
        if not text:
            return self.welcome()
        if low in {"hola", "inicio", "menu", "ayuda"}:
            return self.with_next_step(self.welcome())
        if low in {"guiar", "guia", "guía", "paso a paso"}:
            self.state.guided_mode = True
            return self.with_next_step("Perfecto. Te voy guiando paso a paso hasta generar el Excel.")
        if low in {"detener guia", "detener guía", "sin guia", "sin guía"}:
            self.state.guided_mode = False
            return "Listo. Detuve la guia paso a paso. Escribe guiar para activarla otra vez."
        if low.startswith("poster\n"):
            updated = self.update_poster_from_text(text.partition("\n")[2])
            return self.with_next_step(f"Actualice {updated} campos del poster.")
        if low.startswith("hallazgo\n"):
            added = self.add_record_from_text("hallazgo", text.partition("\n")[2])
            reply = "Hallazgo registrado." if added else "No pude leer el hallazgo. Usa CAMPO: valor."
            return self.with_next_step(reply)
        if low.startswith("accion\n") or low.startswith("acción\n"):
            added = self.add_record_from_text("accion", text.partition("\n")[2])
            reply = "Accion registrada." if added else "No pude leer la accion. Usa CAMPO: valor."
            return self.with_next_step(reply)
        if low.startswith("5 por que\n") or low.startswith("5 por qué\n"):
            added = self.add_record_from_text("5_por_que", text.partition("\n")[2])
            reply = "Analisis 5 Por Que registrado." if added else "No pude leer el analisis. Usa CAMPO: valor."
            return self.with_next_step(reply)
        if "poster" in low:
            return self._poster_prompt()
        if "hallazgo" in low:
            return self._record_prompt("hallazgo", HALLAZGOS_COLUMNS)
        if "accion" in low or "acción" in low:
            return self._record_prompt("accion", ACCIONES_COLUMNS)
        if "5" in low or "por que" in low or "por qué" in low:
            return self._record_prompt("5 por que", FIVE_WHY_COLUMNS)
        if "resumen" in low:
            return self.with_next_step(self.summary())
        if "export" in low or "excel" in low:
            return self.with_next_step(
                "Listo. En Streamlit usa el boton Generar Excel. Desde WhatsApp, "
                "el servidor puede responderte con el enlace cuando este publicado "
                "en una URL publica o enviado por tu proveedor WhatsApp."
            )
        return self.with_next_step(
            "Te entiendo. Para capturar informacion usa este formato: "
            "campo: valor, un dato por linea. Tambien puedes escribir menu."
        )

    def with_next_step(self, reply: str) -> str:
        if not self.state.guided_mode:
            return reply
        return f"{reply}\n\nSiguiente paso:\n{self.next_step()}"

    def next_step(self) -> str:
        missing = [
            label
            for key, label in POSTER_FIELDS
            if key in {"titulo", "autor", "resumen", "objetivo_general"}
            and not self.state.poster.get(key, "").strip()
        ]
        if missing:
            return (
                "Completa el poster. Envia:\n"
                "poster\n"
                "titulo: ...\n"
                "autor: ...\n"
                "resumen: ...\n"
                "objetivo_general: ...\n"
                f"Faltan: {', '.join(missing)}"
            )
        if not self.state.hallazgos:
            return (
                "Registra el primer hallazgo. Envia:\n"
                "hallazgo\n"
                "ITEM: 1\n"
                "LUGAR / UBICACION / SERVICIO: ...\n"
                "FECHA HALLAZGO O REPORTE: 2026-06-01\n"
                "HALLAZGO: ...\n"
                "CALIFICACION: Alta"
            )
        if not self.state.acciones:
            return (
                "Ahora registra la accion de mejora. Envia:\n"
                "accion\n"
                "FECHA DE IDENTIFICACION: 2026-06-01\n"
                "TIPO DE ACCION: Correctiva\n"
                "DETECTADA EN: Inspeccion\n"
                "REPORTADA POR: SST\n"
                "DESCRIPCION: ...\n"
                "CAUSA RAIZ: ...\n"
                "ACCIONES: ...\n"
                "ESTADO: Abierto"
            )
        if not self.state.five_why:
            return (
                "Haz el analisis 5 Por Que. Envia:\n"
                "5 por que\n"
                "ID HALLAZGO: 1\n"
                "PROBLEMA: ...\n"
                "POR QUE 1: ...\n"
                "POR QUE 2: ...\n"
                "POR QUE 3: ...\n"
                "POR QUE 4: ...\n"
                "POR QUE 5: ...\n"
                "CAUSA RAIZ VALIDADA: ..."
            )
        return "Ya tienes estructura minima. Escribe excel para generar el archivo."

    def update_poster_from_text(self, text: str) -> int:
        data = _parse_key_values(text)
        updated = 0
        allowed = {key for key, _ in POSTER_FIELDS}
        labels = {label.lower(): key for key, label in POSTER_FIELDS}
        for key, value in data.items():
            normalized = key.lower().strip().replace(" ", "_")
            target = normalized if normalized in allowed else labels.get(key.lower().strip())
            if target:
                self.state.poster[target] = value
                updated += 1
        return updated

    def add_record_from_text(self, kind: str, text: str) -> int:
        data = _parse_key_values(text)
        if not data:
            return 0
        if kind == "hallazgo":
            columns = HALLAZGOS_COLUMNS
            self.state.hallazgos.append(_normalize_record(data, columns))
        elif kind == "accion":
            columns = ACCIONES_COLUMNS
            self.state.acciones.append(_normalize_record(data, columns))
        elif kind == "5_por_que":
            columns = FIVE_WHY_COLUMNS
            self.state.five_why.append(_normalize_record(data, columns))
        else:
            return 0
        return 1

    def summary(self) -> str:
        return (
            f"Poster: {self.state.poster.get('titulo', 'sin titulo')}\n"
            f"Hallazgos registrados: {len(self.state.hallazgos)}\n"
            f"Acciones registradas: {len(self.state.acciones)}\n"
            f"Analisis 5 Por Que: {len(self.state.five_why)}"
        )

    def _poster_prompt(self) -> str:
        fields = ", ".join(key for key, _ in POSTER_FIELDS[:8])
        return f"Enviame datos del poster con formato campo: valor. Campos iniciales: {fields}."

    def _record_prompt(self, name: str, columns: list[str]) -> str:
        fields = ", ".join(columns[:6])
        return f"Enviame el registro de {name} con formato CAMPO: valor. Campos clave: {fields}."


def _parse_key_values(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in text.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            data[key] = value
    return data


def _normalize_record(data: dict[str, str], columns: list[str]) -> dict[str, str]:
    normalized = {_clean_key(key): value for key, value in data.items()}
    record: dict[str, str] = {}
    for col in columns:
        record[col] = normalized.get(_clean_key(col), "")
    return record


def _clean_key(value: str) -> str:
    return (
        value.upper()
        .replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
        .replace("Ñ", "N")
        .replace("/", " ")
        .replace("_", " ")
        .replace("-", " ")
        .replace(":", "")
        .strip()
    )
