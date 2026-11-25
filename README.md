# ZYNTRIX AgroSphere AI

A software-first agricultural workspace: AgroDoctor crop-photo screening, FloodCrop rainfall preparedness, KrishiMarket net selling comparisons, shared farms, actions and future sensor ingestion.

Open **Farm tools** as a farmer for the crop calendar, in-app alerts and reminders, plot cash ledger, storage batches, community map and encrypted offline notebook. **Farmer Chat** accepts voice drafts on supported browsers and retrieves [agricultural guidance with source links](docs/farmer-chat-rag.md). See the [farm tools plan and release scope](docs/farm-tools-plan.md).

Connect a local MCP client to the [AgroSphere read-only tools](docs/agrosphere-mcp.md) for plot briefs, district prices and storage summaries.

For a public website, see [Netlify + free backend deployment](docs/netlify-deployment.md). The root `netlify.toml` configures the frontend and `render.yaml` prepares the separate free Python/PostgreSQL demo backend. Cloud deployment requires account authorization and the real HTTPS backend URL; localhost Docker URLs cannot serve Netlify visitors.

On Vercel, import the repository with `apps/web` as the Root Directory and the Next.js preset. Set `NEXT_PUBLIC_DEPLOYMENT_TIER=frontend_preview` to publish the website preview before the API is available. For an API-backed deployment, remove that setting, set `NEXT_PUBLIC_API_URL` to the public HTTPS API URL ending in `/api/v1`, add the Vercel origin to the API's `CORS_ORIGINS`, and redeploy.

## KrishiMarket marketplace

Direct fixed-price shopping with optional MOQ, optional auction lots, nearby-first 20 km discovery and nationwide eligible fulfillment is implemented in the existing app. Farmer/customer signup and operator-provisioned admin roles are enforced server-side. Checkout is a clearly labelled prototype with unpaid cash-on-delivery/pickup records; no online payments are processed.

See [marketplace setup, roles, inventory rules and verification](docs/marketplace.md). Current local build: [English](http://127.0.0.1:3300/en/marketplace) / [Bangla](http://127.0.0.1:3300/bn/marketplace). Run additive Alembic migrations and the marketplace lifecycle worker for auction/order expiry; Compose includes the worker and preserves existing data/media volumes.

Marketplace listings now have matching, locally bundled illustrative photos for 20 crops when seller photos are absent or unusable. Normal seller photos take priority. [Photo sources and licenses](docs/crop-images.md) are available through the marketplace's photo credits link.

## AgroRescue harvest planner

Open [English](http://127.0.0.1:3300/en/agrorescue) or [Bangla](http://127.0.0.1:3300/bn/agrorescue). Compare proceeds after declared costs, answer missing-information questions, review saved weather/screening context, and save private decision snapshots. Holding scenarios use explicit farmer assumptions. This is an explainable symbolic planner, with no trained future-price or spoilage prediction and no automatic selling. See [usage, API and limits](docs/agrorescue.md).

For isolated browser QA, set `AGROSPHERE_NEXT_DIST_DIR=.next-rescue-e2e` and the matching `NEXT_PUBLIC_API_URL` on a separate web process/port. Point the test API at a separate database/storage and set `PLAYWRIGHT_BASE_URL`, `E2E_BASE_URL`, `AGROSPHERE_API_URL` and `E2E_API_URL` accordingly. The default build directory remains `.next`.

## Multi-crop screening

Set `GROQ_API_KEY` in the private root `.env` or API service environment, then restart the API. AgroDoctor sends a metadata-stripped photo to Groq's vision model for leaf and produce screening. It shows visible signs, possible causes, limitations and follow-up checks in the selected language. **Identify from photo** accepts crops outside the plot catalog as an unsaved preview. The model ID defaults to `qwen/qwen3.8-27b` and can be set with `GROQ_VISION_MODEL`. Provider or quota failures are shown in the form. Produce results describe visible damage such as surface mold or internal breakdown. A negative leaf assessment gets an independent check when a matching local leaf model with a healthy reference class is available. A disagreement or missing corroboration yields an uncertain result.

In AgroDoctor, select **Leaf** or **Fruit, vegetable or tuber** and answer the two observation questions. **Not sure** is available for each. The **আজ কী করব?** card adapts its scouting action to the photo and the reported extent, timing or storage context. **শুনুন** reads the card aloud with a local voice or bundled recordings. A second view can be submitted directly from a vision result or an existing saved vision case. Both images are analyzed together. Saved cases retain both views, the farmer's answers and the first assessment. Where further help is appropriate, a Bangla summary and a user-initiated **16123** call link are shown.

Without a Groq key, two pinned local research models support leaf screening for 12 crop groups: apple, cherry, maize, grape, orange, peach, bell pepper, potato, squash, strawberry, tomato and rice. Original three-class tomato artifacts and historical cases are preserved separately. See [multi-crop setup, sources and limitations](docs/agrodoctor-multicrop.md).

Install the active bundles from the repository root before running native inference or local Compose:

```powershell
.\.venv\Scripts\python -m pip install -r apps/api/requirements.txt
.\.venv\Scripts\python -m pip install -r apps/api/requirements-ml.txt --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python -m pip install -r ml/doctor/requirements-export.txt
.\.venv\Scripts\python scripts/install_doctor_models.py
```

Weights are downloaded from pinned SafeTensor revisions, verified and exported locally; no remote model code runs. Missing models are shown as unavailable. No independent multi-crop accuracy or field validation is claimed. The old `v0.1.0` tomato artifact alone does not enable multi-crop inference.

## Run locally (Windows, without Docker)

Sign up and sign in with a phone number or email and a password. Store a stable Fernet encryption key as `SIGNUP_DATA_KEY` in the private root `.env` for signup details and photos. Generate it once with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` after installing the API dependencies. The API, migrations and worker load private settings from the root `.env`; service environment variables take precedence.

From this directory, create a Python environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r apps/api/requirements.txt
cd apps/api
..\..\.venv\Scripts\python -m alembic upgrade head
..\..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd apps/web
npm ci
npm run dev
```

Open http://127.0.0.1:3000/en or /bn and choose **Explore a demo farm**. The initial session is private and expires in seven days. This is local demo authentication, not a production identity provider.

To choose your area, open **FloodCrop AI**, search a place or click/drag the map pin, then consent and press **Save area & use live weather**. The same picker is available when creating a farm. Manual coordinates work when search is unavailable. See [area selection](docs/area-selection.md).

The current checkout has its own `.venv` in this repository. Use `../../.venv/Scripts/python.exe` from `apps/api`. The implementation test/demo session uses API 8300 and web 3300 to keep older services separate.

## PostgreSQL / Docker

Start Docker Desktop first, then run `docker compose up -d --build` from this repository. It starts PostgreSQL, migrations, FastAPI with CPU model inference, and the Next.js standalone server. This checkout uses the Compose project name **agrosphere-congress**, separate from the older `agrosphere-ai` project on this PC.

- Website: http://127.0.0.1:3100
- API / interactive reference: http://127.0.0.1:8100/docs
- PostgreSQL (local tools): 127.0.0.1:55432

`WEB_PORT`, `API_PORT` and `DB_PORT` can override these defaults. Rebuild the web image after changing API_PORT because its browser-facing API address is set at build time. CORS includes the chosen local website origins. Ports bind only to localhost. Demo credentials are local development values; replace them for deployment. Images and PostgreSQL use separate persistent named volumes. Existing local SQLite records are not automatically migrated into the fresh PostgreSQL workspace.

```powershell
docker compose ps
docker compose logs --tail 50 api
docker compose stop
docker compose start
```

Stopping containers preserves records. Avoid `down -v` unless you intend to destroy the Docker database and image storage. The API and web containers run as non-root users. The first build downloads Linux dependencies and can take several minutes.

To repeat integration checks with the parent-directory environment used in this workspace:

```powershell
..\.venv\Scripts\python scripts/docker_verify.py
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:3100'
$env:AGROSPHERE_API_URL='http://127.0.0.1:8100/api/v1'
$env:E2E_API_URL=$env:AGROSPHERE_API_URL
cd apps/web
npm run test:e2e
```

`docker_verify.py` creates a disposable test workspace, tests actual model inference and all modules, restarts only this stack's API, verifies persisted records and device deduplication, then removes the disposable workspace.

For standalone PostgreSQL, set `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/agrosphere`, then run migrations and the API. The Python API, migrations and worker load the root `.env`; `.env.example` remains a reference file. Next.js reads its own frontend environment settings separately.

## Models and data

See [multi-crop setup](docs/agrodoctor-multicrop.md), [model cards](docs/model_card.md) and [original tomato training instructions](ml/doctor/README.md). The local leaf models have 38 PlantVillage outputs and 17 rice outputs; only disease-enabled crops are selectable. Selecting a crop does not renormalize the model scores. Cross-crop global predictions and scores below 0.85 abstain. Closed-set scores remain uncalibrated and unknown/non-leaf inputs can still score highly.

Runtime uses installed CPU torch/torchvision and checks bundle metadata, checksums and outputs. The 0.958 original tomato holdout accuracy belongs only to the retired three-class artifact, never to these upstream models. Rainfall thresholds remain illustrative; initial market prices are synthetic; official FFWC/DAM links are references.

## Quality gates

```powershell
# API directory, using your chosen virtual environment
python -m pytest -q
# Web directory
npm run typecheck
npm run lint
npm run test
npm run build
# Run API and frontend first; installed Microsoft Edge is used on Windows
npm run test:e2e
```

For Linux CI, `PLAYWRIGHT_CHANNEL=chromium` uses Playwright's installed Chromium instead of Edge. Production uses `npm run build` and the standalone server; the provided Dockerfile packages static assets alongside it.

API reference: http://127.0.0.1:8000/docs. All personal routes require a Bearer session token. Device ingestion uses a separate `X-Device-Key` header. See [hardware contract](docs/hardware_integration.md), [architecture](docs/architecture.md), [evidence](docs/evidence.md) and [status](docs/status.md).

## GitHub Actions template

The complete CI definition is supplied as [docs/ci-workflow.yml](docs/ci-workflow.yml). The current GitHub login can upload repositories and releases but lacks the additional `workflow` permission required to create active Actions files. No account permissions were changed. To enable CI later, use an authorized GitHub login, copy the template to `.github/workflows/ci.yml`, and explicitly add that file (it is currently ignored to keep uploads compatible with this login). Automated GitHub Actions execution is not claimed; the documented local and Docker checks have been run.
