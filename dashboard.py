from datetime import datetime
import asyncio
import random
import pandas as pd
import streamlit as st
import config

st.set_page_config(page_title="Terminal de Arbitragem Multi-Estratégia", layout="wide")

st.title("🦅 Terminal de Arbitragem Multi-Estratégia (Binance & Bybit)")

ExecutorArbitragem = None
erro_executor = None
try:
    from executor import ExecutorArbitragem
except Exception as e:
    erro_executor = str(e)

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

if erro_executor:
    st.warning(f"Aviso no executor.py: {erro_executor}")

if "historico_trades" not in st.session_state:
    st.session_state.historico_trades = []
if "historico_decisoes" not in st.session_state:
    st.session_state.historico_decisoes = []
if "lucro_acumulado" not in st.session_state:
    st.session_state.lucro_acumulado = 0.0
if "travamento_meta_acionado" not in st.session_state:
    st.session_state.travamento_meta_acionado = False
if "travamento_prejuizo_acionado" not in st.session_state:
    st.session_state.travamento_prejuizo_acionado = False
if "ultimo_df" not in st.session_state:
    st.session_state.ultimo_df = pd.DataFrame()
if "fonte_dados" not in st.session_state:
    st.session_state.fonte_dados = "Aguardando ciclo"
if "executor" not in st.session_state and ExecutorArbitragem is not None:
    st.session_state.executor = ExecutorArbitragem(
        modo=getattr(config, "MODO_EXECUCAO", "DRY_RUN"),
        lote_max_usdt=getattr(config, "LOTE_OPERACAO_USDT", 1000.0),
        gatilho_pct=getattr(config, "SPREAD_MINIMO_LIQUIDO", 0.05),
    )


def _gerar_sinais_apoio(lote_usdt: float) -> list[dict]:
    agora = datetime.now().strftime("%H:%M:%S")
    base = [
        ("BTC/USDT", "Espacial (Cross-Exchange)", "Binance Spot -> Bybit Spot", 0.14),
        ("ETH/USDT", "Cash & Carry (Spot x Fut)", "Binance Spot / Futuros", 0.11),
        ("SOL/USDT", "Espacial (Cross-Exchange)", "Bybit Spot -> Binance Spot", 0.18),
        ("BNB/USDT", "Triangular (Intra-Exchange)", "BNB -> ETH -> USDT (Binance)", 0.08),
        ("XRP/USDT", "Cash & Carry (Spot x Fut)", "Bybit Spot / Futuros", 0.09),
    ]
    sinais = []
    for ativo, est, rota, sp_base in base:
        sp_liq = round(max(-0.05, sp_base + random.uniform(-0.04, 0.12)), 4)
        sp_bruto = round(sp_liq + 0.18, 4)
        lucro_est = round(lote_usdt * (sp_liq / 100.0), 4)
        sinais.append({
            "Hora": agora,
            "Estrategia": est,
            "Ativo": ativo,
            "Rota": rota,
            "Funding_8h_%": round(random.uniform(-0.02, 0.05), 4),
            "Spread_Bruto_%": sp_bruto,
            "Spread_Liquido_%": sp_liq,
            "Lucro_Est_USDT": lucro_est,
            "Liquidez_Ponta_USDT": round(lote_usdt * random.uniform(1.2, 6.0), 2),
        })
    return sinais


def _csv_bytes_memoria(registros: list[dict]) -> bytes:
    if not registros:
        return "sem_registros\n".encode("utf-8-sig")
    return pd.DataFrame(registros).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def _resumo_agrupado(trades: list[dict], coluna_grupo: str) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df_t = pd.DataFrame(trades)
    if coluna_grupo not in df_t.columns:
        return pd.DataFrame()

    df_t["Lucro_Liquido_USDT"] = pd.to_numeric(df_t.get("Lucro_Liquido_USDT", 0.0), errors="coerce").fillna(0.0)
    df_t["Spread_Liquido_%"] = pd.to_numeric(df_t.get("Spread_Liquido_%", 0.0), errors="coerce").fillna(0.0)

    resumo = (
        df_t.groupby(coluna_grupo, as_index=False)
        .agg(
            Ordens=("Lucro_Liquido_USDT", "count"),
            Spread_Medio_Pct=("Spread_Liquido_%", "mean"),
            Lucro_Liquido_USDT=("Lucro_Liquido_USDT", "sum"),
        )
        .sort_values(by="Lucro_Liquido_USDT", ascending=False)
        .reset_index(drop=True)
    )
    resumo["Spread_Medio_Pct"] = resumo["Spread_Medio_Pct"].round(4)
    resumo["Lucro_Liquido_USDT"] = resumo["Lucro_Liquido_USDT"].round(4)
    return resumo


async def _coletar_dados():
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


def _executar_ciclo(lote_usdt: float, filtro_est: list[str], meta_alvo: float, auto_travar: bool, max_perda: float):
    dados_atuais = []
    fonte = "Simulação Cloud (Memória)"

    if MotorClasse is not None:
        try:
            coletados = asyncio.run(_coletar_dados())
            if coletados:
                dados_atuais = coletados
                fonte = f"Motor ({modo_motor})"
        except Exception:
            dados_atuais = []

    if not dados_atuais:
        dados_atuais = _gerar_sinais_apoio(lote_usdt)
        fonte = "Simulação Cloud (Memória)"

    st.session_state.fonte_dados = fonte
    df = pd.DataFrame(dados_atuais)

    if "Funding_8h_%" not in df.columns:
        df["Funding_8h_%"] = 0.0
    else:
        df["Funding_8h_%"] = df["Funding_8h_%"].fillna(0.0)

    if "Estrategia" in df.columns and filtro_est:
        df = df[df["Estrategia"].isin(filtro_est)]
    if "Spread_Liquido_%" in df.columns:
        df = df.sort_values(by="Spread_Liquido_%", ascending=False).reset_index(drop=True)

    st.session_state.ultimo_df = df

    if "executor" in st.session_state and not df.empty:
        for _, row in df.iterrows():
            sinal = row.to_dict()
            resultado = st.session_state.executor.executar_ordem(sinal)
            st.session_state.historico_decisoes.insert(0, resultado)
            st.session_state.historico_decisoes = st.session_state.historico_decisoes[:300]

            if resultado.get("status") == "SIMULADO_OK":
                lucro_row = float(resultado.get("Lucro_Liquido_USDT", sinal.get("Lucro_Est_USDT", 0.0)) or 0.0)
                st.session_state.lucro_acumulado += lucro_row
                st.session_state.historico_trades.insert(0, resultado)
                st.session_state.historico_trades = st.session_state.historico_trades[:150]

                if max_perda > 0 and st.session_state.lucro_acumulado <= -abs(max_perda):
                    st.session_state.executor.travado = True
                    st.session_state.travamento_prejuizo_acionado = True
                    break

                if auto_travar and meta_alvo > 0 and st.session_state.lucro_acumulado >= meta_alvo:
                    st.session_state.executor.travado = True
                    st.session_state.travamento_meta_acionado = True


with st.sidebar:
    st.header("⚙️ Parâmetros do Robô")
    auto_atualizar = st.toggle("Atualização Automática", value=False)
    intervalo_seg = st.slider("Intervalo automático (seg)", 5, 30, 10)
    mostrar_todas_colunas = st.toggle("Mostrar todas as colunas", value=False)
    lote = st.number_input("Lote por Operação (USDT)", value=float(getattr(config, "LOTE_OPERACAO_USDT", 1000.0)), step=100.0)
    gatilho = st.number_input("Gatilho Lucro Líquido Mínimo (%)", value=0.01, step=0.01, format="%.2f")
    meta_lucro = st.number_input("Meta de Lucro Simulado (USDT)", min_value=0.0, value=10.0, step=1.0, format="%.2f")
    travar_ao_atingir_meta = st.toggle("Travar executor ao atingir meta", value=False)
    limite_prejuizo = st.number_input("Limite Máximo de Prejuízo (USDT)", min_value=0.0, value=5.0, step=1.0, format="%.2f")
    filtro_estrategia = st.multiselect(
        "Estratégias Ativas",
        ["Espacial (Cross-Exchange)", "Cash & Carry (Spot x Fut)", "Triangular (Intra-Exchange)"],
        default=["Espacial (Cross-Exchange)", "Cash & Carry (Spot x Fut)", "Triangular (Intra-Exchange)"],
    )

    if "executor" in st.session_state:
        st.divider()
        st.subheader("🛑 Trava de Segurança (Executor)")
        if st.session_state.executor.travado:
            st.error("EXECUTOR TRAVADO")
            if st.button("Destravar Executor", width="stretch"):
                st.session_state.executor.travado = False
                st.session_state.travamento_prejuizo_acionado = False
                st.rerun()
        else:
            st.success("EXECUTOR LIBERADO")
            if st.button("Acionar Trava de Emergência", width="stretch"):
                st.session_state.executor.travado = True
                st.rerun()

    st.divider()
    if st.button("🧹 Limpar Histórico da Sessão", width="stretch"):
        st.session_state.historico_trades = []
        st.session_state.historico_decisoes = []
        st.session_state.lucro_acumulado = 0.0
        st.session_state.travamento_meta_acionado = False
        st.session_state.travamento_prejuizo_acionado = False
        st.rerun()

if "executor" in st.session_state:
    st.session_state.executor.lote_max_usdt = lote
    st.session_state.executor.gatilho_pct = gatilho

col_acao1, col_acao2 = st.columns([1, 3])
with col_acao1:
    rodar_agora = st.button("🔄 Rodar Ciclo Agora", width="stretch")
with col_acao2:
    st.caption(f"Fonte atual: **{st.session_state.fonte_dados}** | Modo: **DRY_RUN** (Memória)")

if rodar_agora or st.session_state.ultimo_df.empty:
    _executar_ciclo(lote, filtro_estrategia, meta_lucro, travar_ao_atingir_meta, limite_prejuizo)

if auto_atualizar:
    @st.fragment(run_every=intervalo_seg)
    def _loop_silencioso():
        _executar_ciclo(lote, filtro_estrategia, meta_lucro, travar_ao_atingir_meta, limite_prejuizo)
        st.rerun()

    _loop_silencioso()

lucro_atual = st.session_state.lucro_acumulado
if limite_prejuizo > 0 and lucro_atual <= -abs(limite_prejuizo):
    st.error(f"🚨 LIMITE DE PREJUÍZO ATINGIDO! Acumulado: $ {lucro_atual:.2f} USDT (Limite: -$ {abs(limite_prejuizo):.2f} USDT)")
elif limite_prejuizo > 0 and lucro_atual < 0:
    st.caption(f"⚠️ Risco de Prejuízo: -$ {abs(lucro_atual):.2f} / -$ {abs(limite_prejuizo):.2f} USDT")

if meta_lucro > 0:
    pct_meta = max(0.0, (lucro_atual / meta_lucro) * 100.0)
    st.caption(f"🎯 Meta: $ {lucro_atual:.2f} / $ {meta_lucro:.2f} USDT ({pct_meta:.1f}%)")
    st.progress(min(1.0, max(0.0, lucro_atual / meta_lucro)))
    if lucro_atual >= meta_lucro:
        st.success(f"🎯 META ATINGIDA! Lucro simulado acumulado: $ {lucro_atual:.2f} USDT")

df = st.session_state.ultimo_df
c1, c2 = st.columns(2)
c3, c4 = st.columns(2)
melhor_spread = df["Spread_Liquido_%"].max() if not df.empty and "Spread_Liquido_%" in df.columns else 0.0
ultimas_ciclo = [d for d in st.session_state.historico_decisoes if d.get("status") == "SIMULADO_OK"]
c1.metric("Melhor Spread Líquido Agora", f"{melhor_spread:.4f}%")
c2.metric("Aprovadas no Histórico", len(ultimas_ciclo))
c3.metric("Ordens Simuladas (Sessão)", len(st.session_state.historico_trades))
c4.metric("Lucro Líquido Simulado", f"$ {st.session_state.lucro_acumulado:.2f} USDT")

colunas_compactas = [c for c in ["Ativo", "Rota", "Spread_Liquido_%", "Lucro_Est_USDT"] if c in df.columns]
colunas_completas = [
    c for c in [
        "Hora", "Estrategia", "Ativo", "Rota", "Funding_8h_%",
        "Spread_Bruto_%", "Spread_Liquido_%", "Lucro_Est_USDT", "Liquidez_Ponta_USDT"
    ] if c in df.columns
]
cols_ativas = colunas_completas if mostrar_todas_colunas else colunas_compactas

st.subheader("📡 Radar de Oportunidades")
if not df.empty:
    st.dataframe(df[cols_ativas] if cols_ativas else df, width="stretch", height=300)
else:
    st.info("Sem linhas no radar.")

st.subheader("🏆 Onde o Simulador Ganha Mais (Estratégia & Ativo)")
res_est = _resumo_agrupado(st.session_state.historico_trades, "Estrategia")
res_atv = _resumo_agrupado(st.session_state.historico_trades, "Ativo")

if not res_est.empty or not res_atv.empty:
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.caption("Por Estratégia")
        if not res_est.empty:
            st.dataframe(res_est, width="stretch", height=180)
    with col_r2:
        st.caption("Por Ativo")
        if not res_atv.empty:
            st.dataframe(res_atv, width="stretch", height=180)

    if not res_atv.empty:
        st.caption("📊 Lucro Líquido Simulado Acumulado por Ativo (USDT)")
        st.bar_chart(res_atv.set_index("Ativo")[["Lucro_Liquido_USDT"]], width="stretch", height=220)

st.subheader("📋 Auditoria do Executor & CSVs")
col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    st.download_button(
        label="⬇️ Baixar Ordens Simuladas (CSV)",
        data=_csv_bytes_memoria(st.session_state.historico_trades),
        file_name="ordens_simuladas.csv",
        mime="text/csv",
        width="stretch",
        key="dl_ordens_cloud",
    )
with col_dl2:
    st.download_button(
        label="⬇️ Baixar Decisões do Executor (CSV)",
        data=_csv_bytes_memoria(st.session_state.historico_decisoes),
        file_name="decisoes_executor.csv",
        mime="text/csv",
        width="stretch",
        key="dl_decisoes_cloud",
    )

aba_ordens, aba_decisoes = st.tabs(["✅ Ordens Simuladas", "🔎 Decisões & Motivos"])
with aba_ordens:
    if st.session_state.historico_trades:
        df_ordens = pd.DataFrame(st.session_state.historico_trades)
        cols_ordens = [c for c in ["Hora", "Ativo", "Rota", "Lote_USDT", "Spread_Liquido_%", "Lucro_Liquido_USDT", "status"] if c in df_ordens.columns]
        st.dataframe(df_ordens[cols_ordens] if cols_ordens else df_ordens, width="stretch", height=220)
    else:
        st.caption("Nenhuma ordem simulada ainda.")

with aba_decisoes:
    if st.session_state.historico_decisoes:
        df_dec = pd.DataFrame(st.session_state.historico_decisoes)
        cols_dec = [c for c in ["Hora", "Ativo", "Rota", "Spread_Liquido_%", "status", "motivo"] if c in df_dec.columns]
        st.dataframe(df_dec[cols_dec] if cols_dec else df_dec, width="stretch", height=240)
    else:
        st.caption("Nenhuma decisão registrada ainda.")
