# -*- coding: utf-8 -*-
"""supervisora_1h.py — SESIÓN MINERA DE 1 HORA con informes cada 5 min.

Orden del dueño (22/10/2026):
  * Ejecutar el bot minero 1 hora con aviso de INICIO y CIERRE a Telegram.
  * Cada 5 minutos: shares aceptados, bloques, hashrate (H/s) del minuto.
  * Que el bot APRENDA a tomar mejores caminos: ranking de objetivos por
    shares/minuto en data/miner_aprendizaje.json (el failover del motor
    ya salta de camino si no hay shares; aquí se mide cuál rinde).

Cómo funciona:
  1. Lanza run_miner.py (motor agresivo: XMRig RandomX -> unMineable ->
     BTC en tu direccion de deposito de Binance) DESACOPLO del proceso.
  2. Lee hashrate/shares de la API de XMRig (:4068) con respaldo en
     data/metrics_daemon.json.
  3. Cada CADA s manda el informe a Telegram y acumula aprendizaje.
  4. A los DURACION s escribe control.action=stop -> el propio daemon
     hace shutdown limpio y avisa su CIERRE; aqui va el RESUMEN final.
  5. Si el daemon muere con la sesion viva, lo relanza (best-effort).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

os.chdir(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import control                      # noqa: E402
import telegram_bot as tg           # noqa: E402
from aggressive_engine import TARGETS  # noqa: E402
from config import load_secrets, format_hashrate  # noqa: E402

CFG = load_secrets()
DURACION = 3600          # 1 hora
CADA = 300               # informe cada 5 minutos
PASO = 30                # latido
API = "http://127.0.0.1:4068/2/summary"
ESTADO = os.path.join("data", "supervisora_1h.json")
APREND = os.path.join("data", "miner_aprendizaje.json")
METRICAS = os.path.join("data", "metrics_daemon.json")
ENGINE_STATE = os.path.join("data", "engine_state.json")
RESULTADO = os.path.join("data", "supervisora_1h_resultado.json")
PAGO = {t["id"]: t.get("pago", "?") for t in TARGETS}
NOMBRE = {"unmineable": "unMineable (BTC → Binance)",
          "moneroocean": "MoneroOcean (XMR)", "supportxmr": "SupportXMR (XMR)"}


def _cargar(ruta, default):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _guardar(ruta, obj):
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def api_xmrig():
    """Resumen vivo de XMRig: hashrate (10s/60s/15m) y shares buenos."""
    try:
        with urllib.request.urlopen(API, timeout=4) as r:
            d = json.load(r)
        hr = d.get("hashrate", {}).get("total", [0, 0, 0]) or [0, 0, 0]
        res = d.get("results", {})
        good = int(res.get("shares_good", 0) or 0)
        bloques = int(res.get("blocks", 0) or 0)
        return {"hr10": float(hr[0] or 0), "hr60": float(hr[1] or 0),
                "shares": good, "bloques": bloques}
    except Exception:
        return None


def metricas_respaldo():
    m = _cargar(METRICAS, {})
    ult = m.get("last_stats") or {}
    hist = m.get("history") or []
    if not ult and hist:
        ult = hist[-1]
    shares = m.get("shares") or []
    good = sum(1 for s in shares
               if str(s.get("status", s) if isinstance(s, dict) else s)
               .lower().startswith(("acept", "accepted", "ok")))
    return {"hr10": float(ult.get("hashrate", 0) or 0),
            "hr60": float(hist[-1].get("hashrate", 0) or 0) if hist else 0.0,
            "shares": good, "bloques": 0}


def objetivo_actual():
    e = _cargar(ENGINE_STATE, {})
    return e.get("target") or "?", e


def aprender(target, shares, dt):
    """Acumula seg y shares por camino (núcleo del aprendizaje de rutas)."""
    ap = _cargar(APREND, {"objetivos": {}, "actualizado": 0})
    objs = ap.setdefault("objetivos", {})
    if ap.get("_ultimo_target") != target:
        # cambió de camino: reinicia la referencia de shares
        ap["_ref_shares"] = shares
        ap["_ultimo_target"] = target
    obj = objs.setdefault(target, {"seg": 0.0, "shares": 0, "muestras": 0})
    delta = max(0, int(shares) - int(ap.get("_ref_shares", shares)))
    ap["_ref_shares"] = shares
    obj["seg"] = round(obj["seg"] + dt, 1)
    obj["shares"] += delta
    obj["muestras"] += 1
    ap["actualizado"] = int(time.time())
    _guardar(APREND, ap)
    return delta


def ranking():
    ap = _cargar(APREND, {"objetivos": {}})
    filas = []
    for tid, o in ap.get("objetivos", {}).items():
        if o["seg"] >= 60:
            tasa = o["shares"] / o["seg"] * 60.0
            filas.append((tasa, tid, o))
    filas.sort(reverse=True)
    return filas


def informe(n, inicio, r, target, delta, restan):
    rk = ranking()
    if rk and rk[0][0] > 0:
        mejor = f"{NOMBRE.get(rk[0][1], rk[0][1])} ({rk[0][0]:.2f} sh/min)"
        tabla = " · ".join(
            f"{NOMBRE.get(t, t).split(' ')[0]} {o['shares']}sh/{o['seg'] / 60:.0f}m"
            for _t, t, o in rk[:3])
    elif rk:
        mejor = "recopilando datos (0 shares hasta ahora)"
        tabla = " · ".join(
            f"{NOMBRE.get(t, t).split(' ')[0]} {o['seg'] / 60:.0f}m sin shares"
            for _t, t, o in rk[:3])
    else:
        mejor = "primeras muestras…"
        tabla = "—"
    minuto = int((time.time() - inicio) // 60)
    texto = (
        f"📊 <b>MINUTO {minuto}/60 · informe {n}</b> · "
        f"{time.strftime('%H:%M:%S')}\n"
        f"🎯 Camino actual: <b>{NOMBRE.get(target, target)}</b>\n"
        f"⛏️ Shares aceptados: <b>{r['shares']}</b> (+{delta} en 5 min)\n"
        f"🔥 Hashrate: <b>{format_hashrate(r['hr10'])}</b> (10 s) · "
        f"{format_hashrate(r.get('hr60') or r['hr10'])} (60 s) = "
        f"<b>{int(r['hr60'] or r['hr10']):,} H/s</b> minuto\n"
        f"🧱 Bloques: {r['bloques']} (los BTC llegan por los shares: "
        f"unMineable convierte y paga a tu Binance)\n"
        f"🧠 Aprendizaje de caminos → mejor: <b>{mejor}</b>\n"
        f"   📐 {tabla}\n"
        f"⏱ Restan <b>{max(0, restan)} min</b>")
    ok = tg.send(CFG, texto, "info")
    _log(f"informe {n}: shares={r['shares']} hr={int(r['hr60'] or r['hr10'])} "
         f"target={target} -> {'enviado' if ok else 'FALLO TG'}")


def arrancar_daemon():
    logf = open(os.path.join("data", "supervisora_daemon.log"), "a",
                encoding="utf-8")
    p = subprocess.Popen(
        [sys.executable, "run_miner.py"],
        stdout=logf, stderr=subprocess.STDOUT,
        cwd=os.getcwd(),
        creationflags=subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NEW_PROCESS_GROUP)
    _log(f"daemon run_miner PID {p.pid}")
    return p.pid


def daemon_vivo():
    if api_xmrig() is not None:
        return True
    for f in (METRICAS, ENGINE_STATE):
        try:
            if time.time() - os.path.getmtime(f) < 180:
                return True
        except OSError:
            pass
    return False


def main():
    inicio = time.time()
    estado = _cargar(ESTADO, {})
    reanudando = False
    if estado and estado.get("sesion") == time.strftime("%Y%m%d") \
            and time.time() - estado.get("inicio", 0) < DURACION + 600:
        # sesión previa sin terminar (reanudación)
        inicio = estado["inicio"]
        reanudando = True
    else:
        estado = {"inicio": int(inicio), "informes": 0, "relanzados": 0,
                  "sesion": time.strftime("%Y%m%d")}
    _guardar(ESTADO, estado)

    arrancar_daemon()
    time.sleep(8)
    r0 = api_xmrig() or metricas_respaldo()
    restan = int((inicio + DURACION - time.time()) // 60)
    tg.send(CFG,
            f"🎛 <b>SESIÓN MINERA · 1 HORA {'(reanudada)' if reanudando else ''}</b>\n"
            f"🕐 Inicio {time.strftime('%H:%M:%S')} · fin ~"
            f"{time.strftime('%H:%M', time.localtime(inicio + DURACION))}\n"
            f"🎯 Motor agresivo: XMRig (RandomX) → unMineable → "
            f"<b>BTC a tu dirección de Binance</b>\n"
            f"⛏️ Shares hoy: {r0['shares']} · hashrate "
            f"{format_hashrate(r0['hr60'] or r0['hr10'])}\n"
            f"📊 Informes cada 5 min: shares, bloques, hashrate H/s y "
            f"camino actual\n"
            f"🧠 Aprendizaje de caminos ON (ranking por shares/minuto)\n"
            f"⏱ Restan {max(0, restan)} min · cierre limpio automático",
            "ok")
    _log(f"inicio enviado (reanudando={reanudando}, shares={r0['shares']})")

    ultimo = time.time()
    n = int(estado.get("informes", 0))
    dt = PASO
    sh_ref = int(r0["shares"])
    while time.time() - inicio < DURACION:
        time.sleep(PASO)
        vivo = daemon_vivo()
        if not vivo and time.time() - inicio < DURACION - 60:
            estado["relanzados"] = estado.get("relanzados", 0) + 1
            _guardar(ESTADO, estado)
            if estado["relanzados"] <= 5:
                _log("daemon caído -> relanzar")
                arrancar_daemon()
                time.sleep(15)
        r = api_xmrig() or metricas_respaldo()
        target, _e = objetivo_actual()
        aprender(target, r["shares"], dt)
        dt = PASO
        if time.time() - ultimo >= CADA:
            ultimo = time.time()
            n += 1
            estado["informes"] = n
            _guardar(ESTADO, estado)
            delta = max(0, int(r["shares"]) - sh_ref)
            sh_ref = int(r["shares"])
            restan = int((inicio + DURACION - time.time()) // 60)
            try:
                informe(n, inicio, r, target, delta, restan)
            except Exception as e:
                _log(f"informe falló: {e}")

    # ---------------- CIERRE: parada limpia del daemon ----------------
    _log("hora cumplida -> stop limpio del daemon")
    try:
        control.write(action="stop", updated_by="supervisora_1h")
    except Exception as e:
        _log(f"control.write falló: {e}")
    time.sleep(20)
    r = api_xmrig() or metricas_respaldo()
    rk = ranking()
    mejor = (f"{NOMBRE.get(rk[0][1], rk[0][1])} ({rk[0][0]:.2f} sh/min)"
             if rk and rk[0][0] > 0 else "sin datos suficientes")
    usado = {t: {"seg": o["seg"], "shares": o["shares"]}
             for _s, t, o in rk}
    resumen = {"inicio_utc": int(inicio), "minutos": DURACION // 60,
               "shares_finales": r["shares"], "hashrate_fin_hr60":
               int(r["hr60"] or r["hr10"]), "objetivos": usado,
               "mejor_camino": mejor, "informes": n,
               "relanzados": estado.get("relanzados", 0)}
    _guardar(RESULTADO, resumen)
    tg.send(CFG,
            f"🏁 <b>FIN DE LA HORA · resumen minero</b>\n"
            f"⛏️ Shares aceptados en la sesión: <b>{r['shares']}</b>\n"
            f"🔥 Hashrate final: <b>{int(r['hr60'] or r['hr10']):,} H/s</b> "
            f"({format_hashrate(r['hr60'] or r['hr10'])})\n"
            f"🧱 Bloques: {r['bloques']}\n"
            f"🧠 Mejor camino del día: <b>{mejor}</b>\n"
            f"📄 Objetivos: {json.dumps(usado, ensure_ascii=False)}\n"
            f"📊 Informes enviados: {n} · relanzados: "
            f"{estado.get('relanzados', 0)}\n"
            f"💤 El daemon recibió la orden de parada limpia (su aviso de "
            f"cierre llega enseguida).\n"
            f"<i>Resultados en data/{os.path.basename(RESULTADO)}</i>",
            "ok")
    _log("resumen final enviado; fin de la supervisora")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
