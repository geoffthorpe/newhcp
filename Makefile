ifndef V
	Q := @
endif

TOP ?= $(shell pwd)
DEBVERSION ?= trixie
DEBSUPPORTED := bookworm trixie
TAG ?= $(DEBVERSION)
TIMEZONE ?= US/Eastern
DBCMD := docker build --build-arg MYTZ=$(TIMEZONE)
DRMV := docker image rm
DRUN := docker run --rm
HEIMDAL_OUT := heimdal-install.tar.gz
CRUD := $(TOP)/_crud
MDIRS := $(CRUD)
TARGETS :=

include Makefile.macros

# So the Dockerfile and this Makefile need to agree on dependencies;
#
#        hcp_baseline:[bookworm|trixie]
#             |
#        hcp_platform:[bookworm|trixie]
#             |
#             +----------+
#             |          |
#             |     hcp_builder:bookworm
#             |          |
#             |   heimdal-install.tar.gz
#             |          |
#             +----------+
#             |
#         hcp_caboodle:trixie
#
# Sub-text: heimdal build is broken on trixie, so we need to build on bookworm,
# but bookworm's swtpm/tpm2-tools is too old, so we need to install and run on
# trixie. Fortunately, the bookworm-based build runs fine on trixie.
#
define cb_hcp_caboodle
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): $(shell find ./ctx/hcp) $(shell find ./ctx/safeboot) ./ctx/ssh_config ./heimdal/$(HEIMDAL_OUT)
	$Qrsync -a ./ctx/hcp ./ctx/safeboot ./ctx/ssh_config ./heimdal/$(HEIMDAL_OUT) $(_CTX)/
	$Qtouch $$@
endef

$(eval $(call parse_target,hcp_baseline,debian))
$(eval $(call parse_target,hcp_builder,hcp_baseline))
$(eval $(call parse_target,hcp_caboodle,hcp_baseline,cb_hcp_caboodle))

# default needs to go after parse_target() but before gen_rules()
default: testcreds $(hcp_caboodle_trixie)

$(eval $(call gen_rules))

# NB: the following dep uses "|" to avoid gratuitous rebuilds
heimdal/$(HEIMDAL_OUT): | $(hcp_builder_bookworm)
	$Q$(DRUN) -v $(TOP)/heimdal:/heimdal $(hcp_builder_bookworm_DNAME) bash -c \
		"cd /heimdal && ./autogen.sh && MAKEINFO=true ./configure --disable-texinfo --prefix=/install-heimdal && MAKEINFO=true make && MAKEINFO=true make install && tar zcf heimdal-install.tar.gz /install-heimdal"

clean:
ifneq (,$(wildcard $(CRUD)))
	$Qrm -rf $(CRUD)
endif

include Makefile.testcreds

$(MDIRS):
	$Qmkdir $@
