# Bot Poster SST

Bot separado del sistema de trading para capturar informacion del poster SST,
hallazgos, acciones de mejora, analisis 5 Por Que y generar un Excel listo para
graficas e indicadores.

## Ejecutar Streamlit

```powershell
cd C:\software_phyton\Efra_BOT
python -m streamlit run poster_sst_bot/app_streamlit.py --server.port 8502
```

Abrir:

```text
http://localhost:8502
```

Si lo ejecutas como proyecto independiente desde `C:\software_phyton\BOT_SST`,
usa el puerto recomendado `8503`:

```powershell
cd C:\software_phyton\BOT_SST
python -m streamlit run poster_sst_bot/app_streamlit.py --server.port 8503
```

Abrir:

```text
http://localhost:8503
```

## Ejecutar webhook WhatsApp

```powershell
cd C:\software_phyton\Efra_BOT
python -m uvicorn poster_sst_bot.whatsapp_webhook:app --host 0.0.0.0 --port 8001
```

Variables necesarias para WhatsApp Cloud API:

```text
WHATSAPP_VERIFY_TOKEN=efra_sst_bot
WHATSAPP_ACCESS_TOKEN=<token_meta>
WHATSAPP_PHONE_NUMBER_ID=<id_numero_whatsapp>
BOT_SST_OWNER_WHATSAPP=573186146023
BOT_SST_RESTRICT_TO_OWNER=0
PUBLIC_FILE_BASE_URL=https://tu-dominio-publico/files
```

Para pruebas locales con Meta se necesita exponer el puerto con HTTPS, por
ejemplo con ngrok o Cloudflare Tunnel, y configurar en Meta:

```text
https://tu-dominio-publico/webhook
```

## Formato de mensajes

Poster:

```text
poster
titulo: De la gestion a la inteligencia preventiva
autor: Efrain Sarmiento Crespo
resumen: Texto del resumen
objetivo_general: Transformar registros en inteligencia preventiva
```

Hallazgo:

```text
hallazgo
ITEM: 1
LUGAR / UBICACION / SERVICIO: Cocina
FECHA HALLAZGO O REPORTE: 2026-06-01
HALLAZGO: Piso humedo sin senalizacion
CALIFICACION: Alta
PLAN DE ACCION: Instalar senalizacion y reforzar inspeccion
```

Accion:

```text
accion
FECHA DE IDENTIFICACION: 2026-06-01
TIPO DE ACCION: Correctiva
DETECTADA EN: Inspeccion
REPORTADA POR: SST
DESCRIPCION: Piso humedo
CAUSA RAIZ: Procedimiento incompleto
ACCIONES: Actualizar checklist
ESTADO: Abierto
```

5 Por Que:

```text
5 por que
ID HALLAZGO: 1
PROBLEMA: Piso humedo sin senalizacion
POR QUE 1: No se coloco aviso
POR QUE 2: No habia aviso disponible
POR QUE 3: No hay inventario
POR QUE 4: No hay responsable
POR QUE 5: El procedimiento no lo exige
CAUSA RAIZ VALIDADA: Procedimiento incompleto
ACCION CORRECTIVA: Comprar avisos
ACCION PREVENTIVA: Actualizar procedimiento
```

Exportar:

```text
excel
```

## Salida

Los Excel se generan en:

```text
C:\software_phyton\Efra_BOT\outputs\poster_sst_bot
```

Hojas del archivo:

- Poster
- Hallazgos SST
- Acciones Mejora
- 5 Por Que
- Indicadores
- Predicciones Base
- Diccionario
