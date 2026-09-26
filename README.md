# semanticdrift

Verifier-guided pipeline for **semantic drift**: a model checker reports *proved* while the formal model or property no longer matches the source program or the informal requirement.

The pipeline is formalize → validate → verify → audit → repair. A local coder (Qwen2.5-Coder 7B) writes Promela and LTL from Python plus English. A second model (DeepSeek-Coder-V2-Lite) and SPIN’s parser validate that output. Unmodified SPIN, NuSMV, CBMC, and Dafny verify; parse failure skips the solver. The auditor runs LTL vacuity probes, trace agreement against the Python reference, and a five-way failure classifier. Repair is capped at five attempts, may not weaken properties, and does not patch the code under test.

Gold `reference.pml` is the answer key and is not sent to the generator. Metrics are SVR, VSR, TAR, FAR, and ATS. FAR excludes vacuity so ATS does not count the same property twice.

## Repository

```
benchmarks/protocols/   five Python + Promela references, precise/ambiguous English, Cosmic Ray mutants
benchmarks/heldout/     40 pinned post-cutoff MIT C files
benchmarks/vacuity/     LTL mutation battery and 61 hand labels
benchmarks/sv-sample/   300-task SV-Benchmarks sample (150 true / 150 false, seed 7)
src/semanticdrift/      agents, verifiers, auditor, repair, baselines, metrics
tests/                  unit tests
Dockerfile              Ubuntu image for pinned replay
```

Protocols: Peterson (mutex and starvation), bounded producer-consumer, dining philosophers, two-phase commit, TCP three-way handshake. Each ambiguous requirement is the precise text minus one documented constraint sentence (`benchmarks/protocols/requirement_edits.yaml`).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m semanticdrift check-tools
```

SPIN, a C compiler, and Ollama (`qwen2.5-coder:7b`, `deepseek-coder-v2:lite`) are required for live formalize/validate. `ollama serve` must be running. NuSMV, CBMC, Dafny, and Docker are optional backends.

```bash
python -m semanticdrift list
python -m semanticdrift check-promela
python -m semanticdrift prove-promela
python -m semanticdrift pipeline --all
python -m semanticdrift metrics
pytest
```

`check-promela` is `spin -a` on gold models. `prove-promela` compiles `pan` and checks each `ltl` claim (starvation claims use weak fairness). Other commands: `formalize`, `validate`, `verify`, `verify-tool`, `audit`, `repair`, `baseline`, `sample-sv`, `seed-mutants`, `list-heldout`, `list-vacuity`.
