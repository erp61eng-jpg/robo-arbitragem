from datetime import datetime
import html
import random
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Simulador Realista com Custos (DRY_RUN)", layout="wide")
st.title("🦅 Simulador Realista de Arbitragem — Descontando Taxas & Custos (DRY_RUN)")

ATIVOS_BASE = [
    ("SOL/USDT", "Bybit -> Binance", 98.50, 0.24),
    ("BTC/USDT", "Binance -> Bybit", 64200.00, 0.16),
    ("ETH/USDT", "Binance Spot/Fut", 2540.00, 0.12),
    ("BNB/USDT", "BNB -> ETH -> USDT", 585.00, 0.08),
    ("XRP/USDT", "Bybit Spot/Fut", 0.5400, 0.05),
]

if "ciclo" not in st.session_state:
    st.session_state.ciclo = 0
if "acumulado_usdt" not in st.session_state:
    st.session_state.acumulado_usdt = 0.0
if "custos_totais_usdt" not in st.session_state:
    st.session_state.custos_totais_usdt = 0.0
if "linhas" not in st.session_state:
    st.session_state.linhas = []
if "historico_grafico" not in st.session_state:
    st.session_state.historico_grafico = []


def calcular_operacao_realista(
    lote_usdt: float,
    spread_bruto_pct: float,
    taxa_ponta_pct: float,
    slippage_pct: float,
    custo_transf_usdt: float,
    cotacao_brl: float,
):
    # Duas pontas (entrada e saída) de taxa + slippage estimado
    taxas_pct_total = taxa_ponta_pct * 2.0
    custo_variavel_pct = taxas_pct_total + slippage_pct

    lucro_bruto_usdt = lote_usdt * (spread_bruto_pct / 100.0)
    custo_variavel_usdt = lote_usdt * (custo_variavel_pct / 100.0)
    custo_total_usdt = custo_variavel_usdt + custo_transf_usdt
    lucro_liq_usdt = lucro_bruto_usdt - custo_total_usdt
    spread_liq_real_pct = (lucro_liq_usdt / lote_usdt * 100.0) if lote_usdt > 0 else 0.0

    return {
        "bruto_usdt": round(lucro_bruto_usdt, 4),
        "custos_usdt": round(custo_total_usdt, 4),
        "liq_usdt": round(lucro_liq_usdt, 4),
        "liq_brl": round(lucro_liq_usdt * cotacao_brl, 2),
        "spread_liq_real_pct": round(spread_liq_real_pct, 4),
    }


def gerar_ciclo(
    lote_usdt: float,
    gatilho_liq_pct: float,
    taxa_ponta_pct: float,
    slippage_pct: float,
    custo_transf_usdt: float,
    cotacao_brl: float,
):
    st.session_state.ciclo += 1
    agora = datetime.now().strftime("%H:%M:%S")
    ciclo_num = st.session_state.ciclo
    novas = []

    for ativo, rota, preco_base, sp_bruto_base in ATIVOS_BASE:
        preco = round(preco_base * (1.0 + random.uniform(-0.004, 0.004)), 4)
        sp_bruto = round(max(0.0, sp_bruto_base + random.uniform(-0.06, 0.14)), 4)

        calc = calcular_operacao_realista(
            lote_usdt=lote_usdt,
            spread_bruto_pct=sp_bruto,
            taxa_ponta_pct=taxa_ponta_pct,
            slippage_pct=slippage_pct,
            custo_transf_usdt=custo_transf_usdt,
            cotacao_brl=cotacao_brl,
        )

        lucro_liq = calc["liq_usdt"]
        custos_op = calc["custos_usdt"]
        sp_liq_real = calc["spread_liq_real_pct"]
        atuou = (sp_liq_real >= gatilho_liq_pct) and (lucro_liq > 0)

        if atuou:
            st.session_state.acumulado_usdt = round(st.session_state.acumulado_usdt + lucro_liq, 4)
            st.session_state.custos_totais_usdt = round(st.session_state.custos_totais_usdt + custos_op, 4)

        if lucro_liq <= 0:
            bg, fg, tag = "#fee2e2", "#991b1b", "🔴 PREJUÍZO / ZERO"
        elif lucro_liq >= 0.50:
            bg, fg, tag = "#d1fae5", "#065f46", "🟢 LUCRO REAL POSITIVO"
        else:
            bg, fg, tag = "#fef3c7", "#92400e", "🟡 MARGEM APERTADA"

        novas.append({
            "Ciclo": ciclo_num,
            "Hora": agora,
            "Tag": tag,
            "Ativo": ativo,
            "Rota": rota,
            "Preco": preco,
            "Sp_Bruto_%": sp_bruto,
            "Custos_USDT": custos_op,
            "Lucro_Liq_USDT": lucro_liq,
            "Lucro_Liq_BRL": calc["liq_brl"],
            "Sp_Liq_Real_%": sp_liq_real,
            "Atuou": "✅ SIMULOU" if atuou else "❌ PULOU (CUSTO > GANHO)",
            "bg": bg,
            "fg": fg,
        })

        st.session_state.historico_grafico.append({
            "Ciclo": ciclo_num,
            "Ativo": ativo,
            "Sp_Bruto_%": sp_bruto,
            "Sp_Liq_Real_%": sp_liq_real,
            "Lucro_Liq_USDT": lucro_liq if atuou else 0.0,
            "Lucro_Acumulado_USDT": st.session_state.acumulado_usdt,
        })

    st.session_state.historico_grafico = st.session_state.historico_grafico[-300:]
    novas.sort(key=lambda x: x["Lucro_Liq_USDT"], reverse=True)
    st.session_state.linhas = novas


with st.sidebar:
    st.header("💸 Custos & Parâmetros Reais")
    lote_usdt = st.number_input("Capital / Lote por Giro (USDT)", min_value=20.0, value=180.0, step=20.0)
    cotacao_brl = st.number_input("Cotação Estimada (R$ / USDT)", min_value=1.0, value=5.50, step=0.10, format="%.2f")
    gatilho_liq_pct = st.number_input("Gatilho Lucro Líquido Mínimo (%)", min_value=0.0, value=0.02, step=0.01, format="%.2f")

    st.divider()
    st.subheader("📉 Descontos por Operação")
    taxa_ponta_pct = st.number_input("Taxa por Ponta (%)", min_value=0.0, value=0.10, step=0.01, format="%.3f")
    slippage_pct = st.number_input("Slippage Estimado Total (%)", min_value=0.0, value=0.04, step=0.01, format="%.3f")
    custo_transf_usdt = st.number_input("Custo Fixo Transferência (USDT)", min_value=0.0, value=0.00, step=0.25, format="%.2f")

    auto_ciclo = st.toggle("▶️ Auto-Ciclo Ativo", value=False)
    intervalo = st.slider("Intervalo (seg)", min_value=2, max_value=15, value=4)
    ativo_foco = st.selectbox("Ativo no Gráfico", [a[0] for a in ATIVOS_BASE], index=0)

    if st.button("🧹 Zerar Tudo", width="stretch"):
        st.session_state.ciclo = 0
        st.session_state.acumulado_usdt = 0.0
        st.session_state.custos_totais_usdt = 0.0
        st.session_state.linhas = []
        st.session_state.historico_grafico = []


def renderizar_painel(executar: bool):
    if executar or not st.session_state.linhas:
        gerar_ciclo(lote_usdt, gatilho_liq_pct, taxa_ponta_pct, slippage_pct, custo_transf_usdt, cotacao_brl)

    acum_brl = round(st.session_state.acumulado_usdt * cotacao_brl, 2)
    custos_brl = round(st.session_state.custos_totais_usdt * cotacao_brl, 2)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ciclo Atual", f"#{st.session_state.ciclo}")
    m2.metric("Lucro Líquido Simulado", f"$ {st.session_state.acumulado_usdt:.4f} USDT", f"R$ {acum_brl:.2f}")
    m3.metric("Custos Descontados", f"$ {st.session_state.custos_totais_usdt:.4f} USDT", f"R$ {custos_brl:.2f}")
    m4.metric("Lote Configurado", f"$ {lote_usdt:.0f} USDT", f"~R$ {lote_usdt * cotacao_brl:.2f}")

    df_hist = pd.DataFrame(st.session_state.historico_grafico)
    if not df_hist.empty:
        df_ativo = df_hist[df_hist["Ativo"] == ativo_foco].copy()
        if not df_ativo.empty:
            st.subheader(f"📈 Spread Bruto vs. Spread Líquido Real — {ativo_foco}")
            idx_df = df_ativo.set_index("Ciclo")
            g1, g2 = st.columns(2)
            with g1:
                st.caption("Spread Bruto (%) vs. Spread Líquido Real após Custos (%)")
                st.line_chart(idx_df[["Sp_Bruto_%", "Sp_Liq_Real_%"]], height=230, width="stretch")
            with g2:
                st.caption("Lucro Líquido Acumulado Simulado (USDT)")
                st.line_chart(idx_df[["Lucro_Acumulado_USDT"]], height=230, width="stretch")

    st.subheader("🎯 Radar com Desconto de Taxas, Slippage e Transferência")
    trs = []
    for r in st.session_state.linhas:
        trs.append(
            f"<tr style='background:{r['bg']};color:{r['fg']};border-bottom:2px solid #fff;'>"
            f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Tag'])}</td>"
            f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Ativo'])}</td>"
            f"<td style='padding:8px;'>{r['Sp_Bruto_%']:.4f}%</td>"
            f"<td style='padding:8px;'>-$ {r['Custos_USDT']:.4f}</td>"
            f"<td style='padding:8px;font-weight:700;'>{r['Sp_Liq_Real_%']:.4f}%</td>"
            f"<td style='padding:8px;font-weight:700;'>$ {r['Lucro_Liq_USDT']:.4f} (R$ {r['Lucro_Liq_BRL']:.2f})</td>"
            f"<td style='padding:8px;font-weight:700;'>{html.escape(r['Atuou'])}</td>"
            f"</tr>"
        )

    st.markdown(
        "<table style='width:100%;border-collapse:collapse;font-size:14px;'>"
        "<tr style='background:#1f2937;color:#fff;'>"
        "<th style='padding:8px;text-align:left;'>Status</th>"
        "<th style='padding:8px;text-align:left;'>Ativo</th>"
        "<th style='padding:8px;text-align:left;'>Sp. Bruto</th>"
        "<th style='padding:8px;text-align:left;'>Custos Est.</th>"
        "<th style='padding:8px;text-align:left;'>Sp. Líq. Real</th>"
        "<th style='padding:8px;text-align:left;'>Lucro Líquido</th>"
        "<th style='padding:8px;text-align:left;'>Decisão</th>"
        "</tr>" + "".join(trs) + "</table>",
        unsafe_allow_html=True,
    )


rodar_manual = st.button("🔄 Rodar 1 Ciclo Realista", type="primary", disabled=auto_ciclo)

if auto_ciclo:
    @st.fragment(run_every=intervalo)
    def loop_realista():
        renderizar_painel(executar=True)

    loop_realista()
else:
    renderizar_painel(executar=rodar_manual)
