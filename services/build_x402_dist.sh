#!/usr/bin/env bash
# Build + push ARM64 (GHCR) de tous les services x402, sur le modele de
# docker_install/build_arm_img.sh — aucune operation lourde sur Oracle,
# qui se contente ensuite d'un `docker compose pull && up -d`.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GHCR_USER="${GHCR_USER:-fredericsuretat}"
GHCR_TOKEN="${GHCR_TOKEN:-}"
PLATFORM="${PLATFORM:-linux/arm64}"
TAG="${TAG:-latest}"
PUSH="${PUSH:-1}"
BUILDER_NAME="${BUILDER_NAME:-multi}"
USE_REGISTRY_CACHE="${USE_REGISTRY_CACHE:-1}"
PROGRESS="${PROGRESS:-plain}"
ONLY="${ONLY:-}"
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-1}"
NICE_LEVEL="${NICE_LEVEL:-10}"

log() { printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn() { printf '\n[WARN] %s\n' "$*"; }
die() { printf '\n[ERROR] %s\n' "$*" >&2; exit 1; }

ensure_buildx() {
  command -v docker >/dev/null 2>&1 || die "docker manquant"
  docker buildx version >/dev/null 2>&1 || die "docker buildx non disponible"
  if ! docker buildx inspect "$BUILDER_NAME" >/dev/null 2>&1; then
    log "Creation du builder buildx: $BUILDER_NAME"
    docker buildx create --name "$BUILDER_NAME" --use >/dev/null
  else
    docker buildx use "$BUILDER_NAME" >/dev/null
  fi
  docker buildx inspect --bootstrap >/dev/null
}

ensure_ghcr_login_if_token() {
  [[ "$PUSH" == "1" ]] || return 0
  if [[ -n "$GHCR_TOKEN" ]]; then
    log "Login GHCR via GHCR_TOKEN (utilisateur: $GHCR_USER)"
    printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin >/dev/null
  else
    warn "GHCR_TOKEN non fourni, on utilise le login docker deja en place."
  fi
}

build_one() {
  local dir="$1"
  local name="${dir#x402-}"
  local dockerfile="$HERE/$dir/Dockerfile"
  local context="$HERE/$dir"

  if [[ -f "$HERE/$dir/app/Dockerfile" ]]; then
    dockerfile="$HERE/$dir/app/Dockerfile"
    context="$HERE/$dir/app"
  fi

  [[ -f "$dockerfile" ]] || { warn "$dir: Dockerfile introuvable, skip"; return 0; }

  local image_repo="ghcr.io/$GHCR_USER/x402-$name"
  local cmd=(nice -n "$NICE_LEVEL" docker buildx build --platform "$PLATFORM" -f "$dockerfile" "$context" -t "$image_repo:$TAG" --progress "$PROGRESS" --provenance=false --sbom=false)

  if [[ "$USE_REGISTRY_CACHE" == "1" && "$PUSH" == "1" ]]; then
    cmd+=(--cache-from "type=registry,ref=$image_repo:buildcache-arm64")
    cmd+=(--cache-to "type=registry,ref=$image_repo:buildcache-arm64,mode=max")
  fi

  if [[ "$PUSH" == "1" ]]; then
    cmd+=(--push)
  else
    cmd+=(--load)
  fi

  log "Build $dir -> $image_repo:$TAG"
  "${cmd[@]}"
}

main() {
  ensure_buildx
  ensure_ghcr_login_if_token

  local dirs=()
  if [[ -n "$ONLY" ]]; then
    IFS=',' read -r -a dirs <<< "$ONLY"
  else
    for d in "$HERE"/x402-*/; do
      d="$(basename "$d")"
      [[ "$d" == "x402-mcp" ]] && continue
      dirs+=("$d")
    done
  fi

  log "Total services a builder: ${#dirs[@]}"
  local failures=0 i=0
  for d in "${dirs[@]}"; do
    i=$((i+1))
    log "[$i/${#dirs[@]}] $d"
    if ! build_one "$d"; then
      failures=$((failures+1))
      warn "$d: echec"
      [[ "$CONTINUE_ON_ERROR" == "1" ]] || die "Arret apres echec sur $d"
    fi
  done

  log "Termine. Echecs: $failures / ${#dirs[@]}"
}

main "$@"
