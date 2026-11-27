import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image


def test_catalog_exposes_disease_enabled_crops_and_excludes_healthy_only(tmp_path):
    from app.doctor_models import DoctorRegistry
    catalog = DoctorRegistry(tmp_path).capabilities()
    crops = {c['id']: c for c in catalog['crops']}
    assert len(crops) == 12
    assert {'tomato', 'potato', 'maize', 'rice', 'bell_pepper'} <= crops.keys()
    assert not {'blueberry', 'raspberry', 'soybean'} & crops.keys()
    assert all(not c['available'] and c['labels'] for c in crops.values())
    assert all(c['name_bn'] and c['model_id'] for c in crops.values())


def test_unknown_crop_is_rejected_before_model_loading(tmp_path):
    from app.doctor_models import DoctorRegistry
    with pytest.raises(ValueError, match='Unsupported crop'):
        DoctorRegistry(tmp_path).infer(Image.new('RGB', (250, 250)), 'wheat')


def test_quality_failure_is_an_observation_without_fake_scores(tmp_path):
    from app.doctor_models import DoctorRegistry
    result = DoctorRegistry(tmp_path).infer(Image.new('RGB', (250, 250), (40, 110, 40)), 'rice')
    assert result['status'] == 'unable_to_classify'
    assert result['classification']['score'] is None
    assert result['quality_flags']
    assert result['crop'] == 'rice'


def test_score_policy_does_not_renormalize_wrong_crop_or_nonfinite_values():
    from app.doctor_models import classify_logits, PLANT_LABELS
    import torch
    logits = torch.full((len(PLANT_LABELS),), -20.)
    logits[PLANT_LABELS.index('Tomato___healthy')] = 20
    result = classify_logits(logits, PLANT_LABELS, 'potato', .85)
    assert result['abstained'] and result['top_label'] == 'unknown'
    assert result['rejection_reason'] == 'crop_mismatch'
    options = result['selected_crop_options']
    assert {option['label'] for option in options} == {
        'Potato___Early_blight', 'Potato___Late_blight', 'Potato___healthy',
    }
    assert sum(option['score'] for option in options) < 0.01
    for bad in [float('nan'), float('inf')]:
        logits[0] = bad
        with pytest.raises(ValueError, match='finite'):
            classify_logits(logits, PLANT_LABELS, 'potato', .85)


def test_nonfinite_shape_and_low_confidence_are_safe():
    from app.doctor_models import classify_logits, RICE_LABELS
    import torch
    result = classify_logits(torch.zeros(len(RICE_LABELS)), RICE_LABELS, 'rice', .85)
    assert result['abstained'] and result['rejection_reason'] == 'low_confidence'
    with pytest.raises(ValueError, match='shape'):
        classify_logits(torch.zeros(2), RICE_LABELS, 'rice', .85)


def test_research_bundle_preserves_trained_preprocessing_and_abstention(monkeypatch, tmp_path):
    import hashlib
    import torch
    from app.doctor_models import DoctorRegistry

    class TestModel(torch.nn.Module):
        def forward(self, inputs):
            green = inputs[:, 1].mean(dim=(1, 2))
            return torch.stack((green, -green), dim=1)

    model = tmp_path / 'model.ts'
    torch.jit.trace(TestModel(), torch.zeros(1, 3, 224, 224)).save(str(model))
    checksum = hashlib.sha256(model.read_bytes()).hexdigest()
    card = {
        'schema_version': 1, 'architecture': 'mobilenet_v3_small', 'version': 'test-research-export',
        'artifact': {'path': 'model.ts', 'size_bytes': model.stat().st_size, 'sha256': checksum},
        'labels': [
            {'id': 'potato__late_blight', 'crop': 'potato', 'plant_part': 'leaf', 'label': 'late_blight'},
            {'id': 'tomato__healthy', 'crop': 'tomato', 'plant_part': 'leaf', 'label': 'healthy'},
        ],
        'preprocessing': {
            'image_size': 224, 'color_mode': 'RGB', 'resize': 'square', 'interpolation': 'bilinear',
            'scale': 255.0, 'mean': [0.485, 0.456, 0.406], 'std': [0.229, 0.224, 0.225],
            'exif_transpose': True,
        },
        'output': 'joint_logits', 'score_type': 'uncalibrated_joint_softmax',
        'thresholds': {'potato__late_blight': 0.9, 'tomato__healthy': None},
        'field_validated': False, 'release_approved': False, 'synthetic_smoke': False,
    }
    card_path = tmp_path / 'model.json'
    card_path.write_text(json.dumps(card), encoding='utf-8')
    monkeypatch.setenv('AGRODOCTOR_RESEARCH_MODEL_DIR', str(tmp_path))
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.setattr('app.doctor_models.image_quality', lambda _: [])
    registry = DoctorRegistry(tmp_path / 'standard')
    assert registry.capabilities()['research_leaf_model']['field_validated'] is False
    green = Image.new('RGB', (320, 240), (0, 255, 0))
    regular = registry.infer_research(green, 'potato')
    assert regular['model']['version'] == 'test-research-export'
    assert regular['classification']['top_label'] == 'Potato___Late_blight'
    assert registry.infer_research(green, 'tomato')['classification']['rejection_reason'] == 'crop_mismatch'
    red = Image.new('RGB', (320, 240), (255, 0, 0))
    assert registry.infer_research(red, 'tomato')['classification']['rejection_reason'] == 'class_disabled'
    card['artifact']['sha256'] = '0' * 64
    card_path.write_text(json.dumps(card), encoding='utf-8')
    assert registry.capabilities()['research_leaf_model']['available'] is False


def test_matching_digest_corrupt_artifact_never_ready(tmp_path):
    from app.doctor_models import DoctorRegistry, CATALOG
    import hashlib
    d = tmp_path / 'plantvillage'; d.mkdir()
    data = b'not a torchscript model'
    (d/'model.pt').write_bytes(data)
    spec=CATALOG['models']['plantvillage']
    (d/'model.json').write_text(json.dumps(dict(**spec,version='fixture',
        source_sha256_verified=spec['source_sha256'],artifact_sha256=hashlib.sha256(data).hexdigest())))
    card = DoctorRegistry(tmp_path).card('potato')
    assert card['available'] is False
    assert card['artifact_status'] == 'broken_artifact'


def test_crop_aliases_are_explicit_not_arbitrary():
    from app.doctor_models import normalize_crop
    assert normalize_crop(' Corn ') == 'maize'
    assert normalize_crop('PEPPER') == 'bell_pepper'
    with pytest.raises(ValueError): normalize_crop('')

def test_shallow_container_layout_honours_explicit_path(monkeypatch, tmp_path):
    import app.doctor_models as module
    monkeypatch.setattr(module,'__file__','/app/app/doctor_models.py')
    monkeypatch.setenv('MULTICROP_MODEL_DIR',str(tmp_path))
    assert module.DoctorRegistry().root==tmp_path
    monkeypatch.delenv('MULTICROP_MODEL_DIR')
    assert module.DoctorRegistry().root.is_absolute()

def fixture_bundle(tmp_path, monkeypatch, source_override=None):
    import hashlib, torch
    import app.doctor_models as module
    spec=module.CATALOG['models']['plantvillage']
    folder=tmp_path/'plantvillage';folder.mkdir()
    data=b'fixture only; torch loader mocked'
    (folder/'model.pt').write_bytes(data)
    card={**spec,'version':'fixture','artifact_sha256':hashlib.sha256(data).hexdigest(),
        'source_sha256_verified':spec['source_sha256'],
        'integration_checks':{'native_export_tensor_controls':3,'max_absolute_logit_error':0.,'saved_artifact_reload':True,'remote_code_executed':False}}
    if source_override:card.update(source_override)
    (folder/'model.json').write_text(json.dumps(card),encoding='utf-8')
    calls=[]
    class Dummy:
        def eval(self):return self
        def __call__(self, tensor):return torch.zeros(1,len(spec['labels']))
    def load(*args,**kwargs):calls.append(args);return Dummy()
    monkeypatch.setattr(torch.jit,'load',load)
    return module.DoctorRegistry(tmp_path),calls

def test_catalog_cannot_activate_a_different_source_revision(tmp_path,monkeypatch):
    registry,calls=fixture_bundle(tmp_path,monkeypatch,{'revision':'not-the-pinned-revision'})
    card=registry.card('potato')
    assert not card['available'] and 'pinned' in card['artifact_error'].lower()
    assert not calls

def test_model_initialization_is_single_flight_and_preprocessing_matches(tmp_path,monkeypatch):
    registry,calls=fixture_bundle(tmp_path,monkeypatch)
    with ThreadPoolExecutor(max_workers=4) as pool:
        cards=list(pool.map(lambda _:registry.card('potato'),range(8)))
    assert all(card['available'] for card in cards) and len(calls)==1
    tensor=registry._bundle('plantvillage')['transform'](Image.new('RGB',(300,250),(255,0,128)))
    assert tuple(tensor.shape)==(3,224,224)
    assert float(tensor[0,0,0])==pytest.approx(1.)
    assert float(tensor[1,0,0])==pytest.approx(-1.)


@pytest.mark.parametrize('wider_label, expected', [
    ('Potato___Late_blight', 'Potato___Late_blight'),
    ('Potato___Early_blight', 'unknown'),
    ('Tomato___Late_blight', 'unknown'),
])
def test_low_confidence_potato_view_requires_agreement(monkeypatch, tmp_path, wider_label, expected):
    import torch
    from app.doctor_models import DoctorRegistry, PLANT_LABELS

    registry, _ = fixture_bundle(tmp_path, monkeypatch)
    bundle = registry._bundle('plantvillage')
    center = torch.zeros(len(PLANT_LABELS))
    center[PLANT_LABELS.index('Potato___Late_blight')] = 4
    wider = torch.zeros(len(PLANT_LABELS))
    wider[PLANT_LABELS.index(wider_label)] = 12
    predictions = iter([center.unsqueeze(0), wider.unsqueeze(0)])
    monkeypatch.setitem(bundle, 'model', lambda _: next(predictions))
    monkeypatch.setattr('app.doctor_models.image_quality', lambda _: [])

    result = registry.infer(Image.new('RGB', (400, 240)), 'potato')['classification']
    assert result['top_label'] == expected
    assert result.get('image_view') == ('full_frame' if expected != 'unknown' else None)
