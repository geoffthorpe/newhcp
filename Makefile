ifndef V
	Q := @
endif

TOP ?= $(shell pwd)
DEBVERSION ?= trixie
TAG ?= $(DEBVERSION)
TIMEZONE ?= US/Eastern

default: caboodle testcreds
clean:

caboodle: Dockerfile.$(DEBVERSION)
	$Qecho "SETTING TIMEZONE: $(TIMEZONE)"
	$Qdocker build -f $< \
		-t caboodle:$(TAG) \
		--build-arg MYTZ=$(TIMEZONE) \
		.
ifneq (,$(shell docker image ls -q caboodle:$(TAG)))
clean_caboodle:
	$Qdocker image rm caboodle:$(TAG)
clean: clean_caboodle
endif

Dockerfile.$(DEBVERSION): Dockerfile.input
	$Qecho "FROM debian:$(DEBVERSION)" > $@
	$Qcat $< >> $@
ifneq (,$(wildcard Dockerfile.$(DEBVERSION)))
clean_Dockerfile:
	$Qrm Dockerfile.$(DEBVERSION)
clean: clean_Dockerfile
endif

include Makefile.testcreds
