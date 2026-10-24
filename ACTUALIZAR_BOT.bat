@echo off
REM ============================================================
REM  ACTUALIZAR_BOT.bat - Cripo_Mine (Windows)  [v3.4]
REM  Sincroniza tu carpeta local <-> GitHub con un doble clic:
REM    1) descarga lo nuevo del repo (pull)
REM    2) sube tus cambios locales (commit + push)
REM  Cuando el repo se actualiza, Streamlit Cloud redespliega
REM  la app automaticamente. Nunca mas descargas manuales.
REM  (La primera vez hace el setup guiado: instala git si falta,
REM   conecta la carpeta y pide confirmacion. Despues: instantaneo)
REM ============================================================
setlocal
cd /d "%~dp0"
title Sincronizar Cripo_Mine - GitHub
echo.
echo   ==============================================
echo    SINCRONIZAR BOT  local ^<^>  GitHub
echo    Carpeta: %CD%
echo   ==============================================
echo.
where python >nul 2>nul
if errorlevel 1 (set PY=py -3) else (set PY=python)
%PY% sincronizar.py auto %*
echo.
echo   (Esta ventana puedes cerrarla. Streamlit Cloud se actualizara solo)
pause
