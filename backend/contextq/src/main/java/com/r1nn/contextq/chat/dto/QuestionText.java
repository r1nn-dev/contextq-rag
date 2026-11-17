package com.r1nn.contextq.chat.dto;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Question length after trim: 1~1,000 characters (policy §5.1, api-spec §3.1). */
@Documented
@Constraint(validatedBy = QuestionText.Validator.class)
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
public @interface QuestionText {

  int MAX_LENGTH = 1000;

  String message() default "질문은 공백을 제외하고 1~1,000자여야 합니다.";

  Class<?>[] groups() default {};

  Class<? extends Payload>[] payload() default {};

  class Validator implements ConstraintValidator<QuestionText, String> {
    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
      if (value == null) {
        return false;
      }
      int length = value.strip().codePointCount(0, value.strip().length());
      return length >= 1 && length <= MAX_LENGTH;
    }
  }
}
