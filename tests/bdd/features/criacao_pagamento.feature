# language: pt
Funcionalidade: Criação de pagamento Pix via fila SQS
  Como sistema de pagamentos
  Quero criar uma Order Pix no Mercado Pago ao receber uma solicitação
  Para que o restante do sistema saiba se o pagamento foi efetuado ou recusado

  Cenário: Pagamento criado com sucesso é publicado como efetuado
    Dado uma solicitação de pagamento válida para o pedido "order_bdd_001"
    Quando a solicitação é processada
    Então uma Order é criada no Mercado Pago
    E o resultado é persistido no repositório de orders
    E uma notificação de status "efetuado" é publicada

  Cenário: Recusa do gateway é publicada como recusado
    Dado uma solicitação de pagamento válida para o pedido "order_bdd_002"
    E o gateway de pagamento vai recusar a solicitação
    Quando a solicitação é processada
    Então uma notificação de status "recusado" é publicada
    E a tentativa recusada é registrada usando o external_reference como identificador
