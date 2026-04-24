provider "aws" {
  region = "ap-southeast-2"
}

# Dead Letter Queue
resource "aws_sqs_queue" "order_dlq" {
  name = "careplan-order-dlq"
}

# 主队列，失败 3 次就移到 DLQ
resource "aws_sqs_queue" "order_queue" {
  name = "careplan-order-queue"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.order_dlq.arn
    maxReceiveCount     = 3
  })
}

# RDS PostgreSQL 数据库
resource "aws_db_instance" "careplan_db" {
  identifier        = "careplan"
  engine            = "postgres"
  engine_version    = "17.4"
  instance_class    = "db.t3.micro"
  allocated_storage = 20

  db_name  = "careplan"
  username = "postgres"
  password = var.db_password

  skip_final_snapshot = true
  publicly_accessible = true

  tags = {
    Name = "careplan-db"
  }
}

# Lambda 执行权限
resource "aws_iam_role" "lambda_role" {
  name = "careplan-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# 给 Lambda 权限：写日志、操作 SQS、操作 RDS
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_sqs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSQSFullAccess"
}

resource "aws_iam_role_policy_attachment" "lambda_rds" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonRDSFullAccess"
}


# Lambda: create_order
resource "aws_lambda_function" "create_order" {
  filename         = "lambda_functions/create_order.zip"
  function_name    = "careplan-create-order"
  role             = aws_iam_role.lambda_role.arn
  handler          = "create_order.handler"
  runtime          = "python3.11"

  environment {
    variables = {
      SQS_QUEUE_URL = aws_sqs_queue.order_queue.url
      DB_HOST       = aws_db_instance.careplan_db.address
      DB_NAME       = "careplan"
      DB_USER       = "postgres"
      DB_PASSWORD   = var.db_password
    }
  }
}

# Lambda: generate_careplan
resource "aws_lambda_function" "generate_careplan" {
  filename         = "lambda_functions/generate_careplan.zip"
  function_name    = "careplan-generate-careplan"
  role             = aws_iam_role.lambda_role.arn
  handler          = "generate_careplan.handler"
  runtime          = "python3.11"

  environment {
    variables = {
      DB_HOST     = aws_db_instance.careplan_db.address
      DB_NAME     = "careplan"
      DB_USER     = "postgres"
      DB_PASSWORD = var.db_password
    }
  }
}

# Lambda: get_order
resource "aws_lambda_function" "get_order" {
  filename         = "lambda_functions/get_order.zip"
  function_name    = "careplan-get-order"
  role             = aws_iam_role.lambda_role.arn
  handler          = "get_order.handler"
  runtime          = "python3.11"

  environment {
    variables = {
      DB_HOST     = aws_db_instance.careplan_db.address
      DB_NAME     = "careplan"
      DB_USER     = "postgres"
      DB_PASSWORD = var.db_password
    }
  }
}

# SQS 触发 generate_careplan Lambda
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.order_queue.arn
  function_name    = aws_lambda_function.generate_careplan.arn
  batch_size       = 1
}

# API Gateway
resource "aws_apigatewayv2_api" "careplan_api" {
  name          = "careplan-api"
  protocol_type = "HTTP"
}

# 连接 create_order Lambda
resource "aws_apigatewayv2_integration" "create_order" {
  api_id             = aws_apigatewayv2_api.careplan_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.create_order.invoke_arn
}

# 连接 get_order Lambda
resource "aws_apigatewayv2_integration" "get_order" {
  api_id             = aws_apigatewayv2_api.careplan_api.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.get_order.invoke_arn
}

# 路由：POST /orders → create_order
resource "aws_apigatewayv2_route" "post_orders" {
  api_id    = aws_apigatewayv2_api.careplan_api.id
  route_key = "POST /orders"
  target    = "integrations/${aws_apigatewayv2_integration.create_order.id}"
}

# 路由：GET /orders/{id} → get_order
resource "aws_apigatewayv2_route" "get_orders" {
  api_id    = aws_apigatewayv2_api.careplan_api.id
  route_key = "GET /orders/{id}"
  target    = "integrations/${aws_apigatewayv2_integration.get_order.id}"
}

# 部署 stage
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.careplan_api.id
  name        = "$default"
  auto_deploy = true
}

# 给 API Gateway 权限调用 Lambda
resource "aws_lambda_permission" "apigw_create_order" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.create_order.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.careplan_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_get_order" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_order.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.careplan_api.execution_arn}/*/*"
}

# 输出 API 的 URL
output "api_url" {
  value = aws_apigatewayv2_stage.default.invoke_url
}