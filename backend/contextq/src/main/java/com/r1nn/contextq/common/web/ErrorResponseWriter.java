package com.r1nn.contextq.common.web;

import com.r1nn.contextq.common.error.ErrorBody;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.common.response.ApiResponse;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * Writes the common error body from servlet filters, which run before {@code
 * GlobalExceptionHandler} can (api-spec §0.3, policy §9.2).
 */
@Component
public class ErrorResponseWriter {

  private static final ObjectMapper JSON = JsonMapper.builder().build();

  public void write(HttpServletResponse response, ErrorCode code) throws IOException {
    if (response.isCommitted()) {
      return;
    }
    response.setStatus(code.status().value());
    response.setCharacterEncoding(StandardCharsets.UTF_8.name());
    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
    JSON.writeValue(
        response.getOutputStream(),
        ApiResponse.fail(new ErrorBody(code.name(), code.defaultMessage(), List.of())));
  }
}
