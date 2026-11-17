package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.QuotaProperties;
import com.r1nn.contextq.support.MutableClock;
import java.time.Duration;
import org.junit.jupiter.api.Test;

/** policy §8.1: 10 questions per minute per user, Retry-After until the next token. */
class QuestionRateLimiterTest {

  private final MutableClock clock = new MutableClock();
  private final QuestionRateLimiter limiter =
      new QuestionRateLimiter(new QuotaProperties(10, 100, 2, 1), clock);

  @Test
  void eleventhQuestionWithinAMinuteIsLimited() {
    for (int i = 0; i < 10; i++) {
      limiter.acquire(1L);
    }

    Throwable thrown = catchThrowable(() -> limiter.acquire(1L));

    assertThat(thrown).isInstanceOf(BusinessException.class);
    BusinessException e = (BusinessException) thrown;
    assertThat(e.getErrorCode()).isEqualTo(ErrorCode.RATE_LIMITED);
    assertThat(e.getHeaders()).containsEntry("Retry-After", "6");
  }

  @Test
  void oneTokenComesBackEverySixSeconds() {
    for (int i = 0; i < 10; i++) {
      limiter.acquire(1L);
    }

    clock.advance(Duration.ofSeconds(6));
    assertThatCode(() -> limiter.acquire(1L)).doesNotThrowAnyException();
    assertThat(catchThrowable(() -> limiter.acquire(1L))).isInstanceOf(BusinessException.class);
  }

  @Test
  void usersHaveSeparateBuckets() {
    for (int i = 0; i < 10; i++) {
      limiter.acquire(1L);
    }

    assertThatCode(() -> limiter.acquire(2L)).doesNotThrowAnyException();
  }
}
