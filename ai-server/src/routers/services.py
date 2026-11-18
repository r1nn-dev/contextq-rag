"""내부 API가 쓰는 서비스 객체 묶음 — 첫 요청 때 만들어 앱 상태에 둔다.

- 인덱스 묶음(DB·Chroma·포인터 캐시): 헬스체크·소스 조회·reload·질의가 함께 쓴다. OpenAI 키 불필요.
- 질의 묶음: 인덱스 묶음 + 임베딩·생성 클라이언트. 포인터 캐시를 공유해야 reload가 질의에 반영된다.
헬스체크·문서는 OpenAI 키 없이도 열려야 하므로 기동 시점이 아니라 첫 사용 시점에 만든다.
테스트는 `app.dependency_overrides[get_services | get_index_services]`로 바꿔 끼운다.
"""

import asyncio
import logging
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.ingest_config import load_embedding_config
from src.config.rag_config import (
    RagConfig,
    load_compare_model_config,
    load_llm_config,
    load_rag_config,
    load_rewrite_model_config,
)
from src.config.settings import Settings
from src.ingest.store import ChromaVectorStore, VectorStore
from src.pipeline.compare import ComparePipeline
from src.pipeline.compare_generator import OpenAICompareGenerator
from src.pipeline.generator import OpenAIAnswerGenerator
from src.pipeline.rewriter import OpenAIQueryRewriter
from src.pipeline.single import SingleModePipeline
from src.retrieval.embedding import OpenAIQueryEmbedder
from src.retrieval.pairs import ComparePairCatalog, PairSource
from src.retrieval.pointers import PointerCache
from src.retrieval.search import ChromaRetriever
from src.routers.errors import ApiError

logger = logging.getLogger(__name__)


@dataclass
class IndexServices:
    session_factory: sessionmaker[Session]
    store: VectorStore
    pointers: PointerCache


def build_index_services(settings: Settings) -> IndexServices:
    session_factory = sessionmaker(create_engine(settings.database_url, pool_pre_ping=True))
    return IndexServices(
        session_factory, ChromaVectorStore(settings.chroma_data_dir), PointerCache(session_factory)
    )


def get_index_services(request: Request) -> IndexServices:
    services: IndexServices | None = getattr(request.app.state, "index_services", None)
    if services is None:
        services = build_index_services(request.app.state.settings)
        request.app.state.index_services = services
    return services


@dataclass
class ChatServices:
    config: RagConfig
    pointers: PointerCache | None  # reload가 무효화한다 (R-4-5)
    retriever: ChromaRetriever
    pipeline: SingleModePipeline
    slots: asyncio.Semaphore  # 시스템 전체 동시 처리 상한 (정책서 §8.1) — 비교 모드도 1개
    compare: ComparePipeline | None = None  # 비교 모드 (R-8-1). 없으면 COMPARE 요청은 500
    pairs: PairSource | None = None  # 허용 비교 쌍 (정책서 §3.2)


def build_services(settings: Settings, index: IndexServices) -> ChatServices:
    config = load_rag_config()
    pointers = index.pointers
    retriever = ChromaRetriever(
        index.store,
        pointers,
        OpenAIQueryEmbedder(settings.openai_api_key, load_embedding_config()),
    )
    generator = OpenAIAnswerGenerator(
        settings.openai_api_key, load_llm_config(), model_override=settings.llm_model
    )
    rewriter = OpenAIQueryRewriter(
        settings.openai_api_key, load_rewrite_model_config(), config.rewrite
    )
    pipeline = SingleModePipeline(
        retriever,
        generator,
        config.retrieval,
        tau_overrides=settings.tau_overrides(),
        rewriter=rewriter,
    )
    compare = ComparePipeline(
        retriever,
        OpenAICompareGenerator(
            settings.openai_api_key, load_compare_model_config(), model_override=settings.llm_model
        ),
        config.retrieval,
        tau_overrides=settings.tau_overrides(),
        rewriter=rewriter,
    )
    return ChatServices(
        config,
        pointers,
        retriever,
        pipeline,
        asyncio.Semaphore(config.stream.max_concurrency),
        compare,
        ComparePairCatalog(index.session_factory),
    )


def get_services(request: Request) -> ChatServices:
    services: ChatServices | None = getattr(request.app.state, "chat_services", None)
    if services is None:
        try:
            services = build_services(request.app.state.settings, get_index_services(request))
        except Exception:
            logger.exception("chat_services_init_failed")
            raise ApiError(
                500, "INTERNAL_ERROR", "서버 설정 오류로 요청을 처리할 수 없습니다"
            ) from None
        request.app.state.chat_services = services
    return services
