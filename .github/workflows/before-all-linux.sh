#!/bin/bash

# Inspired by build process of spead2

set -e -u

dnf install -y boost-devel cln-devel gmp-devel glpk-devel hwloc-devel z3-devel xerces-c-devel eigen3-devel python3-devel # missing ginac

PROJECT_DIR="${CIBW_PROJECT_DIR:-$PWD}"

# Use a stable interpreter to query stormpy once in before-all.
# manylinux images ship multiple Pythons under /opt/python.
if [[ -x "/opt/python/cp310-cp310/bin/python" ]]; then
	STORMPY_PYTHON="/opt/python/cp310-cp310/bin/python"
elif [[ -x "/opt/python/cp311-cp311/bin/python" ]]; then
	STORMPY_PYTHON="/opt/python/cp311-cp311/bin/python"
else
	STORMPY_PYTHON="python3"
fi

# Determine which Storm version stormpy was built against.
#
# IMPORTANT: do NOT `pip install stormpy` here (macOS runners and some managed
# Python installs disallow system-wide installs). Instead, extract the origin
# info directly from a stormpy wheel.
WHEEL_DIR="${PROJECT_DIR}/stormpy_wheels"
if [[ -d "${WHEEL_DIR}" ]] && compgen -G "${WHEEL_DIR}/stormpy-*.whl" > /dev/null; then
	echo "Using local stormpy wheels in: ${WHEEL_DIR}"
else
	mkdir -p /tmp/stormpy_wheels
	if [[ -n "${STORMPY_VERSION:-}" ]]; then
		echo "Downloading stormpy==${STORMPY_VERSION} wheel from PyPI"
		"${STORMPY_PYTHON}" -m pip download --only-binary=:all: --no-deps -d /tmp/stormpy_wheels "stormpy==${STORMPY_VERSION}"
	else
		echo "Downloading stormpy wheel from PyPI (latest)"
		"${STORMPY_PYTHON}" -m pip download --only-binary=:all: --no-deps -d /tmp/stormpy_wheels stormpy
	fi
	WHEEL_DIR=/tmp/stormpy_wheels
fi

# Prefer cp310 wheel; fall back to any wheel.
PYTAG=$("${STORMPY_PYTHON}" - <<'PY'
import sys
print(f"cp{sys.version_info.major}{sys.version_info.minor}")
PY
)

# Prefer a wheel matching the interpreter used for querying.
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
"${STORMPY_PYTHON}" -m venv "${STORMPY_QUERY_VENV}"

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

# Write origin information for CMake (used to avoid re-querying stormpy per wheel and to enable pretend-fetch metadata).
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

cd /tmp

# Install ginac
ginac_version=1.8.10
curl -fsSLO https://www.ginac.de/ginac-${ginac_version}.tar.bz2
tar -jxf ginac-${ginac_version}.tar.bz2
cd ginac-${ginac_version}
./configure CXXFLAGS="-O2"
make -j ${NR_JOBS}
make install
cd ..

# Install Boost 1.83 headers (no full build)
#
# Building all Boost libraries from source is extremely slow on GitHub-hosted Linux runners
# and is unnecessary for our use (we only need Boost headers at >= 1.83 for compilation).
BOOST_VERSION=1.83.0
BOOST_VERSION_UNDERSCORE=${BOOST_VERSION//./_}
BOOST_PREFIX=/opt/boost_${BOOST_VERSION_UNDERSCORE}

curl -fsSLO https://archives.boost.io/release/${BOOST_VERSION}/source/boost_${BOOST_VERSION_UNDERSCORE}.tar.gz
tar -xzf boost_${BOOST_VERSION_UNDERSCORE}.tar.gz

mkdir -p "${BOOST_PREFIX}/include"
cp -a "boost_${BOOST_VERSION_UNDERSCORE}/boost" "${BOOST_PREFIX}/include/"

# Install Storm (matching stormpy)
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
make install
cd ..
rm -rf build
