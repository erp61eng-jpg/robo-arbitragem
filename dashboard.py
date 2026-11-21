import html
import random
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Arbitragem DRY_RUN — Simulador Realista", layout="wide")
st.title("🦅 Arbitragem DRY_RUN — Simulador Realista com Custos")

ATIVOS = [
    ("SOL/USDT", "Bybit -> Binance", 98.50, 0.24),
    ("BTC/USDT", "Binance -> Bybit", 64200.00, 0.16),
    ("ETH/USDT", "Binance Spot/Fut", 2540.00, 0.12),
    ("BNB/USDT", "BNB -> ETH -> USDT", 585.00, 0.08),
    ("XRP/USDT", "Bybit Spot/Fut", 0.5400, 0.05),
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


def _garantir_historico_inicial(lote: float, taxa_ponta: float, slippage: float, transf: float, cotacao: float):
    if st.session_state.hist or st.session_state.ciclo > 0:
        return
    custo_pct = (taxa_ponta * 2.0) + slippage
    acum_tmp = 0.0
    for idx in range(1, 5):
        for ativo, _, _, sp_base in ATIVOS:
            sp_bruto = round(max(0.0, sp_base + (idx - 2.5) * 0.03), 4)
            bruto_usdt = lote * (sp_bruto / 100.0)
            custo_usdt = (lote * (custo_pct / 100.0)) + transf
            liq_usdt = round(bruto_usdt - custo_usdt, 4)
            sp_liq = round((liq_usdt / lote * 100.0) if lote > 0 else 0.0, 4)
            if liq_usdt > 0:
                acum_tmp = round(acum_tmp + liq_usdt, 4)
            st.session_state.hist.append({
                "Ciclo": idx,
                "Ativo": ativo,
                "Sp_Bruto_%": sp_bruto,
                "Sp_Liq_%": sp_liq,
                "Acumulado_USDT": acum_tmp,
            })


def rodar_ciclo(lote: float, taxa_ponta: float, slippage: float, transf: float, cotacao: float, gatilho: float):
    st.session_state.ciclo += 1
    c_num = st.session_state.ciclo
    hora = datetime.now().strftime("%H:%M:%S")
    custo_pct = (taxa_ponta * 2.0) + slippage
    novas = []

    for ativo, rota, preco_base, sp_base in ATIVOS:
        preco = round(preco_base * (1.0 + random.uniform(-0.004, 0.004)), 4)
        sp_bruto = round(max(0.0, sp_base + random.uniform(-0.06, 0.14)), 4)
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
            "Preco": preco,
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

    st.session_state.hist = st.session_state.hist[-250:]
    novas.sort(key=lambda x: x["Liq_USDT"], reverse=True)
    st.session_state.linhas = novas


def renderizar_painel(lote: float, taxa_ponta: float, slippage: float, transf: float, cotacao: float, gatilho: float, ativo_foco: str, executar: bool):
    _garantir_historico_inicial(lote, taxa_ponta, slippage, transf, cotacao)
    if executar or not st.session_state.linhas:
        rodar_ciclo(lote, taxa_ponta, slippage, transf, cotacao, gatilho)

    acum_brl = st.session_state.acum_usdt * cotacao
    custos_brl = st.session_state.custos_usdt * cotacao

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ciclos Rodados", f"#{st.session_state.ciclo}")
    m2.metric("Lucro Líquido Simulado", f"$ {st.session_state.acum_usdt:.4f} USDT", f"R$ {acum_brl:.2f}")
    m3.metric("Custos Descontados", f"$ {st.session_state.custos_usdt:.4f} USDT", f"R$ {custos_brl:.2f}")
    m4.metric("Lote Configurado", f"$ {lote:.0f} USDT", f"~R$ {lote * cotacao:.2f}")

    df_hist = pd.DataFrame(st.session_state.hist)
    if not df_hist.empty:
        df_a = df_hist[df_hist["Ativo"] == ativo_foco].set_index("Ciclo")
        if not df_a.empty:
            st.subheader(f"📈 Spread Bruto vs. Spread Líquido Real — {ativo_foco}")
            g1, g2 = st.columns(2)
            with g1:
                st.caption("Spread Bruto (%) vs. Spread Líquido após Custos (%)")
                st.line_chart(df_a[["Sp_Bruto_%", "Sp_Liq_%"]], height=230)
            with g2:
                st.caption("Lucro Líquido Acumulado Simulado (USDT)")
                st.line_chart(df_a[["Acumulado_USDT"]], height=230)

    st.subheader("🎯 Radar & Execuções do Ciclo")
    trs = []
    for r in st.session_state.linhas:
        trs.append(
            f"<tr style='background:{r['bg']};color:{r['fg']};border-bottom:2px solid #ffffff;'>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>{html.escape(r['Tag'])}</td>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>{html.escape(r['Ativo'])}</td>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>{r['Sp_Liq']:.4f}%</td>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>$ {r['Liq_USDT']:.4f} (R$ {r['Liq_BRL']:.2f})</td>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>{html.escape(r['Acao'])}</td>"
            f"</tr>"
        )

    st.markdown(
        "<div style='width:100%;overflow-x:auto;border-radius:8px;border:1px solid #d1d5db;'>"
        "<table style='width:100%;border-collapse:collapse;font-size:17px;'>"
        "<thead>"
        "<tr style='background:#1f2937;color:#ffffff;font-size:16px;'>"
        "<th style='padding:11px 10px;text-align:left;'>Qualidade</th>"
        "<th style='padding:11px 10px;text-align:left;'>Ativo</th>"
        "<th style='padding:11px 10px;text-align:left;'>Sp. Líquido</th>"
        "<th style='padding:11px 10px;text-align:left;'>Lucro Líquido</th>"
        "<th style='padding:11px 10px;text-align:left;'>Decisão</th>"
        "</tr>"
        "</thead>"
        "<tbody>" + "".join(trs) + "</tbody>"
        "</table>"
        "</div>",
        unsafe_allow_html=True,
    )


with st.sidebar:
    st.header("⚙️ Custos & Controles")
    lote = st.number_input("Lote por Giro (USDT)", min_value=20.0, value=180.0, step=20.0)
    cotacao = st.number_input("Cotação R$ / USDT", min_value=1.0, value=5.50, step=0.10)
    taxa_ponta = st.number_input("Taxa por Ponta (%)", min_value=0.0, value=0.10, step=0.01, format="%.3f")
    slippage = st.number_input("Slippage Total (%)", min_value=0.0, value=0.04, step=0.01, format="%.3f")
    transf = st.number_input("Taxa Transferência (USDT)", min_value=0.0, value=0.00, step=0.25, format="%.2f")
    gatilho = st.number_input("Gatilho Líquido Mínimo (%)", min_value=0.0, value=0.02, step=0.01, format="%.2f")
    ativo_foco = st.selectbox("Ativo no Gráfico", [a[0] for a in ATIVOS], index=0)

    st.divider()
    auto_rodar = st.toggle("▶️ Auto-Ciclo Leve", value=False)
    segundos = st.slider("Intervalo (seg)", min_value=2, max_value=15, value=4)

    if st.button("🧹 Zerar Tudo"):
        st.session_state.ciclo = 0
        st.session_state.acum_usdt = 0.0
        st.session_state.custos_usdt = 0.0
        st.session_state.linhas = []
        st.session_state.hist = []

b1, b2 = st.columns([2, 2])
with b1:
    rodar_1 = st.button("🔄 Rodar 1 Ciclo", type="primary", disabled=auto_rodar)
with b2:
    rodar_10 = st.button("⚡ Simular 10 Ciclos", disabled=auto_rodar)

if rodar_10 and not auto_rodar:
    for _ in range(10):
        rodar_ciclo(lote, taxa_ponta, slippage, transf, cotacao, gatilho)

if auto_rodar:
    st.caption(f"🟢 Auto-ciclo ativo a cada **{segundos}s**.")

    @st.fragment(run_every=segundos)
    def painel_vivo():
        renderizar_painel(lote, taxa_ponta, slippage, transf, cotacao, gatilho, ativo_foco, executar=True)

    painel_vivo()
else:
    renderizar_painel(lote, taxa_ponta, slippage, transf, cotacao, gatilho, ativo_foco, executar=rodar_1)
