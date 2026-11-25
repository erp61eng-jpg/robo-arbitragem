import os
import streamlit as st

import corretora_cliente as cc

st.set_page_config(page_title="Monitor e Execução - Arbitragem", layout="wide")
st.title("Monitor de Rentabilidade e Arbitragem (Binance x OKX)")

if "resultados_varredura" not in st.session_state:
    st.session_state["resultados_varredura"] = []

col_cfg1, col_cfg2, col_cfg3, col_cfg4 = st.columns(4)
with col_cfg1:
    lote_usdt = st.number_input("Lote por operação (USDT)", min_value=5.0, max_value=5000.0, value=15.0, step=5.0)
with col_cfg2:
    meta_liq = st.number_input("Meta spread líquido (%)", min_value=0.01, max_value=5.0, value=0.05, step=0.01)
with col_cfg3:
    buf_slip = st.number_input("Buffer slippage (%)", min_value=0.0, max_value=2.0, value=0.02, step=0.01)
with col_cfg4:
    allow_live_atual = os.getenv("ROBO_ARBITRAGEM_ALLOW_LIVE", "0").strip()
    st.metric("Modo Real (ALLOW_LIVE)", allow_live_atual)

pares_padrao = "BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, DOGE/USDT, ADA/USDT, LINK/USDT, TRX/USDT, SUI/USDT, AVAX/USDT"
pares_texto = st.text_input("Ativos USDT para monitorar (separados por vírgula)", value=pares_padrao)
lista_pares = [p.strip().upper() for p in pares_texto.split(",") if p.strip()]

cli = cc.ClienteBinanceOKX()

if st.button("Monitorar ativos agora", type="primary"):
    with st.spinner("Consultando Binance e OKX..."):
        st.session_state["resultados_varredura"] = cc.varrer_oportunidades_usdt(
            cli=cli,
            pares=lista_pares,
            lote_usdt=float(lote_usdt),
            min_spread_liq_pct=float(meta_liq),
            slippage_buf_pct=float(buf_slip),
            apenas_aprovados=False,
        )

resultados = st.session_state["resultados_varredura"]
if resultados:
    st.subheader("Rentabilidade após taxas")
    st.dataframe(resultados, use_container_width=True)

    opcoes_ativos = [r["ativo"] for r in resultados]
    ativo_escolhido = st.selectbox("Escolha o ativo para revalidar e operar", options=opcoes_ativos)
    av_atual = cli.avaliar_oportunidade(
        ativo=ativo_escolhido,
        lote_usdt=float(lote_usdt),
        min_spread_liq_pct=float(meta_liq),
        slippage_buf_pct=float(buf_slip),
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rota", av_atual.sentido or "-")
    c2.metric("Spread Líquido", f"{av_atual.spread_liquido_pct:+.4f}%")
    c3.metric("Lucro Líquido Est.", f"{float(lote_usdt) * (av_atual.spread_liquido_pct / 100.0):+.5f} USDT")
    c4.metric("Aprovado p/ Operar", "SIM" if av_atual.permitido else "NÃO")

    st.info(f"Diagnóstico atual: {av_atual.motivo}")

    if st.button("Operar ativo selecionado (se aprovado)", disabled=not av_atual.permitido):
        try:
            res_exec = cli.executar_par_arbitragem(
                ativo=ativo_escolhido,
                rota=av_atual.sentido or "OKX->Binance",
                lote=float(lote_usdt),
                min_spread_liq_pct=float(meta_liq),
                slippage_buf_pct=float(buf_slip),
            )
            st.success(f"Ordem executada: {res_exec}")
        except Exception as exc:
            st.error(f"Execução bloqueada/falhou: {exc}")
