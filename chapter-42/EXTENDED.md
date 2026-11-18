# Chapter 42 — Code Quality and CI: extended material

The printed edition of *Building AI-Powered Apps* keeps each chapter short. This file holds the longer material that was moved here so that nothing is lost: the full hands-on lab, troubleshooting tables, checklists, further exercises, and sections that were condensed for print.


---

# Sections condensed for print


## A Python and Django Toolchain: Ruff › The first run on real code: what Ruff found in Chapter 32

Chapter 32’s backend code was written with care and has 106 passing tests. We ran Ruff on it for the first time. The result is typical, and the way the numbers fall is the lesson.

| **Rule** | **Findings** | **What it was** |
|---|---|---|
| **E501** | 56 | Lines longer than 110 characters |
| **E702** | 19 | Several statements on one line, joined with semicolons (my test helpers) |
| **RUF012** | 10 | A mutable class attribute: Django `Meta.ordering`, DRF `permission_classes` |
| **I001, E401** | 9 | Imports in the wrong order or on one line |
| **S603, S607** | 6 | `subprocess` calls (ffmpeg), some in tests |
| **DJ008** | 3 | Models without a `__str__` method |
| **S311** | 2 | The `random` module used where a reader might expect secure randomness |
| **F401** | 2 | Imports that nothing used |
| **RUF059** | 2 | Unpacked variables that were never used |
| **S105, SIM117, UP037, B904** | 4 | A hard-coded password-like string, nested `with`, a quoted type, a `raise` inside `except` without `from` |
| **Total** | **113** | and `ruff format --check` said 28 of 40 files would be reformatted |

*(figure: see the printed book)*


## A Python and Django Toolchain: Ruff › Triage: fix it, suppress it with a reason, or switch it off

A first run like this is where teams give up and turn the linter off. Do not. Work in this order, and re-run the tests after each step.

1. **Format first.**  `ruff format .` removed 72 of the 113 findings by itself (the long lines and the semicolons), changing nothing about behaviour. 41 remained.
2. **Apply the safe fixes.**  `ruff check --fix` rewrites only things that are certain: imports sorted, unused imports removed, a quote removed. 8 more disappeared. 33 remained.
3. **Decide the rest, one rule at a time.** For each remaining finding choose exactly one: **fix the code**, **suppress this one line with a reason**, or **switch the rule off** for a good reason you write down.
| **Finding** | **Decision** | **Why** |
|---|---|---|
| **F401** unused imports (2) | Fixed automatically | Dead code the tests never noticed |
| **B904**  `raise` inside `except` with no `from` | Fixed: `raise ... from exc` | Keeps the original cause visible in the traceback |
| **DJ008** model without `__str__` | Fixed: `__str__` returns the kind and the public id | The Django admin and every log line shows it. It deliberately shows **no file name and no text**, which is private data (Chapter 17) |
| **RUF059, SIM117, E731, long lines** | Fixed by hand | Small, honest improvements |
| **S603** subprocess in `audio.py` | Suppressed on one line, with the reason written next to it | The rule warns about running untrusted input; here the arguments are a list and the paths are ours. The comment lets the next reader check that claim |
| **S311**  `random()` for retry jitter | Suppressed on one line, with the reason | Jitter spreads retries out; it protects nothing, so it need not be secure |
| **RUF012** mutable class attributes | Rule switched off for the project | Django and DRF read these attributes as configuration and never mutate them. The rule produces only noise here |
| **S101, S105, S106, S311, S603, S607 in tests** | Switched off for test files only | Asserts, fake passwords and spawning ffmpeg to make fixtures are what tests do |

**attachments/tasks.py (the S311 and B904 decisions)**

```
jitter = 0.5 + random() / 2  # noqa: S311  (spreads retries out; it protects
    nothing, so it need not be secure)
raise self.retry(exc=exc, countdown=(5 * 2**self.request.retries) * jitter) from exc
```

**attachments/audio.py (the S603 decision)**

```
return subprocess.run(args, capture_output=True, timeout=timeout, check=False)  #
    noqa: S603  (a list of arguments, never a shell; the paths are ours)
```

> **A suppression is a comment to a future reader**
>
> `# noqa: S603` without a reason is a lie told to the next person. With the reason in the same line, it is documentation that a review can challenge. Ruff even helps: the `RUF100` rule flags a `noqa` that no longer suppresses anything, so old suppressions do not pile up.

After the decisions, `ruff check .` reports **All checks passed**, `ruff format --check .` reports nothing to change, and the 106 tests still pass. The cost was one afternoon of work, and from now on the cost of keeping it clean is zero, because the checks run by themselves.


## Types: mypy and django-stubs › The first run: 147 errors

Run on the same Chapter 32 code, mypy reported **147 errors in 13 files**. That looks frightening, so look at where they are.

| **Where** | **Errors** | **What they were** |
|---|---|---|
| **Test files** | 136 | Tests that index into dictionaries and optional fields on purpose, mostly one pattern repeated: `blocks[0]["source"]` on a union type |
| **Our production code** | 8 | Real findings (below) |
| **Missing type information** | 3 | Celery ships no type information (twice), and a stand-in user manager |

The eight real findings are the interesting ones, because the tests were all green and nothing was visibly wrong.

| **Finding** | **What was wrong** | **The fix** |
|---|---|---|
| **Reusing one variable for different types** (images.py, 3 errors) | `img` started as a file image, then became a rotated image, a converted image and a resized image. Four different types behind one name | One name per stage: `upright`, `work`, `clean` |
| **A `**dict` into a typed SDK call** (providers.py) | Building `params = {...}` and calling `create(**params)` hides every argument from the type checker | Pass the arguments directly, and use the SDK’s `omit` marker for “not given” |
| **A plain** `str` **where a fixed set was required** (providers.py, speech_service.py) | The speech API accepts only `mp3`, `opus`, `aac`, `flac`, `wav` or `pcm`; our code accepted any string | An `AudioFormat` type that lists exactly those values |
| **A list that mypy could not infer** (providers.py, 2 errors) | `self.calls = []` has no element type | `self.calls: list[dict[str, Any]] = []` |
| **A** `type: ignore` **that was no longer needed** (content.py) | An old suppression that no longer suppressed anything | Delete it. `warn_unused_ignores` found it |

**attachments/providers.py (before and after)**

```
# before: the type checker cannot see inside the dict
params = {"model": self.model, "file": ("audio.wav", io.BytesIO(wav), "audio/wav")}
if language:
    params["language"] = language
result = self.client.audio.transcriptions.create(**params)

# after: every argument is checked
result = self.client.audio.transcriptions.create(
    model=self.model,
    file=("audio.wav", io.BytesIO(wav), "audio/wav"),
    language=language or openai.omit,
)
```

One more finding came from a different place. The tests for the OpenAI adapter built their fake server with the `httpx` library. The tests passed, because Python is relaxed about types at run time. But mypy reported that the OpenAI SDK, like the Anthropic SDK, is now built on `httpx2`, and the tests were handing it the wrong kind of object. We changed the tests to `httpx2`, and they still passed. A test that passes for the wrong reason is a test that will break on an upgrade, and the type checker saw it first.


## The TypeScript Toolchain: Prettier, ESLint and tsc › Tool versions: the compatibility traps of today

Quality tools depend on each other, and in the months when a big new version appears, they disagree. We hit three real ones while preparing this chapter. They are worth knowing as a class of problem, because you will meet others.

| **What we saw** | **Why** | **What to do** |
|---|---|---|
| `typescript-eslint` refused to start with TypeScript 7.0, and its message said so | TypeScript 7 is a rewrite in a different language. The ESLint plugin that reads TypeScript code did not support it yet | Pin `typescript` to `~6.0` in the apps that lint (we did, and the type check and tests passed under both 6.0.3 and 7.0.2). Move when the plugin announces support |
| ESLint 10 crashed on the Expo configuration with `context.getFilename is not a function` | A plugin inside `eslint-config-expo` 58 still used a function that ESLint 10 removed | Use ESLint 9 for the mobile app today. The Next.js configuration, in a scratch project, worked with ESLint 10 |
| `npm` printed that ESLint 9.39 “is no longer supported” | The newest supported ESLint is 10, but the mobile configuration cannot use it yet | Know the trade-off, and put a calendar reminder to revisit it. Each app has its own `package.json`, so the web app can be ahead of the mobile app |

The lesson is a process, not a version number. **Upgrade quality tools on purpose, in their own pull request, and let CI show whether the combination works.** Dependabot will propose the upgrades; the pull request tells you if they broke the pipeline.


## The TypeScript Toolchain: Prettier, ESLint and tsc › The first run on real code: what ESLint found in Chapter 32

We ran the Expo configuration on the Chapter 32 mobile code. Prettier said 19 of the 32 TypeScript files did not match the style (the new configuration, not mistakes). ESLint reported six problems: five warnings that `eslint --fix` repaired by itself (the `Array<T>` style in tests, and a file importing from the same module twice) and one **error that was a real finding**.

**eslint (Chapter 32 mobile code, before the fix)**

```
hooks/useReadAloud.ts
  22:21  error  Error: Cannot access variable before it is declared

`next` is accessed before it is declared, which prevents the earlier access from
    updating
when this value changes over time.

  20 |     Speech.speak(text, {
  21 |       language,
> 22 |       onDone: () => next(id, language),
     |                     ^^^^ `next` accessed before it is declared

components/DictationButton.tsx
  1:70  warning  'react-native' imported multiple times  import/no-duplicates
  2:25  warning  'react-native' imported multiple times  import/no-duplicates

__tests__/upload.test.ts
  10:12  warning  Array type using 'Array<T>' is forbidden. Use 'T[]' instead
      @typescript-eslint/array-type

6 problems (1 error, 5 warnings)
```

The React rules, built from the React Compiler’s checks, noticed that the speech hook defined a function with `useCallback` and then used that very function inside its own body, to call itself from the speech engine’s callback. It worked at run time, but a hook that refers to a value still being created is fragile and cannot be optimised. The fix is to move the repeating part out into a plain function that has no hooks and can safely refer to itself.

**hooks/useReadAloud.ts (after)**

```
function speakChunks(chunks: string[], language: string | undefined, isCurrent: ()
    => boolean, onEnd: () => void): void {
  const queue = [...chunks];
  const finish = () => {
    if (isCurrent()) onEnd();
  };
  const step = (): void => {
    if (!isCurrent()) return; // Stop was pressed, or a newer reading started
    const text = queue.shift();
    if (text === undefined) return finish();
    Speech.speak(text, { language, onDone: step, onStopped: finish, onError: finish
        });
  };
  step();
}
```

After the fixes and `prettier --write`, `eslint . --max-warnings=0` is silent, `tsc --noEmit` is silent, and the 63 tests still pass. The two patches in this chapter’s code download (`fixes-from-chapter-32/`) apply cleanly to the Chapter 32 files you already have.

**package.json (mobile and web, the scripts to add)**

```
{
  "scripts": {
    "test": "tsx --test __tests__/*.test.ts",
    "typecheck": "tsc --noEmit",
    "lint": "eslint . --max-warnings=0",
    "format:check": "prettier --check ."
  },
  "devDependencies": {
    "eslint": "^9.39.0",
    "eslint-config-expo": "^58.0.4",
    "prettier": "^3.9.10",
    "tsx": "^4.23.0",
    "typescript": "~6.0.3"
  }
}
```


## Pre-commit Hooks › A clean run, then a bad commit (real output)

First the hooks on clean files: every one passes.

**pre-commit run --all-files**

```
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...............................................................Passed
check toml...............................................................Passed
check for merge conflicts................................................Passed
check for added large files..............................................Passed
detect private key.......................................................Passed
ruff check...............................................................Passed
ruff format..............................................................Passed
prettier.................................................................Passed
eslint...................................................................Passed
```

Now we try to commit five bad files at once: a Python file with unused imports and trailing spaces, a TypeScript file using `Array<number>`, a fake private key, a 700 KB binary and a broken YAML file.

**git commit -m "add stuff"**

```
trim trailing whitespace.................................................Failed
- hook id: trailing-whitespace
- exit code: 1
- files were modified by this hook

Fixing backend/attachments/bad.py

fix end of files.........................................................Failed
- hook id: end-of-file-fixer
- exit code: 1
- files were modified by this hook

Fixing backend/attachments/bad.py

check yaml...............................................................Failed
- hook id: check-yaml
- exit code: 1

while parsing a flow sequence
  in "broken.yml", line 2, column 5
expected ',' or ']', but got ':'
  in "broken.yml", line 3, column 5

check toml...........................................(no files to check)Skipped
check for merge conflicts................................................Passed
check for added large files..............................................Failed
- hook id: check-added-large-files
- exit code: 1

assets/big.bin (684 KB) exceeds 500 KB.

detect private key.......................................................Failed
- hook id: detect-private-key
- exit code: 1

Private key found: keys/deploy.pem

ruff check...............................................................Failed
- hook id: ruff-check
- exit code: 1
- files were modified by this hook

Found 2 errors (2 fixed, 0 remaining).

ruff format..............................................................Failed
- hook id: ruff-format
- files were modified by this hook

1 file reformatted

prettier.................................................................Failed
- hook id: prettier
- files were modified by this hook

lib/bad.ts 49ms

eslint...................................................................Failed
- hook id: eslint
- exit code: 1

mobile/lib/bad.ts
  1:13  warning  Array type using 'Array<number>' is forbidden. Use 'number[]'
      instead  @typescript-eslint/array-type

✖ 1 problem (0 errors, 1 warning)
  0 errors and 1 warning potentially fixable with the `--fix` option.

ESLint found too many warnings (maximum: 0).
```

Read this output as a lesson in what hooks can and cannot do. Some hooks **fixed** the file and failed the commit on purpose (whitespace, end of file, Ruff removing the two unused imports, Ruff format, Prettier): look at `git diff`, stage the changes and commit again. Some hooks only **refuse** (the private key, the large file, the broken YAML, ESLint’s `Array<number>` warning): a person must decide. Nothing was committed, and the private key never entered the history.

> **A mistake we made: npx downloads tools**
>
> Our first hook run used plain `npx eslint`. In the sandbox the tool was not installed in that folder, and `npx` helpfully **downloaded ESLint from the internet** and ran it. That is slow, it can pick a different version from the one your project pins, and it executes freshly downloaded code on every commit. `npx --no-install` makes the hook fail loudly instead if the tool is missing. The same lesson applies in CI: install from a lock file, then run only what is installed.


## Pre-commit Hooks › Keep hooks fast

The budget for a hook is a few seconds, because developers who wait ten seconds on every commit will start to use `--no-verify`. We measured the real costs of the checks on this project.

| **Check** | **Measured time** | **Where it belongs** |
|---|---|---|
| `ruff check`, `ruff format --check` | 0.5 s | Hook and CI |
| `prettier --check` (whole app) | 3.7 s | Hook (staged files only: much less) and CI |
| `pre-commit run --all-files`, all hooks | 3.4 s | The whole hook set |
| `mypy` (warm cache / cold cache) | 1.1 s / 24.2 s | CI. Cold cache is too slow for a hook |
| `eslint` (whole app) | 14.2 s | Hook on staged files only; whole app in CI |
| `tsc --noEmit` | 5.3 s | CI |
| Backend tests (106) / with coverage | 8.5 s / 18.3 s | CI, or before pushing |
| `pip-audit` | 15.6 s | A scheduled job |

These numbers come from one computer and one project, so look at the proportions: formatting and linting are cheap enough for every commit, while types, tests and audits belong to CI. Tools that cache (mypy, ESLint) are far faster the second time, which is why CI should cache them.

- **Hooks are not installed by** `git clone`**.** Each developer runs `pre-commit install` once. Put it in the setup instructions and in your onboarding script.
- `--no-verify` **is for emergencies, and CI is the safety net.** If people use it routinely, the hooks are too slow or too strict: fix that.
- **Never rely on hooks for security.** A hook that detects private keys is a seatbelt, not a vault. Use a real secret scanner in CI as well, and rotate any secret that was ever committed.

## The Workflow, Piece by Piece › Only check what changed

In a monorepo, a change to the mobile app should not start a Django test run on PostgreSQL. The obvious tool is a `paths:` filter on the workflow, but it has a trap: if a required check never runs because of a path filter, GitHub shows it as “waiting” and the pull request can never be merged. The reliable pattern is to **run one workflow always, decide inside it which jobs are needed, and have a single final job that is always required**.

The deciding is a tiny Python script with no dependencies. It reads the list of changed files and prints one line per area. Writing it ourselves (instead of using a third-party action) means one less thing that can be compromised, and it can be tested.

**ci/changed_areas.py**

```
AREAS = ("backend", "web", "mobile")

# A change to the pipeline itself, or to files every area shares, must re-check
    everything.
SHARED_PREFIXES = (".github/", "ci/")
SHARED_FILES = {".pre-commit-config.yaml"}

def classify(paths: list[str]) -> dict[str, bool]:
    result = dict.fromkeys(AREAS, False)
    for raw in paths:
        path = raw.strip().replace("\\", "/").removeprefix("./")
        if not path:
            continue
        if path in SHARED_FILES or path.startswith(SHARED_PREFIXES):
            return dict.fromkeys(AREAS, True)
        for area in AREAS:
            if path.startswith(f"{area}/"):
                result[area] = True
    return result

def parse_nul_separated(data: bytes) -> list[str]:
    """`git diff --name-only -z` separates names with NUL, so unusual file names
        stay whole."""
    return [p.decode("utf-8", errors="replace") for p in data.split(b"\0") if p]

def render(result: dict[str, bool]) -> str:
    return "\n".join(f"{area}={'true' if result[area] else 'false'}" for area in
        AREAS)

def main(argv: list[str]) -> int:
```

Three details come from thinking about what can go wrong. A change to the pipeline itself (`.github/`, `ci/`) or to a shared file runs **everything**, because a broken workflow must be tested. Look-alike folders such as `webinar/` must not count as `web/`. And `git diff --name-only -z` separates names with a NUL byte, so a file with spaces or accents in its name stays in one piece.

**ci/test_ci_scripts.py (excerpt)**

```
def test_a_change_to_the_pipeline_or_shared_files_runs_everything(self):
    for path in (".github/workflows/ci.yml", "ci/gate.py",
        ".pre-commit-config.yaml"):
        self.assertEqual(changed_areas.classify([path, "docs/readme.md"]),
            ALL_TRUE, path)

def test_look_alike_folders_do_not_count(self):
    self.assertEqual(
        changed_areas.classify(["backend-notes/a.md", "webinar/b.md",
            "mobile_old/c.md"]), ALL_FALSE
    )

def test_nul_separated_input_keeps_odd_file_names_whole(self):
    data = b"backend/a b.py\0web/\xc3\xa9.ts\0"
    self.assertEqual(changed_areas.parse_nul_separated(data), ["backend/a b.py",
        "web/\u00e9.ts"])
```

**.github/workflows/ci.yml (the changes job)**

```
  changes:
    name: What changed?
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    outputs:
      backend: ${{ steps.areas.outputs.backend }}
      web: ${{ steps.areas.outputs.web }}
      mobile: ${{ steps.areas.outputs.mobile }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 2 # the merge commit and its first parent: enough to see
              what the pull request changes
          persist-credentials: false
      - name: Test the CI scripts themselves
        run: python3 ci/test_ci_scripts.py
      - name: Decide which areas to check
        id: areas
        env:
          EVENT_NAME: ${{ github.event_name }}
        run: |
          if [ "$EVENT_NAME" = "pull_request" ]; then
            git diff --name-only -z HEAD^1 HEAD | python3 ci/changed_areas.py >>
                "$GITHUB_OUTPUT"
          else
            python3 ci/changed_areas.py --all >> "$GITHUB_OUTPUT"
          fi
          cat "$GITHUB_OUTPUT"
```

For a pull request, GitHub checks out a temporary **merge commit** of your branch into the target branch. Its first parent is the target branch, so `git diff HEAD^1 HEAD` is exactly “what this pull request changes”, and `fetch-depth: 2` is enough history to ask. On a push to `main` nothing is skipped.


## The Workflow, Piece by Piece › The backend job

**.github/workflows/ci.yml (the backend job)**

```
      backend: ${{ steps.areas.outputs.backend }}
      web: ${{ steps.areas.outputs.web }}
      mobile: ${{ steps.areas.outputs.mobile }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 2 # the merge commit and its first parent: enough to see
              what the pull request changes
          persist-credentials: false
      - name: Test the CI scripts themselves
        run: python3 ci/test_ci_scripts.py
      - name: Decide which areas to check
        id: areas
        env:
          EVENT_NAME: ${{ github.event_name }}
        run: |
          if [ "$EVENT_NAME" = "pull_request" ]; then
            git diff --name-only -z HEAD^1 HEAD | python3 ci/changed_areas.py >>
                "$GITHUB_OUTPUT"
          else
            python3 ci/changed_areas.py --all >> "$GITHUB_OUTPUT"
          fi
          cat "$GITHUB_OUTPUT"

  workflows:
    name: Workflow files
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Install actionlint (pinned and checksummed)
        run: ci/install_actionlint.sh "$RUNNER_TEMP/bin"
      - name: Lint the workflow files
        run: '"$RUNNER_TEMP/bin/actionlint" -color'

  backend:
    name: Backend
    needs: changes
    if: needs.changes.outputs.backend == 'true'
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    defaults:
      run:
        working-directory: backend
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: ci
          POSTGRES_PASSWORD: ci # a throwaway database that exists for this run only
          POSTGRES_DB: ci
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U ci"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      DATABASE_URL: postgres://ci:ci@localhost:5432/ci
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            backend/requirements.txt
            backend/requirements-dev.txt
      - name: System packages (ffmpeg is used by the attachment tests)
        run: sudo apt-get update && sudo apt-get install -y --no-install-recommends
            ffmpeg
      - name: Install Python packages
        run: python -m pip install -r requirements.txt -r requirements-dev.txt
      - name: Lint
        run: ruff check .
      - name: Format check
        run: ruff format --check .
      - name: Type check
        run: mypy .
      - name: Every model change has a migration
        run: python manage.py makemigrations --check --dry-run
      - name: Tests with coverage
        run: |
          coverage run manage.py test
          coverage report
          coverage xml
      - name: Keep the coverage report
        if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 #
            v7.0.2
        with:
          name: backend-coverage
          path: backend/coverage.xml
          if-no-files-found: ignore
          retention-days: 14
```

- **A real PostgreSQL** runs beside the job as a service container. `--health-cmd` makes the job wait until the database accepts connections; without it the first test fails in a race. The password is a throwaway for a database that exists only for this run.
- `cache: pip` in `setup-python` saves the downloaded packages between runs, keyed on the requirements files.
- **ffmpeg** is installed because Chapter 32’s tests create real audio files.
- **Five checks, cheapest first**: lint, format, types, migrations, then tests. A lint failure should not wait for the tests.
- **The coverage report is kept as an artifact even when tests fail** (`if: always()`), because that is when you want it.
- `persist-credentials: false` stops the checkout from leaving the token in the repository’s Git configuration, where a later step could use or leak it.

## The Workflow, Piece by Piece › The web and mobile jobs

**.github/workflows/ci.yml (the web job)**

```
      web: ${{ steps.areas.outputs.web }}
      mobile: ${{ steps.areas.outputs.mobile }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 2 # the merge commit and its first parent: enough to see
              what the pull request changes
          persist-credentials: false
      - name: Test the CI scripts themselves
        run: python3 ci/test_ci_scripts.py
      - name: Decide which areas to check
        id: areas
        env:
          EVENT_NAME: ${{ github.event_name }}
        run: |
          if [ "$EVENT_NAME" = "pull_request" ]; then
            git diff --name-only -z HEAD^1 HEAD | python3 ci/changed_areas.py >>
                "$GITHUB_OUTPUT"
          else
            python3 ci/changed_areas.py --all >> "$GITHUB_OUTPUT"
          fi
          cat "$GITHUB_OUTPUT"

  workflows:
    name: Workflow files
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Install actionlint (pinned and checksummed)
        run: ci/install_actionlint.sh "$RUNNER_TEMP/bin"
      - name: Lint the workflow files
        run: '"$RUNNER_TEMP/bin/actionlint" -color'

  backend:
    name: Backend
    needs: changes
    if: needs.changes.outputs.backend == 'true'
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    defaults:
      run:
        working-directory: backend
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: ci
          POSTGRES_PASSWORD: ci # a throwaway database that exists for this run only
          POSTGRES_DB: ci
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U ci"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      DATABASE_URL: postgres://ci:ci@localhost:5432/ci
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            backend/requirements.txt
            backend/requirements-dev.txt
      - name: System packages (ffmpeg is used by the attachment tests)
        run: sudo apt-get update && sudo apt-get install -y --no-install-recommends
            ffmpeg
      - name: Install Python packages
        run: python -m pip install -r requirements.txt -r requirements-dev.txt
      - name: Lint
        run: ruff check .
      - name: Format check
        run: ruff format --check .
      - name: Type check
        run: mypy .
      - name: Every model change has a migration
        run: python manage.py makemigrations --check --dry-run
      - name: Tests with coverage
        run: |
          coverage run manage.py test
          coverage report
          coverage xml
      - name: Keep the coverage report
        if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 #
            v7.0.2
        with:
          name: backend-coverage
          path: backend/coverage.xml
          if-no-files-found: ignore
          retention-days: 14

  web:
    name: Web
    needs: changes
    if: needs.changes.outputs.web == 'true'
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: web/.nvmrc
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - name: Format check
        run: npx prettier --check .
      - name: Lint (Next.js 16 removed "next lint", so run ESLint itself)
        run: npx eslint . --max-warnings=0
      - name: Type check
        run: npx tsc --noEmit
      - name: Tests
        run: npm test --if-present
      - name: Build
        env:
          NEXT_PUBLIC_API_URL: https://api.example.test # a placeholder: the build
              must not need real secrets
        run: npm run build
```

The mobile job is the same shape with `mobile/` as its folder, without the build step (building the native app belongs to Chapter 26). Three details matter. `npm ci` installs exactly what the lock file says and fails if the lock file and `package.json` disagree, unlike `npm install`. `node-version-file` reads the Node version from a `.nvmrc` file in your repository, so the developer’s machine and CI use the same one. And **the build gets a placeholder** `NEXT_PUBLIC_API_URL`: a build that needs real secrets to compile is a build that cannot run on a pull request from a fork. Remember that anything in `NEXT_PUBLIC_` is public anyway (Chapter 17).

If Chapter 39 moved you to Jest, Vitest or Playwright, the `npm test --if-present` line runs whatever your `package.json` defines. End-to-end tests that need a running server belong in their own job.


## A Dress Rehearsal: Run the Job Before You Push It

The slowest way to debug a workflow is to push it and wait. Before pushing, rehearse every step on your own machine, in a **clean environment** that has nothing left over from your daily work. We did that for the backend job: a brand-new virtual environment, only the pinned requirements, a real PostgreSQL, and every step of the workflow in order.

**bash terminal**

```bash
python3 -m venv /tmp/rehearsal/venv && . /tmp/rehearsal/venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
export DATABASE_URL=postgres://ci:ci@localhost:5432/ci
ruff check .                                    # All checks passed!
ruff format --check .                           # 40 files already formatted
mypy .                                          # Success: no issues found in 40
    source files
python manage.py makemigrations --check --dry-run    # No changes detected
coverage run manage.py test                     # Ran 106 tests ... OK
coverage report                                 # TOTAL ... 96%
```

It passed, and the rehearsal was worth doing, because it found two mistakes **in my own requirements file** that a laptop with years of installed packages would never show.

| **What the clean room showed** | **Why it happened** | **The fix** |
|---|---|---|
| The database driver was missing on a clean machine | I made the list with `pip freeze \| grep` for a few package names. That kept `psycopg` but dropped its companion `psycopg-binary`, which contains the compiled part. It worked here only because the sandbox already had the system library | List the **complete** set of packages, or use a real lock file. Add `psycopg-binary` |
| A test-only package was in the production list | `reportlab`, which the tests use to make sample PDFs, sat in `requirements.txt` and would have shipped to production | Move test tools to `requirements-dev.txt`. What you do not install cannot be attacked |

> **Pin everything, in two files**
>
> `requirements.txt` is what production installs; `requirements-dev.txt` adds the tools for linting and testing. Both are fully pinned (`ruff==0.17.4`, not `ruff>=0.17`), so a green build today is a green build next month, and a new version arrives as a visible pull request (Dependabot, 42.12), never as a surprise inside an unrelated change.

The same rehearsal idea applies to `act`, a tool that runs workflows locally in containers. It is useful, but a plain script of the same commands, as above, catches most problems with no extra machinery.


## Keeping the Pipeline Itself Safe › Two tools look at a deliberately dangerous workflow

To see what automated checkers can do, we wrote a workflow with three classic mistakes: `pull_request_target`, a checkout of the pull request’s code, and the pull request title pasted into a shell command. Then we ran **actionlint** (syntax and expressions) and **zizmor** (a security analyzer for workflows).

**bad.yml (what we scanned)**

```
name: bad
on:
  pull_request_target:
jobs:
  greet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: echo "Title is ${{ github.event.pull_request.title }}"
      - run: ./build.sh
        env:
          TOKEN: ${{ secrets.DEPLOY_TOKEN }}
```

**actionlint on bad.yml**

```
.github/workflows/bad.yml:11:33: "github.event.pull_request.title" is potentially
    untrusted. avoid using it directly in inline scripts. instead, pass it through
    an environment variable. see
    https://docs.github.com/en/actions/reference/security/secure-use#good-practices-
    for-mitigating-script-injection-attacks for more details [expression]
   |
11 |       - run: echo "Title is ${{ github.event.pull_request.title }}"
   |                                 ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
```

actionlint caught the injection (it names the exact expression and tells you how to fix it) and nothing else, because the other mistakes are not syntax errors. zizmor, which looks for security patterns, reported the rest:

**zizmor on bad.yml (finding titles)**

```
warning[artipacked]: credential persistence through GitHub Actions artifacts
warning[excessive-permissions]: overly broad permissions
error[dangerous-triggers]: use of fundamentally insecure workflow trigger
error[template-injection]: code injection via template expansion
error[unpinned-uses]: unpinned action reference
```

Two tools with different jobs found different problems, which is why we run both. We then ran both on our own workflows: actionlint exits clean, and zizmor reports no findings at its normal level. At its stricter, “pedantic” level it flagged two things. The `security.yml` workflow had no `concurrency` group, which we added. And the `postgres:16` service image is referenced by a tag instead of a digest. We kept the tag on purpose: this database exists for one test run and holds nothing real, and a digest would freeze the image and stop it receiving security patches. For images you ship to production the answer is the opposite: pin them by digest (Chapters 51 and 52).


## Keeping the Pipeline Itself Safe › Pin actions to a commit

A version tag is a label that its owner can move. A commit SHA cannot be moved. You find the SHA of a release without any API key:

**bash terminal**

```bash
$ git ls-remote https://github.com/actions/checkout.git refs/tags/v7.0.1
3d3c42e5aac5ba805825da76410c181273ba90b1    refs/tags/v7.0.1
```

**.github/workflows/ci.yml**

```
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

The comment keeps it readable, and Dependabot understands the pattern and sends a pull request when a new release appears, with the new SHA and the new comment. (At the time of writing these were the current releases: checkout 7.0.1, setup-python 7.1.0, setup-node 7.1.0, upload-artifact 7.0.2. Look up the current ones when you copy the file.)


## Keeping the Pipeline Itself Safe › Secrets, environments and short-lived credentials

- **Keep secrets out of pull-request builds entirely.** CI needs none for linting, types and tests. If a test needs an external service, fake it (as Chapter 32 did for speech and vision).
- **Deployment secrets live in GitHub Environments**, which can require a human approval and can be limited to the `main` branch. Chapter 54 uses this for deployment.
- **Prefer short-lived credentials to stored keys.** For cloud access, GitHub can prove its identity to your provider (OpenID Connect) and receive a token that lasts minutes, so there is no long-lived key to steal. Support depends on your provider.
- **Never print a secret.** GitHub masks known secrets in logs, but only exact matches, and a transformed value is not masked.
- **A secret scanner belongs in CI too.** GitHub offers secret scanning and push protection; availability for private repositories depends on your plan. A scanner such as Gitleaks, run in a workflow, works anywhere. If a secret reaches the repository, **rotate it**: deleting the commit is not enough.

## Dependencies: Updates and Audits › Audits: known vulnerabilities

`pip-audit` checks your pinned Python packages against a database of known vulnerabilities, and `npm audit` does the same for Node. We ran `pip-audit` on the project’s requirements and it reported **no known vulnerabilities**, on the day we ran it. That answer changes without any change to your code: a new vulnerability can be published tomorrow about a package you have used for a year.

For that reason the audits live in their own **scheduled** workflow, not in the pull-request gate. If audits ran on every pull request, a newly published vulnerability would make every unrelated pull request fail, and developers would learn to ignore red builds. On a schedule, a failure is a task for the team, handled on purpose.

**.github/workflows/security.yml**

```
name: Security audit

# Vulnerabilities are discovered without any change to our code, so they must not
    make unrelated pull
# requests fail. This runs on a schedule instead, and a failure here is a task for
    the team, not a broken build.
on:
  schedule:
    - cron: "17 5 * * 1" # Mondays, 05:17 UTC
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: security-${{ github.workflow }}
  cancel-in-progress: false

jobs:
  python:
    name: Python packages
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: "3.12"
      - run: python -m pip install pip-audit==2.10.1
      - run: pip-audit -r backend/requirements.txt --progress-spinner off

  node:
    name: Node packages (${{ matrix.area }})
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    strategy:
      fail-fast: false
      matrix:
        area: [web, mobile]
    defaults:
      run:
        working-directory: ${{ matrix.area }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version-file: ${{ matrix.area }}/.nvmrc
      - run: npm audit --omit=dev --audit-level=high
```

- **Decide what “high” means.**  `npm audit --audit-level=high` fails only on high and critical findings, and `--omit=dev` ignores tools that never reach production. Many findings are in code paths you do not use; decide, write down the decision and move on.
- **Lock files are part of the defence.**  `package-lock.json` and pinned requirements mean an update arrives only when you review it.
- **Fewer dependencies is the best audit.** Every package you do not install is a vulnerability you cannot have. We moved `reportlab` out of production for this reason.

## Branch Protection: Making the Gate Real

Everything so far can be ignored by someone with push access, unless the repository refuses. **Branch protection** (GitHub calls the newer version **rulesets**) is the setting that turns CI from advice into a gate. Configure it once for `main`; the menu names differ a little between plans and over time, so look for **Settings, then Rules** in your repository.

| **Setting** | **What to choose** | **Why** |
|---|---|---|
| **Require a pull request** | On, with at least one approval | Nothing reaches `main` unseen, and someone other than the author looked at it |
| **Require status checks** | Only `CI result` (the gate job) | The one stable name. Jobs can be added and renamed without touching this setting |
| **Require branches to be up to date** | On | The check ran on the code as it will be merged, not on an old version of it |
| **Require review from code owners** | On, with the `CODEOWNERS` file | Changes to `.github/` and `ci/` need the platform team: whoever edits the gate cannot approve their own change |
| **Block force pushes and deletion** | On | History stays trustworthy |
| **Squash merge, or linear history** | Your team’s choice, but choose | Readable history and easy reverts |
| **Who may bypass** | Nobody, or only a named group | A rule that the boss may ignore is a suggestion |

**.github/CODEOWNERS**

```
# Who must review changes to what. Replace the handles with your own team.
*                       @your-org/maintainers
/.github/               @your-org/platform
/ci/                    @your-org/platform
/backend/               @your-org/backend
/web/                   @your-org/web
/mobile/                @your-org/mobile
```

> **Protect the pipeline from the people who edit it**
>
> Anyone who can edit `.github/workflows/` can change what CI checks, including making it check nothing. That is why `CODEOWNERS` requires the platform team for those files, and why the `changes` job runs everything when `.github/` or `ci/` changes. A pull request that weakens the gate must be reviewed by someone who did not write it.

When many people merge at once, GitHub’s **merge queue** re-tests each pull request on top of the ones ahead of it, so two individually green changes cannot combine into a red `main`. You may not need it for a small team, and it needs the workflow to also run on the `merge_group` event when you do.


## Flaky Tests and Trust

A **flaky** test is one that sometimes fails for no reason related to the change. Nothing destroys trust in CI faster. After the third mysterious red build, developers re-run until green, and the gate has become a slot machine.

| **Usual cause** | **How to prevent it** |
|---|---|
| **Tests that depend on order** | Run with `--shuffle` regularly; each test creates its own data |
| **Real time and randomness** | Inject the clock and the random source; compare with tolerances (Chapter 32’s tests give the retry code a fake clock) |
| **Real network services** | Fake the provider, as Chapter 32 did with a mock transport and fake speech classes. CI must not depend on a vendor being up, or cost money |
| **Shared state between tests** | Temporary folders and fresh databases per test (Django does this for the database) |
| **Timing assumptions (**`sleep(1)`**)** | Wait for a condition, not for a duration |
| **A slow machine** | Generous timeouts on the real cause; never `retry 3 times` on the whole suite |

- **Automatic retries hide flakiness. They do not fix it.** If you allow a retry at all, make it report which tests needed it, and treat that list as a bug list.
- **Quarantine, do not ignore.** Move a flaky test to a separate, non-blocking job with an owner and a date. The main gate stays trustworthy while the test is repaired.
- **A red build is everyone’s problem and a green build must mean something.** Fix or revert a broken `main` within the hour.

## From CI to Deployment

This chapter stops at the merge, on purpose. Deployment is a different kind of work: it has side effects, it needs secrets, and it must not happen from a pull request. When you reach Chapter 54 (Deploying with Dokploy) you will add it on top of the gate you built here, with a few rules that follow directly from this chapter.

- **Deploy only from** `main`**, only after** `CI result` **passed on that exact commit.** A deployment that can be started from a branch that was never checked defeats the gate.
- **Build once, deploy that build.** The container image tested in CI (Chapter 52) is the image that goes to production, not a second build of the same source.
- **Use a GitHub Environment** with the deployment secrets, limited to `main`, and with an optional human approval for production.
- **Keep deployment out of pull requests.** A pull request may build an image to test it; it never receives production credentials.