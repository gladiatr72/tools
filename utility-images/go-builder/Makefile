.PHONY: image all

ifndef IMAGE_VERSION
	IMAGE_VERSION := go-build
endif

all: image image-push

image:
	@echo "building go-builder"
	@docker buildx build -t gladiatr72/misc:go-build .

image-push: image
	@echo "pushing go-builder"
	@docker push gladiatr72/misc:go-build

clean:
	@docker inspect gladiatr72/misc:go-build >& /dev/null && docker rm gladiatr72/misc:go-build

