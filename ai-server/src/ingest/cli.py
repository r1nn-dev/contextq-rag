"""인덱스 관리 CLI — Makefile 타깃이 호출한다 (ADR-005).

    uv run python -m src.ingest.cli ingest --source langchain_v1x

수집·임베딩 명령은 prod 프로필이거나 `INGEST_ENABLED`가 꺼져 있으면 등록하지 않는다
(정책서 §4.5 운영 수집 금지, INV-17).
"""

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.ingest_config import load_embedding_config
from src.config.settings import Settings
from src.ingest.embedder import OpenAIEmbeddingClient
from src.ingest.pipeline import (
    IngestDependencies,
    IngestFailedError,
    IngestOptions,
    run_ingest,
)
from src.ingest.runs import SourceNotFoundError
from src.ingest.store import ChromaVectorStore

FORBIDDEN_IN_PROFILE = "FORBIDDEN_IN_PROFILE"
INGEST_COMMANDS = ("ingest",)


def ingest_allowed(settings: Settings) -> bool:
    return settings.app_profile != "prod" and settings.ingest_enabled


def build_parser(settings: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.ingest.cli", description="인덱스 관리")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    if ingest_allowed(settings):
        ingest = commands.add_parser("ingest", help="소스 하나를 새 run으로 수집한다")
        ingest.add_argument("--source", required=True, help="ai.sources.source_key")
        ingest.add_argument(
            "--strategy",
            choices=["A", "B", "C"],
            help="청킹 전략 (기본: configs/ingest.yaml default_strategy)",
        )
        ingest.add_argument(
            "--accept-drift",
            action="store_true",
            help="검증 게이트의 청크 수 드리프트(±30%%) 초과를 허용한다 (정책서 §4.4)",
        )
    return parser


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    settings = settings or Settings()
    args_list = list(sys.argv[1:] if argv is None else argv)

    if args_list[:1] and args_list[0] in INGEST_COMMANDS and not ingest_allowed(settings):
        print(
            f"{FORBIDDEN_IN_PROFILE}: '{args_list[0]}'은(는) local·staging 프로필에서 "
            "INGEST_ENABLED=true일 때만 사용할 수 있습니다 "
            f"(현재 APP_PROFILE={settings.app_profile}, INGEST_ENABLED={settings.ingest_enabled})",
            file=sys.stderr,
        )
        return 2

    parser = build_parser(settings)
    args = parser.parse_args(args_list)
    if args.command is None:
        parser.print_help()
        return 2

    engine = create_engine(settings.database_url)
    session_factory = sessionmaker(engine)
    try:
        if args.command == "ingest":
            options = IngestOptions(
                data_dir=settings.ingest_data_dir,
                accept_drift=args.accept_drift,
                strategy=args.strategy,
            )
            embedding = load_embedding_config()
            deps = IngestDependencies(
                embedder_factory=lambda: OpenAIEmbeddingClient(settings.openai_api_key, embedding),
                store=ChromaVectorStore(settings.chroma_data_dir),
                price_per_1m_tokens_usd=embedding.price_per_1m_tokens_usd,
            )
            summary = run_ingest(session_factory, args.source, options, deps)
            print(
                f"run {summary.run_id} ({args.source}): {summary.status} — "
                f"문서 {summary.documents}, 섹션 {summary.sections}, 청크 {summary.chunks}, "
                f"누락 스니펫 {summary.missing_snippets}"
            )
        return 0
    except SourceNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except IngestFailedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
