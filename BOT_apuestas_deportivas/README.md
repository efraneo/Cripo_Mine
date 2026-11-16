# 🤖 AI Sports Bet Generator PRO

App **Streamlit** de predicción deportiva asistida por IA (The Odds API + OpenAI),
con un motor estadístico propio que convierte el consenso de las casas de apuestas
en probabilidades justas, detecta valor (+EV) y **mide los aciertos reales** del bot.

## 🧠 El cerebro del bot

| Capa | Qué hace | Origen |
|---|---|---|
| **Consenso sin margen** | Retira el margen (vig) de cada casa por partido/mercado y promedia → probabilidad justa | `market_model.py` (idea: golazo, Sentinel) |
| **Line shopping** | Toma siempre la mejor cuota disponible entre casas | idea: prediction‑tool |
| **Dixon‑Coles anclado al mercado** | Resuelve λ_home/λ_away desde las 1X2 justas → Over/Under 2.5, BTTS, doble oportunidad consistentes | golazo (Dixon & Coles 1997) |
| **Solo picks +EV** | EV = p_justa × cuota − 1; resalta valor ≥ +2% | idea: Sentinel / SportsPredictionBot |
| **Kelly fraccional (¼, tope 5%)** | Tamaño de stake sugerido por pick | Testbett (`kelly.py`) |
| **IA con contexto cuantitativo** | gpt‑4o‑mini (temp 0.2) recibe las probabilidades justas + el historial medido del bot; EV y prob se recalculan en el servidor (no se confía en la IA) | patrón BetAnalyst |
| **Loop de medición** | Los picks se guardan y se **liquidan** (scores API o manual, con cuota de cierre → **CLV**). Métricas: % aciertos, ROI, **Brier**, CLV, desgloses por riesgo/deporte/mercado | disciplina SportsPredictionBot / clv_tracker |

> **Honestidad ante todo:** ningún modelo público bate al cierre del mercado.
> Esta app no vende certezas: mide. El valor real que aporta es consenso justo,
> mejor precio y registro auditable de resultados. Juego responsable 🎲

## 🇨🇴 Liga BetPlay Dimayor (opcional)

The Odds API **no cubre** la Primera A colombiana. Si configuras `football_api`
(API-Football, plan gratuito), aparece una sección **"🇨🇴 Liga BetPlay — análisis IA"**:

- Fixtures de la semana de la Primera A (cacheado: liga 7 días, fixtures 1h)
- **Forma real de cada equipo** (últimos 5: `G/E/P` vía `/fixtures?team=…&last=5`)
- **Análisis IA táctico/estadístico** alimentado con esa forma (sin líneas de valor:
  The Odds API no da cuotas BetPlay)
- Los picks se guardan **sin cuota** → cuentan en % de aciertos, **no ensucian el ROI**

Si tu plan de API-Football incluye `odds` para esta liga (coverage `odds: true`),
el siguiente paso natural es conectar esas líneas al mismo motor de valor (+EV).

## 📁 Estructura

```
app.py             # Navegación + control de membresía/login
auth.py            # Login / registro / recuperación + banner de persistencia
dashboard.py       # Admin: usuarios + 🧠 Rendimiento de picks + 🛠️ Panel MASTER (CRUD + historial)
betting_app.py     # UI del bot: partidos, /sports de la semana, IA, historial
market_model.py    # Motor estadístico (stdlib puro)
betplay.py         # Liga BetPlay vía API-Football (opcional: secret football_api)
database.py        # Persistencia dual: Supabase (Postgres) si hay SUPABASE_URL/KEY; si no, SQLite
SUPABASE_SCHEMA.sql  # Esquema para copiar/pegar en Supabase → SQL Editor
email_sender.py    # Recuperación de contraseña (Gmail SMTP)
payment.py         # Simulador de pago PSE (membresía 30 días)
```

## 🗄️ Supabase — para que NUNCA se borren tus datos (OBLIGATORIO en producción)

Streamlit Cloud **borra el disco en cada redeploy**, así que SQLite (`bot_ad.db`) no sobrevive.
Con Supabase (Postgres gratuito) todo persiste entre redeploys.

**Paso 1** — Crea el proyecto free en [supabase.com](https://supabase.com).
**Paso 2** — En el proyecto: **SQL Editor → New query** → pega **todo** el contenido de
[`SUPABASE_SCHEMA.sql`](SUPABASE_SCHEMA.sql) (incluido en el repo) → **Run**.
Debe crear las tablas `users`, `picks` y `login_history` y mostrarte 3 filas en el SELECT final.
**Paso 3** — **Project Settings → API**: copia la **Project URL** y la **service_role key**
(NO uses la `anon` key: la app corre en el servidor, esa sí puede tocar todo — trátala como una contraseña).
**Paso 4** — En **Streamlit Cloud → App → Settings → Secrets**, pega:

```toml
SUPABASE_URL = "https://tu-proyecto.supabase.co"
SUPABASE_KEY = "eyJhbGciOi...tu service_role key..."
```

**Paso 5** — Redeploy. Deberás ver el banner verde: **"🗄️ Persistencia: Supabase"**.
Si falta algo, la app lo dirá en pantalla ("faltan las tablas" o "corriendo en SQLite local").

> Sin `SUPABASE_URL`/`SUPABASE_KEY` la app funciona igual pero en SQLite local (se borra en redeploy).

### Panel MASTER — control total, solo tú

Si entras con las credenciales maestras, apareces en **Panel Admin** con la sección
**"🛠️ Panel MASTER — Control Total (solo tú)"**:

| Pestaña | Qué permite |
|---|---|
| ✏️ Editar | Edición en tabla: correo, fechas, perfil, estado, membresía, ingresos, análisis. Guarda de una vez. |
| ➕ Crear | Alta manual directa (entra sin aprobación) |
| 🗑️ Borrar | Borrado con confirmación |
| ⏳ Extender tiempo | +7/+30/+90 días (resta desde hoy o desde el vencimiento, lo que sea mayor) → activa membresía paga |
| 🔑 Reset clave | Cambia la clave de cualquier usuario |
| 📜 Historial de ingresos | **Tabla `login_history` independiente**: cada login (normal y master) y cada acción del panel. Solo visible para el acceso master |

Cada acción registra un evento `crud` con detalle en el historial (quién, qué y cuándo).
Los usuarios normales (admin incluido) no ven nada de este panel.

## 🔑 Secrets (Streamlit Cloud → App → Settings → Secrets)

```toml
odds_api     = "tu-clave"        # https://the-odds-api.com/ (h2h + totals)
openai       = "tu-clave"        # OpenAI API key
SUPABASE_URL = "https://tu-proyecto.supabase.co"   # ver sección Supabase ↑
SUPABASE_KEY = "eyJhbGciOi...service_role key..."  # service_role, NUNCA anon
email_user   = "tu-correo@gmail.com"
email_pass   = "app-password"    # Contraseña de aplicación de Google

# Credenciales maestras (acceso super-admin sin pasar por la BD):
USUARIO_MASTER = "tu_usuario_master"
CLAVE_MASTER   = "una clave fuerte"

# 🇨🇴 Liga BetPlay (opcional): análisis IA de la Primera A colombiana vía API-Football
# (https://www.api-football.com — plan free 100 req/día). Sin esta clave, la sección no aparece.
football_api = "tu-clave-api-football"
# FOOTBALL_API_KEY = "..."        # alternativa: igual de válida (mayúsculas, igual que el env)

# Opcionales:
admin_password = "..."           # Clave del admin sembrado en la BD (dasb1512)
openai_model   = "gpt-4o-mini"   # Modelo OpenAI a usar
odds_markets   = "h2h"           # DEFAULT "h2h" (1 crédito/deporte/call). "h2h,totals" = 2× créditos
```

**Reglas del acceso maestro** (igual que tu implementación actual en Secrets):
- Entra como **administrador** (pestañas Panel Admin + Bot) sin aprobación ni pago.
- Si `USUARIO_MASTER` o `CLAVE_MASTER` están **vacíos**, el acceso maestro queda
  deshabilitado por completo (una clave vacía nunca da entrada).
- No se guarda en la BD y la comparación es en tiempo constante.

## 📊 Medición (cómo se "aprende" cada semana)

1. Genera análisis → presiona **💾 Guardar picks** de cada partido.
2. Panel Admin → **🧠 Rendimiento de Picks** → **🔄 Liquidar picks pendientes**
   (auto‑liquidación h2h/1X2 y Over/Under 2.5 hasta 3 días después vía
   `…/scores`), o liquidación manual con cuota de cierre (→ **CLV**).
3. Revisa % aciertos / ROI / Brier / CLV por riesgo, deporte y mercado.
   La IA recibe ese historial en su contexto, de modo que el bot se calibra
   a sí mismo.

## 🚀 Deploy

1. Sube los archivos al repo (ya están en tu rama local).
2. En Streamlit Cloud: **New app** → main file `app.py`.
3. Pega los secrets de arriba → **Deploy**.
4. Entra con `USUARIO_MASTER` / `CLAVE_MASTER`.

## ⚠️ Responsable

Las apuestas implican riesgo de pérdida total. El 55–65% de aciertos en picks
1X2 con cuotas cercanas a 2.0 no garantiza ganancia: la ventaja proviene solo
del precio y de la disciplina de medición.
