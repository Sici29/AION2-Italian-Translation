"""Strict ASCII append framing; the append cannot shadow a PyInstaller MEI cookie."""
import base64,hashlib,json,re
MAGIC=b'A2EXEFOOTERv1___'
FOOTER_BYTES=328
MAX_BYTES=64*1024*1024
MANIFEST_KEYS={'schema_version','steam_build','runtime_locale','catalog_total','payload_sha256','technical_errors','deterministic_encoding','decoded_readback_equal','human_review_complete','runtime_verified','root_read_complete'}
RECEIPT_KEYS={'schema_version','kind','project_id','build_id','base_patch','created_at_utc','payload_sha256','base_package_sha256','private_metadata_sha256','template_sha256','key_order_sha256','versions_sha256','source_identity_sha256','catalog_total','current_context_pending','technical_errors','deterministic_encoding','decoded_readback_equal','human_review_complete','runtime_verified','root_read_complete','account_tokens_in_receipt'}
def need(ok,message):
    if not ok:raise ValueError(message)
def sha(value):return hashlib.sha256(value).hexdigest().upper()
def unique(pairs):
    out={}
    for key,value in pairs:
        need(key not in out,'Campo JSON duplicato');out[key]=value
    return out
def technical(value,keys):
    need(isinstance(value,dict) and set(value)<=keys,'Campi del manifest/receipt non ammessi')
    for field,item in value.items():
        need(type(item) in (str,int,bool),'Dato non tecnico nel receipt')
        if type(item) is str:need(len(item)<=300 and item.isascii() and all(32<=ord(c)<=126 for c in item),'Testo/credenziale non ammesso')
        if type(item) is int:need(0<=item<=2**53-1,'Numero del receipt non valido')
    need(type(value.get('technical_errors')) is int and value['technical_errors']==0 and value.get('decoded_readback_equal') is True and value.get('deterministic_encoding') is True,'Prova tecnica del payload assente')
    need(value.get('human_review_complete') is False and value.get('runtime_verified') is False,'Flag umani/runtime non ammessi')
    if 'root_read_complete' in value:need(value['root_read_complete'] is False,'Flag root non ammesso')
def read_executable(path):
    total=path.stat().st_size;need(FOOTER_BYTES<total<MAX_BYTES*3,'Dimensione EXE non valida')
    with path.open('rb') as stream:
        stream.seek(-FOOTER_BYTES,2);footer=stream.read(FOOTER_BYTES)
        need(footer[:16]==MAGIC and footer[16:24]==b'00000001','Payload autonomo assente o versione non supportata')
        need(all(32<=b<=126 for b in footer),'Footer non ASCII')
        need(re.fullmatch(b'[0-9A-F]{312}',footer[16:]),'Footer non canonico')
        need(sha(footer[:264])==footer[264:].decode(),'Hash footer non valido')
        sl,el,dl=[int(footer[p:p+16],16) for p in (24,40,56)]
        need(all(0<n<=MAX_BYTES for n in (sl,el,dl)) and total==sl+el+FOOTER_BYTES,'Lunghezze EXE incoerenti')
        stream.seek(0);stub=stream.read(sl);envelope=stream.read(el)
    need(stub[:2]==b'MZ' and sha(stub)==footer[72:136].decode(),'Stub EXE corrotto')
    need(sha(envelope)==footer[136:200].decode(),'Envelope corrotto')
    need(all(32<=b<=126 for b in envelope),'Envelope non ASCII')
    value=json.loads(envelope.decode('ascii'),object_pairs_hook=unique)
    need(set(value)=={'schema_version','kind','dat_base64','manifest','receipt'} and type(value['schema_version']) is int and value['schema_version']==1 and value['kind']=='aion2_autonomous_browser_payload','Schema payload non valido')
    text=value['dat_base64'];need(isinstance(text,str) and len(text)==4*((dl+2)//3),'Lunghezza base64 non valida')
    data=base64.b64decode(text,validate=True);need(len(data)==dl and base64.b64encode(data).decode()==text,'Base64 non canonico')
    digest=sha(data);need(digest==footer[200:264].decode(),'DAT corrotto')
    technical(value['manifest'],MANIFEST_KEYS);technical(value['receipt'],RECEIPT_KEYS)
    need(value['manifest'].get('payload_sha256')==digest==value['receipt'].get('payload_sha256'),'Pin DAT divergenti')
    return data,value['manifest'],value['receipt'],{'stub_sha256':sha(stub),'stub_bytes':sl,'envelope_sha256':sha(envelope),'dat_sha256':digest,'dat_bytes':dl,'footer_bytes':FOOTER_BYTES}
