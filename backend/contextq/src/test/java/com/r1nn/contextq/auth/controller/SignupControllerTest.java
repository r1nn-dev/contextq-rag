package com.r1nn.contextq.auth.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.r1nn.contextq.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

  @Autowired private MockMvc mockMvc;

  @Test
  void signupIsPublicAndReturns201() throws Exception {
    mockMvc
        .perform(signup("user" + System.nanoTime() + "@example.com", "pass1234"))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.success").value(true))
        .andExpect(jsonPath("$.message").value("회원가입이 완료되었습니다."))
        .andExpect(jsonPath("$.data.userId").isNumber());
  }

  @Test
  void invalidFieldsListEachReason() throws Exception {
    mockMvc
        .perform(signup("not-an-email", "short"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"))
        .andExpect(jsonPath("$.error.details.length()").value(2));
  }

  @Test
  void duplicateEmailIsInvalidRequest() throws Exception {
    String email = "twice" + System.nanoTime() + "@example.com";
    mockMvc.perform(signup(email, "pass1234")).andExpect(status().isCreated());

    mockMvc
        .perform(signup(email.toUpperCase(), "pass1234"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.error.details[0].field").value("email"))
        .andExpect(jsonPath("$.error.details[0].reason").value("이미 사용 중인 이메일입니다."));
  }

  private static org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder signup(
      String email, String password) {
    return post("/api/v1/auth/signup")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"email\":\"" + email + "\",\"password\":\"" + password + "\"}");
  }
}
