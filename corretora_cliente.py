import os
from dataclasses import dataclass


@dataclass
class ValidacaoArbitragem:
    permitido: bool
    motivo: str
    sentido: str | None = None
    corretora_compra: str | None = None
    corretora_venda: str | None = None
    preco_binance: float = 0.0
    preco_okx: float = 0.0
    spread_bruto_pct: float = 0.0
    taxas_pct: float = 0.0
    spread_liquido_pct: float = 0.0
    min_spread_liq_pct: float = 0.05
    saldo_usdt_compra: float = 0.0
    saldo_btc_venda: float = 0.0


def _saldo_livre_seguro(exchange, moeda: str) -> float:
    bal = exchange.fetch_balance() or {}
    free = bal.get("free") or {}
    if moeda in free and free[moeda] is not None:
        return float(free[moeda])
    dados_moeda = bal.get(moeda) or {}
    if isinstance(dados_moeda, dict) and dados_moeda.get("free") is not None:
        return float(dados_moeda["free"])
    return 0.0


def validar_execucao_arbitragem_btc(
    cli,
    valor_usdt_ordem: float = 15.0,
    min_spread_liq_pct: float | None = None,
    slippage_buf_pct: float | None = None,
) -> ValidacaoArbitragem:
    par = "BTC/USDT"
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

    cli.binance.load_markets()
    cli.okx.load_markets()

    pb = float(cli.binance.fetch_ticker(par)["last"])
    po = float(cli.okx.fetch_ticker(par)["last"])

    tb = float(cli.binance.market(par).get("taker") or 0.001)
    to = float(cli.okx.market(par).get("taker") or 0.001)
    taxas_pct = (tb + to) * 100.0

    # Se OKX > Binance: compra na Binance, vende na OKX
    # Se Binance > OKX: compra na OKX, vende na Binance
    if po >= pb:
        sentido = "Binance -> OKX"
        corretora_compra, corretora_venda = "Binance", "OKX"
        ex_compra, ex_venda = cli.binance, cli.okx
        preco_compra, preco_venda = pb, po
    else:
        sentido = "OKX -> Binance"
        corretora_compra, corretora_venda = "OKX", "Binance"
        ex_compra, ex_venda = cli.okx, cli.binance
        preco_compra, preco_venda = po, pb

    spread_bruto_pct = ((preco_venda - preco_compra) / preco_compra) * 100.0
    spread_liquido_pct = spread_bruto_pct - taxas_pct

    saldo_usdt = _saldo_livre_seguro(ex_compra, "USDT")
    saldo_btc = _saldo_livre_seguro(ex_venda, "BTC")

    qtd_btc_estimada = valor_usdt_ordem / preco_compra if preco_compra > 0 else 0.0
    mercado_venda = ex_venda.market(par)
    min_amount_venda = float((mercado_venda.get("limits") or {}).get("amount", {}).get("min") or 0.00001)
    min_cost_compra = float((ex_compra.market(par).get("limits") or {}).get("cost", {}).get("min") or 5.0)

    base = dict(
        sentido=sentido,
        corretora_compra=corretora_compra,
        corretora_venda=corretora_venda,
        preco_binance=pb,
        preco_okx=po,
        spread_bruto_pct=spread_bruto_pct,
        taxas_pct=taxas_pct,
        spread_liquido_pct=spread_liquido_pct,
        min_spread_liq_pct=limiar_exigido,
        saldo_usdt_compra=saldo_usdt,
        saldo_btc_venda=saldo_btc,
    )

    if spread_liquido_pct < limiar_exigido:
        return ValidacaoArbitragem(
            permitido=False,
            motivo=f"Spread liquido ({spread_liquido_pct:+.4f}%) abaixo do exigido ({limiar_exigido:+.4f}%).",
            **base,
        )

    if valor_usdt_ordem < min_cost_compra:
        return ValidacaoArbitragem(
            permitido=False,
            motivo=f"Valor da ordem ({valor_usdt_ordem:.2f} USDT) abaixo do minimo ({min_cost_compra:.2f} USDT) em {corretora_compra}.",
            **base,
        )

    if saldo_usdt < valor_usdt_ordem:
        return ValidacaoArbitragem(
            permitido=False,
            motivo=f"Saldo USDT insuficiente em {corretora_compra}: livre {saldo_usdt:.4f}, necessario {valor_usdt_ordem:.4f}.",
            **base,
        )

    qtd_minima_exigida = max(qtd_btc_estimada, min_amount_venda)
    if saldo_btc < qtd_minima_exigida:
        return ValidacaoArbitragem(
            permitido=False,
            motivo=f"Saldo BTC insuficiente em {corretora_venda}: livre {saldo_btc:.8f}, necessario {qtd_minima_exigida:.8f}.",
            **base,
        )

    if not live_ativo:
        return ValidacaoArbitragem(
            permitido=False,
            motivo="Condicoes atendidas, mas ROBO_ARBITRAGEM_ALLOW_LIVE != 1 (modo simulacao/bloqueado).",
            **base,
        )

    return ValidacaoArbitragem(
        permitido=True,
        motivo="Aprovado para execucao real em BTC/USDT.",
        **base,
    )
