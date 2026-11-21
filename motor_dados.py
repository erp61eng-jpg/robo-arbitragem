import time
import aiohttp


class ControleRateLimit:
    def __init__(self, pausa_base: float = 10.0, pausa_maxima: float = 120.0):
        self.pausa_base = pausa_base
        self.pausa_maxima = pausa_maxima
        self.tentativas_bloqueio = 0
        self.bloqueado_ate = 0.0

    def pode_chamar(self) -> tuple[bool, float]:
        agora = time.monotonic()
        if agora < self.bloqueado_ate:
            restante = round(self.bloqueado_ate - agora, 1)
            return False, restante
        return True, 0.0

    def registrar_limite(self, retry_after: float | None = None):
        self.tentativas_bloqueio += 1
        if retry_after and retry_after > 0:
            espera = min(retry_after, self.pausa_maxima)
        else:
            # Pausa dobra a cada bloqueio consecutivo: 10s, 20s, 40s, 80s...
            espera = min(self.pausa_base * (2 ** (self.tentativas_bloqueio - 1)), self.pausa_maxima)
        self.bloqueado_ate = time.monotonic() + espera
        return espera

    def registrar_sucesso(self):
        self.tentativas_bloqueio = 0
        self.bloqueado_ate = 0.0


async def buscar_json_com_pausa(session: aiohttp.ClientSession, url: str, limiter: ControleRateLimit):
    permitido, restante = limiter.pode_chamar()
    if not permitido:
        return {"status": "pausado", "restante_seg": restante, "dados": None}

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status in (429, 418):
                retry_hdr = resp.headers.get("Retry-After")
                retry_val = float(retry_hdr) if retry_hdr and retry_hdr.isdigit() else None
                espera = limiter.registrar_limite(retry_val)
                return {"status": "rate_limit", "espera_seg": espera, "dados": None}

            resp.raise_for_status()
            dados = await resp.json()
            limiter.registrar_sucesso()
            return {"status": "ok", "espera_seg": 0.0, "dados": dados}

    except aiohttp.ClientError as exc:
        espera = limiter.registrar_limite()
        return {"status": "erro_rede", "espera_seg": espera, "erro": str(exc), "dados": None}
