import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import ccxt
except Exception:
    ccxt = None


def carregar_env_local(caminho: str = ".env"):
    arquivo = Path(caminho)
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor


class ClienteBinanceOKX:
    def __init__(
        self,
        binance_api_key: Optional[str] = None,
        binance_api_secret: Optional[str] = None,
        okx_api_key: Optional[str] = None,
        okx_api_secret: Optional[str] = None,
        okx_passphrase: Optional[str] = None,
    ):
        carregar_env_local()

        self.b_key = (binance_api_key or os.getenv("BINANCE_API_KEY", "")).strip()
        self.b_secret = (binance_api_secret or os.getenv("BINANCE_API_SECRET", "")).strip()

        self.o_key = (okx_api_key or os.getenv("OKX_API_KEY", "")).strip()
        self.o_secret = (okx_api_secret or os.getenv("OKX_API_SECRET", "")).strip()
        self.o_passphrase = (okx_passphrase or os.getenv("OKX_API_PASSPHRASE", "")).strip()

        self.binance = None
        self.okx = None

        if ccxt is not None:
            if self.b_key and self.b_secret:
                self.binance = ccxt.binance({
                    "apiKey": self.b_key,
                    "secret": self.b_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                })
            if self.o_key and self.o_secret and self.o_passphrase:
                self.okx = ccxt.okx({
                    "apiKey": self.o_key,
                    "secret": self.o_secret,
                    "password": self.o_passphrase,
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                })

    def status_conexoes(self) -> Dict[str, bool]:
        return {
            "binance_configurada": self.binance is not None,
            "okx_configurada": self.okx is not None,
        }

    def consultar_saldo_usdt(self) -> Dict[str, Any]:
        resultado: Dict[str, Any] = {
            "Binance": 0.0,
            "OKX": 0.0,
            "erro_binance": "",
            "erro_okx": "",
        }

        if self.binance is not None:
            try:
                bal_b = self.binance.fetch_balance()
                resultado["Binance"] = float((bal_b.get("USDT") or {}).get("free", 0.0) or 0.0)
            except Exception as exc:
                resultado["erro_binance"] = str(exc)

        if self.okx is not None:
            try:
                bal_o = self.okx.fetch_balance()
                resultado["OKX"] = float((bal_o.get("USDT") or {}).get("free", 0.0) or 0.0)
            except Exception as exc:
                resultado["erro_okx"] = str(exc)

        return resultado

    def executar_par_arbitragem(self, ativo: str, rota: str, lote_usdt: float) -> Dict[str, Any]:
        raise RuntimeError(
            "Execucao real bloqueada neste cliente inicial: valide leitura de saldo e precos com DRY_RUN=True antes de habilitar envio de ordens."
        )


if __name__ == "__main__":
    cli = ClienteBinanceOKX()
    print("Conexoes:", cli.status_conexoes())
    print("Saldos USDT:", cli.consultar_saldo_usdt())
