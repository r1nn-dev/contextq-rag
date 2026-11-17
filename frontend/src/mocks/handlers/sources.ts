// GET /api/v1/sources mock.

import { MOCK_SOURCES } from '../data'
import { ok, route } from '../router'

route('GET', '/sources', () => ok(MOCK_SOURCES))
