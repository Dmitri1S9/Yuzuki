"""Local English embedding model (fastembed/ONNX, CPU). Atomic: text in, unit vectors out.

Query/passage instructions: BGE and e5-family models were trained for asymmetric retrieval — a "query"
instruction is prepended to the text being searched FOR, nothing is prepended to the reference "passage"
text it's compared against. fastembed does not do this automatically for these ONNX models (`query_embed`/
`passage_embed` are no-ops that just call plain `embed`, verified against fastembed 0.8.1's OnnxTextEmbedding),
so it's applied here, keyed off the model name. bge-small-en-v1.5's own model card calls this "not so
necessary" for v1.5, but still recommended for short/ambiguous query-like text.
"""
import numpy as np

_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
_E5_QUERY_PREFIX = "query: "
_E5_PASSAGE_PREFIX = "passage: "


class Embedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        """`is_query=True` for the text being classified/searched; `False` (default) for reference text
        (anchor examples, documents) -- matches how these models were trained."""
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        texts = [self._prefixed(t, is_query) for t in texts]
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.model_name)
        vectors = np.array(list(self._model.embed(texts)), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)

    def _prefixed(self, text: str, is_query: bool) -> str:
        name = self.model_name.lower()
        if "bge" in name:
            return _BGE_QUERY_INSTRUCTION + text if is_query else text
        if "e5" in name:
            return (_E5_QUERY_PREFIX if is_query else _E5_PASSAGE_PREFIX) + text
        return text
