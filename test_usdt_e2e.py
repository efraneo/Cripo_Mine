# -*- coding: utf-8 -*-
"""E2E: lanza XMRig real 100 s contra unMineable con user USDT:T....worker.

Comprueba (sin adivinar): si el pool autoriza y acepta shares con el formato
de pago USDT, el log del ExternalMiner lo mostrará (evento "authorized" /
"Share aceptado"). Si el formato fuera inválido, XMRig loguea un error de
autorización.
"""
import time

from miner_manager import ExternalMiner

evs = []


def on_event(msg, lvl="info"):
    evs.append((lvl, msg))
    print(f"[{lvl}] {msg}", flush=True)


m = ExternalMiner(
    binary_path=r"bin\xmrig-mo\xmrig.exe",
    pool_url="rx.unmineable.com:3333",
    user="USDT:TUChk95DbGD5LULCjBesKaM7849Zk9hvM9.e2etest",
    password="x", threads=2,
    on_event=on_event,
    on_share=lambda j, n, s: print(f"SHARE: {s}", flush=True),
    on_stats=lambda s: print(f"STATS: hr={s.get('hashrate')} "
                             f"acc={s.get('shares_ok')} rej={s.get('shares_rej')}",
                             flush=True),
)
m.start()
t0 = time.time()
while time.time() - t0 < 100:
    time.sleep(5)
m.stop()
print(f"--- resumen: eventos={len(evs)} shares_ok={m.shares_ok} "
      f"shares_rej={m.shares_rej} ---")
