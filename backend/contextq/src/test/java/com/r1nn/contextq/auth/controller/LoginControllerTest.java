package com.r1nn.contextq.auth.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import tools.jackson.databind.json.JsonMapper;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class LoginControllerTest {

  @Autowired private MockMvc mockMvc;

  private String email;

  @BeforeEach
  void setUp() throws Exception {
    email = "api" + System.nanoTime() + "@example.com";
    mockMvc.perform(credentials("/api/v1/auth/signup", email, "pass1234"));
  }

  @Test
  void loginReturnsBearerTokenThatOpensMe() throws Exception {
    MvcResult result =
        mockMvc
            .perform(credentials("/api/v1/auth/login", email, "pass1234"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.tokenType").value("Bearer"))
            .andExpect(jsonPath("$.data.expiresIn").value(1800))
            .andReturn();
    String token =
        JsonMapper.builder()
            .build()
            .readTree(result.getResponse().getContentAsString())
            .at("/data/accessToken")
            .asString();

    mockMvc
        .perform(get("/api/v1/auth/me").header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.email").value(email))
        .andExpect(jsonPath("$.data.role").value("ROLE_USER"))
        .andExpect(jsonPath("$.data.userId").isNumber())
        .andExpect(jsonPath("$.data.createdAt").isString());
  }

  @Test
  void wrongPasswordAndUnknownEmailHaveSameBody() throws Exception {
    String wrong =
        mockMvc
            .perform(credentials("/api/v1/auth/login", email, "wrong1234"))
            .andExpect(status().isUnauthorized())
            .andReturn()
            .getResponse()
            .getContentAsString();
    String unknown =
        mockMvc
            .perform(credentials("/api/v1/auth/login", "x" + email, "wrong1234"))
            .andExpect(status().isUnauthorized())
            .andReturn()
            .getResponse()
            .getContentAsString();

    assertThat(wrong).isEqualTo(unknown).contains("AUTH_INVALID_CREDENTIALS");
  }

  @Test
  void fifthFailureReturnsLockedWithRetryAfter() throws Exception {
    for (int i = 0; i < 4; i++) {
      mockMvc.perform(credentials("/api/v1/auth/login", email, "wrong1234"));
    }

    mockMvc
        .perform(credentials("/api/v1/auth/login", email, "wrong1234"))
        .andExpect(status().isTooManyRequests())
        .andExpect(header().string("Retry-After", "900"))
        .andExpect(jsonPath("$.error.code").value("AUTH_LOCKED"));
  }

  @Test
  void missingFieldsAreInvalidRequest() throws Exception {
    mockMvc
        .perform(post("/api/v1/auth/login").contentType(MediaType.APPLICATION_JSON).content("{}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
  }

  @Test
  void meWithoutTokenIsMissing() throws Exception {
    mockMvc
        .perform(get("/api/v1/auth/me"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.error.code").value("AUTH_TOKEN_MISSING"));
  }

  private static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
      credentials(String path, String email, String password) {
    return post(path)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"email\":\"" + email + "\",\"password\":\"" + password + "\"}");
  }
}
