from django.conf import settings
from prompts.demo import SUMMARY_SCHEMA
from prompts.llm import AnthropicLLM
from prompts.runner import run_prompt
from prompt_runs.recorder import django_recorder

text = "user: How do I retry a failed Celery task?\nassistant: Use self.retry() inside a bound task."
result = run_prompt(settings.PROMPT_REGISTRY, AnthropicLLM(), "summarize_conversation",
                    {"conversation": text}, schema=SUMMARY_SCHEMA, recorder=django_recorder)
print(result.data)
print(result.record)
