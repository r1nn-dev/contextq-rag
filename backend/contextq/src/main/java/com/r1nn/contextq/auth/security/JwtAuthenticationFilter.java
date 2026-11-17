package com.r1nn.contextq.auth.security;

import com.r1nn.contextq.auth.service.JwtProvider;
import com.r1nn.contextq.auth.service.JwtProvider.AccessClaims;
import com.r1nn.contextq.common.error.BusinessException;
import com.r1nn.contextq.common.web.ErrorResponseWriter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Reads {@code Authorization: Bearer <access token>} (api-spec §0.1, 부록 D.1).
 *
 * <p>Valid token → authenticated principal whose name is the user ID ({@code sub}) and whose
 * authority is the role. No header → anonymous (the entry point answers {@code AUTH_TOKEN_MISSING}
 * on protected paths). A present but expired or invalid token is answered with 401 at once, also on
 * public paths, so the client refreshes instead of silently becoming a guest — except under {@code
 * /api/v1/auth/}, where login·refresh must work with a stale header.
 *
 * <p>Not a Spring bean on purpose: it is added to the security chain only, never to the servlet
 * filter chain.
 */
public class JwtAuthenticationFilter extends OncePerRequestFilter {

  private static final String BEARER = "Bearer ";
  private static final String AUTH_PATH = "/api/v1/auth/";

  private final JwtProvider jwtProvider;
  private final ErrorResponseWriter errorWriter;

  public JwtAuthenticationFilter(JwtProvider jwtProvider, ErrorResponseWriter errorWriter) {
    this.jwtProvider = jwtProvider;
    this.errorWriter = errorWriter;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    String header = request.getHeader(HttpHeaders.AUTHORIZATION);
    if (header == null || !header.startsWith(BEARER)) {
      chain.doFilter(request, response);
      return;
    }
    try {
      AccessClaims claims = jwtProvider.verify(header.substring(BEARER.length()).strip());
      UsernamePasswordAuthenticationToken authentication =
          new UsernamePasswordAuthenticationToken(
              String.valueOf(claims.userId()),
              null,
              List.of(new SimpleGrantedAuthority(claims.role().name())));
      SecurityContextHolder.getContext().setAuthentication(authentication);
    } catch (BusinessException e) {
      if (!request.getRequestURI().startsWith(AUTH_PATH)) {
        errorWriter.write(response, e.getErrorCode());
        return;
      }
    }
    chain.doFilter(request, response);
  }
}
