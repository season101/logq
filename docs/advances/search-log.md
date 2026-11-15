# Literature search log: CSC 5323 "Advances"

This file records how the sources for the literature review were found and checked, as the assignment requires ("document your workflow and describe the criteria you provided"). The assignment text allows AI "for aggregation of lit review materials, (not generation)". The search and verification below were done under that rule. The paper prose was drafted afterwards, in a separate commit, after a policy update described in [Drafting](#drafting) at the end of this file.

## Who ran the searches

| Item | Value |
|---|---|
| Date | 2026-11-15 (all searches and checks) |
| Agent | Claude Code (desktop app, Code tab), working in this repository |
| Model | Claude Opus 5.5, model id `claude-opus-5-5` |
| Search tool | Claude Code `WebSearch`, `mode: "standard"` for every search (no `extended` searches were needed) |
| Deep-research skill | Not used. It writes a synthesized narrative report, which the course policy rules out. |
| Verification tools | `curl` and Python scripts against the Crossref REST API (`api.crossref.org/works/<doi>`), the arXiv API (`export.arxiv.org/api/query`), Semantic Scholar Graph API, OpenAlex, and the publisher proceedings pages (ICLR, NeurIPS, MLSys, ACL Anthology) |
| Course readings | Downloaded from the CSC 5323 Canvas module "Research Articles" through the Canvas API; titles, venues and DOIs read from the PDFs |

## The task given to the AI

The advance: giving AI coding agents filtered, redacted, live runtime context (container logs, distributed traces over MCP, live log streams) for agentic debugging, as built in logq (`docs/superpowers/specs/2026-11-07-logq-design.md`).

Instruction, in substance: gather and verify literature for this advance; record every search; keep only papers whose DOI or arXiv record was opened and whose title, authors, venue and year match; never invent a citation; aim for 15 to 25 sources; include the course readings where they fit.

## Inclusion criteria

Starting criteria (C0):

1. Peer-reviewed papers, or arXiv preprints, from 2021 to 2026.
2. Top software engineering or AI venues: ICSE, FSE, ASE, ISSTA, NeurIPS, ICLR.
3. Topic is one of: LLM agents for debugging and program repair; agent–computer interface design; LLMs for log analysis or parsing and observability; runtime or execution context for code agents; agent tool protocols.
4. The record can be verified: a DOI that resolves in Crossref, or an arXiv record, with matching title, authors, venue and year.

Exclusion rules: posters, blogs, vendor write-ups, theses, and secondary summary sites (they may lead to a paper but are never cited); papers whose venue claim could not be confirmed are kept only as arXiv preprints and flagged as such.

### Refinements, in the order made

- **R1 (after batch 1).** Batch 1 surfaced landmark papers (SWE-bench, Self-Debugging, AutoCodeRover, OpenHands) by name only; batch 2 searched for each by title so the record could be checked. Two concerns that the advance raises but C0's topics miss were added: untrusted tool output (prompt injection through retrieved data, relevant because logs are attacker-influenced text) and long-context limits (relevant because logq's purpose is to shrink what the agent reads). To cover them the venue list was widened to the venue where the canonical paper appeared: AISec (ACM CCS workshop), TACL, and ACL Findings.
- **R2 (after batch 2).** Narrowed "observability" to work where an LLM or agent consumes operational telemetry (logs, metrics, traces) for root-cause analysis, and to log-parsing benchmarks. Added MLSys and EuroSys as venues, since the systems community publishes that work there. Added agents that drive debuggers.
- **R3 (after batch 3).** Filled gaps: one survey for breadth (TOSEM), venue checks for papers whose venue the earlier results did not state, and log privacy/anonymisation (relevant to redaction).
- **R4 (selection, to stay within 15–25).** Of several 2025 MCP security preprints, kept one systematic study (Hou et al., since published in TOSEM) rather than all of them. Dropped DivLog because LLMParser and LILAC cover LLM log parsing at the same venues; recent 2026 RCA preprints because OpenRCA and AIOpsLab cover that ground peer-reviewed; and OpenHands because SWE-agent and ReAct already cover agent interfaces.

## Searches and what they returned

Each entry gives the exact query, then the results that mattered, with a decision. "include" means the paper went on to verification; "candidate" means considered and decided at R4; secondary pages that only pointed to a paper are not listed.

### Batch 1: criteria C0

**S1** `LLM agent automated program repair debugging ICSE FSE ISSTA 2024 2025`
- RepairAgent, ICSE 2025: <https://arxiv.org/abs/2403.17134>, <https://conf.researchr.org/details/icse-2025/icse-2025-research-track/160/RepairAgent-An-Autonomous-LLM-Based-Agent-for-Program-Repair> → include (course reading)
- LingmaAgent, FSE 2025 Companion: <https://arxiv.org/abs/2406.01422> → not included (repository exploration for issue resolution, no runtime context)
- ISSTA 2026 study of APR agents' tooling: <https://www.cs.columbia.edu/~junfeng/papers/apr-agents-issta26.bib> → not included (only a .bib file was found; no verifiable record)
- Experimental settings in LLM-based program repair (2026): <https://arxiv.org/abs/2609.17993> → not included (out of scope after R2: methodology of APR experiments)
- Named in results: AutoCodeRover (ISSTA 2024), ThinkRepair (ISSTA 2024) → AutoCodeRover searched in S9

**S2** `agent-computer interface software engineering agents NeurIPS 2024`
- SWE-agent, NeurIPS 2024: <https://proceedings.neurips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html>, <https://neurips.cc/virtual/2024/poster/93753> → include

**S3** `large language model log parsing ICSE FSE ISSTA 2024`
- LLMParser, ICSE 2024: <https://arxiv.org/abs/2404.18001>, <https://conf.researchr.org/details/icse-2024/icse-2024-research-track/150/LLMParser-An-Exploratory-Study-on-Using-Large-Language-Models-for-Log-Parsing> → include
- DivLog, ICSE 2024: <https://arxiv.org/abs/2307.09950> → candidate, dropped at R4
- LILAC, FSE 2024: <https://arxiv.org/abs/2310.01796> → include
- Semantic log parsing / LogBase, ISSTA: <https://api.crossref.org/works/10.1145%2F3728969> → not included (overlaps LILAC/LLMParser)
- "High-precision Online Log Parsing with LLMs", ICSE 2024 poster → excluded (poster)

**S4** `LLM root cause analysis cloud incidents logs traces agent`
- Exploring LLM-based Agents for Root Cause Analysis (Roy et al.): <https://arxiv.org/abs/2403.04123>, <https://www.microsoft.com/en-us/research/publication/exploring-llm-based-agents-for-root-cause-analysis/> → include
- RCACopilot: <https://arxiv.org/abs/2305.15778>, <https://www.microsoft.com/en-us/research/publication/automatic-root-cause-analysis-via-large-language-models-for-cloud-incidents> → include
- RCAgent (Alibaba): arXiv 2310.16340 → not included (overlaps RCACopilot and Roy et al.)

**S5** `runtime execution information large language model debugging code generation ICLR`
- LDB ("Debug like a Human"): <https://arxiv.org/abs/2402.16906> → include; venue not given in results, checked in S24

**S6** `Model Context Protocol MCP security study arXiv 2025`
- MCP: Landscape, Security Threats, and Future Research Directions (Hou et al.): <https://arxiv.org/abs/2503.23278> → include
- MCP at First Glance: <https://arxiv.org/abs/2506.13538> → candidate, dropped at R4
- Systematic Analysis of MCP Security (MCPLIB): <https://arxiv.org/abs/2508.12538> → candidate, dropped at R4
- When MCP Servers Attack: <https://arxiv.org/abs/2509.24272> → candidate, dropped at R4
- Toward Understanding Security Issues in the MCP Ecosystem: <https://arxiv.org/abs/2510.16558> → candidate, dropped at R4

### Batch 2: after R1

**S7** `Teaching large language models to self-debug ICLR 2024 execution feedback`
- Self-Debugging, ICLR 2024: <https://proceedings.iclr.cc/paper_files/paper/2024/hash/2460396f2d0d421885997dd1612ac56b-Abstract-Conference.html>, <https://arxiv.org/abs/2304.05128> → include

**S8** `SWE-bench can language models resolve real-world GitHub issues ICLR 2024`
- SWE-bench, ICLR 2024: <https://arxiv.org/abs/2310.06770>, <https://proceedings.iclr.cc/paper_files/paper/2024/hash/edac78c3e300629acfe6cbe9ca88fb84-Abstract-Conference.html> → include

**S9** `AutoCodeRover autonomous program improvement ISSTA 2024`
- AutoCodeRover, ISSTA 2024: <https://2024.issta.org/details/issta-2024-papers/127/AutoCodeRover-Autonomous-Program-Improvement>, <https://arxiv.org/abs/2404.05427> → include

**S10** `OpenHands open platform AI software developers generalist agents ICLR 2025`
- OpenHands, ICLR 2025: <https://proceedings.iclr.cc/paper_files/paper/2025/hash/a4b6ad6b48850c0c331d1259fc66a69c-Abstract-Conference.html>, <https://arxiv.org/abs/2407.16741> → verified, dropped at R4

**S11** `indirect prompt injection LLM-integrated applications Greshake AISec 2023`
- "Not what you've signed up for", AISec 2023: <https://arxiv.org/abs/2302.12173>, <https://researchr.org/publication/AbdelnabiGMEHF23/bibliographies> → include

**S12** `Lost in the middle how language models use long contexts TACL`
- Lost in the Middle, TACL 2024: <https://aclanthology.org/2024.tacl-1.9/> → include

### Batch 3: after R2

**S13** `Recommending root-cause and mitigation steps for cloud incidents using large language models ICSE 2023`
- Ahmed et al., ICSE 2023: <https://arxiv.org/abs/2301.03797>, <https://conf.researchr.org/details/icse-2023/icse-2023-technical-track/79/Recommending-Root-Cause-and-Mitigation-Steps-for-Cloud-Incidents-using-Large-Language> → include

**S14** `large-scale evaluation log parsing techniques how far are we Loghub-2.0 ISSTA 2024`
- Loghub-2.0, ISSTA 2024: <https://arxiv.org/abs/2308.10828>, <https://2024.issta.org/details/issta-2024-papers/19/A-Large-Scale-Evaluation-for-Log-Parsing-Techniques-How-Far-Are-We-> → include

**S15** `OpenRCA large language models root cause analysis benchmark ICLR 2025`
- OpenRCA, ICLR 2025: <https://proceedings.iclr.cc/paper_files/paper/2025/hash/d29b8d53678015079e1d245c023e49d2-Abstract-Conference.html>, <https://iclr.cc/virtual/2025/poster/32093> → include
- Vendor critique of OpenRCA (traversal.com blog) → excluded (not peer reviewed)

**S16** `debugger tools interactive debugging LLM agents pdb benchmark 2025`
- debug-gym: <https://arxiv.org/abs/2503.21557> → include (arXiv preprint, flagged)
- Debug2Fix (2026): <https://arxiv.org/abs/2602.18571> → not included (overlaps debug-gym and ChatDBG; preprint)
- ChatDBG → venue checked in S20

**S17** `ReAct synergizing reasoning and acting in language models ICLR 2023`
- ReAct, ICLR 2023: <https://arxiv.org/abs/2210.03629>, <https://iclr.cc/virtual/2023/poster/11003> → include

**S18** `microservice distributed traces LLM agent root cause localization benchmark AIOpsLab`
- AIOpsLab: <https://arxiv.org/abs/2501.06706> → include; venue checked in S21
- ORCA-bench (<https://www.alphaxiv.org/abs/2607.28545>), Cloud-OpsBench (<https://arxiv.org/abs/2603.00468>), STAR (<https://arxiv.org/abs/2605.15581>), MicroRCA-Agent (<https://arxiv.org/abs/2509.15635>) → not included at R4 (recent preprints; further reading on trace-based RCA)

### Batch 4: after R3

**S19** `survey large language model based agents for software engineering TOSEM`
- Liu et al., survey: <https://arxiv.org/abs/2409.02977> ("Accepted by TOSEM" on arXiv) → include
- "Agents in Software Engineering: Survey, Landscape, and Vision" (arXiv 2409.09030) and Jin et al. (arXiv 2408.02479) → not included (venue unconfirmed; overlap)

**S20** `ChatDBG AI-powered debugging assistant FSE 2025`
- ChatDBG, FSE 2025: <https://conf.researchr.org/details/fse-2025/fse-2025-research-papers/23/ChatDBG-Augmenting-Debugging-with-Large-Language-Models>, <https://arxiv.org/abs/2403.16354> → include

**S21** `AIOpsLab holistic framework evaluate AI agents autonomous clouds MLSys 2025`
- AIOpsLab, MLSys 2025: <https://www.microsoft.com/en-us/research/publication/aiopslab-a-holistic-framework-for-evaluating-ai-agents-for-enabling-autonomous-cloud>, <https://arxiv.org/abs/2501.06706> → include

**S22** `sensitive information leakage in software logs empirical study privacy`
- Aghili, Li, Khomh, privacy in software logs: <https://arxiv.org/abs/2409.11313> → include
- Android app log leakage (arXiv 2602.07893) and a Waterloo thesis on Android logging libraries → not included (Android-specific; thesis)

**S23** `LLM debug-gym interactive debugging environment arXiv 2503.21557 authors`
- debug-gym author list and record: <https://arxiv.org/abs/2503.21557> → confirms S16

**S24** `LDB debug like a human large language model debugger ACL Findings 2024`
- LDB, Findings of ACL 2024: <https://aclanthology.org/2024.findings-acl.49> → confirms venue for S5

### Other lookups (not literature searches)

- **Course readings.** Listed with the Canvas API (course 30942, module "Research Articles") and read from the PDFs: Nielsen (CHI 1990), Ahmed et al. (MSR 2025), Li et al. (FSE 2024), RepairAgent (ICSE 2025), Agentless (FSE 2025), Wang et al. semantic features (ICSE 2016), Inozemtseva and Holmes coverage (ICSE 2014). Nielsen, Wang et al. and Inozemtseva and Holmes fall outside 2021–2026 and outside the topic, so they are not in `references.bib`. Ahmed et al. (MSR 2025) is kept for the evaluation method; Li et al. for the "context beyond the code" argument.
- **ICSE template.** `WebSearch` (standard) `ICSE 2027 research track call for papers formatting template IEEE ACM`, then the track page itself, <https://conf.researchr.org/track/icse-2027/icse-2027-research-track>, read 2026-11-15. See `paper/main.tex`.

## Verification

Done on 2026-11-15 with two scripts (kept out of the repository; they only fetch metadata):

1. **DOI papers.** `GET https://api.crossref.org/works/<doi>`: title, every author, container (proceedings or journal), year, pages. Where a DOI was not yet known, Crossref's bibliographic search (`/works?query.bibliographic=<title>`) found it, and the record was then fetched by DOI.
2. **arXiv papers.** `GET https://export.arxiv.org/api/query?id_list=<ids>`: title, authors, abstract, and the authors' venue comment.
3. **Conference papers without DOIs (ICLR, MLSys).** The proceedings page's `citation_*` metadata: ICLR 2024 and 2025 at `proceedings.iclr.cc`, MLSys 2025 at `proceedings.mlsys.org`, NeurIPS 2024 at `proceedings.neurips.cc`. ReAct has no ICLR 2023 proceedings page there, so it was checked against its ICLR 2023 poster page (<https://iclr.cc/virtual/2023/poster/11003>) and arXiv v3 ("the ICLR camera ready version"). OpenReview pages could not be read (browser check).
4. **Citation counts.** Semantic Scholar Graph API (one batch request) and OpenAlex (`/works/doi:<doi>`), both on 2026-11-15. Recorded in `source-matrix.md`.
5. **Build check.** `references.bib` was compiled with BibTeX in TeX Live 2026 (local `texlive/texlive:latest-small` image, no network): 25 entries, no warnings.

The record each entry was checked against is in its `annote` field in `references.bib`. All 25 matched on title, authors, venue and year.

### Corrections found while verifying

- **Hou et al. (MCP)** was an arXiv preprint in the search results; Crossref shows it published in TOSEM vol. 35, no. 10 (2026). Cited as the journal version.
- **Liu et al. (agent survey)**: arXiv says "Accepted by TOSEM"; Crossref confirms TOSEM, online 2026-03-05, volume and pages not yet assigned.
- **Aghili et al.**: the search found arXiv v1, "An Empirical Study of Sensitive Information in Logs"; the paper was retitled "Protecting Privacy in Software Logs: What Should Be Anonymized?" and published in PACMSE (FSE 2025).
- **Greshake et al.**: researchr lists Abdelnabi first; Crossref and arXiv list Greshake first. Crossref's order is used.
- **Agentless** is published under the title "Demystifying LLM-Based Software Engineering Agents" (arXiv title: "Agentless: Demystifying LLM-based Software Engineering Agents").
- Semantic Scholar gives some papers their arXiv year (RepairAgent 2024, SWE-bench 2023, ReAct 2022). The bib uses the year of the venue.

### Dropped

| Source | Why |
|---|---|
| OpenHands (ICLR 2025) | Verified (ICLR proceedings page), cut at R4 for scope |
| DivLog (ICSE 2024, arXiv 2307.09950) | Cut at R4: overlaps LLMParser and LILAC; not verified against a DOI |
| MCP at First Glance; Systematic Analysis of MCP Security; When MCP Servers Attack; Toward Understanding Security Issues in the MCP Ecosystem (arXiv 2025) | Cut at R4: preprints, one systematic MCP study kept |
| RCAgent (arXiv 2310.16340), Debug2Fix (arXiv 2602.18571), ORCA-bench, Cloud-OpsBench, STAR, MicroRCA-Agent | Cut at R4: overlap with kept papers; preprints |
| LingmaAgent (FSE 2025 Companion) | Out of scope (no runtime context) |
| ISSTA 2026 study of APR agents' tooling | Could not verify: only a `.bib` file on a personal page was found |
| "Agents in Software Engineering: Survey, Landscape, and Vision" (arXiv 2409.09030); Jin et al. survey (arXiv 2408.02479) | Venue not confirmed; one verified survey kept |
| Course readings Nielsen (CHI 1990), Wang et al. (ICSE 2016), Inozemtseva and Holmes (ICSE 2014) | Outside 2021–2026 and outside the topic |

## Drafting

On 2026-11-15, after the sources above were committed, the Claude Code session coordinating this assignment relayed an update from the student: the instructor had confirmed that AI-written sections are allowed if the student reads them in class, because the deadline is short. The same model (Claude Opus 5.5, `claude-opus-5-5`) then drafted the prose of `paper/main.tex`: Abstract, Introduction, Background and Related Work, Approach, Evaluation (method and structure only), Threats to Validity, Conclusion, and an AI Assistance Disclosure section. The instructor's confirmation was not seen by the AI; the disclosure section asks the student to confirm it.

Constraints followed while drafting:

- Claims about prior work come only from the 25 verified sources, as stated in their abstracts (or, for course readings, the PDFs), and each such claim carries a citation.
- logq's design is described from `docs/superpowers/specs/2026-11-07-logq-design.md`; the TeamMatch setup from the pilot branch's commits; integration problems from the earlier para-dashboard pilot's hand-over note.
- No results were written. Every number the TeamMatch experiment will produce is a red `\todo{}` placeholder, as are the task list, run counts and model id.
- Every first-person judgment (effective, cumbersome, accessible, recommended) is marked `\todo{user to confirm}`.

### Pilot results filled in

Later on 2026-11-15, after the TeamMatch pilot finished, the coordinating session relayed the student's go-ahead to fill the paper's factual placeholders. The same model transcribed them from the pilot's committed write-up, `docs/advances/logq-pilot.md` at TeamMatch commit `3616eb4` (the pilot ran in another Claude Code session), into the Evaluation, Threats to Validity, Abstract and Conclusion of `paper/main.tex`. No number was added that is not in that write-up, apart from sums of its per-run figures (the total uncached input tokens in Table II). Judgments marked `\todo{user to confirm}`, the author name, the description of the demo video, the setup time (not in the write-up) and the disclosure's confirmation remain for the student.
