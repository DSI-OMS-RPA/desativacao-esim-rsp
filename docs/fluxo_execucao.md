1. INICIALIZAÇÃO
   ├─ Verificar/criar lock file (PID-based)
   ├─ Limpar pasta local "processed/" da execução anterior
   └─ Inicializar logger rotativo (daily rotation)

2. DESCOBERTA DE FICHEIROS
   ├─ Conectar FTP
   ├─ Listar *.xml na pasta raiz
   ├─ Filtrar: padrão "NGIN_DataFile_YYYYMMDD.xml"
   └─ Ordenar por timestamp no nome (mais antigo primeiro - FIFO)

3. LOOP PRINCIPAL (para cada ficheiro)
   ├─ Download para pasta "staging/"
   ├─ Validação XML básica
   ├─ Parse e extração de registos
   ├─ Filtrar DEACTIVATE + eSIM range
   ├─ Deduplicar ICCIDs
   │
   ├─ PROCESSAMENTO API (micro-batches)
   │   ├─ Agrupar ICCIDs em chunks de 10
   │   ├─ Para cada chunk (sequencial):
   │   │   └─ Para cada ICCID:
   │   │       ├─ Call ExpireOrder API
   │   │       ├─ Retry com exponential backoff (3 tentativas)
   │   │       └─ Log resultado
   │   └─ Sleep 1s entre chunks (rate limit safety)
   │
   ├─ FINALIZAÇÃO DO FICHEIRO
   │   ├─ Se 100% sucesso OU >95% sucesso:
   │   │   ├─ Mover no FTP: raiz → "done/"
   │   │   └─ Mover local: "staging/" → "processed/"
   │   └─ Se <95% sucesso:
   │       └─ Deixar na raiz (será reprocessado na próxima)
   │
   └─ Gerar relatório parcial do ficheiro

4. RELATÓRIO CONSOLIDADO
   ├─ Agregar resultados de todos os ficheiros
   ├─ Gerar CSV com detalhes
   └─ Enviar email com sumário + CSV anexo

5. CLEANUP E ENCERRAMENTO
   ├─ Remover ficheiros em "staging/"
   ├─ Remover lock file
   └─ Exit code: 0 (sucesso) ou 1 (falhas críticas)


### Decisões de Design Pragmáticas

#### **Gestão de Falhas**
- **Threshold 95%**: Ficheiro considerado sucesso se ≥95% dos ICCIDs processados OK
- **Falha total**: Se <95%, ficheiro permanece para retry completo
- **Sem dead letter queue**: Simplicidade > complexidade nesta fase

#### **Performance**
- **Micro-batches de 10**: Balanço entre velocidade e segurança
- **Sleep 1s entre batches**: Evita overwhelming da API
- **Sequencial por defeito**: Pode evoluir para concurrent se API suportar

#### **Observabilidade**
- **Logs estruturados** (JSON) para parsing fácil
- **Métricas no log**: timings, counts, success rates
- **Email diário**: Push notification dos resultados

#### **Gestão de Estado**
- **Lock via PID file**: Simples e eficaz para single-instance
- **Stateless**: Cada execução é independente
- **"done/" como marker**: Estado persistido no FTP

### Estrutura de Pastas Proposta

/opt/esim-deactivation/
├── main.py
├── config.yaml
├── .env
├── /staging/       (download temporário)
├── /processed/     (ficheiros processados - limpo a cada run)
├── /logs/          (rotativos)
│   └── app_YYYYMMDD.log
└── /reports/       (opcional - manter últimos N dias)
    └── report_YYYYMMDD.csv
