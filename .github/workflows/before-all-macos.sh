#!/bin/bash

# Inspired by build process of spead2

set -e -u

brew install ccache automake boost cln ginac glpk hwloc z3 xerces-c

PROJECT_DIR="${CIBW_PROJECT_DIR:-$PWD}"

# Determine which Storm version stormpy was built against.
#
# IMPORTANT: do NOT `pip install stormpy` here (macOS runners may disallow
# system-wide installs). Instead, extract the origin info directly from a
# stormpy wheel.
WHEEL_DIR="${PROJECT_DIR}/stormpy_wheels"
if [[ -d "${WHEEL_DIR}" ]] && compgen -G "${WHEEL_DIR}/stormpy-*.whl" > /dev/null; then
	echo "Using local stormpy wheels in: ${WHEEL_DIR}"
else
	mkdir -p /tmp/stormpy_wheels
	if [[ -n "${STORMPY_VERSION:-}" ]]; then
		echo "Downloading stormpy==${STORMPY_VERSION} wheel from PyPI"
		python3 -m pip download --only-binary=:all: --no-deps -d /tmp/stormpy_wheels "stormpy==${STORMPY_VERSION}"
	else
		echo "Downloading stormpy wheel from PyPI (latest)"
		python3 -m pip download --only-binary=:all: --no-deps -d /tmp/stormpy_wheels stormpy
	fi
	WHEEL_DIR=/tmp/stormpy_wheels
fi

# Prefer a wheel matching the interpreter used for querying.
PYTAG=$(python3 - <<'PY'
import sys
print(f"cp{sys.version_info.major}{sys.version_info.minor}")
PY
)

WHEEL=$(ls "${WHEEL_DIR}"/stormpy-*-${PYTAG}-*.whl 2>/dev/null | head -n 1 || true)
if [[ -z "${WHEEL:-}" ]]; then
	WHEEL=$(ls "${WHEEL_DIR}"/stormpy-*.whl 2>/dev/null | head -n 1 || true)
fi
if [[ -z "${WHEEL:-}" ]]; then
	echo "No stormpy wheel found in ${WHEEL_DIR}" >&2
	exit 1
fi

echo "stormpy wheel used for origin query: ${WHEEL}"

# Install the wheel into a temporary venv and query stormpy.info.
# This avoids system-wide installs and gives us access to Version.git_hash.
STORMPY_QUERY_VENV="$(mktemp -d /tmp/paynt_stormpy_query_venv.XXXXXX)"
python3 -m venv "${STORMPY_QUERY_VENV}"

STORM_ORIGIN=$(
	"${STORMPY_QUERY_VENV}/bin/python" -m pip install --no-deps "$WHEEL" >/dev/null
	"${STORMPY_QUERY_VENV}/bin/python" -c "import stormpy.info; repo, tag, commit = stormpy.info.storm_origin_info(); print(f'{repo or \"\"};{tag or \"\"};{commit or \"\"}')"
)
rm -rf "${STORMPY_QUERY_VENV}"
STORM_REPO="${STORM_ORIGIN%%;*}"
REST="${STORM_ORIGIN#*;}"
STORM_TAG="${REST%%;*}"
STORM_COMMIT="${REST#*;}"

# Prefer commit hash for building Storm; use tag when commit isn't available.
if [[ -n "${STORM_COMMIT}" ]]; then
	STORM_VERSION_TO_BUILD="${STORM_COMMIT}"
elif [[ -n "${STORM_TAG}" ]]; then
	STORM_VERSION_TO_BUILD="${STORM_TAG}"
else
	echo "Failed to determine Storm origin from stormpy (got: '${STORM_ORIGIN}')" >&2
	STORM_VERSION_TO_BUILD="${STORM_VERSION:-master}"
fi

# Prefer tag for metadata (human-readable), fall back to commit.
if [[ -n "${STORM_TAG}" ]]; then
	STORM_VERSION_RESOLVED="${STORM_TAG}"
elif [[ -n "${STORM_COMMIT}" ]]; then
	STORM_VERSION_RESOLVED="${STORM_COMMIT}"
else
	STORM_VERSION_RESOLVED="${STORM_VERSION_TO_BUILD}"
fi

if [[ -z "${STORM_REPO}" ]]; then
	STORM_REPO="https://github.com/moves-rwth/storm.git"
fi

echo "Resolved Storm origin: repo='${STORM_REPO}', tag='${STORM_TAG}', commit='${STORM_COMMIT}'"
echo "Storm version to build: ${STORM_VERSION_TO_BUILD}"

ORIGIN_FILE="${PROJECT_DIR}/.paynt_storm_origin.cmake"
cat > "${ORIGIN_FILE}" <<EOF
set(PAYNT_INFO_PRETEND_FETCH ON)
set(STORM_GIT_REPO "${STORM_REPO}")
set(STORM_GIT_TAG "${STORM_VERSION_RESOLVED}")
set(ALLOW_STORM_SYSTEM ON)
set(ALLOW_STORM_FETCH OFF)
set(STORM_DIR_HINT "/usr/local/lib/cmake/storm")
EOF
echo "Wrote Storm origin file: ${ORIGIN_FILE}"

# Install Storm
STORM_VERSION="${STORM_VERSION_TO_BUILD}"

rm -rf storm
if [[ "${STORM_VERSION}" =~ ^[0-9a-fA-F]{40}$ ]]; then
	# Commit hash: fetch just that commit.
	echo "Fetching Storm commit ${STORM_VERSION}"
	git init storm
	cd storm
	git remote add origin "${STORM_REPO}"
	if git fetch --depth 1 origin "${STORM_VERSION}" 2>/dev/null; then
		git -c advice.detachedHead=false checkout FETCH_HEAD
	else
		echo "Shallow fetch by commit failed; falling back to full clone"
		cd ..
		rm -rf storm
		git clone "${STORM_REPO}" storm
		cd storm
		git checkout "${STORM_VERSION}"
	fi
	cd ..
elif git clone --depth 1 --branch "${STORM_VERSION}" "${STORM_REPO}" storm 2>/dev/null; then
	echo "Cloned Storm via --branch ${STORM_VERSION}"
else
	echo "Falling back to clone+checkout for Storm version '${STORM_VERSION}'"
	git clone "${STORM_REPO}" storm
	cd storm
	git checkout "${STORM_VERSION}"
	cd ..
fi

cd storm
mkdir build
cd build
cmake .. -DSTORM_BUILD_TESTS=OFF -DSTORM_BUILD_EXECUTABLES=OFF -DSTORM_PORTABLE=ON
make -j ${NR_JOBS}
sudo chown runner:admin /usr/local/ # Permission differ in macOS 14, see https://github.com/actions/runner-images/issues/9272
make install
cd ..
rm -rf build
