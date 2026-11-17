import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { Icon } from '@/components/common/Icon'
import { QUESTION_MAX_LENGTH } from '@/types/chat'

interface ComposerProps {
  placeholder: string
  hint: string | null
  disabled: boolean
  value: string
  onChange: (value: string) => void
  onSubmit: (question: string) => void
  onStop?: () => void
  streaming?: boolean
}

export function Composer({
  placeholder,
  hint,
  disabled,
  value,
  onChange,
  onSubmit,
  onStop,
  streaming = false,
}: ComposerProps): JSX.Element {
  const [focused, setFocused] = useState(false)
  const trimmed = value.trim()
  const tooLong = trimmed.length > QUESTION_MAX_LENGTH
  const canSend = !disabled && trimmed.length > 0 && !tooLong

  const submit = (e?: FormEvent): void => {
    e?.preventDefault()
    if (canSend) onSubmit(trimmed)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    // Ctrl+Enter (Cmd+Enter on macOS) sends; plain Enter inserts a newline
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form className="composer" onSubmit={submit}>
      {(focused || value !== '') && hint !== null && (
        <div className="composer-hint">
          {hint}
          {trimmed.length > QUESTION_MAX_LENGTH - 100 && (
            <span className={tooLong ? 'over' : undefined}>
              {' '}
              · {trimmed.length}/{QUESTION_MAX_LENGTH}
            </span>
          )}
        </div>
      )}
      <div className="composer-row">
        <textarea
          rows={1}
          value={value}
          placeholder={placeholder}
          disabled={disabled}
          aria-label="질문 입력"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
        />
        {streaming && onStop !== undefined ? (
          <button type="button" className="composer-send stop" onClick={onStop} aria-label="답변 중단">
            <Icon name="stop" size={16} />
          </button>
        ) : (
          <button type="submit" className="composer-send" disabled={!canSend} aria-label="질문 보내기">
            <Icon name="send" size={18} />
          </button>
        )}
      </div>
    </form>
  )
}
