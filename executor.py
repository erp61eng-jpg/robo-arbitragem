import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class ConfigRisco:
    dry_run: bool = True
    confirmacao_live_explicita: str = "DESATIVADO"

    capital_referencia_usdt: float = 180.0
    lote_minimo_usdt: float = 15.0
    lote_maximo_usdt: float = 90.0
    meta_ganho_sessao_usdt: float = 15.0
    perda_maxima_sessao_usdt: float = 5.0
    gatilho_spread_liq_pct: float = 0.05
    max_ordens_sessao: int = 120
    max_ciclos_sem_oportunidade: int = 15

    taxa_ponta_pct: float = 0.10
    slippage_total_pct: float = 0.05
    taxa_transferencia_usdt: float = 0.00


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
    decisao: str
    motivo: str


class ExecutorArbitragem:
    def __init__(
        self,
        config: Optional[ConfigRisco] = None,
        pasta_logs: str = "logs",
        cliente_corretora=None,
    ):
        self.cfg = config if config is not None else ConfigRisco()
        self.cliente = cliente_corretora
        self.pasta_logs = Path(pasta_logs)
        self.pasta_logs.mkdir(parents=True, exist_ok=True)

        self.arquivo_csv = self.pasta_logs / "execucoes_auditoria.csv"
        self.arquivo_estado = self.pasta_logs / "estado_executor.json"

        self.pnl_acumulado_usdt: float = 0.0
        self.custos_acumulados_usdt: float = 0.0
        self.ordens_executadas: int = 0
        self.ciclos_sem_oportunidade: int = 0
        self.travado_por_risco: bool = False
        self.status_meta: str = "EM_ANDAMENTO"
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
                self.ciclos_sem_oportunidade = int(dados.get("ciclos_sem_oportunidade", 0))
                self.travado_por_risco = bool(dados.get("travado_por_risco", False))
                self.status_meta = str(dados.get("status_meta", "EM_ANDAMENTO"))
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
            "ciclos_sem_oportunidade": self.ciclos_sem_oportunidade,
            "travado_por_risco": self.travado_por_risco,
            "status_meta": self.status_meta,
            "motivo_trava": self.motivo_trava,
        }
        self.arquivo_estado.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def resetar_sessao(self):
        self.pnl_acumulado_usdt = 0.0
        self.custos_acumulados_usdt = 0.0
        self.ordens_executadas = 0
        self.ciclos_sem_oportunidade = 0
        self.travado_por_risco = False
        self.status_meta = "EM_ANDAMENTO"
        self.motivo_trava = ""
        self._salvar_estado()

    def registrar_ciclo_sem_oportunidade(self) -> bool:
        max_sem_op = int(getattr(self.cfg, "max_ciclos_sem_oportunidade", 15))
        self.ciclos_sem_oportunidade += 1
        if max_sem_op > 0 and self.ciclos_sem_oportunidade >= max_sem_op:
            self.travado_por_risco = True
            self.status_meta = "SEM_OPORTUNIDADE"
            self.motivo_trava = f"Parada automatica apos {self.ciclos_sem_oportunidade} ciclos sem oportunidade"
            self._salvar_estado()
            return True
        self._salvar_estado()
        return False

    def _avaliar_limites_sessao(self) -> bool:
        meta_ganho = float(getattr(self.cfg, "meta_ganho_sessao_usdt", 15.0))
        perda_max = float(getattr(self.cfg, "perda_maxima_sessao_usdt", 5.0))
        max_ordens = int(getattr(self.cfg, "max_ordens_sessao", 120))

        if perda_max > 0 and self.pnl_acumulado_usdt <= -abs(perda_max):
            self.travado_por_risco = True
            self.status_meta = "STOP_LOSS_ATINGIDO"
            self.motivo_trava = f"Limite de perda atingido ({self.pnl_acumulado_usdt:.4f} USDT)"
            return True

        if meta_ganho > 0 and self.pnl_acumulado_usdt >= abs(meta_ganho):
            self.travado_por_risco = True
            self.status_meta = "META_GANHO_ATINGIDA"
            self.motivo_trava = f"Limite de ganho atingido ({self.pnl_acumulado_usdt:.4f} USDT)"
            return True

        if max_ordens > 0 and self.ordens_executadas >= max_ordens:
            self.travado_por_risco = True
            self.status_meta = "LIMITE_ORDENS_ATINGIDO"
            self.motivo_trava = f"Limite de {max_ordens} ordens atingido na sessao"
            return True

        return False

    def calcular_lote_fechamento_dia(
        self,
        saldo_base_usdt: float,
        percentual_uso: float = 0.50,
    ) -> float:
        saldo_pos_dia = max(0.0, float(saldo_base_usdt) + float(self.pnl_acumulado_usdt))
        lote_calculado = saldo_pos_dia * float(percentual_uso)
        lote_limitado = min(lote_calculado, float(self.cfg.lote_maximo_usdt))
        return round(max(float(self.cfg.lote_minimo_usdt), lote_limitado), 2)

    def calcular_viabilidade(
        self, lote_usdt: float, spread_bruto_pct: float
    ) -> Tuple[float, float, float]:
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

    def _pode_operar_live(self) -> Tuple[bool, str]:
        if self.cfg.dry_run:
            return False, "Modo DRY_RUN ativo por padrao."
        if self.cfg.confirmacao_live_explicita != "LIBERAR_LIVE_COM_RISCO":
            return False, "Frase de confirmacao LIVE ausente ou incorreta."
        if os.getenv("ROBO_ARBITRAGEM_ALLOW_LIVE", "0") != "1":
            return False, "Variavel de ambiente ROBO_ARBITRAGEM_ALLOW_LIVE!=1."
        if self.cliente is None:
            return False, "Cliente da corretora nao injetado."
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

        if self._avaliar_limites_sessao() or self.travado_por_risco:
            return bloquear("PARADA AUTOMATICA: " + (self.motivo_trava or "Limite atingido"))

        if lote_usdt < self.cfg.lote_minimo_usdt:
            return bloquear(f"Lote {lote_usdt} abaixo do minimo ({self.cfg.lote_minimo_usdt} USDT).")
        if lote_usdt > self.cfg.lote_maximo_usdt:
            return bloquear(f"Lote {lote_usdt} acima do teto de risco ({self.cfg.lote_maximo_usdt} USDT).")
        if lote_usdt > saldo_disponivel_usdt:
            return bloquear(f"Saldo insuficiente ({saldo_disponivel_usdt:.2f} USDT) para lote {lote_usdt:.2f}.")

        if lucro_liq_usdt <= 0:
            return bloquear(f"Spread bruto ({spread_bruto_pct:.4f}%) nao cobre custos (-$ {custos_usdt:.4f}).")
        if sp_liq_pct < self.cfg.gatilho_spread_liq_pct:
            return bloquear(
                f"Spread liquido ({sp_liq_pct:.4f}%) abaixo do gatilho ({self.cfg.gatilho_spread_liq_pct:.4f}%)."
            )

        if self.cfg.dry_run:
            self.pnl_acumulado_usdt = round(self.pnl_acumulado_usdt + lucro_liq_usdt, 4)
            self.custos_acumulados_usdt = round(self.custos_acumulados_usdt + custos_usdt, 4)
            self.ordens_executadas += 1
            self.ciclos_sem_oportunidade = 0
            self._avaliar_limites_sessao()
            self._salvar_estado()

            res = ResultadoExecucao(
                timestamp=agora,
                modo="DRY_RUN",
                ativo=ativo,
                rota=rota,
                lote_usdt=lote_usdt,
                spread_bruto_pct=spread_bruto_pct,
                custos_totais_usdt=custos_usdt,
                spread_liquido_pct=sp_liq_pct,
                lucro_liquido_est_usdt=lucro_liq_usdt,
                decisao="EXECUTADO_DRY_RUN",
                motivo="Simulacao aprovada apos desconto de todos os custos.",
            )
            self._registrar_log(res)
            return res

        pode_live, motivo_live = self._pode_operar_live()
        if not pode_live:
            return bloquear("Bloqueio de seguranca LIVE: " + motivo_live)

        try:
            resposta_api = self.cliente.executar_par_arbitragem(
                ativo=ativo,
                rota=rota,
                lote_usdt=lote_usdt,
            )
            pnl_real_usdt = float(resposta_api.get("pnl_liquido_usdt", 0.0))
            custo_real_usdt = float(resposta_api.get("custo_real_usdt", custos_usdt))

            self.pnl_acumulado_usdt = round(self.pnl_acumulado_usdt + pnl_real_usdt, 4)
            self.custos_acumulados_usdt = round(self.custos_acumulados_usdt + custo_real_usdt, 4)
            self.ordens_executadas += 1
            self.ciclos_sem_oportunidade = 0
            self._avaliar_limites_sessao()
            self._salvar_estado()

            res = ResultadoExecucao(
                timestamp=agora,
                modo="LIVE",
                ativo=ativo,
                rota=rota,
                lote_usdt=lote_usdt,
                spread_bruto_pct=spread_bruto_pct,
                custos_totais_usdt=custo_real_usdt,
                spread_liquido_pct=sp_liq_pct,
                lucro_liquido_est_usdt=pnl_real_usdt,
                decisao="EXECUTADO_LIVE",
                motivo="Ordem real enviada e contabilizada.",
            )
            self._registrar_log(res)
            return res

        except Exception as exc:
            self.travado_por_risco = True
            self.status_meta = "STOP_LOSS_ATINGIDO"
            self.motivo_trava = f"Falha na execucao real: {exc}"
            return bloquear(self.motivo_trava)
