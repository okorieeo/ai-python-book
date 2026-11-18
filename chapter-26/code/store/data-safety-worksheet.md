# Data declaration worksheet (fill in BEFORE opening Play Console / App Store Connect)

One row per kind of data. The same facts answer Apple's privacy labels and Google's Data safety form.

| Data | Collected? | Linked to the user? | Why | Shared with | Can the user delete it? |
|---|---|---|---|---|---|
| Email address | yes | yes | account, login | no one | yes, delete account |
| Chat messages | yes | yes | provide the chat feature | AI provider (Anthropic) | yes, delete chat / account |
| Images the user attaches | yes | yes | provide the chat feature | AI provider (Anthropic) | yes |
| Crash logs / diagnostics | yes | no | fix bugs | crash-reporting service (Chapter 55) | n/a |
| Device identifiers for ads | no | n/a | n/a | n/a | n/a |

Rule: if you add an SDK (analytics, crash reporting, ads), re-open this table first.
