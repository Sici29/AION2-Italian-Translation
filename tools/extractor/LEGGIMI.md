# Estrattore delle fonti originali

Sorgenti per manutentori. Legge i PAK del gioco posseduto, anche quando il DAT italiano è già installato. Estrae tutte le lingue presenti, comprese EN ed ES, con chiavi e hash.

Richiede Python e tools/requirements.txt; repak è incluso con licenze MIT/Apache. La libreria proprietaria oo2core_9_win64.dll non è redistribuita: usa la tua copia locale verificata accanto a repak.exe. Il comando --repak permette di indicare una cartella di strumenti già predisposta.

`python extract_sources.py --game "D:/SteamLibrary/steamapps/common/AION2"`

Per confrontare la prossima build aggiungi `--previous "catalogo_precedente/ARCHIVIO/source_catalog.json"`. Per la prima estrazione il programma produce soltanto il catalogo; non inventa differenze. Nessun catalogo originale è incluso nei sorgenti pubblici. Il laboratorio offline può caricare il catalogo completo con il tasto Fonti locali facoltative.
