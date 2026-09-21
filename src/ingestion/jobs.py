"""Shared Bedrock ingestion job polling for the smoke and POC commands."""
import time

TERMINAL = {'COMPLETE', 'FAILED', 'STOPPED'}


def poll_job(agent, args, job, timeout, on_update=lambda job: None,
             clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    while True:
        job = agent.get_ingestion_job(**args, ingestionJobId=job['ingestionJobId'])['ingestionJob']
        on_update(job)
        if job['status'] == 'COMPLETE':
            if 'numberOfDocumentsFailed' not in job.get('statistics', {}):
                raise RuntimeError(f"Ingestion returned no document failure statistics: {job}")
            if job.get('statistics', {}).get('numberOfDocumentsFailed', 0):
                raise RuntimeError(f"Ingestion completed with document failures: {job}")
            return job
        if job['status'] in TERMINAL:
            raise RuntimeError(f'Ingestion unsuccessful: {job}')
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError(f"Ingestion still running: {job['ingestionJobId']}; inspect before retrying")
        sleep(min(5, remaining))
