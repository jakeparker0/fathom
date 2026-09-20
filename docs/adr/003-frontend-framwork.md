# ADR-003: Frontend approach

**Status:** Accepted
**Date:** 2026-09-20

Sprint task: S1-09 · Story refs: ET-14, ET-17, ET-19, SA-01 to SA-07, SP-09, BF-01, BF-02

## Context

A web frontend is already settled; the approach is not. The app has exactly one user, on their own machine or a private OCI instance. There is no SEO requirement, no public traffic, no native mobile app and no design system to satisfy.

Two parts of the app are where the frontend gets genuinely demanding, and they should drive this decision rather than the accounts list in Sprint 1:

- **The categorisation card (ET-14, ET-17, ET-19).** One transaction at a time, with set category, set sub-category, add tags, add note, split, mark as transfer, and skip. Tags can be created inline without leaving the flow (ET-19). Splits accept either dollars or percentages, validate live that they reconcile to the full amount, and block save when they do not (ET-17). This is a stateful, keyboard-speed, many-small-interactions screen, and it is the screen that gets used most.
- **Sprint 5 analysis (SA-01 to SA-07, BF-01, BF-02, SP-09).** A period selector defaulting to the pay-cycle month with five other period types plus custom ranges, spend-by-category charts with drill-down to sub-category and then to transactions, trend lines per category, allocation charts, and a forecast chart with an upper and lower band. Interactive charts with drill-down, not static images.

Other forces:

- Sprint 1 only needs a settings screen and an accounts list (S1-26, S1-28), so the walking skeleton will not stress-test whichever choice is made — the cost of a wrong choice surfaces in Sprints 2 and 5.
- The project is explicitly a learning exercise, and frontend is the area furthest from existing Oracle/APEX experience.
- Development is AI-assisted, with UI work firmly on the generated side of the human/AI split (S1-33).
- Coupled to ADR-002: Django leans toward server-rendered templates, FastAPI toward a JSON API.

## Options Considered

### Option A: React SPA with Vite
- Pros:
  - Best fit for the categorisation card: local component state, optimistic updates, inline tag creation and live split validation are exactly what the model is built for.
  - Strongest charting ecosystem for the Sprint 5 work (Recharts, visx, ECharts), including drill-down and banded forecast charts.
  - The most transferable skill of the three, and the most relevant to a software engineering move.
  - Clean separation: backend becomes a typed JSON API with no view concerns.
- Cons:
  - A second toolchain, language and dependency tree to own, plus CI, build and deploy steps for it.
  - Every screen costs a component plus an endpoint plus a client-side type — highest boilerplate per feature, including for the trivial Sprint 1 screens.
  - Duplicated domain logic risk: formatting, period maths and net-vs-gross rules can quietly diverge from the backend.
  - Largest surface area for AI-generated code to sprawl, exactly where you have least experience to review it.

### Option B: Server-rendered templates with HTMX
- Pros:
  - One language, one deployment artifact, one mental model; no build step for the frontend.
  - Server keeps ownership of every domain rule — net vs gross, transfers excluded, pay-cycle boundaries — so there is one implementation, not two.
  - Fits the card workflow reasonably well: each action is a small POST returning the next card as a fragment.
  - Low per-screen cost for the many simple CRUD screens (accounts, categories, tags, trades, manual transactions).
- Cons:
  - Live client-side validation (the $/% split reconciliation in ET-17) is either a server round-trip per keystroke or a sprinkle of Alpine.js — a second, smaller frontend model creeping in.
  - Interactive charts still require a JS library (Chart.js, Plotly, ECharts) wired up by hand; HTMX does nothing for them, so Sprint 5 is the weakest part of this option.
  - Fragment-returning endpoints are less cleanly typed and less reusable than a JSON API if a different client ever appears.
  - Smaller talent pool of examples than React, so generated code quality is more variable.

### Option C: Streamlit
- Pros:
  - Fastest path to something usable — the entire Sprint 1 walking skeleton is a few dozen lines, and charts come essentially free.
  - Pure Python, zero frontend toolchain, trivially deployable next to the backend.
  - Good for the analysis and forecasting views specifically, which is the use case it was built for.
- Cons:
  - The rerun-on-every-interaction model fights the categorisation card badly: per-card state, inline tag creation and live split validation all become session-state gymnastics.
  - Little control over layout, keyboard interaction or URL routing — and the card workflow lives or dies on feeling fast.
  - Effectively a dead end for a real web app: outgrowing it means a full rewrite, not an incremental migration.
  - Teaches the least of the three about web application development.

## Decision

**Option A — a React SPA built with Vite, written in TypeScript**, consuming the FastAPI JSON API from ADR-002.

Four things decided it, and unusually they all point the same way. The categorisation card is the screen this app lives or dies on, and ET-14 and ET-17 — per-card state, inline tag creation, live dollar-and-percentage split validation that blocks save until it reconciles — describe a component model almost exactly. Sprint 5 needs interactive drill-down charts and a banded forecast, which no server-rendered approach gives for free; every option ends up wiring a JavaScript charting library, so the one with the strongest ecosystem wins on work that has to happen regardless. React is also the most transferable of the three and the furthest from existing Oracle and APEX experience, which is the point of building this rather than buying a finance app. And it keeps the backend a pure JSON API with no view concerns, which is what ADR-002 already commits to.

TypeScript rather than plain JavaScript, with the client types generated from FastAPI's OpenAPI schema. ADR-002's central argument is a typed boundary; stopping types at the network hop would throw away half of it. Generating them means a backend schema change breaks the frontend build instead of failing quietly at runtime in front of the only user.

## Consequences

**What this commits the project to**

- **A second toolchain.** Node, a package manager and a lockfile join the repo. S1-02's one-command setup story grows a frontend half, S1-29's CI pipeline runs a second set of checks (typecheck, lint, build), and S1-30's runbook has to cover both halves from a clean clone.
- **A generated API client.** The OpenAPI schema becomes a real artifact, not a byproduct: a generation step (`openapi-typescript` or similar) runs as part of the frontend build or as a committed generated file, and regenerating it is part of any change to a response schema. If that step is skipped, the types drift and the main benefit of choosing TypeScript is lost.
- **One deployment artifact.** Vite builds to static files that FastAPI serves, so Sprint 6 deploys a single process to the OCI instance with no CORS configuration and no second web server. Local development uses Vite's dev proxy to reach the API, which is the only place the two-origin split shows up.
- **A scope statement for ADR-005.** There are now two trees. ADR-005 governs the backend; the frontend needs either its own stated layout or an explicit note that it is out of scope — otherwise generated components organise themselves.
- **Duplicated-logic risk to actively manage.** Currency formatting, pay-cycle period boundaries and net-versus-gross rules must not be reimplemented client-side. The rule is that the API returns computed and formatted values where the domain is involved, and the frontend renders them. This belongs in CLAUDE.md (S1-31) and the review checklist (S1-32).

**Accepted costs**

- **Sprint 1 gets slower, Sprints 2 and 5 get faster.** The settings screen and accounts list (S1-26, S1-28) are trivial screens carrying the full setup cost of a SPA. That is the trade being made knowingly: the investment is paid in Sprint 1 and returned on the card workflow and the analysis views.
- **Highest surface area for generated code to sprawl**, in the area with the least existing experience to review it. Mitigated only by a stated frontend structure and the S1-32 checklist, not by the framework.
- **Every screen costs a component, an endpoint and a generated type** — the most boilerplate per feature of the three options, including for simple CRUD.

**Deferred, deliberately**

- **The charting library is not chosen here.** It is a known gap owned by Sprint 5, recorded so it is a scheduled decision rather than a surprise. Nothing before Sprint 5 renders a chart, so nothing is blocked. The trigger is the start of the SA-03 / SA-04 work; candidates are Recharts, ECharts and Plotly.
- **Client-side data fetching and state management** (TanStack Query or equivalent) are not decided here. Worth settling before Sprint 2 rather than accumulating hand-rolled `fetch` calls, but Sprint 1's two screens do not force it.

**Validation before Sprint 2**

- ET-14 and ET-17 are the real acceptance test for this decision, and Sprint 1 will not exercise them. Sketching the card interaction — one transaction, all its actions, a split that validates live — before Sprint 2 starts is much cheaper than discovering a mismatch mid-sprint.

## Notes

- The fourth shape considered and set aside: server-rendered pages for CRUD with React islands only on the card and the dashboard. It was not needed once the drivers all pointed one way, and it costs two mental models in one repo.
- Decided together with ADR-002; the pairing is FastAPI + React, with the OpenAPI schema as the contract between them.
- Triggers to revisit: the card feeling slow in daily use; Sprint 5 charting outgrowing whatever library is chosen; the generated-client step proving too awkward to keep in the loop.
- Depends on: S1-07, ADR-002. Feeds: S1-26 (settings screen), S1-28 (accounts list), S1-29 (CI), S1-30 (runbook), S1-31 (CLAUDE.md), all of Sprint 2 and Sprint 5.
