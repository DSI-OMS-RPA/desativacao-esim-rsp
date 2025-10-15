# Testes unitários — business_rules

Este ficheiro explica como executar os testes unitários para o módulo `core/business_rules.py`.

## Requisitos
- Python 3.10+
- Instalar dependências do projeto (ideal num virtualenv):

```bash
pip install -r requirements.txt
````

* `pytest` deve estar disponível (pode ser instalado com `pip install pytest`).

## Executar os testes

A partir da root do repositório, correr:

```bash
pytest tests/test_business_rules.py -q
```

Saída esperada (resumida):

```
4 passed in 0.1s
```

## Observações

* Os testes não fazem chamadas externas; são unitários e determinísticos.
* Se alterares os `start`/`end` do `EsimRange` no ficheiro `core/business_rules.py`, atualiza os valores nos testes para manter coerência.
* Para mais detalhes sobre pytest, consultar a [documentação oficial](https://docs.pytest.org/en/stable/).
