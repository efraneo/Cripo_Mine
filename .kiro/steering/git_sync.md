---
inclusion: always
---

# Regla: sincronizar GitHub siempre

**REGLA OBLIGATORIA**: Cada vez que Kiro modifique archivos en la carpeta local del proyecto (`C:\software_phyton\Cripo_Mine`), debe hacer commit y push al repositorio remoto `https://github.com/efraneo/Cripo_Mine` para mantenerlo actualizado y que Streamlit Cloud despliegue los cambios automáticamente.

## Procedimiento de push

Usar siempre estas variables de entorno para evitar el error de permisos en `.gitconfig`:

```powershell
$env:GIT_CONFIG_GLOBAL = "C:\software_phyton\Cripo_Mine\.git_kiro_config"
$env:HOME = "C:\software_phyton\Cripo_Mine"
cd "C:\software_phyton\Cripo_Mine"
git add <archivos>
git commit -m "descripcion clara del cambio"
git push origin main
```

## Archivos que NUNCA se suben al repo

- `.streamlit/secrets.toml` (credenciales — ya está en `.gitignore`)
- `.git_kiro_config` (config temporal de Kiro)
- `data/*.json` (estado local del daemon)
- `data/*.lock`
- `logs/`
- `bin/` (binarios de xmrig)

## Si el push falla por DNS (sandbox de Kiro)

El sandbox de Kiro puede no tener acceso a internet. En ese caso:
1. Hacer el commit igualmente (queda local)
2. Avisar al usuario que ejecute `git push origin main` desde su terminal normal
