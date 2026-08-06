# Architecture

All diagrams below are **single-sourced** from `docs/diagrams/*.puml` via
`!include` and rendered inline at build time by the local `plantuml.jar`
(offline, Graphviz-free via Smetana). Edit the `.puml` files to update them.

## System overview

```plantuml
!include diagrams/system_overview.puml
```

## CV pipeline (detailed flow)

```plantuml
!include diagrams/cv_pipeline_detail.puml
```

## Component diagram

```plantuml
!include diagrams/component.puml
```

## Class diagram — overview

A high-level view: the driven ports, the adapter families (collapsed), and the
domain data-model spine. Detailed per-component diagrams follow below.

```plantuml
!include diagrams/class.puml
```

### Detail — detector port & adapters

```plantuml
!include diagrams/class_detectors.puml
```

### Detail — capture port & adapters (ADR-018)

```plantuml
!include diagrams/class_capture.puml
```

### Detail — actuator port & adapters (ADR-019)

```plantuml
!include diagrams/class_actuator.puml
```

### Detail — domain analysis engine

```plantuml
!include diagrams/class_domain.puml
```

## Sequence — screenshot → DOM

```plantuml
!include diagrams/sequence.puml
```

## Distributed / hexagonal architecture (ADR-017 / 018 / 019)

Ports & adapters, with the detector, capture, and actuator as pluggable driven
ports that can each run in-process or as a remote gRPC service.

```plantuml
!include diagrams/architecture.puml
```

### Microservice-oriented ports

The ports are first-class **service boundaries**, not just internal seams. Each of
**detector**, **capture**, and **actuator** has a versioned protobuf contract
(`protos/*.proto`) and a standalone gRPC server (`python -m visual_dom.adapters.inbound.grpc.*_server`),
so any port can be deployed, scaled, and upgraded as an independent microservice.
That orientation buys the microservice benefits exactly where this problem needs them:

- **Independent scaling** — one warm-GPU *detector* service serves many thin clients
  instead of every client loading a heavy model.
- **Heterogeneous placement** — capture on the device, detection on a GPU host,
  actuation at the SUT or a robot-arm controller.
- **Fault & resource isolation** — a busy or crashed detector doesn't stall capture.
- **Polyglot substitution** — a service can be reimplemented in any language behind
  the same contract.

It is microservice-oriented **by construction** — the boundaries are designed in, not
retrofitted — yet the same services **collapse into one process** when co-location is
enough (gRPC is a transport, not a requirement). So distribution is adopted
incrementally: a local run pays no network or server-lifecycle cost, and going
distributed needs no code change, only a different strategy name + target. See the
per-service ports and start commands in [Using as a Client](USAGE.md#2-distributed-via-grpc).
