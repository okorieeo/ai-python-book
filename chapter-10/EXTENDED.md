# Chapter 10 — Planning a Real Product: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## From Idea to Product › Cheap ways to test an idea before building

| **Method** | **How** | **What you learn** |
|---|---|---|
| **Interviews** | Talk to 5 people with the problem (Chapter 9) | Is the problem real and painful? |
| **Manual prototype** | Do the task for them by hand using an AI chat tool and paste the results | Is the output actually useful? |
| **Landing page** | One page with the promise, a screenshot mockup and an email sign-up | Do strangers care enough to leave an email? |
| **Clickable prototype** | Figma prototype of the core flow | Can people use it without help? |
| **Pre-sell** | Ask three people to pay or commit before it exists | Is it worth money? |
| **Concierge MVP** | Serve the first users with scripts and manual work behind the scenes | What really needs automating? |

Each costs hours, not months. If nobody responds to these, building the full stack would not have saved the idea.


## Requirements and User Stories › The INVEST checklist

| **Letter** | **A good story is...** |
|---|---|
| **I**ndependent | Can be built and released without waiting for other stories (as far as possible) |
| **N**egotiable | Describes the need, not every implementation detail |
| **V**aluable | Delivers something a user or the business cares about |
| **E**stimable | Clear enough that you can guess the effort |
| **S**mall | Fits within a few days; split large ones |
| **T**estable | Has acceptance criteria you can verify |


## Requirements and User Stories › Epics, stories and tasks

| **Level** | **Size** | **Example** |
|---|---|---|
| **Epic** | Weeks | Billing: users can subscribe with Stripe or Paystack |
| **Story** | Days | As a user, I can start a Paystack checkout for the Pro plan |
| **Task** | Hours | Create the `POST /billing/checkout` endpoint; add the webhook handler; write tests |

Work from top to bottom: define epics from your job stories (Chapter 9), break each into stories, and break stories into tasks as you pick them up. Tasks for a story are written just in time, because plans made weeks ahead go stale.


## Scoping the MVP › RICE: a score to compare features

When several features compete, give each a score so the decision is not just the loudest opinion:

**RICE**

```
RICE = (Reach x Impact x Confidence) / Effort

Reach       how many users will this affect in a period (for example per quarter)?
Impact      0.25 minimal, 0.5 low, 1 medium, 2 high, 3 massive
Confidence  50% to 100%: how sure are you about the numbers? (low = guessing)
Effort      person-weeks to build
```

RICE is a conversation tool, not a law. The guesses are rough; the value is that it makes your assumptions visible and comparable. This script ranks a sample backlog for our product. Save it as `prioritize.py` and run it:

**prioritize.py**

```
"""Rank a feature backlog with RICE scoring and group it with MoSCoW labels."""

# reach: users affected per quarter | impact: 0.25 minimal, 0.5 low, 1 medium, 2 high, 3 massive
# confidence: 0.5 to 1.0 (how sure are we?) | effort: person-weeks | moscow: must/should/could/wont
BACKLOG = [
    {"name": "Email sign-up and login",           "reach": 1000, "impact": 3,    "confidence": 1.0, "effort": 2,   "moscow": "must"},
    {"name": "Streaming chat with the assistant", "reach": 1000, "impact": 3,    "confidence": 0.8, "effort": 4,   "moscow": "must"},
    {"name": "Conversation history",              "reach": 900,  "impact": 2,    "confidence": 1.0, "effort": 1.5, "moscow": "must"},
    {"name": "Plans, limits and usage meter",     "reach": 1000, "impact": 2,    "confidence": 0.8, "effort": 3,   "moscow": "must"},
    {"name": "Stripe and Paystack subscriptions", "reach": 400,  "impact": 3,    "confidence": 0.8, "effort": 5,   "moscow": "must"},
    {"name": "Mobile app (React Native)",         "reach": 700,  "impact": 2,    "confidence": 0.8, "effort": 6,   "moscow": "should"},
    {"name": "Document Q&A (RAG)",                "reach": 300,  "impact": 2,    "confidence": 0.5, "effort": 6,   "moscow": "could"},
    {"name": "Social login (Google)",             "reach": 600,  "impact": 1,    "confidence": 0.8, "effort": 1,   "moscow": "should"},
    {"name": "Dark mode",                         "reach": 500,  "impact": 0.5,  "confidence": 1.0, "effort": 0.5, "moscow": "could"},
    {"name": "Team workspaces",                   "reach": 100,  "impact": 2,    "confidence": 0.5, "effort": 8,   "moscow": "wont"},
]

for item in BACKLOG:
    item["rice"] = item["reach"] * item["impact"] * item["confidence"] / item["effort"]

print(f"{'#':>2}  {'Feature':<36} {'RICE':>7}  {'Effort':>6}  MoSCoW")
for rank, item in enumerate(sorted(BACKLOG, key=lambda i: i["rice"], reverse=True), start=1):
    print(f"{rank:>2}  {item['name']:<36} {item['rice']:>7.0f}  {item['effort']:>4}w   {item['moscow']}")

mvp = [i for i in BACKLOG if i["moscow"] == "must"]
print(f"\nMVP (the 'must' items): {len(mvp)} features, {sum(i['effort'] for i in mvp):g} person-weeks")
later = [i["name"] for i in BACKLOG if i["moscow"] in ("should", "could")]
print("After launch:", "; ".join(later))
print("Not now:", "; ".join(i["name"] for i in BACKLOG if i["moscow"] == "wont"))
```

**output**

```text
python prioritize.py
 #  Feature                                 RICE  Effort  MoSCoW
 1  Email sign-up and login                 1500     2w   must
 2  Conversation history                    1200   1.5w   must
 3  Streaming chat with the assistant        600     4w   must
 4  Plans, limits and usage meter            533     3w   must
 5  Dark mode                                500   0.5w   could
 6  Social login (Google)                    480     1w   should
 7  Stripe and Paystack subscriptions        192     5w   must
 8  Mobile app (React Native)                187     6w   should
 9  Document Q&A (RAG)                        50     6w   could
10  Team workspaces                           12     8w   wont

MVP (the 'must' items): 5 features, 15.5 person-weeks
After launch: Mobile app (React Native); Document Q&A (RAG); Social login (Google); Dark mode
Not now: Team workspaces
```

Read the result critically. **Dark mode scores high** because it is cheap, yet it is a Could; **Stripe and Paystack subscriptions score low** because they take five weeks, yet they are a Must because without payments there is no business. Scores inform; **your judgment about what makes the product viable decides**. Also notice the confidence column: Document Q&A has 50% confidence because we have not validated demand, which is a good reason to wait.


## Estimating and Scheduling › Dependencies and the critical path

Some tasks cannot start until others finish. The **critical path** is the longest chain of dependent tasks; it determines the earliest possible finish date, and delaying any task on it delays the project. Tasks off the path have slack. This tiny scheduler computes start and end days from durations and dependencies and finds the critical path. Save as `plan.py`:

**plan.py**

```
"""Turn tasks with durations and dependencies into a schedule and find the critical path."""
from collections import defaultdict

# task: (duration in working days, [tasks that must finish first])
TASKS = {
    "design":        (5,  []),
    "schema":        (2,  ["design"]),
    "auth-api":      (4,  ["schema"]),
    "chat-api":      (5,  ["schema"]),
    "ai-service":    (4,  ["chat-api"]),
    "websocket":     (4,  ["ai-service"]),
    "web-ui":        (8,  ["design", "auth-api"]),
    "mobile-ui":     (8,  ["design", "auth-api"]),
    "billing":       (6,  ["auth-api"]),
    "deploy":        (3,  ["websocket", "web-ui", "billing"]),
    "beta-testing":  (5,  ["deploy", "mobile-ui"]),
}

def schedule(tasks):
    start, finish = {}, {}

    def finish_of(name):
        if name not in finish:
            duration, deps = tasks[name]
            start[name] = max((finish_of(d) for d in deps), default=0)
            finish[name] = start[name] + duration
        return finish[name]

    for name in tasks:
        finish_of(name)
    return start, finish

start, finish = schedule(TASKS)
total = max(finish.values())

# Walk backwards from the last task along the dependency that finishes latest = critical path
current = max(finish, key=finish.get)
critical = [current]
while TASKS[current][1]:
    current = max(TASKS[current][1], key=lambda d: finish[d])
    critical.append(current)
critical.reverse()

print(f"{'Task':<14} {'Start':>5} {'End':>4}  Timeline (each # = 1 day)")
for name in sorted(TASKS, key=lambda n: (start[n], finish[n])):
    bar = " " * start[name] + "#" * TASKS[name][0]
    mark = "*" if name in critical else " "
    print(f"{name:<13}{mark} {start[name]:>5} {finish[name]:>4}  {bar}")
print(f"\nTotal: {total} working days (about {total / 5:.1f} weeks) with unlimited parallel help")
print("Critical path (*): " + " -> ".join(critical))
print(f"Sum of all task days: {sum(d for d, _ in TASKS.values())} (one person working alone)")
```

**output**

```text
python plan.py
Task           Start  End  Timeline (each # = 1 day)
design       *     0    5  #####
schema       *     5    7       ##
auth-api           7   11         ####
chat-api     *     7   12         #####
billing           11   17             ######
web-ui            11   19             ########
mobile-ui         11   19             ########
ai-service   *    12   16              ####
websocket    *    16   20                  ####
deploy       *    20   23                      ###
beta-testing *    23   28                         #####

Total: 28 working days (about 5.6 weeks) with unlimited parallel help
Critical path (*): design -> schema -> chat-api -> ai-service -> websocket -> deploy -> beta-testing
Sum of all task days: 54 (one person working alone)
```

Two lessons. First, the **critical path** here runs through the chat, AI and WebSocket work, so those deserve your best attention and earliest start. Second, the gap between **28 days** (with a team that can work in parallel) and **54 days** (one person doing everything in sequence) is the difference between a team plan and a solo plan. If you are building alone, use the **sum**, not the critical path, and expect about 11 weeks of full-time work for this scope, before adding buffers.

> **Solo developer reality check**
>
> People working part-time, learning as they go, and handling their first deployment, payments and app store release should multiply a "full-time expert" estimate by two or three. That is normal, not failure. Plan for it, and prefer small releases so you see progress every week.


## Estimating and Scheduling › Working rhythm

| **Approach** | **How it works** | **Good for** |
|---|---|---|
| **Kanban** | A board with columns (Backlog, Doing, Review, Done) and a limit on work in progress | Solo developers and small teams with changing priorities |
| **Scrum sprints** | Fixed 1 to 2 week cycles, planning at the start, demo and retrospective at the end | Teams that benefit from a regular cadence |
| **Weekly goals** | One or two measurable goals per week, reviewed on Fridays | A simple start for individuals |

Whichever you choose, keep **work in progress low** (finish before starting), **demo working software** frequently, and hold a short retrospective: what went well, what did not, what will we change?


## Risks and the Definition of Done › A risk register

List what could go wrong, how likely and how damaging it is, and what you will do about it. Spending 30 minutes here saves weeks later. A starter register for our product:

| **Risk** | **Likelihood / impact** | **Mitigation** |
|---|---|---|
| AI costs exceed revenue | High / High | Token caps per plan, usage ledger, monitoring, model choice, unit economics model (10.5) |
| AI provider outage or rate limits | Medium / High | Timeouts, retries, fallback model, clear user messages (Chapter 6) |
| Payment webhooks missed or duplicated | Medium / High | Signature verification, idempotent storage, reconciliation job, alerts |
| Security breach or leaked key | Low / Very high | Secrets management, least privilege, dependency updates, backups (Chapter 17) |
| Scope creep delays launch | High / Medium | MVP list, "not now" list, weekly review |
| Underestimated learning curve | High / Medium | Walking skeleton first, risky parts early, buffers |
| App store rejection | Medium / Medium | Read guidelines early; privacy policy and account deletion in place (Chapter 26) |
| Data loss | Low / Very high | Automated, tested backups; separate staging database |
| Nobody wants it | Medium / Very high | Early user conversations, landing page test, quick beta |


## Using AI Assistants in Planning and Development › Habits that keep it useful

- **Give context**: the product brief, stack, constraints and conventions. Keep them in files in the repo, so every conversation can start from the same source.
- **Maintain a project instructions file** for your coding assistant (many tools read one, for example `CLAUDE.md` for Claude Code): the stack, folder layout, commands to run tests, naming rules and "never do" items (never commit `.env`, never skip migrations). It stops you repeating yourself and keeps generated code consistent.
- **Work in small steps** with Git commits between them, so any change can be reviewed and undone.
- **Verify**: run the tests, read the diff, check documentation for APIs and library versions it mentions.
- **Own the decisions**: AI can list options; you decide what the product is and what to cut.
- **Protect secrets and personal data**: do not paste keys, `.env` contents or real customer data.