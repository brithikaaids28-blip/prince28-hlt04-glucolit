# Dataset: GlucoLit

<!-- generated:start -->
| Measurement | Current corpus |
|---|---:|
| Downloaded XML papers | 24 |
| Estimated pages | 265 |
| Body words | 126,369 |
| Estimated tokens | 164,291 |
| Raw XML size | 2.79 MiB |
| Average tokens per paper | 6,845 |
| Average tokens per page | 620 |

## Paper Licences

| Paper | Licence |
|---|---|
| Tamil Nadu STEPS Survey | CC BY 4.0 |
| Epidemiology of type 2 diabetes in India | CC BY-NC-SA 4.0 |
| Meta-analysis of SGLT-2 inhibitors and heart failure | CC BY 4.0 |
| DPP-4 inhibitors and risk of hypoglycaemia | CC BY-NC 3.0 |
| Metabolic and clinical markers of T2D in obese Indians: an age-sex matched case-control study | CC BY 4.0 |
| Digital lifestyle program in type 2 diabetes in India | CC BY 4.0 |
| CURES study diabetes complications | CC BY-NC-SA 4.0 |
| Diet and Exercise Effects on Glucose Metabolism | CC BY 4.0 |
| Expert Consensus Statement on Simplified Glycemic Care in Patients With Type 2 Diabetes Mellitus | CC BY 4.0 |
| Out-of-Pocket Expenditure and Catastrophic Health Spending Among Patients With Type 2 Diabetes in Rural Tamil Nadu: A Cross-Sectional Study | CC BY 4.0 |
| Interplay Between the American Diabetes Association's ABC Targets for Diabetes, Insulin Resistance Indices, and Dyslipidemia in Indian Type 2 Diabetes Patients | CC BY 4.0 |
| Assessment of Prevalence and Risk Factors of Diabetes Distress Among Patients With Type 2 Diabetes Mellitus in an Urban Area of Chengalpattu District, India: A Cross-Sectional Study | CC BY 4.0 |
| Treatment Compliance Among People With Type 2 Diabetes in Rural Tamil Nadu, India: Prevalence, Associated Factors, and a Comparison of Public and Private Care | CC BY 4.0 |
| Insulin Resistance and Beta-Cell Function in the Context of Dyslipidemia in a Non-obese Indian Population With Type 2 Diabetes | CC BY 4.0 |
| Understanding Diabetes Through the Patients' Lens: A Mixed-Methods Study on Experiences and Outcomes in Urban Areas of Rajasthan, India | CC BY 4.0 |
| Unmasking the Emotional and Behavioral Determinants of Glycemic Control in Diabetes Management | CC BY 4.0 |
| Urban-Rural Comparison of Knowledge and Practices of Diabetes Mellitus Among Type 2 Diabetic Population in Telangana: A Cross-Sectional Study | CC BY 4.0 |
| Dietary Practices Among Type 2 Diabetes Patients Visiting a Non-communicable Disease (NCD) Clinic in a District of Western India: A Cross-Sectional Study | CC BY 4.0 |
| Determinants of Poor Glycemic Control Among Type 2 Diabetes Patients | CC BY 4.0 |
| Type 2 Diabetes Mellitus and Cardiometabolic Prospects | CC BY 4.0 |
| Type 2 Diabetes Mellitus: New Pathogenetic Mechanisms Treatment and Complications | CC BY 4.0 |
| Differentially Expressed Genes and Pathways in Diabetes | CC BY 4.0 |
| Advances in Research on Type 2 Diabetes Mellitus Targets and Therapeutic Agents | CC BY 4.0 |
| Mobile Reminders to Improve Opportunistic Screening of Type 2 Diabetes | CC BY 4.0 |

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
