import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ccxt


def carregar_env_local(caminho_env: str | Path | None = None) -> dict[str, str]:
    """Carrega variaveis de um arquivo .env local."""
    if caminho_env:
        alvo = Path(caminho_env)
    else:
        candidato_modulo = Path(__file__).resolve().parent / ".env"
        candidato_cwd = Path.cwd() / ".env"
        alvo = candidato_modulo if candidato_modulo.exists() else candidato_cwd

    carregadas: dict[str, str] = {}
    if not alvo.exists():
        return carregadas

    for linha_bruta in alvo.read_text(encoding="utf-8-sig").splitlines():
        linha = linha_bruta.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip().lstrip("\ufeff")
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in ("'", '"'):
            valor = valor[1:-1].strip()
        if chave:
            if os.getenv(chave) is None or os.getenv(chave, "").strip() == "":
                os.environ[chave] = valor
            carregadas[chave] = os.environ.get(chave, valor)
    return carregadas


def _saldo_livre_seguro(exchange: Any, moeda: str) -> float:
    """Retorna o saldo livre de uma moeda com seguranca para diferentes formatos do ccxt."""
    if exchange is None:
        return 0.0
    bal = exchange.fetch_balance() or {}
    free = bal.get("free") or {}
    if moeda in free and free[moeda] is not None:
        return float(free[moeda])
    dados_moeda = bal.get(moeda) or {}
    if isinstance(dados_moeda, dict) and dados_moeda.get("free") is not None:
        return float(dados_moeda["free"])
    return 0.0


@dataclass
class ValidacaoArbitragem:
    permitido: bool
    motivo: str
    ativo: str = "BTC/USDT"
    sentido: str | None = None
    corretora_compra: str | None = None
    corretora_venda: str | None = None
    preco_compra: float = 0.0
    preco_venda: float = 0.0
    preco_binance: float = 0.0
    preco_okx: float = 0.0
    spread_bruto_pct: float = 0.0
    taxas_pct: float = 0.0
    spread_liquido_pct: float = 0.0
    min_spread_liq_pct: float = 0.05
    saldo_usdt_compra: float = 0.0
    saldo_moeda_venda: float = 0.0


class ClienteBinanceOKX:
    def __init__(
        self,
        binance_api_key: str | None = None,
        binance_secret: str | None = None,
        okx_api_key: str | None = None,
        okx_secret: str | None = None,
        okx_password: str | None = None,
    ) -> None:
        env_lido = carregar_env_local()

        b_key = (
            binance_api_key
            or os.getenv("BINANCE_API_KEY")
            or os.getenv("API_KEY_BINANCE")
            or env_lido.get("BINANCE_API_KEY")
            or ""
        ).strip()
        b_sec = (
            binance_secret
            or os.getenv("BINANCE_SECRET")
            or os.getenv("BINANCE_API_SECRET")
            or os.getenv("SECRET_BINANCE")
            or env_lido.get("BINANCE_API_SECRET")
            or ""
        ).strip()

        o_key = (
            okx_api_key
            or os.getenv("OKX_API_KEY")
            or os.getenv("API_KEY_OKX")
            or env_lido.get("OKX_API_KEY")
            or ""
        ).strip()
        o_sec = (
            okx_secret
            or os.getenv("OKX_SECRET")
            or os.getenv("OKX_API_SECRET")
            or os.getenv("SECRET_OKX")
            or env_lido.get("OKX_API_SECRET")
            or ""
        ).strip()
        o_pwd = (
            okx_password
            or os.getenv("OKX_API_PASSPHRASE")
            or os.getenv("OKX_PASSWORD")
            or os.getenv("PASSPHRASE_OKX")
            or env_lido.get("OKX_API_PASSPHRASE")
            or env_lido.get("OKX_PASSWORD")
            or ""
        ).strip()

        self.binance = ccxt.binance(
            {
                "apiKey": b_key,
                "secret": b_sec,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        self.okx = ccxt.okx(
            {
                "apiKey": o_key,
                "secret": o_sec,
                "password": o_pwd,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        if o_pwd:
            self.okx.password = o_pwd

    def _garantir_mercados(self, ativo: str) -> None:
        if self.binance is None or self.okx is None:
            raise RuntimeError("Clientes ccxt da Binance e OKX nao estao inicializados.")
        self.binance.load_markets()
        self.okx.load_markets()
        if ativo not in self.binance.markets or ativo not in self.okx.markets:
            raise ValueError(f"Ativo {ativo} nao disponivel em ambos os mercados spot.")

    def _taxas_somadas_pct(self, ativo: str) -> float:
        tb = float((self.binance.market(ativo) or {}).get("taker") or 0.001)
        to = float((self.okx.market(ativo) or {}).get("taker") or 0.001)
        return (tb + to) * 100.0

    def _liquidez_topo_suficiente(self, ex: Any, lado: str, ativo: str, lote_usdt: float) -> tuple[bool, str]:
        """Confere se o livro de ofertas tem volume no topo para absorver o lote sem derrapagem severa."""
        try:
            ob = ex.fetch_order_book(ativo, limit=5) or {}
            niveis = (ob.get("asks") if lado == "buy" else ob.get("bids")) or []
            if not niveis:
                return False, "Livro de ofertas vazio."
            preco_topo = float(niveis[0][0] or 0.0)
            qtd_topo = float(niveis[0][1] or 0.0)
            if preco_topo <= 0 or qtd_topo <= 0:
                return False, "Cotacao/volume invalido no topo do livro."
            notional_topo = preco_topo * qtd_topo
            if notional_topo < lote_usdt * 1.5:
                return False, f"Liquidez baixa no topo ({notional_topo:.2f} USDT para lote de {lote_usdt:.2f} USDT)."
            return True, "OK"
        except Exception as exc:
            return False, f"Falha ao ler livro de ofertas: {exc}"

    def avaliar_oportunidade(
        self,
        ativo: str = "BTC/USDT",
        lote_usdt: float = 15.0,
        min_spread_liq_pct: float | None = None,
        slippage_buf_pct: float | None = None,
    ) -> ValidacaoArbitragem:
        self._garantir_mercados(ativo)

        live_ativo = os.getenv("ROBO_ARBITRAGEM_ALLOW_LIVE", "0").strip() == "1"
        meta_liq = (
            float(os.getenv("ROBO_ARBITRAGEM_MIN_SPREAD_LIQ_PCT", "0.05"))
            if min_spread_liq_pct is None
            else float(min_spread_liq_pct)
        )
        buf_slip = (
            float(os.getenv("ROBO_ARBITRAGEM_SLIPPAGE_BUF_PCT", "0.02"))
            if slippage_buf_pct is None
            else float(slippage_buf_pct)
        )
        limiar_exigido = meta_liq + buf_slip

        tb_ticker = self.binance.fetch_ticker(ativo) or {}
        to_ticker = self.okx.fetch_ticker(ativo) or {}

        ab = float(tb_ticker.get("ask") or tb_ticker.get("last") or 0.0)
        bb = float(tb_ticker.get("bid") or tb_ticker.get("last") or 0.0)
        ao = float(to_ticker.get("ask") or to_ticker.get("last") or 0.0)
        bo = float(to_ticker.get("bid") or to_ticker.get("last") or 0.0)
        pb = float(tb_ticker.get("last") or ab or bb or 0.0)
        po = float(to_ticker.get("last") or ao or bo or 0.0)

        if min(ab, bb, ao, bo) <= 0:
            return ValidacaoArbitragem(
                permitido=False,
                motivo="Cotacoes bid/ask invalidas.",
                ativo=ativo,
                preco_binance=pb,
                preco_okx=po,
                min_spread_liq_pct=limiar_exigido,
            )

        if (bo - ab) >= (bb - ao):
            sentido = "Binance->OKX"
            corretora_compra, corretora_venda = "Binance", "OKX"
            ex_compra, ex_venda = self.binance, self.okx
            pc, pv = ab, bo
        else:
            sentido = "OKX->Binance"
            corretora_compra, corretora_venda = "OKX", "Binance"
            ex_compra, ex_venda = self.okx, self.binance
            pc, pv = ao, bb

        taxas_pct = self._taxas_somadas_pct(ativo)
        spread_bruto_pct = ((pv - pc) / pc) * 100.0
        spread_liquido_pct = spread_bruto_pct - taxas_pct

        moeda_base = ativo.split("/")[0]
        saldo_usdt = _saldo_livre_seguro(ex_compra, "USDT")
        saldo_base = _saldo_livre_seguro(ex_venda, moeda_base)

        mercado_compra = ex_compra.market(ativo) or {}
        mercado_venda = ex_venda.market(ativo) or {}
        min_cost_compra = float(((mercado_compra.get("limits") or {}).get("cost") or {}).get("min") or 5.0)
        min_amount_venda = float(((mercado_venda.get("limits") or {}).get("amount") or {}).get("min") or 0.00001)

        qtd_estimada = lote_usdt / pc if pc > 0 else 0.0
        qtd_minima_venda = max(qtd_estimada, min_amount_venda)

        base_kwargs = dict(
            ativo=ativo,
            sentido=sentido,
            corretora_compra=corretora_compra,
            corretora_venda=corretora_venda,
            preco_compra=pc,
            preco_venda=pv,
            preco_binance=pb,
            preco_okx=po,
            spread_bruto_pct=spread_bruto_pct,
            taxas_pct=taxas_pct,
            spread_liquido_pct=spread_liquido_pct,
            min_spread_liq_pct=limiar_exigido,
            saldo_usdt_compra=saldo_usdt,
            saldo_moeda_venda=saldo_base,
        )

        if spread_liquido_pct <= 0:
            return ValidacaoArbitragem(
                permitido=False,
                motivo=f"Sem lucro apos taxas (spread liquido {spread_liquido_pct:+.4f}%).",
                **base_kwargs,
            )

        if spread_liquido_pct < limiar_exigido:
            return ValidacaoArbitragem(
                permitido=False,
                motivo=f"Spread liquido ({spread_liquido_pct:+.4f}%) abaixo do minimo exigido ({limiar_exigido:+.4f}%).",
                **base_kwargs,
            )

        if lote_usdt < min_cost_compra:
            return ValidacaoArbitragem(
                permitido=False,
                motivo=f"Lote ({lote_usdt:.2f} USDT) abaixo do custo minimo ({min_cost_compra:.2f} USDT) em {corretora_compra}.",
                **base_kwargs,
            )

        if saldo_usdt < lote_usdt:
            return ValidacaoArbitragem(
                permitido=False,
                motivo=f"Saldo USDT insuficiente em {corretora_compra}: livre {saldo_usdt:.4f}, necessario {lote_usdt:.4f}.",
                **base_kwargs,
            )

        if saldo_base < qtd_minima_venda:
            return ValidacaoArbitragem(
                permitido=False,
                motivo=f"Saldo {moeda_base} insuficiente em {corretora_venda}: livre {saldo_base:.8f}, necessario {qtd_minima_venda:.8f}.",
                **base_kwargs,
            )

        liq_c_ok, liq_c_msg = self._liquidez_topo_suficiente(ex_compra, "buy", ativo, lote_usdt)
        if not liq_c_ok:
            return ValidacaoArbitragem(
                permitido=False,
                motivo=f"Compra em {corretora_compra}: {liq_c_msg}",
                **base_kwargs,
            )

        liq_v_ok, liq_v_msg = self._liquidez_topo_suficiente(ex_venda, "sell", ativo, lote_usdt)
        if not liq_v_ok:
            return ValidacaoArbitragem(
                permitido=False,
                motivo=f"Venda em {corretora_venda}: {liq_v_msg}",
                **base_kwargs,
            )

        if not live_ativo:
            return ValidacaoArbitragem(
                permitido=False,
                motivo="Lucro e liquidez ok, mas ROBO_ARBITRAGEM_ALLOW_LIVE != 1 (modo bloqueado).",
                **base_kwargs,
            )

        return ValidacaoArbitragem(
            permitido=True,
            motivo="Aprovado para execucao real (lucro, saldo e liquidez validados).",
            **base_kwargs,
        )

    def executar_par_arbitragem(
        self,
        ativo: str = "BTC/USDT",
        rota: str = "OKX->Binance",
        lote: float = 15.0,
        min_spread_liq_pct: float | None = None,
        slippage_buf_pct: float | None = None,
    ) -> dict[str, Any]:
        self._garantir_mercados(ativo)

        if os.getenv("ROBO_ARBITRAGEM_ALLOW_LIVE", "0").strip() != "1":
            raise RuntimeError("Execucao real bloqueada: defina ROBO_ARBITRAGEM_ALLOW_LIVE=1 para enviar ordens reais.")

        av = self.avaliar_oportunidade(
            ativo=ativo,
            lote_usdt=lote,
            min_spread_liq_pct=min_spread_liq_pct,
            slippage_buf_pct=slippage_buf_pct,
        )
        if not av.permitido:
            raise RuntimeError(f"Operacao recusada por seguranca: {av.motivo}")

        rl = rota.replace(" ", "")
        if rl in ("Binance->OKX", "BINANCE_TO_OKX"):
            ec, ev, pc, pv, nc, nv = self.binance, self.okx, av.preco_compra, av.preco_venda, "Binance", "OKX"
        elif rl in ("OKX->Binance", "OKX_TO_BINANCE"):
            ec, ev, pc, pv, nc, nv = self.okx, self.binance, av.preco_compra, av.preco_venda, "OKX", "Binance"
        else:
            ec, ev, pc, pv, nc, nv = (
                (self.binance, self.okx, av.preco_compra, av.preco_venda, "Binance", "OKX")
                if av.sentido == "Binance->OKX"
                else (self.okx, self.binance, av.preco_compra, av.preco_venda, "OKX", "Binance")
            )

        q = float(ec.amount_to_precision(ativo, lote / pc))
        qv = float(ev.amount_to_precision(ativo, q))
        if q <= 0 or qv <= 0:
            raise ValueError("Quantidade zerada apos arredondamento.")

        oc = ec.create_order(ativo, "market", "buy", q)
        ov = ev.create_order(ativo, "market", "sell", qv)
        return {
            "ok": True,
            "modo": "REAL",
            "ativo": ativo,
            "rota": av.sentido or rota,
            "lote_usdt": lote,
            "spread_pct": round(av.spread_bruto_pct, 4),
            "spread_liquido_pct": round(av.spread_liquido_pct, 4),
            "lucro_liq_est_usdt": round(lote * (av.spread_liquido_pct / 100.0), 5),
            "qtd_compra": q,
            "qtd_venda": qv,
            "ordem_compra_id": oc.get("id"),
            "ordem_venda_id": ov.get("id"),
            "compra_em": nc,
            "venda_em": nv,
        }


def varrer_oportunidades_usdt(
    cli: ClienteBinanceOKX,
    pares: list[str] | tuple[str, ...] | None = None,
    lote_usdt: float = 15.0,
    min_spread_liq_pct: float | None = None,
    slippage_buf_pct: float | None = None,
    apenas_aprovados: bool = False,
) -> list[dict[str, Any]]:
    """Varre multiplos pares USDT na Binance e OKX mostrando rentabilidade apos taxas."""
    cli._garantir_mercados("BTC/USDT")
    mercados_comuns = sorted(
        s for s, m in (cli.binance.markets or {}).items()
        if s.endswith("/USDT")
        and m.get("spot")
        and s in (cli.okx.markets or {})
        and (cli.okx.markets or {}).get(s, {}).get("spot")
    )

    if pares is None:
        candidatos = mercados_comuns
    else:
        candidatos = [p.strip().upper() for p in pares if p and p.strip()]
        candidatos = [p for p in candidatos if p in mercados_comuns]

    resultados: list[dict[str, Any]] = []
    for par in candidatos:
        try:
            av = cli.avaliar_oportunidade(
                ativo=par,
                lote_usdt=lote_usdt,
                min_spread_liq_pct=min_spread_liq_pct,
                slippage_buf_pct=slippage_buf_pct,
            )
            if apenas_aprovados and not av.permitido:
                continue
            lucro_est_usdt = lote_usdt * (av.spread_liquido_pct / 100.0)
            resultados.append(
                {
                    "ativo": av.ativo,
                    "sentido": av.sentido,
                    "spread_bruto_pct": round(av.spread_bruto_pct, 4),
                    "taxas_pct": round(av.taxas_pct, 4),
                    "spread_liquido_pct": round(av.spread_liquido_pct, 4),
                    "lucro_liq_est_usdt": round(lucro_est_usdt, 5),
                    "saldo_usdt_compra": round(av.saldo_usdt_compra, 4),
                    "saldo_moeda_venda": round(av.saldo_moeda_venda, 8),
                    "permitido": av.permitido,
                    "motivo": av.motivo,
                }
            )
        except Exception as exc:
            resultados.append(
                {
                    "ativo": par,
                    "sentido": None,
                    "spread_bruto_pct": 0.0,
                    "taxas_pct": 0.0,
                    "spread_liquido_pct": -999.0,
                    "lucro_liq_est_usdt": 0.0,
                    "saldo_usdt_compra": 0.0,
                    "saldo_moeda_venda": 0.0,
                    "permitido": False,
                    "motivo": f"Erro na leitura: {exc}",
                }
            )

    resultados.sort(key=lambda item: item["spread_liquido_pct"], reverse=True)
    return resultados


def validar_execucao_arbitragem_btc(
    cli: ClienteBinanceOKX,
    valor_usdt_ordem: float = 15.0,
    min_spread_liq_pct: float | None = None,
    slippage_buf_pct: float | None = None,
) -> ValidacaoArbitragem:
    return cli.avaliar_oportunidade(
        ativo="BTC/USDT",
        lote_usdt=valor_usdt_ordem,
        min_spread_liq_pct=min_spread_liq_pct,
        slippage_buf_pct=slippage_buf_pct,
    )
