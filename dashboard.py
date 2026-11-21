from datetime import datetime
import asyncio
import html
import random
import pandas as pd
import streamlit as st
import config

st.set_page_config(page_title="Terminal de Arbitragem", layout="wide")

st.title("🦅 Terminal de Arbitragem Multi-Estratégia (Binance & Bybit)")

ExecutorArbitragem = None
try:
    from executor import ExecutorArbitragem
except Exception:
    ExecutorArbitragem = None

MotorClasse = None
modo_motor = None
try:
    from motor_dados import MotorDados
    MotorClasse = MotorDados
    modo_motor = "motor_dados"
except Exception:
    try:
        from motor_arbitragem import MotorArbitragem
        MotorClasse = MotorArbitragem
        modo_motor = "motor_arbitragem"
    except Exception:
        MotorClasse = None

if "num_ciclo" not in st.session_state:
    st.session_state.num_ciclo = 0
if "historico_trades" not in st.session_state:
    st.session_state.historico_trades = []
if "historico_decisoes" not in st.session_state:
    st.session_state.historico_decisoes = []
if "lucro_acumulado" not in st.session_state:
    st.session_state.lucro_acumulado = 0.0
if "ultimo_df" not in st.session_state:
    st.session_state.ultimo_df = pd.DataFrame()
if "fonte_dados" not in st.session_state:
    st.session_state.fonte_dados = "Simulação de Apoio"
if "executor" not in st.session_state and ExecutorArbitragem is not None:
    st.session_state.executor = ExecutorArbitragem(
        modo="DRY_RUN",
        lote_max_usdt=float(getattr(config, "LOTE_OPERACAO_USDT", 1000.0)),
        gatilho_pct=float(getattr(config, "SPREAD_MINIMO_LIQUIDO", 0.05)),
    )


def _gerar_sinais_apoio(lote_usdt: float) -> list[dict]:
    agora = datetime.now().strftime("%H:%M:%S")
    base = [
        ("SOL/USDT", "Espacial", "Bybit Spot -> Binance Spot", 0.22),
        ("BTC/USDT", "Espacial", "Binance Spot -> Bybit Spot", 0.14),
        ("ETH/USDT", "Cash & Carry", "Binance Spot / Futuros", 0.09),
        ("BNB/USDT", "Triangular", "BNB -> ETH -> USDT", 0.04),
        ("XRP/USDT", "Cash & Carry", "Bybit Spot / Futuros", -0.02),
    ]
    linhas = []
    for ativo, est, rota, sp_base in base:
        sp_liq = round(sp_base + random.uniform(-0.08, 0.12), 4)
        lucro_est = round(lote_usdt * (sp_liq / 100.0), 4)
        linhas.append({
            "Hora": agora,
            "Estrategia": est,
            "Ativo": ativo,
            "Rota": rota,
            "Spread_Liquido_%": sp_liq,
            "Lucro_Est_USDT": lucro_est,
            "Liquidez_Ponta_USDT": round(lote_usdt * random.uniform(0.7, 5.0), 2),
        })
    return linhas


def _avaliar_linhas(df: pd.DataFrame, lote_usdt: float) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    sp = pd.to_numeric(out["Spread_Liquido_%"], errors="coerce").fillna(0.0)
    lucro = (lote_usdt * (sp / 100.0)).round(4)
    out["Lucro_Est_USDT"] = lucro

    scores = []
    status_cor = []
    for s_val, l_val in zip(sp, lucro):
        sc = max(0.0, min(100.0, (s_val / 0.25) * 70.0 + (l_val / max(0.1, lote_usdt * 0.0025)) * 30.0))
        scores.append(round(sc, 1))
        if s_val <= 0 or sc < 45:
            status_cor.append("VERMELHO")
        elif sc >= 70:
            status_cor.append("VERDE")
        else:
            status_cor.append("AMARELO")

    out["Score"] = scores
    out["Status_Cor"] = status_cor
    return out.sort_values(by=["Score", "Lucro_Est_USDT"], ascending=[False, False]).reset_index(drop=True)


def _render_tabela_colorida(df: pd.DataFrame):
    if df.empty:
        st.info("Sem linhas para exibir.")
        return

    paleta = {
        "VERDE": ("#d1fae5", "#065f46", "#059669", "🟢 TOP LUCRO"),
        "AMARELO": ("#fef3c7", "#92400e", "#d97706", "🟡 MODERADA"),
        "VERMELHO": ("#fee2e2", "#991b1b", "#dc2626", "🔴 FRACA / PREJUÍZO"),
    }

    linhas_html = []
    for _, r in df.iterrows():
        cor_chave = str(r.get("Status_Cor", "AMARELO"))
        bg, fg, borda, badge = paleta.get(cor_chave, paleta["AMARELO"])
        ativo = html.escape(str(r.get("Ativo", "")))
        rota = html.escape(str(r.get("Rota", "")))
        est = html.escape(str(r.get("Estrategia", "")))
        sp = float(r.get("Spread_Liquido_%", 0.0))
        lucro = float(r.get("Lucro_Est_USDT", 0.0))
        score = float(r.get("Score", 0.0))

        linhas_html.append(
            f"<tr style='background-color:{bg}; color:{fg}; border-bottom:2px solid #ffffff;'>"
            f"<td style='padding:10px; border-left:6px solid {borda}; font-weight:700;'>{badge}</td>"
            f"<td style='padding:10px; font-weight:700;'>{ativo}</td>"
            f"<td style='padding:10px;'>{est}</td>"
            f"<td style='padding:10px;'>{rota}</td>"
            f"<td style='padding:10px; font-weight:700;'>{sp:.4f}%</td>"
            f"<td style='padding:10px; font-weight:700;'>$ {lucro:.4f} USDT</td>"
            f"<td style='padding:10px; font-weight:700;'>{score:.1f}</td>"
            f"</tr>"
        )

    tabela_html = (
        "<div style='width:100%; overflow-x:auto; border-radius:8px; border:1px solid #d1d5db;'>"
        "<table style='width:100%; border-collapse:collapse; font-size:15px; text-align:left;'>"
        "<thead>"
        "<tr style='background-color:#1f2937; color:#ffffff;'>"
        "<th style='padding:10px;'>Nível</th>"
        "<th style='padding:10px;'>Ativo</th>"
        "<th style='padding:10px;'>Estratégia</th>"
        "<th style='padding:10px;'>Rota</th>"
        "<th style='padding:10px;'>Spread Líq.</th>"
        "<th style='padding:10px;'>Lucro Est.</th>"
        "<th style='padding:10px;'>Score</th>"
        "</tr>"
        "</thead>"
        f"<tbody>{''.join(linhas_html)}</tbody>"
        "</table>"
        "</div>"
    )
    st.markdown(tabela_html, unsafe_allow_html=True)


async def _buscar_motor():
    if MotorClasse is None:
        return []
    motor = MotorClasse()
    try:
        if modo_motor == "motor_dados":
            return await motor.varrer_mercado()
        return await motor.escanear_tudo()
    finally:
        if hasattr(motor, "fechar"):
            await motor.fechar()
        elif hasattr(motor, "fechar_conexoes"):
            await motor.fechar_conexoes()


def _rodar_ciclo(lote_usdt: float, gatilho_pct: float, fonte_escolha: str):
    st.session_state.num_ciclo += 1
    dados = []
    fonte_usada = "Simulação de Apoio"

    if fonte_escolha in ("Auto (Real -> Simulação)", "Apenas Motor Real") and MotorClasse is not None:
        try:
            coletados = asyncio.run(_buscar_motor())
            if coletados:
                dados = coletados
                fonte_usada = "Motor Real"
        except Exception:
            dados = []

    if not dados and fonte_escolha != "Apenas Motor Real":
        dados = _gerar_sinais_apoio(lote_usdt)
        fonte_usada = "Simulação de Apoio"

    st.session_state.fonte_dados = fonte_usada
    df = pd.DataFrame(dados)
    if not df.empty:
        df = _avaliar_linhas(df, lote_usdt)
    st.session_state.ultimo_df = df

    if "executor" in st.session_state and st.session_state.executor is not None and not df.empty:
        st.session_state.executor.lote_max_usdt = lote_usdt
        st.session_state.executor.gatilho_pct = gatilho_pct
        for _, row in df.iterrows():
            res = st.session_state.executor.executar_ordem(row.to_dict())
            st.session_state.historico_decisoes.insert(0, res)
            if res.get("status") == "SIMULADO_OK":
                val = float(res.get("Lucro_Liquido_USDT", row.get("Lucro_Est_USDT", 0.0)) or 0.0)
                st.session_state.lucro_acumulado += val
                st.session_state.historico_trades.insert(0, res)


with st.sidebar:
    st.header("⚙️ Controles")
    fonte_escolha = st.selectbox(
        "Fonte de Dados",
        ["Auto (Real -> Simulação)", "Apenas Simulação de Apoio", "Apenas Motor Real"],
        index=0,
    )
    lote = st.number_input("Lote por Operação (USDT)", min_value=10.0, value=1000.0, step=100.0)
    gatilho = st.number_input("Gatilho Lucro Líquido (%)", min_value=0.0, value=0.05, step=0.01, format="%.2f")
    if st.button("🧹 Zerar Sessão", use_container_width=True):
        st.session_state.num_ciclo = 0
        st.session_state.historico_trades = []
        st.session_state.historico_decisoes = []
        st.session_state.lucro_acumulado = 0.0
        st.session_state.ultimo_df = pd.DataFrame()
        st.rerun()

col1, col2, col3 = st.columns([2, 2, 3])
with col1:
    clicou = st.button("🔄 Rodar Ciclo Agora", use_container_width=True, type="primary")
with col2:
    st.metric("Ciclo Atual", f"#{st.session_state.num_ciclo}")
with col3:
    st.metric("Lucro Simulado Acumulado", f"$ {st.session_state.lucro_acumulado:.4f} USDT")

if clicou or st.session_state.ultimo_df.empty:
    _rodar_ciclo(lote, gatilho, fonte_escolha)
    st.rerun()

st.caption(f"Fonte ativa: **{st.session_state.fonte_dados}** | Modo: **DRY_RUN**")
_render_tabela_colorida(st.session_state.ultimo_df)

st.divider()
c_dl1, c_dl2 = st.columns(2)
with c_dl1:
    csv_trades = pd.DataFrame(st.session_state.historico_trades).to_csv(index=False).encode("utf-8-sig") if st.session_state.historico_trades else b"sem_ordens\n"
    st.download_button("⬇️ Baixar Ordens Simuladas (CSV)", data=csv_trades, file_name="ordens_simuladas.csv", mime="text/csv", use_container_width=True)
with c_dl2:
    csv_dec = pd.DataFrame(st.session_state.historico_decisoes).to_csv(index=False).encode("utf-8-sig") if st.session_state.historico_decisoes else b"sem_decisoes\n"
    st.download_button("⬇️ Baixar Decisões (CSV)", data=csv_dec, file_name="decisoes_executor.csv", mime="text/csv", use_container_width=True)
