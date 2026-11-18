"""Command line helpers: python -m prompts.cli <render|eval|lock|check|scan|live> ..."""
import argparse
import sys
from pathlib import Path

from .demo import CASES, SUMMARY_SCHEMA, demo_model, format_conversation
from .evals import format_comparison, run_eval
from .injection import risk_level, scan_for_injection
from .llm import ScriptedLLM
from .registry import PromptRegistry

LIBRARY = Path(__file__).resolve().parent.parent / "prompt_library"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="prompts.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render", help="print a rendered prompt for the sample conversation")
    render.add_argument("name")
    render.add_argument("version")
    sub.add_parser("eval", help="compare summarize_conversation v1 and v2 on the sample cases (scripted stand-in model)")
    sub.add_parser("lock", help="add new prompt versions to LOCK.json")
    sub.add_parser("check", help="verify LOCK.json")
    scan = sub.add_parser("scan", help="scan text for injection patterns")
    scan.add_argument("text")
    live = sub.add_parser("live", help="run the eval against the real Claude API (needs ANTHROPIC_API_KEY)")
    live.add_argument("--model", default=None)
    args = parser.parse_args(argv)

    registry = PromptRegistry(LIBRARY)

    if args.command == "render":
        sample = {"conversation": format_conversation([
            {"role": "user", "content": "How do I retry a failed Celery task?"},
            {"role": "assistant", "content": "Use self.retry() inside a bound task."},
        ])}
        pv = registry.get(args.name, args.version)
        prompt = pv.render(sample if "conversation" in pv.template.variables else
                           {v: "(example)" for v in pv.template.variables})
        print(f"prompt_id: {prompt.prompt_id}\n\n--- SYSTEM ---\n{prompt.system}\n\n--- USER ---\n{prompt.messages[0]['content']}")
    elif args.command == "eval":
        llm = ScriptedLLM(demo_model)
        reports = [run_eval(llm, registry.get("summarize_conversation", v), CASES)
                   for v in registry.versions("summarize_conversation")]
        print(format_comparison(reports))
    elif args.command == "lock":
        registry.write_lock()
        print("LOCK.json updated")
    elif args.command == "check":
        problems = registry.verify_lock()
        print("\n".join(problems) if problems else "LOCK.json OK")
        return 1 if problems else 0
    elif args.command == "scan":
        findings = scan_for_injection(args.text)
        print(f"risk: {risk_level(findings)}")
        for f in findings:
            print(f"  {f.kind}: {f.excerpt}")
    elif args.command == "live":
        from .llm import AnthropicLLM
        llm = AnthropicLLM(args.model)
        print(f"model: {llm.model}")
        reports = [run_eval(llm, registry.get("summarize_conversation", v), CASES)
                   for v in registry.versions("summarize_conversation")]
        print(format_comparison(reports))
    return 0


if __name__ == "__main__":
    sys.exit(main())
