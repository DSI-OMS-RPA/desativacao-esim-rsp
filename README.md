# Desativação de Cartões eSIM - RSP (Remote SIM Provisioning)

Processo RPA que desativa cartões eSIM na plataforma RSP com base em dados de desativação provenientes do NGIN/Siebel.

## 🧩 Objetivo
Garantir a sincronização dos estados dos cartões entre o NGIN/Siebel e a plataforma RSP, assegurando a integridade e consistência dos dados.

## ⚙️ Funcionalidades
- Leitura de ficheiros XML exportados do NGIN;
- Identificação de cartões eSIM com base em ranges ICCID;
- Desativação automática via API RSP;
- Registo detalhado de logs e tratamento de exceções.

## 🗂️ Estrutura
- `docs/` → documentação técnica e de processo
- `scripts/` → código-fonte da automação
- `config/` → parâmetros e tabelas de apoio
- `logs/` → ficheiros de execução
- `tests/` → testes unitários e integração

## 🧠 Requisitos
- Python 3.10+
- Bibliotecas: `requests`, `xmltodict`, `dotenv`, `pandas`

## 🔒 Notas
Credenciais e endpoints devem ser configurados em `.env` (não incluído no repositório).
