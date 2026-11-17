package com.r1nn.contextq.infra.aiserver;

/**
 * ai-server answered the stream request with a pre-stream error (HTTP status + {@code {code,
 * message, request_id, timestamp}}, api-spec §6.1).
 */
public class UpstreamRejectedException extends RuntimeException {

  private final int status;
  private final String code;

  public UpstreamRejectedException(int status, String code, String message) {
    super(message);
    this.status = status;
    this.code = code;
  }

  public int getStatus() {
    return status;
  }

  /** ai-server error code, or {@code null} when the body had none. */
  public String getCode() {
    return code;
  }
}
