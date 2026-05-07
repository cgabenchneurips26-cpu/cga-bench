#!/usr/bin/env bash
# Package the anonymized submission copy as a tarball + SHA-256 manifest
# for upload to anon4openreview / Zenodo / anonymous GitHub.
#
# Inputs
# ------
#   --source PATH    Path to the anonymized tree (default:
#                    ../anonymous_repo relative to cga_bench/)
#   --output DIR     Output directory (default: release/)
#   --tag STRING     Tag appended to filenames (default: v7.3)
#
# Outputs
# -------
#   <output>/cga_bench_anon_<tag>.tar.gz
#   <output>/cga_bench_anon_<tag>.tar.gz.sha256
#   <output>/cga_bench_anon_<tag>.MANIFEST.txt   (file count + sizes)
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

SOURCE=""
OUTPUT="${REPO_ROOT}/release"
TAG="v7.3"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source) SOURCE="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --tag)    TAG="$2";    shift 2 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "ERR: unknown arg: $1" >&2; exit 2 ;;
    esac
done

# Default source: sibling of repo root (where prepare_anonymous_repo
# places its output when run from inside cga_bench/).
if [[ -z "${SOURCE}" ]]; then
    SOURCE="${REPO_ROOT}/anonymous_repo"
fi

if [[ ! -d "${SOURCE}" ]]; then
    echo "ERR: source not a directory: ${SOURCE}" >&2
    exit 2
fi

mkdir -p "${OUTPUT}"
TARBALL="${OUTPUT}/cga_bench_anon_${TAG}.tar.gz"
SHAFILE="${TARBALL}.sha256"
MANIFEST="${OUTPUT}/cga_bench_anon_${TAG}.MANIFEST.txt"

echo "Source:   ${SOURCE}"
echo "Tarball:  ${TARBALL}"

# Use a stable archive name inside the tar so reviewers extract to
# 'cga_bench/' regardless of host path.
SOURCE_PARENT="$(dirname -- "${SOURCE}")"
SOURCE_NAME="$(basename -- "${SOURCE}")"

(
    cd "${SOURCE_PARENT}"
    tar --transform "s|^${SOURCE_NAME}|cga_bench|" \
        --owner=0 --group=0 --numeric-owner \
        -czf "${TARBALL}" \
        "${SOURCE_NAME}"
)

sha256sum "${TARBALL}" | awk '{print $1}' > "${SHAFILE}"
HASH="$(cat "${SHAFILE}")"

# Manifest: file count + total size + extracted-name preview.
{
    echo "# CGA-Bench Anonymous Submission Tarball Manifest"
    echo "# Tag:       ${TAG}"
    echo "# Built:     $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "# Tarball:   $(basename -- "${TARBALL}")"
    echo "# Size:      $(du -sh "${TARBALL}" | awk '{print $1}')"
    echo "# Files:     $(find "${SOURCE}" -type f | wc -l)"
    echo "# SHA-256:   ${HASH}"
    echo "# Extracts to: cga_bench/"
} > "${MANIFEST}"

echo "Manifest: ${MANIFEST}"
echo "SHA-256:  ${HASH}"
echo
echo "Done. Upload destinations:"
echo "  - https://anonymous.4open.science/  (NeurIPS preferred for review)"
echo "  - https://zenodo.org/               (anonymous deposit)"
echo "  - https://github.com/<anon>/cga_bench  (force-push without history)"
