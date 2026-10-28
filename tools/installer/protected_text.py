"""Block changed formatting tokens; never change a translated string."""
from collections import Counter
import re
BRACE=re.compile(r'\{[^{}\r\n]*\}')
ANGLE=re.compile(r'<[^<>\r\n]*>')
PRINTF=re.compile(r"%%|%(?:\d+\$)?[-+#0']*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlLjzt]*[diuoxXfFeEgGaAcspn]")

def numeric_sequence(text):
    text=BRACE.sub('',text); text=ANGLE.sub('',text)
    values=[]
    for value in re.findall(r'[-−+]?\d+(?:[., ]\d+)*(?:\s*%)?',text):
        value=value.replace('−','-').replace(' %','%')
        if re.fullmatch(r'[-+]?\d{1,3}(?:[., ]\d{3})+%?',value): value=re.sub(r'[., ]','',value)
        values.append(value)
    return values

def numeric_values(text):
    return Counter(numeric_sequence(text))

def validate(reference,candidate):
    if not isinstance(candidate,str): raise ValueError('Testo italiano non valido')
    if '\ufffd' in candidate or '\x00' in candidate: raise ValueError('Carattere non valido')
    if not candidate.strip() and reference.strip(): raise ValueError('Testo italiano vuoto')
    checks={
        'segnaposto':Counter(BRACE.findall(reference))==Counter(BRACE.findall(candidate)),
        'parentesi dei segnaposto':Counter(re.findall(r'[{}]',reference))==Counter(re.findall(r'[{}]',candidate)),
        'tag e ordine':ANGLE.findall(reference)==ANGLE.findall(candidate),
        'codici percentuali':Counter(PRINTF.findall(reference))==Counter(PRINTF.findall(candidate)),
        'ordine dei codici percentuali':[p for p in PRINTF.findall(reference) if p!='%%' and not re.match(r'%\d+\$',p)]==[p for p in PRINTF.findall(candidate) if p!='%%' and not re.match(r'%\d+\$',p)],
        'numeri':numeric_values(reference)==numeric_values(candidate),
        'valori numerici per riga':[numeric_sequence(line) for line in reference.split('\n')]==[numeric_sequence(line) for line in candidate.split('\n')],
        'a capo funzionali':reference.count('\n')==candidate.count('\n'),
        'sequenze letterali':candidate.count('\\n')==reference.count('\\n'),
    }
    failed=[name for name,ok in checks.items() if not ok]
    if failed: raise ValueError('Modifica bloccata: '+', '.join(failed))
    return checks
