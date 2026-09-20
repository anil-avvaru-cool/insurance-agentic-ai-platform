"""Prepare reviewable development teardown plans; never apply or purge messages."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import uuid


ROOT = Path(__file__).resolve().parents[1] / "infra/aws/terraform/development"
VARIABLES = ROOT / "teardown.tfvars.json"
COUNTERS = (
    "ApproximateNumberOfMessages",
    "ApproximateNumberOfMessagesNotVisible",
    "ApproximateNumberOfMessagesDelayed",
)


def run(*args):
    return subprocess.check_output(args, text=True)


def aws(*args):
    return json.loads(run("aws", *args, "--region", os.environ["AWS_REGION"],
                          "--output", "json", "--no-cli-pager"))


def check_queues():
    account = os.environ["AWS_ACCOUNT_ID"]
    if aws("sts", "get-caller-identity")["Account"] != account:
        raise SystemExit("AWS credentials do not match AWS_ACCOUNT_ID.")
    outputs = json.loads(run("terraform", f"-chdir={ROOT}", "output", "-json"))
    busy = False
    for name in ("task_queue_url", "dead_letter_queue_url"):
        url = outputs[name]["value"]
        result = aws("sqs", "get-queue-attributes", "--queue-url", url,
                     "--attribute-names", "QueueArn", *COUNTERS)["Attributes"]
        arn = result["QueueArn"].split(":")
        if arn[3:5] != [os.environ["AWS_REGION"], account]:
            raise SystemExit(f"Unexpected account/region for {name}.")
        counts = {key: int(result[key]) for key in COUNTERS}
        print(f"{name}: {counts}", flush=True)
        busy |= any(counts.values())
    if busy:
        raise SystemExit("Pending/in-flight/delayed messages remain. Reconcile both queues first.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "prepare", "destroy_plan"))
    parser.add_argument("--reconciled", action="store_true",
                        help="Confirm producers/workers stopped and business tasks reconciled")
    args = parser.parse_args()
    if args.action != "check" and not args.reconciled:
        parser.error("Stop workloads and reconcile business tasks, then pass --reconciled.")
    check_queues()
    if args.action == "check":
        return
    if not VARIABLES.exists():
        if args.action == "destroy_plan":
            raise SystemExit("Run prepare and apply its reviewed plan first.")
        snapshot = "final" + datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S") + uuid.uuid4().hex
        with open(VARIABLES, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
            json.dump({"db_deletion_protection": False,
                       "final_snapshot_identifier": snapshot}, file, indent=2)
            file.write("\n")
    values = json.loads(VARIABLES.read_text())
    print(f"Final snapshot identifier: {values['final_snapshot_identifier']}", flush=True)
    print(f"Recorded in {VARIABLES}", flush=True)
    plan = "teardown_prepare.tfplan" if args.action == "prepare" else "teardown.tfplan"
    command = ["terraform", f"-chdir={ROOT}", "plan", "-input=false",
               f"-var-file={VARIABLES}", f"-out={plan}"]
    if args.action == "destroy_plan":
        command.append("-destroy")
    subprocess.run(command, check=True)
    print(f"Review: terraform -chdir={ROOT} show {plan}")
    print(f"Apply after review: terraform -chdir={ROOT} apply {plan}")


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, KeyError, ValueError, OSError) as error:
        raise SystemExit(f"Teardown preparation failed: {error}") from error
