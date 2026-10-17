terraform {
  required_version = ">= 1.6, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.69"
    }
  }
}
provider "aws" {
  region = var.region
  default_tags { tags = { Project = "incident-assistant-poc", ManagedBy = "Terraform" } }
}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
locals {
  account   = data.aws_caller_identity.current.account_id
  partition = data.aws_partition.current.partition
  titan_arn = "arn:${local.partition}:bedrock:${var.region}::foundation-model/amazon.titan-embed-text-v2:0"
  nova_arn  = "arn:${local.partition}:bedrock:${var.region}::foundation-model/${var.generation_model_id}"
}
resource "aws_s3_bucket" "source" {
  bucket_prefix = "${var.name}-source-"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "source" {
  bucket                  = aws_s3_bucket.source.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "source" {
  bucket = aws_s3_bucket.source.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_policy" "source_tls" {
  bucket = aws_s3_bucket.source.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Deny", Principal = "*", Action = "s3:*"
    Resource  = [aws_s3_bucket.source.arn, "${aws_s3_bucket.source.arn}/*"]
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}
resource "aws_s3vectors_vector_bucket" "history" {
  vector_bucket_name = "${var.name}-${local.account}-vectors"
  force_destroy      = false
}
resource "aws_s3vectors_index" "history" {
  vector_bucket_name = aws_s3vectors_vector_bucket.history.vector_bucket_name
  index_name         = "incident-deployment-history"
  data_type          = "float32"
  dimension          = 1024
  distance_metric    = "cosine"
  metadata_configuration {
    non_filterable_metadata_keys = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
  }
}
resource "aws_iam_role" "knowledge_base" {
  name_prefix = "${var.name}-kb-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "bedrock.amazonaws.com" }, Action = "sts:AssumeRole"
    Condition = {
      StringEquals = { "aws:SourceAccount" = local.account }
      ArnLike      = { "aws:SourceArn" = "arn:${local.partition}:bedrock:${var.region}:${local.account}:knowledge-base/*" }
    }
  }] })
}
resource "aws_iam_role_policy" "knowledge_base" {
  role = aws_iam_role.knowledge_base.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = local.titan_arn },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.source.arn },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.source.arn}/knowledge/*" },
    { Effect = "Allow", Action = ["s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors", "s3vectors:QueryVectors", "s3vectors:GetIndex"], Resource = aws_s3vectors_index.history.index_arn }
  ] })
}
resource "aws_bedrockagent_knowledge_base" "history" {
  name     = "${var.name}-history"
  role_arn = aws_iam_role.knowledge_base.arn
  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = local.titan_arn
      embedding_model_configuration {
        bedrock_embedding_model_configuration { dimensions = 1024 }
      }
    }
  }
  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration { index_arn = aws_s3vectors_index.history.index_arn }
  }
  depends_on = [aws_iam_role_policy.knowledge_base, aws_s3_bucket_public_access_block.source]
}
resource "aws_bedrockagent_data_source" "history" {
  knowledge_base_id    = aws_bedrockagent_knowledge_base.history.id
  name                 = "synthetic-incident-deployment-records"
  data_deletion_policy = "RETAIN"
  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn         = aws_s3_bucket.source.arn
      inclusion_prefixes = ["knowledge/"]
    }
  }
  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 300
        overlap_percentage = 20
      }
    }
  }
}
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = 14
}
resource "aws_iam_role" "lambda" {
  name_prefix = "${var.name}-lambda-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_iam_role_policy" "lambda" {
  role = aws_iam_role.lambda.id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.lambda.arn}:*" },
    { Effect = "Allow", Action = ["bedrock:Retrieve"], Resource = aws_bedrockagent_knowledge_base.history.arn },
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = local.nova_arn }
    ], length(var.cloudwatch_log_groups) == 0 ? [] : [
    { Effect = "Allow", Action = ["logs:FilterLogEvents"], Resource = [for group in var.cloudwatch_log_groups : "arn:${local.partition}:logs:${var.region}:${local.account}:log-group:${group}:*"] }
    ], var.cloudwatch_metric_namespace == "" ? [] : [
    # GetMetricStatistics does not support resource-level IAM restrictions.
    { Effect = "Allow", Action = ["cloudwatch:GetMetricStatistics"], Resource = "*" }
  ]) })
}
resource "aws_lambda_function" "assistant" {
  function_name                  = var.name
  role                           = aws_iam_role.lambda.arn
  filename                       = var.lambda_zip
  source_code_hash               = filebase64sha256(var.lambda_zip)
  handler                        = "app.lambda_handler.lambda_handler"
  runtime                        = "python3.13"
  architectures                  = ["x86_64"]
  timeout                        = 60
  memory_size                    = 256
  reserved_concurrent_executions = 2
  environment {
    variables = {
      BEDROCK_KNOWLEDGE_BASE_ID    = aws_bedrockagent_knowledge_base.history.id
      BEDROCK_GENERATION_MODEL_ID  = var.generation_model_id
      CLOUDWATCH_LOG_GROUPS        = join(",", var.cloudwatch_log_groups)
      CLOUDWATCH_METRIC_NAMESPACE  = var.cloudwatch_metric_namespace
      CLOUDWATCH_METRIC_NAME       = var.cloudwatch_metric_name
      CLOUDWATCH_METRIC_DIMENSIONS = jsonencode(var.cloudwatch_metric_dimensions)
    }
  }
  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
  }
  depends_on = [aws_iam_role_policy.lambda]
}
resource "aws_apigatewayv2_api" "assistant" {
  name          = "${var.name}-api"
  protocol_type = "HTTP"
}
resource "aws_apigatewayv2_integration" "assistant" {
  api_id                 = aws_apigatewayv2_api.assistant.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.assistant.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}
resource "aws_apigatewayv2_route" "assistant" {
  for_each           = toset(["POST /ask", "POST /incidents"])
  api_id             = aws_apigatewayv2_api.assistant.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.assistant.id}"
  authorization_type = "AWS_IAM"
}
resource "aws_apigatewayv2_stage" "assistant" {
  api_id      = aws_apigatewayv2_api.assistant.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 4
    throttling_rate_limit  = 2
  }
}
resource "aws_lambda_permission" "gateway" {
  statement_id   = "AllowApiGateway"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.assistant.function_name
  principal      = "apigateway.amazonaws.com"
  source_arn     = "${aws_apigatewayv2_api.assistant.execution_arn}/*/POST/*"
  source_account = local.account
}
output "api_endpoint" { value = aws_apigatewayv2_api.assistant.api_endpoint }
output "knowledge_base_id" { value = aws_bedrockagent_knowledge_base.history.id }
output "data_source_id" { value = aws_bedrockagent_data_source.history.data_source_id }
output "source_bucket" { value = aws_s3_bucket.source.id }
output "vector_index_arn" { value = aws_s3vectors_index.history.index_arn }
