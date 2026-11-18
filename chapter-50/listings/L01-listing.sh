$ echo '{"tool_name":"Read","tool_input":{"file_path":"backend/.env.production"}}' | python3 .claude/hooks/guard.py
Blocked by project hook: 'backend/.env.production' is a secrets file and is off limits. Use .env.example for variable names.
   -> exit=2

$ echo '{"tool_name":"Bash","tool_input":{"command":"cat .env | head"}}' | python3 .claude/hooks/guard.py
Blocked by project hook: '.env' is a secrets file. Do not read or write it; use .env.example for names only.
   -> exit=2

$ ... "git push --force origin main"
Blocked by project hook: Force-pushing, or pushing straight to main, is blocked. Push a branch and open a pull request.
   -> exit=2

$ ... "docker compose down -v"
Blocked by project hook: This deletes Docker volumes or images (it can delete your database). Ask me to run it.
   -> exit=2

$ ... "python manage.py test sharing"          (allowed: no output)
   -> exit=0
$ ... Read ".env.example"                       (allowed: no output)
   -> exit=0
