package com.r1nn.contextq.common.web;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class RequestIdFilterTest {

  private final RequestIdFilter filter = new RequestIdFilter();

  @Test
  void reusesIncomingUuid() throws Exception {
    String incoming = "a1b2c3d4-0000-4000-8000-000000000001";
    MockHttpServletResponse response = run(incoming, new AtomicReference<>());

    assertThat(response.getHeader(RequestIdFilter.HEADER)).isEqualTo(incoming);
  }

  @Test
  void createsUuidWhenHeaderMissing() throws Exception {
    MockHttpServletResponse response = run(null, new AtomicReference<>());

    UUID created = UUID.fromString(response.getHeader(RequestIdFilter.HEADER));
    assertThat(created.version()).isEqualTo(4);
  }

  @Test
  void replacesMalformedHeader() throws Exception {
    MockHttpServletResponse response = run("abc\r\nInjected: 1", new AtomicReference<>());

    assertThat(response.getHeader(RequestIdFilter.HEADER)).doesNotContain("Injected");
    UUID.fromString(response.getHeader(RequestIdFilter.HEADER));
  }

  @Test
  void exposesIdInLogContextOnlyDuringRequest() throws Exception {
    AtomicReference<String> seen = new AtomicReference<>();
    MockHttpServletResponse response = run(null, seen);

    assertThat(seen.get()).isEqualTo(response.getHeader(RequestIdFilter.HEADER));
    assertThat(MDC.get(RequestIdFilter.MDC_KEY)).isNull();
  }

  private MockHttpServletResponse run(String header, AtomicReference<String> seenInChain)
      throws Exception {
    MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/sources");
    if (header != null) {
      request.addHeader(RequestIdFilter.HEADER, header);
    }
    MockHttpServletResponse response = new MockHttpServletResponse();
    MockFilterChain chain =
        new MockFilterChain() {
          @Override
          public void doFilter(
              jakarta.servlet.ServletRequest req, jakarta.servlet.ServletResponse res) {
            seenInChain.set(MDC.get(RequestIdFilter.MDC_KEY));
          }
        };
    filter.doFilter(request, response, chain);
    return response;
  }
}
