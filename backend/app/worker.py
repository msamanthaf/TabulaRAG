import os
import time

from sqlalchemy import select

from .db import SessionLocal
from .models import Job
from .ingest import resume_embedding_job

POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "5"))

def main():
    while True:
        db = SessionLocal()
        try:
            jobs = db.execute(
                select(Job).where(Job.status.in_(["indexing"]))
            ).scalars().all()
        finally:
            db.close()

        for job in jobs:
            try:
                print(f"[worker] embedding job {job.id} table {job.table_id}", flush=True)
                resume_embedding_job(job.id)
                print(f"[worker] finished job {job.id}", flush=True)
            except Exception as e:
                print(f"[worker] job {job.id} failed: {e}", flush=True)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
