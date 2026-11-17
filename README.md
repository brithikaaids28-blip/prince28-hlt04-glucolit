# GlucoLit

A research assistant for diabetes literature that answers questions from open-access papers with paper and section citations and the study design.

**Status:** Day 1 foundation (FastAPI skeleton, quality gates). Live URL from Day 5.

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