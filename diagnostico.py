#!/usr/bin/env python3
"""
diagnostico.py — EXAMEN COMPLETO DEL BOT EN UN CLIC (v3.8 DESBLOQUEO)
=====================================================================
¿Hashrate 0? ¿"no hace nada"? Ejecuta esto y sabrás en 1 minuto QUÉ está
pasando y la mayoría de las veces SE ARREGLA SOLO.

Qué revisa (todo en español claro):
  1. Entorno      → python, carpeta, archivos del bot
  2. Secrets      → dirección BTC / wallet XMR / Telegram / Binance / HIDRA
  3. Daemon       → ¿vivo? ¿pausado? ¿control.json pegado? métricas frescas
  4. XMRig        → ¿existe el binario? ¿tamaño sano?
  5. Defender     → ¿admin? ¿exclusiones correctas? ¿amenazas contra xmrig?
  6. POOLS AHORA  → sondeo REAL stratum de cada pool (detecta ZOMBIS)
  7. HIDRA        → récord de hashrate y últimas reparaciones

Y además REPARA solo: restaura/re-descarga xmrig si falta, excluye en
Defender si hay admin, limpia marcas zombi viejas, quita pausas pegadas,
ARRANCA el daemon si está caído y hay credenciales.

Uso:
    python diagnostico.py             # examina + repara + arranca si falta
    python diagnostico.py --solo-ver  # solo examina, no toca nada

Guarda evidencia en data/diagnostico_YYYYmmdd_HHMMSS.json
"""
import argparse
import json
import os
import sys
import time

# ---------------------------------------------------------------------------
ap = argparse.ArgumentParser(description="Examen + reparación del bot")
ap.add_argument("--solo-ver", action="store_true",
                help="solo examinar, no reparar nada")
_args = ap.parse_args()

REPARAR = not _args.solo_ver

import control                      # noqa: E402
import pools_salud                  # noqa: E402
import hidra_minera                 # noqa: E402
from config import BASE_DIR, DATA_DIR, load_secrets  # noqa: E402
from aggressive_engine import TARGETS  # noqa: E402

PROBLEMAS: list = []
REPARADOS: list = []
PENDIENTES: list = []


def linea(txt: str = "", simbolo: str = ""):
    print(f"  {simbolo} {txt}" if simbolo else f"  {txt}", flush=True)


def ok(txt: str):
    linea(txt, "[OK]  ")


def mal(txt: str):
    linea(txt, "[MAL] ")
    PROBLEMAS.append(txt)


def info(txt: str):
    linea(txt, "[..]  ")


def repara(txt: str):
    linea(txt, "[FIX] ")
    REPARADOS.append(txt)


def pend(txt: str):
    linea(txt, "[PEND]")  # requiere mano del usuario
    PENDIENTES.append(txt)


def titulo(t: str):
    print(f"\n=== {t} " + "=" * max(0, 58 - len(t)), flush=True)


# ---------------------------------------------------------------------------
def chk_entorno(cfg: dict):
    titulo("1. ENTORNO")
    info(f"Python {sys.version.split()[0]} · carpeta: {BASE_DIR}")
    faltan = [f for f in ("run_miner.py", "aggressive_engine.py",
                          "miner_manager.py", "config.py", "app.py")
              if not os.path.exists(os.path.join(BASE_DIR, f))]
    if faltan:
        mal(f"Faltan archivos del bot: {', '.join(faltan)} — extrae el ZIP "
            f"v3.8 COMPLETO sobre esta carpeta")
    else:
        ok("Archivos del bot presentes")
    try:
        probe = os.path.join(DATA_DIR, ".probe")
        os.makedirs(DATA_DIR, exist_ok=True)
        open(probe, "w").write("x")
        os.remove(probe)
        ok("Carpeta data/ con permiso de escritura")
    except Exception as e:                      # noqa: BLE001
        mal(f"Carpeta data/ SIN permiso de escritura: {e}")


def chk_secrets(cfg: dict):
    titulo("2. SECRETS (.streamlit/secrets.toml)")
    btc = (cfg.get("BTC_PAYOUT_ADDRESS") or "").strip()
    xmr = (cfg.get("WALLET_XMR") or "").strip()
    if btc:
        ok(f"BTC_PAYOUT_ADDRESS: {btc[:10]}…{btc[-6:]} (pago BTC → Binance)")
    else:
        mal("Falta BTC_PAYOUT_ADDRESS → sin ella unMineable no puede pagarte")
    if xmr:
        ok("WALLET_XMR presente → respaldo MoneroOcean/SupportXMR activo")
    else:
        info("WALLET_XMR vacío → modo SOLO-BTC: unMineable + ZergPool "
             "(ambos pagan BTC directo a Binance)")
    if cfg.get("TELEGRAM_BOT_TOKEN") and cfg.get("TELEGRAM_CHAT_ID"):
        ok("Telegram configurado (alertas al celular)")
    else:
        pend("Telegram sin configurar: no verás alertas en el celular")
    if cfg.get("BINANCE_API_KEY") and cfg.get("BINANCE_API_SECRET"):
        ok("Claves Binance presentes (alertas de depósitos)")
    else:
        info("Binance sin claves: solo pierdes las alertas de depósito")
    if str(cfg.get("HIDRA_ACTIVA", "true")).lower() in ("0", "false", "no"):
        mal("HIDRA_ACTIVA=false → estás sin escudo, médico ni vigía")


def chk_daemon(cfg: dict) -> bool:
    titulo("3. DAEMON (run_miner.py)")
    ctrl = control.read()
    pid = ctrl.get("daemon_pid")
    vivo = control.is_pid_alive(pid)
    if vivo:
        ok(f"Daemon VIVO (PID {pid})")
    else:
        mal("Daemon NO está corriendo (por eso no hay hashrate)")
    if ctrl.get("paused_manual"):
        mal(f"Pausa MANUAL activa ({ctrl.get('updated_by') or '?'}): el "
            f"motor está detenido a propósito — reanuda con /reanudar o "
            f"el botón del dashboard")
    if ctrl.get("paused_thermal"):
        mal("Pausa TÉRMICA activa: el CPU llegó a la temperatura límite; "
            "revisa ventilación o sube CPU_TEMP_MAX en secrets")
    if ctrl.get("force_target"):
        info(f"Cambio forzado pendiente: {ctrl['force_target']}")
    # métricas frescas
    mf = os.path.join(DATA_DIR, "metrics_daemon.json")
    try:
        with open(mf, "r", encoding="utf-8") as f:
            m = json.load(f)
        eda = time.time() - (m.get("ts") or 0)
        hr = (m.get("last") or {}).get("hashrate", 0) or 0
        if eda < 120:
            ok(f"Métricas frescas ({eda:.0f}s): hashrate "
               f"{hr:,.0f} H/s")
        else:
            mal(f"Métricas VIEJAS ({eda/60:.0f} min) → el daemon no está "
                f"escribiendo")
    except Exception:                           # noqa: BLE001
        if vivo:
            mal("metrics_daemon.json no existe aunque el daemon vive "
                "(espera 1-2 min y vuelve a pasar el diagnóstico)")
    ef = os.path.join(DATA_DIR, "engine_state.json")
    try:
        with open(ef, "r", encoding="utf-8") as f:
            e = json.load(f)
        tsel = (e.get("target") or "—")
        edad = (time.time() - (e.get("ts") or 0)) / 60
        info(f"Último objetivo del motor: {tsel} (hace {edad:.0f} min)")
    except Exception:                           # noqa: BLE001
        pass
    return vivo


def chk_xmrig(cfg: dict) -> str:
    titulo("4. XMRIG (el minero)")
    ruta = hidra_minera.binario_vivo(cfg)
    if ruta:
        ok(f"Binario sano: {ruta}")
        return ruta
    mal("xmrig NO está o está incompleto (¿el antivirus lo cuarentenó?)")
    return ""


def chk_defender(cfg: dict):
    titulo("5. DEFENDER / ANTIVIRUS (solo Windows)")
    if os.name != "nt":
        info("No-Windows: sin Defender; si usas otro AV revisa su panel")
        return
    d = hidra_minera.defender_estado(cfg)
    if not d.get("aplica"):
        info("Defender no aplica")
        return
    if d.get("admin"):
        ok("Corriendo como ADMINISTRADOR (el MSR puede aplicarse)")
    else:
        mal("SIN administrador: el mod MSR no se aplica y minas a menos "
            "de la mitad — abre con CORRER_BOT.bat (pide UAC solo)")
    base_low = BASE_DIR.lower()
    excs = [e for e in d.get("exclusiones", []) if base_low in e.lower()]
    procs = d.get("procesos", [])
    if excs and any("xmrig.exe" in p.lower() for p in procs):
        ok(f"Exclusiones correctas ({len(excs)} rutas + proceso xmrig.exe)")
    else:
        mal("Faltan exclusiones de Defender (carpeta bin + .exe + proceso)")
    n = len(d.get("amenazas", []) or [])
    if n:
        mal(f"Defender tiene {n} detecciones contra xmrig → el MÉDICO "
            f"debe restaurarlo de cuarentena")
    if not d.get("servicio"):
        info("Servicio Defender no accesible (¿otro antivirus? excluye "
             "bin\\xmrig-mo a mano en su panel)")


def chk_pools(cfg: dict, reparar: bool):
    titulo("6. POOLS AHORA (sondeo stratum REAL)")
    btc = bool((cfg.get("BTC_PAYOUT_ADDRESS") or "").strip())
    xmr = bool((cfg.get("WALLET_XMR") or "").strip())
    usables = []
    for t in TARGETS:
        try:
            t["_user"] = t["user_fn"](cfg, "probe")
            usables.append(t)
        except ValueError:
            info(f"{t['id']}: sin credenciales en secrets (se ignora)")
    if not usables:
        mal("NINGÚN pool usable: pon BTC_PAYOUT_ADDRESS o WALLET_XMR")
        return
    if reparar:
        for t in usables:            # limpiar marcas zombi → sondeo fresco
            pools_salud.limpiar_marca(t["url"])
    salud = pools_salud.sondear_muchos([t["url"] for t in usables])
    vivos = []
    for t in usables:
        ms = salud.get(t["url"])
        if ms is None:
            mal(f"{t['id']} ({t['url']}): ZOMBI o caído — acepta TCP pero "
                f"NO habla stratum (hashrate 0 si se mina aquí)")
        else:
            ok(f"{t['id']} ({t['url']}): VIVO ({ms:.0f} ms)")
            vivos.append((ms, t))
    vivos.sort(key=lambda x: x[0])
    if not vivos:
        mal("NINGÚN pool responde stratum AHORA: es caída de los pools, "
            "no de tu PC. El bot re-sondea cada ronda y arranca solo en "
            "cuanto uno reviva.")
    else:
        info(f"El motor debe minar en: {vivos[0][1]['id']} (el más rápido "
             f"y vivo)")


def chk_hidra():
    titulo("7. HIDRA (récord y reparaciones)")
    try:
        with open(hidra_minera.STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        best = st.get("best_hashrate") or 0
        if best:
            ok(f"Récord de hashrate: {best:,.0f} H/s")
        acciones = (st.get("acciones") or [])[-3:]
        for a in acciones:
            fecha = time.strftime("%d/%m %H:%M",
                                  time.localtime(a.get("ts", 0) or 0))
            det = ", ".join(a.get("acciones", []) or []) or \
                str(a.get("detalle", ""))[:80]
            info(f"acción {fecha}: {a.get('tipo')} · {det}")
        if not acciones and not best:
            info("Sin historial aún (la hidra no ha tenido que reparar)")
    except Exception:                           # noqa: BLE001
        info("Sin estado de hidra todavía")


# ---------------------------------------------------------------------------
def reparar_y_arrancar(cfg: dict, daemon_vivo: bool):
    titulo("8. AUTO-REPARACIÓN" + (" (desactivada: --solo-ver)"
                                   if not REPARAR else ""))
    if not REPARAR:
        return
    # 1) binario
    if not hidra_minera.binario_vivo(cfg):
        info("Reparando xmrig (restaurar de cuarentena / re-descargar)…")
        ruta = hidra_minera.medico_binario(cfg, on_event=lambda m, l="info":
                                           print(f"    · {m}"))
        if ruta:
            repara(f"xmrig recuperado: {ruta}")
        else:
            pend("No pude recuperar xmrig: ejecuta defender_fix.ps1 como "
                 "ADMINISTRADOR y vuelve a correr este diagnóstico")
    # 2) exclusiones Defender
    if os.name == "nt" and hidra_minera.es_admin():
        hechas = hidra_minera.defender_excluir(cfg)
        if hechas:
            repara(f"Defender: {len(hechas)} exclusiones aplicadas")
        if hidra_minera.defender_restaurar():
            repara("Cuarentena de Defender restaurada")
    elif os.name == "nt":
        pend("Exclusiones de Defender requieren ADMIN: cierra esto y "
             "lanza DIAGNOSTICO.bat o CORRER_BOT.bat aceptando UAC")
    # 3) pausas pegadas con daemon muerto
    ctrl = control.read()
    if not daemon_vivo and (ctrl.get("paused_manual") or
                            ctrl.get("paused_thermal")):
        control.write(paused_manual=False, paused_thermal=False,
                      updated_by="diagnostico")
        repara("Pausas pegadas limpiadas")
    # 4) arranque del daemon
    if not daemon_vivo:
        if (cfg.get("BTC_PAYOUT_ADDRESS") or "").strip() or \
                (cfg.get("WALLET_XMR") or "").strip():
            try:
                pid = control.start_daemon()
                repara(f"Daemon ARRANCADO (PID {pid}); en 1-2 min debe "
                       f"aparecer hashrate y te llega la prueba de "
                       f"ganancias a Telegram")
            except Exception as e:              # noqa: BLE001
                pend(f"No pude arrancar el daemon: {e} — usa "
                     f"CORRER_BOT.bat")
        else:
            pend("No arranco el daemon: faltan direcciones en secrets")


def resumen():
    titulo("RESUMEN")
    print(f"  Problemas detectados : {len(PROBLEMAS)}")
    print(f"  Reparados automático : {len(REPARADOS)}")
    print(f"  Pendientes de ti     : {len(PENDIENTES)}")
    if PROBLEMAS:
        print("\n  FALLÓ:")
        for p in PROBLEMAS:
            print(f"   ✗ {p}")
    if REPARADOS:
        print("\n  ARREGLADO:")
        for r in REPARADOS:
            print(f"   ✓ {r}")
    if PENDIENTES:
        print("\n  TE TOCA A TI:")
        for p in PENDIENTES:
            print(f"   ▶ {p}")
    print("\n  Próximo paso natural: si todo dio OK, el hashrate aparece en "
          "1-2 min\n  en el dashboard y te llega la prueba de ganancias a "
          "Telegram.")
    # evidencia JSON
    try:
        ev = {"ts": time.time(),
              "problemas": PROBLEMAS, "reparados": REPARADOS,
              "pendientes": PENDIENTES,
              "salud_pools": pools_salud.estado_salud()}
        path = os.path.join(
            DATA_DIR, f"diagnostico_{time.strftime('%Y%m%d_%H%M%S')}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ev, f, indent=2)
        print(f"\n  Evidencia guardada: {path}")
    except Exception:                           # noqa: BLE001
        pass


def main():
    print("=" * 64)
    print("  CRIPPO_MINE · DIAGNÓSTICO v3.8 — examen completo del bot")
    print("=" * 64)
    cfg = load_secrets()
    chk_entorno(cfg)
    chk_secrets(cfg)
    daemon_vivo = chk_daemon(cfg)
    chk_xmrig(cfg)
    chk_defender(cfg)
    chk_pools(cfg, REPARAR)
    chk_hidra()
    reparar_y_arrancar(cfg, daemon_vivo)
    resumen()


if __name__ == "__main__":
    main()
