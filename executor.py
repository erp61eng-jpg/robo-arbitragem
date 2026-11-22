import csv
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ConfigRisco:
    # SEGURANÇA: Nunca altere dry_run para False sem testar exaustivamente
    # e sem configurar chaves de API SEM permissão de saque.
    dry_run: bool = True
    confirmacao_live_explicita: str = "DESATIVADO"  # Só libera real se == "LIBERAR_LIVE_COM_RISCO"

    capital_referencia_usdt: float = 180.0   # ~R$ 1.000,00
    lote_minimo_usdt: float = 15.0           # Mínimo operacional da corretora
    lote_maximo_usdt: float = 90.0           # Máx 50% do capital por giro
    perda_maxima_sessao_usdt: float = 5.40   # Stop-loss: 3% de 180 USDT (~R$ 30)
    gatilho_spread_liq_pct: float = 0.05     # Margem líquida mínima após todos os custos
    max_ordens_sessao: int = 30              # Limite de disparos por sessão

    taxa_ponta_pct: float = 0.10             # Taxa por ponta (0,10% entrada + 0,10% saída)
    slippage_total_pct: float = 0.05         # Slippage estimado total
    taxa_transferencia_usdt: float = 0.00    # Custo fixo de movimentação se aplicável


@dataclass
class ResultadoExecucao:
    timestamp: str
    modo: str
    ativo: str
    rota: str
    lote_usdt: float
    spread_bruto_pct: float
    custos_totais_usdt: float
    spread_liquido_pct: float
    lucro_liquido_est_usdt: float
    decisao: str          # EXECUTADO_DRY_RUN | EXECUTADO_LIVE | BLOQUEADO
    motivo: str


class ExecutorArbitragem:
    def __init__(
        self,
        config: Optional[ConfigRisco] = None,
        pasta_logs: str = "logs",
        cliente_corretora=None,
    ):
        self.cfg = config or ConfigRisco()
        self.cliente = cliente_corretora
        self.pasta_logs = Path(pasta_logs)
        self.pasta_logs.mkdir(parents=True, exist_ok=True)

        self.arquivo_csv = self.pasta_logs / "execucoes_auditoria.csv"
        self.arquivo_estado = self.pasta_logs / "estado_executor.json"

        self.pnl_acumulado_usdt: float = 0.0
        self.custos_acumulados_usdt: float = 0.0
        self.ordens_executadas: int = 0
        self.travado_por_risco: bool = False
        self.motivo_trava: str = ""

        self._carregar_estado()
        self._garantir_cabecalho_csv()

    def _garantir_cabecalho_csv(self):
        if not self.arquivo_csv.exists():
            with open(self.arquivo_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "modo", "ativo", "rota", "lote_usdt",
                    "spread_bruto_pct", "custos_totais_usdt", "spread_liquido_pct",
                    "lucro_liquido_est_usdt", "decisao", "motivo"
                ])

    def _carregar_estado(self):
        if self.arquivo_estado.exists():
            try:
                dados = json.loads(self.arquivo_estado.read_text(encoding="utf-8"))
                self.pnl_acumulado_usdt = float(dados.get("pnl_acumulado_usdt", 0.0))
                self.custos_acumulados_usdt = float(dados.get("custos_acumulados_usdt", 0.0))
                self.ordens_executadas = int(dados.get("ordens_executadas", 0))
                self.travado_por_risco = bool(dados.get("travado_por_risco", False))
                self.motivo_trava = str(dados.get("motivo_trava", ""))
            except Exception:
                pass

    def _salvar_estado(self):
        payload = {
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
            "dry_run": self.cfg.dry_run,
            "pnl_acumulado_usdt": round(self.pnl_acumulado_usdt, 4),
            "custos_acumulados_usdt": round(self.custos_acumulados_usdt, 4),
            "ordens_executadas": self.ordens_executadas,
            "travado_por_risco": self.travado_por_risco,
            "motivo_trava": self.motivo_trava,
        }
        self.arquivo_estado.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def resetar_sessao(self):
        self.pnl_acumulado_usdt = 0.0
        self.custos_acumulados_usdt = 0.0
        self.ordens_executadas = 0
        self.travado_por_risco = False
        self.motivo_trava = ""
        self._salvar_estado()

    def calcular_viabilidade(self, lote_usdt: float, spread_bruto_pct: float) -> tuple[float, float, float]:
        custo_variavel_pct = (self.cfg.taxa_ponta_pct * 2.0) + self.cfg.slippage_total_pct
        ganho_bruto_usdt = lote_usdt * (spread_bruto_pct / 100.0)
        custos_totais_usdt = (lote_usdt * (custo_variavel_pct / 100.0)) + self.cfg.taxa_transferencia_usdt
        lucro_liquido_usdt = ganho_bruto_usdt - custos_totais_usdt
        spread_liquido_pct = (lucro_liquido_usdt / lote_usdt * 100.0) if lote_usdt > 0 else 0.0
        return round(custos_totais_usdt, 4), round(spread_liquido_pct, 4), round(lucro_liquido_usdt, 4)

    def _registrar_log(self, res: ResultadoExecucao):
        with open(self.arquivo_csv, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                res.timestamp, res.modo, res.ativo, res.rota, res.lote_usdt,
                res.spread_bruto_pct, res.custos_totais_usdt, res.spread_liquido_pct,
                res.lucro_liquido_est_usdt, res.decisao, res.motivo
            ])

    def _pode_operar_live(self) -> tuple[bool, str]:
        if self.cfg.dry_run:
            return False, "Modo DRY_RUN ativo por padrão."
        if self.cfg.confirmacao_live_explicita != "LIBERAR_LIVE_COM_RISCO":
            return False, "Frase de confirmação LIVE ausente ou incorreta."
        if os.getenv("ROBO_ARBITRAGEM_ALLOW_LIVE", "0") != "1":
            return False, "Variável de ambiente ROBO_ARBITRAGEM_ALLOW_LIVE!=1."
        if self.cliente is None:
            return False, "Cliente da corretora não injetado."
        return True, "OK"

    def avaliar_e_executar(
        self,
        ativo: str,
        rota: str,
        lote_usdt: float,
        spread_bruto_pct: float,
        saldo_disponivel_usdt: float,
    ) -> ResultadoExecucao:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        modo_atual = "DRY_RUN" if self.cfg.dry_run else "LIVE"
        custos_usdt, sp_liq_pct, lucro_liq_usdt = self.calcular_viabilidade(lote_usdt, spread_bruto_pct)

        def bloquear(motivo: str) -> ResultadoExecucao:
            res = ResultadoExecucao(
                timestamp=agora,
                modo=modo_atual,
                ativo=ativo,
                rota=rota,
                lote_usdt=lote_usdt,
                spread_bruto_pct=spread_bruto_pct,
                custos_totais_usdt=custos_usdt,
                spread_liquido_pct=sp_liq_pct,
                lucro_liquido_est_usdt=lucro_liq_usdt,
                decisao="BLOQUEADO",
                motivo=motivo,
            )
            self._registrar_log(res)
            self._salvar_estado()
            return res

        # 1. Trava de Circuit Breaker (Stop-Loss da Sessão)
        if self.travado_por_risco:
            return bloquear(f"CIRCUIT BREAKER ATIVO: {self.motivo_trava}")

        if self.pnl_acumulado_usdt <= -abs(self.cfg.perda_maxima_sessao_usdt):
            self.travado_por_risco = True
            self.motivo_trava = f"Perda máxima atingida ({self.pnl_acumulado_usdt:.4f} USDT)"
            return bloquear(self.motivo_trava)

        # 2. Limite de ordens por sessão
        if self.ordens_executadas >= self.cfg.max_ordens_sessao:
            return bloquear(f"Limite máximo de {self.cfg.max_ordens_sessao} ordens atingido na sessão.")

        # 3. Validação de Lote e Saldo Disponível
        if lote_usdt < self.cfg.lote_minimo_usdt:
            return bloquear(f"Lote {lote_usdt} abaixo do mínimo ({self.cfg.lote_minimo_usdt} USDT).")
        if lote_usdt > self.cfg.lote_maximo_usdt:
            return bloquear(f"Lote {lote_usdt} acima do teto de risco ({self.cfg.lote_maximo_usdt} USDT).")
        if lote_usdt > saldo_disponivel_usdt:
            return bloquear(f"Saldo insuficiente ({saldo_disponivel_usdt:.2f} USDT) para lote {lote_usdt:.2f}.")

        # 4. Filtro Rigoroso de Custos e Gatilho Líquido
        if lucro_liq_usdt <= 0:
            return bloquear(f"Spread bruto ({spread_bruto_pct:.4f}%) não cobre custos (-
