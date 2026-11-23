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

# ==========================================================
# FUNÇÕES SEGURAS PARA LER CORRETORA_CLIENTE SEM IMPORTBREAK
# ==========================================================
def _extrair_numero(valor, padrao=0.0):
    try:
        if valor is None:
            return padrao
        return float(valor)
    except (TypeError, ValueError):
        return padrao


def ler_saldos_reais():
    """Tenta ler saldos de várias funções possíveis em corretora_cliente.py."""
    nomes_possiveis = (
        "consultar_saldos_usdt",
        "obter_saldos_usdt",
        "buscar_saldos_usdt",
        "ler_saldos_usdt",
        "consultar_saldos",
        "obter_saldos",
        "buscar_saldos",
        "get_saldos",
    )

    resultado = None
    for nome in nomes_possiveis:
        func = getattr(corretora_cliente, nome, None)
        if callable(func):
            try:
                resultado = func()
                break
            except Exception as exc:
                return {
                    "Binance": 0.0,
                    "OKX": 0.0,
                    "erro_binance": str(exc),
                    "erro_okx": str(exc),
                }

    if isinstance(resultado, dict):
        binance = _extrair_numero(
            resultado.get("Binance", resultado.get("binance", resultado.get("BINANCE", 0.0))),
            0.0,
        )
        okx = _extrair_numero(
            resultado.get("OKX", resultado.get("okx", resultado.get("Okx", 0.0))),
            0.0,
        )
        erro_binance = str(resultado.get("erro_binance", "") or "")
        erro_okx = str(resultado.get("erro_okx", "") or "")
        return {
            "Binance": binance,
            "OKX": okx,
            "erro_binance": erro_binance,
            "erro_okx": erro_okx,
        }

    # Caso o corretora_cliente tenha funções separadas por corretora
    binance_val = 0.0
    okx_val = 0.0
    erro_b = ""
    erro_o = ""

    for nome_b in ("saldo_binance", "obter_saldo_binance", "consultar_binance"):
        fb = getattr(corretora_cliente, nome_b, None)
        if callable(fb):
            try:
                binance_val = _extrair_numero(fb(), 0.0)
            except Exception as exc:
                erro_b = str(exc)
            break

    for nome_o in ("saldo_okx", "obter_saldo_okx", "consultar_okx"):
        fo = getattr(corretora_cliente, nome_o, None)
        if callable(fo):
            try:
                okx_val = _extrair_numero(fo(), 0.0)
            except Exception as exc:
                erro_o = str(exc)
            break

    return {
        "Binance": binance_val,
        "OKX": okx_val,
        "erro_binance": erro_b,
        "erro_okx": erro_o,
    }


def verificar_status_conexoes(saldos_dict):
    for nome in ("verificar_conexoes", "status_conexoes", "checar_conexoes"):
        func = getattr(corretora_cliente, nome, None)
        if callable(func):
            try:
                res = func()
                if isinstance(res, dict):
                    return res
            except Exception:
                pass
    return {
        "binance_ok": not bool(saldos_dict.get("erro_binance")),
        "okx_ok": not bool(saldos_dict.get("erro_okx")),
    }


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
modo_real_liberado = False

if quer_modo_real:
    confirmar_real = st.checkbox(
        "⚠️ Confirmo que quero operar em MODO REAL com saldo real na Binance e na OKX",
        value=False,
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
        st.cache_data.clear()
        st.rerun()

    saldos_reais = ler_saldos_reais()
    status_conn = verificar_status_conexoes(saldos_reais)

    saldo_binance = saldos_reais["Binance"]
    saldo_okx = saldos_reais["OKX"]
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

    st.write(f"Conexões — Binance: `{status_conn.get('binance_ok', True)}` | OKX: `{status_conn.get('okx_ok', True)}`")

    if saldos_reais["erro_binance"]:
        st.error(f"Binance: {saldos_reais['erro_binance']}")
    if saldos_reais["erro_okx"]:
        st.error(f"OKX: {saldos_reais['erro_okx']}")

with col_sim:
    st.subheader("🧪 SIMULADO (Ambiente de Teste / DRY_RUN)")

    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        if st.button("➕ Simular +1 Entrada (+0.08 USDT)", key="btn_sim_entrada"):
            if st.session_state.entradas_sim < LIMITE_ENTRADAS:
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
    with c_btn2:
        if st.button("♻️ Resetar Simulação (200 Entradas)", key="btn_reset_sim"):
            st.session_state.entradas_sim = 200
            st.session_state.lucro_sim = 0.0
            st.session_state.historico_sim = []

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
        st.dataframe(pd.DataFrame(st.session_state.historico_sim).tail(5), use_container_width=True)

st.divider()

# ==========================================================
# ESTADO FINAL DO EXECUTOR (DRY_RUN SEMPRE ATIVO SE NÃO LIBERADO)
# ==========================================================
dry_run_efetivo = not modo_real_liberado
st.caption(
    f"Estado do executor: `dry_run={dry_run_efetivo}` | "
    f"`ROBO_ARBITRAGEM_ALLOW_LIVE={os.environ.get('ROBO_ARBITRAGEM_ALLOW_LIVE', '0')}`"
)
