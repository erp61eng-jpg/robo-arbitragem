import asyncio
import os
import time
import pandas as pd
import streamlit as st

try:
    import corretora_cliente
except Exception:
    corretora_cliente = None

try:
    from motor_arbitragem import MotorArbitragem
except Exception:
    MotorArbitragem = None

st.set_page_config(
    page_title="Arbitragem Automática — Números Grandes",
    page_icon="🟢",
    layout="wide",
)

st.markdown(
    """
    <style>
        .card-verde {
            padding: 22px;
            border-radius: 14px;
            border: 3px solid #00E676;
            background-color: #071d12;
            margin-bottom: 14px;
        }
        .card-soma {
            padding: 24px;
            border-radius: 14px;
            border: 3px solid #00FF7F;
            background-color: #092617;
            margin-bottom: 14px;
        }
        .rotulo-verde {
            color: #A5F5B8;
            font-size: 16px;
            font-weight: 800;
            margin: 0 0 6px 0;
            letter-spacing: 0.5px;
        }
        .numero-gigante {
            color: #00FF7F !important;
            font-size: 46px !important;
            font-weight: 900 !important;
            line-height: 1.1 !important;
            margin: 4px 0 10px 0 !important;
        }
        .numero-grande {
            color: #00FF7F !important;
            font-size: 32px !important;
            font-weight: 900 !important;
            line-height: 1.15 !important;
            margin: 4px 0 8px 0 !important;
        }
        .linha-grande {
            color: #F0FFF4;
            font-size: 18px;
            font-weight: 700;
            margin: 6px 0 0 0;
        }
        .verde-destaque {
            color: #00FF7F !important;
            font-weight: 900;
        }
        div.stButton > button {
            font-size: 17px !important;
            font-weight: 800 !important;
            padding: 12px 16px !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

BASE_TOTAL = 162.0
LOTE_MAX = 40.5
GATILHO_PCT = 0.05
LIMITE_ENT = 500
META_USDT = 30.0
STOP_USDT = -10.0
INTERVALO_SCAN_SEG = 4.0


def _get_cliente(metodo: str):
    if corretora_cliente is None:
        return None
    for attr in dir(corretora_cliente):
        obj = getattr(corretora_cliente, attr)
        if isinstance(obj, type):
            try:
                inst = obj()
                if hasattr(inst, metodo):
                    return inst
            except Exception:
                pass
    return None


def _num(val) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        for k in ("free", "total", "usdt", "USDT", "saldo", "balance"):
            if k in val and isinstance(val[k], (int, float)):
                return float(val[k])
    return 0.0


def corrigir_saldo_real_final() -> dict:
    cli = _get_cliente("consultar_saldo_usdt")
    if cli is None:
        return {"Binance": 0.0, "OKX": 0.0, "erro": "Sem consultar_saldo_usdt em corretora_cliente.py"}
    try:
        d = cli.consultar_saldo_usdt()
        if not isinstance(d, dict):
            return {"Binance": 0.0, "OKX": 0.0, "erro": str(d)}
        b = next(
            (_num(v) for k, v in d.items() if "binance" in str(k).lower() and not str(k).lower().startswith("erro")),
            0.0,
        )
        o = next(
            (_num(v) for k, v in d.items() if "okx" in str(k).lower() and not str(k).lower().startswith("erro")),
            0.0,
        )
        err = d.get("erro_binance") or d.get("erro_okx") or ""
        return {"Binance": b, "OKX": o, "erro": str(err)}
    except Exception as e:
        return {"Binance": 0.0, "OKX": 0.0, "erro": f"{type(e).__name__}: {e}"}


async def _coletar_motor_async(par_alvo: str, rota_alvo: str, margem_min_pct: float) -> dict:
    if MotorArbitragem is None:
        return {
            "ok": False,
            "total_rotas": 0,
            "melhor_rota": rota_alvo,
            "spread_liq_pct": 0.0,
            "lucro_est_usdt": 0.0,
            "motivo": "motor_arbitragem.py não encontrado; usando modo base.",
        }

    motor = MotorArbitragem(margem_minima_pct=margem_min_pct, apenas_viaveis=False)
    try:
        ops = await motor.escanear_tudo()
    finally:
        await motor.fechar_conexoes()
        await asyncio.sleep(0.25)

    if not ops:
        return {
            "ok": False,
            "total_rotas": 0,
            "melhor_rota": rota_alvo,
            "spread_liq_pct": 0.0,
            "lucro_est_usdt": 0.0,
            "motivo": "Nenhuma rota retornada pelo motor.",
        }

    filtradas_par = [o for o in ops if str(o.get("Ativo", "")).upper() == par_alvo.upper()]
    candidatas = filtradas_par if filtradas_par else ops

    parte_rota = rota_alvo.split("->")[0].strip().upper() if "->" in rota_alvo else rota_alvo.upper()
    filtradas_rota = [o for o in candidatas if parte_rota in str(o.get("Rota", "")).upper()]
    pool = filtradas_rota if filtradas_rota else candidatas

    melhor = max(pool, key=lambda x: float(x.get("Spread_Liquido_%", -999.0)))
    spread_liq = float(melhor.get("Spread_Liquido_%", 0.0))
    lucro_est = float(melhor.get("Lucro_Est_USDT", 0.0))

    return {
        "ok": spread_liq >= margem_min_pct,
        "total_rotas": len(ops),
        "melhor_rota": str(melhor.get("Rota", rota_alvo)),
        "spread_liq_pct": spread_liq,
        "lucro_est_usdt": lucro_est,
        "motivo": (
            f"Spread líquido {spread_liq:+.4f}% (mín. {margem_min_pct:.2f}%)"
            if spread_liq >= margem_min_pct
            else f"Spread líquido {spread_liq:+.4f}% abaixo de {margem_min_pct:.2f}%"
        ),
    }


def consultar_motor(par: str, rota: str, margem_min_pct: float) -> dict:
    agora = time.monotonic()
    cache = st.session_state.get("ultimo_scan_motor")
    if cache and (agora - cache.get("ts", 0.0)) < INTERVALO_SCAN_SEG:
        if cache.get("par") == par and cache.get("rota") == rota and cache.get("margem") == margem_min_pct:
            return cache["dados"]

    try:
        dados = asyncio.run(_coletar_motor_async(par, rota, margem_min_pct))
    except Exception as e:
        dados = {
            "ok": False,
            "total_rotas": 0,
            "melhor_rota": rota,
            "spread_liq_pct": 0.0,
            "lucro_est_usdt": 0.0,
            "motivo": f"Falha na leitura do motor: {type(e).__name__}: {e}",
        }

    st.session_state.ultimo_scan_motor = {
        "ts": time.monotonic(),
        "par": par,
        "rota": rota,
        "margem": margem_min_pct,
        "dados": dados,
    }
    return dados


def rodar_op(par: str, rota: str, lote: float, real_ok: bool, scan: dict, simular_sem_spread: bool) -> dict:
    hora = time.strftime("%H:%M:%S")
    spread_liq = float(scan.get("spread_liq_pct", 0.0))
    lucro_real_est = round(float(lote) * (spread_liq / 100.0), 4)
    lucro_sim = 0.08 if float(lote) == LOTE_MAX else round(float(lote) * 0.002, 4)

    if not real_ok:
        if scan.get("ok"):
            lucro_final = lucro_real_est if lucro_real_est > 0 else lucro_sim
            return {
                "ok": True,
                "modo": "SIMULADO",
                "hora": hora,
                "par": par,
                "rota": scan.get("melhor_rota", rota),
                "lote": float(lote),
                "lucro": lucro_final,
                "msg": f"AUTO SIMULADO (APROVADO) — {par} ({spread_liq:+.4f}%) | +${lucro_final:.4f} USDT",
            }
        if simular_sem_spread:
            return {
                "ok": True,
                "modo": "SIMULADO",
                "hora": hora,
                "par": par,
                "rota": rota,
                "lote": float(lote),
                "lucro": lucro_sim,
                "msg": f"AUTO SIMULADO — {par} ({spread_liq:+.4f}%) | +${lucro_sim:.4f} USDT",
            }
        return {
            "ok": False,
            "modo": "SIMULADO",
            "hora": hora,
            "par": par,
            "rota": rota,
            "lote": float(lote),
            "lucro": 0.0,
            "msg": f"Aguardando spread >= {GATILHO_PCT:.2f}% ({scan.get('motivo', '')})",
        }

    if not scan.get("ok"):
        return {
            "ok": False,
            "modo": "REAL",
            "hora": hora,
            "par": par,
            "rota": rota,
            "lote": float(lote),
            "lucro": 0.0,
            "msg": f"Bloqueado no REAL: {scan.get('motivo', 'spread insuficiente')}",
        }

    cli = _get_cliente("executar_par_arbitragem")
    if cli is None:
        return {
            "ok": False,
            "modo": "REAL",
            "hora": hora,
            "par": par,
            "rota": rota,
            "lote": float(lote),
            "lucro": 0.0,
            "msg": "Sem executar_par_arbitragem em corretora_cliente.py",
        }

    try:
        r = cli.executar_par_arbitragem(ativo=par, rota=rota, lote_usdt=float(lote))
        err = (r.get("erro") or r.get("error") or "") if isinstance(r, dict) else ""
        if err:
            return {
                "ok": False,
                "modo": "REAL",
                "hora": hora,
                "par": par,
                "rota": rota,
                "lote": float(lote),
                "lucro": 0.0,
                "msg": str(err),
            }
        return {
            "ok": True,
            "modo": "REAL",
            "hora": hora,
            "par": par,
            "rota": rota,
            "lote": float(lote),
            "lucro": lucro_real_est,
            "msg": f"AUTO REAL — {par} ({rota}) | {spread_liq:+.4f}%",
        }
    except Exception as e:
        return {
            "ok": False,
            "modo": "REAL",
            "hora": hora,
            "par": par,
            "rota": rota,
            "lote": float(lote),
            "lucro": 0.0,
            "msg": f"{type(e).__name__}: {e}",
        }


def executar_passo(par: str, rota: str, lote: float, real_ok: bool, simular_sem_spread: bool) -> tuple[bool, str]:
    if (
        st.session_state.lucro >= META_USDT
        or st.session_state.lucro <= STOP_USDT
        or st.session_state.entradas >= LIMITE_ENT
    ):
        return False, "Limite de entradas, meta ou stop atingido."

    scan = consultar_motor(par, rota, GATILHO_PCT)
    r = rodar_op(par, rota, float(lote), real_ok, scan, simular_sem_spread)
    if r["ok"]:
        st.session_state.entradas += 1
        st.session_state.contagem_ops += 1
        st.session_state.lucro = round(st.session_state.lucro + r["lucro"], 4)
        st.session_state.operacoes.insert(
            0,
            {
                "Nº": st.session_state.contagem_ops,
                "Hora": r["hora"],
                "Modo": r["modo"],
                "Par": r["par"],
                "Rota": r["rota"],
                "Lote": r["lote"],
                "Spread_Liq_%": round(float(scan.get("spread_liq_pct", 0.0)), 4),
                "Lucro": r["lucro"],
            },
        )
        return True, r["msg"]
    return False, r["msg"]


if "saldo_real" not in st.session_state:
    st.session_state.saldo_real = {"Binance": 81.1099, "OKX": 84.8030, "erro": ""}
if "entradas" not in st.session_state:
    st.session_state.entradas = 200
if "contagem_ops" not in st.session_state:
    st.session_state.contagem_ops = 0
if "lucro" not in st.session_state:
    st.session_state.lucro = 0.0
if "operacoes" not in st.session_state:
    st.session_state.operacoes = []
if "aviso" not in st.session_state:
    st.session_state.aviso = None
if "rodando_auto" not in st.session_state:
    st.session_state.rodando_auto = True
if "ultimo_scan_motor" not in st.session_state:
    st.session_state.ultimo_scan_motor = None

st.title("🟢 Robô de Arbitragem Automático — Binance & OKX")
st.caption(
    f"Base: ${BASE_TOTAL:.1f} USDT | Lote máx.: ${LOTE_MAX:.1f} USDT | "
    f"Gatilho: {GATILHO_PCT:.2f}% | Intervalo: {INTERVALO_SCAN_SEG:.1f}s | "
    f"Meta: +{META_USDT:.1f} / Stop: {STOP_USDT:.1f} USDT"
)

modo = st.radio(
    "Modo:",
    ["🧪 SIMULADO (DRY_RUN)", "💰 REAL (ORDENS REAIS)"],
    horizontal=True,
)

simular_sem_spread = False
real_liberado = False
if modo.startswith("💰"):
    real_liberado = st.checkbox("⚠️ Confirmo operar em MODO REAL na Binance e na OKX", value=False)
    os.environ["ROBO_ARBITRAGEM_ALLOW_LIVE"] = "1" if real_liberado else "0"
    if real_liberado:
        st.success("🟢 MODO REAL LIBERADO")
    else:
        st.session_state.rodando_auto = False
        st.warning("🟡 Marque a caixa para liberar o MODO REAL")
else:
    os.environ["ROBO_ARBITRAGEM_ALLOW_LIVE"] = "0"
    simular_sem_spread = st.checkbox(
        "🧪 Simular passos mesmo quando o spread líquido estiver abaixo do gatilho",
        value=True,
    )
    st.info("🔵 MODO SIMULADO (DRY_RUN) COM MOTOR VWAP ATIVO")

soma_total = BASE_TOTAL + st.session_state.lucro
st.markdown(
    f"""
    <div class="card-soma">
        <p class="rotulo-verde">SOMA TOTAL (BASE + LUCRO)</p>
        <div class="numero-gigante">${soma_total:,.4f} USDT</div>
        <p class="linha-grande">
            LUCRO: <span class="verde-destaque">{st.session_state.lucro:+.4f} USDT</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            OPERAÇÕES FEITAS: <span class="verde-destaque">{st.session_state.contagem_ops}</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            ENTRADAS: <span class="verde-destaque">{st.session_state.entradas}/{LIMITE_ENT}</span>
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

c1, c2 = st.columns(2)

with c1:
    sb = float(st.session_state.saldo_real.get("Binance", 0.0))
    so = float(st.session_state.saldo_real.get("OKX", 0.0))
    st.markdown(
        f"""
        <div class="card-verde">
            <p class="rotulo-verde">SALDO REAL (AJUSTE SÓ NO FINAL)</p>
            <div class="numero-grande">${sb + so:,.4f} USDT</div>
            <p class="linha-grande">
                Binance: <span class="verde-destaque">${sb:,.4f}</span> |
                OKX: <span class="verde-destaque">${so:,.4f}</span>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("✅ Corrigir / Atualizar Saldo Real Agora (Final)"):
        st.session_state.rodando_auto = False
        st.session_state.saldo_real = corrigir_saldo_real_final()
    if st.session_state.saldo_real.get("erro"):
        st.error(st.session_state.saldo_real["erro"])

with c2:
    ultimo = (st.session_state.ultimo_scan_motor or {}).get("dados") or {}
    sp_atual = float(ultimo.get("spread_liq_pct", 0.0)) if ultimo else 0.0
    st.markdown(
        f"""
        <div class="card-verde">
            <p class="rotulo-verde">CONTAGEM DAS OPERAÇÕES E MOTOR VWAP</p>
            <div class="numero-grande">{st.session_state.contagem_ops} OPS</div>
            <p class="linha-grande">
                Lucro: <span class="verde-destaque">{st.session_state.lucro:+.4f} USDT</span> |
                Spread Liq.: <span class="verde-destaque">{sp_atual:+.4f}%</span>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")
p1, p2, p3, p4, p5 = st.columns([1.1, 1.3, 1.0, 1.2, 1.2])
with p1:
    par = st.selectbox("Par", ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
with p2:
    rota = st.selectbox("Rota", ["Binance -> OKX", "OKX -> Binance"])
with p3:
    lote = st.number_input("Lote (USDT)", min_value=1.0, max_value=LOTE_MAX, value=10.0, step=0.5)
with p4:
    st.write("")
    if st.session_state.rodando_auto:
        if st.button("⏸️ Pausar Auto", use_container_width=True):
            st.session_state.rodando_auto = False
            st.rerun()
    else:
        if st.button("▶️ Retomar Auto", use_container_width=True):
            if not modo.startswith("💰") or real_liberado:
                st.session_state.rodando_auto = True
                st.rerun()
with p5:
    st.write("")
    if st.button("♻️ Resetar e Rodar", use_container_width=True):
        st.session_state.entradas = 200
        st.session_state.contagem_ops = 0
        st.session_state.lucro = 0.0
        st.session_state.operacoes = []
        st.session_state.aviso = None
        st.session_state.ultimo_scan_motor = None
        st.session_state.rodando_auto = True
        st.rerun()

if st.session_state.aviso:
    t, m = st.session_state.aviso
    if t == "ok":
        st.success(m)
    else:
        st.error(m)

st.subheader(f"🧾 Operações Realizadas ({st.session_state.contagem_ops})")
if st.session_state.operacoes:
    st.dataframe(pd.DataFrame(st.session_state.operacoes), use_container_width=True)
else:
    st.info("Iniciando operações automáticas...")

pode_rodar_real = modo.startswith("💰") and real_liberado
if st.session_state.rodando_auto and (not modo.startswith("💰") or pode_rodar_real):
    ok_op, msg_op = executar_passo(par, rota, float(lote), pode_rodar_real, simular_sem_spread)
    st.session_state.aviso = ("ok" if ok_op else "err", msg_op)
    time.sleep(INTERVALO_SCAN_SEG)
    st.rerun()
