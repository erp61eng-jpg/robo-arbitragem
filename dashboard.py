import random
import streamlit as st

st.set_page_config(page_title="Arbitragem DRY_RUN", layout="wide")
st.title("Arbitragem DRY_RUN — Teste Limpo")

if "ciclo" not in st.session_state:
    st.session_state.ciclo = 1
if "saldo_liq" not in st.session_state:
    st.session_state.saldo_liq = 0.0

lote = st.sidebar.number_input("Lote (USDT)", min_value=10.0, value=180.0, step=10.0)
cotacao = st.sidebar.number_input("R$ por USDT", min_value=1.0, value=5.50, step=0.10)
taxa_total_pct = st.sidebar.number_input("Taxas + Slippage (%)", min_value=0.0, value=0.24, step=0.02)

if st.button("Rodar Proximo Ciclo"):
    st.session_state.ciclo += 1

st.write(f"### Ciclo atual: #{st.session_state.ciclo}")

pares = ["SOL/USDT", "BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT"]
linhas_html = []
lucro_ciclo_usdt = 0.0

for par in pares:
    sp_bruto = round(random.uniform(0.02, 0.35), 4)
    sp_liq = round(sp_bruto - taxa_total_pct, 4)
    lucro_usdt = round(lote * (sp_liq / 100.0), 4)
    lucro_brl = round(lucro_usdt * cotacao, 2)

    if lucro_usdt > 0:
        cor_fundo = "#d1fae5"
        cor_texto = "#065f46"
        acao = "SIMULA ENTRADA"
        lucro_ciclo_usdt += lucro_usdt
    else:
        cor_fundo = "#fee2e2"
        cor_texto = "#991b1b"
        acao = "PULA (CUSTO MAIOR)"

    linhas_html.append(
        f"<tr style='background:{cor_fundo};color:{cor_texto};font-size:17px;'>"
        f"<td style='padding:10px;font-weight:bold;'>{par}</td>"
        f"<td style='padding:10px;'>Bruto: {sp_bruto:.4f}%</td>"
        f"<td style='padding:10px;font-weight:bold;'>Liq: {sp_liq:.4f}%</td>"
        f"<td style='padding:10px;font-weight:bold;'>$ {lucro_usdt:.4f} (R$ {lucro_brl:.2f})</td>"
        f"<td style='padding:10px;font-weight:bold;'>{acao}</td>"
        f"</tr>"
    )

st.session_state.saldo_liq = round(st.session_state.saldo_liq + lucro_ciclo_usdt, 4)
st.write(
    f"**Lucro líquido do ciclo:** $ {lucro_ciclo_usdt:.4f} USDT | "
    f"**Acumulado na sessão:** $ {st.session_state.saldo_liq:.4f} USDT "
    f"(R$ {st.session_state.saldo_liq * cotacao:.2f})"
)

st.markdown(
    "<table style='width:100%;border-collapse:collapse;'>" + "".join(linhas_html) + "</table>",
    unsafe_allow_html=True,
)
