# Capacity plan: GlucoLit

<!-- generated:start -->
| Measurement | Current corpus | Full target |
|---|---:|---:|
| Papers | 500 | 500 |
| Estimated pages | 6,084 | 6,084 |
| Estimated tokens | 3,791,219 | 3,791,219 |
| Tokens per page | 623 | 623 |
| Chunks (500 tokens each) | 7,583 | 7,583 |
| Embedding cost | Rs 72.03 | Rs 72.03 |
| Vector storage (1024 dimensions, float32) | 29.62 MiB | 29.62 MiB |

**Assumptions:** 0.20 USD per million tokens, Rs 95.00 per USD.
1024 embedding dimensions, 500 tokens per chunk, and 4 bytes per vector value.
Storage excludes PostgreSQL indexes, metadata, and text.

**Measurement note:** Token counts and pages are estimates based on XML body text.
They are not actual embedding tokenizer measurements or PDF page counts.
<!-- generated:end -->
