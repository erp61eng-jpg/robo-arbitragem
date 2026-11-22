import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class CotacaoPar:
    ativo: str
    rota: str
    preco_ref: float
    spread_bruto_pct: float
    status: str
    mensagem: str = ""


class ControleRateLimit:
    def __init__(self, pausa_base: float = 10.0, pausa_maxima: float = 120.0):
        self.pausa_base = float(pausa_base)
        self.pausa_maxima = float(pausa_maxima)
        self.tentativas_bloqueio: int = 0
        self.bloqueado_ate: float = 0.0

    def pode_chamar(self) -> Tuple[bool, float]:
        agora = time.monotonic()
        if agora < self.bloqueado_ate:
            return False, round(self.bloqueado_ate - agora, 1)
        return True, 0.0

    def registrar_limite(self, retry_after: Optional[float] = None) -> float:
        self.tentativas_bloqueio += 1
        if retry_after is not None and retry_after > 0:
            espera = min(float(retry_after), self.pausa_maxima)
        else:
            espera = min(
                self.pausa_base * (2 ** (self.tentativas_bloqueio - 1)),
                self.pausa_maxima,
            )
        self.bloqueado_ate = time.monotonic() + espera
        return round(espera, 1)

    def registrar_sucesso(self):
        self.tentativas_bloqueio = 0
        self.bloqueado_ate = 0.0

    def status_texto(self) -> str:
        permitido, restante = self.pode_chamar()
        if permitido:
            return "Motor em modo observacao livre"
        return f"Em pausa por limite/rede ({restante:.1f}s restantes)"


class MotorDadosArbitragem:
    ATIVOS_PADRAO = [
        ("SOL/USDT", "Bybit -> Binance", 98.50, 0.24),
        ("BTC/USDT", "Binance -> Bybit", 64200.00, 0.16),
        ("ETH/USDT", "Binance Spot/Fut", 2540.00, 0.12),
        ("BNB/USDT", "BNB -> ETH -> USDT", 585.00, 0.08),
        ("XRP/USDT", "Bybit Spot/Fut", 0.5400, 0.05),
    ]

    def __init__(
        self,
        modo: str = "observacao",
        rate_limiter: Optional[ControleRateLimit] = None,
    ):
        self.modo = modo
        self.limiter = rate_limiter if rate_limiter is not None else ControleRateLimit()

    def coletar_ciclo(
        self, ativos: Optional[List[Tuple[str, str, float, float]]] = None
    ) -> List[CotacaoPar]:
        lista_ativos = ativos if ativos is not None else self.ATIVOS_PADRAO
        permitido, restante = self.limiter.pode_chamar()

        if not permitido:
            return [
                CotacaoPar(
                    ativo=ativo,
                    rota=rota,
                    preco_ref=preco_base,
                    spread_bruto_pct=0.0,
                    status="pausado",
                    mensagem=f"Aguardando fim da pausa ({restante:.1f}s)",
                )
                for ativo, rota, preco_base, _ in lista_ativos
            ]

        resultados: List[CotacaoPar] = []
        for ativo, rota, preco_base, sp_base in lista_ativos:
            preco_atual = round(preco_base * (1.0 + random.uniform(-0.004, 0.004)), 4)
            sp_bruto = round(max(0.0, sp_base + random.uniform(-0.06, 0.14)), 4)
            resultados.append(
                CotacaoPar(
                    ativo=ativo,
                    rota=rota,
                    preco_ref=preco_atual,
                    spread_bruto_pct=sp_bruto,
                    status="ok",
                    mensagem="Leitura em modo observacao",
                )
            )

        self.limiter.registrar_sucesso()
        return resultados

    def historico_inicial(
        self, lote: float, taxa_ponta: float, slippage: float, transf: float
    ) -> List[Dict]:
        custo_pct = (taxa_ponta * 2.0) + slippage
        acum_tmp = 0.0
        linhas_hist: List[Dict] = []

        for idx in range(1, 5):
            for ativo, _, _, sp_base in self.ATIVOS_PADRAO:
                sp_bruto = round(max(0.0, sp_base + (idx - 2.5) * 0.03), 4)
                bruto_usdt = lote * (sp_bruto / 100.0)
                custo_usdt = (lote * (custo_pct / 100.0)) + transf
                liq_usdt = round(bruto_usdt - custo_usdt, 4)
                sp_liq = round((liq_usdt / lote * 100.0) if lote > 0 else 0.0, 4)
                if liq_usdt > 0:
                    acum_tmp = round(acum_tmp + liq_usdt, 4)
                linhas_hist.append({
                    "Ciclo": idx,
                    "Ativo": ativo,
                    "Sp_Bruto_%": sp_bruto,
                    "Sp_Liq_%": sp_liq,
                    "Acumulado_USDT": acum_tmp,
                })

        return linhas_hist
