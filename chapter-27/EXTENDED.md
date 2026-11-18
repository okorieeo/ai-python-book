# Chapter 27 — AI Fundamentals for App Developers: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## Tokens: The Unit of Everything › Three ways to count tokens

| **Method** | **How** | **Accuracy** | **Use it for** |
|---|---|---|---|
| **Estimate** | `estimate_tokens(text)`: characters divided by three, rounded up. No network. | A rough guess | Quick "obviously fits" or "obviously huge" checks, and tests |
| **Count endpoint** | `client.messages.count_tokens(...)`: Anthropic counts a request without running it. | Close to billing; documented as an estimate | Checking a prompt before you send it. Free, but rate limited. |
| **Usage in the reply** | `response.usage` on every real call. | Exact: this is what you are billed | Cost tracking, budgets, invoices |

The first two are in `ai_lab/tokens.py`. The third is parsed into one shape by `ai_lab/cost.py`, which Section 27.7 uses.

**ai_lab/tokens.py (excerpt)**

```
def estimate_tokens(text: str, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
    """A quick guess. Good enough to decide 'obviously fits' or 'obviously huge'.

    Never use it for billing. Use the usage the API returns for that.
    """
    if not text:
        return 0
    return math.ceil(len(text) / chars_per_token)

def fits_in_context(model: ModelInfo, prompt_tokens: int, max_output: int) -> bool:
    """Input plus the largest reply you allow must fit in the context window."""
    return prompt_tokens + max_output <= model.context_window
```

> **A mistake worth avoiding**
>
> **Do not estimate cost from** `len(text.split())`**.** Words are not tokens, and the gap changes with language, code and model. Use the `usage` numbers the API returns for anything involving money.


## Embeddings: Meaning as Numbers › Where embeddings come from

| **Source** | **What to know** |
|---|---|
| **Anthropic** | Anthropic does not offer its own embedding model. Its documentation points to Voyage AI as one provider to pair with Claude. Check the current embeddings page for how to get access. |
| **OpenAI** | A dedicated embeddings endpoint (`client.embeddings.create`) with several model sizes. Many other providers copy this shape. |
| **Open-source models** | Models you run yourself, for example through Ollama or a Python library such as sentence-transformers. No per-token fee and your text never leaves your server, but you manage the hardware. |

Our `OpenAICompatEmbedder` works with the second and third rows, because Ollama and many gateways expose the same `/v1/embeddings` shape that OpenAI does.


## Embeddings: Meaning as Numbers › Six rules for embeddings

1. **Use the same model for documents and queries.** Vectors from different models live in different spaces and cannot be compared. Our `dot` function raises an error if the lengths differ, which catches the most common version of this mistake.
2. **Store the model name and the dimension with every vector.** Future you will need to know which model made them.
3. **Changing the model means re-embedding everything.** Plan for it, and keep the original text.
4. **Match your database column to the dimension.** In Chapter 31 a pgvector column has a fixed size.
5. **Treat embeddings as personal data.** They are derived from your users' text, and vectors can reveal information about it. Protect and delete them like the text itself (Chapters 17 and 34).
6. **Similar is not the same as correct.** Search finds related text. Whether that text answers the question is a separate check.
Embeddings are usually billed only for input tokens and cost far less than generating text with a chat model, which is why it is practical to embed a whole library of documents once and reuse the vectors.


## The Model Landscape: Providers and Model Families › Three kinds of model

- **Hosted frontier models** are reached through a company's API. You send text over the internet and pay per token. The main providers are Anthropic (Claude), OpenAI (the GPT-6 family in late 2026) and Google (Gemini). Their strongest models are usually the most capable, and you manage no hardware.
- **Open-weight models** have downloadable weights that you can run yourself or rent through a host. Families you will see in 2026 include gpt-oss, Gemma, Qwen, DeepSeek, Mistral and Llama. "Open-weight" is not the same as "open-source": always read the licence. Some are permissive (Apache 2.0, MIT), while others use custom community licences with conditions on commercial use.
- **Specialized models** do one job: embeddings (section 27.5), speech-to-text and text-to-speech, and image models. Chapter 32 covers them.
There are also several **ways to reach** the same model. Claude, for example, is available through Anthropic's own API and through Amazon Bedrock, Google Cloud, Microsoft Foundry and Claude Platform on AWS. Some teams use a **gateway** such as OpenRouter or LiteLLM to reach many providers through one interface. Local runtimes such as Ollama, vLLM and llama.cpp serve open-weight models on your own machine or server.


## The Model Landscape: Providers and Model Families › Hosted API or your own server?

| **Question** | **Hosted API (Claude, OpenAI)** | **Open-weight model you run** |
|---|---|---|
| **Setup** | An account and a key. Working in minutes. | Hardware or a rented GPU, a runtime, model files. Hours or days. |
| **Cost shape** | Pay per token. Cost scales with usage and is easy to measure. | Pay for the machine whether or not it is busy. Cheap at steady high volume, wasteful when idle. |
| **Quality ceiling** | The strongest models are here. | Strong and improving, but the best open models are usually large and need serious hardware. |
| **Data control** | Your text goes to the provider. Read its data and retention terms (Chapter 34). | Text stays on your servers. |
| **Reliability work** | The provider runs it. You handle rate limits and outages (Chapter 29). | You run it: updates, monitoring, scaling, security (Chapters 53 to 55). |
| **Good first choice for** | Almost every new product. | Strict data rules, offline use, or very high steady volume. |

> **Budgeting when your customers pay in naira**
>
> API bills are in US dollars, and so are the prices in this chapter. If you charge customers in naira (Chapter 37 covers Paystack), a falling exchange rate raises your cost without changing your usage. Plan in dollars, convert at a cautious rate, and use the per-user limits and daily budget from Chapter 17 section 17.8 so one heavy user cannot burn the month's margin. Confirm on the provider's supported-regions page that your account and payment method work from where you operate, before you design around it.


## Choosing a Model: Cost, Speed and Quality › Routing: the cheapest model that fits the job

Real products often use more than one model: a fast one to classify the request, a balanced one to answer, a strong one for the rare hard case. `ai_lab/router.py` captures the idea in a few lines. You describe a job by its minimum tier and its size, and it returns the cheapest catalog model that qualifies.

**ai_lab/router.py (excerpt)**

```
def choose_model(job: Job, models: Optional[Iterable[ModelInfo]] = None) -> ModelInfo:
    candidates = []
    for model in models if models is not None else CATALOG.values():
        if TIER_ORDER[model.tier] < TIER_ORDER[job.min_tier]:
            continue
        if job.providers and model.provider not in job.providers:
            continue
        if job.prompt_tokens + job.max_output > model.context_window:
            continue
        if job.max_output > model.max_output:
            continue
        candidates.append(model)
    if not candidates:
        raise NoModelFits(
            f"No model satisfies job {job.name!r}. "
            "Relax a requirement or register more models."
        )

    def sort_key(model: ModelInfo):
        price = blended_price(model.price_for(job.prompt_tokens))
        return (price, TIER_ORDER[model.tier])

    return min(candidates, key=sort_key)
```

**python (a shell, or a scratch file)**

```python
from ai_lab.router import Job, choose_model

for job in (
    Job("classify-intent", min_tier="fast"),
    Job("chat-reply", min_tier="balanced"),
    Job("plan-a-refactor", min_tier="strong", prompt_tokens=200_000, max_output=20_000),
):
    print(f"{job.name:<18}-> {choose_model(job).model_id}")
```

**output**

```text
classify-intent   -> claude-haiku-5-5
chat-reply        -> claude-sonnet-5-5
plan-a-refactor   -> claude-opus-5-5
```


## Model APIs: How You Actually Call One › OpenAI and the API shape everyone copies

OpenAI's API has a similar job and different names. OpenAI's current guidance for new projects is its **Responses API**; the older **Chat Completions** shape is still accepted by OpenAI, and, importantly, by almost every other service that wants to be compatible: Ollama, vLLM, and many gateways and hosts. That compatibility is why one class can talk to all of them:

**ai_lab/providers.py (OpenAICompatProvider, excerpt)**

```
def _params(self, request: ChatRequest) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if request.system:
        messages.append({"role": "system", "content": request.system})
    messages.extend({"role": m.role, "content": m.content} for m in request.messages)
    params: dict[str, Any] = {
        "model": request.model,
        "messages": messages,
        self.token_param: request.max_tokens,
    }
    if request.effort:
        params["reasoning_effort"] = request.effort
    params.update(request.extra)
    return params

def complete(self, request: ChatRequest) -> Completion:
    started = _now_ms()
    response = self.client.chat.completions.create(**self._params(request))
    choice = response.choices[0]
    return Completion(
        text=choice.message.content or "",
        model=response.model,
        provider=self.name,
        stop_reason=str(choice.finish_reason),
        usage=TokenUsage.from_openai(response.usage),
        latency_ms=int(_now_ms() - started),
    )
```

| **Topic** | **Anthropic Messages API** | **OpenAI Chat Completions style** |
|---|---|---|
| **System prompt** | A top-level `system` field. | A message with role `system` at the start of `messages`. |
| **Reply text** | `content`: a list of blocks; read the `text` ones. | `choices[0].message.content`: a string. |
| **Why it stopped** | `stop_reason`: `end_turn`, `max_tokens`, ... | `finish_reason`: `stop`, `length`, ... |
| **Token usage** | `input_tokens`, `output_tokens`; cache reads and writes are separate fields. | `prompt_tokens`, `completion_tokens`; cached tokens are counted **inside**  `prompt_tokens`. |
| **Reply limit** | `max_tokens` (required). | `max_completion_tokens` on newer models; many local servers still expect `max_tokens`. |
| **Sampling settings** | Omit `temperature`, `top_p`, `top_k` on current Claude models. | Usually accepted, though some reasoning models restrict them. |
| **Embeddings** | No Anthropic model (section 27.5). | A separate `/embeddings` endpoint. |

That table is the reason `TokenUsage` has two constructors, `from_anthropic` and `from_openai`. One treats cached tokens as separate, the other as a subset. Getting that wrong silently double-counts or under-counts your bill, and the tests check both.


## Model APIs: How You Actually Call One › Local and open-source models

Ollama and vLLM both run open-weight models and expose an OpenAI-compatible server, so the same provider class works with a different `base_url`. Ollama listens on `http://localhost:11434/v1` by default. Pass `token_param="max_tokens"` because local servers usually expect the older name:

**ai_lab/lab.py (excerpt)**

```
def build_provider(kind: str) -> LLMProvider:
    if kind == "anthropic":
        config.require("ANTHROPIC_API_KEY")  # fail early with a friendly message
        return AnthropicProvider()
    if kind == "openai":
        return OpenAICompatProvider(
            name="openai", api_key=config.require("OPENAI_API_KEY"),
            base_url=config.optional("OPENAI_BASE_URL") or None,
        )
    if kind == "local":
        return OpenAICompatProvider(
            name="local",
            base_url=config.optional("LLM_BASE_URL", "http://localhost:11434/v1"),
            token_param="max_tokens",
        )
    raise SystemExit(f"Unknown provider {kind!r}. Use anthropic, openai or local.")
```

- **Pull the model first.** A local server can only answer with a model you have downloaded. Ollama's `ollama list` shows the exact names to use.
- **Mind the context size.** Local runtimes often default to a much smaller context window than the model supports. If a local model seems to ignore the start of a long prompt, raise the runtime's context setting.
- **Expect different quality.** Small models run well on a laptop, but they are not the same as a frontier model. Test them on your own examples (section 27.7).
- **Keep the server private.** A local model server has no authentication by default. Bind it to localhost, or put it behind your own authentication, and never expose it to the internet (Chapter 17).