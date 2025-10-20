"""
core/business_rules.py
----------------------
Regras de negócio do processo de Desativação de Cartões eSIM na Plataforma RSP.

Este módulo pode:
 - ser usado isoladamente (instanciar EsimRange e RetryPolicy manualmente)
 - carregar automaticamente valores de `configs.json` na raiz do repositório
   através de get_default_rules()
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional

from helpers.configuration import load_json_config
from helpers.logger_manager import LoggerManager

# -----------------------------
# Data classes das regras
# -----------------------------
@dataclass
class EsimRange:
    """Representa o intervalo válido de ICCID eSIM."""

    def __init__(self, start: int, end: int):
        """Initialize the orchestrator with configuration."""

        # Setup logging
        self.logger_manager = LoggerManager()
        self.logger = logging.getLogger(__name__)

        # Intervalo de ICCID para eSIM
        self.start = start
        self.end = end

    def luhn_valid(self, num_str: str) -> bool:
        """Verifica se a string numérica passa o algoritmo de Luhn."""
        if not num_str.isdigit():
            return False
        total = 0
        # parity = 0 se len even, 1 se odd -> padrão de duplicação
        parity = len(num_str) % 2
        for i, ch in enumerate(num_str):
            d = int(ch)
            if i % 2 == parity:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        return total % 10 == 0

    def is_esim(self, iccid: Optional[str]) -> bool:
        """
        RN-ESIM-01 Verifica se o ICCID está dentro do intervalo definido para eSIM.
        Suporta ICCIDs com ou sem dígito Luhn extra:
        - Se iccid tiver 1 dígito a mais que start/end e o último for Luhn válido, corta o último dígito antes da comparação.
        - Aceita strings (com zeros à esquerda preservados).
        - Retorna False para valores None, vazios ou não numéricos.
        """
        if not iccid:
            self.logger.debug("ICCID vazio ou None.")
            return False

        iccid_s = str(iccid).strip()
        if not iccid_s.isdigit():
            self.logger.debug(f"ICCID inválido (não numérico): '{iccid_s}'")
            return False

        # normaliza start/end como strings
        start_s = str(getattr(self, "start", "")).strip()
        end_s = str(getattr(self, "end", "")).strip()

        if not (start_s.isdigit() and end_s.isdigit()):
            self.logger.error(f"Start/End inválidos: start='{start_s}' end='{end_s}'")
            return False

        # caso normal: mesmos comprimentos -> comparar por string (mais seguro para IDs)
        if len(iccid_s) == len(start_s) == len(end_s):
            in_range = start_s <= iccid_s <= end_s
            self.logger.debug(f"Same-length compare -> {iccid_s} {'in' if in_range else 'out'}")
            return in_range

        # caso comum no teu ambiente: iccid tem 1 dígito extra (Luhn)
        if len(iccid_s) == len(start_s) + 1 and self.luhn_valid(iccid_s):
            candidate = iccid_s[:-1]  # remove dígito Luhn
            self.logger.debug(f"Detected Luhn-digit ICCID; comparing '{candidate}' against ranges")
            in_range = start_s <= candidate <= end_s
            self.logger.debug(f"After stripping Luhn: {candidate} {'dentro' if in_range else 'fora'}")
            return in_range

        # fallback: tenta comparação numérica (suporta comprimentos diferentes, mas com cuidado)
        try:
            iccid_i = int(iccid_s)
            start_i = int(start_s)
            end_i = int(end_s)
        except ValueError:
            self.logger.debug("Falha ao converter para int durante fallback.")
            return False

        in_range = start_i <= iccid_i <= end_i
        self.logger.debug(f"Numeric fallback -> {iccid_s} {'dentro' if in_range else 'fora'}")
        return in_range

@dataclass
class RetryPolicy:
    """Define parâmetros de retentativa de chamadas API."""
    max_attempts: int = 3
    delay_seconds: float = 5.0
    backoff_factor: float = 2.0  # multiplicador exponencial

    def can_retry(self, attempt: int) -> bool:
        """
        RN-API-01
        Determina se ainda é permitido retentar a operação.
        - attempt: número de tentativas já feitas (0-based ou 1-based, conveção definida no uso).
        Aqui usamos a convenção: attempt é o número da tentativa atual (1..n).
        can_retry retorna True se attempt < max_attempts.
        """
        return attempt < self.max_attempts

    def next_delay(self, attempt: int) -> float:
        """
        Calcula o tempo de espera antes da próxima tentativa.
        Fórmula: delay_seconds * (backoff_factor ** (attempt - 1))
        - attempt: tentativa atual (1-based). Para attempt=1 -> delay_seconds * backoff_factor**0 = delay_seconds
        """
        if attempt <= 0:
            attempt = 1
        return float(self.delay_seconds) * (float(self.backoff_factor) ** (attempt - 1))


class ErrorHandler:
    """Implementa tratamento genérico de erros conforme RN-ERR-01."""

    @staticmethod
    def handle_error(error: Exception, context: str = "", raise_on_debug: bool = False) -> Dict:
        """
        Regista e devolve um dicionário estruturado de erro.
        - context: string com contexto (ex.: 'API RSP', 'Parser XML')
        - raise_on_debug: se True, re-levanta a exceção (útil em dev)
        """
        payload = {
            "status": "failed",
            "context": context,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if raise_on_debug:
            raise error
        return payload




def rules_from_config(config: Dict) -> Tuple[EsimRange, RetryPolicy]:
    """
    Cria EsimRange e RetryPolicy a partir do dicionário de configuração.
    Espera a estrutura similar a:
    {
        "retry_policy": {"max_retries": 3, "delay_seconds": 5, "backoff_factor": 2},
        "esim_range": {"start": 892380..., "end": 892380...}
    }
    """
    # valores por defeito coerentes com o PDD/POP
    retry_cfg = config.get("retry_policy", {}) if isinstance(config, dict) else {}
    esim_cfg = config.get("esim_range", {}) if isinstance(config, dict) else {}

    max_retries = int(retry_cfg.get("max_retries", retry_cfg.get("max_attempts", 3)))
    delay_seconds = float(retry_cfg.get("delay_seconds", retry_cfg.get("delay", 5.0)))
    backoff_factor = float(retry_cfg.get("backoff_factor", retry_cfg.get("backoff", 2.0)))

    start = int(esim_cfg.get("start", 89238010000101000000))
    end = int(esim_cfg.get("end", 89238010000101999999))

    esim_range = EsimRange(start=start, end=end)
    retry_policy = RetryPolicy(max_attempts=max_retries, delay_seconds=delay_seconds, backoff_factor=backoff_factor)

    return esim_range, retry_policy


def get_default_rules(config_path: Optional[str] = None) -> Tuple[EsimRange, RetryPolicy]:
    """
    Tenta carregar as regras a partir do ficheiro de configuração.
    - Se não encontrar ficheiro/config, retorna regras por defeito.
    """
    cfg = load_json_config(config_path)

    if not cfg:
        # retorna defaults embutidos
        return rules_from_config({})
    return rules_from_config(cfg)


# -----------------------------
# Módulo executável (exemplos)
# -----------------------------
if __name__ == "__main__":
    # tenta carregar configs.json na raiz; se não existir, usa defaults
    esim_range_def, retry_policy_def = get_default_rules()

    print("EsimRange:", esim_range_def)
    print("RetryPolicy:", retry_policy_def)

    # testes rápidos
    test_iccids = [
        "89238010000101000000",
        "89238010000101999999",
        "89238010000102000000",
        "",
        "notnumeric",
    ]
    for v in test_iccids:
        print(f"ICCID={v!r} => is_esim={esim_range_def.is_esim(v)}")

    # demonstração do retry delays
    for attempt in range(1, retry_policy_def.max_attempts + 2):
        allowed = retry_policy_def.can_retry(attempt)
        delay = retry_policy_def.next_delay(attempt) if allowed else None
        print(f"Attempt {attempt}: can_retry={allowed}, next_delay={delay}")
