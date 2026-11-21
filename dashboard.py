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
erro_motor = None

try:
    from motor_dados import MotorDados
    MotorClasse = MotorDados
    modo_motor = "motor_dados"
except Exception as e1:
    try:
        from motor_arbitragem import MotorArbitragem
        MotorClasse = MotorArbitragem
        modo_motor = "motor_arbitragem"
    except Exception as e2:
        erro_motor = f"motor_dados: {e1} | motor_arbitragem: {e2}"

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
if "ultimo_aviso_motor" not in st.session_state:
    st.session_state.ultimo_aviso_motor = ""
if "executor" not in st.session_state and ExecutorArbitragem is not None:
    st.session_state.executor = ExecutorArbitragem(
        modo="DRY_RUN",
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
        sp_liq = round(max(-0.05, sp_base + random.uniform(-0.06, 0.14)), 4)
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
            "Liquidez_Ponta_USDT": round(lote_usdt * random.uniform(0.8, 6.0), 2),
        })
    return sinais


def _calcular_qualidade_dataframe(df: pd.DataFrame, lote_usdt: float) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    sp = pd.to_numeric(out.get("Spread_Liquido_%", 0.0), errors="coerce").fillna(0.0)
    lucro = pd.to_numeric(out.get("Lucro_Est_USDT", 0.0), errors="coerce")
    if "Lucro_Est_USDT" not in out.columns:
        lucro = lote_usdt * (sp / 100.0)
    else:
        lucro = lucro.fillna(lote_usdt * (sp / 100.0))

    liq = pd.to_numeric(out.get("Liquidez_Ponta_USDT", lote_usdt * 2.0), errors="coerce").fillna(lote_usdt * 2.0)

    # Score 0-100: 50% spread líquido, 30% potencial de lucro vs lote, 20% liquidez disponível
    pts_spread = ((sp / 0.25).clip(lower=0.0, upper=1.0)) * 50.0
    lucro_alvo = max(0.5, lote_usdt * 0.002)
    pts_lucro = ((lucro / lucro_alvo).clip(lower=0.0, upper=1.0)) * 30.0
    liq_alvo = max(500.0, lote_usdt * 3.0)
    pts_liq = ((liq / liq_alvo).clip(lower=0.0, upper=1.0)) * 20.0

    score = (pts_spread + pts_lucro + pts_liq).round(1)
    out["Lucro_Est_USDT"] = lucro.round(4)
    out["Score_Qualidade"] = score

    def _rotulo(row):
        if row["Spread_Liquido_%"] <= 0 or row["Score_Qualidade"] < 45:
            return "🔴 Fraca"
        if row["Score_Qualidade"] >= 75:
            return "🟢 Top Lucro"
        return "🟡 Moderada"

    out["Qualidade"] = out.apply(_rotulo, axis=1)
    return out


def _estilizar_radar(df: pd.DataFrame):
    if df.empty:
        return df

    def _estilo_linha(row):
        sp = float(row.get("Spread_Liquido_%", 0.0) or 0.0)
        sc = float(row.get("Score_Qualidade", 0.0) or 0.0)

        if sp <= 0 or sc < 45:
            bg = "#fde8e8"
            fg = "#7f1d1d"
        elif sc >= 75:
            bg = "#dcfce7"
            fg = "#14532d"
        else:
            bg = "#fef9c3"
            fg = "#713f12"

        estilos = []
        for col in df.columns:
            if col in ("Qualidade", "Score_Qualidade", "Spread_Liquido_%", "Lucro_Est_USDT"):
                estilos.append(f"background-color: {bg}; color: {fg}; font-weight: 700;")
            else:
                estilos.append(f"background-color: {bg}; color: {fg};")
        return estilos

    return df.style.apply(_estilo_linha, axis=1).format({
        "Spread_Liquido_%": "{:.4f}%",
        "Spread_Bruto_%": "{:.4f}%",
        "Funding_8h_%": "{:.4f}%",
        "Lucro_Est_USDT": "$ {:.4f}",
        "Liquidez_Ponta_USDT": "$ {:.2f}",
        "Score_Qualidade": "{:.1f}",
    }, na_rep="-")


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
        raise RuntimeError(erro_motor or "Nenhuma classe de motor encontrada")
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


def _executar_ciclo(
    lote_usdt: float,
    filtro_est: list[str],
    meta_alvo: float,
    auto_travar: bool,
    max_perda: float,
    origem_modo: str,
):
    dados_atuais = []
    rotulo_origem = "Simulação de Apoio"
    st.session_state.ultimo_aviso_motor = ""

    if origem_modo in ("Auto (Motor Real -> Fallback Simulação)", "Apenas Motor Real"):
        try:
            coletados = asyncio.run(_coletar_dados())
            if coletados:
                dados_atuais = coletados
                rotulo_origem = "Motor Real"
            elif origem_modo == "Apenas Motor Real":
                st.session_state.ultimo_aviso_motor = "O motor real retornou lista vazia neste ciclo."
        except Exception as e:
            if origem_modo == "Apenas Motor Real":
                st.session_state.ultimo_aviso_motor = f"Falha ao consultar o motor real: {e}"

    if not dados_atuais and origem_modo != "Apenas Motor Real":
        dados_atuais = _gerar_sinais_apoio(lote_usdt)
        rotulo_origem = "Simulação de Apoio"

    st.session_state.fonte_dados = rotulo_origem

    if not dados_atuais:
        st.session_state.ultimo_df = pd.DataFrame()
        return

    df = pd.DataFrame(dados_atuais)
    df["Origem"] = rotulo_origem

    if "Funding_8h_%" not in df.columns:
        df["Funding_8h_%"] = 0.0
    else:
        df["Funding_8h_%"] = df["Funding_8h_%"].fillna(0.0)

    if "Estrategia" in df.columns and filtro_est:
        df = df[df["Estrategia"].isin(filtro_est)]

    df = _calcular_qualidade_dataframe(df, lote_usdt)

    if not df.empty:
        df = df.sort_values(by=["Score_Qualidade", "Lucro_Est_USDT"], ascending=[False, False]).reset_index(drop=True)

    st.session_state.ultimo_df = df

    if "executor" in st.session_state and not df.empty:
        for _, row in df.iterrows():
            sinal = row.to_dict()
            resultado = st.session_state.executor.executar_ordem(sinal)
            resultado["Origem"] = rotulo_origem
            resultado["Qualidade"] = sinal.get("Qualidade", "")
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
    origem_dados = st.selectbox(
        "Origem dos Dados",
        [
            "Auto (Motor Real -> Fallback Simulação)",
            "Apenas Motor Real",
            "Apenas Simulação de Apoio",
        ],
        index=0,
    )
    apenas_top_lucro = st.toggle("Destacar só oportunidades com spread > 0", value=False)
    auto_atualizar = st.toggle("Atualização Automática", value=False)
    intervalo_seg = st.slider("Intervalo automático (seg)", 5, 30, 10)
    mostrar_todas_colunas = st.toggle("Mostrar todas as colunas", value=False)
    lote = st.number_input("Lote por Operação (USDT)", value=float(getattr(config, "LOTE_OPERACAO_USDT", 1000.0)), step=100.0)
    gatilho = st.number_input("Gatilho Lucro Líquido Mínimo (%)", value=float(getattr(config, "SPREAD_MINIMO_LIQUIDO", 0.05)), step=0.01, format="%.2f")
    meta_lucro = st.number_input("Meta de Lucro Simulado (USDT)", min_value=0.0, value=10.0, step=1.0, format="%.2f")
    travar_ao_atingir_meta = st.toggle("Travar executor ao atingir meta", value=False)
    limite_prejuizo = st.number_input("Limite Máximo de Prejuízo (USDT)", min_value=0.0, value=5.0, step=1.0, format="%.2f")
    filtro_estrategia = st.multiselect(
        "Estratégias Ativas",
        ["Espacial (Cross-Exchange)", "Cash & Carry (Spot x Fut)", "Triangular (Intra-Exchange)"],
        default=["Espacial (Cross-Exchange)", "Cash & Carry (Spot x Fut)", "Triangular (Intra-Exchange)"],
    )

    if "executor" in st.session_state:
        st.session_state.executor.modo = "DRY_RUN"
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
    motor_status = modo_motor if modo_motor else "não encontrado"
    st.caption(f"Fonte atual: **{st.session_state.fonte_dados}** | Motor: `{motor_status}` | Modo: **DRY_RUN**")

if st.session_state.ultimo_aviso_motor:
    st.warning(st.session_state.ultimo_aviso_motor)

if rodar_agora or st.session_state.ultimo_df.empty:
    _executar_ciclo(lote, filtro_estrategia, meta_lucro, travar_ao_atingir_meta, limite_prejuizo, origem_dados)

if auto_atualizar:
    @st.fragment(run_every=intervalo_seg)
    def _loop_silencioso():
        _executar_ciclo(lote, filtro_estrategia, meta_lucro, travar_ao_atingir_meta, limite_prejuizo, origem_dados)
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

df = st.session_state.ultimo_df.copy()
if not df.empty and apenas_top_lucro and "Spread_Liquido_%" in df.columns:
    df = df[df["Spread_Liquido_%"] > 0].reset_index(drop=True)

c1, c2 = st.columns(2)
c3, c4 = st.columns(2)
melhor_spread = df["Spread_Liquido_%"].max() if not df.empty and "Spread_Liquido_%" in df.columns else 0.0
melhor_lucro = df["Lucro_Est_USDT"].max() if not df.empty and "Lucro_Est_USDT" in df.columns else 0.0
c1.metric("Melhor Spread Líquido Agora", f"{melhor_spread:.4f}%")
c2.metric("Maior Lucro Est. no Radar", f"$ {melhor_lucro:.4f} USDT")
c3.metric("Ordens Simuladas (Sessão)", len(st.session_state.historico_trades))
c4.metric("Lucro Líquido Simulado", f"$ {st.session_state.lucro_acumulado:.2f} USDT")

colunas_compactas = [
    c for c in ["Qualidade", "Score_Qualidade", "Ativo", "Rota", "Spread_Liquido_%", "Lucro_Est_USDT"]
    if c in df.columns
]
colunas_completas = [
    c for c in [
        "Hora", "Qualidade", "Score_Qualidade", "Origem", "Estrategia", "Ativo", "Rota",
        "Funding_8h_%", "Spread_Bruto_%", "Spread_Liquido_%", "Lucro_Est_USDT", "Liquidez_Ponta_USDT"
    ] if c in df.columns
]
cols_ativas = colunas_completas if mostrar_todas_colunas else colunas_compactas

st.subheader("📡 Radar Dinâmico de Oportunidades (Por Qualidade & Potencial de Lucro)")
st.caption("Legenda: 🟢 Top Lucro (Score >= 75) | 🟡 Moderada (Score 45–74.9) | 🔴 Fraca (Score < 45 ou Spread <= 0)")
if not df.empty:
    df_exibir = df[cols_ativas] if cols_ativas else df
    st.dataframe(_estilizar_radar(df_exibir), width="stretch", height=310)
else:
    st.info("Sem linhas no radar.")

st.subheader("⚖️ Comparação: Motor Real vs. Simulação de Apoio")
res_origem = _resumo_agrupado(st.session_state.historico_trades, "Origem")
if not res_origem.empty:
    st.dataframe(res_origem, width="stretch", height=150)
else:
    st.caption("Execute ciclos com ordens aprovadas para comparar o desempenho acumulado por origem.")

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
        cols_ordens = [c for c in ["Hora", "Qualidade", "Origem", "Ativo", "Rota", "Lote_USDT", "Spread_Liquido_%", "Lucro_Liquido_USDT", "status"] if c in df_ordens.columns]
        st.dataframe(df_ordens[cols_ordens] if cols_ordens else df_ordens, width="stretch", height=220)
    else:
        st.caption("Nenhuma ordem simulada ainda.")

with aba_decisoes:
    if st.session_state.historico_decisoes:
        df_dec = pd.DataFrame(st.session_state.historico_decisoes)
        cols_dec = [c for c in ["Hora", "Qualidade", "Origem", "Ativo", "Rota", "Spread_Liquido_%", "status", "motivo"] if c in df_dec.columns]
        st.dataframe(df_dec[cols_dec] if cols_dec else df_dec, width="stretch", height=240)
    else:
        st.caption("Nenhuma decisão registrada ainda.")
