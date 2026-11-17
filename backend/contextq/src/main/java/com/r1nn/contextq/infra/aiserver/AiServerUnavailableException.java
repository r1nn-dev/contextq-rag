package com.r1nn.contextq.infra.aiserver;

/** ai-server could not be reached or answered with an unusable response. */
public class AiServerUnavailableException extends RuntimeException {

  public AiServerUnavailableException(String message, Throwable cause) {
    super(message, cause);
  }
}
