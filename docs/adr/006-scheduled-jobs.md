# ADR-006: Scheduled job mechanism

**Status:** Accepted
**Date:** 2026-09-20

Sprint task: S1-12 · Story refs: ET-02, ET-03, SP-08, SP-11, SP-12

## Context

Four pieces of work run outside a user request:

| Job | Story | Shape |
|---|---|---|
| Up transaction and balance sync | ET-02 | Daily, at most once per day, configurable |
| Manual "Sync Now" | ET-03 | On demand, debounced while one is already running |
| ASX EOD price fetch | SP-08 | Daily; failures logged and retried next cycle |
| Portfolio and net worth snapshot | SP-11, SA-11 | Daily, **after** the price fetch — an ordering dependency, not two independent jobs |
| Snapshot backfill on backdated import | SP-12 | Ad hoc, potentially long-running, triggered by a user action |

Constraints that shape the choice:

- **Idempotent reruns are required, not optional.** Up sync upserts on transaction ID (S1-15 confirms whether those IDs are stable enough to trust); snapshots are keyed by holding and date. Running twice must never duplicate.
- **Status has to reach the UI.** ET-02 requires a visible last-successful-sync timestamp and surfaced failures. That means job runs are persisted — a `job_run` table with job name, started/finished timestamps, status, row counts and error — regardless of which mechanism runs them. This is a data-model consequence that currently has no home in S1-20 to S1-24.
- **Two different environments.** Sprint 1 to 5 run locally on a laptop that is closed at night, so daily jobs will miss their window routinely and need catch-up-on-next-start behaviour. Sprint 6 moves everything to a single always-on AWS host, where a plain timer is reliable.
- **Small scale.** One user, a few hundred transactions a month, a handful of ASX codes. Nothing here needs a distributed queue for throughput; it may need one for operational features.
- **Sprint 6 explicitly includes "move scheduled jobs server-side"**, so whatever is chosen now is allowed to be a local-development answer with a documented migration — but it should be a deliberate one.

## Options Considered

### Option A: OS cron (local) / systemd timers (AWS), invoking a CLI entry point
- Pros:
  - Simplest possible mechanism; the app just needs `python -m fathom.jobs.daily_sync` to be runnable and idempotent, which is good design regardless of the option chosen.
  - Scheduling lives outside the app, so a crashed or restarted app cannot take the schedule down with it.
  - Trivially testable — run the command by hand and watch what happens.
  - Migrates cleanly to Sprint 6: same entry point, a systemd timer instead of crontab.
- Cons:
  - Lives outside the repo, so the schedule is not version-controlled and is one more thing the S1-30 runbook has to tell a reader to set up.
  - A laptop that is asleep at the scheduled time simply misses the run — cron does not catch up, so a "has today's sync happened?" check on app start is needed anyway.
  - No native retry, no concurrency guard, no run history — all of which you build yourself (a database advisory lock or a status row).
  - Windows/macOS/Linux differences make the local setup step less uniform than the rest of the tooling.

### Option B: APScheduler, in-process
- Pros:
  - Schedule is defined in Python, in the repo, versioned with the code and visible to anyone reading it.
  - No extra services or infrastructure; starts and stops with the app, so one process is the whole system.
  - Supports a Postgres job store, so missed runs can be caught up and schedules survive restarts — which directly addresses the closed-laptop problem.
  - Same mechanism works locally and on AWS; Sprint 6 becomes a deployment change, not a rearchitecture.
- Cons:
  - Jobs run in the app process: a long SP-12 backfill competes with request handling, and an unhandled error in a job can affect the app.
  - Needs care if the app ever runs more than one worker — two workers means two schedulers and two syncs unless a lock or a dedicated scheduler process is used.
  - Adds a dependency whose failure modes (misfire grace time, coalescing, timezone handling) are subtle and easy to get wrong, especially in generated code.
  - Jobs only run while the app is running, which locally means "while you have it open".

### Option C: Celery with a broker (Redis) and Celery Beat
- Pros:
  - Proper job infrastructure: retries with backoff, out-of-process workers, task results, scheduled tasks via Beat, and a natural home for the long SP-12 backfill without blocking the app.
  - The same machinery serves ET-03's manual Sync Now — enqueue a task, return immediately, poll status — which is the interaction the UI actually wants.
  - Flower or similar gives a ready-made view of run history and failures.
  - Widely used and genuinely worth learning if the goal includes production-shaped patterns.
- Cons:
  - Adds Redis (or RabbitMQ) plus at least two extra processes to run, in both docker-compose and on a small AWS instance where resources are scarce.
  - Operational complexity far beyond four daily jobs for one user — by some distance the heaviest option here.
  - More moving parts to keep running before any feature work happens, and more surface area for an unfamiliar failure to eat an evening.
  - Local development becomes "three things must be running", which works against the clean-clone story in S1-30.

## Decision

**Option A — OS-level scheduling (cron locally, systemd timers on AWS) invoking CLI entry points**, with a review at Sprint 6 to decide whether to move to APScheduler.

Two things decided it. It is the least to build now, and Sprint 1 is already the long pole — there is no dependency to add, no scheduler semantics to learn and nothing to configure beyond a crontab line, which keeps attention on the domain problems that are the actual point of the project. More importantly, it forces the job design that every other option would also want: each job becomes a plain, idempotent, independently runnable entry point (`python -m fathom.jobs.daily_sync`) with no scheduler-specific code inside it. That property is what makes the later move cheap.

This is explicitly a first choice, not a final one. APScheduler stays the named successor, and the decision is revisited at the Sprint 6 deployment review — at which point an always-on AWS instance may well make a systemd timer entirely sufficient, and "stay on timers" is a legitimate outcome of that review.

## Consequences

**What this commits the project to**

- **Jobs as CLI entry points.** `jobs/` holds one module per job, each runnable standalone, each idempotent, each calling a service (per ADR-005 rule 6) and never a repository. No scheduling logic lives inside a job.
- **A catch-up check on app start.** Locally the laptop is shut overnight and cron simply will not fire, so on startup the app checks `job_run` and runs today's sync if it has not succeeded yet. This makes the app self-correcting, makes the local crontab entry close to optional, and — usefully — means the scheduled path gets exercised in development rather than first running for real in Sprint 6.
- **A `job_run` table in the initial migration.** Job name, started at, finished at, status, items processed, error. It is what ET-02's visible last-successful-sync timestamp and surfaced failures are read from, and what the catch-up check queries. This is new scope for S1-20 to S1-24 and must be in the S1-25 migration — it is not in the plan as currently written.
- **A Postgres advisory lock around every job.** A scheduled sync and a manual Sync Now (ET-03) must not overlap, and the lock is also what backs the button's disabled state. Added now rather than when the first collision happens.
- **Scheduling that is not in the repo.** The crontab lives on the machine, so the schedule is not version-controlled and the S1-30 runbook has to tell a reader how to set it up. Mitigated by committing the intended crontab and the eventual systemd unit as documented files under `docs/`, even though nothing reads them automatically.
- **Retry and error handling are yours.** Cron offers none. SP-08's "failures are logged and retried the next cycle" is satisfied by the next day's run plus the catch-up check, not by the scheduler.

**Job structure this implies**

- Pricing and snapshot are one ordered daily pipeline (SP-08 then SP-11), not two independent schedules — a single entry point that runs both in order, so the snapshot can never run against stale prices.
- SP-12's backfill is a separate on-demand entry point triggered by the import, not a scheduled job. Being long-running and out-of-band is precisely the case that would later argue for APScheduler.
- Idempotency is an application property, not a scheduler feature: Up sync upserts on transaction ID (pending S1-15 confirming those IDs are stable), snapshots are keyed by holding and date. Running any job twice must change nothing the second time.

**What the deferral costs**

- The local setup story gains a manual, platform-specific step, which is the least uniform part of the otherwise clean-clone tooling.
- Some of what APScheduler provides for free — missed-run coalescing, retry policy, a schedule visible in code — gets hand-rolled in a small way. The catch-up check is the first instance of that, and it is the thing to watch: if this logic grows, that is the signal below.

**Unaffected**

- The mechanism is deliberately invisible to the rest of the app. Because jobs are plain functions behind an entry point, switching to APScheduler later changes the trigger and nothing else — no service, repository or domain code moves.

## Notes

- Recorded in `CLAUDE.md` (S1-31): jobs are idempotent CLI entry points calling services, with no scheduler-specific code, so generated code does not invent a second scheduling approach alongside this one.
- **Named review point:** the Sprint 6 deployment task. Decide then between a systemd timer and APScheduler with a Postgres job store. Secondary triggers that would bring the review forward: the catch-up and locking logic starting to look like a scheduler in its own right, or SP-12 backfills running long enough to want out-of-process execution.
- Celery was rejected as far too heavy — Redis plus two extra processes on a small AWS instance, for four daily jobs and one user, and a clean-clone story that becomes "three things must be running".
- A Postgres-backed queue (`procrastinate`, `arq`) remains the interesting middle ground if job infrastructure is ever genuinely wanted: Celery-style retries, run history and out-of-process workers using the database already in the stack, with no broker to run. Worth reconsidering at the same Sprint 6 review.
- Depends on: S1-07, ADR-002 (entry points are plain Python modules, since FastAPI provides no scheduler), ADR-005 (jobs call services). Feeds: S1-20 to S1-25 (`job_run` table and advisory lock), S1-30 (runbook), S1-31 (CLAUDE.md), Sprint 2 sync work, Sprint 4 pricing and snapshots, Sprint 6 server-side jobs.
