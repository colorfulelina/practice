# semanticdrift

Verifier-guided pipeline for **semantic drift**: a model checker says *proved*, but the formal model or property no longer matches the source program or the informal requirement.

**Weeks 1–2 are done.** Week 3 gold Promela now parses (`check-promela`) and proves (`prove-promela`: compile `pan`, run each `ltl` claim). Paired precise/ambiguous requirements, seeded mutants, held-out GitHub tasks, and vacuity labels are in place.

## Layout

```
benchmarks/protocols/     five Python+Promela references, precise/ambiguous requirements, Cosmic Ray mutants
benchmarks/sv-sample/     300-task manifest plus pycparser C mutants and a 30-mutant spot-check
src/semanticdrift/        tool check, protocol list, SV sampler, mutant seeding
Dockerfile                Ubuntu image matching the methodology’s Linux setup
```

## Python environment

```bash
cd ~/semanticdrift
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m semanticdrift check-tools
python -m semanticdrift list
python -m semanticdrift run --name peterson
python -m semanticdrift check-promela
python -m semanticdrift prove-promela
python -m semanticdrift formalize --name peterson --requirement precise
python -m semanticdrift validate --name peterson --requirement precise
python -m semanticdrift verify --name peterson --requirement precise
python -m semanticdrift verify-tool --file path/to/file.c
python -m semanticdrift baseline --name peterson --kind zero_shot
python -m semanticdrift pipeline --all
python -m semanticdrift metrics
python -m semanticdrift audit --name peterson --requirement precise
python -m semanticdrift repair --name peterson --requirement precise
python -m semanticdrift seed-mutants
pytest
```

`formalize` calls local Ollama (`qwen2.5-coder:7b`) with the Python source and one English requirement. It writes JSON plus a `.pml` under `results/formalize/` and does **not** parse or prove that output. Start the server with `ollama serve` first. Gold `reference.pml` is not sent to the model.

`validate` runs SPIN's parser (`spin -a`) on that generated Promela, then asks a **different** model (`deepseek-coder-v2:lite`) for 0–5 correspondence scores. It does not prove LTL.

`verify` is unmodified SPIN: `spin -a`, then compile `pan` and run each `ltl` claim. If parse fails, `pan` is not built (`skipped_pan: true`). Gold proofs stay on `prove-promela`; this command is for generated models.

`verify-tool --file path` picks CBMC (`.c`), NuSMV (`.smv`), Dafny (`.dfy`), or SPIN (`.pml`) and calls the binary unmodified. A parse/resolve failure skips the solver.

`baseline --kind` is one of the six §8.8 comparisons, not the full pipeline: `zero_shot`, `few_shot`, `chain_of_thought`, `verifier_feedback`, `retrieval`, `rule_based`. Few-shot and retrieval use TLA+ Examples translated to Promela, not gold `reference.pml`. `rule_based` is keyword templates and does not call a model.

`audit` runs the four LTL vacuity mutations through pan (skipped if the file does not parse), compares Python `EVENT_SINK` traces to event names in the Promela, and applies the five-way classifier (`no_failure`, `property_error`, `modeling_error`, `program_bug`, `tool_limitation`, or `missing_invariant`). Gold: `python -m semanticdrift audit --name peterson --from-pml benchmarks/protocols/peterson/reference.pml`.

`repair` loops audit → category-restricted edit, at most 5 times. It may rewrite Promela (`modeling_error`) or LTL (`property_error` / `missing_invariant`), raise the SPIN timeout (`tool_limitation`), or stop (`program_bug`). It never edits `reference.py` and it rejects property edits that weaken a claim.

`pipeline --all` runs formalize → validate → verify → audit → repair on the five protocols × two English files. `metrics` reads those rows and prints SVR, VSR, TAR, FAR, and ATS. FAR is only low trace agreement (or a human flag) on tasks SPIN proved; vacuous proofs are a separate vacuity rate so ATS does not count them twice.

`check-promela` is only `spin -a` (the model parses). `prove-promela` compiles SPIN's `pan` checker and runs each named `ltl` claim. Starvation claims use weak fairness (`pan -a -f`), matching the English "weakly fair scheduler". All nine gold claims currently prove.

`check-tools` reports which of SPIN, NuSMV, CBMC, Dafny, Ollama, and Docker are on your `PATH`. On this Mac you can install what is missing with Homebrew / the Ollama app. Docker is for later pinned replay. You do not need every tool installed on day one.

## Google Colab

Use Colab so the professor can run Linux + a GPU in the browser. It does not replace the Docker replay.

1. Put the repo on GitHub, **or** zip the folder **without** `.venv`, `.github_token`, and `results/`.
2. In Colab: Runtime → GPU.
3. Upload `notebooks/semanticdrift_colab.ipynb` (File → Upload) and run the cells in order: `apt` SPIN, clone or unzip, `pip install -e ".[dev]"`, then `check-promela` / `prove-promela`.
4. Optional: install Ollama in the VM and `formalize` one protocol. Do not paste tokens into the notebook. Copy `results/` to Drive if the session will die.

**Push this repo, not your laptop junk.** Add `src/`, `benchmarks/` (protocols, held-out, vacuity; not the 12 GB SV clone), `tests/`, `notebooks/`, `scripts/colab_setup.sh`, `Dockerfile`, `pyproject.toml`, `requirements-colab.txt`, `README.md`. Leave out `.venv`, `.github_token`, `.env`, and `results/*.json`. After the first push, set `REPO` in the notebook to `you/semanticdrift`.


## Software Verification Benchmarks sample

```bash
python -m semanticdrift sample-sv
```

That clones [SV-Benchmarks](https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks) (about 12 GB) and writes `benchmarks/sv-sample/manifest.json`: 150 expected-true and 150 expected-false tasks, seed 7. The clone is gitignored; re-run this command only if you need to rebuild the sample.

## Ambiguous requirements

Each protocol has `requirement_ambiguous.txt`: the precise text with exactly one constraint sentence deleted. The deleted sentence is recorded in `benchmarks/protocols/requirement_edits.yaml`. That is the controlled missing-assumption pair from the methodology, not a rewrite.

## Held-out GitHub set

`benchmarks/heldout/manifest.json` lists 40 small MIT C files from repos created after 2025-06-01, each pinned to a commit.

```bash
python -m semanticdrift list-heldout
```

## Vacuity battery

`benchmarks/vacuity/battery.json` is the text-level LTL mutation set from the methodology. `labels.json` has 61 hand labels (`vacuous` yes/no) for scoring the auditor later.

```bash
python -m semanticdrift seed-vacuity
python -m semanticdrift list-vacuity
```

## Seeded mutants

```bash
python -m semanticdrift seed-mutants
```

Python mutants live under `benchmarks/protocols/<name>/mutants/` and are produced with Cosmic Ray operators, then classified by running `run()`. C mutants live under `benchmarks/sv-sample/mutants/`: originally-correct SV sample programs, mutated with boundary flips, comparison swaps, and off-by-one shifts. `spot_check.json` is a hand review of 30 of those C mutants.

## Protocols (Python + precise / ambiguous requirements)

| Protocol | Property |
|----------|----------|
| Peterson | Mutual exclusion and starvation freedom |
| Bounded producer-consumer | No buffer overflow and no deadlock |
| Dining philosophers | Deadlock freedom under ordered fork acquisition |
| Two-phase commit | All participants commit or all abort |
| TCP three-way handshake | Handshake states; no half-open accept |
