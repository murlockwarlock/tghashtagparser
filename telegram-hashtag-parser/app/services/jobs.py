import json
import socket
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import Job

JOB_SEARCH = "search"
JOB_AI_ANALYSIS = "ai_analysis"
JOB_BINGX_SYNC = "bingx_sync"


def enqueue_job(
    db: Session,
    kind: str,
    payload: dict | None = None,
    created_by_admin_id: int | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> Job:
    if kind == JOB_SEARCH:
        active_job = db.query(Job).filter(Job.kind == kind, Job.status.in_(["pending", "running"])).first()
        if active_job:
            return active_job

    job = Job(
        kind=kind,
        status="pending",
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        created_by_admin_id=created_by_admin_id,
        run_after=run_after or datetime.utcnow(),
        max_attempts=max_attempts,
    )
    db.add(job)
    db.flush()
    return job


def claim_next_job(db: Session) -> Job | None:
    now = datetime.utcnow()
    job = (
        db.query(Job)
        .filter(Job.status == "pending")
        .filter(Job.run_after <= now)
        .order_by(Job.created_at.asc())
        .first()
    )
    if not job:
        return None
    job.status = "running"
    job.attempts += 1
    job.started_at = now
    job.locked_at = now
    job.locked_by = socket.gethostname()
    db.flush()
    return job


def finish_job(db: Session, job: Job) -> None:
    job.status = "done"
    job.finished_at = datetime.utcnow()
    job.last_error = None


def fail_job(db: Session, job: Job, error: str) -> None:
    job.last_error = error
    job.finished_at = datetime.utcnow()
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        return
    job.status = "pending"
    job.run_after = datetime.utcnow() + timedelta(seconds=min(300, 30 * job.attempts))


def requeue_stale_jobs(db: Session, timeout_minutes: int = 30) -> int:
    threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)
    jobs = (
        db.query(Job)
        .filter(Job.status == "running")
        .filter(Job.locked_at <= threshold)
        .all()
    )
    for job in jobs:
        fail_job(db, job, "job lock timeout")
    return len(jobs)
