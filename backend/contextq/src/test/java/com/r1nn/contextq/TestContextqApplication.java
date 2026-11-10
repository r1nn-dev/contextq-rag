package com.r1nn.contextq;

import org.springframework.boot.SpringApplication;

public class TestContextqApplication {

  public static void main(String[] args) {
    SpringApplication.from(ContextqApplication::main)
        .with(TestcontainersConfiguration.class)
        .run(args);
  }
}
