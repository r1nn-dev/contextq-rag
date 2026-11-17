package com.r1nn.contextq.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

import com.r1nn.contextq.TestcontainersConfiguration;
import com.r1nn.contextq.auth.domain.RefreshToken;
import com.r1nn.contextq.auth.domain.TokenFamily;
import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.repository.RefreshTokenRepository;
import com.r1nn.contextq.auth.repository.TokenFamilyRepository;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.auth.service.RefreshTokenService.Issued;
import com.r1nn.contextq.auth.service.RefreshTokenService.Rotated;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.support.FixedClockConfiguration;
import com.r1nn.contextq.support.MutableClock;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;

/** policy §1.2·§10.3, INV-15: rotation, 5-second grace, reuse detection, 10-family cap. */
@Import({TestcontainersConfiguration.class, FixedClockConfiguration.class})
@SpringBootTest
class RefreshTokenServiceTest {

  @Autowired private RefreshTokenService service;
  @Autowired private RefreshTokenRepository tokens;
  @Autowired private TokenFamilyRepository families;
  @Autowired private UserRepository users;
  @Autowired private MutableClock clock;

  private Long userId;

  @BeforeEach
  void setUp() {
    userId = users.save(User.member("rf" + System.nanoTime() + "@example.com", "$2a$10$x")).getId();
  }

  @Test
  void rotationLeavesExactlyOneActiveToken() {
    Issued first = service.startFamily(userId);

    Rotated rotated = service.rotate(first.rawToken());

    assertThat(rotated.userId()).isEqualTo(userId);
    assertThat(rotated.next().rawToken()).isNotEqualTo(first.rawToken());
    Long familyId = familyOf(first);
    assertThat(tokens.countByFamily_IdAndStatus(familyId, RefreshToken.Status.ACTIVE)).isEqualTo(1);
    assertThat(tokens.countByFamily_IdAndStatus(familyId, RefreshToken.Status.USED)).isEqualTo(1);
    assertThat(tokenStatus(first)).isEqualTo(RefreshToken.Status.USED);
    assertThat(stored(rotated.next().rawToken())).doesNotContain(rotated.next().rawToken());
  }

  @Test
  void resendWithinGraceIsConflictAndChangesNothing() {
    Issued first = service.startFamily(userId);
    service.rotate(first.rawToken());

    clock.advance(Duration.ofSeconds(4));
    BusinessException e = failure(first.rawToken());

    assertThat(e.getErrorCode()).isEqualTo(ErrorCode.AUTH_REFRESH_CONFLICT);
    assertThat(e.getHeaders()).doesNotContainKey(HttpHeaders.SET_COOKIE);
    assertThat(tokens.countByFamily_IdAndStatus(familyOf(first), RefreshToken.Status.ACTIVE))
        .isEqualTo(1);
  }

  @Test
  void resendAfterGraceRevokesTheWholeFamily() {
    Issued first = service.startFamily(userId);
    Rotated rotated = service.rotate(first.rawToken());

    clock.advance(Duration.ofSeconds(6));
    BusinessException e = failure(first.rawToken());

    assertThat(e.getErrorCode()).isEqualTo(ErrorCode.AUTH_REFRESH_REUSED);
    assertThat(e.getHeaders().get(HttpHeaders.SET_COOKIE)).contains("Max-Age=0");
    assertThat(tokens.countByFamily_IdAndStatus(familyOf(first), RefreshToken.Status.ACTIVE))
        .isZero();
    assertThat(failure(rotated.next().rawToken()).getErrorCode())
        .isEqualTo(ErrorCode.AUTH_REFRESH_INVALID);
  }

  @Test
  void familyExpiresSevenDaysAfterLoginEvenWithRotation() {
    Issued token = service.startFamily(userId);
    clock.advance(Duration.ofDays(6));
    Rotated rotated = service.rotate(token.rawToken());
    assertThat(rotated.next().maxAge()).isEqualTo(Duration.ofDays(1));

    clock.advance(Duration.ofDays(1));

    assertThat(failure(rotated.next().rawToken()).getErrorCode())
        .isEqualTo(ErrorCode.AUTH_REFRESH_EXPIRED);
  }

  @Test
  void missingAndUnknownTokens() {
    assertThat(failure(null).getErrorCode()).isEqualTo(ErrorCode.AUTH_REFRESH_MISSING);
    assertThat(failure("unknown-token").getErrorCode()).isEqualTo(ErrorCode.AUTH_REFRESH_INVALID);
  }

  @Test
  void logoutIsIdempotentAndRevokes() {
    Issued token = service.startFamily(userId);

    service.logout(token.rawToken());
    service.logout(token.rawToken());
    service.logout(null);

    assertThat(failure(token.rawToken()).getErrorCode()).isEqualTo(ErrorCode.AUTH_REFRESH_INVALID);
  }

  @Test
  void eleventhLoginRevokesTheOldestFamily() {
    Issued oldest = service.startFamily(userId);
    for (int i = 0; i < 10; i++) {
      clock.advance(Duration.ofSeconds(1));
      service.startFamily(userId);
    }

    List<TokenFamily> active = families.findActive(userId, clock.instant());
    assertThat(active).hasSize(10);
    assertThat(families.findById(familyOf(oldest)).orElseThrow().getStatus())
        .isEqualTo(TokenFamily.Status.REVOKED);
  }

  /** Two tabs rotating the same token at once: one wins, the other gets 409 (INV-15). */
  @Test
  void concurrentRotationOfOneTokenHasOneWinner() throws Exception {
    Issued token = service.startFamily(userId);
    CountDownLatch start = new CountDownLatch(1);

    CompletableFuture<Object> a = CompletableFuture.supplyAsync(() -> attempt(start, token));
    CompletableFuture<Object> b = CompletableFuture.supplyAsync(() -> attempt(start, token));
    start.countDown();

    List<Object> results = List.of(a.get(), b.get());
    assertThat(results).filteredOn(r -> r instanceof Rotated).hasSize(1);
    assertThat(results).filteredOn(r -> r == ErrorCode.AUTH_REFRESH_CONFLICT).hasSize(1);
    assertThat(tokens.countByFamily_IdAndStatus(familyOf(token), RefreshToken.Status.ACTIVE))
        .isEqualTo(1);
  }

  private Object attempt(CountDownLatch start, Issued token) {
    try {
      start.await();
      return service.rotate(token.rawToken());
    } catch (BusinessException e) {
      return e.getErrorCode();
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException(e);
    }
  }

  private BusinessException failure(String raw) {
    Throwable thrown = catchThrowable(() -> service.rotate(raw));
    assertThat(thrown).isInstanceOf(BusinessException.class);
    return (BusinessException) thrown;
  }

  private Long familyOf(Issued issued) {
    return tokens
        .findFamilyIdByTokenHash(RefreshTokenService.hash(issued.rawToken()))
        .orElseThrow();
  }

  private RefreshToken.Status tokenStatus(Issued issued) {
    return tokens
        .findByTokenHash(RefreshTokenService.hash(issued.rawToken()))
        .orElseThrow()
        .getStatus();
  }

  private String stored(String raw) {
    return tokens.findByTokenHash(RefreshTokenService.hash(raw)).orElseThrow().getTokenHash();
  }
}
