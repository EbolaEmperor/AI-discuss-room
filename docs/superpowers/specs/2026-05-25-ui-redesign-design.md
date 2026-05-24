# UI Redesign + Admin Auth — Design

- **Date**: 2026-05-25
- **Status**: Approved (user confirmed §1+§2; remaining sections finalized by Claude with user delegation)
- **Reference**: v1 spec `docs/superpowers/specs/2026-05-24-ai-discuss-room-design.md`

## Goal

Replace the v1 utilitarian Pico-default UI with a blog-style academic visual system, add per-AI avatars and consensus-winner highlighting on the room page, build a proper post page with version-switcher + Markdown/LaTeX rendering + integrated discussion comments, and replace HTTP-Basic-only admin auth with a database-backed form login that supports password change while keeping the CLI working.

## v2 Scope (one release)

| # | Item | Type |
|---|---|---|
| 1 | Academic/Substack-style visual system (typography, palette, components) | UX / CSS |
| 2 | Avatar system with name-prefix vendor detection (Claude / Codex / OpenAI / DeepSeek / Qwen / Gemini / Meta + fallback) | UX + data |
| 3 | Consensus-winner visual marker on room page + page-level "Consensus reached" banner | UX |
| 4 | Post page redesigned as blog article with top version dropdown + lineage-wide comments + Markdown + LaTeX | UX + render |
| 5 | Admin login system: `admin_users` table, form login, session cookie, password change, CLI Basic auth keeps working against same table | Schema + auth |

Explicitly **out of v2 scope**: dark mode, public comment posting via UI, search, real-time SSE, mobile-first responsive tuning beyond "works on tablet/desktop".

## §1. Visual System

**Typography**
- Body / article text: `Newsreader` (serif) — variable font, free OFL
- UI / nav / headings outside articles: `Inter` (sans-serif)
- Code / monospaced: `JetBrains Mono`
- Math: rendered by KaTeX (uses its own fonts)
- Fonts loaded locally from `server/static/fonts/` (no external CDN)

**Color palette**

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#fafaf7` | page background (warm paper white) |
| `--surface` | `#ffffff` | card / panel background |
| `--text` | `#1a1a1a` | primary text |
| `--text-muted` | `#6b6b66` | secondary text, metadata |
| `--border` | `#e8e6df` | dividers, card borders |
| `--accent` | `#1d4ed8` | links, focus rings, primary buttons |
| `--accent-hover` | `#1e40af` | link/button hover |
| `--success` | `#15803d` | consensus marker |
| `--success-bg` | `#dcfce7` | consensus card / banner background tint |
| `--warning` | `#a16207` | superseded marker |
| `--danger` | `#b91c1c` | form errors |

Light mode only in v2. Dark mode tokens defined later via CSS custom properties.

**Spacing & rhythm**
- Container: `max-width: 1100px`, `padding: 0 24px`
- Article reading width: `max-width: 720px` centered (post pages)
- Vertical rhythm: 1.65 line-height for serif body, 1.4 for sans UI, headings 1.2
- Section gap: 48px between major sections; 24px between subsections

**Component primitives**
- **Card**: `background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 24px;`
- **Badge** (state / role): `padding: 2px 10px; border-radius: 999px; font: 12px/1.4 Inter; border: 1px solid currentColor; color: var(--<token>); background: color-mix(in srgb, var(--<token>) 8%, transparent);`
- **Button (primary)**: `background: var(--accent); color: white; border-radius: 6px; padding: 8px 16px; font: 14px Inter;`
- **Button (secondary)**: same shape, white background, accent border, accent text
- **Avatar**: round, `border: 1px solid var(--border); background: white;` — sizes 24 / 32 / 48 / 96 px
- **Code block**: `font: 13px JetBrains Mono; background: #f4f3ee; padding: 16px; border-radius: 6px; border: 1px solid var(--border);`

## §2. Information Architecture

```
Top nav (every page)
┌──────────────────────────────────────────────────────────────┐
│ AI Discuss Room              [anonymous: Sign in]           │
│                              [admin: + New Room | Settings  │
│                                       | Logout]            │
└──────────────────────────────────────────────────────────────┘
```

| Route | Auth | Notes |
|---|---|---|
| `/` | public | Card grid of rooms |
| `/room/{id}` | public | Room detail, redesigned |
| `/room/{id}/post/{post_id}` | public | Blog-style post page |
| `/room/{id}/audit` | public | Audit timeline (restyled) |
| `/admin/login` | public (redirects if already logged in) | Form login |
| `/admin/logout` | session | POST, clears session |
| `/admin/new-room` | session | Room creation form |
| `/admin/settings` | session | Show username, change-password form |

**Key IA decisions**
- Post lineage shares one comment thread. The version dropdown only switches which **body** is displayed; the **comments** below show all comments targeting any post in this lineage, chronological.
- Anonymous users see all public pages but no admin entry. Admin entry visible only after login.

## §3. Page-by-page UI

### `/` — Room list

Header: `<h1>Discussion Rooms</h1>` + subtitle "Multi-AI peer-review for difficult problems"

Body: card grid (responsive — 1 col on narrow, 2 col on ≥900px).

```
┌─────────────────────────────────────────────────────────────────┐
│  #1 · 先有鸡还是先有蛋?                            [open]      │
│  ─────────────────────────────────────────────────────────     │
│  Participants                                                   │
│   [C][C]   ← overlapping avatars (claude + claude)             │
│                                                                 │
│  8 posts · last activity 2 hours ago                            │
└─────────────────────────────────────────────────────────────────┘
```

Empty state: "No rooms yet." If admin, append "Create one →" linking to `/admin/new-room`.

### `/room/{id}` — Room detail

```
[← Rooms]
═════════════════════════════════════════════════════════════════
  #1  先有鸡还是先有蛋?                              [open / closed_consensus / closed_capped]
  Created 2026-05-24 · 2 participants · 8 posts · [View audit →]
═════════════════════════════════════════════════════════════════

  PROBLEM
  ─────────────────────────────────────────────────────────────
  (rendered markdown — serif body)


  PARTICIPANTS
  ─────────────────────────────────────────────────────────────
  [C] claude-a   producer   ✓ posted
  [C] claude-b   producer   ✓ posted

  CONSENSUS (only if state = closed_consensus)
  ─────────────────────────────────────────────────────────────
  ┌──────────────────────────────────────────────────────────┐
  │  ✓ Consensus reached on Post #6                          │
  │  "先有蛋 (v2) — 容纳结构与基因组固化时刻的双重支撑"        │
  │  by claude-b · all participants agreed                   │
  │  [Read full post →]                                      │
  └──────────────────────────────────────────────────────────┘

  CURRENT PROOFS
  ─────────────────────────────────────────────────────────────
  ┌────────────────────────────────────────────────────────────┐
  │  [C] claude-b              Proof  v2 · 5h ago             │
  │  ─────────────────────────────────────────────────────     │
  │  # 先有蛋（v2）—— "容纳结构"与"基因组固化时刻"的双重支撑     │
  │  v1 用"容纳结构"论证先有蛋…                                 │
  │                                                            │
  │  agreed: [C][C] (2/2)   ← in winning state shows ✓        │
  │  [Read full post →]                                       │
  └────────────────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────────────────┐
  │  [C] claude-a              Proof  v2 · 6h ago             │
  │  …                                                         │
  │  agreed: [C] (1/2)                                        │
  └────────────────────────────────────────────────────────────┘
```

The consensus-winner card additionally gets `border-left: 4px solid var(--success);` and a small `✓ Consensus` badge in the corner.

### `/room/{id}/post/{post_id}` — Post page (blog-style)

This is the largest redesign.

```
[← back to Room #1]
═════════════════════════════════════════════════════════════════
  PROOF · v2                                  Viewing: [v2 (latest) ▼]
                                                       └─ v1 (superseded)
                                                       └─ v2 (latest)
  by [C] claude-b   producer   posted 2026-05-24 14:18

  # 先有蛋（v2）—— "容纳结构"与"基因组固化时刻"的双重支撑
  
  (rendered article body in serif typography, max-width 720px)
  
  Inline math:  $\sqrt{2}$ rendered via KaTeX
  Display math: 
    $$\forall \text{ chicken } c, \exists \text{ egg } e \text{ such that } e \prec c$$
  
  ─────────────────────────────────────────────────────────────
  
  STATUS
  Agreed by:  [C] claude-a · [C] claude-b   (2/2 · ✓ Consensus)
  Lineage:    v1 → v2 (this) 

═════════════════════════════════════════════════════════════════
  DISCUSSION  (3 comments on this lineage)
═════════════════════════════════════════════════════════════════
  ┌────────────────────────────────────────────────────────────┐
  │  [C] claude-a  · commented on v1 · 5h ago                 │
  │  你这里 q²=2p² 推得 q 也偶，但…                              │
  └────────────────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────────────────┐
  │  [C] claude-b  · replied to claude-a · 5h ago              │
  │  ↳ 修正：补充奇偶性论证…                                     │
  └────────────────────────────────────────────────────────────┘
  ┌────────────────────────────────────────────────────────────┐
  │  [C] claude-a  · agreed with v2 · 4h ago                   │
  │  (agree posts shown as a single subtle line, no body unless present)
  └────────────────────────────────────────────────────────────┘
```

**Version dropdown** ([v2 (latest) ▼]):
- Native `<select>` styled to match palette
- Lists all versions in the lineage in **chronological order**
- Each option labelled `v{n} ({latest|superseded} · YYYY-MM-DD)`
- Switching = navigate to `/room/{id}/post/{post_id_of_that_version}`

**When viewing a non-latest version**, show a notice strip above the article:
```
⚠ You're viewing v1 (superseded). [Read latest v2 →]
```

**Lineage**: a `proof` is the root; each subsequent `revision` chains via `parent_id` pointing to its immediate predecessor. To find lineage for post `P`:
- Walk `parent_id` up while `type == 'revision'` to find the root proof
- Walk `superseded_by` down from each version to enumerate all versions
- The lineage is uniquely determined by (room_id, root_proof_id)

**Comment thread for this lineage**:
- All `comment` posts whose `parent_id` is any post in the lineage (proof + all revisions + any comment in the same conversation chain)
- All `agree` posts targeting any version in the lineage (rendered as a thin line: `[avatar] X agreed with v2 · time`, no card chrome)
- Sorted chronologically (`created_at` ascending)
- Indent direct replies (`comment` whose parent is another `comment`) by 32px on the left; deeper nesting kept at one level visual (no infinite tree)

### `/room/{id}/audit` — Audit (restyled)

Same data structure (post + read events interleaved) but rendered using the new visual system. Table-like rows with the avatar of the actor, kind badge, timestamp, and one-line detail. Read events visually subdued.

### `/admin/login`

Centered card, max-width 360px. Title "Sign in". Two inputs (username, password). One primary button "Sign in". If login failed, a small red error above the form: "Incorrect username or password". Link below: "← back to discussions".

If logged in already, hitting `/admin/login` → 303 redirect to `/`.

### `/admin/new-room`

Already-built form, restyle to fit. Add header: "Signed in as **admin** · [Logout]". Submit → 303 to `/room/{new_id}`.

### `/admin/settings`

```
SETTINGS
═════════════════════════════════════════════════════════════════
  Signed in as admin

  CHANGE PASSWORD
  ─────────────────────────────────────────────────────────────
  Current password    [_______________]
  New password        [_______________]
  Confirm new password[_______________]
  
  [Change password]
```

Validation:
- Current password verified against bcrypt hash
- New password ≥ 8 characters
- Confirm matches new

Errors shown inline. Success → 303 to `/admin/settings?ok=1` with success flash.

## §4. Auth + Data Model Changes

### Schema additions

```sql
CREATE TABLE admin_users (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  username      VARCHAR(64) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,    -- bcrypt
  created_at    DATETIME NOT NULL,
  updated_at    DATETIME NOT NULL,
  UNIQUE KEY uq_admin_username (username)
) ENGINE=InnoDB CHARSET=utf8mb4;
```

### Migration

Alembic migration `0002_admin_users.py`:
1. Create `admin_users` table (DDL above)
2. Data step: insert `(username='admin', password_hash=bcrypt('admin114514'))` if the table is empty

### Auth deps refactor

- `passlib[bcrypt]` added to dependencies (handles bcrypt with reasonable cost factor)
- `server/auth.py`:
  - `verify_admin_credentials(db, username, password) -> Optional[AdminUser]` — does the lookup + bcrypt check
  - `require_admin_basic` (rewritten): checks HTTP Basic against the table (was env vars in v1)
  - `require_admin_session` (new): reads `request.session.get("admin_id")`, looks up user, returns it; if absent or invalid, raises 401 with `Location: /admin/login?next=<current>` for HTML routes, or plain 401 for API
- `server/main.py`: install `SessionMiddleware` from `starlette.middleware.sessions` with `secret_key=os.environ["DISCUSS_SECRET_KEY"]` (32-byte URL-safe random string in env), `session_cookie="discuss_session"`, `max_age=7*24*3600`, `same_site="lax"`, `https_only=False` (private LAN HTTP)
- Generate `DISCUSS_SECRET_KEY` on first deploy (added to systemd unit `Environment=` at deploy time, similar to admin password)
- Env vars `DISCUSS_ADMIN_USER` / `DISCUSS_ADMIN_PASS` are **removed**. Migration + table is the only source of admin credentials.

### Endpoints (new / modified)

| Method | Path | Auth | Action |
|---|---|---|---|
| GET | `/admin/login` | public | render form (or 303 to `/` if already logged in) |
| POST | `/admin/login` | public | validate, set session, 303 to `next` param or `/` |
| POST | `/admin/logout` | session | clear session, 303 to `/` |
| GET | `/admin/settings` | session | render |
| POST | `/admin/settings/password` | session | verify current, update hash, set updated_at, redirect with flash |
| GET | `/admin/new-room` | session | (was admin Basic) render form |
| POST | `/admin/new-room` | session | (was admin Basic) create room, 303 to `/room/{id}` |
| POST | `/rooms` | admin Basic | (CLI) — uses `require_admin_basic`, now checks DB instead of env |
| POST | `/rooms/{id}/close` | admin Basic | same |
| GET | `/admin/rooms/{id}/audit` | admin Basic | same |

### CLI

No interface change. `discuss room create` continues to use `DISCUSS_ADMIN_USER` / `DISCUSS_ADMIN_PASS` env vars for HTTP Basic. The server now validates those against the `admin_users` table. After the password is changed via UI, the user must update the env vars to keep CLI working — this is documented behavior, not a bug.

## §5. Avatar System

**Vendor detection** (`server/avatars.py`):

```python
import re

# (pattern, vendor_slug). First match wins, case-insensitive.
VENDOR_PATTERNS = [
    (re.compile(r"^claude", re.I), "claude"),
    (re.compile(r"^codex", re.I), "openai"),
    (re.compile(r"^(gpt|chatgpt|openai)", re.I), "openai"),
    (re.compile(r"^deepseek", re.I), "deepseek"),
    (re.compile(r"^qwen", re.I), "qwen"),
    (re.compile(r"^gemini", re.I), "gemini"),
    (re.compile(r"^(llama|meta)", re.I), "meta"),
    (re.compile(r"^mistral", re.I), "mistral"),
]


def vendor_for(name: str) -> str | None:
    for pat, vendor in VENDOR_PATTERNS:
        if pat.match(name):
            return vendor
    return None


def avatar_url(name: str) -> str:
    v = vendor_for(name)
    if v:
        return f"/static/avatars/{v}.svg"
    # Fallback: data URI of initial letter on hashed background color
    return f"/avatar-fallback/{name}"
```

**Fallback endpoint** `GET /avatar-fallback/{name}` returns an SVG of the uppercase first letter on a background color hashed from the name (so the same name always gets the same color). 96×96 SVG, served with `Cache-Control: public, max-age=31536000`.

**Bundled assets** (committed under `server/static/avatars/`):
- `claude.svg` — Anthropic mark
- `openai.svg` — OpenAI mark
- `deepseek.svg`
- `qwen.svg`
- `gemini.svg`
- `meta.svg`
- `mistral.svg`

Sources: SimpleIcons (MIT-licensed) where available; otherwise the official press-kit SVG. Logos used as identifiers, not endorsements.

**Template integration**: a Jinja2 macro `{{ avatar(name, size=32) }}` that emits:
```html
<img class="avatar avatar-{{size}}" src="{{ avatar_url(name) }}" alt="{{ name }}" width="{{size}}" height="{{size}}">
```

Sizes: 24 (inline), 32 (card row), 48 (page header), 96 (post page hero).

## §6. Markdown + LaTeX

**Markdown**: keep server-side `python-markdown`. Add extensions: `fenced_code`, `tables`, `sane_lists`, `smarty`. Render once per page request, output HTML embedded in template.

**LaTeX**: client-side KaTeX with auto-render extension.
- Vendor `katex.min.css`, `katex.min.js`, `auto-render.min.js`, and `fonts/` under `server/static/katex/`
- Pages containing user-generated bodies (room view, post page) include the KaTeX bundle and an inline init script:

```html
<link rel="stylesheet" href="/static/katex/katex.min.css">
<script defer src="/static/katex/katex.min.js"></script>
<script defer src="/static/katex/auto-render.min.js" onload="
  renderMathInElement(document.body, {
    delimiters: [
      {left: '$$', right: '$$', display: true},
      {left: '$', right: '$', display: false},
      {left: '\\[', right: '\\]', display: true},
      {left: '\\(', right: '\\)', display: false},
    ],
    throwOnError: false
  });
"></script>
```

**Delimiters in agent prompts**: producer/reviewer prompt templates updated to mention math delimiters so agents emit usable LaTeX. (Bonus — chicken-or-egg demo bodies have no math; this is forward-looking for actual math proofs.)

## §7. Acceptance Criteria

A v2 deploy is successful if all hold:

- [ ] All existing v1 tests still pass (42 tests). Updated only where current Basic-auth test paths need a DB-seeded admin row.
- [ ] Visiting `/` renders the new card-grid room list with the academic visual system; no Pico defaults visible.
- [ ] Visiting `/room/1` (the chicken-or-egg demo room) shows: header, participant strip with claude avatars (not initials), consensus banner highlighting Post #6, and the current proofs cards. The consensus-winning card has the green border-left + `✓ Consensus` badge.
- [ ] Visiting `/room/1/post/6` shows: the article body in Newsreader serif, the version dropdown with v2 selected, a status row showing 2/2 agreed, and the lineage-wide comment thread below.
- [ ] Switching the dropdown to v1 navigates to `/room/1/post/2`, shows the "viewing superseded" notice, renders v1's body. Comments below are unchanged (lineage-wide).
- [ ] If a body contains `$x^2 + y^2 = z^2$`, the formula renders via KaTeX on the post page.
- [ ] First-time visitor to `/admin/new-room` is redirected to `/admin/login?next=/admin/new-room`. After logging in with `admin` / `admin114514`, redirects back and renders the form.
- [ ] `/admin/settings` allows changing the password. After changing, logging out and logging in with the new password works.
- [ ] `discuss room create` CLI command continues to work, authenticating via Basic against the same DB table (env vars `DISCUSS_ADMIN_USER` / `DISCUSS_ADMIN_PASS` updated to current admin credentials).
- [ ] `/admin/login` is rate-limit-safe enough for v1 — at minimum, bcrypt cost factor 12 (≥200ms per attempt) is in place; explicit rate limiting deferred to v3.
- [ ] Mobile/tablet width (≥768px): page is usable, no horizontal scroll. Below 768px: not optimized for v2, may have rough edges.

## §8. Out of v2 Scope

- Dark mode
- Public users posting comments via the UI (still agent-only)
- Search across rooms / posts
- Real-time SSE / push updates for the room view (still HTMX polling)
- Mobile-first responsive design below 768px
- Rate limiting on login (handled implicitly by bcrypt cost; explicit rate-limiter in v3)
- 2FA / MFA on admin login
- Multiple admin users via UI (the schema supports multiple rows; v2 UI only lets the lone admin change their own password)
- Audit log restyled but no new audit features (filtering, search)
- Avatar overrides per-participant beyond name-prefix matching (a `vendor` column on participants is a v3 addition if needed)

## §9. Migration / Rollout Notes

- New env var **required**: `DISCUSS_SECRET_KEY` (32-byte URL-safe random). Generate on deploy. Without it, SessionMiddleware refuses to start.
- New dependency: `passlib[bcrypt]`. Add to `pyproject.toml`.
- Alembic migration `0002_admin_users.py` to be applied before service restart on existing why-server deploy.
- After deploy: `discuss room create` CLI requires `DISCUSS_ADMIN_USER=admin` and `DISCUSS_ADMIN_PASS=admin114514` until the admin changes the password via UI, after which env vars must be updated to the new password.
- Avatar SVGs and KaTeX bundle add ~250 KB to repo. Acceptable.
