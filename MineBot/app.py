# app.py

import streamlit as st
import numpy as np
import random
import matplotlib.pyplot as plt

from solver import DiamondSolver
from regime_engine import RegimeEngine
from autoplay_engine import AutoPlayEngine
from portfolio_engine import PortfolioEngine

st.set_page_config("DiamondBot PRO", layout="centered")
st.title("💎 DiamondBot PRO — Efra BOT")

# ==========================================================
# CONTROLES
# ==========================================================

size = st.slider("Tamaño del tablero", 4, 6, 4, key="size_slider")
mines = st.slider("Minas ocultas", 1, 10, 3, key="mines_slider")
profile = st.selectbox("Perfil de riesgo", ["SAFE", "PRO", "INST"])

assistant_mode = st.toggle("🤖 Mostrar recomendación IA (Manual)")
auto_mode = st.toggle("🔥 Auto AI Execution (Imparable)")
portfolio_mode = st.toggle("🏦 Portfolio Mode (Multi-Board)", key="portfolio_toggle")
ai_policy = st.selectbox(
    "🧠 Política IA",
    ["ULTRA (1 óptima)", "TOP 3 (ranking institucional)"],
    index=0
)

# ==========================================================
# RESET CONTROLADO (SIN CLEAR GLOBAL)
# ==========================================================

def reset_game():
    st.session_state.solver = DiamondSolver(size, mines)

    hidden = [-1] * mines + [1] * (size * size - mines)
    random.shuffle(hidden)

    st.session_state.hidden = hidden
    st.session_state.clicked = [False] * (size * size)
    st.session_state.robot_target = None

if st.button("🔄 Nuevo juego"):
    reset_game()
    st.rerun()

# ==========================================================
# INICIALIZACIÓN ESTABLE
# ==========================================================

if "solver" not in st.session_state:
    reset_game()

solver = st.session_state.solver

# ==========================================================
# PANEL INSTITUCIONAL
# ==========================================================

st.subheader("🏦 Panel Institucional")

p_mine = solver.base_mine_probability()
regime = RegimeEngine.classify(p_mine)

roi = (solver.capital - solver.initial_capital) / solver.initial_capital
sharpe = solver.sharpe()

col1, col2, col3 = st.columns(3)
col1.metric("Capital", f"${solver.capital:.2f}")
col2.metric("ROI", f"{roi*100:.2f}%")
col3.metric("Max DD", f"{solver.max_drawdown*100:.2f}%")

col4, col5, col6 = st.columns(3)
col4.metric("Sharpe", f"{sharpe:.2f}")
col5.metric("Kelly Activo", f"{solver.last_kelly*100:.2f}%")
col6.metric("Régimen", regime)

# ==========================================================
# AUTO AI ESTABLE
# ==========================================================

safe_moves = solver.safest_cells_pro()

recommended_cells = []
confidence_map = {}

if safe_moves:

    if ai_policy.startswith("ULTRA"):
        idx, score = safe_moves[0]
        recommended_cells = [idx]
        confidence_map[idx] = score

    else:  # TOP 3
        top_moves = safe_moves[:3]
        for idx, score in top_moves:
            recommended_cells.append(idx)
            confidence_map[idx] = score

if auto_mode and solver.capital > 0 and recommended_cells:

    best_cell = recommended_cells[0]

    if not st.session_state.clicked[best_cell]:
        st.session_state.clicked[best_cell] = True
        is_diamond = st.session_state.hidden[best_cell] == 1
        solver.register_click(is_diamond, index=best_cell)
        st.rerun()

# ==========================================================
# TABLERO ESTABLE DEFINITIVO
# ==========================================================

st.subheader("🧩 Tablero Interactivo")

robot_target = st.session_state.get("robot_target", None)

for row in range(size):

    cols = st.columns(size)

    for col_idx in range(size):

        i = row * size + col_idx

        if i >= len(st.session_state.clicked):
            continue

        if st.session_state.clicked[i]:

            if st.session_state.hidden[i] == 1:
                cols[col_idx].markdown(
                    "<div style='background:#1f7a1f;height:60px;"
                    "display:flex;align-items:center;"
                    "justify-content:center;border-radius:6px;"
                    "font-size:20px;color:white'>💎</div>",
                    unsafe_allow_html=True
                )
            else:
                cols[col_idx].markdown(
                    "<div style='background:#8b0000;height:60px;"
                    "display:flex;align-items:center;"
                    "justify-content:center;border-radius:6px;"
                    "font-size:20px;color:white'>💥</div>",
                    unsafe_allow_html=True
                )

        else:

            label = ""

            if assistant_mode and i in recommended_cells:

                if ai_policy.startswith("ULTRA"):
                    label = "🤖🔥"

                else:
                    # Ranking institucional
                    rank = recommended_cells.index(i)

                    if rank == 0:
                        label = "🤖🟢"   # Alta confianza
                    elif rank == 1:
                        label = "🤖🟡"   # Media
                    else:
                        label = "🤖🔴"   # Baja

            if cols[col_idx].button(
                label,
                key=f"cell_{i}",
                use_container_width=True
            ):
                st.session_state.clicked[i] = True
                is_diamond = st.session_state.hidden[i] == 1
                solver.register_click(is_diamond, index=i)
                st.rerun()

# ==========================================================
# EQUITY CURVE
# ==========================================================

st.subheader("📈 Equity Curve")

fig2, ax2 = plt.subplots()
ax2.plot(solver.equity_curve)
ax2.set_xlabel("Decisión")
ax2.set_ylabel("Capital")
ax2.set_title("Evolución del Capital")
st.pyplot(fig2)