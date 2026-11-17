package com.r1nn.contextq.auth.service;

import com.r1nn.contextq.auth.domain.User;
import com.r1nn.contextq.auth.repository.UserRepository;
import com.r1nn.contextq.global.config.AdminSeedProperties;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Component;

/**
 * Creates the admin account from environment variables once at startup (policy §1.1, all profiles
 * per §9.1). Skips when either value is empty or the account already exists. A value that is not a
 * BCrypt hash is refused, so no admin with an unusable password is created.
 */
@Component
public class AdminSeeder implements ApplicationRunner {

  public enum Result {
    CREATED,
    EXISTS,
    DISABLED,
    INVALID_HASH
  }

  private static final Logger log = LoggerFactory.getLogger(AdminSeeder.class);
  private static final Pattern BCRYPT = Pattern.compile("^\\$2[aby]\\$\\d{2}\\$[./A-Za-z0-9]{53}$");

  private final UserRepository users;
  private final AdminSeedProperties properties;

  public AdminSeeder(UserRepository users, AdminSeedProperties properties) {
    this.users = users;
    this.properties = properties;
  }

  @Override
  public void run(ApplicationArguments args) {
    seed();
  }

  public Result seed() {
    String email = User.normalizeEmail(properties.email());
    String hash = properties.passwordBcrypt() == null ? null : properties.passwordBcrypt().strip();
    if (email == null || email.isEmpty() || hash == null || hash.isEmpty()) {
      log.info("admin_seed_skipped reason=not_configured");
      return Result.DISABLED;
    }
    if (!BCRYPT.matcher(hash).matches()) {
      log.error("admin_seed_skipped reason=invalid_bcrypt_hash");
      return Result.INVALID_HASH;
    }
    if (users.existsByEmail(email)) {
      log.info("admin_seed_skipped reason=exists");
      return Result.EXISTS;
    }
    try {
      users.saveAndFlush(User.admin(email, hash));
    } catch (DataIntegrityViolationException e) {
      log.info("admin_seed_skipped reason=exists (concurrent start)");
      return Result.EXISTS;
    }
    log.info("admin_seed_created");
    return Result.CREATED;
  }
}
