# Logging contract

What an app logs so `logq` can filter it precisely. Plain-text logs still work, but only on a best-effort basis (level guessed from a word in the line, multi-line tracebacks folded by heuristics). Follow this contract and `logq query --trace <id>` returns one request across every service.

Field names follow the OpenTelemetry semantic conventions.

## Format

- One JSON object per line on stdout. No multi-line output: exceptions go in the `exception.*` fields.
- Logs go to stdout, not to files inside the container.

## Fields

| Field | When | Notes |
|---|---|---|
| `timestamp` | always | RFC 3339 / ISO 8601, UTC. logq sorts by Docker's own timestamp, so a skewed clock does not reorder output. |
| `severity_text` | always | `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` (case-insensitive; `WARNING` and `CRITICAL` are understood). |
| `body` | always | The message. Short, no secrets, no whole payloads. |
| `service.name` | always | The service's name. Same value as `OTEL_SERVICE_NAME`. If absent, logq uses the compose service label. |
| `trace_id` | inside a request or job | 32 hex characters, the W3C trace ID. |
| `span_id` | when a span exists | 16 hex characters. |
| `http.request.method` | `request finished` | `GET`, `POST`, ... |
| `http.route` | `request finished` | The route template, not the raw path: `/api/orders/{id}`, never `/api/orders/8841`. |
| `http.response.status_code` | `request finished` | Integer. |
| `duration_ms` | `request finished` | Integer or float, milliseconds. |
| `exception.type` | errors | Class name, e.g. `KeyError`. |
| `exception.message` | errors | The exception message. |
| `exception.stacktrace` | errors | The whole stack trace as one string with `\n` escapes. |
| `code.function` | optional | Function that logged. Enables `logq query --func`. |

Example (one line, wrapped here for reading):

```json
{"timestamp":"2026-11-07T18:04:31.214Z","severity_text":"ERROR","body":"KeyError: 'sku'",
 "service.name":"api","trace_id":"7f3a9c21b04e4d5a8e12c6d9f0a3b457","span_id":"a1b2c3d4e5f60718",
 "code.function":"create_order","exception.type":"KeyError","exception.message":"'sku'",
 "exception.stacktrace":"Traceback (most recent call last):\n  File \"orders/views.py\", line 42, in create_order\n    sku = data['sku']\nKeyError: 'sku'"}
```

## One `request finished` line per HTTP request

Log it when the response has been sent, with the message `request finished`:

```json
{"timestamp":"2026-11-07T18:04:31.220Z","severity_text":"INFO","body":"request finished",
 "service.name":"api","trace_id":"7f3a9c21b04e4d5a8e12c6d9f0a3b457","span_id":"a1b2c3d4e5f60718",
 "http.request.method":"POST","http.route":"/api/orders","http.response.status_code":500,"duration_ms":812}
```

logq's default level is `warn`, so INFO lines like this one do not show by default. Use `logq query --status 5xx -l info`, or `--trace <id>`, which defaults to `debug`.

## Errors

Log every handled and unhandled error once, at `ERROR` (or `FATAL`), with `exception.type`, `exception.message` and `exception.stacktrace`. Do not print the trace a second time to stderr.

## Trace context

- Incoming requests: read the W3C `traceparent` header (`00-<trace_id>-<span_id>-<flags>`). If it is missing, this service is the first one and creates the trace.
- Outgoing HTTP calls: send `traceparent` with the current trace ID. OpenTelemetry's HTTP client instrumentation does this for you.
- Queues and background jobs: put `traceparent` in the message headers (or job metadata) and continue the trace in the consumer.
- Every HTTP response carries `X-Request-ID: <trace_id>`, so `curl -si` shows the ID to pass to `logq query --trace`. The value is the same 32-character `trace_id` that appears in the logs.

## Never log

- Secrets: passwords, tokens, API keys, `Authorization` and `Cookie` headers, connection strings with credentials.
- Whole request or response bodies. Log IDs and sizes instead.
- Personal data: emails, phone numbers, names, addresses, payment details.

logq redacts common secret shapes (`[REDACTED]`) on every line it prints. That is a safety net, not the control: the app must not log them in the first place.

## Recipes

Prefer the libraries below over custom code. Set these environment variables on the service in every stack:

```
OTEL_SERVICE_NAME=api
OTEL_TRACES_EXPORTER=none
OTEL_METRICS_EXPORTER=none
OTEL_LOGS_EXPORTER=none
```

The three `none` exporters are the trace-IDs-only setup (phase 2): spans are created, so every log line gets a `trace_id`, but nothing is exported. "Traces in Jaeger (phase 3)" at the end of this file switches traces on.

### Python

Packages: `python-json-logger`, `opentelemetry-distro`, and the instrumentation for your framework (`opentelemetry-instrumentation-django`, `-fastapi`, `-flask`, ...). `opentelemetry-bootstrap -a install` adds the matching ones.

Start the server through the wrapper with log correlation on, which adds `otelTraceID`, `otelSpanID` and `otelServiceName` to every log record:

```
OTEL_PYTHON_LOG_CORRELATION=true opentelemetry-instrument gunicorn app.wsgi:application
```

Format logs as JSON and rename the OpenTelemetry attributes to the contract's names (python-json-logger 3.1+; older versions use `pythonjsonlogger.jsonlogger.JsonFormatter`):

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {
        "()": "pythonjsonlogger.json.JsonFormatter",
        "fmt": "%(levelname)s %(message)s %(otelTraceID)s %(otelSpanID)s %(otelServiceName)s %(funcName)s",
        "timestamp": True,
        "rename_fields": {
            "levelname": "severity_text", "message": "body", "funcName": "code.function",
            "otelTraceID": "trace_id", "otelSpanID": "span_id", "otelServiceName": "service.name",
            "exc_info": "exception.stacktrace",
        },
    }},
    "handlers": {"stdout": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "json"}},
    "root": {"handlers": ["stdout"], "level": "INFO"},
}
```

Add `exception.type` and `exception.message` with `logger.error(..., extra={...})` where you catch exceptions; logq reads `exception.stacktrace` alone if they are missing.

The `request finished` line and the `X-Request-ID` header need a small middleware (Django, Flask) or `asgi-correlation-id` (FastAPI, Starlette). That library sets `X-Request-ID` on responses and exposes the ID to the log formatter; make it generate the ID from the current OpenTelemetry trace ID so both are the same value.

### Node

Packages: `pino`, `pino-http`, `@opentelemetry/auto-instrumentations-node`. The pino instrumentation inside the auto-instrumentations package adds `trace_id` and `span_id` to every pino record. Start the app with the register hook:

```
node --require @opentelemetry/auto-instrumentations-node/register server.js
```

```js
const pino = require("pino");
const logger = pino({
  base: { "service.name": process.env.OTEL_SERVICE_NAME },
  messageKey: "body",
  timestamp: () => `,"timestamp":"${new Date().toISOString()}"`,
  formatters: { level: (label) => ({ severity_text: label.toUpperCase() }) },
});
const httpLogger = require("pino-http")({
  logger,
  serializers: { req: () => undefined, res: () => undefined }, // the default req/res objects carry headers (cookies, tokens)
  customSuccessMessage: () => "request finished",
  customErrorMessage: () => "request finished",
  customAttributeKeys: { responseTime: "duration_ms" },
  customProps: (req, res) => ({
    "http.request.method": req.method,
    "http.route": req.route ? req.baseUrl + req.route.path : undefined, // Express route template
    "http.response.status_code": res.statusCode,
  }),
});
```

Set `X-Request-ID` in a middleware before the routes:

```js
const { trace } = require("@opentelemetry/api");
app.use((req, res, next) => {
  res.setHeader("X-Request-ID", trace.getActiveSpan()?.spanContext().traceId ?? "");
  next();
});
```

logq also reads pino's `err` key (`err.type`, `err.message`, `err.stack`), so `logger.error({ err }, "...")` needs no renaming.

### Go

Packages: `log/slog` (standard library), `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` for server and client spans and `traceparent` propagation, and `go.opentelemetry.io/contrib/bridges/otelslog` for the OpenTelemetry logs pipeline. `otelslog` hands records to the OpenTelemetry SDK; it does not write the stdout line logq reads, so keep the slog JSON handler for stdout and add the IDs to it from the context:

```go
import "go.opentelemetry.io/otel/trace"

type traceHandler struct{ slog.Handler }

func (h traceHandler) Handle(ctx context.Context, r slog.Record) error {
	if sc := trace.SpanContextFromContext(ctx); sc.IsValid() {
		r.AddAttrs(slog.String("trace_id", sc.TraceID().String()), slog.String("span_id", sc.SpanID().String()))
	}
	return h.Handler.Handle(ctx, r)
}
func (h traceHandler) WithAttrs(a []slog.Attr) slog.Handler { return traceHandler{h.Handler.WithAttrs(a)} }
func (h traceHandler) WithGroup(n string) slog.Handler     { return traceHandler{h.Handler.WithGroup(n)} }

func newLogger() *slog.Logger {
	names := map[string]string{slog.TimeKey: "timestamp", slog.LevelKey: "severity_text", slog.MessageKey: "body"}
	base := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
		if n, ok := names[a.Key]; ok && len(groups) == 0 {
			a.Key = n
		}
		return a
	}})
	return slog.New(traceHandler{base}).With("service.name", os.Getenv("OTEL_SERVICE_NAME"))
}
```

Spans need a tracer provider and the W3C propagator at startup: `otel.SetTracerProvider(sdktrace.NewTracerProvider())` (no exporter is enough for trace IDs) and `otel.SetTextMapPropagator(propagation.TraceContext{})`. Wrap the server handler with `otelhttp.NewHandler` and the HTTP client transport with `otelhttp.NewTransport`.

Always log with the context (`slog.InfoContext(ctx, "request finished", ...)`), or the span is not visible to the handler. Write the `request finished` line and set `X-Request-ID` (from `trace.SpanContextFromContext(r.Context()).TraceID().String()`) in a middleware placed inside `otelhttp.NewHandler`.

## Traces in Jaeger (phase 3)

Logs say what happened; spans show which service called which, and which SQL statement or storage call took the time. `logq ui` starts one shared Jaeger on `localhost:16686`; apps export traces to it over OTLP. For local development only.

Replace the environment block of the recipes above with these six lines (Jaeger stores traces only, so metrics and logs stay `none`):

```
OTEL_SERVICE_NAME=<compose service>
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318
OTEL_METRICS_EXPORTER=none
OTEL_LOGS_EXPORTER=none
```

In Python, install the OTLP exporter: `opentelemetry-exporter-otlp-proto-http` (or `opentelemetry-distro[otlp]`). `opentelemetry-distro` alone does not ship it, so without it `OTEL_TRACES_EXPORTER=otlp` fails and no trace reaches Jaeger.

Install the instrumentation for each resource the app uses. `opentelemetry-bootstrap -a install` detects them (instrumentations only, not exporters): Django, psycopg (SQL statements), requests/httpx (outgoing HTTP) and botocore (S3, which covers MinIO).

Docker Desktop resolves `host.docker.internal`. Plain Docker Engine needs this on each exporting service:

```yaml
    extra_hosts: ["host.docker.internal:host-gateway"]
```

`logq query --trace <id>` then ends with a `-- view in Jaeger:` link. It opens a real trace only when the logged `trace_id` is the OpenTelemetry trace ID, as this contract asks.

### Request bodies in spans (opt-in)

Spans carry routes and statements, not bodies. This Django middleware adds `http.request.body` and `http.response.body` when `LOGQ_CAPTURE_BODY=1`: JSON content types only, the first 2 KB, redacted first because Jaeger stores what it receives. **Local development only: never set it in a shared or production environment.** It is the one exception to "Never log whole bodies". The patterns are adapted from logq's redaction (`logq/render.py`); do not import logq, it is not installed in app containers.

```python
# logq_body_capture.py: add to MIDDLEWARE after OpenTelemetry's Django middleware.
import os, re
from django.core.exceptions import MiddlewareNotUsed
from opentelemetry import trace

_SECRET = re.compile(r"""
    (?P<k>\b(?:authorization|\w*(?:pass(?:word|wd)|secret|token|api[_-]?key)\w*)["']?\s*[:=]\s*)  # key: value
        (?:"(?:\\.|[^"\\])*"|(?:[a-z][\w-]*\s+)?[^\s,;&"'}]+)
  | \bbearer\s+[\w.~+/=-]+ | \beyJ[\w-]+\.[\w-]+\.[\w-]+                                          # Bearer, JWT
  | \b(?:AKIA[0-9A-Z]{16}|sk-[\w-]{20,}|ghp_\w{20,}|github_pat_\w{20,}|xox[bp]-[\w-]+)            # key shapes
  | (?<=://)[^\s:/@]*:[^\s/]+(?=@)                                                                # URL credentials
""", re.I | re.X)

def _clean(raw):  # redact first, then cut to 2 KB, so the cut cannot leave half a secret
    text = _SECRET.sub(lambda m: (m["k"] or "") + "[REDACTED]", raw.decode("utf-8", "replace"))
    return text.encode()[:2048].decode("utf-8", "ignore")

def capture_body(get_response):
    if os.environ.get("LOGQ_CAPTURE_BODY") != "1":
        raise MiddlewareNotUsed  # off by default: Django drops this middleware
    def middleware(request):
        span = trace.get_current_span()
        try:  # a debug aid must never change the response; request bodies over 64 KB are skipped
            if "json" in request.content_type and int(request.META.get("CONTENT_LENGTH") or 0) <= 65536:
                span.set_attribute("http.request.body", _clean(request.body))
        except Exception:
            pass
        response = get_response(request)
        try:
            if "json" in response.headers.get("Content-Type", "") and not response.streaming:
                span.set_attribute("http.response.body", _clean(response.content))
        except Exception:
            pass
        return response
    return middleware
```
