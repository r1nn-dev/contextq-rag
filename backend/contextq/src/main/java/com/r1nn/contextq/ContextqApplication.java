package com.r1nn.contextq;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ContextqApplication {

  public static void main(String[] args) {
    SpringApplication.run(ContextqApplication.class, args);
  }
}
