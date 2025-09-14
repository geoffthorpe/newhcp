ifndef V
	Q := @
endif

ifndef TOP
$(warning "Interactive shell should export TOP=$$(pwd) !!")
endif

TOP ?= $(shell pwd)
DEBVERSION ?= trixie
DEBSUPPORTED := bookworm trixie
QEMUSUPPORT := yes
UMLSUPPORT := yes
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
ifdef QEMUSUPPORT
QEMU_DISK_SIZE_MB := 4096
endif
ifdef UMLSUPPORT
UML_KERN_VER := 6.6.106
UML_DISK_SIZE_MB := 2096
endif

# Make this the first target
default:

ifneq ($(QEMUSUPPORT),yes)
QEMUSUPPORT :=
endif
ifneq ($(UMLSUPPORT),yes)
UMLSUPPORT :=
endif

qemusupport:
	$Q$(if $(QEMUSUPPORT),/bin/true,/bin/false)
umlsupport:
	$Q$(if $(UMLSUPPORT),/bin/true,/bin/false)

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
#      hcp_environment:trixie
#
# Sub-text: heimdal build is broken on trixie, so we need to build on bookworm,
# but bookworm's swtpm/tpm2-tools is too old, so we need to install and run on
# trixie. Fortunately, the bookworm-based build runs fine on trixie.
#
define cb_hcp_environment
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

ifdef QEMUSUPPORT
define cb_hcp_builder_qemu
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/qemu_create_image.sh ./ctx/syslinux.cfg
	$Qrsync -a ./ctx/qemu_create_image.sh ./ctx/syslinux.cfg $(_CTX)/
	$Qtouch $$@
endef
define cb_hcp_qemu_guest
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/systemd-shim.sh ./ctx/hcp.service
	$Qrsync -a ./ctx/systemd-shim.sh ./ctx/hcp.service $(_CTX)/
	$Qtouch $$@
endef
define cb_hcp_qemu_host
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/qemu_run.sh
	$Qrsync -a ./ctx/qemu_run.sh $(_CTX)/
	$Qtouch $$@
endef
endif

ifdef UMLSUPPORT
define cb_hcp_builder_uml
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/uml_create_image.sh ./ctx/syslinux.cfg
	$Qrsync -a ./ctx/uml_create_image.sh ./ctx/syslinux.cfg $(_CTX)/
	$Qtouch $$@
endef
define cb_hcp_builder_uml_kernel
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/uml-kernel.config
	$Qrsync -a ./ctx/uml-kernel.config $(_CTX)/
	$Qtouch $$@
endef
define cb_hcp_uml_guest
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/systemd-shim.sh ./ctx/hcp.service
	$Qrsync -a ./ctx/systemd-shim.sh ./ctx/hcp.service $(_CTX)/
	$Qtouch $$@
endef
define cb_hcp_uml_host
$(eval D := $(strip $1))
$(eval _CTX := $(strip $2))
$($D_SYNC): ./ctx/uml_run.sh
	$Qrsync -a ./ctx/uml_run.sh $(_CTX)/
	$Qtouch $$@
endef
endif

$(eval $(call parse_target,hcp_baseline,debian))
$(eval $(call parse_target,hcp_builder_heimdal,hcp_baseline))
$(eval $(call parse_target,hcp_builder_nginx,hcp_builder_heimdal,cb_hcp_builder_nginx))
$(eval $(call parse_target,hcp_environment,hcp_baseline,cb_hcp_environment))
ifdef QEMUSUPPORT
$(eval $(call parse_target,hcp_builder_qemu,hcp_baseline,cb_hcp_builder_qemu))
$(eval $(call parse_target,hcp_qemu_guest,hcp_environment,cb_hcp_qemu_guest))
$(eval $(call parse_target,hcp_qemu_host,hcp_environment,cb_hcp_qemu_host))
endif
ifdef UMLSUPPORT
$(eval $(call parse_target,hcp_builder_uml,hcp_baseline,cb_hcp_builder_uml))
$(eval $(call parse_target,hcp_builder_uml_kernel,hcp_builder_heimdal,cb_hcp_builder_uml_kernel))
$(eval $(call parse_target,hcp_uml_guest,hcp_environment,cb_hcp_uml_guest))
$(eval $(call parse_target,hcp_uml_host,hcp_environment,cb_hcp_uml_host))
endif

# The usecase requires host configs (and docker-compose.yml) to be generated
# from fleet.json
USECASE_HOSTS := $(shell PYTHONPATH=hcp/python ./usecase/fleet.py --show)
USECASE_DIR := $(CRUD)/usecase
USECASE_OUTS := $(foreach i,$(USECASE_HOSTS),$(USECASE_DIR)/$(i).json)
USECASE_OUTS += $(USECASE_DIR)/docker-compose.yml

# default needs to go after parse_target() but before gen_rules()
default: testcreds $(USECASE_OUTS)
default: $(foreach i,environment,$(hcp_$i_$(DEBVERSION)))
ifdef QEMUSUPPORT
default: $(foreach i,builder_qemu qemu_guest qemu_host,$(hcp_$i_$(DEBVERSION)))
endif
ifdef UMLSUPPORT
default: $(foreach i,builder_uml builder_uml_kernel uml_guest uml_host,$(hcp_$i_$(DEBVERSION)))
endif

$(eval $(call gen_rules))

ifdef QEMUSUPPORT
$(CRUD)/hcp_qemu_guest.tar: $(hcp_qemu_guest_$(DEBVERSION)) $(TOP)/Makefile
	$Qdocker export -o $@ `docker run --entrypoint="" -d hcp_qemu_guest:$(DEBVERSION) /bin/true`
$(CRUD)/hcp_qemu_guest.img: $(CRUD)/hcp_qemu_guest.tar $(hcp_builder_qemu_$(DEBVERSION))
	$Qdocker run -it --rm -v $(CRUD):/crud:rw \
		--privileged --cap-add SYS_ADMIN \
		hcp_builder_qemu:$(DEBVERSION) \
		bash -c 'mkdir -p /poo && tar -C /poo --numeric-owner -xf /crud/hcp_qemu_guest.tar && qemu_create_image.sh $(shell id -u) $(shell id -g) $(QEMU_DISK_SIZE_MB)'
default: $(CRUD)/hcp_qemu_guest.img
endif

ifdef UMLSUPPORT
$(CRUD)/hcp_uml_guest.tar: $(hcp_uml_guest_$(DEBVERSION)) $(TOP)/Makefile
	$Qdocker export -o $@ `docker run --entrypoint="" -d hcp_uml_guest:$(DEBVERSION) /bin/true`
$(CRUD)/hcp_uml_guest.img: $(CRUD)/hcp_uml_guest.tar $(hcp_builder_uml_$(DEBVERSION))
	$Qdocker run -it --rm -v $(CRUD):/crud:rw \
		--privileged --cap-add SYS_ADMIN \
		hcp_builder_uml:$(DEBVERSION) \
		bash -c 'mkdir -p /poo && tar -C /poo --numeric-owner -xf /crud/hcp_uml_guest.tar && uml_create_image.sh $(shell id -u) $(shell id -g) $(UML_DISK_SIZE_MB)'
default: $(CRUD)/hcp_uml_guest.img
$(CRUD)/linux-$(UML_KERN_VER).tar.xz:
	$Qcd $(CRUD) && wget https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-$(UML_KERN_VER).tar.xz
$(CRUD)/linux-$(UML_KERN_VER): $(CRUD)/linux-$(UML_KERN_VER).tar.xz
	$Qcd $(CRUD) && unxz -k linux-$(UML_KERN_VER).tar.xz && tar xf linux-$(UML_KERN_VER).tar
$(CRUD)/linux: $(hcp_builder_uml_kernel_$(DEBVERSION)) | $(CRUD)/linux-$(UML_KERN_VER)
	$Qdocker run -it --rm -v $(CRUD):/crud:rw \
		hcp_builder_uml_kernel:$(DEBVERSION) \
		bash -c 'cd /crud/linux-$(UML_KERN_VER) && cp /uml-kernel.config .config && make oldconfig ARCH=um && make ARCH=um -j 8 && cp linux /crud'
# Interactive shell to manually compile the kernel
uml_kernel_build_shell: $(hcp_builder_uml_kernel_$(DEBVERSION)) | $(CRUD)/linux-$(UML_KERN_VER)
	$Qecho "Kernel source tree is in: /crud/linux-$(UML_KERN_VER)"
	$Qecho "Don't forget to export ARCH=um"
	$Qdocker run -it --rm -v $(CRUD):/crud:rw \
		hcp_builder_uml_kernel:$(DEBVERSION) \
		bash
default: $(CRUD)/linux
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
