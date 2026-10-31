#!/usr/bin/env bash
# install-syft.sh — install a pinned, verified Syft release into ~/.local/bin.
#
# Used by scripts/sbom-scan.sh (nightly SBOMs for Dependency-Track). No sudo.
#
# Supply chain (the March 2026 Trivy compromise shipped malicious release
# binaries for days): the tarball's sha256 is pinned HERE, in reviewed git,
# so a later tampered upload to the same GitHub release can't be installed.
# The pinned hash came from the release's checksums.txt, whose Sigstore
# signature was verified with cosign before pinning (signer identity below).
# If cosign is on PATH, this script re-verifies that signature too.
# Pick releases at least ~2 weeks old, so a bad release has time to be noticed.
#
# Upgrade: bump SYFT_VERSION, then on a machine with cosign:
#   gh release download vX.Y.Z -R anchore/syft -p 'syft_X.Y.Z_checksums.txt*'
#   cosign verify-blob --bundle syft_X.Y.Z_checksums.txt.sigstore.json \
#     --certificate-identity "$SYFT_SIGNER" \
#     --certificate-oidc-issuer https://token.actions.githubusercontent.com \
#     syft_X.Y.Z_checksums.txt
#   grep linux_amd64.tar.gz syft_X.Y.Z_checksums.txt   # -> SYFT_SHA256
#
# Usage: scripts/install-syft.sh            # no-op if already installed
#        scripts/install-syft.sh --force    # reinstall
set -euo pipefail

SYFT_VERSION="1.54.1"
# syft_1.54.1_linux_amd64.tar.gz; checksums.txt signature verified 2026-10-31.
SYFT_SHA256="c069905b391cc4c20a5ba65ad5c10be2a7ba074f8ea6ad203e24d14e303dad47"
SYFT_SIGNER="https://github.com/anchore/syft/.github/workflows/release.yaml@refs/heads/main"
OIDC_ISSUER="https://token.actions.githubusercontent.com"

BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
BASE_URL="https://github.com/anchore/syft/releases/download/v${SYFT_VERSION}"
TARBALL="syft_${SYFT_VERSION}_linux_amd64.tar.gz"
CHECKSUMS="syft_${SYFT_VERSION}_checksums.txt"

if [[ "$(uname -s)/$(uname -m)" != "Linux/x86_64" ]]; then
    echo "install-syft: only linux/amd64 is pinned (this is $(uname -s)/$(uname -m))" >&2
    exit 1
fi

if [[ "${1:-}" != "--force" ]] && [[ -x "${BIN_DIR}/syft" ]] \
    && "${BIN_DIR}/syft" version 2>/dev/null | grep -Eq "^Version:[[:space:]]+${SYFT_VERSION}$"; then
    echo "install-syft: syft ${SYFT_VERSION} already installed at ${BIN_DIR}/syft"
    exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

echo "install-syft: downloading syft ${SYFT_VERSION}"
curl -fsSL --proto '=https' -o "${work}/${TARBALL}" "${BASE_URL}/${TARBALL}"
curl -fsSL --proto '=https' -o "${work}/${CHECKSUMS}" "${BASE_URL}/${CHECKSUMS}"
curl -fsSL --proto '=https' -o "${work}/${CHECKSUMS}.sigstore.json" "${BASE_URL}/${CHECKSUMS}.sigstore.json"

actual=$(sha256sum "${work}/${TARBALL}" | cut -d' ' -f1)
if [[ "$actual" != "$SYFT_SHA256" ]]; then
    echo "install-syft: SHA256 MISMATCH for ${TARBALL}" >&2
    echo "  expected ${SYFT_SHA256}" >&2
    echo "  got      ${actual}" >&2
    exit 1
fi
# The published checksums file must agree with the pin (catches a pin typo
# as well as a swapped checksums file).
if ! grep -qx "${SYFT_SHA256}  ${TARBALL}" "${work}/${CHECKSUMS}"; then
    echo "install-syft: ${CHECKSUMS} does not list the pinned hash" >&2
    exit 1
fi
echo "install-syft: sha256 OK (${actual})"

if command -v cosign >/dev/null 2>&1; then
    cosign verify-blob --bundle "${work}/${CHECKSUMS}.sigstore.json" \
        --certificate-identity "$SYFT_SIGNER" \
        --certificate-oidc-issuer "$OIDC_ISSUER" \
        "${work}/${CHECKSUMS}"
    echo "install-syft: cosign signature OK"
else
    echo "install-syft: cosign not installed; relying on the pinned sha256 (signature was checked when pinning)"
fi

tar -xzf "${work}/${TARBALL}" -C "$work" syft
mkdir -p "$BIN_DIR"
install -m 0755 "${work}/syft" "${BIN_DIR}/syft.new"
mv -f "${BIN_DIR}/syft.new" "${BIN_DIR}/syft"
"${BIN_DIR}/syft" version | grep -E '^(Version|BuildDate|GitCommit):'
echo "install-syft: installed ${BIN_DIR}/syft"
