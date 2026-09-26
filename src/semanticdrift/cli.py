"""Command-line entry: tools, protocols, SV sample, seeded mutants."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from semanticdrift.agents.formalize import formalize_protocol, write_formalization
from semanticdrift.baselines.run import BASELINES, run_baseline
from semanticdrift.metrics import compute_metrics, load_task_rows
from semanticdrift.pipeline import PIPELINE_OUT, run_pipeline, run_suite
from semanticdrift.agents.validate import validate_protocol
from semanticdrift.audit.run import audit_protocol
from semanticdrift.heldout import DEFAULT_OUT
from semanticdrift.repair.loop import REPAIR_CAP, repair_protocol
from semanticdrift.verifiers.dispatch import verify_file
from semanticdrift.verifiers.spin import verify_protocol
from semanticdrift.mutants.seed import seed_all
from semanticdrift.ollama import GENERATOR_MODEL, VALIDATOR_MODEL, OllamaError
from semanticdrift.promela import check_syntax, prove_file
from semanticdrift.protocols import get_protocol, list_protocols
from semanticdrift.sv_sample import build_sample
from semanticdrift.vacuity_seed import OUT_DIR as VACUITY_DIR
from semanticdrift.vacuity_seed import build_battery

ROOT = Path(__file__).resolve().parents[2]

TOOLS = (
    ("spin", "SPIN model checker"),
    ("cbmc", "CBMC bounded model checker"),
    ("NuSMV", "NuSMV symbolic model checker"),
    ("nusmv", "NuSMV (lowercase binary name)"),
    ("dafny", "Dafny verifier"),
    ("ollama", "Ollama local model runtime"),
    ("docker", "Docker (pinned replay later)"),
    ("git", "git (needed to clone Software Verification Benchmarks)"),
)


def check_tools() -> int:
    print("Tool check (weeks 1–2). Missing tools can be installed as you go.\n")
    missing = 0
    for binary, role in TOOLS:
        path = shutil.which(binary)
        status = path or "NOT on PATH"
        if path is None:
            missing += 1
        print(f"  {binary:8}  {status:40}  {role}")
    print()
    if missing:
        print("Install whatever you need for the next smoke test; not everything is required today.")
    else:
        print("All listed binaries were found on PATH.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Semantic drift — protocol references, tools, SV sample."
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("list", help="List the five protocol references.")
    sub.add_parser("check-tools", help="See which verifiers and Ollama are installed.")
    sample = sub.add_parser(
        "sample-sv",
        help="Clone Software Verification Benchmarks and write a 300-task manifest.",
    )
    sample.add_argument(
        "--no-clone",
        action="store_true",
        help="Use an existing sv-benchmarks/ directory; do not clone.",
    )
    run = sub.add_parser("run", help="Run one protocol's Python reference.")
    run.add_argument("--name", required=True, help="Protocol folder name, for example peterson.")
    sub.add_parser("check-promela", help="Parse each gold Promela file with SPIN.")
    sub.add_parser(
        "prove-promela",
        help="Compile pan and prove each gold LTL claim (mutex, starve, ...).",
    )
    seed = sub.add_parser(
        "seed-mutants",
        help="Write Cosmic Ray protocol mutants and pycparser C mutants.",
    )
    seed.add_argument("--python-only", action="store_true")
    seed.add_argument("--c-only", action="store_true")
    sub.add_parser("list-heldout", help="Show the pinned post-cutoff GitHub tasks.")
    sub.add_parser("seed-vacuity", help="Rebuild the vacuity mutant battery from gold LTL.")
    sub.add_parser("list-vacuity", help="Show vacuity gold labels.")
    gen = sub.add_parser(
        "formalize",
        help="Qwen2.5-Coder: turn source + English into Promela/LTL JSON.",
    )
    gen.add_argument("--name", required=True, help="Protocol folder name, for example peterson.")
    gen.add_argument(
        "--requirement",
        choices=("precise", "ambiguous"),
        default="precise",
        help="Which English requirement to give the model (default: precise).",
    )
    gen.add_argument(
        "--model",
        default=GENERATOR_MODEL,
        help=f"Ollama model tag (default: {GENERATOR_MODEL}).",
    )
    gen.add_argument(
        "--out",
        default=str(ROOT / "results" / "formalize"),
        help="Directory for the JSON and .pml files.",
    )
    val = sub.add_parser(
        "validate",
        help="SPIN parser plus DeepSeek correspondence scores on a formalize JSON.",
    )
    val.add_argument("--name", required=True, help="Protocol folder name, for example peterson.")
    val.add_argument(
        "--requirement",
        choices=("precise", "ambiguous"),
        default="precise",
    )
    val.add_argument(
        "--from-json",
        dest="from_json",
        default=None,
        help="Formalize JSON (default: results/formalize/<name>_<requirement>.json).",
    )
    val.add_argument(
        "--model",
        default=VALIDATOR_MODEL,
        help=f"Ollama model tag (default: {VALIDATOR_MODEL}).",
    )
    val.add_argument(
        "--out",
        default=str(ROOT / "results" / "validate"),
        help="Directory for the validation JSON.",
    )
    ver = sub.add_parser(
        "verify",
        help="Run unmodified SPIN/pan on generated Promela. Skip pan if spin -a fails.",
    )
    ver.add_argument("--name", required=True, help="Protocol folder name, for example peterson.")
    ver.add_argument(
        "--requirement",
        choices=("precise", "ambiguous"),
        default="precise",
    )
    ver.add_argument(
        "--from-json",
        dest="from_json",
        default=None,
        help="Formalize JSON (default: results/formalize/<name>_<requirement>.json).",
    )
    ver.add_argument(
        "--from-pml",
        dest="from_pml",
        default=None,
        help="Promela file to check instead of the formalize JSON.",
    )
    ver.add_argument(
        "--out",
        default=str(ROOT / "results" / "verify"),
        help="Directory for the verify JSON.",
    )
    vtool = sub.add_parser(
        "verify-tool",
        help="Unmodified CBMC / NuSMV / Dafny / SPIN on a file, chosen by suffix.",
    )
    vtool.add_argument("--file", required=True, help="Path to .c, .smv, .dfy, or .pml")
    base = sub.add_parser(
        "baseline",
        help="One §8.8 baseline (zero-shot, few-shot, CoT, verifier-feedback, retrieval, rules).",
    )
    base.add_argument("--name", required=True, help="Protocol folder name, for example peterson.")
    base.add_argument(
        "--kind",
        required=True,
        choices=BASELINES,
        help="Which baseline to run.",
    )
    base.add_argument(
        "--requirement",
        choices=("precise", "ambiguous"),
        default="precise",
    )
    base.add_argument(
        "--model",
        default=GENERATOR_MODEL,
        help=f"Ollama model tag (default: {GENERATOR_MODEL}).",
    )
    base.add_argument(
        "--cap",
        type=int,
        default=5,
        help="Retry cap for verifier-feedback (default: 5).",
    )
    base.add_argument(
        "--embeddings",
        action="store_true",
        help="Retrieval: use sentence-transformers if installed (default: bag-of-words).",
    )
    base.add_argument(
        "--out",
        default=str(ROOT / "results" / "baselines"),
        help="Directory for the baseline JSON / Promela.",
    )
    pipe = sub.add_parser(
        "pipeline",
        help="Formalize → validate → verify → audit → repair, then write a task row.",
    )
    pipe.add_argument("--name", help="One protocol. Omit with --all for all five × two English files.")
    pipe.add_argument(
        "--requirement",
        choices=("precise", "ambiguous"),
        default="precise",
    )
    pipe.add_argument(
        "--all",
        action="store_true",
        dest="all_tasks",
        help="Run every protocol with both requirement variants.",
    )
    pipe.add_argument("--cap", type=int, default=REPAIR_CAP)
    pipe.add_argument(
        "--out",
        default=str(PIPELINE_OUT),
        help="Directory for pipeline JSON and suite.json.",
    )
    met = sub.add_parser(
        "metrics",
        help="SVR / VSR / TAR / FAR / ATS from pipeline JSON. FAR excludes vacuity.",
    )
    met.add_argument(
        "--from",
        dest="from_dir",
        default=str(PIPELINE_OUT),
        help="Directory of pipeline JSON (default: results/pipeline).",
    )
    aud = sub.add_parser(
        "audit",
        help="Vacuity probes, traces vs Python, five-way failure class.",
    )
    aud.add_argument("--name", required=True, help="Protocol folder name, for example peterson.")
    aud.add_argument(
        "--requirement",
        choices=("precise", "ambiguous"),
        default="precise",
    )
    aud.add_argument(
        "--from-json",
        dest="from_json",
        default=None,
        help="Formalize JSON (default: results/formalize/<name>_<requirement>.json).",
    )
    aud.add_argument(
        "--from-pml",
        dest="from_pml",
        default=None,
        help="Promela file instead of the formalize JSON (for example gold reference.pml).",
    )
    aud.add_argument(
        "--out",
        default=str(ROOT / "results" / "audit"),
        help="Directory for the audit JSON.",
    )
    rep = sub.add_parser(
        "repair",
        help="Category-restricted repair loop (cap 5; no property weakening; no source patches).",
    )
    rep.add_argument("--name", required=True)
    rep.add_argument("--requirement", choices=("precise", "ambiguous"), default="precise")
    rep.add_argument("--from-json", dest="from_json", default=None)
    rep.add_argument("--cap", type=int, default=REPAIR_CAP)
    rep.add_argument("--out", default=str(ROOT / "results" / "repair"))
    args = parser.parse_args(argv)
    cmd = args.cmd or "list"

    if cmd == "check-tools":
        return check_tools()

    if cmd == "list":
        protocols = list_protocols()
        if not protocols:
            print("No protocols under benchmarks/protocols/", file=sys.stderr)
            return 1
        for proto in protocols:
            print(f"{proto.name:24}  {proto.property_class}")
        return 0

    if cmd == "sample-sv":
        result = build_sample(
            repo_root=ROOT / "sv-benchmarks",
            manifest_path=ROOT / "benchmarks" / "sv-sample" / "manifest.json",
            clone=not args.no_clone,
        )
        print(json.dumps(result, indent=2))
        return 0

    if cmd == "check-promela":
        failed = 0
        for proto in list_protocols():
            ok, detail = check_syntax(proto.promela_path)
            status = "ok" if ok else "FAIL"
            print(f"{proto.name:24}  {status}  {detail.splitlines()[-1] if detail else ''}")
            if not ok:
                failed += 1
        return 1 if failed else 0

    if cmd == "prove-promela":
        failed = 0
        for proto in list_protocols():
            results = prove_file(proto.promela_path)
            for claim in results:
                status = "PROVED" if claim.proved else "FAIL"
                fair = "  weak-fairness" if claim.fairness else ""
                print(
                    f"{proto.name:24}  {claim.name:32}  {status:6}  "
                    f"{claim.detail}{fair}"
                )
                if not claim.proved:
                    failed += 1
        return 1 if failed else 0

    if cmd == "formalize":
        try:
            proto = get_protocol(args.name)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        try:
            result = formalize_protocol(
                args.name,
                requirement=args.requirement,
                model=args.model,
                proto=proto,
            )
        except (OllamaError, ValueError, json.JSONDecodeError) as exc:
            print(f"formalize failed: {exc}", file=sys.stderr)
            return 1
        paths = write_formalization(
            result,
            Path(args.out),
            f"{args.name}_{args.requirement}",
        )
        print(json.dumps(result.to_dict(), indent=2))
        print(f"wrote {paths['json']}", file=sys.stderr)
        print(f"wrote {paths['pml']}", file=sys.stderr)
        return 0

    if cmd == "validate":
        from_json = Path(args.from_json) if args.from_json else None
        try:
            result = validate_protocol(
                args.name,
                requirement=args.requirement,
                from_json=from_json,
                model=args.model,
            )
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except (OllamaError, ValueError, json.JSONDecodeError, KeyError) as exc:
            print(f"validate failed: {exc}", file=sys.stderr)
            return 1
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{args.name}_{args.requirement}.json"
        out_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result.to_dict(), indent=2))
        print(f"wrote {out_path}", file=sys.stderr)
        return 0

    if cmd == "verify":
        from_json = Path(args.from_json) if args.from_json else None
        from_pml = Path(args.from_pml) if args.from_pml else None
        try:
            result = verify_protocol(
                args.name,
                requirement=args.requirement,
                from_json=from_json,
                from_pml=from_pml,
            )
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{args.name}_{args.requirement}.json"
        out_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result.to_dict(), indent=2))
        print(f"wrote {out_path}", file=sys.stderr)
        return 0

    if cmd == "verify-tool":
        path = Path(args.file)
        if not path.is_file():
            print(f"No such file: {path}", file=sys.stderr)
            return 1
        try:
            result = verify_file(path)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    if cmd == "baseline":
        try:
            result = run_baseline(
                args.kind,
                args.name,
                requirement=args.requirement,
                model=args.model,
                cap=args.cap,
                use_embeddings=args.embeddings,
            )
        except (KeyError, ValueError, OllamaError, json.JSONDecodeError) as exc:
            print(f"baseline failed: {exc}", file=sys.stderr)
            return 1
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{args.kind}_{args.name}_{args.requirement}"
        out_path = out_dir / f"{stem}.json"
        out_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        if result.artifact:
            from semanticdrift.agents.formalize import parse_formalization

            pml_path = out_dir / f"{stem}.pml"
            pml_path.write_text(
                parse_formalization(json.dumps(result.artifact)).as_promela(),
                encoding="utf-8",
            )
            print(f"wrote {pml_path}", file=sys.stderr)
        print(json.dumps(result.to_dict(), indent=2))
        print(f"wrote {out_path}", file=sys.stderr)
        return 0

    if cmd == "pipeline":
        out_dir = Path(args.out)
        try:
            if args.all_tasks:
                payload = run_suite(out_dir=out_dir, cap=args.cap)
                print(json.dumps(payload["metrics"], indent=2))
                print(f"wrote {out_dir / 'suite.json'}", file=sys.stderr)
                return 0
            if not args.name:
                print("Pass --name or --all", file=sys.stderr)
                return 1
            result = run_pipeline(
                args.name,
                requirement=args.requirement,
                cap=args.cap,
                out_dir=out_dir,
            )
        except (KeyError, FileNotFoundError, OllamaError, ValueError, json.JSONDecodeError) as exc:
            print(f"pipeline failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result.to_dict(), indent=2))
        print(f"wrote {out_dir / f'{args.name}_{args.requirement}.json'}", file=sys.stderr)
        return 1 if result.error else 0

    if cmd == "metrics":
        directory = Path(args.from_dir)
        rows = load_task_rows(directory)
        if not rows:
            print(f"No task rows in {directory}", file=sys.stderr)
            return 1
        payload = compute_metrics(rows)
        print(json.dumps(payload, indent=2))
        return 0

    if cmd == "audit":
        from_json = Path(args.from_json) if args.from_json else None
        from_pml = Path(args.from_pml) if args.from_pml else None
        try:
            result = audit_protocol(
                args.name,
                requirement=args.requirement,
                from_json=from_json,
                from_pml=from_pml,
            )
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{args.name}_{args.requirement}.json"
        out_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result.to_dict(), indent=2))
        print(f"wrote {out_path}", file=sys.stderr)
        return 0

    if cmd == "repair":
        from_json = Path(args.from_json) if args.from_json else None
        try:
            result = repair_protocol(
                args.name,
                requirement=args.requirement,
                from_json=from_json,
                cap=args.cap,
            )
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except (OllamaError, ValueError, json.JSONDecodeError) as exc:
            print(f"repair failed: {exc}", file=sys.stderr)
            return 1
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{args.name}_{args.requirement}.json"
        out_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result.to_dict(), indent=2))
        print(f"wrote {out_path}", file=sys.stderr)
        return 0

    if cmd == "list-heldout":
        path = DEFAULT_OUT / "manifest.json"
        if not path.is_file():
            print("No held-out manifest yet.", file=sys.stderr)
            return 1
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"{data['n_tasks']} tasks from {data['n_repos']} repos (cutoff {data['cutoff']})")
        for task in data["tasks"]:
            print(f"{task['repo']:50}  {task['path']}  {task['commit'][:8]}")
        return 0

    if cmd == "seed-vacuity":
        payload = build_battery()
        print(json.dumps({"n": payload["n"], "path": str(VACUITY_DIR / "battery.json")}, indent=2))
        return 0

    if cmd == "list-vacuity":
        path = VACUITY_DIR / "labels.json"
        if not path.is_file():
            print("No vacuity labels yet.", file=sys.stderr)
            return 1
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"{data['n_reviewed']} labeled  vacuous={data['n_vacuous']}  not={data['n_not_vacuous']}")
        for row in data["reviews"]:
            print(f"{row['vacuous']:3}  {row['kind']:20}  {row['id']}")
        return 0

    if cmd == "seed-mutants":
        report = seed_all(python=not args.c_only, c_sources=not args.python_only)
        print(json.dumps(report, indent=2))
        return 0

    if cmd == "run":
        if not args.name:
            print("Pass --name, for example: python -m semanticdrift run --name peterson", file=sys.stderr)
            return 1
        match = [p for p in list_protocols() if p.name == args.name]
        if not match:
            print(f"Unknown protocol {args.name!r}", file=sys.stderr)
            return 1
        module = match[0].load_module()
        events = module.run()
        for event in events:
            print(event)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
