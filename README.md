# GlucoLit

A research assistant for diabetes literature that answers questions from open-access papers with paper and section citations and the study design.

**Status:** Deployed and running on Render.

**Live API:** https://glucolit-main.onrender.com

**Health Check:** https://glucolit-main.onrender.com/health

**Readiness Check:** https://glucolit-main.onrender.com/ready

[![CI](https://github.com/brithikaaids28-blip/prince28-hlt04-glucolit/actions/workflows/ci.yml/badge.svg)](https://github.com/brithikaaids28-blip/prince28-hlt04-glucolit/actions/workflows/ci.yml)
## Who it's for

Endocrinology postgraduate resident at a Chennai medical college writing a thesis on type 2 diabetes in South Indian adults.

## The problem

There are thousands of research papers on diabetes, making it difficult for postgraduate residents to find reliable evidence quickly. Residents need a simple way to understand what existing studies say about type 2 diabetes. They often struggle to identify the correct study design, population, and important findings. GlucoLit helps by providing evidence-based answers with exact paper and section citations, focusing on the Results section rather than general background information.

## Data sources

PMC Open Access subset filtered to type 2 diabetes (full-text JATS XML), with licence kept per article.

- https://pmc.ncbi.nlm.nih.gov/tools/openftlist/
- https://europepmc.org/RestfulWebService
- Terms: Use only Open Access articles; store each article's licence (CC BY, CC0 etc.).

## Hardest problem (my interview story)

Study design and section awareness: 'does metformin reduce cardiovascular risk' must weigh RCTs and meta-analyses over case reports, show the population (Indian vs Western cohorts), and cite claims from Results, which needs section-aware chunking of JATS XML.

## Signature feature

Evidence table: every answer comes with a sortable table of the cited studies (design, n, country, effect).

## Target metric

The accuracy targets are set at 95% citation precision and 90% study-type extraction to improve the reliability of evidence-based answers for medical research.

## Run it locally

```bash
uv sync
cp .env.example .env   # Windows: copy .env.example .env
uv run uvicorn glucolit.api.main:create_app --factory --reload
```

Then open http://localhost:8000/docs

## Checks

```bash
uv run pytest
uv run ruff check .

```

## Run locally in one command

You need Docker Desktop running. From a fresh clone:

```bash
docker compose up --build
```

This starts Postgres (with pgvector), Redis, runs the migrations and loads the sample data once, then starts the API.

- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Liveness: [http://localhost:8000/health](http://localhost:8000/health)
- Readiness (checks the database): [http://localhost:8000/ready](http://localhost:8000/ready)

Stop with `Ctrl+C`, then `docker compose down`. Add `-v` to also delete the database volume.

## Develop and test

| Task | Mac / Linux | Windows |
|---|---|---|
| Run the API with reload | `make dev` | `uv run poe dev` |
| Unit tests (no network) | `make test` | `uv run poe test` |
| Integration tests (needs `docker compose up`) | `make test-integration` | `uv run poe test-integration` |
| Coverage report | `make cov` | `uv run poe cov` |
| Lint and format check | `make lint` | `uv run poe lint` |
