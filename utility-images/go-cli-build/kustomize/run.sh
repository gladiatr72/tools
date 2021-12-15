#!/bin/bash -
#===============================================================================
#
#          FILE: run.sh
#
#         USAGE: ./run.sh
#
#   DESCRIPTION: 
#
#       OPTIONS: ---
#  REQUIREMENTS: ---
#          BUGS: ---
#         NOTES: ---
#        AUTHOR: YOUR NAME (), 
#  ORGANIZATION: 
#       CREATED: 12/14/2021 11:49:57 AM
#      REVISION:  ---
#===============================================================================

set -o nounset                                  # Treat unset variables as an error

PROJECT=kustomize
KUST_FQ=github.com/kubernetes-sigs/kustomize
KUST_SRC="${GOPATH}/src/${KUST_FQ}"
DATE=$( date --iso-8601 )
VERSION=${VERSION:-$( cd $KUST_SRC && git describe --tags )}
VERSION=v${VERSION%%/*}
VERSION=v4.4.1
VERSION=v3.9.4

# --cache-from=gladiatr72/misc:${PROJECT}-src \

if [[ ! -f /usr/local/bin/_${PROJECT}-${VERSION} ]];
then
	docker run --rm -u $UID -v /usr/local/bin:/outbox gladiatr72/misc:${PROJECT}-${VERSION}

	if [[ $? ]];
	then
		docker buildx build  -t gladiatr72/misc:kustomize-src \
			-f ./Dockerfile-src \
			--build-arg=VERSION=${VERSION} \
			--build-arg=PROJECT=${PROJECT} \
			--build-arg BUILDKIT_INLINE_CACHE=1 \
			.

		docker buildx build -t gladiatr72/misc:${PROJECT}-${VERSION}-build \
			--build-arg=PROJECT=${PROJECT} \
			--build-arg=VERSION=${VERSION} \
			--build-arg=DATE=${DATE} \
			--build-arg BUILDKIT_INLINE_CACHE=1 \
			-f ./Dockerfile-build \
			.
		
		docker buildx build -t gladiatr72/misc:${PROJECT}-${VERSION} \
			--build-arg=PROJECT=${PROJECT} \
			--build-arg=VERSION=${VERSION} \
			. 

		docker push gladiatr72/misc:${PROJECT}-${VERSION} 
		docker push gladiatr72/misc:${PROJECT}-src 

		docker run --rm -u $UID -v /usr/local/bin:/outbox gladiatr72/misc:${PROJECT}-${VERSION}
	fi
fi
