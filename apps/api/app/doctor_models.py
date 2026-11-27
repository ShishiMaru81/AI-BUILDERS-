"""Pinned, crop-aware research inference. Never conditions scores on a chosen crop."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from PIL import Image, ImageFilter, ImageOps, ImageStat
from . import doctor_vision
from .doctor_patterns import field_check
from .services import ModelBrokenError

CATALOG = json.loads(Path(__file__).with_name('doctor_catalog.json').read_text(encoding='utf-8'))
CROPS = {c['id']: c for c in CATALOG['crops']}
PLANT_LABELS = CATALOG['models']['plantvillage']['labels']
RICE_LABELS = CATALOG['models']['rice']['labels']
NOTICE = 'Research screening only. Crop identification and out-of-distribution rejection are not field-validated.'
RESEARCH_MODEL_ID = 'agrodoctor-research-leaf'
RESEARCH_PREPROCESSING = {
    'image_size': 224, 'color_mode': 'RGB', 'resize': 'square', 'interpolation': 'bilinear',
    'scale': 255.0, 'mean': [0.485, 0.456, 0.406], 'std': [0.229, 0.224, 0.225],
    'exif_transpose': True,
}
RESEARCH_LABELS = {
    'potato__early_blight': 'Potato___Early_blight', 'potato__healthy': 'Potato___healthy',
    'potato__late_blight': 'Potato___Late_blight', 'potato__leafroll': 'Potato___Leafroll',
    'tomato__bacterial_spot': 'Tomato___Bacterial_spot', 'tomato__early_blight': 'Tomato___Early_blight',
    'tomato__healthy': 'Tomato___healthy', 'tomato__late_blight': 'Tomato___Late_blight',
    'tomato__leaf_mold': 'Tomato___Leaf_Mold', 'tomato__septoria_leaf_spot': 'Tomato___Septoria_leaf_spot',
}
RESEARCH_PRODUCE_LABELS = {
    'potato__sound_appearance': 'Potato___Sound_appearance',
    'potato__visible_damage': 'Potato___Visible_damage',
    'tomato__sound_appearance': 'Tomato___Sound_appearance',
    'tomato__visible_damage': 'Tomato___Visible_damage',
    'other__out_of_scope': 'Other___Out_of_scope',
}
_LOCK = threading.RLock()
_CACHE: dict[tuple, dict] = {}


class VisionUnavailable(HTTPException):
    """The remote image assessment could not complete."""


def _blight_reference(label: str) -> bool:
    return label in {'Potato___Early_blight', 'Potato___Late_blight',
                     'Tomato___Early_blight', 'Tomato___Late_blight'}


def normalize_crop(value: str) -> str:
    value = str(value).strip().lower()
    value = {'corn': 'maize', 'pepper': 'bell_pepper', 'bell pepper': 'bell_pepper', 'paddy': 'rice'}.get(value, value)
    if value not in CROPS:
        raise ValueError('Unsupported crop. Choose a disease-enabled crop from the capability catalog.')
    return value


def crop_for_label(label: str) -> str | None:
    prefix = label.split('___', 1)[0]
    return next((c['id'] for c in CROPS.values() if c['label_prefix'] == prefix), None)


def classify_logits(logits, labels: list[str], crop: str, threshold: float | dict[str, float | None]) -> dict:
    import torch
    if logits.ndim != 1 or logits.numel() != len(labels):
        raise ValueError('Model output shape does not match class metadata')
    if not bool(torch.isfinite(logits).all()):
        raise ValueError('Model output must be finite')
    probs = logits.float().softmax(0)
    indices = probs.argsort(descending=True)[:3].tolist()
    crop_indices = [i for i, label in enumerate(labels) if crop_for_label(label) == crop]
    crop_indices.sort(key=lambda i: float(probs[i]), reverse=True)
    index = indices[0]
    score = float(probs[index])
    cutoff = threshold[labels[index]] if isinstance(threshold, dict) else threshold
    reason = None
    if crop_for_label(labels[index]) != crop:
        reason = 'crop_mismatch'
    elif cutoff is None:
        reason = 'class_disabled'
    elif score < cutoff:
        reason = 'low_confidence'
    return dict(top_label='unknown' if reason else labels[index], abstained=bool(reason), score=score,
        score_type='uncalibrated_model_score', rejection_reason=reason, ood_notice=NOTICE,
        alternatives=[{'label': labels[i], 'score': float(probs[i])} for i in indices],
        selected_crop_options=[{'label': labels[i], 'score': float(probs[i])} for i in crop_indices[:3]])


def image_quality(image: Image.Image) -> list[str]:
    gray = image.convert('L'); stats = ImageStat.Stat(gray)
    flags = []
    if min(image.size) < 160: flags.append('low_resolution')
    if stats.mean[0] < 35: flags.append('underexposed')
    if stats.mean[0] > 235: flags.append('overexposed')
    inner = gray.crop((2, 2, max(3, gray.width-2), max(3, gray.height-2))) if min(gray.size)>6 else gray
    if stats.var[0] < 8 or ImageStat.Stat(inner.filter(ImageFilter.FIND_EDGES)).var[0] < 80:
        flags.append('possibly_blurred')
    return flags


class DoctorRegistry:
    def __init__(self, root: Path | str | None = None):
        configured = root or os.getenv('MULTICROP_MODEL_DIR')
        if configured:
            self.root = Path(configured)
        else:
            # Source checkout and /app/app container layouts have different depths.
            repo = next((p for p in Path(__file__).resolve().parents if (p/'ml/artifacts').is_dir()), None)
            self.root = repo/'ml/artifacts/multicrop' if repo else Path('/models/multicrop').resolve()

    def _research_bundle(self, part: str = 'leaf') -> dict | None:
        produce = part == 'produce'
        key_name = 'AGRODOCTOR_RESEARCH_PRODUCE_MODEL_DIR' if produce else 'AGRODOCTOR_RESEARCH_MODEL_DIR'
        configured = os.getenv(key_name, '').strip()
        if not configured:
            return None
        model_id = 'agrodoctor-research-produce' if produce else RESEARCH_MODEL_ID
        labels = RESEARCH_PRODUCE_LABELS if produce else RESEARCH_LABELS
        folder = Path(configured)
        binary = folder / 'model.ts'
        card = dict(model_id=model_id, version=model_id, available=False,
                    artifact_status='broken_artifact', labels=[], field_validated=False, metrics=None,
                    source='AgroDoctor training run', limitations=[NOTICE])
        try:
            raw = (folder / 'model.json').read_bytes()
            stat = binary.stat()
        except OSError:
            return {'card': {**card, 'artifact_status': 'absent'}}

        with _LOCK:
            key = (model_id, str(folder.resolve()), hashlib.sha256(raw).hexdigest(), stat.st_size, stat.st_mtime_ns)
            if key in _CACHE:
                return _CACHE[key]
            try:
                metadata = json.loads(raw)
                if (metadata.get('schema_version') != 1 or metadata.get('architecture') != 'mobilenet_v3_small'
                        or metadata.get('synthetic_smoke') is not False or metadata.get('field_validated') is not False
                        or metadata.get('release_approved') is not False
                        or metadata.get('output') != 'joint_logits'
                        or metadata.get('score_type') != 'uncalibrated_joint_softmax'
                        or metadata.get('preprocessing') != RESEARCH_PREPROCESSING):
                    raise ValueError('Expected a compatible AgroDoctor research export')
                entries = metadata['labels']
                ids = [entry['id'] for entry in entries]
                if (ids != sorted(set(ids)) or any(
                    entry['id'] not in labels
                    or entry['plant_part'] != ('leaf' if entry['id'] == 'other__out_of_scope' else part)
                    or entry['id'] != f"{entry['crop']}__{entry['label']}" for entry in entries
                ) or {entry['crop'] for entry in entries if entry['id'] != 'other__out_of_scope'} != {'potato', 'tomato'}
                        or (produce and set(ids) != set(RESEARCH_PRODUCE_LABELS))):
                    raise ValueError('Invalid research model class metadata')
                cutoffs = metadata['thresholds']
                if not isinstance(cutoffs, dict) or cutoffs.keys() != set(ids) or any(
                    value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1)
                    for value in cutoffs.values()
                ) or (produce and cutoffs['other__out_of_scope'] is not None):
                    raise ValueError('Invalid research model thresholds')
                data = binary.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                version = metadata['version']
                if (metadata['artifact'] != {'path': 'model.ts', 'sha256': digest, 'size_bytes': len(data)}
                        or not isinstance(version, str) or not version.strip()):
                    raise ValueError('Research artifact checksum or version is invalid')
                import torch
                from torchvision import transforms

                torch.set_num_threads(2)
                model = torch.jit.load(io.BytesIO(data), map_location='cpu').eval()
                with torch.inference_mode():
                    output = model(torch.zeros(1, 3, 224, 224))
                if tuple(output.shape) != (1, len(ids)) or not bool(torch.isfinite(output).all()):
                    raise ValueError('Research artifact output does not match model classes')
                transform = transforms.Compose([
                    transforms.Resize((224, 224), interpolation=transforms.InterpolationMode.BILINEAR),
                    transforms.ToTensor(),
                    transforms.Normalize(RESEARCH_PREPROCESSING['mean'], RESEARCH_PREPROCESSING['std']),
                ])
                entry = {
                    'card': {**card, 'version': version, 'available': True, 'artifact_status': 'ready',
                             'labels': [labels[class_id] for class_id in ids]},
                    'thresholds': {labels[class_id]: cutoffs[class_id] for class_id in ids},
                    'model': model, 'transform': transform,
                }
            except Exception:
                entry = {'card': card}
            _CACHE[key] = entry
            return entry

    def _bundle(self, model_id: str) -> dict:
        spec = CATALOG['models'][model_id]
        folder = self.root / model_id
        card_path, binary = folder/'model.json', folder/'model.pt'
        base = dict(version=f'{model_id}-{spec["revision"][:12]}', available=False,
            field_validated=False, labels=spec['labels'], metrics=None, reported_metrics=None,
            source=spec['source_repo'], source_url=spec['source_url'], license=spec['license'],
            revision=spec['revision'], model_id=model_id, threshold=spec['threshold'],
            limitations=[NOTICE, 'Publisher metrics are external reports, not AgroSphere field validation.'],
            artifact_status='absent', artifact_error=None)
        if not card_path.is_file() and not binary.is_file():
            return {'card':base}
        try:
            raw = card_path.read_bytes()
            stat = binary.stat()
            key = (str(folder.resolve()), hashlib.sha256(raw).hexdigest(), stat.st_size, stat.st_mtime_ns)
        except OSError as exc:
            return {'card':{**base,'artifact_status':'broken_artifact','artifact_error':str(exc)}}
        # Single-flight initialization: public capability checks cannot duplicate cold loads.
        with _LOCK:
            if key in _CACHE: return _CACHE[key]
            try:
                card = json.loads(raw)
                for field in ['model_id','source_repo','revision','source_sha256','license']:
                    if card.get(field) != spec[field]:
                        raise ValueError(f'{field} does not match the pinned model source')
                if card.get('source_sha256_verified') != spec['source_sha256']:
                    raise ValueError('Verified source checksum does not match pinned weights')
                if card.get('labels') != spec['labels'] or len(set(card['labels'])) != len(card['labels']):
                    raise ValueError('Class labels/order do not match the pinned catalog')
                if card.get('preprocessing') != spec['preprocessing']:
                    raise ValueError('Preprocessing does not match pinned metadata')
                if card.get('threshold') != spec['threshold']:
                    raise ValueError('Threshold does not match declared research policy')
                if hashlib.sha256(binary.read_bytes()).hexdigest() != card.get('artifact_sha256'):
                    raise ValueError('Model artifact checksum mismatch')
                import torch
                from torchvision import transforms
                torch.set_num_threads(2)
                model = torch.jit.load(str(binary), map_location='cpu').eval()
                with torch.inference_mode(): output = model(torch.zeros(1,3,224,224))
                if tuple(output.shape) != (1,len(spec['labels'])) or not bool(torch.isfinite(output).all()):
                    raise ValueError('Model output shape/values are invalid')
                prep = spec['preprocessing']
                interpolation = transforms.InterpolationMode.BICUBIC if prep['interpolation']=='bicubic' else transforms.InterpolationMode.BILINEAR
                normalize = transforms.Compose([transforms.ToTensor(), transforms.Normalize(prep['mean'], prep['std'])])
                transform = transforms.Compose([transforms.Resize(prep['resize'], interpolation=interpolation),
                    transforms.CenterCrop(prep['crop']), normalize])
                entry = {'card':{**base, **card, 'metrics':None, 'available':True, 'artifact_status':'ready',
                    'field_validated':False,'artifact_error':None}, 'model':model,'transform':transform,
                    'normalize':normalize}
            except Exception as exc:
                entry = {'card':{**base, 'artifact_status':'broken_artifact','artifact_error':str(exc)}}
            _CACHE[key] = entry
            return entry

    def card(self, crop: str = 'tomato') -> dict:
        crop = normalize_crop(crop)
        if doctor_vision.configured():
            return {**doctor_vision.model_card(), 'supported_crop_ids': list(CROPS)}
        card = dict(self._bundle(CROPS[crop]['model_id'])['card'])
        card['supported_crop_ids'] = [c['id'] for c in CROPS.values() if c['model_id']==card['model_id']]
        return card

    def capabilities(self) -> dict:
        extra = {}
        for part in ('leaf', 'produce'):
            if research := self._research_bundle(part):
                extra[f'research_{part}_model'] = research['card']
        if doctor_vision.configured():
            card = doctor_vision.model_card()
            crops = [{**crop, 'model_id': card['model_id'], 'model_version': card['version'],
                      'available': True, 'artifact_status': 'configured', 'labels': [],
                      'has_healthy_class': False, 'limitations': card['limitations']} for crop in CROPS.values()]
            return {'provider': 'groq', 'crops': crops, 'models': [card],
                    'limitations': card['limitations'], 'automatic_crop_detection': True, **extra}
        cards = {mid:self._bundle(mid)['card'] for mid in CATALOG['models']}
        crops = []
        for crop in CROPS.values():
            card = cards[crop['model_id']]
            labels = [label for label in card['labels'] if label.startswith(crop['label_prefix']+'___')]
            healthy = any(label.lower().endswith('___healthy') for label in labels)
            crops.append({**crop, 'labels':labels, 'available':card['available'], 'model_version':card['version'],
                'artifact_status':card['artifact_status'], 'has_healthy_class':healthy,
                'limitations':[NOTICE]+([] if healthy else ['This crop has no healthy reference class; a healthy plant cannot be ruled in/out.'])})
        return {'crops':crops,'models':list(cards.values()),'limitations':[NOTICE], 'automatic_crop_detection':False, **extra}

    def infer_research(self, image: Image.Image, crop: str, *, part: str = 'leaf') -> dict:
        bundle = self._research_bundle(part)
        if crop not in {'tomato', 'potato'} or not bundle or not bundle['card']['available']:
            raise ModelBrokenError(f'The AgroDoctor research {part} model is unavailable.')
        image = ImageOps.exif_transpose(image).convert('RGB')
        flags = image_quality(image)
        result = dict(top_label='unknown', abstained=True, score=None, score_type='not_available',
                      alternatives=[], rejection_reason='image_quality', ood_notice=NOTICE)
        if not flags:
            try:
                import torch
                with torch.inference_mode():
                    logits = bundle['model'](bundle['transform'](image).unsqueeze(0))[0]
                result = classify_logits(logits, bundle['card']['labels'], crop, bundle['thresholds'])
            except Exception as exc:
                raise ModelBrokenError('Research inference could not complete.') from exc
        if part == 'produce':
            return dict(crop=crop, classification=result, model=bundle['card'], quality_flags=flags,
                        status='unable_to_classify' if result['abstained'] else 'completed',
                        advice=['Look at the whole item and photograph any discolored or damaged area in even light.',
                                'Keep visibly damaged items separate while checking the rest of the batch.'],
                        disclaimer='Appearance screening only. A photo cannot establish whether produce is safe to eat.')
        return dict(crop=crop, classification=result, model=bundle['card'], quality_flags=flags,
                    status='unable_to_classify' if result['abstained'] else 'completed',
                    advice=['Compare symptoms on both sides of the leaf and record when they first appeared.',
                            'Ask an agricultural extension officer to review symptoms before treatment.'],
                    disclaimer=NOTICE)

    def screen_with_vision(self, image: Image.Image, crop: str, part: str, locale: str,
                           follow_up: Image.Image | None = None) -> dict:
        bn = locale == 'bn'
        try:
            result = doctor_vision.inspect_photo(image, crop, part, 'Bangla' if bn else 'English', follow_up)
        except HTTPException as exc:
            if exc.status_code not in (429, 502, 503, 504):
                raise
            if part == 'leaf' and crop in ('potato', 'tomato') and follow_up is None:
                try:
                    return {**self.infer(image, crop), 'fallback_reason': 'vision_unavailable'}
                except ModelBrokenError:
                    pass  # Preserve the provider's retry information when neither model is available.
            raise VisionUnavailable(exc.status_code, exc.detail, headers=exc.headers) from exc
        assessment = result['assessment']
        if assessment['outcome'] != 'no_visible_damage' or assessment['part'] != 'leaf':
            check = field_check(crop, assessment, locale)
            if check:
                assessment['field_check'] = check
            return result

        # A false healthy result can hide a lesion. Only corroborate a negative using a
        # matching leaf classifier with a healthy class. Never run it on harvested produce.
        checks = []
        if crop in CROPS and assessment['crop_match'] == 'match':
            spec = CATALOG['models'][CROPS[crop]['model_id']]
            healthy_label = CROPS[crop]['label_prefix'] + '___healthy'
            if any(label.casefold() == healthy_label.casefold() for label in spec['labels']):
                try:
                    for photo in (image, follow_up) if follow_up is not None else (image,):
                        checks.append(self.infer(photo, crop))
                except ModelBrokenError:
                    pass
        reason = 'unconfirmed_leaf_screen'
        labels = [check['classification']['top_label'].lower() for check in checks
                  if not check['classification']['abstained']]
        if labels:
            result['cross_check_model'] = checks[0]['model']['version']
            if len(labels) == (2 if follow_up is not None else 1) and all(label.endswith('___healthy') for label in labels):
                return result
            if any(not label.endswith('___healthy') for label in labels):
                reason = 'model_disagreement'
        explanation = ('ছবিতে ক্ষতি আছে কি না তা নিশ্চিত করা যায়নি।' if bn else
                       'The photo does not give enough evidence to rule out leaf damage.')
        if reason == 'model_disagreement':
            explanation = ('গ্রক ভিশন স্পষ্ট ক্ষতি শনাক্ত করেনি, কিন্তু পাতার দ্বিতীয় মডেলটি ক্ষতির ইঙ্গিত দিয়েছে।' if bn else
                           'Groq did not identify clear damage, but the independent leaf classifier flagged a possible lesion.')
        advice = ['আক্রান্ত অংশ ও পাতার উল্টো পাশের কাছ থেকে পরিষ্কার ছবি তুলুন।' if bn else
                  'Take a close-up of the affected area and another photo of the underside.']
        assessment.update(outcome='uncertain', condition=None, distinguishing_sign=None, marker='nonspecific',
                          pattern='অনিশ্চিত' if bn else 'Uncertain', signs=[], explanation=explanation,
                          uncertainty='কারণ নির্ধারণ করা যায়নি।' if bn else 'The cause is unresolved.', next_steps=advice)
        result['classification'].update(top_label='unknown', abstained=True, rejection_reason=reason)
        result.update(status='unable_to_classify', advice=advice)
        return result

    def infer(self, image: Image.Image, crop: str) -> dict:
        crop = normalize_crop(crop)
        flags = image_quality(image)
        bundle = self._bundle(CROPS[crop]['model_id']); card = dict(bundle['card'])
        result = dict(top_label='unknown', abstained=True, score=None, score_type='not_available',
            alternatives=[], rejection_reason='image_quality' if flags else 'model_unavailable', ood_notice=NOTICE)
        if not flags:
            if not card['available']:
                raise ModelBrokenError('The selected crop model is unavailable. Install/verify its pinned bundle before screening.')
            try:
                import torch
                transform = bundle['transform']
                with torch.inference_mode():
                    logits = bundle['model'](transform(image).unsqueeze(0))[0]
                result = classify_logits(logits, card['labels'], crop, card['threshold'])
                if crop in {'tomato', 'potato'} and result['rejection_reason'] in ('low_confidence', 'crop_mismatch'):
                    candidate = result['alternatives'][0]['label']
                    if (not candidate.lower().endswith('___healthy') and
                            (result['rejection_reason'] == 'low_confidence' or _blight_reference(candidate))):
                        # The standard center crop can omit affected tissue near the edges.
                        # Accept the wider view only when it supports the same condition.
                        side = card['preprocessing']['crop']
                        framed = ImageOps.pad(image, (side, side), method=Image.Resampling.BICUBIC,
                                              color=tuple(round(value * 255) for value in card['preprocessing']['mean']))
                        tensor = bundle['normalize'](framed)
                        with torch.inference_mode():
                            wider_logits = bundle['model'](tensor.unsqueeze(0))[0]
                        wider = classify_logits(wider_logits, card['labels'], crop, card['threshold'])
                        if wider['top_label'] == candidate:
                            result = {**wider, 'image_view': 'full_frame'}
                        else:
                            wide_label = wider['alternatives'][0]['label']
                            # A weak first-place label in a nearly flat score distribution
                            # provides no reason to single out blight for a field check.
                            if (candidate != wide_label and _blight_reference(candidate) and _blight_reference(wide_label)
                                    and min(result['score'], wider['score']) > 0.5
                                    and crop in (crop_for_label(candidate), crop_for_label(wide_label))):
                                result.update(rejection_reason='conflicting_leaf_views', pattern_hint='blight_like')
            except Exception as exc:
                raise ModelBrokenError(f'Crop model inference failed safely: {exc}') from exc
        return dict(crop=crop, classification=result, model=card, quality_flags=flags,
            status='unable_to_classify' if result['abstained'] else 'completed',
            advice=[f'Confirm this is a {CROPS[crop]["name_en"].lower()} leaf; check several leaves in natural light.',
                'Record symptoms and photograph both sides of affected leaves; inspect neighbouring plants.',
                'Consult a qualified local agronomist or DAE extension officer before treatment decisions.'],
            disclaimer=NOTICE+' No treatment or pesticide dosing is prescribed.')
