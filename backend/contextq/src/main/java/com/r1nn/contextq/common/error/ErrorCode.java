package com.r1nn.contextq.common.error;

import org.springframework.http.HttpStatus;

/**
 * Error codes of api-spec §0.4 with HTTP status and the default user-facing message (policy §9.2).
 *
 * <p>Messages are Korean and never include stack traces or internal host names.
 */
public enum ErrorCode {
  INVALID_REQUEST(HttpStatus.BAD_REQUEST, "입력값을 확인해주세요."),

  AUTH_INVALID_CREDENTIALS(HttpStatus.UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다."),
  AUTH_TOKEN_MISSING(HttpStatus.UNAUTHORIZED, "로그인이 필요합니다."),
  AUTH_TOKEN_INVALID(HttpStatus.UNAUTHORIZED, "인증 정보가 올바르지 않습니다. 다시 로그인해주세요."),
  AUTH_TOKEN_EXPIRED(HttpStatus.UNAUTHORIZED, "인증이 만료되었습니다."),
  AUTH_REFRESH_MISSING(HttpStatus.UNAUTHORIZED, "로그인이 필요합니다."),
  AUTH_REFRESH_INVALID(HttpStatus.UNAUTHORIZED, "로그인 정보가 유효하지 않습니다. 다시 로그인해주세요."),
  AUTH_REFRESH_EXPIRED(HttpStatus.UNAUTHORIZED, "로그인 유지 기간이 끝났습니다. 다시 로그인해주세요."),
  AUTH_REFRESH_REUSED(HttpStatus.UNAUTHORIZED, "보안을 위해 로그아웃되었습니다. 다시 로그인해주세요."),
  INTERNAL_UNAUTHORIZED(HttpStatus.UNAUTHORIZED, "내부 인증에 실패했습니다."),

  FORBIDDEN(HttpStatus.FORBIDDEN, "접근 권한이 없습니다."),
  FORBIDDEN_IN_PROFILE(HttpStatus.FORBIDDEN, "현재 환경에서는 사용할 수 없는 기능입니다."),
  GUEST_MODE_NOT_ALLOWED(HttpStatus.FORBIDDEN, "비교 모드는 로그인 후 이용할 수 있습니다."),

  CONVERSATION_NOT_FOUND(HttpStatus.NOT_FOUND, "대화를 찾을 수 없습니다."),
  SOURCE_NOT_FOUND(HttpStatus.NOT_FOUND, "선택한 문서 버전을 찾을 수 없습니다."),

  AUTH_REFRESH_CONFLICT(HttpStatus.CONFLICT, "토큰 갱신이 동시에 요청되었습니다. 다시 시도해주세요."),
  CONVERSATION_BUSY(HttpStatus.CONFLICT, "이전 답변이 끝난 뒤 질문해주세요."),
  CONVERSATION_FULL(HttpStatus.CONFLICT, "대화 메시지 한도에 도달했습니다. 새 대화를 시작해주세요."),
  SOURCE_UNAVAILABLE(HttpStatus.CONFLICT, "선택한 문서 버전은 현재 질문할 수 없습니다."),

  AUTH_LOCKED(HttpStatus.TOO_MANY_REQUESTS, "로그인 시도 초과. 15분 후 다시 시도해주세요."),
  GUEST_QUOTA_EXCEEDED(HttpStatus.TOO_MANY_REQUESTS, "게스트 질문 한도(5회)를 모두 사용했습니다. 로그인 후 이용해주세요."),
  GUEST_SESSION_LIMIT(HttpStatus.TOO_MANY_REQUESTS, "게스트 이용 요청이 많습니다. 잠시 후 다시 시도하거나 로그인해주세요."),
  RATE_LIMITED(HttpStatus.TOO_MANY_REQUESTS, "질문이 너무 잦습니다. 잠시 후 다시 시도해주세요."),
  DAILY_QUOTA_EXCEEDED(HttpStatus.TOO_MANY_REQUESTS, "오늘의 질문 한도를 모두 사용했습니다. 내일 다시 이용해주세요."),
  CONCURRENT_STREAM_LIMIT(HttpStatus.TOO_MANY_REQUESTS, "진행 중인 답변이 끝난 뒤 다시 시도해주세요."),

  INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요."),
  EMBEDDING_MODEL_MISMATCH(HttpStatus.INTERNAL_SERVER_ERROR, "검색 인덱스 설정 오류가 발생했습니다. 관리자에게 알려주세요."),

  LLM_ERROR(HttpStatus.BAD_GATEWAY, "LLM 오류가 발생했습니다. 다시 질문해주세요."),
  COMPARE_PARSE_ERROR(HttpStatus.BAD_GATEWAY, "비교 결과를 만들지 못했습니다. 다시 질문해주세요."),

  AI_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "AI 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."),
  AI_BUSY(HttpStatus.SERVICE_UNAVAILABLE, "시스템이 혼잡합니다. 잠시 후 다시 시도해주세요."),
  INDEX_NOT_ACTIVE(HttpStatus.SERVICE_UNAVAILABLE, "검색 인덱스가 준비되지 않았습니다. 관리자에게 알려주세요."),

  UPSTREAM_TIMEOUT(HttpStatus.GATEWAY_TIMEOUT, "응답이 지연되고 있습니다. 다시 질문해주세요.");

  private final HttpStatus status;
  private final String defaultMessage;

  ErrorCode(HttpStatus status, String defaultMessage) {
    this.status = status;
    this.defaultMessage = defaultMessage;
  }

  public HttpStatus status() {
    return status;
  }

  public String defaultMessage() {
    return defaultMessage;
  }
}
