# AgroDoctor leaf and produce follow-up

Both research previews are running in the local app. The leaf preview uses `agrodoctor-leaf-mobilenetv3-small-d53b97aafd2c`. The separate produce preview uses `agrodoctor-produce-mobilenetv3-small-c5c6e42d0899`. The models use image evidence and can return an uncertain result. Research previews save no observations.

## Leaf ranking and uncertainty

On the earlier tomato set, v2 ranked early blight first for 49 of 76 photos labeled late blight. It made 228 incorrect named predictions with scores of at least 0.99. The old cutoffs came from controlled PlantVillage validation, where the model encountered different images. Raising a cutoff on its own could reduce coverage without correcting the rankings.

For the follow-up I used the Kaggle-trained v2 backbone and fitted a new classification head locally on CPU. The first attempt added the previously scored Rachin archive to development and produced very few named results. The second added screened images from the authored Pakistan Potato Leaf Dataset training and validation folders and one TOM2024 development region. It used 6,085 training photos and 1,303 development photos. Selection used source-averaged validation macro-F1. A named class needs at least 10 development predictions and at least 85% agreement at a tested cutoff. Both held-out datasets stayed outside fitting and cutoff selection. [Pakistan potato leaf dataset](https://www.kaggle.com/datasets/rizwan123456789/potato-disease-leaf-datasetpld) · [TOM2024 dataset](https://data.mendeley.com/datasets/3d4yg89rtr/1)

| Benchmark | v2 top-rank matches | Adapted top-rank matches | v2 correct / incorrect named results | Adapted correct / incorrect named results |
| --- | ---: | ---: | ---: | ---: |
| TOM2024 Plateau-Central tomato photos | 0/85 | 84/85 | 0 / 70 | 19 / 0 |
| Pakistan PLD potato author test fold | 149/330 | 310/330 | 109 / 101 | 306 / 11 |

All 44 tomato late blight photos in the reserved region returned uncertain after applying the development cutoffs. Tomato late blight remains disabled for named screening even though the held-out top ranks improved. On the Pakistan potato fold the adapted model named 111 of 115 late-blight examples correctly, returned uncertain on three and named the wrong condition on one. The Pakistan data use the same deposit's authored training and test folders with additional exact and near-duplicate screening. TOM2024 uses different regions from the same deposit. Neither archive provides verified distinct farm and plant IDs for the test records.

## Separate produce model

The produce classifier learned four appearance categories for tomato fruit and potato tubers and an out-of-scope leaf class. It was fitted on CPU with an ImageNet backbone, 1,464 training photos and 330 validation photos. The public primary archive provides fresh and rotten source classes. The UI uses broader appearance language to avoid assigning a cause from pixels. Grouped filename splits and image checks keep known duplicate variants together. Separate research images from a BARI-reviewed potato collection and the Malaysian deposit supplement the held-out test. The Malaysian archive contributed fresh-class images for these two crops. [Primary produce archive](https://www.kaggle.com/datasets/muhriddinmuxiddinov/fruits-and-vegetables-dataset) · [BARI-reviewed potato collection](https://github.com/Mukaffi28/Potato-Disease) · [Malaysian deposit](https://doi.org/10.5281/zenodo.20843858)

| Held-out produce source | Agreement after uncertainty |
| --- | ---: |
| Primary produce archive, grouped test | 266/285 |
| BARI-reviewed tuber collection | 224/293 |
| Malaysian fresh-category photos | 10/35 |
| All known produce labels | 500/613 (81.6%) |

The model accepted 544 of the 613 known produce photos and was correct on 500 of those named results. It returned uncertain on all 76 controlled leaf challenge photos when the corresponding produce crop was selected. Source-level performance varied substantially, and the data lack traceable individual-item and farm IDs.

## App verification and limits

- In the browser, **Preview with research produce model** returned possible visible damage or decay on the two held-out damaged produce examples. The result showed the model version and practical checks, and the saved-case count stayed the same.
- Authenticated local API uploads reproduced the two produce results in requests for English and Bangla, abstained on a leaf submitted as a tuber, and produced uncertain results for the two separately selected leaf examples. Both model IDs and artifact versions were read back from the running service.
- The produced score describes an appearance match. The application does not use it to determine edibility or identify a causal organism. The field datasets establish photo-level benchmark evidence. Independent farm validation still needs qualified labels and traceable farm groups, so named farmer-facing rollout remains pending. Both candidates are available through the local research controls.
