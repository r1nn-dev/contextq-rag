package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.r1nn.contextq.chat.service.StreamSlots.Slot;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import org.junit.jupiter.api.Test;

class StreamSlotsTest {

  private final StreamSlots slots = new StreamSlots();

  @Test
  void thirdStreamOfAUserIsLimited() {
    slots.acquire("u:1", 2);
    slots.acquire("u:1", 2);

    Throwable thrown = catchThrowable(() -> slots.acquire("u:1", 2));

    assertThat(((BusinessException) thrown).getErrorCode())
        .isEqualTo(ErrorCode.CONCURRENT_STREAM_LIMIT);
  }

  @Test
  void releaseIsIdempotentAndFreesTheSlot() {
    Slot first = slots.acquire("g:abc", 1);

    first.release();
    first.release();

    assertThat(slots.openCount("g:abc")).isZero();
    assertThatCode(() -> slots.acquire("g:abc", 1)).doesNotThrowAnyException();
  }

  @Test
  void keysAreIndependent() {
    slots.acquire("u:1", 1);

    assertThatCode(() -> slots.acquire("u:2", 1)).doesNotThrowAnyException();
  }
}
