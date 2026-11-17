package com.r1nn.contextq.common.error;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

class GlobalExceptionHandlerTest {

  private MockMvc mockMvc;

  @BeforeEach
  void setUp() {
    mockMvc =
        MockMvcBuilders.standaloneSetup(new TestController())
            .setControllerAdvice(new GlobalExceptionHandler())
            .build();
  }

  @Test
  void beanValidationFailureListsFieldReasons() throws Exception {
    mockMvc
        .perform(
            post("/test/validate")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"\",\"password\":\"short\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.success").value(false))
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"))
        .andExpect(jsonPath("$.error.message").value("입력값을 확인해주세요."))
        .andExpect(jsonPath("$.error.details.length()").value(2))
        .andExpect(jsonPath("$.data").doesNotExist());
  }

  @Test
  void unreadableBodyIsInvalidRequest() throws Exception {
    mockMvc
        .perform(post("/test/validate").contentType(MediaType.APPLICATION_JSON).content("{oops"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"))
        .andExpect(jsonPath("$.error.details[0].field").value("body"));
  }

  @Test
  void businessExceptionUsesCodeStatusAndHeaders() throws Exception {
    mockMvc
        .perform(get("/test/locked"))
        .andExpect(status().isTooManyRequests())
        .andExpect(header().string("Retry-After", "900"))
        .andExpect(jsonPath("$.error.code").value("AUTH_LOCKED"))
        .andExpect(jsonPath("$.error.details").isArray());
  }

  @Test
  void invalidFieldHelperReportsOneField() throws Exception {
    mockMvc
        .perform(get("/test/duplicate"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.details[0].field").value("email"))
        .andExpect(jsonPath("$.error.details[0].reason").value("이미 사용 중인 이메일입니다."));
  }

  @Test
  void unexpectedErrorHidesInternals() throws Exception {
    mockMvc
        .perform(get("/test/boom"))
        .andExpect(status().isInternalServerError())
        .andExpect(jsonPath("$.error.code").value("INTERNAL_ERROR"))
        .andExpect(content().string(not(containsString("db-host-secret"))))
        .andExpect(content().string(not(containsString("IllegalStateException"))));
  }

  @Test
  void unsupportedMethodIsInvalidRequestWith405() throws Exception {
    mockMvc
        .perform(post("/test/locked"))
        .andExpect(status().isMethodNotAllowed())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
  }

  @Test
  void everyErrorCodeHasErrorStatusAndMessage() {
    for (ErrorCode code : ErrorCode.values()) {
      assertThat(code.status().isError()).as(code.name()).isTrue();
      assertThat(code.defaultMessage()).as(code.name()).isNotBlank();
    }
  }

  record SignupLike(
      @NotBlank(message = "필수 값입니다.") String email,
      @Size(min = 8, message = "8~64자여야 합니다.") String password) {}

  @RestController
  static class TestController {

    @PostMapping("/test/validate")
    String validate(@Valid @RequestBody SignupLike body) {
      return "ok";
    }

    @GetMapping("/test/locked")
    String locked() {
      throw BusinessException.retryAfter(ErrorCode.AUTH_LOCKED, 900);
    }

    @GetMapping("/test/duplicate")
    String duplicate() {
      throw BusinessException.invalidField("email", "이미 사용 중인 이메일입니다.");
    }

    @GetMapping("/test/boom")
    String boom() {
      throw new IllegalStateException("connection to db-host-secret failed");
    }
  }
}
