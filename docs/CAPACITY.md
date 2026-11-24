# Capacity plan: GlucoLit

<!-- generated:start -->
| Measurement | Current corpus | Full target |
|---|---:|---:|
| Papers | 60 | 500 |
| Estimated pages | 735 | 6,125 |
| Estimated tokens | 460,254 | 3,835,450 |
| Tokens per page | 626 | 626 |
| Chunks (500 tokens each) | 921 | 7,671 |
| Embedding cost | Rs 8.74 | Rs 72.87 |
| Vector storage (1024 dimensions, float32) | 3.60 MiB | 29.96 MiB |

**Assumptions:** 0.20 USD per million tokens, Rs 95.00 per USD.
1024 embedding dimensions, 500 tokens per chunk, and 4 bytes per vector value.
Storage excludes PostgreSQL indexes, metadata, and text.

**Measurement note:** Token counts and pages are estimates based on XML body text.
They are not actual embedding tokenizer measurements or PDF page counts.
<!-- generated:end -->
