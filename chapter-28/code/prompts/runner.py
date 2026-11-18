"""Run a named, versioned prompt and record what happened (never the text itself)."""
import time
from dataclasses import dataclass

from .injection import check_output, risk_level, scan_for_injection
from .structured import complete_structured


@dataclass
class RunResult:
    data: object            # parsed JSON when a schema was given, else the reply text
    record: dict            # ids, counts and flags: safe to store and log
    output_problems: list   # empty when the reply passed check_output


def run_prompt(registry, llm, name: str, variables: dict, *, version: str = None, schema: dict = None,
               recorder=None, max_tokens: int = 800, max_retries: int = 1,
               canary: str = "", allowed_hosts=frozenset()) -> RunResult:
    """Render, call, validate, check, record. Errors from rendering or parsing propagate."""
    prompt_version = registry.get(name, version)
    prompt = prompt_version.render(variables)

    findings = []
    for var in prompt_version.template.untrusted:
        findings.extend(scan_for_injection(variables[var]))

    started = time.monotonic()
    if schema is not None:
        result = complete_structured(llm, system=prompt.system, messages=prompt.messages,
                                     schema=schema, max_tokens=max_tokens, max_retries=max_retries)
        data, attempts = result.data, result.attempts
        tokens_in, tokens_out = result.input_tokens, result.output_tokens
        reply_text = str(data)
    else:
        reply = llm.complete(system=prompt.system, messages=prompt.messages, max_tokens=max_tokens)
        data = reply_text = reply.text
        attempts, tokens_in, tokens_out = 1, reply.input_tokens, reply.output_tokens

    problems = check_output(reply_text, canary=canary, allowed_hosts=allowed_hosts)
    record = {
        "prompt_id": prompt.prompt_id,
        "model": getattr(llm, "model", ""),
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "attempts": attempts,
        "injection_risk": risk_level(findings),
        "output_flagged": bool(problems),
    }
    if recorder:
        recorder(record)
    return RunResult(data=data, record=record, output_problems=problems)
