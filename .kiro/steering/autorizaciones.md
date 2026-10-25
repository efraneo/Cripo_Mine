---
inclusion: always
---

# Reglas del proyecto Cripo_Mine

## REGLA 1 — Sincronizar GitHub siempre
Cada vez que Kiro modifique archivos locales, hacer commit y push a `https://github.com/efraneo/Cripo_Mine`.

Comando estándar para git (evita error de permisos en .gitconfig):
```powershell
$env:GIT_CONFIG_GLOBAL = "C:\software_phyton\Cripo_Mine\.git_kiro_config"
$env:HOME = "C:\software_phyton\Cripo_Mine"
cd "C:\software_phyton\Cripo_Mine"
git add <archivos>
git commit -m "descripcion"
git push origin main
```

Archivos que NUNCA se suben: `.streamlit/secrets.toml`, `.git_kiro_config`, `data/*.json`, `data/*.lock`, `logs/`, `bin/`

## REGLA 2 — Autorización total
El usuario ha autorizado a Kiro para hacer TODOS los cambios necesarios sin pedir permiso ni confirmación. No mostrar frases como "¿quieres que...?" o "¿te parece bien si...?". Actuar directamente. Se pierde tiempo valioso con esas interrupciones.
