package com.r1nn.contextq.common.error;

import com.r1nn.contextq.common.error.ErrorBody.FieldReason;
import com.r1nn.contextq.common.response.ApiResponse;
import jakarta.validation.ConstraintViolationException;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.async.AsyncRequestNotUsableException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * Maps every failure to the common error body (api-spec §0.3, policy §9.2).
 *
 * <p>Content-Type is always {@code application/json}, also for {@code Accept: text/event-stream}
 * requests (pre-stream errors of the chat stream), so content negotiation cannot fail.
 *
 * <p>Stack traces and messages of unexpected errors go to the server log only; the client gets
 * {@code INTERNAL_ERROR} with the default message. The request ID travels in the {@code
 * X-Request-Id} response header and in the log context.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

  private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

  @ExceptionHandler(BusinessException.class)
  ResponseEntity<ApiResponse<Void>> handleBusiness(BusinessException e) {
    ResponseEntity.BodyBuilder builder =
        ResponseEntity.status(e.getErrorCode().status()).contentType(MediaType.APPLICATION_JSON);
    e.getHeaders().forEach(builder::header);
    return builder.body(ApiResponse.fail(e.toBody()));
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  ResponseEntity<ApiResponse<Void>> handleInvalidBody(MethodArgumentNotValidException e) {
    List<FieldReason> details = new ArrayList<>();
    e.getBindingResult()
        .getFieldErrors()
        .forEach(f -> details.add(new FieldReason(f.getField(), f.getDefaultMessage())));
    e.getBindingResult()
        .getGlobalErrors()
        .forEach(g -> details.add(new FieldReason(g.getObjectName(), g.getDefaultMessage())));
    return invalid(HttpStatus.BAD_REQUEST, details);
  }

  @ExceptionHandler(HandlerMethodValidationException.class)
  ResponseEntity<ApiResponse<Void>> handleInvalidParameter(HandlerMethodValidationException e) {
    List<FieldReason> details = new ArrayList<>();
    e.getParameterValidationResults()
        .forEach(
            result ->
                result
                    .getResolvableErrors()
                    .forEach(
                        err ->
                            details.add(
                                new FieldReason(
                                    result.getMethodParameter().getParameterName(),
                                    err.getDefaultMessage()))));
    return invalid(HttpStatus.BAD_REQUEST, details);
  }

  @ExceptionHandler(ConstraintViolationException.class)
  ResponseEntity<ApiResponse<Void>> handleConstraint(ConstraintViolationException e) {
    List<FieldReason> details =
        e.getConstraintViolations().stream()
            .map(v -> new FieldReason(lastNode(v.getPropertyPath().toString()), v.getMessage()))
            .toList();
    return invalid(HttpStatus.BAD_REQUEST, details);
  }

  @ExceptionHandler(HttpMessageNotReadableException.class)
  ResponseEntity<ApiResponse<Void>> handleUnreadable(HttpMessageNotReadableException e) {
    return invalid(HttpStatus.BAD_REQUEST, List.of(new FieldReason("body", "요청 본문을 읽을 수 없습니다.")));
  }

  @ExceptionHandler(MissingServletRequestParameterException.class)
  ResponseEntity<ApiResponse<Void>> handleMissingParam(MissingServletRequestParameterException e) {
    return invalid(
        HttpStatus.BAD_REQUEST, List.of(new FieldReason(e.getParameterName(), "필수 값입니다.")));
  }

  @ExceptionHandler(MethodArgumentTypeMismatchException.class)
  ResponseEntity<ApiResponse<Void>> handleTypeMismatch(MethodArgumentTypeMismatchException e) {
    return invalid(HttpStatus.BAD_REQUEST, List.of(new FieldReason(e.getName(), "형식이 올바르지 않습니다.")));
  }

  @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
  ResponseEntity<ApiResponse<Void>> handleMediaType(HttpMediaTypeNotSupportedException e) {
    return invalid(
        HttpStatus.UNSUPPORTED_MEDIA_TYPE,
        List.of(new FieldReason("Content-Type", "application/json 요청만 받습니다.")));
  }

  /** Unknown path: INVALID_REQUEST code with HTTP 404 (api-spec §0.4). */
  @ExceptionHandler(NoResourceFoundException.class)
  ResponseEntity<ApiResponse<Void>> handleNotFound(NoResourceFoundException e) {
    return invalid(HttpStatus.NOT_FOUND, List.of());
  }

  /** Unsupported method: INVALID_REQUEST code with HTTP 405 (api-spec §0.4). */
  @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
  ResponseEntity<ApiResponse<Void>> handleMethod(HttpRequestMethodNotSupportedException e) {
    return invalid(HttpStatus.METHOD_NOT_ALLOWED, List.of());
  }

  /** The client closed the stream; the response is unusable, so nothing is written. */
  @ExceptionHandler(AsyncRequestNotUsableException.class)
  void handleClientGone(AsyncRequestNotUsableException e) {
    log.debug("client_disconnected {}", e.getMessage());
  }

  @ExceptionHandler(Exception.class)
  ResponseEntity<ApiResponse<Void>> handleUnexpected(Exception e) {
    log.error("unexpected_error", e);
    ErrorCode code = ErrorCode.INTERNAL_ERROR;
    return ResponseEntity.status(code.status())
        .contentType(MediaType.APPLICATION_JSON)
        .body(ApiResponse.fail(new ErrorBody(code.name(), code.defaultMessage(), List.of())));
  }

  private static ResponseEntity<ApiResponse<Void>> invalid(
      HttpStatusCode status, List<FieldReason> details) {
    ErrorCode code = ErrorCode.INVALID_REQUEST;
    return ResponseEntity.status(status)
        .contentType(MediaType.APPLICATION_JSON)
        .body(ApiResponse.fail(new ErrorBody(code.name(), code.defaultMessage(), details)));
  }

  private static String lastNode(String path) {
    int dot = path.lastIndexOf('.');
    return dot < 0 ? path : path.substring(dot + 1);
  }
}
