# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Bounded legacy metadata decoding, independent of Qt and any installed SDK.

Layout verified against SDK 2017 oracle fixtures, not copied SDK file data.
The geometry walk supplies the exact end of the root entity list. Shadow
schema 7 stores longitude/latitude/timezone then a unit north direction,
not the GeoReferenceNorthAngle or a style's TempShadowInfoNorthAngle.
Unsupported layouts remain unknown; they must not become an assumed zero.
"""
import math
import re
import struct


def shadow_north(legacy,archive,data):
    if archive.ver!=17:
        return None
    key=b'\xff\xfe\xff\x0b'+'CShadowInfo'.encode('utf-16-le')
    at=data.find(key,0,min(len(data),0x2000))
    if at<0 or data[at+len(key):at+len(key)+4]!=struct.pack('<I',7):
        return None
    try:
        r=legacy._R(data,archive.r.pos+14)
        city,country=r.utf16(),r.utf16()
        longitude,latitude,timezone,x,y,z=r.f64s(6)
        flags=r.raw(4)
        if len(city)>512 or len(country)>512 or not all(math.isfinite(v) for v in (longitude,latitude,timezone,x,y,z)) or abs(longitude)>180 or abs(latitude)>90 or abs(timezone)>24 or abs(x*x+y*y-1)>1e-8 or abs(z)>1e-10 or len(flags)!=4 or any(v not in (0,1) for v in flags):
            return None
        return round(math.degrees(math.atan2(x,y))%360,12)%360
    except (ValueError,IndexError,struct.error):
        return None


def model_dictionaries(legacy,archive,data):
    """Walk the prefix to a container ending at the model-manager boundary.

    The two pre-model class IDs come from the first real attribute container,
    with an explicitly checked declaration order (VersionMap, optional Dib).
    After ModelProperties come the optional preview, camera (schema 5),
    217 bytes of model settings, then the model attribute pointer. A typed
    container OR null must end exactly 18 bytes before the material manager.
    Both boundaries must agree; embedded PNG/entity strings cannot qualify.
    """
    if archive.ver!=17:
        return None
    declaration=lambda name: re.escape(b'\xff\xff')+b'..'+re.escape(struct.pack('<H',len(name))+name.encode())
    material=re.search(declaration('CMaterial'),data,re.S)
    if material:
        manager=material.start()
    else:
        layer=re.search(declaration('CLayer'),data,re.S)
        if layer is None:
            return None
        manager=layer.start()-9
    if manager>32*1024*1024:
        return None
    first=re.search(declaration('CAttributeContainer'),data[:manager],re.S)
    if first is None:
        return None
    preceding=[]
    for m in re.finditer(rb'\xff\xff..([\x01-\x30])\x00',data[:first.start()],re.S):
        name=data[m.end():m.end()+m.group(1)[0]]
        if re.fullmatch(rb'C[A-Za-z]+',name):
            preceding.append(name.decode())
    if preceding not in (['CVersionMap'],['CVersionMap','CDib']):
        return None
    try:
        ar=legacy._Archive(data,17)
        ar.readers.update(legacy._READERS)
        ar.next_slot=1+2*len(preceding)
        ar.walk_base=1
        ar.r.pos=first.start()
        _,_,initial=ar.read_object(ar.r,expect='CAttributeContainer')
        if 'ModelProperties' not in legacy._extract_legacy_attribute_dictionaries(initial):
            return None
        ar.read_object(ar.r,expect='CDib')
        ar.read_object(ar.r,expect='CCamera')
        if ar.class_schema.get('CCamera')!=5:
            return None
        ar.r.pos+=217
        _,_,value=ar.read_object(ar.r,expect='CAttributeContainer')
        if ar.r.pos!=manager-18:
            return None
        return legacy._extract_legacy_attribute_dictionaries(value)
    except (ValueError,IndexError,struct.error,RecursionError):
        return None
