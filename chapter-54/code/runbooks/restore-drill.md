# Runbook: restore drill (do this once now, then every quarter)

1. In Dokploy create a NEW PostgreSQL database named chat-restore-test (never restore over production to "see if it works").
2. Open it, Backups tab, Restore: choose the S3 destination, the production database's newest backup, and the new database.
3. Connect through an SSH tunnel and count rows: `SELECT count(*) FROM auth_user;` and compare with production.
4. Write down how long it took and the size of the backup. That is your real recovery time.
5. Delete chat-restore-test.
