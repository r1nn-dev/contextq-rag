package com.r1nn.contextq.common.response;

import static org.assertj.core.api.Assertions.assertThat;

import com.r1nn.contextq.common.error.ErrorBody;
import com.r1nn.contextq.common.error.ErrorBody.FieldReason;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

class ApiResponseTest {

  private final ObjectMapper mapper = JsonMapper.builder().build();

  @Test
  void singleResourceKeepsNullMessageKey() {
    JsonNode json = mapper.valueToTree(ApiResponse.ok(Map.of("userId", 12)));

    assertThat(json.propertyNames()).containsExactly("success", "message", "data");
    assertThat(json.get("success").booleanValue()).isTrue();
    assertThat(json.get("message").isNull()).isTrue();
    assertThat(json.get("data").get("userId").intValue()).isEqualTo(12);
  }

  @Test
  void actionResultKeepsNullDataKey() {
    JsonNode json = mapper.valueToTree(ApiResponse.ok("로그아웃되었습니다.", null));

    assertThat(json.propertyNames()).containsExactly("success", "message", "data");
    assertThat(json.get("message").asString()).isEqualTo("로그아웃되었습니다.");
    assertThat(json.get("data").isNull()).isTrue();
  }

  @Test
  void failureHasOnlySuccessAndError() {
    ErrorBody error =
        new ErrorBody(
            "INVALID_REQUEST",
            "입력값을 확인해주세요.",
            List.of(new FieldReason("email", "올바른 이메일 형식이 아닙니다.")));

    JsonNode json = mapper.valueToTree(ApiResponse.fail(error));

    assertThat(json.propertyNames()).containsExactly("success", "error");
    assertThat(json.get("success").booleanValue()).isFalse();
    assertThat(json.at("/error/code").asString()).isEqualTo("INVALID_REQUEST");
    assertThat(json.at("/error/details/0/field").asString()).isEqualTo("email");
  }

  @Test
  void failureWithoutDetailsHasEmptyArray() {
    JsonNode json = mapper.valueToTree(ApiResponse.fail(new ErrorBody("AUTH_LOCKED", "잠금", null)));

    assertThat(json.at("/error/details").isArray()).isTrue();
    assertThat(json.at("/error/details").size()).isZero();
  }

  @Test
  void cursorPageSerializesCamelCaseFields() {
    JsonNode json =
        mapper.valueToTree(
            ApiResponse.ok(new CursorResponse<>(List.of(1, 2), "2026-10-01T09:00:00Z", true)));

    assertThat(json.at("/data").propertyNames()).containsExactly("items", "cursor", "hasNext");
    assertThat(json.at("/data/hasNext").booleanValue()).isTrue();
  }
}
