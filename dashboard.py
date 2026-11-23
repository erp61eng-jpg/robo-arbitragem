import os
import pandas as pd
import streamlit as st
import corretora_cliente

# ==========================================================
# CONFIGURAÇÃO DA PÁGINA E ESTILO (SALDOS E LUCRO EM VERDE)
# ==========================================================
st.set_page_config(
    page_title="Robô de Arbitragem — Real vs. Simulado",
    page_icon="🟢",
    layout="wide",
)

st.markdown(
    """
    <style>
        .card-real {
            padding: 16px;
            border-radius: 12px;
            border: 2px solid #00C853;
            background-color: #0b1f14;
            margin-bottom: 10px;
        }
        .card-sim {
            padding: 16px;
            border-radius: 12px;
            border: 2px solid #29B6F6;
            background-color: #0b1929;
            margin-bottom: 10px;
        }
        .texto-verde {
            color: #00E676 !important;
            font-weight: 700;
        }
        .subtexto-verde {
            color: #A5D6A7;
            font-size: 14px;
            margin: 0;
        }
        .linha-info {
            color: #E8F5E9;
            font-size: 14px;
            margin: 6px 0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================================
# PARÂMETROS BASE DO ROBÔ
# ==========================================================
CAPITAL_POR_CORRETORA = 81.0
CAPITAL_TOTAL_BASE = 162.0
LOTE_MAXIMO = 40.5
GATILHO_SPREAD_PCT = 0.05
LIMITE_ENTRADAS = 500
META_LUCRO_USDT = 30.0
LIMITE_PERDA_USDT = -10.0

if "entradas_sim" not in st.session_state:
    st.session_state.entradas_sim = 200
if "lucro_sim" not in st.session_state:
    st.session_state.lucro_sim = 0.0
if "historico_sim" not in st.session_state:
    st.session_state.historico_sim = []
if "saldos_reais_cache" not in st.session_state:
    st.session_state.saldos_reais_cache = None
if "checkbox_confirma_real" not in st.session_state:
    st.session_state.checkbox_confirma_real = False
if "ultimo_resultado_execucao" not in st.session_state:
    st.session_state.ultimo_resultado_execucao = None


def buscar_saldos_seguro() -> dict:
    try:
        if hasattr(corretora_cliente, "obter_saldos_reais"):
            dados = corretora_cliente.obter_saldos_reais()
        else:
            cli = corretora_cliente.ClienteBinanceOKX()
            dados = cli.consultar_saldo_usdt()
        if not isinstance(dados, dict):
            return {
                "Binance": 0.0,
                "OKX": 0.0,
                "erro_binance": "Retorno inválido ao consultar saldos.",
                "erro_okx": "Retorno inválido ao consultar saldos.",
            }
        return {
            "Binance": float(dados.get("Binance", 0.0) or 0.0),
            "OKX": float(dados.get("OKX", 0.0) or 0.0),
            "erro_binance": str(dados.get("erro_binance") or ""),
            "erro_okx": str(dados.get("erro_okx") or ""),
        }
    except Exception as exc:
        msg = str(exc)
        return {
            "Binance": 0.0,
            "OKX": 0.0,
            "erro_binance": msg,
            "erro_okx": msg,
        }


def atualizar_saldos_reais_agora():
    st.session_state.saldos_reais_cache = buscar_saldos_seguro()


if st.session_state.saldos_reais_cache is None:
    atualizar_saldos_reais_agora()

# ==========================================================
# CABEÇALHO E BOTÃO / SELETOR DE MODO (SIMULADO vs. REAL)
# ==========================================================
st.title("⚡ Painel de Arbitragem — Binance & OKX")
st.caption(
    f"Base: ${CAPITAL_TOTAL_BASE:.1f} USDT (${CAPITAL_POR_CORRETORA:.1f} cada) | "
    f"Lote máx.: ${LOTE_MAXIMO:.1f} USDT | Gatilho: {GATILHO_SPREAD_PCT:.2f}% | "
    f"Limite: {LIMITE_ENTRADAS} entradas | Meta: +{META_LUCRO_USDT:.1f} / Stop: {LIMITE_PERDA_USDT:.1f} USDT"
)

st.markdown("### 🎛️ Selecionar Modo de Operação")

modo_selecionado = st.radio(
    "Escolha o modo:",
    options=["🧪 SIMULADO (DRY_RUN)", "💰 REAL (ORDENS REAIS)"],
    horizontal=True,
    key="radio_modo_operacao",
)

quer_modo_real = modo_selecionado == "💰 REAL (ORDENS REAIS)"

if not quer_modo_real and st.session_state.checkbox_confirma_real:
    st.session_state.checkbox_confirma_real = False

modo_real_liberado = False

if quer_modo_real:
    confirmar_real = st.checkbox(
        "⚠️ Confirmo que quero operar em MODO REAL com saldo real na Binance e na OKX",
        key="checkbox_confirma_real",
    )
    if confirmar_real:
        modo_real_liberado = True
        os.environ["ROBO_ARBITRAGEM_ALLOW_LIVE"] = "1"
        st.success("🟢 MODO REAL LIBERADO — Execução real habilitada (ROBO_ARBITRAGEM_ALLOW_LIVE=1).")
    else:
        os.environ["ROBO_ARBITRAGEM_ALLOW_LIVE"] = "0"
        st.warning("🟡 MODO REAL SELECIONADO, MAS BLOQUEADO — Marque a caixa de confirmação para liberar.")
else:
    os.environ["ROBO_ARBITRAGEM_ALLOW_LIVE"] = "0"
    st.info("🔵 MODO SIMULADO (DRY_RUN) ATIVO — Nenhuma ordem real é enviada às corretoras.")

st.divider()

# ==========================================================
# BLOCO 1 (REAL) vs. BLOCO 2 (SIMULADO) LADO A LADO
# ==========================================================
col_real, col_sim = st.columns(2)

with col_real:
    st.subheader("💰 REAL (Saldos Diretos nas Corretoras)")
    if st.button("🔄 Atualizar Saldos Reais", key="btn_atualizar_saldos_reais"):
        atualizar_saldos_reais_agora()
        st.rerun()

    saldos_reais = st.session_state.saldos_reais_cache or buscar_saldos_seguro()
    saldo_binance = float(saldos_reais.get("Binance", 0.0))
    saldo_okx = float(saldos_reais.get("OKX", 0.0))
    saldo_total_real = saldo_binance + saldo_okx
    variacao_real = saldo_total_real - CAPITAL_TOTAL_BASE

    st.markdown(
        f"""
        <div class="card-real">
            <p class="subtexto-verde">SALDO TOTAL REAL (BINANCE + OKX)</p>
            <h2 class="texto-verde" style="margin: 4px 0;">${saldo_total_real:,.4f} USDT</h2>
            <p class="linha-info">
                Binance: <span class="texto-verde">${saldo_binance:,.4f} USDT</span> |
                OKX: <span class="texto-verde">${saldo_okx:,.4f} USDT</span>
            </p>
            <p class="linha-info">
                Resultado vs. Base ($162.00): <span class="texto-verde">{variacao_real:+.4f} USDT</span>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    binance_ok = not bool(saldos_reais.get("erro_binance"))
    okx_ok = not bool(saldos_reais.get("erro_okx"))
    st.write(f"Conexões — Binance: `{binance_ok}` | OKX: `{okx_ok}`")

    if saldos_reais.get("erro_binance"):
        st.error(f"Binance: {saldos_reais['erro_binance']}")
    if saldos_reais.get("erro_okx"):
        st.error(f"OKX: {saldos_reais['erro_okx']}")

with col_sim:
    st.subheader("🧪 SIMULADO (Ambiente de Teste / DRY_RUN)")

    atingiu_meta = st.session_state.lucro_sim >= META_LUCRO_USDT
    atingiu_stop = st.session_state.lucro_sim <= LIMITE_PERDA_USDT
    atingiu_limite = st.session_state.entradas_sim >= LIMITE_ENTRADAS
    bloqueio_sim = atingiu_meta or atingiu_stop or atingiu_limite

    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button(
            "➕ Simular +1 Entrada (+0.08 USDT)",
            key="btn_sim_entrada",
            disabled=bloqueio_sim,
        ):
            ganho_passo = 0.08
            st.session_state.entradas_sim += 1
            st.session_state.lucro_sim = round(st.session_state.lucro_sim + ganho_passo, 4)
            st.session_state.historico_sim.append(
                {
                    "Entrada": st.session_state.entradas_sim,
                    "Lote (USDT)": LOTE_MAXIMO,
                    "Spread (%)": GATILHO_SPREAD_PCT,
                    "Lucro Passo (USDT)": ganho_passo,
                    "Lucro Acumulado (USDT)": st.session_state.lucro_sim,
                }
            )
            st.rerun()
    with c_btn2:
        if st.button("♻️ Resetar Simulação (200 Entradas)", key="btn_reset_sim"):
            st.session_state.entradas_sim = 200
            st.session_state.lucro_sim = 0.0
            st.session_state.historico_sim = []
            st.rerun()

    if atingiu_meta:
        st.success(f"🎯 Meta atingida (+{META_LUCRO_USDT:.1f} USDT).")
    elif atingiu_stop:
        st.error(f"🛑 Limite de perda atingido ({LIMITE_PERDA_USDT:.1f} USDT).")
    elif atingiu_limite:
        st.warning(f"📌 Limite de {LIMITE_ENTRADAS} entradas atingido.")

    saldo_total_sim = CAPITAL_TOTAL_BASE + st.session_state.lucro_sim

    st.markdown(
        f"""
        <div class="card-sim">
            <p class="subtexto-verde">SALDO SIMULADO (DRY_RUN)</p>
            <h2 class="texto-verde" style="margin: 4px 0;">${saldo_total_sim:,.4f} USDT</h2>
            <p class="linha-info">
                Entradas: <b>{st.session_state.entradas_sim} / {LIMITE_ENTRADAS}</b> |
                Lote Máx.: <b>${LOTE_MAXIMO:.1f} USDT</b>
            </p>
            <p class="linha-info">
                Lucro Simulado: <span class="texto-verde">{st.session_state.lucro_sim:+.4f} USDT</span>
                (Meta: +{META_LUCRO_USDT:.1f} | Stop: {LIMITE_PERDA_USDT:.1f})
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.historico_sim:
        df_hist = pd.DataFrame(st.session_state.historico_sim).tail(5)
        try:
            st.dataframe(df_hist, width="stretch")
        except TypeError:
            st.dataframe(df_hist, use_container_width=True)

st.divider()

# ==========================================================
# TESTE MANUAL PROTEGIDO POR DRY_RUN_EFETIVO
# ==========================================================
dry_run_efetivo = not modo_real_liberado

st.markdown("### 🎯 Teste Manual de Execução")
c_t1, c_t2, c_t3 = st.columns([1.2, 1.2, 1.6])
with c_t1:
    ativo_teste = st.text_input("Par", value="BTC/USDT", key="input_ativo_teste")
with c_t2:
    rota_teste = st.selectbox(
        "Rota",
        options=["Binance -> OKX", "OKX -> Binance"],
        key="select_rota_teste",
    )
with c_t3:
    lote_teste = st.number_input(
        "Lote (USDT)",
        min_value=1.0,
        max_value=float(LOTE_MAXIMO),
        value=12.0,
        step=1.0,
        key="input_lote_teste",
    )

if st.button("🚀 Executar Teste Manual", key="btn_executar_teste_manual"):
    try:
        cli = corretora_cliente.ClienteBinanceOKX()
        if dry_run_efetivo:
            st.session_state.ultimo_resultado_execucao = {
                "modo": "SIMULADO (DRY_RUN)",
                "ativo": ativo_teste,
                "rota": rota_teste,
                "lote_usdt": float(lote_teste),
                "status": "BLOQUEADO_POR_DRY_RUN",
                "mensagem": "Nenhuma ordem real enviada. Ative o MODO REAL e marque a confirmação para enviar ordens.",
            }
        else:
            resultado = cli.executar_par_arbitragem(
                ativo=ativo_teste,
                rota=rota_teste,
                lote_usdt=float(lote_teste),
            )
            st.session_state.ultimo_resultado_execucao = resultado
            atualizar_saldos_reais_agora()
    except Exception as exc:
        st.session_state.ultimo_resultado_execucao = {
            "erro": str(exc),
            "tipo_erro": type(exc).__name__,
        }

if st.session_state.ultimo_resultado_execucao is not None:
    st.json(st.session_state.ultimo_resultado_execucao)

st.divider()

# ==========================================================
# ESTADO FINAL DO EXECUTOR (DRY_RUN SEMPRE ATIVO SE NÃO LIBERADO)
# ==========================================================
st.caption(
    f"Estado do executor: `dry_run={dry_run_efetivo}` | "
    f"`ROBO_ARBITRAGEM_ALLOW_LIVE={os.environ.get('ROBO_ARBITRAGEM_ALLOW_LIVE', '0')}`"
)
