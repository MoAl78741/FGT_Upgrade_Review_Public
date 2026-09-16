#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/verify_vendor.py
docker load -i vendor/base-images/node-22-linux-amd64.tar.gz
docker load -i vendor/base-images/python-3.12-linux-amd64.tar.gz
edition=$(cat EDITION)
image_edition=$edition
if [ "$edition" = private ]; then image_edition=pro; fi
docker build --platform linux/amd64 --network=none --pull=false \
  --build-arg "APP_EDITION=$edition" --build-arg "BUILD_NUMBER=${BUILD_NUMBER:-offline}" \
  --build-arg "BUILD_REVISION=${BUILD_REVISION:-}" \
  -t "fgt-upgrade-review-$image_edition:${IMAGE_TAG:-offline}" .
