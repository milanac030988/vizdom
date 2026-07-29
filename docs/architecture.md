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

## Class diagram (core)

```plantuml
!include diagrams/class.puml
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
