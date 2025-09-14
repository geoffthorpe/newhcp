ifndef V
	Q := @
endif

ifndef TOP
$(warning "Interactive shell should export TOP=$$(pwd) !!")
endif

TOP ?= $(shell pwd)
DEBVERSION ?= trixie
DEBSUPPORTED := bookworm trixie
VMSUPPORT := yes
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
ifdef VMSUPPORT
VM_DISK_SIZE_MB := 4096
endif

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
#             |     hcp_builder_nginx:trixie
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
$($D_SYNC): ./ctx/ssh_config ./heimdal/$(HEIMDAL_OUT) ./nginx/$(NGINX_OUT)
	$Qrsync -a ./ctx/ssh_config ./heimdal/$(HEIMDAL_OUT) ./nginx/$(NGINX_OUT) $(_CTX)/
	$Qtouch $$@
endef

define cb_hcp_builder_nginx
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./heimdal/$(HEIMDAL_OUT)
	$Qrsync -a ./heimdal/$(HEIMDAL_OUT) $(_CTX)/
	$Qtouch $$@
endef

ifdef VMSUPPORT

define cb_hcp_builder_vm
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/create_image.sh ./ctx/syslinux.cfg
	$Qrsync -a ./ctx/create_image.sh ./ctx/syslinux.cfg $(_CTX)/
	$Qtouch $$@
endef

define cb_hcp_caboodle_vm
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/systemd-shim.sh ./ctx/hcp.service
	$Qrsync -a ./ctx/systemd-shim.sh ./ctx/hcp.service $(_CTX)/
	$Qtouch $$@
endef

define cb_hcp_caboodle_qemu
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/qemu_run.sh
	$Qrsync -a ./ctx/qemu_run.sh $(_CTX)/
	$Qtouch $$@
endef

endif

$(eval $(call parse_target,hcp_baseline,debian))
$(eval $(call parse_target,hcp_builder_heimdal,hcp_baseline))
$(eval $(call parse_target,hcp_builder_nginx,hcp_builder_heimdal,cb_hcp_builder_nginx))
$(eval $(call parse_target,hcp_caboodle,hcp_baseline,cb_hcp_caboodle))
ifdef VMSUPPORT
$(eval $(call parse_target,hcp_builder_vm,hcp_baseline,cb_hcp_builder_vm))
$(eval $(call parse_target,hcp_caboodle_vm,hcp_caboodle,cb_hcp_caboodle_vm))
$(eval $(call parse_target,hcp_caboodle_qemu,hcp_caboodle,cb_hcp_caboodle_qemu))
endif

# The usecase requires host configs (and docker-compose.yml) to be generated
# from fleet.json
USECASE_HOSTS := $(shell PYTHONPATH=hcp/python ./usecase/fleet.py --show)
USECASE_DIR := $(CRUD)/usecase
USECASE_OUTS := $(foreach i,$(USECASE_HOSTS),$(USECASE_DIR)/$(i).json)
USECASE_OUTS += $(USECASE_DIR)/docker-compose.yml

# default needs to go after parse_target() but before gen_rules()
default: testcreds $(USECASE_OUTS)
default: $(foreach i,caboodle,$(hcp_$i_$(DEBVERSION)))
ifdef VMSUPPORT
default: $(foreach i,builder_vm caboodle_vm caboodle_qemu,$(hcp_$i_$(DEBVERSION)))
endif

$(eval $(call gen_rules))

ifdef VMSUPPORT
$(CRUD)/hcp_caboodle_vm.tar: $(hcp_caboodle_vm_$(DEBVERSION)) $(TOP)/Makefile
	$Qdocker export -o $@ `docker run --entrypoint="" -d hcp_caboodle_vm:$(DEBVERSION) /bin/true`
$(CRUD)/hcp_caboodle_vm.img: $(CRUD)/hcp_caboodle_vm.tar $(hcp_builder_vm_$(DEBVERSION))
	$Qdocker run -it -v $(CRUD):/crud:rw \
		--privileged --cap-add SYS_ADMIN \
		hcp_builder_vm:$(DEBVERSION) \
		bash -c 'mkdir -p /poo && tar -C /poo --numeric-owner -xf /crud/hcp_caboodle_vm.tar && create_image.sh $(shell id -u) $(shell id -g) $(VM_DISK_SIZE_MB)'
default: $(CRUD)/hcp_caboodle_vm.img
endif

$(USECASE_DIR): | $(CRUD)
MDIRS += $(USECASE_DIR)
$(USECASE_DIR)/docker-compose.yml: usecase/fleet.json usecase/fleet.py
	$Q PYTHONPATH=hcp/python ./usecase/fleet.py --docker $@
define usecase_host
$(USECASE_DIR)/$1.json: | $(USECASE_DIR)
$(USECASE_DIR)/$1.json: usecase/fleet.json usecase/fleet.py
	$Q PYTHONPATH=hcp/python ./usecase/fleet.py --hosts=$(USECASE_DIR) $1
endef
$(foreach i,$(USECASE_HOSTS),$(eval $(call usecase_host,$i)))
ifneq (,$(wildcard $(USECASE_DIR)))
clean_usecase:
	$Qrm $(USECASE_OUTS)
	$Qrmdir $(USECASE_DIR)
clean: clean_usecase
endif

# NB: the following dep uses "|" to avoid gratuitous rebuilds
heimdal/$(HEIMDAL_OUT): | $(hcp_builder_heimdal_bookworm)
	$Q$(DRUN) -v $(TOP)/heimdal:/heimdal $(hcp_builder_heimdal_bookworm_DNAME) bash -c \
		"cd /heimdal && ./autogen.sh && MAKEINFO=true ./configure --disable-texinfo --prefix=/install-heimdal && MAKEINFO=true make && MAKEINFO=true make install && tar zcf heimdal-install.tar.gz /install-heimdal"

nginx/$(NGINX_OUT): | $(hcp_builder_nginx_trixie)
	$Q$(DRUN) -v $(TOP)/nginx:/nginx -v$(TOP)/spnego-http-auth-nginx-module:/nginx/spnego-http-auth-nginx-module $(hcp_builder_nginx_trixie_DNAME) bash -c \
		"cd /nginx && perl -pi.bak -e 's/-lgssapi_krb5/-lgssapi/' spnego-http-auth-nginx-module/config && auto/configure --prefix=/install-nginx --with-http_ssl_module --add-module=spnego-http-auth-nginx-module --with-cc-opt='-I /install-heimdal/include' --with-ld-opt='-L /install-heimdal/lib' && make install && tar zcf nginx-install.tar.gz /install-nginx"

clean:
ifneq (,$(wildcard $(CRUD)))
	$Qrm -rf $(CRUD)
endif

include Makefile.testcreds

$(MDIRS):
	$Qmkdir $@
