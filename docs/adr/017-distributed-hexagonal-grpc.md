# ADR-017: Distributed Hexagonal Architecture with gRPC Model Services

## Status

Proposed

## Date

2026-07-26

## Author

Nguyen Huynh Tri Cuong

## Reviewer

- Nguyen Huynh Tri Cuong

## History

| Date | Version | Description |
|------|---------|-------------|
| 2026-07-26 | 0.1 | Initial proposal — hexagonal ports/adapters + gRPC detector service |

## Context

The heavy pipeline stages are GPU-bound and expensive to load:

- **Detector** (OmniParser = YOLOv8 + Florence-2) — ~10s model load, needs a GPU.
- **SLM refiner** (Ollama VLM, e.g. minicpm-v) — needs a GPU.
- **OCR** (EasyOCR, optionally upscaled) — GPU-accelerated.

Today they all run **in one process on one machine**, which:

1. Overloads a single PC (two large models + OCR + the app).
2. Reloads models on almost every run (the per-process `_MODEL_CACHE` helps
   within a session, but a fresh CLI/Viewer run pays the ~10s again).
3. Prevents sharing one GPU box across several client machines / test runners.

We want the detector and refiner to run as **separate services**, potentially on
**other PCs**, so a warm model server serves many lightweight clients. This is an
applied-project goal (Method 3): a scalable, decoupled deployment for GPU-shared
GUI test automation — not a change to the core CV→DOM method.

Crucially, **the codebase is already most of the way there**:

- `DetectorBackend` (ADR-015) is already a **port**: `detect(image) -> List[Detection]`,
  with local adapters (UIED/YOLO/OmniParser).
- `SLMAdvisor` already talks to **Ollama over HTTP** — the refiner can *already*
  run on another PC by pointing `slm_host` at it. No new transport required.

## Decision

Adopt a **hexagonal (ports & adapters)** structure and add **remote adapters**;
do NOT rewrite into many microservices. Extract only the two heavy stages.

### 1. Hexagonal layering

```
                        Driving adapters (inbound)
        CLI (process_gui_image) · Viewer · Dashboard · Robot Framework
                                   │
                                   ▼
   ┌───────────────────────────────────────────────────────────────┐
   │  DOMAIN CORE (pure, no I/O)                                     │
   │  pipeline orchestration · reading-order · smart-merge ·        │
   │  coarse hierarchy · DOM compiler · schema                      │
   │                                                                │
   │  PORTS (interfaces):                                           │
   │    DetectorPort   detect(image) -> [Detection]                 │
   │    RefinerPort    review(elements, image) -> [Suggestion]      │
   │    OcrPort        detect_text(image) -> [TextElement]          │
   └───────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                    Driven adapters (outbound)
   local: UIEDBackend · YOLOBackend · OmniParserBackend · TextDetector · SLMAdvisor
   remote: GrpcDetectorBackend ─(gRPC)→ Detector service (GPU box)
           SLMAdvisor(host=other-pc) ─(HTTP)→ Ollama (GPU box)
```

The domain core stays **local and CPU-cheap** (it is also the project's main
technical content — geometry, hierarchy, DOM). Only **model inference** crosses
the wire.

### 2. Ports (formalize what exists)

- `DetectorPort` ← existing `DetectorBackend` (no change).
- `RefinerPort` ← extracted from `SLMAdvisor.review_elements(...)`.
- `OcrPort` ← extracted from `TextDetector.detect(...)`.

Each port has ≥1 **local** adapter (in-process) and MAY have a **remote** adapter.

### 3. Remote detector via gRPC

- **Contract:** `protos/detector.proto` — `Detector.Detect(DetectRequest) -> DetectResponse`
  where request carries the encoded image + params + a `request_id`
  (correlation id for cross-service tracing), and the response carries
  `repeated Detection` (bounds, visual_type, confidence, text, interactable, source).
- **Server** (`src/visual_dom/rpc/detector_server.py`): wraps any local backend
  (`create_detector(...)`), loads the model **once at startup**, serves Detect.
  Runs on the GPU PC.
- **Client** (`GrpcDetectorBackend`): a `DetectorBackend` adapter that marshals
  the image to the service and converts the proto response back to `Detection`.
  Registered as detector name **`grpc`**; selected exactly like any other backend.

### 4. Remote refiner (already available)

`SLMAdvisor(backend="ollama", host="http://<gpu-pc>:11434")` already runs the SLM
on another machine. Optionally, a later phase can wrap it behind a gRPC
`RefinerService` for a uniform contract — not required for the load-distribution win.

### 5. Rollout phases

- **Phase 0 (no code):** run the refiner remotely by setting `slm_host`.
- **Phase 1:** formalize ports (thin refactor; mostly naming around existing classes).
- **Phase 2:** gRPC **detector service** + `GrpcDetectorBackend` client (this ADR's
  code sketch). Delivers the main goal.
- **Phase 3 (optional):** gRPC refiner/OCR services for a uniform transport.

## Alternatives Considered

- **Full microservices** (every stage its own service, discovery, mesh) —
  rejected: sprawl and ops cost not justified for a mostly single-user tool;
  the domain core is cheap and belongs local.
- **REST/HTTP for the detector** (like Ollama) — viable, but gRPC gives typed,
  versioned contracts and efficient binary image payloads; worth it for the
  image-in / structured-out shape.
- **Keep everything in-process** — rejected: the GPU-overload and model-reuse
  problems are the whole point.

## Consequences

### Positive
- One warm GPU model server serves many clients → no per-run reload, no
  single-PC overload; a CI farm can share a couple of GPU boxes.
- Clean separation: **geometry/hierarchy (CPU, local)** vs **inference (GPU, remote)**.
- Minimal disturbance: remote detector is just another `DetectorBackend`; the
  pipeline is untouched.
- Strong, demonstrable systems story for the applied project.

### Negative / risks
- Distributed debugging — mitigate with `request_id` correlation IDs threaded
  through `logging_utils`.
- **Contract versioning** — the `Detection`/DOM schema still evolves (label,
  interactable added recently); freeze it carefully with proto field numbers and
  a `v1` package.
- Image payload over the network (~0.1–2 MB/req) — fine on a LAN; encode as PNG.
- Security — use TLS/auth if the network is not trusted.
- Extra deps: `grpcio`, `grpcio-tools` (client/server); generated `*_pb2.py`.

## Deployment & scaling path

**Decision: run services as plain native processes — no containers, no
orchestrator.** For the project's scale (a single user with 1–3 PCs, one GPU box
serving a few clients), that is the right-sized choice:

- A launcher script (`start_detector.bat`) starts the detector service on the
  GPU host; clients point at `host:50051`. That is the whole deployment.
- Optionally register it as an always-on Windows service with **NSSM** (a few MB,
  no VM) — not required.

**Explicitly rejected for now (YAGNI at this scale):**

| Option | Why not now |
|--------|-------------|
| **Docker / Compose** | On Windows it pulls in a WSL2 VM + daemon — heavy RAM/disk for no benefit at 1–3 nodes; conflicts with this project's resource constraints. |
| **Consul** (discovery/health/mesh) | A static `target` (config) already locates the service; a `HealthCheck` RPC already exists. Discovery earns its keep only when services move/scale dynamically. |
| **Nomad** (scheduling) | No cluster to schedule across; 1–2 servers are started by hand / a launcher. |
| **Kubernetes** | Far beyond the scale; large ops surface. |

**Future scaling path** (documented, not built) — if this grows into a
multi-node CI/test farm where many runners share a dynamic pool of GPU model
servers: (1) **gRPC client-side load balancing** over a static endpoint list +
`HealthCheck`-based failover — pure code, still no infra; then (2) **Consul** for
discovery/health + **Nomad** (or Kubernetes) for scheduling. Start at (1) and add
orchestration only when nodes actually come and go.

## Files (this proposal introduces)

- `protos/detector.proto` — the service contract (v1).
- `src/visual_dom/cv/detectors/grpc_backend.py` — `GrpcDetectorBackend` client adapter.
- `src/visual_dom/rpc/detector_server.py` — the detector gRPC server.
- `src/visual_dom/cv/detectors/registry.py` — register `grpc` backend.
- `docs/diagrams/architecture.puml` — the ports/adapters + deployment diagram
  (was `hexagonal.puml`; extended for capture ADR-018 and actuator ADR-019).
- `start_detector.bat` — launcher for the detector service (native process).

### Code generation

> The `rpc/` package below became `src/visual_dom/generated/` (stubs) plus
> `adapters/inbound/grpc/` (servers) in the ADR-014 hexagonal restructure. The
> current command is:

```bash
pip install grpcio grpcio-tools
python -m grpc_tools.protoc -I protos \
  --python_out=src/visual_dom/generated --grpc_python_out=src/visual_dom/generated \
  protos/detector.proto protos/capture.proto protos/actuator.proto
# protoc emits a bare import that breaks inside a package — qualify it:
sed -i 's/^import detector_pb2 as /from visual_dom.generated import detector_pb2 as /' \
  src/visual_dom/generated/detector_pb2_grpc.py
```

**Verified end-to-end (2026-07-26):** with the `uied` backend, client → gRPC
service → 10 detections returned over the wire (correlation id logged,
~91 ms server-side, 0.12 s round-trip). Same path works cross-PC by pointing the
client `target` at the service host.
