from dataclasses import fields
import html
from pathlib import Path
import time

import pandas as pd
import streamlit as st

from executor import ConfigRisco, ExecutorArbitragem
from motor_dados import ControleRateLimit, MotorDadosArbitragem

st.set_page_config(page_title="Arbitragem Automatica — Somente Executadas", layout="wide")
st.title("Arbitragem Automatica — Rodando & Contabilizando Apenas Executadas")


def _stats_padrao() -> dict:
    return {
        "Binance": {"lucro_usdt": 0.0, "loss_usdt": 0.0, "ops": 0},
        "Bybit": {"lucro_usdt": 0.0, "loss_usdt": 0.0, "ops": 0},
    }


def _init_state():
    defaults = {
        "ciclo": 0,
        "acum_usdt": 0.0,
        "custos_usdt": 0.0,
        "executadas_qtd": 0,
        "lote_dia_atual": 180.0,
        "auto_ativo": True,
        "linhas": [],
        "hist": [],
        "stats_corretoras": _stats_padrao(),
        "destravado_inicial": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if not isinstance(st.session_state.get("stats_corretoras"), dict) or not st.session_state["stats_corretoras"]:
        st.session_state["stats_corretoras"] = _stats_padrao()


def _extrair_corretora(rota: str) -> str:
    rota_limpa = (rota or "").strip()
    if "->" in rota_limpa:
        partes = [p.strip() for p in rota_limpa.split("->")]
        if "Binance" in partes[-1]:
            return "Binance"
        if "Bybit" in partes[-1]:
            return "Bybit"
    if "Binance" in rota_limpa:
        return "Binance"
    if "Bybit" in rota_limpa:
        return "Bybit"
    return "Binance"


def _criar_config_segura(valores: dict) -> ConfigRisco:
    campos_validos = {f.name for f in fields(ConfigRisco)}
    filtrados = {k: v for k, v in valores.items() if k in campos_validos}
    cfg = ConfigRisco(**filtrados)
    for k, v in valores.items():
        if not hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def _obter_motor() -> MotorDadosArbitragem:
    if "motor_dados" not in st.session_state:
        st.session_state.motor_dados = MotorDadosArbitragem(
            modo="observacao",
            rate_limiter=ControleRateLimit(pausa_base=2.0, pausa_maxima=30.0),
        )
    motor = st.session_state.motor_dados
    if hasattr(motor, "limiter") and getattr(motor.limiter, "bloqueado_ate", 0) > time.time():
        motor.limiter.bloqueado_ate = 0.0
    return motor


def _obter_executor(
    lote_max: float,
    meta_ganho: float,
    perda_max: float,
    max_ordens: int,
    taxa_ponta: float,
    slippage: float,
    transf: float,
    gatilho: float,
) -> ExecutorArbitragem:
    valores_cfg = {
        "dry_run": True,
        "capital_referencia_usdt": 180.0,
        "lote_minimo_usdt": 15.0,
        "lote_maximo_usdt": lote_max,
        "meta_ganho_sessao_usdt": meta_ganho,
        "perda_maxima_sessao_usdt": perda_max,
        "max_ordens_sessao": max_ordens,
        "max_ciclos_sem_oportunidade": 999999,
        "gatilho_spread_liq_pct": gatilho,
        "taxa_ponta_pct": taxa_ponta,
        "slippage_total_pct": slippage,
        "taxa_transferencia_usdt": transf,
    }

    if "executor" not in st.session_state:
        cfg = _criar_config_segura(valores_cfg)
        st.session_state.executor = ExecutorArbitragem(config=cfg, pasta_logs="logs")

    ex = st.session_state.executor
    for k, v in valores_cfg.items():
        setattr(ex.cfg, k, v)

    if not hasattr(ex, "status_meta"):
        ex.status_meta = "EM_ANDAMENTO"
    if not hasattr(ex, "ciclos_sem_oportunidade"):
        ex.ciclos_sem_oportunidade = 0

    # Na primeira abertura com o novo painel, limpa travas antigas herdadas do JSON
    if not st.session_state.get("destravado_inicial", False):
        ex.travado_por_risco = False
        ex.status_meta = "EM_ANDAMENTO"
        ex.motivo_trava = ""
        ex.ciclos_sem_oportunidade = 0
        st.session_state.destravado_inicial = True

    if hasattr(ex, "_avaliar_limites_sessao"):
        ex._avaliar_limites_sessao()
    if hasattr(ex, "_salvar_estado"):
        ex._salvar_estado()
    return ex


def rodar_ciclo(
    motor: MotorDadosArbitragem,
    executor: ExecutorArbitragem,
    lote_base: float,
    cotacao: float,
    atualizar_lote_fim_dia: bool,
    pct_lote_dia: float,
):
    if executor.travado_por_risco or executor._avaliar_limites_sessao():
        st.session_state.auto_ativo = False
        executor._salvar_estado()
        return

    st.session_state.ciclo += 1
    c_num = st.session_state.ciclo
    novas_executadas = []

    lote_efetivo = min(float(st.session_state.lote_dia_atual), float(executor.cfg.lote_maximo_usdt))
    cotacoes = motor.coletar_ciclo(motor.ATIVOS_PADRAO)

    for cot in cotacoes:
        if executor.travado_por_risco:
            st.session_state.auto_ativo = False
            break

        if cot.status != "ok":
            continue

        corretora = _extrair_corretora(cot.rota)
        if corretora not in st.session_state.stats_corretoras:
            st.session_state.stats_corretoras[corretora] = {"lucro_usdt": 0.0, "loss_usdt": 0.0, "ops": 0}

        res = executor.avaliar_e_executar(
            ativo=cot.ativo,
            rota=cot.rota,
            lote_usdt=lote_efetivo,
            spread_bruto_pct=cot.spread_bruto_pct,
            saldo_disponivel_usdt=max(lote_base, float(st.session_state.lote_dia_atual)),
        )

        # Contabiliza e exibe EXCLUSIVAMENTE o que foi executado
        if res.decisao not in ("EXECUTADO_DRY_RUN", "EXECUTADO_LIVE"):
            continue

        sp_liq = res.spread_liquido_pct
        liq_usdt = res.lucro_liquido_est_usdt
        liq_brl = round(liq_usdt * cotacao, 2)

        st.session_state.executadas_qtd += 1
        st.session_state.acum_usdt = executor.pnl_acumulado_usdt
        st.session_state.custos_usdt = executor.custos_acumulados_usdt
        st.session_state.stats_corretoras[corretora]["ops"] += 1

        if liq_usdt >= 0:
            st.session_state.stats_corretoras[corretora]["lucro_usdt"] = round(
                st.session_state.stats_corretoras[corretora]["lucro_usdt"] + liq_usdt, 4
            )
            bg, fg, tag = "#d1fae5", "#065f46", "🟢 LUCRO"
        else:
            st.session_state.stats_corretoras[corretora]["loss_usdt"] = round(
                st.session_state.stats_corretoras[corretora]["loss_usdt"] + abs(liq_usdt), 4
            )
            bg, fg, tag = "#fee2e2", "#991b1b", "🔴 LOSS"

        novas_executadas.append({
            "Tag": tag,
            "Ativo": cot.ativo,
            "Corretora": corretora,
            "Sp_Liq": sp_liq,
            "Liq_USDT": liq_usdt,
            "Liq_BRL": liq_brl,
            "Acao": "EXECUTADA",
            "bg": bg,
            "fg": fg,
        })

        st.session_state.hist.append({
            "Ciclo": c_num,
            "Ativo": cot.ativo,
            "Sp_Bruto_%": cot.spread_bruto_pct,
            "Sp_Liq_%": sp_liq,
            "Acumulado_USDT": st.session_state.acum_usdt,
        })

    if executor.travado_por_risco:
        st.session_state.auto_ativo = False

    if atualizar_lote_fim_dia and hasattr(executor, "calcular_lote_fechamento_dia"):
        st.session_state.lote_dia_atual = executor.calcular_lote_fechamento_dia(
            saldo_base_usdt=lote_base,
            percentual_uso=pct_lote_dia,
        )

    st.session_state.hist = st.session_state.hist[-250:]
    if novas_executadas:
        novas_executadas.sort(key=lambda x: x["Liq_USDT"], reverse=True)
        st.session_state.linhas = (novas_executadas + st.session_state.linhas)[:80]


def renderizar_bloco_corretoras(cotacao: float):
    st.subheader("🟢 Lucro e 🔴 Loss por Corretora (Apenas Executadas)")
    stats = st.session_state.get("stats_corretoras") or _stats_padrao()
    nomes = list(stats.keys()) or ["Binance", "Bybit"]
    cols = st.columns(len(nomes))

    for idx, nome_cor in enumerate(nomes):
        dados = stats.get(nome_cor) or {"lucro_usdt": 0.0, "loss_usdt": 0.0, "ops": 0}
        lucro_u = float(dados.get("lucro_usdt", 0.0))
        loss_u = float(dados.get("loss_usdt", 0.0))
        saldo_liq_u = round(lucro_u - loss_u, 4)
        ops_qtd = int(dados.get("ops", 0))
        sinal_saldo = "🟢 +" if saldo_liq_u >= 0 else "🔴 "

        with cols[idx]:
            st.markdown(
                f"<div style='padding:14px;border-radius:10px;border:1px solid #d1d5db;background:#ffffff;'>"
                f"<div style='font-size:18px;font-weight:800;color:#111827;margin-bottom:8px;'>{html.escape(str(nome_cor))}</div>"
                f"<div style='font-size:17px;font-weight:700;color:#065f46;background:#d1fae5;padding:6px 10px;border-radius:6px;margin-bottom:6px;'>"
                f"🟢 Lucro: +$ {lucro_u:.4f} USDT (R$ {lucro_u * cotacao:.2f})</div>"
                f"<div style='font-size:17px;font-weight:700;color:#991b1b;background:#fee2e2;padding:6px 10px;border-radius:6px;margin-bottom:6px;'>"
                f"🔴 Loss: -$ {loss_u:.4f} USDT (-R$ {loss_u * cotacao:.2f})</div>"
                f"<div style='font-size:16px;font-weight:700;color:#1f2937;'>"
                f"Saldo: {sinal_saldo}$ {saldo_liq_u:.4f} USDT | Executadas: {ops_qtd}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


def renderizar_bloco_executor(executor: ExecutorArbitragem, cotacao: float):
    st.divider()
    st.subheader("Controle de Limites, Risco & Auditoria")

    status_meta = getattr(executor, "status_meta", "EM_ANDAMENTO")
    meta_ganho_val = float(getattr(executor.cfg, "meta_ganho_sessao_usdt", 15.0))
    perda_max_val = float(getattr(executor.cfg, "perda_maxima_sessao_usdt", 5.0))
    max_ordens_val = int(getattr(executor.cfg, "max_ordens_sessao", 120))

    col_status, col_acao = st.columns([3, 1])
    with col_status:
        if status_meta == "META_GANHO_ATINGIDA":
            st.success(f"🟢 PARADA AUTOMATICA — LIMITE DE GANHO ATINGIDO: {executor.motivo_trava}")
        elif status_meta == "STOP_LOSS_ATINGIDO":
            st.error(f"🔴 PARADA AUTOMATICA — LIMITE DE PERDA ATINGIDO: {executor.motivo_trava}")
        elif status_meta == "LIMITE_ORDENS_ATINGIDO":
            st.warning(f"⏸️ PARADA AUTOMATICA — {executor.motivo_trava}")
        else:
            st.info(
                f"RODANDO AUTOMATICO — Ganho: +{meta_ganho_val:.2f} USDT | "
                f"Perda: -{perda_max_val:.2f} USDT | "
                f"Teto Ordens: {executor.ordens_executadas}/{max_ordens_val}"
            )

    with col_acao:
        if st.button("Resetar e Retomar Auto", use_container_width=True):
            executor.resetar_sessao()
            st.session_state.ciclo = 0
            st.session_state.acum_usdt = 0.0
            st.session_state.custos_usdt = 0.0
            st.session_state.executadas_qtd = 0
            st.session_state.lote_dia_atual = 180.0
            st.session_state.auto_ativo = True
            st.session_state.linhas = []
            st.session_state.hist = []
            st.session_state.stats_corretoras = _stats_padrao()
            st.rerun()

    e1, e2, e3 = st.columns(3)
    sinal_pnl = "🟢 +" if executor.pnl_acumulado_usdt >= 0 else "🔴 "
    e1.metric(
        "PnL Acumulado (Executadas)",
        f"{sinal_pnl}$ {executor.pnl_acumulado_usdt:.4f} USDT",
        f"R$ {executor.pnl_acumulado_usdt * cotacao:.2f}",
    )
    e2.metric(
        "Custos Descontados",
        f"$ {executor.custos_acumulados_usdt:.4f} USDT",
        f"R$ {executor.custos_acumulados_usdt * cotacao:.2f}",
    )
    e3.metric(
        "Ordens Executadas",
        f"{executor.ordens_executadas}/{max_ordens_val}",
    )

    st.markdown("#### Historico de Auditoria (`logs/execucoes_auditoria.csv` — Apenas Executadas)")
    caminho_csv: Path = executor.arquivo_csv

    if caminho_csv.exists():
        try:
            df_log = pd.read_csv(caminho_csv)
            if not df_log.empty and "decisao" in df_log.columns:
                df_exec = df_log[df_log["decisao"].isin(["EXECUTADO_DRY_RUN", "EXECUTADO_LIVE"])]
                if not df_exec.empty:
                    st.dataframe(
                        df_exec.tail(30).iloc[::-1],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Nenhuma operacao executada registrada no CSV ainda.")
            else:
                st.info("O arquivo CSV existe, mas ainda nao ha execucoes registradas.")
        except Exception as exc:
            st.warning(f"Nao foi possivel ler o CSV agora: {exc}")
    else:
        st.info("Nenhum log CSV gerado ainda em `logs/execucoes_auditoria.csv`.")


def renderizar_painel(
    motor: MotorDadosArbitragem,
    executor: ExecutorArbitragem,
    lote: float,
    taxa_ponta: float,
    slippage: float,
    transf: float,
    cotacao: float,
    ativo_foco: str,
    atualizar_lote_fim_dia: bool,
    pct_lote_dia: float,
    executar: bool,
):
    if not st.session_state.hist and st.session_state.ciclo == 0:
        st.session_state.hist = motor.historico_inicial(lote, taxa_ponta, slippage, transf)

    if executar or not st.session_state.linhas:
        rodar_ciclo(motor, executor, lote, cotacao, atualizar_lote_fim_dia, pct_lote_dia)

    st.caption(f"{motor.limiter.status_texto()} | Ciclo #{st.session_state.ciclo} | Auto: {'ON' if st.session_state.auto_ativo else 'OFF'}")

    stats = st.session_state.get("stats_corretoras") or _stats_padrao()
    total_lucro_cor = sum(float(v.get("lucro_usdt", 0.0)) for v in stats.values())
    total_loss_cor = sum(float(v.get("loss_usdt", 0.0)) for v in stats.values())
    acum_usdt = float(executor.pnl_acumulado_usdt)
    acum_brl = acum_usdt * cotacao
    saldo_conta_estimado = lote + acum_usdt
    sinal_acum = "🟢 +" if acum_usdt >= 0 else "🔴 "

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Operacoes Executadas", f"{st.session_state.executadas_qtd}")
    m2.metric("🟢 Lucro Executado", f"+$ {total_lucro_cor:.4f} USDT", f"R$ {total_lucro_cor * cotacao:.2f}")
    m3.metric("🔴 Loss Executado", f"-$ {total_loss_cor:.4f} USDT", f"-R$ {total_loss_cor * cotacao:.2f}")
    m4.metric(
        "Saldo Liquido Sessao",
        f"{sinal_acum}$ {acum_usdt:.4f}",
        f"Conta: $ {saldo_conta_estimado:.2f} (R$ {acum_brl:.2f})",
    )

    renderizar_bloco_corretoras(cotacao)

    df_hist = pd.DataFrame(st.session_state.hist)
    if not df_hist.empty:
        df_a = df_hist[df_hist["Ativo"] == ativo_foco].set_index("Ciclo")
        if not df_a.empty:
            st.subheader(f"Spread Bruto vs. Spread Liquido (Executadas) — {ativo_foco}")
            g1, g2 = st.columns(2)
            with g1:
                st.caption("Spread Bruto (%) vs. Spread Liquido apos Custos (%)")
                st.line_chart(df_a[["Sp_Bruto_%", "Sp_Liq_%"]], height=230)
            with g2:
                st.caption("Lucro Liquido Acumulado (USDT)")
                st.line_chart(df_a[["Acumulado_USDT"]], height=230)

    st.subheader("Operacoes Executadas")
    trs = []
    for r in st.session_state.linhas:
        if r.get("Acao") != "EXECUTADA":
            continue
        liq_val = float(r.get("Liq_USDT", 0.0))
        sinal_val = "+" if liq_val > 0 else ""
        cor_nome = str(r.get("Corretora") or _extrair_corretora(str(r.get("Ativo", ""))))
        trs.append(
            f"<tr style='background:{r.get('bg', '#ffffff')};color:{r.get('fg', '#111827')};border-bottom:2px solid #ffffff;'>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>{html.escape(str(r.get('Tag', '')))}</td>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>{html.escape(str(r.get('Ativo', '')))}</td>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>{html.escape(cor_nome)}</td>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>{sinal_val}$ {liq_val:.4f}</td>"
            f"<td style='padding:12px 10px;font-weight:700;font-size:17px;'>{html.escape(str(r.get('Acao', '')))}</td>"
            f"</tr>"
        )

    if trs:
        st.markdown(
            "<div style='width:100%;overflow-x:auto;border-radius:8px;border:1px solid #d1d5db;'>"
            "<table style='width:100%;border-collapse:collapse;font-size:17px;'>"
            "<thead>"
            "<tr style='background:#1f2937;color:#ffffff;font-size:16px;'>"
            "<th style='padding:11px 10px;text-align:left;'>Resultado</th>"
            "<th style='padding:11px 10px;text-align:left;'>Ativo</th>"
            "<th style='padding:11px 10px;text-align:left;'>Corretora</th>"
            "<th style='padding:11px 10px;text-align:left;'>Valor USDT</th>"
            "<th style='padding:11px 10px;text-align:left;'>Status</th>"
            "</tr>"
            "</thead>"
            "<tbody>" + "".join(trs) + "</tbody>"
            "</table>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Rodando em tempo real — aguardando nova operacao executada...")

    renderizar_bloco_executor(executor, cotacao)


_init_state()

with st.sidebar:
    st.header("Limites, Custos & Controles")
    lote = st.number_input("Saldo Base / Lote Inicial (USDT)", min_value=20.0, value=180.0, step=20.0)
    lote_max = st.number_input("Teto Lote / Giro (USDT)", min_value=15.0, value=90.0, step=5.0)
    meta_ganho = st.number_input("Limite de Ganho Sessao (USDT)", min_value=0.50, value=15.00, step=0.50)
    perda_max = st.number_input("Limite de Perda Sessao (USDT)", min_value=0.50, value=5.00, step=0.50)
    max_ordens = st.number_input("Max Ordens na Sessao", min_value=1, value=120, step=5)
    cotacao = st.number_input("Cotacao R$ / USDT", min_value=1.0, value=5.50, step=0.10)
    taxa_ponta = st.number_input("Taxa por Ponta (%)", min_value=0.0, value=0.10, step=0.01, format="%.3f")
    slippage = st.number_input("Slippage Total (%)", min_value=0.0, value=0.04, step=0.01, format="%.3f")
    transf = st.number_input("Taxa Transferencia (USDT)", min_value=0.0, value=0.00, step=0.25, format="%.2f")
    gatilho = st.number_input("Gatilho Liquido Minimo (%)", min_value=0.0, value=0.00, step=0.01, format="%.2f")
    atualizar_lote_fim_dia = st.toggle("Atualizar Lote no Final do Dia", value=True)
    pct_lote_dia = st.slider("% do Saldo no Giro", min_value=10, max_value=100, value=50, step=5) / 100.0
    ativo_foco = st.selectbox("Ativo no Grafico", [a[0] for a in MotorDadosArbitragem.ATIVOS_PADRAO], index=0)

    st.divider()
    auto_rodar = st.toggle("Modo Automatico Continuo", value=st.session_state.auto_ativo)
    st.session_state.auto_ativo = auto_rodar
    segundos = st.slider("Intervalo (seg)", min_value=2, max_value=15, value=3)

    if st.button("Zerar Tudo"):
        st.session_state.ciclo = 0
        st.session_state.acum_usdt = 0.0
        st.session_state.custos_usdt = 0.0
        st.session_state.executadas_qtd = 0
        st.session_state.lote_dia_atual = lote
        st.session_state.auto_ativo = True
        st.session_state.linhas = []
        st.session_state.hist = []
        st.session_state.stats_corretoras = _stats_padrao()

motor = _obter_motor()
executor = _obter_executor(
    lote_max, meta_ganho, perda_max, max_ordens, taxa_ponta, slippage, transf, gatilho
)

if executor.travado_por_risco:
    st.session_state.auto_ativo = False
    auto_rodar = False

renderizar_painel(
    motor,
    executor,
    lote,
    taxa_ponta,
    slippage,
    transf,
    cotacao,
    ativo_foco,
    atualizar_lote_fim_dia,
    pct_lote_dia,
    executar=True,
)

if st.session_state.auto_ativo and not executor.travado_por_risco:
    st.caption(f"Automatico ativo a cada {segundos}s — so para ao bater +15.00 USDT, -5.00 USDT ou teto de ordens.")
    time.sleep(segundos)
    st.rerun()
