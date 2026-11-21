import asyncio
from datetime import datetime
import aiohttp
import config


class MotorDados:
    BINANCE_DEPTH_URL = "https://api.binance.com/api/v3/depth"
    BYBIT_ORDERBOOK_URL = "https://api.bybit.com/v5/orderbook/quote"

    def __init__(
        self,
        pares: list[str] | None = None,
        taxa_total_pct: float = 0.20,
        timeout_seg: float = 6.0,
    ):
        self.pares = pares or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        self.taxa_total_pct = float(taxa_total_pct)
        self.timeout = aiohttp.ClientTimeout(total=timeout_seg)
        self._session: aiohttp.ClientSession | None = None

    async def _obter_sessao(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def fechar(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _buscar_binance_topo(self, session: aiohttp.ClientSession, par: str) -> dict | None:
        params = {"symbol": par, "limit": 5}
        async with session.get(self.BINANCE_DEPTH_URL, params=params) as resp:
            if resp.status != 200:
                return None
            dados = await resp.json()

        bids = dados.get("bids") or []
        asks = dados.get("asks") or []
        if not bids or not asks:
            return None

        melhor_bid = float(bids[0][0])
        qtd_bid = float(bids[0][1])
        melhor_ask = float(asks[0][0])
        qtd_ask = float(asks[0][1])

        return {
            "bid": melhor_bid,
            "ask": melhor_ask,
            "liq_bid_usdt": melhor_bid * qtd_bid,
            "liq_ask_usdt": melhor_ask * qtd_ask,
        }

    async def _buscar_bybit_topo(self, session: aiohttp.ClientSession, par: str) -> dict | None:
        params = {"category": "spot", "symbol": par}
        async with session.get(self.BYBIT_ORDERBOOK_URL, params=params) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json()

        result = payload.get("result") or {}
        bid_p = result.get("b") or result.get("bidPrice")
        ask_p = result.get("a") or result.get("askPrice")
        bid_q = result.get("bs") or result.get("bidSize") or 0.0
        ask_q = result.get("as") or result.get("askSize") or 0.0

        if not bid_p or not ask_p:
            return None

        melhor_bid = float(bid_p)
        melhor_ask = float(ask_p)
        liq_bid = melhor_bid * float(bid_q) if float(bid_q) > 0 else 2500.0
        liq_ask = melhor_ask * float(ask_q) if float(ask_q) > 0 else 2500.0

        return {
            "bid": melhor_bid,
            "ask": melhor_ask,
            "liq_bid_usdt": liq_bid,
            "liq_ask_usdt": liq_ask,
        }

    def _formatar_ativo(self, par: str) -> str:
        if par.endswith("USDT") and len(par) > 4:
            return f"{par[:-4]}/USDT"
        return par

    async def _avaliar_par(self, session: aiohttp.ClientSession, par: str) -> list[dict]:
        binance_task = asyncio.create_task(self._buscar_binance_topo(session, par))
        bybit_task = asyncio.create_task(self._buscar_bybit_topo(session, par))
        b_topo, y_topo = await asyncio.gather(binance_task, bybit_task, return_exceptions=True)

        if isinstance(b_topo, Exception) or not b_topo:
            return []
        if isinstance(y_topo, Exception) or not y_topo:
            return []

        hora = datetime.now().strftime("%H:%M:%S")
        ativo = self._formatar_ativo(par)
        lote = float(getattr(config, "LOTE_OPERACAO_USDT", 1000.0))
        oportunidades = []

        # Rota 1: Compra na Binance (ask) e venda na Bybit (bid)
        if b_topo["ask"] > 0 and y_topo["bid"] > 0:
            spread_bruto_1 = ((y_topo["bid"] - b_topo["ask"]) / b_topo["ask"]) * 100.0
            spread_liq_1 = spread_bruto_1 - self.taxa_total_pct
            liq_1 = min(b_topo["liq_ask_usdt"], y_topo["liq_bid_usdt"])
            oportunidades.append({
                "Hora": hora,
                "Estrategia": "Espacial (Cross-Exchange)",
                "Ativo": ativo,
                "Rota": "Binance Spot -> Bybit Spot",
                "Funding_8h_%": 0.0,
                "Spread_Bruto_%": round(spread_bruto_1, 4),
                "Spread_Liquido_%": round(spread_liq_1, 4),
                "Lucro_Est_USDT": round(lote * (spread_liq_1 / 100.0), 4),
                "Liquidez_Ponta_USDT": round(liq_1, 2),
            })

        # Rota 2: Compra na Bybit (ask) e venda na Binance (bid)
        if y_topo["ask"] > 0 and b_topo["bid"] > 0:
            spread_bruto_2 = ((b_topo["bid"] - y_topo["ask"]) / y_topo["ask"]) * 100.0
            spread_liq_2 = spread_bruto_2 - self.taxa_total_pct
            liq_2 = min(y_topo["liq_ask_usdt"], b_topo["liq_bid_usdt"])
            oportunidades.append({
                "Hora": hora,
                "Estrategia": "Espacial (Cross-Exchange)",
                "Ativo": ativo,
                "Rota": "Bybit Spot -> Binance Spot",
                "Funding_8h_%": 0.0,
                "Spread_Bruto_%": round(spread_bruto_2, 4),
                "Spread_Liquido_%": round(spread_liq_2, 4),
                "Lucro_Est_USDT": round(lote * (spread_liq_2 / 100.0), 4),
                "Liquidez_Ponta_USDT": round(liq_2, 2),
            })

        return oportunidades

    async def varrer_mercado(self) -> list[dict]:
        session = await self._obter_sessao()
        tarefas = [self._avaliar_par(session, par) for par in self.pares]
        resultados = await asyncio.gather(*tarefas, return_exceptions=True)

        linhas: list[dict] = []
        for item in resultados:
            if isinstance(item, list):
                linhas.extend(item)
        return linhas
