# DANGEROUS: a file name like "x; rm -rf /" becomes part of a shell command
subprocess.run(f"ffmpeg -i {upload_path} out.mp3", shell=True)

# SAFE: arguments as a list, no shell, a timeout, and a path we generated ourselves
subprocess.run(["ffmpeg", "-i", str(upload_path), "out.mp3"], check=True, timeout=60)

# Open redirect: only follow a "next" URL that stays on our own site
from django.utils.http import url_has_allowed_host_and_scheme

next_url = request.GET.get("next", "/")
if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()},
                                       require_https=request.is_secure()):
    next_url = "/"
