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
Prefer cloud-managed service such as AWS Bedrock, Azure AI Foundry, or Google Cloud Vertex instead of direct model-vendor APIs when possible.
Inference frameworks like vllm can be used.
Follow docs/adr/0003_controlled_self_hosted_inference.md for self-hosted inference:
approved isolated experiments and gateway/routing experiments use synthetic/public
evaluation data; insurance application integration requires separate acceptance.
Direct model-vendor APIs remain prohibited under ADR 0002 as amended by ADR 0003.

## Documentation:
Keep it short and scannable. Use bullet points and the exact commands needed, not long prose.

## Preview features:
Allowed for learning.

## Planning:
Make sure to check latest reliable documentation before making a plan

## Storage
Do not use storage/s3 bucket versioning for POCs
