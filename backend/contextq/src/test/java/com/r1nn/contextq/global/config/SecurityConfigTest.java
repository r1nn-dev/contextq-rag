package com.r1nn.contextq.global.config;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigTest {

  @Autowired private MockMvc mockMvc;

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
  void otherPathsRequireAuthentication() throws Exception {
    mockMvc
        .perform(MockMvcRequestBuilders.get("/api/v1/anything"))
        .andExpect(status().isUnauthorized());
  }
}
