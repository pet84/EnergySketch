# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Synthetic typed legacy records; no SDK binary data or customer fixtures."""
import math
import struct
from types import SimpleNamespace
import pytest
from plugins.archcontrol.adapter import _reader_package
from plugins.archcontrol.skp_metadata import shadow_north,model_dictionaries


def string(s):
    assert len(s)<255
    return b'\xff\xfe\xff'+bytes([len(s)])+s.encode('utf-16-le')


def new_class(name,schema=1):
    return struct.pack('<HHH',0xffff,schema,len(name))+name.encode()


def dictionary(name,values,new=False):
    body=b'\0\0\0'+b'\0'*4+string(name)
    for k,v in values.items():
        body+=string(k)+(b'\x0a'+string(v) if isinstance(v,str) else b'\x04'+struct.pack('<i',v))
    return (new_class('CAttributeNamed') if new else struct.pack('<H',0x8005))+body+string('')+b'\0'*4


def container(name,values,new=False):
    return (new_class('CAttributeContainer') if new else struct.pack('<H',0x8003))+b'\0\0\0'+dictionary(name,values,new)+b'\0\0'


@pytest.mark.parametrize('angle',[0,22.5,37.5,67.5,123,270,359.25])
def test_shadow_angle_from_root_tail_and_not_a_dictionary_named_north(angle):
    _,legacy=_reader_package()
    header=string('CShadowInfo')+struct.pack('<I',7)+string('TempShadowInfoNorthAngle')+struct.pack('<d',19)
    end=len(header)
    data=header+b'\0'*14+string('Praha')+string('ČR')+struct.pack('<6d',14.4,50.1,1,math.sin(math.radians(angle)),math.cos(math.radians(angle)),0)+b'\0\1\1\0'
    ar=SimpleNamespace(ver=17,r=SimpleNamespace(pos=end))
    assert shadow_north(legacy,ar,data)==angle
    assert shadow_north(legacy,SimpleNamespace(ver=18,r=ar.r),data) is None
    assert shadow_north(legacy,ar,data[:-18]) is None
    assert shadow_north(legacy,ar,data.replace(struct.pack('<I',7),struct.pack('<I',8),1)) is None


def test_root_dictionary_must_end_at_manager_boundary_not_embedded_entity_text():
    _,legacy=_reader_package()
    first=new_class('CVersionMap')+b'ignored-version-fields'+container('ModelProperties',{'IsClassified':0},True)
    decoy=container('ArchControl_LiveModel',{'metadata':'wrong embedded dictionary'})
    real=container('ArchControl_LiveModel',{'metadata':'{"projectId":"qa","revision":12}'})
    camera=new_class('CCamera',5)+b'\0'*139+string('')+b'\0'*33
    settings=(decoy+b'other-configuration').ljust(217,b'\0')
    assert len(settings)==217
    data=first+b'\0\0'+camera+settings+real+b'\0'*18+new_class('CMaterial')
    ar=SimpleNamespace(ver=17)
    assert model_dictionaries(legacy,ar,data)=={'ArchControl_LiveModel':{'metadata':'{"projectId":"qa","revision":12}'}}
    assert model_dictionaries(legacy,ar,data.replace(real,real+b'changed-boundary')) is None
    assert model_dictionaries(legacy,SimpleNamespace(ver=18),data) is None
    empty=first+b'\0\0'+camera+settings+b'\0\0'+b'\0'*18+new_class('CMaterial')
    assert model_dictionaries(legacy,ar,empty)=={}
