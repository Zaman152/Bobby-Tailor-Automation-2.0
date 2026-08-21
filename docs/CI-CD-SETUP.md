# CI/CD Setup — Bobby Tailor

A pipeline for a repository with three unusual properties. Read this section
before copying any YAML, because each one changes what CI is allowed to do.

| Property | Consequence |
|---|---|
| The full suite takes **~80 minutes** (2,765 tests) | It cannot gate every push. Two lanes, not one. |
| Some tests **spend real money** | CI must be structurally incapable of running them. |
| Gates here **skip rather than fail** when a fixture drifts | Green is not proof. The skip count must be asserted. |

---

## 0. The three rules

**1 · CI never spends money.** `pytest.ini` sets `addopts = -m "not golden"`, so
golden tests are deselected by default. That is a default, not a lock — anyone
can pass `-m golden`. CI must also withhold the credential, so that even a
mistaken invocation cannot bill anything. **Never add `ANTHROPIC_API_KEY` to
repository secrets.** There is no CI job in this design that needs it.

**2 · A green suite is not a passing suite.** Twice in one week the determinism
gate went from `19 passed` to `9 passed / 10 skipped` because a replay fixture
drifted, and the suite still reported green — the gate passed for having looked
at nothing. The skip count is the tell, so CI asserts it.

**3 · Deploy is single-worker.** `jobs`, `uploads`, `object_manifests` and the
active-job lock are module-level dicts in one process. `-w 1` is a correctness
requirement, not a tuning choice. With two workers an upload handled by worker A
404s when the follow-up request lands on worker B.

---

## 1. What CI actually has

Fixtures are split deliberately, and it matters for skip counts.

| Path | In git? | Effect in CI |
|---|---|---|
| `tests/fixtures/**` (9.1 MB) | **yes** — incl. Crow + Bob's plan PDFs | The important real-drawing tests RUN |
| `uploads/**` (Moxy 87 MB, Chelsea 67 MB) | no | Four-set sweeps SKIP cleanly |
| `output/**`, `reports/**` | no | Run artifacts, never committed |

So CI exercises two real plan sets. Tests needing the other two skip by design —
every such module carries its own skip guard.

**This means the CI skip count differs from your local one.** Locally, with all
four sets present, the baseline is **1 skipped**. In CI it will be higher.
Measure it once on a green run and pin that number (§3).

---

## 2. Workflows

Create `.github/workflows/`.

### 2.1 `pr.yml` — the fast lane (~12 min, every push and PR)

```yaml
name: PR checks
on:
  pull_request:
  push:
    branches: [main]

jobs:
  fast:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"      # the runtime this app ships on
          cache: pip

      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest
          # NOT playwright browsers: StackCT-only, and this deploy is plans-only.

      - name: Refuse to run with a paid credential present
        run: |
          if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
            echo "::error::ANTHROPIC_API_KEY is set in CI. No job here needs it."
            exit 1
          fi

      - name: Import check
        run: python -c "import bobbytailor, app; print('imports ok')"
        env:
          PYTHONPATH: src
          SECRET_KEY: ci
          ADMIN_EMAIL: ci@example.com
          ADMIN_PASSWORD_HASH: $2b$12$CIonlyCIonlyCIonlyCIonlyCIonlyCIonlyCIonlyCIonlyCIo

      - name: Critical modules
        run: |
          python -m pytest -q --timeout=900 \
            tests/test_production_user_path.py \
            tests/test_report_honesty.py \
            tests/test_blueprint_parity.py \
            tests/test_aggregator.py \
            tests/test_calculator_accuracy.py \
            tests/test_phase31_waste_is_not_quantity.py \
            tests/test_phase31_region_fields_reach_the_aggregator.py
        env:
          PYTHONPATH: src
```

Those seven modules are chosen because each one guards a defect that reached a
paid run: the composed user path, the report's honesty contract, blueprint
parity, aggregation, calculation, waste-vs-quantity, and the reporter whitelist.

### 2.2 `full.yml` — the slow lane (~85 min, nightly + manual + pre-deploy)

```yaml
name: Full suite
on:
  schedule: [{ cron: "0 2 * * *" }]     # 02:00 UTC nightly
  workflow_dispatch:                     # and on demand, before a deploy

jobs:
  full:
    runs-on: ubuntu-latest
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.9", cache: pip }

      - run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt pytest

      - name: Refuse to run with a paid credential present
        run: |
          if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
            echo "::error::ANTHROPIC_API_KEY is set in CI."; exit 1; fi

      - name: Full offline suite
        run: python -m pytest -q | tee /tmp/suite.log
        env: { PYTHONPATH: src }

      - name: A gate that skips is a gate that did not run
        run: |
          SUMMARY=$(tail -5 /tmp/suite.log | grep -E "passed" | tail -1)
          echo "$SUMMARY"
          SKIPPED=$(echo "$SUMMARY" | grep -oE '[0-9]+ skipped' | grep -oE '[0-9]+' || echo 0)
          # Pin this to the number a GREEN CI run reports (see §3).
          EXPECTED=${EXPECTED_SKIPS:-0}
          if [ "$SKIPPED" -gt "$EXPECTED" ]; then
            echo "::error::$SKIPPED skipped, expected $EXPECTED."
            echo "A test that skips is not a test that passed. Most likely a"
            echo "replay fixture drifted: re-author with"
            echo "  python3 scripts/author_replay_fixtures.py"
            exit 1
          fi
        env:
          EXPECTED_SKIPS: "0"   # <-- set this, see §3

      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: suite-log, path: /tmp/suite.log }
```

---

## 3. Pin the skip baseline (do this once)

1. Run **Full suite** manually with `EXPECTED_SKIPS: "0"`. It will fail and print
   the real number.
2. Set `EXPECTED_SKIPS` to that number and commit.
3. From then on, **any increase fails the build.**

The usual cause of an increase is replay-fixture drift after a change to the
symbol gallery. The fix is one zero-API command:

```bash
python3 scripts/author_replay_fixtures.py
```

Do not raise `EXPECTED_SKIPS` to make a build pass. Raising it is how a gate
stops testing and nobody notices.

---

## 4. What CI must never do

- **Never** set `ANTHROPIC_API_KEY`.
- **Never** run `pytest -m golden`, `scripts/accuracy_gate.sh`,
  `scripts/vision_only_benchmark.py`, or `scripts/golden_convergence.py`.
  These call a paid API. Accuracy is measured **deliberately, by a human, on a
  known tree** — not on every merge.
- **Never** commit `output/`, `reports/`, `uploads/` or `manifests/`.
  `manifests/default.json` in particular is a decoy the benchmark plants to
  prove plans-only isolation; a leftover copy silently **disables** that
  tripwire.

---

## 5. Deployment (CD)

### 5.1 Server secrets

Set as GitHub **repository secrets**, never in the repo:

| Secret | Notes |
|---|---|
| `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` | VPS access |
| `SECRET_KEY` | long random string |
| `ADMIN_EMAIL` | login |
| `ADMIN_PASSWORD_HASH` | bcrypt, starts `$2b$` |
| `ANTHROPIC_API_KEY` | **on the server only** — never exposed to a CI job |

Leave `STACKCT_EMAIL` / `STACKCT_PASSWORD` **empty**. With them set the app
starts a 24-hour catalog scheduler against a service a plans-only box never
uses.

### 5.2 The systemd unit

`/etc/systemd/system/bobbytailor.service`:

```ini
[Unit]
Description=Bobby Tailor take-off
After=network.target

[Service]
Type=simple
User=bobbytailor
WorkingDirectory=/opt/bobbytailor
EnvironmentFile=/opt/bobbytailor/.env
# -w 1 is MANDATORY. Job state is in-process; two workers 404 half the uploads.
ExecStart=/opt/bobbytailor/.venv/bin/gunicorn -w 1 --threads 4 \
          -b 127.0.0.1:5050 app:app --timeout 300
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 5.3 `deploy.yml`

```yaml
name: Deploy
on:
  workflow_dispatch:
    inputs:
      confirm:
        description: 'Type "deploy" to confirm'
        required: true

jobs:
  deploy:
    if: github.event.inputs.confirm == 'deploy'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy over SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            set -e
            cd /opt/bobbytailor
            git rev-parse HEAD > /tmp/bt_previous   # for rollback
            git fetch --all && git reset --hard origin/main
            .venv/bin/pip install -q -r requirements.txt
            sudo systemctl restart bobbytailor
            sleep 5

            # Smoke test — every step has a check you can watch fail.
            code() { curl -s -o /dev/null -w '%{http_code}' "$1"; }
            [ "$(code http://127.0.0.1:5050/login)" = "200" ] || { echo "login not served"; exit 1; }
            # 401 here is the point: report data must NOT be public.
            [ "$(code http://127.0.0.1:5050/api/reports)" = "401" ] || { echo "REPORTS ARE PUBLIC"; exit 1; }
            [ "$(code http://127.0.0.1:5050/)" = "302" ] || { echo "root not redirecting"; exit 1; }

            # Exactly one worker, or job state splits across processes.
            W=$(pgrep -fc "gunicorn.*app:app" || echo 0)
            [ "$W" -le 2 ] || { echo "more than one worker ($W)"; exit 1; }
            echo "deploy ok $(git rev-parse --short HEAD)"
```

**Rollback:**

```bash
ssh $DEPLOY_USER@$DEPLOY_HOST \
  'cd /opt/bobbytailor && git reset --hard $(cat /tmp/bt_previous) && sudo systemctl restart bobbytailor'
```

---

## 6. The two failures that look like something else

**Login succeeds, then loops forever.** The session cookie is `Secure` by
default, so over plain HTTP the browser never returns it: `/login` reports
success and every request redirects back to `/login`, with nothing in the log
and nothing on screen. Behind nginx + TLS, leave it unset. For an SSH tunnel or
a local box, uncomment in `.env`:

```bash
SESSION_COOKIE_SECURE=false
```

**Uploads 404 on the follow-up request.** More than one gunicorn worker. See
`-w 1` above.

Also: nginx needs `client_max_body_size 500M` (matching `MAX_UPLOAD_MB`) and
must forward `X-Forwarded-For` / `X-Forwarded-Proto`. The app trusts exactly one
hop.

---

## 7. Measuring accuracy — deliberately, never in CI

Accuracy runs cost money and belong to a human on a known tree:

```bash
python3 scripts/vision_only_benchmark.py \
  --name Bobs_$(date +%Y%m%d) \
  --golden  tests/fixtures/bobs_discount/bobs_discount_golden.csv \
  --plans   "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf" \
  --manifest tests/fixtures/bobs_discount/bobs_plans_derived_manifest.json \
  --repro --budget 3.00
```

`--repro` runs it twice and reports per-item deltas, which is the only honest
answer to "does the same plan give the same result".

Two rules learned the hard way:

- **Use a plans-derived manifest.** `bobs_discount_manifest.json` is a
  byte-identical copy of the golden's item list — running against it produces a
  flattering number that is evidence of nothing.
- **A fix proved on a function is not a fix proved on a row.** A waste-factor
  fix passed its unit tests and left the published Gas Piping row byte-identical
  through a whole paid run, because a second producer published it. Assert the
  ROW.
