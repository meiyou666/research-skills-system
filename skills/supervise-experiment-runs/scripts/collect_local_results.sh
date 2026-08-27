#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: collect_local_results.sh --source-root DIR --manifest FILE --execution-record FILE --destination DIR" >&2
  exit 2
}

source_root=
manifest=
execution_record=
destination=

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-root) [[ $# -ge 2 ]] || usage; source_root=$2; shift 2 ;;
    --manifest) [[ $# -ge 2 ]] || usage; manifest=$2; shift 2 ;;
    --execution-record) [[ $# -ge 2 ]] || usage; execution_record=$2; shift 2 ;;
    --destination) [[ $# -ge 2 ]] || usage; destination=$2; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n $source_root && -n $manifest && -n $execution_record && -n $destination ]] || usage
[[ -d $source_root && ! -L $source_root ]] || { echo "source root must be a directory" >&2; exit 2; }
[[ -f $manifest && ! -L $manifest ]] || { echo "manifest must be a regular file" >&2; exit 2; }
[[ -f $execution_record && ! -L $execution_record ]] || { echo "execution record must be a regular file" >&2; exit 2; }
command -v tar >/dev/null 2>&1 || { echo "tar is required" >&2; exit 127; }
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required" >&2; exit 127; }
mv --help 2>&1 | grep -q -- '-T' && mv --help 2>&1 | grep -q -- '-n' || { echo "GNU mv with -T and -n support is required" >&2; exit 127; }

source_root=$(cd -- "$source_root" && pwd -P)
[[ $source_root != / ]] || { echo "source root must not be the filesystem root" >&2; exit 2; }
parent_input=$(dirname -- "$destination")
base=$(basename -- "$destination")
[[ -n $base && $base != . && $base != .. ]] || { echo "invalid destination" >&2; exit 2; }
mkdir -p -- "$parent_input"
parent=$(cd -- "$parent_input" && pwd -P)
destination="$parent/$base"
[[ ! -e $destination ]] || { echo "destination already exists: $destination" >&2; exit 3; }

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
verifier="$script_dir/verify_result_manifest.py"
[[ -f $verifier ]] || { echo "result verifier is missing" >&2; exit 127; }

staging=$(mktemp -d "$parent/.${base}.partial.XXXXXX")
cleanup() {
  if [[ -n ${staging:-} && -d $staging && $staging == "$parent/.${base}.partial."* ]]; then
    rm -rf -- "$staging"
  fi
}
trap cleanup EXIT
mkdir -p -- "$staging/raw"
cp -- "$manifest" "$staging/result-manifest.json"
cp -- "$execution_record" "$staging/execution-record.json"

tar -C "$source_root" -cf - . | tar -C "$staging/raw" --no-same-owner --no-same-permissions -xf -
python3 "$verifier" \
  --root "$staging/raw" \
  --manifest "$staging/result-manifest.json" \
  --execution-record "$staging/execution-record.json" \
  --report "$staging/verification.json"

mv -Tn -- "$staging" "$destination"
[[ ! -e $staging ]] || { echo "destination appeared during finalization: $destination" >&2; exit 3; }
trap - EXIT
printf 'VERIFIED destination=%s\n' "$destination"
