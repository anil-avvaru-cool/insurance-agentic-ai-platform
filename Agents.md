# This file provides guidance to agents.

## Configuration:
Use .env and example.env for configuration, never hardcoded values

## Fail fast on config:
Use `os.environ["KEY"]` (no defaults)

## Naming standard:
Underscores only (no hyphens)

## Units:
Use USA standard units (miles, feet, pounds) in data and outputs

## Use UV:
Use UV for Python package management, running scripts, and test execution. pyproject.toml should be source of truth. Do not use pip install. Remove requirements.txt

## Do not commit to git:
User needs to review before commit

## Model access:
All model inference must use a cloud-managed service such as AWS Bedrock, Azure AI Foundry, or Google Cloud Vertex AI. Never call direct model-vendor APIs. AWS Bedrock is the implemented provider; explicit disabled mode supports offline tests.

## Documentation:
Keep it short and scannable. Use bullet points and the exact commands needed, not long prose.

## Preview features:
Allowed for learning.

## Planning:
Make sure to check latest reliable documentation before making a plan