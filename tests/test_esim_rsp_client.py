# tests/test_esim_rsp_client.py
import pytest
import requests
import time

from core.esim_rsp_client import ESIMRSPClient


def test_expire_order_success(monkeypatch):
    """
    Quando _make_request retorna sucesso, expire_order deve:
    - retornar status == "success"
    - enviar o endpoint e body corretos
    - incluir finalProfileStatusIndicator == "Unavailable"
    """
    client = ESIMRSPClient(environment="test", env_path=None)

    captured = {}

    def fake_make_request(endpoint, method='POST', body=None):
        # armazenar para assert posterior e simular resposta do RSP
        captured['endpoint'] = endpoint
        captured['method'] = method
        captured['body'] = body
        return {"header": {"functionExecutionStatus": {"status": "Executed-Success"}}}

    monkeypatch.setattr(client, "_make_request", fake_make_request)

    iccid = "89238010000101567890"
    result = client.expire_order(iccid=iccid)

    assert result["status"] == "success"
    # endpoint deve corresponder ao path da ExpireOrder conforme documentação
    assert captured["endpoint"].endswith("/order/expire")
    assert captured["method"] == "POST"
    assert isinstance(captured["body"], dict)
    assert captured["body"].get("iccid") == iccid
    assert captured["body"].get("finalProfileStatusIndicator").lower() == "unavailable"
    # header.functionCallIdentifier deve ser expireOrder
    header = captured["body"].get("header", {})
    assert header.get("functionCallIdentifier") == "expireOrder"
    assert "functionRequesterIdentifier" in header


def test_expire_order_retry_and_fail(monkeypatch):
    """
    Simula falha permanente na API:
    - monkeypatch _make_request para lançar uma RequestException sempre
    - monkeypatch time.sleep para acelerar o teste
    - verificar que expire_order retorna status 'failed' e attempts == max_attempts
    """
    client = ESIMRSPClient(environment="test", env_path=None)

    call_count = {"n": 0}

    def fake_make_request_fail(endpoint, method='POST', body=None):
        call_count["n"] += 1
        raise requests.RequestException("simulated failure")

    monkeypatch.setattr(client, "_make_request", fake_make_request_fail)
    # prevenir delays reais
    monkeypatch.setattr(time, "sleep", lambda s: None)

    iccid = "89238010000101567890"
    result = client.expire_order(iccid=iccid)

    assert result["status"] == "failed"
    # attempts devolvido deve ser igual ao máximo de tentativas da retry policy
    assert result["attempts"] == client.retry_policy.max_attempts
    # confirmar que _make_request foi chamado o número esperado de vezes
    assert call_count["n"] == client.retry_policy.max_attempts
