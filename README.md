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
 ─────────────────────▶  │     PagamentoFunction    │        └─────────┬─────────┘
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
│   │   └── payment_status_notifier_port.py # Interface: publicar em efetuado/recusado
│   └── use_cases/
│       ├── create_payment_order.py     # Fluxo da fila SQS (efetuado/recusado)
│       └── process_order_webhook.py    # Fluxo do webhook (confirmação de pago)
│
└── infrastructure/                # Adapters — implementações concretas
    ├── config.py                       # Leitura de variáveis de ambiente
    ├── adapters/
    │   ├── mercado_pago_gateway.py          # Implementa PaymentGatewayPort (requests)
    │   ├── dynamodb_order_repository.py     # Implementa OrderRepositoryPort (boto3)
    │   └── sqs_payment_status_notifier.py   # Implementa PaymentStatusNotifierPort (boto3)
    ├── security/
    │   └── webhook_signature.py         # Validação HMAC do header x-signature
    └── handlers/
        ├── payment_handler.py           # Entry point ÚNICO da PagamentoFunction (dispatcher)
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
  diretamente pelo `template.yaml`; quem é chamado pela AWS é sempre
  `payment_handler.lambda_handler`, que despacha para um dos dois conforme o
  formato do evento recebido (fila SQS sempre tem a chave `"Records"`).

## Pré-requisitos

- Python 3.12+
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Docker (usado pelo SAM para build/execução local fiel ao ambiente Lambda)
- Uma conta AWS configurada (`aws configure`)
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
| `SQS_PAGAMENTO_EFETUADO_QUEUE_URL` | os dois gatilhos      | ✅ (setado automaticamente pelo `template.yaml`) | URL da fila `sqs-pagamento-efetuado` |
| `SQS_PAGAMENTO_RECUSADO_QUEUE_URL` | gatilho SQS           | ✅ (setado automaticamente pelo `template.yaml`) | URL da fila `sqs-pagamento-recusado` |
| `MP_HTTP_TIMEOUT_SECONDS`          | os dois gatilhos      | não (default `10`) | Timeout das chamadas HTTP ao Mercado Pago |
| `AWS_ENDPOINT_URL`                 | os dois gatilhos      | não | Aponta o boto3 para o LocalStack em vez da AWS real (ver seção "Testando contra o LocalStack") |

> Em produção, prefira buscar `MP_ACCESS_TOKEN` e `MP_WEBHOOK_SECRET` do
> **AWS Secrets Manager** ou **SSM Parameter Store** em vez de variáveis de
> ambiente em texto plano. O `template.yaml` já isola esses valores como
> `Parameters` com `NoEcho: true` para facilitar essa migração depois.

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

## Build e deploy (AWS SAM)

```bash
sam build
sam deploy --guided
```

No modo `--guided`, informe:
- **Stack Name**: ex. `mp-pix-integration`
- **AWS Region**: a região onde deseja implantar
- **MercadoPagoAccessToken**: seu Access Token
- **MercadoPagoWebhookSecret**: o secret do painel de Webhooks (pode deixar
  em branco em ambiente de teste, mas configure em produção)
- Confirme a criação de roles do IAM (`CAPABILITY_IAM`)

Ao final, o SAM mostra os **Outputs**: a URL da fila SQS e a URL do endpoint
de webhook gerado pelo API Gateway.

### Apontando seu domínio customizado para o webhook

Você mencionou o endpoint `https://kortextecnologia.com.br/api/webhooks/mercadopago`.
O API Gateway gera, por padrão, uma URL do tipo
`https://{api-id}.execute-api.{region}.amazonaws.com/Prod/api/webhooks/mercadopago`.
Para usar seu próprio domínio:

1. Solicite/valide um certificado no **AWS Certificate Manager (ACM)** para
   `kortextecnologia.com.br` (ou um subdomínio dedicado, ex.
   `api.kortextecnologia.com.br`).
2. Crie um **Custom Domain Name** no API Gateway apontando esse certificado.
3. Crie um **Base Path Mapping** ligando o domínio customizado ao stage
   `Prod` desta API.
4. No seu provedor de DNS, crie um registro `CNAME`/`ALIAS` apontando
   `kortextecnologia.com.br` (ou o subdomínio escolhido) para o endpoint
   regional/edge gerado pelo Custom Domain Name.
5. Só depois disso, configure a URL final no painel de Webhooks do Mercado
   Pago com o tópico **Orders (order)**.

## Testando localmente (sem deploy)

Como agora existe uma única função (`PagamentoFunction`), o `--event`
escolhido é que determina qual gatilho é simulado (`payment_handler.py`
despacha pelo formato do evento).

**Simulando o gatilho SQS** com o evento de exemplo em `events/sqs_event.json`:

```bash
sam local invoke PagamentoFunction \
  --event events/sqs_event.json \
  --parameter-overrides MercadoPagoAccessToken=TEST-xxxxxxx
```

**Simulando o gatilho webhook** com o evento de exemplo em `events/webhook_event.json`:

```bash
sam local invoke PagamentoFunction \
  --event events/webhook_event.json \
  --parameter-overrides MercadoPagoAccessToken=TEST-xxxxxxx MercadoPagoWebhookSecret=""
```

> Deixe `MercadoPagoWebhookSecret` vazio localmente para pular a validação de
> assinatura, já que gerar um `x-signature` válido manualmente exige calcular
> o HMAC — veja `tests/unit/test_webhook_signature.py` para um exemplo de como
> essa assinatura é gerada.

**Testando o webhook já implantado, via curl:**

```bash
curl -i -X POST https://kortextecnologia.com.br/api/webhooks/mercadopago \
  -H "Content-Type: application/json" \
  -d '{"action": "order.updated", "type": "order", "data": {"id": "ORDTST01KWW9Z6D4YVRVAB6VTJWYN33G"}}'
```

**Publicando uma mensagem de teste na fila SQS via AWS CLI:**

```bash
aws sqs send-message \
  --queue-url <URL_DA_FILA_NO_OUTPUT_DO_SAM_DEPLOY> \
  --message-body file://events/sample_payment_payload.json
```

(crie `events/sample_payment_payload.json` com o mesmo JSON do enunciado, sem
o wrapper de evento SQS — apenas o payload puro).

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

Para testar de ponta a ponta (SQS + DynamoDB + esta Lambda) sem depender de
uma conta AWS real, use o ambiente local do
[`oficina-infra-pagamento`](https://github.com/jaquelineramosit/oficina-infra-pagamento)
(LocalStack via Docker):

1. No repositório `oficina-infra-pagamento`: `docker compose up -d` e
   depois `terraform -chdir=terraform-local apply` — isso cria as 3 filas
   e a tabela `orders` no LocalStack. Anote as URLs de saída
   (`terraform -chdir=terraform-local output`).
2. Neste repositório, exporte as variáveis de ambiente apontando para o
   LocalStack (qualquer valor serve para as credenciais — o LocalStack não
   valida):

   ```bash
   export AWS_ENDPOINT_URL=http://localhost:4566
   export AWS_ACCESS_KEY_ID=test
   export AWS_SECRET_ACCESS_KEY=test
   export AWS_REGION=us-east-1
   export ORDERS_TABLE_NAME=orders
   export SQS_PAGAMENTO_EFETUADO_QUEUE_URL=<output da fila efetuado>
   export SQS_PAGAMENTO_RECUSADO_QUEUE_URL=<output da fila recusado>
   export MP_ACCESS_TOKEN=TEST-xxxxxxx  # token de sandbox do Mercado Pago
   ```

   `AWS_ENDPOINT_URL` é reconhecida nativamente pelo boto3/botocore
   (>=1.29) — nenhum código precisa mudar para apontar para o LocalStack em
   vez da AWS real.
3. Rode o dispatcher direto, sem precisar do SAM/Docker:

   ```bash
   python scripts/local_invoke.py
   ```

   O script carrega `events/sqs_event.json`, chama
   `payment_handler.lambda_handler` e imprime o resultado. Confira o item
   gravado (`aws --endpoint-url=$AWS_ENDPOINT_URL dynamodb scan --table-name orders`)
   e a mensagem publicada
   (`aws --endpoint-url=$AWS_ENDPOINT_URL sqs receive-message --queue-url $SQS_PAGAMENTO_EFETUADO_QUEUE_URL`).

   `sam local invoke` (seção anterior) continua funcionando como
   alternativa de maior fidelidade ao runtime da Lambda — nesse caso, passe
   as mesmas variáveis via `--parameter-overrides`/`--env-vars` e use
   `--docker-network` para a rede do container do LocalStack.

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
  publicado em `sqs-pagamento-recusado` dentro do próprio use case.
- **Payload inválido não é retentado**: um `DomainValidationError` (campo
  obrigatório ausente, tipo errado etc.) nunca vai "se corrigir sozinho" com
  um retry, então a mensagem é removida da fila e o erro fica só no
  CloudWatch Logs. Se você quiser nunca perder esse tipo de mensagem para
  auditoria, é fácil estender `sqs_handler.py` para publicar o payload
  inválido em uma fila/tópico/bucket de "mensagens rejeitadas" antes de
  descartar.
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
