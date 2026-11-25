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

        if not live_ativo:
            return ValidacaoArbitragem(
                permitido=False,
                motivo="Condicoes atendidas, mas ROBO_ARBITRAGEM_ALLOW_LIVE != 1 (modo bloqueado).",
                **base_kwargs,
            )

        return ValidacaoArbitragem(
            permitido=True,
            motivo="Aprovado para execucao real.",
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

        tb = self.binance.fetch_ticker(ativo) or {}
        to = self.okx.fetch_ticker(ativo) or {}
        ab = float(tb.get("ask") or tb.get("last") or 0.0)
        bb = float(tb.get("bid") or tb.get("last") or 0.0)
        ao = float(to.get("ask") or to.get("last") or 0.0)
        bo = float(to.get("bid") or to.get("last") or 0.0)
        if min(ab, bb, ao, bo) <= 0:
            raise RuntimeError("Cotacoes bid/ask invalidas.")

        rl = rota.replace(" ", "")
        if rl in ("Binance->OKX", "BINANCE_TO_OKX"):
            ec, ev, pc, pv, nc, nv = self.binance, self.okx, ab, bo, "Binance", "OKX"
        elif rl in ("OKX->Binance", "OKX_TO_BINANCE"):
            ec, ev, pc, pv, nc, nv = self.okx, self.binance, ao, bb, "OKX", "Binance"
        else:
            raise ValueError(f"Rota desconhecida: {rota}")

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

        taxas_pct = self._taxas_somadas_pct(ativo)
        sp = ((pv - pc) / pc) * 100.0
        spread_liq_pct = sp - taxas_pct
        if spread_liq_pct < limiar_exigido:
            raise RuntimeError(
                f"Spread liquido ({spread_liq_pct:+.4f}%) abaixo do minimo exigido ({limiar_exigido:+.4f}%)."
            )

        moeda_base = ativo.split("/")[0]
        q = float(ec.amount_to_precision(ativo, lote / pc))
        qv = float(ev.amount_to_precision(ativo, q))
        if q <= 0 or qv <= 0:
            raise ValueError("Quantidade zerada apos arredondamento.")

        saldo_usdt_compra = _saldo_livre_seguro(ec, "USDT")
        saldo_base_venda = _saldo_livre_seguro(ev, moeda_base)
        if saldo_usdt_compra < lote:
            raise RuntimeError(f"Saldo USDT insuficiente em {nc}: livre {saldo_usdt_compra:.4f}, necessario {lote:.4f}.")
        if saldo_base_venda < qv:
            raise RuntimeError(f"Saldo {moeda_base} insuficiente em {nv}: livre {saldo_base_venda:.8f}, necessario {qv:.8f}.")

        oc = ec.create_order(ativo, "market", "buy", q)
        ov = ev.create_order(ativo, "market", "sell", qv)
        return {
            "ok": True,
            "modo": "REAL",
            "ativo": ativo,
            "rota": rota,
            "lote_usdt": lote,
            "spread_pct": round(sp, 4),
            "spread_liquido_pct": round(spread_liq_pct, 4),
            "qtd_compra": q,
            "qtd_venda": qv,
            "ordem_compra_id": oc.get("id"),
            "ordem_venda_id": ov.get("id"),
            "compra_em": nc,
            "venda_em": nv,
        }


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
