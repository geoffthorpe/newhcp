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
NGINX_OUT := nginx-install.tar.gz
CRUD := $(TOP)/_crud
MDIRS := $(CRUD)
TARGETS :=

include Makefile.macros

# So the Dockerfile and this Makefile need to agree on dependencies;
#
#      hcp_baseline:[bookworm|trixie]
#             |
#      hcp_platform:[bookworm|trixie]
#             |
#             +---------------+
#             |               |
#             |    hcp_builder_heimdal:bookworm
#             |               |
#             |       heimdal-install.tar.gz
#             |               |
#             |     hcp_builder_nginx:bookworm
#             |               |
#             |        nginx-install.tar.gz
#             |               |
#             +---------------+
#             |
#      hcp_caboodle:trixie
#
# Sub-text: heimdal build is broken on trixie, so we need to build on bookworm,
# but bookworm's swtpm/tpm2-tools is too old, so we need to install and run on
# trixie. Fortunately, the bookworm-based build runs fine on trixie.
#
define cb_hcp_caboodle
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): $(shell find ./ctx/hcp) $(shell find ./ctx/safeboot)
$($D_SYNC): ./ctx/ssh_config ./heimdal/$(HEIMDAL_OUT) ./nginx/$(NGINX_OUT)
	$Qrsync -a ./ctx/hcp ./ctx/safeboot ./ctx/ssh_config \
		./heimdal/$(HEIMDAL_OUT) ./nginx/$(NGINX_OUT) $(_CTX)/
	$Qtouch $$@
endef

define cb_hcp_builder_nginx
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./heimdal/$(HEIMDAL_OUT)
	$Qrsync -a ./heimdal/$(HEIMDAL_OUT) $(_CTX)/
	$Qtouch $$@
endef

$(eval $(call parse_target,hcp_baseline,debian))
$(eval $(call parse_target,hcp_builder_heimdal,hcp_baseline))
$(eval $(call parse_target,hcp_builder_nginx,hcp_builder_heimdal,cb_hcp_builder_nginx))
$(eval $(call parse_target,hcp_caboodle,hcp_baseline,cb_hcp_caboodle))

# default needs to go after parse_target() but before gen_rules()
default: testcreds $(hcp_caboodle_trixie)

$(eval $(call gen_rules))

# NB: the following dep uses "|" to avoid gratuitous rebuilds
heimdal/$(HEIMDAL_OUT): | $(hcp_builder_heimdal_bookworm)
	$Q$(DRUN) -v $(TOP)/heimdal:/heimdal $(hcp_builder_heimdal_bookworm_DNAME) bash -c \
		"cd /heimdal && ./autogen.sh && MAKEINFO=true ./configure --disable-texinfo --prefix=/install-heimdal && MAKEINFO=true make && MAKEINFO=true make install && tar zcf heimdal-install.tar.gz /install-heimdal"

nginx/$(NGINX_OUT): | $(hcp_builder_nginx_bookworm)
	$Q$(DRUN) -v $(TOP)/nginx:/nginx -v$(TOP)/spnego-http-auth-nginx-module:/nginx/spnego-http-auth-nginx-module $(hcp_builder_nginx_bookworm_DNAME) bash -c \
		"cd /nginx && auto/configure --prefix=/install-nginx --with-http_ssl_module --add-module=spnego-http-auth-nginx-module --with-cc-opt='-I /install-heimdal/include' --with-ld-opt='-L /install-heimdal/lib' && make install && tar zcf nginx-install.tar.gz /install-nginx"

clean:
ifneq (,$(wildcard $(CRUD)))
	$Qrm -rf $(CRUD)
endif

include Makefile.testcreds

$(MDIRS):
	$Qmkdir $@
