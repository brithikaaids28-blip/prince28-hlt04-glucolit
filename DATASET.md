# Dataset: GlucoLit

<!-- generated:start -->
| Measurement | Current corpus |
|---|---:|
| Downloaded XML papers | 18 |
| Estimated pages | 200 |
| Body words | 95,196 |
| Estimated tokens | 123,762 |
| Raw XML size | 1.88 MiB |
| Average tokens per paper | 6,876 |
| Average tokens per page | 619 |

**Measurement method:** Text is extracted from each XML `body` element.
Pages are estimated at 500 words per page. Tokens are estimated at 1.3 tokens per word.
These are planning estimates, not PDF page counts or tokenizer measurements.
<!-- generated:end -->
## What I conclude

1. Is embedding cost a problem for this product? No. The estimated cost for 5,000 papers is only Rs 653.19 at the assumed rate of $0.20 per million tokens.

2. Do the vectors and text fit in my free Postgres? To be confirmed after comparing the estimated 268.58 MiB of vectors plus text and indexes with my actual database storage limit.

3. Which number above am I least sure about, and how will I measure it better? Tokens per page. I will measure actual tokens using the tokenizer of the embedding model selected for the project.

4. What changes if the corpus grows 10 times?
- Embedding cost and vector storage will increase approximately 10 times, assuming similar paper sizes and chunking.
- I will need to monitor database storage, indexing performance and retrieval speed, and consider scaling if required.
