# AgroDoctor v2 field source audit

27 November 2026

The archive checks found promising sources for research. None of the checked archives supplied both reliable per-photo diagnoses and farm and plant identifiers for an independent Bangladesh test. No new dataset was approved for the next Kaggle run. The [v1 exploratory evaluation](../../docs/agrodoctor-field-evaluation-2026-11-27.md) stays a separate historical result.

## Tomato

| Deposit | What the files show | Evidence needed |
| --- | --- | --- |
| Hossain et al., Bangladesh, CC BY 4.0 | 2,627 image files. The target folders contain 204 early blight, 166 late blight and 103 healthy photos. Five late blight files duplicate other files in that class byte for byte. All 473 target photos have the same original capture date and the recorded coordinates span about 130 by 30 metres. All 93 target photos from the second phone model are in early blight. [Original deposit](https://data.mendeley.com/datasets/93h9p62kg4/1) | The authors describe a mix of expert and observation-based labeling. Ask for coded capture groups, per-photo review status and any original-to-derivative mapping. Treat the published set as one collection cohort. |
| Rachin et al., Bangladesh, CC BY 4.0 | 2,995 JPEGs. The three main target folders contain 524 early blight, 112 late blight and 380 healthy photos. All 1,016 target images are 640 × 640. Their filenames encode class and sequence. The target images have no camera, date or GPS EXIF and the ZIP contains no metadata sidecar. [Original deposit](https://data.mendeley.com/datasets/jttrv2w27r/1) | The deposit describes collection across different regions. Per-image diagnosis evidence and a farm and plant map are needed to compare independently collected groups. |
| TOM2024, Burkina Faso, CC BY 4.0 | The English labeled archive directory lists 782 healthy tomato leaf crops, 74 tomato late blight crops and 322 under `Alternaria`. The verified public catalog join identifies 428 distinct originals in the healthy and late blight folders across three regions, after setting aside multiple-folder records. [Original deposit](https://data.mendeley.com/datasets/3d4yg89rtr/1) · [Original photo catalog](https://ppedmas.org/search_images.php) | An external research candidate for healthy and late blight. Region-level study is possible after overlap screening. Verified farms and plants are still missing. `Alternaria` needs a documented mapping to early blight. |
| Tomato-Village, India | The Variant B table contains 5,653 entries. Grouping variants by their timestamp stem places 327 stems across the supplied splits. [Author dataset table](https://github.com/mamta-joshi-gehlot/Tomato-Village/blob/main/Variant-b%28MultiLabel%20Classification%29/Multi-Label%20dataset%20-%20with%20augmented.csv) | Establish original capture groups and applicable image license before reuse. The published splits would leak related variants. |

The two Bangladesh archives passed full ZIP-member CRC reads and JPEG header decoding. They shared no identical encoded files with each other, the 3,733-image v1 input, or the 479-image exploratory set. This byte check leaves transformed copies and other near matches unresolved.

- Hossain archive SHA-256 `9d45c4063f796ce85afe312028c40ea9f2f5efc5f14fd33c52d5bbaee430c2cf`.
- Rachin archive SHA-256 `7e24afdb81e0b6b0c189c5588fb57571ebe518b873dc5cb9cd8b52bba4a67069`.

The [TOM2024 regional mapping](tom2024-portal-region-join.csv) contains 610 public original image IDs. All searched catalog entries matched their expected labeled archive folders. The portal's `Tomato Mildew` entries map by image ID to the archive's `tomato_late_blight_d` folder. Five originals appear in multiple archive folders and are flagged. The mapping lists 428 single-folder healthy and late blight originals and 177 `Alternaria` originals awaiting diagnosis clarification. The 428 are distributed across Centre-Ouest (154 healthy, 12 late blight), Centre-Sud (167 healthy, 10 late blight), and Plateau-Central (41 healthy, 44 late blight). These are deposited labels. The mapping has no per-farm independence claim and the originals have not been scored or checked for image overlap.

## Potato

| Deposit | What the files show | Evidence needed |
| --- | --- | --- |
| Laizer et al., Tanzania, CC BY 4.0 | Three ZIP directories list 58,709 JPEGs plus macOS sidecars. The paper describes expert checks and a collection data frame. The public ZIPs lack an image-to-farm or plant map. Directly extracting selected matching entries confirmed six byte-identical pairs across healthy, early blight and late blight folders. [Original deposit](https://zenodo.org/records/8286529) · [Data paper](https://doi.org/10.1016/j.dib.2025.111549) | Ask for the coded original-to-deposit mapping and adjudicated labels. The six targeted confirmations establish conflicts in the archive without estimating their prevalence. |
| PLDD-UP, India, CC BY 4.0 | Three verified ZIP directories contain 4,600 healthy, 4,803 early blight and 6,116 late blight JPEGs. The deposit describes images from three regions. The archives have numbered class files without a metadata sidecar. Direct retrieval confirmed five byte-identical early blight and healthy pairs. [Original deposit](https://data.mendeley.com/datasets/3j4nfkvp2n/1) | Ask the authors for region, farm and plant mappings, their diagnosis review protocol and adjudicated labels. |
| Tilahun et al., Holeta, Ethiopia | The archive decodes 363 healthy and 67 late blight files. The deposit describes 63 late blight files. There are 362 distinct healthy and 67 distinct late blight images by encoded and decoded hashes, with no exact cross-label match. Coverage is one reported farm and two classes. [Original deposit](https://data.mendeley.com/datasets/v4w72bsts5/1) | Useful as an exploratory external set for two labels. There are no public plant identifiers or early blight images. |
| Sharma, IIT Kharagpur | The archive contains 1,561 photos from a field experiment. Its provenance notes say the per-image labels, annotations and split files were not retained. [Original deposit](https://zenodo.org/records/22059910) | Unlabeled photos could be reviewed for a future experiment. Aggregate results are insufficient to score individual photos. |
| Banu and Deb, BARI Chattogram | The previously examined archive contains 84 files named as originals, 72 unique by bytes, no early blight, and no farm or plant map. It was used in the v1 exploratory evaluation. [Original deposit](https://data.mendeley.com/datasets/d5b3fzpw3g/1) | Ask about a fresh reviewed collection from separate farms, or access to the missing original records. Reserve fresh photos for testing v2. |
| BD-PlantDX, Bangladesh | The preprint reports 1,012 healthy and 1,002 late blight potato leaf photos, specimen-level splits and expert review. It also covers mosaic and nutrient deficiency. The linked repository was empty when checked. [Preprint](https://arxiv.org/html/2609.10469v2) · [Linked repository](https://github.com/Abdullah2104/agrovisnet) | Request the expert-reviewed files, permission terms and coded farm groups from the authors. |

For example, the Tanzania archive lists identical image bytes for `earlyblt12220.jpg` and `lateblt14017.jpg`, `earlyblt8238.jpg` and `healthy20435.jpg`, and `healthy4428.jpg` and `lateblt483.jpg`. The check inspected ZIP directories and selected image bytes by HTTP range. It did not download or independently review all images.

## Getting data without personal farm access

Start with the Bangladesh Agricultural Research Institute's Plant Pathology Division or the research teams behind the Bangladesh deposits above. Ask about existing reviewed images from multiple field sites or a referral to a participating extension office. A contributor can provide coded site and plant IDs and keep the identity lookup private. Bangladesh's Agriculture Information Service also provides a route to agricultural specialists through **16123**. [BARI directory](https://bari.gov.bd/pages/officers) · [Agriculture Information Service](https://ais.gov.bd/pages/static-pages/6922df5e933eb65569e21833)

**Draft request for a research team or extension office**

Hello,

I’m developing AgroDoctor, an agricultural research prototype that checks tomato and potato leaf photos for visible signs of disease. I’m looking for existing, reviewed field photos of healthy plants and plants with early or late blight. Would your team be able to share a small set for a private research evaluation, or refer me to someone who can help?

To test on farms the model has never seen, I would need coded farm and plant IDs linked to each filename, the crop and diagnosis, how the diagnosis was checked, and the permitted uses for the photos. Coded IDs are sufficient. Exact locations and farmer contact details can stay with your team. I can share the evaluation results and credit the source as requested.

Thank you,

Anindya Paul
