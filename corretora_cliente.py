import os
from pathlib import Path
import ccxt


def carregar_env_local():
    """Carrega variáveis do arquivo .env na pasta do projeto se existir."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        for linha in env_path.read_text(encoding="utf-8").splitlines():
            linha_limpa = linha.strip()
            if not linha_limpa or linha_limpa.startswith("#") or "=" not in linha_limpa:
                continue
            chave, valor = linha_limpa.split("=", 1)
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if chave and chave not in os.environ:
                os.environ[chave] = valor
    except Exception:
        pass


def _obter_segredo(nome: str) -> str:
    carregar_env_local()
    val = os.getenv(nome, "")
    if val:
        return str(val).strip()
    try:
        import streamlit as st
        if hasattr(st, "secrets") and nome in st.secrets:
            return str(st.secrets[nome]).strip()
    except Exception:
        pass
    return ""


def obter_saldos_reais() -> dict:
    """Consulta o saldo em USDT na Binance e na OKX e retorna um dicionário."""
    carregar_env_local()

    binance_key = _obter_segredo("BINANCE_API_KEY")
    binance_secret = _obter_segredo("BINANCE_API_SECRET")

    okx_key = _obter_segredo("OKX_API_KEY")
    okx_secret = _obter_segredo("OKX_API_SECRET")
    okx_passphrase = _obter_segredo("OKX_API_PASSPHRASE")

    resultado = {
        "Binance": 0.0,
        "OKX": 0.0,
        "erro_binance": "",
        "erro_okx": "",
    }

    if binance_key and binance_secret:
        try:
            exchange_b = ccxt.binance(
                {
                    "apiKey": binance_key,
                    "secret": binance_secret,
                    "enableRateLimit": True,
                }
            )
            bal_b = exchange_b.fetch_balance()
            usdt_b = bal_b.get("USDT") or {}
            livre_b = usdt_b.get("free")
            total_b = usdt_b.get("total")
            if livre_b is not None:
                resultado["Binance"] = float(livre_b)
            elif total_b is not None:
                resultado["Binance"] = float(total_b)
        except Exception as exc:
            resultado["erro_binance"] = str(exc)
    else:
        resultado["erro_binance"] = "Chaves da Binance não configuradas."

    if okx_key and okx_secret and okx_passphrase:
        try:
            exchange_o = ccxt.okx(
                {
                    "apiKey": okx_key,
                    "secret": okx_secret,
                    "password": okx_passphrase,
                    "enableRateLimit": True,
                }
            )
            bal_o = exchange_o.fetch_balance()
            usdt_o = bal_o.get("USDT") or {}
            livre_o = usdt_o.get("free")
            total_o = usdt_o.get("total")
            if livre_o is not None:
                resultado["OKX"] = float(livre_o)
            elif total_o is not None:
                resultado["OKX"] = float(total_o)
        except Exception as exc:
            resultado["erro_okx"] = str(exc)
    else:
        resultado["erro_okx"] = "Chaves ou passphrase da OKX não configuradas."

    return resultado


if __name__ == "__main__":
    saldos = obter_saldos_reais()
    print("Saldos USDT:", saldos)
