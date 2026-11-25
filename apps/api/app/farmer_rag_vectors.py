"""Optional local multilingual E5 reranking. The app can run without the model."""

from functools import lru_cache
import logging
import os
from pathlib import Path
from threading import Lock


logger = logging.getLogger(__name__)
_model_lock = Lock()


def _model_dir() -> Path | None:
    configured = os.getenv("FARMER_RAG_MODEL_DIR")
    if configured:
        return Path(configured)
    root = next((p for p in Path(__file__).resolve().parents if (p / "apps" / "api").is_dir()), None)
    local = root / "work" / "rag-e5" if root else None
    return local if local and local.is_dir() else None


class _Encoder:
    def __init__(self, directory):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(directory / "model_int8.onnx"), options,
                                            providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}

    def encode(self, texts):
        np = self.np
        encodings = self.tokenizer.encode_batch(texts)
        mask = np.array([enc.attention_mask for enc in encodings], dtype=np.int64)
        inputs = {
            "input_ids": np.array([enc.ids for enc in encodings], dtype=np.int64),
            "attention_mask": mask,
            "token_type_ids": np.array([enc.type_ids for enc in encodings], dtype=np.int64),
        }
        (hidden,) = self.session.run(["last_hidden_state"], {key: inputs[key] for key in self.input_names})
        pooled = (hidden * mask[..., None]).sum(axis=1) / mask.sum(axis=1, keepdims=True)
        return pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)


@lru_cache(maxsize=1)
def _index(directory: Path, passages: tuple[tuple[str, str], ...]):
    try:
        encoder = _Encoder(directory)
        rows = [f"passage: {text}" for pair in passages for text in pair]
        encoded = [encoder.encode(rows[i:i + 8]) for i in range(0, len(rows), 8)]
        return encoder, encoder.np.concatenate(encoded).reshape(len(passages), 2, -1)
    except Exception as exc:
        # Optional acceleration must never make weather, chat or the API unavailable.
        logger.warning("Farmer RAG is using keyword search. Embedding index unavailable (%s).", type(exc).__name__)
        return None


def semantic_scores(query: str, passages: tuple[tuple[str, str], ...], candidates: list[int]) -> dict[int, float]:
    directory = _model_dir()
    if not directory:
        return {}
    with _model_lock:
        index = _index(directory.resolve(), passages)
    if index is None:
        return {}
    encoder, vectors = index
    try:
        (query_vector,) = encoder.encode([f"query: {query[:1600]}"])
        scores = (vectors[candidates] @ query_vector).max(axis=1)
        if encoder.np.isfinite(scores).all():
            return dict(zip(candidates, map(float, scores)))
    except Exception as exc:
        logger.debug("Farmer RAG skipped semantic reranking (%s).", type(exc).__name__)
    return {}
