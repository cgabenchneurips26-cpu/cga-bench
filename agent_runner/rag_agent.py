"""RAG-only Baseline Agent: CPG 문서 검색 기반 에이전트

CGA-Bench 명세에 따른 "강한 텍스트 베이스라인" 구현:
- CPG 문서 코퍼스에서 BM25 기반 관련 텍스트 검색
- 검색된 컨텍스트 기반으로 LLM이 행동 생성
- 구조화된 Action 스키마(JSON) 출력 강제
- Planning/Constraint 검증 없이 단일 스텝 결정

중요 설계 원칙 (NeurIPS 리뷰어 비판 대응):
RAG-only를 "강한 텍스트 베이스라인"으로 위치시키기 위한 제약:

✅ RAG가 사용하는 것:
- CPG 문서 코퍼스 검색 (BM25)
- 구조화된 Action schema(JSON) 출력
- Tool 호출 (검사/오더/EHR)
- 단발 정책 (single-step decision)

❌ RAG가 사용하지 않는 것:
- Planning 모듈 (분리된 계획 단계)
- 제약 검증 (forbidden veto/mandatory alarm)
- cpg_engine/ 직접 접근 (채점용 엔진)
- assessor_core/ 직접 접근 (채점 모듈)
- 다중 스텝 계획 및 반복

이 제약들은 RAG 베이스라인이 "텍스트 검색만으로 얼마나 잘할 수 있는가"를
측정하기 위한 공정한 비교를 보장합니다.
"""

from collections import defaultdict
from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path
import re
from typing import Any

import numpy as np

from cga_bench.agent_runner.base_agent import AgentConfig, AgentMetrics, BaseAgent
from cga_bench.agent_runner.llm_provider import (
    ACTION_RECOMMENDATION_SCHEMA,
    CHECKLIST_SYSTEM_PROMPT,
    CLINICAL_SYSTEM_PROMPT,
    CPG_PHASE_PROMPTS,
    DIRECT_SYSTEM_PROMPT,
    TOOL_USE_SYSTEM_PROMPT,
    BaseLLMProvider,
    LLMBackend,
    LLMConfig,
    LLMMessage,
    LLMProviderFactory,
)
from cga_bench.cpg_model.schemas.base import Action, ActionType
from cga_bench.scenario_engine.environment import Observation

logger = logging.getLogger(__name__)


@dataclass
class RAGConfig(AgentConfig):
    """RAG 에이전트 설정"""

    agent_type: str = "rag"
    # 검색 설정
    top_k: int = 5  # 검색할 문서 수
    use_bm25: bool = True  # BM25 사용 여부
    use_dense: bool = False  # Dense Retrieval 사용 여부 (BGE-M3)
    use_hybrid: bool = False  # Hybrid Retrieval (BM25 + Dense)
    dense_weight: float = 0.5  # Hybrid 시 Dense 가중치 (0~1)
    embedding_model: str = "BAAI/bge-m3"  # 임베딩 모델
    # LLM 설정
    llm_backend: LLMBackend = LLMBackend.OPENAI
    llm_model: str = "gpt-4"
    temperature: float = 0.1
    use_llm: bool = True  # LLM 사용 여부 (False면 규칙 기반 폴백)
    base_url: str | None = None  # vLLM 등 커스텀 서버 URL
    api_key: str | None = None  # API key (vLLM 등)
    # CPG 문서 경로
    cpg_sources_path: str | None = None
    # Scaffold type: "react" (default) or "checklist"
    scaffold: str = "react"


@dataclass
class RetrievedDocument:
    """검색된 문서"""

    doc_id: str
    source: str  # ssc_sepsis, aha_chest_pain, kdigo_ckd
    content: str
    score: float
    recommendation_id: str | None = None
    recommendation_text: str | None = None
    strength: str | None = None


class BM25Index:
    """BM25 검색 인덱스"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: list[dict[str, Any]] = []
        self.doc_freqs: dict[str, int] = defaultdict(int)
        self.doc_lengths: list[int] = []
        self.avg_doc_length: float = 0
        self.term_docs: dict[str, list[int]] = defaultdict(list)

    def _tokenize(self, text: str) -> list[str]:
        """텍스트 토큰화"""
        text = text.lower()
        # 알파벳, 숫자, 일부 의료 용어 유지
        tokens = re.findall(r"\b[a-z0-9]+\b", text)
        return tokens

    def add_documents(self, documents: list[dict[str, Any]]):
        """문서 인덱싱"""
        for doc in documents:
            doc_idx = len(self.documents)
            self.documents.append(doc)

            tokens = self._tokenize(doc.get("content", ""))
            self.doc_lengths.append(len(tokens))

            # 문서별 단어 빈도
            seen_terms = set()
            for token in tokens:
                if token not in seen_terms:
                    self.doc_freqs[token] += 1
                    self.term_docs[token].append(doc_idx)
                    seen_terms.add(token)

        if self.doc_lengths:
            self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths)

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        """BM25 검색"""
        query_tokens = self._tokenize(query)
        scores: dict[int, float] = defaultdict(float)

        N = len(self.documents)
        for token in query_tokens:
            if token not in self.doc_freqs:
                continue

            df = self.doc_freqs[token]
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)

            for doc_idx in self.term_docs[token]:
                # 문서 내 단어 빈도 계산
                doc_tokens = self._tokenize(self.documents[doc_idx].get("content", ""))
                tf = doc_tokens.count(token)
                doc_len = self.doc_lengths[doc_idx]

                # BM25 스코어
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_length)
                scores[doc_idx] += idf * (numerator / denominator)

        # 상위 k개 반환
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_docs[:top_k]


class DenseIndex:
    """BGE-M3 기반 Dense Retrieval 인덱스"""

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model_name = model_name
        self.model = None
        self.index = None
        self.documents: list[dict[str, Any]] = []
        self._initialized = False

    def _load_model(self):
        """BGE-M3 모델 로드 (lazy loading)"""
        if self._initialized:
            return

        try:
            from FlagEmbedding import BGEM3FlagModel

            logger.info(f"Loading BGE-M3 model: {self.model_name}")
            self.model = BGEM3FlagModel(
                self.model_name,
                use_fp16=True,  # GPU 메모리 절약
                device="cuda" if self._check_cuda() else "cpu",
            )
            self._initialized = True
            logger.info("BGE-M3 model loaded successfully")
        except ImportError:
            logger.warning("FlagEmbedding not installed. Using sentence-transformers fallback.")
            try:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(self.model_name)
                self._initialized = True
                logger.info("sentence-transformers model loaded successfully")
            except ImportError:
                raise ImportError("Neither FlagEmbedding nor sentence-transformers installed")

    def _check_cuda(self) -> bool:
        """CUDA 사용 가능 여부 확인"""
        try:
            import torch

            return torch.cuda.is_available()
        except ImportError:
            return False

    def _encode(self, texts: list[str]) -> np.ndarray:
        """텍스트를 임베딩으로 변환"""
        self._load_model()

        if self.model is None:
            raise RuntimeError("Model not loaded - ensure FlagEmbedding or sentence-transformers is installed")

        try:
            # FlagEmbedding BGEM3FlagModel 사용
            from FlagEmbedding import BGEM3FlagModel

            if isinstance(self.model, BGEM3FlagModel):
                embeddings = self.model.encode(
                    texts,
                    batch_size=32,
                    max_length=512,
                )["dense_vecs"]
                return np.array(embeddings)
        except (ImportError, AttributeError):
            pass

        # sentence-transformers fallback
        embeddings = self.model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
        return np.array(embeddings)

    def add_documents(self, documents: list[dict[str, Any]]):
        """문서 인덱싱"""
        if not documents:
            return

        self.documents = documents

        # 문서 텍스트 추출
        texts = [doc.get("content", "") for doc in documents]

        # 임베딩 생성
        embeddings = self._encode(texts)

        # FAISS 인덱스 생성
        try:
            import faiss

            dimension = embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension)  # Inner Product (cosine similarity with normalized vectors)
            # float32로 변환 후 정규화 (FAISS 요구사항)
            embeddings_f32 = np.ascontiguousarray(embeddings.astype(np.float32))
            faiss.normalize_L2(embeddings_f32)
            assert self.index is not None
            self.index.add(embeddings_f32)
            logger.info(f"FAISS index created with {len(documents)} documents, dim={dimension}")
        except ImportError:
            logger.warning("FAISS not installed, using numpy fallback")
            self.embeddings = embeddings

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        """Dense 검색"""
        if not self.documents:
            return []

        # 쿼리 임베딩
        query_embedding = self._encode([query])[0]

        if self.index is not None:
            # FAISS 검색
            import faiss

            query_vec = query_embedding.reshape(1, -1).astype(np.float32)
            faiss.normalize_L2(query_vec)
            scores, indices = self.index.search(query_vec, min(top_k, len(self.documents)))
            return [(int(idx), float(score)) for idx, score in zip(indices[0], scores[0]) if idx >= 0]
        else:
            # Numpy fallback
            query_vec = query_embedding / np.linalg.norm(query_embedding)
            similarities = np.dot(self.embeddings, query_vec)
            top_indices = np.argsort(similarities)[::-1][:top_k]
            return [(int(idx), float(similarities[idx])) for idx in top_indices]


class CPGDocumentStore:
    """CPG 문서 저장소 - BM25, Dense, Hybrid Retrieval 지원"""

    def __init__(
        self,
        cpg_sources_path: str | None = None,
        use_dense: bool = False,
        use_hybrid: bool = False,
        embedding_model: str = "BAAI/bge-m3",
        dense_weight: float = 0.5,
    ):
        self.cpg_sources_path = Path(cpg_sources_path) if cpg_sources_path else self._default_path()
        self.documents: list[dict[str, Any]] = []
        self.bm25_index = BM25Index()
        self.dense_index: DenseIndex | None = None
        self.use_dense = use_dense or use_hybrid
        self.use_hybrid = use_hybrid
        self.dense_weight = dense_weight
        self._loaded = False

        if self.use_dense:
            self.dense_index = DenseIndex(model_name=embedding_model)

    def _default_path(self) -> Path:
        """기본 CPG 소스 경로"""
        return Path(__file__).parent.parent / "cpg_sources"

    def load(self):
        """CPG 문서 로드 및 인덱싱"""
        if self._loaded:
            return

        parsed_files = list(self.cpg_sources_path.glob("*.parsed.json"))

        for parsed_file in parsed_files:
            source_name = self._get_source_name(parsed_file.name)

            with open(parsed_file, encoding="utf-8") as f:
                data = json.load(f)

            # 추천사항 인덱싱
            for rec in data.get("recommendations", []):
                doc = {
                    "doc_id": f"{source_name}_{rec.get('recommendation_id', 'unknown')}",
                    "source": source_name,
                    "content": rec.get("text", ""),
                    "recommendation_id": rec.get("recommendation_id"),
                    "recommendation_text": rec.get("text"),
                    "strength": rec.get("strength"),
                    "page": rec.get("page"),
                    "type": "recommendation",
                }
                self.documents.append(doc)

            # 테이블 인덱싱
            for table in data.get("tables", []):
                table_content = self._table_to_text(table)
                if table_content:
                    doc = {
                        "doc_id": f"{source_name}_table_{table.get('table_id', 'unknown')}",
                        "source": source_name,
                        "content": table_content,
                        "type": "table",
                        "page": table.get("page"),
                    }
                    self.documents.append(doc)

            # 키 섹션 인덱싱
            for section_name, section_content in data.get("key_sections", {}).items():
                if section_content:
                    doc = {
                        "doc_id": f"{source_name}_section_{section_name}",
                        "source": source_name,
                        "content": section_content[:2000],  # 섹션은 길 수 있으므로 제한
                        "type": "section",
                        "section_name": section_name,
                    }
                    self.documents.append(doc)

        # BM25 인덱싱
        self.bm25_index.add_documents(self.documents)

        # Dense 인덱싱 (필요한 경우)
        if self.use_dense and self.dense_index:
            logger.info("Building Dense index with BGE-M3...")
            self.dense_index.add_documents(self.documents)
            logger.info("Dense index built successfully")

        self._loaded = True
        logger.info(f"CPGDocumentStore loaded {len(self.documents)} documents")

    # 파일명 키워드 → source_name 매핑 (순서 중요: 구체적 키워드 먼저)
    _SOURCE_NAME_MAP = [
        ("Sepsis", "ssc_sepsis"),
        ("Chest-Pain", "aha_chest_pain"),
        ("Contrast-AKI", "kdigo_contrast_aki"),
        ("AKI", "kdigo_aki"),
        ("Heart-Failure", "aha_heart_failure"),
        ("Stroke", "aha_stroke"),
        ("DKA", "ada_dka"),
        ("AF-Guidelines", "esc_af"),
        ("CAP", "ats_idsa_cap"),
        ("COPD", "gold_copd"),
        ("GOLD", "gold_copd"),
        ("GI-Bleeding", "acg_gi_bleeding"),
        ("Hypertensive", "aha_hypertensive"),
        ("PE-Guidelines", "esc_pe"),
        ("Anaphylaxis", "wao_anaphylaxis"),
        ("ACLS", "aha_acls"),
        ("Status-Epilepticus", "aes_status_epilepticus"),
        ("Asthma", "gina_asthma"),
        ("GINA", "gina_asthma"),
        ("Meningitis", "idsa_meningitis"),
        ("Toxicology", "aact_toxicology"),
        ("AACT", "aact_toxicology"),
        ("Burn", "aba_burn"),
        ("Transfusion", "aabb_transfusion"),
        ("AABB", "aabb_transfusion"),
        ("Obstetric", "acog_obstetric"),
        ("ACOG", "acog_obstetric"),
        ("PALS", "aha_pals"),
        ("Pediatric", "aha_pals"),
        ("Agitation", "apa_agitation"),
        ("Universal", "universal_safety"),
    ]

    def _get_source_name(self, filename: str) -> str:
        """파일명에서 소스 이름 추출"""
        for keyword, source_name in self._SOURCE_NAME_MAP:
            if keyword in filename:
                return source_name
        return filename.replace(".parsed.json", "").lower().replace("-", "_")

    def _table_to_text(self, table: dict) -> str:
        """테이블을 텍스트로 변환"""
        parts = []
        if table.get("title"):
            parts.append(f"Table: {table['title']}")

        data = table.get("data", [])
        for row in data[:20]:  # 최대 20행
            if isinstance(row, list):
                parts.append(" | ".join(str(cell) for cell in row))
            elif isinstance(row, dict):
                parts.append(" | ".join(f"{k}: {v}" for k, v in row.items()))

        return "\n".join(parts)

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedDocument]:
        """쿼리에 대한 관련 문서 검색

        검색 모드:
        - BM25 only (기본): 전통적인 키워드 기반 검색
        - Dense only: BGE-M3 임베딩 기반 의미 검색
        - Hybrid: BM25 + Dense 점수 결합
        """
        self.load()

        if self.use_hybrid and self.dense_index:
            # Hybrid Retrieval: BM25 + Dense 점수 결합
            results = self._hybrid_search(query, top_k)
        elif self.use_dense and self.dense_index and not self.use_hybrid:
            # Dense only: BGE-M3 기반 의미 검색
            results = self.dense_index.search(query, top_k)
        else:
            # BM25 only: 키워드 기반 검색
            results = self.bm25_index.search(query, top_k)

        # P3 Fix: Normalize scores to [0, 1] range for consistency
        results = self._normalize_scores(results)

        retrieved = []
        for doc_idx, score in results:
            if doc_idx < 0 or doc_idx >= len(self.documents):
                continue
            doc = self.documents[doc_idx]
            retrieved.append(
                RetrievedDocument(
                    doc_id=doc["doc_id"],
                    source=doc["source"],
                    content=doc["content"],
                    score=score,
                    recommendation_id=doc.get("recommendation_id"),
                    recommendation_text=doc.get("recommendation_text"),
                    strength=doc.get("strength"),
                )
            )

        return retrieved

    def _normalize_scores(self, results: list[tuple[int, float]]) -> list[tuple[int, float]]:
        """P3 Fix: Normalize retrieval scores to [0, 1] range.

        This ensures consistent score interpretation across different
        retrieval methods (BM25, Dense, Hybrid) and queries.
        """
        if not results:
            return results

        scores = [score for _, score in results]
        min_score = min(scores)
        max_score = max(scores)

        # Avoid division by zero
        if max_score == min_score:
            return [(doc_idx, 1.0) for doc_idx, _ in results]

        normalized = [(doc_idx, (score - min_score) / (max_score - min_score)) for doc_idx, score in results]
        return normalized

    def _hybrid_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Hybrid 검색: BM25와 Dense 점수를 결합

        점수 정규화 후 가중 평균:
        score = (1 - dense_weight) * bm25_norm + dense_weight * dense_norm
        """
        # BM25 검색 (더 많이 가져와서 융합)
        bm25_results = self.bm25_index.search(query, top_k * 2)
        # Dense 검색
        if self.dense_index is None:
            return bm25_results[:top_k]  # Fallback to BM25 only
        dense_results = self.dense_index.search(query, top_k * 2)

        # 점수 정규화를 위한 min-max 계산
        bm25_scores = {idx: score for idx, score in bm25_results}
        dense_scores = {idx: score for idx, score in dense_results}

        # Min-max 정규화
        def normalize_scores(scores: dict[int, float]) -> dict[int, float]:
            if not scores:
                return {}
            values = list(scores.values())
            min_val, max_val = min(values), max(values)
            if max_val == min_val:
                return dict.fromkeys(scores, 1.0)
            return {k: (v - min_val) / (max_val - min_val) for k, v in scores.items()}

        bm25_norm = normalize_scores(bm25_scores)
        dense_norm = normalize_scores(dense_scores)

        # 모든 후보 문서에 대해 융합 점수 계산
        all_doc_ids = set(bm25_scores.keys()) | set(dense_scores.keys())

        combined_scores = {}
        for doc_idx in all_doc_ids:
            bm25_score = bm25_norm.get(doc_idx, 0.0)
            dense_score = dense_norm.get(doc_idx, 0.0)
            # 가중 평균
            combined = (1 - self.dense_weight) * bm25_score + self.dense_weight * dense_score
            combined_scores[doc_idx] = combined

        # 상위 k개 반환
        sorted_results = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]


class RAGAgent(BaseAgent):
    """RAG-only Baseline Agent: 강한 텍스트 베이스라인

    CGA-Bench 명세에 따른 구현:
    - CPG 문서 코퍼스에서 BM25 기반 검색
    - 검색된 컨텍스트 + 환자 상태로 LLM이 행동 생성
    - 구조화된 Action schema(JSON) 출력
    - Planning 모듈 없음 (단일 스텝 결정)
    - Constraint 검증 없음 (CPG-Engine, assessor_core 미사용)

    설계 원칙:
    이 에이전트는 "텍스트 검색만으로 얼마나 잘 수행할 수 있는가"를
    측정하기 위한 공정한 베이스라인입니다.

    제한 사항:
    1. cpg_engine/를 import하거나 사용하지 않음
    2. assessor_core/를 import하거나 사용하지 않음
    3. Planning 모듈 (PlannerAgent의 기능)을 사용하지 않음
    4. Constraint 검증 (forbidden/mandatory veto)을 사용하지 않음
    5. 다중 스텝 계획을 사용하지 않음 - 각 step은 독립적

    검증:
    get_constraint_verification() 메서드로 이러한 제약 준수를 확인할 수 있습니다.
    """

    def __init__(self, config: RAGConfig, llm_provider: BaseLLMProvider | None = None):
        super().__init__(config)
        self.rag_config = config

        # Document Store 초기화 (BM25, Dense, Hybrid 지원)
        self.document_store = CPGDocumentStore(
            cpg_sources_path=config.cpg_sources_path,
            use_dense=config.use_dense,
            use_hybrid=config.use_hybrid,
            embedding_model=config.embedding_model,
            dense_weight=config.dense_weight,
        )
        self._action_history: list[Action] = []
        # P3 Fix: Track completed action IDs efficiently for memory management
        self._completed_action_ids: set = set()
        self._max_history_size: int = 100  # Limit history to prevent memory leak

        # CGA_DEBUG_RAW_RESPONSE hook — ring buffer of raw LLM responses
        # captured at the moment an empty-actions warning fires. Emptied on
        # reset() so the samples are per-episode. Max 20 entries to bound
        # JSON size.
        self._empty_raw_samples: list[dict] = []
        # CGA_CAPTURE_RAW=1 — full per-step (prompt, response, tokens, extracted)
        # buffer for re-scoring/reproducibility. Flushed by the runner to a
        # sibling .raw.jsonl file alongside the episode JSON. Per-episode.
        self._raw_capture_buffer: list[dict] = []
        self._llm_call_counter: int = 0
        # Consecutive LLM empty counter — referenced from _generate_actions;
        # also re-initialised in reset().
        self._consecutive_llm_empty: int = 0
        # Consecutive endpoint (HTTP/connection) failure counter — used to
        # raise EndpointDeadError so the worker exits without writing rule
        # fallback episodes. Reset on any successful LLM call.
        self._consecutive_endpoint_errors: int = 0

        # Scaffold-level hint for base_agent.run_episode: when the agent
        # detects that the latest empty-action return was caused by the LLM
        # proposing only already-completed actions (exhaustion/hallucination)
        # rather than by a genuinely empty model response, set this to
        # "agent_exhausted" so the resulting termination_reason separates the
        # two failure modes. Reset on each successful action production and
        # on episode reset().
        self._preferred_termination_reason: str | None = None

        # Alias map: canonical action-ID lookup for synonym normalisation
        # Loaded from cpg_model/action_alias_map.yaml (agent-side only;
        # cpg_engine/ and assessor_core/ never touch this file).
        self._alias_reverse_map: dict[str, str] = {}
        self._alias_canonical_map: dict[str, list[str]] = {}
        self._load_action_alias_map()

        # Tier 3 fallback set: universal_clinical_safety.yaml allowed actions.
        # Used by _normalize_action_id to tag domain-independent general-ER
        # workup ids as GENERAL_WORKUP (scorer treats as no-op, not DEVIATION).
        # Design doc: docs/attack_gap_exp_exp/260421_three_tier_normalizer_design.md
        self._universal_safety_actions: set[str] = set()
        self._load_universal_safety_actions()

        # LLM Provider 초기화
        self.llm_provider: BaseLLMProvider | None = None
        if llm_provider:
            self.llm_provider = llm_provider
        elif config.use_llm:
            llm_config = LLMConfig(
                backend=config.llm_backend,
                model=config.llm_model,
                temperature=config.temperature,
                base_url=config.base_url,
                api_key=config.api_key,
                seed=config.llm_seed,
            )
            self.llm_provider = LLMProviderFactory.create(llm_config)

    def _load_action_alias_map(self) -> None:
        """Load cpg_model/action_alias_map.yaml into reverse and canonical maps.

        The alias map is the agent-side source of truth for synonym normalisation.
        It is intentionally NOT loaded by cpg_engine/ or assessor_core/ (scoring
        isolation: CLAUDE.md §Architecture).

        Falls back to empty dicts (with a warning) if the file is missing so that
        existing tests that don't use the alias map continue to pass.
        """
        # Resolve path relative to this file: agent_runner/ -> cga_bench/
        alias_map_path = Path(__file__).resolve().parents[1] / "cpg_model" / "action_alias_map.yaml"
        if not alias_map_path.is_file():
            logger.warning(
                "Action alias map not found at %s — synonym normalisation disabled. "
                "Run scripts/tools/build_canonical_action_map.py to generate it.",
                alias_map_path,
            )
            return
        try:
            import yaml as _yaml  # local import keeps top-level imports clean

            with open(alias_map_path) as fh:
                data = _yaml.safe_load(fh)
            self._alias_canonical_map = data.get("canonical_map") or {}
            self._alias_reverse_map = data.get("reverse_map") or {}
            logger.debug(
                "Loaded action alias map: %d canonical groups, %d variants",
                len(self._alias_canonical_map),
                len(self._alias_reverse_map),
            )
        except Exception:
            logger.warning("Failed to load action alias map — synonym normalisation disabled.", exc_info=True)

    def _load_universal_safety_actions(self) -> None:
        """Load cpg_model/graphs/universal_clinical_safety.yaml action set.

        Populates ``self._universal_safety_actions`` with the union of
        allowed_actions, mandatory_actions and action_categories across every
        node of the universal_clinical_safety graph. Used by Tier 3 of
        ``_normalize_action_id`` as a domain-independent general-ER workup
        fallback that avoids flagging clinically defensible actions as
        DEVIATION when they fall outside the specific scenario's graph.

        Agent-side isolation: this method does NOT import cpg_engine/ or
        assessor_core/. The YAML is treated as a flat data file.
        """
        graph_path = Path(__file__).resolve().parents[1] / "cpg_model" / "graphs" / "universal_clinical_safety.yaml"
        if not graph_path.is_file():
            logger.warning(
                "universal_clinical_safety.yaml not found at %s — Tier 3 general-ER fallback disabled.",
                graph_path,
            )
            return
        try:
            import yaml as _yaml

            with open(graph_path) as fh:
                graph = _yaml.safe_load(fh) or {}
            for _nid, node in (graph.get("nodes") or {}).items():
                for key in ("allowed_actions", "mandatory_actions"):
                    for a in node.get(key) or []:
                        self._universal_safety_actions.add(a)
            for _cat, lst in (graph.get("action_categories") or {}).items():
                for a in lst or []:
                    self._universal_safety_actions.add(a)
            logger.debug(
                "Loaded universal_clinical_safety: %d Tier-3 allowed actions",
                len(self._universal_safety_actions),
            )
        except Exception:
            logger.warning(
                "Failed to load universal_clinical_safety.yaml — Tier 3 general-ER fallback disabled.",
                exc_info=True,
            )

    def reset(self):
        """에이전트 상태 리셋"""
        self._action_history = []
        # P3 Fix: Clear completed action IDs set
        self._completed_action_ids = set()
        self.metrics = AgentMetrics()
        self._consecutive_llm_empty = 0  # Track consecutive LLM empty responses
        # NOTE: do NOT reset _consecutive_endpoint_errors here. The counter
        # must accumulate across episodes within a worker lifetime so the
        # 5-strikes threshold can fire. Per-episode reset would mask a dead
        # endpoint (each episode starts at 0 and gets just 1 increment).
        # _consecutive_endpoint_errors is reset only on a successful LLM call
        # (see _generate_actions success path).
        self._preferred_termination_reason = None  # Reset per-episode hint

        # CGA_DEBUG_RAW_RESPONSE hook — per-episode debug buffer.
        self._empty_raw_samples = []
        # CGA_CAPTURE_RAW per-episode buffer (clean slate per episode).
        self._raw_capture_buffer = []
        self._llm_call_counter = 0

    def _capture_raw_call(
        self,
        phase: str,
        messages: list,
        response_raw: str,
        tokens_in: int,
        tokens_out: int,
        thinking: str | None,
        extracted: object,
    ) -> None:
        """Append one (prompt, response) pair to per-episode raw buffer.

        Activated only when env CGA_CAPTURE_RAW=1. Records every LLM call
        emitted by the agent for later re-scoring / reproducibility analysis.
        """
        from datetime import datetime as _dt
        import os as _os

        if not _os.environ.get("CGA_CAPTURE_RAW"):
            return
        try:
            serialized_msgs = [
                {"role": getattr(m, "role", None), "content": getattr(m, "content", str(m))} for m in messages
            ]
        except Exception:
            serialized_msgs = [str(messages)]
        self._raw_capture_buffer.append(
            {
                "step": self._llm_call_counter,
                "ts": _dt.utcnow().isoformat() + "Z",
                "phase": phase,
                "prompt_messages": serialized_msgs,
                "response_raw": response_raw or "",
                "tokens": {"in": int(tokens_in or 0), "out": int(tokens_out or 0)},
                "thinking": thinking or "",
                "extracted": extracted
                if isinstance(extracted, (dict, list, str, int, float, bool, type(None)))
                else str(extracted),
            }
        )
        self._llm_call_counter += 1

    def decide(self, observation: Observation) -> list[Action]:
        """관측을 받아 행동 결정

        RAG 방식:
        1. 환자 상태로 검색 쿼리 생성
        2. CPG 문서에서 관련 추천사항 검색
        3. 검색된 컨텍스트 기반으로 행동 생성
        """
        # 1. 검색 쿼리 생성
        query = self._build_query(observation)

        # 2. 관련 문서 검색
        retrieved_docs = self.document_store.retrieve(query, self.rag_config.top_k)

        # 3. 컨텍스트 기반 행동 생성
        actions = self._generate_actions(observation, retrieved_docs)

        # LLM 호출 추적 (실제 LLM 사용 시)
        self.metrics.total_llm_calls += 1

        return actions

    def _get_visible_state(self, observation: Observation) -> dict[str, Any]:
        """Observation에서 visible_state 추출"""
        return observation.visible_state

    # Domain hint mapping: working_diagnosis → guideline keywords for RAG retrieval
    _DOMAIN_HINTS = {
        "aki": "acute kidney injury AKI KDIGO creatinine nephrotoxic renal",
        "contrast_aki": "contrast-associated AKI KDIGO eGFR hydration nephroprotection renal",
        "dka": "diabetic ketoacidosis DKA ADA insulin potassium anion gap",
        "dka_moderate": "diabetic ketoacidosis DKA ADA insulin potassium fluid resuscitation",
        "septic_shock": "sepsis septic shock SSC hour-1 bundle antibiotics lactate vasopressor",
        "sepsis": "sepsis SSC hour-1 bundle antibiotics lactate blood culture",
        "stemi": "STEMI myocardial infarction AHA chest pain ECG cath lab PCI",
        "nstemi": "NSTEMI ACS troponin antiplatelet AHA chest pain",
        "ischemic_stroke": "ischemic stroke AHA tPA thrombolysis NIHSS thrombectomy",
        "hemorrhagic_stroke": "hemorrhagic stroke intracerebral hemorrhage blood pressure reversal",
        "hfref": "heart failure HFrEF GDMT beta-blocker ACE ARB diuretic",
        "copd_exacerbation": "COPD exacerbation GOLD bronchodilator steroids NIV",
        "pneumonia": "community-acquired pneumonia CAP antibiotics CURB-65",
        "gi_bleeding": "gastrointestinal bleeding endoscopy PPI transfusion hemodynamic",
        "pulmonary_embolism": "pulmonary embolism PE anticoagulation CTPA heparin",
        "atrial_fibrillation": "atrial fibrillation AF rate control rhythm anticoagulation",
        "hypertensive_emergency": "hypertensive emergency IV antihypertensive target organ damage",
    }

    def _build_query(self, observation: Observation) -> str:
        """환자 상태에서 검색 쿼리 생성 (domain hint 포함)"""
        parts = []

        state = self._get_visible_state(observation)

        # 주 호소
        chief_complaint = state.get("chief_complaint", "")
        if chief_complaint:
            parts.append(chief_complaint)

        # 진단 + domain hint
        diagnosis = state.get("working_diagnosis", "")
        if diagnosis:
            parts.append(diagnosis)
            # Domain hint: 진단명에서 관련 가이드라인 키워드 추가
            diag_lower = diagnosis.lower().replace(" ", "_")
            hint = self._DOMAIN_HINTS.get(diag_lower, "")
            if not hint:
                # Partial match
                for key, val in self._DOMAIN_HINTS.items():
                    if key in diag_lower or diag_lower in key:
                        hint = val
                        break
            if hint:
                parts.append(hint)

        # 활력징후 기반 키워드
        vitals = state.get("vitals", {})
        if vitals:
            sbp = vitals.get("blood_pressure_systolic")
            if sbp and sbp < 90:
                parts.append("hypotension shock")
            hr = vitals.get("heart_rate")
            if hr and hr > 100:
                parts.append("tachycardia")
            rr = vitals.get("respiratory_rate")
            if rr and rr > 20:
                parts.append("tachypnea")
            spo2 = vitals.get("oxygen_saturation")
            if spo2 and spo2 < 94:
                parts.append("hypoxia")

        # 검사 결과 기반 키워드
        lab_results = state.get("lab_results", [])
        for lab in lab_results:
            test_code = (lab.get("test_code") or "").lower()
            raw_value = lab.get("value", 0)
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue  # "pending" 등 비숫자 값은 건너뜀
            if "lactate" in test_code and value > 2:
                parts.append("elevated lactate sepsis")
            if "troponin" in test_code and value > 0.04:
                parts.append("elevated troponin STEMI myocardial infarction")
            if "creatinine" in test_code and value > 1.5:
                parts.append("renal impairment kidney")

        # Imaging 결과에서 ECG 검색
        imaging_results = state.get("imaging_results", [])
        for img in imaging_results:
            if "ecg" in str(img).lower():
                ecg_result = str(img)
                parts.append(ecg_result)
                if "st elevation" in ecg_result.lower():
                    parts.append("STEMI acute coronary syndrome")
                if "inferior" in ecg_result.lower():
                    parts.append("inferior wall infarction right ventricle")

        return " ".join(parts)

    def _generate_actions(self, observation: Observation, retrieved_docs: list[RetrievedDocument]) -> list[Action]:
        """검색된 문서 기반 행동 생성

        LLM 사용 가능 시 LLM 호출, 아니면 규칙 기반 폴백
        """
        state = self._get_visible_state(observation)
        current_time = observation.timestamp_minutes
        # P3 Fix: Use efficient set instead of recomputing from list
        completed_action_ids = self._completed_action_ids

        # Available actions from observation (for validation)
        # P1 Fix: 직접 접근하여 타입 안전성 확보, 빈 리스트 경고
        available_actions = observation.available_actions
        if not available_actions:
            logger.warning(
                "available_actions is empty - strict action filtering disabled. "
                "This may allow deviation violations. Check environment configuration."
            )

        # LLM 사용 가능 시 LLM으로 행동 생성
        # P2 Fix: Add retry logic for transient LLM failures
        max_consecutive_llm_empty = (
            10  # After 10 consecutive empty LLM calls, return empty to trigger early termination
        )
        # v6 endpoint-death threshold: after this many consecutive HTTP/connection
        # failures, raise EndpointDeadError so the worker can exit without writing
        # rule-fallback episodes (which would silently contaminate the dataset).
        max_consecutive_endpoint_errors = 5
        if self.llm_provider and self.rag_config.use_llm:
            # Check if LLM is stuck in empty loop — skip LLM entirely
            if self._consecutive_llm_empty >= max_consecutive_llm_empty:
                logger.warning(
                    f"LLM stuck: {self._consecutive_llm_empty} consecutive empty responses, "
                    f"returning empty to trigger episode termination"
                )
                return []
            # v6 endpoint-death gate
            if getattr(self, "_consecutive_endpoint_errors", 0) >= max_consecutive_endpoint_errors:
                from cga_bench.agent_runner.errors import EndpointDeadError

                raise EndpointDeadError(
                    f"endpoint failed {self._consecutive_endpoint_errors} times consecutively "
                    f"(threshold {max_consecutive_endpoint_errors}); aborting worker"
                )

            # Total LLM attempts lowered 2 -> 1 for full_706_v6 (2026-04-22).
            # Rationale: once the Task-2 agent_exhausted / agent_completed split
            # (commit 68395d2c) landed, the main residual "empty" cause was the
            # LLM re-proposing already-completed actions — retrying in-scope
            # does not produce fresh proposals, it just pays another LLM call
            # before falling through to rule fallback. Keeping the single
            # attempt saves ~1 call per empty step.
            max_llm_retries = 1
            last_error = None

            for attempt in range(max_llm_retries):
                try:
                    actions = self._generate_actions_with_llm(
                        observation, retrieved_docs, state, current_time, completed_action_ids
                    )
                    # 토큰 사용량 추적 (Budget-matched 평가용)
                    self.metrics.total_tokens += self.llm_provider.get_total_tokens_from_last_call()
                    if actions:
                        self._consecutive_llm_empty = 0  # Reset on success
                        self._consecutive_endpoint_errors = 0  # Endpoint clearly alive
                        # Clear exhaustion hint: model recovered with fresh actions,
                        # so any earlier "agent_exhausted" signal is stale.
                        self._preferred_termination_reason = None
                        self._add_to_action_history(actions)
                        return actions
                    # P2 Fix: Empty actions - retry with warning
                    logger.warning(f"LLM returned empty actions (attempt {attempt + 1}/{max_llm_retries})")
                    # CGA_DEBUG_RAW_RESPONSE hook — snapshot the raw LLM
                    # content so `diagnose_empty_actions.py` and downstream
                    # analysis can see exactly what the model said when it
                    # returned an empty-actions set.
                    import os as _os

                    if _os.environ.get("CGA_DEBUG_RAW_RESPONSE") and len(self._empty_raw_samples) < 20:
                        raw = getattr(self.llm_provider, "_last_raw_content", "") or ""
                        self._empty_raw_samples.append(
                            {
                                "path": "llm_rejected",
                                "llm_call_index": self._llm_call_counter,
                                "attempt": attempt,
                                "completed_count": len(self._completed_action_ids),
                                "raw_preview": raw[:2000],
                                "raw_len": len(raw),
                            }
                        )
                    self._llm_call_counter += 1
                    if attempt < max_llm_retries - 1:
                        continue  # Retry
                    self._consecutive_llm_empty += 1
                    break  # Fall through to rule-based
                except Exception as e:
                    last_error = e
                    # Detect endpoint-level failures (connection refused, 5xx,
                    # timeout, DNS) so the worker can exit cleanly after enough
                    # consecutive hits. JSON-parse errors are NOT counted here
                    # — they keep the existing rule-fallback path.
                    err_text = repr(e).lower()
                    endpoint_signals = (
                        "apiconnectionerror",
                        "apitimeouterror",
                        "internal server error",
                        "connection refused",
                        "connection reset",
                        "name or service not known",
                        "remote disconnected",
                        "max retries exceeded",
                        "service unavailable",
                        "503",
                        "502",
                        "504",
                    )
                    if any(s in err_text for s in endpoint_signals):
                        self._consecutive_endpoint_errors += 1
                        logger.warning(
                            "Endpoint failure %d/5: %s",
                            self._consecutive_endpoint_errors,
                            type(e).__name__,
                        )
                    logger.warning(f"LLM action generation failed (attempt {attempt + 1}/{max_llm_retries}): {e}")
                    if attempt < max_llm_retries - 1:
                        continue  # Retry

            if last_error:
                self._consecutive_llm_empty += 1
                logger.warning("All LLM attempts failed, falling back to rule-based")

        # 규칙 기반 폴백 (with available_actions validation)
        actions = self._generate_actions_rule_based(
            retrieved_docs, state, current_time, completed_action_ids, available_actions
        )

        # Bug 6 fix: filter out already-completed actions from rule-based fallback.
        # If rule-based returns only already-completed actions, treat as empty
        # to allow consecutive_empty counter in base_agent to trigger termination.
        if actions:
            new_actions = [a for a in actions if a.action_id not in self._completed_action_ids]
            if not new_actions:
                logger.warning("Rule-based fallback returned only already-completed actions, treating as empty")
                # Flag to base_agent that this empty return is exhaustion-induced
                # (rule fallback could only propose already-completed actions),
                # not a genuine empty LLM response.
                self._preferred_termination_reason = "agent_exhausted"
                import os as _os

                if _os.environ.get("CGA_DEBUG_RAW_RESPONSE") and len(self._empty_raw_samples) < 20:
                    self._empty_raw_samples.append(
                        {
                            "path": "rule_fallback",
                            "source": "rule_fallback_already_completed",
                            "fallback_input": [a.action_id for a in actions],
                            "llm_attempted": self._consecutive_llm_empty > 0,
                            "last_llm_raw": getattr(self.llm_provider, "_last_raw_content", "") or "",
                        }
                    )
                return []
            # Rule fallback produced fresh actions — clear stale exhaustion hint
            # set earlier in this decide() by the LLM path so the signal
            # reflects the final returned state, not a superseded intermediate.
            self._preferred_termination_reason = None
            actions = new_actions
            self._add_to_action_history(actions)
            return actions

        # Rule fallback produced no actions at all. Do NOT clear the hint here
        # — if the LLM path earlier in this same decide() detected exhaustion
        # (completed-only hallucination), that signal should survive to the
        # termination check instead of being silently reset by the fact that
        # the rule scaffold happened to have nothing to add.
        self._add_to_action_history(actions)
        return actions

    def _add_to_action_history(self, actions: list[Action]):
        """P3 Fix: Add actions to history with memory management.

        Maintains both:
        - List of recent actions (bounded by _max_history_size)
        - Set of all completed action IDs (for deduplication)
        """
        for action in actions:
            # Always track in set (unbounded but small memory per ID)
            self._completed_action_ids.add(action.action_id)
            # Add to history list
            self._action_history.append(action)

        # Trim history if it exceeds max size (keep most recent)
        if len(self._action_history) > self._max_history_size:
            # Keep the most recent actions
            self._action_history = self._action_history[-self._max_history_size :]

    def _generate_actions_with_llm(
        self,
        observation: Observation,
        retrieved_docs: list[RetrievedDocument],
        state: dict[str, Any],
        current_time: float,
        completed_action_ids: set,
    ) -> list[Action]:
        """LLM을 사용하여 행동 생성"""
        if self.llm_provider is None:
            raise RuntimeError("LLM provider not initialized")
        # 컨텍스트 구성
        context_parts = ["## Retrieved Clinical Guidelines\n"]
        for i, doc in enumerate(retrieved_docs, 1):
            context_parts.append(f"### [{i}] {doc.source} (Score: {doc.score:.2f})")
            if doc.strength:
                context_parts.append(f"**Strength**: {doc.strength}")
            context_parts.append(doc.content[:500])
            context_parts.append("")

        context = "\n".join(context_parts)

        # 환자 상태 요약
        patient_summary = self._format_patient_state(state)

        # 완료된 행동 목록
        completed_str = ", ".join(completed_action_ids) if completed_action_ids else "None"

        # Available Actions 구성 (CPG 노드 기반)
        # P1 Fix #4: 직접 접근하여 타입 안전성 확보
        available_actions = observation.available_actions
        # P1 Fix #5: CPG에서 동적 로드된 mandatory_actions 사용
        mandatory_actions = getattr(observation, "mandatory_actions", [])
        available_actions_str = self._format_available_actions(
            available_actions, completed_action_ids, mandatory_actions
        )

        # CPG Phase 프롬프트 결정
        phase_prompt = self._get_phase_prompt(state, available_actions, current_time)

        # Scaffold-conditional prompt construction
        scaffold = getattr(self.config, "scaffold", "react")
        is_checklist = scaffold == "checklist"
        is_direct = scaffold == "direct"
        is_tool_use = scaffold == "tool_use"

        # ── Tool-use scaffold: function-calling API ──
        if is_tool_use:
            return self._generate_actions_with_tool_use(
                observation,
                retrieved_docs,
                state,
                current_time,
                completed_action_ids,
                available_actions,
                mandatory_actions,
                context,
                patient_summary,
            )

        if is_direct:
            # Direct scaffold: single-shot, output all actions at once, no reasoning
            user_prompt = f"""## Patient State
{patient_summary}

## Time: {current_time} minutes

{available_actions_str}

=== ALREADY DONE ===
{completed_str}
====================

Output ALL clinically indicated actions as a single JSON array.
{{"actions": [{{"action_id": "exact_id_from_list", "action_type": "type", "justification": "brief"}}]}}"""

            sys_prompt = DIRECT_SYSTEM_PROMPT
        elif is_checklist:
            # Checklist scaffold: minimal reasoning, direct action execution
            user_prompt = f"""## Patient State
{patient_summary}

## Time: {current_time} minutes

{available_actions_str}

{context}

=== ALREADY DONE — DO NOT REPEAT ===
{completed_str}
====================================

Output JSON with 1-3 NEW actions (not in the above list).
{{"actions": [{{"action_id": "exact_id_from_list", "action_type": "type", "justification": "brief"}}]}}"""

            sys_prompt = CHECKLIST_SYSTEM_PROMPT
        else:
            # React scaffold (default): full reasoning with phase prompts
            if available_actions_str:
                action_instructions = """INSTRUCTIONS:
1. Use EXACT action_id strings from "Available Actions" - copy them exactly
2. Complete MANDATORY actions (marked with ★) FIRST before optional ones
3. Recommend 1-3 NEW actions per step, prioritizing the most urgent

IMPORTANT: Do NOT return an empty actions list.
After mandatory actions, choose from optional actions based on clinical need:
- Additional labs, monitoring, imaging, reassessments are almost always indicated.
- A stable patient still needs: serial vitals, trending labs, secondary workup.
- If uncertain, choose monitoring or reassessment actions.
The action_id MUST be an EXACT COPY from the available list."""
            else:
                action_instructions = """INSTRUCTIONS:
1. Based on the clinical guidelines above, identify actions the patient needs
2. Use descriptive action_id strings in snake_case (e.g., "order_cbc", "give_medication_X", "assess_bleeding")
3. Recommend 1-3 NEW actions per step, prioritizing the most urgent

IMPORTANT: Do NOT return an empty actions list.
Consider these categories: labs, imaging, medications, assessments, monitoring, consultations.
- A stable patient still needs: serial vitals, trending labs, secondary workup.
- If uncertain, choose monitoring or reassessment actions."""

            user_prompt = f"""## Current Patient State
{patient_summary}

## Time Since Arrival
{current_time} minutes

{phase_prompt}

{available_actions_str}

{context}

## Task
Based on the patient state and retrieved guidelines, recommend the NEXT clinical actions.

{action_instructions}

=== ALREADY DONE — DO NOT REPEAT THESE ===
{completed_str}
===========================================

Respond with JSON ONLY. Include ONLY actions NOT in the above list.
{{"actions": [{{"action_id": "descriptive_snake_case_id", "action_type": "type", "justification": "reason"}}]}}"""

            sys_prompt = CLINICAL_SYSTEM_PROMPT

        messages = [
            LLMMessage(role="system", content=sys_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        # LLM 호출
        result = self.llm_provider.complete_json(messages, ACTION_RECOMMENDATION_SCHEMA)
        # Raw capture (CGA_CAPTURE_RAW=1) — record (prompt, response, tokens)
        # for downstream re-scoring / reproducibility analysis.
        _usage = getattr(self.llm_provider, "_last_usage", {}) or {}
        _raw = getattr(self.llm_provider, "_last_raw_content", "") or ""
        if not _raw:
            # complete_json parses JSON before storing; fallback = serialize
            # the parsed result so re-extraction has the model's full output.
            try:
                _raw = json.dumps(result, ensure_ascii=False)
            except Exception:
                _raw = str(result)
        self._capture_raw_call(
            phase="react_json",
            messages=messages,
            response_raw=_raw,
            tokens_in=int(_usage.get("prompt_tokens", 0) or 0),
            tokens_out=int(_usage.get("completion_tokens", 0) or 0),
            thinking=getattr(self.llm_provider, "_last_thinking", "") or "",
            extracted=result,
        )

        # 결과 파싱
        actions = []
        # 배열 형태로 반환된 경우 처리
        reasoning_text = ""
        if isinstance(result, list):
            actions_data = result
        else:
            actions_data = result.get("actions", [])
            reasoning_text = str(result.get("reasoning", "")).lower()

        # Detect agent-declared completion: LLM explicitly returned an empty
        # actions list accompanied by reasoning that states all required
        # actions are done / the remaining options are not indicated. This is
        # a clinically valid stop signal (e.g. stable STEMI post-reperfusion
        # with no fluid-bolus indication) that should be split from
        # parse-failure "genuine empty" — both currently collapse to
        # ``consecutive_empty_actions`` without this hint.
        _AGENT_COMPLETED_MARKERS = (
            "already been completed",
            "already completed",
            "all mandatory actions",
            "all required actions",
            "no new actions",
            "no action required",
            "no further action",
            "no actions are required",
            "not indicated at this time",
            "nothing else is indicated",
        )
        if not actions_data and reasoning_text and any(m in reasoning_text for m in _AGENT_COMPLETED_MARKERS):
            self._preferred_termination_reason = "agent_completed"

        # Classify drops so base_agent can distinguish "agent proposed only
        # already-completed actions" (exhaustion/hallucination) from other
        # causes when actions ends up empty.
        already_completed_drops = 0

        for action_data in actions_data:
            action_id = action_data.get("action_id", "")
            # Ensure action_id is a string
            if isinstance(action_id, list):
                action_id = action_id[0] if action_id else ""
            action_id = str(action_id)

            # Normalize action_id against available actions via 3-tier pipeline.
            # Tier 4 guarantees a non-None return (tagged DEVIATION) so that
            # _generate_actions never returns [] just because of a lexical miss
            # — the scorer is the sole arbiter of DEVIATION penalties.
            normalized_id, semantic_tag = self._normalize_action_id(action_id, available_actions)
            if normalized_id is None:
                if available_actions:
                    logger.debug(f"Rejecting action '{action_id}' - engine reports no available_actions")
                    continue
            else:
                action_id = normalized_id

            if action_id in completed_action_ids:
                already_completed_drops += 1
                continue

            action_type_str = action_data.get("action_type", "")
            # Ensure action_type_str is a string
            if isinstance(action_type_str, list):
                action_type_str = action_type_str[0] if action_type_str else ""
            action_type_str = str(action_type_str)
            action_type = self._parse_action_type(action_type_str, action_id)
            raw_args = action_data.get("args", {})
            normalized_args = self._normalize_action_args(action_type, raw_args, action_type_str, action_id)

            actions.append(
                Action(
                    type=action_type,
                    action_id=action_id,
                    args=normalized_args,
                    timestamp_minutes=current_time,
                    justification=action_data.get("justification", "LLM recommendation"),
                    semantic_tag=semantic_tag,
                )
            )

        # If the LLM produced structurally-valid action proposals but every
        # single one was dropped because it was already completed, flag the
        # resulting empty return as exhaustion-induced rather than a genuine
        # empty LLM response. Requires at least one completed-drop so we don't
        # mis-classify the "no actions_data at all" case.
        if not actions and already_completed_drops > 0:
            self._preferred_termination_reason = "agent_exhausted"

        return actions[: self.config.max_actions_per_step]

    def _format_available_actions(
        self,
        available_actions: list[str],
        completed_action_ids: set,
        mandatory_actions: list[str] = None,  # P1 Fix: CPG에서 동적 로드된 mandatory actions
    ) -> str:
        """Available Actions 섹션을 포맷팅

        Args:
            available_actions: 현재 phase에서 가능한 모든 action_id 목록
            completed_action_ids: 이미 완료된 action_id set
            mandatory_actions: CPG에서 동적 로드된 필수 actions (deadline 있음)
        """
        if not available_actions:
            return ""

        parts = ["## Available Actions for Current Phase"]
        parts.append("⚠️ TIME-CRITICAL: Complete mandatory actions within deadline!")
        parts.append("Each action takes ~5 minutes. Use EXACT action_id strings below.\n")

        # P1 Fix: mandatory_actions가 제공되면 그대로 사용, 아니면 빈 리스트
        mandatory_set = set(mandatory_actions) if mandatory_actions else set()

        mandatory = []
        optional = []

        for action in available_actions:
            if action in completed_action_ids:
                continue  # 이미 완료된 건 제외

            # P1 Fix: CPG에서 제공된 mandatory_actions 사용 (패턴 매칭 대신)
            if action in mandatory_set:
                mandatory.append(action)
            else:
                optional.append(action)

        # P1 Fix: mandatory_actions는 이미 우선순위 순서로 제공됨 (environment에서)
        # mandatory_actions 순서대로 정렬
        if mandatory_actions:

            def get_priority(action):
                try:
                    return mandatory_actions.index(action)
                except ValueError:
                    return len(mandatory_actions)

            mandatory.sort(key=get_priority)

        if mandatory:
            parts.append("### MANDATORY Actions (Complete these FIRST - deadline 60 min):")
            for action in mandatory:
                parts.append(f'  ★ "{action}"')
            parts.append("")

        if optional:
            parts.append("### Optional Actions:")
            for action in optional[:10]:  # 너무 많으면 제한
                parts.append(f'  ○ "{action}"')
            if len(optional) > 10:
                parts.append(f"  ... and {len(optional) - 10} more")
            parts.append("")

        # 사용 가능한 action_id 목록 요약 (LLM이 복사하기 쉽게)
        all_available = mandatory + optional[:10]
        if all_available:
            parts.append("### Valid action_id values (copy exactly):")
            parts.append(f"  {all_available}")
            parts.append("")

        return "\n".join(parts)

    # ── Tool-use scaffold helpers ──────────────────────────────

    @staticmethod
    def _sanitize_tool_name(action_id: str) -> str:
        """Sanitize action_id to valid function name ([a-zA-Z0-9_-])."""
        name = re.sub(r"[^a-zA-Z0-9_-]", "_", action_id)
        if not name or not name[0].isalpha():
            name = "act_" + name
        return name[:64]

    def _build_tool_definitions(
        self,
        available_actions: list[str],
        completed_action_ids: set,
        mandatory_actions: list[str] | None,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Build OpenAI-format tool definitions from available actions.

        Returns:
            (tools_list, name_to_action_id_map)
        """
        mandatory_set = set(mandatory_actions) if mandatory_actions else set()
        tools: list[dict[str, Any]] = []
        name_map: dict[str, str] = {}

        # Mandatory first, then optional (capped at 20 total)
        ordered = []
        for a in available_actions:
            if a not in completed_action_ids and a in mandatory_set:
                ordered.append((a, True))
        for a in available_actions:
            if a not in completed_action_ids and a not in mandatory_set:
                ordered.append((a, False))

        max_tools = 20
        for action_id, is_mandatory in ordered[:max_tools]:
            safe_name = self._sanitize_tool_name(action_id)
            name_map[safe_name] = action_id
            prefix = "MANDATORY - " if is_mandatory else ""
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": safe_name,
                        "description": f"{prefix}Execute clinical action: {action_id}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "justification": {
                                    "type": "string",
                                    "description": "Brief clinical reasoning for this action",
                                }
                            },
                            "required": ["justification"],
                        },
                    },
                }
            )

        return tools, name_map

    def _generate_actions_with_tool_use(
        self,
        observation: Observation,
        retrieved_docs: list[RetrievedDocument],
        state: dict[str, Any],
        current_time: float,
        completed_action_ids: set,
        available_actions: list[str],
        mandatory_actions: list[str],
        context: str,
        patient_summary: str,
    ) -> list[Action]:
        """Generate actions using OpenAI-compatible function-calling API."""
        tools, name_map = self._build_tool_definitions(
            available_actions,
            completed_action_ids,
            mandatory_actions,
        )

        if not tools:
            logger.warning("Tool-use scaffold: no tools available, falling back to react")
            return []

        completed_str = ", ".join(completed_action_ids) if completed_action_ids else "None"

        user_prompt = f"""## Patient State
{patient_summary}

## Time: {current_time} minutes

{context}

## Already completed actions (DO NOT repeat):
{completed_str}

Select and call the appropriate clinical action functions.
Call MANDATORY functions first, then optional ones based on clinical need.
ALWAYS call at least one function."""

        messages = [
            LLMMessage(role="system", content=TOOL_USE_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]

        # Call LLM with tools
        tool_calls = self.llm_provider.complete_with_tools(messages, tools)
        # Raw capture (CGA_CAPTURE_RAW=1)
        _usage = getattr(self.llm_provider, "_last_usage", {}) or {}
        _raw = getattr(self.llm_provider, "_last_raw_content", "") or ""
        if not _raw:
            try:
                _raw = json.dumps(tool_calls, ensure_ascii=False)
            except Exception:
                _raw = str(tool_calls)
        self._capture_raw_call(
            phase="react_tools",
            messages=messages,
            response_raw=_raw,
            tokens_in=int(_usage.get("prompt_tokens", 0) or 0),
            tokens_out=int(_usage.get("completion_tokens", 0) or 0),
            thinking=getattr(self.llm_provider, "_last_thinking", "") or "",
            extracted=tool_calls,
        )

        actions: list[Action] = []
        already_completed_drops = 0
        for tc in tool_calls:
            fn_name = tc["name"]
            args = tc.get("arguments", {})
            justification = args.get("justification", "tool-use action")

            # Map sanitized name back to original action_id
            action_id = name_map.get(fn_name, fn_name)

            # Normalise via 3-tier pipeline (same as other scaffolds).
            # Tier 4 DEVIATION tag replaces the old silent-drop behaviour.
            normalized_id, semantic_tag = self._normalize_action_id(action_id, available_actions)
            if normalized_id is None:
                if available_actions:
                    logger.debug(f"Tool-use: rejecting '{action_id}' - engine reports no available_actions")
                    continue
            else:
                action_id = normalized_id

            if action_id in completed_action_ids:
                already_completed_drops += 1
                continue

            action_type = self._parse_action_type("", action_id)
            normalized_args = self._normalize_action_args(action_type, {}, "", action_id)
            actions.append(
                Action(
                    type=action_type,
                    action_id=action_id,
                    args=normalized_args,
                    timestamp_minutes=current_time,
                    justification=justification,
                    semantic_tag=semantic_tag,
                )
            )

        # Flag exhaustion when tool-use call emitted function calls but every
        # one was dropped as already-completed — same signal as the JSON path.
        if not actions and already_completed_drops > 0:
            self._preferred_termination_reason = "agent_exhausted"

        return actions[: self.config.max_actions_per_step]

    def _get_phase_prompt(self, state: dict[str, Any], available_actions: list[str], current_time: float) -> str:
        """현재 상태에 맞는 CPG Phase 프롬프트 반환

        P2 Fix: 더 많은 임상 시나리오 지원 (DKA, Stroke, HF, AKI)
        """
        diagnosis = (state.get("working_diagnosis") or "").lower()
        chief_complaint = (state.get("chief_complaint") or "").lower()

        # Combine diagnosis and chief_complaint for better matching
        context = f"{diagnosis} {chief_complaint}"

        # 초기 단계 판단 (available_actions에 assessment가 있으면)
        assessment_actions = [
            "assess_infection_source",
            "assess_organ_dysfunction",
            "assess_vital_signs",
            "obtain_12_lead_ecg",
            "order_ct_head",
            "assess_fluid_status",
        ]
        is_initial_phase = any(a in available_actions for a in assessment_actions)

        # ============================================================
        # Sepsis / Septic Shock
        # ============================================================
        if any(kw in context for kw in ["sepsi", "septic", "infection"]):
            if is_initial_phase:
                return CPG_PHASE_PROMPTS.get("initial_recognition", "")
            return CPG_PHASE_PROMPTS.get("septic_shock_bundle", "")

        # ============================================================
        # STEMI / Chest Pain
        # ============================================================
        if any(kw in context for kw in ["stemi", "st_elevation", "chest_pain", "myocardial"]):
            if is_initial_phase:
                return """
## CURRENT PHASE: Initial Chest Pain Assessment

You are in the INITIAL ASSESSMENT phase for chest pain. Priority actions:
1. FIRST: Obtain 12-lead ECG within 10 minutes
2. Assess vital signs
3. Obtain chest pain history

DO NOT administer treatment until ECG is obtained and interpreted!
"""
            return CPG_PHASE_PROMPTS.get("stemi_pathway", "")

        # ============================================================
        # P2 Fix: DKA (Diabetic Ketoacidosis)
        # ============================================================
        if any(kw in context for kw in ["dka", "ketoacidosis", "diabetic"]):
            return CPG_PHASE_PROMPTS.get("dka_management", "")

        # ============================================================
        # P2 Fix: Stroke
        # ============================================================
        if any(kw in context for kw in ["stroke", "cva", "cerebrovascular", "hemiparesis", "aphasia"]):
            return CPG_PHASE_PROMPTS.get("stroke_assessment", "")

        # ============================================================
        # P2 Fix: Heart Failure
        # ============================================================
        if any(kw in context for kw in ["heart_failure", "chf", "hfref", "hfpef", "cardiomyopathy"]):
            return CPG_PHASE_PROMPTS.get("heart_failure_acute", "")

        # ============================================================
        # P2 Fix: AKI (Acute Kidney Injury)
        # ============================================================
        if any(kw in context for kw in ["aki", "acute_kidney", "renal_failure", "kidney_injury"]):
            return CPG_PHASE_PROMPTS.get("aki_management", "")

        # ============================================================
        # Default: Generic Initial Assessment
        # ============================================================
        if is_initial_phase:
            return """
## CURRENT PHASE: Initial Assessment

Complete assessment before treatment:
1. Assess patient condition
2. Order diagnostic tests
3. Identify the clinical syndrome
"""

        return ""

    def _normalize_action_args(
        self, action_type: ActionType, args: dict[str, Any], action_type_str: str = "", action_id: str = ""
    ) -> dict[str, Any]:
        """LLM 응답의 args를 환경이 기대하는 형식으로 정규화"""
        normalized = {}
        # Ensure string types for safe .lower() call
        if isinstance(action_type_str, list):
            action_type_str = action_type_str[0] if action_type_str else ""
        if isinstance(action_id, list):
            action_id = action_id[0] if action_id else ""
        combined_str = f"{action_type_str!s} {action_id!s}".lower()

        if action_type == ActionType.ORDER_LAB:
            # test_code 추출
            test_code = args.get("test_code")
            if not test_code:
                # lab_test, test, test_name, parameters 등에서 추출
                lab_test = args.get("lab_test", args.get("test", args.get("test_name", "")))
                if not lab_test and args.get("parameters"):
                    # ["lactate", "creatinine"] 형태
                    params = args.get("parameters")
                    if isinstance(params, list) and params:
                        lab_test = params[0]
                if lab_test:
                    # "lactate level" -> "lactate"
                    test_code = lab_test.lower().replace(" level", "").replace(" test", "").strip()
                    test_code = test_code.replace(" ", "_")
                # action_type에서 추출 시도
                if not test_code:
                    for lab in ["lactate", "troponin", "blood_culture", "creatinine", "wbc", "cbc"]:
                        if lab in combined_str:
                            test_code = lab
                            break
            normalized["test_code"] = test_code or "unknown"

        elif action_type == ActionType.ORDER_IMAGING:
            # imaging_type 추출
            imaging_type = args.get("imaging_type")
            if not imaging_type:
                imaging_type = args.get("imaging", args.get("study", args.get("modality", "")))
                if imaging_type:
                    imaging_type = imaging_type.lower().replace(" ", "_")
                # action_type에서 추출 시도
                if not imaging_type:
                    for img in ["ecg", "xray", "ct", "echo", "ultrasound"]:
                        if img in combined_str:
                            imaging_type = img
                            break
            normalized["imaging_type"] = imaging_type or "unknown"

        elif action_type == ActionType.GIVE_MEDICATION:
            # medication_code와 dose 추출
            med_code = args.get("medication_code")
            if not med_code:
                med_code = args.get("medication", args.get("drug", args.get("med", "")))
                if med_code:
                    med_code = med_code.lower().replace(" ", "_")
                # action_type에서 추출 시도
                if not med_code:
                    for med in [
                        "norepinephrine",
                        "vasopressor",
                        "antibiotic",
                        "crystalloid",
                        "bicarbonate",
                        "corticosteroid",
                        "aspirin",
                        "heparin",
                        "nitroglycerin",
                        "fluid",
                        "saline",
                    ]:
                        if med in combined_str:
                            med_code = med
                            break
            normalized["medication_code"] = med_code or "unknown"

            dose = args.get("dose", args.get("dosage", "standard"))
            normalized["dose"] = dose

            # route가 있으면 포함
            if args.get("route"):
                normalized["route"] = args.get("route")

        else:
            # 다른 타입은 그대로 전달
            normalized = args

        return normalized

    def _parse_action_type(self, action_type_str: str, action_id: str) -> ActionType:
        """행동 타입 문자열을 ActionType으로 변환"""
        type_map = {
            "order_lab": ActionType.ORDER_LAB,
            "order_imaging": ActionType.ORDER_IMAGING,
            "give_medication": ActionType.GIVE_MEDICATION,
            "consult": ActionType.CONSULT,
            "disposition": ActionType.DISPOSITION,
            "reassess": ActionType.REASSESS,
            "escalate": ActionType.ESCALATE,
        }

        # Ensure string types for safe .lower() call
        if isinstance(action_type_str, list):
            action_type_str = action_type_str[0] if action_type_str else ""
        if isinstance(action_id, list):
            action_id = action_id[0] if action_id else ""
        action_type_str = str(action_type_str)
        action_id = str(action_id)

        # 문자열 매칭
        action_lower = action_type_str.lower()
        if action_lower in type_map:
            return type_map[action_lower]

        # 키워드 기반 매칭
        medication_keywords = [
            "administer",
            "give",
            "start",
            "initiate_therapy",
            "norepinephrine",
            "vasopressor",
            "antibiotic",
            "fluid",
            "crystalloid",
            "bicarbonate",
            "corticosteroid",
            "aspirin",
            "heparin",
            "nitroglycerin",
            "medication",
            "drug",
        ]
        lab_keywords = [
            "monitor",
            "check",
            "measure",
            "order_lab",
            "lab",
            "lactate",
            "troponin",
            "culture",
            "blood_gas",
            "creatinine",
            "cbc",
            "bmp",
            "coagulation",
        ]
        imaging_keywords = ["imaging", "xray", "x-ray", "ct", "ecg", "echo", "ultrasound", "mri", "chest_xray"]
        consult_keywords = ["consult", "call", "activate", "cath_lab", "surgery", "icu"]

        # 키워드 검색
        combined = f"{action_lower} {action_id.lower()}"
        for kw in medication_keywords:
            if kw in combined:
                return ActionType.GIVE_MEDICATION
        for kw in lab_keywords:
            if kw in combined:
                return ActionType.ORDER_LAB
        for kw in imaging_keywords:
            if kw in combined:
                return ActionType.ORDER_IMAGING
        for kw in consult_keywords:
            if kw in combined:
                return ActionType.CONSULT

        return ActionType.REASSESS  # 기본값

    def _normalize_action_id(self, action_id: str, available_actions: list[str]) -> tuple[str | None, str | None]:
        """Normalise an LLM-emitted ``action_id`` via the 3-tier pipeline.

        Returns ``(resolved_id, semantic_tag)`` where:
          * Tier 1 — exact (case-insensitive) match in ``available_actions``
            returns ``(scenario_id, None)``.
          * Tier 2 — alias map lookup: if ``action_alias_map.yaml``'s reverse
            map resolves this id to a canonical that is itself in
            ``available_actions`` (or shares a canonical with one in the set),
            returns ``(canonical_or_variant, None)``.
          * Tier 3 — if ``action_id`` (or its alias canonical) is in
            ``universal_clinical_safety.yaml``'s allowed action set, returns
            ``(id, "GENERAL_WORKUP")`` — scorer treats as no-op.
          * Substring / Jaccard fuzzy fallback — returns the fuzzy match with
            ``None`` tag if one is found (kept for backward compatibility).
          * Tier 4 — otherwise returns ``(action_id, "DEVIATION")``. The
            caller MUST use this tuple to build an ``Action`` so that the
            scorer can flag the DEVIATION; returning an empty action list
            here is what caused the 98 % ``consecutive_empty_actions`` bug.

        The only case that returns ``(None, None)`` is when
        ``available_actions`` itself is empty (engine-configuration issue).

        Design rationale: docs/attack_gap_exp_exp/260421_three_tier_normalizer_design.md
        """
        if not available_actions:
            return (None, None)

        valid_ids = set(available_actions)

        # Tier 1 — exact match
        if action_id in valid_ids:
            return (action_id, None)

        # Tier 1b — case-insensitive / dash/space normalised exact match
        action_id_lower = action_id.lower().replace("-", "_").replace(" ", "_")
        for valid_id in valid_ids:
            if action_id_lower == valid_id.lower():
                return (valid_id, None)

        # Tier 2 — alias-map lookup resolved INTO the scenario's available set
        if self._alias_reverse_map:
            canonical = self._alias_reverse_map.get(action_id_lower)
            if canonical:
                if canonical in valid_ids:
                    logger.info(
                        "RAG alias matched '%s' -> canonical '%s'",
                        action_id,
                        canonical,
                    )
                    return (canonical, None)
                for variant in self._alias_canonical_map.get(canonical, []):
                    if variant in valid_ids:
                        logger.info(
                            "RAG alias matched '%s' -> canonical '%s' -> variant '%s'",
                            action_id,
                            canonical,
                            variant,
                        )
                        return (variant, None)

        # Abbreviation mapping (e.g., CBC, BMP) — still Tier-1 style
        for valid_id in valid_ids:
            if self._is_abbreviation_match(action_id_lower, valid_id.lower()):
                logger.info(f"RAG abbreviation matched '{action_id}' to '{valid_id}'")
                return (valid_id, None)

        # Tier 3 — universal_clinical_safety fallback (general-ER workup).
        # Emits GENERAL_WORKUP tag so the scorer does not flag as DEVIATION.
        if self._universal_safety_actions:
            if action_id_lower in self._universal_safety_actions:
                logger.info("RAG Tier 3 (UCS) matched '%s' as GENERAL_WORKUP", action_id)
                return (action_id_lower, "GENERAL_WORKUP")
            if self._alias_reverse_map:
                canonical = self._alias_reverse_map.get(action_id_lower)
                if canonical and canonical in self._universal_safety_actions:
                    logger.info(
                        "RAG Tier 3 alias-then-UCS matched '%s' -> '%s' as GENERAL_WORKUP",
                        action_id,
                        canonical,
                    )
                    return (canonical, "GENERAL_WORKUP")

        # Existing strict substring / Jaccard fuzzy fallback (kept for
        # backward compatibility with scenarios whose action ids do share
        # meaningful substrings).
        best_match = None
        best_score = 0.0
        for valid_id in valid_ids:
            valid_id_lower = valid_id.lower()
            if len(action_id_lower) < 8:
                continue
            if action_id_lower in valid_id_lower:
                ratio = len(action_id_lower) / len(valid_id_lower)
                if ratio >= 0.7 and ratio > best_score:
                    best_match = valid_id
                    best_score = ratio
            elif valid_id_lower in action_id_lower:
                ratio = len(valid_id_lower) / len(action_id_lower)
                if ratio >= 0.7 and ratio > best_score:
                    best_match = valid_id
                    best_score = ratio
        if best_match:
            logger.info(f"RAG strict fuzzy matched '{action_id}' to '{best_match}' (score={best_score:.2f})")
            return (best_match, None)

        # Tier 4 — DEVIATION (out-of-guideline, clinically plausible proposal).
        # NEVER return (None, None) here: the scorer, not the normaliser, is
        # responsible for penalising out-of-scope actions.
        logger.info("RAG Tier 4 DEVIATION: '%s' not matched in any tier", action_id)
        return (action_id_lower, "DEVIATION")

    def _is_abbreviation_match(self, candidate: str, valid: str) -> bool:
        """Check if candidate is an abbreviation/variation of valid action ID."""
        # Remove common prefixes for comparison
        prefixes = ["order_", "give_", "lab_", "imaging_", "assess_", "check_", "obtain_"]
        candidate_core = candidate
        valid_core = valid
        for prefix in prefixes:
            candidate_core = candidate_core.replace(prefix, "")
            valid_core = valid_core.replace(prefix, "")

        # Check if cores match
        if candidate_core == valid_core:
            return True

        # Check common abbreviations
        # P3 Fix: Expanded abbreviation map with more clinical terms
        abbrev_map = {
            # ECG/EKG variations
            "ecg": ["12_lead_ecg", "ecg_12_lead", "electrocardiogram"],
            "ekg": ["12_lead_ecg", "ecg_12_lead", "electrocardiogram"],
            # Imaging
            "cxr": ["chest_xray", "chest_x_ray", "xray_chest"],
            "ct": ["ct_scan", "computed_tomography", "ct_head", "ct_chest", "ct_abdomen"],
            "mri": ["magnetic_resonance", "mri_brain", "mri_spine"],
            "echo": ["echocardiogram", "echocardiography", "transthoracic_echo", "tte"],
            "us": ["ultrasound", "ultrasonography"],
            # Cardiac markers
            "bnp": ["bnp_or_ntprobnp", "ntprobnp", "brain_natriuretic_peptide"],
            "troponin": ["cardiac_troponin", "trop", "troponin_i", "troponin_t"],
            # Basic panels
            "bmp": ["basic_metabolic_panel", "metabolic_panel"],
            "cmp": ["comprehensive_metabolic_panel", "metabolic_panel"],
            "cbc": ["complete_blood_count", "blood_count"],
            "lft": ["liver_function", "hepatic_panel", "ast_alt"],
            "coags": ["coagulation", "pt_inr", "ptt", "coagulation_panel"],
            # Specific labs
            "lactate": ["serum_lactate", "lactic_acid", "lactate_level"],
            "tsh": ["thyroid_stimulating_hormone", "thyroid"],
            "creatinine": ["serum_creatinine", "creat", "cr"],
            "glucose": ["blood_glucose", "serum_glucose", "glucose_level"],
            "potassium": ["serum_potassium", "k+", "k_level"],
            "sodium": ["serum_sodium", "na+", "na_level"],
            # Blood cultures
            "bcx": ["blood_culture", "blood_cultures"],
            "culture": ["blood_culture", "urine_culture", "wound_culture"],
            # Medications
            "abx": ["antibiotic", "antibiotics", "broad_spectrum_antibiotics"],
            "fluids": ["crystalloid", "iv_fluid", "fluid_bolus", "ns_bolus"],
            "pressors": ["vasopressor", "norepinephrine", "vasopressin"],
            "aspirin": ["aspirin_loading", "asa"],
            "heparin": ["anticoagulation", "heparin_bolus", "enoxaparin"],
            # Procedures
            "cath": ["cath_lab", "catheterization", "cardiac_cath"],
            "pci": ["percutaneous_coronary", "angioplasty", "stent"],
            "intubation": ["endotracheal_intubation", "eti", "airway"],
            # Assessments
            "vitals": ["vital_signs", "assess_vital_signs"],
            "neuro": ["neurological_exam", "neuro_check", "gcs"],
        }

        for abbrev, full_list in abbrev_map.items():
            if abbrev in candidate_core:
                for full in full_list:
                    if full in valid_core:
                        return True
            # Also check reverse
            for full in full_list:
                if full in candidate_core and abbrev in valid_core:
                    return True

        return False

    def _format_patient_state(self, state: dict[str, Any]) -> str:
        """환자 상태를 포맷팅된 문자열로 변환"""
        parts = []

        if state.get("chief_complaint"):
            parts.append(f"**Chief Complaint**: {state['chief_complaint']}")
        if state.get("working_diagnosis"):
            parts.append(f"**Working Diagnosis**: {state['working_diagnosis']}")

        vitals = state.get("vitals", {})
        if vitals:
            vital_str = []
            if vitals.get("heart_rate"):
                vital_str.append(f"HR: {vitals['heart_rate']}")
            if vitals.get("blood_pressure_systolic"):
                bp = f"{vitals['blood_pressure_systolic']}/{vitals.get('blood_pressure_diastolic', '?')}"
                vital_str.append(f"BP: {bp}")
            if vitals.get("respiratory_rate"):
                vital_str.append(f"RR: {vitals['respiratory_rate']}")
            if vitals.get("temperature"):
                vital_str.append(f"Temp: {vitals['temperature']}°C")
            if vitals.get("oxygen_saturation"):
                vital_str.append(f"SpO2: {vitals['oxygen_saturation']}%")
            if vitals.get("map_mmhg"):
                vital_str.append(f"MAP: {vitals['map_mmhg']}")
            if vital_str:
                parts.append(f"**Vitals**: {', '.join(vital_str)}")

        if state.get("allergies"):
            parts.append(f"**Allergies**: {', '.join(state['allergies'])}")
        if state.get("comorbidities"):
            parts.append(f"**Comorbidities**: {', '.join(state['comorbidities'])}")

        lab_results = state.get("lab_results", [])
        if lab_results:
            lab_strs = []
            for lab in lab_results[:5]:
                if isinstance(lab, dict):
                    lab_strs.append(f"{lab.get('test_code', 'unknown')}: {lab.get('value', '?')}")
            if lab_strs:
                parts.append(f"**Lab Results**: {', '.join(lab_strs)}")

        return "\n".join(parts) if parts else "No detailed state available"

    def _generate_actions_rule_based(
        self,
        retrieved_docs: list[RetrievedDocument],
        state: dict[str, Any],
        current_time: float,
        completed_action_ids: set,
        available_actions: list[str],
    ) -> list[Action]:
        """규칙 기반 행동 생성 (LLM 폴백)

        Args:
            available_actions: CPG에서 허용된 action ID 목록. 이 목록에 없는 action은 생성하지 않음.
        """
        actions = []
        valid_action_ids = set(available_actions) if available_actions else set()

        # 검색된 추천사항에서 행동 추출
        for doc in retrieved_docs:
            if doc.recommendation_text:
                extracted_actions = self._extract_actions_from_recommendation(
                    doc.recommendation_text, doc.source, doc.strength, state, current_time, completed_action_ids
                )
                actions.extend(extracted_actions)

        # 기본 진단 행동 (검색 결과 없을 때)
        if not actions and not completed_action_ids:
            actions.extend(self._get_default_diagnostic_actions(state, current_time, available_actions))

        # available_actions 검증 (P0 Fix: Deviation violation 방지)
        if valid_action_ids:
            validated_actions = []
            for action in actions:
                if action.action_id in valid_action_ids:
                    validated_actions.append(action)
                else:
                    logger.debug(f"Rule-based: Rejecting action '{action.action_id}' - not in available_actions")
            actions = validated_actions

        # 중복 제거 및 제한
        unique_actions = []
        seen_ids = set()
        for action in actions:
            if action.action_id not in seen_ids:
                unique_actions.append(action)
                seen_ids.add(action.action_id)

        return unique_actions[: self.config.max_actions_per_step]

    def _extract_actions_from_recommendation(
        self,
        recommendation_text: str,
        source: str,
        strength: str | None,
        state: dict[str, Any],
        current_time: float,
        completed_action_ids: set,
    ) -> list[Action]:
        """추천사항 텍스트에서 행동 추출"""
        actions = []
        text_lower = recommendation_text.lower()

        # SSC Sepsis 관련 행동
        if source == "ssc_sepsis":
            if "lactate" in text_lower and "order_lab_lactate" not in completed_action_ids:
                actions.append(
                    Action(
                        type=ActionType.ORDER_LAB,
                        action_id="order_lab_lactate",
                        args={"test_code": "lactate"},
                        timestamp_minutes=current_time,
                        justification=f"SSC recommendation: {recommendation_text[:100]}...",
                    )
                )

            if "blood culture" in text_lower and "order_lab_blood_culture" not in completed_action_ids:
                actions.append(
                    Action(
                        type=ActionType.ORDER_LAB,
                        action_id="order_lab_blood_culture",
                        args={"test_code": "blood_culture"},
                        timestamp_minutes=current_time,
                        justification=f"SSC recommendation: {recommendation_text[:100]}...",
                    )
                )

            if (
                "antibiotic" in text_lower or "antimicrobial" in text_lower
            ) and "give_broad_spectrum_antibiotics" not in completed_action_ids:
                actions.append(
                    Action(
                        type=ActionType.GIVE_MEDICATION,
                        action_id="give_broad_spectrum_antibiotics",
                        args={"medication_code": "broad_spectrum_antibiotics", "dose": "empiric"},
                        timestamp_minutes=current_time,
                        justification=f"SSC recommendation: {recommendation_text[:100]}...",
                    )
                )

            if "crystalloid" in text_lower or "fluid" in text_lower:
                if "give_crystalloid_30ml_kg" not in completed_action_ids:
                    actions.append(
                        Action(
                            type=ActionType.GIVE_MEDICATION,
                            action_id="give_crystalloid_30ml_kg",
                            args={"medication_code": "crystalloid", "dose": "30ml/kg"},
                            timestamp_minutes=current_time,
                            justification=f"SSC recommendation: {recommendation_text[:100]}...",
                        )
                    )

            if "vasopressor" in text_lower or "norepinephrine" in text_lower:
                if "start_vasopressor_norepinephrine" not in completed_action_ids:
                    vitals = state.get("vitals", {})
                    sbp = vitals.get("blood_pressure_systolic") if vitals else None
                    if sbp and sbp < 65:
                        actions.append(
                            Action(
                                type=ActionType.GIVE_MEDICATION,
                                action_id="start_vasopressor_norepinephrine",
                                args={"medication_code": "norepinephrine", "dose": "target MAP 65"},
                                timestamp_minutes=current_time,
                                justification=f"SSC recommendation: {recommendation_text[:100]}...",
                            )
                        )

        # AHA Chest Pain 관련 행동
        elif source == "aha_chest_pain":
            if "ecg" in text_lower or "electrocardiogram" in text_lower:
                if "obtain_12_lead_ecg" not in completed_action_ids:
                    actions.append(
                        Action(
                            type=ActionType.ORDER_IMAGING,
                            action_id="obtain_12_lead_ecg",
                            args={"imaging_type": "ecg_12_lead"},
                            timestamp_minutes=current_time,
                            justification=f"AHA recommendation: {recommendation_text[:100]}...",
                        )
                    )

            if "troponin" in text_lower and "order_lab_troponin" not in completed_action_ids:
                actions.append(
                    Action(
                        type=ActionType.ORDER_LAB,
                        action_id="order_lab_troponin",
                        args={"test_code": "troponin"},
                        timestamp_minutes=current_time,
                        justification=f"AHA recommendation: {recommendation_text[:100]}...",
                    )
                )

            if "aspirin" in text_lower and "give_aspirin_loading" not in completed_action_ids:
                actions.append(
                    Action(
                        type=ActionType.GIVE_MEDICATION,
                        action_id="give_aspirin_loading",
                        args={"medication_code": "aspirin", "dose": "325mg"},
                        timestamp_minutes=current_time,
                        justification=f"AHA recommendation: {recommendation_text[:100]}...",
                    )
                )

            if "catheterization" in text_lower or "pci" in text_lower:
                if "activate_cath_lab" not in completed_action_ids:
                    # STEMI면 cath lab 활성화
                    ecg_result = self._get_ecg_result(state)
                    if ecg_result and "st elevation" in ecg_result.lower():
                        actions.append(
                            Action(
                                type=ActionType.CONSULT,
                                action_id="activate_cath_lab",
                                args={"specialty": "interventional_cardiology"},
                                timestamp_minutes=current_time,
                                justification=f"AHA recommendation: {recommendation_text[:100]}...",
                            )
                        )

            # RV infarct 감지 시 V4R 권고
            if "right ventricle" in text_lower or "v4r" in text_lower:
                if "obtain_right_sided_ecg_v4r" not in completed_action_ids:
                    ecg_result = self._get_ecg_result(state)
                    if ecg_result and "inferior" in ecg_result.lower():
                        actions.append(
                            Action(
                                type=ActionType.ORDER_IMAGING,
                                action_id="obtain_right_sided_ecg_v4r",
                                args={"imaging_type": "v4r_ecg"},
                                timestamp_minutes=current_time,
                                justification=f"AHA recommendation: {recommendation_text[:100]}...",
                            )
                        )

        # KDIGO CKD/AKI 관련 행동
        elif source.startswith("kdigo"):
            if "creatinine" in text_lower or "egfr" in text_lower:
                if "order_lab_creatinine" not in completed_action_ids:
                    actions.append(
                        Action(
                            type=ActionType.ORDER_LAB,
                            action_id="order_lab_creatinine",
                            args={"test_code": "creatinine"},
                            timestamp_minutes=current_time,
                            justification=f"KDIGO recommendation: {recommendation_text[:100]}...",
                        )
                    )

            if "hydration" in text_lower or "fluid" in text_lower:
                if "start_iv_hydration" not in completed_action_ids:
                    actions.append(
                        Action(
                            type=ActionType.GIVE_MEDICATION,
                            action_id="start_iv_hydration",
                            args={"medication_code": "normal_saline", "dose": "standard"},
                            timestamp_minutes=current_time,
                            justification=f"KDIGO recommendation: {recommendation_text[:100]}...",
                        )
                    )

        return actions

    def _get_ecg_result(self, state: dict[str, Any]) -> str | None:
        """상태에서 ECG 결과 추출"""
        # working_diagnosis에서 ECG 정보 추출
        diagnosis = state.get("working_diagnosis", "")
        if diagnosis:
            if "stemi" in diagnosis.lower() or "st elevation" in diagnosis.lower():
                return diagnosis

        # imaging_results에서 ECG 검색
        imaging_results = state.get("imaging_results", [])
        for img in imaging_results:
            if isinstance(img, dict):
                result = img.get("result", "")
                if "ecg" in str(img).lower():
                    return result
            elif isinstance(img, str) and "ecg" in img.lower():
                return img

        return None

    def _get_default_diagnostic_actions(
        self, state: dict[str, Any], current_time: float, available_actions: list[str]
    ) -> list[Action]:
        """기본 진단 행동 (검색 결과 없을 때)

        Args:
            available_actions: CPG에서 허용된 action ID 목록.
                              이 목록이 있으면 해당 목록에 있는 action만 생성.

        P0 Fix: available_actions를 검증하여 Deviation violation 방지
        """
        valid_action_ids = set(available_actions) if available_actions else set()

        # 기본 진단 행동 후보 목록 (우선순위 순)
        default_candidates = [
            # ECG (chest pain, STEMI)
            ("obtain_12_lead_ecg", ActionType.ORDER_IMAGING, {"imaging_type": "ecg_12_lead"}),
            # Lactate (sepsis)
            ("order_lab_lactate", ActionType.ORDER_LAB, {"test_code": "lactate"}),
            # Blood culture (sepsis)
            ("order_lab_blood_culture", ActionType.ORDER_LAB, {"test_code": "blood_culture"}),
            # CBC (general)
            ("order_lab_cbc", ActionType.ORDER_LAB, {"test_code": "cbc"}),
            # BMP (general)
            ("order_lab_bmp", ActionType.ORDER_LAB, {"test_code": "bmp"}),
            # Assessment actions
            ("assess_vital_signs", ActionType.REASSESS, {}),
            ("assess_infection_source", ActionType.REASSESS, {}),
            ("assess_organ_dysfunction", ActionType.REASSESS, {}),
        ]

        actions = []
        for action_id, action_type, args in default_candidates:
            # available_actions가 있으면 검증, 없으면 모두 허용
            if valid_action_ids and action_id not in valid_action_ids:
                continue

            actions.append(
                Action(
                    type=action_type,
                    action_id=action_id,
                    args=args,
                    timestamp_minutes=current_time,
                    justification="Initial diagnostic workup",
                )
            )

            # 최대 3개까지만 반환
            if len(actions) >= 3:
                break

        return actions

    def get_retrieved_context(self, observation: Observation) -> list[dict[str, Any]]:
        """현재 관측에 대한 검색 컨텍스트 반환 (디버깅/분석용)"""
        query = self._build_query(observation)
        retrieved_docs = self.document_store.retrieve(query, self.rag_config.top_k)

        return [
            {
                "doc_id": doc.doc_id,
                "source": doc.source,
                "score": doc.score,
                "content": doc.content[:500],
                "recommendation_id": doc.recommendation_id,
                "strength": doc.strength,
            }
            for doc in retrieved_docs
        ]

    def get_constraint_verification(self) -> dict[str, Any]:
        """제약 검증 정보 반환

        이 메서드는 RAG 에이전트가 "강한 텍스트 베이스라인" 제약을 준수하는지
        검증하기 위한 정보를 제공합니다.
        논문 심사자가 공정성을 검증할 때 사용할 수 있습니다.

        Returns:
            Dict containing verification information about RAG constraints
        """
        return {
            # 접근 제어
            "uses_cpg_engine": False,
            "uses_assessor_core": False,
            "cpg_engine_import": False,
            "assessor_core_import": False,
            # 기능 제약
            "uses_planning_module": False,
            "uses_constraint_verification": False,
            "uses_forbidden_veto": False,
            "uses_mandatory_alarm": False,
            "uses_multi_step_planning": False,
            # 허용된 기능
            "uses_bm25_retrieval": True,
            "uses_json_schema_output": True,
            "uses_tool_calls": True,
            "uses_single_step_decision": True,
            # 검색 설정
            "retrieval_method": self._get_retrieval_method_name(),
            "top_k": self.rag_config.top_k,
            "llm_backend": str(self.rag_config.llm_backend),
            "use_dense": self.rag_config.use_dense,
            "use_hybrid": self.rag_config.use_hybrid,
            "embedding_model": self.rag_config.embedding_model if self.rag_config.use_dense else None,
            "dense_weight": self.rag_config.dense_weight if self.rag_config.use_hybrid else None,
            # 검증 노트
            "verification_note": (
                "This RAG agent is a 'strong text baseline' that uses only "
                "document retrieval (BM25) and LLM generation. It does NOT use "
                "planning modules, constraint verification (forbidden/mandatory veto), "
                "or direct access to cpg_engine/ or assessor_core/. "
                "This design ensures fair comparison by measuring 'how well can "
                "text retrieval alone perform' without additional algorithmic advantages."
            ),
        }

    def _get_retrieval_method_name(self) -> str:
        """검색 방법 이름 반환"""
        if self.rag_config.use_hybrid:
            return f"Hybrid (BM25 + {self.rag_config.embedding_model}, weight={self.rag_config.dense_weight})"
        elif self.rag_config.use_dense:
            return f"Dense ({self.rag_config.embedding_model})"
        else:
            return "BM25"

    def get_rag_status(self) -> dict[str, Any]:
        """RAG 에이전트 상태 반환 (디버깅/분석용)"""
        return {
            "agent_type": "rag_baseline",
            "action_count": len(self._action_history),
            "llm_calls": self.metrics.total_llm_calls,
            "uses_planning": False,
            "uses_constraint_verification": False,
            "retrieval_method": self._get_retrieval_method_name(),
            "retrieval_top_k": self.rag_config.top_k,
            "documents_indexed": len(self.document_store.documents) if self.document_store._loaded else 0,
        }
