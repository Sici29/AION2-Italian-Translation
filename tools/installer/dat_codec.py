"""AION2 v2 catalog codec. Same byte layout as the validated project writer."""
import struct
import lz4.block
from Crypto.Cipher import AES
from blake3 import blake3

def fstring(value):
    if all(ord(c)<128 for c in value):
        raw=value.encode('utf-8')+b'\0'; return struct.pack('<i',len(raw))+raw
    raw=value.encode('utf-16le')+b'\0\0'; return struct.pack('<i',-len(raw)//2)+raw

def read_string(raw,pos):
    length=struct.unpack_from('<i',raw,pos)[0]; pos+=4
    size=length if length>=0 else -length*2
    if pos+size>len(raw): raise ValueError('FString troncata')
    part=raw[pos:pos+size]
    if length>0:
        assert part[-1:]==b'\0'; value=part[:-1].decode('utf-8')
    elif length<0:
        assert part[-2:]==b'\0\0'; value=part[:-2].decode('utf-16le')
    else: value=''
    return value,pos+size

def header_key():
    def u64(value): return struct.unpack('<Q',blake3(value).digest()[:8])[0]
    root=u64(struct.pack('<Q',0xCD02190910CE83F6))
    seed=u64(b'L10NString_es-ES')
    return blake3(struct.pack('<QQII',root,seed,3,0)).digest()

def decode(data,key):
    assert struct.unpack_from('<I',data)[0]==2
    header=bytes(a^b for a,b in zip(data[4:20],header_key()))
    packed,kind,aligned,size=struct.unpack('<4I',header)
    assert kind==2 and aligned%16==0 and len(data)==aligned+20
    plain=AES.new(key,AES.MODE_ECB).decrypt(data[20:])
    raw=lz4.block.decompress(plain[32:32+packed],uncompressed_size=size)
    assert struct.unpack_from('<I',raw)[0]==1
    namespace,pos=read_string(raw,4); assert namespace=='AION2'
    count=struct.unpack_from('<I',raw,pos)[0]; pos+=4; result={}
    for _ in range(count):
        name,pos=read_string(raw,pos); value,pos=read_string(raw,pos)
        assert name not in result; result[name]=value
    assert len(result)==count and raw[pos:]==bytes(4)
    return result

def encode(entries,template,key):
    prefix=AES.new(key,AES.MODE_ECB).decrypt(template[20:])[:32]
    pieces=[struct.pack('<I',1),fstring('AION2'),struct.pack('<I',len(entries))]
    for name,value in entries.items(): pieces.extend((fstring(name),fstring(value)))
    pieces.append(bytes(4)); raw=b''.join(pieces)
    compressed=lz4.block.compress(raw,mode='high_compression',compression=9,store_size=False)
    aligned=(32+len(compressed)+15)&~15
    plain=prefix+compressed+bytes(aligned-32-len(compressed))
    header=struct.pack('<4I',len(compressed),2,aligned,len(raw))
    obfuscated=bytes(a^b for a,b in zip(header,header_key()))
    return struct.pack('<I',2)+obfuscated+AES.new(key,AES.MODE_ECB).encrypt(plain)
