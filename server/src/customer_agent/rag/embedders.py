"""向量模型：把文字变成归一化的向量。"""

from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self, model_dir: Path, device: str | None = None):
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        # 4GB 显存要同时放向量和重排两个模型，显卡上一律半精度（实测见 docs/05）
        dtype = torch.float16 if device == "cuda" else torch.float32
        self.name = model_dir.name
        self._model = SentenceTransformer(str(model_dir), device=device, model_kwargs={"torch_dtype": dtype})
        self.dim = self._model.get_embedding_dimension()
        # 有的模型（如 Qwen3）要给问题加提示语，文档不加
        self._query_prompt = "query" if "query" in self._model.prompts else None

    def documents(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(texts, batch_size=8, normalize_embeddings=True)

    def query(self, text: str) -> np.ndarray:
        return self._model.encode(text, prompt_name=self._query_prompt, normalize_embeddings=True)
