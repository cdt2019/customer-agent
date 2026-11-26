"""重排模型：把问题和每个候选块放在一起看，给出更准的相关度。慢，所以只排少量候选。"""

from pathlib import Path

import torch
from sentence_transformers import CrossEncoder


class Reranker:
    def __init__(self, model_dir: Path, device: str | None = None):
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        dtype = torch.float16 if device == "cuda" else torch.float32
        self._model = CrossEncoder(str(model_dir), device=device, model_kwargs={"torch_dtype": dtype})

    def scores(self, query: str, texts: list[str]) -> list[float]:
        return self._model.predict([(query, text) for text in texts], batch_size=4).tolist()
