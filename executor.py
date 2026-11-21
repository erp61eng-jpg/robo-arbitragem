from datetime import datetime


class ExecutorArbitragem:
    def __init__(
        self,
        modo: str = "DRY_RUN",
        lote_max_usdt: float = 1000.0,
        gatilho_pct: float = 0.05,
        liquidez_min_usdt: float = 500.0,
    ):
        self.modo = modo
        self.lote_max_usdt = float(lote_max_usdt)
        self.gatilho_pct = float(gatilho_pct)
        self.liquidez_min_usdt = float(liquidez_min_usdt)
        self.travado = False

    def executar_ordem(self, sinal: dict) -> dict:
        hora = sinal.get("Hora") or datetime.now().strftime("%H:%M:%S")
        ativo = sinal.get("Ativo", "N/A")
        estrategia = sinal.get("Estrategia", "N/A")
        rota = sinal.get("Rota", "N/A")
        spread_liq = float(sinal.get("Spread_Liquido_%", 0.0) or 0.0)
        liquidez = float(sinal.get("Liquidez_Ponta_USDT", self.lote_max_usdt * 2) or 0.0)
        lote = min(self.lote_max_usdt, float(sinal.get("Lote_USDT", self.lote_max_usdt) or self.lote_max_usdt))

        if self.travado:
            return {
                "Hora": hora,
                "Estrategia": estrategia,
                "Ativo": ativo,
                "Rota": rota,
                "Lote_USDT": lote,
                "Spread_Liquido_%": spread_liq,
                "Lucro_Liquido_USDT": 0.0,
                "status": "BLOQUEADO_TRAVA",
                "motivo": "Executor travado manualmente ou por limite",
            }

        if spread_liq < self.gatilho_pct:
            return {
                "Hora": hora,
                "Estrategia": estrategia,
                "Ativo": ativo,
                "Rota": rota,
                "Lote_USDT": lote,
                "Spread_Liquido_%": spread_liq,
                "Lucro_Liquido_USDT": 0.0,
                "status": "IGNORADO_GATILHO",
                "motivo": f"Spread líquido {spread_liq:.4f}% abaixo de {self.gatilho_pct:.4f}%",
            }

        if liquidez < self.liquidez_min_usdt:
            return {
                "Hora": hora,
                "Estrategia": estrategia,
                "Ativo": ativo,
                "Rota": rota,
                "Lote_USDT": lote,
                "Spread_Liquido_%": spread_liq,
                "Lucro_Liquido_USDT": 0.0,
                "status": "IGNORADO_LIQUIDEZ",
                "motivo": f"Liquidez {liquidez:.2f} USDT abaixo do mínimo {self.liquidez_min_usdt:.2f} USDT",
            }

        lucro_liq = round(lote * (spread_liq / 100.0), 4)
        return {
            "Hora": hora,
            "Estrategia": estrategia,
            "Ativo": ativo,
            "Rota": rota,
            "Lote_USDT": lote,
            "Spread_Liquido_%": spread_liq,
            "Lucro_Liquido_USDT": lucro_liq,
            "status": "SIMULADO_OK",
            "motivo": f"Aprovado em {self.modo}",
        }
