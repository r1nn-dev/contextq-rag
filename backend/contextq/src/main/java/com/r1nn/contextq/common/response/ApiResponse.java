package com.r1nn.contextq.common.response;

import com.fasterxml.jackson.annotation.JsonValue;
import com.r1nn.contextq.common.error.ErrorBody;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Common response body (api-spec §0.3).
 *
 * <p>Success: {@code {success: true, message, data}} — {@code message} and {@code data} keys are
 * always present, even when null. Failure: {@code {success: false, error: {code, message,
 * details}}} only.
 */
public final class ApiResponse<T> {

  private final boolean success;
  private final String message;
  private final T data;
  private final ErrorBody error;

  private ApiResponse(boolean success, String message, T data, ErrorBody error) {
    this.success = success;
    this.message = message;
    this.data = data;
    this.error = error;
  }

  /** Single resource lookup: {@code message} is null. */
  public static <T> ApiResponse<T> ok(T data) {
    return new ApiResponse<>(true, null, data, null);
  }

  /** Action result with a user-facing message and optional data. */
  public static <T> ApiResponse<T> ok(String message, T data) {
    return new ApiResponse<>(true, message, data, null);
  }

  public static ApiResponse<Void> fail(ErrorBody error) {
    return new ApiResponse<>(false, null, null, error);
  }

  public boolean isSuccess() {
    return success;
  }

  public String getMessage() {
    return message;
  }

  public T getData() {
    return data;
  }

  public ErrorBody getError() {
    return error;
  }

  /** Serializes the two shapes of §0.3 exactly (null keys kept on success, absent on failure). */
  @JsonValue
  Map<String, Object> toJson() {
    Map<String, Object> json = new LinkedHashMap<>();
    json.put("success", success);
    if (success) {
      json.put("message", message);
      json.put("data", data);
    } else {
      json.put("error", error);
    }
    return json;
  }
}
