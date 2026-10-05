"""Lakeflow pipeline source; attach to a Databricks pipeline, not Run All.

Pipeline default catalog/schema: workspace.insurance_poc (adjust in the UI).
Optional pipeline configuration: insurance.input_path = /Volumes/.../claim_files
No AWS credentials, pip installs, or application dependencies are required.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

INPUT_PATH = spark.conf.get(  # noqa: F821 - supplied by Databricks
    "insurance.input_path", "/Volumes/workspace/insurance_poc/claim_files"
)
FIELDS = [
    "event_id", "claim_id", "policy_id", "owner_id", "lob",
    "incident_date", "event_time", "estimated_loss_usd", "event_type",
]
INPUT_SCHEMA = StructType([StructField(name, StringType(), True) for name in FIELDS])


@dp.table(name="bronze_claim_events_raw")
def bronze_claim_events_raw():
    return (
        spark.readStream.format("cloudFiles")  # noqa: F821
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaEvolutionMode", "rescue")
        .option("rescuedDataColumn", "_rescued_data")
        .schema(INPUT_SCHEMA)
        .load(INPUT_PATH)
        .select("*", F.col("_metadata.file_path").alias("source_file"))
        .withColumn("ingested_at", F.current_timestamp())
    )


@dp.temporary_view(name="classified_claim_events")
def classified_claim_events():
    df = spark.readStream.table("bronze_claim_events_raw")  # noqa: F821
    df = (
        df.withColumn("incident_date_typed", F.expr("try_cast(incident_date AS DATE)"))
        .withColumn("event_time_typed", F.expr("try_cast(event_time AS TIMESTAMP)"))
        .withColumn("loss_typed", F.expr("try_cast(estimated_loss_usd AS DECIMAL(12,2))"))
    )
    checks = {
        **{f"missing_{name}": F.length(F.trim(F.col(name))) > 0
           for name in ["event_id", "claim_id", "policy_id", "owner_id"]},
        "invalid_lob": F.col("lob").isin("auto", "property"),
        "invalid_incident_date": F.col("incident_date_typed").isNotNull(),
        "invalid_event_time": F.col("event_time_typed").isNotNull(),
        "invalid_loss": F.col("loss_typed").isNotNull() & (F.col("loss_typed") >= 0),
        "invalid_event_type": F.col("event_type") == "claim_created",
        "rescued_fields": F.col("_rescued_data").isNull(),
    }
    reasons = [F.when(~F.coalesce(valid, F.lit(False)), F.lit(reason))
               for reason, valid in checks.items()]
    return df.withColumn("rejection_reason", F.concat_ws(";", *reasons)).withColumn(
        "is_valid", F.col("rejection_reason") == ""
    )


@dp.table(name="silver_claim_events_valid")
@dp.expect("valid_delivery", "is_valid = true")
def silver_claim_events_valid():
    return spark.readStream.table("classified_claim_events").filter("is_valid")  # noqa: F821


@dp.table(name="silver_claim_events_rejected")
@dp.expect("rejected_delivery", "is_valid = false")
def silver_claim_events_rejected():
    return spark.readStream.table("classified_claim_events").filter("NOT is_valid")  # noqa: F821


@dp.materialized_view(name="gold_event_conflicts")
@dp.expect_or_fail("one_payload_per_event", "payload_count = 1")
def gold_event_conflicts():
    # Exact payload deduplication excludes ingestion metadata. Conflicting event
    # IDs fail the update instead of silently choosing a claim estimate.
    return (
        spark.read.table("silver_claim_events_valid")  # noqa: F821
        .select(*FIELDS).distinct()
        .groupBy("event_id").agg(F.count("*").alias("payload_count"))
    )


@dp.materialized_view(name="gold_daily_claim_summary")
def gold_daily_claim_summary():
    valid = spark.read.table("silver_claim_events_valid")  # noqa: F821
    unique = valid.select(*FIELDS, "incident_date_typed", "loss_typed").distinct()
    # Make the conflict check an upstream dependency of the summary.
    unique = unique.join(
        spark.read.table("gold_event_conflicts").select("event_id"),  # noqa: F821
        "event_id", "inner",
    )
    return unique.groupBy(
        F.col("incident_date_typed").alias("incident_date"), "lob"
    ).agg(F.count("*").alias("claim_count"), F.sum("loss_typed").alias("total_estimated_loss_usd"))
