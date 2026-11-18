package com.r1nn.contextq.chat.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.global.config.AiServerProperties;
import com.r1nn.contextq.infra.aiserver.AiServerSourcesClient;
import com.r1nn.contextq.infra.aiserver.AiServerUnavailableException;
import com.r1nn.contextq.infra.aiserver.InternalSources;
import com.r1nn.contextq.support.MutableClock;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class SourceCatalogTest {

  private final AiServerSourcesClient client = mock(AiServerSourcesClient.class);
  private final MutableClock clock = new MutableClock();
  private final SourceCatalog catalog =
      new SourceCatalog(
          client,
          clock,
          new AiServerProperties(
              "http://unused",
              null,
              Duration.ofSeconds(3),
              Duration.ofSeconds(5),
              Duration.ofSeconds(15),
              Duration.ofSeconds(30),
              Duration.ofSeconds(60)));

  @Test
  void secondCallWithinTtlUsesCache() {
    when(client.fetch()).thenReturn(catalog("run7"));

    catalog.current();
    clock.advance(Duration.ofSeconds(59));
    catalog.current();

    verify(client, times(1)).fetch();
  }

  @Test
  void refetchesAfterTtl() {
    when(client.fetch()).thenReturn(catalog("run7"), catalog("run8"));

    catalog.current();
    clock.advance(Duration.ofSeconds(60));

    assertThat(catalog.current().sources().getFirst().displayName()).isEqualTo("run8");
  }

  @Test
  void keepsPreviousSnapshotWhenRefreshFails() {
    when(client.fetch())
        .thenReturn(catalog("run7"))
        .thenThrow(new AiServerUnavailableException("down", null));

    catalog.current();
    clock.advance(Duration.ofSeconds(61));

    assertThat(catalog.current().sources().getFirst().displayName()).isEqualTo("run7");
    // failed refresh is retried only after the short back-off, not on every request
    catalog.current();
    verify(client, times(2)).fetch();
  }

  @Test
  void firstFailureIsAiUnavailable() {
    when(client.fetch()).thenThrow(new AiServerUnavailableException("down", null));

    assertThatThrownBy(catalog::current)
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.AI_UNAVAILABLE));
  }

  @Test
  void compareNeedsBothSourcesAskableAndACatalogPairInOrder() {
    when(client.fetch()).thenReturn(compareCatalog(true));

    assertThatCode(() -> catalog.requireComparable("langchain_v03", "langchain_v1x", false))
        .doesNotThrowAnyException();
    assertThatThrownBy(() -> catalog.requireComparable("langchain_v1x", "langchain_v03", false))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> {
              assertThat(e.getErrorCode()).isEqualTo(ErrorCode.INVALID_REQUEST);
              assertThat(e.getDetails().getFirst().field()).isEqualTo("sourceKeyB");
            });
  }

  @Test
  void compareWithAnInactiveSideIsSourceUnavailable() {
    when(client.fetch()).thenReturn(compareCatalog(false));

    assertThatThrownBy(() -> catalog.requireComparable("langchain_v03", "langchain_v1x", true))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.SOURCE_UNAVAILABLE));
  }

  static InternalSources compareCatalog(boolean newerEnabled) {
    InternalSources.Source older = catalog("v0.3").sources().getFirst();
    InternalSources.Source newer =
        new InternalSources.Source(
            "langchain_v1x",
            "langchain",
            "v1.x",
            "LangChain v1.x",
            newerEnabled,
            8L,
            "89abcdef0123456789abcdef0123456789abcdef",
            "2026-10-05",
            20);
    return new InternalSources(
        List.of(older, newer),
        List.of(new InternalSources.ComparePair("langchain_v03", "langchain_v1x")));
  }

  static InternalSources catalog(String displayName) {
    return new InternalSources(
        List.of(
            new InternalSources.Source(
                "langchain_v03",
                "langchain",
                "v0.3",
                displayName,
                true,
                7L,
                "0123456789abcdef0123456789abcdef01234567",
                "2026-10-05",
                10)),
        List.of());
  }
}
