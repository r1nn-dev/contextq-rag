package com.r1nn.contextq.infra.aiserver;

import com.r1nn.contextq.global.config.AiServerProperties;
import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

/**
 * WebClient for the ai-server internal API (ADR-012, policy §2.1).
 *
 * <p>Built directly from {@link WebClient#builder()}: Spring Boot 4 ships the {@code
 * WebClient.Builder} auto-configuration in a separate module that this servlet app does not use.
 *
 * <p>Every call carries {@code X-Internal-Token}. The token is never logged. Calls run outside any
 * DB transaction (callers must not hold one).
 */
@Configuration
public class AiServerWebClientConfig {

  public static final String INTERNAL_TOKEN_HEADER = "X-Internal-Token";

  @Bean
  WebClient aiServerWebClient(AiServerProperties properties) {
    HttpClient httpClient =
        HttpClient.create()
            .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS, (int) properties.connectTimeout().toMillis());
    WebClient.Builder configured =
        WebClient.builder()
            .baseUrl(properties.baseUrl())
            .clientConnector(new ReactorClientHttpConnector(httpClient));
    if (properties.internalToken() != null && !properties.internalToken().isBlank()) {
      configured.defaultHeader(INTERNAL_TOKEN_HEADER, properties.internalToken());
    }
    return configured.build();
  }
}
