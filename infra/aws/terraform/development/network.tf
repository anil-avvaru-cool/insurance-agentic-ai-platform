data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "development" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${local.name}_vpc" }
}

resource "aws_subnet" "private" {
  count                   = 2
  vpc_id                  = aws_vpc.development.id
  cidr_block              = cidrsubnet(aws_vpc.development.cidr_block, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}_private_${count.index + 1}" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.development.id
  tags   = { Name = "${local.name}_private" }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
