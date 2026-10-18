# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Development-only oracle: installed SDK creates OUR fixtures, never bundled.

Official C API contracts: SUModelRef, SUShadowInfoRef, SUTypedValueRef and
SUAttributeDictionaryRef. No runtime dependency, proprietary bytes or DLLs
are distributed with the plugin. Input model is read-only, outputs stay in
the project's ignored .venv directory.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path


class Ref(C.Structure):
    _fields_ = [('ptr',C.c_void_p)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dll',type=Path,required=True)
    ap.add_argument('--model',type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / '.venv/skp-metadata-fixtures'
    output.mkdir(parents=True,exist_ok=True)
    dll = C.CDLL(str(args.dll))
    def api(name,argtypes,restype=C.c_int):
        f=getattr(dll,name);f.argtypes=argtypes;f.restype=restype
        return f
    def ok(value):
        if value!=0:
            raise RuntimeError('SDK result '+str(value))
    create=api('SUModelCreate',[C.POINTER(Ref)])
    load=api('SUModelCreateFromFile',[C.POINTER(Ref),C.c_char_p])
    release=api('SUModelRelease',[C.POINTER(Ref)])
    shadow=api('SUModelGetShadowInfo',[Ref,C.POINTER(Ref)])
    tvcreate=api('SUTypedValueCreate',[C.POINTER(Ref)])
    tvrelease=api('SUTypedValueRelease',[C.POINTER(Ref)])
    double=api('SUTypedValueSetDouble',[Ref,C.c_double])
    string=api('SUTypedValueSetString',[Ref,C.c_char_p])
    setshadow=api('SUShadowInfoSetValue',[Ref,C.c_char_p,Ref])
    getshadow=api('SUShadowInfoGetValue',[Ref,C.c_char_p,C.POINTER(Ref)])
    getdouble=api('SUTypedValueGetDouble',[Ref,C.POINTER(C.c_double)])
    getdict=api('SUModelGetAttributeDictionary',[Ref,C.c_char_p,C.POINTER(Ref)])
    setdict=api('SUAttributeDictionarySetValue',[Ref,C.c_char_p,Ref])
    save=api('SUModelSaveToFile',[Ref,C.c_char_p])
    api('SUInitialize',[],None)()
    original=hashlib.sha256(args.model.read_bytes()).hexdigest() if args.model else None
    report=[]
    try:
        for angle in (0.,37.5,123.,270.):
            model,info,value,dictionary = Ref(),Ref(),Ref(),Ref()
            try:
                ok(load(C.byref(model),str(args.model).encode('utf-8')) if args.model else create(C.byref(model)))
                ok(shadow(model,C.byref(info)))
                ok(tvcreate(C.byref(value)));ok(double(value,angle));ok(setshadow(info,b'NorthAngle',value))
                ok(getshadow(info,b'NorthAngle',C.byref(value)))
                measured=C.c_double();ok(getdouble(value,C.byref(measured)))
                assert abs(measured.value-angle)<1e-9
                metadata={'schema':1,'projectId':'fixture-project','northSource':'QA metadata witness'}
                ok(getdict(model,b'ArchControl_LiveModel',C.byref(dictionary)))
                ok(string(value,json.dumps(metadata).encode('utf-8')));ok(setdict(dictionary,b'metadata',value))
                path=output / (('customer-copy-' if args.model else 'blank-')+str(angle)+'.skp')
                ok(save(model,str(path).encode('utf-8')))
                report.append({'path':str(path),'north_angle':angle,'model_dictionary':metadata,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            finally:
                if value.ptr:tvrelease(C.byref(value))
                if model.ptr:release(C.byref(model))
    finally:
        api('SUTerminate',[],None)()
    if args.model:
        assert original==hashlib.sha256(args.model.read_bytes()).hexdigest()
    target=output / ('customer-manifest.json' if args.model else 'blank-manifest.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Created '+str(len(report))+' separate metadata fixtures; source unchanged.')


if __name__=='__main__':
    main()
