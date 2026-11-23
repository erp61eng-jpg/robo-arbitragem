import os
import streamlit as st
from corretora_cliente import consultar_saldos_usdt, verificar_conexoes

# ==========================================================
# SELETOR DE MODO: SIMULADO vs. REAL (COM TRAVA DE SEGURANÇA)
# ==========================================================
st.markdown("### 🎛️ Modo de Operação")

modo_escolhido = st.radio(
    "Selecione o ambiente:",
    options=["🧪 SIMULADO (DRY_RUN)", "💰 REAL (ORDENS REAIS)"],
    horizontal=True,
    key="modo_operacao_radio",
)

eh_modo_real = modo_escolhido == "💰 REAL (ORDENS REAIS)"

if eh_modo_real:
    confirmar_real = st.checkbox(
        "⚠️ Confirmo que desejo operar em MODO REAL com saldo real na Binance e OKX",
        value=False,
        key="confirmar_modo_real",
    )
    if confirmar_real:
        os.environ["ROBO_ARBITRAGEM_ALLOW_LIVE"] = "1"
        st.success("🟢 MODO REAL ATIVO — Ordens reais habilitadas (respeitando suas travas de risco).")
    else:
        os.environ["ROBO_ARBITRAGEM_ALLOW_LIVE"] = "0"
        st.warning("🟡 MODO REAL SELECIONADO, MAS TRAVADO — Marque a caixa de confirmação acima para liberar ordens reais.")
else:
    os.environ["ROBO_ARBITRAGEM_ALLOW_LIVE"] = "0"
    st.info("🔵 MODO SIMULADO (DRY_RUN) ATIVO — Nenhuma ordem real será enviada às corretoras.")

st.divider()

# ==========================================================
# PAINEL SEPARADO: SALDO REAL (API) vs. SIMULADO (DRY_RUN)
# ==========================================================
col_real, col_sim = st.columns(2)

with col_real:
    st.subheader("💰 REAL (Direto da Binance + OKX)")
    if st.button("🔄 Atualizar Saldo Real Agora", key="btn_atualizar_real"):
        st.cache_data.clear()

    conexoes = verificar_conexoes()
    saldos = consultar_saldos_usdt()

    binance_real = float(saldos.get("Binance", 0.0))
    okx_real = float(saldos.get("OKX", 0.0))
    total_real = binance_real + okx_real
    base_referencia = 162.0  # 81.0 Binance + 81.0 OKX
    lucro_real_est = total_real - base_referencia

    st.markdown(
        f"""
        <div style="padding:14px; border-radius:10px; border:2px solid #00C853; background-color:#0b1f14;">
            <p style="margin:0; font-size:15px; color:#A5D6A7;">Saldo Total Real (API)</p>
            <h2 style="margin:4px 0; color:#00E676;">${total_real:,.4f} USDT</h2>
            <p style="margin:4px 0; font-size:14px; color:#E8F5E9;">
                Binance: <b>${binance_real:,.4f}</b> | OKX: <b>${okx_real:,.4f}</b>
            </p>
            <p style="margin:4px 0 0 0; font-size:15px; color:#00E676;">
                Variação vs. Base ($162.00): <b>{lucro_real_est:+.4f} USDT</b>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if saldos.get("erro_binance"):
        st.error(f"Erro Binance: {saldos['erro_binance']}")
    if saldos.get("erro_okx"):
        st.error(f"Erro OKX: {saldos['erro_okx']}")

with col_sim:
    st.subheader("🧪 SIMULADO (Teste / DRY_RUN)")
    # Substitua as variáveis abaixo pelas variáveis de sessão do seu robô, se já existirem:
    entradas_sim = st.session_state.get("entradas_executadas", 200)
    lucro_sim = st.session_state.get("lucro_simulado", 0.0)
    saldo_sim = 162.0 + lucro_sim

    st.markdown(
        f"""
        <div style="padding:14px; border-radius:10px; border:2px solid #29B6F6; background-color:#0b1929;">
            <p style="margin:0; font-size:15px; color:#B3E5FC;">Saldo Simulado (DRY_RUN)</p>
            <h2 style="margin:4px 0; color:#00E676;">${saldo_sim:,.4f} USDT</h2>
            <p style="margin:4px 0; font-size:14px; color:#E1F5FE;">
                Entradas na Rodada: <b>{entradas_sim} / 500</b> | Lote Máx.: <b>$40.50</b>
            </p>
            <p style="margin:4px 0 0 0; font-size:15px; color:#00E676;">
                Lucro Simulado: <b>{lucro_sim:+.4f} USDT</b> (Meta: +30.0 | Stop: -10.0)
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()
