import html
import random
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Simulador Realista (DRY_RUN)", layout="wide")
st.title("🦅 Simulador Realista de Arbitragem (DRY_RUN)")

ATIVOS = [
    ("SOL/USDT", "Bybit -> Binance", 0.24),
    ("BTC/USDT", "Binance -> Bybit", 0.16),
    ("ETH/USDT", "Binance Spot/Fut", 0.12),
    ("BNB/USDT", "BNB -> ETH -> USDT", 0.08),
    ("XRP/USDT", "Bybit Spot/Fut", 0.05),
]

if "ciclo" not in st.session_state:
    st.session_state.ciclo = 0
if "acum_usdt" not in st.session_state:
    st.session_state.acum_usdt = 0.0
if "custos_usdt" not in st.session_state:
    st.session_state.custos_usdt = 0.0
if "linhas" not in st.session_state:
    st.session_state.linhas = []
if "hist" not in st.session_state:
    st.session_state.hist = []


def rodar_uma_rodada(lote: float, taxa_ponta: float, slippage: float, transf: float, cotacao: float, gatilho: float):
    st.session_state.ciclo += 1
    c_num = st.session_state.ciclo
    hora = datetime.now().strftime("%H:%M:%S")
    novas = []

    for ativo, rota, sp_base in ATIVOS:
        sp_bruto = round(max(0.0, sp_base + random.uniform(-0.06, 0.14)), 4)
        custo_pct = (taxa_ponta * 2.0) + slippage
        bruto_usdt = lote * (sp_bruto / 100.0)
        custo_usdt = (lote * (custo_pct / 100.0)) + transf
        liq_usdt = round(bruto_usdt - custo_usdt, 4)
        liq_brl = round(liq_usdt * cotacao, 2)
        sp_liq = round((liq_usdt / lote * 100.0) if lote > 0 else 0.0, 4)

        atuou = (sp_liq >= gatilho) and (liq_usdt > 0)
        if atuou:
            st.session_state.acum_usdt = round(st.session_state.acum_usdt + liq_usdt, 4)
            st.session_state.custos_usdt = round(st.session_state.custos_usdt + custo_usdt, 4)

        if liq_usdt <= 0:
            bg, fg, tag = "#fee2e2", "#991b1b", "🔴 PREJUÍZO / ZERO"
        elif liq_usdt >= 0.50:
            bg, fg, tag = "#d1fae5", "#065f46", "🟢 LUCRO POSITIVO"
        else:
            bg, fg, tag = "#fef3c7", "#92400e", "🟡 MARGEM CURTA"

        novas.append({
            "Hora": hora,
            "Tag": tag,
            "Ativo": ativo,
            "Rota": rota,
            "Sp_Bruto": sp_bruto,
            "Custo_USDT": round(custo_usdt, 4),
            "Sp_Liq": sp_liq,
            "Liq_USDT": liq_usdt,
            "Liq_BRL": liq_brl,
            "Acao": "✅ SIMULOU" if atuou else "❌ PULOU",
            "bg": bg,
            "fg": fg,
        })

        st.session_state.hist.append({
            "Ciclo": c_num,
            "Ativo": ativo,
            "Sp_Bruto_%": sp_bruto,
            "Sp_Liq_%": sp_liq,
            "Acumulado_USDT": st.session_state.acum_usdt,
        })

    st.session_state.hist = st.session_state.hist[-200:]
    novas.sort(key=lambda x: x["Liq_USDT"], reverse=True)
    st.session_state.linhas = novas


with st.sidebar:
    st.header("⚙️ Parâmetros Reais")
    lote = st.number_input("Lote por Giro (USDT)", min_value=20.0, value=180.0, step=20.0)
    cotacao = st.number_input("Cotação R$ / USDT", min_value=1.0, value=5.50, step=0.10)
    taxa_ponta = st.number_input("Taxa por Ponta (%)", min_value=0.0, value=0.10, step=0.01, format="%.3f")
    slippage = st.number_input("Slippage Total (%)", min_value=0.0, value=0.04, step=0.01, format="%.3f")
    transf = st.number_input("Taxa Transferência (USDT)", min_value=0.0, value=0.00, step=0.25, format="%.2f")
    gatilho = st.number_input("Gatilho Líquido Mínimo (%)", min_value=0.0, value=0.02, step=0.01, format="%.2f")
    ativo_foco = st.selectbox("Ativo no Gráfico", [a[0] for a in ATIVOS], index=0)

    if st.button("🧹 Zerar Contadores"):
        st.session_state.ciclo = 0
        st.session_state.acum_usdt = 0.0
        st.session_state.custos_usdt = 0.0
        st.session_state.linhas = []
        st.session_state.hist = []

col_b1, col_b2 = st.columns([2, 2])
with col_b1:
    clicou_1 = st.button("🔄 Rodar 1 Ciclo", type="primary")
with col_b2:
    clicou_10 = st.button("⚡ Simular 10 Ciclos de Uma Vez")

if clicou_10:
    for _ in range(10):
        rodar_uma_rodada(lote, taxa_ponta, slippage, transf, cotacao, gatilho)
elif clicou_1 or not st.session_state.linhas:
    rodar_uma_rodada(lote, taxa_ponta, slippage, transf, cotacao, gatilho)

m1, m2, m3 = st.columns(3)
m1.metric("Ciclos Rodados", f"#{st.session_state.ciclo}")
m2.metric("Lucro Líquido Simulado", f"$ {st.session_state.acum_usdt:.4f} USDT (R$ {st.session_state.acum_usdt * cotacao:.2f})")
m3.metric("Custos Descontados", f"$ {st.session_state.custos_usdt:.4f} USDT (R$ {st.session_state.custos_usdt * cotacao:.2f})")

df_hist = pd.DataFrame(st.session_state.hist)
if not df_hist.empty:
    df_a = df_hist[df_hist["Ativo"] == ativo_foco].set_index("Ciclo")
    if not df_a.empty:
        st.subheader(f"📈 Gráfico — {ativo_foco}")
        g1, g2 = st.columns(2)
        with g1:
            st.caption("Spread Bruto (%) vs. Spread Líquido após Taxas (%)")
            st.line_chart(df_a[["Sp_Bruto_%", "Sp_Liq_%"]], height=220)
        with g2:
            st.caption("Lucro Líquido Acumulado (USDT)")
            st.line_chart(df_a[["Acumulado_USDT"]], height=220)

st.subheader("🎯 Resultado do Último Ciclo (Com Desconto de Taxas)")
trs = []
for r in st.session_state.linhas:
    trs.append(
        f"<tr style='background:{r['bg']};color:{r['fg']};border-bottom:2px solid #fff;'>"
        f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Tag'])}</td>"
        f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Ativo'])}</td>"
        f"<td style='padding:8px;'>{r['Sp_Bruto']:.4f}%</td>"
        f"<td style='padding:8px;'>-$ {r['Custo_USDT']:.4f}</td>"
        f"<td style='padding:8px;font-weight:700;'>{r['Sp_Liq']:.4f}%</td>"
        f"<td style='padding:8px;font-weight:700;'>$ {r['Liq_USDT']:.4f} (R$ {r['Liq_BRL']:.2f})</td>"
        f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Acao'])}</td>"
        f"</tr>"
    )

st.markdown(
    "<table style='width:100%;border-collapse:collapse;font-size:14px;'>"
    "<tr style='background:#1f2937;color:#fff;'>"
    "<th style='padding:8px;text-align:left;'>Status</th>"
    "<th style='padding:8px;text-align:left;'>Ativo</th>"
    "<th style='padding:8px;text-align:left;'>Sp. Bruto</th>"
    "<th style='padding:8px;text-align:left;'>Custos</th>"
    "<th style='padding:8px;text-align:left;'>Sp. Líquido</th>"
    "<th style='padding:8px;text-align:left;'>Lucro Líquido</th>"
    "<th style='padding:8px;text-align:left;'>Decisão</th>"
    "</tr>" + "".join(trs) + "</table>",
    unsafe_allow_html=True,
)
