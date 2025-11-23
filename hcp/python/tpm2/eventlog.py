#!/usr/bin/python3
# vim: set expandtab shiftwidth=4 softtabstop=4:

import sys
import json
import struct
import enum

# Object type names, we set the '__type' field to one of these strings
STR_PCClientPCREvent = 'TCG_PCClientPCREvent'
STR_PCR_EVENT2 = 'TCG_PCR_EVENT2'
STR_TPML_DIGEST_VALUES = 'TPML_DIGEST_VALUES'
STR_TPMT_HA = 'TPMT_HA'
STR_EfiSpecIdEvent = 'TCG_EfiSpecIdEvent'
STR_EfiSpecIdEventAlgorithmSize = 'TCG_EfiSpecIdEventAlgorithmSize'
# Field names (verbatim from the tables in the TCG doc). Our objects are
# derived from dict in order to store key-value pairs, and these strings are to
# be the keys. (E.g. if there's a need to regionalize, you can modify these.)
STR_PCRIndex = 'PCRIndex'
STR_eventType = 'eventType'
STR_digest = 'digest'
STR_eventDataSize = 'eventDataSize'
STR_event = 'event'
STR_count = 'count'
STR_digests = 'digests'
STR_algId = 'algId'
STR_signature = 'signature'
STR_platformClass = 'platformClass'
STR_familyVersionMinor = 'familyVersionMinor'
STR_familyVersionMajor = 'familyVersionMajor'
STR_specRevision = 'specRevision'
STR_uintnSize = 'uintnSize'
STR_numberOfAlgorithms = 'numberOfAlgorithms'
STR_digestSizes = 'digestSizes'
STR_vendorInfoSize = 'vendorInfoSize'
STR_vendorInfo = 'vendorInfo'
STR_algorithmId = 'algorithmId'
STR_digestSize = 'digestSize'
# Synthetic field names (we add these).
STR_type = '__type'

# We want to be able to JSON-serialize our parsed objects, but these will
# include binary data and we'd prefer to replace those with corresponding
# hex-strings instead.

def getJSONEncoder(cls):
    class newEncoder(cls if cls else json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, bytes):
                return f"hex:{obj.hex()}"
            return json.JSONEncoder.default(self, obj)
    return newEncoder

JSONEncoder = getJSONEncoder(None)

# Now, a user can dump one of our objects using something like;
#
#   my_string = json.dumps(my_object, cls=thismodulename.JSONEncoder)
#
# And if they _already_ use an overloaded encoder (i.e. they already set the
# 'cls' parameter to 'fooEncoder'), then they can piggy-back. I.e. rather than;
#
#   my_string = json.dumps(my_object, cls=fooEncoder)
#
# They would instead do;
#
#   my_string = json.dumps(my_object,
#                   cls=thismodulename.getJSONEncoder(fooEncoder))

EmbedType = True

class basedict(dict):
    def __init__(self):
        super().__init__()
        self.sz = 0
    def set_type(self, t):
        if EmbedType:
            self[STR_type] = t

class TPMT_HA(basedict):
    def __init__(self, b):
        super().__init__()
        assert len(b) >= 2, "Incomplete TPMT_HA header"
        (self[STR_algId],) = struct.unpack("<H", b[0:2])
        b = b[2:]
        self.sz += 2
        match self[STR_algId]:
            case 4: # SHA1
                sz = 20
            case 11: # SHA256
                sz = 32
            case 12: # SHA384
                sz = 48
            case 13: # SHA512
                sz = 64
            case 39: # SHA3_224
                sz = 28
            case 40: # SHA3_256
                sz = 32
            case 41: # SHA3_512
                sz = 64
            case _:
                assert False, f"Unrecognized digest algId: {self[STR_algId]}"
        assert len(b) >= sz, "Incomplete TPMT_HA data"
        (self[STR_digest],) = struct.unpack(f"<{sz}s", b[0:sz])
        b = b[sz:]
        self.sz += sz
        self.set_type(STR_TPMT_HA)

class TPML_DIGEST_VALUES(basedict):
    def __init__(self, b):
        super().__init__()
        assert len(b) >= 4, "Incomplete TPML_DIGEST_VALUES header"
        (self[STR_count],) = struct.unpack("<I", b[0:4])
        b = b[4:]
        self.sz += 4
        self[STR_digests] = []
        num = self[STR_count]
        while num:
            nextdigest = TPMT_HA(b)
            self[STR_digests].append(nextdigest)
            b = b[nextdigest.sz:]
            self.sz += nextdigest.sz
            num -= 1
        self.set_type(STR_TPML_DIGEST_VALUES)

class TCG_EventType(enum.IntEnum):
    EV_PREBOOT_CERT = 0x0
    EV_POST_CODE = 0x1
    EV_UNUSED = 0x2
    EV_NO_ACTION = 0x3
    EV_SEPARATOR = 0x4
    EV_ACTION = 0x5
    EV_EVENT_TAG = 0x6
    EV_S_CRTM_CONTENTS = 0x7
    EV_S_CRTM_VERSION = 0x8
    EV_CPU_MICROCODE = 0x9
    EV_PLATFORM_CONFIG_FLAGS = 0xA
    EV_TABLE_OF_DEVICES = 0xB
    EV_COMPACT_HASH = 0xC
    EV_IPL = 0xD
    EV_IPL_PARTITION_DATA = 0xE
    EV_NONHOST_CODE = 0xF
    EV_NONHOST_CONFIG = 0x10
    EV_NONHOST_INFO = 0x11
    EV_OMIT_BOOT_DEVICE_EVENTS = 0x12
    EV_POST_CODE2 = 0x13
    EV_EFI_EVENT_BASE = 0x80000000
    EV_EFI_VARIABLE_DRIVER_CONFIG = EV_EFI_EVENT_BASE + 0x1
    EV_EFI_VARIABLE_BOOT = EV_EFI_EVENT_BASE + 0x2
    EV_EFI_BOOT_SERVICES_APPLICATION = EV_EFI_EVENT_BASE + 0x3
    EV_EFI_BOOT_SERVICES_DRIVER = EV_EFI_EVENT_BASE + 0x4
    EV_EFI_RUNTIME_SERVICES_DRIVER = EV_EFI_EVENT_BASE + 0x5
    EV_EFI_GPT_EVENT = EV_EFI_EVENT_BASE + 0x6
    EV_EFI_ACTION = EV_EFI_EVENT_BASE + 0x7
    EV_EFI_PLATFORM_FIRMWARE_BLOB = EV_EFI_EVENT_BASE + 0x8
    EV_EFI_HANDOFF_TABLES = EV_EFI_EVENT_BASE + 0x9
    EV_EFI_PLATFORM_FIRMWARE_BLOB2 = EV_EFI_EVENT_BASE + 0xA
    EV_EFI_HANDOFF_TABLES2 = EV_EFI_EVENT_BASE + 0xB
    EV_EFI_VARIABLE_BOOT2 = EV_EFI_EVENT_BASE + 0xC
    EV_EFI_GPT_EVENT2 = EV_EFI_EVENT_BASE + 0xD
    EV_EFI_HCRTM_EVENT2 = EV_EFI_EVENT_BASE + 0x10
    EV_EFI_VARIABLE_AUTHORITY = EV_EFI_EVENT_BASE + 0xE0
    EV_EFI_SPDM_FIRMWARE_BLOB = EV_EFI_EVENT_BASE + 0xE1
    EV_EFI_SPDM_FIRMWARE_CONFIG = EV_EFI_EVENT_BASE + 0xE2
    EV_EFI_SPDM_DEVICE_POLICY = EV_EFI_EVENT_BASE + 0xE3
    EV_EFI_SPDM_DEVICE_AUTHORITY = EV_EFI_EVENT_BASE + 0xE4
    EV_UNKNOWN = 0xFFFFFFFF

class TCG_Event(basedict):
    def __init__(self, b, isFirst = False):
        super().__init__()
        assert len(b) >= 8, "Incomplete TCG event header"
        (self[STR_PCRIndex], self[STR_eventType]) = struct.unpack("<II", b[0:8])
        b = b[8:]
        self.sz += 8
        self.isFirst = isFirst
        if isFirst:
            assert self[STR_eventType] == TCG_EventType.EV_NO_ACTION
            assert len(b) >= 24, "Incomplete PCClientPCREvent header"
            (self[STR_digest], self[STR_eventDataSize]) = struct.unpack("<20sI",
                                                                        b[0:24])
            b = b[24:]
            self.sz += 24
            assert len(b) >= self[STR_eventDataSize], \
                "Incomplete PCClientPCREvent data"
            self.set_type(STR_PCClientPCREvent)
        else:
            # TCG_PCR_EVENT2
            self[STR_digests] = TPML_DIGEST_VALUES(b)
            b = b[self[STR_digests].sz:]
            self.sz += self[STR_digests].sz
            assert len(b) >= 4, "Incomplete PCR_EVENT2 header"
            (self[STR_eventDataSize],) = struct.unpack("<I", b[0:4])
            b = b[4:]
            self.sz += 4
            assert len(b) >= self[STR_eventDataSize], \
                "Incomplete PCR_EVENT2 data"
            self.set_type(STR_PCR_EVENT2)
        self[STR_event] = b[0:self[STR_eventDataSize]]
        b = b[self[STR_eventDataSize]:]
        self.sz += self[STR_eventDataSize]
        # Now specialize the event. This will magically morph the 'event'
        # field, currently filled with a byte array, into a TCG_Event object (a
        # glorified dict) with all the fields decoded.
        if self.isFirst:
            self[STR_event] = TCG_EfiSpecIdEvent(self[STR_event])

class TCG_EventLog(list):
    def __init__(self, b, isFirst = True):
        self.sz = 0
        while len(b) > 0:
            event = TCG_Event(b, isFirst = len(self) == 0)
            b = b[event.sz:]
            self.sz += event.sz
            self.append(event)

class TCG_EfiSpecIdEvent(basedict):
    def __init__(self, b):
        super().__init__()
        assert len(b) >= 28, "Incomplete TCG_EfiSpecIdEvent header"
        (self[STR_signature],
         self[STR_platformClass],
         self[STR_familyVersionMinor],
         self[STR_familyVersionMajor],
         self[STR_specRevision],
         self[STR_uintnSize],
         self[STR_numberOfAlgorithms]) = struct.unpack("<16sIBBBBI", b[0:28])
        b = b[28:]
        self.sz += 28
        self[STR_digestSizes] = []
        num = self[STR_numberOfAlgorithms]
        while num:
            nextDigestSize = TCG_EfiSpecIdEventAlgorithmSize(b)
            self[STR_digestSizes].append(nextDigestSize)
            b = b[nextDigestSize.sz:]
            self.sz += nextDigestSize.sz
            num -= 1
        assert len(b) >= 1, "Incomplete TCG_EfiSpecIdEvent vendorInfoSize"
        (self[STR_vendorInfoSize],) = struct.unpack("<B", b[0:1])
        b = b[1:]
        self.sz += 1
        assert len(b) >= self[STR_vendorInfoSize], \
            "Incomplete TCG_EfiSpecIdEvent vendorInfo"
        (self[STR_vendorInfo],) = struct.unpack(f"<{self[STR_vendorInfoSize]}s",
                                                b[0:self[STR_vendorInfoSize]])
        b = b[self[STR_vendorInfoSize]:]
        self.sz += self[STR_vendorInfoSize]
        self.set_type(STR_EfiSpecIdEvent)

class TCG_EfiSpecIdEventAlgorithmSize(basedict):
    def __init__(self, b):
        super().__init__()
        assert len(b) >= 4, "Incomplete TCG_EfiSpecIdEventAlgorithmSize"
        (self[STR_algorithmId], self[STR_digestSize]) = struct.unpack("<HH",
                                                                      b[0:4])
        b = b[4:]
        self.sz += 4
        self.set_type(STR_EfiSpecIdEventAlgorithmSize)

if __name__ == '__main__':

    sys.argv.pop(0)

    if len(sys.argv) != 1:
        sys.exit(1)

    inputbuf = open(sys.argv[0], 'rb').read()

    #EmbedType = False
    mylog = TCG_EventLog(inputbuf)

    print(json.dumps(mylog, cls=JSONEncoder))
