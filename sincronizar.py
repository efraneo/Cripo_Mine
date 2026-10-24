#!/usr/bin/env python3
"""
sincronizar.py — Auto-commit/push: carpeta local ↔ GitHub (v3.4)
================================================================
Hace que tu carpeta local del bot (ej: C:\\software_phyton\\Cripo_Mine)
y tu repo de GitHub (efraneo/Cripo_Mine) se sincronicen con UN doble
clic en ACTUALIZAR_BOT.bat. Cuando el repo se actualiza, Streamlit
Cloud redespliega la app automáticamente: nunca más descargas manuales.

Comandos:
    python sincronizar.py auto          (default) commit local → pull
                                        --rebase → push
    python sincronizar.py setup         primera vez: conecta esta
                                        carpeta al repo (guiado)
    python sincronizar.py subir         solo commit + push
    python sincronizar.py bajar         solo pull (descarga lo último)
    python sincronizar.py estado        muestra qué cambió sin tocar nada

Ruta de la carpeta: la de este archivo (normal), o el 1er argumento,
o la variable de entorno CRIPPO_REPO_PATH.
Repo remoto: https://github.com/efraneo/Cripo_Mine.git (o env
CRIPPO_REPO_URL). Con --no-confirm no pregunta nada (modo automático).

Seguridad: .gitignore SIEMPRE excluye .streamlit/secrets.toml (tus
claves), data/, logs/, bin/, __pycache__/ y *.zip. Nunca se suben.

Primera vez que hace PUSH: Git Credential Manager (incluido en Git para
Windows) abre tu navegador para autorizar tu cuenta de GitHub. Se hace
UNA sola vez y queda guardado en Windows.
"""
import os
import subprocess
import sys
import time

REPO_URL_DEFAULT = "https://github.com/efraneo/Cripo_Mine.git"
GITIGNORE = """\
# ===== BTC Miner Studio / Cripo_Mine — nunca subir al repo =====
.streamlit/secrets.toml
data/
logs/
bin/
__pycache__/
*.pyc
*.zip
*.log
"""


class SyncError(Exception):
    pass


# ---------------------------------------------------------------------------
def run(args, cwd, check=True):
    """Ejecuta un comando git y devuelve CompletedProcess (texto plano)."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
    except FileNotFoundError:
        raise SyncError(
            "GIT NO ESTÁ INSTALADO. Instálalo (una vez, 2 minutos):\n"
            "  winget install --id Git.Git -e --source winget\n"
            "  o descárgalo de https://git-scm.com/download/win\n"
            "Al instalar deja TODAS las opciones por defecto (incluye el\n"
            "Git Credential Manager que autoriza el push con tu navegador).")
    except subprocess.TimeoutExpired:
        raise SyncError("El comando tardó demasiado: " + " ".join(args))
    if check and r.returncode != 0:
        raise SyncError(f"Fallo: {' '.join(args)}\n{r.stderr.strip()}")
    return r


def git_disponible() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def es_repo(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".git"))


# ---------------------------------------------------------------------------
def rama_remota_default(path: str) -> str:
    """Rama por defecto del remoto (main/master/…) via ls-remote."""
    try:
        r = run(["git", "ls-remote", "--symref", "origin", "HEAD"], path)
        for line in r.stdout.splitlines():
            if line.startswith("ref:"):
                # formato: "ref: refs/heads/main<TAB>HEAD"
                return line.split("refs/heads/")[-1].split()[0].strip()
    except SyncError:
        pass
    for cand in ("main", "master"):
        try:
            run(["git", "rev-parse", "--verify", f"origin/{cand}"], path)
            return cand
        except SyncError:
            continue
    return "main"


def estado_cambios(path: str) -> dict:
    """Clasifica git status --porcelain en {nuevos, modificados, borrados}."""
    r = run(["git", "status", "--porcelain"], path)
    grupos = {"nuevos": [], "modificados": [], "borrados": []}
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        st, nombre = line[:2], line[3:].strip().strip('"')
        if "D" in st:
            grupos["borrados"].append(nombre)
        elif st.strip() == "??" or "A" in st:
            grupos["nuevos"].append(nombre)
        else:
            grupos["modificados"].append(nombre)
    return grupos


def resumen(g: dict) -> str:
    p = []
    if g["nuevos"]:
        p.append(f"+{len(g['nuevos'])} nuevos")
    if g["modificados"]:
        p.append(f"~{len(g['modificados'])} modificados")
    if g["borrados"]:
        p.append(f"-{len(g['borrados'])} borrados")
    return ", ".join(p) if p else "sin cambios"


def _config_base(path: str):
    """Config local mínima: autocrlf + identidad si falta."""
    run(["git", "config", "core.autocrlf", "false"], path)
    r = run(["git", "config", "user.email"], path, check=False)
    if not (r.stdout or "").strip():
        run(["git", "config", "user.name", "efraneo"], path)
        run(["git", "config", "user.email",
             "efraneo@users.noreply.github.com"], path)


def _remoto(path: str) -> str:
    return (os.environ.get("CRIPPO_REPO_URL") or REPO_URL_DEFAULT).strip()


def _gitignore(path: str):
    gi = os.path.join(path, ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8", newline="\n") as f:
            f.write(GITIGNORE)


# ---------------------------------------------------------------------------
def setup(path: str, no_confirm: bool = False):
    """Conecta la carpeta al repo por primera vez (guiado, idempotente)."""
    if not os.path.isdir(path):
        raise SyncError(f"No existe la carpeta: {path}")
    if not git_disponible():
        run(["git", "--version"], path)          # lanza el mensaje claro
    print(f"[setup] Carpeta  : {path}")
    print(f"[setup] Repo     : {_remoto(path)}")

    if not es_repo(path):
        run(["git", "init"], path)
        run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], path)
        print("[setup] Repositorio git inicializado en la carpeta")
    _config_base(path)
    _gitignore(path)

    r = run(["git", "remote", "get-url", "origin"], path, check=False)
    if r.returncode != 0:
        run(["git", "remote", "add", "origin", _remoto(path)], path)
    elif (r.stdout or "").strip() != _remoto(path):
        run(["git", "remote", "set-url", "origin", _remoto(path)], path)

    print("[setup] Descargando estado del repo (fetch)…")
    run(["git", "fetch", "origin", "--prune"], path)
    br = rama_remota_default(path)
    tiene_remoto = run(["git", "rev-parse", "--verify",
                        f"origin/{br}"], path, check=False).returncode == 0

    if tiene_remoto:
        run(["git", "symbolic-ref", "HEAD", f"refs/heads/{br}"], path)
        # Adopta el HISTORIAL remoto sin tocar tus archivos locales:
        run(["git", "reset", "--mixed", f"origin/{br}"], path)
        print(f"[setup] Historial remoto adoptado (rama {br}); tus archivos "
              f"locales quedan como están")
    else:
        print(f"[setup] El repo está vacío o no tiene rama {br}: se creará")

    g = estado_cambios(path)
    print(f"[setup] Diferencias carpeta ↔ repo: {resumen(g)}")
    if g["borrados"]:
        print("  [i] Estos archivos están en el repo pero NO en tu carpeta.")
        print("      El SETUP NO BORRA del repo: se conservan por seguridad.")
        for n in g["borrados"][:20]:
            print("      · ", n)
        if len(g["borrados"]) > 20:
            print(f"      … y {len(g['borrados']) - 20} más")
        print("      (Cuando copies la versión nueva completa y ejecutes "
              "ACTUALIZAR_BOT.bat 'auto', los borrados sí se aplicarán)")
    total = sum(len(v) for v in g.values())
    if total == 0:
        print("[setup] Todo está igual: no hay nada que subir.")
        return
    if not no_confirm:
        resp = input("¿Subir estos cambios al repo? [s/N]: ").strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print("Cancelado. Nada se ha tocado. (Usa --no-confirm para "
                  "modo automático)")
            return
    run(["git", "add", "-A"], path)
    if tiene_remoto:
        # SEGURIDAD: el setup jamás borra del repo. Desescenifica las
        # eliminaciones (los archivos ausentes localmente quedan guardados).
        r = run(["git", "diff", "--cached", "--name-only",
                 "--diff-filter=D"], path, check=False)
        borrados = [l.strip() for l in (r.stdout or "").splitlines()
                    if l.strip()]
        for n in borrados:
            run(["git", "reset", "-q", "--", n], path)
        if borrados:
            print(f"[setup] Conservados en el repo (setup no borra): "
                  f"{', '.join(borrados[:8])}"
                  + (" …" if len(borrados) > 8 else ""))
    run(["git", "commit", "-m", f"sincronizacion inicial "
        f"{time.strftime('%Y-%m-%d %H:%M')}"], path, check=False)
    print(f"[setup] Subiendo a GitHub (1ª vez: se abre el navegador para "
          f"autorizar tu cuenta)…")
    push = run(["git", "push", "-u", "origin", br], path, check=False)
    if push.returncode != 0:
        _error_push(push)
        return
    print(f"[setup] ¡Listo! Repo actualizado. Streamlit Cloud se "
          f"redesplegará solo en 1-3 minutos.")


def _error_push(push):
    err = (push.stderr or "").lower()
    print("[!] El PUSH falló. Motivo:")
    print("    " + (push.stderr or push.stdout or "").strip()[:600])
    if "authentication" in err or "could not read" in err or \
            "terminal prompts disabled" in err or "403" in err:
        print("\nCÓMO AUTORIZAR (elige una):")
        print("  A) En tu PC: abre Git Bash y ejecuta 'git push' dentro de")
        print("     la carpeta: Git Credential Manager abrirá el navegador,")
        print("     inicia sesión como efraneo. Solo la primera vez.")
        print("  B) Token PAT: GitHub → Settings → Developer settings →")
        print("     Personal access tokens (classic) → Generate (marca")
        print("     'repo'). Luego ejecuta: git remote set-url origin")
        print("     https://efraneo:<TU_TOKEN>@github.com/efraneo/"
              "Cripo_Mine.git")
    if "rejected" in err and "fetch first" in err:
        print("  El repo tiene cambios más nuevos: ejecuta de nuevo "
              "ACTUALIZAR_BOT.bat (auto hace pull antes de push).")


def bajar(path: str):
    """Descarga lo último del repo a la carpeta (pull --rebase)."""
    br = rama_remota_default(path)
    print(f"[bajar] git pull --rebase origin {br} …")
    r = run(["git", "pull", "--rebase", "--autostash", "origin", br],
            path, check=False)
    if r.returncode != 0:
        run(["git", "rebase", "--abort"], path, check=False)
        raise SyncError("El pull entró en conflicto y se canceló limpio.\n"
                        "Tus archivos locales NO se tocaron. Si descargaste "
                        "una versión nueva del bot, extrae el ZIP sobre esta "
                        "carpeta y vuelve a ejecutar ACTUALIZAR_BOT.bat.")
    out = (r.stdout or "").strip()
    print("[bajar] " + (out.splitlines()[-1] if out else "ya al día"))


def subir(path: str):
    """Commit de TODO lo cambiado + push (los borrados incluidos)."""
    _config_base(path)
    _gitignore(path)
    g = estado_cambios(path)
    total = sum(len(v) for v in g.values())
    if total == 0:
        print("[subir] Nada que subir: carpeta y repo ya están iguales.")
        return
    print(f"[subir] Cambios detectados: {resumen(g)}")
    run(["git", "add", "-A"], path)
    run(["git", "commit", "-m", f"sync automatico {time.strftime('%Y-%m-%d %H:%M')}"],
        path)
    br = rama_remota_default(path)
    push = run(["git", "push", "origin", br], path, check=False)
    if push.returncode != 0:
        _error_push(push)
        return
    print(f"[subir] Push OK a origin/{br}. Streamlit Cloud redespliega en "
          f"1-3 minutos.")


def auto(path: str, no_confirm: bool = False):
    """Flujo diario: (setup si falta) → commit local → pull → push."""
    if not es_repo(path):
        print("[auto] La carpeta aún no está conectada al repo: lanzo "
              "el setup guiado…\n")
        setup(path, no_confirm)
        return
    _config_base(path)
    _gitignore(path)
    bajar(path)          # primero alinear con el repo
    subir(path)          # luego subir lo local (tu versión nueva gana)


def estado(path: str):
    if not es_repo(path):
        print(f"[estado] {path} NO es un repositorio git todavía "
              f"(ejecuta: python sincronizar.py setup)")
        return
    r = run(["git", "remote", "get-url", "origin"], path, check=False)
    br_r = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], path)
    print(f"[estado] carpeta : {path}")
    print(f"[estado] remoto  : {(r.stdout or '').strip() or '(sin origin)'}")
    print(f"[estado] rama    : {(br_r.stdout or '').strip()}")
    print(f"[estado] cambios : {resumen(estado_cambios(path))}")


# ---------------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:]]
    no_confirm = "--no-confirm" in args
    args = [a for a in args if a != "--no-confirm"]
    cmd = args[0] if args and args[0] in ("setup", "subir", "bajar",
                                          "auto", "estado") else "auto"
    path = ""
    for a in args:
        if a != cmd and not a.startswith("-"):
            path = a
            break
    path = path or os.environ.get("CRIPPO_REPO_PATH") or \
        os.path.dirname(os.path.abspath(__file__))
    try:
        if cmd == "setup":
            setup(path, no_confirm)
        elif cmd == "subir":
            subir(path)
        elif cmd == "bajar":
            bajar(path)
        elif cmd == "estado":
            estado(path)
        else:
            auto(path, no_confirm)
    except SyncError as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
