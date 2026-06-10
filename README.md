# Sistema Financeiro Pessoal

Sistema web simples para controlar contas a pagar, contas pagas, receitas e saldo mensal.

## Tecnologias

- Frontend em HTML, CSS e JavaScript puro
- Backend em Python
- Banco PostgreSQL em producao e SQLite como fallback local
- Docker e Docker Compose

## Como rodar com Docker

```powershell
docker compose up --build
```

Depois acesse:

```text
http://localhost:8000
```

Credenciais administrativas devem ser configuradas pelo proprietario do sistema.

Troque credenciais administrativas iniciais antes de liberar o sistema para outros usuarios.

## Persistencia dos dados

Em producao, configure `DATABASE_URL` apontando para um PostgreSQL persistente, como o banco gerenciado do Render.
Sem `DATABASE_URL`, o sistema usa SQLite em `/app/data/financeiro.db` como fallback local.

## Variaveis de ambiente

- `DATABASE_URL`: URL do PostgreSQL. No Render, use a Internal Database URL do banco.
- `SECRET_KEY`: chave secreta das sessoes.
- `SUPERADMIN_PASSWORD`: senha inicial do SuperAdmin quando ele ainda nao existe.
- `DATA_DIR`: pasta do SQLite local, usada apenas quando `DATABASE_URL` nao estiver definida.
- `PORT`: porta HTTP, padrao `8000`.

## Migrar SQLite para PostgreSQL

Antes de apontar o deploy para PostgreSQL, faca backup do arquivo SQLite atual.

No PowerShell:

```powershell
$env:DATABASE_URL="postgresql://usuario:senha@host:5432/banco"
$env:SQLITE_DB_PATH="data/financeiro.db"
python app/migrate_sqlite_to_postgres.py
```

No Docker Compose local:

```powershell
docker compose up --build
docker compose exec financeiro python app/migrate_sqlite_to_postgres.py
```

O script cria as tabelas se nao existirem e copia usuarios, senhas com hash, categorias, despesas, receitas e metas sem apagar dados existentes.

## Rodar sem Docker

Com Python instalado:

```powershell
python app/server.py
```

Abra `http://localhost:8000`.

## Funcionalidades

- Login simples com usuarios comuns e area administrativa restrita
- Alteracao de senha
- Dashboard mensal com receitas, despesas, saldos, vencidas e proximas contas
- Cadastro, edicao, exclusao e pagamento de contas
- Parcelamento automatico dentro do cadastro de despesas
- Cadastro, edicao e exclusao de receitas
- Metas financeiras com progresso, adicao e retirada de valores
- Graficos simples e fluxo de caixa futuro de 12 meses
- Filtros por mes, ano, status e categoria
- Relatorio mensal com exportacao CSV
- Importacao Excel por modelo oficial `.xlsx` com abas DESPESAS, RECEITAS, METAS e PARCELADAS
- Categorias padrao criadas automaticamente
- SuperAdmin pode gerenciar usuarios e categorias

## Observacoes para uso real

- Altere a senha padrao imediatamente.
- Em rede interna ou uso empresarial, coloque a aplicacao atras de proxy com HTTPS.
- Faca backups periodicos do PostgreSQL.
- No Render, vincule um PostgreSQL gerenciado e configure `DATABASE_URL`; nao dependa do filesystem do container para persistencia.
