import html
import random
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from executor import ConfigRisco, ExecutorArbitragem

st.set_page_config(page_title="Arbitragem DRY_RUN — Painel Completo", layout="wide")
st.title("🦅 Arbitragem DRY_RUN — Simulador, Risco e Auditoria")

ATIVOS = [
    ("SOL/USDT", "Bybit -> Binance", 98.50, 0.24),
    ("BTC/USDT", "Binance -> Bybit", 64200.00, 0.16),
    ("ETH/USDT", "Binance Spot/Fut", 2540.00, 0.12),
    ("BNB/USDT", "BNB -> ETH -> USDT", 585.00, 0.08),
    ("XRP/USDT", "Bybit Spot/Fut", 0.5400, 0.05),
]


def _init_state():
    defaults = {
        "ciclo": 0,
        "acum_usdt": 0.0,
        "custos_usdt": 0.0,
        "simulados_qtd": 0,
        "pulados_qtd": 0,
        "linhas": [],
        "hist": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _obter_executor(
    lote_max: float,
    perda_max: float,
    taxa_ponta: float,
    slippage: float,
    transf: float,
    gatilho: float,
) -> ExecutorArbitragem:
    if "executor" not in st.session_state:
        cfg = ConfigRisco(
            dry_run=True,
            capital_referencia_usdt=180.0,
            lote_minimo_usdt=15.0,
            lote_maximo_usdt=lote_max,
            perda_maxima_sessao_usdt=perda_max,
            gatilho_spread_liq_pct=gatilho,
            taxa_ponta_pct=taxa_ponta,
            slippage_total_pct=slippage,
            taxa_transferencia_usdt=transf,
        )
        st.session_state.executor = ExecutorArbitragem(config=cfg, pasta_logs="logs")

    ex = st.session_state.executor
    ex.cfg.lote_maximo_usdt = lote_max
    ex.cfg.perda_maxima_sessao_usdt = perda_max
    ex.cfg.taxa_ponta_pct = taxa_ponta
    ex.cfg.slippage_total_pct = slippage
    ex.cfg.taxa_transferencia_usdt = transf
    ex.cfg.gatilho_spread_liq_pct = gatilho
    return ex


def _garantir_historico_inicial(lote: float, taxa_ponta: float, slippage: float, transf: float):
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


def rodar_ciclo(
    executor: ExecutorArbitragem,
    lote: float,
    taxa_ponta: float,
    slippage: float,
    transf: float,
    cotacao: float,
    gatilho: float,
):
    st.session_state.ciclo += 1
    c_num = st.session_state.ciclo
    hora = datetime.now().strftime("%H:%M:%S")
    custo_pct = (taxa_ponta * 2.0) + slippage
    novas = []

    for ativo, rota, preco_base, sp_base in ATIVOS:
        preco = round(preco_base * (1.0 + random.uniform(-0.004, 0.004)), 4)
        sp_bruto = round(max(0.0, sp_base + random.uniform(-0.06, 0.14)), 4)
        lote_efetivo = min(lote, executor.cfg.lote_maximo_usdt)

        res = executor.avaliar_e_executar(
            ativo=ativo,
            rota=rota,
            lote_usdt=lote_efetivo,
            spread_bruto_pct=sp_bruto,
            saldo_disponivel_usdt=lote,
        )

        custo_usdt = res.custos_totais_usdt
        sp_liq = res.spread_liquido_pct
        liq_usdt = res.lucro_liquido_est_usdt
        liq_brl = round(liq_usdt * cotacao, 2)
        atuou = res.decisao in ("EXECUTADO_DRY_RUN", "EXECUTADO_LIVE")

        if atuou:
            st.session_state.simulados_qtd += 1
            st.session_state.acum_usdt = round(st.session_state.acum_usdt + liq_usdt, 4)
            st.session_state.custos_usdt = round(st.session_state.custos_usdt + custo_usdt, 4)
        else:
            st.session_state.pulados_qtd += 1

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


def renderizar_bloco_executor(executor: ExecutorArbitragem, cotacao: float):
    st.divider()
    st.subheader("🛡️ Controle de Risco & Auditoria (`ExecutorArbitragem`)")

    col_status, col_acao = st.columns([3, 1])
    with col_status:
        if executor.travado_por_risco:
            st.error(
                f"🚨 **CIRCUIT BREAKER ATIVO** — Novas ordens bloqueadas. "
                f"Motivo: `{executor.motivo_trava}`"
            )
        else:
            st.success(
                f"🟢 **CIRCUIT BREAKER LIBERADO** — Modo: `{'DRY_RUN' if executor.cfg.dry_run else 'LIVE'}` | "
                f"Limite de perda: `-{executor.cfg.perda_maxima_sessao_usdt:.2f} USDT`"
            )

    with col_acao:
        if st.button("🔓 Resetar Trava / Sessão", use_container_width=True):
            executor.resetar_sessao()
            st.session_state.ciclo = 0
            st.session_state.acum_usdt = 0.0
            st.session_state.custos_usdt = 0.0
            st.session_state.simulados_qtd = 0
            st.session_state.pulados_qtd = 0
            st.session_state.linhas = []
            st.session_state.hist = []
            st.rerun()

    e1, e2, e3 = st.columns(3)
    e1.metric(
        "PnL Acumulado (Executor)",
        f"$ {executor.pnl_acumulado_usdt:.4f} USDT",
        f"R$ {executor.pnl_acumulado_usdt * cotacao:.2f}",
    )
    e2.metric(
        "Custos Registrados",
        f"$ {executor.custos_acumulados_usdt:.4f} USDT",
        f"R$ {executor.custos_acumulados_usdt * cotacao:.2f}",
    )
    e3.metric("Ordens / Ciclos Aprovados", executor.ordens_executadas)

    st.markdown("#### 📄 Histórico de Auditoria (`logs/execucoes_auditoria.csv`)")
    caminho_csv: Path = executor.arquivo_csv

    if caminho_csv.exists():
        try:
            df_log = pd.read_csv(caminho_csv)
            if not df_log.empty:
                st.dataframe(
                    df_log.tail(30).iloc[::-1],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("O arquivo CSV existe, mas ainda não há execuções registradas.")
        except Exception as exc:
            st.warning(f"Não foi possível ler o CSV agora: {exc}")
    else:
        st.info("Nenhum log CSV gerado ainda em `logs/execucoes_auditoria.csv`.")


def renderizar_painel(
    executor: ExecutorArbitragem,
    lote: float,
    taxa_ponta: float,
    slippage: float,
    transf: float,
    cotacao: float,
    gatilho: float,
    ativo_foco: str,
    executar: bool,
):
    _garantir_historico_inicial(lote, taxa_ponta, slippage, transf)
    if executar or not st.session_state.linhas:
        rodar_ciclo(executor, lote, taxa_ponta, slippage, transf, cotacao, gatilho)

    acum_brl = st.session_state.acum_usdt * cotacao
    custos_brl = st.session_state.custos_usdt * cotacao

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ciclos Rodados", f"#{st.session_state.ciclo}")
    m2.metric("Lucro Líquido Simulado", f"$ {st.session_state.acum_usdt:.4f} USDT", f"R$ {acum_brl:.2f}")
    m3.metric("Custos Descontados", f"$ {st.session_state.custos_usdt:.4f} USDT", f"R$ {custos_brl:.2f}")
    m4.metric("Lote Configurado", f"$ {lote:.0f} USDT", f"~R$ {lote * cotacao:.2f}")

    total_ops = st.session_state.simulados_qtd + st.session_state.pulados_qtd
    pct_puladas = (st.session_state.pulados_qtd / total_ops * 100.0) if total_ops > 0 else 0.0

    c1, c2, c3 = st.columns(3)
    c1.metric("✅ SIMULOU", st.session_state.simulados_qtd)
    c2.metric("❌ PULOU (Custo/Gatilho)", st.session_state.pulados_qtd, f"{pct_puladas:.1f}% do total")
    c3.metric("📊 Total Avaliado", total_ops)

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

    st.subheader("🎯 Radar & Execuções do Ciclo (Colunas Principais)")
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

    renderizar_bloco_executor(executor, cotacao)


_init_state()

with st.sidebar:
    st.header("⚙️ Custos, Risco & Controles")
    lote = st.number_input("Lote por Giro (USDT)", min_value=20.0, value=180.0, step=20.0)
    lote_max = st.number_input("Teto Lote / Giro (USDT)", min_value=15.0, value=90.0, step=5.0)
    perda_max = st.number_input("Stop-Loss Sessão (USDT)", min_value=0.50, value=5.40, step=0.50)
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
        st.session_state.simulados_qtd = 0
        st.session_state.pulados_qtd = 0
        st.session_state.linhas = []
        st.session_state.hist = []

executor = _obter_executor(lote_max, perda_max, taxa_ponta, slippage, transf, gatilho)

b1, b2 = st.columns([2, 2])
with b1:
    rodar_1 = st.button("🔄 Rodar 1 Ciclo", type="primary", disabled=auto_rodar)
with b2:
    rodar_10 = st.button("⚡ Simular 10 Ciclos", disabled=auto_rodar)

if rodar_10 and not auto_rodar:
    for _ in range(10):
        rodar_ciclo(executor, lote, taxa_ponta, slippage, transf, cotacao, gatilho)

if auto_rodar:
    st.caption(f"🟢 Auto-ciclo ativo a cada **{segundos}s**.")

    @st.fragment(run_every=segundos)
    def painel_vivo():
        renderizar_painel(
            executor, lote, taxa_ponta, slippage, transf, cotacao, gatilho, ativo_foco, executar=True
        )

    painel_vivo()
else:
    renderizar_painel(
        executor, lote, taxa_ponta, slippage, transf, cotacao, gatilho, ativo_foco, executar=rodar_1
    )
