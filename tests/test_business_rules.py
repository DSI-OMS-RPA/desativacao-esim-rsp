# tests/test_business_rules.py
import os
import sys

# Ensure the project root directory to sys.path if it's not already there
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.business_rules import EsimRange, RetryPolicy, ErrorHandler

def test_esim_range_valid():

    esim_range = EsimRange(
        start=89238010000101000000,
        end=89238010000101999999,
    )

    # limites
    assert esim_range.is_esim("89238010000101000000") is True
    assert esim_range.is_esim("89238010000101999999") is True

    # valor intermédio
    assert esim_range.is_esim("89238010000101567890") is True


def test_esim_range_invalid():
    esim_range = EsimRange(
        start=89238010000101000000,
        end=89238010000101999999,
    )

    # fora do range
    assert esim_range.is_esim("89238010000102000000") is False

    # valores inválidos
    assert esim_range.is_esim("") is False
    assert esim_range.is_esim("notnumeric") is False


def test_retry_policy_behavior():
    # Nota: RetryPolicy usa convention 1-based attempts e delay_seconds default=5.0
    rp = RetryPolicy(max_attempts=3, delay_seconds=5.0, backoff_factor=2)

    # can_retry: attempts menores que max_attempts são permitidas
    assert rp.can_retry(0) is True   # ainda permitido (0 tratada como antes da primeira tentativa)
    assert rp.can_retry(1) is True
    assert rp.can_retry(2) is True
    # tentativa igual ou superior ao limite não permite retentar
    assert rp.can_retry(3) is False

    # backoff: verificar delays usando a fórmula delay_seconds * backoff_factor ** (attempt - 1)
    # attempt = 1 -> 5 * 2**0 = 5
    # attempt = 2 -> 5 * 2**1 = 10
    # attempt = 3 -> 5 * 2**2 = 20
    assert rp.next_delay(1) == 5.0
    assert rp.next_delay(2) == 10.0
    assert rp.next_delay(3) == 20.0


def test_error_handler_structure():
    try:
        raise ConnectionError("Falha simulada na API")
    except Exception as exc:
        payload = ErrorHandler.handle_error(exc, context="API RSP")

    assert isinstance(payload, dict)
    assert payload.get("status") == "failed"
    assert payload.get("context") == "API RSP"
    assert payload.get("error_type") == "ConnectionError"
    assert "Falha simulada" in payload.get("error_message")
