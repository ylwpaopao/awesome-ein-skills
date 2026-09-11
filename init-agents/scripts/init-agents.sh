#!/usr/bin/env bash
# macOS (Bash 3.2+) and Linux; no package dependencies.
set -euo pipefail

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'EOF'
Usage: bash init-agents.sh [PROJECT_DIRECTORY]

Create missing files and empty skill directories (default: current directory):
  AGENTS.md                Empty, zero-byte file
  README.md                Empty, zero-byte file
  CLAUDE.md                @AGENTS.md
  .codex/config.toml        Empty TOML; inherits existing defaults
  .agents/skills/           Codex project skills
  .claude/settings.json     {}
  .claude/skills/           Claude Code project skills
  .mcp.json                {"mcpServers": {}} (Claude project MCP)

Initialize Git if the target is not already inside a repository. Preserve
existing repositories and worktrees; do not stage, commit or configure remotes.

Existing files are preserved. A missing standalone import is appended to
CLAUDE.md. Symlinks, case conflicts, wrong path types and unclosed Markdown
fences that would hide the import are rejected before writing scaffold files.

No .codex/mcp/ is needed: Codex MCP lives in .codex/config.toml.
Only project files are managed; user-level configuration is not touched.
Windows is not supported yet; a native version should use PowerShell.
EOF
}

if [[ ${1-} == --help || ${1-} == -h ]]; then usage; exit 0; fi
[[ $# -le 1 ]] || fail 'Expected at most one project directory. Use --help.'
[[ -n ${1-.} ]] || fail 'Project directory must not be empty.'

case "$(uname -s)" in
  Darwin|Linux) ;;
  MINGW*|MSYS*|CYGWIN*|Windows*)
    fail 'Windows is not supported yet. A PowerShell version is required.' ;;
  *) fail 'Supported operating systems: macOS and Linux.' ;;
esac

command -v git >/dev/null 2>&1 || fail 'Git is required. Install Git, then retry.'
# These variables can redirect Git operations away from the selected project.
for variable in GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE; do
  [[ -z ${!variable-} ]] || fail "Unset $variable before running this script."
done

root=${1:-.}
[[ $root == /* ]] || root="$(pwd -P)/$root"
while [[ $root != / && $root == */ ]]; do root=${root%/}; done

# Match actual entries, including on case-insensitive macOS volumes.
check_case() {
  local path=$1 parent name entry actual folded
  parent=$(dirname "$path")
  name=$(basename "$path")
  [[ -d $parent ]] || return 0
  folded=$(printf '%s' "$name" | LC_ALL=C tr '[:upper:]' '[:lower:]')
  for entry in "$parent"/* "$parent"/.[!.]* "$parent"/..?*; do
    [[ -e $entry || -L $entry ]] || continue
    actual=${entry##*/}
    if [[ $actual != "$name" && $(printf '%s' "$actual" | LC_ALL=C tr '[:upper:]' '[:lower:]') == "$folded" ]]; then
      fail "Case conflict: $entry (expected $name)"
    fi
  done
}

check_path() {
  local path=$1 kind=$2
  check_case "$path"
  [[ ! -L $path ]] || fail "Refusing symbolic link: $path"
  if [[ -e $path ]]; then
    if [[ $kind == dir ]]; then
      [[ -d $path ]] || fail "Expected directory: $path"
    else
      [[ -f $path ]] || fail "Expected regular file: $path"
    fi
  fi
}

check_path "$root" dir
# Normalize an existing root before checking children.
if [[ -d $root ]]; then root=$(cd "$root" && pwd -P); fi
dirs=(.codex .agents .agents/skills .claude .claude/skills)
files=(AGENTS.md README.md CLAUDE.md .codex/config.toml .claude/settings.json .mcp.json)
for path in "${dirs[@]}"; do check_path "$root/$path" dir; done
for path in "${files[@]}"; do check_path "$root/$path" file; done

# Probe the nearest existing ancestor, so new subdirectories do not accidentally
# get nested repositories. A .git file is valid for worktrees and submodules.
check_case "$root/.git"
[[ ! -L $root/.git ]] || fail 'Refusing symbolic link: .git'
probe=$root
while [[ ! -d $probe ]]; do probe=$(dirname "$probe"); done
if [[ $(git -C "$probe" rev-parse --is-bare-repository 2>/dev/null || true) == true ]]; then
  fail 'Cannot scaffold inside a bare Git repository.'
fi
git_root=''
if git_root=$(git -C "$probe" rev-parse --show-toplevel 2>/dev/null); then
  :
elif [[ -e $root/.git ]]; then
  fail 'Existing .git is invalid or inaccessible; leaving it unchanged.'
fi

# Return 0 for an active standalone import, 1 if absent, 2 for an open fence.
# Ignore fenced and indented examples; accept either relative spelling and CRLF.
import_state() {
  awk '
    {
      line = $0
      sub(/\r$/, "", line)
      sub(/^ ? ? ?/, "", line)
      if (line ~ /^```/ || line ~ /^~~~/) {
        marker = substr(line, 1, 1)
        n = 0
        while (substr(line, n + 1, 1) == marker) n++
        if (!fence) { fence = marker; width = n }
        else if (marker == fence && n >= width && substr(line, n + 1) ~ /^[ \t]*$/) fence = ""
        next
      }
      if (!fence && line ~ /^@(\.\/)?AGENTS\.md[ \t]*$/) found = 1
    }
    END { if (found) exit 0; if (fence) exit 2; exit 1 }
  ' "$1"
}

append_import=false
if [[ -f $root/CLAUDE.md ]]; then
  [[ -r $root/CLAUDE.md ]] || fail "Cannot read: $root/CLAUDE.md"
  state=0
  import_state "$root/CLAUDE.md" || state=$?
  case $state in
    0) ;;
    1)
      [[ -w $root/CLAUDE.md ]] || fail "Cannot append import: $root/CLAUDE.md"
      append_import=true ;;
    2) fail 'CLAUDE.md has an unclosed Markdown fence. Close it before retrying.' ;;
    *) fail 'Could not inspect CLAUDE.md.' ;;
  esac
fi

mkdir -p "$root"
if [[ -n $git_root ]]; then
  printf 'KEEP Git repository: %s\n' "$git_root"
else
  git -C "$root" init --quiet
  printf 'CREATE Git repository: %s\n' "$root"
fi
for path in "${dirs[@]}"; do
  if [[ -d $root/$path ]]; then
    printf 'KEEP directory: %s\n' "$path"
  else
    mkdir "$root/$path"
    printf 'CREATE directory: %s\n' "$path"
  fi
done

# noclobber prevents truncating a file created since preflight.
create_file() {
  local path=$1 content=$2
  if [[ -f $root/$path ]]; then
    printf 'KEEP file: %s\n' "$path"
  else
    (set -o noclobber; printf '%s' "$content" > "$root/$path")
    printf 'CREATE file: %s\n' "$path"
  fi
}

create_file AGENTS.md ''
create_file README.md ''
create_file CLAUDE.md $'@AGENTS.md\n'
create_file .codex/config.toml ''
create_file .claude/settings.json $'{}\n'
create_file .mcp.json $'{"mcpServers": {}}\n'
if [[ $append_import == true ]]; then
  printf '\n@AGENTS.md\n' >> "$root/CLAUDE.md"
  printf 'APPEND import: CLAUDE.md\n'
fi

[[ -f $root/AGENTS.md ]] || fail 'AGENTS.md is missing.'
import_state "$root/CLAUDE.md" || fail 'CLAUDE.md import verification failed.'
[[ $(git -C "$root" rev-parse --is-inside-work-tree) == true ]] || fail 'Git verification failed.'
printf 'OK: %s (files checked; client loading not tested)\n' "$root"
