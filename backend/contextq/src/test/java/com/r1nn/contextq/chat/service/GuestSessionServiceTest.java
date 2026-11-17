package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.chat.domain.GuestSession;
import com.r1nn.contextq.chat.repository.GuestSessionRepository;
import com.r1nn.contextq.chat.service.GuestSessionService.GuestStatus;
import com.r1nn.contextq.chat.service.GuestSessionService.GuestTicket;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.support.FixedClockConfiguration;
import com.r1nn.contextq.support.MutableClock;
import java.time.Duration;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** policy §1.3: issue on first question, 5 per session, 30 new sessions per IP per hour. */
@Import({TestcontainersConfiguration.class, FixedClockConfiguration.class})
@SpringBootTest
class GuestSessionServiceTest {

  static final Pattern SID = Pattern.compile("devdocs_sid=([^;]+)");

  @Autowired private GuestSessionService service;
  @Autowired private GuestSessionRepository sessions;
  @Autowired private MutableClock clock;

  @Test
  void firstQuestionIssuesCookieAndLaterQuestionsReuseIt() {
    GuestTicket first = service.charge(null, ip());

    assertThat(first.setCookie())
        .contains("HttpOnly", "Secure", "SameSite=Strict", "Path=/api", "Max-Age=86400");
    String raw = sid(first);
    assertThat(raw).hasSize(22); // 128-bit Base64URL
    GuestTicket second = service.charge(raw, ip());
    assertThat(second.setCookie()).isNull();
    assertThat(second.sidHash()).isEqualTo(first.sidHash());
    assertThat(service.status(raw))
        .isEqualTo(new GuestStatus(5, 2, 3, session(first).getExpiresAt()));
  }

  @Test
  void sixthQuestionIsRejectedAndDoesNotResetTheLimit() {
    String raw = sid(service.charge(null, ip()));
    for (int i = 0; i < 4; i++) {
      service.charge(raw, ip());
    }

    assertThat(code(() -> service.charge(raw, ip()))).isEqualTo(ErrorCode.GUEST_QUOTA_EXCEEDED);
    assertThat(service.status(raw).remaining()).isZero();
  }

  @Test
  void expiredOrUnknownCookieStartsANewSession() {
    String ip = ip();
    String raw = sid(service.charge(null, ip));

    clock.advance(Duration.ofHours(24));
    GuestTicket renewed = service.charge(raw, ip);
    assertThat(renewed.setCookie()).isNotNull();
    assertThat(service.charge("unknown-sid", ip).setCookie()).isNotNull();
    assertThat(service.status(raw).used()).isZero(); // expired session reads as fresh
  }

  @Test
  void thirtyFirstNewSessionFromOneIpIsLimited() {
    String ip = ip();
    for (int i = 0; i < 30; i++) {
      service.charge(null, ip);
    }

    assertThat(code(() -> service.charge(null, ip))).isEqualTo(ErrorCode.GUEST_SESSION_LIMIT);
    clock.advance(Duration.ofHours(1).plusSeconds(1));
    assertThat(service.charge(null, ip).setCookie()).isNotNull();
  }

  @Test
  void refundGivesTheQuestionBack() {
    GuestTicket ticket = service.charge(null, ip());

    service.refund(ticket.sidHash());

    assertThat(session(ticket).getUsedCount()).isZero();
  }

  @Test
  void statusWithoutCookieIsFullAndIssuesNothing() {
    long before = sessions.count();

    assertThat(service.status(null)).isEqualTo(new GuestStatus(5, 0, 5, null));
    assertThat(sessions.count()).isEqualTo(before);
  }

  private GuestSession session(GuestTicket ticket) {
    return sessions.findBySidHash(ticket.sidHash()).orElseThrow();
  }

  private static String sid(GuestTicket ticket) {
    Matcher m = SID.matcher(ticket.setCookie());
    assertThat(m.find()).isTrue();
    return m.group(1);
  }

  private static ErrorCode code(Runnable call) {
    Throwable thrown = catchThrowable(call::run);
    assertThat(thrown).isInstanceOf(BusinessException.class);
    return ((BusinessException) thrown).getErrorCode();
  }

  /** A fresh documentation-range IP per test so the per-IP count starts at zero. */
  private static String ip() {
    return "198.51.100." + (System.nanoTime() % 250) + "-" + System.nanoTime();
  }
}
