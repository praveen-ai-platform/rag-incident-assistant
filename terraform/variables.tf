variable "region" {
  type    = string
  default = "us-east-1"
}
variable "name" {
  type    = string
  default = "incident-assistant-poc"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,29}$", var.name))
    error_message = "Use 3 to 30 lowercase letters, numbers, and hyphens, starting with a letter."
  }
}
variable "generation_model_id" {
  type        = string
  default     = "amazon.nova-lite-v1:0"
  description = "Regional Nova foundation model ID. Cross-region profiles need additional IAM permissions."
}
variable "lambda_zip" {
  type    = string
  default = "../dist/lambda.zip"
}
variable "cloudwatch_log_groups" {
  type    = list(string)
  default = []
  validation {
    condition     = length(var.cloudwatch_log_groups) <= 3
    error_message = "At most three CloudWatch log groups may be read in the PoC."
  }
}
variable "cloudwatch_metric_namespace" {
  type    = string
  default = ""
}
variable "cloudwatch_metric_name" {
  type    = string
  default = ""
}
variable "cloudwatch_metric_dimensions" {
  type    = list(object({ Name = string, Value = string }))
  default = []
}
