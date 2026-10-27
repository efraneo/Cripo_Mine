@echo off
REM ============================================================
REM  VER_PLAN.bat - Cripo_Mine v4.4
REM  Abre el PLAN DE OPCIONES ORDENADAS POR COSTO/BENEFICIO.
REM  Tambien existe una version PDF bonita del plan (entregada
REM  aparte): PLAN_COSTO_BENEFICIO_Cripo_Mine.pdf
REM ============================================================
setlocal
cd /d "%~dp0"
title PLAN COSTO/BENEFICIO - Cripo_Mine
start "" notepad.exe "%~dp0PLAN_COSTO_BENEFICIO.md"
