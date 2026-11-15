# Source matrix

> **Notes, not submission text.** The "Notes" column is study material compiled from each paper's abstract (or, for course readings, the PDF), so you can decide what to read closely. Do not paste it into the review: the course allows AI for aggregating sources, not for writing the review.

One row per entry in [`references.bib`](references.bib). How each was found is in [`search-log.md`](search-log.md).

**Topic tags** (they match the Related Work subsections in `paper/main.tex`):

| Tag | Meaning |
|---|---|
| `agent-repair` | LLM agents and agentless pipelines for debugging, program repair and issue resolution |
| `aci` | Agent–computer interfaces and tool use |
| `runtime-context` | Execution feedback, debugger state or other context beyond the code given to an LLM |
| `logs-llm` | LLMs for log parsing and log analysis |
| `aiops-rca` | LLMs and agents over operational telemetry (logs, metrics, traces) for incidents and root-cause analysis |
| `protocols-safety` | Agent tool protocols (MCP), untrusted tool output, sensitive data in logs |
| `context-limits` | How LLMs use long inputs |
| `eval-method` | Evaluation methodology |

**Citation counts** were retrieved on 2026-11-15 from the Semantic Scholar Graph API (S2) and OpenAlex (OA). The two count differently (S2 also counts preprint citations), so compare papers within one column. "–" means the service had no record.

| # | Key | Venue, year | Tag | Notes (not submission text) | Cites S2 / OA |
|---|---|---|---|---|---|
| 1 | `bouzenia2025repairagent` | ICSE 2025 | `agent-repair` | Course reading. LLM (GPT-3.5) agent that chooses tools to gather bug information, find repair ingredients and validate fixes; a finite-state machine guides tool use. Evaluated on Defects4J: 164 bugs fixed, 39 not fixed by prior tools; about 270k tokens (14 US cents) per bug. | 550 / 491 |
| 2 | `xia2025agentless` | FSE 2025 (PACMSE) | `agent-repair` | Course reading. "Agentless": fixed three-phase pipeline (localize, repair, validate patch); the LLM does not choose actions or tools. SWE-bench Lite: 32.00% (96 fixes) at $0.70 average. Manual audit of Lite yields SWE-bench Lite-S without issues that leak the fix or lack information. | 403 / 876 |
| 3 | `jimenez2024swebench` | ICLR 2024 | `agent-repair` | Benchmark of 2,294 real GitHub issues and their PRs from 12 Python repositories; the model edits the repository and is graded by the PR's tests. In the arXiv version the best model (Claude 2) resolves 1.96%. | 4917 / 2106 |
| 4 | `zhang2024autocoderover` | ISSTA 2024 | `agent-repair` | LLM plus AST-aware code search over classes and methods; adds spectrum-based fault localization when tests exist. SWE-bench Lite (300 issues): 19% resolved, $0.43 average cost. | 559 / 549 |
| 5 | `liu2026agentsurvey` | TOSEM 2026 | `agent-repair` | Survey of 124 papers on LLM-based agents in SE, organised by SE task (requirements to debugging) and by agent component (planning, memory, perception, action). No experiment. | 313¹ / 302 |
| 6 | `yao2023react` | ICLR 2023 | `aci` | Prompting that interleaves reasoning traces with actions (tool calls). HotpotQA and FEVER with a Wikipedia API; ALFWorld and WebShop, where it beats imitation and RL baselines by 34 and 10 points absolute success. Basis of the RCA agent in row 18. | 13961 / 5900 |
| 7 | `yang2024sweagent` | NeurIPS 2024 | `aci` | Introduces the agent–computer interface (ACI): file viewer and editor, repository search and test execution designed for LM agents, with an analysis of how interface design changes agent behaviour. SWE-bench pass@1 12.5%, HumanEvalFix 87.7%. | 2496² / 1530 |
| 8 | `chen2024selfdebug` | ICLR 2024 | `runtime-context` | Few-shot prompting in which the model runs its program, explains the code, and uses execution results to fix it ("rubber duck debugging"). Spider, TransCoder, MBPP: up to +12% where unit tests exist, +2–3% on Spider without tests. | 1537 / 853 |
| 9 | `zhong2024ldb` | Findings of ACL 2024 | `runtime-context` | LDB splits a program into basic blocks, records intermediate variable values at runtime, and has the LLM check each block against the task. HumanEval, MBPP, TransCoder: up to +9.8% over baselines for several LLMs. | 231 / 221 |
| 10 | `levin2025chatdbg` | FSE 2025 (PACMSE) | `runtime-context` | LLM inside LLDB, GDB and Pdb; the LLM can drive the debugger (walk stacks, inspect state) and report back. C/C++ programs with known bugs and Python scripts and notebooks; for Python, one query gave an actionable fix 67% of the time, 85% with one follow-up. | 36 / 47 |
| 11 | `yuan2025debuggym` | arXiv 2025 (preprint) | `runtime-context` | Text environment that gives LLM agents tools for interactive debugging, including pdb. Benchmarks named in search results (check in the PDF): Aider, Mini-nightmare, SWE-bench. Not peer reviewed; the abstract reports no numbers. | 22 / 31 |
| 12 | `li2024diff` | FSE 2024 (PACMSE) | `runtime-context` | Course reading. Commit message generation treated as knowledge-intensive reasoning: a ReAct-prompted LLM (OMG) retrieves software context beyond the diff. Human evaluation: +30.2% over human-written messages, +71.6% over prior CMG methods. Relevant as evidence that context beyond the code changes LLM output quality. | 41 / 37 |
| 13 | `ma2024llmparser` | ICSE 2024 | `logs-llm` | Few-shot-tuned generative LLMs (Flan-T5-small/base, LLaMA-7B, ChatGLM-6B) as log parsers. 16 open-source systems: 96% average parsing accuracy; smaller models can match larger ones. | 153 / 121 |
| 14 | `jiang2024lilac` | FSE 2024 (PACMSE) | `logs-llm` | In-context-learning log parser with hierarchical demonstration sampling and an adaptive template cache that cuts LLM calls by orders of magnitude. Large-scale public datasets: +69.5% average F1 of template accuracy. | 161 / 179 |
| 15 | `jiang2024loghub2` | ISSTA 2024 | `logs-llm` | Loghub-2.0 benchmark (14 datasets, 3.6M lines each on average) and a re-evaluation of 15 log parsers; new metric robust to imbalanced data; first look at parsing logs of rare events. | 133 / 131 |
| 16 | `ahmed2023rca` | ICSE 2023 | `aiops-rca` | GPT-3.x models (zero-shot, fine-tuned, multi-task) recommend root cause and mitigation for cloud incidents. Over 40,000 Microsoft incidents, lexical and semantic metrics, plus human evaluation by incident owners. | 164 / 207 |
| 17 | `chen2024rcacopilot` | EuroSys 2024 | `aiops-rca` | RCACopilot: routes an incident to a handler by alert type, collects diagnostic data (logs, traces), and an LLM predicts the root-cause category with an explanation. A year of Microsoft incidents: accuracy up to 0.766; the collection part has run in production for over four years. | 348 / 310 |
| 18 | `roy2024rcaagents` | FSE 2024 Companion (industry) | `aiops-rca` | ReAct agent with retrieval tools that can fetch logs and other diagnostics for RCA. Out-of-distribution Microsoft incidents: competitive with retrieval and reasoning baselines, higher factual accuracy; incident discussions as input did not help; case study adding a team's diagnostic services as tools. | 195 / 176 |
| 19 | `xu2025openrca` | ICLR 2025 | `aiops-rca` | OpenRCA benchmark: 335 failures from three enterprise systems with 68 GB of logs, metrics and traces; the LLM must name the root cause. Best result, Claude 3.5 with the authors' RCA-agent: 11.34% solved. | 106³ / – |
| 20 | `chen2025aiopslab` | MLSys 2025 | `aiops-rca` | AIOpsLab: deploys microservice environments, injects faults, generates load, exports telemetry, and gives agents an interface to act and be scored; evaluates current LLM agents on operations tasks (task counts and results are in the paper, not the abstract). | 109 / 48 |
| 21 | `hou2026mcp` | TOSEM 2026 | `protocols-safety` | Model Context Protocol study: MCP server lifecycle (4 phases, 16 activities), threat taxonomy (4 attacker types, 16 scenarios), real-world case studies, safeguards per phase. Qualitative. Relevant to the Jaeger MCP server in logq. | 611 / 790 |
| 22 | `greshake2023injection` | AISec 2023 (CCS workshop) | `protocols-safety` | Indirect prompt injection: instructions planted in data an LLM application retrieves. Taxonomy of impacts; demonstrations against Bing Chat (GPT-4), code-completion engines and synthetic GPT-4 apps. Relevant because container logs are text an attacker can influence. | 2575 / 1946 |
| 23 | `aghili2025logprivacy` | FSE 2025 (PACMSE) | `protocols-safety` | What to anonymise in software logs: sensitive attributes in 25 public log datasets, GDPR/CCPA review, systematic literature review of log anonymisation, survey of 45 practitioners. Relevant to logq's redaction. | 15 / 18 |
| 24 | `liu2024lostmiddle` | TACL 2024 | `context-limits` | Multi-document QA and key-value retrieval with the relevant item at varied positions: accuracy is U-shaped (best at the start or end) and falls as inputs grow, also for long-context models. Relevant to filtering logs before the agent reads them. | 6041 / 3620 |
| 25 | `ahmed2025annotation` | MSR 2025 | `eval-method` | Course reading. Six LLMs on ten annotation tasks from five prior datasets (e.g. judging code summaries): some LLM annotation reaches human inter-rater agreement; proposes model–model agreement and model confidence to decide when LLMs can replace annotators. Possible method reference if the evaluation uses an LLM judge. | 134 / 108 |

¹ S2 had no record for the TOSEM DOI; the count is from S2's arXiv record (2409.02977).
² S2 holds two records: 2,496 on the arXiv record (2405.15793), 861 on the NeurIPS DOI record.
³ Found by S2 title match; OpenAlex returned no matching record.
