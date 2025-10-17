# Desativação de Cartões eSIM - RSP (Remote SIM Provisioning)

Processo RPA que desativa cartões eSIM na plataforma **RSP** com base em dados de desativação provenientes do **NGIN / Siebel**.

---

## 🧩 Objetivo

Garantir a sincronização dos estados dos cartões entre o NGIN/Siebel e a plataforma RSP, assegurando integridade e consistência dos dados.

---

## ⚙️ Funcionalidades

* Leitura de ficheiros XML exportados pelo NGIN (entregues via Siebel por FTP).
* Identificação de cartões **eSIM** com base em ranges ICCID/IMSI.
* Desativação automática via API RSP (endpoint `SetOrderToExpire`).
* Registo detalhado de logs, tratamento de exceções e alertas.

---

## 🗂️ Estrutura do Repositório (versão recomendada)

```
DESATIVACAO-ESIM-RSP/
├── configs/                   # ficheiros de configuração (.env, config.ini, json)
├── core/                      # núcleo da aplicação (orquestrador, client RSP, regras)
│   ├── esim_rsp_client.py
│   ├── orchestrator.py
│   └── business_rules.py
├── helpers/                   # utilitários e adaptadores (FTP, DB, logging, validators)
│   ├── database/
│   ├── ftp_client.py
│   ├── logger_manager.py
│   └── validation_utils.py
├── docs/                      # PDD, POP, BPMN, BRD, etc.
├── logs/                      # ficheiros de execução e erros (gitignored)
├── template/                  # templates de alerta/report (HTML, email)
├── tests/                     # testes unitários e de integração
├── main.py                    # entrypoint - orquestra execução
├── requirements.txt
└── README.md
```

> Nota: adaptámos `scripts/` para **`core/`** e **`helpers/`** conforme melhor prática modular.

---

## 🧰 Requisitos

* Python 3.10+
* Dependências (ex.:) `requests`, `xmltodict`, `python-dotenv`, `pandas`, `psycopg2-binary` (se usar PostgreSQL)
* Acesso ao servidor FTP interno (ex.: `CVTPRBSSP4`) e permissões necessárias para leitura de ficheiros

Instalação das dependências:

```bash
python -m venv .venv
source .venv/bin/activate    # Unix
.\.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

---

## ⚙️ Configuração

Copiar o ficheiro de exemplo e preencher as credenciais (NUNCA commitar `.env` com segredos):

```bash
cp configs/.env.example configs/.env
# editar configs/.env com ENDPOINT_RSP, FTP_HOST, FTP_USER, FTP_PASS, DB_* etc.
```

Campos principais esperados no `.env`:

* `FTP_HOST`, `FTP_USER`, `FTP_PASS`, `FTP_PATH`
* `RSP_API_BASE`, `RSP_API_KEY` (ou mecanismo OAuth)
* `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME` (se aplicável)

---

## ▶️ Execução

Executar o entrypoint (modo manual / debug):

```bash
python main.py
```

Para produção, agendar a execução diária (ex.: cron, scheduler do ambiente RPA).

---

## 🧪 Testes

* Os testes unitários ficam em `tests/`.
* Exemplo de execução com pytest:

```bash
pytest tests/
```

Recomenda-se usar mocks para chamadas à API RSP e para acesso FTP/DB.

---

## 🔒 Segurança e Boas Práticas

* Nunca commitar ficheiros com credenciais. Usar `.env` e o ficheiro `configs/.env.example` para referência.
* Logs não devem expor MSISDN em claro — maskar antes de persistir/exportar.
* Implementar retry/backoff exponencial para chamadas API e alertas em caso de falha persistente.

---

## 📁 Boas convenções de commit

* `feat:` nova funcionalidade
* `fix:` correção
* `refactor:` reorganização de código
* `docs:` documentação
* `test:` testes
* `chore:` tarefas de manutenção

---

## 📌 Próximos passos sugeridos

* Criar CI simples (GitHub Actions) que execute `pytest` e checa linting (flake8/ruff).
* Gerar artefacto `.bpmn` e adicionar em `docs/` para controlo de versão.
* Implementar monitorização/alertas (email/Teams) para falhas críticas.

---

**Contacto:** Equipa de Processos e Automação — Cabo Verde Telecom

---

*Versão do README: 1.0*
