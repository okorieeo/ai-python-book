# Chapter 30 — Tool Use and AI Agents: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## From Words to Actions: What Tool Use Is › Four formatting rules the API enforces

1. **Results must come right after the request.** The user message holding the `tool_result` blocks must immediately follow the assistant message that holds the `tool_use` blocks. Nothing may sit between them.
2. `tool_result` **blocks come first.** If you add any text to that user message, it must come after every `tool_result`. Putting text first is a 400 error.
3. **One result for every request.** If the model asked for three tools in one turn (parallel tool use, on by default), send all three results together, in one user message, each with its own `tool_use_id`.
4. **Flag failures with** `is_error`**.** When a tool fails, send a `tool_result` whose content explains the problem and whose `is_error` is `true`. The model reads it and can try again or explain.
If you break these rules you will see an error such as "tool_use ids were found without tool_result blocks immediately after". Chapter 30 lists it with the others.

> **The rule that keeps projects safe**
>
> **The model proposes, and your code decides.** Treat every tool call as untrusted input from a stranger who is very good at sounding reasonable. Check who is asking, check the arguments, check the limits, and only then act.


## Defining Tools That Claude Uses Well › Descriptions: the difference is in the details

A model cannot see your code. It knows a tool only by its description, so a vague description produces wrong or missing calls. Compare these two descriptions of the same tool:

**a poor description**

```
"description": "Searches messages."
```

**a good description**

```
"description": "Searches the text of the current user's own messages for a word or phrase and returns matching snippets with the conversation id and title. Use it when the user asks which chat mentioned something. It only searches this user's data, and it does not return whole conversations."
```

The good version says what it returns, when to use it, whose data it covers, and what it leaves out. Those four things answer most of the questions the model would otherwise guess at.


## Defining Tools That Claude Uses Well › Choosing when the model uses tools: tool_choice

| **tool_choice** | **Meaning** | **Notes** |
|---|---|---|
| `auto` | The model decides whether to use a tool. The default. | Add `disable_parallel_tool_use: true` to allow at most one tool per reply. |
| `any` | The model must use one of your tools. | Returns a 400 error on Claude Opus 5.5 and Fable 5.1, and when manual extended thinking is on. |
| `tool` | The model must use one specific tool. | Same restriction as `any`. |
| `none` | The model may not use tools. | Supported everywhere. |

On the current top models you therefore cannot force a tool. Use `auto`, write clear descriptions, and, when you need guaranteed inputs, turn on strict mode. If the model is not calling tools when it should, Anthropic suggests a light instruction in the prompt such as "Use the tools to investigate before responding."


## Running the Tools: Handlers, Validation and Errors › Everything the model can see after a tool call

Every outcome becomes a `tool_result`, so the model always learns what happened and the conversation keeps going. The loop in the next section produces these:

| **What happened** | **What the model receives** | **Result flagged is_error?** |
|---|---|---|
| Tool ran fine | The handler's return value (text or JSON), cut to a size limit | No |
| The model invented a tool name | "Unknown tool 'x'. Available tools: ..." | Yes |
| The user's role may not use the tool | "You are not permitted to use this tool." | Yes |
| Arguments break the schema | "Invalid input: new_title: '' is too short" (readable, per field) | Yes |
| The handler raised `ToolError` | Your message, for example "Conversation 42 was not found." | Yes |
| The handler crashed | "The tool failed unexpectedly." Details go to your logs, never to the model | Yes |
| The user declined an approval | "The user declined this action. Do not retry it." | Yes |

Returning errors, instead of crashing, is what lets the model recover. In the tests, a model that sends an empty title gets a readable "Invalid input" message and tries again with a valid one. A model that is told only "error" cannot.

> **Arguments are user input in disguise**
>
> The model's arguments are generated text, influenced by whatever the user typed and whatever documents the model read. Validate them as you would validate a form field from the internet (Chapter 17, section 17.7): check types and ranges, use parameterized queries, and check ownership on every call. A schema is not authorization.


## The Agent Loop › Workflow or agent?

Do not reach for an agent when ordinary code will do. If you already know the steps, write them as normal code and call the model only for the fuzzy parts, such as summarizing or classifying. That version is cheaper, faster and easier to test. Use an agent when the path really depends on what the model discovers along the way.

|  | **Workflow (you write the steps)** | **Agent (the model chooses the steps)** |
|---|---|---|
| **Best when** | The steps are known: "classify the ticket, then draft a reply" | The steps depend on what is found: "find and fix the problem" |
| **Predictability** | High. The same path every time. | Lower. The path varies. |
| **Cost and speed** | One or two model calls | Several calls, each carrying the growing history |
| **Testing** | Test each step | Test outcomes, limits and safety (Chapter 33) |
| **Risk** | Small: the code limits what can happen | Larger: needs strong guardrails |


## Guardrails: Limits, Permissions and Risk Levels › Choosing the limits

| **Limit** | **Starting value** | **Why** |
|---|---|---|
| `max_steps` | 8 | Most useful tasks need a handful of calls. A loop that reaches the limit is usually stuck, for example retrying a failing tool. |
| `max_tool_calls` | 20 | Parallel calls multiply quickly. This stops one reply asking for hundreds. |
| `max_cost_usd` | 0.50 | A hard stop on money for one run. It is checked before each call, so one expensive step can overshoot it. Set it well below what you can afford to lose. |
| `max_result_chars` | 8,000 | Bounds how much one tool can add to the context. |

These numbers are starting points. Measure real runs (Chapter 33) and set them from data. Also add limits **around** runs, in your normal request throttling from Chapter 17 section 17.8: runs per user per minute, and a daily token budget per plan.


## Designing the Assistant's Tool Set

Building "an assistant that can take actions in your app" is mostly a design exercise, done before any code. A reliable way to do it:

1. **List what users actually ask for.** "Find the chat where I talked about feed prices." "Clean up my old chats." Start from jobs, not from your database.
2. **Turn each job into the smallest set of actions that does it.** Searching and listing are reads; renaming is a write; deleting is destructive.
3. **Assign a risk level to each action** and decide who may use it (roles, plans).
4. **Write the descriptions as if explaining the tool to a new colleague**, including when not to use it.
5. **Write tests for the calls you expect, and for the calls you must refuse.** Always include a second user.
6. **Start small.** Five to ten well-chosen tools beat forty overlapping ones. Add tools only when real requests need them.
For the AI Chat SaaS, the demo app's five tools look like this:

| **Tool** | **Risk** | **Who may use it** | **Notes** |
|---|---|---|---|
| `list_conversations` | read | member, viewer | Returns ids, titles and counts only. No message text. |
| `search_messages` | read | member, viewer | Only the current user's messages; limited result count. |
| `get_usage_summary` | read | member, viewer | No arguments; nothing to inject. |
| `rename_conversation` | write | member | Easy to undo. Runs without approval but is logged. |
| `delete_conversation` | destructive | member | Always pauses for a human to confirm. |

> **When the tool list grows**
>
> Every tool costs tokens on every call, and a very long list makes selection harder. Anthropic's documentation describes server-side tool search and per-tool deferred loading for large tool sets. You do not need either yet; if you reach dozens of tools, read the tool use documentation first. Also worth knowing: the **Model Context Protocol (MCP)** is a standard way for tools to be offered by separate servers and reused across applications. The safety rules in this chapter apply to MCP tools exactly as they do to your own: someone else's tool is still untrusted input.

Other providers offer the same capability under the name function calling: the model returns a structured request, you run it and send back the output. Field names and message shapes differ, so check the provider's documentation. The design and safety rules in this chapter do not change.
