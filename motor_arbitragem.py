import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from motor_dados import MotorDados


@dataclass
class ResultadoVWAP:
    viavel: bool
    vwap: float
    qtd_acumulada: float
    valor_usdt_acumulado: float
    niveis_consumidos: int
    motivo: str = ""


@dataclass
class AvaliacaoRota:
    aprovada: bool
    rota: str
    lucro_liquido_pct: float
    lucro_liquido_usdt: float
    vwap_compra: float
    vwap_venda: float
    motivo: str


def calcular_vwap_profundidade(
    niveis: List[Any],
    lote_usdt: float,
    lado: str,
) -> ResultadoVWAP:
    """
    Calcula o VWAP necessário para consumir 'lote_usdt' no order book.
    lado='compra' consome 'asks' (menor preço -> maior).
    lado='venda' consome 'bids' (maior preço -> menor).
    """
    if lote_usdt <= 0:
        return ResultadoVWAP(False, 0.0, 0.0, 0.0, 0, "lote_usdt inválido")

    if not niveis:
        return ResultadoVWAP(False, 0.0, 0.0, 0.0, 0, "order book vazio")

    niveis_validos = []
    for item in niveis:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            preco = float(item[0])
            qtd = float(item[1])
            if preco > 0 and qtd > 0:
                niveis_validos.append((preco, qtd))

    if not niveis_validos:
        return ResultadoVWAP(False, 0.0, 0.0, 0.0, 0, "sem níveis válidos no livro")

    lado_norm = lado.lower().strip()
    if lado_norm == "compra":
        niveis_ordenados = sorted(niveis_validos, key=lambda x: x[0])
    elif lado_norm == "venda":
        niveis_ordenados = sorted(niveis_validos, key=lambda x: x[0], reverse=True)
    else:
        return ResultadoVWAP(False, 0.0, 0.0, 0.0, 0, "lado inválido")

    usdt_restante = float(lote_usdt)
    usdt_consumido = 0.0
    qtd_consumida = 0.0
    niveis_usados = 0

    for preco, qtd_disponivel in niveis_ordenados:
        niveis_usados += 1
        valor_nivel_usdt = preco * qtd_disponivel

        if valor_nivel_usdt >= usdt_restante:
            qtd_necessaria = usdt_restante / preco
            usdt_consumido += usdt_restante
            qtd_consumida += qtd_necessaria
            usdt_restante = 0.0
            break

        usdt_consumido += valor_nivel_usdt
        qtd_consumida += qtd_disponivel
        usdt_restante -= valor_nivel_usdt

    if usdt_restante > 1e-9 or qtd_consumida <= 0:
        return ResultadoVWAP(
            False,
            0.0,
            qtd_consumida,
            usdt_consumido,
            niveis_usados,
            "liquidez insuficiente no order book para o lote",
        )

    return ResultadoVWAP(
        True,
        usdt_consumido / qtd_consumida,
        qtd_consumida,
        usdt_consumido,
        niveis_usados,
        "ok",
    )


def _avaliar_sentido(
    rota: str,
    book_compra: Optional[Dict[str, Any]],
    book_venda: Optional[Dict[str, Any]],
    lote_usdt: float,
    taxa_compra: float,
    taxa_venda: float,
    margem_minima_pct: float,
) -> AvaliacaoRota:
    if not book_compra or not book_venda:
        return AvaliacaoRota(False, rota, 0.0, 0.0, 0.0, 0.0, "order book indisponível")

    res_compra = calcular_vwap_profundidade(book_compra.get("asks", []), lote_usdt, "compra")
    if not res_compra.viavel:
        return AvaliacaoRota(False, rota, 0.0, 0.0, 0.0, 0.0, f"compra: {res_compra.motivo}")

    res_venda = calcular_vwap_profundidade(book_venda.get("bids", []), lote_usdt, "venda")
    if not res_venda.viavel:
        return AvaliacaoRota(
            False, rota, 0.0, 0.0, res_compra.vwap, 0.0, f"venda: {res_venda.motivo}"
        )

    custo_efetivo = res_compra.vwap * (1.0 + taxa_compra)
    receita_liquida = res_venda.vwap * (1.0 - taxa_venda)

    if custo_efetivo <= 0:
        return AvaliacaoRota(
            False, rota, 0.0, 0.0, res_compra.vwap, res_venda.vwap, "custo efetivo inválido"
        )

    lucro_pct = ((receita_liquida - custo_efetivo) / custo_efetivo) * 100.0
    lucro_usdt = lote_usdt * (lucro_pct / 100.0)

    if lucro_pct < margem_minima_pct:
        return AvaliacaoRota(
            False,
            rota,
            lucro_pct,
            lucro_usdt,
            res_compra.vwap,
            res_venda.vwap,
            f"lucro líquido {lucro_pct:.4f}% menor que mínimo {margem_minima_pct:.4f}%",
        )

    return AvaliacaoRota(
        True,
        rota,
        lucro_pct,
        lucro_usdt,
        res_compra.vwap,
        res_venda.vwap,
        "aprovada",
    )


class MotorArbitragem:
    def __init__(
        self,
        motor_dados: Optional[MotorDados] = None,
        taxa_binance: float = 0.001,
        taxa_okx: float = 0.001,
        margem_minima_pct: float = 0.05,
    ):
        self.dados = motor_dados or MotorDados()
        self._dono_dados = motor_dados is None
        self.taxa_binance = float(taxa_binance)
        self.taxa_okx = float(taxa_venda if False else taxa_okx)
        self.margem_minima_pct = float(margem_minima_pct)

    async def fechar(self):
        if self._dono_dados and hasattr(self.dados, "fechar"):
            await self.dados.fechar()

    async def avaliar_par_async(
        self,
        par: str,
        lote_usdt: float = 40.5,
        margem_minima_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        margem = self.margem_minima_pct if margem_minima_pct is None else float(margem_minima_pct)

        ex_binance = self.dados.exchanges_spot.get("binance")
        ex_okx = self.dados.exchanges_spot.get("okx")

        if ex_binance is None or ex_okx is None:
            return {
                "par": par,
                "executar": False,
                "rota": "",
                "lucro_liquido_pct": 0.0,
                "lucro_liquido_usdt": 0.0,
                "vwap_compra": 0.0,
                "vwap_venda": 0.0,
                "motivo": "exchanges spot binance/okx não inicializadas em MotorDados",
            }

        book_b, book_o = await asyncio.gather(
            self.dados._book(ex_binance, par),
            self.dados._book(ex_okx, par),
        )

        r1 = _avaliar_sentido(
            rota="Binance -> OKX",
            book_compra=book_b,
            book_venda=book_o,
            lote_usdt=lote_usdt,
            taxa_compra=self.taxa_binance,
            taxa_venda=self.taxa_okx,
            margem_minima_pct=margem,
        )
        r2 = _avaliar_sentido(
            rota="OKX -> Binance",
            book_compra=book_o,
            book_venda=book_b,
            lote_usdt=lote_usdt,
            taxa_compra=self.taxa_okx,
            taxa_venda=self.taxa_binance,
            margem_minima_pct=margem,
        )

        aprovadas = [r for r in (r1, r2) if r.aprovada]
        if aprovadas:
            melhor = max(aprovadas, key=lambda x: x.lucro_liquido_pct)
            return {
                "par": par,
                "executar": True,
                "rota": melhor.rota,
                "lucro_liquido_pct": round(melhor.lucro_liquido_pct, 5),
                "lucro_liquido_usdt": round(melhor.lucro_liquido_usdt, 5),
                "vwap_compra": melhor.vwap_compra,
                "vwap_venda": melhor.vwap_venda,
                "motivo": melhor.motivo,
            }

        melhor_neg = max((r1, r2), key=lambda x: x.lucro_liquido_pct)
        return {
            "par": par,
            "executar": False,
            "rota": melhor_neg.rota,
            "lucro_liquido_pct": round(melhor_neg.lucro_liquido_pct, 5),
            "lucro_liquido_usdt": round(melhor_neg.lucro_liquido_usdt, 5),
            "vwap_compra": melhor_neg.vwap_compra,
            "vwap_venda": melhor_neg.vwap_venda,
            "motivo": f"sem oportunidade viável ({melhor_neg.motivo})",
        }

    def avaliar_par(
        self,
        par: str,
        lote_usdt: float = 40.5,
        margem_minima_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Wrapper síncrono para uso direto em scripts ou painel Streamlit."""
        return asyncio.run(
            self.avaliar_par_async(par=par, lote_usdt=lote_usdt, margem_minima_pct=margem_minima_pct)
        )
