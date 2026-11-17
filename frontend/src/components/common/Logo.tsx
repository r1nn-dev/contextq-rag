import { Icon } from './Icon'

export function LogoMark({ size = 28 }: { size?: number }): JSX.Element {
  return (
    <span className="logo-mark">
      <Icon name="bolt" size={Math.round(size * 0.6)} />
    </span>
  )
}

export function Logo({ subtitle }: { subtitle?: string }): JSX.Element {
  return (
    <>
      <LogoMark />
      <span>
        <span className="logo-title">ContextQ</span>
        {subtitle !== undefined && <span className="logo-sub">{subtitle}</span>}
      </span>
    </>
  )
}
