# Build plan: Share a conversation by link

Rules: one task = one prompt = one commit. Do not start a task until its dependencies are
merged. Lane tells you which directory the task may touch. "Covers" lists acceptance criteria.

| ID  | Lane      | Task                                                         | Depends on | Covers        | Done when |
|-----|-----------|--------------------------------------------------------------|------------|---------------|-----------|
| T1  | contract  | Write the OpenAPI contract and lint it                       | spec       | AC-1,2,3,6    | contract_lint passes |
| T2  | backend   | SharedLink model, migration, token helpers                   | T1         | AC-2,4,12     | model tests pass |
| T3  | backend   | Services: create, list, revoke, resolve, record view         | T2         | AC-1,5,6,9    | service tests pass |
| T4  | backend   | Serializers, views, URLs, throttles                          | T3         | AC-3,7,8,10   | API tests pass, schema matches contract |
| T5  | web       | Generate API types, typed client                             | T1         | -             | tsc passes |
| T6  | web       | ShareDialog (create, copy, list, revoke)                     | T5         | AC-1,5,11     | component tests pass |
| T7  | web       | Public page /s/[token] (server component, noindex)           | T5         | AC-3,6,10     | page test passes |
| T8  | mobile    | Typed client, useShareLink hook, ShareButton (native sheet)  | T1         | AC-1,11       | jest passes |
| T9  | infra     | Compose, Dockerfiles, CI jobs for the new code               | T4,T6,T8   | -             | CI green |
| T10 | all       | End-to-end check against a running stack                     | T4,T7,T8   | all           | checklist in PR |

Parallel after T1 merges: {T2 -> T3 -> T4}, {T5 -> T6, T7}, {T8}. Join at T9.
