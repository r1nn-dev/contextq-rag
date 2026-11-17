package com.r1nn.contextq.global.config;

import com.r1nn.contextq.auth.security.JwtAuthenticationFilter;
import com.r1nn.contextq.auth.service.JwtProvider;
import com.r1nn.contextq.common.error.ErrorCode;
import com.r1nn.contextq.common.web.ErrorResponseWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Stateless JWT security (api-spec §0.6 권한 매트릭스, policy §1.2).
 *
 * <p>Errors use the common body: no token → 401 {@code AUTH_TOKEN_MISSING}, bad or expired token →
 * 401 from {@link JwtAuthenticationFilter}, wrong role → 403 {@code FORBIDDEN}.
 */
@Configuration
public class SecurityConfig {

  private static final String[] PUBLIC_PATHS = {
    "/actuator/health", "/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html"
  };

  /** Login·signup·refresh·logout work without an access token (api-spec §0.6). */
  private static final String[] AUTH_PUBLIC = {
    "/api/v1/auth/signup", "/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout"
  };

  @Bean
  SecurityFilterChain securityFilterChain(
      HttpSecurity http, JwtProvider jwtProvider, ErrorResponseWriter errorWriter)
      throws Exception {
    http.csrf(csrf -> csrf.disable()) // stateless API; refresh cookie is SameSite=Strict
        .sessionManagement(
            session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .httpBasic(basic -> basic.disable())
        .formLogin(form -> form.disable())
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers(PUBLIC_PATHS)
                    .permitAll()
                    .requestMatchers(HttpMethod.GET, "/api/v1/sources")
                    .permitAll() // guests may list sources
                    .requestMatchers(HttpMethod.POST, AUTH_PUBLIC)
                    .permitAll()
                    .requestMatchers("/api/v1/admin/**")
                    .hasRole("ADMIN")
                    .anyRequest()
                    .authenticated())
        .exceptionHandling(
            ex ->
                ex.authenticationEntryPoint(
                        (request, response, e) ->
                            errorWriter.write(response, ErrorCode.AUTH_TOKEN_MISSING))
                    .accessDeniedHandler(
                        (request, response, e) -> errorWriter.write(response, ErrorCode.FORBIDDEN)))
        .addFilterBefore(
            new JwtAuthenticationFilter(jwtProvider, errorWriter),
            UsernamePasswordAuthenticationFilter.class);
    return http.build();
  }
}
