import gzip,json,tempfile,unittest,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE/'tools/installer'));import public_compiler as c

class CompilerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.project=json.loads(gzip.decompress((HERE/'payload/italiano.json.gz').read_bytes()).decode('utf8'))
 def attempt(self,data,message):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);(p/'it.json').write_text(json.dumps(data),'utf8')
   with self.assertRaisesRegex(ValueError,message):c.compile_patch(p/'it.json',p/'patch.exe')
   self.assertFalse((p/'patch.exe').exists())
 def test_wrong_build_is_rejected(self):
  data={**self.project,'build_id':'0'};self.attempt(data,'altra build|altra|altr')
 def test_duplicate_key_is_rejected(self):
  data={**self.project,'entries':self.project['entries']+[self.project['entries'][0]]};self.attempt(data,'duplicata')
 def test_missing_key_is_rejected(self):
  data={**self.project,'entries':self.project['entries'][1:]};self.attempt(data,'Mancano chiavi')
 def test_protected_placeholder_is_rejected(self):
  rows=[dict(e) for e in self.project['entries']];row=next(e for e in rows if '{' in e['it']);row['it']+=' {injected}'
  self.attempt({**self.project,'entries':rows},'Tag, numeri, segnaposto')

if __name__=='__main__':unittest.main()
