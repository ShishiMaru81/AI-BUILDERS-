# AgroDoctor training on Kaggle

Use this workflow for the first tomato and potato **leaf** baseline. It uses original RGB PlantVillage photos and a pretrained MobileNetV3 Small model. The run produces a candidate model and measurements on held-out PlantVillage leaves. Bangladesh field data is a separate evaluation phase.

## Files to use

| File | What to do with it |
| --- | --- |
| `work/agrodoctor-kaggle/agrodoctor-kaggle-input.zip` | Upload as a **private dataset on Kaggle**. It contains the approved baseline images, manifest, attribution, trainer, and official pretrained weights. |
| [`agrodoctor_kaggle.ipynb`](../ml/doctor/agrodoctor_kaggle.ipynb) | Import into a **private Kaggle notebook** and attach that dataset. |
| `agrodoctor-results.zip` | Download from the notebook's Output tab after training. Return this file for model and field-test review. |

## Prepare the input bundle

From the repository root, use the local Python environment with the API requirements installed. The preparation script downloads the attributed PlantVillage source and matching group metadata. The bundle builder verifies the official TorchVision starting weights before packaging the photos and manifest.

```powershell
.\.venv\Scripts\python.exe ml/doctor/prepare_kaggle_dataset.py
$weights = 'work/agrodoctor-kaggle/mobilenet_v3_small-047dcff4.pth'
Invoke-WebRequest https://download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth -OutFile $weights
.\.venv\Scripts\python.exe ml/doctor/build_kaggle_bundle.py --data work/agrodoctor-kaggle/data --weights $weights --output work/agrodoctor-kaggle/agrodoctor-kaggle-input.zip
```

## Run your first training

1. Open **Kaggle → Datasets → New Dataset**. Upload `agrodoctor-kaggle-input.zip`, use a name such as **AgroDoctor Leaf Baseline**, and keep visibility **Private**. Kaggle unpacks the ZIP while retaining the folder structure. [Kaggle dataset documentation](https://www.kaggle.com/docs/datasets)
2. Open a new Kaggle Notebook. Use **File → Import Notebook**, select `agrodoctor_kaggle.ipynb`, and keep the notebook private. Use **Add Input** to attach the dataset from step 1.
3. In **Settings → Accelerator**, choose an available **GPU**. A single GPU is enough for this baseline. Check the quota in Kaggle. Keep **Internet off** for this run. The notebook already has the official starting weights. [Kaggle notebook documentation](https://www.kaggle.com/docs/notebooks) · [TorchVision MobileNetV3](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.mobilenet_v3_small.html)
4. Run the first two code cells to verify your input and see the per-class counts. Then choose **Save Version → Save & Run All** for a saved run from start to finish. Keep the default **12 epochs**, **batch size 64**, and **seed 2026** initially. If you choose an interactive run instead, download the result before closing the session.
5. Open **Output** after training. Download `agrodoctor-results.zip`, which includes the trained model, checkpoint, class order, metadata, metrics, training log, and checksums. Save the Kaggle run version alongside it.

The notebook estimates progress from actual epoch timings. Plan for roughly 30–90 minutes for a first GPU run after the environment starts. If Kaggle reports CUDA out of memory, change `BATCH_SIZE` to 32 and rerun. If the notebook cannot find the dataset, check that **Add Input** points to the upload that contains `agrodoctor-input.json`.

## Dataset decisions

The first run covers healthy, early blight, and late blight on both crops, plus tomato bacterial spot, leaf mold, and Septoria leaf spot. PlantVillage files are linked to the authors' physical-leaf groups. The official test fold stays separate and validation comes from the original training fold. [Original PlantVillage source](https://github.com/spMohanty/PlantVillage-Dataset) · [Author-provided splits and licensing](https://huggingface.co/datasets/mohanty/PlantVillage)

| Split | Photos | Source leaf groups |
| --- | ---: | ---: |
| Training | 2,918 | 1,471 |
| Validation | 363 | 363 |
| Test | 452 | 452 |
| Total | 3,733 | 2,286 |

The prepared set excludes 27 near-duplicate candidates and retains the original test membership. The potato healthy label has only six validation and eight test leaves, so treat its measurements as preliminary.

Keep the bundled attribution and CC BY-SA 3.0 source notice with the artifacts. The authors' dataset paper states that they intend models trained on the images to use the same license. [PlantVillage dataset paper](https://arxiv.org/abs/1511.08060)

Potato leafroll and all produce conditions require separate data review. Keep the [Bangladesh field sources](../data/agrodoctor/field-sources.md) out of the Kaggle input for this first run. Earlier photos supplied for debugging can serve as workflow examples. A locked field evaluation needs separate images with reviewed labels and documented grouping.

Before using any named condition in AgroDoctor, review per-class precision, recall including uncertain cases, false alarms, and the results on independently collected field photos. The [implementation plan](superpowers/plans/2026-11-26-agrodoctor-kaggle.md) covers the pilot criteria, reviewed Bangla and English guidance, and the separate tomato fruit and potato tuber model.
