# Capacity plan: GlucoLit

<!-- generated:start -->
| Measurement | Current corpus | Full target |
|---|---:|---:|
| Papers | 18 | 5,000 |
| Estimated pages | 200 | 55,556 |
| Estimated tokens | 123,762 | 34,378,334 |
| Tokens per page | 619 | 619 |
| Chunks (500 tokens each) | 248 | 68,757 |
| Embedding cost | Rs 2.35 | Rs 653.19 |
| Vector storage (1024 dimensions, float32) | 0.97 MiB | 268.58 MiB |

**Assumptions:** 0.20 USD per million tokens, Rs 95.00 per USD.
1024 embedding dimensions, 500 tokens per chunk, and 4 bytes per vector value.
Storage excludes PostgreSQL indexes, metadata, and text.

**Measurement note:** Token counts and pages are estimates based on XML body text.
They are not actual embedding tokenizer measurements or PDF page counts.
<!-- generated:end -->
