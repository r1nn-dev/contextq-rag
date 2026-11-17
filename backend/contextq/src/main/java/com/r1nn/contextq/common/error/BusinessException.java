package com.r1nn.contextq.common.error;

import com.r1nn.contextq.common.error.ErrorBody.FieldReason;
import java.util.List;
import java.util.Map;

/**
 * Domain failure mapped to an api-spec §0.4 error response by {@link GlobalExceptionHandler}.
 *
 * <p>Headers carry values such as {@code Retry-After} (api-spec §0.7).
 */
public class BusinessException extends RuntimeException {

  private final ErrorCode errorCode;
  private final List<FieldReason> details;
  private final Map<String, String> headers;

  public BusinessException(ErrorCode errorCode) {
    this(errorCode, errorCode.defaultMessage(), List.of(), Map.of());
  }

  public BusinessException(ErrorCode errorCode, String message) {
    this(errorCode, message, List.of(), Map.of());
  }

  public BusinessException(
      ErrorCode errorCode, String message, List<FieldReason> details, Map<String, String> headers) {
    super(message);
    this.errorCode = errorCode;
    this.details = List.copyOf(details);
    this.headers = Map.copyOf(headers);
  }

  /** One invalid field reported as {@code INVALID_REQUEST} (e.g. duplicate email). */
  public static BusinessException invalidField(String field, String reason) {
    return new BusinessException(
        ErrorCode.INVALID_REQUEST,
        ErrorCode.INVALID_REQUEST.defaultMessage(),
        List.of(new FieldReason(field, reason)),
        Map.of());
  }

  /** Error with a {@code Retry-After} header in seconds (api-spec §0.7), at least 1. */
  public static BusinessException retryAfter(ErrorCode errorCode, long seconds) {
    return new BusinessException(
        errorCode,
        errorCode.defaultMessage(),
        List.of(),
        Map.of("Retry-After", Long.toString(Math.max(1, seconds))));
  }

  public ErrorCode getErrorCode() {
    return errorCode;
  }

  public List<FieldReason> getDetails() {
    return details;
  }

  public Map<String, String> getHeaders() {
    return headers;
  }

  public ErrorBody toBody() {
    return new ErrorBody(errorCode.name(), getMessage(), details);
  }
}
