## Public demo on Vercel · 25 November 2026

The hosted demo configuration requires PostgreSQL and creates private sample farms without password, registration, or verification-code requests. Delivery uses a standalone FastAPI project and the existing Next.js project. Uploaded images are temporary on the function runtime. The API regression suite passed 47 checks, the web suite passed 91, and the demo production build passed. Local desktop and mobile browser checks verified English and Bangla demo entry screens using a synthetic API response.

## Farmer Chat searches published guidance · 25 November 2026

Farmer Chat searches 12 bilingual guidance passages for crop scouting, storage, field drainage, soil moisture and regional crop calendars. It filters by crop, district or stage where applicable and can use a local multilingual E5 encoder to rerank matches. Groq receives the relevant passages alongside the existing farm evidence. Answers link to the passages cited by the model. If the answer is unavailable or fails citation checks, the chat can show the relevant published passage directly.

Live Groq returned linked guidance for tomato early blight and Septoria symptoms, potato late blight symptoms in Bangla, and sorting damaged potatoes. A real API request retained both tomato references when the conversation was reopened. A 390-pixel browser check showed the published passage and source link with Groq disabled, including after reload. The bundled library covers selected questions. Regional calendars are seasonal references and the chat's symptom comparisons require field confirmation. [Setup and verification](farmer-chat-rag.md)

The production build, 342 API tests, and 91 web unit tests passed. All Farmer Chat browser tests passed. The full browser suite passed 49 of 50 tests, with the existing private marketplace photo-gallery fixture failing at its loading-state assertion.

## FloodCrop forecast motion · 25 November 2026

The forecast-window selector now slides between 24, 48 and 72 hours. Valid outlooks show a decorative field scene, with a short rain animation when the selected window contains precipitation. Simulation and freshness labels appear next to the outlook. Reduced-motion users see still illustrations and an immediate selector change.

Verified rainy, dry, expired and unavailable states, reduced motion, and the Bangla layout at 390 pixels. The build and 326 API tests, 91 web unit tests, and 49 of 50 Playwright tests passed. The existing marketplace gallery fixture remains the only browser failure.

## Account and feature motion · 25 November 2026

The sign-in headline slides into view one phrase at a time in English and Bangla. Reduced-motion settings show both phrases immediately. The desktop English and 375-pixel Bangla browser check, the production build, 91 web unit tests, and 14 authentication API tests passed.

Sign-in and sign-up have a one-time farm photo reveal, a sliding mode indicator, a short form reveal and a pending indicator during submission. AgroDoctor's preview shows a scan effect while the assessment request runs. FloodCrop animates the loaded rainfall total and chart. KrishiMarket and AgroRescue reveal completed comparisons, and Farm tools reveal the selected panel. Visible data, labels and loading states remain available with reduced motion.

The account background is an illustration generated with ImageGen and bundled as `apps/web/public/account-farm-morning.webp`.

> Photorealistic editorial photograph for the left panel of a Bangladeshi agricultural web app's sign-in screen. Portrait 4:5 framing. A lush, smallholder vegetable farm in Bangladesh, with repeated crop rows in rich deep greens and low morning mist in the distance. A single Bangladeshi grower with a simple light shirt and woven field hat is checking the plants in the lower-right third, viewed from behind at a natural distance. Dim and unobtrusive upper-left and central-left areas so white interface text can sit above it. Soft warm light in upper-right, balanced, cinematic, credible agriculture, premium magazine photography, natural green palette, no text, typography, icons, marks or branding. Keep essential agricultural detail readable when cropped to a short landscape panel on mobile.

Verified the desktop sign-in and Bangla sign-up at 375 pixels. A local screening exercised the pending scan effect, its static reduced-motion state and the completed result. The production build, 326 API tests, 91 web unit tests and 48 of 49 Playwright tests passed. The existing private marketplace gallery fixture remains the only browser failure.

## Local MCP and farm-to-market animation · 25 November 2026

The optional local MCP server provides read-only plot discovery, plot briefs, district price summaries and storage balances via stdio. It reuses the AgroSphere API for authentication and ownership. The client receives selected fields together with relevant source and freshness data. A real MCP session exercised all four tools, rejected cross-account and missing-token private reads, accepted Bangla district and crop names, and confirmed saved records were unchanged. A remote MCP endpoint requires its own deployment and authorization setup.

The farmer dashboard shows a produce truck with potato or tomato crates when the selected plot matches. The truck moves once when the scene comes into view. The still scene is used with reduced motion. The bilingual card links to the existing KrishiMarket price page.

The API suite passed 326 tests, the web unit suite passed 91 tests, and the production build passed. The full browser run passed 46 of 47 tests. The existing private marketplace gallery fixture remains the only failure. A focused rerun on the final build verified the truck animation, the Bangla phone layout and the reduced-motion setting.

## Farm tools and Bangla dictation · 25 November 2026

The farmer workspace now includes a stage-based potato and tomato calendar, due reminders and evidence-based scouting and drainage alerts. The plot cash ledger records cash received and farming expenses in BDT. It also calculates the break-even price for a user-entered saleable weight. Storage batches retain harvest and storage dates, inspections, recorded losses and withdrawals. Balances use validated decimal quantities.

Farmer Chat supports Bangla and English dictation with an editable draft. Reply playback uses an installed matching voice. Browser speech services and device language support determine availability. In-app alerts use saved evidence and are visible when the app is open. Official flood warnings still come from FFWC.

The community map shows district and crop bands only after three distinct eligible farmers share recent screenings. Reporters can withdraw consent. Deleting a shared screening removes its report. The map describes community observations and has no independent verification feed. The offline notebook saves a read-only, encrypted copy on the current device. The service worker caches only its public assets and does not save API responses.

The full API suite passed 326 tests. Final focused API checks also passed, including stale forecast suppression and report withdrawal. All 91 web unit tests, TypeScript and the production build passed. Browser checks exercised real network-offline readback, simulated Bangla speech recognition and all five Bangla panels at 375 pixels. The full browser run passed 44 of 46. The mobile chat test passed five consecutive runs after its viewport assertion was updated to wait for the plot to load. The existing private marketplace gallery fixture still fails at the farmer role check. This release has no measured Bangla transcription accuracy or field validation of the scouting prompts.

## FloodCrop rainfall outlook · 20 November 2026

FloodCrop now sums complete hourly intervals inside the selected 24-, 48- or 72-hour window. Open-Meteo labels precipitation by the end of each hour. Counting the hour before the window could change the preparation advice. Each outlook expires at the end of its selected window. A missing reading in that window produces a retryable error. [Open-Meteo hourly definitions](https://open-meteo.com/en/docs#hourly_parameter_definition)

Live weather uses the selected farm's consented coordinates. Moving a plot or changing its waterlogging history clears old advice and discards an outdated refresh already in progress. Viewing simulated rain preserves the saved live outlook and its Action Center record. The page guides new farmers to set up a plot, labels simulated rain, and offers a retry during outages. The preparation threshold is illustrative. Official river warnings are available through the [Bangladesh Flood Forecasting and Warning Centre](https://www.ffwc.gov.bd/).

A browser check using public Dhaka coordinates showed 29.5 mm over 24 hours, 57.1 mm over 48 hours and 60 mm over 72 hours. All three totals matched independent sums of the provider's hourly values at the time of the test. The test switched to simulated rain, checked the saved live evidence and verified that changing the plot's waterlogging history cleared the earlier advice. The temporary account was removed.

All 322 API tests and 91 web unit tests passed. The full browser run passed 43 of 44 tests, including all FloodCrop checks. The previously documented marketplace photo gallery test still failed at the farmer role check.

## AgroDoctor photo screening reliability · 20 November 2026

The plot form shows a loading message while fetching farms and a retry button on failure. A farmer with no farms can create one by entering its name and district in AgroDoctor. The new farm is selected for plot creation. An isolated browser test covered a failed fetch, recovery, first farm creation and saving a potato plot.

The disease identifier offers potato and tomato. The online assessment describes visible damage, including foliage and harvested produce. For eight recognizable disease or disorder patterns it can also show a bilingual field check and an extension reference. These checks require compatible visible features, crop and plant part. The local leaf model retains its existing trained classes.

The supplied potato field photo passed image-quality checks. The center crop ranked a tomato late-blight reference first. The full frame ranked a potato early-blight reference first. The offline result now explains that disagreement and asks for another view. The model withholds the disease label. A live Groq upload of the same image in English and Bangla described brown collapsed leaflets and a dark stem lesion. The app showed late blight as a possible explanation and requested an underside photo at the edge of a fresh lesion. A mobile browser upload reproduced the finding. A separate tomato fruit photo returned possible mold-associated decay. These are functional examples. Field accuracy has not been measured. [University of Minnesota Extension guide to late blight](https://extension.umn.edu/agriculture/specialty-crops/vegetable-farming/disease-management/late-blight)

The API makes one bounded retry for a transient connection, service or response-format failure. A live rate limit returned a retry interval. A confirmed leaf can use the installed local classifier when online screening is unavailable. Auto-detection keeps the image available for retry and lets the farmer confirm it is a leaf. Produce and two-photo assessments require the vision service. Configure `GROQ_API_KEY` on the API server for online analysis.

Verification passed 298 API tests, 91 web unit tests, all AgroDoctor browser tests, TypeScript and the production build. The full browser suite passed 40 of 41 tests. The remaining marketplace-gallery test also failed on unmodified upstream commit `67211fd` because its signed-in farmer fixture could not reach the customer-only gallery. Lint reported nine existing warnings and zero errors.

## Seller order details and potato screening · 19 November 2026

Seller Studio shows the three most recent orders and links to the full history. New pickup orders snapshot the customer’s area and district separately from the farm pickup area. Older pickup orders have no stored customer area. Farmer navigation includes a direct call to the [Bangladesh Agriculture Call Centre](https://ais.gov.bd/pages/static-pages/6922df5e933eb65569e21833).

Two local potato screenings of the same uploaded image passed image quality checks and produced the same crop mismatch. The highest class was tomato late blight at 0.547. The highest potato class scored 0.0074. These are uncalibrated model outputs. The result and the action card now explain the mismatch. The field photo’s disease has no confirmed label.

## Password signup and marketplace access · 19 November 2026

The home and marketplace forms accept a phone number or email and a password. Signup stores the chosen farmer or customer role with the private profile. Farmers publish listings and fulfill orders. Customers browse published listings and place orders. The existing NID, phone, and private photo checks apply at signup. A stable `SIGNUP_DATA_KEY` is required for private profile storage. Contact ownership is not checked during password signup.

## KrishiMarket district prices · 19 November 2026

The seller listing form shows 30 days of KrishiMarket prices for the chosen crop, listing district and unit in Bangla and English. Each figure needs three observations. The card shows separate counts for current eligible asking prices and seller-confirmed orders, and links to the Department of Agricultural Marketing's official reports. Grams convert to kilograms. Pieces, bundles and crates have their own figures. Each checkout contributes at most one agreed price per crop, district and comparable unit. A later edit to the listing leaves the order price intact. [Official market reports](https://market.dam.gov.bd/market_daily_price_report)

Asking prices represent listings. Agreed prices represent order terms, with payment tracking still in demo mode. Demo accounts, test accounts and records with unknown provenance are excluded. An older listing needs a dated publication or price observation. An older order needs a known crop, origin and recorded confirmation. The board can therefore be empty even when the marketplace has activity.

Farmer Chat uses the same database calculation. In an isolated browser and API check, three confirmed tomato orders in Natore yielded a median of BDT 42/kg. Changing their current listings to BDT 50, 52 and 54 yielded an asking median of BDT 52/kg. The chat placed a BDT 40/kg offer BDT 2 below the agreed median and calculated BDT 3,400 before other costs for 100 kg and BDT 600 transport. The figures came from the isolated test database.

Local verification passed 252 API tests, 90 web unit tests, 42 browser tests, TypeScript and the production build. Lint reported nine existing warnings and zero errors. The running local app also returned the empty Gazipur board in both languages and calculated the transport follow-up. Migration 0008 passed on the existing SQLite database, with a backup and matching table counts. PostgreSQL was not exercised end to end.

## Farmer guidance and two-photo cases · 19 November 2026

The Bangla and English upload forms collect when leaf symptoms first appeared or where produce damage was first noticed, plus how many plants or items are affected. Skipped answers remain unknown. Farmer observations are stored with the case and used to select scouting actions separately from Groq's visual findings. One affected item and many affected items in the same stored batch lead to different primary actions. The advice card supports local speech and bundled Bengali and English recordings. Uncertain results or reported damage affecting multiple plants or items show a Bangla adviser summary and a tap-to-dial link for 16123. A farmer initiates the call and decides what to share. [Bangladesh Agriculture Information Service](https://ais.gov.bd/pages/static-pages/6922df5e933eb65569e21833)

A follow-up on a saved Groq case retains its original assessment and photos, and updates the same plot case and linked action. An unsaved preview can also be reviewed with two views. The backend removes metadata and combines both views into one ordered image before requesting a new assessment. Case ownership, retry behavior, conflicting attachments, failed saves and erasure have API regression coverage. Provider quotas can require waiting before retrying.

Live verification used a temporary demo plot, a potato reference photo, and a close-up cropped from that photograph. On the 390-pixel Bangla page, the app recorded storage and many affected items, displayed a Bangla call summary, played and stopped Bengali audio without an installed Bengali voice, and reopened both views and the first assessment in one case. No adviser was contacted. The test account and saved photos were removed after verification. [University of Minnesota potato reference](https://apps.extension.umn.edu/garden/diagnose/plant/vegetable/potato/tuberwhitefuzz.html)

The actions support observation and referral. The tomato early-blight template uses extension guidance for a matching crop and visible ring pattern. Individual advice, translations and audio pronunciation have not received an independent local agronomist or native-speaker review. [University of Minnesota Extension scouting guide](https://extension.umn.edu/agriculture/specialty-crops/diagnostic-help-for-fruit-and-vegetable-farmers)

The checkout passed 174 API tests, 90 web unit tests, 37 browser tests, TypeScript and the production build. Lint reported nine existing warnings and no errors.

## AgroDoctor photo screening · 19 November 2026

The local app uses Groq's Qwen vision model for leaves and produce. The API key stays on the API server. Photos are re-encoded before transmission. The upload form explains the external processing. The API saves signs, explanations, model identity and follow-up checks in the owner's existing case history. Choosing **Identify from photo** runs an unsaved preview. A mismatched crop stays out of the selected plot's history.

Live browser checks used ordinary image uploads with neutral filenames and no disease captions. Purdue early blight figure 1 returned possible early blight. The gray mold fruit in figure 4 returned possible mold-associated decay. Early blight figure 9 remained unresolved: Groq missed the lesion and the local leaf classifier flagged damage. The app asked for a close-up. The potato from Minnesota Extension returned possible internal decay in automatic crop mode. The three plot observations were reopened and the test account was removed. Sources are [Purdue's tomato disease photos](https://ag.purdue.edu/department/arge/swpap/tomato-diseases.html) and [Minnesota Extension's potato tuber gallery](https://apps.extension.umn.edu/garden/diagnose/plant/vegetable/potato/tuberwhitefuzz.html).

Earlier trials overidentified a leaf spot and the cause of potato decay. Leaf labels require a described distinguishing feature. If the vision model sees no damage on a leaf, a matching local model with a healthy reference class must corroborate the negative result. Produce labels describe visually identifiable damage categories. These four examples exercise the demo flow. Field accuracy, food safety, firmness and organism identity cannot be established from these checks. Groq rate limits also apply: the demo displayed a retry interval when the free-tier allowance was reached.

Verification passed with 157 API tests, 74 web unit tests, 35 browser tests, TypeScript and the production build. Lint reported nine warnings and zero errors. The live image checks above used the local app and the actual Groq service.

# Account sign-in and registration — 19 November 2026

New signup also collects a national ID number, present and permanent addresses, ward, gender, a portrait photo, and a confirmed password. Government ID numbers are checked for format. OTP verifies the phone or email. The service does not query a government identity registry. Passwords are hashed. The ID, addresses, ward, and re-encoded photo are encrypted before their database writes. Account exports and photo access are restricted to the signed-in owner, and account erasure removes the private signup record.

Set a stable Fernet key as `SIGNUP_DATA_KEY` in the API service environment before enabling signup. Generate one using `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` in a private terminal and store the output as a secret. Retain the key securely across deployments so existing signup records can still be read. New accounts can use password or OTP sign-in. The signup update passed 130 API tests, 74 frontend unit tests, a production build, and the focused signup and greeting browser test.


The locale home opens with sign-in. New accounts verify a phone number or email and supply a name, age, and role. Farmer accounts can sell, buy, and use AgroDoctor. Customer accounts can buy and use shared features. Existing sellers with listings are carried forward as farmers when the new account schema is applied. Existing password accounts and provisioned admins continue to sign in through the password option.

The account form requires the full Bangladesh mobile number, with exactly 14 characters including the leading `+` and the `880` country code. The national ID field accepts exactly 10, 13, or 17 digits. Both checks run in the browser and the authentication API. English and Bangla numerals are accepted and stored in the same digit format. Email sign-in is also available.

Real OTP delivery requires a configured Twilio Verify service. SMS routes through Twilio Verify and email requires its SendGrid integration. Set `TWILIO_VERIFY_SERVICE_SID`, `TWILIO_API_KEY_SID`, and `TWILIO_API_KEY_SECRET` on the FastAPI service. On Render, set these in the API service's Environment settings and redeploy the API. Configure SMS for the destination countries and an authenticated SendGrid sender for email. Keep these values out of Netlify and GitHub. Runtime demo sign-in defaults to enabled locally and disabled on the hosted service. Legacy password registration is disabled by default and remains available to browser/automation fixtures via `ENABLE_LEGACY_PASSWORD_SIGNUP=1` in an isolated environment.

Verification passed locally with 129 API tests, 74 frontend unit tests, a production build, and all 30 browser tests. OTP flows used a simulated provider for verification. Live delivery is pending provider credentials.

# Crop-first AgroDoctor screening — 18 November 2026

AgroDoctor can screen a leaf photo after the user selects any of the 12 catalog crops. With a matching selected plot, the app saves the observation and adds it to plot history. Otherwise, the app shows a preview without writing a photo, case, or action. The API returns a validation error for corrupt photos, including PNG checksum failures.

Both pinned model bundles were installed and verified in this checkout. Live HTTP screening used one sample leaf photo for each listed crop. Eleven returned a possible condition and the tomato sample returned a low-confidence result. Live browser screening also returned possible early blight for potato and possible bacterial blight for rice through the preview flow. These smoke checks exercise inference and the UI. Field accuracy still requires independent evaluation.

Verification included 126 API tests, 74 web unit tests, TypeScript, and a production build. Lint reported zero errors and nine warnings. All seven AgroDoctor browser checks and both area checks passed on the final retest. The wider browser run surfaced two marketplace tests that encountered duplicate “Fresh from the farm.” headings. The updated app was served locally on web port 3400 and API port 8400.

---

# AgroRescue and marketplace photos — 17 November 2026

AgroRescue is implemented in the existing workspace at `/en/agrorescue` and `/bn/agrorescue`, with a farmer marketplace navigation link. It compares up to six selling options with Decimal money, asks for missing transport costs (including break-even thresholds), checks readiness, distinguishes entered/sourced/simulated quotes, and shows owned weather/screening context. Optional holding calculations require explicit assumptions and total holding/later-selling costs. Saved private plans integrate with history, action center, export and deletion. No automatic transaction or trained price/spoilage forecast is claimed. See [usage and limits](agrorescue.md).

Twenty licensed local crop photographs now provide matching EN/BN illustrative fallbacks. Normal seller uploads take priority; absent, broken or unusably tiny uploads fall back without changing uploaded data. Unknown/mixed crops remain neutral. Credits are accessible from the marketplace. See [photo sources and licenses](crop-images.md).

Fresh final checks: **125 API tests, 74 web unit tests and all 28 browser tests passed**. Typecheck and production build passed. ESLint: 0 errors / 9 earlier warnings; new planner/photo modules pass scoped lint without warnings. Full browser verification used separate web/API ports 3400/8400 and an isolated database/storage, then these QA servers were stopped. Final live visual checks: no page errors, no Bengali mobile overflow, and three existing tiny-upload tomato listings loaded `/crops/tomato.jpg` successfully.

Independent review caught and verified fixes for saved `BDT/kg` quotes, missing farm-gate/retail choices, stale quote confirmations, and an existing MapLibre worker initialization defect. The map now uses the installed `setWorkerUrl` API; area selection and canvas clicks pass. Failed live weather refreshes are retained as warnings on cached weather, with no DEMO substitution. Plans invalidate on input edits/plot changes; delayed responses cannot restore stale results. Hold-cost scope, source dates and cent/fractional quantity rounding have regression coverage.

Updated app remains on 3300/API 8300 with its prior database/media and lifecycle worker; SQLite backups were made before API restarts. Original 3000/8000 services and previous working-tree changes were preserved. No commit, push or cloud deployment. Field/economic/food-safety validation, trained forecasting, expert Bangla review and production/cloud/security/load review remain unperformed. Historical status sections below refer to earlier stages.

---

# Marketplace implementation status — 17 November 2026

The requested integrated KrishiMarket marketplace is implemented locally: three backend-enforced roles, fixed-price checkout without bidding, optional MOQ, separate auction reservations, 20 km nearby-first nationwide discovery, safe product media, seller fulfillment, customer tools and admin moderation/policies/audit. Prototype cash records are not real online payments. See [marketplace guide](marketplace.md).

Fresh verification: 80 API tests, 18 web unit tests and 17 browser tests passed; typecheck/build passed; lint 0 errors / 9 existing warnings. Independent review fixes verified. Real admin browser actions passed. Original/crop model hashes are unchanged; the existing market comparison duplication is now corrected and the connected journey passes. Additive migration 0004 and photo/listing persistence across native API restart were verified. Docker is unavailable; container/cloud execution is not claimed.

The app is running on 3300 with API 8300 and a separate expiry worker. Existing original 3000/8000 services and project data were preserved. New registration has local password authentication; identity verification/payment/courier/security/load/accessibility/complete translation review remain production work. Earlier status sections below are historical and their old full-E2E failure is superseded by the checks above.

---

# Current implementation status — 17 November 2026

## AgroDoctor multi-crop update

The approved multi-crop design is implemented locally in this checkout. Active inference now uses two pinned upstream bundles for 12 disease-enabled crop groups. This is genuine local model inference; it is research screening with no independent multi-crop accuracy or field validation. Original tomato artifacts and historical case snapshots are preserved.

- 46 API tests passed, including crop/plot ownership and mismatch, source pinning, corrupt/missing models, single-flight initialization, preprocessing controls, EXIF/transparency/animation and failed-save cleanup.
- 18 frontend unit tests, TypeScript and production build passed. ESLint: 0 errors, 9 warnings (existing navigation/config warnings plus native private/blob image warnings).
- 6 AgroDoctor browser regressions passed: selector/createplot, stale upload/drop/context, older history and plot isolation, private-photo/notes/missing-image detail, unavailable model and delayed plot creation. Initial plot loading now disables photo controls to prevent losing a selection during context initialization. Actual desktop rice inference and 390px Bengali layout inspected; no page errors or horizontal page overflow.
- HTTP smoke tests used one potato, one maize and one rice image, a wrong-crop control, noise and a flat image. Results are in the multi-crop verification handoff, with sources and limitations. They are not an accuracy estimate or proof of unseen-data generalization.
- Independent code review found 3 issues (container path resolution, active-model readiness, delayed plot-create selection); all 3 were reproduced and fixed with regression checks.
- Full connected browser suite still has the pre-existing market/action-center journey failure. Area/manual-coordinate and Bengali journeys pass. The map worker remains an earlier audit item; a passing canvas interaction test does not prove map tiles/worker correctness.
- Docker executable is unavailable in this environment, so updated Compose/hosted Docker configuration is unbuilt here. No cloud deployment, free-tier resource fit or production migration success is claimed.

Current isolated local sessions: frontend http://127.0.0.1:3300/en/agrodoctor and API http://127.0.0.1:8300/docs. Older original checkout services on 3000/8000 were left intact.

See [multi-crop setup and limitations](agrodoctor-multicrop.md). Secondary copy and raw condition names remain partly English; expert agronomic/translation review, genuine field evaluation, calibrated uncertainty and robust OOD detection remain future work. This scoped change does not close the full earlier project audit backlog.

## Historical status recorded before this update

The following earlier claims are retained as history. They are not fresh verification of this checkout or the new upstream models.

# Current implementation status

Last updated: 2026-11-17, Asia/Dhaka (audit remediation in progress on branch `fix/audit-remediation`).

**Honest summary:** local software corrections for the audit backlog are substantially implemented and gated by isolated API/unit/build checks; this is **not** field-validated, competition-submitted, or live-cloud proven. See `docs/audit-remediation.md`, `docs/audit-verification.md`, and `docs/audit-handoff.md`.

| Area | State | Evidence / remaining work |
|---|---|---|
| Premium frontend | DONE for demo | Patched Next.js production image builds on Linux; desktop and 360px Bengali browser journeys pass against Docker |
| Backend / local persistence | DONE for demo | FastAPI + SQLAlchemy, 12 integration tests passed locally and against PostgreSQL |
| Farm area selection | DONE | Worldwide place search, clickable/draggable map pin and manual coordinates on FloodCrop and farm creation. Explicit save consent, persisted location, automatic live-weather refresh and forecast invalidation. Browser tests cover saved search, reload/map clicks and mobile offline fallback |
| PostgreSQL / containers | DONE for local prototype | Isolated agrosphere-congress stack runs on 3100/8100/55432. All containers healthy; Alembic reports no drift; 10 backend tests pass against a separate PostgreSQL test database. Cases, private images, sessions and device readings survive API restart |
| AgroDoctor workflow | DONE for demo | Private upload, validation, quality checks, uncertainty, history, feedback, CSV export/delete tested |
| Real disease classifier | DONE for controlled-image research prototype | 570 leaf-grouped images, 360/90/120 split. Holdout accuracy 95.8%, macro-F1 0.958; exported model parity and real HTTP upload checked. No field validation |
| FloodCrop | DONE for scenario and live weather / PARTIAL official feeds | Live Open-Meteo request returned HTTP 200 with non-simulated provenance. No authorized official flood feed |
| KrishiMarket | DONE for prototype | Atomic private CSV validation/dedup, explicit costs, decimal proceeds comparisons, watch storage. No forecasting or automatic watch delivery |
| Action Center | DONE for demo | Plot-scoped actions update from all three modules; latest desktop/mobile browser regression passed |
| Localization | PARTIAL | English/Bangla navigation, main headings and flagship upload flow. Secondary/help text remains English; no agronomic translation review |
| Hardware contract | DONE for virtual test | Auth, validation, deduplication, persistence and status UI tested; no physical hardware |
| Production security / advisor service | NOT IMPLEMENTED | Local demo sessions only; no independent security review, external advisor delivery or deployment |
| Documentation | DONE for current prototype | Installation, architecture, privacy, sources, model card, hardware, OpenAPI, evidence and demo runbook supplied |
| Netlify + free cloud hosting | PREPARED / ACCOUNT ACCESS PENDING | Netlify monorepo config and free Render blueprint supplied; Netlify-mode build, deployment preflight tests, cloud image/model checksum and memory-limited inference verified locally. No live cloud deployment is claimed; Netlify authorization and Render connection are still required |

Final local checks passed: API tests, frontend unit tests/typecheck/lint/build, desktop/mobile browser journeys, exported-model holdout parity, actual HTTP image inference, live weather connectivity and Alembic upgrade/schema consistency. Docker follow-up verified actual Linux inference, PostgreSQL integration tests and restart persistence. Patched MapLibre and Vitest and pinned the linter's minimatch dependency; npm audit now reports zero known advisories. Advanced field robustness, recent observed rain, market forecasting and full translation are not claimed. The application is functional as a local research prototype, not a fully validated production agricultural service.
# SMS setup and local persistence — 19 November 2026

This checkout runs on web 3000/API 8000 with SQLite at `apps/api/agrosphere.db`. There are 24 tables including Alembic tracking, revision `0006`. Read-only integrity and foreign-key checks passed, and saved row counts matched the pre-restart backup after restarting the API. Marketplace and other modules share SQLAlchemy's database; private images remain in storage. PostgreSQL is supported but is not running in this native local setup. This check is not a production database/security/load audit.

The disabled verification action was caused by missing delivery credentials and missing signup encryption configuration, not the valid phone-number format in the reported screenshot. The API, migrations and worker now load root `.env` settings without overriding service environment variables. Tests explicitly disable local dotenv loading to avoid using real credentials. The OTP start route returns 503 for an unconfigured provider before its account-enumeration protection path, rather than issuing a pretend successful start. English/Bangla forms explain an unavailable service beside the disabled action.

Both API-key credentials and Account SID/Auth Token credentials are supported. A live authenticated Twilio service lookup passed, an AgroSphere AI Verify service was created, and the private settings were saved in ignored `.env`. The server now reports OTP/signup enabled and the browser displays an enabled send-code action. A stable private-data encryption key was prepared without replacing existing keys. See [SMS setup](sms-setup.md) for the private setup/check commands.

**Handset delivery has not been tested.** The connected Twilio account reports Trial status, and its recipient lookup returned no verified numbers. The operator must verify an eligible trial recipient and check Bangladesh Verify Geo Permissions in Twilio Console before requesting a code. No SMS, real signup, paid account upgrade or payment was performed. Email additionally requires its own provider integration. No credentials are included in this report.

Fresh verification: 136 API tests, 74 frontend unit tests and 32 isolated browser tests passed; TypeScript and production build passed. Lint reported 0 errors and 9 existing warnings. OTP send/verify browser regression tests simulate the provider boundary; they do not establish live SMS receipt. Browser tests used a separate SQLite database/storage, preserving the user's existing workspace. The API suite's single warning concerns deprecated TorchScript loading.

# Email verification paused for demo — 19 November 2026

At the user's explicit request, stop the Gmail setup and use **Explore a demo farm**. Email and SMS delivery are disabled in the current local configuration; no Gmail App Password was stored and no email was sent. The SMTP implementation is an unfinished draft, not a completed authentication feature. Resume from `work/gmail-auth/progress.md`, including the independent review findings, before any later activation. Do not interpret earlier SMTP test/build results as live mailbox delivery. Demo farm access and its persistent database remain available.


## Farmer chat — 19 November 2026

Signed-in farmers can open Farmer chat from the lower-right sprout icon, or select “Ask about this screening” in AgroDoctor. Saved cases use their own plot and private screening records. An unsaved preview fills an editable question. Farmer conversations and confirmed case notes use the existing SQL database. New chats have separate histories. Removing a case or plot also removes its associated conversations.

The backend uses the existing private Groq configuration for language understanding and conversation. It can answer in Bangla or English, including questions written in Banglish. A second Groq-hosted text model handles some provider capacity errors. When model service is unavailable, the interface identifies replies limited to available evidence. Buyer comparisons use decimal arithmetic, and storage instructions use crop-specific source material. A farmer chooses whether to save an observation or use an editable adviser summary. Additional counts stay in the farmer's words.

Bangladesh Agro-Meteorological Information Service bulletins carry issue dates and coverage periods. Regional crop calendar PDFs are season references. Open-Meteo requires consented farm coordinates. Price lookup supports the farmer's recorded commodity, date, trade type and market. DAM's public report requires a selected market, date and trade type, so the assistant links the official report when a matching daily price cannot be verified. Photo screening and conversational smoke tests do not establish field accuracy.

Verification covered 230 API tests, 90 frontend unit tests, 40 Edge browser tests, TypeScript, and the production web build. All 53 chat-specific API tests also passed after tightening observation detection. Lint reported nine existing warnings. Live browser checks used disposable farm accounts, a tomato leaf and a cut potato. Additional checks exercised a second potato photo, a Bengali case note and editable adviser summary, a dated Gazipur bulletin, a regional calendar, and a buyer comparison recalculated after a fare change. The provider rate-limited one follow-up photo request; a later retry succeeded.


## Tomato and potato leaf screening

For a low-confidence tomato or potato disease candidate, the local classifier checks a full-frame view for damage that the standard center crop can omit. The full-frame result must independently meet the existing screening threshold and agree with the original candidate. An uncertain result shows symptom comparisons and management steps on the result card. These changes were exercised with controlled model outputs and browser fixtures. Field accuracy and the original uploaded photos remain unverified.

The AgroDoctor upload dropdown offers tomato and potato. When a different plot crop is active, the form defaults to a tomato preview and requires a matching plot to save the result. The API crop catalog still describes the underlying models.

### Additional potato leaf checks

Potato leaf results now include English and Bangla field checks for leafroll, virus-like mosaic, and blackleg. Groq Vision, when configured, receives potato-specific instructions for the same patterns. Curling alone cannot confirm leafroll, mosaic cannot distinguish PVY from PVX, and suspected blackleg needs a stem-base view. The offline classifier still supports healthy, early blight, and late blight labels.

The CC BY 4.0 [Banu and Deb field-photo archive](https://data.mendeley.com/datasets/d5b3fzpw3g/1) (version 1, SHA-256 `549c7f3343422fa2b77b6fb2c5009a52215aa00626b2646435ba19f4826f8192`) contains 84 files named `orig_*` and 2,267 named `aug_*`. The augmented filenames do not identify a source leaf. An exploratory offline check excluded all augmented files and skipped 12 byte-for-byte duplicates. The current classifier abstained on all 72 retained photos (69 crop mismatches and 3 low-confidence results), including 20 late blight and 4 healthy images. The archive contains no early blight class. No weights were trained or changed, and this small single-source check does not establish field accuracy.

### Marketplace role separation

Marketplace buying tools are for customer accounts and selling tools are for farmer accounts. The UI gates buyer routes and the API checks the stored role for cart, checkout, bids, award confirmation, and customer tools. Earlier orders remain accessible to their participants. Active auction bids from farmer accounts are ineligible, and an ineligible unconfirmed award releases the reserved stock. Browser testing uses separate local storage and a disposable SQLite database with test signup enabled.
