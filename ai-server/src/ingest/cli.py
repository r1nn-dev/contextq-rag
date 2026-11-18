"""인덱스 관리 CLI — Makefile 타깃이 호출한다 (ADR-005).

    uv run python -m src.ingest.cli ingest --source langchain_v1x [--strategy B]
    uv run python -m src.ingest.cli activate --run 12
    uv run python -m src.ingest.cli rollback --source langchain_v1x
    uv run python -m src.ingest.cli smoke [--source langchain_v1x]
    uv run python -m src.ingest.cli snapshot --run 12 [--out data/snapshots]
    uv run python -m src.ingest.cli restore --snapshot data/snapshots/snapshot-….tar.gz [--activate]

수집·임베딩 명령(`ingest`)은 prod 프로필이거나 `INGEST_ENABLED`가 꺼져 있으면 등록하지 않는다
(정책서 §4.5 운영 수집 금지, INV-17). 활성화·롤백은 모든 프로필에서 쓸 수 있다.
`smoke`는 ACTIVE run에 스모크 질문만 다시 돌리고 인덱스 상태는 바꾸지 않는다(정책서 §4.4).
`snapshot`은 run 하나를 스냅샷 파일로 내보낸다(정책서 §4.5). DB는 읽기만 한다.
`restore`는 스냅샷을 같은 run id로 복원·검증하고, `--activate`면 이어서 활성화한다(모든 프로필).
모든 명령은 시작할 때 24시간 지난 FAILED run을 정리한다(정책서 §4.5).
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.ingest_config import load_embedding_config, load_smoke_config
from src.config.rag_config import load_rag_config
from src.config.settings import Settings
from src.ingest.activation import (
    ActivationError,
    ActivationResult,
    activate,
    purge_expired_failed,
    rollback,
)
from src.ingest.collect import is_commit_sha
from src.ingest.embedder import OpenAIEmbeddingClient
from src.ingest.permalinks import PermalinkChecker
from src.ingest.pipeline import (
    IngestDependencies,
    IngestFailedError,
    IngestOptions,
    run_ingest,
)
from src.ingest.reload import notify_reload
from src.ingest.runs import InvalidTransitionError, SourceNotFoundError
from src.ingest.smoke import format_outcome, run_smoke
from src.ingest.snapshot import (
    RestoreDependencies,
    SnapshotError,
    export_snapshot,
    restore_snapshot,
)
from src.ingest.store import ChromaVectorStore, VectorStore
from src.retrieval.errors import RetrievalError

FORBIDDEN_IN_PROFILE = "FORBIDDEN_IN_PROFILE"
INGEST_COMMANDS = ("ingest",)


def ingest_allowed(settings: Settings) -> bool:
    return settings.app_profile != "prod" and settings.ingest_enabled


def _commit_sha(value: str) -> str:
    """argparse 타입 — 40자 소문자 SHA만 받는다(브랜치 이름은 permalink 규칙 INV-05 위반)."""
    if not is_commit_sha(value):
        raise argparse.ArgumentTypeError(f"40자 소문자 커밋 SHA가 아닙니다: {value!r}")
    return value


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
            "--commit",
            type=_commit_sha,
            help="수집할 커밋 SHA(40자). 소스 ref 이력에 있어야 한다 (기본: ref의 최신 커밋)",
        )
        ingest.add_argument(
            "--accept-drift",
            action="store_true",
            help="검증 게이트의 청크 수 드리프트(±30%%) 초과를 허용한다 (정책서 §4.4)",
        )
    activate_cmd = commands.add_parser("activate", help="READY run을 ACTIVE로 올린다")
    activate_cmd.add_argument("--run", type=int, required=True, help="ai.ingest_runs.id")
    rollback_cmd = commands.add_parser("rollback", help="직전 SUPERSEDED run으로 되돌린다")
    rollback_cmd.add_argument("--source", required=True, help="ai.sources.source_key")
    smoke_cmd = commands.add_parser(
        "smoke", help="ACTIVE 인덱스에 스모크 질문을 다시 돌린다 (읽기 전용, τ 변경 후)"
    )
    smoke_cmd.add_argument(
        "--source", help="ai.sources.source_key (생략하면 smoke_questions.yaml의 모든 소스)"
    )
    snapshot_cmd = commands.add_parser("snapshot", help="run 하나를 스냅샷 파일로 내보낸다")
    snapshot_cmd.add_argument("--run", type=int, required=True, help="ai.ingest_runs.id")
    snapshot_cmd.add_argument(
        "--out", type=Path, help="저장 디렉터리 (기본: ${INGEST_DATA_DIR}/snapshots)"
    )
    restore_cmd = commands.add_parser(
        "restore", help="스냅샷을 같은 run id로 복원·검증한다 (RESTORING → VALIDATING → READY)"
    )
    restore_cmd.add_argument("--snapshot", type=Path, required=True, help="스냅샷 .tar.gz 경로")
    restore_cmd.add_argument(
        "--activate", action="store_true", help="복원 검증을 통과하면 바로 활성화한다"
    )
    return parser


def _restore(
    args: argparse.Namespace,
    settings: Settings,
    session_factory: sessionmaker[Session],
    store: VectorStore,
) -> None:
    embedding = load_embedding_config()
    deps = RestoreDependencies(
        store=store,
        embedder_factory=lambda: OpenAIEmbeddingClient(settings.openai_api_key, embedding),
        smoke=load_smoke_config(),
        smoke_tau=lambda key: _tau(settings, key),
        embedding_model=embedding.model,
        embedding_dim=embedding.dimensions,
    )
    summary = restore_snapshot(session_factory, args.snapshot, deps)
    print(
        f"restore: run {summary.run_id} ({summary.source_key}) {summary.status} — "
        f"청크 {summary.chunk_count}"
    )
    if args.activate:
        with session_factory() as session:
            _print_activation("activate", activate(session, store, summary.run_id), settings)


def _ingest(
    args: argparse.Namespace,
    settings: Settings,
    session_factory: sessionmaker[Session],
    store: VectorStore,
) -> None:
    options = IngestOptions(
        data_dir=settings.ingest_data_dir,
        accept_drift=args.accept_drift,
        strategy=args.strategy,
        commit=args.commit,
    )
    embedding = load_embedding_config()
    deps = IngestDependencies(
        embedder_factory=lambda: OpenAIEmbeddingClient(settings.openai_api_key, embedding),
        store=store,
        price_per_1m_tokens_usd=embedding.price_per_1m_tokens_usd,
        permalink_checker=PermalinkChecker.create(settings.github_token),
        smoke=load_smoke_config(),
        smoke_tau=lambda key: _tau(settings, key),
    )
    summary = run_ingest(session_factory, args.source, options, deps)
    print(
        f"run {summary.run_id} ({args.source}): {summary.status} — "
        f"문서 {summary.documents}, 섹션 {summary.sections}, 청크 {summary.chunks}, "
        f"누락 스니펫 {summary.missing_snippets}"
    )


def _tau(settings: Settings, source_key: str) -> float:
    """서비스와 같은 τ — `configs/rag.yaml` + `TAU_{SOURCE_KEY}` 덮어쓰기."""
    return load_rag_config().retrieval.tau(source_key, settings.tau_overrides())


def _smoke(
    args: argparse.Namespace,
    settings: Settings,
    session_factory: sessionmaker[Session],
    store: VectorStore,
) -> int:
    smoke = load_smoke_config()
    sources = [args.source] if args.source else list(smoke.sources)
    embedding = load_embedding_config()
    with session_factory() as session:
        outcomes = run_smoke(
            session,
            store,
            lambda: OpenAIEmbeddingClient(settings.openai_api_key, embedding),
            smoke,
            lambda key: _tau(settings, key),
            sources,
        )
    for outcome in outcomes:
        print(format_outcome(outcome))
    return 0 if all(o.result.passed for o in outcomes) else 1


def _print_activation(
    action: str,
    result: ActivationResult,
    settings: Settings,
    notify: Callable[[str, str, str], str | None] = notify_reload,
) -> None:
    """결과를 출력하고 ai-server에 reload를 요청한다. 실패는 경고만 남긴다 (정책서 §4.5)."""
    print(
        f"{action}: {result.source_key} → run {result.active_run_id} ACTIVE"
        f" (SUPERSEDED {result.superseded or '-'}, PURGED {result.purged or '-'})."
    )
    failure = notify(settings.ai_server_internal_url, settings.internal_token, result.source_key)
    if failure is None:
        print(f"서버 포인터 reload 완료: {settings.ai_server_internal_url}")
    else:
        print(
            f"경고: 서버 포인터 reload 실패 ({failure}). 포인터 캐시 만료(30초) 후 반영된다.",
            file=sys.stderr,
        )


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
    store = ChromaVectorStore(settings.chroma_data_dir)
    try:
        with session_factory() as session:
            purged = purge_expired_failed(session, store)
        if purged:
            print(f"24시간 지난 FAILED run 정리: {purged}")

        if args.command == "ingest":
            _ingest(args, settings, session_factory, store)
        elif args.command == "activate":
            with session_factory() as session:
                _print_activation("activate", activate(session, store, args.run), settings)
        elif args.command == "smoke":
            return _smoke(args, settings, session_factory, store)
        elif args.command == "rollback":
            with session_factory() as session:
                _print_activation("rollback", rollback(session, store, args.source), settings)
        elif args.command == "restore":
            _restore(args, settings, session_factory, store)
        elif args.command == "snapshot":
            out_dir = args.out or settings.ingest_data_dir / "snapshots"
            with session_factory() as session:
                result = export_snapshot(session, store, args.run, out_dir)
            print(
                f"snapshot: run {args.run} → {result.path} "
                f"(청크 {result.manifest['chunk_count']}, "
                f"records_sha256 {result.manifest['records_sha256'][:12]}…)"
            )
        return 0
    except (
        SourceNotFoundError,
        IngestFailedError,
        ActivationError,
        InvalidTransitionError,
        RetrievalError,
        SnapshotError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
