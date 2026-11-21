from datetime import datetime
import html
import random
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Terminal de Arbitragem no Gráfico", layout="wide")
st.title("🦅 Terminal de Arbitragem — Atuação no Gráfico (DRY_RUN)")

if "ciclo" not in st.session_state:
    st.session_state.ciclo = 0
if "acumulado" not in st.session_state:
    st.session_state.acumulado = 0.0
if "linhas" not in st.session_state:
    st.session_state.linhas = []
if "historico_grafico" not in st.session_state:
    st.session_state.historico_grafico = []

ATIVOS_BASE = [
    ("SOL/USDT", "Bybit -> Binance", 98.50, 0.22),
    ("BTC/USDT", "Binance -> Bybit", 64200.00, 0.14),
    ("ETH/USDT", "Binance Spot/Fut", 2540.00, 0.09),
    ("BNB/USDT", "BNB -> ETH -> USDT", 585.00, 0.04),
    ("XRP/USDT", "Bybit Spot/Fut", 0.5400, -0.02),
]


def gerar_ciclo(lote: float, gatilho: float):
    st.session_state.ciclo += 1
    agora = datetime.now().strftime("%H:%M:%S")
    ciclo_num = st.session_state.ciclo
    novas = []

    for ativo, rota, preco_base, sp_base in ATIVOS_BASE:
        preco = round(preco_base * (1.0 + random.uniform(-0.004, 0.004)), 4)
        sp = round(sp_base + random.uniform(-0.08, 0.12), 4)
        lucro = round(lote * (sp / 100.0), 4)
        score = max(0.0, min(100.0, (sp / 0.25) * 100.0))
        atuou = sp >= gatilho and lucro > 0

        if atuou:
            st.session_state.acumulado = round(st.session_state.acumulado + lucro, 4)

        if sp <= 0 or score < 40:
            bg, fg, tag = "#fee2e2", "#991b1b", "🔴 FRACA"
        elif score >= 65:
            bg, fg, tag = "#d1fae5", "#065f46", "🟢 TOP LUCRO"
        else:
            bg, fg, tag = "#fef3c7", "#92400e", "🟡 MODERADA"

        novas.append({
            "Ciclo": ciclo_num,
            "Hora": agora,
            "Tag": tag,
            "Ativo": ativo,
            "Rota": rota,
            "Preco": preco,
            "Spread_%": sp,
            "Lucro_USDT": lucro,
            "Score": round(score, 1),
            "Atuou": "✅ SIMULOU" if atuou else "⏸️ PULOU",
            "bg": bg,
            "fg": fg,
        })
        st.session_state.historico_grafico.append({
            "Ciclo": ciclo_num,
            "Ativo": ativo,
            "Preco": preco,
            "Spread_%": sp,
            "Lucro_Execucao": lucro if atuou else 0.0,
            "Lucro_Acumulado": st.session_state.acumulado,
            "Atuou_Flag": 1 if atuou else 0,
        })

    novas.sort(key=lambda x: x["Score"], reverse=True)
    st.session_state.linhas = novas


with st.sidebar:
    st.header("⚙️ Controles")
    lote = st.number_input("Lote (USDT)", min_value=50.0, value=1000.0, step=100.0)
    gatilho = st.number_input("Gatilho Mínimo (%)", min_value=0.0, value=0.05, step=0.01, format="%.2f")
    ativo_foco = st.selectbox("Ativo no Gráfico", [a[0] for a in ATIVOS_BASE], index=0)
    if st.button("🧹 Zerar Tudo", use_container_width=True):
        st.session_state.ciclo = 0
        st.session_state.acumulado = 0.0
        st.session_state.linhas = []
        st.session_state.historico_grafico = []

col_btn, col_m1, col_m2 = st.columns([2, 2, 3])
with col_btn:
    if st.button("🔄 Rodar Ciclo & Atuar", type="primary", use_container_width=True) or not st.session_state.linhas:
        gerar_ciclo(lote, gatilho)
with col_m1:
    st.metric("Ciclo Atual", f"#{st.session_state.ciclo}")
with col_m2:
    st.metric("Lucro Simulado Acumulado", f"$ {st.session_state.acumulado:.4f} USDT")

# Gráfico de atuação do robô no ativo escolhido
df_hist = pd.DataFrame(st.session_state.historico_grafico)
if not df_hist.empty:
    st.subheader(f"📈 Atuação do Robô no Gráfico — {ativo_foco}")
    df_ativo = df_hist[df_hist["Ativo"] == ativo_foco].copy()
    if not df_ativo.empty:
        g1, g2 = st.columns(2)
        with g1:
            st.caption("Preço Simulado por Ciclo (onde o robô avalia/atua)")
            st.line_chart(df_ativo.set_index("Ciclo")[["Preco"]], height=220, use_container_width=True)
        with g2:
            st.caption("Spread Líquido (%) vs. Lucro Acumulado (USDT)")
            st.line_chart(
                df_ativo.set_index("Ciclo")[["Spread_%", "Lucro_Acumulado"]],
                height=220,
                use_container_width=True,
            )

# Tabela colorida do ciclo atual
st.subheader("🎯 Radar & Execuções do Ciclo")
trs = []
for r in st.session_state.linhas:
    trs.append(
        f"<tr style='background:{r['bg']};color:{r['fg']};border-bottom:2px solid #fff;'>"
        f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Tag'])}</td>"
        f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Ativo'])}</td>"
        f"<td style='padding:8px;'>{r['Preco']:.4f}</td>"
        f"<td style='padding:8px;font-weight:700;'>{r['Spread_%']:.4f}%</td>"
        f"<td style='padding:8px;font-weight:700;'>$ {r['Lucro_USDT']:.4f}</td>"
        f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Atuou'])}</td>"
        f"</tr>"
    )

st.markdown(
    "<table style='width:100%;border-collapse:collapse;font-size:15px;'>"
    "<tr style='background:#1f2937;color:#fff;'>"
    "<th style='padding:8px;text-align:left;'>Qualidade</th>"
    "<th style='padding:8px;text-align:left;'>Ativo</th>"
    "<th style='padding:8px;text-align:left;'>Preço</th>"
    "<th style='padding:8px;text-align:left;'>Spread</th>"
    "<th style='padding:8px;text-align:left;'>Lucro Est.</th>"
    "<th style='padding:8px;text-align:left;'>Ação do Robô</th>"
    "</tr>" + "".join(trs) + "</table>",
    unsafe_allow_html=True,
)
