# logq

Filtered, redacted Docker container logs for AI coding agents.

logq reads the logs of a Docker Compose project, keeps the lines that matter, merges them in time order, removes secrets, and links each line to its request trace in a local Jaeger. An agent such as Claude Code gets a few filtered lines instead of thousands of raw ones, and reads the traces through Jaeger's MCP server.

## Paper and demo (CSC 5323, Advances)

- **Paper:** [Helping AI Coding Agents Read Container Logs: A Literature Review and a Pilot of logq](https://github.com/season101/logq/blob/docs/advances-lit-review/docs/advances/paper/main.tex) (LaTeX source), Sijan Malla, Louisiana Tech University
- **AI use statement:** [cover.tex](https://github.com/season101/logq/blob/docs/advances-lit-review/docs/advances/paper/cover.tex)
- **Literature search:** [search log](https://github.com/season101/logq/blob/docs/advances-lit-review/docs/advances/search-log.md) (model, queries, inclusion rules) and [source matrix](https://github.com/season101/logq/blob/docs/advances-lit-review/docs/advances/source-matrix.md) (all 25 verified sources and why each was kept or left out)
- **Pilot on TeamMatch:** feature branch [`feat/infallible-albattani-7f1466`](https://github.com/season101/teammatch/tree/feat/infallible-albattani-7f1466), with the [pilot write-up](https://github.com/season101/teammatch/blob/feat/infallible-albattani-7f1466/docs/advances/logq-pilot.md) and the [demo script](https://github.com/season101/teammatch/blob/feat/infallible-albattani-7f1466/docs/advances/logq-demo-script.md)

Pilot result, one run per task: Claude Opus 5.5 found all three seeded root causes with and without logq; with logq it used 27 turns instead of 30, about 20% lower estimated cost and a third fewer characters of logs and traces. A trend, not proof.

## Install

Needs Python 3.11+ and the Docker CLI. No other dependencies.

```bash
uv tool install --editable .
```

## Use

```bash
logq ps                          # containers, with stopped/restarting/unhealthy ones marked "!"
logq query -s api --since 10m    # warnings and errors from one service
logq query --status 5xx          # failed requests
logq query --trace <id>          # one request across all services, with a Jaeger link
logq follow                      # live warnings, errors and container events
logq ui                          # start the shared local Jaeger
```

`-p NAME` picks a Compose project; without it, logq uses the project whose folder you are in. Each query ends with a footer saying what was searched. Redaction is always on.

## Traces

`logq ui` starts one Jaeger container on `127.0.0.1` and prints the `OTEL_*` settings an app needs. To give Claude Code the Jaeger tools, run once:

```bash
claude mcp add --transport http --scope user jaeger http://localhost:16686/api/ai/mcp/
```

## Claude Code skill

[`skill/SKILL.md`](skill/SKILL.md) tells Claude Code when and how to use logq. Install it for every project with:

```bash
ln -s "$PWD/skill" ~/.claude/skills/docker-logs
```

## Logging contract

logq works on any logs, but filtering by trace, route or status needs the app to follow [docs/logging-contract.md](docs/logging-contract.md): one JSON object per line and one `request finished` line per request, plus an `X-Request-ID` response header that holds the trace ID.

## Design and tests

Design: [docs/superpowers/specs/2026-11-07-logq-design.md](docs/superpowers/specs/2026-11-07-logq-design.md).

```bash
uv run pytest
```
