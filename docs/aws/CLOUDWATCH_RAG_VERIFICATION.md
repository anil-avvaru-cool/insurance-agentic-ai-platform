# Verify RAG logs and metrics in CloudWatch

Use this runbook after deploying the query API to verify online RAG telemetry.
It is a manual procedure, not evidence that live verification has passed.

## Offline validation and the telemetry gap

[Offline index validation](OFFLINE_INDEX_VALIDATION.md) calls Bedrock directly,
bypassing API Gateway and the query Lambda. It saves evidence locally under
`validation_reports/` and does not publish CloudWatch events. The ingestion CLI
also writes local reports; it does not yet publish its terminal events to
CloudWatch.

Terraform creates the ingestion log group and metric filters, including
`IndexValidationFailures`, but these resources do not generate events. An empty
ingestion/index-validation dashboard is currently expected and is **not evidence
of successful validation or zero failures**. Retain the local reports and manual
review records required by the offline runbooks.

## 1. Find the deployment's observability resources

From the repository root, using the intended AWS profile:

```bash
export AWS_PAGER=""
aws sts get-caller-identity

export AWS_DEFAULT_REGION="$(
  terraform -chdir=infra/aws/terraform/development \
    output -json ingestion_environment | jq -r '.AWS_REGION'
)"

terraform -chdir=infra/aws/terraform/development output -json observability
```

Stop if a command fails or the region is empty or `null`. The `observability`
output contains:

| Output | Use |
|---|---|
| `ingestion_log_group` | Destination reserved for ingestion and index-validation events |
| `query_log_group` | Query Lambda application logs |
| `api_log_group` | API Gateway access logs |
| `metric_namespace` | Custom log-derived metrics |
| `dashboard_name` | Dashboard combining custom and native metrics |

If the query/API log groups are `null`, the query API is disabled. Complete
offline validation and follow the
[query deployment procedure](../../infra/aws/terraform/README.md#phase-1-query-deployment)
before continuing. Do not enable the API just to inspect offline validation.

Use the same account and region in the CloudWatch console. Reading Terraform
outputs requires backend access. Viewing logs, running Logs Insights queries,
and viewing metrics/dashboard data require corresponding CloudWatch read/query
permissions. The validation runner policy alone does not grant these permissions.
The identity used to invoke the API must be the configured query operator; a
separate authorized identity may inspect CloudWatch.

## 2. Generate and retain an online query

Configure `.env` and operator credentials as described in
[online RAG testing](ONLINE_RAG_TESTING.md), then run one case:

```bash
uv run --locked --env-file .env python scripts/test_online_rag.py \
  --case-id auto_user_1_v1_comprehensive_deductible
```

Ensure `.env` uses the deployment's region and endpoint. This invokes paid AWS
services. Retain the report under `online_rag_reports/`, its request ID, and the
test time. The runner checks the API response; it does not verify CloudWatch.

## 3. Correlate API and Lambda logs

Open **CloudWatch → Logs Insights**, select both the returned `query_log_group`
and `api_log_group`, and set the time range to include the test. Replace the
placeholder with the request ID from the report:

```sql
fields @timestamp, @log, event, request_id, status,
       retrieval_count, has_citations, insufficient_information,
       input_tokens, output_tokens, duration_ms, reason
| filter request_id = "YOUR_REQUEST_ID"
| sort @timestamp asc
```

For a successful answer supported by the corpus, verify:

- The API access log has `status = "200"`.
- The Lambda application log has `event = "query_completed"` with the same
  `request_id`.
- `retrieval_count` is positive, `has_citations = true`, and
  `insufficient_information = false`.
- `input_tokens`, `output_tokens`, and `duration_ms` are numeric. When generation
  runs, compare usage with the resulting metrics.

An insufficient-information response is also HTTP 200, but its completion event
has `has_citations = false` and `insufficient_information = true`. If no usable
evidence is retrieved, the handler skips generation and records zero token usage.

For a terminal failure, inspect `query_failed` and its sanitized `reason`, plus
the API status. Input rejections use `query_rejected`; Lambda authorization
rejections use `authorization_failed`.

## 4. Verify metrics and the dashboard

Open **CloudWatch → Dashboards** and select the returned `dashboard_name`. To
inspect individual custom metrics, open **Metrics → All metrics** and select
the returned `metric_namespace`. Set the time range to cover the test and use
**Sum** with a **one-minute period** for custom counters.

| Signal | Expected metric evidence |
|---|---|
| Retrieved evidence | `RetrievalResults` reflects the logged `retrieval_count` |
| Answer with citations | `AnswersWithCitations` increments for `has_citations = true` |
| Model usage | `InputTokens` and `OutputTokens` reflect logged usage |
| Insufficient evidence | `InsufficientInformation` increments when that flag is true |
| Lambda authorization rejection | `AuthorizationFailures` increments for `authorization_failed` |
| API 401/403 response | `ApiAuthenticationFailures` increments |
| API traffic/errors | Native `AWS/ApiGateway` metrics: `Count`, `4XXError`, `5XXError` |
| Lambda execution | Native `AWS/Lambda` metrics: `Invocations`, `Errors`, `Throttles` |
| Latency | Native API Gateway `Latency` and Lambda `Duration`; the dashboard uses p95 |

For an isolated successful request with citations, expect
`AnswersWithCitations` to increase by one and retrieval/token totals to match the
completion event. If other requests share the time bucket, compare against all
matching events in that bucket. Request IDs are log fields, not metric dimensions.
`RetrievalResults` sums retrieved items; it is not a request counter and may also
include counts logged on failed queries.

Allow time for log and metric delivery. A metric becomes visible only after data
points arrive; metric filters do not process historical events retroactively.
See [AWS metric-filter setup](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CreateMetricFilterProcedure.html)
and [AWS metric-filter behavior](https://aws.amazon.com/blogs/mt/quantify-custom-application-metrics-with-amazon-cloudwatch-logs-and-metric-filters/).

The filters do not configure default zero values. A missing failure metric is
not proof of zero failures. Custom metrics are derived from logs; do not also
publish the same observations with `PutMetricData`, which would double-count.

## 5. Interpret rejection and failure checks

For a separately performed signed request from another valid AWS principal,
expect API Gateway to return 403 and increment `ApiAuthenticationFailures`.
Confirm an API access record and no corresponding Lambda application event or
execution. Gateway rejection does not require a Lambda `authorization_failed`
event because the request is blocked before Lambda. Use an isolated test window
when checking invocation counts, since concurrent requests also affect metrics.

For a separately arranged controlled backend failure, check `query_failed` and
the HTTP 503/504 response. The handler catches backend exceptions and returns an
HTTP response, so Lambda's native `Errors` metric may remain zero. Assess the
application event and API status together. This runbook does not inject faults.

If expected telemetry is missing, check account, region, time range, deployed
artifact, log destinations, and the group's metric filters. Confirm that the
expected JSON event actually arrived before interpreting an empty metric chart.
Log retention defaults to 14 days, so retain acceptance evidence separately.

## 6. Record acceptance evidence

Retain the online runner report, request IDs, test timestamps, relevant log
records, and metric/dashboard evidence for the same time window. Record the
account, region, corpus revision, reviewer, and pass/fail decisions. Identify any
authentication or controlled-failure checks that were not run. Successful online
telemetry verification does not fill the offline event-publication gap.

Implementation references:

- [Metric filters, dashboard, and destinations](../../infra/aws/terraform/development/observability.tf)
- [Query events and failure handling](../../src/apps/query_lambda/query.py)
- [API access-log configuration](../../infra/aws/terraform/development/query.tf)
- [Telemetry contract](../../infra/aws/terraform/README.md#telemetry-contract)
