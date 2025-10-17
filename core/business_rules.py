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
from pathlib import Path
from typing import Dict, Tuple, Optional

from helpers.configuration import load_json_config

# -----------------------------
# Data classes das regras
# -----------------------------
@dataclass
class EsimRange:
    """Representa o intervalo válido de ICCID eSIM."""
    start: int
    end: int

    def is_esim(self, iccid: Optional[str]) -> bool:
        """
        RN-ESIM-01
        Verifica se o ICCID está dentro do intervalo definido para eSIM.

        - Aceita strings (com zeros à esquerda preservados).
        - Retorna False para valores None, vazios ou não numéricos.
        """
        if not iccid:
            return False
        iccid_clean = str(iccid).strip()
        if not iccid_clean.isdigit():
            return False
        try:
            iccid_int = int(iccid_clean)
        except ValueError:
            return False
        return self.start <= iccid_int <= self.end


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
