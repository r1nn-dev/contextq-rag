import { Link } from 'react-router-dom'

export function NotFoundPage(): JSX.Element {
  return (
    <div className="full-center">
      <h1>페이지를 찾을 수 없습니다</h1>
      <p className="muted">주소가 바뀌었거나 없는 화면입니다.</p>
      <Link to="/" className="btn btn-outline">
        처음으로
      </Link>
    </div>
  )
}
