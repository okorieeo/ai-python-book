$ git diff main...HEAD | python -m tools.dep_review
ERROR   backend/requirements.txt: reqeusts ==2.32.3: name is very close to popular package 'requests'. Typo, or a lookalike?
NEW     pypi package 'reqeusts': verify it exists, who maintains it and when it was published
WARNING backend/requirements.txt: django-rest-auth-helper >=1.0: not pinned exactly (use == and a lockfile with hashes if you can)
NEW     pypi package 'django-rest-auth-helper': verify it exists, who maintains it and when it was published
NEW     pypi package 'celery': verify it exists, who maintains it and when it was published
WARNING backend/requirements.txt: -e git+https://github.com/someone/fastjwt.git#egg=fastjwt url: installed from a URL or git, not the package registry
ERROR   web/package.json: lodahs ^4.17.21: name is very close to popular package 'lodash'. Typo, or a lookalike?
NEW     npm package 'lodahs': verify it exists, who maintains it and when it was published
NEW     npm package 'zod': verify it exists, who maintains it and when it was published

Before accepting a new dependency:
  1. Does the package really exist in the registry, under exactly this name?  (npm view <name> / the PyPI page)
  2. Is it what you meant? Compare with the official docs or repository of the library you wanted.
  3. Age, maintainers, recent releases, download count, license, open security advisories.
  4. Do you need it at all? Could the standard library or an existing dependency do the job?
  5. Is the version pinned and the lockfile committed? Does the install run scripts?
exit=1
