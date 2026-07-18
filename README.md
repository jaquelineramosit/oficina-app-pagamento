# Integração de Pagamentos Pix — Mercado Pago (AWS Lambda, Python 3.12, Arquitetura Hexagonal)

Uma única Lambda (`oficina-pagamento`) com dois gatilhos, que juntos criam e
acompanham pagamentos Pix usando a **Orders API** do Mercado Pago:

1. **Gatilho SQS** — consome mensagens da fila `sqs-pagamento-solicitar`,
   valida o payload e cria a Order no Mercado Pago (`POST /v1/orders`). Em
   caso de sucesso, publica em `sqs-pagamento-efetuado` (status
   **`efetuado`**); se o gateway recusar/falhar, publica em
   `sqs-pagamento-recusado` (status **`recusado`**) — em ambos os casos o
   resultado é persistido no DynamoDB antes da publicação.
2. **Gatilho API Gateway (webhook)** — recebe as notificações do Mercado
   Pago no tópico `order`, confirma em até 200/201, busca o recurso completo
   (`GET /v1/orders/{id}`), atualiza o status do pedido e, quando o
   pagamento é confirmado, publica novamente em `sqs-pagamento-efetuado`
   (status **`pago`**).

O mesmo `lambda_handler` (`payment_handler.py`) despacha para a lógica
certa conforme o formato do evento recebido — ver `Arquitetura` abaixo.

```
                          ┌────────────────────────┐        ┌───────────────────┐
   sqs-pagamento-solicitar│                        │──────▶ │ Mercado Pago API  │
 ─────────────────────▶  │    oficina-pagamento     │        └─────────┬─────────┘
                          │   (payment_handler.py)   │                  │
                          │  gatilho 1: fila SQS      │                  │ webhook (order)
                          │  gatilho 2: API Gateway   │ ◀────────────────┘
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
│       └── process_order_webhook.py    # Fluxo do webhook (confirmação de pago)
│
└── infrastructure/                # Adapters — implementações concretas
    ├── config.py                       # Leitura de variáveis de ambiente
    ├── adapters/
    │   ├── mercado_pago_gateway.py          # Implementa PaymentGatewayPort (requests)
    │   ├── dynamodb_order_repository.py     # Implementa OrderRepositoryPort (boto3)
    │   ├── sqs_payment_status_notifier.py   # Implementa PaymentStatusNotifierPort (boto3)
    │   └── sqs_dead_letter_publisher.py     # Implementa DeadLetterPublisherPort (boto3)
    ├── security/
    │   └── webhook_signature.py         # Validação HMAC do header x-signature
    └── handlers/
        ├── payment_handler.py           # Entry point ÚNICO da Lambda oficina-pagamento (dispatcher)
        ├── sqs_handler.py               # Lógica do gatilho SQS (chamada pelo dispatcher)
        └── webhook_handler.py           # Lógica do gatilho webhook (chamada pelo dispatcher)
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
- `sqs_handler.py`/`webhook_handler.py` continuam sendo dois módulos com uma
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
- A chave secreta do webhook (painel **Webhooks** da aplicação no Mercado Pago)

## Variáveis de ambiente

| Variável                          | Usada por           | Obrigatória | Descrição |
|------------------------------------|----------------------|:-----------:|-----------|
| `MP_ACCESS_TOKEN`                  | os dois gatilhos      | ✅ | Bearer token da API do Mercado Pago |
| `MP_WEBHOOK_SECRET`                | gatilho webhook       | recomendada | Secret para validar o header `x-signature` |
| `MP_API_BASE_URL`                  | os dois gatilhos      | não (default `https://api.mercadopago.com`) | Útil para apontar a um mock em testes |
| `ORDERS_TABLE_NAME`                | os dois gatilhos      | não (default `orders`) | Nome da tabela DynamoDB |
| `SQS_PAGAMENTO_EFETUADO_QUEUE_URL` | os dois gatilhos      | ✅ (setado automaticamente pelo `terraform/`) | URL da fila `sqs-pagamento-efetuado` |
| `SQS_PAGAMENTO_RECUSADO_QUEUE_URL` | gatilho SQS           | ✅ (setado automaticamente pelo `terraform/`) | URL da fila `sqs-pagamento-recusado` |
| `SQS_PAGAMENTO_SOLICITAR_DLQ_URL`  | gatilho SQS           | recomendada | URL da DLQ `sqs-pagamento-solicitar-dlq`, usada para preservar payloads inválidos (`DomainValidationError`) |
| `MP_HTTP_TIMEOUT_SECONDS`          | os dois gatilhos      | não (default `10`) | Timeout das chamadas HTTP ao Mercado Pago |
| `AWS_ENDPOINT_URL`                 | os dois gatilhos      | não | Aponta o boto3 para o LocalStack em vez da AWS real (ver seção "Testando contra o LocalStack") |

> Em produção, prefira buscar `MP_ACCESS_TOKEN` e `MP_WEBHOOK_SECRET` do
> **AWS Secrets Manager** ou **SSM Parameter Store** em vez de variáveis de
> ambiente em texto plano. No `terraform/`, esses dois valores já são
> `variable`s `sensitive = true` para facilitar essa migração depois.

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

Os testes cobrem:
- Validação de todos os campos obrigatórios do payload (`test_entities.py`)
- O caso de uso de criação de order, com o gateway/repositório mockados
  (`test_create_payment_order.py`)
- O caso de uso de processamento do webhook (`test_process_order_webhook.py`)
- A validação de assinatura HMAC (`test_webhook_signature.py`)
- Os dois `lambda_handler` de ponta a ponta, com dependências externas
  mockadas (`test_sqs_handler.py`, `test_webhook_handler.py`)

## CI/CD (GitHub Actions)

- **`.github/workflows/ci.yml`** — roda em todo push (exceto direto em
  `main`) e em PRs para `main`: `pytest -v` e, num job separado,
  `terraform fmt -check` + `terraform init -backend=false` +
  `terraform validate` dentro de `terraform/`. Não precisa de credenciais
  AWS.
- **`.github/workflows/terraform-apply-pagamento.yml`** — dispara no push
  pra `main` (ou seja, no merge do PR): `terraform init`/`plan`/`apply` de
  verdade, criando/atualizando a Lambda, o gatilho SQS e o endpoint de
  webhook. Depende de Secrets/Variables configurados no repositório (veja
  abaixo) e do resultado ainda é incerto: a AWS Academy pode não liberar
  `lambda:CreateFunction`/`apigateway:*` pro usuário `voclabs`, mesmo com a
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
| `MP_WEBHOOK_SECRET` | Secret do webhook (pode ficar vazio) |

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

## Build e deploy (Terraform)

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

`terraform/main.tf` empacota a Lambda sozinho (instala `requirements.txt`
em `build/`, copia `src/` e zipa — sem precisar do SAM CLI) e usa a
`LabRole` da AWS Academy diretamente como execution role (`role =
var.lab_role_arn`), então não tenta criar nenhuma IAM role nova.

Ao final, `terraform output` mostra a URL do endpoint de webhook gerado
pelo API Gateway (formato
`https://{api-id}.execute-api.{region}.amazonaws.com/api/webhooks/mercadopago`
— API Gateway HTTP API, sem prefixo de stage tipo `/Prod`).

### Apontando seu domínio customizado para o webhook

Para usar um domínio próprio em vez da URL gerada pelo API Gateway:

1. Solicite/valide um certificado no **AWS Certificate Manager (ACM)** para
   o domínio/subdomínio desejado.
2. Crie um `aws_apigatewayv2_domain_name` + `aws_apigatewayv2_api_mapping`
   apontando pro `aws_apigatewayv2_api.webhook` deste `terraform/`.
3. No seu provedor de DNS, crie um registro `CNAME`/`ALIAS` apontando para
   o endpoint regional gerado pelo domínio customizado.
4. Só depois disso, configure a URL final no painel de Webhooks do Mercado
   Pago com o tópico **Orders (order)**.

**Testando o webhook já implantado, via curl:**

```bash
curl -i -X POST <webhook_endpoint do terraform output> \
  -H "Content-Type: application/json" \
  -d '{"action": "order.updated", "type": "order", "data": {"id": "ORDTST01KWW9Z6D4YVRVAB6VTJWYN33G"}}'
```

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

**3) Quando o webhook confirma o pagamento (gatilho webhook) — status
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

> **Sobre o critério usado para considerar "pago"**: o webhook do tópico
> `order` é disparado em qualquer atualização da order (não só quando ela é
> paga — também pode disparar em expiração, cancelamento etc.). Por isso, o
> gatilho webhook só publica `status: "pago"` quando a Order consultada em
> `GET /v1/orders/{id}` retorna `status: "processed"` e
> `status_detail: "accredited"` (o padrão documentado pelo Mercado Pago para
> pagamentos concluídos via Orders API). Se, nos seus testes de homologação
> com Pix, você observar uma combinação diferente de `status`/`status_detail`
> para "pago", ajuste as constantes `_PAID_STATUS` e `_PAID_STATUS_DETAIL` em
> `src/application/use_cases/process_order_webhook.py`. Para outras
> atualizações (order expirada, cancelada etc.) nenhuma mensagem é publicada
> ainda — é um ponto simples de estender caso você precise desses status
> também nas filas de saída.

## Testando contra o LocalStack

> **Seção em revisão**: este repositório usava um `terraform-local/` para
> publicar a Lambda de verdade no LocalStack (Opção B), mas esse diretório
> foi removido e ainda não tem substituto documentado — o diretório
> `resources_local/` que está tomando o lugar dele (scripts Python puros,
> sem Terraform) ainda está em construção. Até essa migração terminar, use
> a Opção A abaixo (invocar o código em processo) para testar contra o
> LocalStack.

Suba o LocalStack e crie as filas + tabela usando o
[`oficina-pagamento-infras`](https://github.com/jaquelineramosit/oficina-pagamento-infras)
(consulte o README daquele repositório para o setup local mais atual).

### Invocar em processo (sem publicar nada, sem Terraform nem executor Docker de Lambda)

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
2. Invoque o handler chamando `payment_handler.lambda_handler` diretamente
   com um evento de exemplo (`events/sqs_event.json` ou
   `events/webhook_event.json`) — o script anterior usado para isso
   (`scripts/local_invoke.py`) foi removido nesta migração; use
   `resources_local/` ou um script equivalente até a documentação dessa
   parte ser atualizada.

Confira o resultado:

```bash
aws --endpoint-url=http://localhost:4566 dynamodb scan --table-name orders
aws --endpoint-url=http://localhost:4566 sqs receive-message --queue-url <url da fila efetuado/recusado>
```

O Mercado Pago em si **não** é mockado nesse fluxo — as chamadas HTTP vão
para o sandbox real com o token `TEST-...`, já que é um sistema externo ao
domínio de Pagamento.

## Decisões de design e pontos de atenção

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
- **Resposta rápida ao Mercado Pago (webhook)**: a documentação exige resposta
  em até ~22s. O fluxo atual (`get_order` + `update_item` no DynamoDB) é
  rápido o bastante na prática, mas se no futuro o processamento pós-webhook
  ficar mais pesado (ex. disparar e-mails, notificar outros sistemas),
  considere responder 200 imediatamente após validar a assinatura e mover o
  processamento pesado para uma fila SQS separada, desacoplando o "avisar
  recebimento" do "processar".
- **Validação de assinatura do webhook**: implementada em
  `webhook_signature.py`, seguindo o algoritmo HMAC-SHA256 documentado pelo
  Mercado Pago. Só é pulada se `MP_WEBHOOK_SECRET` não estiver configurado —
  configure-a em produção.
- **Falha ao publicar nas filas de saída conta como falha do processamento**:
  `SQSPaymentStatusNotifier.notify(...)` é chamado depois de persistir a
  order/atualizar o status — se o `send_message` falhar (ex. erro transitório
  no SQS), a exceção sobe e a mensagem original (da fila de entrada ou do
  webhook) é tratada como falha, gerando retry. No gatilho SQS, isso é seguro
  graças à idempotência determinística explicada acima (inclusive no
  caminho de recusa, que persiste/notifica usando o `external_reference`
  como chave). No gatilho webhook, reprocessar é sempre seguro, pois
  `get_order` e `update_order_status` são idempotentes por natureza (apenas
  leem/sobrescrevem o estado mais atual da order).
- **DynamoDB como repositório padrão**: escolhido por ser serverless e sem
  necessidade de gerenciar conexões/VPC a partir da Lambda. Se seu sistema já
  usa outro banco (RDS, etc.), basta criar um novo adapter que implemente
  `OrderRepositoryPort` — os casos de uso e os handlers não precisam mudar.

## Próximos passos sugeridos

- Mover `MP_ACCESS_TOKEN`/`MP_WEBHOOK_SECRET` para o Secrets Manager e
  buscá-los no cold start da lambda (com cache em variável de módulo).
- Adicionar um alarme de CloudWatch na DLQ (`sqs-pagamento-solicitar-dlq`)
  para saber quando mensagens estão sendo definitivamente descartadas.
- Se o volume justificar, considerar processar o webhook de forma assíncrona
  (API Gateway → SQS → Lambda) para desacoplar totalmente a resposta HTTP do
  processamento.
