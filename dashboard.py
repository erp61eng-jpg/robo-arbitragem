st.subheader("🎯 Radar Enxuto (Colunas Principais)")
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
