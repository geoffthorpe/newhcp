ifndef V
	Q := @
endif

TOP ?= $(shell pwd)
DEBVERSION ?= trixie
TAG ?= $(DEBVERSION)
TIMEZONE ?= US/Eastern
DBCMD := docker build --build-arg MYTZ=$(TIMEZONE)
DRUN := docker run --rm
HEIMDAL_OUT := heimdal-install.tar.gz

# So the Dockerfile and this Makefile need to agree on dependencies;
#
#        hcp_baseline
#             |
#        hcp_platform
#             |
#             +----------+
#             |          |
#             |     hcp_builder
#             |          |
#             |   heimdal-install.tar.gz
#             |          |
#             +----------+
#             |
#         hcp_caboodle

default: testcreds hcp_caboodle
clean:

Dockerfile.$(DEBVERSION): Dockerfile.input Makefile
	$Qecho "FROM debian:$(DEBVERSION) AS hcp_baseline" > $@
	$Qcat $< >> $@
ifneq (,$(wildcard Dockerfile.$(DEBVERSION)))
clean_Dockerfile:
	$Qrm Dockerfile.$(DEBVERSION)
clean: clean_Dockerfile
endif

hcp_baseline: Dockerfile.$(DEBVERSION)
	$Q$(DBCMD) -f $< -t $@:$(TAG) --target $@ ctx
hcp_platform: hcp_baseline
hcp_builder: hcp_platform
hcp_caboodle: hcp_platform ctx/$(HEIMDAL_OUT)
hcp_platform hcp_builder hcp_caboodle:
	$Q$(DBCMD) -f Dockerfile.$(TAG) -t $@:$(TAG) --target $@ ctx

#ctx/$(HEIMDAL_OUT): heimdal/$(HEIMDAL_OUT)
#	cp $< $@
#heimdal/touch-to-rebuild: heimdal/configure.ac
#	$Qtouch $@
#heimdal/$(HEIMDAL_OUT): hcp_builder heimdal/touch-to-rebuild
#	$Q$(DRUN) -v $(TOP)/heimdal:/heimdal hcp_builder:$(TAG) bash -c \
#		"cd /heimdal && MAKEINFO=true make install && tar zcf heimdal-install.tar.gz /install-heimdal"
		#"cd /heimdal && ./autogen.sh && MAKEINFO=true ./configure --disable-texinfo --prefix=/install-heimdal && MAKEINFO=true make && MAKEINFO=true make install && tar zcf heimdal-install.tar.gz /install-heimdal"

ifneq (,$(shell docker image ls -q hcp_caboodle:$(TAG)))
clean_hcp_caboodle:
	$Qdocker image rm hcp_caboodle:$(TAG)
clean: clean_hcp_caboodle
clean_hcp_platform: clean_hcp_caboodle
endif
ifneq (,$(shell docker image ls -q hcp_builder:$(TAG)))
clean_hcp_builder:
	$Qdocker image rm hcp_builder:$(TAG)
clean: clean_hcp_builder
clean_hcp_platform: clean_hcp_builder
endif
ifneq (,$(shell docker image ls -q hcp_platform:$(TAG)))
clean_hcp_platform:
	$Qdocker image rm hcp_platform:$(TAG)
clean: clean_hcp_platform
clean_hcp_baseline: clean_hcp_platform
endif
ifneq (,$(shell docker image ls -q hcp_baseline:$(TAG)))
clean_hcp_baseline:
	$Qdocker image rm hcp_baseline:$(TAG)
clean: clean_hcp_baseline
endif

include Makefile.testcreds
