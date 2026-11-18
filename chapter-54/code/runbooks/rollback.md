# Runbook: roll back a bad deploy (Compose project)

1. Stop the bleeding: open the service in Dokploy, Deployments tab, and look at the failed deployment's log.
2. Find the last good commit: `git log --oneline -10` (the Dokploy deployment list shows commit hashes).
3. Revert, do not rewrite history: `git revert <bad-commit>` then `git push origin main`.
4. The push triggers CI (or press Deploy in Dokploy if you deploy manually). Wait for the smoke test.
5. If a migration already ran: do NOT reverse it blindly. Check whether the old code can run on the new schema
   (it can, if the migration only ADDED things). If not, restore from backup into a scratch database first (restore-drill.md).
6. Write down what happened in docs/incidents.md: what broke, how you noticed, what fixed it, what stops it next time.
