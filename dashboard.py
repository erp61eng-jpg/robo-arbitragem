def _renderizar_cards_coloridos(df_radar: pd.DataFrame):
    if df_radar.empty:
        return

    st.markdown("#### 🎨 Destaque Visual por Qualidade e Lucro Estimado")
    top_linhas = df_radar.head(5)

    for _, linha in top_linhas.iterrows():
        ativo = linha.get("Ativo", "N/A")
        rota = linha.get("Rota", "N/A")
        sp = float(linha.get("Spread_Liquido_%", 0.0) or 0.0)
        lucro = float(linha.get("Lucro_Est_USDT", 0.0) or 0.0)
        score = float(linha.get("Score_Qualidade", 0.0) or 0.0)

        if sp <= 0 or score < 45:
            bg = "#fee2e2"
            borda = "#dc2626"
            texto = "#7f1d1d"
            tag = "🔴 FRACA / BAIXO LUCRO"
        elif score >= 75:
            bg = "#dcfce7"
            borda = "#16a34a"
            texto = "#14532d"
            tag = "🟢 TOP LUCRO"
        else:
            bg = "#fef9c3"
            borda = "#ca8a04"
            texto = "#713f12"
            tag = "🟡 MODERADA"

        st.markdown(
            f"""
            <div style="
                background-color: {bg};
                border-left: 6px solid {borda};
                color: {texto};
                padding: 10px 14px;
                border-radius: 6px;
                margin-bottom: 8px;
                font-size: 15px;
            ">
                <strong>{tag}</strong> — <strong>{ativo}</strong> ({rota}) |
                Spread Líquido: <strong>{sp:.4f}%</strong> |
                Lucro Est.: <strong>$ {lucro:.4f} USDT</strong> |
                Score: <strong>{score:.1f}/100</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )
