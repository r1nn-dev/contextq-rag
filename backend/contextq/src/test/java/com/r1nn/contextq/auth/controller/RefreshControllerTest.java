package com.r1nn.contextq.auth.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.auth.domain.RefreshToken;
import com.r1nn.contextq.auth.domain.TokenFamily;
import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.repository.RefreshTokenRepository;
import com.r1nn.contextq.auth.repository.TokenFamilyRepository;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.auth.service.RefreshTokenCleanup;
import jakarta.servlet.http.Cookie;
import java.time.Duration;
import java.time.Instant;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
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

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class RefreshControllerTest {

  static final Pattern COOKIE = Pattern.compile("devdocs_rt=([^;]*)");

  @Autowired private MockMvc mockMvc;
  @Autowired private UserRepository users;
  @Autowired private TokenFamilyRepository families;
  @Autowired private RefreshTokenRepository tokens;
  @Autowired private RefreshTokenCleanup cleanup;

  private String email;

  @BeforeEach
  void setUp() throws Exception {
    email = "rc" + System.nanoTime() + "@example.com";
    mockMvc.perform(json("/api/v1/auth/signup", email));
  }

  @Test
  void loginSetsSecureRefreshCookie() throws Exception {
    String setCookie = login().getResponse().getHeader(HttpHeaders.SET_COOKIE);

    assertThat(setCookie)
        .contains("HttpOnly", "Secure", "SameSite=Strict", "Path=/api/v1/auth", "Max-Age=604800");
    assertThat(cookieValue(setCookie)).hasSize(43); // 256-bit Base64URL without padding
  }

  @Test
  void refreshRotatesCookieAndReturnsAccessToken() throws Exception {
    String first = cookieValue(login().getResponse().getHeader(HttpHeaders.SET_COOKIE));

    MvcResult result =
        mockMvc
            .perform(post("/api/v1/auth/refresh").cookie(new Cookie("devdocs_rt", first)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.accessToken").isString())
            .andExpect(jsonPath("$.data.expiresIn").value(1800))
            .andReturn();

    String second = cookieValue(result.getResponse().getHeader(HttpHeaders.SET_COOKIE));
    assertThat(second).isNotEqualTo(first).isNotEmpty();
    mockMvc
        .perform(post("/api/v1/auth/refresh").cookie(new Cookie("devdocs_rt", first)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.error.code").value("AUTH_REFRESH_CONFLICT"));
  }

  @Test
  void refreshWithoutCookieIsMissing() throws Exception {
    mockMvc
        .perform(post("/api/v1/auth/refresh"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.error.code").value("AUTH_REFRESH_MISSING"));
  }

  @Test
  void unknownCookieIsInvalidAndCleared() throws Exception {
    MvcResult result =
        mockMvc
            .perform(post("/api/v1/auth/refresh").cookie(new Cookie("devdocs_rt", "forged")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error.code").value("AUTH_REFRESH_INVALID"))
            .andReturn();

    assertThat(result.getResponse().getHeader(HttpHeaders.SET_COOKIE)).contains("Max-Age=0");
  }

  @Test
  void logoutIsIdempotentAndClearsCookie() throws Exception {
    String token = cookieValue(login().getResponse().getHeader(HttpHeaders.SET_COOKIE));

    for (int i = 0; i < 2; i++) {
      MvcResult result =
          mockMvc
              .perform(post("/api/v1/auth/logout").cookie(new Cookie("devdocs_rt", token)))
              .andExpect(status().isOk())
              .andExpect(jsonPath("$.message").value("로그아웃되었습니다."))
              .andReturn();
      assertThat(result.getResponse().getHeader(HttpHeaders.SET_COOKIE)).contains("Max-Age=0");
    }
    mockMvc.perform(post("/api/v1/auth/logout")).andExpect(status().isOk());
    mockMvc
        .perform(post("/api/v1/auth/refresh").cookie(new Cookie("devdocs_rt", token)))
        .andExpect(jsonPath("$.error.code").value("AUTH_REFRESH_INVALID"));
  }

  @Test
  void cleanupDeletesOnlyFamiliesPastExpiryPlusOneDay() {
    Long userId = users.findByEmail(email).map(User::getId).orElseThrow();
    Instant now = Instant.now();
    TokenFamily old =
        families.save(TokenFamily.start(userId, now.minus(Duration.ofDays(9)), Duration.ofDays(7)));
    TokenFamily recent =
        families.save(
            TokenFamily.start(
                userId, now.minus(Duration.ofDays(7)).plusSeconds(3600), Duration.ofDays(7)));
    RefreshToken oldToken = tokens.save(RefreshToken.issue(old, "c".repeat(64), now));
    RefreshToken recentToken = tokens.save(RefreshToken.issue(recent, "d".repeat(64), now));

    cleanup.cleanup();

    assertThat(families.findById(old.getId())).isEmpty();
    assertThat(tokens.findById(oldToken.getId())).isEmpty(); // tokens go before their family (FK)
    assertThat(families.findById(recent.getId())).isPresent();
    assertThat(tokens.findById(recentToken.getId())).isPresent();
  }

  private MvcResult login() throws Exception {
    return mockMvc
        .perform(json("/api/v1/auth/login", email))
        .andExpect(status().isOk())
        .andReturn();
  }

  private static String cookieValue(String setCookie) {
    Matcher m = COOKIE.matcher(setCookie);
    assertThat(m.find()).isTrue();
    return m.group(1);
  }

  private static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder json(
      String path, String email) {
    return post(path)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"email\":\"" + email + "\",\"password\":\"pass1234\"}");
  }
}
