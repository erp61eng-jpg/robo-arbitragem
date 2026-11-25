import os
import time
import ccxt


def _env(nome: str, padrao: str = "") -> str:
    return (os.getenv(nome) or padrao).strip()


class CorretoraCliente:
    def __init__(self):
        self.binance = ccxt.binance(
            {
                "apiKey": _env("BINANCE_API_KEY"),
                "secret": _env("BINANCE_API_SECRET"),
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        okx_cfg = {
            "apiKey": _env("OKX_API_KEY"),
            "secret": _env("OKX_API_SECRET"),
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        passphrase = _env("OKX_PASSPHRASE")
        if passphrase:
            okx_cfg["password"] = passphrase
        self.okx = ccxt.okx(okx_cfg)

    def _saldo_livre(self, exchange, moeda: str) -> float:
        bal = exchange.fetch_balance()
        moeda_u = moeda.upper()
        info_moeda = bal.get(moeda_u)
        if isinstance(info_moeda, dict) and info_moeda.get("free") is not None:
            return float(info_moeda["free"] or 0.0)
        free_dict = bal.get("free")
        if isinstance(free_dict, dict) and free_dict.get(moeda_u) is not None:
            return float(free_dict[moeda_u] or 0.0)
        return 0.0

    def consultar_saldo_usdt(self) -> dict:
        res = {"Binance": 0.0, "OKX": 0.0, "erro_binance": "", "erro_okx": ""}
        try:
            res["Binance"] = round(self._saldo_livre(self.binance, "USDT"), 4)
        except Exception as e:
            res["erro_binance"] = f"Binance: {type(e).__name__}: {e}"

        try:
            res["OKX"] = round(self._saldo_livre(self.okx, "USDT"), 4)
        except Exception as e:
            res["erro_okx"] = f"OKX: {type(e).__name__}: {e}"

        return res

    def _corretoras_da_rota(self, rota: str):
        texto = (rota or "").upper()
        if "OKX" in texto.split("->")[0]:
            return self.okx, self.binance, "OKX", "Binance"
        return self.binance, self.okx, "Binance", "OKX"

    def executar_par_arbitragem(self, ativo: str = "BTC/USDT", rota: str = "Binance -> OKX", lote_usdt: float = 10.0) -> dict:
        if os.getenv("ROBO_ARBITRAGEM_ALLOW_LIVE") != "1":
            return {"erro": "Modo REAL bloqueado: confirme o modo REAL no painel antes de enviar ordem."}

        lote = float(lote_usdt)
        if lote <= 0:
            return {"erro": "Lote em USDT deve ser maior que zero."}

        par = ativo.upper().strip()
        if "/" not in par:
            return {"erro": f"Par invalido: {ativo}"}
        moeda_base, moeda_cotacao = par.split("/", 1)
        if moeda_cotacao != "USDT":
            return {"erro": f"Apenas pares contra USDT sao suportados no momento (recebido: {par})."}

        ex_compra, ex_venda, nome_compra, nome_venda = self._corretoras_da_rota(rota)

        try:
            ex_compra.load_markets()
            ex_venda.load_markets()

            ticker_compra = ex_compra.fetch_ticker(par)
            preco_compra = float(ticker_compra.get("ask") or ticker_compra.get("last") or 0.0)
            if preco_compra <= 0:
                return {"erro": f"Preco de compra invalido em {nome_compra} para {par}."}

            qtd_moeda = float(ex_compra.amount_to_precision(par, lote / preco_compra))
            if qtd_moeda <= 0:
                return {"erro": f"Quantidade calculada zerada para {par} com lote {lote} USDT."}

            saldo_usdt_compra = self._saldo_livre(ex_compra, "USDT")
            custo_estimado_usdt = qtd_moeda * preco_compra * 1.003
            if saldo_usdt_compra < custo_estimado_usdt:
                return {
                    "erro": (
                        f"Saldo USDT insuficiente em {nome_compra}: tem {saldo_usdt_compra:.4f} USDT, "
                        f"precisa ~{custo_estimado_usdt:.4f} USDT."
                    )
                }

            saldo_base_venda = self._saldo_livre(ex_venda, moeda_base)
            if saldo_base_venda < qtd_moeda:
                return {
                    "erro": (
                        f"Saldo {moeda_base} insuficiente em {nome_venda} para vender simultaneamente: "
                        f"tem {saldo_base_venda:.6f} {moeda_base}, precisa {qtd_moeda:.6f} {moeda_base}."
                    )
                }

            ordem_compra = ex_compra.create_market_buy_order(par, qtd_moeda)
            try:
                ordem_venda = ex_venda.create_market_sell_order(par, qtd_moeda)
            except Exception as err_venda:
                # Tenta reverter a compra na ponta de origem para nao ficar exposto de um lado so
                try:
                    ex_compra.create_market_sell_order(par, qtd_moeda)
                except Exception:
                    pass
                return {
                    "erro": (
                        f"Venda falhou em {nome_venda} ({type(err_venda).__name__}: {err_venda}). "
                        f"Tentativa de reversao automatica executada em {nome_compra}."
                    )
                }

            return {
                "ok": True,
                "timestamp": int(time.time()),
                "par": par,
                "rota": f"{nome_compra} -> {nome_venda}",
                "quantidade": qtd_moeda,
                "ordem_compra_id": ordem_compra.get("id"),
                "ordem_venda_id": ordem_venda.get("id"),
            }
        except Exception as e:
            return {"erro": f"{type(e).__name__}: {e}"}
