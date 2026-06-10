# Sistema Financeiro Pessoal

Sistema web simples para controlar contas a pagar, contas pagas, receitas e saldo mensal.

## Tecnologias

- Frontend em HTML, CSS e JavaScript puro
- Backend em Python com biblioteca padrao
- Banco SQLite
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

O banco SQLite fica em `/app/data/financeiro.db` dentro do container e e salvo no volume Docker `financeiro_data`.
Assim os dados continuam existindo mesmo se o container for recriado.

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
- Importacao por modelo CSV compativel com Excel, com previa e validacao
- Filtros por mes, ano, status e categoria
- Relatorio mensal com exportacao CSV
- Importacao Excel por modelo oficial `.xlsx` com abas DESPESAS, RECEITAS, METAS e PARCELADAS
- Categorias padrao criadas automaticamente
- SuperAdmin pode gerenciar usuarios e categorias

## Observacoes para uso real

- Altere a senha padrao imediatamente.
- Em rede interna ou uso empresarial, coloque a aplicacao atras de proxy com HTTPS.
- Faca backup do volume `financeiro_data` periodicamente.
- No Render, use o `render.yaml` e mantenha um disco persistente montado em `/app/data` para preservar o SQLite.
