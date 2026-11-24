# Capacity plan: GlucoLit

<!-- generated:start -->
| Measurement | Current corpus | Full target |
|---|---:|---:|
| Papers | 24 | 500 |
| Estimated pages | 265 | 5,521 |
| Estimated tokens | 164,291 | 3,422,730 |
| Tokens per page | 620 | 620 |
| Chunks (500 tokens each) | 329 | 6,846 |
| Embedding cost | Rs 3.12 | Rs 65.03 |
| Vector storage (1024 dimensions, float32) | 1.29 MiB | 26.74 MiB |

**Assumptions:** 0.20 USD per million tokens, Rs 95.00 per USD.
1024 embedding dimensions, 500 tokens per chunk, and 4 bytes per vector value.
Storage excludes PostgreSQL indexes, metadata, and text.

**Measurement note:** Token counts and pages are estimates based on XML body text.
They are not actual embedding tokenizer measurements or PDF page counts.
<!-- generated:end -->
