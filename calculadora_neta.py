#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calculadora_neta.py — Cripo_Mine v4.4
La REGLA DEL NETO del PLAN_COSTO_BENEFICIO.md (opcion #7):
    NETO/dia = bruto XMR - costo de luz
Mismas formulas y fuentes que probar_ganancias.py (una sola verdad):
    - hashrate real: data/metrics_daemon.json (daemon 24/7) o metrics.json
    - precio XMR: Kraken -> coinpaprika (fallback $600)
    - red Monero: Blockchair (dificultad / 120 s; fallback 6.5 GH/s)
Veredicto:
    NETO > 0        -> MINAR 24/7 (DESVELO) y considerar sumar maquinas
    NETO ≈ 0        -> MINAR solo con el PC encendido por otras razones
    NETO < 0        -> APAGAR el minado en esta maquina (sin perder saldo)
Uso: python calculadora_neta.py
     python calculadora_neta.py --hashrate 1000 --watts 45 --tarifa 0.20 --si
(Sin acentos a proposito: consola de Windows ANSI.)
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from probar_ganancias import (  # noqa: E402
    BLOQUES_DIA, RECOMPENSA_XMR, UMBRAL_MO,
    hashrate_medido, precio_xmr, red_xmr, xmr_por_dia)

PRECIO_DEF = 600.0      # USD/XMR si no hay internet
TARIFA_DEF = 0.20       # USD por kWh (colocar tu tarifa local)
WATTS_DEF = 45.0        # laptop tipico; mira la etiqueta del cargador
HORAS_DEF = 24.0        # 24 h con DESVELO; usa 8 si solo mina de dia


def _num(txt, defecto):
    try:
        return float(str(txt).strip().replace(",", "."))
    except (TypeError, ValueError):
        return defecto


def _fmt_d(x):
    if x <= 0:
        return "ya cruzo el umbral"
    if x > 365:
        return "%.1f anos" % (x / 365.0)
    return "%.1f dias" % x


def pedir(clave, defecto, unidad):
    try:
        raw = input("  %s [%s %s]: " % (clave, _g(defecto), unidad))
    except EOFError:
        raw = ""
    return _num(raw, defecto)


def _g(x):
    return ("%.4g" % x) if x != int(x) else str(int(x))


def main():
    ap = argparse.ArgumentParser(description="Regla del NETO Cripo_Mine")
    ap.add_argument("--hashrate", type=float, default=0.0)
    ap.add_argument("--watts", type=float, default=0.0)
    ap.add_argument("--tarifa", type=float, default=0.0)
    ap.add_argument("--precio", type=float, default=0.0)
    ap.add_argument("--horas", type=float, default=0.0)
    ap.add_argument("--si", action="store_true",
                    help="sin preguntas: usa defaults")
    a = ap.parse_args()

    print("=" * 62)
    print("  CALCULADORA DEL NETO - Cripo_Mine v4.4")
    print("  bruto XMR - luz = ?   (la decision madre del plan)")
    print("=" * 62)

    hr_med, fuente = hashrate_medido()
    if a.hashrate > 0:
        hr, hr_fuente = a.hashrate, "fijado a mano"
    elif hr_med > 0:
        hr, hr_fuente = hr_med, "medido del daemon (%s)" % fuente
    else:
        hr, hr_fuente = 0.0, "sin medicion reciente"
    if not a.si:
        print("\n  Hasrate de TU maquina. Fuente: %s" % hr_fuente)
        if hr <= 0:
            hr = pedir("  hashrate", 500.0, "H/s")
        else:
            hr = pedir("  hashrate", hr, "H/s")
    hr = max(hr, 0.0)

    watts = a.watts or WATTS_DEF
    tarifa = a.tarifa or TARIFA_DEF
    horas = a.horas or HORAS_DEF
    if not a.si:
        print("\n  Electricidad: mira la ETIQUETA del cargador (W) y tu")
        print("  recibo (precio por kWh). Default = laptop 45 W, $0.20/kWh.")
        watts = pedir("  vatios", watts, "W")
        tarifa = pedir("  tarifa", tarifa, "USD/kWh")
        horas = pedir("  horas de minado al dia", horas, "h")
    watts = max(watts, 1.0)
    horas = min(max(horas, 0.0), 24.0)

    px = a.precio or precio_xmr() or PRECIO_DEF
    red = red_xmr()
    red_h = red["hashrate"]

    print("\n" + "-" * 62)
    print("  PRECIOS DEL DIA%s" % ("" if px != PRECIO_DEF else " (sin internet: default)"))
    print("    XMR            : $%.2f" % px)
    print("    Red Monero     : %s H/s%s" % (format(int(red_h), ","),
                                            "" if red["exacto"] else " (fallback)"))
    print("    Tu hashrate    : %s H/s  (%s)" % (format(int(hr), ","), hr_fuente))
    print("-" * 62)

    xmr_dia = xmr_por_dia(hr, red)
    bruto = xmr_dia * px
    kwh = watts * horas / 1000.0
    luz = kwh * tarifa
    neto = bruto - luz
    falta = max(UMBRAL_MO, 0.0)
    eta = falta / xmr_dia if xmr_dia > 0 else float("inf")

    print("\n  RESULTADO (por dia, con %g h de minado):" % horas)
    print("    XMR minado    : %.6f XMR" % xmr_dia)
    print("    INGRESO bruto : $%.4f" % bruto)
    print("    LUZ (%g W x %g h = %.2f kWh a $%.2f): $%.4f" % (
        watts, horas, kwh, tarifa, luz))
    print("    NETO          : %s$%.4f  %s" % (
        "-" if neto < 0 else " ", abs(neto),
        "(PERDIDA)" if neto < 0 else "(DEJA)"))
    print("    Pago MO 0.003 XMR (~$%.2f): en %s minando asi" % (
        falta * px, _fmt_d(eta)))

    bruto24 = (RECOMPENSA_XMR * BLOQUES_DIA * (hr / red_h) * px
               if (hr > 0 and red_h > 0) else 0.0)
    print("\n  Referencia 24/7: bruto $%.4f | luz $%.4f | neto %s$%.4f" % (
        bruto24, watts * 24 / 1000.0 * tarifa,
        "-" if bruto24 - watts * 24 / 1000.0 * tarifa < 0 else " ",
        abs(bruto24 - watts * 24 / 1000.0 * tarifa)))

    meta_h = (10.0 / (px * RECOMPENSA_XMR * BLOQUES_DIA / red_h)) if (
        px > 0 and red_h > 0) else 0.0
    if meta_h > 0:
        print("  Meta $10/dia    : necesita ~%s H/s (%s kH/s) con este precio"
              % (format(int(meta_h), ","), _g(meta_h / 1000.0)))

    print("\n" + "=" * 62)
    if neto > 0.02:
        print("  VEREDICTO: MINAR 24/7 (DESVELO activo).")
        print("  Si el neto > 0 tambien en otra maquina, sumala (opcion #9).")
    elif neto >= -0.02:
        print("  VEREDICTO: EMPATE. Minar SOLO cuando el PC este encendido")
        print("  por otras razones; el daemon respeta el apagado limpio.")
    else:
        print("  VEREDICTO: APAGAR el minado en ESTA maquina (DETENER_TODO).")
        print("  NO pierdes nada: el saldo ya minado queda en el pool.")
        print("  Antes de rendirte: DIAGNOSTICO.bat (el hashrate bajo es")
        print("  la causa mas comun; arreglarlo es gratis).")
    print("=" * 62)
    print("  Ver PLAN_COSTO_BENEFICIO.md (VER_PLAN.bat) para el plan completo.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
