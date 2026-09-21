variable "create_cognito" {
  description = "Provision an optional operator-managed test identity provider, independently of API enablement."
  type        = bool
  default     = false
}
resource "aws_cognito_user_pool" "poc" {
  count = var.create_cognito ? 1 : 0
  name  = "${local.name}_poc"
  admin_create_user_config { allow_admin_create_user_only = true }
  password_policy {
    minimum_length    = 14
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
}
resource "aws_cognito_user_pool_client" "poc" {
  count                         = var.create_cognito ? 1 : 0
  name                          = "${local.name}_poc"
  user_pool_id                  = aws_cognito_user_pool.poc[0].id
  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
  access_token_validity         = 15
  id_token_validity             = 15
  refresh_token_validity        = 1
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
output "poc_identity" {
  value = var.create_cognito ? {
    user_pool_id = aws_cognito_user_pool.poc[0].id
    client_id    = aws_cognito_user_pool_client.poc[0].id
    issuer       = local.jwt_issuer
  } : null
}
