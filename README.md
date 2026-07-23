# Integração de Pagamentos Pix — Mercado Pago (AWS Lambda, Python 3.12, Arquitetura Hexagonal)

Uma única Lambda (`oficina-pagamento`) com dois gatilhos, que juntos criam e
acompanham pagamentos Pix usando a **Orders API** do Mercado Pago:

1. **Gatilho SQS** — consome mensagens da fila `sqs-pagamento-solicitar`,
   valida o payload e cria a Order no Mercado Pago (`POST /v1/orders`). Em
   caso de sucesso, publica em `sqs-pagamento-efetuado` (status
   **`efetuado`**); se o gateway recusar/falhar, publica em
   `sqs-pagamento-recusado` (status **`recusado`**) — em ambos os casos o
   resultado é persistido no DynamoDB antes da publicação.
2. **Gatilho EventBridge (polling)** — acionado periodicamente (rate
   configurável), busca no DynamoDB as orders com status `efetuado` ainda
   pendentes de confirmação e, para cada uma, consulta o Mercado Pago
   (`GET /v1/orders/{id}`) para saber se o Pix já foi processado. Quando o
   `status` retornado é `processed`, atualiza o status do pedido e publica
   novamente em `sqs-pagamento-efetuado` (status **`pago`**).

O mesmo `lambda_handler` (`payment_handler.py`) despacha para a lógica
certa conforme o formato do evento recebido — ver `Arquitetura` abaixo.

```
                          ┌────────────────────────┐        ┌───────────────────┐
   sqs-pagamento-solicitar│                        │──────▶ │ Mercado Pago API  │
 ─────────────────────▶  │    oficina-pagamento     │        └─────────┬─────────┘
                          │   (payment_handler.py)   │                  │
                          │  gatilho 1: fila SQS      │                  │ GET /v1/orders/{id}
                          │  gatilho 2: EventBridge   │ ────polling──────┘
                          │  (polling agendado)       │
                          └────────────┬─────────────┘
                     sucesso/pago      │      falha no gateway
                          ▼            ▼
          sqs-pagamento-efetuado   sqs-pagamento-recusado
```

## Arquitetura (Hexagonal / Ports & Adapters)


```
src/
├── domain/                        # Núcleo — regras de negócio puras, sem AWS/HTTP
│   ├── entities.py                 # OrderRequest, Order, Payer, PaymentMethod...
│   ├── payment_status.py            # Constantes "efetuado" / "recusado" / "pago"
│   └── exceptions.py                # DomainValidationError, PaymentGatewayError...
│
├── application/                   # Casos de uso — orquestram o domínio via portas
│   ├── ports/
│   │   ├── payment_gateway_port.py         # Interface: criar/consultar order
│   │   ├── order_repository_port.py        # Interface: persistir estado da order
│   │   ├── payment_status_notifier_port.py # Interface: publicar em efetuado/recusado
│   │   └── dead_letter_publisher_port.py   # Interface: publicar payload inválido na DLQ
│   └── use_cases/
│       ├── create_payment_order.py     # Fluxo da fila SQS (efetuado/recusado)
│       └── check_payment_status.py     # Fluxo do polling (confirmação de pago)
│
└── infrastructure/                # Adapters — implementações concretas
    ├── config.py                       # Leitura de variáveis de ambiente
    ├── adapters/
    │   ├── mercado_pago_gateway.py          # Implementa PaymentGatewayPort (requests)
    │   ├── dynamodb_order_repository.py     # Implementa OrderRepositoryPort (boto3)
    │   ├── sqs_payment_status_notifier.py   # Implementa PaymentStatusNotifierPort (boto3)
    │   └── sqs_dead_letter_publisher.py     # Implementa DeadLetterPublisherPort (boto3)
    └── handlers/
        ├── payment_handler.py           # Entry point ÚNICO da Lambda oficina-pagamento (dispatcher)
        ├── sqs_handler.py               # Lógica do gatilho SQS (chamada pelo dispatcher)
        └── polling_handler.py           # Lógica do gatilho de polling (chamada pelo dispatcher)
```

**Por que essa separação importa na prática:**
- `domain/` não importa `boto3`, `requests` nem nada de AWS — pode ser testado
  em milissegundos, sem mocks pesados.
- `application/` (casos de uso) depende apenas das *interfaces* (`ports/`), não
  das implementações. Nos testes, injetamos `MagicMock()` no lugar do gateway
  Mercado Pago, do repositório DynamoDB e do notifier das filas de saída.
- `infrastructure/` é o único lugar que sabe falar HTTP com o Mercado Pago,
  persistir no DynamoDB ou publicar no SQS. Trocar de banco (ex. Postgres),
  de gateway de pagamento, ou até de mecanismo de notificação (ex. SNS em vez
  de SQS) não exige tocar em `domain/` nem `application/`.
- `sqs_handler.py`/`polling_handler.py` continuam sendo dois módulos com uma
  função `lambda_handler` cada — só que agora nenhum dos dois é referenciado
  diretamente pela infra (`terraform/`); quem é chamado pela AWS é sempre
  `payment_handler.lambda_handler`, que despacha para um dos dois conforme o
  formato do evento recebido (fila SQS sempre tem a chave `"Records"`).

## Pré-requisitos

- Python 3.12+
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.10
- Uma conta AWS configurada (`aws configure`) — só necessária pro deploy
  real; para testar via LocalStack (veja "Testando contra o LocalStack"),
  qualquer credencial fake serve
- Docker — só necessário para a Opção B de teste local (Lambda publicada
  de verdade no LocalStack, que usa o executor Docker dele)
- Os recursos do [`oficina-pagamento-infras`](https://github.com/jaquelineramosit/oficina-pagamento-infras)
  já aplicados (filas SQS + tabela DynamoDB) — este repositório só cria a
  Lambda e referencia esses recursos, não os cria
- Access Token de produção/teste da sua aplicação no Mercado Pago
  (`APP_USR-...` ou `TEST-...`)

## Variáveis de ambiente

| Variável                          | Usada por           | Obrigatória | Descrição |
|------------------------------------|----------------------|:-----------:|-----------|
| `MP_ACCESS_TOKEN`                  | os dois gatilhos      | ✅ | Bearer token da API do Mercado Pago |
| `MP_API_BASE_URL`                  | os dois gatilhos      | não (default `https://api.mercadopago.com`) | Útil para apontar a um mock em testes |
| `ORDERS_TABLE_NAME`                | os dois gatilhos      | não (default `orders`) | Nome da tabela DynamoDB |
| `SQS_PAGAMENTO_EFETUADO_QUEUE_URL` | os dois gatilhos      | ✅ (setado automaticamente pelo `terraform/`) | URL da fila `sqs-pagamento-efetuado` |
| `SQS_PAGAMENTO_RECUSADO_QUEUE_URL` | gatilho SQS           | ✅ (setado automaticamente pelo `terraform/`) | URL da fila `sqs-pagamento-recusado` |
| `SQS_PAGAMENTO_SOLICITAR_DLQ_URL`  | gatilho SQS           | recomendada | URL da DLQ `sqs-pagamento-solicitar-dlq`, usada para preservar payloads inválidos (`DomainValidationError`) |
| `MP_HTTP_TIMEOUT_SECONDS`          | os dois gatilhos      | não (default `10`) | Timeout das chamadas HTTP ao Mercado Pago |
| `ORDER_EXPIRATION_MINUTES`         | gatilho de polling    | não (default `10`) | Minutos após a criação da order sem confirmação de pagamento até ela ser marcada como `recusado` e parar de ser verificada pelo polling |
| `AWS_ENDPOINT_URL`                 | os dois gatilhos      | não | Aponta o boto3 para o LocalStack em vez da AWS real (ver seção "Testando contra o LocalStack") |

> Em produção, prefira buscar `MP_ACCESS_TOKEN` do **AWS Secrets Manager**
> ou **SSM Parameter Store** em vez de variável de ambiente em texto plano.
> No `terraform/`, esse valor já é uma `variable` `sensitive = true` para
> facilitar essa migração depois.

## Instalação para desenvolvimento local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Rodando os testes

```bash
pytest -v
```

Isso roda tanto os testes unitários (`tests/unit/`) quanto o cenário BDD
(`tests/bdd/`) — o pytest descobre os dois automaticamente via
`pytest-bdd`, não precisa de comando separado.

Os testes cobrem:
- Validação de todos os campos obrigatórios do payload (`test_entities.py`)
- O caso de uso de criação de order, com o gateway/repositório mockados
  (`test_create_payment_order.py`)
- O adapter HTTP que fala com o Mercado Pago (`create_order`/`get_order`,
  sucesso/erro de rede/status inesperado) — `test_mercado_pago_gateway.py`
- O caso de uso de verificação de status via polling, incluindo a
  expiração de orders pendentes (`test_check_payment_status.py`)
- O filtro de orders pendentes do `DynamoDBOrderRepository`, contra uma
  tabela DynamoDB simulada com `moto` (`test_dynamodb_order_repository.py`)
- Os dois `lambda_handler` de ponta a ponta, com dependências externas
  mockadas (`test_sqs_handler.py`, `test_polling_handler.py`)
- O dispatcher que decide qual dos dois handlers chamar
  (`test_payment_handler.py`)
- **BDD (`tests/bdd/`)**: o fluxo completo de criação de pagamento via
  fila SQS, escrito em Gherkin em português
  (`tests/bdd/features/criacao_pagamento.feature`, implementado com
  `pytest-bdd` em `tests/bdd/step_defs/test_criacao_pagamento.py`) —
  cobre tanto o caminho de sucesso (Order criada → publicada como
  `efetuado`) quanto a recusa do gateway (→ publicada como `recusado`).

### Cobertura de testes

```bash
pytest --cov=src --cov-report=term-missing --cov-report=xml --cov-fail-under=80
```

A configuração de cobertura fica em `.coveragerc` (`source = src` — só a
aplicação em si entra na conta, não os próprios testes nem
`resources_local/`). O CI (`ci.yml`) roda exatamente esse comando e
**falha o build se a cobertura total cair abaixo de 80%**
(`--cov-fail-under=80`), além de publicar `coverage.xml` como artefato
para o job de qualidade (SonarQube) usar — veja a seção seguinte.

**Onde ver a cobertura no GitHub Actions:** abra o workflow run → job
`test` → o **Job Summary** (resumo que aparece no topo da página do run,
sem precisar abrir nenhum log) mostra a tabela de cobertura por arquivo +
o total, gerada pela action `irongut/CodeCoverageSummary`. O `coverage.xml`
bruto também fica disponível como artefato do job (`coverage-report`), se
precisar do dado cru. Isso é a única visão de cobertura persistente hoje:
o job `quality-gate` (SonarQube) só existe durante a execução — não há
dashboard do Sonar pra consultar depois, apenas o resultado do Quality
Gate (✅/❌) naquele run.

## CI/CD (GitHub Actions)

`ci.yml` e `terraform-apply-pagamento.yml` são dois workflows
independentes: o primeiro cobre build + testes + qualidade em todo
push/PR (nunca toca em infraestrutura real), o segundo só dispara no
push pra `main` e é quem de fato provisiona/atualiza os recursos na AWS.

- **`.github/workflows/ci.yml`** — roda em todo push (exceto direto em
  `main`) e em PRs para `main`, em três jobs independentes:
  1. **`test`** — instala `requirements-dev.txt` e roda
     `pytest -v --cov=src --cov-fail-under=80` (unit + BDD juntos, ver
     "Rodando os testes" acima), publicando `coverage.xml` como artefato.
  2. **`quality-gate`** — depende do job `test`. Sobe um **SonarQube
     Community Edition efêmero via Docker** (só para a duração deste
     job, sem depender de nenhuma conta/serviço externo), roda o
     `sonar-scanner` (config em `sonar-project.properties`, usando o
     `coverage.xml` do job anterior) e falha o build se o **Quality
     Gate** não vier `OK` — o gate padrão do SonarQube ("Sonar way") já
     cobre cobertura ≥ 80% em código novo (que, numa análise sempre "do
     zero" como essa, é o código inteiro), além de bugs, vulnerabilidades,
     code smells e duplicação. Não precisa de nenhum secret novo — a
     senha de admin usada é local ao container, que é destruído no final
     do job.

     > **Ainda não é required status check.** Como o SonarQube sobe do
     > zero a cada execução (com Elasticsearch embutido), esse job é mais
     > sujeito a timing/flakiness do que `test`/`validate-terraform`. Por
     > enquanto ele fica **informativo** — aparece no PR mas não bloqueia
     > merge. A recomendação é observar algumas execuções reais e só
     > então promovê-lo a required status check em Settings → Branches
     > (mesmo lugar onde `Testes unitários` e `Validar Terraform` já
     > estão configurados).
  3. **`validate-terraform`** — empacota a Lambda e roda
     `terraform fmt -check` + `terraform init -backend=false` +
     `terraform validate` dentro de `terraform/`. Não precisa de
     credenciais AWS.

  Nenhum desses três jobs precisa de credenciais AWS nem toca em infra
  real — só o workflow abaixo faz isso.
- **`.github/workflows/terraform-apply-pagamento.yml`** — dispara no push
  pra `main` (ou seja, no merge do PR): empacota a Lambda (`Build Lambda
  package`) e roda `terraform init`/`plan`/`apply` de verdade, criando/
  atualizando a Lambda, o gatilho SQS e a regra do EventBridge que aciona o
  polling. Depende de Secrets/Variables configurados no repositório (veja
  abaixo) e do resultado ainda é incerto: a AWS Academy pode não liberar
  `lambda:CreateFunction`/`events:*` pro usuário `voclabs`, mesmo com a
  Lambda usando a `LabRole` como execution role — é o mesmo tipo de
  bloqueio de permissão já visto no
  [`oficina-pagamento-infras`](https://github.com/jaquelineramosit/oficina-pagamento-infras)
  pras filas SQS.

### Secrets e Variables necessários no GitHub (Settings → Secrets and variables → Actions)

**Secrets:**

| Secret | Descrição |
|--------|-----------|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` | Credenciais AWS (mesmas do `oficina-pagamento-infras`) |
| `AWS_REGION` | Região AWS |
| `TF_STATE_BUCKET` | Bucket S3 do state Terraform (pode ser o mesmo do outro repo, com chave de state diferente) |
| `MP_ACCESS_TOKEN` | Access Token do Mercado Pago |

**Variables** (copiadas manualmente dos outputs do `oficina-pagamento-infras`
depois que o workflow de apply de lá rodar — veja o README daquele
repositório):

| Variable | De onde vem |
|----------|-------------|
| `SOLICITAR_QUEUE_ARN` | `terraform -chdir=terraform output` → `sqs_pagamento_solicitar_arn` |
| `EFETUADO_QUEUE_URL` | idem, `sqs_pagamento_efetuado_url` |
| `RECUSADO_QUEUE_URL` | idem, `sqs_pagamento_recusado_url` |
| `SOLICITAR_DLQ_QUEUE_URL` | idem, fila `sqs-pagamento-solicitar-dlq` — **opcional por enquanto**: o `oficina-pagamento-infras` cria essa fila mas ainda não expõe um output para ela em `outputs.tf`; esta variable fica vazia até que esse output seja adicionado lá |
| `ORDERS_TABLE_NAME` | idem, `dynamodb_table_name` |
| `ENVIRONMENT` | Opcional (default `dev`) — usada na chave do state Terraform (`oficina-app-pagamento/${ENVIRONMENT}/pagamento/terraform.tfstate`) |
| `PROJECT_NAME` | Opcional (default `oficina`) — repassada como `TF_VAR_project_name` |
| `POLL_ENABLED` | Opcional (default `true`) — feature flag do polling, repassada como `TF_VAR_poll_enabled`. Veja "Ligando/desligando o polling manualmente" abaixo |

## Build e deploy (Terraform)

Você precisa empacotar a Lambda antes do `terraform apply` (o
`.github/workflows/terraform-apply-pagamento.yml` faz isso automaticamente
no step `Build Lambda package`; localmente, replique o mesmo processo):

```bash
rm -rf terraform/build terraform/lambda.zip
mkdir terraform/build
pip install -r requirements.txt -t terraform/build --quiet
cp -R src terraform/build/
(cd terraform/build && zip -qr ../lambda.zip .)
```

```bash
cd terraform
terraform init
terraform apply \
  -var="aws_region=us-east-1" \
  -var="mp_access_token=TEST-xxxxxxx" \
  -var="solicitar_queue_arn=<output do oficina-pagamento-infras>" \
  -var="efetuado_queue_url=<output do oficina-pagamento-infras>" \
  -var="recusado_queue_url=<output do oficina-pagamento-infras>" \
  -var="orders_table_name=orders"
```

`terraform/lambda.tf` usa a `LabRole` da AWS Academy diretamente como
execution role (`role = var.lab_role_arn`), então não tenta criar nenhuma
IAM role nova. `terraform/eventbridge.tf` cria a regra do EventBridge que
aciona o polling (rate configurável via `var.poll_schedule_expression`,
default `rate(10 minutes)`) e a permissão para ela invocar a Lambda.
`var.order_expiration_minutes` (default `10`, repassada como
`ORDER_EXPIRATION_MINUTES` na Lambda) define depois de quantos minutos sem
confirmação uma order pendente é considerada expirada — ver "Decisões de
design" abaixo.

### Ligando/desligando o polling manualmente

`var.poll_enabled` (default `true`) é uma feature flag que controla o
`state` (`ENABLED`/`DISABLED`) da regra `aws_cloudwatch_event_rule.poll_payment_status`
em `terraform/eventbridge.tf`. Com ela em `false`, a regra fica
`DISABLED` e a lambda simplesmente para de ser invocada pelo schedule —
zero execuções, sem precisar mudar nenhum código. O gatilho SQS
(`sqs-pagamento-solicitar`) não é afetado, continua funcionando normalmente.

Formas de alternar:

- **Via GitHub Actions** (recomendado para manter o Terraform state
  consistente): configure a variable `POLL_ENABLED` como `false` em
  Settings → Secrets and variables → Actions → Variables e rode o workflow
  `terraform-apply-pagamento.yml` (push ou `workflow_dispatch`).
- **Via Terraform local**: `terraform apply -var="poll_enabled=false"`
  (mantendo as demais `-var` do comando de deploy).
- **Via AWS CLI, para um desligamento imediato sem esperar um deploy**:
  ```bash
  aws events disable-rule --name oficina-pagamento-poll-status
  # para religar:
  aws events enable-rule --name oficina-pagamento-poll-status
  ```
  Como o `state` da regra é gerenciado pelo Terraform, um toggle feito
  assim aparece como *drift* no próximo `terraform plan`/`apply` — ele só
  se torna permanente se você também atualizar `poll_enabled` na mesma
  direção antes do próximo apply.

**Publicando uma mensagem de teste na fila SQS via AWS CLI:**

```bash
aws sqs send-message \
  --queue-url <SOLICITAR_QUEUE_URL do oficina-pagamento-infras> \
  --message-body file://events/sample_payment_payload.json
```

(crie `events/sample_payment_payload.json` com o mesmo JSON do enunciado, sem
o wrapper de evento SQS — apenas o payload puro).

Para testar sem depender de nenhum deploy real (nem AWS, nem permissões da
Academy), veja a seção "Testando contra o LocalStack" abaixo.

## Filas de saída: `sqs-pagamento-efetuado` e `sqs-pagamento-recusado`

Sempre que o resultado de um pagamento é conhecido, uma mensagem é
publicada numa dessas duas filas para o restante do seu sistema consumir.

**1) Ao criar a order com sucesso (gatilho SQS) — status `efetuado`,
publicado em `sqs-pagamento-efetuado`:**

```json
{
  "order_id": "ORDTST01KWW9Z6D4YVRVAB6VTJWYN33G",
  "external_reference": "order_test_001",
  "status": "efetuado",
  "mercado_pago_status": "action_required",
  "mercado_pago_status_detail": "waiting_transfer",
  "total_amount": "10.00",
  "currency": "BRL",
  "pix": {
    "payment_id": "PAY01KWW9Z6DPSQA8X54AE03DFWSJ",
    "qr_code": "00020126580014br.gov.bcb.pix...",
    "qr_code_base64": "iVBORw0KGgoAAAANSUhEUgAABWQ...",
    "ticket_url": "https://www.mercadopago.com.br/sandbox/payments/.../ticket",
    "date_of_expiration": "2026-07-07T18:10:11.873+00:00"
  },
  "notified_at": "2026-07-06T18:10:12.700Z"
}
```

**2) Se o gateway recusar/falhar ao criar a order (gatilho SQS) — status
`recusado`, publicado em `sqs-pagamento-recusado`:**

```json
{
  "order_id": "order_test_001",
  "external_reference": "order_test_001",
  "status": "recusado",
  "mercado_pago_status": "recusado",
  "mercado_pago_status_detail": "PaymentGatewayError: ...",
  "notified_at": "2026-07-06T18:10:12.700Z"
}
```

Não existe uma Order real do Mercado Pago nesse caso (o gateway falhou
antes de devolver uma), então o registro usa o `external_reference` como
`order_id` — é a única chave disponível para rastrear a tentativa recusada.

> O mesmo status `recusado` também é publicado pelo gatilho de polling
> quando uma order pendente ultrapassa `ORDER_EXPIRATION_MINUTES` sem
> chegar a `processed` (ver "Expiração de orders pendentes" em "Decisões
> de design"). Nesse caso `order_id` é o id real da Order no Mercado Pago
> (ela chegou a ser criada) e `mercado_pago_status` aparece como
> `"recusado"` — o sentinel interno usado pelo sistema, não um status
> nativo do Mercado Pago.

**3) Quando o polling confirma o pagamento (gatilho EventBridge) — status
`pago`, publicado novamente em `sqs-pagamento-efetuado`:**

```json
{
  "order_id": "ORDTST01KWW9Z6D4YVRVAB6VTJWYN33G",
  "external_reference": "order_test_001",
  "status": "pago",
  "mercado_pago_status": "processed",
  "mercado_pago_status_detail": "accredited",
  "total_amount": "10.00",
  "currency": "BRL",
  "notified_at": "2026-07-06T18:12:40.100Z"
}
```

> **Sobre o critério usado para considerar "pago"**: a cada ciclo de
> polling, o gatilho EventBridge só publica `status: "pago"` quando a Order
> consultada em `GET /v1/orders/{id}` retorna `status: "processed"` (o
> padrão documentado pelo Mercado Pago para pagamentos concluídos via
> Orders API). Se, nos seus testes de homologação com Pix, você observar um
> valor diferente de `status` para "pago", ajuste a constante
> `_PAID_STATUS` em
> `src/application/use_cases/check_payment_status.py`. Para outras
> atualizações (order expirada, cancelada etc.) nenhuma mensagem é
> publicada ainda, e a order continua sendo verificada a cada ciclo — é um
> ponto simples de estender caso você precise tratar esses status também
> (ver "Próximos passos sugeridos").

## Testando contra o LocalStack

Suba o LocalStack e crie as filas + tabela usando o
[`oficina-pagamento-infras`](https://github.com/jaquelineramosit/oficina-pagamento-infras)
(consulte o README daquele repositório para o setup local mais atual).

O antigo `terraform-local/` (que publicava a Lambda de verdade no executor
Docker do LocalStack) foi removido. No lugar dele, use uma das opções
abaixo — nenhuma exige Terraform ou o executor Docker de Lambda.

### Opção A — runner do `resources_local/` (recomendada)

O pacote [`resources_local/`](resources_local/README.md) dá long-polling na
fila `sqs-pagamento-solicitar` do LocalStack e chama
`payment_handler.lambda_handler` (o handler real) diretamente em processo a
cada mensagem recebida — mais próximo do comportamento de produção do que
uma invocação avulsa. Veja o [README daquele diretório](resources_local/README.md)
para configuração e uso (`python -m resources_local.local_runner` +
`python -m resources_local.send_message`).

### Opção B — invocação avulsa em processo

1. Exporte as variáveis de ambiente apontando pro LocalStack (qualquer
   valor serve pras credenciais — o LocalStack não valida):

   ```bash
   export AWS_ENDPOINT_URL=http://localhost:4566
   export AWS_ACCESS_KEY_ID=test
   export AWS_SECRET_ACCESS_KEY=test
   export AWS_REGION=us-east-1
   export ORDERS_TABLE_NAME=orders
   export SQS_PAGAMENTO_EFETUADO_QUEUE_URL=<output da fila efetuado>
   export SQS_PAGAMENTO_RECUSADO_QUEUE_URL=<output da fila recusado>
   export SQS_PAGAMENTO_SOLICITAR_DLQ_URL=<output da DLQ solicitar, se já criado>
   export MP_ACCESS_TOKEN=TEST-xxxxxxx  # token de sandbox do Mercado Pago
   ```

   `AWS_ENDPOINT_URL` é reconhecida nativamente pelo boto3/botocore
   (>=1.29) — nenhum código precisa mudar para apontar para o LocalStack em
   vez da AWS real.
2. Invoque `payment_handler.lambda_handler` diretamente num shell Python,
   passando um evento de exemplo (ex. `resources_local/sample_event.json`)
   como primeiro argumento e `None` como contexto.

Confira o resultado (em qualquer uma das opções):

```bash
aws --endpoint-url=http://localhost:4566 dynamodb scan --table-name orders
aws --endpoint-url=http://localhost:4566 sqs receive-message --queue-url <url da fila efetuado/recusado>
```

O Mercado Pago em si **não** é mockado nesse fluxo — as chamadas HTTP vão
para o sandbox real com o token `TEST-...`, já que é um sistema externo ao
domínio de Pagamento.

## Decisões de design e pontos de atenção

- **Serverless por decisão, não por omissão — sem Kubernetes**: este
  serviço roda inteiramente como Lambda (SQS + EventBridge como gatilhos),
  provisionada via Terraform. Não há Dockerfile de aplicação nem manifests
  de Kubernetes neste repositório, e essa é uma escolha arquitetural
  deliberada para uma carga de trabalho orientada a filas/polling, não uma
  lacuna. Se o requisito de "deploy automatizado em ambiente Kubernetes"
  do seu trabalho se aplica a este serviço especificamente (e não a outro
  componente do sistema mais amplo), isso exigiria uma reescrita real —
  containerizar um consumer de longa duração para a fila `sqs-pagamento-
  solicitar` e um `CronJob` para o polling — que ainda não foi feita aqui.
- **Idempotência determinística por `external_reference`**: a
  `X-Idempotency-Key` enviada ao Mercado Pago é derivada do
  `external_reference` do pedido (`uuid5`), e não é mais um UUID aleatório.
  Isso é o que torna seguro reprocessar a mesma mensagem SQS do início ao
  fim (por exemplo, se a chamada `notify(...)` do passo 5 falhar depois da
  order já ter sido criada): o Mercado Pago recebe a mesma chave e devolve a
  order já existente, em vez de criar uma duplicada. Se dois pedidos
  diferentes puderem compartilhar o mesmo `external_reference` no seu
  sistema, revise essa premissa antes de ir para produção.
- **Partial Batch Response (SQS)**: o gatilho SQS usa
  `ReportBatchItemFailures`, então, em um lote de 10 mensagens, se apenas uma
  falhar por erro de infraestrutura, só ela retorna para a fila — as demais
  não são reprocessadas. Uma recusa do gateway (`PaymentGatewayError`) não
  entra nesse retry: é um resultado de negócio definitivo, tratado e
  publicado em `sqs-pagamento-recusado` dentro do próprio use case. Se um
  `PaymentGatewayError` escapar do use case por algum outro motivo (rede de
  segurança para bugs, já que no fluxo normal ele nunca chega ao handler), o
  handler trata da mesma forma — via
  `CreatePaymentOrderUseCase.handle_gateway_error_as_recusado` — em vez de
  reprocessar indefinidamente; só entra em retry se essa própria tentativa de
  registrar a recusa falhar (erro de infra).
- **Payload inválido vai para a DLQ, não é retentado**: um
  `DomainValidationError` (campo obrigatório ausente, tipo errado etc.) nunca
  vai "se corrigir sozinho" com um retry, então a mensagem é removida da fila
  `sqs-pagamento-solicitar` sem reprocessamento — mas, em vez de descartar o
  payload, o `sqs_handler.py` publica o corpo original + o motivo do erro
  diretamente na DLQ (`SQS_PAGAMENTO_SOLICITAR_DLQ_URL`) para investigação
  manual. Se a própria publicação na DLQ falhar, a mensagem é marcada para
  retry (para não perdê-la de vez).
- **Polling em vez de webhook**: a aplicação não expõe mais nenhum endpoint
  HTTP público — é ela quem periodicamente pergunta ao Mercado Pago pelo
  status de cada order pendente (`GET /v1/orders/{id}`), via
  `polling_handler.py` acionado pelo EventBridge. Isso elimina a
  necessidade de validar assinatura de requisição (não há mais requisição
  de entrada de terceiros) e de responder rápido a um caller externo — o
  único trade-off é a latência entre o pagamento ser processado no Mercado
  Pago e a próxima execução do polling detectar isso (hoje até
  `var.poll_schedule_expression`, default `rate(10 minutes)`).
- **Expiração de orders pendentes**: `CheckPaymentStatusUseCase` compara
  `Order.created_date` (retornado pelo Mercado Pago na criação) com o
  instante atual — se passaram mais de `ORDER_EXPIRATION_MINUTES` (default
  `10`, propositalmente curto para facilitar a homologação/demo deste
  trabalho — em produção considere um valor mais próximo do
  `date_of_expiration` real do Pix) sem a order chegar a `processed`, ela é
  marcada localmente como `PaymentStatus.RECUSADO`, publicada em
  `sqs-pagamento-recusado` e passa a ser ignorada por
  `list_pending_orders()` — ou seja, o polling para de verificá-la.
  Orders sem `created_date` (nenhum caso hoje, já que só orders reais do
  Mercado Pago entram nesse fluxo) nunca expiram por segurança.
- **Falha ao publicar nas filas de saída conta como falha do processamento**:
  `SQSPaymentStatusNotifier.notify(...)` é chamado depois de persistir a
  order/atualizar o status — se o `send_message` falhar (ex. erro transitório
  no SQS), a exceção sobe e a mensagem original (da fila de entrada) ou a
  execução do polling são tratadas como falha. No gatilho SQS, isso é seguro
  graças à idempotência determinística explicada acima (inclusive no
  caminho de recusa, que persiste/notifica usando o `external_reference`
  como chave). No polling, reprocessar é sempre seguro, pois `get_order` e
  `update_order_status` são idempotentes por natureza (apenas leem/
  sobrescrevem o estado mais atual da order) — uma falha numa order não
  impede as demais de serem verificadas no mesmo ciclo, e a order que falhou
  simplesmente é tentada de novo no próximo.
- **DynamoDB como repositório padrão**: escolhido por ser serverless e sem
  necessidade de gerenciar conexões/VPC a partir da Lambda. Se seu sistema já
  usa outro banco (RDS, etc.), basta criar um novo adapter que implemente
  `OrderRepositoryPort` — os casos de uso e os handlers não precisam mudar.

## Próximos passos sugeridos

- Mover `MP_ACCESS_TOKEN` para o Secrets Manager e buscá-lo no cold start
  da lambda (com cache em variável de módulo).
- Adicionar um alarme de CloudWatch na DLQ (`sqs-pagamento-solicitar-dlq`)
  para saber quando mensagens estão sendo definitivamente descartadas.
- Se o volume de orders pendentes crescer muito, trocar o `scan` do
  `list_pending_orders` por uma query num GSI por `status`, e/ou paralelizar
  as chamadas ao Mercado Pago dentro do `polling_handler.py`.
