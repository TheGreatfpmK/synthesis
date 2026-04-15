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

"${STORMPY_PYTHON}" -m pip install -U pip

# Install stormpy for querying Storm origin information.
# - nightly: use wheels downloaded into stormpy_wheels/
# - release: install from PyPI (optionally pinned via STORMPY_VERSION)
WHEEL_DIR="${PROJECT_DIR}/stormpy_wheels"
if [[ -d "${WHEEL_DIR}" ]] && compgen -G "${WHEEL_DIR}/stormpy-*.whl" > /dev/null; then
	echo "Installing stormpy from local wheels in: ${WHEEL_DIR}"
	# Prefer cp310 wheel; fall back to any compatible wheel.
	WHEEL=$(ls "${WHEEL_DIR}"/stormpy-*-cp310-*.whl 2>/dev/null | head -n 1 || true)
	if [[ -z "${WHEEL:-}" ]]; then
		WHEEL=$(ls "${WHEEL_DIR}"/stormpy-*.whl 2>/dev/null | head -n 1 || true)
	fi
	if [[ -z "${WHEEL:-}" ]]; then
		echo "No stormpy wheel found in ${WHEEL_DIR}" >&2
		exit 1
	fi
	"${STORMPY_PYTHON}" -m pip install --force-reinstall "${WHEEL}"
else
	if [[ -n "${STORMPY_VERSION:-}" ]]; then
		echo "Installing stormpy==${STORMPY_VERSION} from PyPI"
		"${STORMPY_PYTHON}" -m pip install "stormpy==${STORMPY_VERSION}"
	else
		echo "Installing stormpy from PyPI (latest)"
		"${STORMPY_PYTHON}" -m pip install stormpy
	fi
fi

echo "stormpy for origin query:"
"${STORMPY_PYTHON}" -c "import stormpy; print(stormpy.__version__, 'from', stormpy.__file__)"

# Determine which Storm version stormpy was built against.
STORM_ORIGIN=$(
	"${STORMPY_PYTHON}" -c "import stormpy.info; repo, tag, commit = stormpy.info.storm_origin_info(); print('{};{};{}'.format(repo or '', tag or '', commit or ''))"
)

STORM_REPO="${STORM_ORIGIN%%;*}"
REST="${STORM_ORIGIN#*;}"
STORM_TAG="${REST%%;*}"
STORM_COMMIT="${REST#*;}"

if [[ -n "${STORM_TAG}" ]]; then
	STORM_VERSION_RESOLVED="${STORM_TAG}"
elif [[ -n "${STORM_COMMIT}" ]]; then
	STORM_VERSION_RESOLVED="${STORM_COMMIT}"
else
	echo "Failed to determine Storm origin from stormpy (got: '${STORM_ORIGIN}')" >&2
	STORM_VERSION_RESOLVED="${STORM_VERSION:-master}"
fi

if [[ -z "${STORM_REPO}" ]]; then
	STORM_REPO="https://github.com/moves-rwth/storm.git"
fi

echo "Resolved Storm origin: repo='${STORM_REPO}', tag='${STORM_TAG}', commit='${STORM_COMMIT}'"
echo "Storm version to build: ${STORM_VERSION_RESOLVED}"

# Write origin information for CMake (used to avoid re-querying stormpy per wheel and to enable pretend-fetch metadata).
ORIGIN_FILE="${PROJECT_DIR}/.paynt_storm_origin.cmake"
cat > "${ORIGIN_FILE}" <<EOF
set(PAYNT_INFO_PRETEND_FETCH ON)
set(STORM_GIT_REPO "${STORM_REPO}")
set(STORM_GIT_TAG "${STORM_VERSION_RESOLVED}")
set(ALLOW_STORM_SYSTEM ON)
set(ALLOW_STORM_FETCH OFF)
set(STORM_DIR_HINT "/usr/local")
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
STORM_VERSION="${STORM_VERSION_RESOLVED}"

rm -rf storm
if git clone --depth 1 --branch "${STORM_VERSION}" "${STORM_REPO}" storm 2>/dev/null; then
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
