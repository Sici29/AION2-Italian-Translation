/** Generic packer. No game key, template, account token, or corpus is embedded. */
export const FOOTER_MAGIC='A2EXEFOOTERv1___';
export const FOOTER_BYTES=328;
export const ENVELOPE_KIND='aion2_autonomous_browser_payload';
const encoder=new TextEncoder();
const MANIFEST_KEYS=new Set(['schema_version','steam_build','runtime_locale','catalog_total','payload_sha256','technical_errors','deterministic_encoding','decoded_readback_equal','human_review_complete','runtime_verified','root_read_complete']);
const RECEIPT_KEYS=new Set(['schema_version','kind','project_id','build_id','base_patch','created_at_utc','payload_sha256','base_package_sha256','private_metadata_sha256','template_sha256','key_order_sha256','versions_sha256','source_identity_sha256','catalog_total','current_context_pending','technical_errors','deterministic_encoding','decoded_readback_equal','human_review_complete','runtime_verified','root_read_complete','account_tokens_in_receipt']);
const need=(ok,message)=>{if(!ok)throw Error(message);};
const bytes=value=>value instanceof Uint8Array?value:new Uint8Array(value);
const hash=async data=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data)),v=>v.toString(16).padStart(2,'0')).join('').toUpperCase();
function technical(object,keys,label){
  need(object&&typeof object==='object'&&!Array.isArray(object),'Invalid '+label);
  for(const [key,value] of Object.entries(object)){
    need(keys.has(key),'Unapproved '+label+' field: '+key);
    need(['string','boolean','number'].includes(typeof value),'Non-scalar '+label+' field');
    if(typeof value==='string')need(value.length<=300&&/^[\x20-\x7E]*$/.test(value),'Nontechnical/private '+label+' value');
    if(typeof value==='number')need(Number.isSafeInteger(value)&&value>=0,'Invalid '+label+' number');
  }
  need(object.technical_errors===0&&object.decoded_readback_equal===true&&object.deterministic_encoding===true,'Unverified '+label);
  need(object.human_review_complete===false&&object.runtime_verified===false,'Unsupported proof flags');
  if('root_read_complete'in object)need(object.root_read_complete===false,'Unsupported root proof');
}
function base64(data){let result='';const size=3*16384;for(let p=0;p<data.length;p+=size){let text='';for(const b of data.subarray(p,p+size))text+=String.fromCharCode(b);result+=btoa(text);}return result;}
const length=value=>{need(Number.isSafeInteger(value)&&value>0&&value<=64*1024*1024,'Invalid binary length');return value.toString(16).toUpperCase().padStart(16,'0');};
export async function packStandaloneExe({stubBytes,datBytes,manifest,receipt,expectedStubSha256,expectedStubLength}){
  const stub=bytes(stubBytes),dat=bytes(datBytes);
  need(stub.length===expectedStubLength&&stub[0]===77&&stub[1]===90,'Stub length/PE mismatch');
  need(/^[A-Fa-f0-9]{64}$/.test(expectedStubSha256||''),'Approved stub pin required');
  const stubSha=await hash(stub),datSha=await hash(dat);
  need(stubSha===expectedStubSha256.toUpperCase(),'Stub SHA mismatch');
  technical(manifest,MANIFEST_KEYS,'manifest');technical(receipt,RECEIPT_KEYS,'receipt');
  need(manifest.payload_sha256===datSha&&receipt.payload_sha256===datSha,'DAT SHA mismatch');
  need(manifest.steam_build==='26262663'&&manifest.runtime_locale==='es-ES'&&manifest.catalog_total===153297,'Wrong build/slot/count');
  need(receipt.build_id==='26262663'&&receipt.catalog_total===153297&&receipt.root_read_complete===false&&receipt.account_tokens_in_receipt===false,'Wrong receipt identity/privacy');
  const ordered=(value,keys)=>Object.fromEntries([...keys].filter(key=>key in value).map(key=>[key,value[key]]));
  const envelope=encoder.encode(JSON.stringify({schema_version:1,kind:ENVELOPE_KIND,dat_base64:base64(dat),manifest:ordered(manifest,MANIFEST_KEYS),receipt:ordered(receipt,RECEIPT_KEYS)}));
  need(envelope.every(b=>b>=32&&b<=126),'Envelope must be ASCII');
  const prefix=encoder.encode(FOOTER_MAGIC+'00000001'+length(stub.length)+length(envelope.length)+length(dat.length)+stubSha+await hash(envelope)+datSha);
  need(prefix.length===264,'Footer prefix size mismatch');
  const footer=encoder.encode(new TextDecoder().decode(prefix)+await hash(prefix));need(footer.length===FOOTER_BYTES,'Footer size mismatch');
  const result=new Uint8Array(stub.length+envelope.length+footer.length);result.set(stub);result.set(envelope,stub.length);result.set(footer,stub.length+envelope.length);
  return result;
}
