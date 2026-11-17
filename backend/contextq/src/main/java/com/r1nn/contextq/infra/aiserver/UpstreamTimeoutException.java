package com.r1nn.contextq.infra.aiserver;

/** ai-server did not answer within the limit (headers or the first event). */
public class UpstreamTimeoutException extends RuntimeException {

  public UpstreamTimeoutException(String message) {
    super(message);
  }
}
