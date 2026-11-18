package com.r1nn.contextq.global.config;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.auth.domain.UserRole;
import com.r1nn.contextq.auth.service.JwtProvider;
import com.r1nn.contextq.support.MutableClock;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private JwtProvider jwtProvider;
  @Autowired private JwtProperties jwtProperties;

  @Test
  void healthIsPublicAndUp() throws Exception {
    mockMvc
        .perform(MockMvcRequestBuilders.get("/actuator/health"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("UP"));
  }

  @Test
  void apiDocsArePublic() throws Exception {
    mockMvc.perform(MockMvcRequestBuilders.get("/v3/api-docs")).andExpect(status().isOk());
  }

  @Test
  void swaggerUiIsPublic() throws Exception {
    mockMvc
        .perform(MockMvcRequestBuilders.get("/swagger-ui/index.html"))
        .andExpect(status().isOk());
  }

  @Test
  void missingTokenIsAuthTokenMissing() throws Exception {
    mockMvc
        .perform(MockMvcRequestBuilders.get("/api/v1/anything"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.success").value(false))
        .andExpect(jsonPath("$.error.code").value("AUTH_TOKEN_MISSING"));
  }

  @Test
  void rejectedRequestStillCarriesRequestId() throws Exception {
    mockMvc
        .perform(
            MockMvcRequestBuilders.get("/api/v1/anything")
                .header("X-Request-Id", "a1b2c3d4-0000-4000-8000-000000000001"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string("X-Request-Id", "a1b2c3d4-0000-4000-8000-000000000001"));
  }

  @Test
  void forgedTokenIsInvalidEvenOnPublicPath() throws Exception {
    mockMvc
        .perform(
            MockMvcRequestBuilders.get("/api/v1/sources")
                .header(HttpHeaders.AUTHORIZATION, "Bearer not.a.jwt"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.error.code").value("AUTH_TOKEN_INVALID"));
  }

  @Test
  void expiredTokenIsAuthTokenExpired() throws Exception {
    MutableClock past = new MutableClock(Instant.now().minus(Duration.ofHours(2)));
    String expired = new JwtProvider(jwtProperties, past).issue(1L, UserRole.ROLE_USER);

    mockMvc
        .perform(
            MockMvcRequestBuilders.get("/api/v1/anything")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + expired))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.error.code").value("AUTH_TOKEN_EXPIRED"));
  }

  @Test
  void staleTokenDoesNotBlockAuthEndpoints() throws Exception {
    mockMvc
        .perform(
            MockMvcRequestBuilders.post("/api/v1/auth/signup")
                .header(HttpHeaders.AUTHORIZATION, "Bearer not.a.jwt")
                .contentType("application/json")
                .content("{}"))
        .andExpect(status().isBadRequest());
  }

  @Test
  void userTokenOnAdminPathIsForbidden() throws Exception {
    mockMvc
        .perform(
            MockMvcRequestBuilders.get("/api/v1/admin/index/status")
                .header(HttpHeaders.AUTHORIZATION, bearer(UserRole.ROLE_USER)))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.error.code").value("FORBIDDEN"));
  }

  @Test
  void adminTokenPassesAdminPath() throws Exception {
    // an unmapped admin path: passing security means the MVC 404, not 401/403
    mockMvc
        .perform(
            MockMvcRequestBuilders.get("/api/v1/admin/not-mapped")
                .header(HttpHeaders.AUTHORIZATION, bearer(UserRole.ROLE_ADMIN)))
        .andExpect(status().isNotFound());
  }

  private String bearer(UserRole role) {
    return "Bearer " + jwtProvider.issue(1L, role);
  }
}
