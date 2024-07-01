ifndef V
	Q := @
endif

TOP ?= $(shell pwd)
DEBVERSION ?= trixie
DEBSUPPORTED := bookworm trixie
TAG ?= $(DEBVERSION)
TIMEZONE ?= US/Eastern
DBCMD := docker build --build-arg MYTZ=$(TIMEZONE)
DRUN := docker run --rm
HEIMDAL_OUT := heimdal-install.tar.gz
CRUD := $(TOP)/_crud
MDIRS := $(CRUD)

# For a given debian version, define a rule for the given target
define prep_target
$(eval IMG := $(strip $1))
$(eval DEB := $(strip $2))
$(eval $(IMG)_$(DEB) := $(CRUD)/built_$(IMG)_$(DEB))
$(eval $(IMG)_$(DEB)_DNAME := $(IMG):$(DEB))
endef
define do_target
$(eval IMG := $(strip $1))
$(eval DEB := $(strip $2))
$(IMG)_$(DEB): $($(IMG)_$(DEB))
$($(IMG)_$(DEB)): $(CRUD)/Dockerfile.$(DEB)
	$Q$(DBCMD) -f $(CRUD)/Dockerfile.$(DEB) -t $($(IMG)_$(DEB)_DNAME) --target $(IMG) ctx
	$Qtouch $$@
endef

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

$(eval $(call prep_target,hcp_baseline,bookworm))
$(eval $(call prep_target,hcp_baseline,trixie))
$(eval $(call prep_target,hcp_platform,bookworm))
$(eval $(call prep_target,hcp_platform,trixie))
$(eval $(call prep_target,hcp_builder,bookworm))
$(eval $(call prep_target,hcp_caboodle,trixie))

default: testcreds $(hcp_caboodle_trixie)
clean:
ifneq (,$(wildcard $(MDIRS)))
	$Qrmdir $(MDIRS)
endif

$(eval $(call do_target,hcp_baseline,bookworm))
$(eval $(call do_target,hcp_baseline,trixie))
$(eval $(call do_target,hcp_platform,bookworm))
$(eval $(call do_target,hcp_platform,trixie))
$(eval $(call do_target,hcp_caboodle,trixie))
$(eval $(call do_target,hcp_builder,bookworm))
$(hcp_caboodle_trixie): $(hcp_platform_trixie) ctx/$(HEIMDAL_OUT)
$(hcp_platform_trixie): $(hcp_baseline_trixie)
$(hcp_platform_bookworm): $(hcp_baseline_bookworm)
$(hcp_builder_bookworm): $(hcp_platform_bookworm)

$(CRUD)/Dockerfile.trixie: Dockerfile.input Makefile | $(CRUD)
	$Qecho "FROM debian:trixie AS hcp_baseline" > $@
	$Qcat $< >> $@
ifneq (,$(wildcard $(CRUD)/Dockerfile.trixie))
clean_Dockerfile_trixie:
	$Qrm $(CRUD)/Dockerfile.trixie
clean: clean_Dockerfile_trixie
endif
$(CRUD)/Dockerfile.bookworm: Dockerfile.input Makefile | $(CRUD)
	$Qecho "FROM debian:bookworm AS hcp_baseline" > $@
	$Qcat $< >> $@
ifneq (,$(wildcard $(CRUD)/Dockerfile.bookworm))
clean_Dockerfile_bookworm:
	$Qrm $(CRUD)/Dockerfile.bookworm
clean: clean_Dockerfile_bookworm
endif

ctx/$(HEIMDAL_OUT): heimdal/$(HEIMDAL_OUT)
	cp $< $@
heimdal/$(HEIMDAL_OUT): $(hcp_builder_bookworm)
	$Q$(DRUN) -v $(TOP)/heimdal:/heimdal $(hcp_builder_bookworm_DNAME) bash -c \
		"cd /heimdal && ./autogen.sh && MAKEINFO=true ./configure --disable-texinfo --prefix=/install-heimdal && MAKEINFO=true make && MAKEINFO=true make install && tar zcf heimdal-install.tar.gz /install-heimdal"
ifneq (,ctx/$(HEIMDAL_OUT))
clean_heimdal_tarball:
	$Qrm ctx/$(HEIMDAL_OUT)
clean: clean_heimdal_tarball
endif

ifneq (,$(wildcard $(hcp_caboodle_trixie)))
clean_hcp_caboodle_trixie:
	$Qdocker image rm $(hcp_caboodle_trixie_DNAME)
	$Qrm -f $(hcp_caboodle_trixie)
clean: clean_hcp_caboodle_trixie
clean_hcp_platform_trixie: clean_hcp_caboodle_trixie
endif
ifneq (,$(wildcard $(hcp_builder_bookworm)))
clean_hcp_builder_bookworm:
	$Qdocker image rm $(hcp_builder_bookworm_DNAME)
	$Qrm -f $(hcp_builder_bookworm)
clean: clean_hcp_builder_bookworm
clean_hcp_platform_bookworm: clean_hcp_builder_bookworm
endif
ifneq (,$(wildcard $(hcp_platform_trixie)))
clean_hcp_platform_trixie:
	$Qdocker image rm $(hcp_platform_trixie_DNAME)
	$Qrm -f $(hcp_platform_trixie)
clean: clean_hcp_platform_trixie
clean_hcp_baseline_trixie: clean_hcp_platform_trixie
endif
ifneq (,$(wildcard $(hcp_platform_bookworm)))
clean_hcp_platform_bookworm:
	$Qdocker image rm $(hcp_platform_bookworm_DNAME)
	$Qrm -f $(hcp_platform_bookworm)
clean: clean_hcp_platform_bookworm
clean_hcp_baseline_bookworm: clean_hcp_platform_bookworm
endif
ifneq (,$(wildcard $(hcp_baseline_trixie)))
clean_hcp_baseline_trixie:
	$Qdocker image rm $(hcp_baseline_trixie_DNAME)
	$Qrm -f $(hcp_baseline_trixie)
clean: clean_hcp_baseline_trixie
endif
ifneq (,$(wildcard $(hcp_baseline_bookworm)))
clean_hcp_baseline_bookworm:
	$Qdocker image rm $(hcp_baseline_bookworm_DNAME)
	$Qrm -f $(hcp_baseline_bookworm)
clean: clean_hcp_baseline_bookworm
endif

include Makefile.testcreds

$(MDIRS):
	$Qmkdir $@
