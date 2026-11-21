from datetime import datetime
import html
import random
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Terminal de Arbitragem no Gráfico", layout="wide")
st.title("🦅 Terminal de Arbitragem — Atuação no Gráfico (DRY_RUN)")

ATIVOS_BASE = [
    ("SOL/USDT", "Bybit -> Binance", 98.50, 0.22),
    ("BTC/USDT", "Binance -> Bybit", 64200.00, 0.14),
    ("ETH/USDT", "Binance Spot/Fut", 2540.00, 0.09),
    ("BNB/USDT", "BNB -> ETH -> USDT", 585.00, 0.04),
    ("XRP/USDT", "Bybit Spot/Fut", 0.5400, -0.02),
]

if "ciclo" not in st.session_state:
    st.session_state.ciclo = 0
if "acumulado" not in st.session_state:
    st.session_state.acumulado = 0.0
if "linhas" not in st.session_state:
    st.session_state.linhas = []
if "historico_grafico" not in st.session_state:
    st.session_state.historico_grafico = []

# Pré-popula pontos iniciais para o gráfico já aparecer desenhado na abertura
if not st.session_state.historico_grafico:
    for idx in range(1, 7):
        acum_tmp = 0.0
        for ativo, rota, preco_base, sp_base in ATIVOS_BASE:
            preco_ini = round(preco_base * (1.0 + (idx - 3.5) * 0.0018), 4)
            sp_ini = round(sp_base + (idx - 3.5) * 0.025, 4)
            lucro_ini = round(1000.0 * (sp_ini / 100.0), 4)
            atuou_ini = sp_ini >= 0.05 and lucro_ini > 0
            if atuou_ini:
                acum_tmp = round(acum_tmp + lucro_ini, 4)
            st.session_state.historico_grafico.append({
                "Ciclo": idx,
                "Ativo": ativo,
                "Preco": preco_ini,
                "Spread_%": sp_ini,
                "Gatilho_%": 0.05,
                "Preco_Atuacao": preco_ini if atuou_ini else None,
                "Spread_Atuacao": sp_ini if atuou_ini else None,
                "Lucro_Execucao": lucro_ini if atuou_ini else 0.0,
                "Lucro_Acumulado": acum_tmp,
            })


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
            "Gatilho_%": gatilho,
            "Preco_Atuacao": preco if atuou else None,
            "Spread_Atuacao": sp if atuou else None,
            "Lucro_Execucao": lucro if atuou else 0.0,
            "Lucro_Acumulado": st.session_state.acumulado,
        })

    st.session_state.historico_grafico = st.session_state.historico_grafico[-300:]
    novas.sort(key=lambda x: x["Score"], reverse=True)
    st.session_state.linhas = novas


def renderizar_graficos(df_ativo: pd.DataFrame, ativo_foco: str, gatilho: float):
    st.subheader(f"📈 Gráfico de Atuação do Robô — {ativo_foco}")
    st.caption(
        "🟢 **Preco_Atuacao / Spread_Atuacao** mostram os ciclos em que o robô executou (`SIMULOU`); "
        "**Gatilho_%** marca a linha mínima exigida."
    )

    base_idx = df_ativo.set_index("Ciclo")
    g1, g2 = st.columns(2)
    with g1:
        st.caption("Preço & Pontos de Atuação do Robô")
        st.line_chart(base_idx[["Preco", "Preco_Atuacao"]], height=250, width="stretch")
    with g2:
        st.caption(f"Spread Líquido (%) vs. Gatilho ({gatilho:.2f}%) & Execuções")
        df_sp = base_idx[["Spread_%", "Spread_Atuacao"]].copy()
        df_sp["Gatilho_%"] = gatilho
        st.line_chart(df_sp[["Spread_%", "Gatilho_%", "Spread_Atuacao"]], height=250, width="stretch")

    st.caption("💰 Evolução do Lucro Simulado Acumulado (USDT) e Lucro por Execução")
    st.line_chart(base_idx[["Lucro_Acumulado", "Lucro_Execucao"]], height=220, width="stretch")


def renderizar_conteudo(lote: float, gatilho: float, ativo_foco: str, executar: bool):
    if executar or not st.session_state.linhas:
        gerar_ciclo(lote, gatilho)

    c1, c2, c3 = st.columns([2, 2, 3])
    c1.metric("Ciclo Atual", f"#{st.session_state.ciclo}")
    c2.metric("Lucro Simulado Acumulado", f"$ {st.session_state.acumulado:.4f} USDT")
    c3.metric("Ativo em Foco", ativo_foco)

    df_hist = pd.DataFrame(st.session_state.historico_grafico)
    if not df_hist.empty:
        df_ativo = df_hist[df_hist["Ativo"] == ativo_foco].copy()
        if not df_ativo.empty:
            renderizar_graficos(df_ativo, ativo_foco, gatilho)

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


with st.sidebar:
    st.header("⚙️ Controles")
    auto_ciclo = st.toggle("▶️ Auto-Ciclo Ativo", value=False)
    intervalo = st.slider("Intervalo (segundos)", min_value=2, max_value=15, value=4)
    lote = st.number_input("Lote (USDT)", min_value=50.0, value=1000.0, step=100.0)
    gatilho = st.number_input("Gatilho Mínimo (%)", min_value=0.0, value=0.05, step=0.01, format="%.2f")
    ativo_foco = st.selectbox("Ativo no Gráfico", [a[0] for a in ATIVOS_BASE], index=0)

    if st.button("🧹 Zerar Tudo", width="stretch"):
        st.session_state.ciclo = 0
        st.session_state.acumulado = 0.0
        st.session_state.linhas = []
        st.session_state.historico_grafico = []

rodar_manual = st.button("🔄 Rodar 1 Ciclo Manual", type="primary", disabled=auto_ciclo)

if auto_ciclo:
    st.caption(f"🟢 Auto-ciclo rodando a cada **{intervalo}s** (desligue na barra lateral para pausar).")

    @st.fragment(run_every=intervalo)
    def painel_automatico():
        renderizar_conteudo(lote, gatilho, ativo_foco, executar=True)

    painel_automatico()
else:
    renderizar_conteudo(lote, gatilho, ativo_foco, executar=rodar_manual)
