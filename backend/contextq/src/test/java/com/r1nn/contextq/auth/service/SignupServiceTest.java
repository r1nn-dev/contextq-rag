package com.r1nn.contextq.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.dto.SignupRequest;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.common.error.BusinessException;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.crypto.password.PasswordEncoder;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
class SignupServiceTest {

  private static final Validator VALIDATOR =
      Validation.buildDefaultValidatorFactory().getValidator();

  @Autowired private SignupService signupService;
  @Autowired private UserRepository users;
  @Autowired private PasswordEncoder passwordEncoder;

  @Test
  void storesNormalizedEmailAndBcryptHash() {
    String email = unique("New.User");

    Long id = signupService.signup(new SignupRequest("  " + email + "  ", "pass1234"));

    User user = users.findById(id).orElseThrow();
    assertThat(user.getEmail()).isEqualTo(email.toLowerCase());
    assertThat(user.getPasswordHash()).startsWith("$2a$10$");
    assertThat(passwordEncoder.matches("pass1234", user.getPasswordHash())).isTrue();
  }

  @Test
  void duplicateEmailIgnoringCaseIsInvalidEmail() {
    String email = unique("dup");
    signupService.signup(new SignupRequest(email, "pass1234"));

    assertThatThrownBy(
            () -> signupService.signup(new SignupRequest(email.toUpperCase(), "pass5678")))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> {
              assertThat(e.getDetails().getFirst().field()).isEqualTo("email");
              assertThat(e.getDetails().getFirst().reason()).isEqualTo("이미 사용 중인 이메일입니다.");
            });
  }

  @Test
  void passwordEqualToEmailIsRejected() {
    String email = "abc12345@ex.co";

    assertThatThrownBy(() -> signupService.signup(new SignupRequest(email, "ABC12345@EX.CO")))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.getDetails().getFirst().field()).isEqualTo("password"));
  }

  @ParameterizedTest
  @ValueSource(strings = {"plain", "a@b", "a@@b.com", "a b@c.com", "@b.com", "a@.com", "a@b.", ""})
  void malformedEmailIsRejected(String email) {
    assertThat(violations(new SignupRequest(email, "pass1234"))).containsExactly("email");
  }

  @Test
  void emailOver254IsRejected() {
    String email = "a".repeat(245) + "@exam.com"; // 254
    assertThat(violations(new SignupRequest(email, "pass1234"))).isEmpty();
    assertThat(violations(new SignupRequest("a" + email, "pass1234"))).containsExactly("email");
  }

  @ParameterizedTest
  @ValueSource(strings = {"short1a", "onlyletters", "12345678", ""})
  void weakPasswordIsRejected(String password) {
    assertThat(violations(new SignupRequest("user@example.com", password)))
        .containsExactly("password");
  }

  @Test
  void passwordLengthBoundaries() {
    assertThat(violations(new SignupRequest("u@example.com", "a1" + "x".repeat(62)))).isEmpty();
    assertThat(violations(new SignupRequest("u@example.com", "a1" + "x".repeat(63))))
        .containsExactly("password");
  }

  private static Set<String> violations(SignupRequest request) {
    return VALIDATOR.validate(request).stream()
        .map(ConstraintViolation::getPropertyPath)
        .map(Object::toString)
        .collect(Collectors.toSet());
  }

  private static String unique(String prefix) {
    return prefix + System.nanoTime() + "@Example.com";
  }
}
