# AgroSphere farm tools

The November 25 baseline is AI-BUILDERS- commit `f99dae7`. The app already has private farm and plot records, a Groq-based chat, Open-Meteo rainfall, screening cases, marketplace comparisons and in-app notifications. The seven proposed workflows extend those features in the existing Next.js and FastAPI app. A separate application would duplicate logins and records. New hosted AI and messaging services would increase costs and operational requirements, so this release uses existing services and browser capabilities.

| Feature | Design and dependencies | Release check |
|---|---|---|
| Bangla voice assistant | Add a microphone to Farmer Chat. Dictate in `bn-BD` or `en-BD`, review the transcript before submitting, and read replies using a matching installed voice. Keep typed chat available. Browser speech services can process audio remotely. | Test start, results, edit, cancellation and denial with a simulated browser recognizer. Check device support separately. |
| Advisory calendar | Plan weekly tasks from declared crop stage, optional planting date and district. Start with tomato and potato. Link to BAMIS, selecting the regional reference where the mapping is verified. Mark future weeks as tentative and require a grower to confirm stage changes. | Test both crops, district fallback and missing or invalid planting dates. Review content with DAE before extending it into growing instructions. |
| Smart alerts | Combine due farmer reminders with explainable notices based on fresh live FloodCrop results and recent saved AgroDoctor observations with compatible evidence. Use date and evidence identifiers to group notices. Store acknowledgement privately. | Test silencing, expiry, duplicate delivery, failed or simulated forecasts, and stale cases. This phase offers in-app delivery when the farmer opens or refreshes the farm workspace. Push and scheduled provider refresh require separately operated infrastructure. |
| Expense and profit tracker | Record dated expenses and actual receipts in BDT, with category and optional sale weight. Sum using decimal arithmetic. Share the plot context with KrishiMarket and display a transparent break-even price for a hypothetical quantity. | Verify decimal totals, empty records, refunds or corrections via explicit deletion, and cross-account restrictions. Keep projections and recorded cash margin separate. |
| Offline PWA | Serve an installable offline notebook with service-worker-cached public files. Explicitly save a read-only snapshot of selected farm records and advice, encrypted with a device passphrase. Strip precise locations, image files, authentication tokens, and private account fields. Show snapshot time and a delete control. | Test offline reload, password failure, deletion, invalid sessions, and no authenticated response caching. |
| Community crop report map | Share a saved screening only with explicit consent. Publish district/crop aggregates from at least three distinct eligible accounts, using count bands, and allow withdrawal. Use licensed Bangladesh district boundaries. Display screening reports as unverified field observations. Expert verification requires an extension workflow and evidence from outside this release. | Test sparse data, demo exclusion, duplicate accounts, consent withdrawal, case deletion, and absence of farm-level fields. |
| Post-harvest storage tracker | Record a harvested batch in kg, harvest/store dates and storage method. Add dated inspections, losses, and removals. Prevent overdraw and show remaining stock and loss percentage. Record sales separately in the ledger when payment is received. | Test transactional stock limits, precision, corrections, chronology, and private ownership. |

## Build order

1. Add typed, private plot workflows and rules to FastAPI. Use existing owner, farm and plot identifiers and database transactions. Cover record caps, date and number validation, export and deletion.
2. Add a bilingual Farm tools workspace with calendar and alerts, ledger, storage, community reports, and offline notebook. Add dictation to the existing chatbot and link the ledger from KrishiMarket.
3. Bundle the attributed community map and offline assets. Verify desktop and mobile workflows with isolated data and inspect real service status independently of automated fixtures.
4. Run the API and web suites, type checks, production build and Playwright. Record actual results and limits in `docs/status.md`. Review the migrated experience on Netlify and the API host before a public rollout.

## Public rollout and follow-up

- Deploy the API before the frontend because the new pages depend on `/api/v1/farm-tools`. Use the existing database and check that a test farmer can export and delete the new records. Deploy the frontend on HTTPS and test install and offline reopening on an Android phone and an iPhone.
- Review Bangla prompts and voice transcriptions with farmers on their own devices. Keep a small shared set of example utterances, including regional pronunciation and crop names. Track correction rates before adopting a hosted transcription fallback.
- Ask an extension adviser to review the potato and tomato checklist by stage and district. Expand to another crop or region only after its source, coverage and translation have been verified. Recheck the source dates at the start of each growing season.
- To deliver alerts while the app is closed, add a scheduler with bounded weather refreshes, explicit subscriptions, quiet hours and expiry. Keep the tested in-app panel available for users who opt out or lose network access.
- Before adding verified disease layers, define the reviewing organization's evidence standard and withdrawal policy. Publish a verified label only from an authorized review and continue to hide observations that fall below the minimum district count.

## Sources

- [Bangladesh Agro-Meteorological Information Service crop weather calendars](https://www.bamis.gov.bd/en/calendar/)
- [Open-Meteo weather API](https://open-meteo.com/en/docs)
- [Bangladesh Flood Forecasting and Warning Centre](https://www.ffwc.gov.bd/)
- [geoBoundaries BGD ADM2 metadata with BBS and OCHA attribution](https://www.geoboundaries.org/api/current/gbOpen/BGD/ADM2/)
- [Web Speech API recognition support](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
- [Service worker lifecycle and cache behavior](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers)

The community map bundles simplified, projected paths for all 64 Bangladesh districts. The original boundary source is Bangladesh Bureau of Statistics and OCHA ROAP, distributed by geoBoundaries under CC BY 3.0 IGO. To reproduce the derived paths, download the simplified BGD ADM2 GeoJSON from geoBoundaries revision `9469f09`, then pass the downloaded path to `scripts/build_district_map.py` with the API environment active. Four administrative spelling variants are matched to the app's district catalog.
