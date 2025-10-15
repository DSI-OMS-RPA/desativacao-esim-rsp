"""
business_rules.py
-----------------
Regras de negócio do processo de Desativação de Cartões eSIM na Plataforma RSP.

Responsável por aplicar as validações, políticas de repetição (retry)
e definições de comportamento associadas às regras:
- RN-ESIM-01 → Identificação de eSIM com base em range ICCID.
- RN-API-01 → Limite de tentativas de chamada à API.
- RN-ERR-01 → Tratamento padronizado de erros.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class EsimRange:
    """Representa o intervalo válido de ICCID eSIM."""
    start: int
    end: int

    def is_esim(self, iccid: str) -> bool:
        """
        RN-ESIM-01
        Verifica se o ICCID está dentro do intervalo definido para eSIM.
        """
        try:
            iccid_int = int(iccid)
            return self.start <= iccid_int <= self.end
        except ValueError:
            return False


@dataclass
class RetryPolicy:
    """Define parâmetros de retentativa de chamadas API."""
    max_attempts: int = 3
    backoff_factor: float = 1.5  # segundos multiplicadores progressivos

    def can_retry(self, attempt: int) -> bool:
        """
        RN-API-01
        Determina se ainda é permitido retentar a operação.
        """
        return attempt < self.max_attempts

    def next_delay(self, attempt: int) -> float:
        """
        Calcula o tempo de espera antes da próxima tentativa.
        """
        return self.backoff_factor ** attempt


class ErrorHandler:
    """Implementa tratamento genérico de erros conforme RN-ERR-01."""

    @staticmethod
    def handle_error(error: Exception, context: str = "") -> dict:
        """
        Regista e devolve um dicionário estruturado de erro.
        """
        return {
            "status": "failed",
            "context": context,
            "error_type": type(error).__name__,
            "error_message": str(error)
        }


# ======================
# Exemplos de utilização
# ======================
if __name__ == "__main__":
    # Definição do range de eSIM (exemplo de POP)
    esim_range = EsimRange(
        start=89238010000101000000,
        end=89238010000101999999
    )

    sample_iccid = "89238010000101567890"
    print("É eSIM?", esim_range.is_esim(sample_iccid))  # True

    # Política de retry
    retry_policy = RetryPolicy(max_attempts=3)
    for attempt in range(1, 5):
        if retry_policy.can_retry(attempt):
            print(f"Tentativa {attempt} permitida, próximo delay: {retry_policy.next_delay(attempt):.2f}s")
        else:
            print(f"Tentativa {attempt} bloqueada (limite atingido)")

    # Exemplo de erro tratado
    try:
        raise ConnectionError("Falha na API RSP")
    except Exception as e:
        print(ErrorHandler.handle_error(e, context="API RSP"))
