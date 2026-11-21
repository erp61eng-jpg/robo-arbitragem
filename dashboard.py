from datetime import datetime
import asyncio
import html
import random
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Terminal de Arbitragem", layout="wide")
st.title("🦅 Terminal de Arbitragem (Modo DRY_RUN)")

if "ciclo" not in st.session_state:
    st.session_state.ciclo = 0
if "acumulado" not in st.session_state:
    st.session_state.acumulado = 0.0
if "linhas" not in st.session_state:
    st.session_state.linhas = []

def gerar_dados(lote: float):
    agora = datetime.now().strftime("%H:%M:%S")
    base = [
        ("SOL/USDT", "Bybit -> Binance", round(random.uniform(0.12, 0.28), 4)),
        ("BTC/USDT", "Binance -> Bybit", round(random.uniform(0.06, 0.20), 4)),
        ("ETH/USDT", "Binance Spot/Fut", round(random.uniform(0.02, 0.14), 4)),
        ("BNB/USDT", "BNB -> ETH -> USDT", round(random.uniform(-0.02, 0.09), 4)),
        ("XRP/USDT", "Bybit Spot/Fut", round(random.uniform(-0.05, 0.06), 4)),
    ]
    out = []
    for ativo, rota, sp in base:
        lucro = round(lote * (sp / 100.0), 4)
        score = max(0.0, min(100.0, (sp / 0.25) * 100.0))
        if sp <= 0 or score < 40:
            cor, tag = ("#fee2e2", "#991b1b"), "🔴 FRACA"
        elif score >= 65:
            cor, tag = ("#d1fae5", "#065f46"), "🟢 TOP LUCRO"
        else:
            cor, tag = ("#fef3c7", "#92400e"), "🟡 MODERADA"
        out.append({
            "Hora": agora, "Tag": tag, "Ativo": ativo, "Rota": rota,
            "Spread_%": sp, "Lucro_USDT": lucro, "Score": round(score, 1),
            "bg": cor[0], "fg": cor[1]
        })
    out.sort(key=lambda x: x["Score"], reverse=True)
    return out

with st.sidebar:
    lote = st.number_input("Lote (USDT)", min_value=50.0, value=1000.0, step=100.0)
    gatilho = st.number_input("Gatilho Mínimo (%)", min_value=0.0, value=0.05, step=0.01, format="%.2f")
    if st.button("Zerar"):
        st.session_state.ciclo = 0
        st.session_state.acumulado = 0.0
        st.session_state.linhas = []

if st.button("🔄 Rodar Ciclo Agora", type="primary") or not st.session_state.linhas:
    st.session_state.ciclo += 1
    novas = gerar_dados(lote)
    st.session_state.linhas = novas
    for item in novas:
        if item["Spread_%"] >= gatilho and item["Lucro_USDT"] > 0:
            st.session_state.acumulado = round(st.session_state.acumulado + item["Lucro_USDT"], 4)

c1, c2 = st.columns(2)
c1.metric("Ciclo", f"#{st.session_state.ciclo}")
c2.metric("Lucro Simulado Acumulado", f"$ {st.session_state.acumulado:.4f} USDT")

trs = []
for r in st.session_state.linhas:
    trs.append(
        f"<tr style='background:{r['bg']};color:{r['fg']};border-bottom:2px solid #fff;'>"
        f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Tag'])}</td>"
        f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Ativo'])}</td>"
        f"<td style='padding:8px;'>{html.escape(r['Rota'])}</td>"
        f"<td style='padding:8px;font-weight:700;'>{r['Spread_%']:.4f}%</td>"
        f"<td style='padding:8px;font-weight:700;'>$ {r['Lucro_USDT']:.4f}</td>"
        f"<td style='padding:8px;'>{r['Score']:.1f}</td>"
        f"</tr>"
    )

st.markdown(
    "<table style='width:100%;border-collapse:collapse;font-size:15px;'>"
    "<tr style='background:#1f2937;color:#fff;'>"
    "<th style='padding:8px;text-align:left;'>Qualidade</th>"
    "<th style='padding:8px;text-align:left;'>Ativo</th>"
    "<th style='padding:8px;text-align:left;'>Rota</th>"
    "<th style='padding:8px;text-align:left;'>Spread</th>"
    "<th style='padding:8px;text-align:left;'>Lucro Est.</th>"
    "<th style='padding:8px;text-align:left;'>Score</th>"
    "</tr>" + "".join(trs) + "</table>",
    unsafe_allow_html=True,
)
